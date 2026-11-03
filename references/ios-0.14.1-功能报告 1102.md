# iOS 工具 0.14.1 版本完整特性分析

**分析对象**: hmigbot-ios-git (iOS → HarmonyOS 迁移工具)  
**版本**: 0.14.1  
**创建日期**: 2026-11-02

---

## 📊 总体概览

### 基本统计
- **总 Skills**: 102 个
- **iOS 专用 Skills**: 11 个核心 + 22 个包含 iOS 适配
- **Agents**: 31 个
- **支持平台**: macOS (主要), Windows (部分)

---

## 🎯 iOS 专用核心能力 (11 个核心 Skills)

### 1. **ios-source-analysis** ⭐⭐⭐⭐⭐
**路径**: `skills/ios-source-analysis/`

**核心功能**:
- iOS 源码分析总入口
- 协调四类分析器 (工程/UI/功能/API)
- 管理 expertise-plan/review 流程

**关键特性**:
```markdown
## 分析流程
1. 工程分析 (ios-project-inspector)
2. UI 分析 (ios-ui-analyzer) 
3. 功能分析 (ios-feature-analyzer)
4. API 分析 (ios-api-inventory)

## 输出
- ios-facts.json (源码事实)
- ios-obligations.json (实现义务)
- ios-semantics.json (语义映射)
```

---

### 2. **ios-project-inspector** ⭐⭐⭐⭐⭐
**路径**: `skills/ios-project-inspector/`

**核心功能**:
- Xcode 工程结构解析
- pbxproj 文件分析
- Target/Scheme/Configuration 提取

**关键脚本**:
```python
# scripts/parse_pbxproj.py
- 解析 .xcodeproj/project.pbxproj
- 提取编译目标
- 分析依赖关系

# scripts/extract_targets.py
- 枚举 targets
- 读取 build settings
- 提取签名信息
```

**输出**:
```json
{
  "targets": [
    {
      "name": "App",
      "type": "application",
      "bundle_id": "com.example.app",
      "build_settings": {...}
    }
  ],
  "schemes": [...],
  "configurations": ["Debug", "Release"]
}
```

---

### 3. **ios-ui-analyzer** ⭐⭐⭐⭐⭐
**路径**: `skills/ios-ui-analyzer/`

**核心功能**:
- SwiftUI/UIKit 页面枚举
- UI 层次结构分析
- 状态管理识别

**关键能力**:
```markdown
## SwiftUI 支持
- View 结构识别
- @State/@Binding/@ObservedObject 识别
- NavigationStack/TabView 解析
- sheet/fullScreenCover/popover 枚举

## UIKit 支持  
- ViewController 识别
- Storyboard/XIB 解析
- Segue 识别
```

**输出**:
```json
{
  "pages": [
    {
      "page_id": "page_0001",
      "view_name": "HomeView",
      "framework": "swiftui",
      "file": "App/Views/HomeView.swift",
      "states": ["@State private var isLoading", ...],
      "navigation": {
        "type": "NavigationStack",
        "destinations": [...]
      }
    }
  ]
}
```

---

### 4. **swiftui-fact-tree** ⭐⭐⭐⭐
**路径**: `skills/swiftui-fact-tree/`

**核心功能**:
- SwiftUI DSL 语法树提取
- 使用 Swift Syntax 解析
- 组件层次识别

**技术实现**:
```swift
// 使用 swift-syntax 库
import SwiftSyntax
import SwiftParser

// 解析 SwiftUI View
let source = """
struct ContentView: View {
    var body: some View {
        VStack {
            Text("Hello")
            Button("Tap") { }
        }
    }
}
"""

let tree = Parser.parse(source: source)
```

**输出**:
```json
{
  "view": "ContentView",
  "body_structure": {
    "type": "VStack",
    "children": [
      {"type": "Text", "content": "Hello"},
      {"type": "Button", "label": "Tap"}
    ]
  }
}
```

---

### 5. **ios-feature-analyzer** ⭐⭐⭐⭐
**路径**: `skills/ios-feature-analyzer/`

**核心功能**:
- 功能模块识别
- 业务逻辑提取
- 数据流分析

**分析维度**:
```markdown
## 数据层
- Core Data / SwiftData
- UserDefaults
- Keychain

## 网络层
- URLSession
- Alamofire
- 自定义网络层

## 业务层
- ViewModels
- Services
- Repositories
```

---

### 6. **ios-api-inventory** ⭐⭐⭐⭐
**路径**: `skills/ios-api-inventory/`

**核心功能**:
- iOS SDK API 调用清单
- 第三方库识别
- API 映射生成

