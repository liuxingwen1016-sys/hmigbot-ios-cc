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

Root-page navigation chrome is source-backed. Do not add an app title, vendor
bar, or default navigation header when the iOS root page does not render one.
Keep source toolbar actions at the same edge and preserve the source first
viewport budget so Harmony-only chrome cannot push source content below the
floating tab envelope.

## Source-backed custom geometry and ordering

SwiftUI `Shape`, `InsettableShape`, `Path`, `Canvas`, and `.path(in:)` are
source geometry obligations. When the source trigger is present, the target
must preserve the outline, curves, inner label area, gradients, typography,
and shadows with an ArkUI `Shape`/`Path`/Canvas or an equivalent custom draw
implementation. A single rounded rectangle, plain text, emoji, or Unicode
glyph is a placeholder and cannot be recorded as pixel-equivalent evidence.
If an SDK limitation prevents an exact path, the decision ledger must record
the source anchor and the measured geometry difference.

Seed data and list queries must preserve the iOS source order and stable
tie-breakers. Generated timestamps must not reverse the visible order merely
to make sample dates monotonic. Acceptance evidence should include the first
viewport order and the explicit comparator used by the Harmony store.

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

When the iOS baseline presents a primary action in the initial viewport, the
Harmony page must expose that action in the initial accessibility dump as well.
Do not move a sheet's primary CTA below a long `Scroll` just because the target
device has a taller logical canvas. Keep the CTA in a fixed bottom region or
reserve enough content height for it to remain visible above the safe area.
Stage-1 smoke records the first-screen action node before any swipe, then runs
the end-of-scroll check separately. A primary CTA that appears only after a
swipe is a `FAIL` finding even when the route remains reachable.

For a source `Form` picker, compare the row geometry and selected-value affordance
before comparing the option list. The Harmony dump must expose a picker or
button-equivalent role with the source label, selected value, chevron and stable
identifier. A chip grid is acceptable only when the source itself uses a
segmented or chip control. Target-only preview cards or explanatory blocks must
follow the source section order and cannot displace About, save, or primary form
content from the initial viewport.

Sheet content must be top-aligned inside the selected detent. Do not let a
short builder column be vertically centered by the sheet or `Scroll` container,
which creates a large blank region above the title and shifts the iOS content
downward. Use an explicit top-aligned wrapper or a minimum content height when
the source sheet fills the viewport. Compare the title, first section, and
bottom CTA frames against the iOS baseline before accepting the sheet.

## F101 camera and OCR capability closure

Determine whether the approved iOS source takes a photo or continuously recognizes
text in an in-app preview. `capability_gate.py` checks the approved source anchors
against their frozen hashes and reports `source_camera_mode`. A stale or unavailable
anchor requires source evidence recovery before Stage 5 can pass.

- `module.json5` declares `ohos.permission.CAMERA` with a user-facing reason
  and an `EntryAbility` in-use scene.
- The page requests runtime permission through `abilityAccessCtrl` and shows a
  source-backed fallback when the user denies it.
- For still capture, create `cameraPicker.PickerProfile` with an object literal containing the
  back camera and a writable `saveUri`. Some Harmony releases expose profile
  properties as read-only after construction, so mutating `new PickerProfile()`
  is a runtime crash pattern. Handle both synchronous and Promise failures.
- For `DataScannerViewController`, mount a live preview from the scanner route and
  feed preview frames into on-device OCR. Camera Kit can render one preview output
  to an `XComponent` surface and feed another to an `ImageReceiver`. Release the
  frame, session and surfaces on cancellation, confirmation and exit. A still-camera
  picker can be a fallback where the source allows one.
- A failed camera path must leave the app alive and expose album selection,
  sample-image OCR, and manual BeanEditor entry.
- OCR distinguishes an unreadable image from an image containing no text. The
  latter remains `ERR_OCR_EMPTY` so the user can correct the image or use a
  fallback. Evidence records the actual camera result and OCR text or error.

Run permission, launch, OCR and fallbacks on the selected real device. For still
capture, verify the returned photo reaches the editor. For continuous scanning,
verify live frame recognition against known text, confirm and read back the editor
contents, then test cancellation and release. Keep each result separate. Report a
physical lens obstruction as an environmental PARTIAL even when sample or album
OCR passes. The static F101 report sets `behavior_verified` to false.

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
