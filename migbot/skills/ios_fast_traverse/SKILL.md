---
name: ios_fast_traverse
description: Fast traversal utility for iOS source code - quickly scan Swift/Objective-C files to identify classes, ViewControllers, SwiftUI Views, properties, methods, protocols, and dependencies without deep parsing. Use when you need a quick overview of iOS project structure, file inventory, or dependency mapping without full AST analysis.
type: domain
domain: migration
tags: [migration, ios, utility, traversal]
---

# iOS Fast Traverse

## Purpose

Quickly scan an iOS project to build a lightweight inventory of:
- Swift and Objective-C source files
- Class, struct, protocol, enum declarations
- ViewControllers and SwiftUI Views
- Properties (including @IBOutlet, @State, @Published)
- Methods and functions
- Import dependencies
- Extensions
- File-to-file relationships

This is a **fast, shallow scan** (regex/grep-based), not a full AST parse. Use when you need quick insights without the overhead of full static analysis.

---

## Use Cases

1. **Project overview**: "What ViewControllers does this iOS project have?"
2. **Dependency mapping**: "What files import UIKit?"
3. **Architecture detection**: "How many UIKit vs SwiftUI files?"
4. **Quick search**: "Find all classes that conform to Codable"
5. **Pre-migration scan**: Quick inventory before deep analysis

---

## Output

Produces `spec/ios-traverse-output.json`:

```json
{
  "metadata": {
    "project_root": "/path/to/project",
    "scanned_at": "2024-01-01T12:00:00Z",
    "swift_files": 127,
    "objc_files": 5
  },
  "files": [
    {
      "path": "ViewControllers/HomeViewController.swift",
      "type": "swift",
      "classes": ["HomeViewController"],
      "protocols": [],
      "extensions": ["UITableViewDataSource"],
      "imports": ["UIKit", "Combine"],
      "line_count": 245
    }
  ],
  "classes": {...},
  "protocols": {...},
  "dependencies": {...}
}
```

---

## Workflow

### Step 1: Scan all Swift files

```bash
find <project_root> -name "*.swift" | sort > swift_files.txt
```

For each Swift file:

```bash
# Extract class declarations
grep -E "^class\s+\w+" file.swift

# Extract struct declarations
grep -E "^struct\s+\w+" file.swift

# Extract protocol declarations
grep -E "^protocol\s+\w+" file.swift

# Extract enum declarations
grep -E "^enum\s+\w+" file.swift

# Extract extensions
grep -E "^extension\s+\w+" file.swift

# Extract imports
grep -E "^import\s+\w+" file.swift
```

### Step 2: Scan all Objective-C files

```bash
find <project_root> -name "*.m" -o -name "*.h" | sort > objc_files.txt
```

For each Objective-C file:

```bash
# Extract @interface declarations (.h)
grep -E "@interface\s+\w+" file.h

# Extract @implementation (.m)
grep -E "@implementation\s+\w+" file.m

# Extract @protocol
grep -E "@protocol\s+\w+" file.h

# Extract #import
grep -E "#import\s+" file.m
```

### Step 3: Identify ViewControllers

UIKit ViewControllers:
```bash
grep -E ":\s*(UI)?.*ViewController\b" --include="*.swift" -r <project_root>
```

SwiftUI Views:
```bash
grep -E "struct\s+\w+.*:\s*View" --include="*.swift" -r <project_root>
```

### Step 4: Extract properties

Swift properties:
```bash
# @IBOutlet
grep -E "@IBOutlet.*var\s+\w+" file.swift

# @State, @Binding, @Published, etc.
grep -E "@(State|Binding|ObservedObject|StateObject|Published|EnvironmentObject)\s+(var|let)\s+\w+" file.swift

# Regular properties
grep -E "(var|let)\s+\w+:" file.swift
```

Objective-C properties:
```bash
grep -E "@property\s*\(.*\)\s*\w+\s*\*?\w+" file.h
```

### Step 5: Extract methods

Swift methods:
```bash
# Instance methods
grep -E "func\s+\w+\(" file.swift

# @IBAction
grep -E "@IBAction\s+func\s+\w+" file.swift

# @objc methods
grep -E "@objc\s+func\s+\w+" file.swift
```

Objective-C methods:
```bash
# Instance methods
grep -E "^-\s*\(.*\)\s*\w+" file.m

# Class methods
grep -E "^\+\s*\(.*\)\s*\w+" file.m
```

### Step 6: Build dependency graph

For each file, map imports to create a dependency graph:

```json
{
  "file": "HomeViewController.swift",
  "imports": [
    {"module": "UIKit", "type": "system"},
    {"module": "Combine", "type": "system"},
    {"module": "NetworkService", "type": "local"}
  ],
  "imported_by": [
    "AppDelegate.swift",
    "SceneDelegate.swift"
  ]
}
```