**输出**:
```json
{
  "ios_apis": [
    {
      "api": "UIKit.UIViewController",
      "usage_count": 15,
      "files": ["HomeViewController.swift", ...],
      "harmonyos_mapping": {
        "target": "NavDestination",
        "confidence": "high"
      }
    }
  ],
  "third_party": [
    {
      "name": "Alamofire",
      "version": "5.0",
      "harmonyos_alternative": "http 模块"
    }
  ]
}
```

---

### 7. **ios-ui-graph-builder** ⭐⭐⭐⭐
**路径**: `skills/ios-ui-graph-builder/`

**核心功能**:
- UI 导航图构建
- 页面跳转关系
- 模态层次识别

**图结构**:
```json
{
  "nodes": [
    {"id": "page_0001", "name": "HomeView", "type": "root"},
    {"id": "page_0002", "name": "DetailView", "type": "child"}
  ],
  "edges": [
    {
      "from": "page_0001",
      "to": "page_0002",
      "type": "navigation_link",
      "trigger": "List item tap"
    }
  ]
}
```

---

### 8. **ios-ui-graph-query** ⭐⭐⭐
**路径**: `skills/ios-ui-graph-query/`

**核心功能**:
- UI 图查询
- 路径查找
- 可达性分析

**查询能力**:
```python
# 查询从 A 到 B 的所有路径
paths = query_paths(from="page_0001", to="page_0005")

# 查询孤立页面
orphan_pages = query_orphan_pages()

# 查询循环引用
cycles = query_cycles()
```

---

### 9. **ios-ui-to-arkui** ⭐⭐⭐⭐⭐
**路径**: `skills/ios-ui-to-arkui/`

**核心功能**:
- SwiftUI → ArkTS 转换规则
- UIKit → ArkTS 转换规则
- 布局映射

**映射规则**:
```typescript
// SwiftUI → ArkTS 映射
VStack → Column
HStack → Row
Text → Text
Button → Button
NavigationStack → Navigation
TabView → Tabs

// UIKit → ArkTS 映射
UIViewController → NavDestination
UITableView → List
UICollectionView → Grid
UINavigationController → Navigation
```

---

### 10. **ios-resources-convert** ⭐⭐⭐⭐
**路径**: `skills/ios-resources-convert/`

**核心功能**:
- Assets.xcassets 转换
- 图片资源处理
- 本地化文件转换

**转换流程**:
```markdown
## 图片资源
Assets.xcassets/
  ├─ AppIcon.appiconset/
  │   ├─ AppIcon.png (@1x, @2x, @3x)
  │   └─ Contents.json
  └─ Images/
      └─ logo.imageset/
          ├─ logo.png
          └─ Contents.json

转换为 ↓

entry/src/main/resources/base/media/
  ├─ app_icon.png
  └─ logo.png
```

---

### 11. **ios-fact-tree** ⭐⭐⭐⭐
**路径**: `skills/ios-fact-tree/`

**核心功能**:
- iOS 源码事实提取
- AST 解析
- 语义分析

**提取内容**:
```json
{
  "facts": [
    {
      "type": "property_declaration",
      "name": "username",
      "property_type": "String",
      "is_optional": false,
      "file": "User.swift",
      "line": 12
    },
    {
      "type": "function_declaration",
      "name": "login",
      "parameters": ["username: String", "password: String"],
      "return_type": "Bool",
      "file": "AuthService.swift",
      "line": 25
    }
  ]
}
```

---

## 🔧 iOS 专用工具与脚本

### 1. **Xcode 工程解析**
```bash
# pbxproj 解析器
skills/ios-project-inspector/scripts/parse_pbxproj.py

# Build Settings 提取
skills/ios-project-inspector/scripts/extract_build_settings.py

# Target 枚举
skills/ios-project-inspector/scripts/enumerate_targets.py
```

### 2. **Swift 语法解析**
```bash
# Swift Syntax 集成
skills/swiftui-fact-tree/scripts/parse_swift.py

# SwiftUI DSL 解析
skills/swiftui-fact-tree/scripts/parse_swiftui_dsl.py
```

### 3. **资源转换**
```bash
# Assets.xcassets 转换
skills/ios-resources-convert/scripts/convert_assets.py

# Localizable.strings 转换
skills/ios-resources-convert/scripts/convert_localizations.py

# Info.plist 解析
skills/ios-resources-convert/scripts/parse_plist.py
```

---

## 🎨 iOS 到 HarmonyOS 映射能力

### 1. **UI 组件映射**
**文档**: `skills/ios-ui-graph-query/references/ios-to-harmonyOS-ui-atomic-component-mapping-reference.md`

```markdown
## SwiftUI 组件映射

| iOS (SwiftUI) | HarmonyOS (ArkTS) | 兼容度 |
|---|---|---|
| Text | Text | 100% |
| Button | Button | 95% |
| Image | Image | 90% |
| VStack | Column | 100% |
| HStack | Row | 100% |
| List | List | 85% |
| NavigationStack | Navigation | 80% |
| TabView | Tabs | 85% |
| TextField | TextInput | 90% |
| Toggle | Toggle | 95% |
```

