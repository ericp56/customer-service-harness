"""Browser journeys for the transient public Echo Web Chat page."""

from __future__ import annotations

import asyncio
import threading
import time
from urllib.request import urlopen

import pytest
import uvicorn
from playwright.sync_api import expect

from src import app
from src.task_agents import ConversationResponse, TaskAgentResult
from src.task_runtime import (
    TaskOutcome,
    TaskRunResult,
    TaskState,
    TaskStatus,
    begin_task,
    request_simulated_approval,
)


pytestmark = pytest.mark.e2e


@pytest.fixture(autouse=True)
def fake_reply(monkeypatch):
    async def reply(text: str, _history: tuple, **_kwargs) -> TaskRunResult:
        task = TaskState(text, TaskStatus.COMPLETED, 0.01, None)
        response = ConversationResponse(status="completed", message=f"Answer: {text}")
        return TaskRunResult(task, response, TaskOutcome.COMPLETED)

    monkeypatch.setattr(app, "run_customer_task", reply)


@pytest.fixture(scope="session")
def browser_runtime_available(browser) -> None:
    """Use pytest-playwright's browser fixture; it skips only if runtime setup is unavailable."""
    assert browser.is_connected()


@pytest.fixture(scope="session")
def echo_url(browser_runtime_available: None) -> str:
    server = uvicorn.Server(
        uvicorn.Config(
            app.create_server(),
            host="127.0.0.1",
            port=7860,
            access_log=False,
            log_level="critical",
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    url = "http://127.0.0.1:7860"
    for _ in range(50):
        try:
            with urlopen(f"{url}/healthz", timeout=0.2) as response:
                if response.status == 200:
                    break
        except OSError:
            time.sleep(0.1)
    else:
        server.should_exit = True
        thread.join(timeout=5)
        pytest.fail("Echo application did not become ready.")

    yield url

    server.should_exit = True
    thread.join(timeout=5)


def submit(page, text: str) -> None:
    page.locator("#echo-message textarea").fill(text)
    page.locator("#echo-send").click()


def test_normal_unicode_and_line_break_reply(page, echo_url: str) -> None:
    page.goto(echo_url)
    text = "Hello\n世界 <tag>"

    submit(page, text)

    conversation = page.locator("#echo-conversation")
    expect(conversation).to_contain_text("Answer:")
    expect(conversation).to_contain_text("世界")
    expect(conversation).to_contain_text("<tag>")
    assert conversation.locator("script").count() == 0
    assert page.context.cookies() == []
    assert page.evaluate("Object.keys(localStorage)") == []
    assert page.evaluate("Object.keys(sessionStorage)") == []


def test_accessible_validation_and_recovery(page, echo_url: str) -> None:
    page.goto(echo_url)

    submit(page, " \t")

    status = page.locator("#echo-status [role='alert']")
    expect(status).to_contain_text("non-whitespace")
    expect(page.locator("#echo-conversation [role='log']")).to_have_text("")


def test_keyboard_retry_recovers_a_declared_operational_failure(page, echo_url: str, monkeypatch) -> None:
    page.goto(echo_url)

    async def fail(text: str, _history: tuple, **_kwargs) -> TaskRunResult:
        task = TaskState(
            text,
            TaskStatus.FAILED,
            0.01,
            None,
            turn_count=1,
            capability_call_ids=("call-1",),
            capability_step_ids=("lookup-1",),
            completed_step_ids=("lookup-1",),
        )
        response = ConversationResponse(status="failed", message="I couldn't complete that task. Please try again.")
        return TaskRunResult(task, response, TaskOutcome.FAILED)

    monkeypatch.setattr(app, "run_customer_task", fail)
    submit(page, "retry this")
    expect(page.locator("#echo-status [role='alert']")).to_contain_text("You can try again")
    retry = page.locator("#echo-retry")
    expect(retry).to_be_visible()

    async def recovered(text: str, _history: tuple, **kwargs) -> TaskRunResult:
        prior_task = kwargs.get("prior_task")
        assert prior_task is not None
        assert prior_task.completed_step_ids == ("lookup-1",)
        task = TaskState(
            text,
            TaskStatus.COMPLETED,
            prior_task.active_seconds + 0.01,
            None,
            turn_count=2,
            capability_call_ids=prior_task.capability_call_ids,
            capability_step_ids=prior_task.capability_step_ids,
            completed_step_ids=prior_task.completed_step_ids,
        )
        response = ConversationResponse(status="completed", message=f"Answer: {text}")
        return TaskRunResult(task, response, TaskOutcome.COMPLETED)

    monkeypatch.setattr(app, "run_customer_task", recovered)
    retry.focus()
    retry.press("Enter")
    expect(page.locator("#echo-conversation [role='log']")).to_contain_text("retry this")


def test_fifty_pairs_require_new_conversation(page, echo_url: str) -> None:
    page.goto(echo_url)
    for number in range(50):
        submit(page, str(number))
        expect(page.locator("#echo-message textarea")).to_have_value("")

    expect(page.locator("#echo-new-conversation")).to_be_visible()
    page.locator("#echo-new-conversation").click()
    expect(page.locator("#echo-conversation [role='log']")).to_have_text("")


def test_cancel_stops_active_task_without_partial_reply(page, echo_url: str, monkeypatch) -> None:
    page.goto(echo_url)

    async def slow_task(text: str, _history: tuple, **_kwargs) -> TaskRunResult:
        await asyncio.sleep(30)
        task = TaskState(text, TaskStatus.COMPLETED, 30.0, None)
        response = ConversationResponse(status="completed", message="Should not appear.")
        return TaskRunResult(task, response, TaskOutcome.COMPLETED)

    monkeypatch.setattr(app, "run_customer_task", slow_task)
    submit(page, "cancel this task")

    cancel = page.locator("#echo-cancel-task")
    expect(cancel).to_be_visible()
    cancel.click()

    expect(page.locator("#echo-status [role='status']")).to_contain_text("Task canceled.")
    expect(page.locator("#echo-message textarea")).to_have_value("cancel this task")
    expect(page.locator("#echo-conversation [role='log']")).not_to_contain_text("Should not appear.")


@pytest.mark.parametrize(
    ("decision", "expected_text"),
    [
        ("approve", "The simulated action was approved and completed."),
        ("reject", "I didn't proceed with the proposed action."),
        ("cancel", "Task canceled."),
    ],
)
def test_simulated_action_requires_customer_decision(
    page,
    echo_url: str,
    monkeypatch,
    decision: str,
    expected_text: str,
) -> None:
    page.goto(echo_url)

    async def pending_approval(text: str, _history: tuple, **_kwargs) -> TaskRunResult:
        task = request_simulated_approval(
            begin_task(text, now=0.0),
            "Change the sample customer-service preference.",
            now=0.1,
        ).state
        response = ConversationResponse(
            status="approval_required",
            message="Please review this simulated action.",
            task_result=TaskAgentResult(
                status="approval_required",
                summary="The sample preference is ready for review.",
                proposal="Change the sample customer-service preference.",
            ),
        )
        return TaskRunResult(task, response, TaskOutcome.PAUSED)

    monkeypatch.setattr(app, "run_customer_task", pending_approval)
    submit(page, "change the sample preference")

    expect(page.locator("#echo-approve-task")).to_be_visible()
    expect(page.locator("#echo-reject-task")).to_be_visible()
    expect(page.locator("#echo-conversation")).to_contain_text("Please review this simulated action.")

    page.locator(f"#echo-{decision}-task").click()

    expect(page.locator("#echo-conversation")).to_contain_text(expected_text)
    expect(page.locator("#echo-approve-task")).to_be_hidden()
    expect(page.locator("#echo-reject-task")).to_be_hidden()


def test_clarification_resumes_existing_task(page, echo_url: str, monkeypatch) -> None:
    page.goto(echo_url)
    calls = 0

    async def task_with_clarification(text: str, _history: tuple, *, prior_task=None) -> TaskRunResult:
        nonlocal calls
        calls += 1
        if prior_task is None:
            task = TaskState(text, TaskStatus.WAITING_FOR_CLARIFICATION, 2.0, None, turn_count=1)
            response = ConversationResponse(
                status="clarification_required",
                message="Which day should I check?",
                task_result=TaskAgentResult(
                    status="clarification_required",
                    summary="",
                    question="Which day should I check?",
                ),
            )
            return TaskRunResult(task, response, TaskOutcome.PAUSED)

        task = TaskState(prior_task.request, TaskStatus.COMPLETED, 3.0, None, turn_count=2)
        response = ConversationResponse(status="completed", message=f"Hours for {text}: weekdays.")
        return TaskRunResult(task, response, TaskOutcome.COMPLETED)

    monkeypatch.setattr(app, "run_customer_task", task_with_clarification)
    submit(page, "Find the service hours")
    expect(page.locator("#echo-conversation")).to_contain_text("Which day should I check?")

    submit(page, "Weekdays")

    expect(page.locator("#echo-conversation")).to_contain_text("Hours for Weekdays: weekdays.")
    assert calls == 2


def test_progress_updates_after_five_seconds_outside_chat(page, echo_url: str, monkeypatch) -> None:
    page.goto(echo_url)

    async def slow_task(text: str, _history: tuple, **_kwargs) -> TaskRunResult:
        await asyncio.sleep(6.2)
        task = TaskState(text, TaskStatus.COMPLETED, 6.2, None)
        response = ConversationResponse(status="completed", message="Synthetic result.")
        return TaskRunResult(task, response, TaskOutcome.COMPLETED)

    monkeypatch.setattr(app, "run_customer_task", slow_task)
    started_at = time.monotonic()
    submit(page, "slow supported lookup")
    status = page.locator("#echo-status [role='status']")

    expect(status).to_contain_text("I'm working on that now.")
    expect(status).to_contain_text("I'm still working on that.", timeout=6000)
    assert 5.0 <= time.monotonic() - started_at <= 6.0
    expect(page.locator("#echo-conversation")).not_to_contain_text("I'm still working on that.")
    expect(page.locator("#echo-conversation")).to_contain_text("Synthetic result.")


def test_task_timeout_keeps_input_for_safe_retry(page, echo_url: str, monkeypatch) -> None:
    page.goto(echo_url)

    async def timed_out(text: str, _history: tuple, **_kwargs) -> TaskRunResult:
        task = TaskState(text, TaskStatus.TIMED_OUT, 60.0, None)
        response = ConversationResponse(status="failed", message="This task took too long to finish.")
        return TaskRunResult(task, response, TaskOutcome.TIMED_OUT)

    monkeypatch.setattr(app, "run_customer_task", timed_out)
    submit(page, "time out safely")

    expect(page.locator("#echo-status [role='alert']")).to_contain_text("too long to finish")
    expect(page.locator("#echo-message textarea")).to_have_value("time out safely")
    expect(page.locator("#echo-retry")).to_be_visible()
