---

description: "Task list for Echo Web Chat implementation"
---

# Tasks: Echo Web Chat

**Input**: Design documents from `/specs/001-echo-web-chat/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md,
data-model.md, contracts/echo-chat-contract.md, quickstart.md

**Tests**: Automated tests are required by the implementation plan and project constitution:
pytest validation/callback tests, Playwright browser E2E tests, and a k6 release-candidate load
scenario.

**Organization**: Tasks are grouped by user story so each increment can be implemented and tested
independently.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel because it uses a different file and has no incomplete dependency.
- **[Story]**: Maps the task to the corresponding user story.
- Each task identifies its exact file path.

## Path Conventions

- Application source: `src/`
- Unit tests: `tests/unit/`
- Integration tests: `tests/integration/`
- Browser E2E tests: `tests/e2e/`
- Release load scenario: `load/`

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Establish the single Python web-application project and development dependencies.

- [X] T001 Define Python `>=3.14,<3.15` project metadata, add an exact pinned `gradio==6.x.y` runtime dependency, and add a `dev` optional-dependency group containing `pytest` and `pytest-playwright` in `pyproject.toml`; keep k6 out of Python dependencies because it is an external release-test prerequisite.
- [X] T002 [P] Create the `src/__init__.py` package marker and application source directory structure in `src/__init__.py`.
- [X] T003 [P] Configure pytest and pytest-playwright test discovery in `pyproject.toml`.
- [X] T004 [P] Document `python -m pip install -e ".[dev]"`, `playwright install`, and the externally installed k6 prerequisite in `specs/001-echo-web-chat/quickstart.md`.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Provide privacy-safe operational primitives and an application entry point required by
both user stories.

**⚠️ CRITICAL**: Complete this phase before user-story implementation.

- [X] T005 Implement fixed-cardinality, content-free outcome, duration, queue-depth, and health diagnostics in `src/observability.py`.
- [X] T006 Implement a same-origin Gradio application entry point with health/readiness handling, finite queue configuration, at-least-50 handler concurrency, analytics disabled, and no application-created persistence in `src/app.py`.
- [X] T007 Add privacy and health integration coverage that rejects message content and visitor identifiers from diagnostics in `tests/integration/test_app.py`.

**Checkpoint**: Shared application and observability foundations are ready for story work.

---

## Phase 3: User Story 1 - Send and Receive an Echo (Priority: P1) 🎯 MVP

**Goal**: Let an unauthenticated visitor submit valid text and receive one identical, ordered echo
pair in a transient conversation of at most 50 completed pairs.

**Independent Test**: A visitor submits valid text, including punctuation, line breaks, and
non-English characters, and receives exactly one following identical echo; after 50 completed
pairs, history remains visible and a new conversation can be started.

### Tests for User Story 1

- [X] T008 [P] [US1] Add pure validation and successful state-transition tests for "`content` | String | Required; contains a non-whitespace character; at most 4,096 Unicode code points; preserved exactly if accepted" in `tests/unit/test_echo.py`.
- [X] T009 [P] [US1] Add callback integration tests for one exact ordered `user`/`assistant` pair, transient history, and the 50-completed-pair limit in `tests/integration/test_app.py`.
- [X] T010 [P] [US1] Add browser E2E coverage for normal, Unicode, line-break, and 50-pair/new-conversation journeys in `tests/e2e/test_echo_chat.py`.

### Implementation for User Story 1

- [X] T011 [US1] Implement transient chat-message and active-conversation state, including `history`, `pending_text`, and `submission_state`, in `src/echo.py`.
- [X] T012 [US1] Implement exact-input validation and successful state transitions in `src/echo.py` so accepted content is never trimmed, normalized, or transformed and success appends exactly one `user` message followed by one `assistant` message.
- [X] T013 [US1] Implement the text-only Gradio chat page, Send handling, ordered conversation presentation, and 50-pair limit state in `src/app.py`.
- [X] T014 [US1] Add the accessible Start New Conversation control that clears only transient conversation state after the pair limit in `src/app.py`.

**Checkpoint**: User Story 1 delivers the independently testable MVP echo workflow.

---

## Phase 4: User Story 2 - Correct Invalid or Unsent Input (Priority: P2)

**Goal**: Give visitors accessible corrective feedback for invalid input and a retry path for
operational failures without losing their valid pending input or completed conversation.

**Independent Test**: A visitor receives feedback and no new pair for blank or oversized input;
after a simulated operational failure, the original valid text and prior history remain available
and Retry creates one ordered pair when the failure is restored.

### Tests for User Story 2

- [X] T015 [P] [US2] Add unit tests for blank, whitespace-only, exactly-4,096-code-point, and 4,097-code-point input, plus failed-to-retry state transitions, in `tests/unit/test_echo.py`.
- [X] T016 [P] [US2] Add integration tests for callback failure, mismatched callback output, retained pending text, preserved history, and duplicate-prevention during sending in `tests/integration/test_app.py`.
- [X] T017 [P] [US2] Add browser E2E coverage for accessible validation, error status, keyboard-reachable Retry, and successful recovery in `tests/e2e/test_echo_chat.py`.

### Implementation for User Story 2

- [X] T018 [US2] Implement validation and operational-failure transitions in `src/echo.py` so invalid or failed attempts append no messages, retain required state, and prevent duplicate or reordered pairs while sending.
- [X] T019 [US2] Implement accessible blank/oversize feedback, content-preserving operational errors, and keyboard-reachable Retry wiring in `src/app.py`.

**Checkpoint**: User Stories 1 and 2 are independently testable with recovery and validation.

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Complete release-facing accessibility, privacy, performance, and operational coverage.

- [X] T020 [P] Add a 50-virtual-user, 5-to-10-minute release-candidate p95-under-one-second scenario with exact-echo and queue-saturation assertions in `load/echo_load.js`.
- [X] T021 [P] Add integration coverage that confirms text-only rendering and prohibits Markdown, HTML, rich content, browser restoration, cookies, uploads, analytics, feedback, and sharing in `tests/integration/test_app.py`.
- [X] T022 Document application launch, browser validation, diagnostics inspection, and the release load command in `specs/001-echo-web-chat/quickstart.md`.
- [ ] T023 Obtain platform-owner confirmation of same-origin HTTPS, finite ingress timeouts, and disabled request/response body logging for the echo route in `specs/001-echo-web-chat/quickstart.md`.
- [ ] T024 Validate the deployed echo route's HTTPS, timeout, and body-log suppression controls in `specs/001-echo-web-chat/quickstart.md`.
- [ ] T025 Execute the rollout readiness checks and record the content-free monitoring and rollback triggers in `specs/001-echo-web-chat/quickstart.md`.
- [ ] T026 Execute and document the application-route withdrawal and post-rollback transient-data verification procedure in `specs/001-echo-web-chat/quickstart.md`.
- [ ] T027 Run the complete unit, integration, browser E2E, and release-load validation workflow described in `specs/001-echo-web-chat/quickstart.md`.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Starts immediately.
- **Foundational (Phase 2)**: Depends on T001–T004 and blocks user-story work.
- **User Story 1 (Phase 3)**: Depends on Phase 2 and is the MVP.
- **User Story 2 (Phase 4)**: Depends on the state and UI introduced by User Story 1.
- **Polish (Phase 5)**: Depends on both user stories.

### User Story Dependencies

- **User Story 1 (P1)**: Starts after T005–T007; no dependency on another user story.
- **User Story 2 (P2)**: Extends the conversation state and UI from User Story 1, so begins after
  T011–T014.

### Within Each User Story

- Story tests precede the corresponding implementation tasks.
- State and validation logic in `src/echo.py` precede UI wiring in `src/app.py`.
- Each story is complete at its checkpoint before release-focused cross-cutting work begins.

## Parallel Opportunities

- T002–T004 can proceed in parallel after T001 establishes dependency conventions.
- T008–T010 can proceed in parallel for User Story 1; T015–T017 can proceed in parallel for User
  Story 2 because they target separate test layers.
- T020 and T021 can proceed in parallel after both stories.

## Parallel Example: User Story 1

```text
Task: "Add pure validation and successful state-transition tests in tests/unit/test_echo.py"
Task: "Add callback integration tests in tests/integration/test_app.py"
Task: "Add browser E2E coverage in tests/e2e/test_echo_chat.py"
```

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 and Phase 2.
2. Complete T008–T014 for the P1 send-and-echo workflow.
3. Validate the User Story 1 independent test criterion before beginning recovery behavior.

### Incremental Delivery

1. Deliver the bounded, transient exact-echo workflow from User Story 1.
2. Add validation and operational recovery from User Story 2 without changing successful-pair
   semantics.
3. Complete privacy, browser, diagnostics, and release-performance coverage.

## Notes

- `[P]` tasks use different files or independent test layers and have no incomplete dependency.
- `[US1]` and `[US2]` labels provide story traceability.
- The maximum-length constraint is quoted in T008; retain it exactly during implementation.
- No task introduces durable transcripts, accounts, external integrations, message-content logging,
  browser persistence, or model/LLM dependencies.
