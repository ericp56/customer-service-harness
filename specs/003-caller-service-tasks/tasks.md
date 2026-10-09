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
