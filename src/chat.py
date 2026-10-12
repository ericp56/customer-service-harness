"""Pure, transient chat state transitions and model conversation context."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Literal, TypeAlias

MAX_MESSAGE_LENGTH = 4_096
MAX_COMPLETED_PAIRS = 50
MAX_CALLER_MESSAGES = 50
MAX_ASSISTANT_MESSAGES = 100


class MessageKind(StrEnum):
    INFORMATION = "information"
    QUESTION = "question"
    CONFIRMATION = "confirmation"
    COMPLETION = "completion"
    RECOVERY = "recovery"
    NOTICE = "notice"
    PROGRESS = "progress"


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
    sequence: int = 0
    revision: int = 0
    kind: MessageKind = MessageKind.INFORMATION

    @property
    def needs_response(self) -> bool:
        return self.kind in (MessageKind.QUESTION, MessageKind.CONFIRMATION)

    @property
    def model_visible(self) -> bool:
        return self.kind not in (MessageKind.NOTICE, MessageKind.PROGRESS)


@dataclass(frozen=True)
class CallerInput:
    sequence: int
    content: str
    revision: int
    proposal_version: int | None = None


@dataclass(frozen=True)
class Dialogue:
    history: tuple[ChatMessage, ...] = ()
    inputs: tuple[CallerInput, ...] = ()
    sequence: int = 0
    revision: int = 0
    generation: int = 0

    @property
    def caller_limit(self) -> bool:
        return len(self.inputs) >= MAX_CALLER_MESSAGES

    @property
    def assistant_count(self) -> int:
        return sum(item.role == "assistant" for item in self.history)


def accept_caller(state: Dialogue, content: str, proposal_version: int | None = None) -> tuple[Dialogue, CallerInput]:
    if state.caller_limit or validate_submission(content) is not None:
        raise ValueError("input not accepted")
    sequence = state.sequence + 1
    event = CallerInput(sequence, content, state.revision + 1, proposal_version)
    message = ChatMessage("user", content, sequence, event.revision)
    return replace(state, history=(*state.history, message), inputs=(*state.inputs, event), sequence=sequence, revision=event.revision), event


def publish_assistant(state: Dialogue, content: str, kind: MessageKind, *, revision: int) -> Dialogue:
    limit = MAX_ASSISTANT_MESSAGES if kind is MessageKind.RECOVERY else MAX_ASSISTANT_MESSAGES - 1
    if state.assistant_count >= limit:
        raise ValueError("assistant limit reached")
    sequence = state.sequence + 1
    message = ChatMessage("assistant", content, sequence, revision, kind)
    return replace(state, history=(*state.history, message), sequence=sequence)


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
