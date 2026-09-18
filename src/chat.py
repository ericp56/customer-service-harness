"""Pure, transient chat state transitions and model conversation context."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, TypeAlias

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
    ALREADY_SENDING = "already_sending"
    LIMIT_REACHED = "limit_reached"
    RETRY_UNAVAILABLE = "retry_unavailable"


@dataclass(frozen=True)
class ChatMessage:
    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True)
class ToolInvocation:
    call_id: str
    name: str
    arguments: str
    output: str


ConversationItem: TypeAlias = ChatMessage | ToolInvocation


@dataclass(frozen=True)
class ActiveConversation:
    history: tuple[ConversationItem, ...] = ()
    pending_text: str | None = None
    submission_state: SubmissionState = SubmissionState.IDLE

    @property
    def completed_pairs(self) -> int:
        return sum(isinstance(item, ChatMessage) and item.role == "user" for item in self.history)


@dataclass(frozen=True)
class Transition:
    state: ActiveConversation
    outcome: Outcome


def new_conversation() -> ActiveConversation:
    return ActiveConversation()


def validate_submission(content: str) -> Outcome | None:
    if not content.strip():
        return Outcome.BLANK
    if len(content) > MAX_MESSAGE_LENGTH:
        return Outcome.TOO_LONG
    return None


def begin_submission(state: ActiveConversation, content: str) -> Transition:
    if state.submission_state is SubmissionState.SENDING:
        return Transition(state, Outcome.ALREADY_SENDING)
    if state.submission_state is SubmissionState.LIMIT_REACHED:
        return Transition(state, Outcome.LIMIT_REACHED)
    validation_outcome = validate_submission(content)
    if validation_outcome is not None:
        return Transition(state, validation_outcome)
    if state.completed_pairs >= MAX_COMPLETED_PAIRS:
        return Transition(
            ActiveConversation(state.history, state.pending_text, SubmissionState.LIMIT_REACHED),
            Outcome.LIMIT_REACHED,
        )
    return Transition(ActiveConversation(state.history, content, SubmissionState.SENDING), Outcome.SENT)


def complete_submission(
    state: ActiveConversation, reply: str, tool_invocations: tuple[ToolInvocation, ...] = ()
) -> Transition:
    if state.submission_state is not SubmissionState.SENDING or state.pending_text is None:
        return Transition(state, Outcome.ALREADY_SENDING)
    if not reply.strip():
        return fail_submission(state)
    history = state.history + (
        ChatMessage("user", state.pending_text),
        *tool_invocations,
        ChatMessage("assistant", reply),
    )
    next_state = (
        SubmissionState.LIMIT_REACHED
        if state.completed_pairs + 1 >= MAX_COMPLETED_PAIRS
        else SubmissionState.IDLE
    )
    return Transition(ActiveConversation(history=history, submission_state=next_state), Outcome.SENT)


def fail_submission(state: ActiveConversation, outcome: Outcome = Outcome.FAILED) -> Transition:
    if state.submission_state is not SubmissionState.SENDING:
        return Transition(state, Outcome.RETRY_UNAVAILABLE)
    return Transition(ActiveConversation(state.history, state.pending_text, SubmissionState.FAILED), outcome)


def begin_retry(state: ActiveConversation) -> Transition:
    if state.submission_state is not SubmissionState.FAILED or state.pending_text is None:
        return Transition(state, Outcome.RETRY_UNAVAILABLE)
    return Transition(ActiveConversation(state.history, state.pending_text, SubmissionState.SENDING), Outcome.SENT)
