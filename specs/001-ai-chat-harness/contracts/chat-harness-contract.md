# Chat Harness Interface Contract

## Purpose

This contract defines the user-visible and service boundary behavior for the conversational task
harness. It does not authorize direct external actions; authorization remains server-side.

## Identity and Access

- Every request is associated with a verified internal user identity.
- The service MUST enforce permission to use chat, confirm plans, and perform each action category.
- A browser session identifier MAY correlate UI state but MUST NOT establish identity or authorize
  a plan action.

## Conversation Operations

| Operation | Required input | Successful result | Failure result |
|-----------|----------------|-------------------|----------------|
| Start conversation | Authenticated user | New active conversation with identifier | Clear authorization or service error |
| Send message | Conversation identifier and message | Persisted message and an assistant response or focused question | Validation, permission, or temporary-service error |
| View conversation | Conversation identifier | Ordered messages, current plan, and current statuses | Not-found or access-denied result without information leakage |
| Resume conversation | Conversation identifier and user message | Current state and next actionable step | Clear blocked or archived status |
| Cancel plan | Conversation and plan identifier | Plan and eligible pending steps marked canceled | Clear reason if terminal state prevents cancellation |

## Plan Representation

Every plan returned to the user contains:

- a stable plan identifier and revision;
- a clear objective, assumptions, constraints, and risk summary;
- ordered steps with outcome, dependencies, status, and next action;
- a current overall status; and
- a digest or opaque revision token used to detect stale approvals.

The harness MUST render the server-persisted, validated plan rather than an unvalidated model
response.

## Plan Revision

When a user changes the request, the service returns an impact summary and a proposed plan
revision. The previous revision remains visible for audit but is superseded for pending work after
the revised plan is accepted. A revision invalidates approvals tied to the previous digest.

## Confirmation and Execution

1. The service presents a confirmation request for each consequential action, stating the action,
   impact, target, and relevant plan revision.
2. The user approves or declines the request.
3. On approval, the service creates a single-use, expiring confirmation bound to the user and
   plan revision.
4. Before execution, the service rechecks authorization, plan revision, confirmation status, and
   action allow-list.
5. The service returns completed, blocked, failed, or canceled status with a privacy-safe summary
   and a next action.

Duplicate submissions, stale revisions, expired confirmations, and unauthorized confirmations MUST
not cause an effect.

## Errors and Privacy

All user-facing errors state what happened, whether work was changed, and the next available
action. Errors, status messages, and diagnostics MUST NOT reveal secrets, credentials, or
unauthorized conversation information.
