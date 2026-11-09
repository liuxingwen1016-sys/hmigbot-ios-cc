---
name: ios-ui-graph-query
description: Query a structured iOS UI graph (produced by ios-ui-graph-builder) to answer questions about screens, components, navigation, containment, and dependencies. Use when the user asks about UI structure, navigation flows, component hierarchies, or relationships between screens in an iOS project. This is a read-only skill; to create or update the graph, use ios-ui-graph-builder.
metadata:
  type: domain
  domain: migration
  tags:
  - migration
  - ios
  - ui-graph
  - query
---
# iOS UI Graph Query

## Purpose

This skill queries an existing iOS UI knowledge graph (the four JSON files produced by `ios-ui-graph-builder`) to answer questions about:
- Which screens exist in the project
- What components are in a specific screen
- How screens navigate to each other
- Parent-child relationships between components
- Entry points, modal flows, and navigation patterns

It does NOT build the graph (use `ios-ui-graph-builder` for that). It only reads and queries.

---

## Prerequisites

The graph must already exist at `spec/baseline/ui-graph/`:
- `Screen.json`
- `Component.json`
- `Navigation_Edge.json`
- `Containment_Edge.json`

If these files don't exist, instruct the user to run `ios-ui-graph-builder` first.

---

## Query Capabilities

### 1. List all screens

**User request**: "Show me all screens in this iOS project"

**Query**:
```bash
jq '.[] | {id, name, type, ui_framework}' spec/baseline/ui-graph/Screen.json
```

**Output example**:
```
{
  "id": "screen_home_view_controller",
  "name": "HomeViewController",
  "type": "UIViewController",
  "ui_framework": "uikit"
}
{
  "id": "screen_profile_view",
  "name": "ProfileView",
  "type": "SwiftUI.View",
  "ui_framework": "swiftui"
}
```

### 2. Find screen by name

**User request**: "Find the HomeViewController screen"

**Query**:
```bash
jq '.[] | select(.name == "HomeViewController")' spec/baseline/ui-graph/Screen.json
```

### 3. Find entry point screens

**User request**: "What is the app's entry point?"

**Query**:
```bash
jq '.[] | select(.is_entry_point == true)' spec/baseline/ui-graph/Screen.json
```

### 4. List components in a screen

**User request**: "What components are in HomeViewController?"

**Steps**:
1. Find the screen ID
2. Find all components via containment edges

```bash
# Get screen ID
SCREEN_ID=$(jq -r '.[] | select(.name == "HomeViewController") | .id' spec/baseline/ui-graph/Screen.json)

# Find all components in this screen via containment edges
jq --arg screen "$SCREEN_ID" \
  '[.[] | select(.parent == $screen)] | map(.child)' \
  spec/baseline/ui-graph/Containment_Edge.json | \
  jq -r '.[]' | while read comp_id; do
    jq --arg id "$comp_id" '.[] | select(.id == $id)' spec/baseline/ui-graph/Component.json
  done
```

### 5. Find navigation from a screen

**User request**: "Where can I navigate from HomeViewController?"

**Query**:
```bash
# Get screen ID
SCREEN_ID=$(jq -r '.[] | select(.name == "HomeViewController") | .id' spec/baseline/ui-graph/Screen.json)

# Find navigation edges
jq --arg screen "$SCREEN_ID" \
  '.[] | select(.from == $screen) | {to, mechanism, trigger}' \
  spec/baseline/ui-graph/Navigation_Edge.json
```

**Output example**:
```
{
  "to": "screen_detail_view_controller",
  "mechanism": "Push",
  "trigger": "点击列表项"
}
{
  "to": "screen_settings_view",
  "mechanism": "Modal",
  "trigger": "点击设置按钮"
}
```

### 6. Find navigation to a screen

**User request**: "What screens navigate to ProfileView?"

**Query**:
```bash
# Get target screen ID
TO_SCREEN=$(jq -r '.[] | select(.name == "ProfileView") | .id' spec/baseline/ui-graph/Screen.json)

# Find incoming navigation edges
jq --arg to "$TO_SCREEN" \
  '.[] | select(.to == $to) | {from, mechanism, trigger}' \
  spec/baseline/ui-graph/Navigation_Edge.json | \
  while read edge; do
    FROM_ID=$(echo "$edge" | jq -r '.from')
    FROM_NAME=$(jq --arg id "$FROM_ID" -r '.[] | select(.id == $id) | .name' spec/baseline/ui-graph/Screen.json)
    echo "$edge" | jq --arg name "$FROM_NAME" '. + {from_name: $name}'
  done
```

