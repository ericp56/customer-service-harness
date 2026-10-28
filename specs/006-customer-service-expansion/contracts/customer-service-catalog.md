# Customer Service Catalog Contract

## Scope and authority

- Public interaction stays in the existing Gradio chat; no public HTTP endpoint is added.
- Feature 006 expands the public task catalog beyond feature 003's exact-three-task limit. Feature 003's verification, privacy, refusal, and support-contact guarantees remain in force, as does feature 005's ordered event/confirmation contract.
- The model can route to a fixed `TaskName` and invoke only strict, task-specific server capabilities. Application code validates caller provenance, verified account ownership, state transitions, result facts, and final customer-visible wording.
- Current-time lookup does not require account verification. Every account/profile/card/case read or write requires `current_account == verified_account` and a non-ended session.

## Operations

| Customer workflow | Allowed behavior | Mutation rule |
|---|---|---|
| Retrieve Account | Return favorite color, preferred name, card-on-file status/alias for verified account | None; stored zip is never returned |
| Update Account | Change one allowed profile setting or toggle fixed demo alias | Version-bound Yes/No approval, then one application commit |
| List Open Cases | Return open cases owned by verified account only | None |
| Open Case | Accept bounded caller description and generate case number | Offer list; commit after approval |
| Follow Up | Select owned open case and append bounded caller update | Commit after approval |
| Close Case | Select owned open case | Commit after approval; terminal status |

Real card data, generic arbitrary-field updates, account/zip edits, foreign-case access, reopening, updates to closed cases, and external service effects are unsupported.

## Approval and event ordering

1. Application validates caller-supplied values and creates a canonical server-owned proposal bound to session generation, account identity, target record revision, task revision and proposal version.
2. Customer sees the exact proposed action and responds Yes or No for the current proposal.
3. Yes commits only after all bindings and preconditions are rechecked. The application records the committed step before publishing success.
4. No, stale/replayed approval, changed identity, correction, switch, cancellation, reset, expiry, session end, or record-version conflict produces no commit.
5. Existing correction/cancel/switch proposals remain distinct from mutation approval. Do not treat one Yes as authorization for both.
6. Already committed changes survive task retry within the same conversation; they do not survive conversation reset, expiry, or process restart.

## Privacy and diagnostics

- Never request or accept card PAN, CVV, expiration, bank credentials, or payment-provider tokens.
- Never return/log stored zip, preferred name, case descriptions, follow-up text, prompts, model output, tool payload, proposal contents, case IDs, or card data.
- Preserve existing fixed diagnostic allowlists. Task names may be emitted only as values of the fixed catalog enum. No new content-bearing fields.
- No provider tracing, durable storage, browser persistence, or third-party integration.

## Safe outcomes

- Profile and case replies are rendered from validated application-owned typed facts, not free-form model output.
- Empty open-case lists receive fixed copy. Unknown, foreign, closed, duplicate, stale, malformed or unapproved targets fail closed without data change.
- Clarification asks only for the missing value. Rejected input remains unaccepted where required by the existing event contract.
- Preserve account and zip attempt limits, safe support transfer, current-time GMT wording, cancellation, retry, reset, accessibility, and existing event bounds.
