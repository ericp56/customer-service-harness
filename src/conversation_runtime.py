"""One-tab, server-only coordination for interruptible catalog conversations."""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
import re
from time import monotonic
from typing import Any, AsyncIterator
from weakref import WeakKeyDictionary

from agents import RunConfig, Runner

from src.accounts import correct_account, is_account_number
from src.catalog_policy import CATALOG_HELP, SAFE_FAILURE, SCOPE_REFUSAL, CatalogFacts, catalog_reply
from src.chat import CallerInput, Dialogue, MessageKind, accept_caller, publish_assistant, validate_submission
from src.model_diagnostics import ModelCallRecorder
from src.observability import TaskName, record_task_outcome
from src.task_agents import CatalogRoute, ConversationResponse, INTERRUPTION_INSTRUCTIONS, InterruptionDecision, TaskAgents, TaskProgressHooks
from src.task_runtime import SESSION_ENDED_MESSAGE, TaskOutcome, TaskRunResult, TaskState, TaskStatus, _merge_tool_ledger, _task_progress_snapshot, begin_task, resolve_simulated_approval
from src.tools import ExecutionControl, RevisionRequested, TaskProgress, TaskToolLedger

INBOX_CAPACITY = 10
LIMIT_MESSAGE = "This conversation has reached its message limit. Start a new conversation to continue."
_CAPACITY: WeakKeyDictionary[asyncio.AbstractEventLoop, int] = WeakKeyDictionary()


@dataclass(frozen=True)
class ChangeProposal:
    version: int
    source: CallerInput
    action: str
    task_name: TaskName | None
    detail_kind: str
    value: str | None
    original_revision: int


