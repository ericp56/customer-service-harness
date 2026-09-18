"""Gradio 6 application wiring for the transient Echo Web Chat prototype."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from time import monotonic
from typing import Literal

import gradio as gr
import uvicorn
from fastapi import FastAPI

from src.echo import (
    ActiveConversation,
    Outcome,
    SubmissionState,
    begin_retry,
    begin_submission,
    complete_submission,
    fail_submission,
    new_conversation,
)
from src.observability import DiagnosticOutcome, Diagnostics, HealthStatus

DIAGNOSTICS = Diagnostics()
StatusRole = Literal["status", "alert"]


class EchoOperationalError(RuntimeError):
    """A declared, content-free operational failure from the echo operation."""


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


def generate_echo(content: str) -> str:
    """Return the exact input; tests can replace this declared operation."""
    return content


def initial_state() -> ActiveConversation:
    return new_conversation()


def render_history(state: ActiveConversation) -> list[dict[str, str]]:
    return [{"role": item.role, "content": item.content} for item in state.history]


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
        Outcome.SENT: ("status", "Message sent and echoed."),
        Outcome.BLANK: ("alert", "Enter at least one non-whitespace character before sending."),
        Outcome.TOO_LONG: ("alert", "Messages must contain no more than 4,096 Unicode code points."),
        Outcome.FAILED: ("alert", "The message could not be sent. Retry is available."),
        Outcome.MISMATCHED_ECHO: ("alert", "The message could not be verified. Retry is available."),
        Outcome.ALREADY_SENDING: ("status", "A message is already being sent."),
        Outcome.LIMIT_REACHED: (
            "alert",
            "This conversation has reached 50 message pairs. Start a new conversation to continue.",
        ),
        Outcome.RETRY_UNAVAILABLE: ("status", "There is no failed message to retry."),
        Outcome.IDLE: ("status", "Ready to send a message."),
    }
    return messages[outcome]


def _diagnostic_outcome(outcome: Outcome) -> DiagnosticOutcome | None:
    mapping = {
        Outcome.SENT: DiagnosticOutcome.SUCCESS,
        Outcome.BLANK: DiagnosticOutcome.VALIDATION_BLANK,
        Outcome.TOO_LONG: DiagnosticOutcome.VALIDATION_TOO_LONG,
        Outcome.FAILED: DiagnosticOutcome.OPERATIONAL_FAILURE,
        Outcome.MISMATCHED_ECHO: DiagnosticOutcome.ECHO_MISMATCH,
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
    try:
        echoed = generate_echo(state.pending_text)
    except EchoOperationalError:
        failed = fail_submission(state)
        DIAGNOSTICS.record(
            DiagnosticOutcome.OPERATIONAL_FAILURE,
            started_at=started_at,
        )
        return _callback_result(failed.state, failed.outcome, state.pending_text)

    completed = complete_submission(state, echoed)
    diagnostic_outcome = _diagnostic_outcome(completed.outcome)
    if diagnostic_outcome is not None:
        DIAGNOSTICS.record(diagnostic_outcome, started_at=started_at)
    input_value = "" if completed.outcome is Outcome.SENT else (completed.state.pending_text or "")
    return _callback_result(completed.state, completed.outcome, input_value)


def send_message(content: str, state: ActiveConversation) -> CallbackResult:
    """Run validation and one echo callback without exposing content to diagnostics."""
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
        state = gr.State(value=initial_state())
        message = gr.Textbox(
            label="Message",
            lines=3,
            placeholder="Enter a message",
            autofocus=True,
            elem_id="echo-message",
        )
        status = gr.HTML(
            value=_status_markup("status", "Ready to send a message."),
            elem_id="echo-status",
        )
        with gr.Row():
            send = gr.Button("Send", variant="primary", elem_id="echo-send")
            retry = gr.Button("Retry", visible=False, elem_id="echo-retry")
            reset = gr.Button(
                "Start New Conversation",
                visible=False,
                elem_id="echo-new-conversation",
            )

        outputs = [conversation, message, state, status, send, retry, reset]
        send.click(
            send_event,
            inputs=[message, state],
            outputs=outputs,
            concurrency_limit=50,
            concurrency_id="echo-submission",
            trigger_mode="once",
            api_name="submit",
            api_visibility="undocumented",
        )
        message.submit(
            send_event,
            inputs=[message, state],
            outputs=outputs,
            concurrency_limit=50,
            concurrency_id="echo-submission",
            trigger_mode="once",
            api_name="submit-on-enter",
            api_visibility="undocumented",
        )
        retry.click(
            retry_event,
            inputs=[state],
            outputs=outputs,
            concurrency_limit=50,
            concurrency_id="echo-submission",
            trigger_mode="once",
            api_name="retry",
            api_visibility="undocumented",
        )
        reset.click(
            reset_event,
            outputs=outputs,
            queue=False,
            api_name="new-conversation",
            api_visibility="undocumented",
        )
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
