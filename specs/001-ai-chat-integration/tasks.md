# Tasks: AI Chat Integration

**Input**: Design documents from `/specs/001-ai-chat-integration/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`,
`contracts/model-service-contract.md`, and `quickstart.md`

**Tests**: Tests are required by the project constitution and the plan. Write the named test tasks
first and establish their failure before implementing the corresponding behavior. Normal tests use
deterministic fakes and must not contact an external model service.

**Organization**: Tasks are grouped by user story so each increment has a clear, independently
verifiable outcome.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel because it affects a different file and has no incomplete-task dependency.
- **[Story]**: User story traceability label; omitted for setup, foundational, and polish tasks.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Add the minimal runtime dependency and safe operator-facing configuration reference.

- [X] T001 Add a pinned official OpenAI Python SDK runtime dependency in `pyproject.toml`.
- [X] T002 [P] Create `.env.example` with only `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_BASE_URL`, and `OPENAI_TIMEOUT_SECONDS` names plus non-secret example values.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Establish the transient conversation-context model, configuration boundary, and
content-free diagnostics that every story shares.

**⚠️ CRITICAL**: Complete this phase before any user-story implementation.

- [X] T003 Write failing pure state-transition tests for ordered user/assistant dialog, retained pending input, and the quoted limits "maximum 50 completed user/assistant pairs" and "User content must contain a non-whitespace character and no more than 4,096 Unicode code points" in `tests/unit/test_echo.py`.
- [X] T004 Write failing configuration and diagnostics tests for required non-empty API key/model, optional HTTPS base URL, timeout "defaults to and may not exceed `10`", and content-free invalid-configuration outcomes in `tests/unit/test_ai_client.py`.
- [X] T005 Replace echo-specific state with pure transient conversation-context transitions in `src/chat.py`; preserve validation, retry, reset, and the quoted 50-pair/4,096-code-point limits, and retain tool invocations separately from displayable messages.
- [X] T006 Implement validated server-only AI service configuration, declared safe provider errors, and client construction with a 10-second timeout and no automatic retries in `src/ai_client.py`.
- [X] T007 Update fixed-cardinality diagnostic outcomes and readiness evaluation for success, invalid configuration, timeout/unavailability, provider rejection, and unusable response in `src/observability.py`.
- [X] T008 Remove the superseded echo-state module in `src/echo.py` after all imports and tests use `src/chat.py`.

**Checkpoint**: The shared state, configuration, diagnostics, and readiness boundary are available
without model network access.

---

## Phase 3: User Story 1 - Receive an AI Answer (Priority: P1) 🎯 MVP

**Goal**: A non-empty chat submission produces one generated assistant reply rather than an echo,
using the fixed system context and all active-session dialog/tool context.

**Independent Test**: With a deterministic fake model boundary, submit non-empty messages and
assert one ordered user/assistant pair per success, a generated reply rather than an echo, and
complete active-session context on every model submission.

- [X] T009 [P] [US1] Write failing adapter tests for ordered active-session dialog serialization, system-context inclusion, prior tool-invocation inclusion, non-empty final replies, and no external network calls in `tests/unit/test_ai_client.py`.
- [X] T010 [P] [US1] Write failing callback tests for generated non-echo replies, ordered history, blank-message rejection, 50-pair limit, and retained input on retry in `tests/integration/test_app.py`.
- [X] T011 [US1] Create the fixed server-owned helpful-assistant and no-inner-workings instruction file in `src/prompts/system.txt`.
- [X] T012 [US1] Implement Responses API request/response handling in `src/ai_client.py` that includes the server-owned system context and complete ordered active-session user/assistant dialog and tool-invocation history with every submission.
- [X] T013 [US1] Replace the echo-generation boundary and complete a successful reply as exactly one user/assistant display pair in `src/app.py`, preserving transient history, retry, reset, and accessible status behavior.
- [X] T014 [US1] Update app-level privacy configuration, health/readiness behavior, and fixed user-safe statuses for the generated-reply flow in `src/app.py`.
- [X] T015 [US1] Update generated-answer, ordered-history, blank-validation, and safe-rendering browser smoke coverage using a deterministic AI fake in `tests/e2e/test_echo_chat.py`.

**Checkpoint**: User Story 1 is independently usable with a fake configured AI service; generated
answers replace echoes and each model request receives the full active-session context.

---

## Phase 4: User Story 2 - Ask Time-Sensitive Questions (Priority: P2)

**Goal**: The assistant may use only `getCurrentDateTimeIso` and receives the resulting
invocation/output as part of later active-session context.

