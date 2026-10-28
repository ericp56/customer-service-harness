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
    list_open_cases_tool,
    propose_case_closure_tool,
    propose_case_follow_up_tool,
    propose_demo_card_toggle_tool,
    propose_favorite_color_update_tool,
    propose_open_support_case_tool,
    propose_preferred_name_update_tool,
    retrieve_account_profile_tool,
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
        "retrieveAccountProfile",
        "proposeFavoriteColorUpdate",
        "proposePreferredNameUpdate",
        "proposeDemoCardToggle",
        "listOpenCases",
        "proposeOpenSupportCase",
        "proposeCaseFollowUp",
        "proposeCaseClosure",
    }
    assert all(tool.strict_json_schema is True for tool in tools_by_name.values())
    assert tools_by_name[TOOL_NAME].strict_json_schema is True
    assert "lookupServiceInformation" not in tools_by_name
    assert tools_by_name["proposeFavoriteColorUpdate"].params_json_schema["properties"]["favorite_color"]["enum"] == [
        "red", "blue", "green", "purple", "black", "white",
    ]
    assert set(tools_by_name["proposeDemoCardToggle"].params_json_schema["properties"]) == {"action"}
    assert set(tools_by_name["proposeOpenSupportCase"].params_json_schema["properties"]) == {"description"}
    assert set(tools_by_name["proposeCaseFollowUp"].params_json_schema["properties"]) == {
        "case_number", "follow_up",
    }
    assert set(tools_by_name["proposeCaseClosure"].params_json_schema["properties"]) == {"case_number"}


def test_account_capabilities_are_separated_by_workflow() -> None:
    from src.catalog_policy import allowed_capabilities
    from src.observability import TaskName

    assert allowed_capabilities(TaskName.RETRIEVE_ACCOUNT) == frozenset({
        "account_lookup", "verify_account_zip", "retrieveAccountProfile",
    })
    assert allowed_capabilities(TaskName.UPDATE_ACCOUNT) == frozenset({
        "account_lookup",
        "verify_account_zip",
        "proposeFavoriteColorUpdate",
        "proposePreferredNameUpdate",
        "proposeDemoCardToggle",
    })
    verification = {"account_lookup", "verify_account_zip"}
    assert allowed_capabilities(TaskName.LIST_OPEN_CASES) == verification | {"listOpenCases"}
    assert allowed_capabilities(TaskName.OPEN_SUPPORT_CASE) == verification | {"proposeOpenSupportCase"}
    assert allowed_capabilities(TaskName.FOLLOW_UP_CASE) == verification | {
        "listOpenCases", "proposeCaseFollowUp",
    }
    assert allowed_capabilities(TaskName.CLOSE_SUPPORT_CASE) == verification | {
        "listOpenCases", "proposeCaseClosure",
    }


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


def test_profile_retrieval_requires_the_verified_account(run_async) -> None:
    from agents.tool_context import ToolContext

    from src.observability import TaskName

    ledger = TaskToolLedger(
        task_name=TaskName.RETRIEVE_ACCOUNT,
        caller_input="show my account settings",
    )
    context = ToolContext(
        context=ledger,
        tool_name="retrieveAccountProfile",
        tool_call_id="profile-unverified",
        tool_arguments="{}",
    )

    run_async(retrieve_account_profile_tool.on_invoke_tool(context, "{}"))

    assert ledger.facts.profile is None
    assert ledger.completed_step_results == []
    assert ledger.policy_violated


def test_profile_retrieval_returns_only_allowlisted_settings(run_async) -> None:
    from agents.tool_context import ToolContext

    from src.accounts import CallerSession
    from src.observability import TaskName

    ledger = TaskToolLedger(
        task_name=TaskName.RETRIEVE_ACCOUNT,
        caller=CallerSession(current_account="123", verified_account="123"),
        caller_input="show my account settings",
    )
    context = ToolContext(
        context=ledger,
        tool_name="retrieveAccountProfile",
        tool_call_id="profile-verified",
        tool_arguments="{}",
    )

    result = run_async(retrieve_account_profile_tool.on_invoke_tool(context, "{}"))

    assert result == "Favorite color: blue; preferred name: Alex; demo card on file: no."
    assert "12345" not in result
    assert ledger.facts.profile is not None
    assert ledger.completed_step_ids == ["retrieve-account-profile-1"]


@pytest.mark.parametrize(
    ("tool_name", "tool", "arguments", "caller_input", "kind"),
    [
        (
            "proposeFavoriteColorUpdate",
            propose_favorite_color_update_tool,
            '{"favorite_color":"red"}',
            "change favorite color to red",
            "update_favorite_color",
        ),
        (
            "proposePreferredNameUpdate",
            propose_preferred_name_update_tool,
            '{"preferred_name":"Casey"}',
            "change my preferred name to Casey",
            "update_preferred_name",
        ),
        (
            "proposeDemoCardToggle",
            propose_demo_card_toggle_tool,
            '{"action":"save"}',
            "save the demo card",
            "save_demo_card",
        ),
    ],
)
def test_account_write_capabilities_stage_without_mutating(
    run_async, tool_name, tool, arguments, caller_input, kind
) -> None:
    from agents.tool_context import ToolContext

    from src.accounts import CallerSession
    from src.customer_data import seed_demo_data
    from src.observability import TaskName

    original = seed_demo_data()
    ledger = TaskToolLedger(
        task_name=TaskName.UPDATE_ACCOUNT,
        caller=CallerSession(current_account="123", verified_account="123"),
        caller_input=caller_input,
        demo_data=original,
    )
    context = ToolContext(
        context=ledger,
        tool_name=tool_name,
        tool_call_id="proposal-1",
        tool_arguments=arguments,
    )

    result = run_async(tool.on_invoke_tool(context, arguments))

    assert ledger.demo_data == original
    assert ledger.pending_mutation is not None
    assert ledger.pending_mutation.kind.value == kind
    assert result.startswith("Please approve")
    assert ledger.facts.mutation_kind is ledger.pending_mutation.kind


