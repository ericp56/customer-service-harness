---

description: "Implementation tasks for the Conversational AI Task Harness"
---

# Tasks: Conversational AI Task Harness

**Input**: Design documents from `/specs/001-ai-chat-harness/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md),
[data-model.md](data-model.md), [contracts/chat-harness-contract.md](contracts/chat-harness-contract.md)

**Tests**: Required by the specification and Constitution IV. Write each listed test before its
corresponding implementation and confirm it fails for the expected reason.

**Organization**: Tasks are grouped by user story so each increment has an independent acceptance
test.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel because it uses separate files and has no unfinished dependency.
- **[Story]**: Maps a task to its user story.
- Each task includes its exact target path.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Initialize the single Python web application and local development workflow.

- [ ] T001 Create the Python 3.13 project and production/development dependencies in `pyproject.toml`
- [ ] T002 [P] Create package directories and module markers in `src/harness/__init__.py`, `src/harness/api/__init__.py`, `src/harness/domain/__init__.py`, `src/harness/services/__init__.py`, `src/harness/adapters/__init__.py`, and `src/harness/ui/__init__.py`
- [ ] T003 Configure formatting, linting, type checking, and pytest defaults in `pyproject.toml`
- [ ] T004 [P] Define local configuration variables, secret handling, and safe defaults in `.env.example` and `src/harness/config.py`
- [ ] T005 [P] Define the local PostgreSQL development service in `docker-compose.yml`
- [ ] T006 Create application startup, health check, and dependency wiring in `src/harness/app.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Establish durable, authorized, observable, and validated primitives required by every
user story.

**⚠️ CRITICAL**: Complete this phase before user-story implementation.

- [ ] T007 Create strict domain entities in `src/harness/domain/models.py`, enforcing the documented constraints: plan revision is “Positive and unique within a conversation”; step sequence is “Positive and unique within a plan”; confirmation expiry “Must be in the future at issuance”; and effect idempotency key is “Unique for the intended effect”
- [ ] T008 [P] Write domain lifecycle tests in `tests/unit/domain/test_state_machine.py` for every documented plan and step transition, including rejection of invalid transitions
- [ ] T009 [P] Write strict structured-plan validation tests in `tests/unit/domain/test_plan_validation.py` covering malformed fields, unknown fields, cyclic dependencies, and missing required outcomes
- [ ] T010 Implement validated plan schemas and dependency-cycle checks in `src/harness/domain/plan_validation.py`
- [ ] T011 Implement plan and step state-transition guards in `src/harness/domain/state_machine.py`
- [ ] T012 Create SQLAlchemy persistence entities and database migration configuration in `src/harness/adapters/persistence.py` and `migrations/`
- [ ] T013 Implement repositories for conversations, messages, plans, confirmation grants, effect attempts, and append-only audit events in `src/harness/adapters/persistence.py`
- [ ] T014 [P] Implement organization identity extraction, server-side permission checks, and ownership authorization in `src/harness/api/auth.py`
- [ ] T015 [P] Implement correlation IDs, privacy-safe structured logging, tracing, and metrics in `src/harness/observability.py`
- [ ] T016 [P] Define the provider-neutral planning and summarization interface, normalized errors, timeouts, and usage metadata in `src/harness/adapters/llm.py`
- [ ] T017 [P] Define an allow-listed external-effect interface that cannot execute without service authorization in `src/harness/adapters/effects.py`
- [ ] T018 Create reusable authenticated-user, database, and fake-provider fixtures in `tests/conftest.py`
- [ ] T019 Write persistence and authorization integration tests in `tests/integration/test_foundation.py` for conversation ownership, append-only messages, immutable audit events, and unauthorized access denial
- [ ] T020 Implement authenticated application routes, consistent error responses, and dependency injection in `src/harness/api/routes.py`

**Checkpoint**: Durable state, authorization, validation, and observability are available for all
user stories.

---

## Phase 3: User Story 1 - Turn a Request into a Plan (Priority: P1) 🎯 MVP

**Goal**: Let an authenticated user submit a request, receive focused clarification when required,
and review a validated ordered plan with current step statuses.

**Independent Test**: Submit clear, ambiguous, and out-of-scope requests and verify that the
conversation presents a goal, assumptions or clarifications, ordered statuses, and safe limits.

