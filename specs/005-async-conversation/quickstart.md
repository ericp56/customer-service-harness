# Validation and Review

Use existing Python 3.14 venv/fake models; no external provider calls.
1. `pytest tests/integration/test_app.py -k interrupt`: second input <=1s during
   blocked tool, ordered history, one worker, confirmation before next work.
2. Touched scopes, then `pytest -q --tb=short`.
3. `pytest -m e2e tests/e2e/test_echo_chat.py tests/e2e/test_caller_verification.py`:
   desktop 1280x900/mobile 390x844; order/enabled Send/chat progress notices/confirmation,
   focus/layout/privacy/storage, accessible announcements, no visible echo-status
   component, no display-only notice in model context, and progress suppression at
   the 90-entry threshold. Notices share the 100-assistant-entry bound.
4. Measure 50-session fake blocked-tool ingress/render <=1s; check k6 availability.
5. Account 123 -> 456 -> Yes -> new ZIP; No -> original ZIP/no replay; account ->
   time -> Yes; off-topic; stale Yes/new correction; reset blocked work.

Browser tests start isolated servers with deterministic scripted model boundaries.
An operator review server uses the normal application entrypoint on a free port;
live task execution requires valid environment configuration.

## Executed Results (2026-10-11)

- `.venv/bin/pytest tests/integration/test_app.py -k 'async or interrupt' -q --tb=short`:
   15 passed. Yes/No/latest correction, ambiguous/stale Yes, early ZIP, switch,
   conversational cancel, no-replay facts, overflow/dedup, reset/close/hard cancel,
   ended sessions, isolated histories, retry and diagnostic refusal status covered.
- `.venv/bin/pytest tests/integration/test_app.py tests/unit/test_echo.py tests/unit/test_task_runtime.py -q --tb=short`:
   79 passed. Includes 50/100 message bounds and terminal reserve, pause-aware
   remaining active budget, and account/runtime tests.
- `.venv/bin/pytest -q --tb=short`: 222 passed, 347 existing Gradio/Pandas
   dependency deprecation warnings, 36.03s. No external model calls.
- `.venv/bin/pytest -m e2e tests/e2e/test_echo_chat.py tests/e2e/test_caller_verification.py -q --tb=short --basetemp=/tmp/customer-service-async-browser-final`:
   22 passed, 348 dependency warnings, 34.92s. Desktop 1280x900 and mobile 390x844
   blocked-capability second sends/display each satisfied the one-second bound.
   Yes/No/latest/switch confirmations, ordered input, Send availability, separate
   progress, unchanged unsent typing, storage absence and layout bounds verified.
   Desktop/mobile confirmation screenshots inspected with no overlap/overflow.
- `.venv/bin/pytest tests/integration/test_app.py::test_async_fifty_session_capacity_and_responsiveness -q -s --tb=short`:
   1 passed; 50 blocked fake-boundary sessions accepted/rendered second messages
   in 39.29ms total. Exactly 50 workers; 51st rejected; cleanup released capacity.
   This is an in-process coordinator measurement, not full HTTP/browser load.
- `git diff --check` and Spec Kit prerequisites: pass. Requirements checklist:
   6 checked, 0 unchecked; no extension hooks file exists.

## Review Server and Remaining Gates

Final coordinator adapter encapsulation check: callback scope 50 passed; full
suite rerun 222 passed, 348 dependency warnings, 36.45s; whitespace check passed.

Started after verification using
`.venv/bin/uvicorn src.app:create_server --factory --host 127.0.0.1 --port 7862 --no-access-log --log-level warning`.
UI: http://127.0.0.1:7862 (HTTP 200).
Terminal UUID after final-code restart: `167de292-5be3-4a72-b3a6-5dec03023c79`.
Health/readiness: `not_ready`; valid OpenAI configuration is unavailable in the
new terminal. No secrets inspected or provider calls made. Browser verification
used separate fake-model servers, not this operator server.

k6 is not installed; network-level 50-session load remains unverified. Independent
peer review (T019) is required before release. Natural-language provider semantics
are not proven by ScriptedModel. Idle TTL/unload wiring and explicit close/reset
are implemented; prolonged real-browser disconnect/expiry remains an operator
deployment check. Rollout/rollback must reset transient sessions; no migration.
No commits, pushes or branch changes performed.

## Async Notice Follow-Up Verification (2026-10-12)

- Focused state/context/callback slice: 85 passed.
- `.venv/bin/pytest -q --tb=short`: 228 passed, 347 existing Gradio/Pandas warnings, 36.95s on final rerun.
- `.venv/bin/pytest -m e2e tests/e2e/test_echo_chat.py tests/e2e/test_caller_verification.py -q --tb=short`: 22 passed, 347 existing dependency warnings, 35.34s on final rerun; desktop and mobile transcript announcements, progress timing, invalid-input retention, session-end/refusal, and interruption journeys passed.
- Rejected-ingress Reset-visibility regression: 2 passed. `git diff --check`: passed.
- No live provider calls. The application preview remains stopped; this turn did not inspect secrets or restart it. Network-level k6 load and peer review remain release gates.