def test_case_listing_is_owned_and_open_only(run_async) -> None:
    from agents.tool_context import ToolContext

    from src.accounts import CallerSession
    from src.observability import TaskName

    ledger = TaskToolLedger(
        task_name=TaskName.LIST_OPEN_CASES,
        caller=CallerSession(current_account="123", verified_account="123"),
        caller_input="list my open cases",
    )
    context = ToolContext(
        context=ledger,
        tool_name="listOpenCases",
        tool_call_id="list-cases",
        tool_arguments="{}",
    )

    result = run_async(list_open_cases_tool.on_invoke_tool(context, "{}"))

    assert "CASE-1001" in result
    assert "CASE-1000" not in result
    assert "CASE-1002" not in result
    assert ledger.facts.cases is not None
    assert all(case.account_number == "123" and case.status == "open" for case in ledger.facts.cases)


@pytest.mark.parametrize(
    ("tool_name", "tool", "arguments", "caller_input", "task_name", "kind"),
    [
        (
            "proposeOpenSupportCase",
            propose_open_support_case_tool,
            '{"description":"Package arrived damaged"}',
            "open a case: Package arrived damaged",
            "Open Support Case",
            "open_case",
        ),
        (
            "proposeCaseFollowUp",
            propose_case_follow_up_tool,
            '{"case_number":"CASE-1001","follow_up":"The package is still missing"}',
            "follow up CASE-1001: The package is still missing",
            "Follow Up Support Case",
            "add_follow_up",
        ),
        (
            "proposeCaseClosure",
            propose_case_closure_tool,
            '{"case_number":"CASE-1001"}',
            "close CASE-1001",
            "Close Support Case",
            "close_case",
        ),
    ],
)
def test_case_write_capabilities_stage_exact_owned_proposals(
    run_async, tool_name, tool, arguments, caller_input, task_name, kind
) -> None:
    from agents.tool_context import ToolContext

    from src.accounts import CallerSession
    from src.customer_data import seed_demo_data
    from src.observability import TaskName

    original = seed_demo_data()
    ledger = TaskToolLedger(
        task_name=TaskName(task_name),
        caller=CallerSession(current_account="123", verified_account="123"),
        caller_input=caller_input,
        demo_data=original,
    )
    context = ToolContext(
        context=ledger,
        tool_name=tool_name,
        tool_call_id="case-proposal",
        tool_arguments=arguments,
    )

    result = run_async(tool.on_invoke_tool(context, arguments))

    assert ledger.demo_data == original
    assert ledger.pending_mutation is not None
    assert ledger.pending_mutation.kind.value == kind
    assert result.startswith("Please approve")


@pytest.mark.parametrize("case_number", ["CASE-1000", "CASE-1002", "CASE-9999"])
def test_case_mutations_reject_closed_foreign_and_unknown_targets(run_async, case_number) -> None:
    from agents.tool_context import ToolContext

    from src.accounts import CallerSession
    from src.observability import TaskName

    caller_input = f"Follow up {case_number}: Additional detail"
    arguments = '{"case_number":"' + case_number + '","follow_up":"Additional detail"}'
    ledger = TaskToolLedger(
        task_name=TaskName.FOLLOW_UP_CASE,
        caller=CallerSession(current_account="123", verified_account="123"),
        caller_input=caller_input,
    )
    context = ToolContext(
        context=ledger,
        tool_name="proposeCaseFollowUp",
        tool_call_id="invalid-case-proposal",
        tool_arguments=arguments,
    )

    run_async(propose_case_follow_up_tool.on_invoke_tool(context, arguments))

    assert ledger.pending_mutation is None
    assert ledger.policy_violated


def test_case_target_must_be_present_in_caller_input(run_async) -> None:
    from agents.tool_context import ToolContext

    from src.accounts import CallerSession
    from src.observability import TaskName

    arguments = '{"case_number":"CASE-1001","follow_up":"More detail"}'
    ledger = TaskToolLedger(
        task_name=TaskName.FOLLOW_UP_CASE,
        caller=CallerSession(current_account="123", verified_account="123"),
        caller_input="add More detail to my case",
    )
    context = ToolContext(
        context=ledger,
        tool_name="proposeCaseFollowUp",
        tool_call_id="invented-case-proposal",
        tool_arguments=arguments,
    )

    run_async(propose_case_follow_up_tool.on_invoke_tool(context, arguments))

    assert ledger.pending_mutation is None
    assert ledger.policy_violated


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
