"""Strict, server-owned tools available to the conversational model."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
from typing import Any, Literal

from agents import function_tool
from agents.tool_context import ToolContext

TOOL_NAME = "getCurrentDateTimeIso"
TOOLS = [
    {
        "type": "function",
        "name": TOOL_NAME,
        "description": "Get the current date and time as an ISO 8601 UTC timestamp.",
        "parameters": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
        "strict": True,
    }
]

_SERVICE_INFORMATION = {
    "hours": "Support is available Monday through Friday, 09:00 to 17:00 UTC.",
    "contact": "Contact support through the customer service page.",
}


class CapabilityPolicyError(RuntimeError):
    """A fixed, content-free rejection of a repeated or malformed capability call."""


@dataclass
class TaskToolLedger:
    capability_call_ids: list[str] = field(default_factory=list)
    capability_step_ids: list[str] = field(default_factory=list)
    completed_step_ids: list[str] = field(default_factory=list)
    completed_step_results: list[str] = field(default_factory=list)

    def claim(self, call_id: str, step_id: str) -> None:
        if not call_id or call_id in self.capability_call_ids:
            raise CapabilityPolicyError("capability call rejected")
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", step_id):
            raise CapabilityPolicyError("capability call rejected")
        if step_id in self.completed_step_ids or step_id in self.capability_step_ids:
            raise CapabilityPolicyError("capability call rejected")
        self.capability_call_ids.append(call_id)
        self.capability_step_ids.append(step_id)

    def complete(self, step_id: str, result: str) -> None:
        if step_id not in self.capability_step_ids or step_id in self.completed_step_ids:
            raise CapabilityPolicyError("capability call rejected")
        self.completed_step_ids.append(step_id)
        self.completed_step_results.append(result)


def lookup_service_information(topic: str) -> str:
    if topic not in _SERVICE_INFORMATION:
        raise ValueError("unsupported synthetic lookup topic")
    return _SERVICE_INFORMATION[topic]


def get_current_datetime_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@function_tool(
    name_override=TOOL_NAME,
    description_override="Get the current date and time as an ISO 8601 UTC timestamp.",
    strict_mode=True,
)
def current_datetime_tool(ctx: ToolContext[TaskToolLedger]) -> str:
    step_id = f"current-date-time-{len(ctx.context.capability_call_ids) + 1}"
    ctx.context.claim(ctx.tool_call_id, step_id)
    result = get_current_datetime_iso()
    ctx.context.complete(step_id, result)
    return result


@function_tool(
    name_override="lookupServiceInformation",
    description_override="Look up fixed synthetic customer-service information by topic.",
    strict_mode=True,
)
def lookup_service_information_tool(
    ctx: ToolContext[TaskToolLedger],
    topic: Literal["hours", "contact"],
    step_id: str,
) -> str:
    ctx.context.claim(ctx.tool_call_id, step_id)
    result = lookup_service_information(topic)
    ctx.context.complete(step_id, result)
    return result


TASK_TOOLS: tuple[Any, ...] = (current_datetime_tool, lookup_service_information_tool)
