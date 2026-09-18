# Quickstart: AI Chat Integration Validation

## Prerequisites

- Python 3.14 and a modern browser.
- An OpenAI account or an OpenAI-compatible service that implements the Responses and strict
  function-calling contract.
- A permitted API key and model identifier. Do not use customer data as validation input.

## Setup

1. Create and activate a virtual environment, then install the project and development
   dependencies:

   ```sh
   python3.14 -m venv .venv
   . .venv/bin/activate
   python -m pip install -e ".[dev]"
   playwright install chromium
   ```

2. Supply required configuration only through the process environment:

   ```sh
   export OPENAI_API_KEY='replace-with-a-permitted-key'
   export OPENAI_MODEL='replace-with-a-supported-model'
   export OPENAI_BASE_URL='https://compatible.example/v1' # Optional; omit for hosted OpenAI
   export OPENAI_TIMEOUT_SECONDS='10'                     # Optional
   ```

3. Start the application:

   ```sh
   python -m src.app
   ```

## Validation Scenarios

| Scenario | Action | Expected outcome |
|---|---|---|
| Generated answer | Submit a non-empty factual question in the browser. | The next chat message is an assistant-generated answer, not an echo of the submitted text. |
| Conversation context | Submit a question, request the current time, then submit a follow-up that refers to both answers. | The follow-up's model submission includes the fixed system context, all prior user/assistant dialog, and the prior date-time tool invocation and result for the active session. |
| Current time | Ask for the current date and time. | The assistant can use `getCurrentDateTimeIso`; any returned timestamp is parseable ISO 8601 UTC and within 60 seconds of the check. |
| Blank input | Submit only spaces, tabs, or newlines. | An accessible validation alert appears; no model request or chat pair is created. |
| Provider failure | Use an invalid key, unreachable compatible base URL, or a test fake that raises the declared service error. | The conversation is unchanged, the original input is retained for retry, and a fixed retry alert contains no key, URL, message content, or provider details. |
| Configuration failure | Omit `OPENAI_API_KEY` or `OPENAI_MODEL`, then submit a valid message. | `/readyz` reports `not_ready`; the browser shows the same safe retry alert and no partial pair. |
| Privacy | Inspect the diagnostic snapshot and browser storage after a successful and failed submission. | Diagnostics contain only fixed categories/buckets; local/session storage, cookies, analytics, and message-body logs are absent. |
| Structured diagnostics | Capture stdout for success, validation, and caught-error cases. | Each normal record is one UTC JSON object with timestamp, component, level, and message; errors are ERROR records with a sanitized stack when available; no sensitive content appears. |
| Latency diagnostics | Submit a question that triggers the date-time capability and inspect captured stdout. | Separate INFO records identify `model_request`, `date_time_tool`, and `chat_submission`, each with a non-negative integer `duration_ms`; no input, output, call ID, or provider metadata appears. |

## Automated Checks

Run the local deterministic suite without contacting an external model service:

```sh
pytest
```

The narrow test layers and provider boundary are described in [research.md](research.md); request
and failure behavior is defined in [contracts/model-service-contract.md](contracts/model-service-contract.md);
state and validation rules are defined in [data-model.md](data-model.md).

For release candidates, run the existing load scenario after updating it for 100 submissions and
verify the p95 user-visible completion target is under 5 seconds and no request exceeds the
10-second hard timeout. Perform a separate,
authorized live-provider smoke check with non-sensitive prompts only.
