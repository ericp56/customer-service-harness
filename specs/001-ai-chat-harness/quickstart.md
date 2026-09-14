# Quickstart: Conversational AI Task Harness

## Prerequisites

- Python 3.13
- Access to the organization's development identity provider
- A local PostgreSQL instance or approved development database
- Development credentials for an approved AI provider; never place them in source control

## Setup

1. Create the local environment and install the project with development dependencies:

   ```bash
   python3.13 -m venv .venv
   source .venv/bin/activate
   pip install -e ".[dev]"
   ```

2. Provide local configuration for the database, organizational identity integration, AI provider,
   encryption, and telemetry. Confirm that public sharing is disabled.

3. Initialize the local database using the project's migration command, then start the service:

   ```bash
   python -m harness.app
   ```

## End-to-End Validation

1. Sign in with a test internal identity and begin a new conversation.
2. Submit a clear multi-step request. Confirm that the chat presents an objective, assumptions,
   ordered steps, and their initial statuses as defined in the
   [interface contract](contracts/chat-harness-contract.md).
3. Submit an ambiguous request. Confirm that the harness asks focused questions rather than
   presenting a ready plan.
4. Revise a pending plan step. Confirm that the changed plan receives a new revision, the impact
   is summarized, and prior approvals cannot be reused.
5. Attempt a consequential action. Confirm that it cannot proceed before explicit user approval
   and that duplicate approval submissions result in one effect attempt at most.
6. Interrupt and resume a conversation. Confirm that the current plan and next step remain
   available.
7. Cause a dependency failure. Confirm that the relevant step is blocked and the chat provides a
   recovery action without exposing sensitive information.

## Automated Validation

Run the automated suite:

```bash
pytest
```

Run the load scenario for 50 active conversations using the project load-test command. Confirm
that at least 90% of clear requests receive a reviewable plan within 10 seconds and inspect queue
wait, provider failure, and privacy-safe telemetry. See [data-model.md](data-model.md) for state
and confirmation invariants.