### Step 7: Detect patterns

**Architecture hints**:
- Many ViewControllers + few ViewModels → MVC
- Many ViewModels (ObservableObject) → MVVM
- Coordinator pattern files → Coordinator architecture
- SwiftUI Views dominate → SwiftUI architecture

**Frameworks detected**:
```bash
# UIKit
grep -c "import UIKit" *.swift

# SwiftUI
grep -c "import SwiftUI" *.swift

# Combine
grep -c "import Combine" *.swift

# Core Data
grep -c "import CoreData" *.swift
```

---

## Output Structure

### File-level

```json
{
  "path": "ViewControllers/HomeViewController.swift",
  "type": "swift",
  "line_count": 245,
  "classes": [
    {
      "name": "HomeViewController",
      "type": "class",
      "superclass": "UIViewController",
      "protocols": ["UITableViewDataSource", "UITableViewDelegate"],
      "properties": [
        {"name": "tableView", "type": "UITableView", "decorator": "@IBOutlet"},
        {"name": "viewModel", "type": "HomeViewModel", "decorator": null}
      ],
      "methods": [
        {"name": "viewDidLoad", "type": "instance", "decorator": null},
        {"name": "didTapRefresh", "type": "instance", "decorator": "@IBAction"}
      ]
    }
  ],
  "imports": ["UIKit", "Combine"],
  "extensions": []
}
```

### Class-level aggregation

```json
{
  "classes": {
    "HomeViewController": {
      "file": "ViewControllers/HomeViewController.swift",
      "type": "class",
      "superclass": "UIViewController",
      "is_view_controller": true,
      "is_swiftui_view": false,
      "line_count": 180
    },
    "HomeView": {
      "file": "Views/HomeView.swift",
      "type": "struct",
      "protocols": ["View"],
      "is_view_controller": false,
      "is_swiftui_view": true,
      "line_count": 95
    }
  }
}
```

### Dependency graph

```json
{
  "dependencies": {
    "UIKit": {
      "type": "system",
      "imported_by": ["HomeViewController.swift", "SettingsViewController.swift"]
    },
    "Combine": {
      "type": "system",
      "imported_by": ["HomeViewModel.swift", "NetworkService.swift"]
    },
    "NetworkService": {
      "type": "local",
      "file": "Services/NetworkService.swift",
      "imported_by": ["HomeViewModel.swift", "ProfileViewModel.swift"]
    }
  }
}
```

---

## Performance

Fast traverse is designed for speed over accuracy:

| Project Size | Scan Time |
|--------------|-----------|
| 50 files | ~2 seconds |
| 200 files | ~5 seconds |
| 500 files | ~15 seconds |
| 1000 files | ~30 seconds |

Much faster than full AST parsing (which can take minutes for large projects).

---

## Limitations

**This is not a full parser**:
- May miss complex syntax (multi-line declarations, nested generics)
- Doesn't understand scope (may count commented-out code)
- Doesn't resolve types (sees strings, not symbols)
- Doesn't handle conditional compilation (#if)

**Use full parsing when you need**:
- 100% accurate type resolution
- Call graph analysis
- Control flow analysis
- Semantic understanding

**Use fast traverse when you need**:
- Quick project overview
- File/class inventory
- Dependency mapping
- Pre-migration scanning

---

## Quick Commands

```bash
# Count ViewControllers
grep -r "class.*:.*UIViewController" --include="*.swift" | wc -l

# Count SwiftUI Views
grep -r "struct.*:.*View" --include="*.swift" | wc -l

# Find all @IBOutlet declarations
grep -r "@IBOutlet" --include="*.swift"

# Find all @State properties
grep -r "@State" --include="*.swift"

# List all imports
grep -r "^import" --include="*.swift" | sort -u

# Find Core Data usage
grep -r "NSManagedObject\|@FetchRequest" --include="*.swift"

# Find Combine usage
grep -r "@Published\|PassthroughSubject\|CurrentValueSubject" --include="*.swift"

# Find all protocols
grep -r "^protocol" --include="*.swift"

# Find all extensions
grep -r "^extension" --include="*.swift"
```

---

## Integration with Other Skills

Fast traverse output can feed:
- **ios-ui-graph-builder**: File inventory for targeted scanning
- **ios-fact-tree**: Quick pre-scan before deep analysis
- **i2h-spec**: Initial project structure understanding
- **swiftui-to-arkui**: Identify which files need migration

---

## Quick Triage

Use this skill when:
- "Give me a quick overview of this iOS project"
- "How many ViewControllers are there?"
- "What files import UIKit?"
- "List all SwiftUI Views"
- "Show project dependencies"

Do not use for:
- Detailed code analysis (use ios-fact-tree)
- UI graph building (use ios-ui-graph-builder)
- Actual migration work
