"""Pure, transient Echo Web Chat validation and state transitions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

MAX_MESSAGE_LENGTH = 4_096
MAX_COMPLETED_PAIRS = 50


class SubmissionState(StrEnum):
    IDLE = "idle"
    SENDING = "sending"
    FAILED = "failed"
    LIMIT_REACHED = "limit_reached"


class Outcome(StrEnum):
    IDLE = "idle"
    SENT = "sent"
    BLANK = "blank"
    TOO_LONG = "too_long"
    FAILED = "failed"
    MISMATCHED_ECHO = "mismatched_echo"
    ALREADY_SENDING = "already_sending"
    LIMIT_REACHED = "limit_reached"
    RETRY_UNAVAILABLE = "retry_unavailable"


@dataclass(frozen=True)
class ChatMessage:
    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True)
class ActiveConversation:
    history: tuple[ChatMessage, ...] = ()
    pending_text: str | None = None
    submission_state: SubmissionState = SubmissionState.IDLE

    @property
    def completed_pairs(self) -> int:
        return len(self.history) // 2


@dataclass(frozen=True)
class Transition:
    state: ActiveConversation
    outcome: Outcome


def new_conversation() -> ActiveConversation:
    """Create empty page-session state without persisting any content."""
    return ActiveConversation()


def validate_submission(content: str) -> Outcome | None:
    """Return the validation outcome, preserving valid input without modification."""
    if not content.strip():
        return Outcome.BLANK
    if len(content) > MAX_MESSAGE_LENGTH:
        return Outcome.TOO_LONG
    return None


def begin_submission(state: ActiveConversation, content: str) -> Transition:
    """Validate and begin one submission without appending a partial pair."""
    if state.submission_state is SubmissionState.SENDING:
        return Transition(state, Outcome.ALREADY_SENDING)
    if state.submission_state is SubmissionState.LIMIT_REACHED:
        return Transition(state, Outcome.LIMIT_REACHED)

    validation_outcome = validate_submission(content)
    if validation_outcome is not None:
        return Transition(state, validation_outcome)

    if state.completed_pairs >= MAX_COMPLETED_PAIRS:
        limited = ActiveConversation(
            history=state.history,
            pending_text=state.pending_text,
            submission_state=SubmissionState.LIMIT_REACHED,
        )
        return Transition(limited, Outcome.LIMIT_REACHED)

    sending = ActiveConversation(
        history=state.history,
        pending_text=content,
        submission_state=SubmissionState.SENDING,
    )
    return Transition(sending, Outcome.SENT)


def complete_submission(state: ActiveConversation, echo: str) -> Transition:
    """Append an exact pair only after the echo output is verified."""
    if state.submission_state is not SubmissionState.SENDING or state.pending_text is None:
        return Transition(state, Outcome.ALREADY_SENDING)
    if echo != state.pending_text:
        return fail_submission(state, Outcome.MISMATCHED_ECHO)

    history = state.history + (
        ChatMessage(role="user", content=state.pending_text),
        ChatMessage(role="assistant", content=echo),
    )
    next_status = (
        SubmissionState.LIMIT_REACHED
        if len(history) // 2 >= MAX_COMPLETED_PAIRS
        else SubmissionState.IDLE
    )
    completed = ActiveConversation(history=history, submission_state=next_status)
    return Transition(completed, Outcome.SENT)


def fail_submission(state: ActiveConversation, outcome: Outcome = Outcome.FAILED) -> Transition:
    """Retain valid pending content after a declared operational failure."""
    if state.submission_state is not SubmissionState.SENDING:
        return Transition(state, Outcome.RETRY_UNAVAILABLE)
    failed = ActiveConversation(
        history=state.history,
        pending_text=state.pending_text,
        submission_state=SubmissionState.FAILED,
    )
    return Transition(failed, outcome)


def begin_retry(state: ActiveConversation) -> Transition:
    """Retry exactly the previously retained valid input."""
    if state.submission_state is not SubmissionState.FAILED or state.pending_text is None:
        return Transition(state, Outcome.RETRY_UNAVAILABLE)
    retrying = ActiveConversation(
        history=state.history,
        pending_text=state.pending_text,
        submission_state=SubmissionState.SENDING,
    )
    return Transition(retrying, Outcome.SENT)
