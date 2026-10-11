# Catalog Boundary Research

## Decisions

- **Tool-free admission**: Reuse the conversation model for strict finite routing before exposing delegation. Prompt-only refusal was rejected because the runtime accepts arbitrary completed replies today. Routing is a semantic interpretation, not proof of caller intent.
- **Invocation authorization**: Enforce catalog task and caller-state prerequisites in tools, not progress hooks or model-supplied task names. Remove the unused generic lookup from public execution.
- **Fixed rendering**: The three tasks have a small fixed output vocabulary. Render validated timestamp/contact and verification outcomes in application code rather than adding another probabilistic output classifier. Store typed facts separately from textual tool history.
- **Transient input provenance**: Only current-message account/zip values can be submitted by tools. Neither previous transcript instructions nor model-invented values authorize verification.
- **Refusal is dialogue**: Preserve paused verification on diversions, do not increment attempts, offer no Retry, and use fixed diagnostics without task names for standalone refusals/help.
- **Legacy boundary**: The sync app callbacks are not wired into Blocks, but directly call a general-purpose adapter. Make them fail closed rather than introduce an event-loop bridge or maintain two task runtimes.

## Constraints and Alternatives

No new dependency, model role, provider storage, SDK sessions, tracing, browser persistence, or diagnostic content. Admission consumes one bounded conversation-model turn; execution shares the remaining eight-turn/sixty-second budget. A third classifier or unrestricted model-response sanitizer would add latency without deterministic output guarantees. Pure regex-only natural-language routing would reject normal phrasing and contextual replies.

Deterministic tests establish the execution/rendering boundary, not real-provider classification accuracy. Optional deployment red-team testing must be reported separately and never log request/reply content.