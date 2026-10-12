from __future__ import annotations

from src.accounts import (
    CallerSession,
    LookupResult,
    ZipResult,
    lookup_account,
    support_contact,
    verify_zip,
)


def test_known_accounts_are_found_and_unknown_are_not() -> None:
    session, result = lookup_account(CallerSession(), "123")
    assert result is LookupResult.FOUND
    assert session.current_account == "123"
    _, result = lookup_account(CallerSession(), "999")
    assert result is LookupResult.NOT_FOUND


def test_third_unknown_account_ends_the_session() -> None:
    session = CallerSession()
    session, first = lookup_account(session, "1")
    session, second = lookup_account(session, "2")
    session, third = lookup_account(session, "3")
    assert (first, second) == (LookupResult.NOT_FOUND, LookupResult.NOT_FOUND)
    assert third is LookupResult.SESSION_ENDED
    assert session.ended


def test_known_account_after_unknown_attempts_still_works() -> None:
    session, _ = lookup_account(CallerSession(), "1")
    session, _ = lookup_account(session, "2")
    session, result = lookup_account(session, "456")
    assert result is LookupResult.FOUND
    assert not session.ended


def test_matching_zip_verifies_each_account() -> None:
    for account, zip_code in (("123", "12345"), ("456", "54321")):
        session, _ = lookup_account(CallerSession(), account)
        session, result = verify_zip(session, zip_code)
        assert result is ZipResult.MATCH
        assert session.verified_account == account


def test_one_mismatch_then_match_succeeds() -> None:
    session, _ = lookup_account(CallerSession(), "123")
    session, first = verify_zip(session, "99999")
    session, second = verify_zip(session, "12345")
    assert first is ZipResult.MISMATCH
    assert second is ZipResult.MATCH
    assert not session.ended


def test_second_mismatch_ends_the_session() -> None:
    session, _ = lookup_account(CallerSession(), "123")
    session, _ = verify_zip(session, "99999")
    session, result = verify_zip(session, "11111")
    assert result is ZipResult.SESSION_ENDED
    assert session.ended
    assert session.verified_account is None


def test_malformed_zip_counts_as_a_mismatch() -> None:
    session, _ = lookup_account(CallerSession(), "123")
    session, result = verify_zip(session, "1234")
    assert result is ZipResult.MISMATCH
    assert session.zip_attempts == 1


def test_different_known_account_resets_zip_attempts_but_not_account_attempts() -> None:
    session, _ = lookup_account(CallerSession(), "1")
    session, _ = lookup_account(session, "123")
    session, _ = verify_zip(session, "99999")
    assert session.zip_attempts == 1
    session, _ = lookup_account(session, "456")
    assert session.zip_attempts == 0
    assert session.account_attempts == 1


def test_same_account_does_not_reset_zip_attempts() -> None:
    session, _ = lookup_account(CallerSession(), "123")
    session, _ = verify_zip(session, "99999")
    session, _ = lookup_account(session, "123")
    assert session.zip_attempts == 1


def test_zip_without_account_is_rejected() -> None:
    session, result = verify_zip(CallerSession(), "12345")
    assert result is ZipResult.NO_ACCOUNT
    assert session.zip_attempts == 0


def test_ended_session_rejects_further_checks() -> None:
    ended = CallerSession(ended=True)
    assert lookup_account(ended, "123")[1] is LookupResult.SESSION_ENDED
    assert verify_zip(ended, "12345")[1] is ZipResult.SESSION_ENDED


def test_support_contact_depends_on_verified_zip() -> None:
    assert support_contact(CallerSession()) is None
    assert support_contact(CallerSession(current_account="123")) is None
    assert support_contact(CallerSession(current_account="123", verified_account="123")) == "800-555-1212"
    assert support_contact(CallerSession(current_account="456", verified_account="456")) == "help@demo.com"
    assert support_contact(CallerSession(verified_account="123", ended=True)) is None


def test_correction_invalidates_identity_without_refunding_attempts() -> None:
    from src.accounts import correct_account

    original = CallerSession(current_account="123", verified_account="123", account_attempts=2, zip_attempts=1)
    corrected = correct_account(original, "456")
    assert corrected.current_account is None and corrected.verified_account is None
    assert corrected.account_attempts == 2 and corrected.zip_attempts == 1
    assert support_contact(corrected) is None
    selected, outcome = lookup_account(corrected, "456")
    assert outcome is LookupResult.FOUND and selected.zip_attempts == 0
    assert selected.account_attempts == 2 and selected.verified_account is None
    assert correct_account(original, "123") == original
    assert correct_account(CallerSession(ended=True), "456").ended


def test_contact_rejects_superseded_verified_account() -> None:
    assert support_contact(CallerSession(current_account="456", verified_account="123")) is None