**Independent Test**: With a deterministic fake that requests the date-time capability, assert an
ISO 8601 UTC result is returned against its call identifier, the final answer is displayed, and a
later submission includes the retained tool invocation and result.

- [X] T016 [P] [US2] Write failing ISO 8601 UTC and no-argument validation tests for `getCurrentDateTimeIso` in `tests/unit/test_tools.py`.
- [X] T017 [P] [US2] Extend failing adapter tests for permitted date-time calls, rejected unknown/non-empty/repeated calls, call-identifier correlation, and later-request tool-history inclusion in `tests/unit/test_ai_client.py`.
- [X] T018 [US2] Implement the strict no-argument `getCurrentDateTimeIso` registry and UTC ISO 8601 result in `src/tools.py`.
- [X] T019 [US2] Implement the bounded one-round-trip tool loop in `src/ai_client.py`, retaining accepted date-time invocation/results in transient conversation context and translating malformed/disallowed tool activity into a declared safe error.
- [X] T020 [US2] Integrate date-time tool results into transient state without displaying tool records as chat messages in `src/app.py`.

**Checkpoint**: User Story 2 produces final assistant answers after valid date-time calls, preserves
tool history only in active-session context, and rejects every other capability.

---

## Phase 5: User Story 3 - Receive Safe, Actionable Failures (Priority: P3)

**Goal**: Unavailable services, invalid configuration, and unusable model results retain the
conversation and give a fixed accessible retry message without exposing confidential details.

**Independent Test**: Make the AI boundary raise each declared error and assert that prior history
and pending input are preserved, no partial pair is added, diagnostics contain no content or
configuration, and the same accessible retry status is returned.

- [X] T021 [P] [US3] Write failing adapter error-mapping tests for timeout/unavailability, credential rejection, provider rejection, malformed output, and empty output in `tests/unit/test_ai_client.py`.
- [X] T022 [P] [US3] Write failing callback and readiness tests for fixed safe failure messages, retry without duplicate pairs, `not_ready` invalid configuration, and content-free diagnostics in `tests/integration/test_app.py`.
- [X] T023 [US3] Map configuration and provider failure categories to declared application errors without retaining provider bodies, request identifiers, credentials, service URLs, or message content in `src/ai_client.py`.
- [X] T024 [US3] Complete failure handling, accessible retry messaging, preserved conversation state, privacy-safe diagnostics, and readiness status in `src/app.py` and `src/observability.py`.
- [X] T025 [US3] Update browser failure-and-retry smoke coverage to assert accessible safe alerts, retained input, no partial history, and no secret/provider-detail exposure in `tests/e2e/test_echo_chat.py`.

**Checkpoint**: User Story 3 safely handles all documented configuration and model-service
failures without content leakage.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Align repository guidance, validate all required behavior, and confirm release
criteria without adding scope.

- [X] T026 [P] Update AI chat behavior, required environment variables, compatible-service contract, and privacy constraints in `README.md`.
- [X] T027 Update the 100-submission release-candidate scenario and 10-second p95 threshold in `load/echo_load.js`.
- [X] T028 Run the full deterministic test suite and correct any implementation regressions in `tests/`.
- [ ] T029 Run the quickstart configuration, generated-answer, conversation-context, tool, failure, privacy, and release-candidate checks in `specs/001-ai-chat-integration/quickstart.md`.

---

## Phase 7: Structured Stdout Diagnostics

**Purpose**: Emit privacy-safe operational diagnostics to stdout for the external collector without
adding application-side retention.

- [X] T030 Write failing stdout-capture tests for UTC JSON records, required `timestamp`/`component`/`level`/`message` fields, INFO normal records, ERROR caught-exception records, sanitized optional stacks, and serialization fallback in `tests/unit/test_observability.py`.
- [X] T031 Implement a content-free JSON Lines stdout formatter with UTC timestamps, fixed component names, INFO/ERROR levels, sanitized filename/source-location stacks, and text fallback on JSON serialization failure in `src/observability.py`.
- [X] T032 Connect every app diagnostic outcome and caught model-service exception to the stdout formatter without logging API keys, URLs, request/response bodies, chat messages, prompts, tool outputs, provider metadata, or exception secrets in `src/app.py` and `src/ai_client.py`.
- [X] T033 [P] Update stdout diagnostic behavior, collector ownership, and redaction/fallback constraints in `README.md` and `specs/001-ai-chat-integration/quickstart.md`.
- [X] T034 Run deterministic stdout-capture and full regression tests in `tests/`.

**Checkpoint**: Every expected outcome emits a valid, privacy-safe stdout diagnostic record, while
JSON serialization failure falls back safely and chat behavior remains unaffected.

