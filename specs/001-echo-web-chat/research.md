# Research: Echo Web Chat

**Date**: 2026-09-16

## Decision: Use Python 3.14 and Gradio Blocks

Use Python 3.14 and a pinned Gradio 6.x release. Build the UI with `gr.Blocks`,
`gr.Chatbot(type="messages")`, a text-only `gr.Textbox`, and explicit Send, Retry, and Start New
Conversation controls.

**Rationale**: Python establishes the requested foundation for later LLM and ML features. Gradio
provides a web chat experience without a separate frontend, while Blocks event wiring retains
control of validation, pending input, retry, and exact append ordering. Its message-dictionary
shape (`user` and `assistant` content) also aligns with common LLM APIs.

**Alternatives considered**: `gr.ChatInterface` is concise but hides state handling needed for
retry and append-after-success. A custom frontend adds a separate technology surface without
current benefit. A model/LLM dependency is intentionally deferred.

## Decision: Permit only bounded, ephemeral Gradio state

Content may exist in a browser component, in-flight Gradio event payload, and application memory
while a current interaction is rendered or processed. It must not be written to disk, browser
storage, cookies, logs, analytics, traces, databases, caches, external queues, or persisted Gradio
artifacts. Reload, session expiry, or process restart discards it.

**Rationale**: Gradio uses transient request/session and event-queue handling to operate. This
allows only needed in-memory processing while preserving the no-durable-retention promise.

**Alternatives considered**: Durable transcripts and browser storage require retention,
authorization, and deletion designs outside this milestone.

## Decision: Bound messages and conversation history

Accept at most 4,096 Unicode code points per message and 50 completed user/assistant pairs per
conversation. Validate at the callback boundary and preserve accepted text without trimming or
normalization. At the pair limit, retain visible history and require an explicit new conversation.

**Rationale**: The message limit is a clear user boundary. The history cap prevents unbounded
Gradio event payload and in-memory growth while preserving normal active-session recovery.

**Alternatives considered**: Raw JSON API limits do not apply because Gradio owns the event
protocol. Unlimited history conflicts with bounded interactive work.

## Decision: Configure Gradio for privacy and performance

Disable analytics, share links, feedback/flagging, uploads, rich-text/Markdown rendering, history
restoration, and application-created persistence. Configure a finite queue and a concurrency limit
of at least 50 for the stateless echo handler. Use same-origin HTTPS ingress with finite timeouts
and disabled body logging.

**Rationale**: Gradio queues events by default and its default single-event concurrency is not
suitable as an unexamined setting for 50 sessions. Disabling optional capture/sharing features
protects the privacy boundary; text-only rendering preserves input safely.

**Alternatives considered**: Default queue settings, analytics, and share links add privacy or
performance uncertainty. Multi-replica operation is deferred because it requires session affinity.

## Decision: Verify at narrow layers

Use pytest for validation/callback tests, pytest-playwright for browser E2E, and k6 for release
performance checks.

**Rationale**: These layers directly verify exact echo behavior, accessible feedback, retry,
session-only history, and the p95 target. k6 runs are proportionate for releases or infrastructure
changes rather than every UI edit.

**Alternatives considered**: A broader framework stack or distributed tracing adds dependencies or
privacy risk without improving this single-application feature.

## Sources

- [Python version status](https://devguide.python.org/versions/)
- [Gradio Blocks](https://www.gradio.app/docs/gradio/blocks)
- [Gradio Chatbot](https://www.gradio.app/docs/gradio/chatbot)
- [Gradio queuing](https://www.gradio.app/guides/queuing)
- [Playwright for Python](https://playwright.dev/python/docs/intro)
- [WCAG 2.2 error identification](https://www.w3.org/WAI/WCAG22/Understanding/error-identification.html)
- [WCAG 2.2 status messages](https://www.w3.org/WAI/WCAG22/Understanding/status-messages.html)
