"""Agent role definitions for transient customer task workflows."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Sequence

from agents import Agent, RunResult, set_tracing_disabled
from pydantic import BaseModel, ConfigDict

MAX_TASK_SPECIALIST_TURNS = 4
_PROMPT_DIRECTORY = Path(__file__).parent / "prompts"
set_tracing_disabled(True)


def _prompt(name: str) -> str:
    return (_PROMPT_DIRECTORY / name).read_text(encoding="utf-8").strip()


def _instructions(name: str) -> str:
    return f"{_prompt(name)}\n\nThe person you are helping is the caller.\n\n{_prompt('task_catalog.md')}"


class TaskAgentResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    status: Literal["completed", "clarification_required", "approval_required", "unsupported"]
    summary: str
    question: str | None = None
    proposal: str | None = None


class ConversationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    status: Literal["completed", "clarification_required", "approval_required", "unsupported", "failed", "session_ended"]
    message: str
    task_result: TaskAgentResult | None = None


async def _extract_task_result(result: RunResult[Any]) -> str:
    final_output = result.final_output
    if not isinstance(final_output, TaskAgentResult):
        raise TypeError("task specialist returned an invalid result")
    return final_output.model_dump_json()


@dataclass(frozen=True)
class TaskAgents:
    conversation: Agent[Any]
    task: Agent[Any]


def create_task_agents(
    *,
    conversation_model: Any,
    task_model: Any,
    task_tools: Sequence[Any],
) -> TaskAgents:
    task_agent = Agent(
        name="Customer task specialist",
        instructions=_instructions("task_executor.txt"),
        tools=list(task_tools),
        model=task_model,
        output_type=TaskAgentResult,
    )
    task_tool = task_agent.as_tool(
        tool_name="delegate_to_task_agent",
        tool_description="Complete one bounded task step using approved capabilities.",
        custom_output_extractor=_extract_task_result,
        max_turns=MAX_TASK_SPECIALIST_TURNS,
    )
    conversation_agent = Agent(
        name="Customer conversation assistant",
        instructions=_instructions("task_conversation.txt"),
        tools=[task_tool],
        model=conversation_model,
        output_type=ConversationResponse,
    )
    return TaskAgents(conversation=conversation_agent, task=task_agent)