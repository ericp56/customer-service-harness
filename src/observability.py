"""In-memory, fixed-cardinality diagnostics with no visitor content or identifiers."""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
import json
import re
import sys
from time import monotonic
import traceback


class DiagnosticOutcome(StrEnum):
    SUCCESS = "success"
    VALIDATION_BLANK = "validation_blank"
    VALIDATION_TOO_LONG = "validation_too_long"
    OPERATIONAL_FAILURE = "operational_failure"
    INVALID_CONFIGURATION = "invalid_configuration"
    TIMEOUT_OR_UNAVAILABLE = "timeout_or_unavailable"
    PROVIDER_REJECTED = "provider_rejected"
    UNUSABLE_RESPONSE = "unusable_response"
    LIMIT_REACHED = "limit_reached"
    DUPLICATE_PREVENTED = "duplicate_prevented"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    TASK_CANCELED = "task_canceled"
    TASK_REJECTED = "task_rejected"
    TASK_TIMEOUT = "task_timeout"
    TASK_APPROVAL_REQUIRED = "task_approval_required"
    TASK_CLARIFICATION_REQUIRED = "task_clarification_required"
    TASK_UNSUPPORTED_CAPABILITY = "task_unsupported_capability"
    TASK_SESSION_ENDED = "task_session_ended"


class HealthStatus(StrEnum):
    READY = "ready"
    NOT_READY = "not_ready"


class TaskName(StrEnum):
    CURRENT_TIME = "Retrieve the current time"
    CUSTOMER_ACCOUNT = "Retrieve customer account"
    CUSTOMER_SERVICE = "Transfer to Customer Service"
    RETRIEVE_ACCOUNT = "Retrieve Account"
    UPDATE_ACCOUNT = "Update Account"
    LIST_OPEN_CASES = "List Open Cases"
    OPEN_SUPPORT_CASE = "Open Support Case"
    FOLLOW_UP_CASE = "Follow Up Support Case"
    CLOSE_SUPPORT_CASE = "Close Support Case"


@dataclass(frozen=True)
class DiagnosticEvent:
    """A deliberately content-free event shape with a finite set of values."""

    name: str
    outcome: DiagnosticOutcome
    duration_bucket: str
    queue_depth_bucket: str
    health: HealthStatus


def duration_bucket(seconds: float) -> str:
    if seconds < 0.1:
        return "under_100ms"
    if seconds < 1.0:
        return "100ms_to_under_1s"
    return "1s_or_more"


def queue_depth_bucket(depth: int) -> str:
    if depth <= 0:
        return "empty"
    if depth < 50:
        return "1_to_49"
    if depth < 100:
        return "50_to_99"
    return "100_or_more"


@dataclass
class Diagnostics:
    """Aggregate operational diagnostics held only in process memory."""

    outcomes: Counter[DiagnosticOutcome] = field(default_factory=Counter)
    events: deque[DiagnosticEvent] = field(default_factory=lambda: deque(maxlen=256))
    ready: bool = True

    def record(
        self,
        outcome: DiagnosticOutcome,
        *,
        started_at: float,
        queue_depth: int = 0,
        error: Exception | None = None,
        step: str = "chat_submission",
        account_number: str | None = None,
        task_id: str | None = None,
        task_name: TaskName | None = None,
    ) -> None:
        event = DiagnosticEvent(
            name="chat_submission",
            outcome=outcome,
            duration_bucket=duration_bucket(max(0.0, monotonic() - started_at)),
            queue_depth_bucket=queue_depth_bucket(max(0, queue_depth)),
            health=HealthStatus.READY if self.ready else HealthStatus.NOT_READY,
        )
        self.outcomes[outcome] += 1
        self.events.append(event)
        payload: dict[str, object] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "component": step,
            "level": "ERROR" if error else "INFO",
            "message": _sanitize(str(error)) if error else outcome.value,
            "step": step,
            "duration_ms": max(0, round((monotonic() - started_at) * 1000)),
        }
        # Account numbers are the only caller-supplied value permitted in diagnostics.
        if account_number is not None and re.fullmatch(r"[0-9]{1,12}", account_number):
            payload["account_number"] = account_number
        if task_id is not None and _TASK_ID_PATTERN.fullmatch(task_id):
            payload["task_id"] = task_id
        if outcome is DiagnosticOutcome.TASK_COMPLETED and isinstance(task_name, TaskName):
            payload["task_name"] = task_name.value
        if error:
            stack = [f"{frame.filename}:{frame.lineno}" for frame in traceback.extract_tb(error.__traceback__)]
            if stack:
                payload["stack"] = stack
        try:
            print(json.dumps(payload, separators=(",", ":"), ensure_ascii=True), file=sys.stdout, flush=True)
        except (TypeError, ValueError):
            print("diagnostic serialization failed", file=sys.stdout, flush=True)

    def health(self) -> HealthStatus:
        return HealthStatus.READY if self.ready else HealthStatus.NOT_READY


def _sanitize(message: str) -> str:
    message = re.sub(r"https?://\S+", "[redacted-url]", message)
    message = re.sub(r"\b(?:sk|key)-[A-Za-z0-9_-]+\b", "[redacted-secret]", message)
    return message


