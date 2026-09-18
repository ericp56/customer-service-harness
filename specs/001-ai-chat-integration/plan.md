# Implementation Plan: AI Chat Integration

**Branch**: `001-ai-chat-integration` | **Date**: 2026-09-18 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/001-ai-chat-integration/spec.md`

## Summary

Replace the prototype's exact echo operation with a configurable AI-generated response. The existing
Gradio event flow and transient conversation state remain the user interface boundary; a small
server-side OpenAI client adapter will send the server-owned system context plus the complete
active-session user/assistant dialog and prior tool invocations with every user message to the
configured model. It will execute only the `getCurrentDateTimeIso` tool when requested and return
a final displayable reply. Configuration and credentials are obtained from deployment environment
variables and never exposed to the browser or diagnostics. Each operational outcome is emitted as
a sanitized UTC JSON record to stdout for an external collector; no log store is added.

## Technical Context

**Language/Version**: Python 3.14

**Primary Dependencies**: Pinned Gradio 6.27.0 and FastAPI/Uvicorn transitive application stack;
add the official `openai` Python SDK compatible with Python 3.14; pytest and pytest-playwright for
development verification

**Storage**: No durable storage. Active user/assistant dialog, tool invocations, pending retry
input, aggregate diagnostics, and emitted stdout records remain in process/current interaction
memory only; external infrastructure owns stdout collection and retention.

**Testing**: pytest unit tests for configuration, tool execution, conversation-context
serialization, and state transitions; pytest callback/integration tests with a fake AI service;
targeted Gradio configuration tests; existing Playwright smoke journeys with the AI boundary
replaced by a deterministic fake; optional credentialed provider smoke check excluded from normal
CI

**Target Platform**: Linux-hosted Python web application behind same-origin HTTPS ingress; current
desktop and mobile web browsers; outbound HTTPS access to the configured OpenAI-compatible service

**Project Type**: Single Python web application with a Gradio chat UI

**Performance Goals**: At least 95% of successful submissions display an assistant answer within
5 seconds across 100 expected-load submissions; each request has a 10-second hard timeout.
Emit content-free elapsed-millisecond diagnostics for each blocking chat-path step; preserve the
existing 50 active-session and 50-message-pair bounds.

**Constraints**: 4,096 Unicode-code-point message maximum; no accounts, browser persistence,
transcript storage, analytics, request/response-body logging, message-content diagnostics, or
client-side credentials; explicit 10-second AI-service timeout with no automatic SDK retries;
only `getCurrentDateTimeIso` is callable in the initial release

**Scale/Scope**: One existing Gradio chat page and health/readiness routes. The feature adds one
outbound model-service integration, environment-supplied configuration, fixed prompt and tool
definition files, and no new public HTTP endpoint or persistent data store.

## Constitution Check

*GATE: Passed before Phase 0 research and re-checked after Phase 1 design.*

| Principle | Plan response |
|-----------|---------------|
| Customer Outcome and Experience Consistency | The existing send, validation, retry, reset, and accessible status controls are retained. Generated answers replace only the prior echo response; failures retain the message and provide the same clear retry path. |
| Secure Customer Data | Credentials and service locations exist only in environment configuration. User content, responses, credentials, prompt values, and provider diagnostics are excluded from logs, aggregate diagnostics, browser persistence, and test fixtures that could reach the service. |
| Code Quality and Maintainability | A focused AI-service adapter isolates SDK response parsing, tool-loop validation, configuration, and provider errors from Gradio callbacks and the pure conversation state machine. The prompt and tools are separate server-owned files, avoiding duplicated policy. |
| Testing Standards | Deterministic unit and callback tests cover full active-session context, normal answers, tool calls, invalid configuration, provider timeout/unavailability, empty output, retry, and privacy-safe diagnostics. Browser tests remain limited to user-visible behavior. |
| Performance Requirements | The interactive path has an explicit 10-second service timeout, no SDK retries, bounded input/history, and existing finite Gradio queue limits. It records elapsed milliseconds for each AI request, capability execution, and blocking chat step; the release check measures the 5-second p95 target across 100 submissions. |
| Observable Service Behavior | Content-free diagnostics emit one UTC JSON stdout record with timestamp, component, level, message, elapsed duration for timed steps, and optional sanitized stack. Errors use ERROR; other outcomes use INFO; serialization failure uses a content-free text fallback. |
| Simplicity and Compatibility | The existing single application remains intact; one official client dependency and one server-side adapter are added. OpenAI-compatible services are selected by an environment-supplied base URL and must implement the chosen Responses and function-calling contract. |

**Result (pre-design)**: PASS. No constitution violation or complexity exception is required.

**Result (post-design)**: PASS. The design keeps all sensitive values server-side, creates no
durable conversation data, bounds the external request, documents failure signals and rollback, and
uses the current application seams without a second service or public API.

## Rollout & Rollback

- Before rollout, configure `OPENAI_API_KEY`, `OPENAI_MODEL`, and, when using a compatible
  provider, `OPENAI_BASE_URL`; validate the configuration without printing values, confirm outbound
  HTTPS access, and execute the quickstart checks.
- Deploy first with a low-traffic prototype environment. Monitor only aggregate outcome, duration,
  queue-depth, and readiness signals; do not capture prompts, messages, model output, headers, or
  provider response bodies.
- Roll back if the 5-second p95 responsiveness criterion or 10-second hard timeout fails, readiness reports invalid
  configuration, provider failures materially affect completion, or diagnostics/telemetry expose
  content or configuration. Restore the prior echo release or withdraw the route, verify the
  previous route serves, and confirm no conversation data was retained.

## Project Structure

### Documentation (this feature)

```text
specs/001-ai-chat-integration/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── model-service-contract.md
└── tasks.md                  # Created by /speckit-tasks
```

### Source Code (repository root)

```text
src/
├── app.py                    # Gradio UI, callback wiring, health, and privacy-safe statuses
├── chat.py                   # Pure transient conversation state and reply completion transitions
├── ai_client.py              # Validated configuration, provider boundary, response/tool loop
├── tools.py                  # getCurrentDateTimeIso implementation and tool registry
├── prompts/
│   └── system.txt            # Server-owned assistant instruction
└── observability.py          # Content-free aggregate diagnostics and readiness

tests/
├── unit/
│   ├── test_chat.py
│   ├── test_ai_client.py
│   └── test_tools.py
├── integration/
│   └── test_app.py
└── e2e/
    └── test_chat.py

load/
└── echo_load.js              # Updated 100-submission release-candidate scenario

pyproject.toml                # Pinned runtime and development dependencies
.env.example                  # Safe configuration-variable names and non-secret examples
```

**Structure Decision**: Retain the single Python/Gradio application. Rename the echo-specific
state module to `chat.py` because an assistant reply is not required to equal the input; preserve
its pure validation, bounded history, retry, and reset behavior. Keep external-model mechanics in
`ai_client.py` so tests can replace one reply-generation boundary without network access.

## Complexity Tracking

No constitution violations require justification.
