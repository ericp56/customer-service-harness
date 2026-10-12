# Feature Specification: Agent-Assisted Customer Tasks

**Current public UI supersession**: Feature 005's 2026-10-12 async-notice refinement
replaces the separate progress/status area with fixed accessible assistant chat
entries. See [the current conversation contract](../005-async-conversation/contracts/conversation-events.md).

**Async Interaction Update (2026-10-11)**: Feature 005 supersedes alternating
submission and the 50-pair interpretation for the public application with ordered
caller events, bounded inbox and versioned confirmation. Legacy lifecycle helper
tests remain valid. See [feature 005](../005-async-conversation/spec.md).

**Catalog Scope Update (2026-10-11)**: Feature 003's catalog-only refinement supersedes generic service-information and simulated approval examples for the public application. This feature's pure lifecycle/harness behavior remains independently tested; public submissions execute only catalog tasks and use fixed refusals for unrelated work. See [the catalog boundary contract](../003-caller-service-tasks/contracts/catalog-boundary.md).

**Feature Branch**: `002-agent-assisted-tasks`

**Created**: 2026-10-04

**Status**: Draft

**Input**: User description: "Update the customer chat so customers can interact with task-expert agents that plan and carry out work using approved tools. Use a conversation agent to communicate with customers, provide simple progress updates every five seconds while active work is underway, evaluate task-agent results, and decide whether to continue or return to dialogue."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Complete a Customer Task (Priority: P1)

As a customer, I can describe a task in the existing chat and receive a useful result from an assistant that plans and performs bounded work using approved capabilities.

**Why this priority**: Task completion is the feature's core value.

**Independent Test**: Submit a supported request that can be completed using a synthetic read-only lookup and verify a clear final answer appears in the existing conversation.

**Acceptance Scenarios**:

1. **Given** a supported request and available synthetic lookup data, **When** the customer submits the request, **Then** the assistant returns a response based on the lookup and does not expose internal plans, reasoning, prompts, or tool details.
2. **Given** a request requires clarification, **When** the assistant asks a question, **Then** it waits for the customer's answer before continuing the task.
3. **Given** the customer asks a question requiring current date or time, **When** the task uses that capability, **Then** the final response uses its current ISO 8601 result.

### User Story 2 - Receive Progress During Work (Priority: P1)

As a customer, I receive a simple status while a task is taking time, so I know the request is still being handled.

**Why this priority**: Multi-step work can outlast the current synchronous response, and customers need feedback without being shown internal orchestration.

**Independent Test**: Hold deterministic task execution and result evaluation open and verify the status at five-second intervals reflects the current known activity, then stop updates when the task completes or asks the customer a question.

**Acceptance Scenarios**:

1. **Given** a task remains active and is not waiting for customer input, **When** five seconds elapse, **Then** the customer sees concise fixed copy reflecting the latest known activity, without internal agent, capability, prompt, provider, or harness details.
2. **Given** execution advances from a lookup to evaluating its result, **When** a progress interval elapses in each phase, **Then** the status changes to describe the current phase rather than claiming the earlier phase is still underway.
3. **Given** a validated catalog task name is known for the activity, **When** progress is shown, **Then** the status may identify that task by its exact catalog name; otherwise it uses generic fixed copy or the existing rotating fallback messages.
4. **Given** the assistant is waiting for the customer, **When** time passes, **Then** no periodic work-in-progress status is shown.
5. **Given** a task completes, fails, times out, or is canceled, **When** its terminal status is presented, **Then** periodic progress stops.

### User Story 3 - Approve or Reject a Consequential Action (Priority: P2)

As a customer, I can review and decide whether a consequential action should proceed.

**Why this priority**: Customers must retain control over actions that could affect them or another service.

**Independent Test**: Request a task containing the simulated consequential action and verify that it pauses for approval, executes no effect before approval, and handles approval, rejection, and cancellation distinctly.

**Acceptance Scenarios**:

1. **Given** a task proposes a consequential action, **When** it reaches that step, **Then** the assistant explains the proposed action in customer-appropriate terms and waits for explicit approval.
2. **Given** the customer approves, **When** the simulated action proceeds, **Then** the assistant reports its simulated result and no real-world side effect occurs.
3. **Given** the customer rejects or cancels the proposal, **When** the decision is received, **Then** the action does not proceed and the assistant explains the task outcome.
4. **Given** an approval is pending, **When** the customer resets the conversation or its session expires, **Then** the pending action is discarded and cannot execute later.

