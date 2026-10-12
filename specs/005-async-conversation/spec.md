# Feature Specification: Interruptible Async Conversation

**Feature Branch**: unchanged (`mac-copilot`; no branch creation)
**Created**: 2026-10-11
**Status**: Approved for implementation
**Input**: Start implementation of the approved session-memory async conversation plan.

## User Scenarios & Testing

### User Story 1 - Speak While Work Continues (Priority: P1)

The caller can send another message while a task is working and see every accepted
message in receipt order. Answers and questions arrive independently.
**Why this priority**: Corrections must not be blocked by a slow lookup.
**Independent Test**: Block a lookup, accept a second message within one second,
then release the lookup and observe confirmation before any next step or answer.

**Acceptance Scenarios**:
1. **Given** account 123 is being checked, **When** the caller corrects it to 456,
   **Then** both inputs appear, the current check finishes, and one change question
   appears before any further work or stale ZIP question.
2. **Given** a current-time task is active, **When** no further input arrives,
   **Then** an initial fixed working message appears in chat, later activity changes
   appear no more often than every five seconds, and a tool-backed answer arrives
   without requiring a reply to progress messages.

### User Story 2 - Confirm the Latest Intent (Priority: P1)

The caller can correct, cancel, or switch catalog tasks through explicit confirmation.
**Why this priority**: Only the displayed intent may authorize changed work.
**Independent Test**: Yes changes account; No continues from committed lookup without replay.

**Acceptance Scenarios**:
1. **Given** a displayed change proposal, **When** Yes arrives after publication,
   **Then** that proposal applies once; an earlier Yes cannot apply it.
2. **Given** a pending proposal, **When** a newer correction arrives,
   **Then** it replaces the proposal and requires a fresh confirmation.
3. **Given** account work, **When** the caller asks for current time and confirms,
   **Then** the old task is canceled and a fresh current-time task starts.
4. **Given** an unrelated diversion, **When** it arrives mid-task,
   **Then** it is declined without losing the original task or pending proposal.

### User Story 3 - Safe Recovery and Session Isolation (Priority: P2)

The caller can retry, hard-cancel, or reset without duplicated work or late replies.
**Why this priority**: Transient work must remain bounded and private.
**Independent Test**: Reset a blocked task and prove its late result cannot publish;
two sessions never share dialogue, verification, or workers.

**Acceptance Scenarios**:
1. **Given** a failed accepted input, **When** Retry is selected,
   **Then** the same event is retried without duplicate input or committed capability replay.
2. **Given** a full inbox, **When** more input is submitted,
   **Then** it remains in the textbox, is not accepted, and fixed recovery appears.
3. **Given** a final failed verification attempt, **When** a correction is queued,
   **Then** session end wins and no new work starts.

### Edge Cases

Duplicate Send/Enter; stale Yes; ambiguous confirmation; several conflicting
details; early ZIP bound to original account; correction after verified identity;
router/tool/evaluation/publication races; error after committed tool; hard cancel,
reset, disconnect and expiry; exhausted message, turn, and active-work limits.

## Requirements

### Functional Requirements

- **FR-001**: Accept and publish caller messages independently of active work,
  in receipt order; only one task worker per one-tab transient conversation.
- **FR-002**: Bound unprocessed input to 10 messages, each at most 4,096 Unicode
  code points; retain rejected input with fixed accessible feedback in the chat.
- **FR-003**: Permit at most 50 accepted caller messages (including confirmations
  and corrections, excluding exact retries), and 100 assistant entries including
  progress and notice entries plus reserved terminal recovery capacity. Suppress
  optional progress at 90 assistant entries and preserve the final slot for reset
  guidance. Never ask for an impossible next reply.
- **FR-004**: Finish and commit the current capability before reconciling queued
  input; gate every next model/capability and final publication against stale intent.
- **FR-005**: Always confirm correction, conversational cancellation, and catalog
  switch. Compatible detail advances only with unambiguous stage and source.
