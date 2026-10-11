from __future__ import annotations

import asyncio
from types import SimpleNamespace

from agents import ModelTimeoutError
from agents.testing import ModelStep, ScriptedModel, assistant_message, function_call

from src.ai_client import AIServiceConfiguration
from src.chat import ChatMessage
from src.task_runtime import (
    TaskOutcome,
    TaskState,
    TaskStatus,
    accrue_active_time,
    begin_agent_turn,
    begin_task,
    _conversation_input,
    cancel_task,
    complete_task,
    complete_task_step,
    fail_task,
    pause_task,
    record_capability_invocation,
    remaining_active_seconds,
    request_simulated_approval,
    resolve_simulated_approval,
    resume_task,
    run_customer_task,
)
from src.task_agents import ConversationResponse, create_task_agents
from src.tools import TASK_TOOLS, TaskActivity, TaskProgress


def test_active_work_budget_pauses_while_waiting_for_customer() -> None:
    task = begin_task("synthetic lookup", now=10.0)
    task = accrue_active_time(task, now=22.0).state
    paused = pause_task(task, TaskStatus.WAITING_FOR_APPROVAL, now=25.0)

    assert paused.outcome is TaskOutcome.PAUSED
    assert paused.state.active_seconds == 15.0
    assert paused.state.status is TaskStatus.WAITING_FOR_APPROVAL

    resumed = resume_task(paused.state, now=300.0)
    active = accrue_active_time(resumed.state, now=305.0)

    assert resumed.outcome is TaskOutcome.RESUMED
    assert active.state.active_seconds == 20.0
    assert active.state.status is TaskStatus.ACTIVE


def test_sixty_second_active_budget_times_out() -> None:
    task = begin_task("synthetic lookup", now=0.0)

    timed_out = accrue_active_time(task, now=60.0)

    assert timed_out.outcome is TaskOutcome.TIMED_OUT
    assert timed_out.state.status is TaskStatus.TIMED_OUT
    assert timed_out.state.active_seconds == 60.0


def test_resumed_task_uses_only_remaining_active_time() -> None:
    near_limit = TaskState(
        "synthetic lookup",
        TaskStatus.WAITING_FOR_CLARIFICATION,
        59.75,
        None,
    )

    assert remaining_active_seconds(near_limit) == 0.25


def test_clarification_context_is_carried_in_resume_input() -> None:
    prior_task = TaskState(
        "Find support hours",
        TaskStatus.WAITING_FOR_CLARIFICATION,
        3.0,
        None,
        continuation_context=("specialist found weekday hours",),
    )
    history = (ChatMessage("assistant", "Which day should I check?"),)

    resumed_input = _conversation_input(history, "Weekdays", prior_task)

    assert resumed_input[0] == {"role": "assistant", "content": "Which day should I check?"}
    assert resumed_input[1]["role"] == "assistant"
    assert "specialist found weekday hours" in resumed_input[1]["content"]
    assert resumed_input[-1] == {"role": "user", "content": "Weekdays"}


def test_monotonic_clock_regression_does_not_rewind_active_marker() -> None:
    task = begin_task("synthetic lookup", now=10.0)

    unchanged = accrue_active_time(task, now=9.0)

    assert unchanged.outcome is TaskOutcome.ACTIVE
    assert unchanged.state.active_seconds == 0.0
    assert unchanged.state.last_active_at == 10.0


def test_task_allows_eight_turns_and_rejects_the_ninth() -> None:
    task = begin_task("synthetic lookup", now=0.0)

    for _ in range(8):
        turn = begin_agent_turn(task)
        assert turn.outcome is TaskOutcome.TURN_STARTED
        task = turn.state

    rejected = begin_agent_turn(task)

    assert rejected.outcome is TaskOutcome.TURN_LIMIT
    assert rejected.state.status is TaskStatus.FAILED
    assert rejected.state.turn_count == 8


def test_only_one_capability_call_is_accepted_per_turn() -> None:
    task = begin_agent_turn(begin_task("synthetic lookup", now=0.0)).state
    first = record_capability_invocation(task, "call-1", "lookup-1")
    second = record_capability_invocation(first.state, "call-2", "lookup-2")

    assert first.outcome is TaskOutcome.CAPABILITY_ACCEPTED
    assert second.outcome is TaskOutcome.CAPABILITY_LIMIT
    assert second.state.capability_call_ids == ("call-1",)


def test_completed_steps_and_call_identifiers_cannot_be_replayed() -> None:
    task = begin_agent_turn(begin_task("synthetic lookup", now=0.0)).state
    accepted = record_capability_invocation(task, "call-1", "lookup-1")
    completed = complete_task_step(accepted.state, "lookup-1")
    next_turn = begin_agent_turn(completed.state)

    duplicate_call = record_capability_invocation(next_turn.state, "call-1", "lookup-2")
    replayed_step = record_capability_invocation(next_turn.state, "call-2", "lookup-1")

    assert completed.outcome is TaskOutcome.STEP_COMPLETED
    assert duplicate_call.outcome is TaskOutcome.DUPLICATE_CALL
    assert replayed_step.outcome is TaskOutcome.DUPLICATE_STEP
    assert duplicate_call.state.completed_step_ids == ("lookup-1",)