### User Story 4 - Cancel or Recover a Task (Priority: P2)

As a customer, I can stop work or recover from a failure without losing the conversation or being misled about what happened.

**Why this priority**: Bounded work needs a clear and safe end state when a customer changes their mind or a dependency fails.

**Independent Test**: Cancel a held task and separately force a synthetic tool failure and the task time limit; verify remaining work stops, prior conversation remains, and a clear recovery status is shown.

**Acceptance Scenarios**:

1. **Given** work is in progress, **When** the customer cancels, **Then** no remaining task steps begin, the assistant reports whether a prior action completed, and the conversation remains available.
2. **Given** a tool or model step fails, **When** the failure is handled, **Then** the customer sees a fixed, actionable recovery message without sensitive configuration or internal details.
3. **Given** a task reaches its 60-second active-work limit, including while a model or tool step is still in progress, **When** it is stopped, **Then** the assistant reports that it could not finish and provides a safe next step, with no unhandled error shown to the customer.
4. **Given** the customer retries after a recoverable failure, **When** the request is resubmitted, **Then** the system does not duplicate a completed task step or simulated action.

### Edge Cases

- The customer submits blank or over-limit input, or submits again while a task is active.
- The customer does not answer a clarification or approval request, or resets/expires the session while one is pending.
- A task requires an unapproved capability, returns malformed data, has no matching synthetic lookup result, or replays a capability call identifier/completed step.
- Cancellation arrives while a step is completing; the system reports any completed action and prevents subsequent steps.
- A progress interval elapses just as the task completes, fails, is canceled, or enters a wait for customer input.
- The active phase is unknown or changes between progress ticks; use safe fallback copy and never retain a completed phase as current activity.
- Multiple task steps or agent turns approach the active-work limit.
- The active-work limit expires while a model request or tool step is in flight; the in-flight work is abandoned and the same fixed timeout recovery is shown, never a generic error.
- The task-agent and conversation-agent disagree about whether a task is complete or safe to continue.
- Diagnostic serialization fails while a task is in progress.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST let a customer describe a task in the existing chat and receive a customer-facing response based on the task outcome.
- **FR-002**: The task role MUST identify the requested outcome, define bounded steps, and execute only approved capabilities. The conversation role MUST handle customer communication, clarification, work evaluation, and next-action selection.
- **FR-003**: The conversation role MUST evaluate task results and choose whether to request another bounded task step, ask the customer for input, or provide a final response.
- **FR-004**: The system MUST ask the customer for clarification when required information is missing and MUST wait for the customer's response before continuing.
- **FR-005**: The system MUST schedule progress at five-second intervals while work continues and the system is not waiting for customer input. Each update MUST reflect the latest known active-work phase at the time of the tick. Under normal service responsiveness, each update MUST be visible no later than one second after its scheduled interval.
- **FR-006**: Progress and customer-facing task responses MUST NOT disclose internal reasoning, agent instructions, prompts, provider details, capability identifiers or arguments, or orchestration implementation details. Progress MUST use fixed application copy and MAY include only a catalog task name validated against the fixed catalog enum; if activity or name is unknown, it MUST use generic fixed copy or the existing fallback messages.
- **FR-007**: Progress MUST stop while waiting for customer input and upon task completion, failure, timeout, or cancellation. For the current public UI, progress is fixed accessible assistant chat content, counts toward the bounded transcript, and is excluded from model context and diagnostics; no separate visible status area is used.
- **FR-008**: The initial capability set MUST retain the current date/time capability and permit only deterministic synthetic customer-service lookups. Real database access, external service integrations, and real-world write actions are out of scope for this release.
- **FR-009**: The system MUST require explicit customer approval before any consequential action is performed. The initial release MUST use a simulated consequential action with no real-world side effect to exercise proposal, approval, rejection, and cancellation outcomes.
- **FR-010**: The system MUST NOT perform a proposed consequential action before approval, and MUST NOT perform it after rejection or cancellation.
- **FR-011**: The customer MUST be able to cancel active work. Cancellation MUST prevent remaining steps from starting where possible and MUST report any action that completed before cancellation.
- **FR-012**: Active task processing MUST be bounded to 60 seconds. Time spent waiting for customer input does not count as active task processing; processing MUST resume only after the customer responds and MUST stop when the active-work budget is exhausted.
- **FR-013**: Each individual external model request MUST remain bounded by the existing maximum 10-second timeout. Agent and tool work MUST stop safely when the active task limit is reached.
- **FR-014**: For task failures, timeouts, and unsupported capabilities, the system MUST preserve prior conversation, provide an accessible fixed recovery status, and avoid exposing credentials, service addresses, customer content, or internal diagnostics.
- **FR-015**: The system MUST preserve existing blank-input and maximum-message-length validation, retry behavior, new-conversation behavior, and 50-pair conversation bound unless a separately approved requirement changes them.
- **FR-016**: User content, model output, synthetic tool output, approval details, prompts, provider payloads, and credentials MUST remain transient and MUST NOT enter diagnostics, durable storage, or browser persistence.
- **FR-017**: Normal automated tests MUST use deterministic fake model and tool boundaries and MUST NOT call an external model provider.
- **FR-018**: Customer-facing dialogue MUST be friendly, concise, and clear about whether the assistant is asking a question, requesting approval, reporting progress, or giving a final result.
- **FR-019**: Every capability request MUST match a strict server-owned schema and allowlist. The system MUST accept at most one capability invocation per model turn, at most eight conversation-manager turns per task, and at most four turns per task-specialist invocation; unknown, malformed, duplicate-call-identifier, replayed-completed-step, or over-budget requests MUST stop safely without executing an unapproved action.
- **FR-020**: A pending clarification or approval MUST be discarded when its customer conversation is reset or its active session expires; a discarded pending action MUST NOT execute later.

