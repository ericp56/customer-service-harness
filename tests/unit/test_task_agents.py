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