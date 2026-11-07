---
description: Run the full i2h migration pipeline (spec → plan → execute → verify → retrospect)
---

`$ARGUMENTS` is ignored.

## Goal

Sequence the five pipeline-stage skills end-to-end for iOS → HarmonyOS migration.

## 1. Detect mode

Read `.migbot/config.json` from current directory.

- If file doesn't exist, stop: `"migbot not installed. Run /i2h-init first."`
- If `confirmed != true`, stop: `"Config not confirmed. Run /i2h-init first."`

## 2. Probe completion markers

Check stage completion:

| # | Stage | Markers |
|---|-------|---------|
| 1 | `i2h-spec` | `spec/baseline/spec-complete.txt` |
| 2 | `i2h-plan` | `spec/baseline/plans/complete.txt` |
| 3 | `i2h-execute` | `spec/execution/stage5-complete.txt` and `spec/migration-report.md` |
| 4 | `i2h-verify` | `spec/verify-report.md` |
| 5 | `i2h-retrospect` | `spec/retrospect-complete.txt` |

Resume from first incomplete stage.

## 3. Run each stage

For each stage from resume target through stage 5:

1. Announce: `"Starting stage <N>/5: <id>"`
2. Invoke skill: `Skill(skill="<skill-name>")`
3. Summarize outcome (2-3 lines)
4. Verify completion markers exist
5. Auto-advance to next stage

On failure, halt: `"Stopped at <id> due to error. Resume with /i2h-run."`

## 4. After stage 5

Print final summary listing all five stages and outputs.

Remind user:
```
All five stages complete.

Next steps:
1. Review reports in docs/
2. Test on HarmonyOS device
3. Run /i2h-build to compile (if not done)
```
