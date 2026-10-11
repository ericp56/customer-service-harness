"""Callback and privacy-boundary tests that run without a browser."""

from __future__ import annotations

import asyncio
from copy import deepcopy
import json
from types import SimpleNamespace

import gradio as gr

from src import app
import pytest

from src.ai_client import ModelReply
from src.chat import MAX_COMPLETED_PAIRS, ActiveConversation, Outcome, new_conversation
from src.observability import DiagnosticOutcome
from src.task_runtime import (
    TaskOutcome,
    TaskRunResult,
    TaskState,
    TaskStatus,
    begin_task,
    request_simulated_approval,
)
from src.task_agents import ConversationResponse
from src.tools import TaskActivity


def state_from_result(result: app.CallbackResult) -> ActiveConversation:
    return result.state


@pytest.fixture(autouse=True)
def fake_reply(monkeypatch):
    monkeypatch.setattr(
        app,
        "generate_reply",
        lambda text, history: ModelReply(f"Answer: {text}"),
    )


def test_send_callback_creates_one_exact_ordered_pair() -> None:
    content = "  hello\n世界 <tag>  "
    result = app.send_message(content, new_conversation())

    assert result.outcome is Outcome.SENT
    assert result.input_value == ""
    assert [(item["role"], item["content"]) for item in result.history] == [
        ("user", content),
        ("assistant", f"Answer: {content}"),
    ]
    assert result.state.pending_text is None


def test_history_is_transient_per_state_instance() -> None:
    result = app.send_message("first", new_conversation())

    assert len(result.history) == 2
    assert app.initial_state() == new_conversation()


def test_limit_preserves_history_and_requires_new_conversation() -> None:
    state = new_conversation()
    for index in range(MAX_COMPLETED_PAIRS):
        state = state_from_result(app.send_message(str(index), state))

    blocked = app.send_message("over limit", state)
    reset = app.start_new_conversation()

    assert blocked.outcome is Outcome.LIMIT_REACHED
    assert len(blocked.history) == MAX_COMPLETED_PAIRS * 2
    assert reset.state == new_conversation()
    assert reset.history == []


def test_callback_failure_retains_input_and_prior_history(monkeypatch) -> None:
    prior = app.send_message("previous", new_conversation()).state

    def fail(_: str, __: tuple) -> ModelReply:
        raise app.AIServiceError()

    monkeypatch.setattr(app, "generate_reply", fail)
    failed = app.send_message("retain me", prior)

    assert failed.outcome is Outcome.FAILED
    assert len(failed.history) == 2
    assert failed.state.pending_text == "retain me"
    assert "Retry" in failed.status_text


def test_empty_callback_output_is_a_retryable_failure(monkeypatch) -> None:
    monkeypatch.setattr(app, "generate_reply", lambda *_: ModelReply(""))

    failed = app.send_message("original", new_conversation())

    assert failed.outcome is Outcome.FAILED
    assert failed.history == []
    assert failed.state.pending_text == "original"
    assert failed.retry_visible


def test_retry_uses_retained_input_without_duplicate_pairs(monkeypatch) -> None:
    monkeypatch.setattr(app, "generate_reply", lambda *_: (_ for _ in ()).throw(app.AIServiceError()))
    failed = app.send_message("retry", new_conversation())
    monkeypatch.setattr(app, "generate_reply", lambda text, history: ModelReply(f"Answer: {text}"))

    recovered = app.retry_message(failed.state)

    assert recovered.outcome is Outcome.SENT
    assert [(item["role"], item["content"]) for item in recovered.history] == [
        ("user", "retry"),
        ("assistant", "Answer: retry"),
    ]


def test_sending_state_prevents_duplicates() -> None:
    sending = ActiveConversation(pending_text="already", submission_state=app.SubmissionState.SENDING)
    result = app.send_message("second", sending)

    assert result.outcome is Outcome.ALREADY_SENDING
    assert result.history == []


def test_validation_feedback_is_accessible_and_does_not_add_messages() -> None:
    blank = app.send_message(" \t", new_conversation())
    oversized = app.send_message("x" * 4097, new_conversation())

    assert blank.history == []
    assert blank.status_role == "alert"
    assert "non-whitespace" in blank.status_text
    assert oversized.history == []
    assert "4,096" in oversized.status_text


