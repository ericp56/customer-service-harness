# Catalog Boundary Data Model

- **Catalog route**: Strict finite disposition (task, continuation, decline, help), optional fixed TaskName and mixed-request flag. No reply or rationale. Inconsistent fields are rejected. Continuation resolves only against a paused catalog task.
- **Admitted task**: The parent catalog enum stored on transient TaskState and ledger. Transfer account prerequisites do not replace it.
- **Capability facts**: Typed transient time, lookup outcome, zip outcome and support contact. Produced only by successful authorized tool execution, never parsed from arbitrary model prose. Facts used for a response belong to the current submission.
- **Caller input**: Current message held transiently on the ledger to validate account/zip argument provenance. It is never part of diagnostics or storage.
- **Retry facts**: Frozen capability facts and their transient submission input are retained on TaskState after failure. Retrying that exact input reuses completed facts rather than repeating a lookup/attempt. New input or a clarification turn starts a fresh facts slice; the caller/session and call/step ledger remain intact.
- **Scope result**: Finite declined/help outcome, fixed response copy and unchanged caller state. On diversion, retain the previous paused task; otherwise end the current non-catalog submission without a catalog completion.

Verification counters, account matching, support selection and ended-session transitions remain owned by `src/accounts.py`. Reset clears all transient state. Existing diagnostics receive only fixed outcome/status values and the existing safe snapshot; no routing reasons, facts, prompts or arguments.