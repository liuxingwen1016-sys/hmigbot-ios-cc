---
name: ios-fact-tree
description: Extract structured facts from iOS source code to build a fact tree covering app architecture, data models, view hierarchy, navigation patterns, state management, API endpoints, and dependencies. Use when analyzing iOS projects for migration planning, architecture understanding, or dependency mapping. Produces JSON fact trees that downstream skills can query.
type: domain
domain: migration
tags: [migration, ios, analysis, fact-extraction]
---

# iOS Fact Tree Builder

## Purpose

Extract structured "facts" from iOS Swift/Objective-C source code into a queryable JSON tree. Facts include:
- App architecture pattern (MVC, MVVM, VIPER, SwiftUI)
- ViewController and View hierarchies
- Data models (structs, classes, Core Data entities)
- ViewModels and business logic
- Navigation patterns (segues, coordinators, routers)
- State management (@State, @Published, Combine)
- API endpoints and network calls
- Third-party dependencies
- Persistence mechanisms (UserDefaults, Core Data, Keychain)

This skill is the iOS equivalent of `android-fact-tree`.

---

## Output

Produces `spec/baseline/ios-facts.json` containing:

```json
{
  "architecture": {
    "pattern": "MVVM",
    "ui_framework": "mixed",
    "uikit_ratio": 0.6,
    "swiftui_ratio": 0.4
  },
  "view_controllers": [...],
  "swiftui_views": [...],
  "view_models": [...],
  "models": [...],
  "navigation": {...},
  "state_management": {...},
  "api_endpoints": [...],
  "persistence": {...},
  "dependencies": [...]
}
```

---

## Workflow

### Step 1: Detect Architecture Pattern

Scan the project to identify the primary architecture:

**MVC (Model-View-Controller)**:
- ViewControllers contain most business logic
- Models are passive data structures
- No separate ViewModel layer

**MVVM (Model-View-ViewModel)**:
- ViewModels (ObservableObject classes) exist
- ViewControllers/Views are thin, delegate to ViewModels
- Data binding via @Published, Combine, or delegates

**VIPER (View-Interactor-Presenter-Entity-Router)**:
- Interactor, Presenter, Router classes exist
- Each screen has 5+ related files
- Protocol-heavy architecture

**SwiftUI**:
- Entire app built with SwiftUI Views
- @State, @Binding, @ObservedObject usage
- No UIViewControllers

**Mixed**:
- Both UIKit and SwiftUI present
- UIHostingController bridges

**Detection commands**:
```bash
# Count ViewControllers
VC_COUNT=$(find . -name "*.swift" -exec grep -l "UIViewController" {} \; | wc -l)

# Count ViewModels
VM_COUNT=$(find . -name "*ViewModel.swift" | wc -l)
OBSERVABLE_COUNT=$(grep -r "ObservableObject" --include="*.swift" | wc -l)

# Count SwiftUI Views
SWIFTUI_COUNT=$(grep -r "struct.*:.*View" --include="*.swift" | grep -v "UIView" | wc -l)

# Check for VIPER
INTERACTOR_COUNT=$(find . -name "*Interactor.swift" | wc -l)
PRESENTER_COUNT=$(find . -name "*Presenter.swift" | wc -l)

if [ $INTERACTOR_COUNT -gt 0 ] && [ $PRESENTER_COUNT -gt 0 ]; then
  echo "VIPER"
elif [ $VM_COUNT -gt 0 ] || [ $OBSERVABLE_COUNT -gt 0 ]; then
  echo "MVVM"
elif [ $SWIFTUI_COUNT -gt $VC_COUNT ]; then
  echo "SwiftUI"
else
  echo "MVC"
fi
```

### Step 2: Extract ViewControllers

For each ViewController class:

```bash
grep -r "class.*:.*UIViewController" --include="*.swift" -H | \
  while IFS=: read file line; do
    CLASS_NAME=$(echo "$line" | sed -E 's/.*class ([A-Za-z0-9_]+).*/\1/')
    echo "Extracting $CLASS_NAME from $file"
  done
```

For each ViewController, extract:
- **name**: Class name
- **file**: Source file path
- **superclass**: Direct parent (UIViewController, UITableViewController, etc.)
- **outlets**: @IBOutlet properties
- **actions**: @IBAction methods
- **properties**: @State-like properties
- **lifecycle_methods**: viewDidLoad, viewWillAppear, etc.
- **data_source_delegate**: UITableViewDataSource, etc.
- **storyboard_id**: Storyboard identifier
- **navigation**: Segue usage, navigationController calls