def test_diagnostics_are_content_free_and_fixed_cardinality() -> None:
    secret = "unique visitor secret <script>example</script>"
    result = app.send_message(secret, new_conversation())
    snapshot = app.diagnostics_snapshot()

    serialized = repr(snapshot)
    assert secret not in serialized
    assert "visitor" not in serialized.lower()
    assert result.outcome is Outcome.SENT
    assert DiagnosticOutcome.SUCCESS in snapshot["outcomes"]


def test_app_disables_rich_features_and_persistence() -> None:
    policy = app.privacy_configuration()

    assert policy == {
        "analytics_enabled": False,
        "share_enabled": False,
        "feedback_enabled": False,
        "uploads_enabled": False,
        "browser_persistence_enabled": False,
        "rich_content_enabled": False,
    }
    page = app.build_app()
    assert page.analytics_enabled is False
    config = page.get_config_file()
    chatbot = next(
        component
        for component in config["components"]
        if component["props"].get("elem_id") == "echo-conversation"
    )
    assert config["analytics_enabled"] is False
    assert chatbot["props"]["render_markdown"] is False
    assert chatbot["props"]["sanitize_html"] is True
    assert chatbot["props"]["allow_tags"] is False
    assert chatbot["props"]["allow_file_downloads"] is False
    assert not any(
        component["type"] in {"audio", "file", "image", "video"}
        for component in config["components"]
    )


def test_health_readiness_is_content_free() -> None:
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    try:
        assert app.health_status() == {"status": "ready"}
    finally:
        monkeypatch.undo()


@pytest.mark.parametrize(
    ("task_status", "expected_role", "expected_text"),
    [
        (TaskStatus.ACTIVE, "status", "I'm working on that now."),
        (TaskStatus.WAITING_FOR_CLARIFICATION, "status", "I need one detail to continue."),
        (TaskStatus.WAITING_FOR_APPROVAL, "alert", "Please review the proposed action to continue."),
        (TaskStatus.COMPLETED, "status", "Task completed."),
        (TaskStatus.FAILED, "alert", "The task couldn't be completed. You can try again."),
        (TaskStatus.CANCELED, "status", "Task canceled."),
        (TaskStatus.REJECTED, "status", "I didn't proceed with the proposed action."),
        (TaskStatus.TIMED_OUT, "alert", "This task took too long to finish. Please try again."),
    ],
)
def test_task_status_messages_are_fixed_and_accessible(
    task_status: TaskStatus,
    expected_role: str,
    expected_text: str,
) -> None:
    role, text = app.task_status(task_status)

    assert role == expected_role
    assert text == expected_text
    assert "checkpoint-fixture" not in text


def test_progress_status_rotation_uses_only_fixed_customer_safe_copy() -> None:
    assert app.progress_status(1) == ("status", "I'm still working on that.")
    assert app.progress_status(2) == ("status", "I'm continuing to work on that.")
    assert app.progress_status(3) == app.progress_status(1)


def test_progress_status_uses_known_activity_and_validated_task_name() -> None:
    from src.observability import TaskName

    lookup = SimpleNamespace(activity="looking_up_information", task_name=None)
    evaluation = SimpleNamespace(activity="evaluating_result", task_name=TaskName.CURRENT_TIME)
    unknown = SimpleNamespace(activity="unknown", task_name="PRIVATE-TEXT")

    assert app.progress_status(1, lookup) == ("status", "I'm looking up information.")
    assert app.progress_status(2, evaluation) == (
        "status",
        "I'm evaluating the result for: Retrieve the current time.",
    )
    assert app.progress_status(3, unknown) == app.progress_status(3)


def test_task_outcomes_map_to_fixed_diagnostic_categories() -> None:
    assert app.task_diagnostic_outcome(TaskOutcome.COMPLETED) is DiagnosticOutcome.TASK_COMPLETED
    assert app.task_diagnostic_outcome(TaskOutcome.CANCELED) is DiagnosticOutcome.TASK_CANCELED
    assert app.task_diagnostic_outcome(TaskOutcome.REJECTED) is DiagnosticOutcome.TASK_REJECTED
    assert app.task_diagnostic_outcome(TaskOutcome.TIMED_OUT) is DiagnosticOutcome.TASK_TIMEOUT
    assert app.task_diagnostic_outcome(TaskOutcome.DUPLICATE_CALL) is DiagnosticOutcome.TASK_UNSUPPORTED_CAPABILITY
    assert app.task_diagnostic_outcome(TaskOutcome.INVALID_CONFIGURATION) is DiagnosticOutcome.INVALID_CONFIGURATION