_TASK_ID_PATTERN = re.compile(r"[0-9a-f]{32}")
MODEL_CALL_AGENTS = frozenset({"conversation", "task"})
MODEL_CALL_OUTCOMES = frozenset({"success", "timeout", "error", "canceled"})
TASK_STATUSES = frozenset(
    {
        "active",
        "waiting_for_clarification",
        "waiting_for_approval",
        "completed",
        "failed",
        "canceled",
        "rejected",
        "timed_out",
        "session_ended",
    }
)
_TASK_COUNT_FIELDS = (
    "active_duration_ms",
    "remaining_active_ms",
    "turn_count",
    "capability_count",
    "completed_step_count",
    "account_attempts",
    "zip_attempts",
)


@dataclass(frozen=True)
class TaskProgressSnapshot:
    task_status: str
    active_duration_ms: int
    remaining_active_ms: int
    turn_count: int
    capability_count: int
    completed_step_count: int
    approval_pending: bool
    account_attempts: int
    zip_attempts: int
    account_verified: bool
    session_ended: bool

    def __post_init__(self) -> None:
        if self.task_status not in TASK_STATUSES:
            raise ValueError("unsupported task status")
        if any(type(getattr(self, name)) is not int or getattr(self, name) < 0 for name in _TASK_COUNT_FIELDS):
            raise ValueError("invalid task metric")
        if any(type(value) is not bool for value in (self.approval_pending, self.account_verified, self.session_ended)):
            raise ValueError("invalid task flag")

    def to_payload(self) -> dict[str, object]:
        return {
            "task_status": self.task_status,
            "active_duration_ms": self.active_duration_ms,
            "remaining_active_ms": self.remaining_active_ms,
            "turn_count": self.turn_count,
            "capability_count": self.capability_count,
            "completed_step_count": self.completed_step_count,
            "approval_pending": self.approval_pending,
            "account_attempts": self.account_attempts,
            "zip_attempts": self.zip_attempts,
            "account_verified": self.account_verified,
            "session_ended": self.session_ended,
        }


def _emit_json_line(payload: dict[str, object]) -> None:
    try:
        print(json.dumps(payload, separators=(",", ":"), ensure_ascii=True), file=sys.stdout, flush=True)
    except (TypeError, ValueError):
        print("diagnostic serialization failed", file=sys.stdout, flush=True)


def record_model_call(
    *,
    task_id: str,
    agent: str,
    call_index: int,
    outcome: str,
    started_at: float,
    input_tokens: int = 0,
    output_tokens: int = 0,
    total_tokens: int = 0,
    cached_input_tokens: int = 0,
    reasoning_tokens: int = 0,
    usage_reported: bool = False,
    message_items: int = 0,
    tool_calls: int = 0,
    tool: str | None = None,
    task_state: TaskProgressSnapshot | None = None,
) -> None:
    """Emit one content-free line for a single model call from a fixed field allowlist."""
    if (
        not _TASK_ID_PATTERN.fullmatch(task_id)
        or agent not in MODEL_CALL_AGENTS
        or outcome not in MODEL_CALL_OUTCOMES
        or call_index < 1
        or (task_state is not None and not isinstance(task_state, TaskProgressSnapshot))
    ):
        raise ValueError("unsupported model call diagnostic")
    payload: dict[str, object] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "component": "model_call",
        "level": "INFO" if outcome == "success" else "ERROR",
        "message": outcome,
        "step": "model_request",
        "duration_ms": max(0, round((monotonic() - started_at) * 1000)),
        "task_id": task_id,
        "agent": agent,
        "call_index": call_index,
        "outcome": outcome,
    }
    if outcome == "success":
        payload.update(
            {
                "usage_reported": bool(usage_reported),
                "input_tokens": max(0, int(input_tokens)),
                "output_tokens": max(0, int(output_tokens)),
                "total_tokens": max(0, int(total_tokens)),
                "cached_input_tokens": max(0, int(cached_input_tokens)),
                "reasoning_tokens": max(0, int(reasoning_tokens)),
                "message_items": max(0, int(message_items)),
                "tool_calls": max(0, int(tool_calls)),
            }
        )
        if tool is not None:
            payload["tool"] = tool
    if task_state is not None:
        payload["task_state"] = task_state.to_payload()
    _emit_json_line(payload)


def record_task_outcome(
    *,
    task_id: str,
    outcome: str,
    started_at: float,
    task_state: TaskProgressSnapshot,
    task_name: TaskName | None = None,
) -> None:
    if (
        not _TASK_ID_PATTERN.fullmatch(task_id)
        or outcome not in TASK_STATUSES
        or not isinstance(task_state, TaskProgressSnapshot)
        or task_state.task_status != outcome
    ):
        raise ValueError("unsupported task outcome diagnostic")
    payload: dict[str, object] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "component": "task_outcome",
            "level": "ERROR" if outcome in {"failed", "canceled", "timed_out"} else "INFO",
            "message": outcome,
            "step": "chat_submission",
            "duration_ms": max(0, round((monotonic() - started_at) * 1000)),
            "task_id": task_id,
            "outcome": outcome,
            "task_state": task_state.to_payload(),
    }
    if isinstance(task_name, TaskName):
        payload["task_name"] = task_name.value
    _emit_json_line(payload)


def record_timing(step: str, started_at: float) -> None:
    """Emit a content-free duration record for an allowlisted blocking step."""
    if step not in {"model_request", "date_time_tool"}:
        raise ValueError("unsupported diagnostic step")
    Diagnostics().record(DiagnosticOutcome.SUCCESS, started_at=started_at, step=step)
