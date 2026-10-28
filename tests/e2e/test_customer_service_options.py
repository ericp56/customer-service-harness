"""Browser journeys for transient account settings and support cases."""

from __future__ import annotations

import json

import pytest
from agents.testing import ModelStep, ScriptedModel, assistant_message, function_call
from playwright.sync_api import expect

from src import app
from src.accounts import CallerSession
from src.observability import TaskName
from src.task_agents import ConversationResponse, create_task_agents
from src.task_runtime import TaskOutcome, TaskRunResult, TaskState, TaskStatus, run_customer_task
from src.tools import TASK_TOOLS
from test_echo_chat import browser_runtime_available, echo_url, submit  # noqa: F401,F811


pytestmark = pytest.mark.e2e


def _agents(task_name: TaskName, tool_name: str, arguments: dict[str, str], *, writes: bool):
    response_status = "approval_required" if writes else "completed"
    route = {
        "action": "task",
        "task_name": task_name.value,
        "detail_kind": "none",
        "decline_remainder": False,
    }
    conversation = ScriptedModel([
        ModelStep(output=[assistant_message(json.dumps(route))]),
        ModelStep(output=[function_call(
            "delegate_to_task_agent", {"input": "Complete the requested catalog operation."},
            call_id="e2e-delegate",
        )]),
        ModelStep(output=[assistant_message(json.dumps({
            "status": response_status,
            "message": "UNTRUSTED-MODEL-COPY",
        }))]),
    ])
    specialist = ScriptedModel([
        ModelStep(output=[function_call(tool_name, arguments, call_id="e2e-capability")]),
        ModelStep(output=[assistant_message(json.dumps({
            "status": response_status,
            "summary": "Operation returned.",
            "question": None,
            "proposal": "untrusted proposal",
        }))]),
    ])
    return create_task_agents(
        conversation_model=conversation,
        task_model=specialist,
        task_tools=TASK_TOOLS,
    )


