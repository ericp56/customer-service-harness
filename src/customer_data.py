"""Transient synthetic account settings and support-case state."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import StrEnum
import re

from src.accounts import ACCOUNTS

MAX_CASES = 20
MAX_FOLLOW_UPS = 10
MAX_CASE_TEXT_LENGTH = 500
MAX_PREFERRED_NAME_LENGTH = 40
FAVORITE_COLORS = frozenset({"red", "blue", "green", "purple", "black", "white"})
DEMO_CARD_ALIAS = "Demo card ending in 4242"
_PROPOSAL_ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")


@dataclass(frozen=True)
class AccountProfile:
    account_number: str
    zip_code: str = field(repr=False)
    favorite_color: str
    preferred_name: str = field(repr=False)
    demo_card_alias: str | None = field(default=None, repr=False)
    revision: int = 0


@dataclass(frozen=True)
class AccountView:
    favorite_color: str
    preferred_name: str = field(repr=False)
    card_on_file: bool
    card_alias: str | None = field(repr=False)


@dataclass(frozen=True)
class CaseFollowUp:
    text: str = field(repr=False)
    created_at: str


@dataclass(frozen=True)
class SupportCase:
    case_number: str = field(repr=False)
    account_number: str = field(repr=False)
    description: str = field(repr=False)
    status: str
    created_at: str
    updated_at: str
    follow_ups: tuple[CaseFollowUp, ...] = field(default=(), repr=False)
    revision: int = 0


@dataclass(frozen=True)
class DemoData:
    profiles: tuple[AccountProfile, ...] = field(repr=False)
    cases: tuple[SupportCase, ...] = field(repr=False)
    next_case_number: int = 1003
    revision: int = 0
    consumed_mutations: tuple[str, ...] = field(default=(), repr=False)


class MutationKind(StrEnum):
    UPDATE_FAVORITE_COLOR = "update_favorite_color"
    UPDATE_PREFERRED_NAME = "update_preferred_name"
    SAVE_DEMO_CARD = "save_demo_card"
    REMOVE_DEMO_CARD = "remove_demo_card"
    OPEN_CASE = "open_case"
    ADD_FOLLOW_UP = "add_follow_up"
    CLOSE_CASE = "close_case"


class MutationOutcome(StrEnum):
    APPLIED = "applied"
    NO_CHANGE = "no_change"
    UNAUTHORIZED = "unauthorized"
    STALE = "stale"
    DUPLICATE = "duplicate"


@dataclass(frozen=True)
class PendingMutation:
    proposal_id: str = field(repr=False)
    generation: int
    account_number: str = field(repr=False)
    kind: MutationKind
    expected_data_revision: int
    value: str | None = field(default=None, repr=False)
    target_case_number: str | None = field(default=None, repr=False)
    expected_record_revision: int | None = None


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat()


def _clean_bounded_text(value: str | None, *, maximum: int, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} is required")
    cleaned = value.strip()
    if not cleaned or len(cleaned) > maximum:
        raise ValueError(f"invalid {label}")
    return cleaned


def seed_demo_data() -> DemoData:
    """Return a fresh deterministic fixture for one conversation."""
    profiles = (
        AccountProfile(
            account_number="123",
            zip_code=ACCOUNTS["123"],
            favorite_color="blue",
            preferred_name="Alex",
        ),
        AccountProfile(
            account_number="456",
            zip_code=ACCOUNTS["456"],
            favorite_color="green",
            preferred_name="Jordan",
            demo_card_alias=DEMO_CARD_ALIAS,
        ),
    )
    cases = (
        SupportCase(
            case_number="CASE-1000",
            account_number="123",
            description="Previous billing question",
            status="closed",
            created_at="2026-10-01T09:00:00+00:00",
            updated_at="2026-10-02T09:30:00+00:00",
        ),
        SupportCase(
            case_number="CASE-1001",
            account_number="123",
            description="Delivery status question",
            status="open",
            created_at="2026-10-03T10:00:00+00:00",
            updated_at="2026-10-03T10:00:00+00:00",
        ),
        SupportCase(
            case_number="CASE-1002",
            account_number="456",
            description="Service appointment question",
            status="open",
            created_at="2026-10-04T11:00:00+00:00",
            updated_at="2026-10-04T11:00:00+00:00",
        ),
    )
    return DemoData(profiles=profiles, cases=cases)


def retrieve_account(data: DemoData, verified_account: str | None) -> AccountView | None:
    if verified_account is None:
        return None
    profile = next((item for item in data.profiles if item.account_number == verified_account), None)
    if profile is None:
        return None
    return AccountView(
        favorite_color=profile.favorite_color,
        preferred_name=profile.preferred_name,
        card_on_file=profile.demo_card_alias is not None,
        card_alias=profile.demo_card_alias,
    )


def list_open_cases(data: DemoData, verified_account: str | None) -> tuple[SupportCase, ...]:
    if verified_account is None or not any(item.account_number == verified_account for item in data.profiles):
        return ()
    return tuple(
        case for case in data.cases
        if case.account_number == verified_account and case.status == "open"
    )


def propose_mutation(
    data: DemoData,
    *,
    proposal_id: str,
    generation: int,
    account_number: str,
    kind: MutationKind,
    value: str | None = None,
    target_case_number: str | None = None,
) -> PendingMutation:
    if not isinstance(proposal_id, str) or _PROPOSAL_ID_PATTERN.fullmatch(proposal_id) is None:
        raise ValueError("invalid proposal identifier")
    if generation < 0:
        raise ValueError("invalid conversation generation")
    profile = next((item for item in data.profiles if item.account_number == account_number), None)
    if profile is None:
        raise ValueError("unknown account")

    canonical_value: str | None = None
    record_revision: int | None = profile.revision
    if kind is MutationKind.UPDATE_FAVORITE_COLOR:
        canonical_value = _clean_bounded_text(value, maximum=20, label="favorite color").lower()
        if canonical_value not in FAVORITE_COLORS:
            raise ValueError("unsupported favorite color")
    elif kind is MutationKind.UPDATE_PREFERRED_NAME:
        canonical_value = _clean_bounded_text(value, maximum=MAX_PREFERRED_NAME_LENGTH, label="preferred name")
    elif kind in (MutationKind.SAVE_DEMO_CARD, MutationKind.REMOVE_DEMO_CARD):
        if value is not None or target_case_number is not None:
            raise ValueError("unexpected card mutation value")
    elif kind is MutationKind.OPEN_CASE:
        canonical_value = _clean_bounded_text(value, maximum=MAX_CASE_TEXT_LENGTH, label="case description")
        if target_case_number is not None or len(data.cases) >= MAX_CASES:
            raise ValueError("case limit reached or invalid target")
        record_revision = None
    elif kind in (MutationKind.ADD_FOLLOW_UP, MutationKind.CLOSE_CASE):
        if not isinstance(target_case_number, str) or not target_case_number:
            raise ValueError("case number is required")
        case = next((item for item in data.cases if item.case_number == target_case_number), None)
        if case is None or case.account_number != account_number or case.status != "open":
            raise ValueError("case is not available")
        if kind is MutationKind.ADD_FOLLOW_UP:
            canonical_value = _clean_bounded_text(value, maximum=MAX_CASE_TEXT_LENGTH, label="follow-up")
            if len(case.follow_ups) >= MAX_FOLLOW_UPS:
                raise ValueError("follow-up limit reached")
        elif value is not None:
            raise ValueError("unexpected case close value")
        record_revision = case.revision
    else:
        raise ValueError("unsupported mutation")

    return PendingMutation(
        proposal_id=proposal_id,
        generation=generation,
        account_number=account_number,
        kind=kind,
        expected_data_revision=data.revision,
        value=canonical_value,
        target_case_number=target_case_number,
        expected_record_revision=record_revision,
    )


def _consumed(data: DemoData, proposal_id: str) -> DemoData:
    return replace(data, consumed_mutations=(*data.consumed_mutations, proposal_id))


def commit_mutation(
    data: DemoData,
    proposal: PendingMutation,
    *,
    generation: int,
    verified_account: str | None,
    now: datetime | None = None,
) -> tuple[DemoData, MutationOutcome]:
    """Apply an approved proposal once after rechecking its server-side bindings."""
    if proposal.proposal_id in data.consumed_mutations:
        return data, MutationOutcome.DUPLICATE
    if generation != proposal.generation or data.revision != proposal.expected_data_revision:
        return data, MutationOutcome.STALE
    if verified_account != proposal.account_number:
        return data, MutationOutcome.UNAUTHORIZED

    profiles = list(data.profiles)
    profile_index = next(
        (index for index, item in enumerate(profiles) if item.account_number == proposal.account_number),
        None,
    )
    if profile_index is None:
        return data, MutationOutcome.UNAUTHORIZED
    profile = profiles[profile_index]
    cases = list(data.cases)
    consumed = _consumed(data, proposal.proposal_id)
    timestamp = _utc_text(now or datetime.now(timezone.utc))

    if proposal.kind is MutationKind.UPDATE_FAVORITE_COLOR:
        if profile.revision != proposal.expected_record_revision:
            return data, MutationOutcome.STALE
        if profile.favorite_color == proposal.value:
            return consumed, MutationOutcome.NO_CHANGE
        profiles[profile_index] = replace(
            profile, favorite_color=proposal.value or "", revision=profile.revision + 1
        )
    elif proposal.kind is MutationKind.UPDATE_PREFERRED_NAME:
        if profile.revision != proposal.expected_record_revision:
            return data, MutationOutcome.STALE
        if profile.preferred_name == proposal.value:
            return consumed, MutationOutcome.NO_CHANGE
        profiles[profile_index] = replace(
            profile, preferred_name=proposal.value or "", revision=profile.revision + 1
        )
    elif proposal.kind is MutationKind.SAVE_DEMO_CARD:
        if profile.revision != proposal.expected_record_revision:
            return data, MutationOutcome.STALE
        if profile.demo_card_alias is not None:
            return consumed, MutationOutcome.NO_CHANGE
        profiles[profile_index] = replace(
            profile, demo_card_alias=DEMO_CARD_ALIAS, revision=profile.revision + 1
        )
    elif proposal.kind is MutationKind.REMOVE_DEMO_CARD:
        if profile.revision != proposal.expected_record_revision:
            return data, MutationOutcome.STALE
        if profile.demo_card_alias is None:
            return consumed, MutationOutcome.NO_CHANGE
        profiles[profile_index] = replace(profile, demo_card_alias=None, revision=profile.revision + 1)
    elif proposal.kind is MutationKind.OPEN_CASE:
        if len(cases) >= MAX_CASES:
            return data, MutationOutcome.STALE
        case_number = f"CASE-{data.next_case_number}"
        if any(case.case_number == case_number for case in cases):
            return data, MutationOutcome.STALE
        cases.append(SupportCase(
            case_number=case_number,
            account_number=proposal.account_number,
            description=proposal.value or "",
            status="open",
            created_at=timestamp,
            updated_at=timestamp,
        ))
        return replace(
            data,
            cases=tuple(cases),
            next_case_number=data.next_case_number + 1,
            revision=data.revision + 1,
            consumed_mutations=consumed.consumed_mutations,
        ), MutationOutcome.APPLIED
    elif proposal.kind in (MutationKind.ADD_FOLLOW_UP, MutationKind.CLOSE_CASE):
        case_index = next(
            (index for index, item in enumerate(cases) if item.case_number == proposal.target_case_number),
            None,
        )
        if case_index is None:
            return data, MutationOutcome.STALE
        case = cases[case_index]
        if (
            case.account_number != proposal.account_number
            or case.status != "open"
            or case.revision != proposal.expected_record_revision
        ):
            return data, MutationOutcome.STALE
        if proposal.kind is MutationKind.ADD_FOLLOW_UP:
            if len(case.follow_ups) >= MAX_FOLLOW_UPS:
                return data, MutationOutcome.STALE
            cases[case_index] = replace(
                case,
                follow_ups=(*case.follow_ups, CaseFollowUp(proposal.value or "", timestamp)),
                updated_at=timestamp,
                revision=case.revision + 1,
            )
        else:
            cases[case_index] = replace(
                case, status="closed", updated_at=timestamp, revision=case.revision + 1
            )
    else:
        return data, MutationOutcome.STALE

    return replace(
        data,
        profiles=tuple(profiles),
        cases=tuple(cases),
        revision=data.revision + 1,
        consumed_mutations=consumed.consumed_mutations,
    ), MutationOutcome.APPLIED
