import asyncio
import json

from agents import RunConfig, Runner
from agents.testing import ModelStep, ScriptedModel, assistant_message, function_call

from src.task_agents import ConversationResponse, create_task_agents


def test_task_names_match_catalog_and_reject_arbitrary_text() -> None:
    from pathlib import Path

    import pytest
    from pydantic import ValidationError

    from src.observability import TaskName
    from src.task_agents import TaskAgentResult

    catalog = Path("src/prompts/task_catalog.md").read_text(encoding="utf-8")
    titles = [line.removeprefix("## Task - ") for line in catalog.splitlines() if line.startswith("## Task - ")]
    assert {name.value for name in TaskName} == set(titles)
    for title in titles:
        result = ConversationResponse.model_validate_json(
            json.dumps({"status": "completed", "message": "Done.", "task_name": title})
        )
        assert result.task_name.value == title
    with pytest.raises(ValidationError):
        TaskAgentResult.model_validate_json(
            '{"status":"completed","summary":"Done.","task_name":"PRIVATE-TEXT"}'
        )


def test_conversation_role_delegates_to_separate_task_agent(run_async) -> None:
    conversation_model = ScriptedModel(
        [
            ModelStep(
                output=[
                    function_call(
                        "delegate_to_task_agent",
                        {"input": "Find the synthetic service hours."},
                        call_id="delegate-1",
                    )
                ]
            ),
            ModelStep(
                output=[
                    assistant_message(
                        '{"status":"completed","message":"The service is open weekdays."}'
                    )
                ]
            ),
        ]
    )
    task_model = ScriptedModel(
        [
            ModelStep(
                output=[
                    assistant_message(
                        '{"status":"completed","summary":"Service hours: weekdays.",'
                        '"question":null,"proposal":null}'
                    )
                ]
            )
        ]
    )
    agents = create_task_agents(
        conversation_model=conversation_model,
        task_model=task_model,
        task_tools=(),
    )

    result = run_async(
        Runner.run(
            agents.conversation,
            "What are the service hours?",
            run_config=RunConfig(tracing_disabled=True, trace_include_sensitive_data=False),
            max_turns=4,
        )
    )

    assert agents.conversation is not agents.task
    assert isinstance(result.final_output, ConversationResponse)
    assert result.final_output.status == "completed"
    assert result.final_output.message == "The service is open weekdays."
    assert [item.type for item in result.new_items] == [
        "tool_call_item",
        "tool_call_output_item",
        "message_output_item",
    ]
    assert isinstance(agents.task.output_type, type)
    assert "\"status\":\"completed\"" in result.new_items[1].output
    assert not agents.conversation.tools[0].name.startswith("get_")


def test_nested_progress_hooks_track_lookup_and_validated_result_name(run_async) -> None:
    from agents import function_tool
    from agents.tool_context import ToolContext

    from src.observability import TaskName
    from src.task_agents import TaskProgressHooks
    from src.tools import TaskActivity, TaskProgress, TaskToolLedger

    lookup_started = asyncio.Event()
    release_lookup = asyncio.Event()
    evaluation_started = asyncio.Event()

    class ObservedProgress(TaskProgress):
        def set(self, activity: TaskActivity, task_name: TaskName | None = None) -> None:
            super().set(activity, task_name)
            if activity is TaskActivity.EVALUATING_RESULT:
                evaluation_started.set()

    @function_tool(name_override="getCurrentDateTimeIso")
    async def held_time(tool_context: ToolContext[TaskToolLedger]) -> str:
        tool_context.context.claim(tool_context.tool_call_id, "current-date-time-1")
        lookup_started.set()
        await release_lookup.wait()
        result = "2026-10-11T12:00:00+00:00"
        tool_context.context.complete("current-date-time-1", result)
        return result

    async def scenario() -> None:
        progress = ObservedProgress()
        ledger = TaskToolLedger(progress=progress)
        agents = create_task_agents(
            conversation_model=ScriptedModel(
                [
                    ModelStep(
                        output=[
                            function_call(
                                "delegate_to_task_agent",
                                {"input": "Get the current time."},
                                call_id="delegate-progress",
                            )
                        ]
                    ),
                    ModelStep(
                        output=[
                            assistant_message(
                                '{"status":"completed","message":"It is noon."}'
                            )
                        ]
                    ),
                ]
            ),
            task_model=ScriptedModel(
                [
                    ModelStep(
                        output=[
                            function_call(
                                "getCurrentDateTimeIso", {}, call_id="date-progress"
                            )
                        ]
                    ),
                    ModelStep(
                        output=[
                            assistant_message(
                                '{"status":"completed","summary":"The current time is noon.",'
                                '"question":null,"proposal":null,'
                                '"task_name":"Retrieve the current time"}'
                            )
                        ]
                    ),
                ]
            ),
            task_tools=(held_time,),
        )
        runner = asyncio.create_task(
            Runner.run(
                agents.conversation,
                "What time is it?",
                context=ledger,
                run_config=RunConfig(tracing_disabled=True, trace_include_sensitive_data=False),
                max_turns=4,
                hooks=TaskProgressHooks("conversation"),
            )
        )

        await asyncio.wait_for(lookup_started.wait(), timeout=1)
        assert ledger.progress is progress
        assert progress.activity is TaskActivity.LOOKING_UP_INFORMATION
        release_lookup.set()
        await asyncio.wait_for(evaluation_started.wait(), timeout=1)
        assert progress.task_name is TaskName.CURRENT_TIME
        assert progress.activity is TaskActivity.EVALUATING_RESULT
        await runner

    run_async(scenario())