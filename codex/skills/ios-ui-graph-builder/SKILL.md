---
name: ios-ui-graph-builder
description: 'Build a structured graph model (knowledge graph) from an iOS project''s UI code. Analyzes Storyboards, XIB files, Swift/Objective-C sources, Info.plist, and navigation patterns to produce four JSON files: Screen.json, Component.json, Navigation_Edge.json, Containment_Edge.json. Use whenever the user asks to analyze, model, or reverse-engineer the UI layer of an iOS project ("界面图谱", "UI 建模", "组件关系", "界面跳转关系", "screen/component/navigation map"), or simply says "analyze this iOS project" when it contains UI code. This skill creates the graph; to query an existing graph use ios-ui-graph-query.'
metadata:
  type: domain
  domain: migration
  tags:
  - migration
  - ios
  - ui-graph
  - analysis
  - uikit
  - swiftui
---
# iOS UI Graph Builder

## 静态 UI 事实分支（opt-in）

i2h-spec 的 ui_facts_policy=static-v1 使用本 skill 的 target_input.py、
static_page_facts.py 和 static_dialog_inventory.py。它们按同一个显式 target
读取源文件，合成 view_hierarchy.json，并输出 visual.json/fixture.json/templates；
旧 parse_storyboards/synthesize_meta_json/synthesize_view_hierarchy 的默认行为保留。
接入和 Gate B 规范见 [static-ui-facts](../i2h-spec/references/static-ui-facts.md)。

This skill turns an iOS frontend project into a structured graph expressed as four JSON files.
The graph captures every screen (ViewController, SwiftUI View, Modal, etc.), every UI component (UIView/SwiftUI component),
their full attributes, the parent-child containment tree, and all navigation (screen-to-screen) edges.

## Core design: division of labor

A critical insight: LLMs are good at semantic understanding (identifying screens, understanding
navigation intent, describing triggers in natural language) but unreliable at deterministic
bookkeeping (generating unique IDs for hundreds of components, counting view siblings, maintaining
cross-file ID consistency). This skill addresses this by splitting work:

| Task | Who does it | Why |
|------|-------------|-----|
| Identify screens, extract screen metadata | **LLM** | Requires understanding Swift/ObjC code, Info.plist, inheritance |
| Parse Storyboards/XIBs → Components + Containment | **Python script** | Deterministic, no missed IDs, no counter errors |
| Identify navigation, write trigger descriptions | **LLM** | Requires understanding code logic, segues, navigation patterns |
| Merge, validate, fix ID references | **Python script** | Guarantees cross-file ID consistency |

## Prerequisites

The user should provide access to an iOS project. The skill adapts to different project structures:

**Standard single-target:**
```
MyApp/
├── AppDelegate.swift / MyApp.swift
├── ViewControllers/
├── Views/
├── Models/
├── Storyboards/
│   ├── Main.storyboard
│   └── LaunchScreen.storyboard
├── Assets.xcassets/
└── Info.plist
```

**Multi-target (Workspace):**
```
MyApp.xcworkspace
├── MyApp/
├── FeatureLogin/
├── FeatureHome/
└── CommonUI/
```

**SwiftUI-only:**
```
MyApp/
├── MyApp.swift (App entry)
├── Views/
├── ViewModels/
└── Models/
```

**Mixed UIKit + SwiftUI:**
```
MyApp/
├── ViewControllers/ (UIKit)
├── Views/ (SwiftUI)
└── Storyboards/
```

At minimum these are needed:
- Swift or Objective-C source files containing screen classes
- Storyboard files (`.storyboard`) or XIB files (`.xib`) for UIKit
- SwiftUI View files (`.swift`) for SwiftUI
- `Info.plist`

---

## Workflow (7 steps)

