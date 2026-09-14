# Research: Conversational AI Task Harness

## Decision: Use Python 3.13 with Gradio 6.27.0 mounted in FastAPI

**Rationale**: Gradio provides the required chat interaction while FastAPI supplies the service
boundary needed for organization authentication, authorization, health checks, and application
routes. Use Gradio queue limits to bound concurrent model work rather than allowing unbounded
requests.

**Alternatives considered**: A standalone Gradio application lacks an appropriate boundary for
enterprise authentication and authorization. A custom browser UI adds delivery cost without
benefit for the first release.

**Sources**: [Gradio ChatInterface](https://www.gradio.app/main/docs/gradio/chatinterface),
[Gradio queuing](https://www.gradio.app/guides/queuing),
[Gradio mounting and authentication](https://www.gradio.app/guides/sharing-your-app).

## Decision: Keep a small provider-neutral AI interface

**Rationale**: The application owns prompts, plan validation, confirmations, and effect execution.
An internal interface for planning and summarization permits an OpenAI-compatible initial client
while allowing provider-native adapters where structured output or other features require them.

**Alternatives considered**: Calling a vendor SDK directly throughout the application couples
business rules to one provider. Adopting a broad agent framework would hide the confirmation state
machine that must remain explicit and testable.

**Sources**: [Anthropic SDK overview and OpenAI compatibility](https://platform.claude.com/docs/en/cli-sdks-libraries/overview).

## Decision: Store authoritative state in PostgreSQL

**Rationale**: Concurrent conversations, plan revisions, confirmations, and exactly-once effect
attempts require transactions that remain correct across multiple service instances. PostgreSQL
provides the required multiuser transaction semantics. SQLite/WAL remains suitable only for local
development or a deliberately single-instance pilot.

**Alternatives considered**: Browser or Gradio session state is temporary and cannot authorize or
audit work. SQLite is simpler but limits reliable multi-instance deployment.

**Sources**: [PostgreSQL concurrency control](https://www.postgresql.org/docs/current/mvcc-intro.html),
[SQLite appropriate uses](https://www.sqlite.org/whentouse.html),
[SQLite WAL](https://www.sqlite.org/wal.html),
[Gradio state](https://www.gradio.app/guides/state-in-blocks).

## Decision: Require constrained structured output plus local validation

**Rationale**: The AI response becomes a candidate plan, never an authorization decision. Provider
schema constraints and strict Pydantic validation reject malformed fields, while application rules
enforce allowed actions, required confirmation, user permissions, expiration, and idempotency.

**Alternatives considered**: Parsing prose plans is fragile. Trusting validated schema alone is
unsafe because structural validation cannot establish truth, authorization, or business safety.

**Sources**: [OpenAI structured outputs](https://platform.openai.com/docs/guides/structured-outputs),
[Pydantic strict mode](https://docs.pydantic.dev/latest/concepts/strict_mode/),
[Anthropic structured outputs](https://docs.anthropic.com/en/docs/build-with-claude/structured-outputs).

## Decision: Use organization OIDC identity and server-side authorization

**Rationale**: The service will be internal but must not rely on Gradio's basic authentication.
The reverse proxy or application middleware verifies organizational identity; the service then
enforces roles for chat use, confirmation, and each effect. Gradio session identifiers remain UI
correlation values only.

**Alternatives considered**: Gradio username/password authentication does not satisfy expected
controls such as MFA, lockout, or enterprise identity lifecycle management.

**Sources**: [FastAPI OAuth2 scopes](https://fastapi.tiangolo.com/advanced/security/oauth2-scopes/),
[Gradio authentication guidance](https://www.gradio.app/guides/sharing-your-app).

## Decision: Test the state machine and external-effect boundary first

**Rationale**: Unit and property tests prove invalid plans and unconfirmed actions cannot reach an
effect adapter. Database integration tests exercise concurrent confirmation consumption, while
adapter contract, browser, and load tests verify the service boundary and user workflow.

**Alternatives considered**: UI-only tests cannot prove authorization, idempotency, or transaction
safety. Live AI-provider tests remain separately gated to avoid unreliable normal CI.

**Sources**: [pytest](https://docs.pytest.org/en/stable/),
[Gradio queuing](https://www.gradio.app/guides/queuing).

## Decision: Use privacy-safe observability with a separate audit trail

**Rationale**: Trace request, queue, AI, validation, plan, confirmation, and effect outcomes using
correlation IDs and metadata, not raw prompts or secrets. Store immutable audit metadata separately
from conversation content and define data retention before launch.

**Alternatives considered**: Logging full content aids debugging but violates the constitution's
data minimization rule. Provider retention is a configuration and procurement decision, not an
assumption.

**Sources**: [OpenTelemetry Python](https://opentelemetry.io/docs/languages/python/),
[OpenAI API data controls](https://platform.openai.com/docs/guides/your-data).
