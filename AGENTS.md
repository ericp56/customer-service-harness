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
  accessible fixed chat progress/validation/recovery/approval messages, and the boundary from
  callbacks to transient task state and the task runtime.
- `src/chat.py` is the pure immutable state machine. It validates messages,
  enforces 4,096 Unicode code points, 50 accepted caller messages and 100 assistant entries,
  preserves failed input for retry, and stores tool records separately from
  displayable chat messages.
- `src/conversation_runtime.py` owns one transient server-side worker, an inbox
  of 10, versioned change confirmation, independent acceptance/publication and
  generation-guarded cancellation/reset/unload/expiry. No coordinator is serialized.
- `src/ai_client.py` owns validated environment configuration and bounded async
  OpenAI-compatible clients. Each agent role receives a distinct client/model
  object. Model attempts have a maximum 10-second timeout, no automatic retries,
  no server-side storage, and no agent tracing. Optional `OPENAI_REASONING`
  accepts `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, or `max`; unset or
  blank preserves provider defaults, while unknown values are invalid config.
- `src/task_agents.py` defines the distinct conversation manager and task
  specialist, their fixed prompts, and strict structured results. The manager
  evaluates results and chooses completion, clarification, approval, or recovery.
- `src/task_runtime.py` owns pure task lifecycle transitions, active-time
  accounting, turn/capability limits, cancellation, clarification resume, and
  one-shot simulated approval decisions.
- `src/tools.py` defines `getCurrentDateTimeIso`, deterministic synthetic customer-service lookups, verified profile/case reads, and field-scoped proposal capabilities. Schemas are strict and server-owned. Approved profile/case mutations affect only the coordinator's transient `DemoData`; the synthetic card alias is not payment data and there are no external side effects.
- `src/accounts.py` owns the hard-coded demo accounts and the pure caller
  verification rules (three account-number attempts, two zip attempts per
  account, session end, support-contact choice). The model only reaches
  verification through the `account_lookup`, `verify_account_zip`, and
  `getSupportContact` tools and never sees a stored zip code. `src/customer_data.py`
  owns deterministic session-local profiles/cases and validated mutations;
  `Retrieve Account` exposes only favorite color, preferred name, and demo-card-on-file
  status. `Update Account` and every case write require separate explicit approval
  before commit. No real card data is accepted. The task catalog is
  `src/prompts/task_catalog.md`; a "caller" is the user who starts the conversation.
- `src/observability.py` emits privacy-safe UTC JSON Lines to stdout and keeps
  bounded, in-process aggregate diagnostics only.
- `src/model_diagnostics.py` emits one content-free `model_call` line per model
  call (role, sequence, `duration_ms`, token counts, outcome, response shape)
  through SDK lifecycle hooks, tied to its task outcome by a random `task_id`.
  Call lines include only the explicit task-state snapshot allowlist; one
  `task_outcome` line records the final caller-turn status and safe snapshot.

The public path is: short Gradio ingress -> ordered caller event/inbox -> one
bounded task worker -> committed-step reconciliation -> independent publication ->
250ms subscriber. Send stays enabled while active. Only browser ingress clears
submitted text; accepted acknowledgements and subscribers never erase later typing.
Fixed progress is emitted as accessible assistant chat entries initially and then
at five-second samples only when the displayed wording changes; optional progress
is suppressed from 90 assistant entries onward. Validation, capacity, and recovery
notices also appear in chat while rejected input remains unaccepted. Notices count
within the 100-assistant-entry bound and are excluded from model context and
diagnostics. No separate visible status component is used. Clarification pauses the active-time budget
and resumes on customer input. Corrections/cancel/switch require versioned Yes/No
confirmation. No resumes committed facts; newer proposals require fresh confirmation.
Provider failures retain an accepted-event retry reference and committed facts;
exhausted budgets require reset. Legacy pair helpers are not the public UI path.

## Privacy, Reliability, and Performance Invariants

- Keep credentials and service configuration in process environment variables:
  `OPENAI_API_KEY`, `OPENAI_MODEL`, optional HTTPS `OPENAI_BASE_URL`, and
  optional `OPENAI_TIMEOUT_SECONDS` (maximum 10 seconds). Never expose or log
  their values.
- Never place chat content, prompts, model output, tool output, call IDs,
  provider payloads, URLs, or credentials in diagnostics, errors, test
  fixtures that reach the service, or browser persistence. Zip codes, names,
  and addresses are PII and must never be logged. The one exception is a
  validated digits-only account number, which may appear in the optional
  `account_number` diagnostic field. A random, content-independent `task_id`
  (32 hex characters), fixed `model_call` fields, and these derived metrics may
  also appear: task status, active/remaining milliseconds, turn/capability/
  completed-step counts, approval-pending, account/zip attempt counts,
  account-verified, and session-ended flags. New progress/outcome records must
  never include account or zip values, model names, provider response IDs, or
  error text.
  `task_completed` and `task_outcome` records may include `task_name` only from
  the fixed `TaskName` enum matching the catalog titles; never arbitrary text.
- Diagnostics have fixed categories and allowlisted timing steps only:
  `model_request`, `date_time_tool`, and `chat_submission`. Preserve
  non-negative integer `duration_ms` values. `model_call` and `task_outcome`
  fields remain explicit allowlists; snapshots contain only fixed statuses,
  non-negative integer metrics, and booleans.
- Keep each model attempt bounded to 10 seconds with no automatic SDK retries.
  Bound active task work to 60 seconds and no more than eight manager turns
  per caller-processing batch, including reconciliation. Confirmation waits are
  excluded from active time; same-task corrections retain the remaining budget.
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

