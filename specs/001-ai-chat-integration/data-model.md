# Data Model: AI Chat Integration

## ChatMessage

Represents one user submission or final assistant response in the current transient conversation.

| Field | Type | Rules |
|-------|------|-------|
| `role` | `user` or `assistant` | Each completed exchange contains a user message followed by an assistant message. |
| `content` | text | User content must contain a non-whitespace character and no more than 4,096 Unicode code points. Assistant content must be non-empty after trimming. |

**Relationship**: Ordered messages belong to one `ActiveConversation`. They exist only in the
current browser/application interaction and are never written to diagnostics or durable storage.

## ActiveConversation

Represents the bounded state of one active browser chat interaction.

| Field | Type | Rules |
|-------|------|-------|
| `history` | ordered conversation-context collection | Contains the complete user/assistant dialog and tool invocations for the active session; maximum 50 completed user/assistant pairs. |
| `pending_text` | text or absent | Holds one validated user message only while submitting or awaiting retry. |
| `submission_state` | state enum | `idle`, `sending`, `failed`, or `limit_reached`. |

**State transitions**:

```text
idle --valid submission--> sending --final usable reply--> idle or limit_reached
                         \--service/configuration/response failure--> failed
failed --retry--> sending
failed --new conversation--> idle
limit_reached --new conversation--> idle
```

No completed message pair is added on validation or operational failure. A successful retry adds
exactly one pair for the retained pending text. Each model submission receives the server-owned
system context and this complete active-session history.

## AIServiceConfiguration

Represents validated server-only deployment configuration. It is constructed for each process
start or request from environment values and must not be included in UI state, chat history,
diagnostics, or exception messages.

| Field | Source | Validation |
|-------|--------|------------|
| API key | `OPENAI_API_KEY` | Required, non-empty secret. |
| Model identifier | `OPENAI_MODEL` | Required, non-empty text. |
| Service base URL | `OPENAI_BASE_URL` | Optional HTTPS URL; default is the hosted OpenAI service. |
| Request timeout | `OPENAI_TIMEOUT_SECONDS` | Optional positive number; default and maximum for this feature: 10 seconds. |

## AssistantPolicy

Represents fixed server-owned behavioral instructions loaded from `src/prompts/system.txt`. Its
required content directs the assistant to be helpful, answer questions, and not reveal its inner
workings to a client. It is not editable by chat users.

## AssistantCapability

Represents an action the model may request during a response.

| Field | Value/rule |
|-------|------------|
| Name | `getCurrentDateTimeIso` |
| Inputs | None; any supplied arguments are rejected. |
| Output | Current UTC date and time as an ISO 8601 timestamp. |
| Authorization | The only permitted capability in this release. |
| Invocation limit | At most one date-time tool round trip per user submission. |

## ToolInvocation

Represents a requested and completed assistant capability call in the active-session conversation
context. It is not shown as a chat message and is never written to diagnostics or durable storage.

| Field | Rules |
|-------|-------|
| Capability name | Must be `getCurrentDateTimeIso`. |
| Call identifier | Preserved with the invocation and matching result so later model submissions retain the complete tool history. |
| Arguments | Empty object only. |
| Result | Current UTC date and time as an ISO 8601 timestamp. |

## DiagnosticEvent

Represents an aggregate, content-free operational signal emitted to stdout for an external
collector; the application keeps no durable log store.

| Field | Rules |
|-------|-------|
| `timestamp` | UTC ISO 8601 timestamp. |
| `component` | Fixed component name. |
| `level` | `INFO` for non-errors; `ERROR` for caught exceptions. |
| `message` | Fixed content-free outcome message; for errors, a sanitized error message. |
| `stack` | Optional sanitized filename/source-location frames for caught exceptions. |
| `step` | Optional fixed, allowlisted blocking-step name; never derived from a request, tool, provider, or customer value. |
| `duration_ms` | Optional non-negative integer elapsed milliseconds for a timed blocking step. |