### 7. Find component by attribute

**User request**: "Find all UIButton components"

**Query**:
```bash
jq '.[] | select(.view_type == "UIButton")' spec/baseline/ui-graph/Component.json
```

**User request**: "Find all Text components in SwiftUI"

**Query**:
```bash
jq '.[] | select(.view_type == "Text")' spec/baseline/ui-graph/Component.json
```

### 8. Find component parent

**User request**: "What is the parent of component comp_home_button_1?"

**Query**:
```bash
COMP_ID="comp_home_button_1"

# Find parent via containment edge
PARENT_ID=$(jq -r --arg child "$COMP_ID" \
  '.[] | select(.child == $child) | .parent' \
  spec/baseline/ui-graph/Containment_Edge.json | head -1)

# Get parent details
if [[ "$PARENT_ID" == screen_* ]]; then
  jq --arg id "$PARENT_ID" '.[] | select(.id == $id)' spec/baseline/ui-graph/Screen.json
else
  jq --arg id "$PARENT_ID" '.[] | select(.id == $id)' spec/baseline/ui-graph/Component.json
fi
```

### 9. Find component children

**User request**: "What are the children of this StackView?"

**Query**:
```bash
COMP_ID="comp_home_stackview_1"

# Find children via containment edges
jq --arg parent "$COMP_ID" \
  '.[] | select(.parent == $parent) | .child' \
  spec/baseline/ui-graph/Containment_Edge.json | \
  while read child_id; do
    jq --arg id "$child_id" '.[] | select(.id == $id)' spec/baseline/ui-graph/Component.json
  done
```

### 10. Find all modal presentations

**User request**: "Show all modal presentations"

**Query**:
```bash
jq '.[] | select(.mechanism == "Modal" or .mechanism == "Sheet" or .mechanism == "FullScreenCover")' \
  spec/baseline/ui-graph/Navigation_Edge.json
```

### 11. Find tab bar structure

**User request**: "Show the tab bar structure"

**Query**:
```bash
# Find TabBarController screen
TAB_SCREEN=$(jq -r '.[] | select(.type == "UITabBarController") | .id' spec/baseline/ui-graph/Screen.json)

# Find its tabs (child screens)
jq --arg parent "$TAB_SCREEN" \
  '.[] | select(.parent == $parent and .relationship_type == "tab") | .child' \
  spec/baseline/ui-graph/Containment_Edge.json | \
  while read tab_id; do
    jq --arg id "$tab_id" '.[] | select(.id == $id) | {name, type}' spec/baseline/ui-graph/Screen.json
  done
```

### 12. Find navigation patterns

**User request**: "Show all navigation patterns used"

**Query**:
```bash
jq '[.[] | .mechanism] | unique' spec/baseline/ui-graph/Navigation_Edge.json
```

**Output example**:
```
["Push", "Modal", "NavigationLink", "Sheet", "Pop", "Dismiss"]
```

### 13. Find UIKit vs SwiftUI split

**User request**: "How many UIKit vs SwiftUI screens?"

**Query**:
```bash
echo "UIKit screens:"
jq '[.[] | select(.ui_framework == "uikit")] | length' spec/baseline/ui-graph/Screen.json

echo "SwiftUI screens:"
jq '[.[] | select(.ui_framework == "swiftui")] | length' spec/baseline/ui-graph/Screen.json
```

### 14. Find storyboard vs code-based screens

**User request**: "Which screens use Storyboards?"

**Query**:
```bash
jq '.[] | select(.layout_source == "storyboard") | {name, layout_ref}' spec/baseline/ui-graph/Screen.json
```

### 15. Find orphan screens (no incoming navigation)

**User request**: "Find screens with no incoming navigation"

