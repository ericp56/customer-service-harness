# Implementation Plan: Agent-Assisted Customer Tasks

**Branch**: `002-agent-assisted-tasks` | **Date**: 2026-10-04 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/002-agent-assisted-tasks/spec.md`

**Current public UI supersession**: The separate accessible progress status-area
decision below is historical. Feature 005's 2026-10-12 refinement publishes fixed
progress and validation/capacity notices as transcript entries; see its
[conversation contract](../../005-async-conversation/contracts/conversation-events.md).

## Summary

Add a bounded multi-agent task workflow to the existing transient customer chat. Use the OpenAI Agents SDK with the configured OpenAI-compatible provider: a conversation manager delegates bounded work to a task specialist, evaluates the result, and either asks the customer for input, resolves a simulated approval, or returns a final answer. The original implementation adapted the synchronous Gradio callback to queued asynchronous work and rendered progress in a separate status area; that presentation is superseded by feature 005's transcript notices. Keep task state in server-side in-memory session state and disable agent tracing and persistent SDK sessions so user, model, tool, and approval data remain transient and do not enter SDK telemetry or browser storage.

## Technical Context

**Language/Version**: Python 3.14

**Primary Dependencies**: Gradio 6.27.0, FastAPI/Uvicorn, OpenAI Python SDK 3.15.0, OpenAI Agents SDK 0.23.1, pytest, pytest-playwright

**Storage**: No durable storage. Conversation, pending task, call/step ledger, clarification findings, and approval proposal live only in server-side in-memory Gradio session state and are cleared on reset/session expiry.

**Testing**: pytest unit tests for immutable task transitions, orchestration, timeout/cancellation, tool allowlisting, and redaction; callback/integration tests using deterministic fake agents/models/tools; Playwright tests for progress, waits, approval, cancel, completion, and privacy. No normal test calls an external provider.

**Target Platform**: Single-process Python web application behind same-origin HTTPS ingress; current desktop and mobile browsers; configured OpenAI-compatible model endpoint.

**Project Type**: Single Python Gradio web application

**Performance Goals**: Emit a customer-safe status on each five-second active-work interval, observable within one additional second under normal service responsiveness; stop progress during customer-input waits and terminal states. Bound each external model attempt to 10 seconds and each task to 60 seconds of active processing. Preserve the existing maximum 50 queued events and 50 completed chat pairs.

**Constraints**: Preserve no accounts, no transcript persistence, no browser storage, no uploads/analytics/rich content, fixed privacy-safe diagnostics, safe text rendering, 4,096-code-point input limit, retry/reset behavior, and deterministic fakes. Only existing date/time and approved synthetic fixtures are enabled. No real database, external business API, or real-world write action. No SDK tracing or durable SDK sessions. Model retries remain disabled. Enforce strict server-owned capability schemas, one capability call per model turn, at most eight manager turns per task, and at most four specialist turns per delegation.

**Scale/Scope**: One existing chat page, its status and input controls, two agent roles, fixed synthetic read-only lookups, one simulated approval-gated action, and no new public API endpoint or durable datastore.

## Constitution Check

*GATE: Passed before Phase 0 research; re-check after Phase 1 design.*

| Principle | Plan response |
|-----------|---------------|
| Customer Outcome and Experience Consistency | Keep the existing chat surface and validation/retry/reset behavior. Add clearly distinct accessible progress, clarification, approval, cancellation, final, and recovery states. |
| Secure Customer Data | Keep all task context and pending proposals server-side and transient. Disable SDK tracing; do not use SDK-managed durable sessions or server-side conversations. Keep customer/model/tool content and approval data out of diagnostics and browser storage. |
| Code Quality and Maintainability | Separate immutable task lifecycle transitions, async orchestration, model-agent definitions, and Gradio event wiring. Use one bounded specialist and strict server-owned tool registry; avoid a general plugin framework. |
| Testing Standards | Exercise lifecycle and policy via unit tests; callback and integration tests use deterministic fakes; browser tests assert observable progress, pause/resume, cancellation, approval, and privacy behavior. Add regressions for late updates and duplicate/replayed decisions. |
| Performance Requirements | Use asynchronous model calls and bounded task turns. Schedule progress independently from each model/tool step. Enforce 10-second model-attempt and 60-second active-work bounds; measure progress delivery under normal and queued load. |
| Observable Service Behavior | Preserve existing fixed diagnostic schema and allowlisted timing steps. Explicitly disable SDK trace exporting, including sensitive prompt/tool spans. Record only existing fixed outcomes and integer timing values. |
| Simplicity and Compatibility | Keep the single application and configured OpenAI-compatible provider. Add the Agents SDK because it provides local specialist delegation and structured-result primitives; retain the existing model credentials/base URL. Keep simulated approval in simple app-owned transitions. Avoid a database, workflow service, and new public API. |

**Result (pre-design)**: PASS. The added SDK is justified by manager/specialist orchestration and structured result requirements. There is no data persistence or observability exception.

**Result (post-design)**: PASS. The integration spike confirms Gradio can yield separate status, cancel active events, and hold app-owned transient task/proposal state without exposing it to the browser. No serialized SDK state or durable storage is needed.

## Architecture Decisions

1. **Manager-style agent workflow**: The customer-conversation agent remains responsible for customer-facing messages and invokes the task agent as a bounded specialist. Give each role distinct instructions, a separate model object/client, and a separate context boundary; send the task specialist only the current bounded task and necessary approved state, then return its structured result to the conversation manager for evaluation. The manager chooses continuation, clarification, approval, or final response. Limit tasks to eight manager turns and one capability call per model turn; each specialist invocation is limited to four turns. This matches the manager/specialist pattern in the Agents SDK and avoids independent, competing user-facing agents.
2. **Transient, application-owned state**: Keep conversation, task lifecycle, tool-call/step ledger, clarification findings, and the simulated approval proposal in existing server-side Gradio state. The no-op simulated action is resolved by one-shot app transitions rather than suspending an SDK tool call. Do not configure SDK sessions, OpenAI Conversations, `previous_response_id`, files, serialized SDK run state, or database-backed checkpoint storage.
3. **Progress outside the transcript**: Use a lower-level queued Blocks event that yields an accessible fixed status separately from Chatbot history. Do not use ChatInterface generator output for progress because each yielded item is treated as assistant chat content.
4. **Cooperative cancellation**: The UI cancel event cancels the queued generator; orchestration must also cancel/await the active async model run and check cancellation between bounded tools/agent turns. Never start the next step after cancellation. A currently executing external call is interruptible only through its async cancellation/timeout behavior; always report known completed actions.
5. **Approval gate**: Keep the simulated consequential proposal in server-owned task state. Require an explicit one-shot button decision, clear it on reset/expiry, and produce no real-world side effect. Never accept proposal or task state from the browser.
6. **SDK telemetry and retries**: Disable Agents SDK tracing per run and globally before any agent run. Disable automatic model retries and set the existing maximum 10-second timeout on each model call. Continue emitting only the repository's content-free stdout diagnostics.
7. **Provider compatibility**: Create a separate async OpenAI client/model object for each agent using the same existing `OPENAI_API_KEY`, `OPENAI_MODEL`, optional HTTPS `OPENAI_BASE_URL`, and `OPENAI_TIMEOUT_SECONDS` configuration. Do not adopt experimental hosted multi-agent APIs; execution and approval remain application-owned and testable.
8. **Truthful periodic progress**: Keep a small mutable, server-side progress holder scoped to one `run_customer_task` invocation and shared through its `TaskToolLedger`. SDK lifecycle hooks set finite activity phases when work actually starts/completes; the Gradio generator samples the holder only on the existing five-second tick. Map phases to fixed application copy, optionally interpolating only an already validated `TaskName`. Unknown phases/names use the existing fixed fallback rotation. Never put activity in `CallerSession`, `TaskState`, logs, browser state, or chat history; never use model/tool text, arguments, results, or identifiers as progress copy. Keep hook composition compatible with `ModelCallHooks`, and stop/clear activity on waits and terminal cleanup.

## Rollout & Rollback

- Add deterministic fake-provider tests and run them before enabling the agent runtime.
- Enable the workflow only after privacy checks prove tracing is disabled, no tool/model/customer content reaches stdout or browser storage, and a cancelled or expired session cannot resume a stale approval.
- Verify progress cadence and terminal-state precedence under normal event-queue load, then run the deterministic browser journeys and the existing 50-session/load scenario.
- Roll back to the prior single-agent chat path if progress is delayed beyond the agreed normal-load target, task/call limits fail, cancellation can start further steps, approval can replay, privacy boundaries fail, or the Agents SDK/provider configuration cannot preserve current compatible-endpoint behavior.
- Rollback requires no data migration because the feature adds no durable state; clear active in-memory task state and deploy the prior app behavior.

## Project Structure

### Documentation (this feature)

```text
specs/002-agent-assisted-tasks/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── checklists/requirements.md
├── contracts/task-chat-contract.md
└── tasks.md
```

### Source Code (repository root)

```text
src/
├── app.py                 # Gradio event wiring, progress/status/approval/cancel controls
├── chat.py                # Existing immutable conversation transitions
├── task_runtime.py        # Bounded active task, pause/resume/cancel lifecycle
├── task_agents.py         # Conversation manager and task specialist definitions
├── tools.py               # Strict current-time and synthetic fixture tools
├── ai_client.py           # Provider configuration and bounded async client
├── observability.py       # Existing content-free diagnostics and timing
└── prompts/               # Separate fixed agent instructions

tests/
├── unit/                  # Pure task lifecycle, tool policy, and adapter tests
├── integration/           # Gradio callback and fake-agent event flow
└── e2e/                   # Progress, approval, cancel, recovery, and privacy journeys
```

**Structure Decision**: Retain the single Python application and test layout. Add focused task lifecycle/orchestration modules; do not create an agent service, durable store, plugin framework, or public HTTP endpoint.

## Complexity Tracking

| Added complexity | Why needed | Simpler alternative rejected because |
|------------------|------------|-------------------------------------|
| OpenAI Agents SDK dependency | Provides bounded agent delegation and structured specialist outputs needed for the two-agent workflow. | Reimplementing runner and handoff mechanics directly over the OpenAI client would create more custom control flow and policy surface. |
| Async generator event flow | Makes periodic accessible status and cancellation possible while model operations are in flight. | The current synchronous callback cannot yield progress or respond to cancellation while blocked. |