Example output:
```json
{
  "name": "HomeViewController",
  "file": "ViewControllers/HomeViewController.swift",
  "superclass": "UIViewController",
  "outlets": [
    {"name": "tableView", "type": "UITableView"},
    {"name": "titleLabel", "type": "UILabel"}
  ],
  "actions": [
    {"name": "didTapRefresh", "sender": "UIButton"}
  ],
  "properties": [
    {"name": "viewModel", "type": "HomeViewModel"}
  ],
  "lifecycle_methods": ["viewDidLoad", "viewWillAppear"],
  "data_source_delegate": ["UITableViewDataSource", "UITableViewDelegate"],
  "storyboard_id": "HomeViewController",
  "navigation": {
    "segues": ["showDetail"],
    "push_calls": ["DetailViewController"],
    "present_calls": []
  }
}
```

### Step 3: Extract SwiftUI Views

For each SwiftUI View struct:

```bash
grep -r "struct.*:.*View" --include="*.swift" | grep -v "UIView"
```

For each View, extract:
- **name**: Struct name
- **file**: Source file path
- **state_properties**: @State, @Binding, @ObservedObject, @StateObject, @EnvironmentObject
- **body_components**: Top-level components in body
- **child_views**: Referenced custom Views
- **navigation**: NavigationLink, .sheet(), .fullScreenCover()
- **modifiers**: .onAppear, .onChange, etc.

Example output:
```json
{
  "name": "HomeView",
  "file": "Views/HomeView.swift",
  "state_properties": [
    {"name": "viewModel", "wrapper": "@StateObject", "type": "HomeViewModel"},
    {"name": "isLoading", "wrapper": "@State", "type": "Bool"}
  ],
  "body_components": ["NavigationView", "List", "Button"],
  "child_views": ["PostRowView", "HeaderView"],
  "navigation": {
    "navigation_links": ["DetailView"],
    "sheets": ["SettingsView"],
    "full_screen_covers": []
  },
  "modifiers": ["onAppear", "onChange(of:)"]
}
```

### Step 4: Extract ViewModels

For MVVM projects:

```bash
find . -name "*ViewModel.swift" -o -name "*VM.swift"
grep -r "ObservableObject" --include="*.swift"
```

For each ViewModel, extract:
- **name**: Class name
- **file**: Source file path
- **published_properties**: @Published properties
- **methods**: Public methods
- **dependencies**: Injected services
- **data_binding**: How it connects to Views

Example output:
```json
{
  "name": "HomeViewModel",
  "file": "ViewModels/HomeViewModel.swift",
  "conforms_to": ["ObservableObject"],
  "published_properties": [
    {"name": "posts", "type": "[Post]"},
    {"name": "isLoading", "type": "Bool"}
  ],
  "methods": [
    {"name": "fetchPosts", "params": [], "return": "Void"},
    {"name": "refreshData", "params": [], "return": "Void"}
  ],
  "dependencies": [
    {"name": "apiService", "type": "APIService"}
  ],
  "combine_subscriptions": ["cancellables"]
}
```

### Step 5: Extract Data Models

Scan for Codable structs, classes, Core Data entities:

```bash
grep -r "struct.*:.*Codable" --include="*.swift"
grep -r "class.*:.*NSManagedObject" --include="*.swift"
```

For each model, extract:
- **name**: Type name
- **file**: Source file path
- **properties**: All properties with types
- **codable**: Whether it conforms to Codable
- **core_data**: Whether it's an NSManagedObject
- **relationships**: For Core Data entities

Example output:
```json
{
  "name": "Post",
  "file": "Models/Post.swift",
  "type": "struct",
  "conforms_to": ["Codable", "Identifiable"],
  "properties": [
    {"name": "id", "type": "UUID"},
    {"name": "title", "type": "String"},
    {"name": "content", "type": "String"},
    {"name": "authorId", "type": "UUID"},
    {"name": "createdAt", "type": "Date"}
  ],
  "codable": true,
  "core_data": false
}
```

### Step 6: Extract Navigation Patterns

Identify navigation mechanisms:

**Storyboard Segues**:
```bash
grep -r "performSegue" --include="*.swift"
grep -r "prepare(for segue:" --include="*.swift"
```

**Programmatic Navigation**:
```bash
grep -r "navigationController?.push" --include="*.swift"
grep -r "present(" --include="*.swift"
```

**Coordinator Pattern**:
```bash
find . -name "*Coordinator.swift"
```

**SwiftUI Navigation**:
```bash
grep -r "NavigationLink" --include="*.swift"
grep -r "@EnvironmentObject.*Router" --include="*.swift"
```

Output:
```json
{
  "navigation": {
    "patterns": ["Storyboard Segues", "Programmatic Push", "SwiftUI NavigationLink"],
    "coordinators": [
      {"name": "AppCoordinator", "file": "Coordinators/AppCoordinator.swift"}
    ],
    "segues": [
      {"identifier": "showDetail", "from": "HomeViewController", "to": "DetailViewController"}
    ],
    "programmatic_transitions": [
      {"from": "HomeViewController", "to": "SettingsViewController", "method": "push"}
    ]
  }
}
```

