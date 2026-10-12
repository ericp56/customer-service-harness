"""Hard-coded demo accounts and pure caller verification rules."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
import re

ACCOUNTS = {"123": "12345", "456": "54321"}
MAX_ACCOUNT_ATTEMPTS = 3
MAX_ZIP_ATTEMPTS = 2
PHONE_SUPPORT_ZIP = "12345"
PHONE_SUPPORT_CONTACT = "800-555-1212"
EMAIL_SUPPORT_CONTACT = "help@demo.com"
_ACCOUNT_PATTERN = re.compile(r"[0-9]{1,12}")
_ZIP_PATTERN = re.compile(r"[0-9]{5}")


class LookupResult(StrEnum):
    FOUND = "found"
    NOT_FOUND = "not_found"
    SESSION_ENDED = "session_ended"


class ZipResult(StrEnum):
    MATCH = "match"
    MISMATCH = "mismatch"
    NO_ACCOUNT = "no_account"
    SESSION_ENDED = "session_ended"


@dataclass(frozen=True)
class CallerSession:
    current_account: str | None = None
    account_attempts: int = 0
    zip_attempts: int = 0
    verified_account: str | None = None
    ended: bool = False


def is_account_number(value: str) -> bool:
    return _ACCOUNT_PATTERN.fullmatch(value) is not None


def correct_account(session: CallerSession, account_number: str) -> CallerSession:
    if session.ended or account_number == session.current_account:
        return session
    if not is_account_number(account_number):
        raise ValueError("invalid account correction")
    return replace(session, current_account=None, verified_account=None)


def lookup_account(session: CallerSession, account_number: str) -> tuple[CallerSession, LookupResult]:
    if session.ended:
        return session, LookupResult.SESSION_ENDED
    candidate = account_number.strip()
    if candidate not in ACCOUNTS:
        attempts = session.account_attempts + 1
        return (
            replace(session, account_attempts=attempts, ended=attempts >= MAX_ACCOUNT_ATTEMPTS),
            LookupResult.NOT_FOUND if attempts < MAX_ACCOUNT_ATTEMPTS else LookupResult.SESSION_ENDED,
        )
    if candidate == session.current_account:
        return session, LookupResult.FOUND
    return replace(session, current_account=candidate, zip_attempts=0, verified_account=None), LookupResult.FOUND


def verify_zip(session: CallerSession, zip_code: str) -> tuple[CallerSession, ZipResult]:
    if session.ended:
        return session, ZipResult.SESSION_ENDED
    if session.current_account is None:
        return session, ZipResult.NO_ACCOUNT
    candidate = zip_code.strip()
    if _ZIP_PATTERN.fullmatch(candidate) and candidate == ACCOUNTS[session.current_account]:
        return replace(session, verified_account=session.current_account), ZipResult.MATCH
    attempts = session.zip_attempts + 1
    if attempts >= MAX_ZIP_ATTEMPTS:
        return replace(session, zip_attempts=attempts, ended=True), ZipResult.SESSION_ENDED
    return replace(session, zip_attempts=attempts), ZipResult.MISMATCH


def support_contact(session: CallerSession) -> str | None:
    if session.ended or session.verified_account is None or session.verified_account != session.current_account:
        return None
    if ACCOUNTS[session.verified_account] == PHONE_SUPPORT_ZIP:
        return PHONE_SUPPORT_CONTACT
    return EMAIL_SUPPORT_CONTACT
