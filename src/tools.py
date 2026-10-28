"""Strict, server-owned tools available to the conversational model."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
import re
from enum import StrEnum
from typing import Any, Literal
from time import monotonic
from uuid import uuid4

from agents import function_tool
from agents.tool_context import ToolContext

from src.observability import TaskName
from src.catalog_policy import CatalogFacts, allowed_capabilities
from src.customer_data import (
    AccountView,
    DemoData,
    MutationKind,
    PendingMutation,
    SupportCase,
    list_open_cases,
    propose_mutation,
    retrieve_account,
    seed_demo_data,
)
from src.accounts import (
    CallerSession,
    LookupResult,
    ZipResult,
    lookup_account,
    support_contact,
    verify_zip,
)

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


class TaskActivity(StrEnum):
    PROCESSING = "processing"
    WORKING_ON_TASK = "working_on_task"
    LOOKING_UP_INFORMATION = "looking_up_information"
    CHECKING_INFORMATION = "checking_information"
    EVALUATING_RESULT = "evaluating_result"


@dataclass
class TaskProgress:
    activity: TaskActivity | None = None
    task_name: TaskName | None = None

    def set(self, activity: TaskActivity, task_name: TaskName | None = None) -> None:
        self.activity = activity if isinstance(activity, TaskActivity) else None
        self.task_name = task_name if isinstance(task_name, TaskName) else None

    def clear(self) -> None:
        self.activity = None
        self.task_name = None


class RevisionRequested(BaseException):
    """Discard an obsolete SDK continuation without converting it to tool output."""


@dataclass
class ExecutionControl:
    checkpoint: Callable[[TaskToolLedger, str], Awaitable[None]]
    revision: int = 0
    base_seconds: float = 0.0
    started_at: float = field(default_factory=monotonic)
    paused_at: float | None = None
    paused_seconds: float = 0.0
    timeout: asyncio.Timeout | None = None
    manager_turns: int = 0
    reconciling: bool = False
    agents: Any = None
    state: Any = None
    change_action: str | None = None
    owned_clients: list[Any] = field(default_factory=list)
    admitted_route: Any = None
    pending_route: Any = None
    recorder: Any = None
    generation: int = 0
    demo_data: DemoData = field(default_factory=seed_demo_data)

    @property
    def active_seconds(self) -> float:
        end = self.paused_at if self.paused_at is not None else monotonic()
        return self.base_seconds + max(0.0, end - self.started_at - self.paused_seconds)

    def pause(self) -> None:
        if self.paused_at is None:
            self.paused_at = monotonic()
        if self.timeout is not None:
            self.timeout.reschedule(None)

    def resume(self) -> None:
        if self.paused_at is not None:
            self.paused_seconds += max(0.0, monotonic() - self.paused_at)
            self.paused_at = None
        if self.timeout is not None:
            self.timeout.reschedule(asyncio.get_running_loop().time() + max(0.0, 60.0 - self.active_seconds))

    async def run(self, work: Awaitable[Any]) -> Any:
        async with asyncio.timeout(None) as timeout:
            self.timeout = timeout
            self.resume()
            try:
                return await work
            finally:
                self.timeout = None


@dataclass
class TaskToolLedger:
    capability_call_ids: list[str] = field(default_factory=list)
    capability_step_ids: list[str] = field(default_factory=list)
    completed_step_ids: list[str] = field(default_factory=list)
    completed_step_results: list[str] = field(default_factory=list)
    caller: CallerSession = field(default_factory=CallerSession)
    progress: TaskProgress = field(default_factory=TaskProgress)
    task_name: TaskName | None = None
    caller_input: str = ""
    detail_kind: Literal["none", "account_number", "zip_code"] = "none"
    facts: CatalogFacts = field(default_factory=CatalogFacts)
    policy_violated: bool = False
    control: ExecutionControl | None = None
    demo_data: DemoData = field(default_factory=seed_demo_data)
    generation: int = 0
    pending_mutation: PendingMutation | None = None

    async def checkpoint(self, boundary: str) -> None:
        if self.control is not None and not self.control.reconciling:
            await self.control.checkpoint(self, boundary)

    def authorize(self, tool_name: str, value: str | None = None) -> None:
        allowed = allowed_capabilities(self.task_name)
        valid = tool_name in allowed and not self.caller.ended
        if tool_name == TOOL_NAME:
            valid = valid and self.facts.timestamp is None
        elif tool_name == "account_lookup":
            valid = valid and self.detail_kind == "account_number" and self.facts.lookup is None
        elif tool_name == "verify_account_zip":
            valid = (
                valid and self.detail_kind == "zip_code" and self.facts.zip_check is None
                and self.caller.current_account is not None and self.caller.verified_account is None
            )
        elif tool_name == "getSupportContact":
            valid = valid and self.caller.verified_account is not None and self.caller.verified_account == self.caller.current_account and self.facts.contact is None
        elif tool_name == "retrieveAccountProfile":
            valid = (
                valid
                and self.task_name is TaskName.RETRIEVE_ACCOUNT
                and self.caller.verified_account is not None
                and self.caller.verified_account == self.caller.current_account
                and self.facts.profile is None
            )
        elif tool_name in (
            "proposeFavoriteColorUpdate",
            "proposePreferredNameUpdate",
            "proposeDemoCardToggle",
            "proposeOpenSupportCase",
            "proposeCaseFollowUp",
            "proposeCaseClosure",
        ):
            valid = (
                valid
                and self.task_name in (
                    TaskName.UPDATE_ACCOUNT,
                    TaskName.OPEN_SUPPORT_CASE,
                    TaskName.FOLLOW_UP_CASE,
                    TaskName.CLOSE_SUPPORT_CASE,
                )
                and self.caller.verified_account is not None
                and self.caller.verified_account == self.caller.current_account
                and self.pending_mutation is None
            )
        elif tool_name == "listOpenCases":
            valid = (
                valid
                and self.task_name in (
                    TaskName.LIST_OPEN_CASES,
                    TaskName.FOLLOW_UP_CASE,
                    TaskName.CLOSE_SUPPORT_CASE,
                )
                and self.caller.verified_account is not None
                and self.caller.verified_account == self.caller.current_account
                and self.facts.cases is None
            )
        if value is not None:
            valid = valid and bool(value.strip()) and (
                value == self.caller_input.strip()
                or re.search(r"(?<!\w)" + re.escape(value) + r"(?!\w)", self.caller_input) is not None
            )
        if not valid:
            self.policy_violated = True
            raise CapabilityPolicyError("capability call rejected")

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
async def current_datetime_tool(ctx: ToolContext[TaskToolLedger]) -> str:
    await ctx.context.checkpoint("dispatch")
    ctx.context.authorize(TOOL_NAME)
    step_id = f"current-date-time-{len(ctx.context.capability_call_ids) + 1}"
    if ctx.context.control is not None:
        step_id = f"r{ctx.context.control.revision}-{step_id}"
    ctx.context.claim(ctx.tool_call_id, step_id)
    result = get_current_datetime_iso()
    ctx.context.facts = replace(ctx.context.facts, timestamp=result)
    ctx.context.complete(step_id, result)
    await ctx.context.checkpoint("committed")
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
    ctx.context.authorize("lookupServiceInformation")
    ctx.context.claim(ctx.tool_call_id, step_id)
    result = lookup_service_information(topic)
    ctx.context.complete(step_id, result)
    return result


_LOOKUP_RESULTS = {
    LookupResult.FOUND: "Account found. Ask the caller for their zip code.",
    LookupResult.NOT_FOUND: "No account found. Tell the caller and ask for the account number again.",
    LookupResult.SESSION_ENDED: "The session has ended.",
}
_ZIP_RESULTS = {
    ZipResult.MATCH: "The zip code matched and the account is verified.",
    ZipResult.MISMATCH: "The zip code did not match. Ask the caller for the zip code again.",
    ZipResult.NO_ACCOUNT: "No account is selected. Ask the caller for the account number first.",
    ZipResult.SESSION_ENDED: "The session has ended.",
}


def _next_step_id(ctx: ToolContext[TaskToolLedger], prefix: str) -> str:
    step_id = f"{prefix}-{len(ctx.context.capability_call_ids) + 1}"
    if ctx.context.control is not None:
        step_id = f"r{ctx.context.control.revision}-{step_id}"
    ctx.context.claim(ctx.tool_call_id, step_id)
    return step_id


def _account_view_result(view: AccountView) -> str:
    return (
        f"Favorite color: {view.favorite_color}; preferred name: {view.preferred_name}; "
        f"demo card on file: {'yes' if view.card_on_file else 'no'}."
    )


def _mutation_proposal_text(proposal: PendingMutation) -> str:
    if proposal.kind is MutationKind.UPDATE_FAVORITE_COLOR:
        return f"Please approve changing your favorite color to {proposal.value}."
    if proposal.kind is MutationKind.UPDATE_PREFERRED_NAME:
        return f"Please approve changing your preferred name to {proposal.value}."
    if proposal.kind is MutationKind.SAVE_DEMO_CARD:
        return "Please approve saving the synthetic demo card on file."
    if proposal.kind is MutationKind.REMOVE_DEMO_CARD:
        return "Please approve removing the synthetic demo card on file."
    if proposal.kind is MutationKind.OPEN_CASE:
        return f"Please approve opening a support case: {proposal.value}."
    if proposal.kind is MutationKind.ADD_FOLLOW_UP:
        return f"Please approve adding this follow-up to case {proposal.target_case_number}: {proposal.value}."
    if proposal.kind is MutationKind.CLOSE_CASE:
        return f"Please approve closing case {proposal.target_case_number}."
    raise CapabilityPolicyError("capability call rejected")


def _stage_mutation(
    ctx: ToolContext[TaskToolLedger],
    tool_name: str,
    kind: MutationKind,
    value: str | None,
    *,
    target_case_number: str | None = None,
    additional_provenance: tuple[str, ...] = (),
) -> tuple[str, str]:
    ledger = ctx.context
    ledger.authorize(tool_name, value)
    for provenance_value in additional_provenance:
        ledger.authorize(tool_name, provenance_value)
    step_id = _next_step_id(ctx, tool_name.lower())
    proposal_value = (
        None
        if kind in (MutationKind.SAVE_DEMO_CARD, MutationKind.REMOVE_DEMO_CARD)
        else value
    )
    try:
        proposal = propose_mutation(
            ledger.demo_data,
            proposal_id=uuid4().hex,
            generation=ledger.generation,
            account_number=ledger.caller.verified_account or "",
            kind=kind,
            value=proposal_value,
            target_case_number=target_case_number,
        )
    except ValueError as error:
        ledger.policy_violated = True
        raise CapabilityPolicyError("capability call rejected") from error
    ledger.pending_mutation = proposal
    ledger.facts = replace(
        ledger.facts,
        mutation_kind=kind,
        mutation_target=target_case_number,
    )
    result = _mutation_proposal_text(proposal)
    ledger.complete(step_id, result)
    return step_id, result


@function_tool(
    name_override="retrieveAccountProfile",
    description_override="Retrieve the verified account's favorite color, preferred name, and demo-card-on-file status.",
    strict_mode=True,
)
async def retrieve_account_profile_tool(ctx: ToolContext[TaskToolLedger]) -> str:
    await ctx.context.checkpoint("dispatch")
    ctx.context.authorize("retrieveAccountProfile")
    step_id = _next_step_id(ctx, "retrieve-account-profile")
    view = retrieve_account(ctx.context.demo_data, ctx.context.caller.verified_account)
    if view is None:
        ctx.context.policy_violated = True
        raise CapabilityPolicyError("capability call rejected")
    ctx.context.facts = replace(ctx.context.facts, profile=view)
    result = _account_view_result(view)
    ctx.context.complete(step_id, result)
    await ctx.context.checkpoint("committed")
    return result


@function_tool(
    name_override="proposeFavoriteColorUpdate",
    description_override="Propose a favorite-color change for explicit caller approval.",
    strict_mode=True,
)
async def propose_favorite_color_update_tool(
    ctx: ToolContext[TaskToolLedger],
    favorite_color: Literal["red", "blue", "green", "purple", "black", "white"],
) -> str:
    await ctx.context.checkpoint("dispatch")
    _, result = _stage_mutation(
        ctx, "proposeFavoriteColorUpdate", MutationKind.UPDATE_FAVORITE_COLOR, favorite_color
    )
    await ctx.context.checkpoint("committed")
    return result


@function_tool(
    name_override="proposePreferredNameUpdate",
    description_override="Propose a preferred-name change for explicit caller approval.",
    strict_mode=True,
)
async def propose_preferred_name_update_tool(
    ctx: ToolContext[TaskToolLedger],
    preferred_name: str,
) -> str:
    await ctx.context.checkpoint("dispatch")
    _, result = _stage_mutation(
        ctx, "proposePreferredNameUpdate", MutationKind.UPDATE_PREFERRED_NAME, preferred_name
    )
    await ctx.context.checkpoint("committed")
    return result


@function_tool(
    name_override="proposeDemoCardToggle",
    description_override="Propose saving or removing only the fixed synthetic demo-card alias for explicit caller approval.",
    strict_mode=True,
)
async def propose_demo_card_toggle_tool(
    ctx: ToolContext[TaskToolLedger],
    action: Literal["save", "remove"],
) -> str:
    await ctx.context.checkpoint("dispatch")
    kind = MutationKind.SAVE_DEMO_CARD if action == "save" else MutationKind.REMOVE_DEMO_CARD
    _, result = _stage_mutation(ctx, "proposeDemoCardToggle", kind, action)
    await ctx.context.checkpoint("committed")
    return result


def _open_cases_result(cases: tuple[SupportCase, ...]) -> str:
    if not cases:
        return "No open support cases were found."
    entries = "; ".join(f"{case.case_number}: {case.description}" for case in cases)
    return "Your open support cases are: " + entries + "."


@function_tool(
    name_override="listOpenCases",
    description_override="List open support cases owned by the verified account.",
    strict_mode=True,
)
async def list_open_cases_tool(ctx: ToolContext[TaskToolLedger]) -> str:
    await ctx.context.checkpoint("dispatch")
    ctx.context.authorize("listOpenCases")
    step_id = _next_step_id(ctx, "list-open-cases")
    cases = list_open_cases(ctx.context.demo_data, ctx.context.caller.verified_account)
    ctx.context.facts = replace(ctx.context.facts, cases=cases)
    result = _open_cases_result(cases)
    ctx.context.complete(step_id, result)
    await ctx.context.checkpoint("committed")
    return result


@function_tool(
    name_override="proposeOpenSupportCase",
    description_override="Propose a support case with caller-provided description for explicit approval.",
    strict_mode=True,
)
async def propose_open_support_case_tool(
    ctx: ToolContext[TaskToolLedger],
    description: str,
) -> str:
    await ctx.context.checkpoint("dispatch")
    _, result = _stage_mutation(
        ctx, "proposeOpenSupportCase", MutationKind.OPEN_CASE, description
    )
    await ctx.context.checkpoint("committed")
    return result


@function_tool(
    name_override="proposeCaseFollowUp",
    description_override="Propose caller-provided follow-up text for an owned open case for explicit approval.",
    strict_mode=True,
)
async def propose_case_follow_up_tool(
    ctx: ToolContext[TaskToolLedger],
    case_number: str,
    follow_up: str,
) -> str:
    await ctx.context.checkpoint("dispatch")
    _, result = _stage_mutation(
        ctx,
        "proposeCaseFollowUp",
        MutationKind.ADD_FOLLOW_UP,
        follow_up,
        target_case_number=case_number,
        additional_provenance=(case_number,),
    )
    await ctx.context.checkpoint("committed")
    return result


@function_tool(
    name_override="proposeCaseClosure",
    description_override="Propose closing an owned open case for explicit approval.",
    strict_mode=True,
)
async def propose_case_closure_tool(
    ctx: ToolContext[TaskToolLedger],
    case_number: str,
) -> str:
    await ctx.context.checkpoint("dispatch")
    _, result = _stage_mutation(
        ctx,
        "proposeCaseClosure",
        MutationKind.CLOSE_CASE,
        None,
        target_case_number=case_number,
        additional_provenance=(case_number,),
    )
    await ctx.context.checkpoint("committed")
    return result


@function_tool(
    name_override="account_lookup",
    description_override="Check whether an account number exists. Never reveals account details.",
    strict_mode=True,
)
async def account_lookup_tool(ctx: ToolContext[TaskToolLedger], account_number: str) -> str:
    await ctx.context.checkpoint("dispatch")
    ctx.context.authorize("account_lookup", account_number)
    step_id = _next_step_id(ctx, "account-lookup")
    ctx.context.caller, outcome = lookup_account(ctx.context.caller, account_number)
    ctx.context.facts = replace(ctx.context.facts, lookup=outcome)
    result = _LOOKUP_RESULTS[outcome]
    ctx.context.complete(step_id, result)
    await ctx.context.checkpoint("committed")
    return result


@function_tool(
    name_override="verify_account_zip",
    description_override="Check the caller's zip code against the account they gave. Never reveals the stored zip code.",
    strict_mode=True,
)
async def verify_account_zip_tool(ctx: ToolContext[TaskToolLedger], zip_code: str) -> str:
    await ctx.context.checkpoint("dispatch")
    ctx.context.authorize("verify_account_zip", zip_code)
    step_id = _next_step_id(ctx, "verify-zip")
    ctx.context.caller, outcome = verify_zip(ctx.context.caller, zip_code)
    ctx.context.facts = replace(ctx.context.facts, zip_check=outcome)
    result = _ZIP_RESULTS[outcome]
    ctx.context.complete(step_id, result)
    await ctx.context.checkpoint("committed")
    return result


@function_tool(
    name_override="getSupportContact",
    description_override="Get the customer support contact for the verified account.",
    strict_mode=True,
)
async def support_contact_tool(ctx: ToolContext[TaskToolLedger]) -> str:
    await ctx.context.checkpoint("dispatch")
    ctx.context.authorize("getSupportContact")
    step_id = _next_step_id(ctx, "support-contact")
    contact = support_contact(ctx.context.caller)
    ctx.context.facts = replace(ctx.context.facts, contact=contact)
    result = (
        f"Customer support contact: {contact}"
        if contact
        else "The account is not verified. Retrieve the customer account first."
    )
    ctx.context.complete(step_id, result)
    await ctx.context.checkpoint("committed")
    return result


TASK_TOOLS: tuple[Any, ...] = (
    current_datetime_tool,
    account_lookup_tool,
    verify_account_zip_tool,
    support_contact_tool,
    retrieve_account_profile_tool,
    propose_favorite_color_update_tool,
    propose_preferred_name_update_tool,
    propose_demo_card_toggle_tool,
    list_open_cases_tool,
    propose_open_support_case_tool,
    propose_case_follow_up_tool,
    propose_case_closure_tool,
)
