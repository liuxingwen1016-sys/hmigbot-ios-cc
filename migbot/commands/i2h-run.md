---
description: Run the full i2h migration pipeline (spec → plan → execute → verify → retrospect)
---

`$ARGUMENTS` may contain `--require-runtime-plan`, `--require-visual-and-ut`, and `--require-behavior`. Pass the requested flags to every preflight call. Visual and UT mode selects CHECK-3/4. Behavior mode also requires passing runtime evidence for CHECK-5 before acceptance can finish.

For full timing, also pass `--require-bound-visual` on every call. Record `visual-scope: <project-relative path>` and `visual-comparison-sha256: <comparison report digest>` in the Verify report after archiving the current comparisons. Preflight replays the approved pairs and checks that visual and behavior evidence use the same signed HAP and device.

## Goal

Sequence the five pipeline-stage skills end-to-end for iOS → HarmonyOS migration.

## 1. Detect mode

Read `.migbot/config.json` from current directory.

- If file doesn't exist, stop: `"migbot not installed. Run /i2h-init first."`
- If `confirmed != true`, stop: `"Config not confirmed. Run /i2h-init first."`

## 2. Run the deterministic preflight

Do not infer completion from a file existing. Run the importable checker before
dispatching any stage:

```bash
python3 "${CLAUDE_PLUGIN_ROOT:-.claude}/skills/i2h-plan/scripts/pipeline_resume.py" \
  --project-root . --summary \
  --out spec/.i2h/i2h-run-status.json
```

Use `resume_stage`, the stage check results, and error codes from the JSON printed by the checker. The full report at `spec/.i2h/i2h-run-status.json` remains the machine receipt. Retrieve a named check from it when a diagnosis needs its detailed evidence.
The checker exits `1` while the pipeline is incomplete; that is the normal
resume case, so continue by reading the JSON rather than treating the exit code
alone as a stage failure.
The checker resolves the canonical indexed-v1 paths first and then the
explicitly supported legacy aliases. A legacy path is reported in
`legacy_paths` and in the stage's `marker.legacy` field; do not silently copy or
replace it while probing. Use `--strict` when a migration policy requires every
stage to be rewritten to canonical paths.

A stage is complete only when all of its checks pass:

- schema-2 markers match the target input hash, their `content_sha256`, and
  every recorded artifact hash;
- `i2h-plan` has an approved schema-2 UI delivery inventory whose
  `target_input_sha256` matches the spec evidence, and the ownership checker
  returns `PASS`;
- execute, verify, and retrospect reports contain recognizable identity/status
  evidence; static-only runs must explicitly record their deferred runtime or
  device checks and verification markers.

If the JSON status is `incomplete`, dispatch exactly `resume_stage`. Its check
errors identify the work to recover in that stage, including missing completion
artifacts. Checks for later stages are diagnostic until their stage is dispatched.
Honor a stage marked complete by the checker even when an acknowledged historical
diagnostic is retained. Apply each dispatched Skill's own prerequisites and stop
advancing if the post-stage check still reports it incomplete. A stale UI delivery
contract must be resolved in Plan before Execute can consume it.

With bound visual verification enabled, `current_ui_delivery.dispatch_diagnostic`
shows the frozen input status for units with missing conversion reports. Recover
READY units through the normal Execute dispatch. For BLOCKED units, resolve the
listed inputs before retrying. Follow the original Execute checks when the
diagnostic is UNAVAILABLE. The stage remains incomplete while reports are missing.

## 3. Run each stage

For each stage from the resume target through stage 5:

1. Announce: `"Starting stage <N>/5: <id>"`
2. Invoke skill: `Skill(skill="<skill-name>")`
3. Summarize outcome (2-3 lines)
4. Run the same deterministic checker command with `--summary` again and inspect the current stage's
   `checks` object; never check marker file existence directly.
5. Auto-advance only when that stage is complete.

For Spec through Verify, time the actual dispatch with the same preflight command and the same gate flags.
Before stage-specific preparation and Skill invocation, add `--timing start --timing-stage <stage>`.
A return code of 1 reports an incomplete pipeline; when JSON contains a running `timing` receipt, the start succeeded.

Save the returned `timing.run_id` and pass it as `--timing-run <id>` to subsequent timing calls.
Use `--timing finish --timing-stage <stage> --timing-run <id>` for step 4, after any device runs,
visual comparisons and repairs for that attempt have returned. Also finish normally failed attempts.
Keep the timing ID for retries within the same invocation. For a new invocation start a new timing ID.
If execution is interrupted without a finish, the receipt retains the running attempt and unknown end time.
Timing measures this invocation through passing Verify, including time between stage attempts.
Use `timing.observed_wall_seconds` for the elapsed span through the last finished
attempt, including failed attempts and gaps. `timing.observed_until` identifies its
cutoff during a retry or interruption. The two-hour result requires passing Verify.
Use `first_verify_ready_seconds` for the first preflight that admits Verify,
`first_verify_start_seconds` for dispatch, and `observed_after_first_verify_seconds`
for the measured span from that dispatch through the latest finished attempt.
Use `pipeline_resume.py --project-root <project> --timing-report --timing-run <id>`
to read one recorded run and summarize attempt durations by stage, gaps between
attempts, and time since the first Verify dispatch. Running attempts keep an
unknown duration. Use the original operation receipts for model, device, and
visual-review breakdowns within attempts.
New receipts compare monotonic time with the UTC elapsed time. A difference
over two seconds marks the measurement partial. Both elapsed values must be
below 7,200 seconds to meet the deadline.
Full timing binds the approved Plan artifact set and the replayed visual and behavior
receipts. If the Plan changes, the evidence is missing, or a pre-existing receipt
is retained unchanged, report the recorded duration with `scope_gaps`.
A run resumed after Spec or missing any strict gate flag has partial timing.
Timing binds the active CC scripts and instructions at the first start. If they change, retain the
original receipt and start a new measured run. Historical receipts without this fingerprint can record partial timing.

Before invoking `i2h-execute`, consume the approved UI delivery contract and
write the ownership receipt. Use the `path` returned in
`stages[i2h-plan].checks.delivery`; the path below is the canonical example.
If the checker selected a supported legacy candidate, pass that reported path
instead of assuming the canonical filename:

```bash
python3 "${CLAUDE_PLUGIN_ROOT:-.claude}/skills/i2h-plan/scripts/ui_state_ownership.py" \
  --project-root . \
  --inventory spec/baseline/ui-delivery-approved.json \
  --out spec/execution/ui-state-ownership.json
```

Require `status: PASS` in the receipt and in the preflight JSON. The execute
skill must use the same approved inventory; it must not regenerate a draft or
silently broaden the state scope.

On failure, halt: `"Stopped at <id> due to error. Resume with /i2h-run."`

## 4. After stage 5

Run the checker one final time. Print the five stage results from its JSON and
continue only when `status` is `complete` and `resume_stage` is `complete`.

Print the stage results and `verification.unpassed_checks`. Label an ended static run as static when runtime checks are missing. The report gate does not certify product behavior, state coverage or the end-to-end time budget.

Remind user:
```
All five stages complete.

Next steps:
1. Review reports in docs/
2. Test on HarmonyOS device
3. Run /i2h-build to compile (if not done)
```
