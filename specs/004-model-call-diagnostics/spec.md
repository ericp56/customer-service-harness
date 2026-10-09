# Feature Specification: Model Call Diagnostics

**Feature Branch**: `004-model-call-diagnostics`

**Created**: 2026-10-09

**Status**: Draft

**Input**: User description: "stdout is very sparse and only shows when a task finishes. Log each model API response with its duration, tokens used, and response information."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See Every Model Call (Priority: P1)

As an operator, I can see one diagnostic line for each model call a task makes, so I can judge latency and token cost and see where a slow task spent its time.

**Why this priority**: It is the core visibility gap; today only task outcomes appear.

**Independent Test**: Run a task that makes several model calls and verify one line per call, each with a duration, token counts, the calling role, and an outcome.

**Acceptance Scenarios**:

1. **Given** a task makes model calls, **When** each call returns, **Then** one diagnostic line is emitted for it with a non-negative integer duration in milliseconds, input, output, and total token counts, the caller role, and a success outcome.
2. **Given** a call returns a tool request, **When** the line is emitted, **Then** it reports the number of message and tool-call items and the name of the requested tool when it is a known tool.
3. **Given** the model service reports no usage data, **When** the line is emitted, **Then** token counts are zero and the line states that usage was not reported.
4. **Given** a task makes calls from both agent roles, **When** lines are emitted, **Then** each line identifies its role and a call sequence number that starts at 1 for each caller message.

### User Story 2 - See Failed Calls (Priority: P1)

As an operator, I can see calls that time out, fail, or are canceled, so slowness and errors are not invisible.

**Why this priority**: Failed calls are the most useful diagnostics and currently leave no trace.

**Independent Test**: Force a call timeout, a provider error, and a cancellation; verify each emits one line with the elapsed duration and a fixed outcome.

**Acceptance Scenarios**:

1. **Given** a model call exceeds its time limit or the task's active-work budget expires during a call, **When** it is abandoned, **Then** a line with outcome `timeout` and the elapsed duration is emitted.
2. **Given** a model call fails for any other reason, **When** the failure is handled, **Then** a line with outcome `error` is emitted and contains no error text.
3. **Given** a task is canceled during a model call, **When** the call is abandoned, **Then** a line with outcome `canceled` is emitted.

### User Story 3 - Follow One Task (Priority: P2)

As an operator, I can tie a task's model calls to its final outcome line, so I can follow one task end to end.

**Why this priority**: Without correlation, lines from concurrent callers cannot be separated.

**Independent Test**: Run two tasks concurrently and verify each task's call lines and its outcome line share an identifier that differs between tasks.

**Acceptance Scenarios**:

1. **Given** a task, **When** its call lines and outcome line are emitted, **Then** all carry the same random task identifier.
2. **Given** a task continues across several caller messages, **When** lines are emitted, **Then** the identifier stays the same.
3. **Given** two tasks, **When** lines are compared, **Then** their identifiers differ and are not derived from any message, account, or caller content.

### Edge Cases

- The model service returns missing or partial usage data.
- A response has no output items, or only tool calls.
- A response requests a tool whose name is not on the known list.
- Two tasks run concurrently and their calls interleave.
- Diagnostic serialization fails while a task is in progress.
- A call is canceled at the moment it completes.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST emit exactly one diagnostic line for each model call that starts, whether it succeeds, times out, fails, or is canceled.
- **FR-002**: Each line MUST contain the UTC timestamp, the existing `model_request` step name, a non-negative integer `duration_ms`, the calling agent role (conversation or task), a call sequence number that starts at 1 for each caller message, and an outcome from the fixed set `success`, `timeout`, `error`, `canceled`.
- **FR-003**: Each successful line MUST contain non-negative integer input, output, total, cached-input, and reasoning token counts and a flag stating whether the service reported usage. When usage is not reported, token counts MUST be zero.
- **FR-004**: Each successful line MUST contain the counts of message and tool-call items in the response and, when a tool was requested, its name if it is on the application's fixed tool list, otherwise `other`.
- **FR-005**: Lines MUST NOT contain prompts, instructions, model replies, tool arguments or results, call or response identifiers, the model name, service addresses, credentials, error text, or any caller-supplied value, including account numbers and zip codes.
- **FR-006**: Every call line and the task's final outcome line MUST carry a random task identifier that is validated as 32 hexadecimal characters, is not derived from any content, and stays the same across the caller messages of one task.
- **FR-007**: Emitting these lines MUST NOT change task behavior, ordering, timeouts, retries, or results, and a serialization failure MUST NOT fail the task.
- **FR-008**: Normal automated tests MUST use deterministic fake model boundaries and MUST assert absence of sensitive content in the emitted lines.
- **FR-009**: Existing diagnostic lines, their fields, and fixed categories MUST remain compatible, except that the final outcome line gains the optional task identifier.

### Key Entities *(include if feature involves data)*

- **Model Call Record**: One content-free line describing a single model call: role, sequence number, duration, outcome, token counts, and response shape.
- **Task Identifier**: A random correlation value for one task, shared by its call records and its outcome record.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In 100% of tested tasks, the number of call lines equals the number of model calls that started, across success, timeout, error, and cancellation.
- **SC-002**: In 100% of tested successful calls, reported token counts equal the usage reported by the model service, and zero with the not-reported flag when absent.
- **SC-003**: In privacy tests, 100% of emitted lines contain no prompt, reply, tool argument, tool result, account number, zip code, error text, model name, or identifier from the model service.
- **SC-004**: In concurrent-task tests, 100% of lines can be grouped to the correct task by identifier, and no two tasks share one.
- **SC-005**: Emitting call lines adds no more than 5 ms of processing per call in tests and changes no task outcome.

## Assumptions

- Operators read stdout through an external collector, as today; no log store or new endpoint is added.
- The task identifier is random and carries no meaning; it is distinct from the account number, which remains the only permitted caller-supplied identifier and is not added to call lines.
- Tool names on the fixed list are application-owned and safe to log; any other name is reported as `other`.
- Tool-step lines, task-start lines, and aggregate metrics are out of scope for this release.
- Duration covers the span from just before the model call to just after its response, including SDK overhead.
