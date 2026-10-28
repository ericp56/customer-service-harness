# Data Model: Expanded Customer Service Options

All values below are synthetic and transient. The account/case snapshot belongs to a single server-side conversation session and is discarded on reset, expiry, or process restart. It is never serialized to browser storage or diagnostics. The existing `CallerSession` remains the identity-verification authority; private zip values do not enter this model's read results.

## AccountProfile

- **Purpose**: Synthetic editable service settings for one fixed demo account.
- **Fields**:
  - `account_number`: immutable fixed demo identifier; links to `CallerSession.current_account`.
  - `favorite_color`: one of `red`, `blue`, `green`, `purple`, `black`, `white`.
  - `preferred_name`: 1-40 Unicode code points after trimming; caller-supplied.
  - `demo_card_alias`: fixed alias or absent; never a PAN, CVV, expiry date, or usable payment token.
  - `revision`: non-negative server-owned integer incremented after each committed update.
- **Seed values**: Account 123 has distinct favorite color/preferred name and no demo card; account 456 has different settings and the fixed demo alias.
- **Constraints**: Account number and zip are not mutable. Retrieval requires verified account equality and returns only favorite color, preferred name, and card-on-file status/masked alias.

## SupportCase

- **Purpose**: Synthetic support issue attached to exactly one demo account.
- **Fields**:
  - `case_number`: unique server-generated identifier within the conversation.
  - `account_number`: immutable owner.
  - `description`: caller-supplied, trimmed, 1-500 Unicode code points.
  - `status`: `open` or `closed`; no reopen transition.
  - `created_at`, `updated_at`: UTC ISO-8601 timestamps from application clock.
  - `follow_ups`: ordered list of at most 10 `CaseFollowUp` entries.
  - `revision`: non-negative server-owned integer incremented after each committed update/close.
- **Constraints**: At most 20 cases per conversation. List only open cases for the verified account. Follow-up and close require an owned open case. Case descriptions and updates remain transient and are never logged.

## CaseFollowUp

- **Fields**: `text` (1-500 trimmed Unicode code points), `created_at` (UTC ISO-8601 application time).
- **Constraints**: Appended only after explicit approval. Entries are immutable and ordered.

## DemoData

- **Purpose**: One conversation's sample account profiles and support cases.
- **Fields**: account-number to `AccountProfile` mapping; case-number to `SupportCase` mapping; monotonic per-session revision.
- **Seed invariants**: Contains accounts 123 and 456; each has at least one open case; at least one case is closed; profiles differ; only account 456 starts with the demo card alias.
- **Lifetime**: Created with the conversation coordinator and discarded on reset, unload, expiry or process restart.

## PendingMutation

- **Purpose**: Exact server-owned proposal for one state-changing operation.
- **Fields**: proposal version; task/generation/revision binding; verified account number; finite operation kind; canonical target ID when applicable; canonical validated value when applicable; expected record revision; `pending`/`approved`/`rejected`/`discarded` state.
- **Constraints**: Never accepted from browser input. It is consumed once. Before commit, revalidate the currently verified account, target ownership/status, expected revision, active conversation generation and proposal version. Clear on reset, expiry, account correction, switch, cancellation, session end and failed validation.

## Read and mutation operations

- `Retrieve Account`: verified account profile allowlist; no mutation.
- `Update Account`: one of update favorite color, update preferred name, save fixed demo-card alias, or remove alias.
- `List Open Cases`: verified-account filter; no mutation.
- `Open Case`: validated description; approval creates one server-generated open case.
- `Follow Up`: case selection plus validated text; approval appends one entry to an owned open case.
- `Close Case`: approval transitions one owned open case to closed.

## State transitions

```text
pending mutation -> approved -> committed once
pending mutation -> rejected | discarded (no data change)
open case -> closed (one-way)
open case -> open case with appended follow-up (bounded to 10)
closed case -> no further mutation
conversation reset/expiry -> discard DemoData and PendingMutation
```
