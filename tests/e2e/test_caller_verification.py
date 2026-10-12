"""Browser journey for caller account verification and the ended session."""

from __future__ import annotations

import pytest
from agents.tool_context import ToolContext
from playwright.sync_api import expect

from src import app
from src.accounts import CallerSession
from src.task_agents import ConversationResponse, TaskAgentResult
from src.tools import TaskToolLedger
from src.task_runtime import (
    SESSION_ENDED_MESSAGE,
    TaskOutcome,
    TaskRunResult,
    TaskState,
    TaskStatus,
)
from test_echo_chat import browser_runtime_available, echo_url, submit  # noqa: F401

pytestmark = pytest.mark.e2e


@pytest.mark.parametrize("viewport", [{"width": 1280, "height": 900}, {"width": 390, "height": 844}])
@pytest.mark.parametrize("decision", ["yes", "no", "latest", "switch"])
def test_async_blocked_lookup_and_confirmation(page, echo_url, monkeypatch, viewport, decision, tmp_path) -> None:
    import asyncio
    from dataclasses import replace
    import json
    import threading
    from time import monotonic

    from agents import function_tool
    from agents.testing import ModelStep, ScriptedModel, assistant_message, function_call
    from src.accounts import lookup_account
    from src.observability import TaskName
    from src.task_agents import create_task_agents
    from src.task_runtime import run_customer_task
    from src.tools import TASK_TOOLS

    entered = threading.Event()
    release = asyncio.Event()
    loops = []
    dispatched = []

    @function_tool(name_override="account_lookup", failure_error_function=None)
    async def blocked_lookup(ctx: ToolContext[TaskToolLedger], account_number: str) -> str:
        await ctx.context.checkpoint("dispatch")
        ctx.context.authorize("account_lookup", account_number)
        step = f"r{ctx.context.control.revision}-lookup-{len(dispatched)}"
        ctx.context.claim(ctx.tool_call_id, step)
        dispatched.append(account_number)
        loops.append(asyncio.get_running_loop())
        entered.set()
        await release.wait()
        ctx.context.caller, outcome = lookup_account(ctx.context.caller, account_number)
        ctx.context.facts = replace(ctx.context.facts, lookup=outcome)
        ctx.context.complete(step, "Account found.")
        await ctx.context.checkpoint("committed")
        return "Account found."

    def output(value):
        return ModelStep(output=[assistant_message(json.dumps(value))])

    manager = [
        output({"action": "task", "task_name": TaskName.CUSTOMER_ACCOUNT, "detail_kind": "account_number"}),
        ModelStep(output=[function_call("delegate_to_task_agent", {"input": "Account 123"}, call_id="original-delegate")]),
        output({"action": "switch", "task_name": TaskName.CURRENT_TIME, "source_sequence": 3} if decision == "switch" else {"action": "correction", "detail_kind": "account_number", "value": "456", "source_sequence": 3}),
    ]
    if decision == "latest":
        manager.append(output({"action": "correction", "detail_kind": "account_number", "value": "123", "source_sequence": 5}))
    specialist = [ModelStep(output=[function_call("account_lookup", {"account_number": "123"}, call_id="original-lookup")])]
    if decision != "no":
        target = "123" if decision == "latest" else "456"
        manager.append(ModelStep(output=[function_call("delegate_to_task_agent", {"input": "Current time" if decision == "switch" else "Account " + target}, call_id="new-delegate")]))
        specialist.append(ModelStep(output=[function_call("getCurrentDateTimeIso" if decision == "switch" else "account_lookup", {} if decision == "switch" else {"account_number": target}, call_id="new-capability")]))
    manager.append(output({"status": "completed" if decision == "switch" else "clarification_required", "message": "FORBIDDEN-PROSE"}))
    specialist.append(output({"status": "completed", "summary": "Done."}))
    agents = create_task_agents(conversation_model=ScriptedModel(manager), task_model=ScriptedModel(specialist), task_tools=[blocked_lookup, TASK_TOOLS[0]])

    async def boundary(text, history, **kwargs):
        return await run_customer_task(text, history, agents=agents, **kwargs)

    monkeypatch.setattr(app, "run_customer_task", boundary)
    page.set_viewport_size(viewport)
    page.goto(echo_url)
    conversation = page.locator("#echo-conversation")
    try:
        submit(page, "Account 123")
        assert entered.wait(2)
        expect(page.locator("#echo-send")).to_be_enabled()
        started = monotonic()
        submit(page, "Current time" if decision == "switch" else "Account 456")
        expect(conversation).to_contain_text("Current time" if decision == "switch" else "Account 456", timeout=1000)
        elapsed = monotonic() - started
        assert elapsed < 1.0
        assert dispatched == ["123"]
        expect(conversation.locator("[role='log']")).to_contain_text("working")
        loops[0].call_soon_threadsafe(release.set)
        expect(conversation).to_contain_text("Please reply Yes or No.")
        expect(conversation).not_to_contain_text("What is your zip code?")
        page.locator("#echo-message textarea").fill("unsent typing")
        expect(page.locator("#echo-message textarea")).to_have_value("unsent typing")
        if decision == "latest":
            submit(page, "Account 123")
            expect(conversation).to_contain_text("Change the account from 123 to 123?")
            assert dispatched == ["123"]
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        page.screenshot(path=str(tmp_path / f"async-confirmation-{decision}-{viewport['width']}.png"), full_page=True)
        submit(page, "No" if decision == "no" else "Yes")
        expect(conversation).to_contain_text("Greenwich Mean Time" if decision == "switch" else "What is your zip code?")
        assert dispatched == (["123"] if decision in ("no", "switch") else ["123", "123" if decision == "latest" else "456"])
        expect(conversation).not_to_contain_text("FORBIDDEN-PROSE")
        assert page.evaluate("Object.keys(localStorage)") == []
        assert page.evaluate("Object.keys(sessionStorage)") == []
        page.screenshot(path=str(tmp_path / f"async-result-{decision}-{viewport['width']}.png"), full_page=True)
    finally:
        if loops:
            loops[0].call_soon_threadsafe(release.set)
        page.locator("#echo-new-conversation").click()


