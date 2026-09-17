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
python -m pip install --requirement requirements-dev.txt
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

Run the planned `load/echo_load.js` scenario against production-like HTTPS ingress:

```sh
k6 run load/echo_load.js
```

Start with a smoke test, then hold 50 virtual users for 5 to 10 minutes. Confirm at least 95% of
successful submissions result in visible echoes within 1 second, every success matches its input
exactly, no duplicate pairs occur, and the Gradio queue does not saturate.