```
1. READ the schema           → references/schema_v2.md
2. SCAN the project           → inventory all relevant files
3. EXTRACT screens (LLM)      → produce Screen.json
4. PARSE UI files (SCRIPT)    → produce components_raw.json + containment_raw.json
5. EXTRACT navigation (LLM)   → produce Navigation_Edge.json (using IDs from step 4)
6. MERGE and ENRICH (SCRIPT)  → produce final Component.json + Containment_Edge.json
7. VALIDATE (SCRIPT)          → cross-check all ID references, fix inconsistencies
```

**Before doing anything else**, read `references/schema_v2.md` in this skill's directory to load
the full JSON schema definition.

---

## Step 1: Read the schema

```bash
view <skill_directory>/references/schema_v2.md
```

Key conventions:
- Every required field must appear in the output.
- Undetermined values → `"unknown"` (strings), `{}` (objects), `[]` (arrays).
- Never omit a required field; never invent values not in the source.

---

## Step 2: Scan the project

Adapt all paths to the actual project. For multi-target projects, scan each target.

```bash
# Detect project structure (single vs multi-target)
find <project_root> -name "*.xcodeproj" -o -name "*.xcworkspace" | head -20

# Find all Storyboard files
find <project_root> -name "*.storyboard" | sort

# Find all XIB files
find <project_root> -name "*.xib" | sort

# Find all potential screen classes (UIKit)
grep -rl --include="*.swift" --include="*.m" -E \
  ":\s*UIViewController\b|:\s*UITableViewController\b|:\s*UICollectionViewController\b|:\s*UINavigationController\b|:\s*UITabBarController\b" \
  <project_root> | sort

# Find SwiftUI Views
grep -rl --include="*.swift" -E \
  ":\s*View\s*\{|struct\s+\w+View\s*:\s*View" \
  <project_root> | sort

# Find custom base ViewControllers (common in real projects)
grep -rl --include="*.swift" --include="*.m" -E \
  "class\s+Base\w*(ViewController|TableViewController)" <project_root>

# Find Info.plist
find <project_root> -name "Info.plist" | sort

# Find navigation patterns (segues, NavigationLink)
grep -rl --include="*.swift" -E \
  "performSegue\(|navigationController\?\.push|present\(|NavigationLink\(" \
  <project_root> | sort
```

Build a complete inventory before proceeding. For multi-target projects, track which target
each file belongs to.

### Identifying screens through inheritance chains

Real projects often use custom base classes. Follow the full chain:

```
BaseViewController: UIViewController       ← abstract, NOT a screen
  └── HomeViewController: BaseViewController      ← IS a screen
  └── LoginViewController: BaseViewController     ← IS a screen

BaseView: View                            ← protocol, NOT a screen
  └── HomeView: View                      ← IS a screen (SwiftUI)
```

Rules:
- Abstract/generic base classes are NOT screens (they have no layout of their own).
- A class is a screen if it (a) transitively extends UIViewController or conforms to SwiftUI View,
  AND (b) is concrete (not abstract), AND (c) has UI content (loadView/viewDidLoad or SwiftUI body).
- Also check for `UITableViewController`, `UICollectionViewController`, `UIPageViewController`,
  `UIHostingController` (SwiftUI wrapper) — they are screens if used in the project.

---

## Step 3: Extract Screen nodes → Screen.json (LLM task)

For each identified Screen class, read its source file, Storyboard/XIB entry, and Info.plist,
then produce a Screen node conforming to the schema.

### 二三层 UI 来源清单（必须全部识别，不依赖 LLM 自由发挥）

下游 [arkts-ui-coverage-auditor](../arkts-ui-coverage-auditor/SKILL.md) 依赖本步骤识别完整。漏识别会导致 spec 缺二三层 page、ArkTS 端手工补救繁重。

按以下 8 类信号穷举搜索：

