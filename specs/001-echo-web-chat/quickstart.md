# Quickstart: Echo Web Chat Validation

## Prerequisites

- Python 3.14
- A modern web browser
- k6 for the release-candidate performance check

## Setup

After implementation artifacts are present:

```sh
python3.14 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
playwright install chromium
pytest
python -m src.app
```

Open the local URL reported by the application. In a separate terminal:

```sh
pytest tests/e2e
```

## End-to-End Validation

1. Submit `Hello`. Confirm one user message and one following assistant echo appear, both `Hello`.
2. Submit line breaks, Unicode, `&`, and `<tag>`. Confirm the echo is identical, line breaks remain
   visible, and text is not interpreted as markup.
3. Submit whitespace-only text. Confirm no message appears and accessible feedback explains the
   correction.
4. Submit exactly 4,096 Unicode code points, then 4,097. Confirm the former is echoed and the
   latter is rejected with the documented limit.
5. Simulate a callback or framework failure. Confirm input remains available, prior messages remain
   visible, an actionable error is announced, and Retry succeeds after restoration.
6. Complete 50 pairs. Confirm the system preserves them, prevents another send, and Start New
   Conversation clears the transient chat only after the visitor activates it.
7. Reload the page. Confirm the chat is empty and no content is restored.
8. Inspect application and ingress diagnostics. Confirm they contain no request/response body,
   message content, or visitor identifier.

## Performance Validation

Run the planned `load/echo_load.js` scenario against production-like HTTPS ingress. `TARGET_URL`
must be the same-origin HTTPS route under test; the default is only for a local smoke test.

```sh
TARGET_URL=https://echo.example.internal LOAD_DURATION=5m k6 run load/echo_load.js
```

Start with a smoke test, then hold exactly 50 virtual users for 5 to 10 minutes. Confirm the k6
thresholds pass: p95 `echo_visible_ms` is under 1,000 milliseconds, `exact_echo` is 1, and
`queue_saturation` is 0.

## Privacy Diagnostics

The app exposes only in-memory aggregate diagnostics through `src.app.diagnostics_snapshot()` for
local verification. Inspect its keys and representative values while using synthetic test input:

```sh
python -c 'from src.app import diagnostics_snapshot; print(diagnostics_snapshot())'
```

Confirm the result contains only fixed outcome names, duration buckets, queue-depth buckets, and
health values. It must not contain messages, visitor identifiers, cookies, user agents, or
serialized exception values. Do not add request-body logging for this check.

## Platform Owner Handoff and Ingress Validation

Platform configuration is outside this repository. Before enabling a production route, have the
platform owner complete and retain this confirmation record; this template intentionally makes no
claim that external controls have already been verified.

```text
Echo route URL:
Platform owner and date:
Same-origin HTTPS termination confirmed: [ ]
Finite connection timeout configured: [ ]
Finite request timeout configured: [ ]
Request-body logging disabled: [ ]
Response-body logging disabled: [ ]
Approval reference:
```

With a deployed route, validate the controls using the platform's approved tooling:

1. Request `https://<echo-route>/healthz` and `https://<echo-route>/readyz`; each must return
   `{"status":"ready"}` through the intended same-origin HTTPS ingress.
2. Inspect the configured finite connection and request timeout values in the platform deployment
   record.
3. Send only a synthetic, non-sensitive canary through the chat route and have the platform owner
   verify that request and response bodies do not appear in ingress or application diagnostics.
4. Record the evidence location and date in the platform confirmation record. Do not copy request
   bodies into this document.

## Rollout, Monitoring, and Rollback

Release readiness requires the platform confirmation record, passing unit/integration/browser
tests, and a passing 50-VU k6 run. During rollout, monitor only the content-free outcome,
duration-bucket, queue-depth-bucket, and health signals.

Withdraw the new application route and restore the prior route if p95 successful echo latency is
not under one second, the queue saturates, or any privacy/body-log-suppression control fails. Then:

1. Confirm the prior route is active and the new route no longer accepts traffic.
2. Confirm the app process has been stopped or replaced, so all process-only diagnostics and
   Gradio session state are discarded.
3. Re-run the health checks against the restored route and record only the result, time, and
   platform approval reference—never conversation content.

## Complete Validation Workflow

Run these commands for a release candidate after the platform route is available:

```sh
pytest tests/unit tests/integration
pytest tests/e2e
TARGET_URL=https://echo.example.internal LOAD_DURATION=5m k6 run load/echo_load.js
```

Browser tests require the locally installed Chromium runtime. The k6 command requires an
externally installed k6 executable and a production-like target; it is not a Python dependency.