### Key Entities *(include if feature involves data)*

- **Customer Task**: A customer's request, its current lifecycle state, and its bounded active-work budget.
- **Task Step**: A proposed piece of work and its outcome, limited to an approved capability.
- **Clarification Request**: A customer-facing question that pauses task processing until answered.
- **Action Approval**: A proposal and the customer's explicit approve, reject, or cancel decision.
- **Progress Notice**: Fixed, accessible, display-only assistant chat content indicating active work; it requires no customer reply and is excluded from model context and diagnostics.
- **Task Result**: The final customer-facing outcome or safe failure/recovery status.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For 20 supported synthetic lookup requests, 100% produce a relevant final response or a clear recoverable failure without invoking an unapproved capability.
- **SC-002**: Under normal service responsiveness, each sampled five-second progress interval with changed display wording produces an accessible chat entry within one additional second; 100% of tested wait and terminal states stop periodic updates and optional progress stops at 90 assistant entries.
- **SC-003**: 100% of tested consequential-action scenarios perform no action before explicit approval, and rejection or cancellation produces no simulated action result.
- **SC-004**: 100% of active task runs complete or reach a safe terminal status at or before 60 seconds of active processing.
- **SC-005**: In cancellation, timeout, and tool-failure tests, 100% preserve prior conversation and report whether a consequential action already completed without duplicating completed steps on retry.
- **SC-006**: In privacy tests, 100% of diagnostics and browser-storage checks contain no customer messages, model outputs, tool outputs, approval details, prompts, provider payloads, or credentials.
- **SC-007**: At least 9 of 10 representative customers can distinguish a temporary progress chat message from a final answer and identify the next action when clarification, approval, or recovery is required.
- **SC-008**: 100% of tests that exceed the eight-manager-turn or four-specialist-turn limit, or submit malformed, duplicate-call-identifier, replayed-completed-step, or unapproved capability calls stop without executing the offending action and show a clear recovery outcome.

## Assumptions

- The feature continues to serve unauthenticated customers using the current web chat; it does not introduce support-agent accounts or customer identity records.
- “Separate agents” means distinct task-execution and user-conversation responsibilities with separate session boundaries as requested; the specification does not select a model vendor or orchestration technology.
- Synthetic lookup fixtures contain no real customer data. Existing date/time behavior remains available.
- The simulated consequential action exists only to validate customer approval and cancellation behavior and has no external side effect.
- The 60-second limit applies to active processing; time awaiting clarification or approval is paused. The task resumes with only its remaining active-work budget.
- Existing privacy, accessible status, safe-rendering, diagnostic redaction, input-length, retry, and conversation-size constraints continue to apply.
- Individual external model requests retain the existing maximum 10-second timeout; bounded multi-step work is limited by the overall active-work budget.
- Each task has at most eight conversation-manager turns; each task-specialist invocation has at most four turns. Each model turn permits one strict, approved capability invocation; exhausting a limit ends with a safe recovery status.