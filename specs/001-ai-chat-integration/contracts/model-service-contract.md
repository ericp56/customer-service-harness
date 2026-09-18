# Model Service Contract

## Purpose

Defines the server-side boundary between the web chat and a configured OpenAI-compatible
conversational model service. This is an outbound integration contract; the application exposes no
new public endpoint.

## Configuration Contract

| Environment variable | Required | Contract |
|---|---|---|
| `OPENAI_API_KEY` | Yes | Non-empty credential supplied only by the deployment environment. |
| `OPENAI_MODEL` | Yes | Non-empty model identifier accepted by the configured service. |
| `OPENAI_BASE_URL` | No | HTTPS base URL for an OpenAI-compatible service; omitted selects the hosted OpenAI default. |
| `OPENAI_TIMEOUT_SECONDS` | No | Positive timeout in seconds; defaults to and may not exceed `10`. |

Missing, malformed, or unusable configuration makes readiness `not_ready`, emits an
`invalid_configuration` diagnostic outcome, and produces a fixed retry-oriented chat error if a
submission is attempted. No configuration value is returned to the browser or diagnostics.

## Request Contract

For each accepted user submission, the adapter sends:

| Element | Contract |
|---|---|
| Model | The validated `OPENAI_MODEL` value. |
| Instructions | Fixed server-owned assistant policy from `src/prompts/system.txt`. |
| Input | The server-owned system context plus the complete ordered active-session user/assistant dialog, every prior tool invocation and result, and the submitted user message; no cross-session data. |
| Tools | Only the strict, no-argument `getCurrentDateTimeIso` function definition. |
| Timeout/retries | A 10-second upper bound and no automatic retry. |

The selected service must support the OpenAI Responses request format and strict function calling.

## Tool-Call Contract

1. The adapter accepts only a `getCurrentDateTimeIso` function call with an empty argument object.
2. It returns one `function_call_output` associated with the supplied call ID. The output contains
   the current UTC date-time in ISO 8601 format.
3. It retains each accepted invocation and result as active-session context so every later model
   submission includes the complete tool-invocation history.
4. The adapter performs at most one tool round trip per chat submission.
5. Unknown functions, arguments, malformed call data, repeated tool loops, or a missing final
   displayable answer are unusable-response failures.

## Response and Failure Contract

| Service outcome | Application result | User-visible result |
|---|---|---|
| Final non-empty assistant text | Append exactly one user/assistant pair in order. | Assistant text appears in the chat. |
| Timeout, connection failure, status error, or rejected credential | Preserve prior history and pending input. | Fixed accessible retry message with no provider details. |
| Missing/invalid configuration | Preserve prior history and pending input; readiness is `not_ready`. | Fixed accessible retry message with no configuration details. |
| Malformed, disallowed-tool, or empty model result | Preserve prior history and pending input. | Fixed accessible retry message with no provider details. |

All failure paths record only fixed diagnostic categories, timing step names, elapsed durations,
duration buckets, queue-depth buckets, and health state. They do not retain or surface message
content, assistant content, prompts, credentials, service URLs, request IDs, headers, stack
traces, or provider response bodies.

## Diagnostic Output Contract

Each operational outcome writes one JSON object to stdout with UTC `timestamp`, `component`,
`level`, and `message`. Caught exceptions use `ERROR` and include an optional sanitized `stack`;
all other records use `INFO`. Records must exclude API keys, service URLs, request/response bodies,
chat messages, prompts, tool outputs, provider metadata, secrets, and customer content. If JSON
serialization fails, write a content-free text line to stdout and continue the chat flow.

The adapter emits a separate `INFO` record after each Responses API invocation and permitted tool
execution; the application emits an `INFO` record after each complete chat-submission path.
Timed records contain a fixed `step` name and non-negative integer `duration_ms`, measured using a
monotonic clock. The permitted values are `model_request`, `date_time_tool`, and
`chat_submission`; no timing record may include inputs, outputs, call IDs, request IDs, or
provider-provided identifiers.
