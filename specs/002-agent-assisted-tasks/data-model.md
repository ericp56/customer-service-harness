# Data Model: Agent-Assisted Customer Tasks

**Current public UI supersession**: The original progress-status presentation below
is historical. Feature 005's 2026-10-12 refinement makes progress and actionable
validation/capacity feedback display-only assistant chat entries; see the
[current conversation contract](../../005-async-conversation/contracts/conversation-events.md).

All entities below are transient and server-owned unless described as customer-visible display text. No task, agent context, approval, tool result, or checkpoint is persisted or placed in browser storage.

## CustomerConversation

- **Purpose**: Existing ordered user/assistant messages for the current chat session.
- **Fields**:
  - `messages`: ordered displayable messages.
  - `pending_input`: valid customer input retained when the active turn needs retry/recovery.
  - `submission_state`: idle, active, waiting for customer, failed, or limited.
- **Constraints**: Preserve the existing 4,096 Unicode-code-point message maximum, blank-input rejection, safe text rendering, retry/reset behavior, and maximum 50 completed message pairs.
- **Relationships**: Owns at most one `CustomerTask` at a time.

## CustomerTask

- **Purpose**: One bounded task initiated from a customer message.
- **Fields**:
  - `task_state`: active, waiting for clarification, waiting for approval, completed, rejected, failed, canceled, or timed out.
  - `started_at`: monotonic active-work start marker.
  - `active_duration`: accumulated active processing duration; paused while awaiting customer input.
  - `turn_count`: bounded to eight conversation-manager turns.
  - `next_progress_at`: next scheduled status interval while active.
  - `checkpoint`: optional app-owned server-only in-memory continuation/approval state; never an SDK-serialized payload.
  - `completed_steps`: ordered task-step outcomes used to avoid duplicate simulated work.
  - `completed_step_results`: transient bounded results paired with completed step IDs for safe continuation after clarification or recoverable failure.
  - `continuation_context`: ordered, transient structured specialist summaries needed after clarification.
- **Constraints**: One task per conversation; maximum 60 seconds accumulated active processing; each model attempt no more than 10 seconds; no automatic retries; all state is destroyed on reset or session expiry.
- **Relationships**: Contains ordered `TaskStep` values and may reference one current `ClarificationRequest` or `ActionApproval`.

## TaskStep

- **Purpose**: A bounded requested or completed activity within a task.
- **Fields**:
  - `kind`: allowlisted date/time lookup, synthetic customer-service lookup, or simulated consequential action.
  - `state`: proposed, awaiting approval, completed, rejected, canceled, or failed.
  - `call_id`: SDK-generated capability call identifier held only in server-side task state.
  - `step_id`: strict server-validated identifier used to reject replay of an already-used task step.
  - `result`: transient server-side result; never copied to diagnostics.
  - `completion_marker`: server-owned marker used to avoid replaying a completed step after retry/resume.
- **Constraints**: At most one capability invocation is accepted per model turn; each task-specialist invocation is bounded to four turns. Every request must match a strict server-owned schema and allowlist. Synthetic lookup results are deterministic and contain no actual customer data. The simulated action has no side effect.

## ClarificationRequest

- **Purpose**: A question the customer must answer before the task can resume.
- **Fields**:
  - `question`: escaped customer-facing text.
  - `task_checkpoint`: server-only continuation information.
  - `state`: waiting or answered.
- **Constraints**: While waiting, progress updates are stopped and active duration is paused. The answer becomes transient task context only after a new customer event.

## ActionApproval

- **Purpose**: Explicit customer decision for a proposed consequential action.
- **Fields**:
  - `proposal`: concise, escaped customer-facing explanation of the simulated action.
  - `pending_step`: server-owned identifier for the exact pending simulated action.
  - `decision`: pending, approved, rejected, or canceled.
  - `consumed`: whether the decision was applied to the pending action.
- **Constraints**: Approval is per action and one-shot. Do not execute before approval; rejection/cancel never execute. Browser inputs contain only the action decision, not serialized model/tool state or arguments. No real-world effect occurs.

## ProgressStatus

- **Purpose**: Temporary accessible status shown while active work continues.
- **Fields**:
  - `activity`: optional finite application-owned phase, such as processing, information lookup, verification, or result evaluation.
  - `task_name`: optional exact title from the fixed catalog enum, only after structured output validation.
  - `text`: fixed customer-safe text rendered from the phase and optional validated name; never model-generated free text.
  - `scheduled_at`: monotonic interval marker.
  - `state`: active or stopped.
- **Ownership**: Mutable holder scoped to one active task-runtime invocation and shared only with its server-side tool ledger and UI callback.
- **Constraints**: Sample and emit every five seconds while active and not waiting. Clear or replace phases when execution advances; do not leave a completed activity as current. If activity or name is unknown, use the existing fixed fallback copy. Keep it outside customer/assistant message history; never include capability names, arguments, prompt/model details, results, or customer content.

## TaskResult

- **Purpose**: Final customer-facing result or safe recovery outcome.
- **Fields**:
  - `outcome`: completed, failed, timed out, canceled, rejected, or unsupported.
  - `text`: final accessible customer-facing response.
  - `completed_step_summary`: safe statement of known completed or not-completed work.
- **Constraints**: No internal diagnostics, raw provider output, secret, or tool payload is included.

## State Transitions

```text
IDLE -> ACTIVE
ACTIVE -> ACTIVE (bounded step complete; conversation role evaluates result)
ACTIVE -> WAITING_FOR_CLARIFICATION -> ACTIVE (customer responds, if budget remains)
ACTIVE -> WAITING_FOR_APPROVAL -> COMPLETED (customer approves the simulated step)
WAITING_FOR_APPROVAL -> REJECTED (customer rejects the simulated step)
ACTIVE -> COMPLETED | FAILED | TIMED_OUT | CANCELED
WAITING_FOR_CLARIFICATION | WAITING_FOR_APPROVAL -> CANCELED | TIMED_OUT
```

Waiting pauses the active-work clock and progress schedule. A task cannot return to `ACTIVE` after a terminal state. A completion marker prevents a completed step from being executed again when a later step fails.