# Transient Data Model

- Frozen conversation: ordered messages/publication sequence, generation/revision;
  at most 50 callers and 100 assistants including terminal reserve.
- Assistant entries include substantive dialogue and fixed display-only notices.
  Notices count toward the same 100-entry ceiling; optional progress is suppressed
  from 90 entries onward and the final entry is reserved for terminal recovery.
- Display-only notice kinds include progress and validation/capacity feedback.
  They are accessible transcript entries but are excluded from model context and
  diagnostics. Substantive recovery messages remain model-visible where a retry
  or continuation needs that dialogue. Progress is sampled every five seconds while active,
  appended only when its fixed display wording changes, and omitted while waiting
  or terminal.
- Assistant entries include substantive dialogue and fixed display-only notices.
  Notices count toward the same 100-entry ceiling; optional progress is suppressed
  from 90 entries onward and the final entry is reserved for terminal recovery.
- Display-only notice kinds include progress and validation/capacity/recovery
  feedback. They are accessible transcript entries but are excluded from model
  context and diagnostics. Progress is sampled every five seconds while active,
  appended only when its fixed display wording changes, and omitted while waiting
  or terminal.
- Frozen input: receipt sequence, text (4,096 code points), revision, observed
  question/proposal version, retry reference. All accepted input stays in dialogue.
- Frozen proposal: version, source sequence, old/new task/revision, finite action,
  validated detail. Apply once only to post-publication Yes/No for that version.
- Coordinator: empty lazy handles initially; session lock, ordered inbox (10),
  one worker/checkpoint, fixed progress/frozen snapshots. No browser serialization,
  logs, persistence or shared content across sessions.
- Task: existing TaskState/random task_id, active budget/caller/facts/fresh step
  IDs. Same-task change retains budget; switch resets task facts/ID, not caller.
- Caller: accounts.py owns attempts. Correction clears verification/contact;
  counters persist until new known identity accepted. Session end always wins.

accept -> queued -> checkpoint -> reconcile -> confirmation wait -> apply/reject/
replace -> resume/rebuild -> independent publish. Hard controls invalidate
generation, cancel/drain, and block late publication.