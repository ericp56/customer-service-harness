# Customer Task Chat Contract

Feature 005 supersedes alternating submission and pair-limit rules for the public
application. See [conversation events](../../005-async-conversation/contracts/conversation-events.md).
Feature 005's 2026-10-12 async-notice refinement supersedes this contract's separate
status-area presentation: progress and actionable fixed notices are assistant chat
entries, are excluded from model context, and count toward the 100-entry bound.
Approval helpers remain internal harness behavior under feature 003's catalog boundary.

## Scope

This is a UI/event contract on the existing Gradio chat page. It adds no public HTTP endpoint. All chat, task, checkpoint, and approval data stays transient and server-side.

## Customer-Visible Events

| Event | Visible behavior | Conversation history |
|---|---|---|
| Accepted request | Existing user message appears once; task begins. | User message only until a final assistant answer. |
| Progress | Accessible concise fixed assistant chat message is initially published and then sampled at five-second active-work intervals only when displayed wording changes. It may include an exact validated catalog task name; unknown activity uses fixed generic copy. No caller reply is required. Optional progress is suppressed from 90 assistant entries. | Counted within the 100-assistant-entry limit; excluded from model context and diagnostics. |
| Clarification | Assistant asks one clear question and pauses active work. | Customer-facing question is a dialogue message; no progress status while waiting. |
| Approval proposal | Assistant describes the simulated consequential action and shows explicit approve/reject/cancel controls. | Customer-facing proposal is dialogue; no action runs before approval. |
| Approval/rejection | Decision applies only to the server-owned pending action and is consumed once. | Final/result dialogue follows the task outcome. |
| Cancellation | Customer can stop active work; remaining steps do not begin. | Prior messages remain; completion status reports any already-completed step. |
| Completion/failure/timeout | Accessible final or fixed recovery message appears and progress stops. | Add no partial assistant final answer on failure; preserve retryable input according to existing behavior. |

## Input and State Rules

- Preserve blank and 4,096-code-point input validation. Feature 005 bounds the
	public conversation to 50 accepted caller messages and 100 assistant entries.
- One worker is active per conversation; distinct input can arrive while it works.
	The inbox holds 10 pending messages; rapid duplicate Send/Enter is deduplicated.
	Correction/cancel/switch requires versioned Yes/No confirmation after step commit.
- Capability requests must match a strict server-owned schema and allowlist; accept at most one invocation per model turn, eight conversation-manager turns per task, and four specialist turns per delegation.
- Progress timing and terminal UI state are owned by the application; no model-provided text is used as a status update.
- Progress activity is transient to the current runtime invocation. It is updated only from actual application/SDK lifecycle events; capability identifiers are mapped to generic fixed customer-facing copy.
- Validation, capacity and fixed recovery feedback appear as accessible assistant chat entries; rejected caller input remains in the textbox. Do not add a separate visible status component or redundant status echo after a substantive assistant message.
- A validated task title may be shown only when available; missing task identity is never inferred from caller text. Display-only progress/notice entries are excluded from model context and diagnostic payloads.
- Model/task checkpoints are opaque server-side session state. They are never sent to the browser, logged, placed in URLs, or accepted from the client.
- Accepted capability call IDs, completed step IDs, bounded step results, and structured specialist findings are retained only in server-side transient task state. On clarification or recoverable retry, the manager receives prior findings plus the new customer input; those findings are not inserted into chat history or diagnostics.
- Customer clarification and approval are new UI events. While waiting, the task active-time clock is paused. Resume only if the remaining active-time budget is positive.
- Reset or session expiry discards pending clarification, approval, and checkpoint state. A discarded approval can never execute if a later session begins.
- The simulated consequential action has no external effect. Reject/cancel never produce an action result.

## Privacy and Diagnostics

- Keep credentials in existing environment variables and do not expose them in the UI.
- Disable Agents SDK tracing and avoid SDK-managed persistent sessions or provider-side conversation storage.
- Preserve the current fixed-cardinality stdout diagnostic schema and timing-step allowlist. Include only fixed categories, approved step names, and non-negative integer durations.
- Exclude all customer messages, model output, prompt text, tool arguments/results, approval content, call IDs, provider payloads, service URLs, and credentials from diagnostics and browser storage.

## Failure Behavior

| Condition | Required behavior |
|---|---|
| Unknown or malformed capability | Do not execute; stop or ask the conversation role to recover using approved capabilities; show fixed safe status if unresolved. |
| Model/tool timeout | Stop at the per-call or task bound; cancel remaining work; preserve prior messages and provide retry-safe recovery. |
| Cancel during step | Cancel active async work where possible, await cleanup, do not start another step, and report completed steps known to the server. |
| Stale/replayed approval | Reject without resuming or executing; preserve current task state. |
| Progress tick races with terminal/wait state | Terminal/wait state wins; no later tick may overwrite it. |
| Client/session reset or expiry | Drop transient conversation/task/checkpoint state; no recovery from browser or durable storage. |