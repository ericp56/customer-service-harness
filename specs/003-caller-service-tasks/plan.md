# Implementation Plan: Caller Service Tasks

**Branch**: `003-caller-service-tasks` | **Date**: 2026-10-09 | **Spec**: [spec.md](spec.md)

## Summary

Add a fixed task catalog (current time, retrieve account, transfer to customer service) to the existing agent-assisted chat. The catalog is plain instruction text given to the existing manager and specialist agents. Verification rules (hard-coded accounts, three account-number attempts, two zip attempts per account, session end, support-contact choice) live in a pure, server-owned module and are exposed to the model only through strict tools, so the model cannot skip, reveal, or override them.

## Technical Context

**Language/Version**: Python 3.14. **Dependencies**: unchanged (Gradio 6.27.0, OpenAI Agents SDK 0.23.1). **Storage**: none; verification progress lives in the existing server-side transient task state. **Testing**: pytest with `ScriptedModel`; Playwright for the browser journey. **Constraints**: existing privacy, 10-second model-attempt, 60-second active-work, and 50-pair limits.

## Constitution Check

| Principle | Plan response |
|-----------|---------------|
| Customer Outcome and Experience Consistency | Fixed, clear messages for retry, final failure, and session end; reuse existing clarification and status patterns. |
| Secure Customer Data | Zip codes are never returned to the model or logged. Account numbers are the only caller-supplied identifier permitted in diagnostics, validated as digits only. |
| Code Quality and Maintainability | One pure module (`src/accounts.py`) owns the rules; tools are thin wrappers; no new dependency. |
| Testing Standards | Unit tests for every transition; deterministic scripted-model tests for the three tasks; integration and browser tests for the ended session. |
| Performance Requirements | No new external calls; existing 10-second and 60-second bounds apply. |
| Observable Service Behavior | Diagnostics gain one optional validated `account_number` field; all other fields remain content-free. |
| Simplicity and Compatibility | Hard-coded lookup table and no persistence. Manager-turn cap becomes per caller message (see Decisions). |

**Result**: PASS, with the documented diagnostics exception in Decision 4.

## Decisions

1. **Rules in code, not prompts**: `src/accounts.py` holds `CallerSession` (frozen) and pure transitions for account lookup, zip verification, and support-contact selection. `account_lookup` returns only found/not found. `verify_account_zip` compares against the current account only, so the model never supplies or receives a zip code. `getSupportContact` returns the contact for the verified account or a fixed "not verified" result.
2. **Session state**: `TaskState` carries a `CallerSession`. The app passes the previous task's session into the next task so verification and attempt counts last until the conversation is reset. Reset discards it.
3. **Ending the session**: A new `TaskStatus.SESSION_ENDED`. When the session ends, the runtime replaces the model's reply with fixed copy that says the session has ended. The app disables sending and rejects further submissions until reset.
4. **Diagnostics exception**: `Diagnostics.record` accepts an optional `account_number`, emitted only when it matches `^[0-9]{1,12}$`. Zip codes, names, and addresses have no path into diagnostics.
5. **Manager-turn budget**: The cap of eight manager turns resets on each caller message instead of accumulating across a task's clarifications, so the permitted account and zip attempts can complete. The 60-second active-time budget is unchanged.
6. **Prompts**: `src/prompts/task_catalog.md` holds the task catalog verbatim. It is appended to both agent instructions. The time wording becomes "Greenwich Mean Time".

## Rollout & Rollback

Ship behind the existing agent runtime. Roll back by reverting this feature; no data migration is needed because no state is persisted.

## Project Structure

```text
src/
├── accounts.py              # new: accounts table, CallerSession, pure transitions
├── tools.py                 # new tools; ledger carries CallerSession
├── task_runtime.py          # SESSION_ENDED, per-message turn budget, session carry-over
├── task_agents.py           # appends catalog to instructions
├── observability.py         # optional validated account_number
├── app.py                   # session-ended UI state
└── prompts/task_catalog.md  # new
tests/unit/test_accounts.py  # new
```

## Complexity Tracking

No new dependencies or services. The per-message turn budget deliberately changes an earlier aggregate-turn rule; the earlier test is updated to match.
