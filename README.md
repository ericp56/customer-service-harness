# Customer Service Harness

A prototype, privacy-safe AI customer-service chat. Visitors can ask for bounded
tasks handled by a conversation assistant and a task specialist, with progress,
clarification and cancellation controls in one transient conversation.
Send remains available while work runs. Caller messages appear in receipt order;
answers and questions arrive independently. A correction, conversational cancel,
or catalog switch finishes the current capability and requires Yes/No confirmation
before further work. No continues from committed facts without repeating a lookup;
a newer correction replaces the proposal and needs fresh confirmation.
The public application executes only the three tasks in its catalog; approval
helpers remain internal harness examples, not public catalog work.

The prototype is intentionally limited: it has no accounts, databases,
transcripts, file uploads, or analytics. Message, task, and proposal context
exists only in transient server-side session state. Initial capabilities are the
existing date/time lookup and deterministic demo account verification. The caller tasks are the
current time (stated as Greenwich Mean Time), retrieving a customer account
(demo accounts 123 and 456, verified by zip code), and transferring to customer
support. A caller gets three account-number attempts and two zip attempts per
account; exhausting either ends the session until a new conversation starts.
No real customer records,
external business APIs, or write actions are enabled. Configure
`OPENAI_API_KEY` and `OPENAI_MODEL` before starting; optional `OPENAI_BASE_URL`
selects an OpenAI-compatible Responses service and `OPENAI_TIMEOUT_SECONDS`
defaults to 10. Optional `OPENAI_REASONING` accepts `none`, `minimal`, `low`,
`medium`, `high`, `xhigh`, or `max`; leave it unset or blank to use the provider
default. Unknown values are rejected as invalid configuration. The operator is
responsible for choosing an effort supported by the selected model. Active tasks
are limited to 60 seconds. Fixed progress messages appear in chat initially and
then at five-second samples only when wording changes while work is active. Progress
copy reflects the latest known activity, such as looking
up information or evaluating a result, without naming capabilities. It may include
an exact catalog task title only when validated; otherwise the existing fixed
fallback messages are used.

