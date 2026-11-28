# iOS MigBot

`hmigbot-ios` is an iOS → HarmonyOS (ArkTS) migration toolkit for Claude Code. It is a platform adaptation of [`../hmigbot-1.8.0`](../hmigbot-1.8.0), whose original workflow targets Android → HarmonyOS migration.

The project keeps the original pipeline shape while replacing Android-specific inputs with iOS inputs such as Xcode projects, Swift/SwiftUI/UIKit source, Info.plist, Assets.xcassets and iOS API usage.

## Current status

The repository contains the five i2h pipeline skills, iOS reference skills, templates and scripts. The flow handoff commands, native symbol relationships and installed acceptance entry points have passed the macOS tool-contract checks documented below. Signing, device capabilities, visual fidelity and complete application behavior still require project-specific verification. Earlier findings remain available in [`docs/IMPLEMENTATION_AUDIT.md`](docs/IMPLEMENTATION_AUDIT.md).

The often-cited Cuike figure of “90.8% automatic conversion” is a historical prototype estimate. It is not a compiler pass rate, behavior-equivalence result or acceptance criterion for arbitrary projects.

## 2026-11-28 update: pipeline handoffs and native symbol acceptance

This update combines the four pipeline handoff fixes and the reviewed native-symbol relationship changes on the `c919b99` source baseline.

| Area | Updated behavior |
| --- | --- |
| Init → Execute | Read the canonical `.migbot/config.json.ios`, resolve relative paths against the project root, and diagnose empty, stale or inconsistent source bindings before execution. |
| Plan → Execute | Consume the indexed UI, feature and base plans with their slices. Use the old single-plan format only through the explicit legacy option. |
| Spec → resource execution | Validate the producer's `target_input_sha256`, `inventory` and resource indexes against the approved scope. Keep missing assets separate from system symbols that still need target mapping. |
| Retrospect | Count the actual source and target files and index the current receipts. Missing or unreadable inputs remain `UNKNOWN/null`; valid empty inputs remain zero. |
| Native symbol relationships | Opt into XCUI Image identifier → visible, unclipped `SymbolGlyph` leaf matching. Require matched parent buttons, compatible tab context and unambiguous repeated groups; reject conflicting descriptions. The final geometry tolerance remains **4 pt**. |
| Active source navigation | Scope source anchors to the independently presented navigation container only when an approved predicate, identifiable target modal, unique source main window and title/control binding establish that relationship. |
| Formal acceptance and upgrades | Replay the new modes from the approved pair and bound raw trees; reject forged report fields. Retain screenshot/installation identity checks, independent appearance evidence and legacy G0/G1 receipt compatibility. |

For the installed `ui_relationships.py`, choose `--native-control-roles --native-symbol-anchors` explicitly. Use `--audit-viewport --tab-bar-id <id>` for a declared custom tab bar and `--approved-source-navigation` for the approved independent source-navigation mode. Existing projects retain their original matching behavior until these options are selected. See the [relationship contract](migbot/skills/i2h-execute/references/ui-delivery-contract.md).

**Validation:** 848 local macOS contract tests passed with zero failures or skips (777 existing + 48 flow handoff + 23 native relationship regressions). Final installed-runtime checks passed: 63 related regressions and 14 separate CLI checks. Clean installation, configuration-preserving upgrade, unchanged legacy relationship replay, and old G0/G1 upgrade checks passed. Windows/Linux remain optional and were not run for this local acceptance.

This commit contains reusable tools, documentation and synthetic tool regressions. Application projects, device captures, package outputs and local maintenance logs are excluded. Application completion and visual fidelity remain project-level acceptance results.

Per-file changes and reproduction commands: [pipeline handoffs](docs/patches/20261126-flow-handoff.md) and [native symbol acceptance](docs/patches/20261128-check3-native-symbols.md). Upgrade existing projects with the normal installer at a stage boundary.

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
| macOS acceptance and optional cross-platform CI | Default pushes/PRs validate `macos-latest`. Keep Windows/Linux code and tests, but run those platforms only through the manual `cross_platform` input; their failures are non-blocking. Retain all common tests, explicit ripgrep setup and UTF-8, including isolated Python subprocess flags. |
| Existing-project upgrades | Preserve existing project configuration and immutable old G0 receipts. The e057f48-generated G0 `PASS` fixture re-summarizes unchanged after installation, and G1 structural acceptance still passes. |

