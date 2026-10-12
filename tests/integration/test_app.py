"""Callback and privacy-boundary tests that run without a browser."""

from __future__ import annotations

import asyncio
from copy import deepcopy
import json
from types import SimpleNamespace

import gradio as gr
from agents.tool_context import ToolContext

from src import app
import pytest

from src import ai_client
from src.ai_client import ModelReply
from src.catalog_policy import SCOPE_REFUSAL
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
from src.tools import TaskActivity, TaskToolLedger


def test_interrupt_accepts_input_while_actual_tool_is_blocked(run_async) -> None:
    from dataclasses import replace
    from agents import function_tool
    from agents.testing import ModelStep, ScriptedModel, assistant_message, function_call
    from src.accounts import lookup_account
    from src.conversation_runtime import SessionCoordinator
    from src.observability import TaskName
    from src.task_agents import create_task_agents

    async def scenario() -> None:
        entered = asyncio.Event()
        release = asyncio.Event()
        dispatched: list[str] = []

        @function_tool(name_override="account_lookup", failure_error_function=None)
        async def blocked_lookup(ctx: ToolContext[TaskToolLedger], account_number: str) -> str:
            ctx.context.authorize("account_lookup", account_number)
            ctx.context.claim(ctx.tool_call_id, "blocked-lookup-1")
            dispatched.append(account_number)
            entered.set()
            await release.wait()
            ctx.context.caller, outcome = lookup_account(ctx.context.caller, account_number)
            ctx.context.facts = replace(ctx.context.facts, lookup=outcome)
            ctx.context.complete("blocked-lookup-1", "Account found.")
            return "Account found."

        models = create_task_agents(
            conversation_model=ScriptedModel([
                ModelStep(output=[assistant_message(json.dumps({"action": "task", "task_name": TaskName.CUSTOMER_ACCOUNT, "detail_kind": "account_number"}))]),
                ModelStep(output=[function_call("delegate_to_task_agent", {"input": "Check account 123."}, call_id="delegate-1")]),
                ModelStep(output=[assistant_message(json.dumps({"action": "correction", "task_name": TaskName.CUSTOMER_ACCOUNT, "detail_kind": "account_number", "source_sequence": 3, "value": "456"}))]),
                ModelStep(output=[assistant_message('{"status":"clarification_required","message":"What is your zip code?"}')]),
            ]),
            task_model=ScriptedModel([
                ModelStep(output=[function_call("account_lookup", {"account_number": "123"}, call_id="lookup-1")]),
                ModelStep(output=[assistant_message('{"status":"clarification_required","summary":"Need ZIP."}')]),
            ]),
            task_tools=[blocked_lookup],
        )
        session = SessionCoordinator(agents=models)
        other = SessionCoordinator(agents=models)
        try:
            assert await app.conversation_send_event("Check account 123", session) == ""
            await asyncio.wait_for(entered.wait(), 1)
            worker = session.worker
            assert await asyncio.wait_for(app.conversation_send_event("Actually account 456", session), 1) == ""
            assert [item.content for item in session.dialogue.history if item.role == "user"] == ["Check account 123", "Actually account 456"]
            assert session.worker is worker and not worker.done()
            assert other.dialogue.history == () and other.worker is None
            release.set()
            await session.wait_until(lambda: session.proposal is not None)
            assert dispatched == ["123"]
            assert session.dialogue.history[-1].content == "Change the account from 123 to 456? Please reply Yes or No."
            assert not any("zip code" in item.content for item in session.dialogue.history)
            assert not worker.done()
        finally:
            await session.close()
            await other.close()

    run_async(scenario())


def state_from_result(result: app.CallbackResult) -> ActiveConversation:
    return result.state


