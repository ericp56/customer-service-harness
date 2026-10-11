# Tasks: Caller Service Tasks

**Input**: `specs/003-caller-service-tasks/spec.md` and `plan.md`

**Tests**: Required. Use deterministic fakes; no provider calls.

## Phase 1: Foundation

- [X] T001 [P] Write unit tests for the hard-coded accounts, three account-number attempts, two zip attempts, zip reset on a different known account, verified carry-over, and support-contact selection in `tests/unit/test_accounts.py`.
- [X] T002 Implement `src/accounts.py` with the accounts table, frozen `CallerSession`, and pure transitions.
- [X] T003 [P] Write tests that a validated account number is emitted and that a zip code or malformed value never is, in `tests/unit/test_observability.py`.
- [X] T004 Add the optional validated `account_number` field to `Diagnostics.record` in `src/observability.py`.

## Phase 2: User Story 1 - Retrieve the Current Time (P1)

- [X] T005 [US1] Add `src/prompts/task_catalog.md` with the three tasks and load it into both agent instructions in `src/task_agents.py`; reword the time guidance to "Greenwich Mean Time".
- [X] T006 [US1] Write a scripted-model test for the time task in `tests/unit/test_task_agents.py`.

## Phase 3: User Story 2 - Retrieve a Customer Account (P1)

- [X] T007 [P] [US2] Write tool tests (strict schema, no zip in results, call-ledger behavior) in `tests/unit/test_tools.py`.
- [X] T008 [US2] Add `account_lookup` and `verify_account_zip` tools and a `CallerSession` on the ledger in `src/tools.py`.
- [X] T009 [P] [US2] Write runtime tests for session carry-over, session end with fixed copy, and the per-message manager-turn budget in `tests/unit/test_task_runtime.py`.
- [X] T010 [US2] Add `SESSION_ENDED`, session carry-over, fixed end copy, and the per-message turn budget in `src/task_runtime.py`; update the aggregate-turn test to match.
- [X] T011 [P] [US2] Write integration tests for the blocked input, the ended message, and reset in `tests/integration/test_app.py`.
- [X] T012 [US2] Add the session-ended UI state, session carry-over between tasks, and account-number diagnostics in `src/app.py`.

## Phase 4: User Story 3 - Transfer to Customer Service (P2)

- [X] T013 [P] [US3] Write scripted-model tests for the transfer chain (contact by zip, no contact without verification) in `tests/unit/test_task_agents.py`.
- [X] T014 [US3] Add the `getSupportContact` tool in `src/tools.py`.

## Phase 5: Polish

- [X] T015 [P] Add a browser journey for account verification and the ended session in `tests/e2e/test_echo_chat.py`.
- [X] T016 Update `AGENTS.md`, `.github/copilot-instructions.md`, and `README.md` for the tasks, session end, and the account-number diagnostics exception.
- [X] T017 Run the full suite with `pytest` and `pytest -m e2e`, and confirm task checkboxes.

## Dependencies

T002 blocks T008, T010, and T014. T004 blocks T012. T008 and T010 block T012. T014 depends on T008.

## Phase 6: Catalog Boundary Foundation

- [X] T018 Refine feature 003 specification, plan, research, data model, contract, quickstart and requirements checklist for FR-016 through FR-022 in `specs/003-caller-service-tasks/`.
- [X] T019 Add negative output/routing and unauthorized capability regressions to `tests/unit/test_caller_tasks.py` and `tests/unit/test_tools.py`.

## Phase 7: User Story 4 - Stay Within the Catalog (P1)

- [X] T020 [US4] Define strict tool-free routing and catalog-only prompts in `src/task_agents.py` and `src/prompts/`; execute routing within existing budgets in `src/task_runtime.py`.
- [X] T021 [US4] Add pure fixed-response policy and typed transient capability facts in `src/catalog_policy.py` and task-scoped invocation checks in `src/tools.py`; keep verification rules in `src/accounts.py`.
- [X] T022 [US4] Enforce tool-backed results, fixed refusals/help and paused-task preservation in `src/task_runtime.py`, preserving diagnostics and progress hooks.
- [X] T023 [US4] Render refusals as normal dialogue and disable unrestricted legacy app callbacks in `src/app.py`; cover fixed status, continuation, no Retry and no completion diagnostics in `tests/integration/test_caller_session.py`.
- [X] T024 [US4] Add deterministic browser refusal/continuation/privacy journeys in `tests/e2e/test_caller_verification.py` and update existing fake-boundary fixtures for explicit routing in `tests/`.

## Phase 8: Hardening Verification

- [X] T025 Run focused boundary checks, full deterministic pytest suite and browser coverage; update `README.md` and task checkboxes with actual results.

T018 blocks T019-T025; T019 precedes T020-T022; T020 and T021 precede T022; T022 precedes T023; T023 precedes T024-T025. Independent unit and browser input matrices can be prepared in parallel, but shared runtime/tool contracts are sequential. MVP is fixed refusals with capability/output enforcement; do not ship a prompt-only intermediate stage.

## Hardening Validation Results (2026-10-11)

- Final full deterministic suite: `pytest -q --tb=short` -> 195 passed, 291 warnings, 23.76 seconds. Warnings are existing Gradio/pandas deprecations and the shared-port browser-fixture startup warning; no test failed.
- Desktop (1280x900) and mobile (390x844) browser refusal/verification journeys passed, with no horizontal overflow, no browser storage, no Retry, unchanged attempt state, and successful zip continuation. Temporary Playwright screenshots were inspected.
- Negative checks cover five unrelated examples, forged completion names/prose, malformed admission, poisoned tool text, wrong task/stage and invented arguments, batch rejection before dispatch, typed-fact retry reuse, mixed requests, fixed help, and paused-task switching. Existing diagnostics, timeout, cancellation and attempt-limit coverage passes.
- `git diff --check` passed. No automated external provider calls, new dependency or persistence. Real-provider classification/red-team accuracy remains an explicitly separate deployment check; deterministic tests verify policy boundaries, not immunity to every semantic attack.
