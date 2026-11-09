---
name: i2h-run
description: Run the full i2h migration pipeline (spec → plan → execute → verify → retrospect)
---
`$ARGUMENTS` is ignored.

## Goal

Sequence the five pipeline-stage skills end-to-end for iOS → HarmonyOS migration.

## 1. Detect mode

Read `.migbot/config.json` from current directory.

- If file doesn't exist, stop: `"migbot not installed. Run $i2h-init first."`
- If `confirmed != true`, stop: `"Config not confirmed. Run $i2h-init first."`

## 2. Run the deterministic preflight

Do not infer completion from a file existing. Run the importable checker before
dispatching any stage:

```bash
python3 "${CODEX_PLUGIN_ROOT:-.agents}/skills/i2h-plan/scripts/pipeline_resume.py" \
  --project-root . \
  --out spec/.i2h/i2h-run-status.json
```

Read `spec/.i2h/i2h-run-status.json`. Its `resume_stage` is authoritative.
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

If the JSON status is `incomplete`, resume at exactly `resume_stage`. If any
stage check contains `errors`, stop and report those error codes instead of
advancing. A marker that merely exists, an unhashed legacy marker, or a stale
UI delivery file is not completion evidence.

## 3. Run each stage

For each stage from the resume target through stage 5:

1. Announce: `"Starting stage <N>/5: <id>"`
2. Invoke skill: `Skill(skill="<skill-name>")`
3. Summarize outcome (2-3 lines)
4. Run the deterministic checker again and inspect the current stage's
   `checks` object; never check marker file existence directly.
5. Auto-advance only when that stage is complete.

Before invoking `i2h-execute`, consume the approved UI delivery contract and
write the ownership receipt. Use the `path` returned in
`stages[i2h-plan].checks.delivery`; the path below is the canonical example.
If the checker selected a supported legacy candidate, pass that reported path
instead of assuming the canonical filename:

```bash
python3 "${CODEX_PLUGIN_ROOT:-.agents}/skills/i2h-plan/scripts/ui_state_ownership.py" \
  --project-root . \
  --inventory spec/baseline/ui-delivery-approved.json \
  --out spec/execution/ui-state-ownership.json
```

Require `status: PASS` in the receipt and in the preflight JSON. The execute
skill must use the same approved inventory; it must not regenerate a draft or
silently broaden the state scope.

On failure, halt: `"Stopped at <id> due to error. Resume with $i2h-run."`

## 4. After stage 5

Run the checker one final time. Print the five stage results from its JSON and
continue only when `status` is `complete` and `resume_stage` is `complete`.

Print final summary listing all five stages and outputs.

Remind user:
```
All five stages complete.

Next steps:
1. Review reports in docs/
2. Test on HarmonyOS device
3. Run $i2h-build to compile (if not done)
```
