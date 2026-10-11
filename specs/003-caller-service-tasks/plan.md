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

## Catalog-Only Refinement (2026-10-11)

The conversation role performs a tool-free strict routing pass before execution. Its finite result selects a catalog task, a continuation, fixed greeting/help, or refusal; it may mark a separable unrelated portion. Routing shares the conversation model/client and diagnostics role, counts toward the eight manager turns and sixty-second active budget, and retains the ten-second model timeout. No new dependency or persistent state is introduced.

The runtime authorizes the selected task on the transient ledger. Tools enforce a fixed task/stage allowlist at invocation: time only for the time task; account lookup and zip verification for account/transfer; support contact only for verified transfer. Account and zip arguments must originate from the caller's current message, not invented agent values. `lookupServiceInformation` is not available in the public catalog runtime. Parent transfer identity survives account prerequisites.

Typed transient capability facts, caller state, and the admitted task determine application-owned replies. Arbitrary manager/specialist prose cannot become a displayed answer. Fixed account questions and mismatch/verification copy, a validated returned timestamp, and the application-selected contact cover the three catalog tasks. An unbacked completion or non-catalog proposal fails closed. Fixed greeting/help and refusal copy do not emit catalog completion records. Refusal during clarification preserves the paused task and attempt counts.

The application adds a distinct scope outcome, while retaining existing retry behavior for real operational failures. Legacy synchronous app callbacks become fail-closed rather than calling the unrestricted reply adapter. Five-second progress and existing selector IDs remain unchanged.
Completed facts are frozen and retained with the last transient submission input for exact-input failure retries. Clarification/new-input turns use fresh facts. Multi-call batches are rejected in lifecycle hooks before any dispatch. Supported-task switching while paused preserves the current task with fixed finish-or-cancel copy, not a retry loop. Refusal/help final diagnostics reuse the existing `rejected` status allowlist, omit task names and account values, and keep one final record.

### Constitution Recheck

PASS: clear non-error refusals and preserved continuation; no new sensitive diagnostic fields, storage, tracing, or sessions; pure narrow policy and typed facts; deterministic unit/integration/browser coverage; bounded extra routing latency; existing role/field allowlists; no dependencies. Semantic routing remains probabilistic, explicitly distinguished from deterministic execution/output enforcement.

### Delivery and Validation

Tasks T018-T025 are sequential except independent test preparation. Start with negative scripted-output and capability-spy tests, then routing/policy, fixed rendering, UI and legacy boundary, and browser/privacy checks. Reuse existing caller, agent, runtime, tool and callback tests. Run focused tests after each substantive edit and the full deterministic suite before completion. See `research.md`, `data-model.md`, `contracts/catalog-boundary.md`, and `quickstart.md`.

### Rollout and Rollback

Ship through the existing task callback after deterministic tests pass and review the routing prompt against the exact five examples. Optional real-provider red-team checks are not a substitute for boundary tests. Rollback reverts only this refinement, requires no migration, and restores the known general-purpose-answer risk; existing verification, reasoning, progress, and diagnostics features remain unchanged.