- [ ] T021 [P] [US1] Write chat-and-plan contract tests in `tests/contract/test_chat_planning_contract.py` for start, send, view, and resume conversation operations defined in `specs/001-ai-chat-harness/contracts/chat-harness-contract.md`
- [ ] T022 [P] [US1] Write planning integration tests in `tests/integration/test_planning_flow.py` for clear, ambiguous, and out-of-scope requests plus validated persisted plans
- [ ] T023 [P] [US1] Write UI behavior tests in `tests/e2e/test_plan_creation.py` that verify a user can view the objective, assumptions, ordered steps, statuses, and next action
- [ ] T024 [US1] Implement request assessment, focused clarification, safe scope limits, and privacy-safe continuity summaries in `src/harness/services/conversation_service.py`
- [ ] T025 [US1] Implement provider-backed candidate-plan generation, strict validation, canonical persistence, and status initialization in `src/harness/services/planning_service.py`
- [ ] T026 [US1] Implement conversation creation, message submission, conversation retrieval, and plan-view routes in `src/harness/api/routes.py`
- [ ] T027 [US1] Implement the Gradio chat interface and validated plan/status rendering in `src/harness/ui/chat.py`
- [ ] T028 [US1] Mount the authenticated Gradio interface, configure bounded request queuing, and disable public sharing in `src/harness/app.py`

**Checkpoint**: A user can independently create and review a safe, persistent plan in the web
chat.

---

## Phase 4: User Story 2 - Complete Work Through Conversation (Priority: P2)

**Goal**: Let a user advance an approved plan, explicitly authorize consequential steps, and see
accurate completed, blocked, failed, or canceled outcomes.

**Independent Test**: Seed an approved multi-step plan, provide required confirmation, and verify
that a step executes once, reports its result, and safely rejects duplicate or stale approval.

- [ ] T029 [P] [US2] Write confirmation contract tests in `tests/contract/test_confirmation_contract.py` for approval, decline, expiry, revision binding, and user authorization
- [ ] T030 [P] [US2] Write execution integration tests in `tests/integration/test_execution_flow.py` for confirmation-gated effects, blocked dependencies, cancellation, and privacy-safe status reporting
- [ ] T031 [P] [US2] Write concurrent confirmation tests in `tests/integration/test_confirmation_concurrency.py` proving that duplicate approval submissions create at most one effect attempt
- [ ] T032 [US2] Implement single-use, expiring confirmation grants bound to user identity, plan identifier, and plan digest in `src/harness/services/confirmation_service.py`
- [ ] T033 [US2] Implement authorization rechecks, idempotency, effect-attempt recording, and terminal step result handling in `src/harness/services/execution_service.py`
- [ ] T034 [US2] Add plan-step advancement, confirmation, decline, cancellation, and terminal-status routes in `src/harness/api/routes.py`
- [ ] T035 [US2] Add plan controls, confirmation prompts, blocked-state explanations, and next-action rendering in `src/harness/ui/chat.py`
- [ ] T036 [US2] Record privacy-safe proposal, confirmation, execution, and outcome audit events in `src/harness/services/execution_service.py`

**Checkpoint**: A user can independently advance a seeded approved plan through safe,
confirmation-gated work and understand every outcome.

---

## Phase 5: User Story 3 - Revise and Resume a Plan (Priority: P3)

**Goal**: Let a user revise a plan or resume an unfinished conversation without losing completed
work or using stale confirmations.

**Independent Test**: Start a plan, complete one step, revise a pending requirement, and resume
the conversation to verify a visible impact summary, preserved completed work, superseded pending
work, and invalidated prior approval.

- [ ] T037 [P] [US3] Write plan-revision integration tests in `tests/integration/test_plan_revision.py` for impact summaries, immutable revisions, superseded pending work, and invalidated confirmation grants
- [ ] T038 [P] [US3] Write conversation-resumption integration tests in `tests/integration/test_conversation_resume.py` for current state, summary generation, and pending or blocked next steps
- [ ] T039 [P] [US3] Write revision-and-resume UI tests in `tests/e2e/test_plan_revision_resume.py` for editing a plan, returning after interruption, and viewing updated statuses
- [ ] T040 [US3] Implement plan revision, canonical digest regeneration, prior-approval invalidation, and preservation of completed results in `src/harness/services/planning_service.py`
- [ ] T041 [US3] Implement resumable conversation summaries and current-next-step selection in `src/harness/services/conversation_service.py`
- [ ] T042 [US3] Add plan revision and resumption routes with ownership checks in `src/harness/api/routes.py`
- [ ] T043 [US3] Add revision controls, impact summaries, resume status, and stale-approval messaging in `src/harness/ui/chat.py`