### 2. **布局映射**
**文档**: `skills/ios-ui-graph-query/references/ios-to-harmonyOS-ui-layout-mapping-reference.md`

```markdown
## 布局系统映射

| iOS | HarmonyOS | 说明 |
|---|---|---|
| frame(width:height:) | width().height() | 尺寸设置 |
| padding() | padding() | 内边距 |
| background() | backgroundColor() | 背景色 |
| cornerRadius() | borderRadius() | 圆角 |
| .foregroundColor() | .fontColor() | 文字颜色 |
```

### 3. **交互映射**
**文档**: `skills/ios-ui-graph-query/references/ios-to-harmonyOS-ui-interaction-mapping-reference.md`

```markdown
## 手势与交互映射

| iOS | HarmonyOS | 兼容度 |
|---|---|---|
| .onTapGesture | .onClick | 100% |
| .onLongPressGesture | .onLongPress | 95% |
| .gesture(DragGesture()) | .gesture(PanGesture()) | 85% |
| @State | @State | 100% |
| @Binding | @Link | 95% |
| @ObservedObject | @ObjectLink | 90% |
```

---

## 📚 iOS 专用 Expertise (固定知识库)

### 1. **SwiftUI 知识库**
**来源**: AvdLee SwiftUI (MIT License)

**内容**:
- 87 个真实示例文件
- SwiftUI 最佳实践
- 常见模式与反模式

**位置**: `skills/ios-source-analysis/references/expertise/swiftui/`

### 2. **Swift Concurrency 知识库**
**来源**: AvdLee Swift Concurrency (MIT License)

**内容**:
- async/await 模式
- Task/TaskGroup
- Actor 隔离

**位置**: `skills/ios-source-analysis/references/expertise/concurrency/`

### 3. **UIKit 知识库**
**来源**: Axiom UIKit (MIT License)

**内容**:
- UIViewController 生命周期
- UITableView/UICollectionView
- 导航与转场

**位置**: `skills/ios-source-analysis/references/expertise/uikit/`

---

## 🔌 MCP (Model Context Protocol) 集成

### **版本**: 0.14.1 新增特性 ⭐⭐⭐⭐⭐

**功能**:
- Xcode 工程只读访问
- Build Settings 提取
- Target 枚举
- 文档搜索 (可选)

**使用方式**:
```markdown
## MCP 通道
- 自动枚举 targets
- 读取 build settings
- 提取 schemes
- DocumentationSearch (可选补充)

## 授权处理
- auth_required → 保存阻塞状态
- 降级为 CLI 分析
- 不自动授权
```

**关键改进** (解决了什么问题):
1. ✅ **只读白名单** - 不修改工程
2. ✅ **分阶段预算** - 避免超时
3. ✅ **降级机制** - MCP 失败不阻塞

---

## 🚀 0.14.0/0.14.1 的关键改进

### **核心改进 1: Spec 分批并行** ⭐⭐⭐⭐⭐

**解决的问题**: 正是您遇到的问题！

**机制**:
```python
# 1. 任务负载分配
def allocate_tasks(pages, capacity=3):
    """按负载分配任务给 agents"""
    batches = []
    current_batch = []
    current_load = 0
    
    for page in pages:
        page_load = estimate_load(page)
        
        if current_load + page_load > capacity:
            batches.append(current_batch)
            current_batch = [page]
            current_load = page_load
        else:
            current_batch.append(page)
            current_load += page_load
    
    return batches

# 2. 空位补充
def refill_slots(running_agents, pending_tasks):
    """有 agent 完成后立即补充新任务"""
    for agent_id in running_agents:
        if is_completed(agent_id):
            if pending_tasks:
                new_task = pending_tasks.pop(0)
                spawn_agent(new_task)

# 3. 超时处理
def monitor_with_timeout(agent_id):
    """监控 agent，超时重派"""
    timeout_count = 0
    
    while timeout_count < 3:
        result = wait_agent(agent_id, timeout=60)
        
        if result['completed']:
            return result
        
        timeout_count += 1
    
    # 超时重派
    return redispatch(agent_id)
```

**关键配置**:
```json
{
  "task_budget": {
    "per_task_minutes": 30,
    "round_minutes": 180,
    "idle_minutes": 20  // 20分钟无进展 = 超时
  },
  "capacity": 3,  // 同时运行3个agent
  "refill_mode": "immediate"  // 立即补充
}
```

---

### **核心改进 2: 有界门禁编排** ⭐⭐⭐⭐

**解决的问题**: 门禁失败导致停机

