from __future__ import annotations

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
        "account_lookup",
        "verify_account_zip",
        "getSupportContact",
    }
    assert all(tool.strict_json_schema is True for tool in tools_by_name.values())
    assert tools_by_name[TOOL_NAME].strict_json_schema is True
    assert "lookupServiceInformation" not in tools_by_name


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


def test_time_task_cannot_invoke_account_lookup(run_async) -> None:
    from agents.tool_context import ToolContext

    from src.observability import TaskName

    ledger = TaskToolLedger(task_name=TaskName.CURRENT_TIME, caller_input="123")
    context = ToolContext(context=ledger, tool_name="account_lookup", tool_call_id="denied-1", tool_arguments='{"account_number":"123"}')
    tool = next(tool for tool in TASK_TOOLS if tool.name == "account_lookup")

    run_async(tool.on_invoke_tool(context, '{"account_number":"123"}'))

    assert ledger.caller.account_attempts == 0
    assert ledger.caller.current_account is None
    assert ledger.capability_call_ids == []


@pytest.mark.parametrize("task_name,tool_name,detail_kind,value", [
    ("Retrieve customer account", "getSupportContact", "none", None),
    ("Retrieve the current time", "lookupServiceInformation", "none", None),
    ("Retrieve customer account", "verify_account_zip", "zip_code", "12345"),
    ("Retrieve customer account", "account_lookup", "account_number", "456"),
])
def test_task_authorization_rejects_wrong_stage_or_invented_value(task_name, tool_name, detail_kind, value) -> None:
    from src.observability import TaskName

    ledger = TaskToolLedger(task_name=TaskName(task_name), caller_input="My account is 123", detail_kind=detail_kind)

    with pytest.raises(CapabilityPolicyError):
        ledger.authorize(tool_name, value)
    assert ledger.policy_violated
    assert ledger.caller.account_attempts == 0


def test_account_input_provenance_does_not_match_inside_a_zip() -> None:
    from src.observability import TaskName

    ledger = TaskToolLedger(task_name=TaskName.CUSTOMER_ACCOUNT, caller_input="12345", detail_kind="account_number")
    with pytest.raises(CapabilityPolicyError):
        ledger.authorize("account_lookup", "123")