def test_canceled_task_is_terminal() -> None:
    task = begin_task("synthetic lookup", now=0.0)
    canceled = cancel_task(task)
    attempted_turn = begin_agent_turn(canceled.state)

    assert canceled.outcome is TaskOutcome.CANCELED
    assert attempted_turn.outcome is TaskOutcome.INVALID_TRANSITION
    assert attempted_turn.state.status is TaskStatus.CANCELED


def test_completion_and_failure_are_terminal_outcomes() -> None:
    task = begin_task("synthetic lookup", now=0.0)
    completed = complete_task(task)
    failed = fail_task(task)

    assert completed.outcome is TaskOutcome.COMPLETED
    assert completed.state.status is TaskStatus.COMPLETED
    assert failed.outcome is TaskOutcome.FAILED
    assert failed.state.status is TaskStatus.FAILED
    assert begin_agent_turn(completed.state).outcome is TaskOutcome.INVALID_TRANSITION


def test_simulated_approval_is_one_shot_and_has_no_side_effect() -> None:
    task = begin_task("simulate an action", now=0.0)
    pending = request_simulated_approval(task, "Update the demo service preference.", now=2.0)

    assert pending.outcome is TaskOutcome.PAUSED
    assert pending.state.status is TaskStatus.WAITING_FOR_APPROVAL
    assert pending.state.completed_step_ids == ()

    approved = resolve_simulated_approval(pending.state, approved=True)
    replayed = resolve_simulated_approval(approved.state, approved=True)

    assert approved.outcome is TaskOutcome.COMPLETED
    assert approved.state.completed_step_ids == ("simulated-consequential-action",)
    assert replayed.outcome is TaskOutcome.INVALID_TRANSITION
    assert replayed.state == approved.state


def test_rejected_simulated_approval_never_completes_action() -> None:
    pending = request_simulated_approval(
        begin_task("simulate an action", now=0.0),
        "Update the demo service preference.",
        now=1.0,
    )

    rejected = resolve_simulated_approval(pending.state, approved=False)

    assert rejected.outcome is TaskOutcome.REJECTED
    assert rejected.state.status is TaskStatus.REJECTED
    assert rejected.state.completed_step_ids == ()


def test_runtime_executes_scripted_agents_and_completes_without_provider_calls(run_async) -> None:
    task_model = ScriptedModel(
        [
            ModelStep(
                output=[
                    assistant_message(
                        '{"status":"completed","summary":"Support is open weekdays.",'
                        '"question":null,"proposal":null}'
                    )
                ]
            )
        ]
    )
    conversation_model = ScriptedModel(
        [
            ModelStep(
                output=[
                    function_call(
                        "delegate_to_task_agent",
                        {"input": "Find the synthetic support hours."},
                        call_id="delegate-1",
                    )
                ]
            ),
            ModelStep(
                output=[
                    assistant_message(
                        '{"status":"completed","message":"Support is open weekdays.",'
                        '"task_result":{"status":"completed","summary":"Support is open weekdays.",'
                        '"question":null,"proposal":null}}'
                    )
                ]
            ),
        ]
    )
    agents = create_task_agents(
        conversation_model=conversation_model,
        task_model=task_model,
        task_tools=(),
    )

    progress = TaskProgress(TaskActivity.PROCESSING)
    result = run_async(run_customer_task("Find support hours.", (), agents=agents, progress=progress))

    assert result.response.message == "Support is open weekdays."
    assert result.task.status is TaskStatus.COMPLETED
    assert result.task.turn_count == 2
    assert progress.activity is None
    assert progress.task_name is None


def test_runtime_resumes_clarification_with_original_active_time_budget(run_async) -> None:
    initial = TaskState(
        "Find support hours",
        TaskStatus.ACTIVE,
        0.0,
        0.0,
        turn_count=2,
    )
    paused = pause_task(initial, TaskStatus.WAITING_FOR_CLARIFICATION, now=3.0)
    conversation_model = ScriptedModel(
        [
            ModelStep(
                output=[
                    assistant_message(
                        '{"status":"completed","message":"Support is open weekdays.",'
                        '"task_result":null}'
                    )
                ]
            )
        ]
    )
    agents = create_task_agents(
        conversation_model=conversation_model,
        task_model=ScriptedModel([]),
        task_tools=(),
    )

    result = run_async(
        run_customer_task(
            "Weekdays",
            (ChatMessage("user", "Find support hours"), ChatMessage("assistant", "Which day?")),
            agents=agents,
            prior_task=paused.state,
        )
    )

    assert result.task.request == "Find support hours"
    assert result.task.active_seconds >= 3.0
    assert result.task.turn_count == 1
    assert result.task.status is TaskStatus.COMPLETED


