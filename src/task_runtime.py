"""Pure lifecycle transitions for bounded, transient customer tasks."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field, replace
from enum import StrEnum
from time import monotonic
from typing import Any
from uuid import uuid4

from agents import ModelTimeoutError, RunConfig, Runner

from src.accounts import CallerSession
from src.catalog_policy import CATALOG_HELP, SAFE_FAILURE, SCOPE_REFUSAL, CatalogFacts, catalog_reply
from src.ai_client import (
    AIServiceConfiguration,
    build_agent_model,
    build_agent_run_config,
    create_async_client,
    InvalidConfigurationError,
    load_configuration,
)
from src.chat import ChatMessage, ConversationItem
from src.model_diagnostics import ModelCallRecorder
from src.observability import TaskName, TaskProgressSnapshot, record_task_outcome
from src.task_agents import CatalogRoute, ConversationResponse, TaskAgents, TaskProgressHooks, catalog_conversation, create_task_agents
from src.tools import TASK_TOOLS, ExecutionControl, RevisionRequested, TaskActivity, TaskProgress, TaskToolLedger

MAX_ACTIVE_SECONDS = 60.0
MAX_MANAGER_TURNS = 8
MAX_CAPABILITY_CALLS_PER_TURN = 1
SESSION_ENDED_MESSAGE = (
    "I can't help any further with this request, so this session has ended. "
    "Please start a new conversation if you need more help."
)


class TaskStatus(StrEnum):
    ACTIVE = "active"
    WAITING_FOR_CLARIFICATION = "waiting_for_clarification"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"
    REJECTED = "rejected"
    TIMED_OUT = "timed_out"
    SESSION_ENDED = "session_ended"


class TaskOutcome(StrEnum):
    STARTED = "started"
    ACTIVE = "active"
    PAUSED = "paused"
    RESUMED = "resumed"
    TURN_STARTED = "turn_started"
    TURN_LIMIT = "turn_limit"
    CAPABILITY_ACCEPTED = "capability_accepted"
    CAPABILITY_LIMIT = "capability_limit"
    DUPLICATE_CALL = "duplicate_call"
    DUPLICATE_STEP = "duplicate_step"
    STEP_COMPLETED = "step_completed"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"
    REJECTED = "rejected"
    TIMED_OUT = "timed_out"
    SESSION_ENDED = "session_ended"
    INVALID_CONFIGURATION = "invalid_configuration"
    INVALID_TRANSITION = "invalid_transition"
    OUT_OF_SCOPE = "out_of_scope"
    CATALOG_HELP = "catalog_help"


@dataclass(frozen=True)
class TaskState:
    request: str
    status: TaskStatus
    active_seconds: float
    last_active_at: float | None
    turn_count: int = 0
    capability_calls_this_turn: int = 0
    capability_call_ids: tuple[str, ...] = ()
    capability_step_ids: tuple[str, ...] = ()
    completed_step_ids: tuple[str, ...] = ()
    completed_step_results: tuple[str, ...] = ()
    pending_proposal: str | None = None
    continuation_context: tuple[str, ...] = ()
    caller: CallerSession = CallerSession()
    # Random correlation value for diagnostics; never derived from content.
    task_id: str = field(default_factory=lambda: uuid4().hex)
    task_name: TaskName | None = None
    catalog_facts: CatalogFacts = CatalogFacts()
    catalog_input: str = ""
    input_revision: int = 0


@dataclass(frozen=True)
class TaskTransition:
    state: TaskState
    outcome: TaskOutcome


@dataclass(frozen=True)
class TaskRunResult:
    task: TaskState
    response: ConversationResponse
    outcome: TaskOutcome


def begin_task(request: str, *, now: float) -> TaskState:
    return TaskState(
        request=request,
        status=TaskStatus.ACTIVE,
        active_seconds=0.0,
        last_active_at=now,
    )


def remaining_active_seconds(state: TaskState) -> float:
    return max(0.0, MAX_ACTIVE_SECONDS - state.active_seconds)


def accrue_active_time(state: TaskState, *, now: float) -> TaskTransition:
    if state.status is not TaskStatus.ACTIVE or state.last_active_at is None:
        return TaskTransition(state, TaskOutcome.INVALID_TRANSITION)

    current_time = max(now, state.last_active_at)
    elapsed = current_time - state.last_active_at
    active_seconds = min(MAX_ACTIVE_SECONDS, state.active_seconds + elapsed)
    if active_seconds >= MAX_ACTIVE_SECONDS:
        timed_out = replace(
            state,
            status=TaskStatus.TIMED_OUT,
            active_seconds=MAX_ACTIVE_SECONDS,
            last_active_at=None,
        )
        return TaskTransition(timed_out, TaskOutcome.TIMED_OUT)

    active = replace(state, active_seconds=active_seconds, last_active_at=current_time)
    return TaskTransition(active, TaskOutcome.ACTIVE)


def pause_task(state: TaskState, status: TaskStatus, *, now: float) -> TaskTransition:
    if status not in (TaskStatus.WAITING_FOR_CLARIFICATION, TaskStatus.WAITING_FOR_APPROVAL):
        return TaskTransition(state, TaskOutcome.INVALID_TRANSITION)
    elapsed = accrue_active_time(state, now=now)
    if elapsed.outcome is TaskOutcome.TIMED_OUT:
        return elapsed
    if elapsed.outcome is not TaskOutcome.ACTIVE:
        return elapsed

    paused = replace(elapsed.state, status=status, last_active_at=None)
    return TaskTransition(paused, TaskOutcome.PAUSED)


def resume_task(state: TaskState, *, now: float) -> TaskTransition:
    if state.status not in (
        TaskStatus.WAITING_FOR_CLARIFICATION,
        TaskStatus.WAITING_FOR_APPROVAL,
        TaskStatus.FAILED,
    ):
        return TaskTransition(state, TaskOutcome.INVALID_TRANSITION)
    if state.active_seconds >= MAX_ACTIVE_SECONDS:
        timed_out = replace(state, status=TaskStatus.TIMED_OUT, last_active_at=None)
        return TaskTransition(timed_out, TaskOutcome.TIMED_OUT)

    active = replace(state, status=TaskStatus.ACTIVE, last_active_at=now)
    return TaskTransition(active, TaskOutcome.RESUMED)


def begin_agent_turn(state: TaskState) -> TaskTransition:
    if state.status is not TaskStatus.ACTIVE:
        return TaskTransition(state, TaskOutcome.INVALID_TRANSITION)
    if state.turn_count >= MAX_MANAGER_TURNS:
        failed = replace(state, status=TaskStatus.FAILED, last_active_at=None)
        return TaskTransition(failed, TaskOutcome.TURN_LIMIT)

    next_turn = replace(
        state,
        turn_count=state.turn_count + 1,
        capability_calls_this_turn=0,
    )
    return TaskTransition(next_turn, TaskOutcome.TURN_STARTED)


def record_capability_invocation(
    state: TaskState,
    call_id: str,
    step_id: str,
) -> TaskTransition:
    if state.status is not TaskStatus.ACTIVE or state.turn_count == 0:
        return TaskTransition(state, TaskOutcome.INVALID_TRANSITION)
    if state.capability_calls_this_turn >= MAX_CAPABILITY_CALLS_PER_TURN:
        return TaskTransition(state, TaskOutcome.CAPABILITY_LIMIT)
    if not call_id or call_id in state.capability_call_ids:
        return TaskTransition(state, TaskOutcome.DUPLICATE_CALL)
    if not step_id or step_id in state.capability_step_ids:
        return TaskTransition(state, TaskOutcome.DUPLICATE_STEP)

    accepted = replace(
        state,
        capability_calls_this_turn=state.capability_calls_this_turn + 1,
        capability_call_ids=(*state.capability_call_ids, call_id),
        capability_step_ids=(*state.capability_step_ids, step_id),
    )
    return TaskTransition(accepted, TaskOutcome.CAPABILITY_ACCEPTED)


def complete_task_step(state: TaskState, step_id: str, result: str = "") -> TaskTransition:
    if state.status is not TaskStatus.ACTIVE or step_id not in state.capability_step_ids:
        return TaskTransition(state, TaskOutcome.INVALID_TRANSITION)
    if step_id in state.completed_step_ids:
        return TaskTransition(state, TaskOutcome.DUPLICATE_STEP)

    completed = replace(
        state,
        completed_step_ids=(*state.completed_step_ids, step_id),
        completed_step_results=(*state.completed_step_results, result),
    )
    return TaskTransition(completed, TaskOutcome.STEP_COMPLETED)


def request_simulated_approval(state: TaskState, proposal: str, *, now: float) -> TaskTransition:
    if not proposal.strip():
        return TaskTransition(state, TaskOutcome.INVALID_TRANSITION)
    paused = pause_task(state, TaskStatus.WAITING_FOR_APPROVAL, now=now)
    if paused.outcome is not TaskOutcome.PAUSED:
        return paused
    return TaskTransition(replace(paused.state, pending_proposal=proposal), TaskOutcome.PAUSED)


def resolve_simulated_approval(state: TaskState, *, approved: bool) -> TaskTransition:
    if state.status is not TaskStatus.WAITING_FOR_APPROVAL or not state.pending_proposal:
        return TaskTransition(state, TaskOutcome.INVALID_TRANSITION)
    if not approved:
        rejected = replace(state, status=TaskStatus.REJECTED, pending_proposal=None, last_active_at=None)
        return TaskTransition(rejected, TaskOutcome.REJECTED)

    completed = replace(
        state,
        status=TaskStatus.COMPLETED,
        completed_step_ids=(*state.completed_step_ids, "simulated-consequential-action"),
        pending_proposal=None,
        last_active_at=None,
    )
    return TaskTransition(completed, TaskOutcome.COMPLETED)


def complete_task(state: TaskState) -> TaskTransition:
    if state.status is not TaskStatus.ACTIVE:
        return TaskTransition(state, TaskOutcome.INVALID_TRANSITION)
    return TaskTransition(
        replace(state, status=TaskStatus.COMPLETED, last_active_at=None),
        TaskOutcome.COMPLETED,
    )


def fail_task(state: TaskState) -> TaskTransition:
    if state.status not in (TaskStatus.ACTIVE, TaskStatus.WAITING_FOR_CLARIFICATION, TaskStatus.WAITING_FOR_APPROVAL):
        return TaskTransition(state, TaskOutcome.INVALID_TRANSITION)
    return TaskTransition(
        replace(
            state,
            status=TaskStatus.FAILED,
            last_active_at=None,
            pending_proposal=None,
            continuation_context=(),
        ),
        TaskOutcome.FAILED,
    )


def end_session(state: TaskState) -> TaskTransition:
    if state.status is not TaskStatus.ACTIVE:
        return TaskTransition(state, TaskOutcome.INVALID_TRANSITION)
    ended = replace(state, status=TaskStatus.SESSION_ENDED, last_active_at=None, pending_proposal=None)
    return TaskTransition(ended, TaskOutcome.SESSION_ENDED)


def cancel_task(state: TaskState, *, now: float | None = None) -> TaskTransition:
    if state.status not in (TaskStatus.ACTIVE, TaskStatus.WAITING_FOR_CLARIFICATION, TaskStatus.WAITING_FOR_APPROVAL):
        return TaskTransition(state, TaskOutcome.INVALID_TRANSITION)

    current = state
    if state.status is TaskStatus.ACTIVE and now is not None:
        elapsed = accrue_active_time(state, now=now)
        if elapsed.outcome is TaskOutcome.TIMED_OUT:
            return elapsed
        current = elapsed.state

    canceled = replace(
        current,
        status=TaskStatus.CANCELED,
        last_active_at=None,
        pending_proposal=None,
        continuation_context=(),
    )
    return TaskTransition(canceled, TaskOutcome.CANCELED)


def _conversation_input(
    history: tuple[ConversationItem, ...],
    pending_text: str,
    prior_task: TaskState | None = None,
) -> list[dict[str, str]]:
    items = [
        {"role": item.role, "content": item.content}
        for item in history
        if isinstance(item, ChatMessage) and item.model_visible
    ]
    if prior_task is not None and prior_task.task_name is not None:
        items.append({"role": "assistant", "content": "Continuing catalog task: " + prior_task.task_name.value})
    if prior_task is not None and prior_task.continuation_context:
        items.append(
            {
                "role": "assistant",
                "content": "Transient task findings for continuation: "
                + "\n".join(prior_task.continuation_context),
            }
        )
    if prior_task is not None and prior_task.completed_step_ids:
        items.append(
            {
                "role": "assistant",
                "content": "Completed task steps and findings; do not repeat them: "
                + "\n".join(
                    f"{step_id}: {result}"
                    for step_id, result in zip(
                        prior_task.completed_step_ids,
                        prior_task.completed_step_results,
                        strict=False,
                    )
                ),
            }
        )
    items.append({"role": "user", "content": pending_text})
    return items


def _merge_tool_ledger(state: TaskState, ledger: TaskToolLedger) -> TaskState:
    return replace(
        state,
        capability_call_ids=tuple(ledger.capability_call_ids),
        capability_step_ids=tuple(ledger.capability_step_ids),
        completed_step_ids=tuple(ledger.completed_step_ids),
        completed_step_results=tuple(ledger.completed_step_results),
        caller=ledger.caller,
        catalog_facts=ledger.facts,
        catalog_input=ledger.caller_input,
        task_name=ledger.task_name or state.task_name,
    )


def _task_progress_snapshot(
    state: TaskState,
    ledger: TaskToolLedger | None = None,
    *,
    turn_count: int | None = None,
    now: float | None = None,
) -> TaskProgressSnapshot:
    current_time = monotonic() if now is None else now
    active_seconds = state.active_seconds
    if state.status is TaskStatus.ACTIVE and state.last_active_at is not None:
        active_seconds += max(0.0, current_time - state.last_active_at)
    active_ms = min(round(MAX_ACTIVE_SECONDS * 1000), max(0, round(active_seconds * 1000)))
    caller = ledger.caller if ledger is not None else state.caller
    capability_ids = ledger.capability_call_ids if ledger is not None else state.capability_call_ids
    completed_ids = ledger.completed_step_ids if ledger is not None else state.completed_step_ids
    return TaskProgressSnapshot(
        task_status=state.status.value,
        active_duration_ms=active_ms,
        remaining_active_ms=max(0, round(MAX_ACTIVE_SECONDS * 1000) - active_ms),
        turn_count=max(0, state.turn_count if turn_count is None else turn_count),
        capability_count=len(capability_ids),
        completed_step_count=len(completed_ids),
        approval_pending=state.pending_proposal is not None,
        account_attempts=caller.account_attempts,
        zip_attempts=caller.zip_attempts,
        account_verified=caller.verified_account is not None,
        session_ended=caller.ended or state.status is TaskStatus.SESSION_ENDED,
    )


def _is_timeout_error(error: BaseException) -> bool:
    pending_errors = [error]
    seen: set[int] = set()
    while pending_errors:
        current_error = pending_errors.pop()
        if id(current_error) in seen:
            continue
        seen.add(id(current_error))
        if isinstance(current_error, (TimeoutError, ModelTimeoutError)):
            return True
        if "timeout" in type(current_error).__name__.lower():
            return True
        if isinstance(current_error, BaseExceptionGroup):
            pending_errors.extend(current_error.exceptions)
        if current_error.__cause__ is not None:
            pending_errors.append(current_error.__cause__)
        if current_error.__context__ is not None:
            pending_errors.append(current_error.__context__)
    return False


async def run_customer_task(
    pending_text: str,
    history: tuple[ConversationItem, ...],
    *,
    agents: TaskAgents | None = None,
    configuration: AIServiceConfiguration | None = None,
    client: Any | None = None,
    prior_task: TaskState | None = None,
    caller: CallerSession | None = None,
    progress: TaskProgress | None = None,
    control: ExecutionControl | None = None,
) -> TaskRunResult:
    """Run one bounded manager/specialist workflow without retaining provider errors."""
    started_at = monotonic()

    def current_time() -> float:
        if control is not None:
            return started_at + max(0.0, control.active_seconds - control.base_seconds)
        return monotonic()

    async def bounded(work: Any, seconds: float) -> Any:
        if control is not None:
            return await control.run(work)
        return await asyncio.wait_for(work, timeout=seconds)

    def finish(
        result: TaskRunResult,
        ledger: TaskToolLedger | None = None,
        turn_count: int | None = None,
    ) -> TaskRunResult:
        if progress is not None:
            progress.clear()
        if control is not None:
            return result
        try:
            snapshot = _task_progress_snapshot(result.task, ledger, turn_count=turn_count)
            record_task_outcome(
                task_id=result.task.task_id,
                outcome=(TaskStatus.REJECTED.value if result.outcome in (TaskOutcome.OUT_OF_SCOPE, TaskOutcome.CATALOG_HELP) else result.task.status.value),
                started_at=started_at,
                task_state=snapshot,
                task_name=(None if result.outcome in (TaskOutcome.OUT_OF_SCOPE, TaskOutcome.CATALOG_HELP) else result.task.task_name),
            )
        except Exception:
            pass
        return result

    if prior_task is None:
        task = replace(begin_task(pending_text, now=started_at), caller=caller or CallerSession())
    else:
        resumed = resume_task(prior_task, now=started_at)
        if resumed.outcome is not TaskOutcome.RESUMED:
            response = ConversationResponse(status="failed", message="This task took too long to finish. Please try again.")
            return finish(TaskRunResult(resumed.state, response, resumed.outcome))
        # The manager-turn budget applies to each caller message, not cumulatively.
        task = replace(resumed.state, turn_count=0)
    if task.caller.ended:
        ended = end_session(task)
        return finish(TaskRunResult(
            ended.state,
            ConversationResponse(status="session_ended", message=SESSION_ENDED_MESSAGE),
            TaskOutcome.SESSION_ENDED,
        ))
    turn = begin_agent_turn(task)
    if turn.outcome is not TaskOutcome.TURN_STARTED:
        return finish(TaskRunResult(
            turn.state,
            ConversationResponse(status="unsupported", message="I couldn't continue that task. Please try again."),
            turn.outcome,
        ))

    owned_clients: list[Any] = []
    tool_ledger = TaskToolLedger(
        capability_call_ids=list(turn.state.capability_call_ids),
        capability_step_ids=list(turn.state.capability_step_ids),
        completed_step_ids=list(turn.state.completed_step_ids),
        completed_step_results=list(turn.state.completed_step_results),
        caller=turn.state.caller,
        progress=progress if progress is not None else TaskProgress(),
        caller_input=pending_text,
        facts=(
            prior_task.catalog_facts
            if prior_task is not None and prior_task.status is TaskStatus.FAILED and prior_task.catalog_input == pending_text
            else CatalogFacts()
        ),
        control=control,
    )
    if control is not None:
        control.base_seconds = turn.state.active_seconds
        control.started_at = started_at
        control.paused_seconds = 0.0
        control.state = turn.state
        turn = TaskTransition(replace(turn.state, input_revision=control.revision), turn.outcome)
        control.state = turn.state
    remaining_seconds = remaining_active_seconds(turn.state)
    if remaining_seconds <= 0:
        timed_out = replace(turn.state, status=TaskStatus.TIMED_OUT, last_active_at=None)
        return finish(TaskRunResult(
            timed_out,
            ConversationResponse(status="failed", message="This task took too long to finish. Please try again."),
            TaskOutcome.TIMED_OUT,
        ))
    recorder = control.recorder if control is not None and control.recorder is not None and control.recorder.task_id == turn.state.task_id else ModelCallRecorder(turn.state.task_id)
    recorder.update_snapshot(lambda turns: _task_progress_snapshot(
        replace(turn.state, active_seconds=min(60.0, control.active_seconds), last_active_at=None) if control is not None else turn.state,
        tool_ledger, turn_count=control.manager_turns if control is not None else turns,
    ))
    if control is not None:
        control.recorder = recorder
    recording_token = recorder.activate()
    try:
        if agents is None:
            config = configuration or load_configuration()
            if client is None:
                conversation_client = create_async_client(config)
                task_client = create_async_client(config)
                owned_clients.extend((conversation_client, task_client))
            else:
                conversation_client = task_client = client
            agents = create_task_agents(
                conversation_model=build_agent_model(config, client=conversation_client),
                task_model=build_agent_model(config, client=task_client),
                task_tools=TASK_TOOLS,
            )
            run_configuration = build_agent_run_config(config)
        else:
            run_configuration = RunConfig(
                tracing_disabled=True,
                trace_include_sensitive_data=False,
            )

        if agents.routing is None:
            raise ValueError("invalid catalog router")
        if control is not None:
            control.agents = agents
        routing_input = [{"role": "user", "content": pending_text}]
        if prior_task is not None and prior_task.task_name is not None:
            expected_detail = "zip_code" if prior_task.caller.current_account is not None else "account_number"
            routing_input.insert(0, {"role": "system", "content": (
                "Application-owned pending catalog task: " + prior_task.task_name.value
                + ". Expected detail: " + expected_detail + "."
            )})
        if control is not None and control.admitted_route is not None:
            route = control.admitted_route
        else:
            routed = await bounded(
                Runner.run(
                    agents.routing,
                    routing_input,
                    context=tool_ledger,
                    run_config=run_configuration,
                    max_turns=1,
                    hooks=TaskProgressHooks("conversation"),
                ),
                remaining_seconds,
            )
            route = routed.final_output
        if not isinstance(route, CatalogRoute):
            raise ValueError("invalid catalog route")
        if route.action in ("decline", "help"):
            outcome = TaskOutcome.OUT_OF_SCOPE if route.action == "decline" else TaskOutcome.CATALOG_HELP
            message = SCOPE_REFUSAL if route.action == "decline" else CATALOG_HELP
            elapsed_route = accrue_active_time(turn.state, now=current_time())
            if elapsed_route.outcome is TaskOutcome.TIMED_OUT:
                return finish(TaskRunResult(
                    elapsed_route.state,
                    ConversationResponse(status="failed", message="This task took too long to finish. Please try again."),
                    TaskOutcome.TIMED_OUT,
                ), tool_ledger, recorder.manager_turn_count)
            if prior_task is not None:
                declined_state = replace(prior_task, active_seconds=elapsed_route.state.active_seconds)
            else:
                declined_state = replace(elapsed_route.state, status=TaskStatus.REJECTED, last_active_at=None, task_name=None)
            return finish(TaskRunResult(
                declined_state,
                ConversationResponse(status="declined" if route.action == "decline" else "catalog_help", message=message),
                outcome,
            ), tool_ledger, recorder.manager_turn_count)
        if control is not None and prior_task is not None and prior_task.task_name is not None and control.admitted_route is None and prior_task.status is not TaskStatus.FAILED:
            tool_ledger.task_name = prior_task.task_name
            control.pending_route = route
            await bounded(tool_ledger.checkpoint("continuation"), remaining_seconds)
        if route.action == "cancel":
            raise ValueError("no active catalog task")
        admitted_name = route.task_name
        if route.action == "continuation":
            if prior_task is None or prior_task.task_name is None:
                raise ValueError("invalid catalog continuation")
            admitted_name = prior_task.task_name
        if not isinstance(admitted_name, TaskName):
            raise ValueError("invalid catalog task")
        if control is None and prior_task is not None and prior_task.task_name not in (None, admitted_name):
            switch_time = accrue_active_time(turn.state, now=current_time())
            if switch_time.outcome is TaskOutcome.TIMED_OUT:
                return finish(TaskRunResult(
                    switch_time.state,
                    ConversationResponse(status="failed", message="This task took too long to finish. Please try again."),
                    TaskOutcome.TIMED_OUT,
                ), tool_ledger, recorder.manager_turn_count)
            waiting = replace(
                prior_task, status=TaskStatus.WAITING_FOR_CLARIFICATION,
                active_seconds=switch_time.state.active_seconds, last_active_at=None,
            )
            return finish(TaskRunResult(
                waiting,
                ConversationResponse(
                    status="clarification_required",
                    message="Please finish or cancel your current task before starting another.",
                    task_name=prior_task.task_name,
                ),
                TaskOutcome.PAUSED,
            ), tool_ledger, recorder.manager_turn_count)
        tool_ledger.task_name = admitted_name
        tool_ledger.detail_kind = route.detail_kind
        await bounded(tool_ledger.checkpoint("admitted"), remaining_seconds)
        tool_ledger.progress.set(TaskActivity.WORKING_ON_TASK, admitted_name)
        remaining_seconds = remaining_active_seconds(accrue_active_time(turn.state, now=current_time()).state)
        if remaining_seconds <= 0:
            raise TimeoutError()
        execution_agent = catalog_conversation(agents, admitted_name, route.detail_kind, tool_ledger.caller)
        result = await bounded(
            Runner.run(
                execution_agent,
                _conversation_input(history, pending_text, prior_task),
                context=tool_ledger,
                run_config=run_configuration,
                max_turns=MAX_MANAGER_TURNS - 1,
                hooks=TaskProgressHooks("conversation"),
            ),
            remaining_seconds,
        )
        await bounded(tool_ledger.checkpoint("publication"), remaining_seconds)
    except RevisionRequested:
        elapsed = accrue_active_time(turn.state, now=current_time())
        status = TaskStatus.SESSION_ENDED if tool_ledger.caller.ended else TaskStatus.CANCELED if control is not None and control.change_action in ("switch", "cancel") else TaskStatus.WAITING_FOR_CLARIFICATION
        checkpoint = replace(_merge_tool_ledger(elapsed.state, tool_ledger), status=status, last_active_at=None)
        return finish(TaskRunResult(
            checkpoint,
            ConversationResponse(status="session_ended" if tool_ledger.caller.ended else "clarification_required", message="", task_name=tool_ledger.task_name),
            TaskOutcome.SESSION_ENDED if tool_ledger.caller.ended else TaskOutcome.RESUMED,
        ), tool_ledger, recorder.manager_turn_count)
    except asyncio.CancelledError:
        recorder.fail("canceled")
        elapsed = accrue_active_time(turn.state, now=current_time())
        canceled_state = replace(
            _merge_tool_ledger(elapsed.state, tool_ledger),
            status=TaskStatus.CANCELED,
            last_active_at=None,
        )
        finish(
            TaskRunResult(
                canceled_state,
                ConversationResponse(status="failed", message="I couldn't complete that task. Please try again."),
                TaskOutcome.CANCELED,
            ),
            tool_ledger,
            recorder.manager_turn_count,
        )
        raise
    except InvalidConfigurationError:
        recorder.fail("error")
        failed = fail_task(_merge_tool_ledger(turn.state, tool_ledger))
        return finish(
            TaskRunResult(
                failed.state,
                ConversationResponse(status="failed", message="I couldn't complete that task. Please try again."),
                TaskOutcome.INVALID_CONFIGURATION,
            ),
            tool_ledger,
            recorder.manager_turn_count,
        )
    except ModelTimeoutError:
        recorder.fail("timeout")
        elapsed = accrue_active_time(turn.state, now=current_time())
        if elapsed.outcome is TaskOutcome.TIMED_OUT:
            timed_out = _merge_tool_ledger(elapsed.state, tool_ledger)
            return finish(TaskRunResult(
                timed_out,
                ConversationResponse(status="failed", message="This task took too long to finish. Please try again."),
                TaskOutcome.TIMED_OUT,
            ), tool_ledger, recorder.manager_turn_count)
        failed = fail_task(_merge_tool_ledger(elapsed.state, tool_ledger))
        return finish(TaskRunResult(
            failed.state,
            ConversationResponse(status="failed", message="I couldn't complete that task. Please try again."),
            TaskOutcome.FAILED,
        ), tool_ledger, recorder.manager_turn_count)
    except Exception as error:
        recorder.fail("timeout" if _is_timeout_error(error) else "error")
        if _is_timeout_error(error):
            timed_out = replace(
                _merge_tool_ledger(turn.state, tool_ledger),
                status=TaskStatus.TIMED_OUT,
                active_seconds=MAX_ACTIVE_SECONDS,
                turn_count=MAX_MANAGER_TURNS,
                last_active_at=None,
            )
            return finish(TaskRunResult(
                timed_out,
                ConversationResponse(status="failed", message="This task took too long to finish. Please try again."),
                TaskOutcome.TIMED_OUT,
            ), tool_ledger, recorder.manager_turn_count)
        elapsed = accrue_active_time(turn.state, now=current_time())
        if elapsed.outcome is TaskOutcome.TIMED_OUT:
            timed_out = _merge_tool_ledger(elapsed.state, tool_ledger)
            return finish(TaskRunResult(
                timed_out,
                ConversationResponse(status="failed", message="This task took too long to finish. Please try again."),
                TaskOutcome.TIMED_OUT,
            ), tool_ledger, recorder.manager_turn_count)
        failed = fail_task(_merge_tool_ledger(elapsed.state, tool_ledger))
        return finish(TaskRunResult(
            failed.state,
            ConversationResponse(status="failed", message="I couldn't complete that task. Please try again."),
            TaskOutcome.FAILED,
        ), tool_ledger, recorder.manager_turn_count)
    finally:
        recorder.fail("canceled")
        recorder.deactivate(recording_token)
        if control is not None:
            control.owned_clients.extend(owned_clients)
        for owned_client in owned_clients if control is None else ():
            try:
                await owned_client.close()
            except Exception:
                pass

    elapsed = accrue_active_time(turn.state, now=current_time())
    if elapsed.outcome is TaskOutcome.TIMED_OUT:
        return finish(TaskRunResult(
            _merge_tool_ledger(elapsed.state, tool_ledger),
            ConversationResponse(status="failed", message="This task took too long to finish. Please try again."),
            TaskOutcome.TIMED_OUT,
        ), tool_ledger, recorder.manager_turn_count)

    manager_turn_count = control.manager_turns if control is not None else min(MAX_MANAGER_TURNS, 1 + len(result.raw_responses))
    response = result.final_output
    elapsed_state = replace(
        _merge_tool_ledger(elapsed.state, tool_ledger),
        turn_count=manager_turn_count,
    )
    if tool_ledger.caller.ended:
        ended = end_session(elapsed_state)
        return finish(TaskRunResult(
            ended.state,
            ConversationResponse(status="session_ended", message=SESSION_ENDED_MESSAGE),
            TaskOutcome.SESSION_ENDED,
        ), tool_ledger, recorder.manager_turn_count)
    if not isinstance(response, ConversationResponse):
        failed = fail_task(elapsed_state)
        return finish(TaskRunResult(
            failed.state,
            ConversationResponse(status="failed", message="I couldn't complete that task. Please try again."),
            TaskOutcome.FAILED,
        ), tool_ledger, recorder.manager_turn_count)

    elapsed_state = replace(elapsed_state, task_name=tool_ledger.task_name)
    if tool_ledger.policy_violated or response.status not in ("completed", "clarification_required"):
        response = ConversationResponse(status="failed", message=SAFE_FAILURE, task_name=tool_ledger.task_name)
    else:
        status, message = catalog_reply(
            tool_ledger.task_name, tool_ledger.caller, tool_ledger.facts,
            completed=response.status == "completed",
        )
        if route.decline_remainder and status != "failed":
            message += " " + SCOPE_REFUSAL
        response = ConversationResponse(status=status, message=message, task_name=tool_ledger.task_name)
    if response.status == "completed":
        completed = complete_task(elapsed_state)
        return finish(TaskRunResult(completed.state, response, completed.outcome), tool_ledger, recorder.manager_turn_count)
    if response.status == "clarification_required":
        paused = pause_task(elapsed_state, TaskStatus.WAITING_FOR_CLARIFICATION, now=monotonic())
        continuation_context = paused.state.continuation_context
        if response.task_result is not None:
            continuation_context = (*continuation_context, response.task_result.model_dump_json())
        paused_state = replace(paused.state, continuation_context=continuation_context)
        return finish(TaskRunResult(paused_state, response, paused.outcome), tool_ledger, recorder.manager_turn_count)
    failed = fail_task(elapsed_state)
    return finish(TaskRunResult(failed.state, response, TaskOutcome.FAILED), tool_ledger, recorder.manager_turn_count)