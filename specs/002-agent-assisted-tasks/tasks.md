# Tasks: Agent-Assisted Customer Tasks

**Input**: Design documents from `/specs/002-agent-assisted-tasks/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/task-chat-contract.md`, and `quickstart.md`

**Tests**: Tests are required by the project constitution and the feature spec. Write deterministic fake-boundary tests before implementation; no normal test may contact a model provider.

**Organization**: Tasks are grouped by user story, with shared state, provider, and Gradio lifecycle work completed first.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel because it affects a different file and has no incomplete-task dependency.
- **[Story]**: User story traceability label; omitted for setup, foundational, and polish tasks.

## Phase 1: Setup

**Purpose**: Add the selected bounded agent runtime without changing provider configuration semantics.

- [X] T001 Pin `openai-agents==0.23.1` in `pyproject.toml` and verify its dependency constraints resolve with Python 3.14 and the existing `openai==3.15.0`.

---

## Phase 2: Foundational Lifecycle and Boundaries

**Purpose**: Establish immutable task state, fake boundaries, and proof that the UI can yield, pause, resume, and cancel without persistent or browser-visible run state. These block every story.

- [X] T002 [P] Write unit tests for `CustomerTask`, active-time accounting, eight manager turns, one capability call per model turn, terminal-state behavior, and duplicate-step prevention in `tests/unit/test_task_runtime.py`.
- [X] T003 [P] Write deterministic fake runner tests for manager/specialist boundaries, strict result shapes, model timeout, and no external requests in `tests/unit/test_task_agents.py`.
- [X] T004 Write an integration spike in `tests/integration/test_app.py` proving Gradio 6.27.0 can yield a separate status, cancel an async run, and retain app-owned pending task state in server-side session state without exposing it to the browser.
- [X] T005 Implement immutable task lifecycle values and pure transitions, including the 60-second active-work budget, eight-manager-turn cap, paused clock, and terminal states, in `src/task_runtime.py`.
- [X] T006 Implement an async configured model-client boundary that uses the existing environment variables, HTTPS base URL validation, 10-second per-attempt timeout, and no automatic retries in `src/ai_client.py`.
- [X] T007 Extend fixed-cardinality outcomes/status mappings for task completion, unsupported capability, timeout, cancellation, approval, and safe failure in `src/observability.py` and `src/app.py` without permitting content-bearing diagnostic fields.

**Checkpoint**: The state machine and async/provider boundaries are independently testable. The Gradio lifecycle spike passes before story implementation begins.

---

## Phase 3: User Story 1 - Complete a Customer Task (Priority: P1)

**Goal**: The customer describes a task and receives a useful result from bounded task work, with the conversation role evaluating the specialist's result.

**Independent Test**: With deterministic fakes, submit a supported synthetic lookup task and verify a relevant final response, no unapproved capability call, and one ordered user/assistant pair.

### Tests for User Story 1

- [X] T008 [P] [US1] Write strict schema, allowlist, synthetic FAQ/service-information fixture, ISO date/time preservation, unknown-tool, malformed-argument, duplicate-call-identifier, and bounded-output tests in `tests/unit/test_tools.py`.
- [X] T009 [P] [US1] Write manager/specialist orchestration tests for task plans, structured specialist results, evaluator continuation/final decisions, and unsupported actions in `tests/unit/test_task_agents.py`.
- [X] T010 [P] [US1] Write callback integration tests for accepted task submission, final result, preserved validation/retry/reset behavior, and no duplicate task completion in `tests/integration/test_app.py`.

### Implementation for User Story 1

- [X] T011 [P] [US1] Add separate fixed conversation-agent and task-agent instructions under `src/prompts/` that define friendly customer dialogue, bounded work, no internal-detail disclosure, strict approved capabilities, and structured handoff results.
- [X] T012 [US1] Define the conversation manager and bounded task specialist with the existing configured OpenAI-compatible model boundary and tracing disabled in `src/task_agents.py`.
- [X] T013 [US1] Add strict server-owned synthetic read-only FAQ/service-information fixtures while preserving `getCurrentDateTimeIso` in `src/tools.py`.
- [X] T014 [US1] Implement bounded manager-to-specialist execution and result evaluation in `src/task_runtime.py`, enforcing one capability invocation per model turn, no more than eight manager turns per task, and safe termination on unsupported results.
- [X] T015 [US1] Replace the blocking submission callback with the basic queued async task event and final-response integration in `src/app.py`, preserving current input validation, history, retry, reset, and safe rendering.
- [X] T016 [US1] Add a deterministic browser journey for a supported synthetic lookup and final response in `tests/e2e/test_echo_chat.py`.

**Checkpoint**: Supported synthetic tasks complete without exposing internal agent/tool details; routine tests use only deterministic fakes.

---

## Phase 4: User Story 2 - Receive Progress During Work (Priority: P1)

**Goal**: Customers see accessible progress every five seconds during active work, outside the dialogue, with no updates during customer-input waits or after terminal outcomes.

**Independent Test**: Hold a deterministic async task open and verify visible status cadence, separation from chat history, and stopping at clarification/completion/failure.

### Tests for User Story 2

