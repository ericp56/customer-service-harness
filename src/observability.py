"""In-memory, fixed-cardinality diagnostics with no visitor content or identifiers."""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, field
from enum import StrEnum
from time import monotonic


class DiagnosticOutcome(StrEnum):
    SUCCESS = "success"
    VALIDATION_BLANK = "validation_blank"
    VALIDATION_TOO_LONG = "validation_too_long"
    OPERATIONAL_FAILURE = "operational_failure"
    ECHO_MISMATCH = "echo_mismatch"
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
    ) -> None:
        event = DiagnosticEvent(
            name="echo_submission",
            outcome=outcome,
            duration_bucket=duration_bucket(max(0.0, monotonic() - started_at)),
            queue_depth_bucket=queue_depth_bucket(max(0, queue_depth)),
            health=HealthStatus.READY if self.ready else HealthStatus.NOT_READY,
        )
        self.outcomes[outcome] += 1
        self.events.append(event)

    def health(self) -> HealthStatus:
        return HealthStatus.READY if self.ready else HealthStatus.NOT_READY