| # | 信号 | 出现位置 | 层级 |
|---|---|---|---|
| 1 | `UIPageViewController` data source → `viewControllerAtIndex:` 返回的 ViewController 列表 | `.swift`/`.m` | 二层 |
| 2 | `UITabBarController` → `viewControllers` 数组的子 VC | `.swift`/`.m`/Storyboard | 二层 |
| 3 | Container View → embed segue 的目标 ViewController | Storyboard | 二/三层 |
| 4 | Modal presentation: `present(_:animated:)` 目标 ViewController | `.swift`/`.m` | 三层 |
| 5 | Alert/ActionSheet: `UIAlertController` | `.swift`/`.m` | 三层 |
| 6 | Popover: `UIPopoverPresentationController` | `.swift`/`.m` | 三层 |
| 7 | SwiftUI `.sheet()`, `.fullScreenCover()` 目标 View | `.swift` | 三层 |
| 8 | SwiftUI `NavigationLink(destination:)` 内嵌 View | `.swift` | 二/三层 |

**验证**：每个类型至少扫描一次全代码库，不可仅从主 ViewController 推断。

示例（UIPageViewController）:
```swift
func pageViewController(_ pageViewController: UIPageViewController, 
                       viewControllerAt index: Int) -> UIViewController? {
    // 返回的 VC 都是二层 Screen
    return pages[index]
}
```

### Screen node structure

For each screen, extract:

**UIKit ViewController:**
```json
{
  "id": "screen_home_view_controller",
  "name": "HomeViewController",
  "type": "UIViewController",
  "class_name": "HomeViewController",
  "storyboard_id": "HomeViewController",
  "layout_source": "storyboard",
  "layout_ref": "Main.storyboard#HomeViewController",
  "is_entry_point": true,
  "navigation_item": {
    "title": "Home",
    "back_button_title": "Back"
  },
  "presentation_style": "push",
  "modal_transition_style": "coverVertical",
  "ui_framework": "uikit"
}
```

**SwiftUI View:**
```json
{
  "id": "screen_home_view",
  "name": "HomeView",
  "type": "SwiftUI.View",
  "class_name": "HomeView",
  "storyboard_id": null,
  "layout_source": "swift",
  "layout_ref": "Views/HomeView.swift",
  "is_entry_point": true,
  "navigation_item": {
    "title": "Home"
  },
  "presentation_style": "navigation",
  "ui_framework": "swiftui"
}
```

### Layout source detection

| Pattern | layout_source | layout_ref |
|---------|--------------|------------|
| `loadView()` / Storyboard reference | `"storyboard"` | `"Main.storyboard#XXX"` |
| XIB file (`UINib(nibName:)`) | `"xib"` | `"HomeView.xib"` |
| Programmatic (`UIView()` in `loadView`) | `"code"` | `"HomeViewController.swift"` |
| SwiftUI View body | `"swift"` | `"Views/HomeView.swift"` |

### Entry point detection

Check `Info.plist` for:
- `UIMainStoryboardFile` → main entry storyboard
- `@main` attribute in SwiftUI App struct → entry point
- `UIApplicationSceneManifest` → scene configuration

---

## Step 4: Parse UI files → components_raw.json + containment_raw.json (SCRIPT task)

**CRITICAL**: DO NOT use LLM for ID generation. Too error-prone for ID reliability. Use the deterministic parser script.

```bash
python3 <skill_directory>/scripts/parse_ios_ui.py \
  <project_root> \
  spec/baseline/ui-graph/Screen.json \
  spec/baseline/ui-graph/raw_output/
```

This produces:
- `spec/baseline/ui-graph/raw_output/components_raw.json` — all Component nodes with deterministic IDs
- `spec/baseline/ui-graph/raw_output/containment_raw.json` — all parent-child edges with correct IDs

The parser:
- Generates consistent component IDs (no counter drift)
- Handles Storyboard scenes, segues, outlets
- Handles XIB files
- Extracts SwiftUI View hierarchies from AST analysis
- Extracts and classifies all attributes (frame, background, text, etc.)
- Recursively follows child views
- Connects Screen → root component containment edges

**Storyboard parsing:**
- XML-based format, parse with ElementTree
- Extract `<view>`, `<button>`, `<label>`, `<imageView>`, `<tableView>`, etc.
- Extract Auto Layout constraints → convert to conceptual layout info
- Extract IBOutlet connections → link components to code

