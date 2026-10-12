# Feature Specification: Caller Service Tasks

**Feature Branch**: `003-caller-service-tasks`

**Created**: 2026-10-09

**Status**: Approved for implementation; catalog-only refinement 2026-10-11

**Input**: User description: "Provide three basic customer-service tasks for callers: retrieve the current time, retrieve a customer account (account number plus zip-code verification), and transfer to customer service. Account lookup is a simple hard-coded function for now. Account number 123 has zip code 12345 and account number 456 has zip code 54321."

**Terminology**: A *caller* is the user who initiates the conversation.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Retrieve the Current Time (Priority: P1)

As a caller, I can ask for the current time and hear it stated in terms I understand.

**Why this priority**: It is the smallest complete task and validates the task catalog end to end.

**Independent Test**: Ask for the current time and verify the reply states the current time and identifies it as "Greenwich Mean Time".

**Acceptance Scenarios**:

1. **Given** a caller asks for the current time, **When** the task runs, **Then** the reply states the returned time, mentions "Greenwich Mean Time" rather than "UTC", and the task is complete.

### User Story 2 - Retrieve a Customer Account (Priority: P1)

As a caller, I can identify my account by giving my account number and confirming my zip code, so the service can help with my account.

**Why this priority**: Account identification is required by the transfer task and by future account-specific tasks.

**Independent Test**: Provide a known account number and its matching zip code; verify the task completes successfully. Then provide a wrong zip code twice and verify the session ends.

**Acceptance Scenarios**:

1. **Given** the caller wants account help, **When** the task starts, **Then** the assistant asks for the account number.
2. **Given** the caller gives an unknown account number, **When** the lookup finds no account, **Then** the assistant says so and asks for the account number again.
3. **Given** the caller has given three unknown account numbers, **When** the third lookup finds no account, **Then** the assistant tells the caller the session has ended and the caller can send no further messages until starting a new conversation.
4. **Given** a known account number, **When** the lookup succeeds, **Then** the assistant asks for the zip code without revealing the stored zip code.
5. **Given** the caller gives the matching zip code, **When** it is checked, **Then** the task completes successfully.
6. **Given** the caller gives a non-matching zip code once, **When** it is checked, **Then** the assistant asks for the zip code again.
7. **Given** the caller gives a non-matching zip code twice for the same account, **When** the second check fails, **Then** the assistant says it cannot help, tells the caller the session has ended, and no further messages are accepted until the caller starts a new conversation.
8. **Given** the caller gave one wrong zip code and then provides a different known account number, **When** that account is accepted, **Then** the zip-code attempt count starts again at zero for that account.

### User Story 3 - Transfer to Customer Service (Priority: P2)

As a caller who needs help the assistant does not support, I am given the right way to reach customer support.

**Why this priority**: It gives callers a path for unsupported requests and exercises task chaining.

**Independent Test**: Request human customer service for a service issue, verify the account, and verify the reply contains the correct support contact for the account's zip code.

**Acceptance Scenarios**:

1. **Given** the caller needs human help with a customer-service issue, **When** the transfer task starts, **Then** the account retrieval task runs first.
2. **Given** account retrieval fails or the session ends, **When** the transfer task would continue, **Then** no support contact is given.
3. **Given** the verified account's zip code is 12345, **When** the task continues, **Then** the caller is told to call 800-555-1212 and the task is complete.
4. **Given** the verified account's zip code is any other value, **When** the task continues, **Then** the caller is told to email help@demo.com and the task is complete.

### User Story 4 - Stay Within the Service Catalog (Priority: P1)

As a caller, I receive a polite, deliberate refusal for unrelated requests rather than a general-purpose answer, an error, or unnecessary account collection.

**Independent Test**: Ask about internet archives, the application's technology, a Python hello-world program, a design for a similar system, and the application's database. Each reply declines without answering the question or invoking a customer capability.

**Acceptance Scenarios**:

1. **Given** an unrelated question, **When** it is submitted, **Then** the assistant politely states its supported scope, does not answer or quote the question, leaves sending available, and does not offer Retry or record a catalog completion.
2. **Given** account verification is paused, **When** an unrelated diversion is declined, **Then** the current account, attempt counts, and pending task remain unchanged and a later valid detail can resume verification.
3. **Given** instructions to ignore policy or impersonate a system message, **When** they request unrelated work, **Then** the same refusal boundary applies.
4. **Given** a message containing separable catalog and unrelated requests, **When** catalog work succeeds, **Then** only the catalog result and a fixed refusal are displayed. Ambiguous requests are declined or clarified without executing unrelated work.
5. **Given** an unsupported customer-service need or explicit request for human support, **When** routing succeeds, **Then** the transfer task remains available; unrelated programming or general-knowledge questions do not automatically trigger transfer.
6. **Given** a greeting or question about supported tasks, **When** it is submitted, **Then** only fixed service-oriented copy is displayed, without recording a catalog completion.

