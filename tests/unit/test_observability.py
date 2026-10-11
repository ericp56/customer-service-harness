import json

from src.observability import DiagnosticOutcome, Diagnostics, TaskProgressSnapshot


def _task_snapshot(**overrides) -> TaskProgressSnapshot:
    values = {
        "task_status": "active",
        "active_duration_ms": 250,
        "remaining_active_ms": 59_750,
        "turn_count": 2,
        "capability_count": 1,
        "completed_step_count": 1,
        "approval_pending": False,
        "account_attempts": 1,
        "zip_attempts": 0,
        "account_verified": False,
        "session_ended": False,
    }
    values.update(overrides)
    return TaskProgressSnapshot(**values)


def test_records_utc_json_line_to_stdout(capsys) -> None:
    Diagnostics().record(DiagnosticOutcome.SUCCESS, started_at=0)

    payload = json.loads(capsys.readouterr().out)
    assert payload["timestamp"].endswith("+00:00")
    assert payload["component"] == "chat_submission"
    assert payload["level"] == "INFO"
    assert payload["message"] == "success"


def test_error_record_redacts_urls_and_includes_source_locations(capsys) -> None:
    try:
        raise RuntimeError("failed at https://secret.example/v1")
    except RuntimeError as error:
        Diagnostics().record(DiagnosticOutcome.OPERATIONAL_FAILURE, started_at=0, error=error)

    payload = json.loads(capsys.readouterr().out)
    assert payload["level"] == "ERROR"
    assert "secret.example" not in payload["message"]
    assert all(":" in frame for frame in payload["stack"])


def test_account_number_is_emitted_only_when_well_formed(capsys) -> None:
    Diagnostics().record(DiagnosticOutcome.SUCCESS, started_at=0, account_number="123")
    assert json.loads(capsys.readouterr().out)["account_number"] == "123"

    for rejected in ("12345 Main St", "zip 12345", "1234567890123", ""):
        Diagnostics().record(DiagnosticOutcome.SUCCESS, started_at=0, account_number=rejected)
        output = capsys.readouterr().out
        assert "account_number" not in json.loads(output)
        assert rejected.strip() == "" or rejected not in output


def test_task_id_is_emitted_only_when_a_random_hex_value(capsys) -> None:
    valid = "a" * 32
    Diagnostics().record(DiagnosticOutcome.SUCCESS, started_at=0, task_id=valid)
    assert json.loads(capsys.readouterr().out)["task_id"] == valid

    for rejected in ("short", "G" * 32, "a" * 33, "my account 123"):
        Diagnostics().record(DiagnosticOutcome.SUCCESS, started_at=0, task_id=rejected)
        assert "task_id" not in json.loads(capsys.readouterr().out)


def test_completed_task_names_are_allowlisted(capsys) -> None:
    from src.observability import TaskName

    for name in TaskName:
        Diagnostics().record(DiagnosticOutcome.TASK_COMPLETED, started_at=0, task_name=name)
        assert json.loads(capsys.readouterr().out)["task_name"] == name.value
    Diagnostics().record(DiagnosticOutcome.TASK_COMPLETED, started_at=0, task_name="PRIVATE-TEXT")
    output = capsys.readouterr().out
    assert "task_name" not in json.loads(output)
    assert "PRIVATE-TEXT" not in output


def test_model_call_line_has_only_allowlisted_fields(capsys) -> None:
    from src.observability import record_model_call

    record_model_call(
        task_id="b" * 32,
        agent="task",
        call_index=2,
        outcome="success",
        started_at=0,
        input_tokens=10,
        output_tokens=5,
        total_tokens=15,
        cached_input_tokens=4,
        reasoning_tokens=1,
        usage_reported=True,
        message_items=0,
        tool_calls=1,
        tool="account_lookup",
    )

    payload = json.loads(capsys.readouterr().out)
    assert set(payload) == {
        "timestamp", "component", "level", "message", "step", "duration_ms", "task_id",
        "agent", "call_index", "outcome", "usage_reported", "input_tokens", "output_tokens",
        "total_tokens", "cached_input_tokens", "reasoning_tokens", "message_items",
        "tool_calls", "tool",
    }
    assert payload["step"] == "model_request"
    assert payload["input_tokens"] == 10
    assert isinstance(payload["duration_ms"], int) and payload["duration_ms"] >= 0


