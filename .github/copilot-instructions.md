# Copilot Instructions

Read and follow the repository-wide instructions in [`AGENTS.md`](../AGENTS.md)
before planning or changing this project.

This repository uses Spec Kit for spec-driven development. Use the relevant
`/speckit-*` workflow before implementing a feature or material behavior
change, and treat `.specify/memory/constitution.md` as binding project policy.
Keep the active feature's specification, plan, tasks, contracts, and code in
sync.

For application changes, preserve the repository's privacy-safe transient-chat
architecture: user and provider data must not enter diagnostics, persistence,
or browser storage; tests must use deterministic fake model boundaries; and
the state, timeout, strict-tool, accessibility, and performance invariants in
`AGENTS.md` must remain intact.
For agent-task changes, also keep task/proposal state server-side and transient,
disable SDK tracing and durable agent sessions, and ensure progress text is fixed
application copy outside the chat transcript.
For caller-service tasks, keep verification rules and attempt limits in
`src/accounts.py`, never expose or log a zip code, and log only a validated
account number.
For model-call diagnostics, emit only the fixed content-free `model_call` fields
and a random `task_id`; never log prompts, replies, tool I/O, or provider IDs.
