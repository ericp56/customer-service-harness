# Implementation Plan: Expanded Customer Service Options

**Branch**: `006-customer-service-expansion` | **Date**: 2026-10-21 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/006-customer-service-expansion/spec.md`

## Summary

Expand the fixed customer-service catalog with account profile retrieval and updates, synthetic card-on-file toggles, and per-account support cases. Keep the existing time and identity-verification behavior. Store deterministic records in a conversation-scoped server-side snapshot; route reads through strict capability policy and stage every write as a version-bound, one-shot application mutation requiring explicit approval. No real payment integration, durable storage, or external case system is introduced.

## Technical Context

**Language/Version**: Python 3.14

**Primary Dependencies**: Existing Gradio 6.27.0, OpenAI Python SDK 3.15.0, OpenAI Agents SDK 0.23.1, Pydantic, pytest, pytest-playwright; no new dependencies

**Storage**: Transient server-side `SessionCoordinator` state only; discard on reset, expiry, or process restart

**Testing**: Deterministic pytest unit/integration tests with `ScriptedModel` and fake boundaries; Playwright e2e; optional k6 load scenario

**Target Platform**: Existing single-process Python web application, desktop and mobile browsers

**Project Type**: Single Python Gradio web application

**Performance Goals**: Preserve existing 10-second model-attempt and 60-second active-task bounds, eight manager turns per processing batch, four specialist turns, and fixed five-second progress sampling

**Constraints**: Preserve privacy-safe diagnostics, no browser storage or durable persistence, strict tool schemas, account verification attempts, one capability per model turn, async event ordering, safe text rendering, 50 accepted callers, 100 assistant entries, 10-event inbox, 4,096-code-point input; bound synthetic case data and field lengths per spec

**Scale/Scope**: One existing chat surface, two synthetic accounts, at most 20 cases per conversation and 10 updates per case; no new endpoints or persistent service

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Plan response |
|-----------|---------------|
| Customer Outcome and Experience Consistency | Preserve existing flows; add explicit verification, clarification, approval, empty, completion and recovery states for each grouped task. |
| Secure Customer Data | Keep profiles, preferred names, case text and pending mutations in transient server state; never log or place them in browser storage. Zip values remain private verification data. No real card data is accepted. |
| Code Quality and Maintainability | Keep pure synthetic record transitions separate from caller verification; use finite capability allowlists, typed results and fixed rendering. Avoid a generic CRUD/plugin framework. |
| Testing Standards | Add deterministic pure state tests, fake-model tool-policy tests, callback integration tests and browser journeys covering authorization, approvals, privacy and recovery. |
| Performance Requirements | Retain existing per-call/task/turn limits and add strict case/description/update bounds to keep work finite. |
| Observable Service Behavior | Add only fixed catalog task names to existing enums; preserve diagnostic field allowlists and exclude all customer/model/tool content. |
| Simplicity and Compatibility | Reuse the current chat, task runner and event contract. Add no dependency, database, external payment/case integration, or public endpoint. Feature 006 supersedes only the three-task catalog restriction from feature 003. |

**Gate**: PASS. Synthetic state and verified writes are compatible with the architecture when mutations remain app-owned and transient; no constitution exception is needed.

## Project Structure

### Documentation (this feature)

```text
specs/006-customer-service-expansion/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/customer-service-catalog.md
├── checklists/requirements.md
└── tasks.md
```

### Source Code (repository root)
```text
src/
├── accounts.py             # Existing identity verification authority and attempt limits
├── customer_data.py        # Immutable synthetic profiles/cases and pure bounded transitions
├── catalog_policy.py       # Fixed task allowlists, typed facts and safe reply construction
├── tools.py                # Strict application-owned capability schemas and ledger
├── task_agents.py          # Fixed routing, prompts and structured task results
├── task_runtime.py         # Bounded execution, server facts and task outcomes
├── conversation_runtime.py # Per-conversation sample data, approval and event ordering
├── observability.py        # Existing fixed diagnostics schema and catalog enum
└── prompts/
  ├── task_catalog.md
  └── task_router.txt

tests/
├── unit/
├── integration/
└── e2e/
```

**Structure Decision**: Extend the existing single Python application. Add `src/customer_data.py` to own synthetic profile/case records independently of identity verification in `src/accounts.py`; keep coordinator ownership and mutation approval in the existing transient session runtime. Extend neighboring tests rather than introducing a new test framework or service.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| None | N/A | No constitution violations or new platform dependencies are proposed. |
