from __future__ import annotations

from dataclasses import fields
from datetime import datetime, timezone

import pytest

from src.customer_data import (
    MutationKind,
    MutationOutcome,
    commit_mutation,
    list_open_cases,
    propose_mutation,
    retrieve_account,
    seed_demo_data,
)


def _proposal(data, *, proposal_id: str = "proposal-1", **kwargs):
    return propose_mutation(
        data,
        proposal_id=proposal_id,
        generation=1,
        account_number="123",
        **kwargs,
    )


def test_seeded_profiles_are_distinct_and_retrieval_has_no_zip_field() -> None:
    data = seed_demo_data()

    first = retrieve_account(data, "123")
    second = retrieve_account(data, "456")

    assert first is not None and second is not None
    assert (first.favorite_color, first.preferred_name) != (second.favorite_color, second.preferred_name)
    assert first.card_on_file is False
    assert second.card_on_file is True
    assert "zip_code" not in {field.name for field in fields(first)}


def test_open_case_listing_is_scoped_to_owner_and_status() -> None:
    data = seed_demo_data()

    first_cases = list_open_cases(data, "123")
    second_cases = list_open_cases(data, "456")

    assert first_cases and second_cases
    assert all(case.account_number == "123" and case.status == "open" for case in first_cases)
    assert all(case.account_number == "456" and case.status == "open" for case in second_cases)
    assert {case.case_number for case in first_cases}.isdisjoint({case.case_number for case in second_cases})


def test_private_sample_values_are_excluded_from_domain_representations() -> None:
    data = seed_demo_data()
    proposal = _proposal(data, kind=MutationKind.UPDATE_PREFERRED_NAME, value="Private Name")

    for value in (
        "12345",
        "54321",
        "Alex",
        "Jordan",
        "Delivery status question",
        "Service appointment question",
        "Demo card ending in 4242",
        "Private Name",
    ):
        assert value not in repr(data)
        assert value not in repr(data.profiles)
        assert value not in repr(data.cases)
        assert value not in repr(proposal)


def test_profile_proposal_does_not_mutate_until_approved_commit() -> None:
    data = seed_demo_data()
    original = retrieve_account(data, "123")
    proposal = _proposal(data, kind=MutationKind.UPDATE_FAVORITE_COLOR, value="red")

    assert retrieve_account(data, "123") == original
    changed, outcome = commit_mutation(
        data,
        proposal,
        generation=1,
        verified_account="123",
        now=datetime(2026, 10, 21, tzinfo=timezone.utc),
    )

    assert outcome is MutationOutcome.APPLIED
    assert retrieve_account(changed, "123").favorite_color == "red"
    assert retrieve_account(data, "123") == original


def test_commit_requires_matching_verified_account_and_generation() -> None:
    data = seed_demo_data()
    proposal = _proposal(data, kind=MutationKind.UPDATE_PREFERRED_NAME, value="Riley")

    unchanged, wrong_account = commit_mutation(data, proposal, generation=1, verified_account="456")
    unchanged_again, wrong_generation = commit_mutation(data, proposal, generation=2, verified_account="123")

    assert unchanged == data and wrong_account is MutationOutcome.UNAUTHORIZED
    assert unchanged_again == data and wrong_generation is MutationOutcome.STALE


def test_mutation_replay_and_stale_data_revision_are_rejected() -> None:
    data = seed_demo_data()
    first = _proposal(data, proposal_id="first", kind=MutationKind.UPDATE_FAVORITE_COLOR, value="red")
    second = _proposal(data, proposal_id="second", kind=MutationKind.UPDATE_PREFERRED_NAME, value="Riley")
    changed, outcome = commit_mutation(data, first, generation=1, verified_account="123")

    replayed, replay_outcome = commit_mutation(changed, first, generation=1, verified_account="123")
    stale, stale_outcome = commit_mutation(changed, second, generation=1, verified_account="123")

    assert outcome is MutationOutcome.APPLIED
    assert replayed == changed and replay_outcome is MutationOutcome.DUPLICATE
    assert stale == changed and stale_outcome is MutationOutcome.STALE


