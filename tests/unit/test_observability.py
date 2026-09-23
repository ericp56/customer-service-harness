import json

from src.observability import DiagnosticOutcome, Diagnostics


def test_records_utc_json_line_to_stdout(capsys) -> None:
    Diagnostics().record(DiagnosticOutcome.SUCCESS, started_at=0)

    payload = json.loads(capsys.readouterr().out)
    assert payload["timestamp"].endswith("+00:00")
    assert payload["component"] == "chat_submission"
    assert payload["level"] == "INFO"
    assert payload["message"] == "success"


def test_error_record_uses_fixed_outcome_and_source_locations(capsys) -> None:
    try:
        raise RuntimeError("failed at https://secret.example/v1 with sk-testsecret")
    except RuntimeError as error:
        Diagnostics().record(DiagnosticOutcome.OPERATIONAL_FAILURE, started_at=0, error=error)

    captured = capsys.readouterr().out
    payload = json.loads(captured)
    assert payload["level"] == "ERROR"
    assert payload["message"] == "operational_failure"
    assert "secret.example" not in captured
    assert "sk-testsecret" not in captured
    assert all(":" in frame for frame in payload["stack"])


def test_serialization_failure_writes_content_free_fallback(monkeypatch, capsys) -> None:
    def explode(*_args, **_kwargs):
        raise TypeError("cannot serialize https://secret.example/v1")

    monkeypatch.setattr("src.observability.json.dumps", explode)
    Diagnostics().record(DiagnosticOutcome.SUCCESS, started_at=0)

    captured = capsys.readouterr().out
    assert captured.strip() == "diagnostic serialization failed"
    assert "secret.example" not in captured


def test_timing_records_only_allowlisted_step_and_duration(capsys) -> None:
    from src.observability import record_timing

    record_timing("model_request", 0)
    payload = json.loads(capsys.readouterr().out)
    assert payload["step"] == "model_request"
    assert isinstance(payload["duration_ms"], int)
    assert payload["duration_ms"] >= 0
