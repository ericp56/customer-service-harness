# Catalog Boundary Contract

1. Ingress validates length/session constraints and accepts ordered caller events independently of work. Feature 005 replaces the pair bound with 50 accepted caller messages, 100 assistant entries and an inbox of 10. Tool-free catalog admission remains mandatory; an ended session makes no model call.
2. Malformed routing, unknown decisions and provider errors yield fixed recovery with no capabilities. Unrelated requests yield fixed refusal; greetings/help yield fixed catalog copy.
3. Only admitted catalog capabilities run. Transfer requires account verification before contact; model instructions cannot change limits or retrieve a stored zip. Account/zip arguments must be caller-supplied in the current message.
4. Display text is application-rendered from typed tool facts/caller state. A valid task label cannot authorize an arbitrary completed answer, clarification, proposal or invented contact/time.
5. Standalone refusal/help clears the submitted input and allows further sending. It has no Retry, no `task_completed` record, no arbitrary diagnostic task name and no account/zip diagnostic values. Diversions retain the paused catalog task and do not mutate counters.
6. A separable mixed request displays only validated catalog output plus fixed refusal. Ambiguous/malformed work fails closed. No quoted bait or implementation detail is displayed.
7. All application callback paths enforce the boundary. Legacy sync callbacks never call a provider. Lower-level approval lifecycle helpers remain internal and are not a public catalog task.
8. Routing/execution/reconciliation together have at most eight manager turns per processing batch, sixty seconds active same-task work excluding confirmation waits, ten seconds per attempt, no automatic retries or parallel tools, and five-second sampled progress.
9. A multi-call model response is rejected before dispatch. Exact-input retries reuse accepted events and typed committed facts. Feature 005 replaces finish-or-cancel switching with versioned confirmation: No resumes committed facts; Yes switches to a fresh task ID/budget or corrects identity with the remaining budget. Old verification/contact and old-account ZIP detail cannot authorize a corrected identity.

See [the async event contract](../../005-async-conversation/contracts/conversation-events.md)
for checkpoint, proposal version, reset/unload/expiry and publication ordering.

## Acceptance Matrix

Unit: five unrelated examples; forged names/direct completion; denied tool and fabricated arguments; trusted time/contact; attempt limits; mixed/help; numeric continuation; invalid route; timeout and cancellation. Integration: fixed refusal, no Retry/completion, preserved clarification, privacy-safe stdout. Browser: desktop/mobile refusal then valid task/continuation, no sensitive browser storage. Fake provider boundaries only in automated checks.