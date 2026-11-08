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

## iOS navigation chrome and floating tab bars

When the iOS source places a toolbar outside a `ScrollView`, the Harmony
conversion must keep that navigation chrome outside `Scroll` as well. A
toolbar inside the scroll content is a semantic regression because it
disappears after the first swipe and makes the same route unreachable.

When the source uses a floating tab capsule, the Harmony implementation may
use a custom overlay over `Tabs`, but the scrollable content must reserve the
full overlay height plus its bottom margin. The required bottom inset is the
capsule height, the bottom margin, and the navigation-indicator safe area.
Stage-1 smoke must scroll each tab to its end and verify that the last visible
row or card remains above the capsule. A screenshot that only shows the
initial page is insufficient for this check.

The converter should preserve source-backed accessibility identifiers and
labels for every toolbar and tab action. The visual report records both the
screen comparison and the end-of-scroll reachability result. Occluded final
content is a `FAIL` finding even when the initial screenshot perceptual score
does not regress.

Interactive source controls must remain interactive Harmony controls. A SwiftUI
Picker, Toggle, Button, Stepper, or `NavigationLink` cannot be emitted as a
plain `Text` node with a coordinate-only gesture. The output must expose a
button, picker, switch, or equivalent accessibility role with the source label,
selected value, and stable identifier. Stage-1 smoke must tap every P0 picker,
toggle, save action, and primary navigation action by identifier or role. A
screen that looks close but exposes only non-clickable text is a `FAIL` finding.

## F101 camera and OCR capability closure

When the iOS source contains camera or VisionKit OCR behavior, the Harmony
delivery is not complete after a static `CameraKit` import. The execute slice
must verify the following on the selected real device when available.

- `module.json5` declares `ohos.permission.CAMERA` with a user-facing reason
  and an `EntryAbility` in-use scene.
- The page requests runtime permission through `abilityAccessCtrl` and shows a
  source-backed fallback when the user denies it.
- `cameraPicker.PickerProfile` is created with an object literal containing the
  back camera and a writable `saveUri`. Some Harmony releases expose profile
  properties as read-only after construction, so mutating `new PickerProfile()`
  is a runtime crash pattern.
- The picker call is protected on both synchronous and Promise failure paths.
  A failed camera path must leave the app alive and expose album selection,
  sample-image OCR, and manual BeanEditor entry.
- OCR distinguishes an unreadable image from an image containing no text. The
  latter remains `ERR_OCR_EMPTY` so the user can correct the image or use a
  fallback. Evidence records the actual camera result and OCR text or error.

The F101 acceptance record has separate results for permission, camera launch,
image return, OCR, sample-image fallback, album fallback, and manual entry. A
physical lens obstruction is an environmental PARTIAL result when the same
OCR chain succeeds on a sample or album image.

## F102/F103/F104 system-surface closure

System-surface features require host-owned evidence. An in-app preview with a
matching label does not satisfy the corresponding iOS capability.

- A service card uses `FormExtensionAbility`, a `type: "form"`
  `extensionAbility`, `ohos.extension.form` metadata, and a valid
  `resources/base/profile/form_config.json`. Its provider must return binding
  data and update published form IDs when the shared last-recipe snapshot
  changes. Verify add-to-host, render, refresh, and click-back to the app.
- A Live Activity adaptation uses `LiveFormExtensionAbility` with a
  `type: "liveForm"` extension and a static host-safe page. The extension must
  not import notification, camera, media, database, or UIAbility-only APIs.
  NotificationKit remains the explicit fallback for hosts that do not expose
  LiveForm activation. A successful in-app `BrewLiveActivity` preview is not
  system-surface evidence.
- Harmony shortcuts are declared through EntryAbility metadata named
  `ohos.ability.shortcuts` that points to
  `resources/base/profile/shortcuts.json`. Do not place a `shortcuts` key at
  module root on API 26. Each shortcut target carries a valid `Want` parameter
  and the EntryAbility reads `want.parameters.uri` as well as `want.uri`.
  Verify system indexing and click-back deeplink separately from static HAP
  packaging. Siri/AppIntent voice phrases have no automatic Harmony
  equivalent and remain an explicit capability gap unless a host feature is
  independently verified.