def test_async_paused_refusal_preserves_task(monkeypatch, run_async) -> None:
    from agents.testing import ModelStep, ScriptedModel, assistant_message, function_call
    from src import task_runtime
    from src.conversation_runtime import SessionCoordinator
    from src.observability import TaskName
    from src.task_agents import create_task_agents
    from src.tools import TASK_TOOLS

    errors = []
    original = task_runtime._is_timeout_error

    def capture(error):
        errors.append(error)
        return original(error)

    monkeypatch.setattr(task_runtime, "_is_timeout_error", capture)

    async def boundary(text, history, **kwargs):
        steps = [ModelStep(output=[assistant_message(json.dumps({"action": "decline"}))])] if text == "unrelated" else [
            ModelStep(output=[assistant_message(json.dumps({"action": "task", "task_name": TaskName.CUSTOMER_ACCOUNT, "detail_kind": "account_number"}))]),
            ModelStep(output=[function_call("delegate_to_task_agent", {"input": "Account 123"}, call_id="delegate")]),
            ModelStep(output=[assistant_message('{"status":"clarification_required","message":"ignored"}')]),
        ]
        specialist = [] if text == "unrelated" else [
            ModelStep(output=[function_call("account_lookup", {"account_number": "123"}, call_id="lookup")]),
            ModelStep(output=[assistant_message('{"status":"completed","summary":"Done."}')]),
        ]
        agents = create_task_agents(conversation_model=ScriptedModel(steps), task_model=ScriptedModel(specialist), task_tools=TASK_TOOLS)
        return await task_runtime.run_customer_task(text, history, agents=agents, **kwargs)

    monkeypatch.setattr(app, "run_customer_task", boundary)

    async def scenario():
        session = SessionCoordinator()
        try:
            assert await session.accept("Account 123")
            await session.worker
            caller = session.task.caller
            assert await session.accept("unrelated")
            await session.worker
            assert errors == []
            assert session.task.caller == caller
            assert session.dialogue.history[-1].content == SCOPE_REFUSAL
        finally:
            await session.close()

    run_async(scenario())


@pytest.mark.parametrize("operation", ["reset", "close", "cancel", "session_end", "overflow"])
def test_async_lifecycle_invalidates_pending_work(operation, monkeypatch, run_async) -> None:
    from dataclasses import replace
    from src.accounts import CallerSession
    from src.conversation_runtime import SessionCoordinator
    from src.observability import TaskName

    async def scenario() -> None:
        entered, release = asyncio.Event(), asyncio.Event()
        calls = []

        async def boundary(text, history, **kwargs):
            calls.append(text)
            entered.set()
            try:
                await release.wait()
            except asyncio.CancelledError:
                pass
            ended = operation == "session_end"
            task = replace(begin_task(text, now=0), task_name=TaskName.CUSTOMER_ACCOUNT, status=TaskStatus.SESSION_ENDED if ended else TaskStatus.COMPLETED, last_active_at=None, caller=CallerSession(ended=ended))
            return TaskRunResult(task, ConversationResponse(status="session_ended" if ended else "completed", message="STALE-ANSWER"), TaskOutcome.SESSION_ENDED if ended else TaskOutcome.COMPLETED)

        monkeypatch.setattr(app, "run_customer_task", boundary)
        session, other = SessionCoordinator(), SessionCoordinator()
        try:
            assert await session.accept("original private input")
            await entered.wait()
            worker = session.worker
            if operation == "overflow":
                assert await session.accept("original private input")
                assert len(session.dialogue.inputs) == 1
                for number in range(10):
                    assert await session.accept(f"queued {number}")
                assert len(session.inbox) == 10
                assert await app.conversation_send_event("retain overflow", session) == "retain overflow"
                assert len(session.dialogue.inputs) == 11
                assert "retain overflow" not in repr(session.dialogue.history)
                assert "Too many" in session.dialogue.history[-1].content
                await session.reset()
            elif operation == "session_end":
                assert await session.accept("Account 456")
                release.set()
                await worker
                assert session.task.caller.ended and not session.inbox
                assert not await session.accept("Yes")
                assert calls == ["original private input"]
                assert "STALE-ANSWER" not in repr(session.dialogue.history)
            else:
                assert await session.accept("pending correction")
                await getattr(session, operation)()
                assert worker.done() and not session.inbox and session.proposal is None
                assert "STALE-ANSWER" not in repr(session.dialogue.history)
                if operation == "reset":
                    assert session.dialogue.history == () and session.task is None and not session.disposed
                elif operation == "close":
                    assert session.disposed and session.task is None and session.dialogue.history == ()
                else:
                    assert "Task canceled." in session.dialogue.history[-1].content
            assert other.dialogue.history == () and other.task is None and other.worker is None
        finally:
            release.set()
            await session.close()
            await other.close()

    run_async(scenario())


