<!-- when: Phase A 扫描 iOS 项目结构、提取 SwiftUI/UIKit 组件清单时加载 -->
<!-- topics: iOS 项目结构、SwiftUI View 识别、UIKit ViewController 识别、Info.plist 解析、资源扫描 -->

# Phase A: iOS 项目扫描策略

Phase A 负责扫描 iOS 项目，提取页面清单和基础元数据。**关键原则**：Python 脚本只做确定性提取（文件列表、类名、属性名），LLM 负责语义理解（用途、复杂度、依赖关系）。

## 扫描策略概览

```
iOS 项目根目录
  ├── {ProjectName}.xcodeproj/     # Xcode 项目文件
  ├── {ProjectName}/               # 主代码目录
  │   ├── Views/                   # SwiftUI Views
  │   ├── ViewControllers/         # UIKit ViewControllers
  │   ├── Models/                  # 数据模型
  │   ├── Services/                # 服务层
  │   └── Resources/               # 资源文件
  ├── Info.plist                   # 应用配置
  └── Assets.xcassets/             # 资源目录
```

## Step A1: 项目结构确定性扫描

### Python 脚本职责（确定性提取）

使用 i2h-spec 随附的确定性证据脚本生成骨架：

```bash
# 理想调用方式（如果 skill 存在）
python3 "${CLAUDE_PLUGIN_ROOT:-.claude}/skills/i2h-spec/scripts/ui_evidence.py" \
  "$IOS_PATH" \
  --output spec/.i2h/resources-inventory.json \
  --skeleton-output spec/.i2h/project-skeleton.json \
  --res-index spec/baseline/res-index
```

完成骨架扫描后，必须运行 i2h-spec 自带的静态 UI/资源证据脚本。iOS 没有
Android UIAutomator 的统一 `view.xml`，因此该脚本负责生成可追溯的源代码和
资源事实，供 Phase B 和 i2h-execute 消费：

```bash
python3 .claude/skills/i2h-spec/scripts/ui_evidence.py \
  "$IOS_PATH" \
  --output spec/.i2h/resources-inventory.json \
  --res-index spec/baseline/res-index
```

脚本会同时生成 `values.json`、`drawables.json`、`usage.json`、
`design-tokens.json` 和 `handoff.json`。所有文件带有相同的
`target_input_sha256`；代码引用无法解析时必须保留为 `unresolved`，不能填入
推测值。若需要真机/模拟器补充事实，使用 `runtime_view.py` 读取 JSON sidecar，
不得把缺少运行时捕获当作静态事实。

只读 iOS 工程没有现成 XCTest helper 时，使用同目录的
`../scripts/ios_xctest_accessibility.py`。该脚本在临时副本中追加一次性
XCUITest probe，保留 `I2H_UI_JSON_OUT` 和 `TEST_RUNNER_I2H_*` 环境变量契约，
再由 `ios_runtime_capture.py` 配对截图。原始 iOS 工程不能被写入。

**脚本应提取**（确定性）：
- Swift 文件路径列表
- SwiftUI View 类名列表（通过 `struct XXX: View` 识别）
- UIKit ViewController 类名列表（通过 `: UIViewController` 识别）
- Info.plist 路径
- Assets.xcassets 路径
- Storyboard/XIB 文件路径

**脚本输出格式**（骨架）：
```json
{
  "project_name": "Cuike",
  "swift_files": [
    "Cuike/Views/HomeView.swift",
    "Cuike/Views/SettingsView.swift"
  ],
  "swiftui_views": [
    {
      "class_name": "HomeView",
      "file_path": "Cuike/Views/HomeView.swift",
      "line_count": 80,
      "has_state": true,
      "state_count": 3
    }
  ],
  "uikit_viewcontrollers": [
    {
      "class_name": "ScanViewController",
      "file_path": "Cuike/Services/ScanViewController.swift",
      "line_count": 200
    }
  ],
  "info_plist": "Cuike/Info.plist",
  "assets": "Cuike/Assets.xcassets"
}
```

### LLM 职责（语义补充）

**如果脚本不存在或调用失败**，LLM 需要：

1. **扫描项目目录**，识别 iOS 项目结构
2. **读取关键文件**，提取类名和基础信息
3. **生成等价的骨架 JSON**

**LLM 补充的语义字段**：
- `purpose`: View/ViewController 的用途（通过阅读代码推断）
- `complexity`: 复杂度评估（simple/medium/complex）
- `dependencies`: 依赖的其他 View 或服务
- `navigation_role`: 导航角色（entry/modal/tab/detail）

示例补充后的结构：
```json
{
  "class_name": "HomeView",
  "file_path": "Cuike/Views/HomeView.swift",
  "line_count": 80,
  "has_state": true,
  "state_count": 3,
  // 以下由 LLM 补充
  "purpose": "应用主页，展示咖啡豆列表和快速操作",
  "complexity": "medium",
  "dependencies": ["BeanStore", "NavigationRouter"],
  "navigation_role": "entry"
}
```

## Step A2: SwiftUI View 详细分析

