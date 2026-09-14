# Implementation Plan: Conversational AI Task Harness

**Branch**: `001-ai-chat-harness` | **Date**: 2026-09-13 |
**Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/001-ai-chat-harness/spec.md`

## Summary

Build an authenticated internal web chat where users submit requests, receive validated plans, and
work through those plans in a persistent conversation. The system will use a Python service with a
Gradio chat interface mounted in FastAPI, PostgreSQL as the authoritative store, a provider-neutral
LLM adapter, and a confirmation-gated execution state machine for consequential actions.

## Technical Context

**Language/Version**: Python 3.13

**Primary Dependencies**: FastAPI, Gradio 6.27.0, Pydantic 2, an OpenAI-compatible AI client,
SQLAlchemy, OpenTelemetry

**Storage**: PostgreSQL for authoritative conversation, plan, confirmation, and audit state;
SQLite/WAL only for local single-instance development

**Testing**: pytest, property-based tests for validation and state transitions, browser end-to-end
tests, and load tests simulating 50 active conversations

**Target Platform**: Containerized Linux web service behind the organization's authenticated reverse
proxy

**Project Type**: Web application

**Performance Goals**: 90% of clear requests receive a reviewable plan within 10 seconds; support
50 concurrent active conversations; measure and control queue wait, response latency, and provider
errors

**Constraints**: Use organization-managed OIDC identity; no public share links; require explicit,
single-use confirmation for consequential actions; retain no sensitive content in logs or telemetry

**Scale/Scope**: First release serves authenticated internal desktop users with conversational
planning, resumable plans, and confirmation-gated in-scope actions

## Constitution Check

*GATE: Passed before Phase 0 research. Re-checked after Phase 1 design: passed.*

| Principle | Design response |
|-----------|-----------------|
| Customer Outcome and Experience Consistency | Plans, step statuses, errors, revisions, and recovery actions use a single consistent lifecycle and user-visible vocabulary. |
| Secure Customer Data | OIDC-protected access, server-side authorization, encrypted stored content, redacted telemetry, and confirmation records bound to identity and plan revision protect conversation data. |
| Code Quality and Maintainability | Domain state transitions, provider adapters, persistence, and UI are separate modules with explicit interfaces and no agent framework as the system of record. |
| Testing Standards | Unit, property, adapter contract, database concurrency, browser, and load coverage test every behavior and confirmation boundary. |
| Performance Requirements | The plan defines queue limits, timeout behavior, latency instrumentation, and a 50-active-conversation load target. |
| Observable Service Behavior | Correlated traces and structured, redacted events cover request, model, plan, confirmation, and effect outcomes. |
| Simplicity and Compatibility | A single web service and PostgreSQL database meet the initial need; provider-specific capabilities stay behind a minimal adapter. |

## Project Structure

### Documentation (this feature)

```text
specs/001-ai-chat-harness/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── chat-harness-contract.md
└── tasks.md
```

### Source Code (repository root)

```text
src/harness/
├── api/
│   ├── auth.py
│   └── routes.py
├── domain/
│   ├── models.py
│   ├── plan_validation.py
│   └── state_machine.py
├── services/
│   ├── conversation_service.py
│   ├── planning_service.py
│   ├── confirmation_service.py
│   └── execution_service.py
├── adapters/
│   ├── llm.py
│   ├── persistence.py
│   └── effects.py
├── ui/
│   └── chat.py
├── observability.py
└── app.py

tests/
├── unit/
├── contract/
├── integration/
├── e2e/
└── load/
```

**Structure Decision**: Use one web application. Domain and service modules own business rules;
adapters isolate AI providers, persistence, and external effects; the Gradio UI is limited to
presentation and interaction state.

## Complexity Tracking

No constitution violations require justification.
