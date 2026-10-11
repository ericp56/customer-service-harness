from __future__ import annotations

import asyncio
import json
from contextlib import suppress

from agents import Usage
from agents.testing import ModelStep, ScriptedModel, assistant_message, function_call

from src.accounts import CallerSession
from src.task_agents import create_task_agents
from src.task_runtime import TaskState, TaskStatus, _task_progress_snapshot, run_customer_task
from src.tools import TASK_TOOLS

_FINAL = (
    '{"status":"completed","message":"%s",'
    '"task_result":{"status":"completed","summary":"Done.","question":null,"proposal":null}}'
)
_CLARIFY = (
    '{"status":"clarification_required","message":"%s",'
    '"task_result":{"status":"clarification_required","summary":"Need.","question":"Q?","proposal":null}}'
)
_SPECIALIST_DONE = '{"status":"completed","summary":"Done.","question":null,"proposal":null}'


def _route(task_name: str = "Retrieve customer account", detail_kind: str = "none") -> str:
    return json.dumps({"action": "task", "task_name": task_name, "detail_kind": detail_kind, "decline_remainder": False})


def _lines(capsys) -> list[dict]:
    return [record for record in _records(capsys) if record.get("component") == "model_call"]


def _records(capsys) -> list[dict]:
    found = []
    for raw in capsys.readouterr().out.splitlines():
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        found.append(payload)
    return found


def _usage(input_tokens: int, output_tokens: int) -> Usage:
    return Usage(
        requests=1,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
    )


def _delegating_agents(tool_name: str, arguments: dict, reply: str):
    return create_task_agents(
        conversation_model=ScriptedModel(
            [
                ModelStep(output=[assistant_message(_route(
                    "Retrieve the current time" if tool_name == "getCurrentDateTimeIso" else "Retrieve customer account",
                    "account_number" if tool_name == "account_lookup" else "none",
                ))], usage=_usage(5, 1)),
                ModelStep(
                    output=[function_call("delegate_to_task_agent", {"input": "Do it."}, call_id="d-1")],
                    usage=_usage(11, 3),
                ),
                ModelStep(output=[assistant_message(reply)], usage=_usage(40, 9)),
            ]
        ),
        task_model=ScriptedModel(
            [
                ModelStep(output=[function_call(tool_name, arguments, call_id="t-1")], usage=_usage(20, 4)),
                ModelStep(output=[assistant_message(_SPECIALIST_DONE)], usage=_usage(30, 6)),
            ]
        ),
        task_tools=TASK_TOOLS,
    )


def _single_reply_agents(reply: str):
    status = json.loads(reply)["status"]
    steps = (
        [ModelStep(output=[assistant_message(_route())]), ModelStep(output=[assistant_message(reply)])]
        if status in ("clarification_required", "approval_required")
        else [ModelStep(output=[assistant_message('{"action":"help","task_name":null,"detail_kind":"none","decline_remainder":false}')])]
    )
    return create_task_agents(
        conversation_model=ScriptedModel(steps),
        task_model=ScriptedModel([]),
        task_tools=(),
    )


def test_one_line_per_model_call_with_role_sequence_tokens_and_shape(run_async, capsys) -> None:
    agents = _delegating_agents("getCurrentDateTimeIso", {}, _FINAL % "It is noon.")

    result = run_async(run_customer_task("What time is it?", (), agents=agents))
    lines = _lines(capsys)

    assert [line["agent"] for line in lines] == ["conversation", "conversation", "task", "task", "conversation"]
    assert [line["call_index"] for line in lines] == [1, 2, 3, 4, 5]
    assert [line["outcome"] for line in lines] == ["success"] * 5
    assert [line["input_tokens"] for line in lines] == [5, 11, 20, 30, 40]
    assert [line["output_tokens"] for line in lines] == [1, 3, 4, 6, 9]
    assert [line["total_tokens"] for line in lines] == [6, 14, 24, 36, 49]
    assert all(line["usage_reported"] is True for line in lines)
    assert [line.get("tool") for line in lines] == [
        None,
        "delegate_to_task_agent",
        "getCurrentDateTimeIso",
        None,
        None,
    ]
    assert [(line["message_items"], line["tool_calls"]) for line in lines] == [(1, 0), (0, 1), (0, 1), (1, 0), (1, 0)]
    assert all(isinstance(line["duration_ms"], int) and line["duration_ms"] >= 0 for line in lines)
    assert all(line["step"] == "model_request" for line in lines)
    assert {line["task_id"] for line in lines} == {result.task.task_id}


