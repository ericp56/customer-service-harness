from datetime import datetime
from types import SimpleNamespace
import json

import httpx
import openai
import pytest

from src.ai_client import (
    AIServiceConfiguration,
    AIServiceError,
    ProviderRejectedError,
    ServiceUnavailableError,
    UnusableResponseError,
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
    assert records[-1]["level"] == "INFO"
    assert records[-1]["message"] == "success"
    assert isinstance(records[-1]["duration_ms"], int)


def _client(create) -> SimpleNamespace:
    return SimpleNamespace(responses=SimpleNamespace(create=create))


def test_permitted_date_time_call_correlates_iso_output(capsys) -> None:
    calls: list[dict] = []

    def create(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            return SimpleNamespace(
                output=(
                    SimpleNamespace(
                        type="function_call",
                        call_id="call_9",
                        name="getCurrentDateTimeIso",
                        arguments="{}",
                    ),
                ),
                output_text="",
            )
        return SimpleNamespace(output=(), output_text="It is the current time.")

    result = generate_reply("what time is it", (), configuration=configuration(), client=_client(create))
    captured = capsys.readouterr().out

    assert result.content == "It is the current time."
    assert len(result.tool_invocations) == 1
    invocation = result.tool_invocations[0]
    assert invocation.call_id == "call_9"
    assert invocation.name == "getCurrentDateTimeIso"
    assert invocation.arguments == "{}"
    parsed = datetime.fromisoformat(invocation.output)
    assert parsed.tzinfo is not None
    assert calls[1]["input"][-1] == {
        "type": "function_call_output",
        "call_id": "call_9",
        "output": invocation.output,
    }
    records = [json.loads(line) for line in captured.splitlines()]
    tool_records = [record for record in records if record["step"] == "date_time_tool"]
    assert tool_records[-1]["message"] == "success"
    assert tool_records[-1]["level"] == "INFO"
    assert isinstance(tool_records[-1]["duration_ms"], int)
    assert invocation.output not in captured


def test_rejects_non_empty_date_time_arguments() -> None:
    response = SimpleNamespace(
        output=(
            SimpleNamespace(
                type="function_call",
                call_id="call_1",
                name="getCurrentDateTimeIso",
                arguments='{"tz":"UTC"}',
            ),
        ),
        output_text="",
    )
    with pytest.raises(UnusableResponseError):
        generate_reply("question", (), configuration=configuration(), client=_client(lambda **_: response))


def test_rejects_repeated_tool_loop() -> None:
    responses = [
        SimpleNamespace(
            output=(
                SimpleNamespace(
                    type="function_call",
                    call_id="call_1",
                    name="getCurrentDateTimeIso",
                    arguments="{}",
                ),
            ),
            output_text="",
        ),
        SimpleNamespace(
            output=(
                SimpleNamespace(
                    type="function_call",
                    call_id="call_2",
                    name="getCurrentDateTimeIso",
                    arguments="{}",
                ),
            ),
            output_text="",
        ),
    ]

    def create(**_kwargs):
        return responses.pop(0)

    with pytest.raises(UnusableResponseError):
        generate_reply("question", (), configuration=configuration(), client=_client(create))


def test_timeout_records_unavailability_without_success_or_secrets(capsys) -> None:
    secret_url = "https://provider.example/v1/responses"

    def create(**_kwargs):
        raise openai.APITimeoutError(httpx.Request("POST", secret_url))

    with pytest.raises(ServiceUnavailableError):
        generate_reply("question", (), configuration=configuration(), client=_client(create))

    captured = capsys.readouterr().out
    records = [json.loads(line) for line in captured.splitlines()]
    model_record = next(record for record in records if record["step"] == "model_request")
    assert model_record["message"] == "timeout_or_unavailable"
    assert model_record["level"] == "ERROR"
    assert model_record["message"] != "success"
    assert "provider.example" not in captured
    assert "question" not in captured


def test_authentication_failure_is_provider_rejection(capsys) -> None:
    request = httpx.Request("POST", "https://provider.example/v1/responses")
    response = httpx.Response(401, request=request)

    def create(**_kwargs):
        raise openai.AuthenticationError("rejected sk-testsecret", response=response, body=None)

    with pytest.raises(ProviderRejectedError):
        generate_reply("question", (), configuration=configuration(), client=_client(create))

    captured = capsys.readouterr().out
    records = [json.loads(line) for line in captured.splitlines()]
    model_record = next(record for record in records if record["step"] == "model_request")
    assert model_record["message"] == "provider_rejected"
    assert model_record["level"] == "ERROR"
    assert "sk-testsecret" not in captured
    assert "provider.example" not in captured


def test_empty_model_output_is_unusable() -> None:
    response = SimpleNamespace(output=(), output_text="  ")
    with pytest.raises(UnusableResponseError):
        generate_reply("question", (), configuration=configuration(), client=_client(lambda **_: response))