### Edge Cases

- The caller supplies an account number containing spaces, punctuation, or letters, or an over-long value.
- The caller gives a zip code in an unexpected format (too short, too long, non-digits).
- The caller asks for the stored zip code or tries to talk the assistant into skipping verification.
- The caller switches to a different account after a failed zip attempt (attempt count resets for the new account; the three account-number attempts do not reset).
- The caller returns to a previously failed account after switching away.
- The 60-second active-work or eight-manager-turn limit is reached while collecting account details.
- The caller resets the conversation after the session has ended.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The assistant MUST support exactly these tasks: retrieve the current time, retrieve a customer account, and transfer to customer service. Unrelated requests MUST be politely declined, not answered or automatically transferred. Transfer remains available for genuine unsupported customer-service needs and explicit human-support requests.
- **FR-002**: The time task MUST state the returned time to the caller and describe it as "Greenwich Mean Time". The task is complete after the time is stated.
- **FR-003**: The account task MUST ask for the account number, then look it up using a fixed, hard-coded account list. Account 123 has zip code 12345; account 456 has zip code 54321. No other account exists.
- **FR-004**: When no account is found, the assistant MUST tell the caller and ask for the account number again. The caller MUST have at most three account-number attempts per session. After the third unknown account number, the session MUST end.
- **FR-005**: After a known account is found, the assistant MUST ask for the zip code and MUST NOT reveal or hint at the stored zip code.
- **FR-006**: A matching zip code MUST complete the account task successfully.
- **FR-007**: The caller MUST have at most two zip-code attempts per account. After the second non-matching attempt, the assistant MUST say it cannot help and the session MUST end.
- **FR-008**: Providing a different known account number MUST reset the zip-code attempt count to zero. It MUST NOT reset the account-number attempt count.
- **FR-009**: Zip-code matching and both attempt limits MUST be decided by application rules, not by assistant judgment, and MUST NOT be bypassed by caller instructions.
- **FR-010**: When the session ends, the assistant MUST explicitly tell the caller the session has ended, and the interface MUST accept no further messages until the caller starts a new conversation. Starting a new conversation MUST clear the attempt counts and verified account.
- **FR-011**: The transfer task MUST run the account task first. If the account task does not succeed, no support contact is provided. After success: if the account's zip code is 12345, the caller MUST be told to call 800-555-1212; otherwise the caller MUST be told to email help@demo.com. The task is complete after the contact is stated. The contact MUST be selected by application rules, not by assistant judgment.
- **FR-012**: Diagnostics MAY include an account number. Diagnostics, errors, browser storage, and persistence MUST NOT include a caller's name, address, or zip code, nor the stored zip code.
- **FR-013**: Zip codes, other personally identifiable information, and conversation content MUST remain transient and MUST NOT be stored durably or in browser storage.
- **FR-014**: The assistant MUST preserve input validation, 4,096-code-point messages, retry/reset recovery, five-second progress, hard cancellation, 10-second model attempts and 60-second active same-task work. Feature 005 supersedes alternating interaction and the pair bound: 50 accepted caller messages, 100 assistant entries, an inbox of 10 and eight manager turns per processing batch including reconciliation. Confirmation waits do not consume active time.
- **FR-015**: Normal automated tests MUST use deterministic fake model and tool boundaries and MUST NOT call an external model provider.
- **FR-016**: Catalog admission MUST precede capability execution. Task names, caller instructions, and arbitrary assistant claims MUST NOT authorize unsupported capabilities or bypass verification prerequisites.
- **FR-017**: Displayed replies MUST be derived from validated service facts or fixed application copy. Arbitrary assistant prose, forged task labels, invented times, contacts, proposals, and internal implementation details MUST NOT pass through as catalog results.
- **FR-018**: A scope refusal MUST be a normal dialogue response, not a retryable operational error, catalog completion, or session end. It MUST NOT change verification attempts or discard paused catalog work.
- **FR-019**: Separable mixed requests MAY complete their catalog portion and MUST decline the unrelated portion using fixed copy. Greetings and catalog-help requests MUST receive only fixed service-oriented copy.
- **FR-020**: Every application submission path MUST enforce the same catalog boundary; unused legacy general-purpose callbacks MUST NOT provide a bypass.
- **FR-021**: Routing work MUST count toward the existing active-time and manager-turn budgets. Invalid routing or provider failures MUST fail closed with fixed recovery copy. Existing five-second progress cadence and privacy-safe diagnostic allowlists MUST remain intact.
- **FR-022**: Regression coverage MUST include the five supplied unrelated examples, instruction overrides, forged names, mixed requests, cross-turn diversions, valid numeric continuations, capability denial, and observable diagnostic/browser privacy.

