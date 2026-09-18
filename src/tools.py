"""Strict, server-owned tools available to the conversational model."""

from __future__ import annotations

from datetime import datetime, timezone

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


def get_current_datetime_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
