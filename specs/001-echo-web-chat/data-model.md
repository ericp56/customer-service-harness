# Data Model: Echo Web Chat

The feature has no persistent data model. Values are transient in the rendered browser page, Gradio
event processing, or application memory, and must not be written to browser storage, cookies, logs,
analytics, traces, databases, files, caches, queues, or persisted artifacts.

## Submitted Message

| Field | Type | Rules |
|-------|------|-------|
| `content` | String | Required; contains a non-whitespace character; at most 4,096 Unicode code points; preserved exactly if accepted. |

Blankness uses whitespace inspection only. The original accepted value is never trimmed, normalized,
or transformed.

## Conversation Message

| Field | Type | Rules |
|-------|------|-------|
| `role` | `user` or `assistant` | Identifies the Gradio-compatible visible origin. |
| `content` | String | Accepted original text or its identical echo, rendered as text rather than markup. |

List position determines order. Success appends exactly one `user` message followed by one
`assistant` message.

## Active Conversation State

| Field | Type | Rules |
|-------|------|-------|
| `history` | Ordered message list | Transient current-page/framework state; maximum 50 completed pairs. |
| `pending_text` | String or absent | Exact valid input retained after operational failure; clears after success or explicit reset. |
| `submission_state` | `idle`, `sending`, `failed`, or `limit_reached` | Controls Send, Retry, and Start New Conversation availability. |

## State Transitions

```text
idle --valid submit--> sending
sending --successful exact echo--> idle + append user/assistant pair + clear input
sending --operational/framework failure--> failed + retain input + no new messages
failed --retry--> sending
idle/failed --blank or overlength submit--> same state + accessible validation + no new messages
idle --50th completed pair--> limit_reached
limit_reached --start new conversation--> idle + empty history and pending input
```

Only a successful exact echo appends messages. Reload, session expiry, and process restart discard
the transient state.