**Checkpoint**: A user can independently revise or resume a plan while retaining correct history,
statuses, and authorization boundaries.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Demonstrate the full constitutional quality bar across all stories.

- [ ] T044 [P] Add AI-provider adapter contract tests for structured output, refusal, timeout, rate-limit, malformed output, and interruption in `tests/contract/test_llm_adapter.py`
- [ ] T045 [P] Add property-based tests proving malformed plans and unconfirmed effect requests never reach an effect adapter in `tests/unit/domain/test_effect_safety_properties.py`
- [ ] T046 [P] Add end-to-end privacy and access-control coverage for unauthorized conversations, sensitive-data redaction, and public-sharing disablement in `tests/e2e/test_privacy_and_access.py`
- [ ] T047 Add a 50-active-conversation load scenario and latency/queue assertions in `tests/load/test_concurrent_conversations.py`
- [ ] T048 Add deployment, identity-provider, secret-management, retention, and rollback guidance in `README.md`
- [ ] T049 Update `specs/001-ai-chat-harness/quickstart.md` with the final migration and load-test commands implemented by the project
- [ ] T050 Run the quickstart end-to-end workflow and record any required corrections in `specs/001-ai-chat-harness/quickstart.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: Starts immediately.
- **Phase 2 (Foundational)**: Depends on Phase 1 and blocks every user story.
- **Phase 3 (US1)**: Depends on Phase 2 and is the MVP.
- **Phase 4 (US2)**: Depends on Phase 2 and the persisted-plan capability from US1.
- **Phase 5 (US3)**: Depends on Phase 2 and the persisted-plan capability from US1.
- **Phase 6 (Polish)**: Depends on all selected user stories.

### User Story Dependencies

- **US1 (P1)**: No user-story dependency; delivers plan creation.
- **US2 (P2)**: Requires US1 to create production plans; its tests may use seeded plans.
- **US3 (P3)**: Requires US1 to create production plans; its tests may use seeded plans.

### Parallel Opportunities

- T002-T005 can run in parallel after T001 begins.
- T008, T009, T014-T017 can run in parallel after T007's domain shape is established.
- T021-T023, T029-T031, and T037-T039 are parallel test tasks within their user stories.
- After US1's persisted plan interfaces stabilize, US2 and US3 test work can proceed in parallel.
- T044-T048 can run in parallel after all user stories complete.

---

## Parallel Example: User Story 1

```text
Task: "Write chat-and-plan contract tests in tests/contract/test_chat_planning_contract.py"
Task: "Write planning integration tests in tests/integration/test_planning_flow.py"
Task: "Write UI behavior tests in tests/e2e/test_plan_creation.py"
```

## Parallel Example: User Story 2

```text
Task: "Write confirmation contract tests in tests/contract/test_confirmation_contract.py"
Task: "Write execution integration tests in tests/integration/test_execution_flow.py"
Task: "Write concurrent confirmation tests in tests/integration/test_confirmation_concurrency.py"
```

## Parallel Example: User Story 3

```text
Task: "Write plan-revision integration tests in tests/integration/test_plan_revision.py"
Task: "Write conversation-resumption integration tests in tests/integration/test_conversation_resume.py"
Task: "Write revision-and-resume UI tests in tests/e2e/test_plan_revision_resume.py"
```

---

## Implementation Strategy

### MVP First

1. Complete Phases 1 and 2.
2. Complete Phase 3 (US1) through T028.
3. Demonstrate a user creating, clarifying, and reviewing a durable plan.
4. Add confirmation-gated execution only after the plan lifecycle is reliable.

### Incremental Delivery

1. Deliver US1 for request assessment and plan creation.
2. Deliver US2 for explicit-confirmation workflow and execution status.
3. Deliver US3 for plan revisions and conversation resumption.
4. Complete cross-cutting safety, privacy, performance, and deployment work.
