# iOS MigBot

`hmigbot-ios` is an iOS → HarmonyOS (ArkTS) migration toolkit for Claude Code. It is a platform adaptation of [`../hmigbot-1.8.0`](../hmigbot-1.8.0), whose original workflow targets Android → HarmonyOS migration.

The project keeps the original pipeline shape while replacing Android-specific inputs with iOS inputs such as Xcode projects, Swift/SwiftUI/UIKit source, Info.plist, Assets.xcassets and iOS API usage.

## Current status

The repository contains the five i2h pipeline skills, iOS reference skills, templates and scripts. The native modal visual tool contracts and installed acceptance entry points have passed the R3 checks documented below. This does not establish production readiness for arbitrary applications: signing, device capabilities, visual fidelity and complete application behavior still require project-specific verification. Earlier findings remain available in [`docs/IMPLEMENTATION_AUDIT.md`](docs/IMPLEMENTATION_AUDIT.md).

The often-cited Cuike figure of “90.8% automatic conversion” is a historical prototype estimate. It is not a compiler pass rate, behavior-equivalence result or acceptance criterion for arbitrary projects.

## 2026-11-24 update: native modal visual acceptance (R3)

This update integrates the reviewed **modal-visual R3** changes onto `main_ui_optimize` at `e057f483540fd98d36d1541bbfecb00a36b6b4e3`. It improves the reusable tool contracts and installed validation commands; it does not claim that an application has completed device acceptance or that the full migration now meets a two-hour target.

### What this version improves

| Capability | Behavior after this update |
|---|---|
| Native active-layer selection | Use the unique focused application window and the active `SheetPage` / `ModalPage` layer. Hidden nodes, foreign windows, UI extensions and covered base-page controls cannot satisfy strict page-state selectors. Independent modal branches are resolved only by the documented native own-focus evidence; ambiguous ordering remains blocked. |
| State checks around a screenshot | Run the **same approved predicate before and after capture**. A weak business readiness check alone is insufficient. If a modal appears or disappears during capture, including on the same bundle and route with a repeated control ID, do not publish an acceptable strict arrival receipt. Preserve both raw trees and their observations. |
| Actual installed application identity | Replay the built HAP's `module.json`, installation log and native bundle-query log. The approved predicate bundle, actual foreground bundle and installed HAP bundle must agree. Missing identity, another bundle/version or malformed identity evidence blocks strict replay. |
| Screenshot and raw-tree integrity | Bind arrival evidence to screenshot/tree SHA-256 values. Installed `capture-index`, assembly, visual archive and formal smoke re-read the actual evidence; missing or replaced screenshots cannot pass by retaining old labels. Strict capture summaries require the image digest recorded at capture time and cannot silently recalculate it after replacement. |
| Approved scope and multiple pairs | Rebuild scope from the current approved inventory and select each predicate by `pair_id`. Multiple pairs for the same page/state are validated separately. Dropping predicates/pairs or changing a caller-supplied schema tag cannot fall back to legacy label matching. |
| Capture-summary consistency | Keep every required pair, require a successful arrival state, bind build/install receipts to the current scope and one HAP/device, and confine raw artifacts to the current capture directory. A `BLOCKED` case with leftover files cannot become `PASS`. |
| Relationship checks without lost diagnostics | Match semantic controls only in the active layer, while keeping the original coordinate viewport and the complete raw tree for existing status-bar clipping/overlap diagnostics. A covered control cannot fill a missing foreground anchor, and activity filtering no longer discards the system status bar. |
| Plan input compatibility | Check that `verification_states` is a list before iterating. Missing/null fields remain readable in the legacy non-strict contract; invalid types and required runtime-state omissions produce structured validation errors. |
| Cross-platform CI routing | Preserve the Ubuntu/macOS/Windows matrix and original common tests. Run POSIX-only routing, cumulative-budget and related upgrade tests on macOS/Linux. Windows retains common contract and new modal regression tests. |
| Existing-project upgrades | Preserve existing project configuration and immutable old G0 receipts. The e057f48-generated G0 `PASS` fixture re-summarizes unchanged after installation, and G1 structural acceptance still passes. |

### How to enable the strict visual contract

Add `target_observation` to each relevant row of the **approved** UI inventory's `verification_states`, through the existing Plan approval process. A predicate enables strict replay for its pair even when the project-wide option is absent:

```json
{
  "bundle": "com.example.demo",
  "page_path": "pages/Root",
  "present": [{"id": "editorName"}],
  "absent": [{"id": "errorDialog"}]
}
```

To require approved predicates for **all** visual pairs, set `native_visual_observation` to `native-page-state-v2` in the project `.migbot/config.json` at a stage boundary. Missing predicates then block acceptance. Collectors must pass the same approved predicate into `capture_checkpoint`, forward its pre-capture tree to `write_visual_arrival`, and retain the resulting image/tree references. See the [native modal visual contract](migbot/skills/i2h-verify/references/native-modal-visual.md) for the API and receipt fields.

Upgrades do not automatically enable strict mode, rewrite approved scope, or manufacture missing observations in old receipts. Old non-strict receipts retain their original reading rules. Strict evidence without the required before/after trees, image binding or verified installation identity remains unverified. CHECK-5 behavior recording, `uitest_scenario.py` and `layout_from_step` are outside this update.

### Preserved capabilities and measured validation

