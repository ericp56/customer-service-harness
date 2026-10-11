"""Callback tests for caller verification, session end, and account-number diagnostics."""

from __future__ import annotations

import json

import pytest

from src import app
from src.accounts import CallerSession
from src.chat import new_conversation
from src.observability import DiagnosticOutcome
from src.task_agents import ConversationResponse
from src.task_runtime import (
    SESSION_ENDED_MESSAGE,
    TaskOutcome,
    TaskRunResult,
    TaskState,
    TaskStatus,
)


def _ended_result() -> TaskRunResult:
    return TaskRunResult(
        TaskState(
            "12345",
            TaskStatus.SESSION_ENDED,
            0.1,
            None,
            caller=CallerSession(current_account="123", zip_attempts=2, ended=True),
        ),
        ConversationResponse(status="session_ended", message=SESSION_ENDED_MESSAGE),
        TaskOutcome.SESSION_ENDED,
    )


def test_session_end_shows_message_blocks_sending_and_offers_reset(monkeypatch, run_async) -> None:
    async def fake_task(*_args, **_kwargs) -> TaskRunResult:
        return _ended_result()

    monkeypatch.setattr(app, "run_customer_task", fake_task)

    async def collect() -> list[tuple[object, ...]]:
        return [output async for output in app.task_send_event("12345", new_conversation(), None)]

    final = run_async(collect())[-1]

    assert final[0][-1] == {"role": "assistant", "content": SESSION_ENDED_MESSAGE}
    assert "This session has ended." in final[4].value
    assert final[5].interactive is False
    assert final[6].visible is False
    assert final[7].visible is True


def test_ended_session_rejects_further_messages_without_running_a_task(monkeypatch, run_async) -> None:
    calls = 0

    async def fake_task(*_args, **_kwargs) -> TaskRunResult:
        nonlocal calls
        calls += 1
        return _ended_result()

    monkeypatch.setattr(app, "run_customer_task", fake_task)

    async def collect() -> list[tuple[object, ...]]:
        first = [output async for output in app.task_send_event("12345", new_conversation(), None)]
        state, task = first[-1][2], first[-1][3]
        second = [output async for output in app.task_send_event("another try", state, task)]
        return [first[-1], second[-1]]

    first_final, second_final = run_async(collect())

    assert calls == 1
    assert second_final[0] == first_final[0]
    assert "This session has ended." in second_final[4].value
    assert second_final[5].interactive is False


def test_reset_clears_the_ended_session() -> None:
    outputs = app.reset_task_event()

    assert outputs[3] is None
    assert outputs[5].interactive is True


def test_caller_session_carries_into_the_next_task(monkeypatch, run_async) -> None:
    seen: list[CallerSession | None] = []
    verified = CallerSession(current_account="456", verified_account="456")

    async def fake_task(text: str, _history: tuple, *, prior_task=None, caller=None) -> TaskRunResult:
        seen.append(caller)
        return TaskRunResult(
            TaskState(text, TaskStatus.COMPLETED, 0.1, None, caller=verified),
            ConversationResponse(status="completed", message="Done."),
            TaskOutcome.COMPLETED,
        )

    monkeypatch.setattr(app, "run_customer_task", fake_task)

    async def collect() -> None:
        first = [output async for output in app.task_send_event("verify me", new_conversation(), None)]
        state, task = first[-1][2], first[-1][3]
        _ = [output async for output in app.task_send_event("transfer me", state, task)]

    run_async(collect())

    assert seen == [None, verified]


def test_diagnostics_include_the_account_number_but_never_a_zip_code(monkeypatch, run_async, capsys) -> None:
    async def fake_task(*_args, **_kwargs) -> TaskRunResult:
        return TaskRunResult(
            TaskState(
                "12345",
                TaskStatus.COMPLETED,
                0.1,
                None,
                caller=CallerSession(current_account="123", verified_account="123"),
            ),
            ConversationResponse(status="completed", message="Verified."),
            TaskOutcome.COMPLETED,
        )

    monkeypatch.setattr(app, "run_customer_task", fake_task)

    async def collect() -> None:
        _ = [output async for output in app.task_send_event("12345", new_conversation(), None)]

    run_async(collect())
    output = capsys.readouterr().out

    assert '"account_number":"123"' in output
    assert "12345" not in output
    assert DiagnosticOutcome.TASK_COMPLETED.value in output


