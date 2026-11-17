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

When the target uses a custom floating tab bar, pass its actual UITest
container ID to `ui_relationships.py --audit-viewport --tab-bar-id <id>`.
The report records the detected bounds or null when the surface is absent.
Multiple visible matches or invalid bounds are errors. The declared ID and
result are replayed against the same tree digest at visual acceptance.
This adds viewport diagnostics and preserves the comparison verdict.
For UITest trees that expose native presentations in stacking order, add
`--respect-presentation` to omit bars fully covered by a later visible
`SheetPage` or `ModalPage`. The report retains the declared bar bounds
alongside the effective bounds used for the viewport audit.

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

## Navigation titles and charts

For a SwiftUI destination with `navigationTitle`, identify whether the existing
target route host owns the navigation title. Compare with the recorded native
expansion mode. In Stack navigation, verify that the route host renders the
title and that scrolling and return produce the expected states.

For Swift Charts, capture the visible axes, labels, gridlines, series layout
and scale together with the actual dataset. Verify label size on the device
if the target uses a Canvas. Include the chart's spoken summary where the source
supplies one.

For an immersive window with a transparent status bar, verify the legibility
of the system foreground against the actual app background in light, dark
and follow-system modes. The window owner should update the status bar after
an explicit app appearance change as well as on system changes in follow mode.

## F101 camera and OCR capability closure

Determine whether the approved iOS source takes a photo or continuously recognizes
text in an in-app preview. `capability_gate.py` checks the approved source anchors
against their frozen hashes and reports `source_camera_mode`. A stale or unavailable
anchor requires source evidence recovery before Stage 5 can pass.

- `module.json5` declares `ohos.permission.CAMERA` with a user-facing reason
  and an `EntryAbility` in-use scene.
- The page requests runtime permission through `abilityAccessCtrl` and shows a
  source-backed fallback when the user denies it.
- The structural check traces the permission request from the rendered scanner
  through its local methods and resolved service calls. Keep the request on the
  user action path and verify the granted and denied outcomes separately.
- For still capture, create `cameraPicker.PickerProfile` with an object literal containing the
  back camera and a writable `saveUri`. Some Harmony releases expose profile
  properties as read-only after construction, so mutating `new PickerProfile()`
  is a runtime crash pattern. Handle both synchronous and Promise failures.
- For `DataScannerViewController`, mount a live preview from the scanner route and
  feed preview frames into on-device OCR. Camera Kit can render one preview output
  to an `XComponent` surface and feed another to an `ImageReceiver`. Release the
  frame, session and surfaces on cancellation, confirmation and exit. A still-camera
  picker can be a fallback where the source allows one.
- Select a device-reported frame format and compatible preview aspect ratio.
  Use the same profile criteria before presenting the scanner and when starting
  the frame stream. If the device advertises previews but none match the frame
  decoder, preserve the scanner's existing unavailable state and fallback actions.
  Compare candidate resolutions with actual text. Where the device accepts
  multiple compatible profiles, retain a tested lower profile for a failed
  higher-resolution configuration. Copy rows with their reported stride and
  normalize camera orientation before sending a readable frame to OCR.
- Record the signed HAP digest and device with every result. For bundled images,
  verify the exact input bytes and then read the visible editor draft fields
  separately from the recognized text. For live scanning, record preview
  configuration, first delivered frame, actual recognized text and the
  confirmed editor fields as separate milestones.
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
## Reusing appearance judgments

When a critical finding conflicts with an original image or the native control tree, review that pair again with labeled source and target panels and the relationship report. Bind the context files by digest. Keep the first judgment and the new one. For occlusion, distinguish an entirely hidden control from a partially clipped frame, and confirm which platform has the issue before changing product layout.

An exhausted visual repair budget stops further failed repair rounds. A current assessment that passes every approved comparison on one installation can still be archived. That archive retains the exhausted repair count.

Use `lib.visual_review_reuse.reusable_reviews` before scheduling appearance reviews
or assembling their results. Compute the expected identity from the current pair,
including both images, the reviewed control trees and any additional context,
the comparison region and the rule revision. Keep the original report and its
verified execution receipt together. Reuse requires the current identity and the
report digest to match. A pair with conflicting verdicts or conflicting failure
severity needs a fresh adjudication with the disagreements recorded. An unresolved
review remains pending.

Before changing review concurrency or grouping, compare two fresh runs on the
same capture and approved scope. Use `compare_review_runs` to require complete,
digest-matched evidence and list changes to verdict or failure severity per
state. Keep benchmark output separate from the active acceptance archive.

When the reviewer disagrees with the original evidence about which device
shows a control, re-review the affected pair with both originals and a
side-by-side image labeled SOURCE iOS and TARGET HarmonyOS. Bind the labeled
image in `source_context_sha256` and archive its checked reference in
`appearance_report.review_context`. A review receipt must also bind the
approved iOS region. A contextual review still needs the original image reads
and the ordinary relationship check.

### UITest 控件角色

关系比较命令可追加 `--native-control-roles`，识别 UITest 标记为可点击的文本控件，并读取显式无障碍名称。报告记录此次选择，视觉门禁使用同一模式重放。已有报告按原模式重放。这一选项不改变几何容差或逐态验收范围。

`--audit-viewport` 在同一份报告诊断首屏控件缺失、范围裁切及目标 TabBar 交叠。长度使用归一化 iOS 点。TabBar 内部控件不参与交叠诊断。交叠反映控件框，不代表已判定遮挡层材质或交互失效，须结合截图与实际点按。视觉门禁按该报告声明的模式验证结果未被篡改。