def test_async_fifty_session_capacity_and_responsiveness(monkeypatch, run_async) -> None:
    from time import monotonic
    from src.conversation_runtime import SessionCoordinator, _CAPACITY

    async def scenario() -> None:
        release = asyncio.Event()
        entered = asyncio.Event()
        count = 0

        async def boundary(text, history, **kwargs):
            nonlocal count
            count += 1
            if count == 50:
                entered.set()
            await release.wait()
            return TaskRunResult(replace_task(text), ConversationResponse(status="completed", message="Done."), TaskOutcome.COMPLETED)

        def replace_task(text):
            return TaskState(text, TaskStatus.COMPLETED, 0.01, None)

        monkeypatch.setattr(app, "run_customer_task", boundary)
        sessions = [SessionCoordinator() for _ in range(51)]
        try:
            for number, session in enumerate(sessions[:50]):
                assert await session.accept(f"session {number}")
            await asyncio.wait_for(entered.wait(), 1)
            assert not await sessions[50].accept("service overflow")
            assert sessions[50].dialogue.history[-1].content == "The service is busy. Please try sending this message again shortly."
            started = monotonic()
            for number, session in enumerate(sessions[:50]):
                assert await session.accept(f"detail {number}")
                projection = await app.conversation_render_event(session)
                assert projection[0][-1]["content"] == f"detail {number}"
                assert len(session.inbox) == 1
            elapsed = monotonic() - started
            assert elapsed < 1
            print(f"50-session blocked-boundary ingress/render: {elapsed * 1000:.2f} ms total")
            assert _CAPACITY[asyncio.get_running_loop()] == 50
        finally:
            await asyncio.gather(*(session.close() for session in sessions))
        assert _CAPACITY[asyncio.get_running_loop()] == 0

    run_async(scenario())


def test_async_retry_reuses_accepted_input_and_committed_facts(monkeypatch, run_async, capsys) -> None:
    from dataclasses import replace
    from src.catalog_policy import CatalogFacts
    from src.conversation_runtime import SessionCoordinator
    from src.observability import TaskName

    async def scenario() -> None:
        calls = []

        async def boundary(text, history, **kwargs):
            prior = kwargs["prior_task"]
            calls.append(text)
            if prior is None:
                task = replace(begin_task(text, now=0), status=TaskStatus.FAILED, last_active_at=None, task_name=TaskName.CURRENT_TIME, catalog_input=text, catalog_facts=CatalogFacts(timestamp="2026-10-11T12:00:00+00:00"), completed_step_ids=("r1-time-1",))
                return TaskRunResult(task, ConversationResponse(status="failed", message="PRIVATE-PROVIDER-ERROR"), TaskOutcome.FAILED)
            assert prior.completed_step_ids == ("r1-time-1",)
            assert prior.catalog_facts.timestamp is not None
            task = replace(prior, status=TaskStatus.COMPLETED)
            return TaskRunResult(task, ConversationResponse(status="completed", message="Done."), TaskOutcome.COMPLETED)

        monkeypatch.setattr(app, "run_customer_task", boundary)
        session = SessionCoordinator()
        try:
            assert await session.accept("private time request")
            await session.worker
            assert session.retry_input is not None
            await session.retry()
            await session.worker
            assert calls == ["private time request", "private time request"]
            assert len(session.dialogue.inputs) == 1 and session.retry_input is None
            assert "PRIVATE-PROVIDER-ERROR" not in repr(session.dialogue.history)
        finally:
            await session.close()

    run_async(scenario())
    records = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith("{")]
    outcomes = [record for record in records if record["component"] == "task_outcome"]
    assert len(outcomes) == 2 and outcomes[0]["task_id"] == outcomes[1]["task_id"]
    assert "private time request" not in json.dumps(records)