### Python 脚本职责（确定性提取）

对每个 SwiftUI View，提取确定性信息：

**提取内容**：
- 属性列表（`@State`, `@Binding`, `@ObservedObject`, etc.）
- 属性类型和初始值
- body 的源码文本
- 依赖的自定义组件（通过 `import` 和使用识别）

**输出格式**（骨架）：
```json
{
  "view_name": "HomeView",
  "file_path": "Cuike/Views/HomeView.swift",
  "properties": [
    {
      "name": "beanStore",
      "wrapper": "@ObservedObject",
      "type": "BeanStore",
      "has_default": false
    },
    {
      "name": "count",
      "wrapper": "@State",
      "type": "Int",
      "default_value": "0"
    }
  ],
  "body_source": "var body: some View { ... }",
  "custom_components": ["BeanCard", "AddButton"]
}
```

### LLM 职责（语义分析）

阅读 View 源码，补充：

1. **UI 结构分析**：
   - 主容器类型（VStack/HStack/ZStack/List）
   - 布局层次（嵌套深度）
   - 关键组件（按钮、列表、输入框）

2. **状态管理分析**：
   - 状态变量的用途
   - 数据流方向（父→子、子→父、双向）
   - 外部依赖（Store、Service）

3. **交互行为分析**：
   - 按钮动作（增删改查、导航、弹窗）
   - 列表操作（滑动删除、拖拽排序）
   - 表单验证

4. **转换策略**：
   - 适用的转换器（template/semantic/manual）
   - 预估自动转换率
   - 需要人工处理的部分

示例补充后的完整 meta.json：
```json
{
  "view_name": "HomeView",
  "file_path": "Cuike/Views/HomeView.swift",
  "properties": [...],
  "body_source": "...",
  "custom_components": [...],
  // 以下由 LLM 补充
  "ui_structure": {
    "container": "VStack",
    "depth": 3,
    "key_components": ["List", "NavigationLink", "Button"]
  },
  "state_management": {
    "local_state": ["count"],
    "observed_objects": ["beanStore"],
    "data_flow": "parent_to_child"
  },
  "interactions": [
    {
      "type": "navigation",
      "trigger": "NavigationLink tap",
      "target": "BeanDetailView"
    },
    {
      "type": "action",
      "trigger": "Add button tap",
      "effect": "Open add bean sheet"
    }
  ],
  "conversion_strategy": {
    "converter": "template",
    "auto_conversion_rate": 0.85,
    "manual_adjustments": ["Sheet presentation", "Navigation binding"]
  }
}
```

## Step A3: UIKit ViewController 分析

UIKit 代码通常更复杂，需要更多 LLM 分析：

### 确定性提取（脚本 or LLM）

- ViewController 类名
- 继承关系
- IBOutlet 列表
- IBAction 列表
- Storyboard/XIB 关联

### 语义分析（LLM 必做）

1. **阅读 ViewController 源码**
2. **识别生命周期方法**（viewDidLoad、viewWillAppear 等）
3. **分析 UI 构建方式**（Storyboard、代码创建、混合）
4. **提取业务逻辑**（数据加载、用户交互、状态管理）
5. **评估迁移复杂度**（high，因为需要完全重写为 ArkTS）

## Step A4: Info.plist 和权限分析

### 确定性提取

读取 Info.plist，提取：
- Bundle ID
- 版本号
- 权限声明（Camera、Location、Notifications 等）
- URL Schemes
- 后台模式

### 语义分析

- **权限用途**：阅读代码，理解为什么需要这些权限
- **HarmonyOS 映射**：判断对应的鸿蒙权限
- **缺失风险**：识别可能遗漏的权限

## 关键约束

1. **强制加载 References**：执行 Phase A 时，必须读取本 reference 全文，不得仅凭 SKILL.md 摘要执行
2. **骨架 + 语义分离**：确定性提取（文件列表、类名）与语义理解（用途、复杂度）严格分离
3. **源码路径验证**：所有 file_path 必须验证存在后再写入 meta.json
4. **降级路径**：脚本不存在或失败时，LLM 必须完成等价的扫描工作，不能跳过或简化

## confidence 评级

| 级别 | 数据来源 | 特征 |
|------|---------|------|
| `high` | 脚本提取 + LLM 阅读源码验证 | 所有字段完整、源码路径已验证 |
| `medium` | LLM 扫描生成 | 基于代码推断，可能有遗漏 |
| `low` | 部分源文件缺失或无法解析 | 需要人工补充 |

## 产出物检查清单

Phase A 完成后必须产出：

- [ ] `spec/.i2h/project-skeleton.json` — 项目骨架
- [ ] `spec/baseline/ui-snapshots/page_NNNN_XXXView/meta.json` — 每个页面的元数据
- [ ] `spec/.i2h/info-plist-analysis.json` — Info.plist 分析
- [ ] `spec/.i2h/resources-inventory.json` — 资源清单
- [ ] `spec/.i2h/phase-a-report.md` — Phase A 总结报告

所有路径基于 HarmonyOS 项目根目录。
