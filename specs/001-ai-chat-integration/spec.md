# Feature Specification: AI Chat Integration

**Feature Branch**: `001-ai-chat-integration`

**Created**: 2026-09-18

**Status**: Draft

**Input**: User description: "Add an openapi client to this prototype application. Instead of echoing back the text in the web chat, submit the user text to the openai client, and then send a response back to the web chat. Set up a basic system prompt file (a basic 'you are a helpful assistant. answer questions. do not reveal your inner workings to the client') and tools file (for now, just a simple tool 'getCurrentDateTimeIso'). The model name and api key - and any other configurable items - will be stored in environment variables. The openai client will access models from openai, and may access other openai client-compatible endpoints."

## Clarifications

### Session 2026-09-18

- Q: What conversation context should accompany each model submission? → A: A server-owned system context, the complete active-session user/assistant dialog history, and prior tool invocations.
- Q: How should operational diagnostics be emitted and protected? → A: Write UTC JSON records to stdout with timestamp, component, level, message, and an optional sanitized error stack; use ERROR for caught exceptions, INFO otherwise, and a text-only stdout fallback if JSON serialization fails.
- Q: Which latency target should the application meet for a complete assistant reply after a user submits a message? → A: p95 under 5 seconds; hard timeout remains 10 seconds.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Receive an AI Answer (Priority: P1)

As a web-chat user, I submit a question and receive the assistant's answer in the conversation rather than a copy of my own message.

**Why this priority**: This is the core value of the prototype: users can get useful answers through the existing chat experience.

**Independent Test**: Submit a question in the web chat and verify that a generated assistant answer appears as the next conversation message, without echoing the submitted text as the answer.

**Acceptance Scenarios**:

1. **Given** a configured and available AI service, **When** a user submits a non-empty chat message, **Then** the chat displays the generated assistant response as the next message.
2. **Given** a user submits a non-empty chat message, **When** the generated response differs from the submitted text, **Then** the chat must display that generated response and not replace it with an echo of the user message.
3. **Given** a user submits a blank or whitespace-only message, **When** they attempt to send it, **Then** the message is not submitted and the chat remains unchanged.
4. **Given** a user has prior messages or date-time capability invocations in the active conversation, **When** they submit another non-empty chat message, **Then** the assistant receives the server-owned system context and the complete active-session dialog and tool-invocation history when producing its response.

---

### User Story 2 - Ask Time-Sensitive Questions (Priority: P2)

As a web-chat user, I can ask a time-sensitive question and the assistant can obtain the current date and time when it needs that information.

**Why this priority**: A trusted current-time capability makes simple time-dependent answers more useful while keeping the prototype's initial capability set intentionally small.

**Independent Test**: Ask for the current date and time and verify that the answer reflects the current date and time in ISO 8601 format.

**Acceptance Scenarios**:

1. **Given** the assistant determines that it needs the current date and time to answer a user question, **When** it requests the available date-time capability, **Then** it receives the current date and time in ISO 8601 format and may use it in its response.
2. **Given** a question that does not require the current date or time, **When** the assistant answers it, **Then** no date-time result is added unnecessarily to the user-visible response.

---

### User Story 3 - Receive Safe, Actionable Failures (Priority: P3)

As a web-chat user, I receive a clear recovery-oriented message if an answer cannot be obtained, without exposing private configuration or internal service details.

**Why this priority**: Clear failures prevent users from being stranded and protect sensitive deployment information.

**Independent Test**: Make the configured AI service unavailable and verify that the user sees a retry-oriented failure message containing no credentials, service addresses, or internal diagnostic details.

**Acceptance Scenarios**:

1. **Given** the AI service cannot be reached or cannot provide an answer, **When** a user submits a message, **Then** the chat displays a clear message that the answer could not be obtained and advises the user to try again.
2. **Given** an AI-service failure, **When** the user-visible failure message is displayed, **Then** it contains no credentials, configuration values, service addresses, or internal diagnostic details.

---

### Edge Cases