---

## Phase 8: Latency Diagnostics and Responsiveness

**Purpose**: Identify blocking chat-path time while preserving the strict diagnostic privacy
boundary and validate the p95-under-5-seconds complete-response target.

- [X] T035 [P] Write failing timing-record tests for the quoted fixed steps "`model_request`", "`date_time_tool`", and "`chat_submission`", non-negative integer "`duration_ms`", and exclusion of content, call IDs, and provider metadata in `tests/unit/test_observability.py`.
- [X] T036 [P] Write failing adapter timing tests for every Responses API invocation and `getCurrentDateTimeIso` execution without external network calls in `tests/unit/test_ai_client.py`.
- [X] T037 Implement allowlisted optional `step` and integer `duration_ms` JSON diagnostic fields, using a monotonic clock compatible elapsed-duration boundary, in `src/observability.py`.
- [X] T038 [US1] Instrument every outbound Responses API invocation and the bounded `getCurrentDateTimeIso` capability invocation with the quoted "`model_request`" and "`date_time_tool`" timing records in `src/ai_client.py`.
- [X] T039 [US1] Instrument the complete blocking send and retry paths with the quoted "`chat_submission`" timing record in `src/app.py`.
- [X] T040 [P] Update the p95-under-5-seconds, 10-second-hard-timeout release check and latency-diagnostic documentation in `load/echo_load.js`, `README.md`, and `specs/001-ai-chat-integration/quickstart.md`.
- [ ] T041 Run deterministic timing-record and full regression coverage, then execute the 100-submission load scenario when the external prerequisites are available, in `tests/` and `load/echo_load.js`.

**Checkpoint**: Every blocking chat-path step emits a privacy-safe elapsed-millisecond diagnostic,
and the release scenario verifies p95 completion under 5 seconds without a submission exceeding
the 10-second hard timeout.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1**: Starts immediately.
- **Phase 2**: Depends on T001-T002 and blocks all user stories.
- **User Story 1**: Depends on Phase 2; it is the MVP.
- **User Story 2**: Depends on User Story 1's adapter and transient-state integration (T012-T014).
- **User Story 3**: Depends on User Story 1's reply boundary and shared diagnostics (T012-T014,
  T017) but may proceed in parallel with User Story 2 after those tasks complete.
- **Polish**: Depends on all desired user stories.
- **Structured Stdout Diagnostics (Phase 7)**: Depends on the existing diagnostics integration
  (T007, T024) and precedes the final quickstart/release validation (T029).
- **Latency Diagnostics and Responsiveness (Phase 8)**: Depends on Phase 7. T035-T036 precede
  T037; T037 precedes T038-T039; T040 may run alongside T038-T039; T041 depends on T038-T040.

### User Story Dependencies

```text
Setup → Foundational → US1 (MVP) → US2
                                  └→ US3
US2 + US3 → Polish
Structured stdout diagnostics → Latency diagnostics → T029
```

### Parallel Opportunities

- T001 and T002 affect independent dependency/configuration files.
- T003 and T004 are independent test files.
- T009 and T010 can be written in parallel after Phase 2; T011 can begin with them.
- T016 and T017 affect different test files and can be written together after User Story 1.
- T021 and T022 can be written together; User Story 3 implementation remains sequential because
  `src/ai_client.py` and `src/app.py` are shared.
- T026 can proceed alongside the story work once environment variable names are final.
- T030 and T033 can proceed in parallel; T031 depends on T030, T032 depends on T031, and T034
  depends on T032-T033.
- T035 and T036 affect independent unit-test files and can proceed together. T040 affects only
  documentation/load validation and can proceed in parallel with T038-T039 after T037.

## Parallel Example: User Story 2

```text
T016: tests/unit/test_tools.py
T017: tests/unit/test_ai_client.py
```

After both tests are established, complete T018, then T019, then T020 because those tasks modify
the shared tool registry, adapter, and UI integration in dependency order.

## Implementation Strategy

### MVP First

1. Complete Setup and Foundational work.
2. Complete User Story 1 through T015 with a deterministic fake model boundary.
3. Run the User Story 1 tests and demonstrate a generated non-echo answer with complete
   active-session context.

### Incremental Delivery

1. Add User Story 2 to support the sole approved date-time capability and preserve its history.
2. Add User Story 3's complete safe-failure and retry handling.
3. Complete documentation, release performance, and quickstart validation.

### Format Validation

Every task uses a checkbox, sequential `T###` identifier, exact file path, and a `[US#]` label for
story-specific work. `[P]` appears only where files and prerequisites permit independent work.
