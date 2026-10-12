# Implementation Plan: Interruptible Async Conversation

**Branch**: unchanged | **Date**: 2026-10-11 | **Spec**: [spec.md](spec.md)

## Summary
Separate short ingress from one background worker and one timer subscriber.
Gate actual capability commit, next model/dispatch, and final publication;
use finite interruption interpretation and versioned confirmation. The subscriber
publishes fixed progress and actionable validation/recovery notices as assistant
chat entries; the separate visible status component is removed.

## Technical Context
Python 3.14.6; existing Gradio 6.27, FastAPI, Agents 0.23.1, pytest/Playwright.
No new dependencies/storage. Server-only transient gr.State. Desktop 1280x900 /
mobile 390x844; ingress/render <=1s, timer 250ms, progress 5s, inbox 10, callers
50, assistants 100 with terminal reserve, capacity 50, queue 100, attempts <=10s,
same-task active work <=60s excluding waiting, manager turns 8/batch.

## Constitution Check
Pre/post design: PASS. US1-3 recovery, FR-013 transient privacy, cohesive ownership,
fake-provider tests, measured performance, allowlisted diagnostics, compatibility
and atomic rollback satisfy I-VII. Peer review remains a release gate. No exception.

## Project Structure
- src/chat.py: frozen caller acceptance/publication and sequence metadata.
- src/conversation_runtime.py: sole new production module; lazy synchronization,
  inbox/worker, proposals, generation guards, snapshots and bounded capacity.
- src/task_runtime.py: checkpoint merge, pause-aware clock and execution bounds.
- src/task_agents.py: finite source-bound interruption through conversation model;
  hooks gate model/actual capability, not entire delegation only.
- src/tools.py: retain invocation authorization; fresh revision-prefixed step IDs.
- src/accounts.py: pure correction invalidation and counter/contact safeguards.
- src/app.py: short ingress; single subscriber never writes textbox; callable
  State initialization, TTL/delete/unload cleanup. Existing test homes reused.

## Execution Design
Short lock serializes receipt, never I/O. Each input records the currently
published proposal version. Merge actual capability caller/facts before pending
reconciliation. No resumes suspended run; confirmed change discards obsolete
continuation and rebuilds with committed counters/new revision. Pause the active
clock and reschedule timeout rather than waiting through confirmation. Retry
references accepted event and retains committed facts.
Tool-free finite interpretation validates source, stage, TaskName/detail kind.
Latest coherent conflict gets one fixed confirmation; newer conflict replaces it.
Ambiguity clarifies without tools; refusal preserves task/proposal; never echo or
reuse ZIP across identity revisions. Session end/hard controls/limits override.
One 250ms subscriber projects changed snapshots; fixed progress and actionable
notices are typed display-only assistant entries, not a separate visible status
component. Subscriber delivery announces new chat text without writing the textbox.
Progress is sampled every five seconds and deduplicated by displayed wording; it is
suppressed at 90 assistant entries. All notices count toward the 100-entry bound;
terminal recovery guidance retains the final slot. The model-context builder
excludes display-only entries. Existing substantive dialogue, proposal publication
sequences, and caller receipt order remain intact.
Only ingress clears textbox. Serialized ticks/generation guards prevent stale
rendering; capacity stores no content globally.

## Rollout and Rollback
Atomic rollout after deterministic/browser/privacy/performance and peer-review
gates. Stop active sessions before replacement. Rollback restores published
request-response wiring/prior interaction contracts, resets transient state, no
migration. Preserve catalog boundaries. No branch/commit/push/live provider calls.

## Complexity Tracking
One coordinator isolates mutable concurrency from pure rules. No broker/global
content registry/new dependency/cross-tab sync. No constitution violations.

## Implementation and Alignment Review (2026-10-11)
T001-T018 completed; T019 remains an external release gate. FR-001/002/012 map
to T003-T008; FR-003 to T004/T014/T015; FR-004/010 to T006/T010/T015;
FR-005/006/007 to T009/T010/T012; FR-008/009 to T010-T012;
FR-011 to T013-T015; FR-013 to T014-T017. SC-001/002 map to T003/T008/T012,
SC-003 to T018, SC-004 to T015/T017. All 13 FRs and 4 SCs have task coverage;
19 tasks, no unmapped implementation tasks or unresolved artifact placeholders.
Superseded pair limits/paused switching are reconciled in features 002/003,
README and repository guidance; prior pure helper contracts remain internal.

Final deterministic suite: 222 passed; explicit desktop/mobile browser suite:
22 passed. Review found and repaired dropped rapid Send events, late ingress
textbox clearing, refusal outcome/snapshot mismatch and session-end alert state.
Cleanup records terminal cancellation without duplicating already-terminal runs.
Active-time pause and identity invalidation remain server-owned and bounded.
Detailed commands, measured capacity and server readiness are in quickstart.md.

Release is not approved: independent peer review is outstanding. k6/network load,
real-provider semantics and prolonged real-browser expiry/disconnect observation
are not claimed verified. These limitations do not waive the constitution's
review/performance release requirements. No extension hooks are configured.

## Async Notice Follow-Up (2026-10-12)

Approved behavior refinement: replace the separate visible status component with
fixed assistant chat notices. See the follow-up tasks at the end of tasks.md.
The 100 assistant-entry ceiling includes notices; optional progress stops at 90,
leaving capacity for substantive dialogue and terminal recovery. Feature 002's
separate-status UI contract is superseded for the current public application.