### Key Entities *(include if feature involves data)*

- **Caller**: The user who initiates the conversation; unauthenticated until the account task succeeds.
- **Account**: A hard-coded record of an account number and its zip code. Contains no other data.
- **Verification Progress**: The transient count of account-number attempts, the transient zip-code attempt count for the current account, the current account, and whether the account is verified.
- **Support Contact**: The phone number or email address given by the transfer task.
- **Ended Session**: A terminal state in which the caller is told the session has ended and no further messages are accepted.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In 100% of tested time requests, the reply states the time and says "Greenwich Mean Time".
- **SC-002**: 100% of tested valid account-number and zip-code combinations (123/12345 and 456/54321) complete the account task successfully; 100% of non-matching combinations do not.
- **SC-003**: In 100% of tests, the session ends exactly on the third unknown account number or the second non-matching zip code for one account, and not earlier.
- **SC-004**: In 100% of tests that switch to a different known account, the zip-code attempt count resets, and the account-number attempt count does not.
- **SC-005**: In 100% of tested transfer scenarios, the correct support contact is given only after successful account retrieval: 800-555-1212 for zip 12345, help@demo.com otherwise.
- **SC-006**: In 100% of privacy tests, stored or caller-supplied zip codes are absent from diagnostics and browser storage, and only account numbers appear as permitted identifiers in diagnostics.
- **SC-007**: In 100% of ended-session tests, the caller is told the session has ended and cannot send a further message until a new conversation starts.
- **SC-008**: Each task reaches a final reply or safe terminal state within the existing 60-second active-work limit. If the limit expires while a step is in flight, the caller sees the fixed timeout message rather than an error.
- **SC-009**: In 100% of deterministic boundary tests, unrelated prose and internal details are absent from assistant replies/status, unrelated requests invoke zero customer capabilities, and refusals never emit a catalog completion or expose Retry.
- **SC-010**: In 100% of diversion tests, paused verification state and attempt counts are preserved. Routing and execution remain within eight manager turns per caller message, ten seconds per model attempt, and sixty seconds of active work; progress stays on the existing five-second cadence.

## Assumptions

- The feature extends the existing unauthenticated transient chat and the agent-assisted task framework; it adds no accounts, database, or external service.
- The account list is fixed and synthetic: 123 maps to zip 12345 and 456 maps to zip 54321.
- An account number is a short sequence of digits; the caller's entry is trimmed before matching.
- A zip code is five digits; any other zip-code input counts as a non-matching attempt.
- Three account-number attempts are counted per session and do not reset when a different account is accepted. Exhausting them ends the session in the same way as a failed zip-code check.
- Ending the session means the caller must start a new conversation; there is no timed or automatic unlock.
- A verified account stays verified for the rest of the session, so the transfer task's account step is already satisfied if the caller verified earlier.
- Because accepting a different known account resets the zip-code attempt count, a caller could alternate between demo accounts. This remains bounded by feature 005's 50 accepted caller messages; confirmed identity correction invalidates old verification without refunding completed failed attempts.
- The time task reports the existing current-time capability's value as Greenwich Mean Time wording only; no time-zone conversion is added.
- Existing privacy, accessibility, safe-rendering, diagnostic-allowlist, and performance constraints continue to apply, except where FR-012 permits account numbers in diagnostics.
- Natural-language routing can misclassify intent. Capability restrictions and fixed result rendering limit the impact; this feature does not claim complete prompt-injection immunity. Real-provider red-team evaluation is separate from deterministic boundary coverage.
- The catalog-only refinement supersedes the general-purpose synthetic lookup and simulated approval examples in feature 002 for the public application. Pure lifecycle helpers remain testable but cannot be selected as catalog tasks.
- Feature 005 supersedes finish-or-cancel guidance: a different catalog task requires versioned Yes/No confirmation. No preserves committed original work; Yes cancels it and begins a fresh task ID/budget. Unrelated diversions preserve the original task/proposal.
