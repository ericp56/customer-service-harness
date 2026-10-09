"""Browser journey for caller account verification and the ended session."""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from src import app
from src.accounts import CallerSession
from src.task_agents import ConversationResponse, TaskAgentResult
from src.task_runtime import (
    SESSION_ENDED_MESSAGE,
    TaskOutcome,
    TaskRunResult,
    TaskState,
    TaskStatus,
)
from test_echo_chat import browser_runtime_available, echo_url, submit  # noqa: F401

pytestmark = pytest.mark.e2e


def test_second_wrong_zip_ends_the_session_until_reset(page, echo_url: str, monkeypatch) -> None:  # noqa: F811
    page.goto(echo_url)

    async def verification(text: str, _history: tuple, *, prior_task=None, caller=None) -> TaskRunResult:
        if prior_task is None:
            session = CallerSession(current_account="123")
        else:
            session = CallerSession(current_account="123", zip_attempts=1) if text == "99999" else prior_task.caller
        if text == "11111":
            session = CallerSession(current_account="123", zip_attempts=2, ended=True)
            task = TaskState(text, TaskStatus.SESSION_ENDED, 1.0, None, caller=session)
            response = ConversationResponse(status="session_ended", message=SESSION_ENDED_MESSAGE)
            return TaskRunResult(task, response, TaskOutcome.SESSION_ENDED)
        task = TaskState(
            text,
            TaskStatus.WAITING_FOR_CLARIFICATION,
            1.0,
            None,
            turn_count=1,
            caller=session,
        )
        response = ConversationResponse(
            status="clarification_required",
            message="What is your zip code?",
            task_result=TaskAgentResult(status="clarification_required", summary="", question="Zip?"),
        )
        return TaskRunResult(task, response, TaskOutcome.PAUSED)

    monkeypatch.setattr(app, "run_customer_task", verification)

    submit(page, "123")
    expect(page.locator("#echo-conversation")).to_contain_text("What is your zip code?")
    submit(page, "99999")
    expect(page.locator("#echo-conversation")).to_contain_text("99999")
    submit(page, "11111")

    expect(page.locator("#echo-conversation")).to_contain_text("this session has ended")
    expect(page.locator("#echo-status [role='alert']")).to_contain_text("This session has ended.")
    expect(page.locator("#echo-send")).to_be_disabled()
    expect(page.locator("#echo-new-conversation")).to_be_visible()
    assert page.evaluate("Object.keys(localStorage)") == []
    assert page.evaluate("Object.keys(sessionStorage)") == []

    page.locator("#echo-new-conversation").click()

    expect(page.locator("#echo-send")).to_be_enabled()
    expect(page.locator("#echo-conversation [role='log']")).to_have_text("")
