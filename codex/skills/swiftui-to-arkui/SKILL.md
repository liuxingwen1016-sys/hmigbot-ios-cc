---
name: swiftui-to-arkui
description: Audit, plan, and migrate iOS UIKit/SwiftUI projects into HarmonyOS ArkUI/ETS in controlled feature batches. Use when you need to port an iOS View-based UI to ArkUI, especially for ViewController/SwiftUI View/Storyboard/XIB codebases where one-shot migrations miss subviews or components, produce wrong screens, or leave syntax and build errors.
metadata:
  type: domain
  domain: migration
  tags:
  - migration
  - ios
  - uikit
  - swiftui
  - arkui
---
# SwiftUI To ArkUI

## Overview

Use this skill to turn iOS UIKit/SwiftUI UI migration into a controlled pipeline instead of a one-shot rewrite. First scan the source UI graph, then generate a per-feature batch, migrate only that batch into ArkUI, and verify both dependency coverage and target build health before moving on.

## Supported Scope

Apply this skill when the source UI is primarily built from:

- iOS `UIViewController` and child view controllers
- SwiftUI `View` structs
- Storyboard and XIB files
- `UITableView` / `UICollectionView` with cells and data sources
- `UINavigationController`, tab bars, modal presentations
- Alerts, action sheets, custom modals

Do not assume direct support for:

- Complex Core Animation or CALayer manipulations
- Custom UIView subclasses with heavy `drawRect:` overrides
- AVPlayer with complex video surface behavior
- MapKit or custom gesture-heavy views
- Business logic, background jobs, or persistence migration

For those cases, read [references/unsupported-patterns.md](references/unsupported-patterns.md) and leave explicit TODOs instead of inventing behavior.

## Project Artifacts

Keep project-specific state under `.codex/ui-migration/` in the repo being migrated:

- `manifest.json`: source UI inventory created by `scripts/scan_ios_ui.py`
- `migration-index.json`: source files and pages already covered by migrated target code
- `batches/*.md`: human-readable migration task packs
- `batches/*.json`: machine-readable batch metadata used by the coverage checker

Do not hardcode project-specific page names or target paths into this skill.

## Workflow

### 1. Audit The Source UI

Run the scanner before planning or coding:

```bash
python3 scripts/scan_ios_ui.py \
  --source-root /path/to/ios-project \
  --output-path /path/to/repo/.codex/ui-migration/manifest.json
```

The scanner inventories:

- page candidates (`UIViewController`, SwiftUI `View`)
- Storyboard and XIB references
- likely modal, cell, child view controller dependencies
- unresolved resource references (Assets.xcassets) that need manual review

Use the manifest as the source of truth for what exists. Do not start migration from memory or from a single ViewController file.

### 1.5. MANDATORY: Deep Verify The Manifest

After the scanner produces `manifest.json`, you MUST run the deep verification script. Do NOT skip this step.

```bash
python3 scripts/deep_verify_ios.py \
  --source-root /path/to/ios-project \
  --manifest-path /path/to/repo/.codex/ui-migration/manifest.json
```

The script performs inheritance-based scanning (not just filename patterns) across ALL targets to find ViewControllers, SwiftUI Views, Custom Views, Cells, and Coordinator patterns that the filename-based scanner missed. It cross-checks every found class against the manifest and outputs a report to `.codex/ui-migration/manifest-verify-report.json`.

If the script exits with code 1 (missing items found):
1. Review the missing items in the report
2. Update `manifest.json` to include the missing pages and dependencies
3. Re-run the script until it reports `COMPLETE`

Do NOT proceed to step 2 until the deep verification passes.

### 2. Build One Feature Batch

Generate a task pack for one or more related entry pages:

```bash
python3 scripts/build_feature_pack.py \
  --manifest-path /path/to/repo/.codex/ui-migration/manifest.json \
  --page-names HomeViewController,ProfileView
```

This creates both a Markdown batch file and a JSON batch file. Use the Markdown file for migration work and keep the JSON file for coverage checking.

Choose the smallest batch that still makes sense:

- app shell first (TabBarController, NavigationController)
- one feature ViewController plus its direct children
- one modal family
- one list screen plus its cell component

Never ask to migrate the entire repo in one pass.

### 3. Read Only The Needed References

Before writing code:

- read [references/uikit-to-arkui-mapping.md](references/uikit-to-arkui-mapping.md) for UIKit control mapping
- read [references/swiftui-to-arkui-mapping.md](references/swiftui-to-arkui-mapping.md) for SwiftUI View mapping
- read [references/prompt-templates.md](references/prompt-templates.md) for task prompts
- read [references/unsupported-patterns.md](references/unsupported-patterns.md) when the batch includes custom views, player UI, or iOS-specific shell behavior

Do not load every reference file unless it is needed for the current batch.

### 4. Migrate One Batch At A Time

When migrating a batch, follow these rules:

#### 4.1 UIKit Migration Rules

- **ViewController → Page**: Each `UIViewController` becomes an `@Entry @Component` ArkUI Page
- **View hierarchy**: Translate `addSubview()` calls and Auto Layout constraints to ArkUI Column/Row/Stack
- **IBOutlet**: `@IBOutlet var label: UILabel!` → `@State label: string = ''`
- **IBAction**: `@IBAction func didTapButton()` → `Button().onClick(() => {})`
- **Storyboard segues**: `performSegue(withIdentifier:)` → `router.pushUrl()`
- **Table/Collection Views**: `UITableView` → `List`, `UICollectionView` → `Grid`

