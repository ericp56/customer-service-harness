# Data Model: Conversational AI Task Harness

## Conversation

| Field | Description | Validation |
|-------|-------------|------------|
| id | Stable conversation identifier | Unique and server-generated |
| user_id | Authenticated owner | Must map to an authorized internal user |
| status | Conversation lifecycle state | Active, completed, canceled, or archived |
| summary | Privacy-safe continuity summary | Must exclude secrets and unnecessary sensitive data |
| created_at / updated_at | Lifecycle timestamps | Server-generated |

A conversation has many messages and plans. The owner may view and continue it only while
authorized.

## Message

| Field | Description | Validation |
|-------|-------------|------------|
| id | Stable message identifier | Unique and server-generated |
| conversation_id | Parent conversation | Must reference an accessible conversation |
| role | Author role | User, assistant, or system |
| content | Message content | Subject to length and sensitive-data handling limits |
| created_at | Submission timestamp | Server-generated |

Messages are append-only. User-visible summaries do not replace original messages.

## Request Assessment

| Field | Description | Validation |
|-------|-------------|------------|
| conversation_id | Assessed conversation | Must reference the current conversation |
| objective | Requested outcome | Required |
| constraints | Relevant boundaries | Structured list |
| assumptions | Defaults used to plan | Structured list |
| information_gaps | Questions needed before planning | Structured list |
| risk_summary | Privacy-safe risk explanation | Required when consequential actions are proposed |

An assessment creates either clarification questions or a candidate plan.

## Plan

| Field | Description | Validation |
|-------|-------------|------------|
| id | Stable plan identifier | Unique and server-generated |
| conversation_id | Parent conversation | Must reference an accessible conversation |
| revision | Immutable version number | Positive and unique within a conversation |
| status | Plan lifecycle state | Draft, awaiting confirmation, confirmed, executing, completed, failed, canceled, expired, or superseded |
| canonical_content | Validated plan structure | Must satisfy the plan schema and domain rules |
| digest | Canonical plan fingerprint | Recomputed on every revision |
| created_at | Creation timestamp | Server-generated |

Each revision has ordered plan steps. A material revision supersedes prior pending work and
invalidates outstanding confirmations.

## Plan Step

| Field | Description | Validation |
|-------|-------------|------------|
| id | Stable step identifier | Unique and server-generated |
| plan_id | Parent plan revision | Must reference the current plan revision |
| sequence | Display and execution order | Positive and unique within a plan |
| outcome | User-visible result to achieve | Required |
| status | Step lifecycle state | Pending, in progress, blocked, completed, failed, or canceled |
| dependencies | Preceding step references | Must not create a cycle |
| requires_confirmation | Consequential-action flag | True for external or irreversible effects |
| result_summary | Privacy-safe outcome | Required when terminal |

## Confirmation Grant

| Field | Description | Validation |
|-------|-------------|------------|
| id | Stable confirmation identifier | Unique and server-generated |
| plan_id / plan_digest | Authorized plan revision | Must match the current unmodified plan |
| user_id | Confirming user | Must be authorized for the action |
| decision | Authorization choice | Approved or declined |
| expires_at | Confirmation deadline | Must be in the future at issuance |
| consumed_at | One-time-use timestamp | May be set exactly once |

An execution consumes an approved, unexpired grant in the same transaction that records its effect
attempt.

## Effect Attempt

| Field | Description | Validation |
|-------|-------------|------------|
| idempotency_key | De-duplication key | Unique for the intended effect |
| plan_step_id | Authorized step | Must reference a confirmed step |
| status | External effect state | Pending, succeeded, failed, or unknown |
| external_reference | Privacy-safe provider reference | Never store credentials or full sensitive payloads |
| created_at / completed_at | Attempt timestamps | Server-generated |

## Audit Event

Audit events are append-only records of plan proposal, display, revision, confirmation, execution,
and terminal outcomes. They contain actor identity, identifiers, timestamps, action category, and
privacy-safe result metadata, not duplicated conversation content.

## State Transitions

```text
Plan:
draft -> awaiting_confirmation -> confirmed -> executing -> completed
                                      |              |-> failed
                                      |              |-> blocked
                                      |-> canceled
draft|awaiting_confirmation|confirmed -> superseded
awaiting_confirmation -> expired

Plan step:
pending -> in_progress -> completed
                     |-> blocked
                     |-> failed
pending|blocked -> canceled
```

Only validated transitions are permitted. A plan cannot execute a consequential step without a
matching, authorized, unexpired, approved, and unconsumed confirmation grant.