@pytest.mark.parametrize("decision", ["yes", "no", "latest", "early_zip", "switch", "cancel"])
def test_interrupt_confirmation_reconciles_committed_facts(decision, run_async, capsys) -> None:
    from dataclasses import replace
    from agents import function_tool
    from agents.testing import ModelStep, ScriptedModel, assistant_message, function_call
    from src.accounts import lookup_account
    from src.conversation_runtime import SessionCoordinator
    from src.observability import TaskName
    from src.task_agents import create_task_agents
    from src.tools import TASK_TOOLS

    async def scenario() -> None:
        entered, release = asyncio.Event(), asyncio.Event()
        dispatched = []

        @function_tool(name_override="account_lookup", failure_error_function=None)
        async def blocked_lookup(ctx: ToolContext[TaskToolLedger], account_number: str) -> str:
            await ctx.context.checkpoint("dispatch")
            ctx.context.authorize("account_lookup", account_number)
            step = f"r{ctx.context.control.revision}-lookup-{len(dispatched)}"
            ctx.context.claim(ctx.tool_call_id, step)
            dispatched.append(account_number)
            entered.set()
            await release.wait()
            ctx.context.caller, outcome = lookup_account(ctx.context.caller, account_number)
            ctx.context.facts = replace(ctx.context.facts, lookup=outcome)
            ctx.context.complete(step, "Account found.")
            await ctx.context.checkpoint("committed")
            return "Account found."

        def output(value):
            return ModelStep(output=[assistant_message(json.dumps(value))])

        action = "supplement" if decision == "early_zip" else "switch" if decision == "switch" else "cancel" if decision == "cancel" else "correction"
        interruption = {"action": action, "source_sequence": 3}
        if action in ("correction", "supplement"):
            interruption.update(detail_kind="zip_code" if decision == "early_zip" else "account_number", value="12345" if decision == "early_zip" else "456")
        if action == "switch":
            interruption["task_name"] = TaskName.CURRENT_TIME
        manager = [
            output({"action": "task", "task_name": TaskName.CUSTOMER_ACCOUNT, "detail_kind": "account_number"}),
            ModelStep(output=[function_call("delegate_to_task_agent", {"input": "Account 123"}, call_id="delegate-original")]),
            output(interruption),
        ]
        if decision == "latest":
            manager.extend([
                output({"action": "ambiguous", "source_sequence": 5}),
                output({"action": "correction", "source_sequence": 7, "detail_kind": "account_number", "value": "123"}),
            ])
        specialist = [ModelStep(output=[function_call("account_lookup", {"account_number": "123"}, call_id="lookup-original")])]
        if decision == "no":
            specialist.append(output({"status": "clarification_required", "summary": "Need ZIP."}))
            manager.append(output({"status": "clarification_required", "message": "FORBIDDEN-PROSE"}))
        elif decision != "cancel":
            target = "123" if decision == "latest" else "456"
            caller_text = "12345" if decision == "early_zip" else "Current time" if decision == "switch" else "Account " + target
            manager.extend([
                ModelStep(output=[function_call("delegate_to_task_agent", {"input": caller_text}, call_id="delegate-new")]),
                output({"status": "completed" if decision in ("early_zip", "switch") else "clarification_required", "message": "FORBIDDEN-PROSE"}),
            ])
            tool = "verify_account_zip" if decision == "early_zip" else "getCurrentDateTimeIso" if decision == "switch" else "account_lookup"
            arguments = {"zip_code": "12345"} if decision == "early_zip" else {} if decision == "switch" else {"account_number": target}
            specialist.extend([
                ModelStep(output=[function_call(tool, arguments, call_id="capability-new")]),
                output({"status": "completed", "summary": "Done."}),
            ])
        agents = create_task_agents(conversation_model=ScriptedModel(manager), task_model=ScriptedModel(specialist), task_tools=[blocked_lookup, *TASK_TOOLS[2:], TASK_TOOLS[0]])
        session = SessionCoordinator(agents=agents)
        try:
            assert await session.accept("Account 123")
            await asyncio.wait_for(entered.wait(), 1)
            original_id = session.task.task_id
            text = "12345" if decision == "early_zip" else "Current time" if decision == "switch" else "Cancel" if decision == "cancel" else "Account 456"
            assert await session.accept(text)
            release.set()
            frozen_seconds = 0.0
            if decision != "early_zip":
                await session.wait_until(lambda: session.proposal is not None)
                assert dispatched == ["123"]
                await app.conversation_render_event(session)
                frozen_seconds = session._control.active_seconds
                assert session._control.paused_at is not None and session._control.timeout.when() is None
                if decision == "latest":
                    version = session.proposal.version
                    assert await session.accept("Maybe")
                    await session.wait_until(lambda: len(session.dialogue.history) == 6)
                    assert session.proposal.version == version and dispatched == ["123"]
                    assert await session.accept("Account 123")
                    await session.wait_until(lambda: session.proposal is not None and session.proposal.version != version)
                    new_version = session.proposal.version
                    assert session.visible_proposal is None
                    assert await session.accept("Yes")
                    await session.wait_until(lambda: session.dialogue.history[-1].content == "Please reply Yes or No to the latest change question.")
                    assert session.proposal.version == new_version and dispatched == ["123"]
                    await app.conversation_render_event(session)
                    assert await session.accept("Yes")
                else:
                    assert await session.accept("No" if decision == "no" else "Yes")
            await asyncio.wait_for(session.worker, 2)
            assert "FORBIDDEN-PROSE" not in repr(session.dialogue.history)
            if decision == "no":
                assert dispatched == ["123"] and session.task.caller.current_account == "123"
                assert session.task.task_id == original_id
                assert session.dialogue.history[-1].content == "What is your zip code?"
            elif decision == "yes":
                assert dispatched == ["123", "456"] and session.task.caller.current_account == "456"
                assert session.task.caller.verified_account is None and session.task.task_id == original_id
                assert session.task.active_seconds >= frozen_seconds
                assert len(set(session.task.completed_step_ids)) == 2
            elif decision == "latest":
                assert dispatched == ["123", "123"] and session.task.caller.current_account == "123"
                assert session.task.task_id == original_id
            elif decision == "early_zip":
                assert session.task.caller.verified_account == "123"
                assert session.dialogue.history[-1].content == "Your account is verified."
                assert session.proposal is None
            elif decision == "switch":
                assert session.task.task_name is TaskName.CURRENT_TIME and session.task.task_id != original_id
                assert session.task.caller.current_account == "123"
                assert "Greenwich Mean Time" in session.dialogue.history[-1].content
            elif decision == "cancel":
                assert session.task.status is TaskStatus.CANCELED and dispatched == ["123"]
        finally:
            await session.close()

    run_async(scenario())
    diagnostics = capsys.readouterr().out
    assert "12345" not in diagnostics and "FORBIDDEN-PROSE" not in diagnostics


