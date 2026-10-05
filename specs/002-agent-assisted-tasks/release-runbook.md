# Release Runbook: Agent-Assisted Customer Tasks

This runbook covers release tasks T040 and T041. It describes how to gather
results; it does not certify the release gates. Keep both tasks open until the
checks have actually run and their aggregate results are recorded in
`quickstart.md`.

## Guardrails

- Run load validation against an isolated non-production deployment with
  release-equivalent capacity and provider configuration. The script sends
  generated synthetic message IDs, but the application still makes model
  requests and may incur provider cost.
- Never use customer conversations or real customer-service records in either
  exercise. Do not record API keys, prompts, responses, participant names,
  contact details, or verbatim participant comments in the release evidence.
- Do not capture screenshots or request/response bodies as evidence. Record
  only build/configuration identifiers that are safe to share and aggregate
  counts and timings.
- The 100-request k6 scenario measures end-to-end completion and whether a
  progress status appeared. Its `progress_observed` metric does not measure
  each five-second interval; use the separate browser timing check below for a
  cadence observation and report the limitation.

## T040: Load Validation

### Prepare

1. Confirm the target is a non-production deployment with enough capacity for
   50 concurrent virtual users. Confirm the release-equivalent model
   configuration is available through the approved secret manager or local
   environment injection. Never put credential values in commands, files, or
   evidence.
2. Confirm the app and deterministic suite are healthy:

   ```sh
   pytest
   ```

3. Install k6 on macOS if it is not already installed:

   ```sh
   brew install k6
   k6 version
   ```

4. Start the application or confirm the staging app is running. Set the target
   URL without a trailing slash and verify readiness. The default target is the
   local app at port 7860.

   ```sh
   export TARGET_URL="https://staging.example.invalid"
   curl -fsS "$TARGET_URL/readyz"
   ```

   For a local run, use `http://127.0.0.1:7860` instead. Do not use the example
   hostname literally.

### Run

From the repository root, run the checked-in scenario:

```sh
k6 run load/echo_load.js
```

It executes 100 shared iterations across 50 virtual users, with a five-minute
maximum duration. The run fails its thresholds if any measured task visibility
exceeds 60 seconds, the generated-reply rate is below 100%, or queue
saturation is observed. Treat any failed k6 check or threshold as a failed
gate; do not rerun repeatedly against a live customer deployment.

### Observe Progress Under Load

During the k6 run, submit one separate synthetic slow task from a browser on
the same staging deployment. Time when each fixed progress status becomes
visible relative to submission, and note whether updates stop at clarification
or completion. Do not capture the chat contents. This is an observational
sample, not a hard real-time guarantee or a substitute for the deterministic
five-second browser tests. The k6 `progress_observed` rate reports only whether
at least one expected progress string was present in a completed event.

### Record and Decide

Record the run in the release record and summarize it in `quickstart.md`:

- Run date, commit/build identifier, target environment name, and k6 version.
- Configured virtual users and iterations (expected: 50 and 100).
- Completed submissions, generated-reply rate, queue-saturation rate,
  `task_visible_ms` p95 and maximum, and `progress_observed` rate.
- For the browser sample, the observed progress offsets and whether progress
  stopped during customer wait/terminal state. Record deviations without
  customer content.
- Pass/fail and a brief description of any threshold or observation failure.

Pass T040 only when all 100 submissions complete with generated replies, no
queue saturation occurs, the maximum measured task visibility is below 60
seconds, and the observed progress behavior is consistent with the five-second
schedule within normal responsiveness. A delayed update caused by queue or
network delay must be reported; do not describe delivery as hard real-time.

## T041: Ten-Customer Usability Check

### Prepare

1. Recruit 10 representative customers and schedule individual sessions.
   Obtain consent for the usability exercise. Explain that the interface is a
   test environment and that all task outcomes are synthetic.
2. Use a non-production UI build with a deterministic scenario boundary that
   can reliably present progress, clarification, approval, final response, and
   recoverable failure states. Do not induce outages or alter provider
   configuration on a production deployment to create the recovery scenario.
   If a safe deterministic recovery scenario is unavailable, mark T041 blocked
   rather than substituting an uncontrolled failure.
3. Prepare four synthetic scenarios: a slow task that completes, a task that
   needs clarification, a task that pauses for the simulated approval, and a
   task that presents the fixed recovery state. Reset the conversation between
   scenarios.

### Facilitate

Give each participant the same neutral instruction: “Please use the chat to
complete the request shown. As you go, tell me what you think the status means
and what you would do next.” Do not explain the status labels or coach the
participant before recording their answer.

For each participant, observe whether they:

1. Correctly identify a temporary progress status as not being the final
   answer, then identify the final response as the task result.
2. Identify that they need to provide the requested information at
   clarification.
3. Identify that they must choose whether to approve or reject the proposed
   action before the task can continue.
4. Identify the displayed recovery next step (for example, retrying the
   request) after the recoverable failure.

Count a participant as meeting SC-007 only if item 1 and all three next-action
items are correct without facilitator hints. Do not infer understanding from
completion of the scenario alone.

### Record and Decide

Use anonymous IDs `P01` through `P10` and record only pass/fail per criterion.
Do not retain names, contact information, chat text, audio/video, or verbatim
comments in the feature artifacts. Report aggregate counts in `quickstart.md`:

- Participants completing the study: `__/10`.
- Correct progress/final distinction: `__/10`.
- Correct clarification next action: `__/10`.
- Correct approval next action: `__/10`.
- Correct recovery next action: `__/10`.
- Participants meeting the combined SC-007 measure: `__/10`.
- Outcome: pass only if at least 9 of 10 meet the combined measure; otherwise
  fail and document the issue in aggregate, non-identifying terms.

Keep T041 open until the completed counts and outcome are added to
`quickstart.md`. Do not check off the task based solely on preparing or
scheduling the study.