- **FR-006**: Version proposals; Yes applies only the displayed version once;
  No resumes original committed facts; ambiguity re-prompts; newer intent replaces
  the proposal. Earlier queued Yes/No cannot answer an unpublished question.
- **FR-007**: Interpret interruptions using finite catalog-only decisions. Decline
  unrelated requests, clarify ambiguous/multiple values without dispatch, and
  render only application-owned responses; never echo ZIP values.
- **FR-008**: Preserve completed unknown-account and wrong-ZIP attempts. Confirmed
  changed identity invalidates prior verification/contact. Only accepting a new
  known account resets ZIP attempts; unknown-account count persists; session end wins.
- **FR-009**: Same-task changes preserve remaining 60-second active budget and
  create a fresh input revision/step IDs. Confirmed switches use a fresh task ID
  and budget, retain caller session, discard old task facts. No does not replay.
- **FR-010**: Freeze substantive work and active-time accounting during confirmation;
  retain <=10-second model attempts, no retries, eight manager turns per processing
  batch including reconciliation, four specialist turns, one capability per model
  turn, no parallel tools, and at most 50 concurrent active task sessions.
- **FR-011**: Hard Cancel immediately stops owned work. Reset/unload/expiry invalidate
  late callbacks and clear transient state. Error/retry retains committed facts.
- **FR-012**: Publish initial fixed working progress and subsequent fixed progress
  as accessible assistant chat messages. Sample activity at five-second intervals
  while active, publishing only when the displayed wording changes. Progress never
  requires a caller reply and stops while waiting or after a terminal state. Suppress
  optional progress at 90 assistant entries; all notices count toward the 100-entry
  assistant bound. Background rendering never writes the textbox.
- **FR-013**: Keep all coordinator/task/proposal state server-side and transient;
  no storage, tracing, durable SDK sessions, provider calls in tests, or content in
  diagnostics. Preserve existing diagnostic allowlists and catalog task names.
- **FR-014**: Publish fixed validation, capacity, and status-only recovery feedback
  as accessible assistant chat messages while retaining rejected input and preserving
  the existing Retry, Reset, Cancel, Approve, and Reject controls. Do not append
  redundant status labels after a substantive answer, question, refusal, or recovery
  message.

### Key Entities

- Conversation: generation, ordered dialogue, accepted-count and publication sequence.
- Input event: receipt sequence, input revision, text, and question/proposal seen on receipt.
- Change proposal: finite decision, source event, original/new task and revision,
  publication sequence, one-shot version, and account-bound detail.
- Committed task: caller verification, typed capability facts, completed step IDs,
  random task ID, remaining active budget, and finite status.
- Display-only assistant notice: fixed application-owned progress, validation, or
  capacity copy in ordered chat history; excluded from model context and diagnostics
  and counted within the assistant-entry limit.

## Success Criteria

### Measurable Outcomes

- **SC-001**: A second caller input is accepted and displayed within one second
  while a deterministic capability is blocked, on desktop and mobile.
- **SC-002**: No stale next capability, question, or completion after accepted
  interruption; exactly one active worker per session in barrier/race tests.
- **SC-003**: At 50 active sessions, ingress/render finish within one second;
  nominal delivery interval 250ms, no unbounded queued render events.
- **SC-004**: Deterministic privacy, lifecycle, account-attempt, confirmation,
  bounds, and desktop/mobile browser tests pass without external provider access.
- **SC-005**: In browser checks, progress and validation/capacity notices are
  announced as chat entries, do not execute HTML or enter model context, and do not
  exceed the existing assistant-entry bound; optional progress stops at 90 entries.

## Assumptions and Compatibility

The supplied planning defaults are approved by the explicit implementation request.
One browser tab only; no reconnect replay, cross-tab sync, durable broker, new
provider/classifier, or simultaneous tasks. This feature supersedes only alternating
submission/pair limits and finish-or-cancel switching in features 001/002/003.
Catalog authorization, privacy, account attempt limits, and timing ceilings remain.
Rollout/rollback resets transient sessions and requires no data migration. Peer
review remains a release gate; deterministic models do not prove provider semantics.