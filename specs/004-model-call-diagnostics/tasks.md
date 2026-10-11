# Tasks: Model Call Diagnostics

**Input**: `specs/004-model-call-diagnostics/spec.md` and `plan.md`

**Tests**: Required. Use deterministic fakes; no provider calls.

## Phase 1: Foundation

- [X] T001 [P] Write tests for `record_model_call` field allowlist, validation, outcome set, task-id format, and serialization-failure tolerance in `tests/unit/test_observability.py`.
- [X] T002 Add `record_model_call` and the optional validated `task_id` on `Diagnostics.record` in `src/observability.py`.
- [X] T003 Add `task_id` to `TaskState` and preserve it on resume in `src/task_runtime.py`.

## Phase 2: User Story 1 - See Every Model Call (P1)

- [X] T004 [P] [US1] Write scripted-model tests for one line per call, token values, not-reported usage, response shape, tool-name allowlist, and role/sequence in `tests/unit/test_model_diagnostics.py`.
- [X] T005 [US1] Implement `ModelCallHooks` and `ModelCallRecorder` in `src/model_diagnostics.py`.
- [X] T006 [US1] Pass the specialist hooks to `as_tool` in `src/task_agents.py` and the conversation hooks plus recorder scope to `Runner.run` in `src/task_runtime.py`.

## Phase 3: User Story 2 - See Failed Calls (P1)

- [X] T007 [P] [US2] Write tests for timeout, error, and cancellation lines in `tests/unit/test_model_diagnostics.py`.
- [X] T008 [US2] Close the open call as `timeout`, `error`, or `canceled` from the runtime's exception and cleanup paths in `src/task_runtime.py`.

## Phase 4: User Story 3 - Follow One Task (P2)

- [X] T009 [P] [US3] Write tests that call and outcome lines share a task id, concurrent tasks differ, and the id persists across a clarification resume, in `tests/unit/test_model_diagnostics.py` and `tests/integration/test_caller_session.py`.
- [X] T010 [US3] Pass `task_id` from the task result into the outcome records in `src/app.py`.

## Phase 5: Polish

- [X] T011 [P] Add observable privacy tests that run secret text through prompts, replies, tool arguments, and account/zip values and assert none appear in stdout, in `tests/unit/test_model_diagnostics.py`.
- [X] T012 Update diagnostics wording in `AGENTS.md`, `.github/copilot-instructions.md`, and `README.md`.
- [X] T013 Run the full suite with `pytest` and confirm task checkboxes.

## Dependencies

T002 blocks T005 and T010. T003 blocks T006 and T010. T005 blocks T006 and T008.

## Phase 6: User Story 4 - Configure Reasoning Effort (P2)

**Goal**: Let operators set a validated optional reasoning effort across agent and synchronous model requests.

**Independent Test**: Recognized values are applied to every request, blank/unset values preserve provider defaults, and unknown values fail as fixed invalid configuration without sending a request.

- [X] T014 [P] [US4] Add configuration and request-path tests for all SDK reasoning efforts, blank/unset/trimmed/invalid values, and tool follow-ups in `tests/unit/test_ai_client.py`.
- [X] T015 [US4] Add the optional validated reasoning-effort configuration and apply it only when configured in `src/ai_client.py`.

## Phase 7: User Story 5 - See Caller Task Progress (P1)

**Goal**: Add explicit privacy-safe live task snapshots to model-call lines and one final snapshot per caller-message runtime outcome.

**Independent Test**: Scripted tasks exercise success, nested capability work, clarification, approval, failure, timeout, cancellation, and early exits; each started call includes a safe snapshot and each invocation emits exactly one final outcome line.

- [X] T016 [P] [US5] Test the typed progress snapshot schema, fixed field allowlist, validation failures, serialization failure isolation, and existing model-call compatibility in `tests/unit/test_observability.py`.
- [X] T017 [P] [US5] Test live per-call progress, final outcomes, cancellation and early exits, concurrency/resume, timing semantics, and privacy sentinels in `tests/unit/test_model_diagnostics.py`.
- [X] T018 [US5] Implement validated task snapshot and task-outcome JSON emitters plus optional snapshots on model-call records in `src/observability.py`.
- [X] T019 [US5] Add snapshot callback support and observer-only manager-turn tracking to the call recorder/hooks in `src/model_diagnostics.py`.
- [X] T020 [US5] Sample `TaskState` and the live tool ledger without mutation; emit exactly one final `task_outcome` for every `run_customer_task` return and cancellation in `src/task_runtime.py`.
- [X] T021 [US5] Map invalid reasoning configuration to the fixed configuration diagnostic and preserve the task failure mapping in `src/app.py`.

## Phase 8: Polish

- [X] T022 [P] Update `README.md`, `AGENTS.md`, and `.github/copilot-instructions.md` with `OPENAI_REASONING` semantics and the approved safe task-diagnostic fields.
- [X] T023 Run focused and full deterministic test suites and verify diagnostic overhead stays within the specified 5 ms per model call; record validation in this task list.

Validation: focused feature tests passed (86 tests), final full suite passed (155 tests), and the average 100-record model-call emitter check remained below 5 ms per call.

### New Task Dependencies

- T014 blocks T015.
- T016 blocks T018.
- T017 blocks T019 and T020.
- T018 and T019 block T020.
- T015 blocks T021; T020 blocks T021.
- T015 and T021 block T022. T015-T022 block T023.
