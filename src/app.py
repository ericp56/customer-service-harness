"""Gradio 6 application wiring for the transient Echo Web Chat prototype."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from html import escape
from time import monotonic
from typing import AsyncIterator, Literal

import gradio as gr
import uvicorn
from fastapi import FastAPI

from src.ai_client import InvalidConfigurationError, load_configuration
from src.catalog_policy import SCOPE_REFUSAL
from src.chat import (
    ActiveConversation,
    ChatMessage,
    Outcome,
    SubmissionState,
    begin_retry,
    begin_submission,
    complete_submission,
    fail_submission,
    new_conversation,
)
from src.accounts import CallerSession
from src.observability import DiagnosticOutcome, Diagnostics, HealthStatus, TaskName
from src.task_runtime import TaskOutcome, TaskStatus
from src.task_runtime import (
    TaskState,
    accrue_active_time,
    begin_task,
    cancel_task,
    resolve_simulated_approval,
    resume_task,
    run_customer_task,
)
from src.tools import TaskActivity, TaskProgress
from src.conversation_runtime import SessionCoordinator, dispose_session

DIAGNOSTICS = Diagnostics()
StatusRole = Literal["status", "alert"]
INGRESS_JS = """(content, state) => {
    const input = document.querySelector('#echo-message textarea');
    if (input && input.value === content) {
        const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
        setter.call(input, '');
        input.dispatchEvent(new Event('input', {bubbles: true}));
    }
    return [content, state];
}"""


def initial_session() -> SessionCoordinator:
    return SessionCoordinator()


async def conversation_send_event(content: str, session: SessionCoordinator) -> str:
    return "" if await session.accept(content) else content


async def conversation_ingress_event(content: str, session: SessionCoordinator) -> tuple[object, SessionCoordinator]:
    return gr.skip() if await session.accept(content) else content, session


async def conversation_render_event(session: SessionCoordinator) -> tuple[object, ...]:
    async with session.render_update(progress_status) as changed:
        active = session.worker is not None and not session.worker.done()
        if not changed:
            return tuple(gr.skip() for _ in range(7))
        ended = session.disposed or (session.task is not None and session.task.caller.ended)
        approval = session.task is not None and session.task.status is TaskStatus.WAITING_FOR_APPROVAL
        paused = session.task is not None and session.task.status in (TaskStatus.WAITING_FOR_CLARIFICATION, TaskStatus.WAITING_FOR_APPROVAL)
        retryable = session.retry_input is not None and session.task is not None and session.task.status is TaskStatus.FAILED
        return (
            [{"role": item.role, "content": escape(item.content, quote=False)} for item in session.dialogue.history],
            gr.Button(interactive=not ended and not session.dialogue.caller_limit and not approval),
            gr.Button(visible=retryable and not ended, interactive=retryable and not active),
            gr.Button(visible=bool(session.dialogue.inputs) or ended),
            gr.Button(visible=active or paused, interactive=active or paused),
            gr.Button(visible=approval, interactive=approval),
            gr.Button(visible=approval, interactive=approval),
        )


async def conversation_retry_event(session: SessionCoordinator) -> SessionCoordinator:
    await session.retry()
    return session


async def conversation_cancel_event(session: SessionCoordinator) -> SessionCoordinator:
    await session.cancel()
    return session


async def conversation_reset_event(session: SessionCoordinator) -> tuple[str, SessionCoordinator]:
    await session.reset()
    return "", session


async def conversation_approval_event(session: SessionCoordinator, approved: bool) -> SessionCoordinator:
    await session.resolve_approval(approved)
    return session


async def conversation_approve_event(session: SessionCoordinator) -> SessionCoordinator:
    return await conversation_approval_event(session, True)


async def conversation_reject_event(session: SessionCoordinator) -> SessionCoordinator:
    return await conversation_approval_event(session, False)


@dataclass(frozen=True)
class CallbackResult:
    """A content-bearing response kept only in the current Gradio interaction."""

    history: list[dict[str, str]]
    input_value: str
    state: ActiveConversation
    outcome: Outcome
    status_text: str
    status_role: StatusRole
    retry_visible: bool
    reset_visible: bool
    send_enabled: bool


def initial_state() -> ActiveConversation:
    return new_conversation()


def render_history(state: ActiveConversation) -> list[dict[str, str]]:
    return [
        {"role": item.role, "content": item.content}
        for item in state.history
        if isinstance(item, ChatMessage)
    ]


def privacy_configuration() -> dict[str, bool]:
    """Document the privacy-relevant application configuration for verification."""
    return {
        "analytics_enabled": False,
        "share_enabled": False,
        "feedback_enabled": False,
        "uploads_enabled": False,
        "browser_persistence_enabled": False,
        "rich_content_enabled": False,
    }


def health_status() -> dict[str, str]:
    """Expose only content-free readiness information."""
    try:
        load_configuration()
    except InvalidConfigurationError:
        return {"status": HealthStatus.NOT_READY.value}
    return {"status": DIAGNOSTICS.health().value}


def diagnostics_snapshot() -> dict[str, object]:
    """Return aggregate, fixed-cardinality diagnostic data without conversation content."""
    return {
        "outcomes": dict(DIAGNOSTICS.outcomes),
        "events": tuple(DIAGNOSTICS.events),
        "health": DIAGNOSTICS.health(),
    }


def _status(outcome: Outcome) -> tuple[StatusRole, str]:
    messages: dict[Outcome, tuple[StatusRole, str]] = {
        Outcome.SENT: ("status", "Message sent."),
        Outcome.BLANK: ("alert", "Enter at least one non-whitespace character before sending."),
        Outcome.TOO_LONG: ("alert", "Messages must contain no more than 4,096 Unicode code points."),
        Outcome.FAILED: ("alert", "The message could not be sent. Retry is available."),
        Outcome.ALREADY_SENDING: ("status", "A message is already being sent."),
        Outcome.LIMIT_REACHED: (
            "alert",
            "This conversation has reached 50 message pairs. Start a new conversation to continue.",
        ),
        Outcome.RETRY_UNAVAILABLE: ("status", "There is no failed message to retry."),
        Outcome.IDLE: ("status", "Ready to send a message."),
    }
    return messages[outcome]


def task_status(status: TaskStatus) -> tuple[StatusRole, str]:
    messages: dict[TaskStatus, tuple[StatusRole, str]] = {
        TaskStatus.ACTIVE: ("status", "I'm working on that now."),
        TaskStatus.WAITING_FOR_CLARIFICATION: ("status", "I need one detail to continue."),
        TaskStatus.WAITING_FOR_APPROVAL: ("alert", "Please review the proposed action to continue."),
        TaskStatus.COMPLETED: ("status", "Task completed."),
        TaskStatus.FAILED: ("alert", "The task couldn't be completed. You can try again."),
        TaskStatus.CANCELED: ("status", "Task canceled."),
        TaskStatus.REJECTED: ("status", "I didn't proceed with the proposed action."),
        TaskStatus.TIMED_OUT: ("alert", "This task took too long to finish. Please try again."),
        TaskStatus.SESSION_ENDED: ("alert", "This session has ended. Start a new conversation to continue."),
    }
    return messages[status]


def progress_status(update_number: int, progress: TaskProgress | None = None) -> tuple[StatusRole, str]:
    activity_messages = {
        TaskActivity.PROCESSING: "I'm reviewing your request.",
        TaskActivity.WORKING_ON_TASK: "I'm working on your task.",
        TaskActivity.LOOKING_UP_INFORMATION: "I'm looking up information.",
        TaskActivity.CHECKING_INFORMATION: "I'm checking your information.",
        TaskActivity.EVALUATING_RESULT: "I'm evaluating the task result.",
    }
    activity = getattr(progress, "activity", None)
    message = activity_messages.get(activity)
    if message is not None:
        task_name = getattr(progress, "task_name", None)
        if activity == TaskActivity.EVALUATING_RESULT and isinstance(task_name, TaskName):
            message = f"I'm evaluating the result for: {task_name.value}."
        return "status", message

    messages = (
        "I'm still working on that.",
        "I'm continuing to work on that.",
    )
    return "status", messages[(max(1, update_number) - 1) % len(messages)]


def task_diagnostic_outcome(outcome: TaskOutcome) -> DiagnosticOutcome | None:
    mapping = {
        TaskOutcome.COMPLETED: DiagnosticOutcome.TASK_COMPLETED,
        TaskOutcome.FAILED: DiagnosticOutcome.TASK_FAILED,
        TaskOutcome.CANCELED: DiagnosticOutcome.TASK_CANCELED,
        TaskOutcome.REJECTED: DiagnosticOutcome.TASK_REJECTED,
        TaskOutcome.TIMED_OUT: DiagnosticOutcome.TASK_TIMEOUT,
        TaskOutcome.INVALID_CONFIGURATION: DiagnosticOutcome.INVALID_CONFIGURATION,
        TaskOutcome.DUPLICATE_CALL: DiagnosticOutcome.TASK_UNSUPPORTED_CAPABILITY,
        TaskOutcome.DUPLICATE_STEP: DiagnosticOutcome.TASK_UNSUPPORTED_CAPABILITY,
        TaskOutcome.CAPABILITY_LIMIT: DiagnosticOutcome.TASK_UNSUPPORTED_CAPABILITY,
        TaskOutcome.TURN_LIMIT: DiagnosticOutcome.TASK_FAILED,
        TaskOutcome.SESSION_ENDED: DiagnosticOutcome.TASK_SESSION_ENDED,
        TaskOutcome.OUT_OF_SCOPE: DiagnosticOutcome.TASK_REJECTED,
        TaskOutcome.CATALOG_HELP: DiagnosticOutcome.TASK_REJECTED,
    }
    return mapping.get(outcome)


def _session_ended(task_state: TaskState | None) -> bool:
    return task_state is not None and (
        task_state.status is TaskStatus.SESSION_ENDED or task_state.caller.ended
    )


def _task_event_outputs(
    state: ActiveConversation,
    task_state: TaskState | None,
    input_value: str,
    status_role: StatusRole,
    status_text: str,
    *,
    retry_visible: bool = False,
) -> tuple[object, ...]:
    active = task_state is not None and task_state.status is TaskStatus.ACTIVE
    waiting_for_clarification = task_state is not None and task_state.status is TaskStatus.WAITING_FOR_CLARIFICATION
    waiting_for_approval = task_state is not None and task_state.status is TaskStatus.WAITING_FOR_APPROVAL
    ended = _session_ended(task_state)
    display_history = [
        {"role": item["role"], "content": escape(item["content"], quote=False)}
        for item in render_history(state)
    ]
    return (
        display_history,
        input_value,
        state,
        task_state,
        gr.HTML(value=_status_markup(status_role, status_text)),
        gr.Button(interactive=not active and not waiting_for_approval and not ended),
        gr.Button(visible=retry_visible and not ended, interactive=retry_visible and not ended),
        gr.Button(visible=state.submission_state is SubmissionState.LIMIT_REACHED or waiting_for_clarification or waiting_for_approval or ended),
        gr.Button(visible=active or waiting_for_clarification or waiting_for_approval, interactive=active or waiting_for_clarification or waiting_for_approval),
        gr.Button(visible=waiting_for_approval, interactive=waiting_for_approval),
        gr.Button(visible=waiting_for_approval, interactive=waiting_for_approval),
    )


async def task_send_event(
    content: str,
    state: ActiveConversation,
    current_task: TaskState | None,
    *,
    progress_interval_seconds: float = 5.0,
    retry: bool = False,
) -> AsyncIterator[tuple[object, ...]]:
    """Submit a task while yielding separate, fixed customer-safe progress status."""
    started_at = monotonic()
    if _session_ended(current_task):
        role, text = task_status(TaskStatus.SESSION_ENDED)
        yield _task_event_outputs(state, current_task, "", role, text)
        return
    if current_task is not None and current_task.status is TaskStatus.WAITING_FOR_APPROVAL:
        role, text = task_status(current_task.status)
        yield _task_event_outputs(state, current_task, content, role, text)
        return
    if current_task is not None and current_task.status is TaskStatus.ACTIVE:
        yield _task_event_outputs(state, current_task, content, "status", "A task is already being handled.")
        return
    if retry and current_task is not None and current_task.status is TaskStatus.TIMED_OUT:
        role, text = task_status(current_task.status)
        yield _task_event_outputs(state, current_task, content, role, text)
        return

    started = begin_retry(state) if retry else begin_submission(state, content)
    if started.outcome is not Outcome.SENT:
        diagnostic_outcome = _diagnostic_outcome(started.outcome)
        if diagnostic_outcome is not None:
            DIAGNOSTICS.record(diagnostic_outcome, started_at=started_at)
        role, text = _status(started.outcome)
        yield _task_event_outputs(started.state, None, content, role, text)
        return

    continuing_task = (
        current_task
        if current_task is not None
        and current_task.status in (TaskStatus.WAITING_FOR_CLARIFICATION, TaskStatus.FAILED)
        else None
    )
    carried_caller = current_task.caller if current_task is not None else None
    if continuing_task is None:
        task_state = replace(begin_task(content, now=started_at), caller=carried_caller or CallerSession())
    else:
        resumed = resume_task(continuing_task, now=started_at)
        if resumed.outcome is not TaskOutcome.RESUMED:
            failed = fail_submission(started.state)
            role, text = task_status(resumed.state.status)
            yield _task_event_outputs(failed.state, resumed.state, content, role, text, retry_visible=True)
            return
        task_state = resumed.state
    progress = TaskProgress()
    task = asyncio.create_task(
        run_customer_task(
            content,
            started.state.history,
            prior_task=continuing_task,
            caller=carried_caller,
            progress=progress,
        )
    )
    progress_count = 0
    try:
        role, text = task_status(TaskStatus.ACTIVE)
        yield _task_event_outputs(started.state, task_state, content, role, text)
        while not task.done():
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=progress_interval_seconds)
            except TimeoutError:
                if task.done():
                    break
                tick = accrue_active_time(task_state, now=monotonic())
                task_state = tick.state
                progress_count += 1
                role, text = progress_status(progress_count, progress)
                yield _task_event_outputs(started.state, task_state, content, role, text)

        result = task.result()
        if result.outcome in (TaskOutcome.OUT_OF_SCOPE, TaskOutcome.CATALOG_HELP):
            completed = complete_submission(started.state, result.response.message)
            DIAGNOSTICS.record(
                DiagnosticOutcome.TASK_REJECTED,
                started_at=started_at,
                task_id=result.task.task_id,
            )
            status_text = (
                "That request is outside the supported tasks."
                if result.outcome is TaskOutcome.OUT_OF_SCOPE
                else "Ready to help with a supported task."
            )
            if result.task.status is TaskStatus.WAITING_FOR_CLARIFICATION:
                status_text += " Your previous task is still waiting for a detail."
            yield _task_event_outputs(completed.state, result.task, "", "status", status_text)
            return
        if result.response.status == "failed" or result.response.status == "unsupported":
            failed = fail_submission(started.state)
            diagnostic_outcome = task_diagnostic_outcome(result.outcome) or DiagnosticOutcome.TASK_FAILED
            diagnostic_error = (
                InvalidConfigurationError("invalid OPENAI_REASONING configuration")
                if result.outcome is TaskOutcome.INVALID_CONFIGURATION
                else None
            )
            DIAGNOSTICS.record(
                diagnostic_outcome,
                started_at=started_at,
                task_id=result.task.task_id,
                error=diagnostic_error,
            )
            role, text = task_status(result.task.status)
            yield _task_event_outputs(failed.state, result.task, content, role, text, retry_visible=True)
            return

        completed = complete_submission(started.state, result.response.message)
        mapped_outcome = task_diagnostic_outcome(result.outcome)
        if mapped_outcome is not None:
            DIAGNOSTICS.record(
                mapped_outcome,
                started_at=started_at,
                account_number=result.task.caller.current_account,
                task_id=result.task.task_id,
                task_name=result.task.task_name,
            )
        role, text = task_status(result.task.status)
        yield _task_event_outputs(completed.state, result.task, "", role, text)
    except asyncio.CancelledError:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        cancel_task(task_state, now=monotonic())
        DIAGNOSTICS.record(DiagnosticOutcome.TASK_CANCELED, started_at=started_at)
        raise
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


def _diagnostic_outcome(outcome: Outcome) -> DiagnosticOutcome | None:
    mapping = {
        Outcome.SENT: DiagnosticOutcome.SUCCESS,
        Outcome.BLANK: DiagnosticOutcome.VALIDATION_BLANK,
        Outcome.TOO_LONG: DiagnosticOutcome.VALIDATION_TOO_LONG,
        Outcome.FAILED: DiagnosticOutcome.OPERATIONAL_FAILURE,
        Outcome.LIMIT_REACHED: DiagnosticOutcome.LIMIT_REACHED,
        Outcome.ALREADY_SENDING: DiagnosticOutcome.DUPLICATE_PREVENTED,
    }
    return mapping.get(outcome)


def _callback_result(state: ActiveConversation, outcome: Outcome, input_value: str) -> CallbackResult:
    status_role, status_text = _status(outcome)
    is_failed = state.submission_state is SubmissionState.FAILED
    is_limited = state.submission_state is SubmissionState.LIMIT_REACHED
    return CallbackResult(
        history=render_history(state),
        input_value=input_value,
        state=state,
        outcome=outcome,
        status_text=status_text,
        status_role=status_role,
        retry_visible=is_failed,
        reset_visible=is_limited,
        send_enabled=not is_limited and state.submission_state is not SubmissionState.SENDING,
    )


def _finish_sending(state: ActiveConversation, started_at: float) -> CallbackResult:
    assert state.pending_text is not None
    completed = complete_submission(state, SCOPE_REFUSAL)
    DIAGNOSTICS.record(DiagnosticOutcome.TASK_REJECTED, started_at=started_at)
    input_value = "" if completed.outcome is Outcome.SENT else (completed.state.pending_text or "")
    return _callback_result(completed.state, completed.outcome, input_value)


def send_message(content: str, state: ActiveConversation) -> CallbackResult:
    """Fail closed on the retired synchronous callback without calling a provider."""
    started_at = monotonic()
    started = begin_submission(state, content)
    if started.outcome is not Outcome.SENT:
        diagnostic_outcome = _diagnostic_outcome(started.outcome)
        if diagnostic_outcome is not None:
            DIAGNOSTICS.record(diagnostic_outcome, started_at=started_at)
        return _callback_result(started.state, started.outcome, content)
    return _finish_sending(started.state, started_at)


def retry_message(state: ActiveConversation) -> CallbackResult:
    """Retry a retained valid input exactly once."""
    started_at = monotonic()
    retried = begin_retry(state)
    if retried.outcome is not Outcome.SENT:
        return _callback_result(retried.state, retried.outcome, state.pending_text or "")
    return _finish_sending(retried.state, started_at)


def start_new_conversation() -> CallbackResult:
    """Clear only the current transient conversation state."""
    state = new_conversation()
    return _callback_result(state, Outcome.IDLE, "")


def _status_markup(role: StatusRole, text: str) -> str:
    """Render only fixed application-controlled status messages as accessible HTML."""
    return f'<div role="{role}" aria-live="polite">{text}</div>'


def _to_gradio_outputs(result: CallbackResult) -> tuple[object, ...]:
    # Gradio's sanitizer otherwise removes literal angle-bracket text. Encode only for display.
    display_history = [
        {"role": item["role"], "content": escape(item["content"], quote=False)}
        for item in result.history
    ]
    return (
        display_history,
        result.input_value,
        result.state,
        gr.HTML(value=_status_markup(result.status_role, result.status_text)),
        gr.Button(visible=result.send_enabled, interactive=result.send_enabled),
        gr.Button(visible=result.retry_visible, interactive=result.retry_visible),
        gr.Button(visible=result.reset_visible, interactive=result.reset_visible),
    )


def send_event(text: str, current: ActiveConversation) -> tuple[object, ...]:
    return _to_gradio_outputs(send_message(text, current))


def retry_event(current: ActiveConversation) -> tuple[object, ...]:
    return _to_gradio_outputs(retry_message(current))


def reset_event() -> tuple[object, ...]:
    return _to_gradio_outputs(start_new_conversation())


async def retry_task_event(
    current: ActiveConversation,
    current_task: TaskState | None,
) -> AsyncIterator[tuple[object, ...]]:
    pending_text = current.pending_text or ""
    async for output in task_send_event(pending_text, current, current_task, retry=True):
        yield output


def reset_task_event() -> tuple[object, ...]:
    state = new_conversation()
    return _task_event_outputs(state, None, "", "status", "Ready to send a message.")


def cancel_task_event(
    current: ActiveConversation,
    current_task: TaskState | None,
) -> tuple[object, ...]:
    if current_task is None:
        return _task_event_outputs(current, None, current.pending_text or "", "status", "There is no task to cancel.")
    canceled = cancel_task(current_task, now=monotonic())
    if current.submission_state is SubmissionState.SENDING:
        next_state = fail_submission(current).state
    else:
        completed_text = (
            "Task canceled. Some work completed before cancellation; no further steps were started."
            if current_task.completed_step_ids
            else "Task canceled. No task steps were completed."
        )
        next_state = replace(
            current,
            history=(*current.history, ChatMessage("assistant", completed_text)),
            pending_text=None,
            submission_state=SubmissionState.IDLE,
        )
    DIAGNOSTICS.record(DiagnosticOutcome.TASK_CANCELED, started_at=monotonic())
    status_text = (
        "Task canceled. Some work completed before cancellation; no further steps were started."
        if current_task.completed_step_ids
        else "Task canceled. No task steps were completed."
    )
    return _task_event_outputs(next_state, canceled.state, current.pending_text or "", "status", status_text)


def _resolve_task_approval(
    current: ActiveConversation,
    current_task: TaskState | None,
    *,
    approved: bool,
) -> tuple[object, ...]:
    if current_task is None:
        return _task_event_outputs(current, None, "", "alert", "There is no pending action to review.")
    resolved = resolve_simulated_approval(current_task, approved=approved)
    if resolved.outcome is TaskOutcome.INVALID_TRANSITION:
        return _task_event_outputs(current, current_task, "", "alert", "This action is no longer awaiting a decision.")

    response_text = (
        "The simulated action was approved and completed."
        if approved
        else "I didn't proceed with the proposed action."
    )
    next_state = replace(
        current,
        history=(*current.history, ChatMessage("assistant", response_text)),
        pending_text=None,
        submission_state=SubmissionState.IDLE,
    )
    diagnostic_outcome = task_diagnostic_outcome(resolved.outcome)
    if diagnostic_outcome is not None:
        DIAGNOSTICS.record(diagnostic_outcome, started_at=monotonic(), task_name=resolved.state.task_name)
    status_role, status_text = task_status(resolved.state.status)
    return _task_event_outputs(next_state, resolved.state, "", status_role, status_text)


def approve_task_event(current: ActiveConversation, current_task: TaskState | None) -> tuple[object, ...]:
    return _resolve_task_approval(current, current_task, approved=True)


def reject_task_event(current: ActiveConversation, current_task: TaskState | None) -> tuple[object, ...]:
    return _resolve_task_approval(current, current_task, approved=False)


def build_app() -> gr.Blocks:
    """Build a text-only Blocks page with a finite, 50-way event queue."""
    with gr.Blocks(analytics_enabled=False, title="Echo Web Chat") as demo:
        gr.HTML("<h1>Echo Web Chat</h1>")
        conversation = gr.Chatbot(
            value=[],
            label="Conversation",
            render_markdown=False,
            sanitize_html=True,
            latex_delimiters=[],
            buttons=[],
            feedback_options=None,
            allow_file_downloads=False,
            allow_tags=False,
            line_breaks=True,
            elem_id="echo-conversation",
        )
        state = gr.State(value=initial_session, time_to_live=300, delete_callback=dispose_session)
        subscriber = gr.Timer(0.25)
        message = gr.Textbox(
            label="Message",
            lines=3,
            placeholder="Enter a message",
            autofocus=True,
            elem_id="echo-message",
        )
        with gr.Row():
            send = gr.Button("Send", variant="primary", elem_id="echo-send")
            retry = gr.Button("Retry", visible=False, elem_id="echo-retry")
            reset = gr.Button(
                "Start New Conversation",
                visible=False,
                elem_id="echo-new-conversation",
            )
            cancel = gr.Button("Cancel Task", visible=False, elem_id="echo-cancel-task")
            approve = gr.Button("Approve Action", visible=False, elem_id="echo-approve-task")
            reject = gr.Button("Reject Action", visible=False, elem_id="echo-reject-task")

        subscriber.tick(
            conversation_render_event,
            inputs=[state],
            outputs=[conversation, send, retry, reset, cancel, approve, reject],
            queue=False,
            trigger_mode="always_last",
            concurrency_limit=1,
            api_name="subscribe",
            api_visibility="private",
            show_progress="hidden",
        )
        send.click(
            conversation_ingress_event,
            inputs=[message, state],
            outputs=[message, state],
            js=INGRESS_JS,
            queue=False,
            trigger_mode="multiple",
            api_name="submit",
            api_visibility="undocumented",
        )
        message.submit(
            conversation_ingress_event,
            inputs=[message, state],
            outputs=[message, state],
            js=INGRESS_JS,
            queue=False,
            trigger_mode="multiple",
            api_name="submit-on-enter",
            api_visibility="undocumented",
        )
        retry.click(
            conversation_retry_event,
            inputs=[state],
            outputs=[state],
            queue=False,
            trigger_mode="once",
            api_name="retry",
            api_visibility="undocumented",
        )
        reset.click(
            conversation_reset_event,
            inputs=[state],
            outputs=[message, state],
            queue=False,
            api_name="new-conversation",
            api_visibility="undocumented",
        )
        cancel.click(
            conversation_cancel_event,
            inputs=[state],
            outputs=[state],
            queue=False,
            api_name="cancel-task",
            api_visibility="undocumented",
        )
        approve.click(
            conversation_approve_event,
            inputs=[state],
            outputs=[state],
            queue=False,
            api_name="approve-task",
            api_visibility="undocumented",
        )
        reject.click(
            conversation_reject_event,
            inputs=[state],
            outputs=[state],
            queue=False,
            api_name="reject-task",
            api_visibility="undocumented",
        )

        async def unload_session(request: gr.Request) -> None:
            current = demo.state_holder.session_data.get(request.session_hash)
            if current is not None:
                session = current.state_data.get(state._id)
                if isinstance(session, SessionCoordinator):
                    await session.close()

        demo.unload(unload_session)
    return demo.queue(default_concurrency_limit=50, max_size=100, api_open=False)


def create_server() -> FastAPI:
    """Mount Gradio and add same-origin content-free health and readiness endpoints."""
    server = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @server.get("/healthz")
    def healthz() -> dict[str, str]:
        return health_status()

    @server.get("/readyz")
    def readyz() -> dict[str, str]:
        return health_status()

    return gr.mount_gradio_app(
        server,
        build_app(),
        path="/",
        run_history=False,
        enable_monitoring=False,
        pwa=False,
        show_error=False,
    )


if __name__ == "__main__":
    uvicorn.run(create_server(), host="127.0.0.1", port=7860, access_log=False, log_level="warning")