def test_call_snapshots_show_live_capability_progress_and_one_final_outcome(run_async, capsys) -> None:
    agents = _delegating_agents("getCurrentDateTimeIso", {}, _FINAL % "It is noon.")

    result = run_async(run_customer_task("What time is it?", (), agents=agents))
    records = _records(capsys)
    calls = [record for record in records if record["component"] == "model_call"]
    [outcome] = [record for record in records if record["component"] == "task_outcome"]
    snapshots = [call["task_state"] for call in calls]

    assert [snapshot["turn_count"] for snapshot in snapshots] == [1, 2, 2, 2, 3]
    assert [snapshot["capability_count"] for snapshot in snapshots] == [0, 0, 0, 1, 1]
    assert [snapshot["completed_step_count"] for snapshot in snapshots] == [0, 0, 0, 1, 1]
    assert all(snapshot["task_status"] == "active" for snapshot in snapshots)
    assert all(snapshot["active_duration_ms"] >= 0 for snapshot in snapshots)
    assert all(0 <= snapshot["remaining_active_ms"] <= 60_000 for snapshot in snapshots)
    assert outcome["outcome"] == "completed"
    assert outcome["task_state"]["completed_step_count"] == 1
    assert outcome["task_id"] == result.task.task_id == calls[0]["task_id"]
    assert sum(record["component"] == "task_outcome" for record in records) == 1


def test_waiting_and_early_exit_outcomes_are_logged_once(run_async, capsys) -> None:
    clarified = run_async(run_customer_task("start", (), agents=_single_reply_agents(_CLARIFY % "More?")))
    clarification_records = _records(capsys)
    [clarification] = [record for record in clarification_records if record["component"] == "task_outcome"]
    assert clarification["outcome"] == "waiting_for_clarification"
    assert clarification["task_state"]["task_status"] == "waiting_for_clarification"

    approval_reply = (
        '{"status":"approval_required","message":"Review the change.",'
        '"task_result":{"status":"approval_required","summary":"Ready.",'
        '"question":null,"proposal":"PRIVATE-PROPOSAL"}}'
    )
    approved_wait = run_async(
        run_customer_task(
            "PRIVATE-REQUEST PRIVATE-ZIP-999",
            (),
            agents=_single_reply_agents(approval_reply),
            caller=CallerSession(
                current_account="PRIVATE-ACCOUNT",
                account_attempts=2,
                zip_attempts=1,
                verified_account="PRIVATE-ACCOUNT",
            ),
        )
    )
    approval_records = _records(capsys)
    [approval] = [record for record in approval_records if record["component"] == "task_outcome"]
    assert approval["outcome"] == "failed"
    assert approval["task_state"]["approval_pending"] is False
    assert approval["task_state"]["account_attempts"] == 2
    assert approval["task_state"]["zip_attempts"] == 1
    assert approval["task_state"]["account_verified"] is True
    for secret in ("PRIVATE-REQUEST", "PRIVATE-ZIP-999", "PRIVATE-ACCOUNT", "PRIVATE-PROPOSAL"):
        assert secret not in json.dumps(approval_records)

    ended = run_async(
        run_customer_task(
            "not logged",
            (),
            caller=CallerSession(current_account="123", account_attempts=3, zip_attempts=2, ended=True),
        )
    )
    ended_records = _records(capsys)
    [session_ended] = [record for record in ended_records if record["component"] == "task_outcome"]
    assert session_ended["outcome"] == "session_ended"
    assert session_ended["task_state"]["session_ended"] is True
    assert session_ended["task_state"]["account_attempts"] == 3
    assert session_ended["task_state"]["zip_attempts"] == 2
    assert not [record for record in ended_records if record["component"] == "model_call"]
    assert clarified.task.task_id == clarification["task_id"]
    assert approved_wait.task.task_id == approval["task_id"]
    assert ended.task.task_id == session_ended["task_id"]


def test_task_progress_snapshot_excludes_customer_wait_from_active_time() -> None:
    active = TaskState("private", TaskStatus.ACTIVE, 12.0, 50.0)
    waiting = TaskState("private", TaskStatus.WAITING_FOR_CLARIFICATION, 12.0, None)

    live = _task_progress_snapshot(active, now=53.0)
    paused = _task_progress_snapshot(waiting, now=500.0)

    assert (live.active_duration_ms, live.remaining_active_ms) == (15_000, 45_000)
    assert (paused.active_duration_ms, paused.remaining_active_ms) == (12_000, 48_000)


def test_missing_usage_is_reported_as_zero_with_a_flag(run_async, capsys) -> None:
    run_async(run_customer_task("hello", (), agents=_single_reply_agents(_FINAL % "Hi.")))

    [line] = _lines(capsys)

    assert line["usage_reported"] is False
    assert (line["input_tokens"], line["output_tokens"], line["total_tokens"]) == (0, 0, 0)
    assert (line["cached_input_tokens"], line["reasoning_tokens"]) == (0, 0)


def test_unknown_tool_names_are_reported_as_other(run_async, capsys) -> None:
    agents = create_task_agents(
        conversation_model=ScriptedModel(
            [
                ModelStep(output=[function_call("not_a_real_tool", {}, call_id="x-1")]),
                ModelStep(output=[assistant_message(_FINAL % "Sorry.")]),
            ]
        ),
        task_model=ScriptedModel([]),
        task_tools=(),
    )

    run_async(run_customer_task("odd", (), agents=agents))
    lines = _lines(capsys)

    assert lines[0]["tool"] == "other"
    assert "not_a_real_tool" not in json.dumps(lines)