@pytest.fixture(autouse=True)
def fake_reply(monkeypatch):
    monkeypatch.setattr(
        ai_client,
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
        ("assistant", SCOPE_REFUSAL),
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


def test_retired_callback_never_invokes_a_failing_provider(monkeypatch) -> None:
    prior = app.send_message("previous", new_conversation()).state

    def fail(_: str, __: tuple) -> ModelReply:
        raise AssertionError("retired callback called provider")

    monkeypatch.setattr(ai_client, "generate_reply", fail)
    failed = app.send_message("retain me", prior)

    assert failed.outcome is Outcome.SENT
    assert len(failed.history) == 4
    assert failed.state.pending_text is None
    assert failed.history[-1]["content"] == SCOPE_REFUSAL
    assert not failed.retry_visible


def test_retired_callback_ignores_unrestricted_provider_output(monkeypatch) -> None:
    monkeypatch.setattr(ai_client, "generate_reply", lambda *_: ModelReply("FORBIDDEN"))

    failed = app.send_message("original", new_conversation())

    assert failed.outcome is Outcome.SENT
    assert failed.history[-1]["content"] == SCOPE_REFUSAL
    assert failed.state.pending_text is None
    assert not failed.retry_visible


def test_retry_uses_retained_input_without_duplicate_pairs(monkeypatch) -> None:
    failed = app.fail_submission(app.begin_submission(new_conversation(), "retry").state)
    monkeypatch.setattr(ai_client, "generate_reply", lambda *_: (_ for _ in ()).throw(AssertionError("provider called")))

    recovered = app.retry_message(failed.state)

    assert recovered.outcome is Outcome.SENT
    assert [(item["role"], item["content"]) for item in recovered.history] == [
        ("user", "retry"),
        ("assistant", SCOPE_REFUSAL),
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
    assert DiagnosticOutcome.TASK_REJECTED in snapshot["outcomes"]


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


def test_async_progress_is_published_once_as_chat_activity_changes(monkeypatch, run_async) -> None:
    from src.conversation_runtime import SessionCoordinator
    from src.observability import TaskName

    async def scenario() -> None:
        entered, release = asyncio.Event(), asyncio.Event()
        clock = [0.0]

        async def blocked_task(text: str, _history: tuple, *, progress, **_kwargs):
            progress.set(TaskActivity.LOOKING_UP_INFORMATION, TaskName.CURRENT_TIME)
            entered.set()
            await release.wait()
            task = TaskState(text, TaskStatus.COMPLETED, 0.01, None)
            return TaskRunResult(task, ConversationResponse(status="completed", message="The result is ready."), TaskOutcome.COMPLETED)

        monkeypatch.setattr("src.conversation_runtime.monotonic", lambda: clock[0])
        monkeypatch.setattr(app, "run_customer_task", blocked_task)
        session = SessionCoordinator()
        session.task = TaskState("prior clarification", TaskStatus.WAITING_FOR_CLARIFICATION, 1.0, None)
        try:
            assert await session.accept("get the current time")
            await asyncio.wait_for(entered.wait(), 1)
            initial = await app.conversation_render_event(session)
            assert len(initial) == 7
            assert [item.content for item in session.dialogue.history if item.role == "assistant"] == [
                "I'm working on that now."
            ]

            clock[0] = 5.0
            sampled = await app.conversation_render_event(session)
            progress_text = "I'm looking up information."
            assert any(item["content"] == progress_text for item in sampled[0])
            history_size = len(session.dialogue.history)
            await app.conversation_render_event(session)
            assert len(session.dialogue.history) == history_size

            progress = session._progress
            progress.set(TaskActivity.EVALUATING_RESULT, TaskName.CURRENT_TIME)
            clock[0] = 10.0
            changed = await app.conversation_render_event(session)
            assert any("evaluating the result" in item["content"] for item in changed[0])
            assert sum(item.content == progress_text for item in session.dialogue.history) == 1
        finally:
            release.set()
            await session.close()

    run_async(scenario())


def test_async_progress_is_suppressed_at_ninety_assistant_entries(monkeypatch, run_async) -> None:
    from src.chat import ChatMessage, Dialogue, MessageKind
    from src.conversation_runtime import SessionCoordinator

    async def scenario() -> None:
        clock = [5.0]
        release = asyncio.Event()

        async def hold_worker() -> None:
            await release.wait()

        monkeypatch.setattr("src.conversation_runtime.monotonic", lambda: clock[0])
        session = SessionCoordinator()
        session.dialogue = Dialogue(
            history=tuple(
                ChatMessage("assistant", f"message {index}", sequence=index + 1, kind=MessageKind.INFORMATION)
                for index in range(89)
            ),
            sequence=89,
        )
        session.worker = asyncio.create_task(hold_worker())
        try:
            first = await app.conversation_render_event(session)
            assert len(first) == 7 and session.dialogue.assistant_count == 90
            assert session.dialogue.history[-1].kind is MessageKind.PROGRESS

            session._progress.set(TaskActivity.LOOKING_UP_INFORMATION)
            clock[0] = 10.0
            await app.conversation_render_event(session)
            assert session.dialogue.assistant_count == 90
            assert not any(item.content == "I'm looking up information." for item in session.dialogue.history)
        finally:
            release.set()
            await session.close()

    run_async(scenario())


@pytest.mark.parametrize(
    ("content", "expected_notice"),
    [
        (" \t", "non-whitespace"),
        ("x" * 4_097, "4,096 Unicode code points"),
    ],
)
def test_async_rejected_ingress_uses_chat_feedback_without_accepting(content, expected_notice, run_async) -> None:
    from src.chat import MessageKind
    from src.conversation_runtime import SessionCoordinator

    async def scenario() -> None:
        session = SessionCoordinator()
        try:
            returned, same_session = await app.conversation_ingress_event(content, session)
            assert returned == content and same_session is session
            assert not session.dialogue.inputs and session.worker is None and not session.inbox
            assert session.dialogue.history[-1].kind is MessageKind.NOTICE
            assert expected_notice in session.dialogue.history[-1].content
            assert all(item.content != content for item in session.dialogue.history)

            await app.conversation_ingress_event(content, session)
            assert session.dialogue.assistant_count == 1
            projection = await app.conversation_render_event(session)
            assert len(projection) == 7
            assert not projection[3].visible
            assert expected_notice in projection[0][-1]["content"]
        finally:
            await session.close()

    run_async(scenario())


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