def test_task_invalid_configuration_emits_fixed_error_without_value(monkeypatch, run_async, capsys) -> None:
    async def invalid_task(*_args, **_kwargs) -> TaskRunResult:
        task = TaskState("secret request", TaskStatus.FAILED, 0.0, None)
        return TaskRunResult(
            task,
            ConversationResponse(status="failed", message="Try again."),
            TaskOutcome.INVALID_CONFIGURATION,
        )

    monkeypatch.setattr(app, "run_customer_task", invalid_task)

    async def collect() -> None:
        _ = [output async for output in app.task_send_event("private-effort-value", new_conversation(), None)]

    run_async(collect())
    payload = json.loads(capsys.readouterr().out.splitlines()[-1])

    assert payload["level"] == "ERROR"
    assert payload["message"] == "invalid OPENAI_REASONING configuration"
    assert "private-effort-value" not in json.dumps(payload)


def test_task_event_appends_generated_response_once(monkeypatch, run_async) -> None:
    async def fake_task(*_args, **_kwargs) -> TaskRunResult:
        return TaskRunResult(
            TaskState("find hours", TaskStatus.COMPLETED, 0.1, None),
            ConversationResponse(status="completed", message="Support is open weekdays."),
            TaskOutcome.COMPLETED,
        )

    monkeypatch.setattr(app, "run_customer_task", fake_task)

    async def collect() -> list[tuple[object, ...]]:
        return [
            output
            async for output in app.task_send_event("find hours", new_conversation(), None)
        ]

    outputs = run_async(collect())

    assert len(outputs) == 2
    assert outputs[0][4].value.find("I'm working on that now.") >= 0
    assert outputs[-1][0] == [
        {"role": "user", "content": "find hours"},
        {"role": "assistant", "content": "Support is open weekdays."},
    ]
    assert outputs[-1][1] == ""
    assert outputs[-1][3].status is TaskStatus.COMPLETED


def test_task_event_yields_progress_outside_chat_history(monkeypatch, run_async) -> None:
    async def fake_task(*_args, **_kwargs) -> TaskRunResult:
        await asyncio.sleep(0.04)
        return TaskRunResult(
            TaskState("slow lookup", TaskStatus.COMPLETED, 0.04, None),
            ConversationResponse(status="completed", message="Done."),
            TaskOutcome.COMPLETED,
        )

    monkeypatch.setattr(app, "run_customer_task", fake_task)

    async def collect() -> list[tuple[object, ...]]:
        return [
            output
            async for output in app.task_send_event(
                "slow lookup",
                new_conversation(),
                None,
                progress_interval_seconds=0.01,
            )
        ]

    outputs = run_async(collect())

    assert len(outputs) >= 2
    assert all(len(output[0]) == 0 for output in outputs[:-1])
    assert "I'm working on that now." in outputs[0][4].value
    assert all(
        any(message in output[4].value for message in ("I'm still working on that.", "I'm continuing to work on that."))
        for output in outputs[1:-1]
    )
    assert outputs[-1][0][-1]["content"] == "Done."


def test_task_event_samples_latest_activity_at_each_progress_tick(monkeypatch, run_async) -> None:
    async def fake_task(*_args, **kwargs) -> TaskRunResult:
        progress = kwargs.get("progress")
        assert progress is not None
        progress.set(TaskActivity.LOOKING_UP_INFORMATION)
        await asyncio.sleep(0.025)
        from src.observability import TaskName

        progress.set(TaskActivity.EVALUATING_RESULT, TaskName.CURRENT_TIME)
        await asyncio.sleep(0.025)
        return TaskRunResult(
            TaskState("current time", TaskStatus.COMPLETED, 0.05, None),
            ConversationResponse(status="completed", message="Done."),
            TaskOutcome.COMPLETED,
        )

    monkeypatch.setattr(app, "run_customer_task", fake_task)

    async def collect() -> list[tuple[object, ...]]:
        return [
            output
            async for output in app.task_send_event(
                "current time",
                new_conversation(),
                None,
                progress_interval_seconds=0.01,
            )
        ]

    outputs = run_async(collect())
    progress_copy = [output[4].value for output in outputs[1:-1]]

    assert any("I'm looking up information." in value for value in progress_copy)
    assert any("I'm evaluating the result for: Retrieve the current time." in value for value in progress_copy)
    assert all(output[0] == [] for output in outputs[:-1])


