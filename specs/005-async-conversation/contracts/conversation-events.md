# Conversation Event Contract

Send/Enter share short serialized ingress. Accepted input clears textbox and
enters receipt-ordered dialogue immediately. Invalid/full input remains retained
and unaccepted with fixed accessible feedback appended to the chat. Only the
subscriber writes history and controls; it never writes the textbox. The separate
visible status component is not part of the public UI.
Browser ingress clears the submitted value before the request completes;
successful acknowledgements skip textbox updates so later typing survives.
Rejected input is returned for recovery. Send/Enter allow multiple triggers;
the server lock orders acceptance and suppresses rapid duplicate submissions.

One tab, server-only transient state, one worker. Commit actual capability before
reconciliation; gate every next model/capability and final publication. No obsolete
ZIP question/answer while confirmation is unresolved.

Correction/cancel/switch need fixed versioned confirmation. Yes/No must observe
that exact question on receipt. Ambiguity never dispatches; newer intent replaces
proposal. No resumes committed facts without replay. Unrelated diversion uses
fixed refusal without losing task/proposal. Never echo ZIP values.

Hard Cancel stops immediately. Reset/unload/expiry invalidate/drain/clear. Session
end and exhausted budgets/messages override pending intent. Retry references
accepted event and never duplicates dialogue/committed capability.

Bounds: inbox 10; callers 50; assistants 100 with terminal reserve; input 4,096;
timer 250ms; fixed progress initially and on changed wording at sampled 5s active
intervals; suppress optional progress from 90 assistant entries; count all notices
within 100 assistant entries and reserve the final entry for terminal recovery;
same-task active 60s excluding waiting; manager 8 turns/batch including
interpretation; specialist 4; attempt 10s/no retry; no parallel capability; active
capacity 50; queue 100. Display-only notices are excluded from model context and
diagnostics. Avoid redundant progress/status echoes after substantive dialogue.

Supersedes only alternating/50-pair/paused finish-or-cancel rules in features
001/002/003. Catalog authorization/privacy/diagnostic allowlists/attempts remain.