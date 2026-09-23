"""Callback and privacy-boundary tests that run without a browser."""

from __future__ import annotations

import json

from src import app
import pytest

from src.ai_client import ModelReply, ServiceUnavailableError
from src.chat import MAX_COMPLETED_PAIRS, ActiveConversation, Outcome, new_conversation
from src.observability import DiagnosticOutcome


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
    assert "could not be obtained" in failed.status_text
    assert "Try again" in failed.status_text
    assert failed.retry_visible


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


def test_missing_configuration_is_not_ready(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)

    assert app.health_status() == {"status": "not_ready"}


def test_failure_status_and_diagnostic_do_not_expose_content(monkeypatch, capsys) -> None:
    def fail(*_args):
        raise ServiceUnavailableError()

    monkeypatch.setattr(app, "generate_reply", fail)
    failed = app.send_message("unique visitor secret", new_conversation())
    captured = capsys.readouterr().out
    payload = json.loads(captured)

    assert failed.outcome is Outcome.FAILED
    assert failed.retry_visible
    assert "could not be obtained" in failed.status_text
    assert "Try again" in failed.status_text
    assert payload["message"] == "timeout_or_unavailable"
    assert payload["level"] == "ERROR"
    assert "unique visitor secret" not in captured