def test_approval_event_completes_simulation_once_and_rejects_replay() -> None:
    pending = request_simulated_approval(
        begin_task("change demo preference", now=0.0),
        "Change the sample preference.",
        now=1.0,
    ).state
    started = app.begin_submission(new_conversation(), "change demo preference")
    conversation = app.complete_submission(started.state, "Please review the proposed change.").state

    approved = app.approve_task_event(conversation, pending)
    replayed = app.approve_task_event(approved[2], approved[3])

    assert approved[3].status is TaskStatus.COMPLETED
    assert approved[3].completed_step_ids == ("simulated-consequential-action",)
    assert approved[9].visible is False
    assert approved[0][-1]["content"] == "The simulated action was approved and completed."
    assert replayed[3] == approved[3]
    assert "no longer awaiting" in replayed[4].value


def test_rejected_approval_does_not_complete_simulated_action() -> None:
    pending = request_simulated_approval(
        begin_task("change demo preference", now=0.0),
        "Change the sample preference.",
        now=1.0,
    ).state
    started = app.begin_submission(new_conversation(), "change demo preference")
    conversation = app.complete_submission(started.state, "Please review the proposed change.").state

    rejected = app.reject_task_event(conversation, pending)

    assert rejected[3].status is TaskStatus.REJECTED
    assert rejected[3].completed_step_ids == ()
    assert rejected[0][-1]["content"] == "I didn't proceed with the proposed action."


def test_reset_discards_pending_approval_state() -> None:
    reset = app.reset_task_event()

    assert reset[0] == []
    assert reset[2] == new_conversation()
    assert reset[3] is None
    assert "proposal" not in reset[4].value


def test_cancel_event_discards_pending_approval() -> None:
    pending = request_simulated_approval(
        begin_task("change demo preference", now=0.0),
        "Change the sample preference.",
        now=1.0,
    ).state
    current = app.complete_submission(
        app.begin_submission(new_conversation(), "change demo preference").state,
        "Please review the proposed change.",
    ).state

    canceled = app.cancel_task_event(current, pending)

    assert canceled[3].status is TaskStatus.CANCELED
    assert canceled[3].pending_proposal is None
    assert canceled[0][-1]["content"] == "Task canceled. No task steps were completed."


def test_cancel_event_reports_prior_completed_steps() -> None:
    task = TaskState(
        "continue lookup",
        TaskStatus.WAITING_FOR_CLARIFICATION,
        2.0,
        None,
        completed_step_ids=("lookup-hours-1",),
    )
    current = app.complete_submission(
        app.begin_submission(new_conversation(), "continue lookup").state,
        "Which day?",
    ).state

    canceled = app.cancel_task_event(current, task)

    assert "Some work completed before cancellation" in canceled[0][-1]["content"]
    assert "no further steps were started" in canceled[4].value


def test_task_diagnostics_and_stdout_exclude_customer_and_model_content(monkeypatch, run_async, capsys) -> None:
    sensitive_text = "private-task-content-7f3a"

    async def fake_task(text: str, _history: tuple, **_kwargs) -> TaskRunResult:
        task = TaskState(text, TaskStatus.COMPLETED, 0.01, None)
        response = ConversationResponse(status="completed", message="Synthetic result.")
        return TaskRunResult(task, response, TaskOutcome.COMPLETED)

    monkeypatch.setattr(app, "run_customer_task", fake_task)

    async def collect() -> None:
        async for _ in app.task_send_event(sensitive_text, new_conversation(), None):
            pass

    run_async(collect())
    snapshot = repr(app.diagnostics_snapshot()) + capsys.readouterr().out

    assert sensitive_text not in snapshot
    assert "Synthetic result." not in snapshot