def test_manager_turn_budget_applies_to_each_caller_message(monkeypatch, run_async) -> None:
    captured = {}

    async def final_one_turn(*_args, **kwargs):
        captured["max_turns"] = kwargs["max_turns"]
        return SimpleNamespace(
            final_output=ConversationResponse(status="completed", message="Completed."),
            raw_responses=[object()],
        )

    monkeypatch.setattr("src.task_runtime.Runner.run", final_one_turn)
    prior_task = TaskState(
        "continue task",
        TaskStatus.WAITING_FOR_CLARIFICATION,
        10.0,
        None,
        turn_count=7,
    )
    agents = create_task_agents(
        conversation_model=ScriptedModel([]),
        task_model=ScriptedModel([]),
        task_tools=(),
    )

    result = run_async(
        run_customer_task("answer", (), agents=agents, prior_task=prior_task)
    )

    assert captured["max_turns"] == 8
    assert result.task.turn_count == 1
    assert result.outcome is TaskOutcome.COMPLETED


def test_run_timeout_returns_fixed_timed_out_result_without_raising(monkeypatch, run_async) -> None:
    async def hang_then_time_out(*_args, **_kwargs):
        raise TimeoutError

    monkeypatch.setattr("src.task_runtime.Runner.run", hang_then_time_out)
    agents = create_task_agents(
        conversation_model=ScriptedModel([]),
        task_model=ScriptedModel([]),
        task_tools=(),
    )

    result = run_async(run_customer_task("slow request", (), agents=agents))

    assert result.outcome is TaskOutcome.TIMED_OUT
    assert result.task.status is TaskStatus.TIMED_OUT
    assert result.response.message == "This task took too long to finish. Please try again."


def test_invalid_configuration_returns_fixed_failure_without_secret_details(run_async) -> None:
    result = run_async(
        run_customer_task(
            "private request",
            (),
            configuration=AIServiceConfiguration("", "", None),
        )
    )

    assert result.task.status is TaskStatus.FAILED
    assert result.response.status == "failed"
    assert result.response.message == "I couldn't complete that task. Please try again."
    assert "private request" not in result.response.message


def test_model_attempt_timeout_maps_to_fixed_task_timeout(monkeypatch, run_async) -> None:
    calls = []

    async def timeout(*_args, **_kwargs):
        calls.append("runner_called")
        raise ModelTimeoutError(10.0)

    monkeypatch.setattr("src.task_runtime.Runner.run", timeout)
    agents = create_task_agents(
        conversation_model=ScriptedModel([]),
        task_model=ScriptedModel([]),
        task_tools=(),
    )

    result = run_async(run_customer_task("private request", (), agents=agents))

    assert calls == ["runner_called"]
    assert result.outcome is TaskOutcome.FAILED
    assert result.task.status is TaskStatus.FAILED
    assert result.response.message == "I couldn't complete that task. Please try again."


def test_model_failure_consumes_active_budget_and_does_not_reset_on_retry(monkeypatch, run_async) -> None:
    async def timeout_after_work(*_args, **_kwargs):
        await asyncio.sleep(0.02)
        raise ModelTimeoutError(10.0)

    monkeypatch.setattr("src.task_runtime.Runner.run", timeout_after_work)
    agents = create_task_agents(
        conversation_model=ScriptedModel([]),
        task_model=ScriptedModel([]),
        task_tools=(),
    )
    prior_task = TaskState(
        "retry task",
        TaskStatus.WAITING_FOR_CLARIFICATION,
        50.0,
        None,
        turn_count=1,
    )

    result = run_async(
        run_customer_task("more details", (), agents=agents, prior_task=prior_task)
    )

    assert result.task.status is TaskStatus.FAILED
    assert result.task.active_seconds > prior_task.active_seconds


def test_actual_synthetic_tool_call_is_recorded_in_task_state(run_async) -> None:
    task_model = ScriptedModel(
        [
            ModelStep(
                output=[
                    function_call(
                        "lookupServiceInformation",
                        {"topic": "hours", "step_id": "lookup-hours-1"},
                        call_id="tool-call-1",
                    )
                ]
            ),
            ModelStep(
                output=[
                    assistant_message(
                        '{"status":"completed","summary":"Support is open weekdays.",'
                        '"question":null,"proposal":null}'
                    )
                ]
            ),
        ]
    )
    conversation_model = ScriptedModel(
        [
            ModelStep(
                output=[
                    function_call(
                        "delegate_to_task_agent",
                        {"input": "Find the synthetic support hours."},
                        call_id="delegate-tool-call",
                    )
                ]
            ),
            ModelStep(
                output=[
                    assistant_message(
                        '{"status":"completed","message":"Support is open weekdays.",'
                        '"task_result":{"status":"completed","summary":"Support is open weekdays.",'
                        '"question":null,"proposal":null}}'
                    )
                ]
            ),
        ]
    )
    agents = create_task_agents(
        conversation_model=conversation_model,
        task_model=task_model,
        task_tools=TASK_TOOLS,
    )

    result = run_async(run_customer_task("Find support hours.", (), agents=agents))

    assert result.task.capability_call_ids == ("tool-call-1",)
    assert result.task.completed_step_ids == ("lookup-hours-1",)
    assert result.task.completed_step_results == (
        "Support is available Monday through Friday, 09:00 to 17:00 UTC.",
    )