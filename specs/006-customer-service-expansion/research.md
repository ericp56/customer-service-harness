# Research: Expanded Customer Service Options

## Decision: Keep the new sample records in one server-owned conversation snapshot

**Rationale**: The application has no datastore and feature 005 requires transient server-side state. A snapshot initialized for each new `SessionCoordinator` supports repeatable demos and deterministic tests without implying persistence or cross-session identity.

**Alternatives considered**: Process-global mutable fixtures would leak edits between callers; a database would expand scope, retention obligations, deployment needs and privacy risk. Neither fits this release.

## Decision: Keep identity verification separate from the profile/case records

**Rationale**: `src/accounts.py` owns account/zip verification and attempt limits. The new profile/case domain can refer to account numbers while requiring `CallerSession.verified_account == current_account` at each data boundary. Stored zip remains only in the verification authority and is never part of a read result.

**Alternatives considered**: Merging profile data and zip verification into a model-visible account object would broaden exposure and couple unrelated state transitions.

## Decision: Use field-scoped capabilities behind customer-facing Retrieve Account and Update Account workflows

**Rationale**: Customer-facing CRUD labels should be understandable, but capability schemas must remain narrow. Account retrieval returns only allowlisted fields; updates accept one setting operation/value at a time. Card actions toggle a predefined demo alias and never receive payment data. Case actions bind ownership from verified server state, not model arguments.

**Alternatives considered**: A generic `set_account(field, value)` would increase authorization surface and make prompt mistakes more consequential. A generic CRUD tool is rejected.

## Decision: Treat every write as a version-bound app-owned mutation proposal

**Rationale**: Existing public approval helpers are a simulated no-op and are not sufficient to commit mutable records. The coordinator must own a canonical pending operation, target, account, data revision, task generation and proposal version. Yes revalidates all bindings and commits exactly once; No or stale intent does not mutate.

**Alternatives considered**: Immediate mutation after zip verification eliminates an important customer-control boundary; reusing the task-runtime simulated action would incorrectly report success without changing the sample data.

## Decision: Use strict size and lifecycle limits

**Rationale**: The feature spec fixes case count, follow-up count, description/update length, preferred-name length and color choices. These bounds keep state small, inputs displayable and task processing predictable.

**Alternatives considered**: Unbounded descriptions and histories conflict with the existing bounded task and transcript architecture.

## Decision: Seed deterministic, distinct fictional data

**Rationale**: Different profile values and cases for accounts 123 and 456 make authorization and filtering observable in tests. Account 123 begins without a demo card; account 456 has the fixed demo alias. Each account has open work and the overall fixture has at least one closed case.

**Alternatives considered**: Identical profiles or cases would make cross-account data leaks harder to detect; random fixtures would make routine tests flaky.

## Project integration

Use Python 3.14 frozen dataclasses and pure transition functions; strict Pydantic/Agents schemas remain the model boundary. Reuse `TaskName`, `allowed_capabilities`, task ledger checkpoints, the ordered async coordinator and current fixed chat controls. No dependency, endpoint, persistent store, diagnostics fields, real card integration or external support system is added.