def test_retry_resumes_failed_task_with_completed_step_ledger(monkeypatch, run_async) -> None:
    calls = 0

    async def fail_then_resume(
        text: str,
        _history: tuple,
        *,
        prior_task=None,
        progress=None,
        **_kwargs,
    ) -> TaskRunResult:
        nonlocal calls
        assert progress is not None
        calls += 1
        if prior_task is None:
            task = TaskState(
                text,
                TaskStatus.FAILED,
                4.0,
                None,
                turn_count=1,
                capability_call_ids=("call-1",),
                capability_step_ids=("lookup-hours-1",),
                completed_step_ids=("lookup-hours-1",),
                completed_step_results=("Support hours: weekdays.",),
            )
            response = ConversationResponse(status="failed", message="Please retry safely.")
            return TaskRunResult(task, response, TaskOutcome.FAILED)

        assert prior_task.completed_step_ids == ("lookup-hours-1",)
        task = TaskState(
            prior_task.request,
            TaskStatus.COMPLETED,
            prior_task.active_seconds + 0.01,
            None,
            turn_count=2,
            capability_call_ids=prior_task.capability_call_ids,
            capability_step_ids=prior_task.capability_step_ids,
            completed_step_ids=prior_task.completed_step_ids,
            completed_step_results=prior_task.completed_step_results,
        )
        response = ConversationResponse(status="completed", message="Completed without repeating lookup.")
        return TaskRunResult(task, response, TaskOutcome.COMPLETED)

    monkeypatch.setattr(app, "run_customer_task", fail_then_resume)

    async def first_attempt() -> list[tuple[object, ...]]:
        return [
            output
            async for output in app.task_send_event("retry without duplicate", new_conversation(), None)
        ]

    failed_outputs = run_async(first_attempt())
    failed_state = failed_outputs[-1][2]
    failed_task = failed_outputs[-1][3]

    async def retry_attempt() -> list[tuple[object, ...]]:
        return [output async for output in app.retry_task_event(failed_state, failed_task)]

    completed_outputs = run_async(retry_attempt())

    assert calls == 2
    assert completed_outputs[-1][0][-1]["content"] == "Completed without repeating lookup."
    assert completed_outputs[-1][3].completed_step_ids == ("lookup-hours-1",)
    assert completed_outputs[-1][3].completed_step_results == ("Support hours: weekdays.",)


def test_gradio_can_hold_pending_task_without_exposing_it_to_browser() -> None:
    checkpoint = TaskState(
        request="checkpoint-fixture",
        status=TaskStatus.WAITING_FOR_APPROVAL,
        active_seconds=1.0,
        last_active_at=None,
        pending_proposal="private approval proposal",
    )

    with gr.Blocks() as page:
        checkpoint_state = gr.State(value=checkpoint)

    copied_checkpoint = deepcopy(checkpoint_state.value)
    serialized_config = json.dumps(page.get_config_file(), default=str)

    assert isinstance(copied_checkpoint, TaskState)
    assert copied_checkpoint.pending_proposal == "private approval proposal"
    assert "checkpoint-fixture" not in serialized_config
    assert "private approval proposal" not in serialized_config


def test_gradio_generator_can_update_separate_status_and_be_canceled() -> None:
    async def task_event() -> tuple[str, str]:
        yield "Working", "server-state"

    def cancel_event() -> None:
        return None

    with gr.Blocks() as page:
        conversation = gr.Chatbot()
        status = gr.Textbox()
        task_state = gr.State(value="server-state")
        start = gr.Button("Start")
        cancel = gr.Button("Cancel")
        running = start.click(task_event, outputs=[status, task_state])
        cancel.click(cancel_event, cancels=[running], queue=False)

    config = page.get_config_file()
    dependencies = config["dependencies"]
    start_event = next(
        dependency
        for dependency in dependencies
        if dependency["outputs"] == [status._id, task_state._id]
    )
    cancel_event_config = next(dependency for dependency in dependencies if dependency["cancels"])
    components = {item["id"]: item for item in config["components"]}

    assert start_event["outputs"] == [status._id, task_state._id]
    assert conversation._id not in start_event["outputs"]
    assert cancel_event_config["cancels"] == [start_event["id"]]
    assert components[task_state._id]["type"] == "state"