### Step 7: Extract State Management

Identify state management approaches:

**Property Wrappers**:
```bash
grep -r "@State\|@Binding\|@ObservedObject\|@StateObject\|@EnvironmentObject" --include="*.swift"
```

**Combine**:
```bash
grep -r "import Combine" --include="*.swift"
grep -r "PassthroughSubject\|CurrentValueSubject" --include="*.swift"
```

**Reactive Frameworks**:
```bash
grep -r "import RxSwift" --include="*.swift"
grep -r "Observable<" --include="*.swift"
```

Output:
```json
{
  "state_management": {
    "swiftui_property_wrappers": {
      "@State": 45,
      "@Binding": 12,
      "@ObservedObject": 8,
      "@StateObject": 15,
      "@EnvironmentObject": 5
    },
    "combine_usage": true,
    "reactive_frameworks": ["RxSwift"],
    "global_state": {
      "user_defaults": true,
      "app_storage": true,
      "shared_singletons": ["UserSession", "AppState"]
    }
  }
}
```

### Step 8: Extract API Endpoints

Scan network code for API calls:

```bash
grep -r "URL(string:" --include="*.swift"
grep -r "URLRequest" --include="*.swift"
grep -r "Alamofire.request" --include="*.swift"
```

For each API call, extract:
- **endpoint**: URL string
- **method**: GET, POST, PUT, DELETE
- **location**: File and line number
- **parameters**: Request parameters
- **response_type**: Expected response model

Example output:
```json
{
  "api_endpoints": [
    {
      "endpoint": "/api/posts",
      "method": "GET",
      "location": "Services/APIService.swift:45",
      "response_type": "[Post]"
    },
    {
      "endpoint": "/api/posts/:id",
      "method": "GET",
      "location": "Services/APIService.swift:67",
      "parameters": ["id"],
      "response_type": "Post"
    }
  ]
}
```

### Step 9: Extract Persistence

Identify data persistence mechanisms:

**UserDefaults**:
```bash
grep -r "UserDefaults.standard" --include="*.swift"
grep -r "@AppStorage" --include="*.swift"
```

**Core Data**:
```bash
find . -name "*.xcdatamodeld"
grep -r "NSPersistentContainer" --include="*.swift"
```

**Keychain**:
```bash
grep -r "Keychain" --include="*.swift"
```

**Third-party**:
```bash
grep -r "import Realm" --include="*.swift"
```

Output:
```json
{
  "persistence": {
    "user_defaults": {
      "keys": ["isDarkMode", "lastSyncDate", "userId"]
    },
    "core_data": {
      "enabled": true,
      "model_file": "MyApp.xcdatamodeld",
      "entities": ["User", "Post", "Comment"]
    },
    "keychain": {
      "enabled": true,
      "stored_items": ["authToken", "refreshToken"]
    },
    "third_party": ["Realm"]
  }
}
```

### Step 10: Extract Dependencies

Parse dependencies from:

**Swift Package Manager**:
```bash
cat Package.swift
```

**CocoaPods**:
```bash
cat Podfile
```

**Carthage**:
```bash
cat Cartfile
```

Output:
```json
{
  "dependencies": [
    {"name": "Alamofire", "version": "5.6.0", "manager": "SPM"},
    {"name": "Kingfisher", "version": "7.0.0", "manager": "SPM"},
    {"name": "Firebase", "version": "10.0.0", "manager": "CocoaPods"}
  ]
}
```

---

## Final Output Structure

Combine all extracted facts into `spec/baseline/ios-facts.json`:

```json
{
  "metadata": {
    "project_name": "MyApp",
    "analyzed_at": "2024-01-01T12:00:00Z",
    "swift_files": 127,
    "objc_files": 5
  },
  "architecture": {
    "pattern": "MVVM",
    "ui_framework": "mixed",
    "uikit_ratio": 0.6,
    "swiftui_ratio": 0.4
  },
  "view_controllers": [...],
  "swiftui_views": [...],
  "view_models": [...],
  "models": [...],
  "navigation": {...},
  "state_management": {...},
  "api_endpoints": [...],
  "persistence": {...},
  "dependencies": [...]
}
```

---

## Usage by Downstream Skills

Other skills can query this fact tree:

```bash
# Find all ViewModels
jq '.view_models[]' spec/baseline/ios-facts.json

# Find all API endpoints
jq '.api_endpoints[]' spec/baseline/ios-facts.json

# Check architecture pattern
jq '.architecture.pattern' spec/baseline/ios-facts.json
```

---

## Quick Triage

Use this skill when:
- "Analyze this iOS project's architecture"
- "What ViewControllers does this app have?"
- "Extract all API endpoints from iOS code"
- "What state management does this app use?"
- "Generate a fact tree for iOS migration planning"

Do not use for:
- UI graph building (use ios-ui-graph-builder)
- Code generation
- Actual migration work