def test_lines_never_contain_prompts_replies_arguments_or_caller_values(run_async, capsys) -> None:
    agents = _delegating_agents("account_lookup", {"account_number": "123"}, _CLARIFY % "SECRET-REPLY zip?")

    run_async(run_customer_task("SECRET-PROMPT 98765", (), agents=agents))
    output = json.dumps(_records(capsys))

    for sensitive in ("SECRET-PROMPT", "SECRET-REPLY", "98765", "123", "12345", "Do it.", "t-1", "d-1"):
        assert sensitive not in output
    assert "account_number" not in output


def test_failed_call_records_error_outcome_without_error_text(run_async, capsys) -> None:
    class FailingModel(ScriptedModel):
        async def get_response(self, *_args, **_kwargs):
            raise RuntimeError("secret provider detail")

    agents = create_task_agents(
        conversation_model=FailingModel([]),
        task_model=ScriptedModel([]),
        task_tools=(),
    )

    run_async(run_customer_task("hello", (), agents=agents))
    records = _records(capsys)
    [line] = [record for record in records if record["component"] == "model_call"]
    [outcome] = [record for record in records if record["component"] == "task_outcome"]

    assert line["outcome"] == "error"
    assert line["level"] == "ERROR"
    assert "secret provider detail" not in json.dumps(line)
    assert "input_tokens" not in line
    assert outcome["outcome"] == "failed"


def test_timed_out_call_records_timeout_outcome(run_async, capsys) -> None:
    class TimingOutModel(ScriptedModel):
        async def get_response(self, *_args, **_kwargs):
            raise TimeoutError

    agents = create_task_agents(
        conversation_model=TimingOutModel([]),
        task_model=ScriptedModel([]),
        task_tools=(),
    )

    result = run_async(run_customer_task("hello", (), agents=agents))
    records = _records(capsys)
    [line] = [record for record in records if record["component"] == "model_call"]
    [outcome] = [record for record in records if record["component"] == "task_outcome"]

    assert line["outcome"] == "timeout"
    assert result.task.status is TaskStatus.TIMED_OUT
    assert outcome["outcome"] == "timed_out"


def test_canceled_call_records_canceled_outcome(run_async, capsys) -> None:
    class HangingModel(ScriptedModel):
        async def get_response(self, *_args, **_kwargs):
            await asyncio.sleep(30)

    agents = create_task_agents(
        conversation_model=HangingModel([]),
        task_model=ScriptedModel([]),
        task_tools=(),
    )

    async def scenario() -> None:
        task = asyncio.create_task(run_customer_task("hello", (), agents=agents))
        await asyncio.sleep(0.05)
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    run_async(scenario())
    records = _records(capsys)
    [line] = [record for record in records if record["component"] == "model_call"]
    [outcome] = [record for record in records if record["component"] == "task_outcome"]

    assert line["outcome"] == "canceled"
    assert outcome["outcome"] == "canceled"


def test_invalid_configuration_has_fixed_task_outcome(run_async, capsys, monkeypatch) -> None:
    from src.ai_client import InvalidConfigurationError

    def invalid_configuration():
        raise InvalidConfigurationError()

    monkeypatch.setattr("src.task_runtime.load_configuration", invalid_configuration)

    result = run_async(run_customer_task("private request", ()))
    records = _records(capsys)
    [outcome] = [record for record in records if record["component"] == "task_outcome"]

    assert result.outcome.name == "INVALID_CONFIGURATION"
    assert outcome["outcome"] == "failed"
    assert "private request" not in json.dumps(records)
    assert not [record for record in records if record["component"] == "model_call"]


def test_concurrent_tasks_have_distinct_ids_and_separate_sequences(run_async, capsys) -> None:
    async def both():
        return await asyncio.gather(
            run_customer_task("first", (), agents=_single_reply_agents(_FINAL % "One.")),
            run_customer_task("second", (), agents=_single_reply_agents(_FINAL % "Two.")),
        )

    first, second = run_async(both())
    lines = _lines(capsys)

    assert first.task.task_id != second.task.task_id
    assert {line["task_id"] for line in lines} == {first.task.task_id, second.task.task_id}
    assert [line["call_index"] for line in lines] == [1, 1]


def test_task_id_persists_across_clarification_and_call_index_restarts(run_async, capsys) -> None:
    first = run_async(run_customer_task("start", (), agents=_single_reply_agents(_CLARIFY % "More?")))
    second = run_async(
        run_customer_task("more", (), agents=_single_reply_agents(_FINAL % "Done."), prior_task=first.task)
    )
    lines = _lines(capsys)

    assert first.task.status is TaskStatus.WAITING_FOR_CLARIFICATION
    assert second.task.task_id == first.task.task_id
    assert [line["task_id"] for line in lines] == [first.task.task_id] * 3
    assert [line["call_index"] for line in lines] == [1, 2, 1]
