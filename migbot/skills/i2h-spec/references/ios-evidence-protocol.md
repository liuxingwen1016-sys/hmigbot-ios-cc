# iOS runtime evidence protocol

`ios_runtime_capture.py` may publish a current evidence manifest beside each
state capture. The manifest binds the PNG and accessibility JSON to the
read-only iOS source, exact Simulator UDID, app bundle, scenario, configuration
and checkpoint. A missing Simulator or Harmony endpoint is recorded as
`not_run` or `blocked` and never converted into a visual pass.

Use the extra identity fields when a runtime capture is selected for Spec:

```bash
python3 .claude/skills/i2h-spec/scripts/ios_runtime_capture.py \
  --source-root "$IOS_PATH" \
  --device-id "$IOS_SIMULATOR_UDID" \
  --require-device-id \
  --scenario-id cuike-smoke \
  --configuration-id Debug \
  --checkpoint-id home-normal \
  ...
```

Validate a manifest before reusing it:

```bash
python3 .claude/skills/i2h-spec/scripts/ios_evidence_protocol.py \
  validate --manifest spec/baseline/ui-snapshots/page/states/normal/manifest.json
```

Pairing is report-only until both endpoints are current. The pair protocol
allows a visual score of 0.95 for a reviewed platform design difference. Each
exception must bind the source and target manifest hashes and the exact
observation. Missing controls, wrong states, route failures and application
error dialogs remain functional failures and cannot be waived.
