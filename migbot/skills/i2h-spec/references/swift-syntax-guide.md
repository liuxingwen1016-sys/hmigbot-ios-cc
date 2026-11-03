# Swift Syntax 解析指南

本文档提供 Swift 代码精准解析的思路和示例，借鉴自 `references/ios-0.14.1` 的设计。

---

## 📊 概述

### 为什么需要 Swift Syntax？

**问题**: 简单的文本解析 + 正则匹配无法处理：
- 复杂的嵌套结构
- 泛型和协议
- 闭包和高阶函数
- SwiftUI DSL 的层次关系

**解决方案**: 使用 SwiftSyntax 库进行精准的 AST 解析。

### 使用策略

根据 `references-integration-analysis.md` 的建议：
- ✅ **作为可选增强功能** - 通过 `--use-swift-syntax` 标志启用
- ✅ **不作为强制依赖** - 简单项目仍用文本解析
- ✅ **适用于复杂项目** - 有深层嵌套、大量泛型的项目

---

## 🔧 实现思路

### 方式 1: 使用 SwiftSyntax CLI（推荐用于原型）

**优点**: 
- 快速上手
- 不需要编译 Swift 代码

**缺点**:
- 需要安装 Xcode 工具链
- 每个文件都要调用外部进程

**示例脚本** (参考 references/ 的设计):
```python
import subprocess
import json

def parse_swift_file(file_path):
    """使用 swift-syntax CLI 解析 Swift 文件"""
    result = subprocess.run([
        'swift-syntax-cli',  # 需要预先安装
        'parse', 
        '--output-format', 'json',
        file_path
    ], capture_output=True, text=True)
    
    if result.returncode != 0:
        return None
    
    ast = json.loads(result.stdout)
    return ast

def extract_swiftui_views(ast):
    """从 AST 中提取 SwiftUI View 定义"""
    views = []
    
    # 遍历 AST，查找 struct 声明且遵循 View 协议
    for node in traverse_ast(ast):
        if node['type'] == 'StructDecl':
            if 'View' in node.get('inheritance', []):
                views.append({
                    'name': node['name'],
                    'properties': extract_properties(node),
                    'body': extract_body(node)
                })
    
    return views

def extract_properties(struct_node):
    """提取属性（@State, @Binding等）"""
    properties = []
    
    for member in struct_node.get('members', []):
        if member['type'] == 'VariableDecl':
            # 检查属性包装器
            wrappers = member.get('attributes', [])
            prop_type = None
            
            for attr in wrappers:
                if attr['name'] in ['State', 'Binding', 'ObservedObject', 
                                     'StateObject', 'Environment']:
                    prop_type = f"@{attr['name']}"
                    break
            
            properties.append({
                'name': member['name'],
                'type': member['type_annotation'],
                'wrapper': prop_type
            })
    
    return properties

def extract_body(struct_node):
    """提取 body 定义（View 层次结构）"""
    for member in struct_node.get('members', []):
        if member['type'] == 'ComputedProperty' and member['name'] == 'body':
            return analyze_view_hierarchy(member['getter'])
    
    return None

def analyze_view_hierarchy(body_expr):
    """分析 SwiftUI View 的层次结构"""
    # 递归遍历 body 表达式
    # 识别 VStack, HStack, List, NavigationStack 等
    # 返回层次化的结构
    pass
```

---

### 方式 2: 使用 Bash + grep 混合（当前推荐）

**优点**:
- 无外部依赖
- 快速简单
- 适合大多数场景

**缺点**:
- 可能遗漏复杂结构