**XIB parsing:**
- Same XML format as Storyboards
- Single view hierarchy (no scenes)

**SwiftUI parsing:**
- Parse Swift files with AST (SwiftSyntax or regex patterns)
- Extract View hierarchy from `body` property
- Identify `VStack`, `HStack`, `ZStack`, `List`, `Text`, `Button`, etc.
- Extract modifiers (`.padding()`, `.frame()`, `.background()`)

**After the script runs**, review its stderr output for any warnings (missing files, parse errors).
If there are issues, investigate and fix the Screen.json `layout_ref` values.

### Enriching component attributes (LLM task, optional)

The script extracts attributes that are directly in Storyboards/XIBs/SwiftUI. The LLM can enrich components with
information from code that isn't visible in UI files:
- Components created dynamically in code (`let label = UILabel()`)
- Property changes in `viewDidLoad` or SwiftUI `.onAppear`
- Click handlers set in code (`.addTarget()` or `.onTapGesture`)

If enrichment is needed, save LLM additions as `spec/baseline/ui-graph/llm_output/Component.json` alongside
a copy of Screen.json and Navigation_Edge.json. These will be merged in Step 6.

---

## Step 5: Extract Navigation edges → Navigation_Edge.json (LLM task)

**CRITICAL**: When writing `source_component` IDs in navigation edges, you MUST reference the exact
IDs from `spec/baseline/ui-graph/raw_output/components_raw.json` (produced in Step 4). Do NOT invent
component IDs from memory. Instead:

1. First read `components_raw.json` and note the available component IDs.
2. For each navigation action found in source code, match the triggering component to an ID
   from that list.
3. If no exact match exists, use `"unknown"`.

### Patterns to detect

| Code pattern | mechanism |
|-------------|-----------|
| `performSegue(withIdentifier: "showDetail")` | `"Segue"` |
| `navigationController?.pushViewController(vc, animated: true)` | `"Push"` |
| `present(vc, animated: true)` | `"Modal"` |
| `show(vc, sender: self)` | `"Show"` |
| `showDetailViewController(vc, sender: self)` | `"ShowDetail"` |
| `dismiss(animated: true)` | `"Dismiss"` |
| `navigationController?.popViewController(animated: true)` | `"Pop"` |
| SwiftUI `NavigationLink(destination:)` | `"NavigationLink"` |
| SwiftUI `.sheet(isPresented:)` | `"Sheet"` |
| SwiftUI `.fullScreenCover(isPresented:)` | `"FullScreenCover"` |

### For each navigation edge

1. Identify `from` (current screen) and `to` (target screen) — use Screen IDs from Screen.json.
2. Find the triggering component: look for the `@IBAction`, `.onTapGesture`, or other event handler
   that contains the navigation code. Map it to a component ID from `components_raw.json` by matching
   outlet name or SwiftUI view ID.
3. Write `trigger` as a Chinese natural-language description.
4. Extract `extras` (parameters passed), `transition_anim`, `condition`.

### Storyboard Segue support

If the project uses Storyboard segues:
1. Parse each `<segue>` element in Storyboard XML; `destination` → target screen.
2. `kind` attribute (e.g., `show`, `modal`, `popover`) → `mechanism`.
3. `identifier` → lookup in code for `prepare(for segue:)` to extract `extras`.
4. Find the triggering button/cell via `<segue>` parent element.

### Output

Save as `spec/baseline/ui-graph/Navigation_Edge.json`.

---

## Step 6: Merge and produce final outputs (SCRIPT task)

If you enriched components in Step 4's optional LLM step, merge them:

```bash
python3 <skill_directory>/scripts/merge_components.py \
  spec/baseline/ui-graph/raw_output/ \
  spec/baseline/ui-graph/llm_output/ \
  spec/baseline/ui-graph/
```

If no LLM enrichment was done, simply copy the authoritative files:

