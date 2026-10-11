# Customer Task Chat Contract

## Scope

This is a UI/event contract on the existing Gradio chat page. It adds no public HTTP endpoint. All chat, task, checkpoint, and approval data stays transient and server-side.

## Customer-Visible Events

| Event | Visible behavior | Conversation history |
|---|---|---|
| Accepted request | Existing user message appears once; task begins. | User message only until a final assistant answer. |
| Progress | Accessible concise status appears at five-second active-work intervals and reflects the latest known active phase. It uses fixed application copy and may include an exact validated catalog task name; unknown activity uses the existing fallback rotation. Normal responsive delivery target is within one additional second. | Not added as an assistant message. |
| Clarification | Assistant asks one clear question and pauses active work. | Customer-facing question is a dialogue message; no progress status while waiting. |
| Approval proposal | Assistant describes the simulated consequential action and shows explicit approve/reject/cancel controls. | Customer-facing proposal is dialogue; no action runs before approval. |
| Approval/rejection | Decision applies only to the server-owned pending action and is consumed once. | Final/result dialogue follows the task outcome. |
| Cancellation | Customer can stop active work; remaining steps do not begin. | Prior messages remain; completion status reports any already-completed step. |
| Completion/failure/timeout | Accessible final or fixed recovery message appears and progress stops. | Add no partial assistant final answer on failure; preserve retryable input according to existing behavior. |

## Input and State Rules

- Preserve existing blank and 4,096-code-point input validation and 50-pair limit.
- Only one task may be active per conversation; duplicate submissions during active work are rejected with accessible status.
- Capability requests must match a strict server-owned schema and allowlist; accept at most one invocation per model turn, eight conversation-manager turns per task, and four specialist turns per delegation.
- Progress timing and terminal UI state are owned by the application; no model-provided text is used as a status update.
- Progress timing and terminal UI state are owned by the application; no model-provided text is used as a status update.
- Progress activity is transient to the current runtime invocation. It is updated only from actual application/SDK lifecycle events; capability identifiers are mapped to generic fixed customer-facing copy.
- The existing initial status and two-message fallback rotation remain unchanged. A validated task title may be shown only when available; missing task identity is never inferred from caller text.
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