- A user submits a blank or whitespace-only message.
- The configured AI service is unavailable, times out, rejects the request, or returns no usable answer.
- Required deployment configuration is missing or invalid.
- The assistant response contains no displayable content.
- The assistant requests a capability that is not available in this prototype.
- A user asks about the assistant's internal reasoning or configuration.
- JSON serialization of a diagnostic record fails.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST submit each non-empty user chat message to the configured conversational AI service with the server-owned system context and the complete active-session user/assistant dialog and tool-invocation history, then display its generated response as the next assistant message.
- **FR-002**: The system MUST no longer use the user's submitted message as the assistant response.
- **FR-003**: The assistant MUST be instructed to be helpful, answer questions, and not reveal its inner workings to the client.
- **FR-004**: The system MUST make a current-date-time capability available to the assistant; when used, it MUST return the current date and time in ISO 8601 format.
- **FR-005**: The system MUST allow deployment operators to supply the AI service model, credentials, service location, and other connection settings without modifying application source.
- **FR-006**: The system MUST support the default hosted AI service and compatible alternative service locations that honor the same conversational request and response contract.
- **FR-007**: The system MUST reject blank or whitespace-only messages without submitting them for a response.
- **FR-008**: When a response cannot be obtained, the system MUST preserve the conversation and display a clear, retry-oriented user message that does not reveal credentials, configuration values, service addresses, or internal diagnostics.
- **FR-009**: The system MUST emit one privacy-safe diagnostic record to standard output for each operational outcome, sufficient for operators to distinguish successful responses, invalid configuration, service unavailability, and response failures; the application itself MUST not retain these records.
- **FR-010**: The initial release MUST expose no assistant capabilities other than the current-date-time capability.
- **FR-011**: Each diagnostic record MUST be a single JSON object with UTC `timestamp`, `component`, `level`, and `message` fields. Caught exceptions MUST use level `ERROR`, all other records MUST use level `INFO`, and error records MUST additionally contain an optional sanitized `stack` field with available file and source-location information.
- **FR-012**: Diagnostic records and fallback text records MUST exclude API keys, service URLs, request or response bodies, chat messages, system prompts, tool outputs, provider metadata, and any secrets or customer content present in exception messages or stacks.
- **FR-013**: If a diagnostic record cannot be serialized as JSON, the system MUST write a content-free text fallback to standard output and continue processing the affected chat submission.
- **FR-014**: The system MUST emit privacy-safe duration diagnostics for each outbound AI-service invocation and assistant capability invocation, plus other blocking processing steps on the chat-submission path. Each duration diagnostic MUST identify only the fixed step name and elapsed duration, and MUST follow the existing diagnostic redaction rules.

### Key Entities

- **Chat message**: A user submission or assistant response shown in a conversation, including its sender and displayable content.
- **Conversation context**: The server-owned system context plus the complete ordered user/assistant dialog and tool invocations for the active session; it is included with each model submission but remains transient and is not shown as a chat message.
- **Assistant policy**: The fixed behavioral instructions that guide the assistant to be helpful, answer questions, and withhold its inner workings.
- **Assistant capability**: A permitted action the assistant may request; the initial capability supplies current date and time in ISO 8601 format.
- **AI service configuration**: Operator-supplied connection details, model selection, and credentials used to obtain responses; these values are confidential and never shown to chat users.
- **Diagnostic record**: An ephemeral structured standard-output record for an external collector, containing UTC timestamp, component, level, message, and optionally a sanitized error stack; it contains no customer content, secrets, or provider details.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In a test set of 20 non-empty chat submissions with an available configured service, 100% display a generated assistant response rather than an echo of the submitted text.
- **SC-002**: With an available configured service, at least 95% of chat submissions display an assistant response within 5 seconds, measured across 100 submissions under expected prototype load; each submission MUST time out within 10 seconds.
- **SC-003**: In a test set of 20 requests for the current date and time, 100% of answers that use the date-time capability contain an ISO 8601 date-time matching the time of the request to within 60 seconds.
- **SC-004**: In usability testing with at least five representative users, at least 80% can submit a question and identify the assistant's answer on their first attempt without assistance.
- **SC-005**: In all tested invalid-configuration and unavailable-service cases, 100% preserve the existing conversation and show a retry-oriented failure message containing no confidential connection details.
- **SC-006**: In a test set covering successful, validation, configuration, provider-failure, and serialization-failure outcomes, 100% of expected diagnostics are emitted to standard output; valid records contain all four required JSON fields, and caught-exception records contain an `ERROR` level and sanitized stack when source information is available.

## Assumptions

- The existing web chat supplies the user-message entry and conversation display experience; this feature changes the source of assistant answers, not the chat's visual design.
- An operator provides valid confidential configuration through the deployment environment and has authorization to use the selected AI service.
- The deployed environment has network access to the selected AI service.
- This prototype does not persist chat conversations, add authentication or authorization, stream partial answers, or expose capabilities beyond current date and time. The complete active-session dialog and tool-invocation history remains transient and accompanies each model submission.
- External AI services are responsible for their own availability and response quality; the application provides clear recovery messaging when they fail.
- An external process is responsible for collecting, retaining, securing, and providing access to standard-output diagnostics; the application creates no log store.
