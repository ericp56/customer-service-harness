# Implementation Plan: Model Call Diagnostics

**Branch**: `004-model-call-diagnostics` | **Date**: 2026-10-09 | **Spec**: [spec.md](spec.md)

## Summary

Emit one content-free JSON line per model call from the agent runtime, using the Agents SDK lifecycle hooks, and tie each task's call lines to its outcome line with a random task identifier. Include explicit safe progress snapshots on model-call records and one final outcome record for every caller-message runtime invocation. Support an optional validated `OPENAI_REASONING` effort across agent and synchronous calls. Failed, timed-out, and canceled calls are recorded from the runtime's existing exception handling because the SDK does not call the end hook for them.

## Technical Context

**Language/Version**: Python 3.14. **Dependencies**: unchanged (OpenAI Agents SDK 0.23.1). **Storage**: none. **Testing**: pytest with `ScriptedModel` (supports scripted `Usage`). **Constraints**: existing privacy invariants; no new endpoint, log store, or dependency. `OPENAI_REASONING` is optional, accepts only the pinned SDK effort literals, and is omitted when unset/blank.

## Constitution Check

| Principle | Plan response |
|-----------|---------------|
| Secure Customer Data | Lines carry fixed metadata and an explicit task snapshot allowlist; no caller values, prompts, replies, results, proposals, or provider identifiers. |
| Observable Service Behavior | Directly advances this principle: correlated, structured, privacy-safe diagnostics for external model calls with actionable failure signals. |
| Testing Standards | Observable tests assert exact line counts, token values, and absence of sensitive strings. |
| Performance Requirements | One synchronous stdout write per call and caller-message outcome; no extra network or model work; call logging overhead remains within 5 ms in tests. |
| Simplicity and Compatibility | One small module and one emitter; existing lines unchanged apart from an optional field. |

**Result**: PASS.

## Decisions

1. **Hooks, not model subclassing**: `RunHooks.on_llm_start` and `on_llm_end` fire for every model call, including those of the specialist run nested inside the delegate tool when hooks are passed to both `Runner.run` and `as_tool`. This also works with `ScriptedModel`.
2. **One hook class per role, one recorder per run**: `ModelCallHooks(role)` is static; the per-run `ModelCallRecorder` (task identifier, per-message call counter, manager-turn counter, the open call, and an optional snapshot callback) is held in a context variable set by `run_customer_task`. This keeps agent construction unchanged for tests that inject agents.
3. **Failures from the runtime**: the runtime's timeout and exception branches close the open call as `timeout` or `error`; the final cleanup closes any remaining open call as `canceled`. Closing is a no-op when no call is open.
4. **Emitter in observability**: `record_model_call` builds the line from validated, typed values only and swallows serialization errors, keeping the fixed field allowlist beside the existing diagnostics code.
5. **Task identifier**: `TaskState.task_id` (random hex) is created in `begin_task`, preserved on resume, and shared by call records, runtime `task_outcome` records, and existing app outcome records.
6. **Tool names**: allowlist is derived from the registered tools plus the delegate tool; anything else is `other`.
7. **Reasoning effort**: validate the trimmed value against `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, and `max`. Omit reasoning when unset or blank. Pass a configured value to `ModelSettings` and to every synchronous Responses request, including follow-ups. Do not probe model compatibility or fall back; the operator selects a supported model/effort combination.
8. **Task snapshots**: define a frozen diagnostic snapshot with only task status, active and remaining milliseconds, turn/capability/completed-step counts, approval-pending, account/zip attempt counts, account-verified, and session-ended. Derive it explicitly from immutable state and the live tool ledger. Never serialize `TaskState`, caller state, or ledger objects directly.
9. **Sampling semantics**: a model-call snapshot observes state as its response returns, before requested tool calls run. A final `task_outcome` line records the post-transition state for every runtime caller message, including early return and cancellation. Wall duration and active-work duration remain distinct.
10. **Failure handling**: invalid reasoning configuration uses the fixed `invalid_configuration` category; model/provider rejection uses existing fixed failure records without raw exception detail. Diagnostics remain best-effort and cannot alter task behavior.

## Rollout & Rollback

No data or contract migration. Roll back by reverting the change; existing lines are unaffected.

## Project Structure

```text
src/
├── model_diagnostics.py   # hooks, per-run recorder
├── observability.py       # record_model_call snapshots and task_outcome
├── ai_client.py           # optional OPENAI_REASONING validation and request setting
├── task_agents.py         # pass specialist hooks to as_tool
├── task_runtime.py        # live safe snapshots and final caller-turn outcome
└── app.py                 # map invalid configuration to fixed diagnostic category
tests/unit/test_ai_client.py
tests/unit/test_model_diagnostics.py
tests/unit/test_observability.py
```

## Complexity Tracking

No new dependencies. One context variable avoids threading a recorder through agent construction.
