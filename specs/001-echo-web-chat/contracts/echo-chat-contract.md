# Echo Chat UI and Callback Contract

## Message Input

The chat accepts text-only input. It must contain at least one non-whitespace Unicode character and
no more than 4,096 Unicode code points. Validation inspects whitespace only; accepted content is
returned without trimming, normalization, or other alteration.

## Success Behavior

For every accepted submission, the callback returns an echo equal to the original content. The UI
appends exactly two ordered chat messages:

```text
{"role": "user", "content": <accepted original>}
{"role": "assistant", "content": <identical echo>}
```

Input and pending state clear only after the pair is successfully appended.

## Validation and Operational Failure Behavior

| Condition | Required UI result |
|-----------|--------------------|
| Blank input | Add no messages; identify the input error in text and keep input focus available. |
| More than 4,096 code points | Add no messages; state the documented limit in an accessible error. |
| Operational or framework failure | Add no messages; preserve completed history and exact valid input; expose a keyboard-reachable Retry control. |
| Callback output is not the exact input | Treat as operational failure; append nothing and provide Retry. |
| 50 completed pairs reached | Preserve history, prevent another submit, and expose an accessible Start New Conversation control. |

While a request is in progress, another submission must not duplicate or reorder messages. Retry
uses retained pending input and must not duplicate a pair.

## Rendering and Transient-State Contract

Render content as text, never Markdown, HTML, or rich content; line breaks remain visible. History,
pending text, and event payloads may exist only in transient browser, Gradio, and application
memory. Disable analytics, sharing, feedback/flagging, history restoration, uploads, and
application-created persistence. Reload, session expiry, or process restart starts an empty chat.

## Operational Contract

Run behind same-origin HTTPS ingress with finite connection/request timeouts and no request/response
body logging. Diagnostics may contain fixed event/result names, duration, queue depth, health, and
aggregate counts; they never contain message content, client identifiers, cookies, user agents, or
serialized exception values that could include input.
