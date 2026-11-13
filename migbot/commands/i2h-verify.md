---
description: Run full iOS migration Verify, first functional Verify, or a targeted functional recheck
argument-hint: "[full | behavior | recheck] [--signed-hap PATH --device ID --run RECEIPT ...]"
---

Read `$ARGUMENTS` for the requested scope. With `full` or no mode, invoke
`Skill(i2h-verify)` and pass any explicit CHECK selection.

For `behavior` or `recheck`, read the native UITest section of
`${CLAUDE_PLUGIN_ROOT:-.claude}/skills/i2h-verify/references/check5-behavior-verify.md`.
Use the current signed HAP and receipts from the authorized device. If the user
requests a device run, use the project's existing native runner and its approved
scenarios. For a recheck, require the first full runner receipt and the exact
scenarios to rerun. Report the missing input if the runner or receipt is unavailable.

Use the installed Python entry point for both modes:

```bash
python3 "${CLAUDE_PLUGIN_ROOT:-.claude}/skills/i2h-plan/scripts/acceptance_plan.py" behavior --help
```

Pass `--baseline` and repeat `--case` for a targeted recheck. Pass actual
`--run` receipts from oldest to newest. With a rebuilt HAP, pass the previous
full receipt only as `--baseline` and supply current-HAP evidence as `--run`.
Use the fresh `spec/verify/check5/behavior-summary.json` after exit 0 or 1.
An exit of 2 means an invalid or missing input. Keep the original scenario
and AC totals and report failures, unrun scenarios, and unverified criteria.
Keep these modes within functional Verify. Use the user's repair request
to determine whether product code may be edited.