def test_outcome_line_carries_the_task_id_for_correlation(monkeypatch, run_async, capsys) -> None:
    task = TaskState("hello", TaskStatus.COMPLETED, 0.1, None)

    async def fake_task(*_args, **_kwargs) -> TaskRunResult:
        return TaskRunResult(
            task,
            ConversationResponse(status="completed", message="Hi."),
            TaskOutcome.COMPLETED,
        )

    monkeypatch.setattr(app, "run_customer_task", fake_task)

    async def collect() -> None:
        _ = [output async for output in app.task_send_event("hello", new_conversation(), None)]

    run_async(collect())
    outcome = next(
        json.loads(line)
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("{") and json.loads(line).get("message") == "task_completed"
    )

    assert outcome["task_id"] == task.task_id


def test_session_end_is_a_fixed_diagnostic_category() -> None:
    assert app.task_diagnostic_outcome(TaskOutcome.SESSION_ENDED) is DiagnosticOutcome.TASK_SESSION_ENDED
    assert app.task_status(TaskStatus.SESSION_ENDED) == (
        "alert",
        "This session has ended. Start a new conversation to continue.",
    )


def test_catalog_completion_logs_parent_task_name_across_resume(monkeypatch, run_async, capsys) -> None:
    from agents.testing import ModelStep, ScriptedModel, assistant_message

    from src.task_agents import create_task_agents
    from src.task_runtime import run_customer_task

    model = ScriptedModel([
        ModelStep(output=[assistant_message(
            '{"status":"clarification_required","message":"Account number?",'
            '"task_name":"Transfer to Customer Service"}'
        )]),
        ModelStep(output=[assistant_message(
            '{"status":"completed","message":"Contact support.",'
            '"task_result":{"status":"completed","summary":"Verified.",'
            '"task_name":"Retrieve customer account","question":null,"proposal":null}}'
        )]),
    ])
    agents = create_task_agents(conversation_model=model, task_model=ScriptedModel([]), task_tools=())

    async def task_boundary(text, history, **kwargs):
        return await run_customer_task(text, history, agents=agents, **kwargs)

    monkeypatch.setattr(app, "run_customer_task", task_boundary)

    async def scenario():
        first = [output async for output in app.task_send_event("help", new_conversation(), None)]
        return [output async for output in app.task_send_event("account", first[-1][2], first[-1][3])]

    final = run_async(scenario())[-1]
    records = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith("{")]
    [completion] = [record for record in records if record.get("message") == "task_completed"]
    assert completion["task_name"] == "Transfer to Customer Service"
    assert final[3].task_name.value == "Transfer to Customer Service"


@pytest.mark.parametrize("title", ["Retrieve the current time", "Retrieve customer account", "Transfer to Customer Service"])
def test_catalog_completion_names_reach_stdout(title, monkeypatch, run_async, capsys) -> None:
    from agents.testing import ModelStep, ScriptedModel, assistant_message

    from src.task_agents import create_task_agents
    from src.task_runtime import run_customer_task

    model = ScriptedModel([ModelStep(output=[assistant_message(json.dumps({
        "status": "completed", "message": "Done.", "task_name": title,
    }))])])
    agents = create_task_agents(conversation_model=model, task_model=ScriptedModel([]), task_tools=())

    async def task_boundary(text, history, **kwargs):
        return await run_customer_task(text, history, agents=agents, **kwargs)

    monkeypatch.setattr(app, "run_customer_task", task_boundary)

    async def scenario():
        return [output async for output in app.task_send_event("request", new_conversation(), None)]

    run_async(scenario())
    records = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith("{")]
    [completion] = [record for record in records if record.get("message") == "task_completed"]
    [outcome] = [record for record in records if record.get("component") == "task_outcome"]
    assert completion["task_name"] == outcome["task_name"] == title
