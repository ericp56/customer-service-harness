# Feature Specification: Expanded Customer Service Options

**Feature Branch**: `006-customer-service-expansion`

**Created**: 2026-10-21

**Status**: Draft

**Input**: User description: "Expand customer service to Personal Settings (favorite color, preferred name), Account Settings (save/remove card on file), and Support (open/close cases and follow up); provide functions for time, account retrieval/update, and case operations, with expanded synthetic account and case data. Use the operation names Retrieve Account and Update Account."

**Supersession**: This feature expands the exactly-three-task public catalog in feature 003. It does not supersede account verification/attempt limits, the feature 005 async conversation contract, privacy constraints, or existing current-time and human-support tasks.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Retrieve and Update Account Settings (Priority: P1)

As a verified caller, I can review and update my permitted personal and account settings, including a synthetic saved-card setting.

**Why this priority**: These common, bounded self-service options provide immediate value while reusing the account verification journey.

**Independent Test**: With deterministic synthetic account data, verify an account, retrieve settings without revealing its zip code, propose a favorite-color or preferred-name update, and prove only explicit approval changes the session's data. Exercise save/remove card using the synthetic alias only.

**Acceptance Scenarios**:

1. **Given** an unverified caller requests account settings, **When** the task starts, **Then** the existing account-number and zip-code verification rules are applied before any account data is returned.
2. **Given** a verified caller requests `Retrieve Account`, **When** retrieval succeeds, **Then** the assistant displays the favorite color, preferred name, and whether a demo card is on file, but never the stored zip code.
3. **Given** a verified caller requests a permitted `Update Account`, **When** the assistant presents the exact proposed setting change, **Then** no data changes until the caller approves that proposal.
4. **Given** the caller rejects, changes identity, resets, or expires the conversation while an update is pending, **When** the pending update is resolved or discarded, **Then** the update is not applied.
5. **Given** the caller requests save/remove card, **When** the operation is approved, **Then** only the synthetic demo-card flag/alias changes; the chat never requests or accepts a real card number, security code, expiry date, or payment token.

### User Story 2 - Manage Support Cases (Priority: P1)

As a verified caller, I can open a support case, see my open cases, add a follow-up to an open case, and close an open case.

**Why this priority**: Case self-service is the largest new support workflow and needs clear ownership and lifecycle rules.

**Independent Test**: With fake model and deterministic per-conversation cases, verify ownership filtering; open a case and approve it; list open cases; add an approved follow-up; close an approved case; then verify closed cases no longer appear in the open list and cannot be updated.

**Acceptance Scenarios**:

1. **Given** the caller is not verified, **When** they request any case operation, **Then** the assistant completes account verification before reading or changing cases.
2. **Given** a verified caller opens a case with a valid description, **When** the proposed case is approved, **Then** a server-generated case number is returned and the assistant offers to list open cases.
3. **Given** the caller accepts that offer or asks to list cases, **When** the list is returned, **Then** it contains only open cases owned by the verified account; an empty list receives a clear fixed response.
4. **Given** a caller requests follow-up without identifying an open case, **When** open cases exist, **Then** the assistant lists the eligible cases and asks which one to update; it collects a bounded follow-up message and requires approval before appending it.
5. **Given** a verified caller requests a case closure, **When** the exact case is approved for closure, **Then** it becomes closed once and no longer appears in open-case results.
6. **Given** a case is closed, belongs to another account, is unknown, or is otherwise ineligible, **When** a mutation is attempted, **Then** no case data changes and the caller receives safe fixed recovery copy.

### User Story 3 - Preserve Existing Customer-Service Tasks (Priority: P1)

As a caller, I can continue to retrieve the current time, verify my account, or reach human Customer Service under the existing rules.

**Why this priority**: The expanded catalog must not strand existing journeys or weaken verification and transfer behavior.

**Independent Test**: Run deterministic tests for current-time wording, all existing account/zip attempt limits, and verified human-support contact selection after catalog expansion.

**Acceptance Scenarios**:

