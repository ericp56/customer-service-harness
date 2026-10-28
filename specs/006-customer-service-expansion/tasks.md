# Tasks: Expanded Customer Service Options

**Input**: Design documents from `/specs/006-customer-service-expansion/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/customer-service-catalog.md`, and `quickstart.md`

**Tests**: Required by the constitution and feature specification. All tests use deterministic fake model and tool boundaries; no provider calls.

**Organization**: Tasks are grouped by user story. The shared synthetic data and mutation boundary must be complete before the story-specific catalog workflows.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel because it affects a different file and has no incomplete-task dependency.
- **[Story]**: User story traceability label.

## Phase 1: Setup

**Purpose**: No dependency or project scaffolding changes are required; preserve the current Python environment and test stack.

- [X] T001 Confirm existing Python 3.14, Gradio, Agents SDK and pytest setup in `pyproject.toml` and `AGENTS.md`; do not add dependencies.

---

## Phase 2: Foundational Data and Mutation Boundary

**Purpose**: Establish immutable session-local sample data, bounded transitions and one-shot approvals before exposing new catalog operations.

### Tests

- [X] T002 Add pure tests for deterministic account/case seed fixtures, field bounds, ownership isolation, unique case IDs, case limits, follow-up limits and open/closed transitions in `tests/unit/test_customer_data.py`.
- [X] T003 Add tests for one-shot mutation proposal approval/rejection, stale revision, replay, account mismatch, task generation mismatch, and no mutation before approval in `tests/unit/test_customer_data.py`.

### Implementation

- [X] T004 Implement frozen account-profile, demo-card, support-case, follow-up and conversation sample-data types plus deterministic seeds in `src/customer_data.py`.
- [X] T005 Implement pure validated profile/case transition functions in `src/customer_data.py`: favorite-color/name update, demo-card save/remove, open-case, list-open-cases, follow-up append and close-case. Enforce 20 cases, 10 follow-ups/case, 500 code points/description and update, 40 code points/preferred name, and the six fixed colors.
- [X] T006 Add a server-owned pending mutation value and one-shot version/revision-bound commit transition in `src/customer_data.py`; reject mismatched account, generation, proposal, target revision, closed/foreign target and duplicate commit.
- [X] T007 Add `DemoData` ownership to `SessionCoordinator` and reset/disposal paths in `src/conversation_runtime.py`; initialize a fresh deterministic snapshot for every new conversation without serializing it to browser state.
- [X] T008 Add unit/integration assertions that sample profiles, zip values, case text and pending mutation values do not appear in diagnostics or browser storage in `tests/integration/test_app.py` and `tests/unit/test_customer_data.py`.

**Checkpoint**: Pure transitions and server-side sample lifetime are tested independently; no public task can mutate state yet.

---

## Phase 3: User Story 1 - Retrieve and Update Account Settings (Priority: P1)

**Goal**: Verified callers can retrieve allowlisted profile data and explicitly approve bounded setting/card changes.

**Independent Test**: Verify a synthetic account, retrieve settings without zip disclosure, approve/reject a profile update, and save/remove only the fixed demo-card alias.

### Tests

- [X] T009 [P] [US1] Add strict-schema, capability-allowlist and application-rendered reply tests for profile retrieval/update and card toggles in `tests/unit/test_tools.py` and `tests/unit/test_caller_tasks.py`.
- [X] T010 [P] [US1] Add deterministic task tests proving no retrieval before verification, exact field allowlist, approval required for writes, and typed facts control success output in `tests/unit/test_caller_tasks.py`.
- [X] T011 [P] [US1] Add integration tests for approved, rejected, stale, replayed and superseded profile/card proposals in `tests/integration/test_caller_session.py`.

### Implementation

- [X] T012 [US1] Add fixed `TaskName` values and task-to-capability mapping for account retrieval/update in `src/observability.py` and `src/catalog_policy.py`; keep `Retrieve Account`/`Update Account` as user-facing workflow labels, not generic arbitrary-field tools.
- [X] T013 [US1] Add strict profile retrieval and field-scoped update/card-toggle capabilities to `src/tools.py`; require verified account, caller-provenance validation, and server-side proposal creation for writes.
- [X] T014 [US1] Extend typed catalog facts and deterministic reply rendering in `src/catalog_policy.py` so only validated favorite color, preferred name, and card status can be returned, never zip or free-form model prose.
- [X] T015 [US1] Add version-bound mutation approval and commit/reject handling to `src/conversation_runtime.py` and `src/task_runtime.py`, keeping write approval separate from existing correction/cancel/switch proposals.
- [X] T016 [US1] Add catalog route/task instructions for profile retrieval, field-specific updates and demo-card save/remove in `src/prompts/task_catalog.md`, `src/prompts/task_router.txt`, and `src/task_agents.py`.
- [X] T017 [US1] Add deterministic end-to-end account retrieval, favorite color/name update and synthetic card toggle journeys in `tests/e2e/test_customer_service_options.py`.

**Checkpoint**: Account settings are available only to the verified account; each update commits once only after explicit current approval.

---

## Phase 4: User Story 2 - Manage Support Cases (Priority: P1)

**Goal**: Verified callers can open cases, list their open cases, add follow-up and close open cases.

**Independent Test**: Verify ownership filtering and one complete approved open/list/follow-up/close sequence, including rejection of foreign and closed case mutations.

### Tests

