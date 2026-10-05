# Repository Instructions

## Spec-Driven Delivery

This repository uses Spec Kit. Treat `.specify/memory/constitution.md` as the
governing policy for all changes.

For new features and material behavior changes, work in this order:

1. `/speckit-specify` — create or refine an implementation-independent feature
   specification under `specs/<feature>/`.
2. `/speckit-clarify` or `/speckit-checklist` — resolve underspecified
   requirements when needed.
3. `/speckit-plan` — document architecture, privacy, performance, rollout, and
   rollback decisions.
4. `/speckit-tasks` — produce dependency-ordered tasks.
5. `/speckit-analyze` — resolve cross-artifact gaps before implementation.
6. `/speckit-implement` — execute the approved tasks and keep `tasks.md`
   checkboxes current.

Before implementing, read the active feature's `spec.md`, `plan.md`,
`tasks.md`, and applicable contracts, data model, research, and quickstart
documents. Keep the artifacts aligned with implementation changes. Do not
invent product behavior that is not approved by the feature specification.

## Application Architecture

This is one Python 3.14 Gradio web application; it has no database, accounts,
browser persistence, transcript storage, uploads, analytics, or application
log store.

- `src/app.py` owns Gradio UI/event wiring, FastAPI health/readiness endpoints,
  accessible fixed status/progress/approval messages, and the boundary from
  callbacks to transient task state and the task runtime.
- `src/chat.py` is the pure immutable state machine. It validates messages,
  enforces 4,096 Unicode code points and 50 completed user/assistant pairs,
  preserves failed input for retry, and stores tool records separately from
  displayable chat messages.
- `src/ai_client.py` owns validated environment configuration and bounded async
  OpenAI-compatible clients. Each agent role receives a distinct client/model
  object. Model attempts have a maximum 10-second timeout, no automatic retries,
  no server-side storage, and no agent tracing.
- `src/task_agents.py` defines the distinct conversation manager and task
  specialist, their fixed prompts, and strict structured results. The manager
  evaluates results and chooses completion, clarification, approval, or recovery.
- `src/task_runtime.py` owns pure task lifecycle transitions, active-time
  accounting, turn/capability limits, cancellation, clarification resume, and
  one-shot simulated approval decisions.
- `src/tools.py` defines `getCurrentDateTimeIso` and deterministic synthetic
  read-only customer-service lookups. Schemas are strict and server-owned. The
  simulated consequential action is an in-memory no-op, not an external side effect.
- `src/observability.py` emits privacy-safe UTC JSON Lines to stdout and keeps
  bounded, in-process aggregate diagnostics only.

The successful submission path is: Gradio async event -> `begin_submission` ->
bounded task runtime -> `complete_submission` -> rendered display messages.
Progress is emitted in a separate accessible status component every five seconds
while active, never in chat history. Clarification pauses the active-time budget
and resumes on customer input. Provider/configuration failures go through
`fail_submission`, retain the pending input, and show fixed retry-safe status.

## Privacy, Reliability, and Performance Invariants

- Keep credentials and service configuration in process environment variables:
  `OPENAI_API_KEY`, `OPENAI_MODEL`, optional HTTPS `OPENAI_BASE_URL`, and
  optional `OPENAI_TIMEOUT_SECONDS` (maximum 10 seconds). Never expose or log
  their values.
- Never place chat content, prompts, model output, tool output, call IDs,
  provider payloads, URLs, or credentials in diagnostics, errors, test
  fixtures that reach the service, or browser persistence.
- Diagnostics have fixed categories and allowlisted timing steps only:
  `model_request`, `date_time_tool`, and `chat_submission`. Preserve
  non-negative integer `duration_ms` values.
- Keep each model attempt bounded to 10 seconds with no automatic SDK retries.
  Bound active task work to 60 seconds and no more than eight manager turns.
  Permit one strict capability call per model turn and disable parallel tool
  calls. Unknown, malformed, duplicate-call-ID, replayed-step, or unapproved
  capability calls are safe declared failures.
- Keep task/proposal state only in server-side transient Gradio state. Disable
  Agents SDK tracing, SDK sessions, provider-managed conversations, and
  serialized run-state transport. Progress is fixed application copy and stops
  while waiting for customer input or at a terminal task state.
- Preserve the Gradio privacy configuration: no analytics, sharing, feedback,
  uploads, rich content, or undocumented public API exposure. Render user and
  model text as text rather than trusted HTML.
- Customer-facing changes require clear accessible validation/recovery states,
  narrow automated coverage, and measurable responsiveness expectations in
  their specification.

## Code and Test Conventions

- Use Python 3.14 with `from __future__ import annotations`, explicit type
  annotations, frozen dataclasses for immutable domain values, and `StrEnum`
  for finite states/outcomes.
- Keep domain transitions pure and independently testable. Inject or
  monkeypatch the AI/agent boundary in tests; normal automated tests must use
  deterministic `ScriptedModel` and fake tool boundaries and must not call an
  external model provider.
- Put pure logic tests in `tests/unit/`, callback/boundary tests in
  `tests/integration/`, and browser journeys in `tests/e2e/`. Mark browser
  tests with `pytest.mark.e2e`.
- Test privacy as observable behavior: assert sensitive input is absent from
  diagnostics and browser storage, not merely that a helper was called.
- Preserve existing stable UI selector IDs (`echo-*`) and status/retry/reset
  behavior unless the active specification changes them.

## Commands

```sh
# Create the supported local environment.
python3.14 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
playwright install chromium

# Start the local application (requires OPENAI_API_KEY and OPENAI_MODEL).
python -m src.app

# Run the deterministic suite.
pytest

# Run one test or one test file.
pytest tests/unit/test_ai_client.py::test_reply_includes_dialog_and_tool_history
pytest tests/integration/test_app.py

# Run browser coverage after installing Chromium.
pytest -m e2e tests/e2e/test_echo_chat.py

# Run the release-candidate load scenario with k6 installed separately.
k6 run load/echo_load.js
```