**机制**:
```python
def process_gate_with_budget(gate_name, max_attempts=3):
    """有界门禁处理"""
    
    for attempt in range(max_attempts):
        result = run_gate(gate_name)
        
        if result['passed']:
            return {'status': 'PASS'}
        
        # 分类处理失败
        failure_type = classify_failure(result['error'])
        
        if failure_type == 'product_defect':
            # 产品缺陷 - 修复
            fix_result = auto_fix(result['error'])
            continue
        
        elif failure_type in ['environment_gap', 'information_gap']:
            # 环境/信息缺口 - 记账放行
            log_debt(gate_name, failure_type, result['error'])
            return {'status': 'DEFERRED', 'can_proceed': True}
    
    # 用尽尝试次数
    return {'status': 'BLOCKED', 'can_proceed': False}
```

---

### **核心改进 3: 冻结输入与断点恢复** ⭐⭐⭐⭐

**解决的问题**: 中断后无法恢复

**机制**:
```json
// spec/baseline/.frozen-input.json
{
  "source_sha256": "abc123...",
  "ios_facts_sha256": "def456...",
  "ui_manifest_sha256": "ghi789...",
  "frozen_at": "2026-11-02T12:00:00Z"
}

// 恢复时验证
if current_sha256 != frozen_sha256:
    raise Exception("输入已变化，不允许恢复")
```

---

## 📊 与 Android 1.8.0 对比

| 特性 | Android 1.8.0 | iOS 0.14.1 | 差距 |
|---|---|---|---|
| **Join 协议** | ✅ 完整 | ⚠️ 部分 | 需加强 |
| **分段落盘** | ✅ 10min初稿 | ❌ 无 | 急需 |
| **门禁分类** | ✅ 5类处理 | ⚠️ 简单 | 需优化 |
| **并行批处理** | ✅ 完整 | ✅ 有 | 相当 |
| **超时处理** | ✅ 3次重派 | ⚠️ 简单 | 需加强 |
| **UI 完备度** | ✅ 完整枚举 | ⚠️ 部分 | 需加强 |
| **MCP 集成** | ❌ 无 | ✅ 有 | iOS优势 |

---

## 🎯 iOS 工具独有优势

### 1. **MCP 集成** (Android 无)
- ✅ Xcode 工程只读访问
- ✅ Build Settings 自动提取
- ✅ 不需要手动配置

### 2. **Expertise 知识库** (Android 无)
- ✅ SwiftUI 87个真实示例
- ✅ UIKit 完整参考
- ✅ 固定摘要，不需要每次读取

### 3. **Swift Syntax 集成** (Android 无)
- ✅ 真实 AST 解析
- ✅ 精确语义理解
- ✅ 不依赖正则表达式

---

## 🚧 iOS 工具当前缺口

### 1. **Join 协议不完整** (P0)
- ❌ 无循环 wait
- ❌ 无死句柄检测
- ❌ 无产物活性探测

### 2. **无分段落盘** (P0)
- ❌ 无10分钟初稿要求
- ❌ 无进展监控
- ❌ 导致61-78分钟无输出

### 3. **门禁分类简单** (P1)
- ⚠️ 只有简单分类
- ⚠️ 无债务追踪
- ⚠️ 记账放行机制不完整

### 4. **UI 枚举不完整** (P1)
- ⚠️ sheet/fullScreenCover 识别不完整
- ⚠️ 容器子页可能遗漏
- ⚠️ 无完备度检查门禁

---

## 📝 下一步优化建议

### **Week 1: 完善 Join 协议**
从 Android 1.8.0 移植:
```python
# 需要添加的文件
skills/a2h-join/scripts/join_gate_ios.py
skills/a2h-join/scripts/wait_for_artifact_ios.py
skills/a2h-spec/scripts/monitor_agent_progress.py
```

### **Week 2: 添加分段落盘**
修改任务书模板:
```markdown
# skills/ios-source-analysis/templates/task-brief-template.md
## 交付时间线
- T+10min: 初稿骨架 (必须)
- T+20min: 完整文档
- 每5min: 进展更新
```

### **Week 3: 增强门禁分类**
创建 iOS 版本:
```python
# skills/a2h-spec/references/gate-policy-ios.md
# skills/a2h-spec/scripts/gate_classifier_ios.py
```

---

## ✅ 总结

iOS 工具 0.14.1 已经实现了：
- ✅ **11个核心 iOS 专用 Skills**
- ✅ **完整的 SwiftUI/UIKit 支持**
- ✅ **MCP 集成** (独有优势)
- ✅ **Expertise 知识库** (87个示例)
- ✅ **分批并行** (已有框架)

但需要从 Android 1.8.0 移植：
- ⚠️ **完整的 Join 协议**
- ⚠️ **分段落盘机制**
- ⚠️ **完善的门禁分类**
- ⚠️ **UI 完备度检查**

---

**文档已保存**: `/tmp/ios-0.14.1-features-analysis.md`