- [X] T018 [P] [US2] Add strict capability and catalog result tests for open/list/follow-up/close, generated case numbers, empty states and ownership filtering in `tests/unit/test_tools.py` and `tests/unit/test_caller_tasks.py`.
- [X] T019 [P] [US2] Add integration tests for case mutation approval, case revision conflicts, foreign/unknown/closed case rejection, case-limit recovery and reset/expiry discard in `tests/integration/test_caller_session.py`.

### Implementation

- [X] T020 [US2] Add fixed case task names, allowlists and typed application-rendered case replies in `src/observability.py` and `src/catalog_policy.py`.
- [X] T021 [US2] Add strict list/open/follow-up/close capabilities to `src/tools.py`; derive owner only from verified server state, accept only caller-supplied bounded text, and prevent model-authored case IDs/ownership.
- [X] T022 [US2] Implement case flow prompts and structured task results, including selection clarification, open-case listing when needed, and offer to list after opening, in `src/prompts/task_catalog.md`, `src/prompts/task_router.txt`, and `src/task_agents.py`.
- [X] T023 [US2] Extend conversation runtime reconciliation so each case write is separately approved, revalidated and committed before success publication in `src/conversation_runtime.py` and `src/task_runtime.py`.
- [X] T024 [US2] Add browser journeys for open/list/follow-up/close, empty list, foreign target rejection, and mobile/desktop layout in `tests/e2e/test_customer_service_options.py`.

**Checkpoint**: Case operations stay within the verified account and every write is applied exactly once after approval.

---

## Phase 5: User Story 3 - Preserve Existing Customer-Service Tasks (Priority: P1)

**Goal**: Current-time lookup, account/zip verification and transfer to human support continue to work unchanged.

**Independent Test**: Run existing deterministic account task, caller verification browser, task-agent and human-support tests against the expanded catalog.

### Tests

- [X] T025 [P] [US3] Extend account/task regression tests for unchanged attempt limits, correction invalidation, zip non-disclosure, current-time wording and verified support contact selection in `tests/unit/test_accounts.py`, `tests/unit/test_caller_tasks.py`, and `tests/unit/test_tools.py`.
- [X] T026 [P] [US3] Extend browser verification and transfer journeys to assert existing behavior with the expanded help/catalog copy in `tests/e2e/test_caller_verification.py`.

### Implementation

- [X] T027 [US3] Update fixed catalog help/refusal, routing and task names to describe all groups while retaining unrelated-request refusal and genuine human-support routing in `src/catalog_policy.py`, `src/observability.py`, `src/prompts/task_catalog.md`, and `src/prompts/task_router.txt`.
- [X] T028 [US3] Verify every app submission path uses the expanded catalog boundary and that account correction, task switching, retry, cancellation and reset cannot carry stale sample data or pending mutation into a new identity in `src/conversation_runtime.py` and `src/app.py`.

**Checkpoint**: All legacy journeys pass with the expanded catalog and no verification bypass.

---

## Phase 6: Polish and Cross-Cutting Validation

**Purpose**: Document the contract and verify privacy, accessibility, responsiveness and full regression coverage.

- [X] T029 [P] Update `README.md`, `AGENTS.md`, `.github/copilot-instructions.md`, and feature quickstart to document transient sample data, new task groups, synthetic-only card alias, approval rules and explicit exclusions.
- [X] T030 [P] Add privacy assertions for case/profile/card content and fixed catalog task names in `tests/unit/test_model_diagnostics.py` and `tests/integration/test_caller_session.py`.
- [X] T031 Run focused unit/integration tests, then full deterministic `pytest`; run Chromium e2e journeys where available and record any environment limitation in `specs/006-customer-service-expansion/quickstart.md`.
- [X] T032 Check for and run the existing k6 scenario if available; k6 was unavailable, so the limitation is documented and no load measurements are claimed in `specs/006-customer-service-expansion/quickstart.md`.
- [X] T033 Review all functional requirements and acceptance scenarios against implementation/tests and update task checkboxes; `.specify/feature.json` already points to this active feature.

## Dependencies & Execution Order

### Phase Dependencies

- Setup is complete; no packages or project scaffolding are required.
- Foundational data and proposal work blocks catalog exposure.
- User Stories 1 and 2 depend on the foundational model and approval boundary. Their pure unit tests can be prepared independently after the foundational model contract is settled, but their runtime integration shares files and should proceed sequentially.
- User Story 3 compatibility checks follow catalog expansion to catch unintended legacy regressions.
- Polish requires all three stories.

### User Story Dependencies

```text
Foundation -> US1 (profile/card) -> US2 (cases) -> US3 (legacy compatibility) -> Polish
```

### Parallel Opportunities

- T002 and T003 share one test file and should be implemented sequentially.
- T009 and T010 can be prepared in separate test files once T004-T006 establish the model interface.
- T018 and T019 can be prepared independently after the case API is stable.
- T025 and T026 target separate unit and browser test files.
- T029 and T030 are independent documentation and diagnostics test tasks.

## Implementation Strategy

1. Complete and validate the pure per-conversation domain and one-shot mutation boundary.
2. Deliver account retrieval/update and demo-card toggles as the first usable slice.
3. Add support case workflows with separate approvals and ownership checks.
4. Re-run existing account, time and transfer journeys after the catalog changes.
5. Complete privacy, browser and load checks; no real card integration or persistent storage is introduced.

## Format Validation

Every task uses a checkbox, sequential T### ID, exact file path, and `[US#]` label in story phases. `[P]` is limited to tasks affecting independent files with no incomplete dependency.
