"""Pure catalog output policy and transient, application-produced facts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from src.accounts import CallerSession, LookupResult, ZipResult, support_contact
from src.observability import TaskName

SCOPE_REFUSAL = (
    "I'm sorry, I can only help with the current time, account verification, "
    "or contacting Customer Service."
)
CATALOG_HELP = "I can help with the current time, account verification, or contacting Customer Service."
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
    }[task_name]


@dataclass(frozen=True)
class CatalogFacts:
    timestamp: str | None = None
    lookup: LookupResult | None = None
    zip_check: ZipResult | None = None
    contact: str | None = None


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
    if task_name not in (TaskName.CUSTOMER_ACCOUNT, TaskName.CUSTOMER_SERVICE):
        return "failed", SAFE_FAILURE
    if caller.verified_account is not None and caller.verified_account != caller.current_account:
        return "failed", SAFE_FAILURE
    if caller.verified_account is not None:
        if task_name is TaskName.CUSTOMER_ACCOUNT:
            return "completed", "Your account is verified."
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