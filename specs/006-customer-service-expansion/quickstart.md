# Quickstart: Expanded Customer Service Options

## Prerequisites

- Python 3.14 environment with project development dependencies installed.
- For normal automated checks, deterministic model/tool fakes are used; no provider credentials are needed.
- Browser journeys require Playwright Chromium.

## Deterministic validation

Run targeted domain and catalog tests:

```sh
pytest tests/unit/test_tools.py tests/unit/test_caller_tasks.py tests/unit/test_accounts.py
pytest tests/integration/test_caller_session.py
```

Run the full deterministic suite after implementation:

```sh
pytest
```

Run browser journeys after Chromium installation:

```sh
playwright install chromium
pytest -m e2e tests/e2e/test_customer_service_options.py
```

## Expected scenarios

1. Verify account 123 with its caller-supplied zip, retrieve profile values, and confirm no stored zip appears in the reply, diagnostic capture, or browser storage.
2. Propose a favorite-color update. Assert unchanged data before Yes, one change after Yes, and no change after No or stale/replayed Yes.
3. Save and remove the fixed demo alias without requesting real card fields.
4. Open a case, approve it, and receive a generated case number plus an offer to list open cases. List results for accounts 123 and 456 and confirm ownership filtering.
5. Add a bounded follow-up and close an open case after separate approvals. Confirm closed/foreign cases reject mutation and closed cases disappear from the open list.
6. Confirm an empty case list uses fixed copy and that case text, preferred names, stored zip, card alias, and proposals never enter diagnostics or browser storage.
7. Re-run time, account verification attempt-limit, correction, and human-support journeys to confirm compatibility.
8. Reset or expire the conversation with a pending proposal and prove neither the proposal nor sample data survives.

Use deterministic fake model and tool boundaries. Do not start the application for this quickstart; browser tests own their test server lifecycle. If any test starts the app in a local environment, inspect `.env.example` only for format and source `.env` in the shell without exposing its contents.

## Validation results

- Full deterministic suite: 280 passed.
- Customer-service browser journeys: 3 passed; human-support transfer regression: 2 passed across desktop and mobile.
- The `k6` executable was unavailable, so no load measurements are reported. The load scenario remains `k6 run load/echo_load.js` when k6 is installed.
