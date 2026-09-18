from src.echo import (
    MAX_COMPLETED_PAIRS,
    MAX_MESSAGE_LENGTH,
    ActiveConversation,
    Outcome,
    SubmissionState,
    Transition,
    begin_retry,
    begin_submission,
    complete_submission,
    fail_submission,
    new_conversation,
    validate_submission,
)


def complete(state: ActiveConversation, text: str) -> ActiveConversation:
    started = begin_submission(state, text)
    assert started.outcome is Outcome.SENT
    completed = complete_submission(started.state, text)
    assert completed.outcome is Outcome.SENT
    return completed.state


def test_accepts_and_preserves_exact_input() -> None:
    content = "  Héllo, <tag>!\n次の行  "
    started = begin_submission(new_conversation(), content)

    assert started.state.pending_text == content
    finished = complete_submission(started.state, content)

    assert [(message.role, message.content) for message in finished.state.history] == [
        ("user", content),
        ("assistant", content),
    ]
    assert finished.state.pending_text is None
    assert finished.state.submission_state is SubmissionState.IDLE


def test_rejects_blank_and_whitespace_without_state_changes() -> None:
    state = new_conversation()

    assert validate_submission("") is Outcome.BLANK
    assert validate_submission(" \n\t") is Outcome.BLANK
    assert begin_submission(state, " \n\t") == Transition(state, Outcome.BLANK)


def test_enforces_unicode_code_point_limit() -> None:
    accepted = "界" * MAX_MESSAGE_LENGTH
    rejected = "界" * (MAX_MESSAGE_LENGTH + 1)

    assert validate_submission(accepted) is None
    assert validate_submission(rejected) is Outcome.TOO_LONG


def test_failed_submission_retains_exact_input_and_retry_appends_once() -> None:
    original = "retry this\nexactly"
    started = begin_submission(new_conversation(), original)
    failed = fail_submission(started.state)

    assert failed.state.pending_text == original
    assert failed.state.history == ()
    assert failed.state.submission_state is SubmissionState.FAILED

    retried = begin_retry(failed.state)
    complete_after_retry = complete_submission(retried.state, original)

    assert len(complete_after_retry.state.history) == 2
    assert complete_after_retry.state.history[0].content == original
    assert complete_after_retry.state.history[1].content == original


def test_mismatched_echo_fails_without_a_partial_pair() -> None:
    started = begin_submission(new_conversation(), "original")
    finished = complete_submission(started.state, "changed")

    assert finished.outcome is Outcome.MISMATCHED_ECHO
    assert finished.state.history == ()
    assert finished.state.pending_text == "original"
    assert finished.state.submission_state is SubmissionState.FAILED


def test_prevents_duplicate_submission_while_sending() -> None:
    started = begin_submission(new_conversation(), "one")
    duplicate = begin_submission(started.state, "two")

    assert duplicate.outcome is Outcome.ALREADY_SENDING
    assert duplicate.state == started.state


def test_limits_completed_pairs_and_allows_explicit_reset() -> None:
    state = new_conversation()
    for index in range(MAX_COMPLETED_PAIRS):
        state = complete(state, f"message {index}")

    assert state.completed_pairs == MAX_COMPLETED_PAIRS
    assert state.submission_state is SubmissionState.LIMIT_REACHED
    assert begin_submission(state, "one more").outcome is Outcome.LIMIT_REACHED
    assert new_conversation() == ActiveConversation()
