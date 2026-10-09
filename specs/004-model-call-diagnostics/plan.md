# Implementation Plan: Model Call Diagnostics

**Branch**: `004-model-call-diagnostics` | **Date**: 2026-10-09 | **Spec**: [spec.md](spec.md)

## Summary

Emit one content-free JSON line per model call from the agent runtime, using the Agents SDK lifecycle hooks, and tie each task's call lines to its outcome line with a random task identifier. Failed, timed-out, and canceled calls are recorded from the runtime's existing exception handling because the SDK does not call the end hook for them.

## Technical Context

**Language/Version**: Python 3.14. **Dependencies**: unchanged (OpenAI Agents SDK 0.23.1). **Storage**: none. **Testing**: pytest with `ScriptedModel` (supports scripted `Usage`). **Constraints**: existing privacy invariants; no new endpoint, log store, or dependency.

## Constitution Check

| Principle | Plan response |
|-----------|---------------|
| Secure Customer Data | Lines carry metadata only and an allowlisted field set; no caller values, prompts, replies, or provider identifiers. |
| Observable Service Behavior | Directly advances this principle: correlated, structured, privacy-safe diagnostics for external model calls with actionable failure signals. |
| Testing Standards | Observable tests assert exact line counts, token values, and absence of sensitive strings. |
| Performance Requirements | One synchronous stdout write per call; no extra network or model work. |
| Simplicity and Compatibility | One small module and one emitter; existing lines unchanged apart from an optional field. |

**Result**: PASS.

## Decisions

1. **Hooks, not model subclassing**: `RunHooks.on_llm_start` and `on_llm_end` fire for every model call, including those of the specialist run nested inside the delegate tool when hooks are passed to both `Runner.run` and `as_tool`. This also works with `ScriptedModel`.
2. **One hook class per role, one recorder per run**: `ModelCallHooks(role)` is static; the per-run `ModelCallRecorder` (task identifier, per-message call counter, the open call) is held in a context variable set by `run_customer_task`. This keeps agent construction unchanged for tests that inject agents.
3. **Failures from the runtime**: the runtime's timeout and exception branches close the open call as `timeout` or `error`; the final cleanup closes any remaining open call as `canceled`. Closing is a no-op when no call is open.
4. **Emitter in observability**: `record_model_call` builds the line from validated, typed values only and swallows serialization errors, keeping the fixed field allowlist beside the existing diagnostics code.
5. **Task identifier**: `TaskState.task_id` (random hex) is created in `begin_task`, preserved on resume, and passed to the existing outcome records through an optional validated field.
6. **Tool names**: allowlist is derived from the registered tools plus the delegate tool; anything else is `other`.

## Rollout & Rollback

No data or contract migration. Roll back by reverting the change; existing lines are unaffected.

## Project Structure

```text
src/
├── model_diagnostics.py   # new: hooks, per-run recorder
├── observability.py       # record_model_call, optional task_id
├── task_agents.py         # pass specialist hooks to as_tool
├── task_runtime.py        # task_id, recorder scope, Runner hooks, failure closing
└── app.py                 # pass task_id to outcome records
tests/unit/test_model_diagnostics.py  # new
```

## Complexity Tracking

No new dependencies. One context variable avoids threading a recorder through agent construction.