**示例脚本** (当前 i2h-spec 可以使用):
```bash
#!/bin/bash
# ios-fact-tree 的核心扫描逻辑

SRC="$1"  # iOS 源码根目录
OUTPUT="$2"  # 输出目录

# 1. 查找所有 SwiftUI View
echo "Scanning SwiftUI Views..."
grep -r --include='*.swift' "struct.*View" "$SRC" > /tmp/views.txt

# 2. 查找属性包装器
echo "Scanning property wrappers..."
grep -r --include='*.swift' "@State\|@Binding\|@ObservedObject\|@StateObject\|@Environment" "$SRC" > /tmp/wrappers.txt

# 3. 查找导航相关
echo "Scanning navigation..."
grep -r --include='*.swift' "NavigationStack\|NavigationLink\|.sheet\|.fullScreenCover" "$SRC" > /tmp/navigation.txt

# 4. 查找 UIKit ViewControllers
echo "Scanning UIKit..."
grep -r --include='*.swift' "class.*UIViewController" "$SRC" > /tmp/viewcontrollers.txt

# 5. 解析结果并生成 JSON
python3 <<'EOF'
import json
import sys

# 处理扫描结果
views = []
with open('/tmp/views.txt', 'r') as f:
    for line in f:
        # 解析文件路径、行号、内容
        parts = line.split(':', 2)
        if len(parts) >= 3:
            file_path = parts[0]
            line_num = parts[1]
            content = parts[2].strip()
            
            # 提取 struct 名称
            if 'struct' in content and 'View' in content:
                # 简单的正则提取
                import re
                match = re.search(r'struct\s+(\w+)', content)
                if match:
                    view_name = match.group(1)
                    views.append({
                        'name': view_name,
                        'file': file_path,
                        'line': int(line_num),
                        'type': 'SwiftUI'
                    })

# 输出 JSON
print(json.dumps({
    'views': views,
    'total': len(views)
}, indent=2))
EOF
```

---

### 方式 3: 综合策略（推荐用于生产）

结合两种方式的优点：
1. **默认使用 Bash + grep** - 快速扫描，适合 90% 的场景
2. **复杂场景使用 SwiftSyntax** - 当检测到以下情况时：
   - 嵌套层数 > 5
   - 大量泛型参数
   - 复杂的闭包链

**实现**:
```python
def analyze_swift_file(file_path, use_syntax=False):
    """
    分析 Swift 文件
    
    Args:
        file_path: Swift 文件路径
        use_syntax: 是否使用 SwiftSyntax（默认 False）
    """
    if use_syntax or is_complex_file(file_path):
        # 使用 SwiftSyntax 精准解析
        return parse_with_swift_syntax(file_path)
    else:
        # 使用简单的文本解析
        return parse_with_regex(file_path)

def is_complex_file(file_path):
    """判断文件是否复杂，需要用 SwiftSyntax"""
    with open(file_path, 'r') as f:
        content = f.read()
    
    # 简单的复杂度检测
    if content.count('{') > 50:  # 嵌套很深
        return True
    if content.count('<') > 20:  # 大量泛型
        return True
    if '@ViewBuilder' in content and content.count('if') > 10:  # 复杂的条件视图
        return True
    
    return False
```

---

## 📋 关键识别模式

### 1. SwiftUI View 识别

```swift
// 标准 View
struct HomeView: View {
    var body: some View {
        Text("Hello")
    }
}

// 需要识别:
// - struct 名称: HomeView
// - 遵循 View 协议
// - body 属性存在
```

**识别逻辑**:
```python
def is_swiftui_view(struct_node):
    """判断是否是 SwiftUI View"""
    # 1. 必须是 struct
    if not is_struct(struct_node):
        return False
    
    # 2. 必须遵循 View 协议
    if 'View' not in get_inheritance(struct_node):
        return False
    
    # 3. 必须有 body 属性
    if not has_body_property(struct_node):
        return False
    
    return True
```

---

### 2. 属性包装器识别

```swift
@State private var count: Int = 0
@Binding var isPresented: Bool
@ObservedObject var viewModel: ViewModel
@StateObject private var store = Store()
@Environment(\.dismiss) private var dismiss
```

**识别逻辑**:
```python
PROPERTY_WRAPPERS = [
    'State', 'Binding', 'ObservedObject', 'StateObject',
    'Environment', 'EnvironmentObject', 'AppStorage',
    'SceneStorage', 'FetchRequest', 'Query'
]

def extract_property_wrappers(struct_node):
    """提取所有属性包装器"""
    wrappers = []
    
    for member in struct_node['members']:
        if member['type'] == 'VariableDecl':
            for attr in member.get('attributes', []):
                if attr['name'] in PROPERTY_WRAPPERS:
                    wrappers.append({
                        'wrapper': attr['name'],
                        'name': member['name'],
                        'type': member['type_annotation'],
                        'initial_value': member.get('initializer')
                    })
    
    return wrappers
```

---

### 3. 导航识别

