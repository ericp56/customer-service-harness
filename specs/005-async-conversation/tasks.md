# Tasks: Interruptible Async Conversation

## Phase 1: Gates
- [x] T001 Create approved spec/checklist/active pointer in specs/005-async-conversation/spec.md and .specify/feature.json.
- [x] T002 Generate design/contracts/tasks and analyze FR-001 through FR-013 in specs/005-async-conversation/.
## Phase 2: Foundation
- [x] T003 Add blocked-tool regression in tests/integration/test_app.py and run immediately.
- [x] T004 Add frozen independent events with 4,096/50/100 limits in src/chat.py.
- [x] T005 Add lazy coordinator/inbox 10/one worker in src/conversation_runtime.py.
## Phase 3: US1
- [x] T006 [US1] Gate capability/model dispatch and pause active budget in src/tools.py, src/task_agents.py and src/task_runtime.py.
- [x] T007 [US1] Wire short ingress/single 250ms subscriber without textbox writes in src/app.py.
- [x] T008 [US1] Prove real browser blocked-tool ingress/order/one worker in tests/e2e/test_caller_verification.py.
## Phase 4: US2
- [x] T009 [US2] Add finite source-bound reconciliation/fixed confirmations in src/task_agents.py and src/conversation_runtime.py.
- [x] T010 [US2] Implement Yes/No/latest/ambiguous/catalog switches and preserved budget in src/conversation_runtime.py.
- [x] T011 [US2] Add correction identity/counter safeguards in src/accounts.py and tests/unit/test_accounts.py.
- [x] T012 [US2] Test stale dispatch/Yes, No/no replay, early ZIP, new IDs/session-end in tests/integration/test_app.py.
## Phase 5: US3
- [x] T013 [US3] Implement cancel/reset/unload/TTL invalidation/drain in src/conversation_runtime.py and src/app.py.
- [x] T014 [US3] Preserve accepted-event retries/facts/limits/diagnostics in src/task_runtime.py and src/conversation_runtime.py.
- [x] T015 [US3] Test overflow/dedup/isolation/errors/budgets/reset/privacy in tests/integration/test_app.py and tests/unit/.
## Phase 6: Delivery
- [x] T016 Reconcile superseded contracts/docs in specs/002-agent-assisted-tasks/, specs/003-caller-service-tasks/ and README.md.
- [x] T017 Run deterministic/desktop/mobile e2e and record in specs/005-async-conversation/quickstart.md.
- [x] T018 Measure 50-session responsiveness/load availability/start review server in specs/005-async-conversation/quickstart.md.
- [ ] T019 Obtain peer review before release, recorded in specs/005-async-conversation/plan.md.

## Phase 7: Async Notices In Chat (Approved 2026-10-12)
- [x] T020 Refine feature 005 requirements, design, data model, conversation contract, and current repository guidance so async progress and actionable status feedback are chat entries rather than a separate visible component.
- [x] T021 Add deterministic regression tests for typed display-only entries, model-context exclusion, initial/activity-change progress, notice deduplication, rejected-input retention, and shared assistant bounds in tests/unit/ and tests/integration/test_app.py.
- [x] T022 Publish fixed progress and actionable ingress feedback through the session coordinator as typed display-only assistant entries, preserving receipt order and terminal recovery capacity in src/chat.py and src/conversation_runtime.py.
- [x] T023 Exclude display-only notices from model context; remove the visible status output/component and retain all existing action controls in src/task_runtime.py and src/app.py.
- [x] T024 Replace status-panel browser assertions with desktop/mobile chat-notice accessibility, ordering, input-retention, control, privacy, and 90/100-entry-bound coverage in tests/e2e/test_echo_chat.py and tests/e2e/test_caller_verification.py.
- [x] T025 Run focused unit/integration tests, full deterministic pytest, explicit desktop/mobile browser suite, and diff validation; record actual outcomes in quickstart.md.

## Dependencies and Strategy
T001 -> T002 -> T003 -> T004/T005 -> T006 -> T007/T009 -> T010/T011 ->
T008/T012 -> T013/T014 -> T015 -> T016 -> T017/T018 -> T019.
US1 first discriminating slice; atomic rollout after US2/US3. Account tests/docs
independent after foundation; no subagents needed. Checkboxes reflect actual work.
T019 is an external release gate.

The approved transcript-notice follow-up is ordered T020 -> T021 -> T022 -> T023
-> T024 -> T025. T019 remains an independent release-review gate after follow-up
verification; existing implementation tasks and their checkboxes are unchanged.

## Verification Record (2026-10-11)
T003/T006/T009-T015: focused async regressions pass; callback/domain slice 79 passed.
T017: full deterministic suite 222 passed; explicit browser-only gate 22 passed.
T018: 50 blocked fake-boundary sessions accepted/rendered second input in 39.29ms
total; 51st session rejected. This is coordinator capacity, not network load.
k6 unavailable. Review UI HTTP 200 at http://127.0.0.1:7862; configuration readiness
not_ready. T019 deliberately unchecked; no external peer review or provider
semantics claimed. Full results and limitations are in quickstart.md.

## Async Notice Verification (2026-10-12)
T025: rejected-ingress regression 2 passed; full deterministic suite 228 passed
with 347 dependency warnings in 36.95s; explicit desktop/mobile browser suite
22 passed with 347 dependency warnings in 35.34s; `git diff --check` passed.
T019 remains unchecked pending independent peer review. Network-level k6 load
remains unavailable/unverified.