**Auto Layout → ArkUI conversion**:
- ArkUI counts margin as part of a component's own size
- `width: constraint.constant` + horizontal margin → use `calc(100% - Nvp)` or sink margin into parent padding
- Vertical margin can be kept as-is
- Every image must have explicit size contract (`width` and `height`) — iOS intrinsic content size is not safe in ArkUI

#### 4.2 SwiftUI Migration Rules

- **View → Component**: Each SwiftUI `View` becomes an `@Component` (or `@Entry @Component` for entry pages)
- **@State**: Maps directly to `@State` in ArkUI
- **@Binding**: Maps to `@Link` in ArkUI
- **@ObservedObject / @StateObject**: Maps to `@ObjectLink` + `@Observed` class
- **@EnvironmentObject**: Maps to `@Provide` + `@Consume`
- **Modifiers**: `.padding()` → `.padding()`, `.frame()` → `.width()/.height()`, `.background()` → `.backgroundColor()`
- **VStack**: → `Column()`
- **HStack**: → `Row()`
- **ZStack**: → `Stack()`
- **List**: → `List()` with `ForEach`
- **NavigationView**: → `Navigation()`

#### 4.3 Common Rules

- List direct dependencies from the batch before editing target files
- Translate static structure first, then add state and interaction wiring
- Create missing subcomponents in the same batch if the source page depends on them
- Split app shell, page, list item, modal, and section components instead of building one giant target file
- Keep unsupported or platform-specific behavior as explicit TODOs
- Do not silently drop modals, alerts, or cell types

If the source page uses child view controllers or dynamic view composition, mirror that as a parent ArkUI component plus extracted child components rather than flattening everything into one page.

### 5. Record Coverage

Keep `migration-index.json` updated after each batch. At minimum, record:

- covered source pages
- covered source files
- target files created for that batch

Then run the coverage checker:

```bash
python3 scripts/check_coverage.py \
  --batch-json /path/to/repo/.codex/ui-migration/batches/home-view.json \
  --migration-index /path/to/repo/.codex/ui-migration/migration-index.json
```

Treat missing coverage as a blocker. Fix the batch or update the migration index before moving on.

### 5.5. MANDATORY: Post-Batch Deep Verification

After coverage check passes, you MUST run this verification before proceeding to the build step. Do NOT skip this.

#### 5.5a — Completeness check: sub-dependencies

For each page in the batch, re-read the iOS source class and verify every dependency was handled:

1. **Child View Controllers**: Search the source for `addChild()`, `childViewControllers` — was each child VC translated into a sub-component?
2. **Table/Collection View Cells**: Does the source use UITableView/UICollectionView? Was each cell type migrated as a separate `@Component`?
3. **Custom Views**: Search for `addSubview()` with custom view classes — were they migrated?
4. **Modals and Sheets**: Search for `present()`, `.sheet()`, `.alert()` — was each modal/alert migrated or noted as TODO?
5. **Segues**: Does the source use Storyboard segues? Were all segue identifiers accounted for?
6. **Navigation targets**: Were all `navigationController?.pushViewController()` or `NavigationLink` targets accounted for?
7. **SwiftUI Child Views**: Does the SwiftUI View include other custom Views? Were they migrated as child components?

For each missing dependency found:
- Create the missing component immediately in this batch, OR
- Add it to the manifest as a new uncovered page/dependency and document it in the batch report

#### 5.5b — Write batch verification report

Append verification results to the batch Markdown file:

```markdown
## Post-Batch Verification

### Sub-dependency check
- Child VCs checked: N, all handled: ✅/❌
- Cell types checked: N, all handled: ✅/❌
- Modals checked: N, all handled: ✅/❌
- Segues checked: N, all handled: ✅/❌
- Custom views checked: N, all handled: ✅/❌
- Items added during verification: N

### Verdict: ✅ PASS / ⚠️ FIXED / ❌ BLOCKED
```

Only proceed to step 6 (build verification) if the verdict is ✅ PASS or ⚠️ FIXED.

### 6. Verify The Target Build

After each batch, verify the target project. This is the ONLY syntax check — the build compiler catches all type errors, missing imports, decorator issues, and ArkTS-specific constraints.

```bash
python3 scripts/verify_target_build.py \
  --target-root /path/to/target-project \
  --build-command "./hvigorw assembleHap"
```

If the build fails:
1. Read the error output carefully
2. Fix each error in the generated `.ets` files
3. Re-run the build
4. Repeat until the build passes or the only remaining errors are from files NOT created in this batch

Do NOT close the task while syntax or build errors remain in files created by this batch.

## Migration Guardrails

- Treat the migration as UI-first. Only port behavior needed to render or navigate the batch.
- Assume source dependencies are hidden in Swift files, Storyboards, XIBs, cells, modals, and child view controllers.
- Prefer reusable ArkUI components over mechanical layout conversion.
- Convert one page family at a time. Large multi-page prompts cause omissions.
- Keep source and target terminology separate. Translate structure, not class names.

## UIKit vs SwiftUI Detection

The scanner automatically detects the UI framework:

- **UIKit**: If the project uses `UIViewController`, Storyboards, XIBs
- **SwiftUI**: If the project uses SwiftUI `View` structs, `@State`, `@Binding`
- **Mixed**: If both are present, handle each page according to its framework

Tag each page in `manifest.json` with `framework: "uikit" | "swiftui"` so migration rules can adapt.

## Quick Triage

Use this skill when the user asks for things like:

- "Scan this iOS app and tell me what UI needs to move"
- "Convert this UIViewController into ArkUI"
- "Convert this SwiftUI View into ArkUI"
- "Find what the previous migration missed"
- "Generate a migration checklist before writing target UI"
- "Fix the target build after a partial UI migration"

Do not use this skill for generic iOS refactors or for non-UI business logic ports.
