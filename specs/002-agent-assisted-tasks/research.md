# Research: Agent-Assisted Customer Tasks

**Date**: 2026-10-04

## Decisions

### Agent orchestration

- **Decision**: Use the OpenAI Agents SDK with the conversation role as a manager and the task role as a bounded specialist invoked by the manager. Give each role its own model object and async client while sharing only validated configuration. Let application-owned task state and hard limits determine whether another turn is permitted.
- **Rationale**: The project already uses the OpenAI Responses API. The SDK documents manager-style agents-as-tools for a manager that retains final-answer ownership, as well as handoffs for changing which agent owns the user-facing turn. The manager/specialist pattern aligns with the requested conversation agent evaluating the task agent's result.
- **Alternatives considered**: Implement all routing and approval directly over the current Responses adapter; use LangChain; allow free-form specialist handoffs. Direct implementation duplicates SDK runner/approval mechanisms; a second framework is unnecessary; free-form handoffs weaken fixed responsibility boundaries.
- **Sources**: [OpenAI Agents SDK overview](https://openai.github.io/openai-agents-python/), [agent orchestration](https://openai.github.io/openai-agents-python/multi_agent/), [human-in-the-loop](https://openai.github.io/openai-agents-python/human_in_the_loop/).

### Gradio progress delivery and cancellation

- **Decision**: Keep the lower-level Blocks UI and implement queued asynchronous generator events that update a dedicated accessible status component separately from the Chatbot. Emit progress on a five-second timer and stop when the workflow waits or terminates. Hold testable task state on the server.
- **Rationale**: Gradio 6.27.0 supports generator event outputs, event cancellation, timers, and per-session state. ChatInterface's yielded responses are appended to chat history, so it does not fit the requirement that progress remain status rather than dialogue. Current `send_message` blocks before returning any outputs and cannot provide progress.
- **Limitations**: Gradio cancellation stops queued work or a generator between yields, not a function already executing. A long blocking step cannot provide a timely update or stop promptly. Use async model calls, short/cooperative tool steps, cancellation checks, bounded requests, and terminal-state guards. UI delivery can be delayed by event queue/network load, so the one-second tolerance applies under normal service responsiveness; test the five-second schedule and latency under expected load.
- **Sources**: [Gradio Blocks and event listeners](https://www.gradio.app/guides/blocks-and-event-listeners), [Gradio Timer](https://www.gradio.app/docs/gradio/timer), [Gradio event listeners](https://www.gradio.app/docs/gradio/state), [Gradio 6.27.0 event implementation](https://github.com/gradio-app/gradio/blob/gradio%406.27.0/gradio/events.py), [Gradio 6.27.0 chat interface implementation](https://github.com/gradio-app/gradio/blob/gradio%406.27.0/gradio/chat_interface.py).

### Pausing for approval and clarification

- **Decision**: Represent customer clarification and the simulated approval proposal as app-owned transient task state. A customer response resumes clarification with the remaining active-work budget; an approval/rejection button consumes only the currently pending simulated proposal.
- **Rationale**: The first release has no real side-effecting tool. Suspending and serializing an SDK tool call would add machinery without value for the no-op simulation. Gradio session state is server-side and transient, and the integration test proves the pending proposal is not serialized in the browser configuration.
- **Security constraints**: Never place task state, proposals, tool arguments, or customer content in browser payloads. Reject stale/replayed decisions, clear pending state on reset, and do not add durable session storage. If future real consequential tools are added, plan a separate authenticated approval workflow before execution.
- **Sources**: [Gradio State in Blocks](https://www.gradio.app/guides/state-in-blocks), [Agents SDK human-in-the-loop](https://openai.github.io/openai-agents-python/human_in_the_loop/) (reviewed; not used for this simulation).

### Privacy, sessions, tracing, and provider configuration

- **Decision**: Keep all history/checkpoints app-owned and in memory; do not use SDK persistence or OpenAI server-managed conversation IDs. Disable Agents SDK tracing globally and per run, and set sensitive trace data off as defense in depth. Configure the SDK through the existing OpenAI-compatible client/env contract.
- **Rationale**: Agents SDK sessions write run items to configured session stores; server-managed Conversations are durable provider-side history. The SDK's default tracing is enabled and its spans can contain model/tool inputs and outputs, with a default exporter. Both conflict with this repository's privacy instructions. The Agents SDK supports a custom `AsyncOpenAI` client/base URL for OpenAI-compatible endpoints.
- **Sources**: [Agents SDK sessions](https://openai.github.io/openai-agents-python/sessions/), [Agents SDK tracing](https://openai.github.io/openai-agents-python/tracing/), [Agents SDK model providers](https://openai.github.io/openai-agents-python/models/).

### SDK and runtime compatibility

- **Decision**: Pin `openai-agents==0.23.1` in implementation and verify the lock-free dependency resolution against the existing `openai==3.15.0` and Python 3.14 environment before merge.
- **Rationale**: PyPI lists Python 3.10+ support for Agents SDK 0.23.1, covering Python 3.14. The repository pins runtime dependencies, so a reproducible version is required. The SDK's manager, approval, and streaming behavior are available in the reviewed release docs.
- **Alternatives considered**: Leave the dependency unpinned or adopt experimental hosted multi-agent orchestration. Unpinned behavior undermines reproducibility; hosted multi-agent is experimental, provider-owned, and its documentation excludes SDK approval interruptions for local tools.
- **Sources**: [openai-agents on PyPI](https://pypi.org/project/openai-agents/), [Agents SDK model guidance](https://openai.github.io/openai-agents-python/models/).

## Validation Risks

- Confirm the exact dependency constraints of the pinned Agents SDK with the repository's pinned OpenAI client during implementation setup.
- Prove an Agents SDK paused `RunState` can safely remain in server-side Gradio session state across the approve/reject event without browser serialization or durable persistence.
- Verify cancellation reaches the active streamed SDK run and that the callback drains/cleans it without allowing later task steps to start.
- Verify fixed five-second status scheduling in an async Gradio generator and prevent an in-flight tick from overwriting approval/wait/final/cancel states.
- Verify test fixtures assert the observable absence of prompt, customer, model, and tool data from diagnostics, stdout, and browser storage.