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


class HealthStatus(StrEnum):
    READY = "ready"
    NOT_READY = "not_ready"


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
            "message": outcome.value,
            "step": step,
            "duration_ms": max(0, round((monotonic() - started_at) * 1000)),
        }
        if error:
            stack = [
                _sanitize(f"{frame.filename}:{frame.lineno}")
                for frame in traceback.extract_tb(error.__traceback__)
            ]
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


def record_timing(
    step: str,
    started_at: float,
    *,
    outcome: DiagnosticOutcome = DiagnosticOutcome.SUCCESS,
    error: BaseException | None = None,
) -> None:
    """Emit a content-free duration record for an allowlisted blocking step."""
    if step not in {"model_request", "date_time_tool"}:
        raise ValueError("unsupported diagnostic step")
    Diagnostics().record(outcome, started_at=started_at, error=error, step=step)