- [X] T017 [P] [US2] Write fixed-copy progress tests, clarification-wait checks, and browser timing coverage for five-second scheduling with one-second normal-responsiveness tolerance in `tests/integration/test_app.py` and `tests/e2e/test_echo_chat.py`.
- [X] T018 [P] [US2] Write callback/browser integration tests proving progress is an accessible status component and is absent from chat messages while awaiting clarification and after termination in `tests/integration/test_app.py` and `tests/e2e/test_echo_chat.py`.

### Implementation for User Story 2

- [X] T019 [US2] Add a separate accessible progress/status component and fixed customer-safe statuses to `src/app.py`, preserving existing stable `echo-*` selectors.
- [X] T020 [US2] Yield status updates on five-second active-work intervals from the queued async generator in `src/app.py`; stop during waits/terminal states and prevent stale ticks from overwriting a newer state.
- [X] T021 [US2] Add the deterministic slow-task browser journey and verify visible progress timing under normal event-queue responsiveness in `tests/e2e/test_echo_chat.py`.

### Activity-Aware Progress Follow-up
- [X] T044 [P] [US2] Add deterministic lifecycle-hook tests for processing, capability activity, result evaluation, unknown names, and validated `TaskName` handling in `tests/unit/test_task_agents.py`.
- [X] T045 [P] [US2] Add callback tests proving each five-second tick samples the latest per-run activity, preserves fallback copy, and yields no stale progress after completion/wait/cancellation in `tests/integration/test_app.py`.
- [X] T046 [US2] Add a finite transient progress holder and thread it through the task runtime/ledger without changing `CallerSession`, `TaskState`, diagnostics, or browser state in `src/tools.py` and `src/task_runtime.py`.
- [X] T047 [US2] Compose progress updates with existing SDK model hooks and observe only actual lifecycle events plus validated structured task names in `src/task_agents.py`.
- [X] T048 [US2] Render latest known activity as fixed accessible copy on the existing five-second tick, retaining current fallback rotation and terminal/wait precedence in `src/app.py`.
- [X] T049 [US2] Extend the deterministic browser journey to verify lookup-to-evaluation progress copy and absence of internal identifiers in `tests/e2e/test_echo_chat.py`.
- [X] T050 [US2] Document activity-specific progress and fallback behavior in `README.md` and `specs/002-agent-assisted-tasks/quickstart.md`.


**Checkpoint**: Progress remains outside the transcript, appears during active work, and stops during waits and terminal states.

---

## Phase 5: User Story 3 - Approve or Reject a Consequential Action (Priority: P2)

**Goal**: A simulated consequential action pauses for explicit customer approval, executes only after approval, and has no real-world side effect.

**Independent Test**: Use deterministic task output to reach the simulated action; assert zero execution before approval, one execution after approval, and none after rejection/cancellation or replay.

### Tests for User Story 3

- [X] T022 [P] [US3] Write unit tests for approval-required simulated action, pending-call binding, one-shot approve/reject, duplicate-call and stale-decision rejection, and zero side effects in `tests/unit/test_task_runtime.py`.
- [X] T023 [P] [US3] Write integration tests for server-side pending-proposal state, customer-facing decision controls, replay rejection, and no proposal content in browser outputs in `tests/integration/test_app.py`.

### Implementation for User Story 3

- [X] T024 [US3] Add the no-op simulated consequential step and proposal state transition, with no real side effect, in `src/task_runtime.py`.
- [X] T025 [US3] Store the pending proposal only in server-side Gradio state and consume one validated approve/reject decision in `src/task_runtime.py`.
- [X] T026 [US3] Add accessible approve/reject/cancel controls and corresponding resume/reject events in `src/app.py`; do not accept serialized run state, tool arguments, or call identifiers from the browser.
- [X] T027 [US3] Add browser journeys for approval, rejection, and proposal cancellation in `tests/e2e/test_echo_chat.py`; cover replay rejection in `tests/integration/test_app.py`.

**Checkpoint**: Approval is explicit, server-owned, one-shot, and has no real-world effect.

---

## Phase 6: User Story 4 - Cancel or Recover a Task (Priority: P2)

**Goal**: Customers can cancel active work or receive safe recovery at timeout/tool/model failure without losing prior conversation or repeating completed steps.

**Independent Test**: Cancel a held fake run, then separately trigger call timeout, task timeout, tool failure, and turn-limit exhaustion; verify no later step begins and recovery is clear and privacy-safe.

### Tests for User Story 4

- [X] T028 [P] [US4] Write task cancellation, cancellation-during-model-call, 10-second call bound, 60-second active budget, eight-manager-turn exhaustion, and no-next-step tests in `tests/unit/test_task_runtime.py`.
- [X] T029 [P] [US4] Write integration tests for cancellation, fixed recovery statuses, retained retry input, prior history preservation, pending-approval cleanup, and no completed-step replay in `tests/integration/test_app.py`.
- [X] T030 [P] [US4] Write browser tests for cancel, timeout, recoverable failure, retry without duplicate completed steps, and preserved conversation in `tests/e2e/test_echo_chat.py`.

### Implementation for User Story 4