def test_mutation_values_are_bounded_and_allowlisted() -> None:
    data = seed_demo_data()

    with pytest.raises(ValueError):
        _proposal(data, kind=MutationKind.UPDATE_FAVORITE_COLOR, value="chartreuse")
    with pytest.raises(ValueError):
        _proposal(data, kind=MutationKind.UPDATE_PREFERRED_NAME, value="x" * 41)
    with pytest.raises(ValueError):
        _proposal(data, kind=MutationKind.OPEN_CASE, value=" ")
    with pytest.raises(ValueError):
        _proposal(data, kind=MutationKind.OPEN_CASE, value="x" * 501)


def test_open_case_is_generated_once_and_followup_is_bounded() -> None:
    data = seed_demo_data()
    proposal = _proposal(data, kind=MutationKind.OPEN_CASE, value="Delivery question")
    changed, outcome = commit_mutation(data, proposal, generation=1, verified_account="123")

    assert outcome is MutationOutcome.APPLIED
    created = tuple(case for case in list_open_cases(changed, "123") if case.description == "Delivery question")
    assert len(created) == 1
    assert created[0].case_number not in {case.case_number for case in data.cases}

    current = changed
    for index in range(10):
        follow_up = _proposal(
            current,
            proposal_id=f"follow-up-{index}",
            kind=MutationKind.ADD_FOLLOW_UP,
            target_case_number=created[0].case_number,
            value=f"Update {index}",
        )
        current, outcome = commit_mutation(current, follow_up, generation=1, verified_account="123")
        assert outcome is MutationOutcome.APPLIED

    with pytest.raises(ValueError):
        _proposal(
            current,
            proposal_id="follow-up-overflow",
            kind=MutationKind.ADD_FOLLOW_UP,
            target_case_number=created[0].case_number,
            value="One too many",
        )


def test_foreign_and_closed_cases_cannot_be_changed() -> None:
    data = seed_demo_data()
    foreign_case = next(case for case in data.cases if case.account_number == "456" and case.status == "open")
    closed_case = next(case for case in data.cases if case.account_number == "123" and case.status == "closed")

    with pytest.raises(ValueError):
        _proposal(data, kind=MutationKind.CLOSE_CASE, target_case_number=foreign_case.case_number)
    with pytest.raises(ValueError):
        _proposal(data, kind=MutationKind.ADD_FOLLOW_UP, target_case_number=closed_case.case_number, value="More")


def test_case_limit_is_enforced_before_proposing_another_open_case() -> None:
    data = seed_demo_data()
    current = data
    for index in range(20 - len(data.cases)):
        proposal = _proposal(current, proposal_id=f"open-{index}", kind=MutationKind.OPEN_CASE, value=f"Issue {index}")
        current, outcome = commit_mutation(current, proposal, generation=1, verified_account="123")
        assert outcome is MutationOutcome.APPLIED

    with pytest.raises(ValueError):
        _proposal(current, proposal_id="overflow", kind=MutationKind.OPEN_CASE, value="Final issue")


def test_demo_card_toggle_changes_only_the_fixed_alias() -> None:
    data = seed_demo_data()
    save = propose_mutation(
        data,
        proposal_id="save-card",
        generation=1,
        account_number="123",
        kind=MutationKind.SAVE_DEMO_CARD,
    )
    saved, save_outcome = commit_mutation(data, save, generation=1, verified_account="123")
    remove = propose_mutation(
        saved,
        proposal_id="remove-card",
        generation=1,
        account_number="123",
        kind=MutationKind.REMOVE_DEMO_CARD,
    )
    removed, remove_outcome = commit_mutation(saved, remove, generation=1, verified_account="123")

    assert save_outcome is MutationOutcome.APPLIED
    assert retrieve_account(saved, "123").card_alias == "Demo card ending in 4242"
    assert remove_outcome is MutationOutcome.APPLIED
    assert retrieve_account(removed, "123").card_on_file is False


def test_close_case_is_one_way_and_removes_it_from_open_list() -> None:
    data = seed_demo_data()
    open_case = next(case for case in list_open_cases(data, "123"))
    proposal = _proposal(data, kind=MutationKind.CLOSE_CASE, target_case_number=open_case.case_number)

    closed, outcome = commit_mutation(data, proposal, generation=1, verified_account="123")

    assert outcome is MutationOutcome.APPLIED
    assert open_case.case_number not in {case.case_number for case in list_open_cases(closed, "123")}
    with pytest.raises(ValueError):
        _proposal(
            closed,
            proposal_id="follow-closed",
            kind=MutationKind.ADD_FOLLOW_UP,
            target_case_number=open_case.case_number,
            value="This must not be added",
        )
