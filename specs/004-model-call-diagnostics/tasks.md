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