1. **Given** a caller asks for the current time, **When** the task completes, **Then** the reply states the time as Greenwich Mean Time.
2. **Given** a caller provides invalid account or zip verification, **When** an attempt limit is reached, **Then** the existing session-ending behavior is unchanged.
3. **Given** a caller explicitly requests human support or raises a supported-system issue outside the new catalog tasks, **When** transfer is requested, **Then** account verification and existing application-selected contact behavior remain in effect.

### Edge Cases

- Requests that mix multiple writes, conflict, omit required fields, or provide ambiguous case identity MUST NOT mutate anything; ask one focused clarification or fail safely.
- Only caller-supplied values or server-owned choices may be used as tool arguments. Never infer a favorite color, preferred name, case number, case owner, or follow-up text.
- The caller may switch accounts only through existing versioned correction confirmation; after correction, old verification and pending writes cannot authorize the new account.
- Approval may be stale, duplicated, replayed, or arrive after cancellation, reset, expiry, or session end; all must fail closed without a duplicate mutation.
- A race with a newly accepted caller event must not publish success until the mutation commit is reconciled against the latest task revision.
- Case lists may be empty; IDs may be unknown or belong to another account; closed cases cannot be followed up or closed again.
- Limits are reached: 20 cases per conversation, 10 follow-up entries per case, 500 Unicode code points per case description and per follow-up, favorite color selected from the fixed values red, blue, green, purple, black, or white, and preferred name at most 40 Unicode code points.
- A seeded account may already have a demo card or cases. Repeating the same update, saving an already-saved demo card, removing an absent demo card, or closing a closed case is an idempotent no-op or safe validation result, never a duplicate side effect.
- A service/model failure, timeout, retry, cancellation, or session expiry must not cause an uncommitted proposal to appear committed or repeat a committed mutation.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST organize customer-facing help around Personal Settings, Account Settings, and Support, and MUST retain current time, account verification, and human-support transfer.
- **FR-002**: The system MUST support `Retrieve Account` and `Update Account` as the customer-facing names. Retrieval and update MUST require the current account to be verified; account number and zip code are verification identifiers, not editable settings.
- **FR-003**: `Retrieve Account` MUST return only application-selected permitted fields: favorite color, preferred name, and demo-card-on-file status. It MUST never return the stored zip code to the model, customer, diagnostics, or browser state.
- **FR-004**: `Update Account` MUST be restricted to favorite color, preferred name, and save/remove of the fixed synthetic demo-card alias. It MUST NOT accept real payment-card data, payment credentials, or arbitrary account fields.
- **FR-005**: Every state-changing setting, card, or case action MUST present the exact proposed change and require explicit, version-bound caller approval before mutation. Rejection, stale/replayed approval, cancellation, identity correction, reset, expiry, or session end MUST leave that pending mutation unapplied.
- **FR-006**: All writes MUST be applied by deterministic application logic against the currently verified account and validated server-owned session snapshot. The model MUST NOT directly mutate records, choose another account's records, or author the final success result.
- **FR-007**: The system MUST provide deterministic synthetic account records for account numbers 123 and 456. Each record MUST include account number, private zip verification value, favorite color, preferred name, and optional demo-card alias. Per-conversation changes MUST be discarded on reset or session expiry.
- **FR-008**: The system MUST support opening a support case with a caller-provided description up to 500 Unicode code points. The application MUST assign a unique case number, bind it to the verified account, and offer to list open cases after successful creation.
- **FR-009**: The system MUST list only open cases belonging to the currently verified account, with a fixed empty-state response when none exist.
- **FR-010**: The system MUST allow follow-up only on an open case owned by the verified account. Follow-up text MUST be supplied by the caller, limited to 500 Unicode code points, and appended to an ordered history of at most 10 entries after approval.
- **FR-011**: The system MUST allow an open case owned by the verified account to be closed after approval. Closed cases MUST not be listed as open and MUST not accept further follow-ups or closure mutations.
- **FR-012**: The synthetic sample data MUST include different account settings for both accounts and multiple cases across accounts, including open and closed cases, so retrieval, filtering, and lifecycle behavior are distinguishable in deterministic tests.
- **FR-013**: Account and case reads/writes MUST be authorized by strict application-owned capability allowlists and typed schemas. All user-provided argument values MUST be present in the current caller message or previously accepted, server-owned task state.
- **FR-014**: Customer content, model prompts/replies, preferred names, zip codes, case descriptions, follow-up content, payment data, and tool payloads MUST remain transient and MUST NOT appear in diagnostics, persistence, or browser storage. Diagnostics MUST retain only existing explicit allowlists and fixed catalog task names.
- **FR-015**: Preserve the existing event contract: 50 accepted caller messages, 100 assistant entries, inbox capacity 10, maximum input 4,096 Unicode code points, eight manager turns per processing batch, four specialist turns per delegation, one capability call per model turn, 10-second model attempt limit, 60-second active-work budget, and fixed progress sampling. Customer waits pause active time.
- **FR-016**: Normal automated tests MUST use deterministic fake model and tool boundaries and MUST NOT contact an external model provider.
- **FR-017**: Existing time, account/zip verification and attempt limits, correction confirmation, human-support contact selection, retry/reset behavior, accessible fixed progress/recovery messages, and safe text rendering MUST remain intact.
- **FR-018**: Unknown, malformed, cross-account, closed, duplicate, conflicting, or unapproved operations MUST fail closed, produce no mutation, and return fixed safe customer-facing copy.

