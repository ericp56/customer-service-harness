from datetime import datetime

import pytest

from src.tools import (
    CapabilityPolicyError,
    TASK_TOOLS,
    TaskToolLedger,
    TOOL_NAME,
    TOOLS,
    get_current_datetime_iso,
    lookup_service_information,
)


def test_date_time_tool_is_strict_and_returns_utc_iso_timestamp() -> None:
    assert TOOL_NAME == "getCurrentDateTimeIso"
    assert TOOLS[0]["strict"] is True
    assert TOOLS[0]["parameters"]["additionalProperties"] is False
    assert datetime.fromisoformat(get_current_datetime_iso()).tzinfo is not None


def test_synthetic_service_information_is_deterministic_and_allowlisted() -> None:
    assert lookup_service_information("hours") == "Support is available Monday through Friday, 09:00 to 17:00 UTC."
    assert lookup_service_information("contact") == "Contact support through the customer service page."
    with pytest.raises(ValueError):
        lookup_service_information("customer-account")


def test_agent_tool_registry_is_strict_and_preserves_date_time() -> None:
    tools_by_name = {tool.name: tool for tool in TASK_TOOLS}

    assert set(tools_by_name) == {
        TOOL_NAME,
        "lookupServiceInformation",
        "account_lookup",
        "verify_account_zip",
        "getSupportContact",
    }
    assert all(tool.strict_json_schema is True for tool in tools_by_name.values())
    lookup_schema = tools_by_name["lookupServiceInformation"].params_json_schema
    assert tools_by_name[TOOL_NAME].strict_json_schema is True
    assert tools_by_name["lookupServiceInformation"].strict_json_schema is True
    assert lookup_schema["properties"]["topic"]["enum"] == ["hours", "contact"]


def test_task_tool_ledger_rejects_duplicate_calls_and_replayed_steps() -> None:
    ledger = TaskToolLedger()
    ledger.claim("call-1", "lookup-hours-1")
    ledger.complete("lookup-hours-1", "Support is open weekdays.")

    with pytest.raises(CapabilityPolicyError):
        ledger.claim("call-1", "lookup-contact-1")
    with pytest.raises(CapabilityPolicyError):
        ledger.claim("call-2", "lookup-hours-1")


def test_ledger_allows_a_later_distinct_date_time_step() -> None:
    ledger = TaskToolLedger()
    ledger.claim("call-1", "current-date-time-1")
    ledger.complete("current-date-time-1", "2026-10-04T12:00:00+00:00")

    ledger.claim("call-2", "current-date-time-2")

    assert ledger.capability_call_ids == ["call-1", "call-2"]
