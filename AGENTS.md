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
  accessible fixed status messages, and the boundary from callbacks to state
  and the AI adapter.
- `src/chat.py` is the pure immutable state machine. It validates messages,
  enforces 4,096 Unicode code points and 50 completed user/assistant pairs,
  preserves failed input for retry, and stores tool records separately from
  displayable chat messages.
- `src/ai_client.py` owns validated environment configuration, the OpenAI
  Responses API boundary, complete active-session context serialization, and
  the bounded tool loop. Keep SDK/provider mechanics out of UI callbacks.
- `src/tools.py` defines the only permitted model tool:
  `getCurrentDateTimeIso`. Tool calls must be strict, argument-free, and
  server-owned.
- `src/observability.py` emits privacy-safe UTC JSON Lines to stdout and keeps
  bounded, in-process aggregate diagnostics only.

The successful submission path is: Gradio callback -> `begin_submission` ->
`generate_reply` -> `complete_submission` -> rendered display messages.
Provider/configuration failures go through `fail_submission`, retain the
pending input, and show the same fixed retry-safe status.

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
- Keep model calls bounded: 10-second timeout, no automatic SDK retries, and
  at most one tool round trip. Unknown, malformed, non-empty-argument, or
  repeated tool calls are safe declared failures.
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
  monkeypatch the AI boundary in tests; normal automated tests must use
  deterministic fakes and must not call an external model provider.
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