@dataclass
class SessionCoordinator:
    agents: TaskAgents | None = field(default=None, repr=False)
    dialogue: Dialogue = field(default_factory=Dialogue, repr=False)
    task: TaskState | None = field(default=None, repr=False)
    inbox: deque[CallerInput] = field(default_factory=deque, repr=False)
    worker: asyncio.Task[None] | None = field(default=None, repr=False)
    proposal: ChangeProposal | None = field(default=None, repr=False)
    status: str = "Ready to send a message."
    status_role: str = "status"
    disposed: bool = False
    retry_input: CallerInput | None = field(default=None, repr=False)
    visible_proposal: int | None = None
    version: int = 0
    rendered_version: int = -1
    _proposal_version: int = 0
    _lock: asyncio.Lock | None = field(default=None, repr=False)
    _changed: asyncio.Event | None = field(default=None, repr=False)
    _control: ExecutionControl | None = field(default=None, repr=False)
    _next_input: CallerInput | None = field(default=None, repr=False)
    _switch: bool = False
    _cancel: bool = False
    _active_input: CallerInput | None = field(default=None, repr=False)
    _last_progress: float = 0.0
    _last_progress_text: str | None = field(default=None, repr=False)
    _loop: asyncio.AbstractEventLoop | None = field(default=None, repr=False)
    _progress: TaskProgress = field(default_factory=TaskProgress, repr=False)
    _clarifying: bool = False
    _applied: ChangeProposal | None = field(default=None, repr=False)
    _pinned_route: CatalogRoute | None = field(default=None, repr=False)
    _retrying: bool = False
    _last_accepted_at: float = 0.0
    _last_accepted: CallerInput | None = field(default=None, repr=False)
    _started_at: float = 0.0
    _owns_slot: bool = False
    _recorder: ModelCallRecorder | None = field(default=None, repr=False)

    def _initialize(self) -> None:
        if self._lock is None:
            self._lock = asyncio.Lock()
            self._changed = asyncio.Event()
            self._loop = asyncio.get_running_loop()

    def _notify(self) -> None:
        self.version += 1
        if self._changed is not None:
            self._changed.set()

    @asynccontextmanager
    async def render_update(self, progress_copy: Callable[[int, TaskProgress], tuple[str, str]]) -> AsyncIterator[bool]:
        self._initialize()
        async with self._lock:
            active = self.worker is not None and not self.worker.done()
            waiting = self.proposal is not None or self._clarifying or (self._control is not None and self._control.paused_at is not None)
            if active and not waiting and self.dialogue.assistant_count < 90 and monotonic() - self._last_progress >= 5.0:
                _, text = progress_copy(1, self._progress)
                if text != self._last_progress_text:
                    self._publish(text, MessageKind.PROGRESS)
                    self._last_progress_text = text
                self._last_progress = monotonic()
            changed = self.rendered_version != self.version
            if changed:
                self.rendered_version = self.version
                self.visible_proposal = self.proposal.version if self.proposal is not None else None
            yield changed

    async def resolve_approval(self, approved: bool) -> None:
        self._initialize()
        async with self._lock:
            if self.task is None:
                return
            result = resolve_simulated_approval(self.task, approved=approved)
            if result.outcome is TaskOutcome.INVALID_TRANSITION:
                return
            self.task = result.state
            self._publish("The simulated action was approved and completed." if approved else "I didn't proceed with the proposed action.", MessageKind.COMPLETION)
            self.status_role = "status"
            self.status = "Task completed." if approved else "I didn't proceed with the proposed action."
            self._notify()

    async def wait_until(self, predicate: Callable[[], bool], timeout: float = 2.0) -> None:
        self._initialize()
        async with asyncio.timeout(timeout):
            while not predicate():
                self._changed.clear()
                if predicate():
                    break
                await self._changed.wait()

    async def accept(self, content: str) -> bool:
        self._initialize()
        async with self._lock:
            validation = validate_submission(content)
            if self.disposed or (self.task is not None and self.task.caller.ended):
                self.status = "This session has ended. Start a new conversation to continue."
                self.status_role = "alert"
                self._publish(self.status, MessageKind.RECOVERY)
                return False
            if validation is not None:
                self.status = "Enter at least one non-whitespace character before sending." if validation.value == "blank" else "Messages must contain no more than 4,096 Unicode code points."
                self.status_role = "alert"
                self._publish(self.status, MessageKind.NOTICE)
                return False
            if self._last_accepted is not None and self._last_accepted.content == content and self._last_accepted.proposal_version == self.visible_proposal and monotonic() - self._last_accepted_at < 0.25:
                return True
            if self.dialogue.caller_limit or len(self.inbox) >= INBOX_CAPACITY:
                self.status = LIMIT_MESSAGE if self.dialogue.caller_limit else "Too many messages are waiting. Please try sending this message again shortly."
                self.status_role = "alert"
                self._publish(self.status, MessageKind.RECOVERY if self.dialogue.caller_limit else MessageKind.NOTICE)
                return False
            starting = self.worker is None or self.worker.done()
            if starting and _CAPACITY.get(self._loop, 0) >= 50:
                self.status, self.status_role = "The service is busy. Please try sending this message again shortly.", "alert"
                self._publish(self.status, MessageKind.NOTICE)
                return False
            self.dialogue, event = accept_caller(self.dialogue, content, self.visible_proposal)
            self.inbox.append(event)
            self._last_accepted, self._last_accepted_at = event, monotonic()
            self.retry_input = None
            if starting:
                _CAPACITY[self._loop] = _CAPACITY.get(self._loop, 0) + 1
                self._owns_slot = True
                self.worker = asyncio.create_task(self._work(self.dialogue.generation))
            self._notify()
            return True

    def _publish(self, text: str, kind: MessageKind = MessageKind.INFORMATION) -> None:
        if kind in (MessageKind.NOTICE, MessageKind.PROGRESS) and self.dialogue.history:
            last = self.dialogue.history[-1]
            if last.role == "assistant" and last.kind is kind and last.content == text:
                return
        if kind in (MessageKind.QUESTION, MessageKind.CONFIRMATION) and self.dialogue.caller_limit:
            text, kind = LIMIT_MESSAGE, MessageKind.RECOVERY
            self._cancel = True
            self.status, self.status_role = LIMIT_MESSAGE, "alert"
        try:
            self.dialogue = publish_assistant(self.dialogue, text, kind, revision=self._active_input.revision if self._active_input else self.dialogue.revision)
        except ValueError:
            if self.dialogue.assistant_count < 100:
                self.dialogue = publish_assistant(self.dialogue, LIMIT_MESSAGE, MessageKind.RECOVERY, revision=self.dialogue.revision)
            self._cancel = True
        self._notify()

    async def _interpret(self, batch: tuple[CallerInput, ...], ledger: TaskToolLedger) -> InterruptionDecision:
        control = ledger.control
        agents = control.agents if control is not None else self.agents
        if agents is None or agents.routing is None:
            raise ValueError("invalid interruption interpreter")
        interpreter = agents.routing.clone(instructions=INTERRUPTION_INSTRUCTIONS, output_type=InterruptionDecision, tools=[])
        stage = "zip_code" if ledger.caller.current_account is not None else "account_number"
        items = [{"role": "system", "content": "Application-owned task: " + (ledger.task_name.value if ledger.task_name else "none") + ". Expected detail: " + stage + ". Original input: " + ledger.caller_input}]
        items.extend({"role": "user", "content": f"Receipt sequence {event.sequence}: {event.content}"} for event in batch)
        if control is not None:
            control.reconciling = True
        try:
            result = await Runner.run(interpreter, items, context=ledger, max_turns=1, run_config=RunConfig(tracing_disabled=True, trace_include_sensitive_data=False), hooks=TaskProgressHooks("conversation"))
        finally:
            if control is not None:
                control.reconciling = False
        decision = result.final_output
        if not isinstance(decision, InterruptionDecision):
            raise ValueError("invalid interruption decision")
        source = next((event for event in batch if event.sequence == decision.source_sequence), None)
        if source is None or source != batch[-1] or (decision.value is not None and re.search(r"(?<!\w)" + re.escape(decision.value) + r"(?!\w)", source.content) is None):
            raise ValueError("invalid interruption provenance")
        if decision.action == "switch" and (not isinstance(decision.task_name, TaskName) or decision.task_name == ledger.task_name or decision.detail_kind != "none" or decision.value is not None):
            raise ValueError("invalid interruption task")
        if decision.action in ("correction", "supplement") and decision.task_name not in (None, ledger.task_name):
            raise ValueError("invalid interruption task")
        if decision.detail_kind == "account_number" and (decision.value is None or not is_account_number(decision.value)):
            raise ValueError("invalid interruption detail")
        if decision.detail_kind == "zip_code" and (decision.value is None or re.fullmatch(r"[0-9]{5}", decision.value) is None):
            raise ValueError("invalid interruption detail")
        if decision.action in ("correction", "supplement") and decision.detail_kind == "none":
            raise ValueError("invalid interruption detail")
        if decision.action in ("cancel", "decline", "help", "ambiguous") and (decision.detail_kind != "none" or decision.value is not None):
            raise ValueError("invalid interruption decision")
        if decision.action in ("correction", "supplement") and len(re.findall(r"(?<!\w)[0-9]+(?!\w)", source.content)) != 1:
            return InterruptionDecision(action="ambiguous", source_sequence=source.sequence)
        return decision

    def _confirmation(self, proposal: ChangeProposal, ledger: TaskToolLedger) -> str:
        if proposal.action == "cancel":
            return "Cancel your current task? Please reply Yes or No."
        if proposal.action == "switch":
            return "Cancel your current task and start: " + proposal.task_name.value + "? Please reply Yes or No."
        if proposal.detail_kind == "account_number":
            old = ledger.caller.current_account
            if old is not None and is_account_number(old):
                return f"Change the account from {old} to {proposal.value}? Please reply Yes or No."
            return f"Change the account to {proposal.value}? Please reply Yes or No."
        return "Change the detail for your current task? Please reply Yes or No."

    async def _checkpoint(self, ledger: TaskToolLedger, boundary: str) -> None:
        control = ledger.control
        if control is not None and control.generation != self.dialogue.generation:
            raise asyncio.CancelledError()
        if control is not None and control.state is not None:
            self.task = replace(_merge_tool_ledger(control.state, ledger), active_seconds=min(60.0, control.active_seconds), last_active_at=monotonic())
        if self.disposed or self._cancel:
            raise asyncio.CancelledError()
        if ledger.caller.ended:
            self.inbox.clear()
            self.proposal = None
            raise RevisionRequested()
        if ledger.task_name is None:
            return
        if boundary == "continuation" and control is not None and control.pending_route is not None:
            route = control.pending_route
            control.pending_route = None
            source = self._active_input
            values = re.findall(r"(?<!\w)[0-9]+(?!\w)", source.content)
            action = "cancel" if route.action == "cancel" else "switch" if route.task_name not in (None, ledger.task_name) else "correction"
            if action in ("cancel", "switch") or (route.detail_kind == "account_number" and ledger.caller.current_account is not None and values != [ledger.caller.current_account]):
                if len(values) > 1:
                    self._clarifying = True
                    self._publish("Please clarify the change you want to make.", MessageKind.QUESTION)
                else:
                    self._propose(InterruptionDecision(action=action, task_name=route.task_name or ledger.task_name, detail_kind=route.detail_kind if action == "correction" else "none", source_sequence=source.sequence, value=values[0] if action == "correction" and values else None), source, ledger)
                control.pause()
        while True:
            async with self._lock:
                batch = tuple(self.inbox)
                self.inbox.clear()
            if not batch:
                if self.proposal is None and not self._clarifying:
                    return
                self._changed.clear()
                if self.inbox:
                    continue
                await self._changed.wait()
                continue
            if self.dialogue.caller_limit:
                self.proposal = None
                self._clarifying = False
                self.status, self.status_role = LIMIT_MESSAGE, "alert"
                self._publish(LIMIT_MESSAGE, MessageKind.RECOVERY)
                if control is not None:
                    control.change_action = "cancel"
                raise RevisionRequested()
            substantive = tuple(event for event in batch if event.content.strip().lower() not in ("yes", "no"))
            if self.proposal is not None and not substantive:
                event = batch[-1]
                answer = event.content.strip().lower()
                if answer in ("yes", "no") and event.proposal_version == self.proposal.version:
                    proposal = self.proposal
                    self.proposal = None
                    self.visible_proposal = None
                    if control is not None:
                        control.resume()
                    self.status = "I'm working on that now."
                    self._notify()
                    if answer == "no":
                        if boundary == "continuation":
                            control.change_action = "keep"
                            raise RevisionRequested()
                        return
                    self._applied = proposal
                    self._next_input = proposal.source
                    self._switch = proposal.action == "switch"
                    self._cancel = proposal.action == "cancel"
                    if control is not None:
                        control.change_action = proposal.action
                    raise RevisionRequested()
                if answer in ("yes", "no"):
                    self._publish("Please reply Yes or No to the latest change question.", MessageKind.CONFIRMATION)
                    continue
            if not substantive:
                self._publish("Please clarify the change you want to make.", MessageKind.QUESTION)
                self._clarifying = True
                if control is not None:
                    control.pause()
                continue
            if control is not None:
                control.resume()
            decision = await self._interpret(substantive, ledger)
            source = next(event for event in batch if event.sequence == decision.source_sequence)
            if decision.action in ("decline", "help"):
                self._publish(SCOPE_REFUSAL if decision.action == "decline" else CATALOG_HELP)
                if self.proposal is not None and control is not None:
                    control.pause()
                continue
            if decision.action == "ambiguous":
                self.status = "Please clarify the change you want to make."
                if self.proposal is not None and not re.search(r"[0-9]", source.content):
                    self._publish(self._confirmation(self.proposal, ledger), MessageKind.CONFIRMATION)
                else:
                    self.proposal = None
                    self.visible_proposal = None
                    self._clarifying = True
                    self._publish(self.status, MessageKind.QUESTION)
                if control is not None:
                    control.pause()
                continue
            compatible = decision.action == "supplement" and self.proposal is None and not self._clarifying and ((decision.detail_kind == "zip_code" and ledger.caller.current_account is not None and ledger.detail_kind in ("none", "account_number") and ledger.caller.verified_account is None) or (decision.detail_kind == "account_number" and ledger.detail_kind == "none" and ledger.caller.current_account is None))
            if compatible:
                self._applied = ChangeProposal(0, source, "supplement", ledger.task_name, decision.detail_kind, decision.value, control.revision if control else 0)
                self._next_input = source
                if control is not None:
                    control.change_action = "supplement"
                raise RevisionRequested()
            self._clarifying = False
            self._propose(decision, source, ledger)
            if control is not None:
                control.pause()
            self._notify()

    def _propose(self, decision: InterruptionDecision, source: CallerInput, ledger: TaskToolLedger) -> None:
        self._proposal_version += 1
        self.proposal = ChangeProposal(self._proposal_version, source, decision.action, decision.task_name or ledger.task_name, decision.detail_kind, decision.value, ledger.control.revision if ledger.control else 0)
        self.visible_proposal = None
        self.status = "Please confirm the latest change to continue."
        self._publish(self._confirmation(self.proposal, ledger), MessageKind.CONFIRMATION)

    async def _work(self, generation: int) -> None:
        cycle_turns = 0
        clients: list[Any] = []
        try:
            while self.inbox and not self.disposed and generation == self.dialogue.generation:
                self._active_input = self.inbox.popleft()
                prior = self.task if self.task is not None and self.task.status in (TaskStatus.WAITING_FOR_CLARIFICATION, TaskStatus.FAILED) else None
                self._started_at = monotonic()
                self._cancel = False
                self.status, self.status_role = "I'm working on that now.", "status"
                self._last_progress = monotonic()
                self._last_progress_text = "I'm working on that now."
                if self.dialogue.assistant_count < 90:
                    self._publish(self._last_progress_text, MessageKind.PROGRESS)
                self._control = ExecutionControl(self._checkpoint, revision=self._active_input.revision, generation=generation, manager_turns=cycle_turns, admitted_route=self._pinned_route, recorder=self._recorder)
                self._pinned_route = None
                self._notify()
                from src import app

                kwargs: dict[str, Any] = {"prior_task": prior, "caller": self.task.caller if self.task else None, "progress": self._progress, "control": self._control}
                if self.agents is not None:
                    kwargs["agents"] = self.agents
                result = await app.run_customer_task(self._active_input.content, tuple(item for item in self.dialogue.history if item.sequence < self._active_input.sequence), **kwargs)
                clients.extend(self._control.owned_clients)
                self._control.owned_clients.clear()
                self._recorder = self._control.recorder
                if self.disposed or generation != self.dialogue.generation:
                    return
                self.task = result.task
                if result.outcome is not TaskOutcome.RESUMED and self.inbox and self.task.task_name is not None and not self.task.caller.ended:
                    result = await self._final_checkpoint(result)
                    self.task = result.task
                cycle_turns = self._control.manager_turns
                if result.outcome is TaskOutcome.RESUMED:
                    self._record(result)
                    if self._control.change_action == "keep":
                        _, text = catalog_reply(self.task.task_name, self.task.caller, self.task.catalog_facts, completed=False)
                        self.task = replace(self.task, status=TaskStatus.WAITING_FOR_CLARIFICATION, last_active_at=None)
                        self._publish(text, MessageKind.QUESTION)
                        self.status = "I need one detail to continue."
                        continue
                    if self._next_input is None:
                        self.task = replace(self.task, status=TaskStatus.CANCELED, last_active_at=None)
                        self.inbox.clear()
                        return
                    event = self._next_input
                    self._next_input = None
                    if self._cancel:
                        self.task = replace(self.task, status=TaskStatus.CANCELED)
                        self._publish("Task canceled.", MessageKind.COMPLETION)
                        self.status = "Task canceled."
                        self._cancel = False
                        return
                    if self._switch:
                        self.task = replace(begin_task(event.content, now=monotonic()), caller=self.task.caller)
                        self._switch = False
                    else:
                        caller = self.task.caller
                        if self._applied is not None and self._applied.detail_kind == "account_number" and self._applied.value is not None:
                            caller = correct_account(caller, self._applied.value)
                        self.task = replace(self.task, status=TaskStatus.WAITING_FOR_CLARIFICATION, request=event.content, caller=caller, catalog_facts=CatalogFacts(), catalog_input="", continuation_context=())
                    if self._applied is not None:
                        self._pinned_route = CatalogRoute(action="task", task_name=self._applied.task_name, detail_kind=self._applied.detail_kind)
                    self._applied = None
                    self.inbox.appendleft(event)
                    continue
                self._record(result)
                cycle_turns = 0
                self._retrying = False
                if result.task.caller.ended:
                    self.inbox.clear()
                    self.proposal = None
                    self._publish(SESSION_ENDED_MESSAGE, MessageKind.COMPLETION)
                    self.status, self.status_role = "This session has ended. Start a new conversation to continue.", "alert"
                    return
                if result.response.status == "failed":
                    self.retry_input = self._active_input
                    self.proposal = None
                    self._clarifying = False
                    self.task = replace(self.task, status=TaskStatus.FAILED if self.task.status is not TaskStatus.TIMED_OUT else TaskStatus.TIMED_OUT, last_active_at=None)
                    self.status, self.status_role = ("This task took too long to finish. Start a new conversation to continue." if self.task.status is TaskStatus.TIMED_OUT else "The task couldn't be completed. You can try again."), "alert"
                    self._publish(self.status, MessageKind.RECOVERY)
                else:
                    kind = MessageKind.QUESTION if result.response.status == "clarification_required" else MessageKind.COMPLETION
                    self._publish(result.response.message, kind)
                    if not self._cancel:
                        self.status = "I need one detail to continue." if kind is MessageKind.QUESTION else "Task completed."
                    if result.outcome in (TaskOutcome.OUT_OF_SCOPE, TaskOutcome.CATALOG_HELP):
                        self.status = "That request is outside the supported tasks." if result.outcome is TaskOutcome.OUT_OF_SCOPE else "Ready to help with a supported task."
                    if result.task.status is TaskStatus.WAITING_FOR_APPROVAL:
                        self.status, self.status_role = "Please review the proposed action to continue.", "alert"
                if self._cancel:
                    self.task = replace(self.task, status=TaskStatus.CANCELED, last_active_at=None)
                    self.inbox.clear()
                    return
                self._notify()
        except asyncio.CancelledError:
            return
        except Exception:
            self.retry_input = self._active_input
            self.proposal = None
            self._clarifying = False
            if self.task is not None:
                self.task = replace(self.task, status=TaskStatus.FAILED, last_active_at=None)
            self.status, self.status_role = "The task couldn't be completed. You can try again.", "alert"
            self._publish(SAFE_FAILURE, MessageKind.RECOVERY)
        finally:
            if self._control is not None:
                clients.extend(self._control.owned_clients)
                if self.task is not None and self.task.status is TaskStatus.ACTIVE:
                    self.task = replace(self.task, active_seconds=min(60.0, self._control.active_seconds), last_active_at=None)
            for client in clients:
                try:
                    await client.close()
                except Exception:
                    pass
            self._control = None
            self._progress.clear()
            if self._owns_slot:
                _CAPACITY[self._loop] = max(0, _CAPACITY.get(self._loop, 1) - 1)
                self._owns_slot = False
            self._notify()

    async def _final_checkpoint(self, result: TaskRunResult) -> TaskRunResult:
        ledger = TaskToolLedger(
            capability_call_ids=list(result.task.capability_call_ids), capability_step_ids=list(result.task.capability_step_ids),
            completed_step_ids=list(result.task.completed_step_ids), completed_step_results=list(result.task.completed_step_results),
            caller=result.task.caller, task_name=result.task.task_name, caller_input=result.task.catalog_input,
            facts=result.task.catalog_facts, control=self._control,
        )
        self._control.state = replace(result.task, status=TaskStatus.ACTIVE)
        recorder = self._recorder or ModelCallRecorder(result.task.task_id)
        recorder.update_snapshot(lambda turns: _task_progress_snapshot(self.task, ledger, turn_count=self._control.manager_turns))
        token = recorder.activate()
        try:
            try:
                await self._control.run(self._checkpoint(ledger, "publication"))
            except RevisionRequested:
                status = TaskStatus.CANCELED if self._control.change_action in ("cancel", "switch") else TaskStatus.WAITING_FOR_CLARIFICATION
                task = replace(_merge_tool_ledger(self.task, ledger), status=status, active_seconds=min(60.0, self._control.active_seconds), last_active_at=None)
                return TaskRunResult(task, result.response, TaskOutcome.RESUMED)
            return result
        finally:
            recorder.fail("canceled")
            recorder.deactivate(token)

    def _record(self, result: TaskRunResult) -> None:
        status = result.task.status.value
        if result.outcome in (TaskOutcome.OUT_OF_SCOPE, TaskOutcome.CATALOG_HELP):
            status = TaskStatus.REJECTED.value
        diagnostic_task = replace(result.task, status=TaskStatus(status))
        record_task_outcome(task_id=result.task.task_id, outcome=status, started_at=self._started_at, task_state=_task_progress_snapshot(diagnostic_task), task_name=None if result.outcome in (TaskOutcome.OUT_OF_SCOPE, TaskOutcome.CATALOG_HELP) else result.task.task_name)
        from src import app

        outcome = app.task_diagnostic_outcome(result.outcome)
        if outcome is not None:
            app.DIAGNOSTICS.record(outcome, started_at=self._started_at, task_id=result.task.task_id, task_name=result.task.task_name)

    async def retry(self) -> None:
        self._initialize()
        async with self._lock:
            if self.retry_input is None or (self.worker is not None and not self.worker.done()) or self.task is None or self.task.status is not TaskStatus.FAILED:
                return
            if _CAPACITY.get(self._loop, 0) >= 50:
                self.status, self.status_role = "The service is busy. Please try again shortly.", "alert"
                self._publish(self.status, MessageKind.NOTICE)
                return
            self.inbox.appendleft(self.retry_input)
            self.retry_input = None
            self._retrying = True
            _CAPACITY[self._loop] = _CAPACITY.get(self._loop, 0) + 1
            self._owns_slot = True
            self.worker = asyncio.create_task(self._work(self.dialogue.generation))

    async def cancel(self) -> None:
        self._initialize()
        async with self._lock:
            self.dialogue = replace(self.dialogue, generation=self.dialogue.generation + 1)
            self.inbox.clear()
            self.proposal = None
            self.visible_proposal = None
            self._clarifying = False
            self.retry_input = None
            worker = self.worker
            if worker is not None and not worker.done():
                worker.cancel()
        if worker is not None:
            await asyncio.gather(worker, return_exceptions=True)
        async with self._lock:
            if self.task is not None and self.task.status in (TaskStatus.ACTIVE, TaskStatus.WAITING_FOR_CLARIFICATION, TaskStatus.WAITING_FOR_APPROVAL):
                self.task = replace(self.task, status=TaskStatus.CANCELED, last_active_at=None)
                self._record(TaskRunResult(self.task, ConversationResponse(status="failed", message=""), TaskOutcome.CANCELED))
            self.status, self.status_role = "Task canceled.", "status"
            self._publish("Task canceled. No further steps were started.", MessageKind.COMPLETION)
            self.worker = None

    async def reset(self) -> None:
        generation = self.dialogue.generation + 1
        await self.close()
        async with self._lock:
            self.dialogue = Dialogue(generation=generation)
            self.task = None
            self.worker = None
            self.retry_input = None
            self._next_input = None
            self._applied = None
            self._pinned_route = None
            self._recorder = None
            self._cancel = self._clarifying = self.disposed = False
            self.visible_proposal = None
            self._last_accepted = None
            self._last_progress_text = None
            self.status, self.status_role = "Ready to send a message.", "status"
            self._notify()

    async def close(self) -> None:
        self._initialize()
        self.disposed = True
        self.dialogue = replace(self.dialogue, generation=self.dialogue.generation + 1)
        self.inbox.clear()
        self.proposal = None
        if self.worker is not None and not self.worker.done():
            self.worker.cancel()
            await asyncio.gather(self.worker, return_exceptions=True)
        if self.task is not None and self.task.status in (TaskStatus.ACTIVE, TaskStatus.WAITING_FOR_CLARIFICATION, TaskStatus.WAITING_FOR_APPROVAL):
            self.task = replace(self.task, status=TaskStatus.CANCELED, last_active_at=None)
            self._record(TaskRunResult(self.task, ConversationResponse(status="failed", message=""), TaskOutcome.CANCELED))
        self.dialogue = Dialogue(generation=self.dialogue.generation)
        self.task = None
        self.retry_input = None
        self._active_input = None
        self._next_input = None
        self._applied = None
        self._last_accepted = None
        self._recorder = None
        self.visible_proposal = None
        self._notify()


def dispose_session(session: SessionCoordinator) -> None:
    loop = session._loop
    if loop is not None and not loop.is_closed():
        loop.call_soon_threadsafe(lambda: loop.create_task(session.close()))