**Query**:
```bash
# Get all screen IDs
ALL_SCREENS=$(jq -r '.[].id' spec/baseline/ui-graph/Screen.json)

# Get screens with incoming edges
HAS_INCOMING=$(jq -r '.[].to' spec/baseline/ui-graph/Navigation_Edge.json | sort -u)

# Find difference (orphans)
comm -23 <(echo "$ALL_SCREENS" | sort) <(echo "$HAS_INCOMING" | sort) | \
  while read orphan_id; do
    jq --arg id "$orphan_id" '.[] | select(.id == $id) | {name, type, is_entry_point}' spec/baseline/ui-graph/Screen.json
  done
```

---

## Complex Queries

### Navigation path between two screens

**User request**: "How do I navigate from Home to Profile?"

**Approach**: BFS search through navigation edges

```python
import json

# Load graph
with open('spec/baseline/ui-graph/Screen.json') as f:
    screens = {s['id']: s['name'] for s in json.load(f)}

with open('spec/baseline/ui-graph/Navigation_Edge.json') as f:
    edges = json.load(f)

# Build adjacency list
graph = {}
for edge in edges:
    if edge['from'] not in graph:
        graph[edge['from']] = []
    graph[edge['from']].append({
        'to': edge['to'],
        'mechanism': edge['mechanism'],
        'trigger': edge.get('trigger', '')
    })

# BFS
from collections import deque

def find_path(from_name, to_name):
    # Find IDs
    from_id = next(id for id, name in screens.items() if name == from_name)
    to_id = next(id for id, name in screens.items() if name == to_name)
    
    queue = deque([(from_id, [])])
    visited = set()
    
    while queue:
        current, path = queue.popleft()
        if current == to_id:
            return path
        if current in visited:
            continue
        visited.add(current)
        
        for neighbor in graph.get(current, []):
            queue.append((neighbor['to'], path + [{
                'from': screens[current],
                'to': screens[neighbor['to']],
                'mechanism': neighbor['mechanism'],
                'trigger': neighbor['trigger']
            }]))
    
    return None

path = find_path('HomeViewController', 'ProfileView')
if path:
    for step in path:
        print(f"{step['from']} → {step['to']} ({step['mechanism']}): {step['trigger']}")
else:
    print("No path found")
```

### Find deeply nested components

**User request**: "Find components nested more than 5 levels deep"

**Approach**: Recursive depth calculation

```python
import json

with open('spec/baseline/ui-graph/Containment_Edge.json') as f:
    edges = json.load(f)

# Build parent-child map
children = {}
for edge in edges:
    if edge['parent'] not in children:
        children[edge['parent']] = []
    children[edge['parent']].append(edge['child'])

def get_depth(node_id, current_depth=0):
    if node_id not in children:
        return current_depth
    return max(get_depth(child, current_depth + 1) for child in children[node_id])

# Find screens
with open('spec/baseline/ui-graph/Screen.json') as f:
    screens = json.load(f)

for screen in screens:
    depth = get_depth(screen['id'])
    if depth > 5:
        print(f"{screen['name']}: {depth} levels deep")
```

---

## Output Formatting

Always format query results in a human-readable way:

**For lists**:
```
Found 3 screens:
1. HomeViewController (UIViewController, UIKit)
2. ProfileView (SwiftUI.View, SwiftUI)
3. SettingsViewController (UITableViewController, UIKit)
```

**For navigation**:
```
Navigation from HomeViewController:
→ DetailViewController (Push): 点击列表项
→ SettingsView (Modal): 点击设置按钮
```

**For hierarchy**:
```
HomeViewController
├── NavigationBar
│   ├── TitleLabel
│   └── RightButton
├── ContentScrollView
│   ├── HeaderView
│   └── ListView
└── TabBar
```

---

## Error Handling

### Graph files missing
If any of the four JSON files don't exist:
```
Error: UI graph not found. Run ios-ui-graph-builder first to create the graph.
```

### Screen not found
```
Error: Screen "XYZViewController" not found. Available screens:
- HomeViewController
- ProfileView
- SettingsViewController
```

### Invalid JSON
```
Error: Graph files are corrupted. Re-run ios-ui-graph-builder to regenerate.
```

---

## Quick Triage

Use this skill when the user asks:
- "What screens are in this iOS project?"
- "Show me the navigation from X to Y"
- "What components are in this screen?"
- "Find all UIButton components"
- "Show the tab bar structure"
- "How many UIKit vs SwiftUI screens?"

Do not use for:
- Creating or building the graph (use ios-ui-graph-builder)
- Modifying the graph
- Code generation
