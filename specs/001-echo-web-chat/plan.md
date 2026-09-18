# Implementation Plan: Echo Web Chat

**Branch**: `001-echo-web-chat` | **Date**: 2026-09-16 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/001-echo-web-chat/spec.md`

## Summary

Provide an unauthenticated web chat page that returns valid visitor submissions exactly once and
unchanged. A Python 3.14 Gradio application provides the chat UI and event handling, while pure
Python validation enforces the echo rules. Conversation state is bounded and transient in the
current browser/framework runtime; no message content is durable.

## Technical Context

**Language/Version**: Python 3.14

**Primary Dependencies**: Pinned Gradio 6.x; pytest; pytest-playwright and Playwright browsers for
development-only E2E verification; k6 for release performance checks

**Storage**: N/A; content exists only in transient browser, Gradio event, and application memory
while an active page is rendered or interaction is processed

**Testing**: pytest unit/callback tests; Playwright browser E2E; k6 release-candidate load test

**Target Platform**: Linux-hosted Python application behind same-origin HTTPS ingress; current
desktop and mobile web browsers

**Project Type**: Single Python web application with a Gradio chat UI

**Performance Goals**: At least 95% of successful submissions show an echo within 1 second; 50
active sessions; every accepted submission receives one identical reply

**Constraints**: 4,096 Unicode-code-point message maximum; 50 completed pairs per active
conversation; no accounts, browser persistence, cookies, transcript storage, analytics,
request-body logging, or message-content diagnostics

**Scale/Scope**: One Gradio chat page, event callbacks, and health/readiness route; no database,
model/LLM dependency, external service, or durable data

## Constitution Check

*GATE: Passed before Phase 0 research and re-checked after Phase 1 design.*

| Principle | Plan response |
|-----------|---------------|
| Customer Outcome and Experience Consistency | The Gradio page provides clear send, error, retry, and start-new-conversation flows with accessible feedback. |
| Secure Customer Data | Only necessary in-memory framework processing is allowed; durable retention, body logging, analytics, and browser persistence are prohibited. |
| Code Quality and Maintainability | A small Python/Gradio application uses pure validation and explicit callback state, providing a direct path to later LLM/ML work. |
| Testing Standards | The plan defines narrow validation/callback tests, browser E2E coverage, and a targeted release load check. |
| Performance Requirements | Bounded history, finite queue/concurrency configuration, and 50-session p95-under-one-second verification meet the feature outcomes. |
| Observable Service Behavior | Aggregate fixed-cardinality metrics and content-free event summaries support diagnosis without retaining visitor content. |
| Simplicity and Compatibility | Gradio avoids a separate frontend; no LLM, database, or custom API is introduced before a requirement needs one. |

**Result**: PASS. No constitution violation or complexity exception is required.

## Rollout & Rollback


- Before rollout, confirm the HTTPS ingress controls, privacy configuration, browser E2E suite,
  and 50-session load scenario pass.
- During rollout, monitor only content-free response-duration, queue-depth, outcome, and health metrics.
- Roll back if fewer than 95% of successful submissions complete within one second, the queue
  saturates, or any privacy control or body-log suppression failure is detected.
- To roll back, withdraw the new application/ingress route, verify the prior route is active,
  and confirm no transient chat content was retained.


### Ingress Ownership

The platform ingress configuration, maintained outside this repository, terminates same-origin HTTPS,
uses finite connection and request timeouts, and disables request/response body logging. Deployment
approval requires platform-owner confirmation of these controls before the application route is
enabled.

## Project Structure

### Documentation (this feature)

```text
specs/001-echo-web-chat/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── echo-chat-contract.md
└── tasks.md              # Created by /speckit-tasks
```

### Source Code (repository root)

```text
src/
├── app.py                    # Gradio Blocks UI, event wiring, health configuration
├── echo.py                   # Pure validation and exact echo callback logic
└── observability.py          # Content-free metrics and event helpers

tests/
├── unit/
│   └── test_echo.py
├── integration/
│   └── test_app.py
└── e2e/
    └── test_echo_chat.py

load/
└── echo_load.js              # 50-session release-candidate scenario

pyproject.toml                # Pinned application and development dependencies
```

**Structure Decision**: Use one Python application and Gradio Blocks interface. Keep validation and
state-transition logic separate from UI event wiring so it remains independently testable and the
reply implementation can later be replaced by an LLM/ML component.


