"""Pure catalog output policy and transient, application-produced facts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from src.accounts import CallerSession, LookupResult, ZipResult, support_contact
from src.customer_data import AccountView, MutationKind, SupportCase
from src.observability import TaskName

SCOPE_REFUSAL = (
    "I'm sorry, I can help with the current time, account verification and settings, "
    "support cases, or contacting Customer Service."
)
CATALOG_HELP = "I can help with the current time, account verification and settings, support cases, or contacting Customer Service."
ACCOUNT_QUESTION = "What is your account number?"
ZIP_QUESTION = "What is your zip code?"
SAFE_FAILURE = "I couldn't complete that task. Please try again."


def allowed_capabilities(task_name: TaskName | None) -> frozenset[str]:
    if not isinstance(task_name, TaskName):
        return frozenset()
    return {
        TaskName.CURRENT_TIME: frozenset({"getCurrentDateTimeIso"}),
        TaskName.CUSTOMER_ACCOUNT: frozenset({"account_lookup", "verify_account_zip"}),
        TaskName.CUSTOMER_SERVICE: frozenset({"account_lookup", "verify_account_zip", "getSupportContact"}),
        TaskName.RETRIEVE_ACCOUNT: frozenset({
            "account_lookup", "verify_account_zip", "retrieveAccountProfile",
        }),
        TaskName.UPDATE_ACCOUNT: frozenset({
            "account_lookup",
            "verify_account_zip",
            "proposeFavoriteColorUpdate",
            "proposePreferredNameUpdate",
            "proposeDemoCardToggle",
        }),
        TaskName.LIST_OPEN_CASES: frozenset({
            "account_lookup", "verify_account_zip", "listOpenCases",
        }),
        TaskName.OPEN_SUPPORT_CASE: frozenset({
            "account_lookup", "verify_account_zip", "proposeOpenSupportCase",
        }),
        TaskName.FOLLOW_UP_CASE: frozenset({
            "account_lookup", "verify_account_zip", "listOpenCases", "proposeCaseFollowUp",
        }),
        TaskName.CLOSE_SUPPORT_CASE: frozenset({
            "account_lookup", "verify_account_zip", "listOpenCases", "proposeCaseClosure",
        }),
    }[task_name]


@dataclass(frozen=True)
class CatalogFacts:
    timestamp: str | None = None
    lookup: LookupResult | None = None
    zip_check: ZipResult | None = None
    contact: str | None = None
    profile: AccountView | None = None
    mutation_kind: MutationKind | None = None
    mutation_target: str | None = None
    case_number: str | None = None
    cases: tuple[SupportCase, ...] | None = None


def catalog_reply(
    task_name: TaskName,
    caller: CallerSession,
    facts: CatalogFacts,
    *,
    completed: bool,
) -> tuple[Literal["completed", "clarification_required", "failed"], str]:
    if task_name is TaskName.CURRENT_TIME:
        if facts.timestamp is None:
            return "failed", SAFE_FAILURE
        try:
            timestamp = datetime.fromisoformat(facts.timestamp)
        except (ValueError, TypeError):
            return "failed", SAFE_FAILURE
        if timestamp.utcoffset() != timedelta(0):
            return "failed", SAFE_FAILURE
        return "completed", f"The current time is {timestamp:%H:%M:%S} Greenwich Mean Time."
    identity_task = task_name in (
        TaskName.CUSTOMER_ACCOUNT,
        TaskName.CUSTOMER_SERVICE,
        TaskName.RETRIEVE_ACCOUNT,
        TaskName.UPDATE_ACCOUNT,
        TaskName.LIST_OPEN_CASES,
        TaskName.OPEN_SUPPORT_CASE,
        TaskName.FOLLOW_UP_CASE,
        TaskName.CLOSE_SUPPORT_CASE,
    )
    if not identity_task:
        return "failed", SAFE_FAILURE
    if caller.verified_account is not None and caller.verified_account != caller.current_account:
        return "failed", SAFE_FAILURE
    if caller.verified_account is not None:
        if task_name is TaskName.CUSTOMER_ACCOUNT:
            return "completed", "Your account is verified."
        if task_name is TaskName.RETRIEVE_ACCOUNT:
            if facts.profile is None:
                return "failed", SAFE_FAILURE
            card_status = "yes" if facts.profile.card_on_file else "no"
            return (
                "completed",
                f"Favorite color: {facts.profile.favorite_color}. Preferred name: "
                f"{facts.profile.preferred_name}. Demo card on file: {card_status}.",
            )
        if task_name is TaskName.UPDATE_ACCOUNT:
            if facts.profile is None or facts.mutation_kind is None or not completed:
                return "failed", SAFE_FAILURE
            if facts.mutation_kind is MutationKind.UPDATE_FAVORITE_COLOR:
                return "completed", f"Your favorite color is now {facts.profile.favorite_color}."
            if facts.mutation_kind is MutationKind.UPDATE_PREFERRED_NAME:
                return "completed", f"Your preferred name is now {facts.profile.preferred_name}."
            if facts.mutation_kind is MutationKind.SAVE_DEMO_CARD:
                return "completed", "The synthetic demo card is now saved on your account."
            if facts.mutation_kind is MutationKind.REMOVE_DEMO_CARD:
                return "completed", "The synthetic demo card has been removed from your account."
            return "failed", SAFE_FAILURE
        if task_name is TaskName.LIST_OPEN_CASES:
            if facts.cases is None:
                return "failed", SAFE_FAILURE
            if not facts.cases:
                return "completed", "You have no open support cases."
            entries = "; ".join(
                f"{case.case_number}: {case.description}" for case in facts.cases
            )
            return "completed", "Your open support cases are: " + entries + "."
        if task_name is TaskName.OPEN_SUPPORT_CASE:
            if facts.mutation_kind is not MutationKind.OPEN_CASE or facts.case_number is None:
                return "failed", SAFE_FAILURE
            return "completed", (
                f"Your support case {facts.case_number} is open. "
                "Would you like to list your open cases?"
            )
        if task_name is TaskName.FOLLOW_UP_CASE:
            if facts.cases is not None and facts.mutation_kind is None:
                if not facts.cases:
                    return "completed", "You have no open support cases to update."
                return "clarification_required", "Which open case would you like to update, and what follow-up should I add?"
            if facts.mutation_kind is not MutationKind.ADD_FOLLOW_UP or facts.mutation_target is None:
                return "failed", SAFE_FAILURE
            return "completed", f"Your follow-up was added to case {facts.mutation_target}."
        if task_name is TaskName.CLOSE_SUPPORT_CASE:
            if facts.cases is not None and facts.mutation_kind is None:
                if not facts.cases:
                    return "completed", "You have no open support cases to close."
                return "clarification_required", "Which open case would you like to close?"
            if facts.mutation_kind is not MutationKind.CLOSE_CASE or facts.mutation_target is None:
                return "failed", SAFE_FAILURE
            return "completed", f"Case {facts.mutation_target} is closed."
        contact = support_contact(caller)
        if contact is None or facts.contact != contact:
            return "failed", SAFE_FAILURE
        if contact == "800-555-1212":
            return "completed", f"Please call Customer Service at {contact}."
        return "completed", f"Please email Customer Service at {contact}."
    if completed and facts.lookup is None and facts.zip_check is None:
        return "failed", SAFE_FAILURE
    if facts.lookup is LookupResult.NOT_FOUND:
        return "clarification_required", "I couldn't find that account. " + ACCOUNT_QUESTION
    if facts.zip_check is ZipResult.MISMATCH:
        return "clarification_required", "That zip code didn't match. " + ZIP_QUESTION
    if caller.current_account is not None:
        return "clarification_required", ZIP_QUESTION
    return "clarification_required", ACCOUNT_QUESTION