from __future__ import annotations

from agents.testing import ModelStep, ScriptedModel, assistant_message, function_call

from src.accounts import CallerSession
from src.task_agents import TaskAgents, create_task_agents
from src.task_runtime import SESSION_ENDED_MESSAGE, TaskOutcome, TaskStatus, run_customer_task
from src.tools import TASK_TOOLS

_COMPLETED = (
    '{"status":"completed","summary":"Done.","question":null,"proposal":null}'
)
_NEEDS_INPUT = (
    '{"status":"clarification_required","summary":"Need more.",'
    '"question":"Please continue.","proposal":null}'
)


def _agents(
    tool_name: str,
    arguments: dict[str, str],
    specialist_result: str,
    reply: str,
    call_id: str = "tool-1",
) -> TaskAgents:
    return create_task_agents(
        conversation_model=ScriptedModel(
            [
                ModelStep(output=[function_call("delegate_to_task_agent", {"input": "Do the task."}, call_id="delegate-1")]),
                ModelStep(output=[assistant_message(reply)]),
            ]
        ),
        task_model=ScriptedModel(
            [
                ModelStep(output=[function_call(tool_name, arguments, call_id=call_id)]),
                ModelStep(output=[assistant_message(specialist_result)]),
            ]
        ),
        task_tools=TASK_TOOLS,
    )


def _completed_reply(message: str) -> str:
    return (
        f'{{"status":"completed","message":"{message}",'
        '"task_result":{"status":"completed","summary":"Done.","question":null,"proposal":null}}'
    )


def _clarification_reply(message: str) -> str:
    return (
        f'{{"status":"clarification_required","message":"{message}",'
        '"task_result":{"status":"clarification_required","summary":"Need more.",'
        '"question":"Please continue.","proposal":null}}'
    )


def test_agent_instructions_include_the_task_catalog_and_gmt_wording() -> None:
    agents = create_task_agents(
        conversation_model=ScriptedModel([]),
        task_model=ScriptedModel([]),
        task_tools=(),
    )

    for agent in (agents.conversation, agents.task):
        assert "Greenwich Mean Time" in agent.instructions
        assert "Retrieve customer account" in agent.instructions
        assert "Transfer to Customer Service" in agent.instructions


def test_time_task_calls_the_date_time_tool(run_async) -> None:
    agents = _agents("getCurrentDateTimeIso", {}, _COMPLETED, _completed_reply("It is noon Greenwich Mean Time."))

    result = run_async(run_customer_task("What time is it?", (), agents=agents))

    assert result.task.status is TaskStatus.COMPLETED
    assert result.task.completed_step_ids == ("current-date-time-1",)


def test_account_lookup_then_matching_zip_verifies_the_account(run_async) -> None:
    lookup_agents = _agents("account_lookup", {"account_number": "123"}, _NEEDS_INPUT, _clarification_reply("What is your zip code?"))

    first = run_async(run_customer_task("Check my account", (), agents=lookup_agents))

    assert first.task.status is TaskStatus.WAITING_FOR_CLARIFICATION
    assert first.task.caller.current_account == "123"
    assert first.task.caller.verified_account is None

    zip_agents = _agents(
        "verify_account_zip",
        {"zip_code": "12345"},
        _COMPLETED,
        _completed_reply("Thanks, you are verified."),
        call_id="tool-2",
    )

    second = run_async(run_customer_task("12345", (), agents=zip_agents, prior_task=first.task))

    assert second.task.status is TaskStatus.COMPLETED
    assert second.task.caller.verified_account == "123"


def test_unknown_account_counts_one_attempt_and_keeps_asking(run_async) -> None:
    agents = _agents("account_lookup", {"account_number": "999"}, _NEEDS_INPUT, _clarification_reply("I couldn't find it."))

    result = run_async(run_customer_task("Check my account", (), agents=agents))

    assert result.task.status is TaskStatus.WAITING_FOR_CLARIFICATION
    assert result.task.caller.account_attempts == 1
    assert result.task.caller.current_account is None


def test_third_unknown_account_ends_the_session_with_fixed_copy(run_async) -> None:
    agents = _agents("account_lookup", {"account_number": "999"}, _NEEDS_INPUT, _clarification_reply("Try again."))

    result = run_async(
        run_customer_task("999", (), agents=agents, caller=CallerSession(account_attempts=2))
    )

    assert result.outcome is TaskOutcome.SESSION_ENDED
    assert result.task.status is TaskStatus.SESSION_ENDED
    assert result.response.message == SESSION_ENDED_MESSAGE
    assert "session has ended" in result.response.message


def test_second_wrong_zip_ends_the_session_even_if_the_model_disagrees(run_async) -> None:
    agents = _agents(
        "verify_account_zip",
        {"zip_code": "99999"},
        _NEEDS_INPUT,
        _clarification_reply("Please try a third time."),
    )

    result = run_async(
        run_customer_task(
            "99999",
            (),
            agents=agents,
            caller=CallerSession(current_account="123", zip_attempts=1),
        )
    )

    assert result.outcome is TaskOutcome.SESSION_ENDED
    assert result.response.message == SESSION_ENDED_MESSAGE
    assert result.task.caller.verified_account is None


def test_first_wrong_zip_keeps_the_conversation_open(run_async) -> None:
    agents = _agents("verify_account_zip", {"zip_code": "99999"}, _NEEDS_INPUT, _clarification_reply("That didn't match."))

    result = run_async(
        run_customer_task("99999", (), agents=agents, caller=CallerSession(current_account="456"))
    )

    assert result.task.status is TaskStatus.WAITING_FOR_CLARIFICATION
    assert result.task.caller.zip_attempts == 1


def test_already_ended_session_does_not_call_the_model(run_async) -> None:
    agents = create_task_agents(
        conversation_model=ScriptedModel([]),
        task_model=ScriptedModel([]),
        task_tools=TASK_TOOLS,
    )

    result = run_async(
        run_customer_task("hello", (), agents=agents, caller=CallerSession(ended=True))
    )

    assert result.outcome is TaskOutcome.SESSION_ENDED
    assert result.response.message == SESSION_ENDED_MESSAGE


def test_transfer_gives_the_contact_for_the_verified_account(run_async) -> None:
    for account, contact in (("123", "800-555-1212"), ("456", "help@demo.com")):
        agents = _agents("getSupportContact", {}, _COMPLETED, _completed_reply("Here is the contact."))

        result = run_async(
            run_customer_task(
                "I need something else",
                (),
                agents=agents,
                caller=CallerSession(current_account=account, verified_account=account),
            )
        )

        assert result.task.completed_step_results == (f"Customer support contact: {contact}",)


def test_transfer_gives_no_contact_without_verification(run_async) -> None:
    agents = _agents("getSupportContact", {}, _COMPLETED, _completed_reply("I need to verify you first."))

    result = run_async(run_customer_task("I need something else", (), agents=agents))

    results = " ".join(result.task.completed_step_results)
    assert "not verified" in results
    assert "800-555-1212" not in results
    assert "help@demo.com" not in results


def test_tool_results_never_contain_a_stored_zip_code(run_async) -> None:
    for tool_name, arguments in (
        ("account_lookup", {"account_number": "123"}),
        ("verify_account_zip", {"zip_code": "99999"}),
    ):
        agents = _agents(tool_name, arguments, _NEEDS_INPUT, _clarification_reply("Continue."))

        result = run_async(
            run_customer_task(
                "go",
                (),
                agents=agents,
                caller=CallerSession(current_account="123"),
            )
        )

        joined = " ".join(result.task.completed_step_results)
        assert "12345" not in joined
        assert "54321" not in joined