Unrelated questions (including coding, system design, websites, and this
application's technology or database) receive a fixed polite refusal, not a
general-purpose answer or an operational error. Human Customer Service remains
available for genuine service needs. A tool-free admission turn selects catalog
work before execution; task-specific tool permissions, input provenance checks,
and application-rendered replies prevent forged task labels or arbitrary model
prose from becoming service results. Admission shares the existing conversation
client and counts toward the eight-manager-turn and sixty-second active budgets.
Separable mixed requests complete catalog work and decline the unrelated part.
Diversions preserve paused verification and do not consume account/zip attempts;
starting another catalog task requires confirming the switch. Compatible early
details can advance without confirmation, but ZIP details cannot cross account
identity revisions. Confirmed identity changes invalidate old verification and
support-contact facts without refunding completed failed attempts.
Each message is limited to 4,096 Unicode code points, each conversation to 50
accepted caller messages and 100 assistant entries, and the pending inbox to 10.
Rejected/full input is retained. Retry references the accepted input without
duplicating history or completed capabilities. Exhausted budgets require reset.
One server-side worker per session gates dispatch and publication; one 250ms
subscriber renders changes without modifying the textbox. Confirmation waits
pause active time. Hard Cancel stops immediately; reset, unload and session expiry
invalidate late results and clear transient state. Capacity is 50 active sessions.
Retired synchronous app callbacks fail closed without calling a provider.
Natural-language admission is probabilistic; the deterministic capability/output
boundary reduces impact but does not claim complete prompt-injection immunity.

Operational diagnostics are emitted as privacy-safe UTC JSON Lines on stdout for an external
collector. The application does not retain logs; records never include chat content, credentials,
model-service URLs, prompts, tool outputs, approval proposals, or provider payloads.
Only a validated account number may appear; zip codes and other PII never do.
Each model call also emits one `model_call` line with the agent role, call sequence,
`duration_ms`, token counts, outcome (`success`, `timeout`, `error`, `canceled`), and
response shape, sharing a random `task_id` with the task's outcome line.
Model-call records also include a fixed `task_state` snapshot with task status,
active and remaining milliseconds, manager turns, capability/completed-step
counts, approval state, verification attempt counts, and verification/session-
ended flags. A `task_outcome` line records the same safe snapshot once for each
caller-processing batch or lifecycle decision, including clarification, failure, timeout, and
cancellation. These records never include account or zip values, task text,
proposals, results, or capability identifiers.
Catalog completions include `task_name` with the exact catalog title, such as
`Retrieve the current time`. Names are validated against a fixed catalog enum;
non-catalog requests never generate catalog completion records. Clarification preserves the parent task
name, and known names also appear on `task_outcome` records.
Standalone refusals/help use the existing fixed `rejected` diagnostic outcome,
omit task/account identifiers, and offer no Retry. No routing reason or content
is logged.
Timing records use fixed step names (`model_request`, `date_time_tool`, and `chat_submission`) and
non-negative `duration_ms` values to identify slow blocking work without exposing request data.
Agents SDK tracing and durable agent sessions are disabled.

## Getting Started

### Prerequisites

- Python 3.14
- A modern web browser

Create an isolated environment and install the application with development
tools:

```sh
python3.14 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
playwright install chromium
```

Start the local application:

```sh
python -m src.app
```

Open the local URL printed by the application, normally
<http://127.0.0.1:7860>.

## Testing and Validation

Run the complete local test suite:

```sh
pytest
```

The suite includes unit, integration, and Playwright browser tests. The
[agent task validation quickstart](specs/002-agent-assisted-tasks/quickstart.md)
describes manual checks, privacy-diagnostics inspection, and the optional k6
release-candidate load test. k6 is intentionally an external prerequisite,
not a Python dependency. The original [AI integration quickstart](specs/001-ai-chat-integration/quickstart.md)
documents the provider configuration and date/time capability baseline.
The [catalog boundary quickstart](specs/003-caller-service-tasks/quickstart.md)
covers fixed refusals, permitted task execution and verification continuation.
The [async conversation validation guide](specs/005-async-conversation/quickstart.md)
records blocked-tool desktop/mobile checks, Yes/No/replacement/switch coverage,
session cleanup, measured coordinator capacity and remaining release gates.
Normal tests use scripted model/tool boundaries; optional real-provider red-team
checks are a separate deployment validation and never require content logging.

## Repository Guide

| Path | Purpose |
| --- | --- |
| `src/` | Gradio app, transient task state, agent roles, strict tools, OpenAI adapter, and privacy-safe diagnostics |
| `tests/` | Unit, integration, and browser end-to-end tests |
| `load/` | k6 release-candidate load scenario |
| `specs/001-ai-chat-integration/` | Feature specification, architecture plan, tasks, contracts, and validation guide |
| `specs/002-agent-assisted-tasks/` | Agent-task specification, architecture, task model, UI contract, and validation guide |
| `specs/005-async-conversation/` | Interruptible ingress, confirmation, lifecycle, compatibility and validation contracts |
| `.specify/` | Spec Kit project configuration and constitution |

## Contributing with Spec Kit

This repository is maintained with [Spec Kit](https://github.com/github/spec-kit).
Feature work begins with an implementation-independent specification and keeps
the resulting planning artifacts under `specs/`. The project constitution in
`.specify/memory/constitution.md` defines the repository's quality, privacy,
testing, and performance expectations.

For a new feature, use the Spec Kit workflow:

1. `/speckit-specify` to create or refine the feature specification.
2. `/speckit-plan` to select the architecture and implementation approach.
3. `/speckit-tasks` to create dependency-ordered implementation tasks.
4. `/speckit-analyze` to check the specification, plan, and tasks for gaps.
5. `/speckit-implement` to execute the approved task plan.

Keep specifications and task plans aligned with code changes, and use
`/speckit-clarify` or `/speckit-checklist` when requirements need further
review before implementation.

## License

This project is licensed under the [MIT License](LICENSE).
