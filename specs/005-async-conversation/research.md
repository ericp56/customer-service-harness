# Research Decisions

- Decision: callable server-only gr.State/lazy runtime handles. Rationale: Gradio
  stores initialized objects by reference; initial deepcopy has no running handles.
  Browser acceptance tests must prove concurrency, not source inspection alone.
- Decision: gate actual capability commit/next model/dispatch/publication. Rationale:
  delegation spans several turns and is not itself the safe step.
- Decision: finite tool-free source-bound interruption result, existing conversation
  model/role. No extra classifier/provider or customer-facing raw interpretation.
- Decision: pause active clock/reschedule timeout during confirmation; an outer
  wait_for must not consume the 60s budget while waiting.
- Decision: single 250ms subscriber; fixed progress is sampled every five seconds
  and appended only when wording changes, as an accessible assistant chat entry.
  Remove the separate visible status area. Validation/capacity/recovery notices
  also use the transcript while rejected input remains in the textbox. All notices
  count toward 100 assistant entries; suppress optional progress from 90 entries
  and reserve the last slot for terminal guidance. Exclude display-only messages
  from model context and diagnostics; retain one render owner and no textbox writes.
- Decision: 50 callers replaces 50 pairs; corrected identity clears verification
  while preserving attempts. Approved deliberate interaction/identity change.
- Python 3.14.6 environment configured; pinned packages retained. No unresolved
  design clarification; runtime tests prove behavior, not provider semantics.