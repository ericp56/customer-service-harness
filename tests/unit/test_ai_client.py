from types import SimpleNamespace
import json

import pytest

from src.ai_client import (
    AIServiceConfiguration,
    AIServiceError,
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
    assert isinstance(records[-1]["duration_ms"], int)
