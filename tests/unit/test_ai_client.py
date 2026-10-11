from types import SimpleNamespace
import json

import pytest

from src.ai_client import (
    AIServiceConfiguration,
    AIServiceError,
    build_agent_model,
    build_agent_run_config,
    create_async_client,
    generate_reply,
    load_configuration,
)
from src.chat import ChatMessage, ToolInvocation


def configuration() -> AIServiceConfiguration:
    return AIServiceConfiguration("key", "model", None)


def test_configuration_rejects_missing_values_and_non_https_url() -> None:
    with pytest.raises(AIServiceError):
        load_configuration({})
    with pytest.raises(AIServiceError):
        load_configuration({"OPENAI_API_KEY": "key", "OPENAI_MODEL": "model", "OPENAI_BASE_URL": "http://x"})


@pytest.mark.parametrize("effort", ["none", "minimal", "low", "medium", "high", "xhigh", "max"])
def test_configuration_accepts_recognized_reasoning_effort(effort: str) -> None:
    config = load_configuration({"OPENAI_API_KEY": "key", "OPENAI_MODEL": "model", "OPENAI_REASONING": effort})

    assert config.reasoning_effort == effort


@pytest.mark.parametrize("effort", [None, "", "   "])
def test_blank_reasoning_effort_uses_provider_default(effort: str | None) -> None:
    environ = {"OPENAI_API_KEY": "key", "OPENAI_MODEL": "model"}
    if effort is not None:
        environ["OPENAI_REASONING"] = effort

    assert load_configuration(environ).reasoning_effort is None


def test_reasoning_effort_is_trimmed_and_unknown_values_are_rejected() -> None:
    config = load_configuration(
        {"OPENAI_API_KEY": "key", "OPENAI_MODEL": "model", "OPENAI_REASONING": "  low  "}
    )

    assert config.reasoning_effort == "low"
    with pytest.raises(AIServiceError):
        load_configuration({"OPENAI_API_KEY": "key", "OPENAI_MODEL": "model", "OPENAI_REASONING": " LOW "})
    with pytest.raises(AIServiceError) as error:
        load_configuration({"OPENAI_API_KEY": "key", "OPENAI_MODEL": "model", "OPENAI_REASONING": "secret-value"})
    assert str(error.value) == "invalid OPENAI_REASONING configuration"
    assert "secret-value" not in str(error.value)


def test_reply_includes_dialog_and_tool_history() -> None:
    calls = []

    class FakeResponses:
        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(output=(), output_text="Answer")

    result = generate_reply(
        "new question",
        (
            ChatMessage("user", "earlier"),
            ChatMessage("assistant", "earlier answer"),
            ToolInvocation("call_1", "getCurrentDateTimeIso", "{}", "2026-09-18T00:00:00+00:00"),
        ),
        configuration=configuration(),
        client=SimpleNamespace(responses=FakeResponses()),
    )

    assert result.content == "Answer"
    assert calls[0]["input"][-1] == {"role": "user", "content": "new question"}
    assert calls[0]["input"][2]["type"] == "function_call"
    assert calls[0]["input"][3]["type"] == "function_call_output"


def test_sync_requests_apply_configured_reasoning_to_tool_follow_up() -> None:
    calls = []
    responses = [
        SimpleNamespace(
            output=(SimpleNamespace(type="function_call", call_id="call-1", name="getCurrentDateTimeIso", arguments="{}"),),
            output_text="",
        ),
        SimpleNamespace(output=(), output_text="Answer"),
    ]

    class FakeResponses:
        def create(self, **kwargs):
            calls.append(kwargs)
            return responses.pop(0)

    config = AIServiceConfiguration("key", "model", None, reasoning_effort="high")
    result = generate_reply("question", (), configuration=config, client=SimpleNamespace(responses=FakeResponses()))

    assert result.content == "Answer"
    assert [call["reasoning"] for call in calls] == [{"effort": "high"}, {"effort": "high"}]


def test_sync_requests_omit_reasoning_when_not_configured() -> None:
    calls = []
    client = SimpleNamespace(
        responses=SimpleNamespace(
            create=lambda **kwargs: calls.append(kwargs) or SimpleNamespace(output=(), output_text="Answer")
        )
    )

    generate_reply("question", (), configuration=configuration(), client=client)

    assert "reasoning" not in calls[0]


def test_rejects_unknown_tool() -> None:
    response = SimpleNamespace(
        output=(SimpleNamespace(type="function_call", call_id="call_1", name="unknown", arguments="{}"),),
        output_text="",
    )
    with pytest.raises(AIServiceError):
        generate_reply("question", (), configuration=configuration(), client=SimpleNamespace(responses=SimpleNamespace(create=lambda **_: response)))


def test_records_duration_for_each_model_request(capsys) -> None:
    client = SimpleNamespace(
        responses=SimpleNamespace(create=lambda **_: SimpleNamespace(output=(), output_text="Answer"))
    )

    generate_reply("question", (), configuration=configuration(), client=client)

    records = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert records[-1]["step"] == "model_request"
    assert isinstance(records[-1]["duration_ms"], int)


def test_async_client_uses_validated_settings_and_disables_retries(monkeypatch) -> None:
    captured = {}

    class FakeAsyncOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("src.ai_client.AsyncOpenAI", FakeAsyncOpenAI)
    config = AIServiceConfiguration("secret", "model", "https://model.example/v1", 7.5)

    client = create_async_client(config)

    assert isinstance(client, FakeAsyncOpenAI)
    assert captured == {
        "api_key": "secret",
        "base_url": "https://model.example/v1",
        "timeout": 7.5,
        "max_retries": 0,
    }


def test_agent_run_config_bounds_requests_and_disables_storage_and_tracing() -> None:
    config = AIServiceConfiguration("secret", "configured-model", None, 8.0)
    run_config = build_agent_run_config(config)

    assert run_config.model_settings.timeout == 8.0
    assert run_config.model_settings.store is False
    assert run_config.model_settings.parallel_tool_calls is False
    assert run_config.model_settings.retry is None
    assert run_config.model_settings.reasoning is None
    assert run_config.tracing_disabled is True
    assert run_config.trace_include_sensitive_data is False


def test_agent_run_config_applies_optional_reasoning_effort() -> None:
    config = AIServiceConfiguration("secret", "configured-model", None, 8.0, "minimal")

    run_config = build_agent_run_config(config)

    assert run_config.model_settings.reasoning.effort == "minimal"


def test_each_agent_can_own_a_distinct_configured_model_client() -> None:
    config = AIServiceConfiguration("secret", "configured-model", None)
    first_client = object()
    second_client = object()

    first_model = build_agent_model(config, client=first_client)
    second_model = build_agent_model(config, client=second_client)

    assert first_model is not second_model
    assert first_model.model == config.model
    assert second_model.model == config.model