The first remote CI run additionally exposed Windows console encoding, an unprovisioned ripgrep dependency and a retired macOS runner label. CI now provisions that dependency and UTF-8 explicitly and uses a supported macOS image. Static analysis uses ripgrep JSON events so Windows drive letters do not corrupt file/line parsing; failed search commands produce tool errors rather than a false zero-violation result. [macOS runner retirement notice](https://github.com/actions/runner-images/issues/13518).

**Current acceptance scope is macOS.** Windows/Linux compatibility is retained for optional investigation and is not a release requirement. In Actions → Run workflow, enable `cross_platform` only when those checks are wanted. This does not change another project’s installed tools, modify its worktree or cancel an existing task.

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

After the remote CI environment fixes, the integration checkout passed **777 local tests, zero skips**, including four new static-analysis transport regressions. This supplements the original 773-test R3 review; remote platform results remain separate.

The required **macOS CI and plugin manifest checks passed** on code commit `dc873de`: [verified Actions run](https://github.com/liuxingwen1016-sys/hmigbot-ios-cc/actions/runs/45347008395). Windows/Linux were not started by this default run and are not acceptance blockers.

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

Prerequisites are Python 3.8+, ripgrep (`rg`) for static checks, Claude Code, an iOS project containing an `.xcodeproj` or `Package.swift`, and a HarmonyOS project prepared for DevEco Studio. Device checks additionally require Xcode tools, `hdc`, and the relevant device or simulator.

After installation, `/i2h-init` and `/i2h-run` are the intended workflow entry points. `/i2h-build` uses the installed `i2h-tool` helper; device and DevEco checks remain explicit runtime prerequisites.

Use `/i2h-verify behavior` for the first functional check and `/i2h-verify recheck` for a targeted
retest after a repair. Both retain the initial scenario scope and all current acceptance criteria.
Use `/i2h-verify full` to run the standard Verify stage. See the [native UITest receipt contract](migbot/skills/i2h-verify/references/check5-behavior-verify.md).

## Flow handoff entry points (2026-11-26)

Three read-only CLI entry points provide validated inputs for Execute and Retrospect stages:

| Command | Purpose | Contract |
|---------|---------|----------|
| `.migbot/bin/i2h execute-source` | Returns resolved absolute iOS source root from `.migbot/config.json` → `ios` field. Validates project structure (`.xcodeproj` or `Package.swift`) and binding consistency with `resources-inventory.json` and `ui-delivery-approved.json`. Exit 2 on any validation error with diagnostic message (no traceback). | Used by Execute Stage 0.1 |
| `.migbot/bin/i2h execute-inputs` | Returns JSON summary of plan inputs (indexed-v1 three-plan default or explicit legacy) and static resource facts (static-v1 default). Validates plan files, `target-input.json` schema/hash, resource indexes, approved scope binding, and blocks on unresolved resources in selected scope. System symbols recorded as target mapping obligations. Strict argparse rejects unknown options and abbreviations. | Used by Execute Stage 0.4 |
| `.migbot/bin/i2h retrospect-metrics` | Returns JSON with per-direction line counts. iOS: Swift/ObjC in source root (excludes Tests/Pods). HarmonyOS: ArkTS/TS under `entry/src/main/ets/`. Status: MEASURED (with counts) or UNKNOWN (with reason, `total_lines: null`). Uses `os.walk` with explicit error handling, no symlink following. Precise per-file counting preserves files without trailing newlines. Never outputs hardcoded project-specific numbers. | Used by Retrospect Stage 2 |

**Implementation details**:
- `execute-inputs`: Real `usage.json` schema is `{"resources": {"name": {"references": [...], "resolved": bool, "disposition": str}}}` (dict, not array). System symbols (kind=system_symbol) separated from missing assets; only regular missing image/color/localization in selected scope blocks execution.
- `retrospect-metrics`: Handles permission errors, symlinks, empty vs missing directories correctly. Returns `files` count in addition to `total_lines`.
- Execute input commands reject invalid JSON/UTF-8 with exit 2. Retrospect keeps each unavailable measurement as `UNKNOWN/null` while preserving independently available data.

**Boundaries**: These commands are read-only and do not write completion markers, approved scopes, or modify project files. They validate structure and binding but do not perform resource landing, Stage 1 execution, or application Verify. Actual device verification, remote CI for Windows/Linux, and frozen `latest` package updates are outside this scope.

**Verification status**: macOS acceptance passed: **825 tests (48 new + 777 existing), zero failures/skips**, plus **32 separate installed-entry probes**. See [per-file reasons and release boundary](docs/patches/20261126-flow-handoff.md). Regression coverage in `tests/test_cc_flow_handoff.py`. Documentation updated: Execute SKILL.md loads stage-0-resources.md, Retrospect SKILL.md data-driven without hardcoded numbers, migration report template uses three-plan format, CI includes flow handoff regression step.

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

Default GitHub Actions runs the offline SwiftUI/UIKit fixture, i2h-execute tests, spec/plan/native Verify contracts and Python compilation on macOS, plus shared plugin manifest checks. Windows/Linux are retained behind the manual `cross_platform` input and are non-blocking. The fixture records device and DevEco checks as `DEFERRED` and never fabricates runtime evidence.