def test_failed_model_call_line_has_no_usage_or_content_fields(capsys) -> None:
    from src.observability import record_model_call

    record_model_call(task_id="c" * 32, agent="conversation", call_index=1, outcome="timeout", started_at=0)

    payload = json.loads(capsys.readouterr().out)
    assert payload["level"] == "ERROR"
    assert payload["outcome"] == "timeout"
    assert "input_tokens" not in payload
    assert "tool" not in payload


def test_model_call_snapshot_is_nested_and_allowlisted(capsys) -> None:
    from src.observability import record_model_call

    snapshot = _task_snapshot()
    record_model_call(
        task_id="e" * 32,
        agent="conversation",
        call_index=1,
        outcome="success",
        started_at=0,
        task_state=snapshot,
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["task_state"] == {
        "task_status": "active",
        "active_duration_ms": 250,
        "remaining_active_ms": 59_750,
        "turn_count": 2,
        "capability_count": 1,
        "completed_step_count": 1,
        "approval_pending": False,
        "account_attempts": 1,
        "zip_attempts": 0,
        "account_verified": False,
        "session_ended": False,
    }
    assert payload["task_id"] == "e" * 32


def test_task_outcome_line_has_fixed_fields_and_final_snapshot(capsys) -> None:
    from src.observability import record_task_outcome

    record_task_outcome(
        task_id="f" * 32,
        outcome="waiting_for_approval",
        started_at=0,
        task_state=_task_snapshot(task_status="waiting_for_approval", approval_pending=True),
    )

    payload = json.loads(capsys.readouterr().out)
    assert set(payload) == {
        "timestamp", "component", "level", "message", "step", "duration_ms",
        "task_id", "outcome", "task_state",
    }
    assert payload["component"] == "task_outcome"
    assert payload["step"] == "chat_submission"
    assert payload["outcome"] == "waiting_for_approval"
    assert payload["task_state"]["approval_pending"] is True


def test_task_snapshot_rejects_invalid_status_counts_and_boolean_types() -> None:
    import pytest

    for override in (
        {"task_status": "secret"},
        {"turn_count": -1},
        {"active_duration_ms": True},
        {"approval_pending": 1},
    ):
        with pytest.raises(ValueError):
            _task_snapshot(**override)


def test_task_outcome_serialization_failure_is_content_free_and_nonfatal(monkeypatch, capsys) -> None:
    from src import observability

    def fail_serialization(*_args, **_kwargs):
        raise TypeError("PRIVATE-TEXT")

    monkeypatch.setattr(observability.json, "dumps", fail_serialization)
    observability.record_task_outcome(
        task_id="a" * 32,
        outcome="completed",
        started_at=0,
        task_state=_task_snapshot(task_status="completed"),
    )

    assert capsys.readouterr().out == "diagnostic serialization failed\n"


def test_model_call_diagnostic_overhead_is_below_five_milliseconds(capsys) -> None:
    from time import perf_counter

    from src.observability import record_model_call

    snapshot = _task_snapshot()
    started = perf_counter()
    for call_index in range(100):
        record_model_call(
            task_id="b" * 32,
            agent="conversation",
            call_index=call_index + 1,
            outcome="success",
            started_at=started,
            input_tokens=10,
            output_tokens=5,
            total_tokens=15,
            usage_reported=True,
            task_state=snapshot,
        )
    average_seconds = (perf_counter() - started) / 100

    assert average_seconds < 0.005
    assert len(capsys.readouterr().out.splitlines()) == 100


def test_model_call_rejects_unsupported_values() -> None:
    import pytest

    from src.observability import record_model_call

    valid = {"task_id": "d" * 32, "agent": "task", "call_index": 1, "outcome": "success", "started_at": 0}
    for override in (
        {"task_id": "not-hex"},
        {"agent": "other"},
        {"outcome": "weird"},
        {"call_index": 0},
    ):
        with pytest.raises(ValueError):
            record_model_call(**{**valid, **override})


def test_timing_records_only_allowlisted_step_and_duration(capsys) -> None:
    from src.observability import record_timing

    record_timing("model_request", 0)
    payload = json.loads(capsys.readouterr().out)
    assert payload["step"] == "model_request"
    assert isinstance(payload["duration_ms"], int)
    assert payload["duration_ms"] >= 0
