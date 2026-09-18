# Customer Service Harness

A prototype, privacy-safe AI Web Chat service. It provides a small Gradio web
application where a visitor receives a generated assistant response in a
transient conversation.

The prototype is intentionally limited: it has no accounts, databases,
transcripts, file uploads, or analytics. Message and tool-invocation context
exists only while the current browser page and application interaction are
active. Configure `OPENAI_API_KEY` and `OPENAI_MODEL` before starting; optional
`OPENAI_BASE_URL` selects an OpenAI-compatible Responses service and
`OPENAI_TIMEOUT_SECONDS` defaults to 10. See the [feature specification](specs/001-ai-chat-integration/spec.md) for
the complete functional and privacy requirements.

Operational diagnostics are emitted as privacy-safe UTC JSON Lines on stdout for an external
collector. The application does not retain logs; records never include chat content, credentials,
model-service URLs, prompts, tool outputs, or provider payloads.
Timing records use fixed step names (`model_request`, `date_time_tool`, and `chat_submission`) and
non-negative `duration_ms` values to identify slow blocking work without exposing request data.

## Getting Started

### Prerequisites

- Python 3.14
- A modern web browser

Create an isolated environment and install the application with development
tools:

```sh
python3.14 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
playwright install chromium
```

Start the local application:

```sh
python -m src.app
```

Open the local URL printed by the application, normally
<http://127.0.0.1:7860>.

## Testing and Validation

Run the complete local test suite:

```sh
pytest
```

The suite includes unit, integration, and Playwright browser tests. The
[validation quickstart](specs/001-ai-chat-integration/quickstart.md) describes
manual checks, privacy-diagnostics inspection, and the optional k6
release-candidate load test. k6 is intentionally an external prerequisite,
not a Python dependency.

## Repository Guide

| Path | Purpose |
| --- | --- |
| `src/` | Gradio app, transient chat context, OpenAI adapter, and privacy-safe diagnostics |
| `tests/` | Unit, integration, and browser end-to-end tests |
| `load/` | k6 release-candidate load scenario |
| `specs/001-ai-chat-integration/` | Feature specification, architecture plan, tasks, contracts, and validation guide |
| `.specify/` | Spec Kit project configuration and constitution |

## Contributing with Spec Kit

This repository is maintained with [Spec Kit](https://github.com/github/spec-kit).
Feature work begins with an implementation-independent specification and keeps
the resulting planning artifacts under `specs/`. The project constitution in
`.specify/memory/constitution.md` defines the repository's quality, privacy,
testing, and performance expectations.

For a new feature, use the Spec Kit workflow:

1. `/speckit-specify` to create or refine the feature specification.
2. `/speckit-plan` to select the architecture and implementation approach.
3. `/speckit-tasks` to create dependency-ordered implementation tasks.
4. `/speckit-analyze` to check the specification, plan, and tasks for gaps.
5. `/speckit-implement` to execute the approved task plan.

Keep specifications and task plans aligned with code changes, and use
`/speckit-clarify` or `/speckit-checklist` when requirements need further
review before implementation.

## License

This project is licensed under the [MIT License](LICENSE).