```bash
cp spec/baseline/ui-graph/Screen.json spec/baseline/ui-graph/Screen.json
cp spec/baseline/ui-graph/raw_output/components_raw.json spec/baseline/ui-graph/Component.json
cp spec/baseline/ui-graph/raw_output/containment_raw.json spec/baseline/ui-graph/Containment_Edge.json
cp spec/baseline/ui-graph/Navigation_Edge.json spec/baseline/ui-graph/Navigation_Edge.json
```

---

## Step 7: Validate (SCRIPT task)

Run cross-reference validation with auto-fix:

```bash
python3 <skill_directory>/scripts/validate_graph.py spec/baseline/ui-graph/ --fix
```

This script checks:
1. Screen ID uniqueness
2. Component ID uniqueness
3. Every `from`/`to` in Navigation edges references an existing Screen
4. Every `source_component` in Navigation edges references an existing Component
5. Every `parent`/`child` in Containment edges references an existing node
6. Every Screen has at least one Containment edge
7. All required fields are present
8. Fuzzy-matches mistyped IDs and auto-fixes them when `--fix` is passed

**If errors remain after auto-fix**, read the validation report and manually correct the issues.
Common fixes:
- A `source_component` ID that doesn't match → look up the correct ID in Component.json
- A Screen with no containment edge → check if `layout_ref` is correct

After fixing, re-run validation until it passes clean.

### Present a summary

After validation passes, present to the user:
- Total Screens (by type breakdown: UIViewController, SwiftUI View, etc.)
- Total Components
- Total Containment edges
- Total Navigation edges
- Any notable findings (orphan screens, deeply nested views, etc.)

---

## Handling large projects

For projects with >20 screens or >50 UI files:
1. The UI parser script handles any number of files automatically.
2. For Screen extraction (Step 3), process in batches by module/target.
3. For Navigation extraction (Step 5), process one screen at a time, always referencing
   the component ID list from Step 4.
4. If the project is too large for one session, process target by target and merge JSON arrays.

---

## Common pitfalls

- **Storyboard references**: `instantiateViewController(withIdentifier:)` → Storyboard ID must match.
- **Custom base classes**: `LoginViewController: BaseViewController: UIViewController` — BaseViewController is NOT a screen; LoginViewController IS.
- **Custom Views**: `class AvatarView: UIView` → `is_custom_view: true`. Don't expand internal subviews unless it's a container.
- **UITableViewCell/UICollectionViewCell**: Register via XIB or code. Include in Component.json; containment edge `source: "dynamic"`.
- **Child ViewControllers**: `addChild()` + `addSubview(childVC.view)` — each child is a separate Screen. Navigation mechanism: `"ChildViewController"`.
- **SwiftUI @ViewBuilder**: Conditional views (`if`, `switch`) create multiple possible hierarchies — document primary path.
- **UIHostingController**: Wraps SwiftUI View in UIKit — treat as bridge, the SwiftUI View is the actual screen.
- **Abstract ViewControllers**: `class BaseListViewController<T>: UIViewController` is NOT a screen. Only concrete subclasses are screens.
- **Tab bar items**: Each tab is a separate Screen with `presentation_style: "tab"`.

---

## iOS-specific considerations

### UIKit Auto Layout
- Constraints define flexible layouts, not absolute frames
- Extract constraint priorities and relations
- Convert to conceptual layout info (e.g., "centered", "fill parent")

### SwiftUI Modifiers
- Modifiers chain to define appearance and behavior
- Extract all modifiers from AST (`.padding()`, `.background()`, `.onTapGesture()`)
- Some modifiers affect layout (`frame`, `padding`), others affect style (`foregroundColor`, `font`)

### Interface Builder outlets
- `@IBOutlet` connects Storyboard/XIB components to code
- Parse connections in XML and link Component ID to code variable name

### Trait variations
- Storyboards support size classes (compact/regular width/height)
- Document primary trait collection, note variations exist

---

## See Also

- [arkts-ui-coverage-auditor](../arkts-ui-coverage-auditor/SKILL.md) — 用本 skill 产出做对账
- [ios-ui-graph-query](../ios-ui-graph-query/SKILL.md) — 查询本 skill 产出的图谱