### Key Entities *(include if feature involves data)*

- **Account**: Synthetic account number, private zip verification value, favorite color, preferred name, and optional fixed demo-card alias. Account number and zip are immutable verification identifiers.
- **Demo Card State**: Whether the synthetic card alias is on file. It is not a payment instrument and contains no PAN, CVV, expiry, or provider token.
- **Support Case**: Server-generated case number, owning account number, caller description, open/closed status, creation/update timestamps, and ordered follow-up entries.
- **Pending Mutation**: Exact validated operation and target, task/revision binding, and one-shot pending/approved/rejected state; server-only and discarded when no longer current.
- **Conversation Sample Data**: Synthetic account/case snapshot with changes scoped to one conversation and cleared on reset/expiry.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In deterministic tests, every permitted account retrieval returns only the allowed settings and no stored zip value; every unverified or mismatched-account request returns no account settings.
- **SC-002**: In 100% of tested write paths, no record changes before explicit approval; approval applies exactly one valid mutation; rejection, stale approval, replay, reset, correction, cancellation, or expiry applies none.
- **SC-003**: In 100% of tested case journeys, listing excludes closed and foreign-account cases, follow-up is appended only to an owned open case, and close removes the case from future open results.
- **SC-004**: In 100% of tests, existing account/zip attempt limits, current-time result wording, and verified human-support contact behavior remain unchanged.
- **SC-005**: In privacy tests, customer/model/tool data, stored zip, preferred names, case content, and card-related inputs are absent from diagnostics and browser storage.
- **SC-006**: Under normal service responsiveness, each supported operation reaches a result, clarification, or fixed recovery within the existing 60-second active budget; each model attempt remains at or below 10 seconds.
- **SC-007**: Desktop and mobile browser journeys can complete each grouped workflow without horizontal overflow, and all approval, clarification, empty, and recovery states are accessible and distinguishable.

## Assumptions

- A caller is unauthenticated until the existing account-number and zip-code checks succeed; verified identity is scoped to the current transient conversation.
- The account sample remains the existing synthetic set 123/456 with zip values unchanged and private. Added sample settings are deterministic, fictional, and distinct.
- Seed account 123 has no demo card; account 456 has the fixed demo card alias. Sample case data includes at least one open case for each account and at least one closed case.
- Preferred names and case text are caller-provided data and remain transient. There is no database, persistence, external case-management service, payment processing, or real customer record.
- The existing fixed catalog and safe refusal rules continue to reject unrelated general-purpose requests. Existing transfer-to-human remains for genuine issues outside the catalog.
- Favorable default limits are 20 cases per conversation, 10 follow-up entries per case, 500 code points per description/update, and 40 code points for preferred name. Favorite color is restricted to the six values listed in Edge Cases.
- Session-local changes are not retained across reset, expiry, process restart, or another conversation; this feature does not promise cross-session durability.