All **48 online files** previously at risk in an older snapshot-sync patch remain byte-for-byte unchanged. Claude task routing, cumulative budgets and agent installation; Execute approved-inventory/source-only checks; Plan requirements and coverage; and Spec Swift declarations, localization, fonts, themes and actual installed-app identity remain in place, with their existing tests. The already-completed Android-binary-to-Python iOS gate migration is retained; this update does not restore old Android executables.

The reviewed tool payload and this integration checkout each passed **773 local macOS contract tests, with zero skips**, including installation/upgrade and old G0/G1 compatibility. Thirteen independent installed-entry tests produced **11 failures / 2 passes on original R2**, then **13 passes after correction**. Applying and reversing the patch at e057f48 restores all baseline file hashes. Windows/Linux CI is configured but had **not been run in that local review**; CI results after this commit must be checked separately. These are tool-contract results, not real-device application verification.

See [the independent review and validation summary](docs/patches/20261124-modal-visual-review.md), [per-file changes](docs/patches/20261123-modal-visual-port.md), and the [machine-readable validation record](docs/patches/20261124-modal-visual-validation.json). Upgrade projects at an existing stage boundary using the standard installer; do not replace tools in the middle of an active conversion stage.

## Pipeline

```text
iOS project
  ↓
i2h-spec       scan source and produce UI / feature specifications
  ↓
i2h-plan       produce indexed-v1 UI, Base and Slice plans
  ↓
i2h-execute   generate ArkTS, wire features, run gates and build loops
  ↓
i2h-verify     run static, identity and selected device checks
  ↓
i2h-retrospect collect measured results and delivery evidence
```

The intended execution model is LLM-led semantic analysis plus deterministic scripts for scanning, validation, writeback and reporting. Parallel work follows the original single-writer discipline: workers own their files, closers own shared wiring and ledgers, and findings close only after the owning check is rerun.

## Install

For Claude Code plugin mode (the supported integration), load the `migbot/`
directory, which contains the plugin manifest and the installable
`commands/`, `agents/`, `skills/` and `hooks/` trees:

```bash
claude --plugin-dir /path/to/hmigbot-ios/migbot
```

The commands then appear under the `hmigbot-ios` namespace, for example
`/hmigbot-ios:i2h-init` and `/hmigbot-ios:i2h-run`.

To install the published marketplace entry instead:

```text
/plugin install hmigbot-ios --marketplace liuxingwen1016-sys/hmigbot-ios-cc
```

```bash
cd /path/to/hmigbot-ios
./install.sh --project /path/to/HarmonyOSProject --ios /path/to/iOSApp
```

Prerequisites are Python 3.8+, Claude Code, an iOS project containing an `.xcodeproj` or `Package.swift`, and a HarmonyOS project prepared for DevEco Studio. Device checks additionally require Xcode tools, `hdc`, and the relevant device or simulator.

After installation, `/i2h-init` and `/i2h-run` are the intended workflow entry points. `/i2h-build` uses the installed `i2h-tool` helper; device and DevEco checks remain explicit runtime prerequisites.

Use `/i2h-verify behavior` for the first functional check and `/i2h-verify recheck` for a targeted
retest after a repair. Both retain the initial scenario scope and all current acceptance criteria.
Use `/i2h-verify full` to run the standard Verify stage. See the [native UITest receipt contract](migbot/skills/i2h-verify/references/check5-behavior-verify.md).

## Repository layout

```text
hmigbot-ios/
├── README.md / README_CN.md       current entry documentation
├── CHANGELOG.md                   iOS-oriented change history
├── HANDOVER.md                    current handover and next actions
├── QUICK_REFERENCE.md             current navigation and evidence policy
├── PROJECT_STATUS.md              current status snapshot
├── docs/
│   ├── METHODOLOGY.md             extracted migration method
│   ├── IMPLEMENTATION_AUDIT.md    evidence-based issue list and fixes
│   ├── ARCHIVE_INDEX.md            document map
│   ├── current/                   durable design notes
│   └── archive/                   phase reports and session history
├── migbot/                        installable commands, agents and skills
└── references/                    imported iOS expertise and source material
```

The historical reports intentionally remain available in `docs/archive/`; they are evidence of the evolution of the adaptation, not current status.

## Reference relationship

`hmigbot-1.8.0` is the Android baseline. Its architecture, gates, artifact contracts and concurrency rules are useful references, but Android assumptions must be translated before reuse. iOS-specific behavior belongs in the i2h skills and in the iOS reference skills under `migbot/skills/ios-*`.

See:

- [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md) for the extracted process and design principles.
- [`docs/ORIGINAL_VS_IOS_ANALYSIS.md`](docs/ORIGINAL_VS_IOS_ANALYSIS.md) for the original UI/resource/performance mechanisms and the iOS gap analysis.
- [`docs/IMPLEMENTATION_AUDIT.md`](docs/IMPLEMENTATION_AUDIT.md) for current defects and concrete repair plans.
- [`docs/current/UNDERSTANDING.md`](docs/current/UNDERSTANDING.md) for the original architecture rationale.
- [`docs/current/TECHNICAL_DECISION.md`](docs/current/TECHNICAL_DECISION.md) for Swift parsing decisions.

## CI contract checks

GitHub Actions runs the offline SwiftUI/UIKit fixture, i2h-execute tests, spec/plan contract tests and Python compilation on Ubuntu, macOS and Windows. The fixture records device and DevEco checks as `DEFERRED` and never fabricates runtime evidence.
