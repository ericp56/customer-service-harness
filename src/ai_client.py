"""OpenAI Responses adapter with validated configuration and a strict tool boundary."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from typing import Any, Iterable
from urllib.parse import urlparse

import openai
from openai import OpenAI

from src.chat import ChatMessage, ConversationItem, ToolInvocation
from src.observability import record_timing
from src.tools import TOOL_NAME, TOOLS, get_current_datetime_iso

DEFAULT_TIMEOUT_SECONDS = 10.0


class AIServiceError(RuntimeError):
    """A declared, content-free failure when generating an assistant reply."""


class InvalidConfigurationError(AIServiceError):
    """Required model-service configuration is absent or invalid."""


@dataclass(frozen=True)
class AIServiceConfiguration:
    api_key: str
    model: str
    base_url: str | None
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS


@dataclass(frozen=True)
class ModelReply:
    content: str
    tool_invocations: tuple[ToolInvocation, ...] = ()


def load_configuration(environ: dict[str, str] | None = None) -> AIServiceConfiguration:
    values = os.environ if environ is None else environ
    api_key = values.get("OPENAI_API_KEY", "").strip()
    model = values.get("OPENAI_MODEL", "").strip()
    base_url = values.get("OPENAI_BASE_URL", "").strip() or None
    if not api_key or not model:
        raise InvalidConfigurationError()
    if base_url and (urlparse(base_url).scheme != "https" or not urlparse(base_url).netloc):
        raise InvalidConfigurationError()
    raw_timeout = values.get("OPENAI_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS))
    try:
        timeout_seconds = float(raw_timeout)
    except ValueError as error:
        raise InvalidConfigurationError() from error
    if not 0 < timeout_seconds <= DEFAULT_TIMEOUT_SECONDS:
        raise InvalidConfigurationError()
    return AIServiceConfiguration(api_key, model, base_url, timeout_seconds)


def _system_instructions() -> str:
    return (Path(__file__).parent / "prompts" / "system.txt").read_text(encoding="utf-8").strip()


def _history_input(history: Iterable[ConversationItem], pending_text: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for item in history:
        if isinstance(item, ChatMessage):
            items.append({"role": item.role, "content": item.content})
        else:
            items.extend(
                [
                    {
                        "type": "function_call",
                        "call_id": item.call_id,
                        "name": item.name,
                        "arguments": item.arguments,
                    },
                    {"type": "function_call_output", "call_id": item.call_id, "output": item.output},
                ]
            )
    items.append({"role": "user", "content": pending_text})
    return items


def _attribute(item: object, name: str, default: Any = None) -> Any:
    return item.get(name, default) if isinstance(item, dict) else getattr(item, name, default)


def _tool_calls(response: object) -> list[object]:
    output = _attribute(response, "output", ())
    if not isinstance(output, (list, tuple)):
        raise AIServiceError()
    return [item for item in output if _attribute(item, "type") == "function_call"]


def _validated_tool_invocations(calls: Iterable[object]) -> tuple[ToolInvocation, ...]:
    invocations: list[ToolInvocation] = []
    for call in calls:
        call_id = _attribute(call, "call_id")
        name = _attribute(call, "name")
        arguments = _attribute(call, "arguments", "{}")
        if not isinstance(call_id, str) or not call_id or name != TOOL_NAME or not isinstance(arguments, str):
            raise AIServiceError()
        try:
            parsed_arguments = json.loads(arguments)
        except json.JSONDecodeError as error:
            raise AIServiceError() from error
        if parsed_arguments != {}:
            raise AIServiceError()
        started_at = monotonic()
        try:
            output = get_current_datetime_iso()
        finally:
            record_timing("date_time_tool", started_at)
        invocations.append(ToolInvocation(call_id, name, arguments, output))
    return tuple(invocations)


def _output_text(response: object) -> str:
    output_text = _attribute(response, "output_text", "")
    if not isinstance(output_text, str) or not output_text.strip():
        raise AIServiceError()
    return output_text


def _create_response(model_client: Any, **request: Any) -> object:
    started_at = monotonic()
    try:
        return model_client.responses.create(**request)
    finally:
        record_timing("model_request", started_at)


def generate_reply(
    pending_text: str,
    history: tuple[ConversationItem, ...],
    *,
    configuration: AIServiceConfiguration | None = None,
    client: Any | None = None,
) -> ModelReply:
    """Generate one final reply, retaining only approved completed tool invocations."""
    config = configuration or load_configuration()
    model_client = client or OpenAI(
        api_key=config.api_key,
        base_url=config.base_url,
        timeout=config.timeout_seconds,
        max_retries=0,
    )
    request_input = _history_input(history, pending_text)
    try:
        response = _create_response(
            model_client,
            model=config.model,
            instructions=_system_instructions(),
            input=request_input,
            tools=TOOLS,
        )
        calls = _tool_calls(response)
        if not calls:
            return ModelReply(_output_text(response))
        invocations = _validated_tool_invocations(calls)
        follow_up = [
            *request_input,
            *_attribute(response, "output", ()),
            *[
                {"type": "function_call_output", "call_id": item.call_id, "output": item.output}
                for item in invocations
            ],
        ]
        final_response = _create_response(
            model_client,
            model=config.model,
            instructions=_system_instructions(),
            input=follow_up,
            tools=TOOLS,
        )
        if _tool_calls(final_response):
            raise AIServiceError()
        return ModelReply(_output_text(final_response), invocations)
    except (openai.OpenAIError, AttributeError, TypeError, ValueError) as error:
        raise AIServiceError() from error