- [X] T031 [US4] Cancel and await the active async agent run on the Gradio cancel event; check cancellation before each next task step and report known completed actions in `src/task_runtime.py`.
- [X] T032 [US4] Enforce per-model-call timeout and remaining active-task deadline, disable retries, and map failures to declared content-free errors in `src/ai_client.py` and `src/task_runtime.py`.
- [X] T033 [US4] Add fixed accessible timeout/cancel/failure/limit statuses and ensure terminal state wins races against progress ticks in `src/app.py`.
- [X] T034 [US4] Verify session reset/expiry discards pending task and approval state without persistence or browser recovery, and cannot execute after a new session begins, in `src/app.py` and `tests/integration/test_app.py`.

**Checkpoint**: Cancellation stops future work; every failure has a safe terminal state and retry cannot duplicate completed work.

---

## Phase 7: Polish and Cross-Cutting Validation

**Purpose**: Align repository instructions and documentation, then run all required privacy, UX, and responsiveness checks.

- [X] T035 [P] Add observable privacy tests proving tracing is disabled and messages, outputs, approval data, credentials, and provider details are absent from diagnostics and browser storage in `tests/unit/test_task_agents.py` and `tests/integration/test_app.py`.
- [X] T036 Update `AGENTS.md` and `.github/copilot-instructions.md` to replace the old single-tool/one-round-trip restriction with the approved strict synthetic task allowlist, per-turn/task bounds, async progress/cancel behavior, and unchanged privacy requirements.
- [X] T037 Update `README.md` with agent behavior, configuration, task/progress/approval/cancel controls, synthetic-only initial capabilities, limits, and privacy behavior.
- [X] T038 Run the feature quickstart scenarios and full deterministic suite with `pytest`; fix only regressions in this feature scope.
- [X] T039 Update `load/echo_load.js` to exercise the task submission event, verify the generated final reply and five-second progress delivery, and enforce the 60-second active-task bound under expected concurrency.
- [ ] T040 Run `k6 run load/echo_load.js` when available and record progress cadence and task completion behavior under expected concurrency; do not claim hard real-time delivery under queue/network delay.
- [ ] T041 Conduct the 10-customer usability check for progress/final distinction and clarification/approval/recovery next actions, recording results against SC-007 in `specs/002-agent-assisted-tasks/quickstart.md`.
- [X] T042 Verify feature artifact and requirement coverage, then update completed task checkboxes and the active feature pointer in `specs/002-agent-assisted-tasks/tasks.md` and `.specify/feature.json`.
- [X] T043 Write a run-level regression test that forces the in-flight active-work timeout (the awaited agent run raises a timeout) and asserts a `TIMED_OUT` task, the fixed timeout message, and no raised exception, in `tests/unit/test_task_runtime.py`; fix the timeout handler in `src/task_runtime.py` to return the already-merged task state.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 Setup**: Immediately available.
- **Phase 2 Foundational**: Depends on T001. T004 is a blocking architecture spike; stop if server-only pending task/proposal state and cancellation semantics cannot be demonstrated without persistence/browser exposure.
- **User Story 1**: Depends on Phase 2; MVP task path.
- **User Story 2**: Depends on the asynchronous event path from US1; adds timed progress UI.
- **User Story 3**: Depends on US1 bounded task execution and server-side state; adds pause/resume approval.
- **User Story 4**: Depends on the shared async runtime and progress terminal-state ownership; adds cancellation and complete recovery.
- **Polish**: Depends on all required stories.

### User Story Dependencies

```text
Setup -> Foundation -> US1 (task completion) -> US2 (progress)
                                      |             |
                                      +-> US3 (approval)
                                      +-> US4 (cancel/recovery)
US1 + US2 + US3 + US4 -> Polish
```

### Parallel Opportunities

- T002 and T003 are independent unit-test files and may be written together.
- Within US1, T008, T009, and T010 are separate test files and can proceed in parallel after the foundational test spike.
- US2's fixed-copy status and wait-state tests (T017) can run alongside the callback/browser status assertions (T018).
- US3 approval unit tests (T022) and app integration tests (T023) can proceed in parallel.
- US4 unit, integration, and browser tests (T028-T030) can proceed in parallel before shared runtime edits.
- T036 and T037 affect separate documentation files and can run in parallel after behavior and names are stable.

## Implementation Strategy

### MVP First

1. Complete Setup and Foundational work, especially T004 before any broad application rewrite.
2. Implement US1 with deterministic synthetic fixtures and the configured fake model boundary.
3. Validate normal task completion plus current input validation, conversation limits, privacy, and recovery.
4. Add progress (US2), then approval (US3) and cancellation/recovery (US4); each story must pass its isolated tests before proceeding.

### Incremental Delivery

1. Keep all first-release tools synthetic, bounded, server-owned, and deterministic.
2. Do not add real integrations or consequential external effects in this implementation.
3. Run the full suite and expected-load validation after the UI lifecycle and tool boundaries are stable.

### Format Validation

Every task has an unchecked checkbox, sequential `T###` identifier, exact file path, and a `[US#]` label only in story phases. `[P]` is used only for tasks that affect independent files and have no unfinished dependency.