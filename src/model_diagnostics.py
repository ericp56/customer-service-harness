"""Content-free per-model-call diagnostics driven by Agents SDK lifecycle hooks."""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass
from time import monotonic
from typing import Any, Callable

from agents import RunHooks

from src.observability import TaskProgressSnapshot, record_model_call
from src.tools import TASK_TOOLS

_KNOWN_TOOLS = frozenset({tool.name for tool in TASK_TOOLS} | {"delegate_to_task_agent"})


@dataclass
class _OpenCall:
    agent: str
    index: int
    started_at: float


def _count(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


class ModelCallRecorder:
    """Tracks the single in-flight model call of one run and emits one line per call."""

    def __init__(
        self,
        task_id: str,
        task_snapshot: Callable[[int], TaskProgressSnapshot] | None = None,
    ) -> None:
        self.task_id = task_id
        self._task_snapshot = task_snapshot
        self._calls = 0
        self._manager_turn_count = 0
        self._open: _OpenCall | None = None

    @property
    def manager_turn_count(self) -> int:
        return self._manager_turn_count

    def activate(self) -> Token[ModelCallRecorder | None]:
        return _current.set(self)

    def deactivate(self, token: Token[ModelCallRecorder | None]) -> None:
        _current.reset(token)

    def start(self, agent: str) -> None:
        self._calls += 1
        if agent == "conversation":
            self._manager_turn_count += 1
        self._open = _OpenCall(agent, self._calls, monotonic())

    def succeed(self, response: Any) -> None:
        call, self._open = self._open, None
        if call is None:
            return
        usage = getattr(response, "usage", None)
        input_tokens = _count(getattr(usage, "input_tokens", 0))
        output_tokens = _count(getattr(usage, "output_tokens", 0))
        total_tokens = _count(getattr(usage, "total_tokens", 0))
        messages = 0
        tool_calls = 0
        tool: str | None = None
        for item in getattr(response, "output", ()) or ():
            kind = getattr(item, "type", None)
            if kind == "message":
                messages += 1
            elif kind == "function_call":
                tool_calls += 1
                if tool is None:
                    name = getattr(item, "name", None)
                    tool = name if name in _KNOWN_TOOLS else "other"
        self._emit(
            call,
            "success",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            cached_input_tokens=_count(getattr(getattr(usage, "input_tokens_details", None), "cached_tokens", 0)),
            reasoning_tokens=_count(getattr(getattr(usage, "output_tokens_details", None), "reasoning_tokens", 0)),
            usage_reported=bool(input_tokens or output_tokens or total_tokens),
            message_items=messages,
            tool_calls=tool_calls,
            tool=tool,
        )

    def fail(self, outcome: str) -> None:
        """Close the in-flight call, if any, with a fixed failure outcome."""
        call, self._open = self._open, None
        if call is not None:
            self._emit(call, outcome)

    def _emit(self, call: _OpenCall, outcome: str, **fields: Any) -> None:
        # Diagnostics must never change task behavior.
        try:
            task_state = None
            if self._task_snapshot is not None:
                try:
                    task_state = self._task_snapshot(self._manager_turn_count)
                except Exception:
                    pass
            record_model_call(
                task_id=self.task_id,
                agent=call.agent,
                call_index=call.index,
                outcome=outcome,
                started_at=call.started_at,
                task_state=task_state,
                **fields,
            )
        except Exception:
            pass


_current: ContextVar[ModelCallRecorder | None] = ContextVar("model_call_recorder", default=None)


class ModelCallHooks(RunHooks[Any]):
    """Reports each model call of one agent role to the active run's recorder."""

    def __init__(self, agent: str) -> None:
        self._agent = agent

    async def on_llm_start(self, context: Any, agent: Any, system_prompt: Any, input_items: Any) -> None:
        recorder = _current.get()
        if recorder is not None:
            recorder.start(self._agent)

    async def on_llm_end(self, context: Any, agent: Any, response: Any) -> None:
        recorder = _current.get()
        if recorder is not None:
            recorder.succeed(response)