@pytest.mark.parametrize("viewport", [{"width": 1280, "height": 900}, {"width": 390, "height": 844}])
def test_account_settings_and_case_lifecycle(page, echo_url: str, monkeypatch, viewport) -> None:  # noqa: F811
    operations = {
        "Retrieve my settings": (
            TaskName.RETRIEVE_ACCOUNT, "retrieveAccountProfile", {}, False,
        ),
        "Change favorite color to red": (
            TaskName.UPDATE_ACCOUNT, "proposeFavoriteColorUpdate", {"favorite_color": "red"}, True,
        ),
        "Change preferred name to Casey": (
            TaskName.UPDATE_ACCOUNT, "proposePreferredNameUpdate", {"preferred_name": "Casey"}, True,
        ),
        "save the demo card": (
            TaskName.UPDATE_ACCOUNT, "proposeDemoCardToggle", {"action": "save"}, True,
        ),
        "remove the demo card": (
            TaskName.UPDATE_ACCOUNT, "proposeDemoCardToggle", {"action": "remove"}, True,
        ),
        "List my open cases": (
            TaskName.LIST_OPEN_CASES, "listOpenCases", {}, False,
        ),
        "Open a case: Demo issue": (
            TaskName.OPEN_SUPPORT_CASE, "proposeOpenSupportCase", {"description": "Demo issue"}, True,
        ),
        "Follow up CASE-1003: Still delayed": (
            TaskName.FOLLOW_UP_CASE,
            "proposeCaseFollowUp",
            {"case_number": "CASE-1003", "follow_up": "Still delayed"},
            True,
        ),
        "Close CASE-1003": (
            TaskName.CLOSE_SUPPORT_CASE, "proposeCaseClosure", {"case_number": "CASE-1003"}, True,
        ),
        "Close CASE-1001": (
            TaskName.CLOSE_SUPPORT_CASE, "proposeCaseClosure", {"case_number": "CASE-1001"}, True,
        ),
    }

    async def deterministic_boundary(text: str, history: tuple, **kwargs) -> TaskRunResult:
        if text == "Verify the demo account":
            caller = CallerSession(current_account="123", verified_account="123")
            return TaskRunResult(
                TaskState(text, TaskStatus.COMPLETED, 0.01, None, caller=caller),
                ConversationResponse(status="completed", message="Your account is verified."),
                TaskOutcome.COMPLETED,
            )
        task_name, tool_name, arguments, writes = operations[text]
        return await run_customer_task(
            text,
            history,
            agents=_agents(task_name, tool_name, arguments, writes=writes),
            **kwargs,
        )

    monkeypatch.setattr(app, "run_customer_task", deterministic_boundary)
    page.set_viewport_size(viewport)
    page.goto(echo_url)
    conversation = page.locator("#echo-conversation")

    submit(page, "Verify the demo account")
    expect(conversation).to_contain_text("Your account is verified.")
    submit(page, "Retrieve my settings")
    expect(conversation).to_contain_text("Favorite color: blue. Preferred name: Alex. Demo card on file: no.")
    expect(conversation).not_to_contain_text("12345")

    submit(page, "Change favorite color to red")
    expect(conversation).to_contain_text("Please approve changing your favorite color to red.")
    expect(page.locator("#echo-approve-task")).to_be_visible()
    page.locator("#echo-approve-task").click()
    expect(conversation).to_contain_text("Your favorite color is now red.")

    submit(page, "Change preferred name to Casey")
    expect(conversation).to_contain_text("Please approve changing your preferred name to Casey.")
    page.locator("#echo-approve-task").click()
    expect(conversation).to_contain_text("Your preferred name is now Casey.")

    submit(page, "save the demo card")
    expect(conversation).to_contain_text("Please approve saving the synthetic demo card on file.")
    page.locator("#echo-approve-task").click()
    expect(conversation).to_contain_text("The synthetic demo card is now saved on your account.")

    submit(page, "Retrieve my settings")
    expect(conversation).to_contain_text("Favorite color: red. Preferred name: Casey. Demo card on file: yes.")

    submit(page, "remove the demo card")
    expect(conversation).to_contain_text("Please approve removing the synthetic demo card on file.")
    page.locator("#echo-approve-task").click()
    expect(conversation).to_contain_text("The synthetic demo card has been removed from your account.")
    submit(page, "List my open cases")
    expect(conversation).to_contain_text("CASE-1001: Delivery status question")
    expect(conversation).not_to_contain_text("CASE-1002: Service appointment question")

    submit(page, "Open a case: Demo issue")
    expect(conversation).to_contain_text("Please approve opening a support case: Demo issue.")
    page.locator("#echo-approve-task").click()
    expect(conversation).to_contain_text("Your support case CASE-1003 is open.")

    submit(page, "Follow up CASE-1003: Still delayed")
    expect(conversation).to_contain_text("Please approve adding this follow-up to case CASE-1003: Still delayed.")
    page.locator("#echo-approve-task").click()
    expect(conversation).to_contain_text("Your follow-up was added to case CASE-1003.")

    submit(page, "Close CASE-1003")
    expect(conversation).to_contain_text("Please approve closing case CASE-1003.")
    page.locator("#echo-approve-task").click()
    expect(conversation).to_contain_text("Case CASE-1003 is closed.")

    submit(page, "Close CASE-1001")
    expect(conversation).to_contain_text("Please approve closing case CASE-1001.")
    page.locator("#echo-approve-task").click()
    expect(conversation).to_contain_text("Case CASE-1001 is closed.")

    submit(page, "List my open cases")
    expect(conversation).to_contain_text("You have no open support cases.")

    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    assert page.evaluate("Object.keys(localStorage)") == []
    assert page.evaluate("Object.keys(sessionStorage)") == []


def test_foreign_case_target_is_rejected_in_browser(page, echo_url: str, monkeypatch) -> None:
    task_name, tool_name, arguments, _writes = (
        TaskName.FOLLOW_UP_CASE,
        "proposeCaseFollowUp",
        {"case_number": "CASE-1002", "follow_up": "Please check this"},
        True,
    )

    async def deterministic_boundary(text: str, history: tuple, **kwargs) -> TaskRunResult:
        if text == "Verify the demo account":
            caller = CallerSession(current_account="123", verified_account="123")
            return TaskRunResult(
                TaskState(text, TaskStatus.COMPLETED, 0.01, None, caller=caller),
                ConversationResponse(status="completed", message="Your account is verified."),
                TaskOutcome.COMPLETED,
            )
        return await run_customer_task(
            text,
            history,
            agents=_agents(task_name, tool_name, arguments, writes=True),
            **kwargs,
        )

    monkeypatch.setattr(app, "run_customer_task", deterministic_boundary)
    page.goto(echo_url)
    conversation = page.locator("#echo-conversation")

    submit(page, "Verify the demo account")
    expect(conversation).to_contain_text("Your account is verified.")
    submit(page, "Follow up CASE-1002: Please check this")

    expect(conversation).to_contain_text("The task couldn't be completed. You can try again.")
    expect(page.locator("#echo-approve-task")).to_be_hidden()
    expect(conversation).not_to_contain_text("Your follow-up was added to case CASE-1002.")
    assert page.evaluate("Object.keys(localStorage)") == []
    assert page.evaluate("Object.keys(sessionStorage)") == []