```swift
// NavigationStack
NavigationStack {
    List {
        NavigationLink("Detail", value: item)
    }
    .navigationDestination(for: Item.self) { item in
        DetailView(item: item)
    }
}

// Sheet
.sheet(isPresented: $showSheet) {
    SettingsView()
}

// UIKit
navigationController?.pushViewController(DetailVC(), animated: true)
```

**识别逻辑**:
```python
NAVIGATION_PATTERNS = {
    'swiftui_navigation_stack': r'NavigationStack\s*{',
    'navigation_link': r'NavigationLink\(',
    'navigation_destination': r'\.navigationDestination\(',
    'sheet': r'\.sheet\(',
    'full_screen_cover': r'\.fullScreenCover\(',
    'popover': r'\.popover\(',
    'uikit_push': r'pushViewController\(',
    'uikit_present': r'present\('
}

def extract_navigation(file_content):
    """提取导航关系"""
    import re
    
    navigations = []
    
    for pattern_name, pattern in NAVIGATION_PATTERNS.items():
        matches = re.finditer(pattern, file_content)
        for match in matches:
            navigations.append({
                'type': pattern_name,
                'location': match.start(),
                'context': file_content[match.start():match.end()+100]
            })
    
    return navigations
```

---

## 🎯 集成到 i2h-spec

### Phase A: 项目结构分析

```python
def generate_toolkit_fact_tree(ios_project_path):
    """
    生成 toolkit-fact-tree.json
    
    这是 i2h-spec Phase A 的核心函数
    """
    fact_tree = {
        '$schema_version': 1,
        'schema_version': 1,
        'app': analyze_app_info(ios_project_path),
        'source': {
            'toolkit': 'ios-fact-tree',
            'generator': {
                'skill': 'ios-fact-tree',
                'script_version': '1.0.0'
            },
            'ios_root': ios_project_path,
            'generated_at': datetime.utcnow().isoformat() + 'Z'
        },
        'pages': [],
        'fragments': [],
        'dialogs': [],
        'components': [],
        'navigation': {
            'nodes': [],
            'edges': []
        },
        'features': [],
        'stats': {}
    }
    
    # 1. 扫描所有 Swift 文件
    swift_files = find_swift_files(ios_project_path)
    
    # 2. 分析每个文件
    for file_path in swift_files:
        # 根据复杂度选择解析方式
        use_syntax = should_use_swift_syntax(file_path)
        
        if use_syntax:
            ast = parse_with_swift_syntax(file_path)
            views = extract_views_from_ast(ast)
        else:
            views = extract_views_with_regex(file_path)
        
        # 3. 识别页面
        for view in views:
            if is_page_view(view):
                fact_tree['pages'].append(create_page_node(view))
            elif is_dialog(view):
                fact_tree['dialogs'].append(create_dialog_node(view))
    
    # 4. 构建导航关系
    fact_tree['navigation'] = build_navigation_graph(fact_tree['pages'])
    
    # 5. 聚类功能
    fact_tree['features'] = cluster_features(fact_tree['pages'])
    
    # 6. 统计信息
    fact_tree['stats'] = calculate_stats(fact_tree)
    
    return fact_tree
```

---

## ⚠️ 注意事项

### 不要引入的内容

根据 `references-integration-analysis.md` 和 `HANDOVER.md` 的指导：

❌ **不要引入**:
1. references/ 的完整 `ios-source-analysis` 架构
2. Python 脚本的 `facts` → `facts-view` 多层生成
3. 单写者分区机制
4. Join 协议和门禁系统
5. 债务追踪机制

✅ **应该做**:
1. 保持简洁的一次性分析流程
2. 直接生成 `toolkit-fact-tree.json`
3. 不需要中间的 `ios-facts.json`, `ios-signals.json` 等文件
4. 作为可选功能，不强制依赖

---

## 📚 参考资源

- **SwiftSyntax 官方文档**: https://github.com/apple/swift-syntax
- **references/ 设计**: `~/Codes/ios2harmony/hmigbot-ios/references/ios-0.14.1-iOS技能与说明/`
- **原版 compose-fact-tree**: `~/Codes/ios2harmony/hmigbot-1.8.0/migbot/skills/compose-fact-tree/`

---

**最后更新**: 2024-11-03  
**状态**: 设计文档，待实现