详情导航到态稳定后，可向 `ui_relationships.py` 传入 `--audit-status-bar`，核对焦点应用的原生标题栏。
自定义标题或返回键用 `--navigation-control-id <id>` 补充。报告记录同显示器的系统状态栏边界、控件原始框和可见框。
`CLIPPED` 表示原框进入状态栏区域且控件可见区域从状态栏下方开始，`INTERSECTS` 表示原框与状态栏相交，
`UNAVAILABLE` 表示缺相应几何证据。这些是诊断结果。返回是否可用由普通入口的实际点按、页面回执和视觉对照判断。

达到返修上限后，可用 `stage1_acceptance.py --kind visual --report-only` 重放已采集的报告。输出带 `report_only: true`，可明确记录逐态结果。该命令不写接受归档、最新指针或返修账本，不提供正式放行凭据。

### Shared capture evidence

Capture preflight and report assembly list states that bind the same target image and control tree in `shared_capture_groups`. Shared evidence across distinct pages can represent a visible parent and child or a presenting page and its sheet. The comparison still evaluates each approved source pair and region. When states of the same page have distinct source evidence, they cannot pass on one shared target image and tree.

### Refresh selected checkpoints on the same installation

Pass `--base-capture <index.json>` to `stage1_visual_report.py capture-index` and list the fresh receipts with `--arrival`. Write the result to a new path. The tool revalidates the full approved denominator, the retained evidence, the signed HAP and the target device. A changed approved scope, HAP or device requires a new capture index.
同一应用包需贯通功能和视觉验收时，向 `stage1_visual_report.py capture-index` 传入 `--expected-hap-sha256`，取已验证应用 HAP 的 SHA-256。索引及后续组装会按原生回执复核该摘要。局部重采沿用基线索引的已验证摘要。

### 源端部分缺证时的逐对判图

按同一份批准范围生成 `capture-index`。源基线和目标原生到态均通过复核的比较可先进入 `review-worklist`。索引与工作清单仍返回退出码 2，`capture_gaps` 完整列出每个未就绪状态。工作清单记录 `reviewable_comparisons`，对可判部分准备输入并派发。只对有图、树和正式到态回执的条目判图。

同一冻结范围内可用部分索引作为 `--base-capture`，追加同 HAP、同设备的到态回执。源端补采后若范围摘要更新，应按新范围生成索引。已有判定只在现行的图、树、区域和判图上下文摘要复核一致时方可复用。最终验收仍要求全范围和所有比较都通过。

### 视觉返修的判图清单

完成本轮原生到态和采集索引后，先准备本轮判图输入。为每个 comparison ID 记录 `rule_version`、`ios_sha256`、`harmony_sha256`、`ios_region_px` 和 `source_context_sha256`。用本轮发给判图执行者的输入生成该 JSON，字段与回执的 `review_inputs` 一致。传入控件树时，`control_tree_sha256` 按 iOS、鸿蒙顺序记录，图像判定阶段未传树时使用空数组，由关系报告独立核对两棵树。判图协议中的平台尺寸和方向字段也要保留。

```sh
python3 stage1_visual_report.py review-worklist --project-root "$project" \
  --scope "$scope" --capture "$capture" --review-inputs "$current_inputs" \
  --prior-report "$previous_report" --out "$worklist"
```

可重复传入 `--prior-report`。工具复核当前采集、历史判图回执和当前控件树，按 `pending` 派发缺失、已变化或有冲突的判图。标为 `capture_blocked` 的条目先补设备证据。已核验的历史 FAIL 仍保留原严重级别。单次 `assemble --judgements "$worklist" "$fresh_judgements"` 可同时读取复用项和本轮新判定；先确认同一比较 ID 仅出现一次，再按正常流程运行视觉门禁。

同一状态包含多个比较区域时，`assemble` 在缺判定的报告中保留已有的
`partial_comparisons`。把这份 BLOCKED 报告交给下一次 `review-worklist`，
工具按当前摘要和原有严格门禁逐项复验后再复用。缺失区域仍需完成判定。

需要定向补判时，给同一命令追加 `--review-receipt spec/…/appearance-group-N.receipt.json`。
可重复传入，工具会复核相邻报告的摘要。只在当前批准截图仍匹配且原失败属于单对超时或
Flash 1M 平台归属错误时，把 `pending[].labeled_recheck.status` 标为 `READY`。
按行中的 `recovery_for` 记录原组号，使用两张原图、标注对照图及关系报告单独判图。
补判回执保存该组号与本轮上下文摘要。下次用包含标注上下文的当前 `--review-inputs`，
同时传入原失败和补判回执，工作清单会把已派过的项标为 `ATTEMPTED`。
可按原流程组装有效判定；失败的补判保留缺项，自动派发跳过该项。
工作清单的 `READY` 表示可以调度，正式视觉结论仍由 `assemble` 和门禁核对。

对于独立的逐对判图任务，调用方可用 `lib.visual_review_reuse.prioritize_review_groups` 按历史回执的单对耗时优先发起慢任务。该排序只读取已验证的耗时，保留全部任务。判图复用仍需验证当次图像、规则和上下文的摘要。测量策略收益时，使用相同采集索引、规则和上下文，并报告判定变化及超时。

宿主可用同模块的 `review_native_groups` 并发调用判图执行器。每组按比较数量设置
时限，多比较组超时后按单项拆分重试。发生 I/O 错误的组在批次汇总保留失败记录，
其余组继续执行。判图接受仍以执行器生成的已验证回执为准。
宿主可用 `labeled_recheck_ids` 找出平台归属校验失败或单对超时的比较。
补判只使用当前图像摘要匹配的原始失败回执，每项单独发起一次 Flash 1M 判图。
同时传入两张原图、标注对照图和关系报告，记录新上下文摘要及原组号
`recovery_for`。续跑用 `attempted_labeled_rechecks` 读取已留存的补判回执。
同一输入补判仍失败时保留缺口，继续由严格门禁报告。
