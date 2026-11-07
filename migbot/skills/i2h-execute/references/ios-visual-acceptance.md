# iOS visual evidence and semantic acceptance

```json
{
  "runtime_evidence": {
    "status": "audited",
    "state": "normal",
    "platform": "ios",
    "png_path": "ios-runtime.png",
    "png_sha256": "<sha256 or sha256:<hex>>",
    "ui_json_path": "ios-accessibility.json",
    "ui_json_sha256": "<sha256 or sha256:<hex>>",
    "device": {"udid": "SIMULATOR-UDID"},
    "app": {"bundle_id": "com.example.app"},
    "build_identity": "debug-build-42"
  }
}
```

`stage1_visual_scope.py` binds page and state explicitly and rejects missing files, state mismatches, hash changes, synthesized evidence, or an application identity mismatch supplied by the wiring page. The checker accepts the P0 aliases `accessibility_json_path` and `accessibility_json_sha256`, plus the legacy Android `view_xml_path` pair.

`stage1_visual_acceptance.py` compares one iOS accessibility JSON with one Harmony evidence JSON. It checks page/state, component identity, role, label, text truncation, frame and safe-area tolerances, token references, and action/navigation paths. A screenshot perceptual difference is emitted as an auxiliary metric and does not replace semantic or geometry checks.

Use `stage1_visual_report.py`'s library `summarize` function or the CLI fallback to produce page/state counts, evidence completeness, semantic coverage, geometry error, and blocked reasons. The current macOS bundle may expose an older command surface, so direct Python module invocation is the deterministic compatibility path until the execute bundle is rebuilt.

The report reserves `device_validation.ios_baseline` for the connected iPhone and `device_validation.harmony_target` for the Huawei Mate 80 Pro. The Harmony row records `preferred_device_type=real_device`, `fallback_device_type=emulator`, `selected_device_type`, `serial`, `system_version`, and `evidence_hashes`. A simulator result is recorded as an emulator result and cannot be presented as a Mate 80 Pro result. Their status remains `PENDING_P0_RUNTIME_CAPTURE` until the iOS capture, Harmony install receipt, screenshots, accessibility dump, click path, and functional path evidence are present. Device or credential failures are retained as explicit `blocked_reasons`.