def test_second_wrong_zip_ends_the_session_until_reset(page, echo_url: str, monkeypatch) -> None:  # noqa: F811
    page.goto(echo_url)

    async def verification(
        text: str,
        _history: tuple,
        *,
        prior_task=None,
        caller=None,
        progress=None,
        control=None,
    ) -> TaskRunResult:
        assert progress is not None
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
    expect(page.locator("#echo-conversation [role='log']")).to_contain_text("session has ended")
    expect(page.locator("#echo-send")).to_be_disabled()
    expect(page.locator("#echo-new-conversation")).to_be_visible()
    assert page.evaluate("Object.keys(localStorage)") == []
    assert page.evaluate("Object.keys(sessionStorage)") == []

    page.locator("#echo-new-conversation").click()

    expect(page.locator("#echo-send")).to_be_enabled()
    expect(page.locator("#echo-conversation [role='log']")).to_have_text("")


@pytest.mark.parametrize("viewport", [{"width": 1280, "height": 900}, {"width": 390, "height": 844}])
def test_catalog_refusal_preserves_verification_on_desktop_and_mobile(page, echo_url: str, monkeypatch, viewport, tmp_path) -> None:  # noqa: F811
    import json

    from agents.testing import ModelStep, ScriptedModel, assistant_message, function_call

    from src.catalog_policy import SCOPE_REFUSAL
    from src.task_agents import create_task_agents
    from src.task_runtime import run_customer_task
    from src.tools import TASK_TOOLS

    seen_sessions = []

    async def boundary(text, history, **kwargs):
        if text == "What database are you using?":
            route = {"action": "decline", "task_name": None, "detail_kind": "none", "decline_remainder": False}
            steps = [ModelStep(output=[assistant_message(json.dumps(route))])]
            specialist = []
        else:
            is_zip = text == "12345"
            route = {
                "action": "continuation" if is_zip else "task",
                "task_name": None if is_zip else "Retrieve customer account",
                "detail_kind": "zip_code" if is_zip else "account_number",
                "decline_remainder": False,
            }
            steps = [
                ModelStep(output=[assistant_message(json.dumps(route))]),
                ModelStep(output=[function_call("delegate_to_task_agent", {"input": text}, call_id="zip-delegate" if is_zip else "account-delegate")]),
                ModelStep(output=[assistant_message(json.dumps({"status": "completed" if is_zip else "clarification_required", "message": "FORBIDDEN-MODEL-PROSE"}))]),
            ]
            specialist = [
                ModelStep(output=[function_call("verify_account_zip" if is_zip else "account_lookup", {"zip_code": "12345"} if is_zip else {"account_number": "123"}, call_id="zip-call" if is_zip else "account-call")]),
                ModelStep(output=[assistant_message('{"status":"completed","summary":"Done."}')]),
            ]
        agents = create_task_agents(conversation_model=ScriptedModel(steps), task_model=ScriptedModel(specialist), task_tools=TASK_TOOLS)
        result = await run_customer_task(text, history, agents=agents, **kwargs)
        seen_sessions.append(result.task.caller)
        return result

    monkeypatch.setattr(app, "run_customer_task", boundary)
    page.set_viewport_size(viewport)
    page.goto(echo_url)
    submit(page, "My account is 123")
    expect(page.locator("#echo-conversation")).to_contain_text("What is your zip code?")
    submit(page, "What database are you using?")
    expect(page.locator("#echo-conversation")).to_contain_text(SCOPE_REFUSAL)
    expect(page.locator("#echo-status")).to_have_count(0)
    expect(page.locator("#echo-retry")).not_to_be_visible()
    expect(page.locator("#echo-send")).to_be_enabled()
    assert seen_sessions[0] == seen_sessions[1]
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.screenshot(path=str(tmp_path / f"catalog-refusal-{viewport['width']}.png"), full_page=True)
    submit(page, "12345")
    expect(page.locator("#echo-conversation")).to_contain_text("Your account is verified.")
    expect(page.locator("#echo-conversation")).not_to_contain_text("FORBIDDEN-MODEL-PROSE")
    assert page.evaluate("Object.keys(localStorage)") == []
    assert page.evaluate("Object.keys(sessionStorage)") == []
