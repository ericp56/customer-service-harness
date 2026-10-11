# Quickstart: Agent-Assisted Customer Tasks

## Prerequisites

- Python 3.14 and the project development dependencies installed.
- For local UI/provider smoke testing only, configure `OPENAI_API_KEY` and `OPENAI_MODEL`; optional `OPENAI_BASE_URL` must be HTTPS and compatible with the selected model request format. Do not put secrets in shell history, test fixtures, or screenshots.
- Install Chromium for browser tests if needed: `playwright install chromium`.
- Normal tests use deterministic fakes and require no provider credentials or network access.

## Deterministic Checks

Run all unit and integration tests:

```sh
pytest tests/unit tests/integration
```

Run the browser task journeys:

```sh
pytest -m e2e tests/e2e/test_echo_chat.py
```

Expected coverage in the existing browser journey file includes supported synthetic lookups, current date/time, missing-information clarification, periodic progress outside the chat transcript, approval/rejection of the no-op simulated action, cancellation, timeout, failure recovery, stale/replayed decisions, and privacy assertions.

## Manual UI Smoke Test

Start the application with configured provider environment values:

```sh
python -m src.app
```

1. Submit a request answerable by a synthetic fixture; confirm the final answer is useful and contains no internal tool or orchestration details.
2. Use the deterministic slow-task fixture; confirm a separate accessible progress status appears at five-second intervals, changes from lookup activity to result evaluation when that becomes the current phase, and stops when the task completes or asks a question. Confirm unknown activity falls back to the existing two fixed messages and progress never names a capability or includes model-provided copy.
3. Ask a task requiring clarification; confirm updates pause, answer the question, and confirm processing resumes only with the remaining task budget.
4. Trigger the simulated consequential step; confirm it has no effect before explicit approval, rejection/cancel does not execute it, and the UI displays the resulting outcome.
5. Cancel a slow task; confirm no subsequent step starts and the result reports whether any step had already completed.
6. Inspect stdout and browser storage; confirm no messages, prompts, model/tool outputs, approvals, provider payloads, URLs, or credentials are present.

## Release Validation

Follow the [release runbook](release-runbook.md) for the 100-submission k6 run,
the 10-customer usability protocol, and privacy-safe result recording.

- Verify every model-call attempt is bounded to 10 seconds, retries are disabled, and active work ends by 60 seconds excluding customer wait time.
- Verify strict capability schemas, at most one capability call per model turn, eight conversation-manager turns per task, four specialist turns per delegation, and safe recovery when either limit is exhausted.
- Verify each progress interval is visible within one additional second under normal service responsiveness. Report deviations under expected concurrency; event-queue/network delay is not a hard real-time guarantee.
- In a usability check with 10 representative customers, verify at least 9 can distinguish progress from the final answer and identify the next action for clarification, approval, or recovery.
- Run the existing app and full deterministic suite:

```sh
pytest
```

- Run the release-candidate 100-submission load scenario when `k6` is available:

```sh
k6 run load/echo_load.js
```

- Record the usability result against SC-007 after the study. Do not check off
	the release gate before the study is completed.

- Do not enable deployment unless trace export is disabled, the approval checkpoint remains server-side/transient, cancellation passes, and all existing diagnostics and browser-persistence privacy tests pass.