---
name: i2h-spec
description: iOS→HarmonyOS 迁移的 Spec 生成（Pipeline 第一步）：分析 iOS 源码产出 UI 清单与功能 Spec。LLM 主导语义分析，Python 脚本辅助确定性提取。
tags: [pipeline, migration]
type: pipeline
domain: migration
---

# i2h-spec

Pipeline 第一步：分析 iOS 项目，生成完整的迁移规格。

**核心原则**：
- **LLM 主导**：语义分析、内容生成、复杂度评估
- **Python 辅助**：只做确定性提取（文件列表、类名、属性名）
- **References 指导**：所有关键步骤必须加载对应的 reference 文档

运行时 UI 采集和双端配对遵循 [references/ios-evidence-protocol.md](./references/ios-evidence-protocol.md)。
证据必须绑定当前源码、构建、精确设备、场景、配置和 checkpoint。缺少设备时记录
`not_run` 或 `blocked`，不把静态推断或单端截图当作运行时通过。

---

## 关键约束（Critical）

- **References / Templates 强制加载（HARD-GATE）**：本 skill body 中所有 `[references/X.md]` / `[templates/Y.md]` 引用，在对应步骤执行时**必须** Read 整个文件作为执行规范，不得仅靠 body 摘要或字段名提示执行。跳过加载 = PROCESS_VIOLATION。
- **门禁失败处置**：任何门禁 FAIL、轮次用完、连续未收敛，按 [references/gate-handling.md](./references/gate-handling.md) 处理——精确类必须修过；推断/管线/环境类有限轮修复，修不掉记账放行。禁止改工具、改门禁报告、为迁就检测器改产物。
- **两道审批门**：Phase B 后 **Gate B**、Phase C 后 **Gate C**。默认无人值守：无 blocking findings 自动通过，有 blocking 但已记账也通过。用户明确要求逐个确认时，停在 Gate 等确认。
- **提问一律选项式**：任何需要用户拍板的时刻，必须给 2–4 个具体选项 + `其他`，恰好一个标「← 推荐」并给理由，用户回复编号即可。无人值守时直接取推荐项，不等待。禁止填空式提问。
- **baseline 已存在 → 停止**：`spec/baseline/` 存在时，提示用户此项目已生成 spec，询问是否重新生成（覆盖）或退出。
- **下游强约束**：所有产物必须符合 [references/outputs-and-layout.md](./references/outputs-and-layout.md) 规范，缺失关键字段会导致下游 i2h-plan / i2h-execute 失败。

---

## 启动检查 — 待办 findings

读取 `spec/.i2h/open-findings.json`（不存在 = 首轮，直接开工）：

| 情况 | 行动 |
|---|---|
| 有 `owner_stage: spec` 的条目 | 先处理这些，再做本轮正常工作；处理完重跑对应 linter 确认消失 |
| 有 `owner_stage` 属上游阶段且 `severity: blocking`、未带 `decision_ref` | 🔴 拒绝开工，提示修复上游问题 |
| 有 `LOOP.NOT_CONVERGING` | 需要人工决策，记录到 decision-ledger.md |

**findings 只能由「原 linter 重跑后不再报」来关闭**，不能由任何一方声明「已修复」而关闭。

---

## 1. 前置检查

检查 `.migbot/config.json`:
- `ios` 路径存在
- `harmonyos` 路径存在
- `confirmed == true`

失败 → 停止，提示运行 `/i2h-init`

记录源码根路径 `$IOS_PATH` 和 HarmonyOS 项目根路径 `$HARMONYOS_PATH`。

---

## 2. 智能路由

检查 `spec/baseline/` 目录状态：

| 状态 | 行动 |
|------|------|
| 不存在 | 初始迁移（执行 Section 3-5） |
| 已存在 | 提示用户：baseline 已存在，询问是否重新生成（会覆盖）或退出 |

判断细节：
- `spec/baseline/ui-manifest.md` + `spec/baseline/feature-index.md` 两个文件都存在 → baseline 已完成
- 只有部分文件存在 → 提示 baseline 不完整，建议重新生成
- 完全不存在 → 初始迁移

---

## 3. Phase A: iOS 项目数据准备

Phase A 负责扫描 iOS 项目，提取页面清单和基础元数据。

### Phase A-0: 前置准备

**MUST READ**: [references/phase-a-ios-scan.md](./references/phase-a-ios-scan.md) 全文

**MUST READ**: [references/ios-to-harmonyos-mapping.md](./references/ios-to-harmonyos-mapping.md) 全文

确认映射规则和扫描策略。

### Step A1: 扫描项目结构（确定性 + 语义）

#### 确定性提取（脚本优先）

使用本 skill 随附的确定性证据脚本生成骨架和资源索引：

```bash
# 理想调用（如果 skill 存在）
python3 "${CLAUDE_PLUGIN_ROOT:-.claude}/skills/i2h-spec/scripts/ui_evidence.py" \
  "$IOS_PATH" \
  --output spec/.i2h/resources-inventory.json \
  --skeleton-output spec/.i2h/project-skeleton.json \
  --res-index spec/baseline/res-index \
  --source-index-output spec/.i2h/cache/source-index.json
```

`ui_evidence.py` 同时生成内容寻址的 `spec/.i2h/cache/source-index.json`。索引包含
全量 Swift 文件的 SHA256、声明行、属性包装器、方法、依赖、路由、资源引用和页面
归属。索引把可导航屏幕写入 `pages[]`，把 PrimaryButton、BeanBag、
UIViewRepresentable 等复用视图写入 `components[]`，两者不能混作页面计数。其 cache
key 由 source tree hash、tool version 和 references/templates hash 组成。页面或
feature worker 必须先读取索引切片，禁止再次 Read 整个 Swift 项目。

#### iOS 专属 UI 风格触发（按命中加载）

在页面交付脚手架生成后，可对当前只读 iOS 源运行：

```bash
python3 "${CLAUDE_PLUGIN_ROOT:-.claude}/skills/i2h-spec/scripts/ios_style_triggers.py" \
  <IOS_SOURCE_ROOT> --output spec/ref/ios-style-triggers.json
```

该产物只记录源码锚点、现有 ArkUI Skill 建议、候选原生 API 和回退路径。它不会全局加载玻璃、Popover、Context Menu 等样式 Skill，也不会把 API 26 能力当成当前项目可用能力。Plan 只消费命中的 `suggested_skills`，无命中项保持不触发。

页面分析使用 `pipeline_workers.run_bounded`，默认 4 个 worker，每批 3–5 页。每个
worker 写入 `spec/.i2h/checkpoints/pages/` 下的独立 checkpoint 和临时目录，失败时只
重试该 worker。主线程只做稳定排序、合并和门禁，不能因为单个模型请求异常退回整批
串行执行。增量运行按 page/feature 的 source hash 复用 checkpoint。

如果 `.migbot/config.json` 已确认 `xcode`、`xcrun`、`simctl`，在页面状态计划生成后执行
`scripts/ios_runtime_capture.py`。它负责启动 Simulator、构建并安装 App、抓取 PNG，
并通过 XCTest/XCUITest helper 生成 accessibility JSON 和同一次探针的 foreground receipt。没有 accessibility JSON 或 foreground receipt 时必须
阻断 `runtime_required`，不能把截图或源码推断伪装成运行时树。

```bash
python3 .claude/skills/i2h-spec/scripts/ios_runtime_capture.py \
  --project-root . \
  --project ../cuike-ios/Cuike.xcodeproj \
  --scheme Cuike \
  --output-dir spec/baseline/ui-snapshots/page_0001_HomeView/states/normal \
  --page-id page_0001_HomeView \
  --state-id normal \
  --accessibility-command '<XCTest helper writes $I2H_UI_JSON_OUT>'
```

当页面状态计划包含多个页面或多个状态时，必须使用批量包装器，不能靠 LLM 临时串联多次单页命令。包装器会验证 page/state 唯一性，首个状态构建一次，后续状态复用 DerivedData，并为每个状态写独立日志和统一汇总清单。

```bash
python3 .claude/skills/i2h-spec/scripts/ios_runtime_capture_plan.py \
  --plan spec/.i2h/ios-runtime-capture-plan.json \
  --output-root spec/baseline/ui-snapshots \
  --project-root . \
  --project ../cuike-ios/Cuike.xcodeproj \
  --scheme Cuike \
  --device-id "$CUIKE_SIMULATOR_ID"
```

计划文件的每个状态必须提供 `page_id`、`state_id`，以及 `accessibility_command` 或已有的 `accessibility_json`。`accessibility_command` 负责在真实 Simulator 中执行确定性导航，并写入环境变量 `I2H_UI_JSON_OUT`。随后的 `I2H_FOREGROUND_RECEIPT_OUT` 必须由同一 XCTest 探针在应用前台且页面就绪后写出，采集器只在 JSON 与 receipt 同时存在时截图。一个状态失败时包装器继续采集其余状态，最终退出码为 2，并在 `capture-plan-manifest.json` 中记录 `blocked_reason`。下游只能把 `status=captured` 的状态作为运行时证据，不能把 partial 汇总伪装成全量通过。

批量包装器同时把同一份清单写入目标工程的
`spec/execution/ios-runtime-capture/capture-plan-manifest.json`。即使
`--output-root` 指向临时目录，i2h-execute 的 visual scope 也会自动发现该清单，
把每个已捕获状态的 PNG、accessibility JSON 和 `meta.json` 同步到
`spec/baseline/ui-snapshots/<page_id>/states/<state_id>`。partial 清单在同步时保持阻断。

运行时证据使用 PNG + accessibility JSON。Android 的 `view.xml` 只适用于 legacy
或 Android 输入，不得作为 iOS 的必需格式。

XCTest helper 可以通过环境变量 `I2H_UI_JSON_OUT` 或
`TEST_RUNNER_I2H_UI_JSON_OUT` 写入 JSON。helper 有两种等价输出形式。优先写入
`nodes` 数组；如果逐节点 XCTest 查询导致采集过慢，可以写入
`debug_description` 字符串。`ios_runtime_capture.py` 会解析 XCUITest 的
`debugDescription`，保留 role、label、identifier 和 frame，并忽略易变的对象地址。
因此每个页面状态仍必须通过真实 Simulator 运行采集 PNG 和无障碍证据，不能把静态
源码推断写成 runtime JSON。

当只读 iOS 工程没有现成 helper 时，使用随 skill 提供的
`ios_xctest_accessibility.py`。它只在临时目录复制 Xcode 工程，向已有的 UI test
源文件追加一次性 probe，并用 `-only-testing:CuikeUITests/I2HAccessibilityCaptureTests/testI2HAccessibilityCapture`
运行该 probe。原始 iOS 工程保持不变。推荐把下面的命令作为
`ios-runtime-capture-plan.json` 的 `accessibility_command`，其中
`I2H_SIMULATOR_UDID` 由采集脚本注入：

```bash
python3 "${CLAUDE_PLUGIN_ROOT:-.claude}/skills/i2h-spec/scripts/ios_xctest_accessibility.py" \
  --project "$IOS_PATH/Cuike.xcodeproj" \
  --scheme Cuike \
  --destination "platform=iOS Simulator,id=$I2H_SIMULATOR_UDID" \
  --derived-data "$PROJECT_ROOT/spec/.i2h/xctest-helper-derived-data" \
  --log "$PROJECT_ROOT/spec/.i2h/xctest-helper.log"
```

该 probe 必须根据 `TEST_RUNNER_I2H_PAGE_ID` 执行确定性导航后再写出
`debug_description`。如果工程的测试 target 或入口不同，保留同样的环境变量契约，
并在临时副本中使用对应的 test source 路径。

**脚本应输出**（骨架）：
- Swift 文件路径列表
- SwiftUI View 类名列表（`struct XXX: View`）
- UIKit ViewController 类名列表（`: UIViewController`）
- Info.plist 路径
- Assets.xcassets 路径
- 代码行数统计

#### LLM 补充（语义分析）

**如果脚本不存在或失败**，LLM 执行等价扫描：

1. **扫描项目目录**，识别 iOS 项目结构（.xcodeproj、Swift 文件）
2. **读取关键文件**，提取类名和基础信息
3. **生成等价的骨架 JSON**

**LLM 补充语义字段**：

对每个识别出的 View/ViewController，补充：
- `purpose`: 用途（通过阅读代码推断）
- `complexity`: 复杂度（simple/medium/complex/very_complex）
- `dependencies`: 依赖的其他组件
- `navigation_role`: 导航角色（entry/modal/tab/detail）

#### 产出验证

- [ ] `spec/.i2h/project-skeleton.json` 存在
- [ ] 包含 `swift_files` 列表（至少 1 个）
- [ ] 包含 `swiftui_views` 或 `uikit_viewcontrollers`（至少 1 个）
- [ ] 包含 `info_plist` 路径
- [ ] 所有文件路径已验证存在

**Findings 报告**：
- 缺少必需文件 → `IOS.MISSING_REQUIRED_FILE`（精确类，blocking）
- 项目结构异常 → `IOS.INVALID_PROJECT_STRUCTURE`（精确类，blocking）
- 无法识别任何 View → `IOS.NO_VIEWS_FOUND`（精确类，blocking）

### Step A2: 逐页详细分析（骨架 + 语义）

对每个 SwiftUI View 和 UIKit ViewController 执行详细分析。

#### Step A2a: 确定性骨架生成（脚本优先）

页面的确定性骨架来自上一步 `ui_evidence.py` 的 `pages[]`。复用组件从
`components[]` 作为共享组件输入，不能为组件创建独立页面或重复执行 runtime capture。
对每个页面 View
仍必须完整读取源码，并由 LLM 补充用途、复杂度、依赖和导航语义。不存在
可执行的 `ios-view-analyzer` 脚本时，不得引用悬空路径或把推断字段伪装成脚本事实。

**脚本应提取**（确定性）：
- 属性列表（`@State`, `@Binding`, `@ObservedObject` 等）
- 属性类型和默认值
- body 源码文本
- 依赖的自定义组件（通过 import 和使用识别）

#### Step A2b: LLM 语义分析（在骨架基础上补充）

**必须执行**（无论脚本是否存在）：

1. **读取 View 源码**（完整读取，不能只看摘要）
2. **分析 UI 结构**：
   - 主容器类型（VStack/HStack/ZStack/List）
   - 布局层次（嵌套深度）
   - 关键组件（按钮、列表、输入框）
3. **分析状态管理**：
   - 状态变量用途
   - 数据流方向
   - 外部依赖（Store、Service）
4. **分析交互行为**：
   - 按钮动作
   - 导航目标
   - 表单操作
5. **评估转换策略**：
   - 适用转换器（template/semantic/manual）
   - 预估自动转换率
   - 人工调整项

#### 补充字段到 meta.json

在脚本骨架基础上，补充以下字段：

```json
{
  // 脚本提取的确定性字段
  "view_name": "HomeView",
  "file_path": "Cuike/Views/HomeView.swift",
  "properties": [...],
  "body_source": "...",
  
  // LLM 补充的语义字段
  "purpose": "应用主页，展示咖啡豆列表和快速操作",
  "complexity": "medium",
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
    }
  ],
  "conversion_strategy": {
    "converter": "template",
    "auto_conversion_rate": 0.85,
    "manual_adjustments": ["Sheet presentation"]
  },
  "ios_source_anchors": {
    "primary_file": "Cuike/Views/HomeView.swift",
    "related_files": ["Cuike/Models/Bean.swift"],
    "key_symbols": ["HomeView.body", "BeanStore.fetchBeans()"]
  }
}
```

#### Confidence 评级

| 级别 | 数据来源 | 特征 |
|------|---------|------|
| `high` | 脚本提取 + LLM 阅读源码验证 | 所有字段完整、源码路径已验证 |
| `medium` | LLM 扫描生成 | 基于代码推断，可能有遗漏 |
| `low` | 部分源文件缺失或无法解析 | 需要人工补充 |

### Step A3: Info.plist 和权限分析

1. **读取 Info.plist**（XML 或二进制格式）
2. **提取关键信息**：
   - Bundle ID
   - 版本号
   - 权限声明（Camera、Location、Notifications 等）
   - URL Schemes
   - 后台模式
3. **映射到 HarmonyOS**：
   - 使用 [references/ios-to-harmonyos-mapping.md](./references/ios-to-harmonyos-mapping.md) § 权限映射
   - 生成对应的鸿蒙权限列表

#### 产出

`spec/.i2h/info-plist-analysis.json`：

```json
{
  "bundle_id": "com.example.cuike",
  "version": "1.0.0",
  "permissions": [
    {
      "ios_key": "NSCameraUsageDescription",
      "ios_description": "需要访问相机以扫描咖啡豆信息",
      "harmonyos_permission": "ohos.permission.CAMERA",
      "usage": "F101 相机扫描功能"
    }
  ]
}
```

### Step A4: 输出 Phase A 报告

生成 `spec/.i2h/phase-a-report.md`（简要总结）：

**MUST READ**: [templates/ui-manifest-template.md](./templates/ui-manifest-template.md) § 统计摘要部分

```markdown
# Phase A: iOS 项目数据准备完成

## 统计
- Swift 文件: {数量} 个
- SwiftUI View: {数量} 个
- UIKit ViewController: {数量} 个
- 资源文件: {数量} 组

## 代码规模
- 总代码行数: {数量} 行
- SwiftUI 代码: {数量} 行 ({百分比}%)
- UIKit 代码: {数量} 行 ({百分比}%)

## Confidence 分布
- High: {数量} 个
- Medium: {数量} 个
- Low: {数量} 个

## Findings
- Blocking: {数量}
- Warnings: {数量}

## 下一步
Phase B: 生成 UI 清单
```

### Gate A（自动，无需确认）

**检查项**：
- [ ] `spec/.i2h/project-skeleton.json` 存在
- [ ] 至少识别出 1 个页面
- [ ] 所有源文件路径已验证存在
- [ ] 无 blocking findings（或已记账）

#### Step A1b: 生成静态 UI/资源事实（确定性脚本）

在完成项目骨架扫描后，必须运行随本 skill 安装的静态证据脚本。它是 iOS
版本对 Android `view.xml`/资源索引的对应物，记录源代码锚点、SwiftUI/UIKit
页面、Assets.xcassets 变体、本地化条目和代码到资源的引用；它不会猜测运行时值。

```bash
python3 .claude/skills/i2h-spec/scripts/ui_evidence.py \
  "$IOS_PATH" \
  --output spec/.i2h/resources-inventory.json \
  --res-index spec/baseline/res-index
```

必须验证以下产物存在且 `target_input_sha256` 一致：

- `spec/.i2h/resources-inventory.json`
- `spec/baseline/res-index/{values,drawables,usage,design-tokens,handoff}.json`

资源代码引用中无法在源资源目录解析的名称必须保留在 `usage.json` 的
`disposition=unresolved` 中，交由 Gate B 记账，不得静默删除或生成默认值。

**失败处理**：按 [references/gate-handling.md](./references/gate-handling.md) 处理

---

## 4. Phase B: UI 清单生成

Phase B 基于 Phase A 的数据，生成结构化的 UI Spec 文档。

### Step B1: 生成 ui-manifest.md

**MUST READ**: [templates/ui-manifest-template.md](./templates/ui-manifest-template.md) 全文

基于 Phase A 数据，生成 `spec/baseline/ui-manifest.md`：

**必须包含的内容**：
1. 全局约定（页面 ID 规则、复杂度标准）
2. SwiftUI Views 清单（表格）
3. UIKit ViewControllers 清单（表格）
4. 页面关系图（导航层次）
5. 状态管理总览
6. 系统功能使用
7. 转换批次规划
8. 共享组件
9. 资源清单
10. 统计摘要

**关键约束**：
- 页面 ID 必须按 `page_NNNN_ClassName` 格式
- 复杂度评估必须基于 mapping reference 的标准
- 所有表格必须完整，不用 TODO 占位

### Step B2: 生成分页 UI Spec

**MUST READ**: [templates/page-spec-template.md](./templates/page-spec-template.md) 全文

对每个页面生成详细 spec：

**产出**: `spec/baseline/ui/page_NNNN_ClassName.md`

**必填字段**（不得省略）：
- 基本信息（Page ID、类名、文件路径、类型、复杂度、行数、Confidence）
- ios_source_anchors（complex/very_complex 页面必填）
- 页面结构（非空行 ≥ 5）
- 状态管理
- 交互行为
- 转换策略
- 依赖关系

**关键约束**：
- 所有文件路径必须验证存在
- ios_source_anchors 的 YAML 必须完整
- 不用 TODO 或占位符

### Step B3: UI 覆盖率审计

检查：
- [ ] 所有 Phase A 识别的 View 都有对应的 page spec
- [ ] 没有遗漏的 UI 文件
- [ ] 页面 ID 命名一致（meta.json、文件名、manifest 中的引用）

**Findings 报告**：
- 页面 spec 缺失 → `SPEC.PAGE_SPEC_MISSING`（精确类，blocking）
- 页面 ID 不一致 → `SPEC.PAGE_ID_MISMATCH`（精确类，blocking）
- 覆盖率 < 90% → `SPEC.UI_COVERAGE_LOW`（推断类，warning）

### Gate B（可选确认）

**检查项**：
- [ ] `spec/baseline/ui-manifest.md` 存在
- [ ] UI 覆盖率 >= 90%（推断类）
- [ ] 所有页面都有 page spec
- [ ] 无 blocking findings（或已记账）

**默认行为**：无人值守，自动通过（无 blocking 或已记账）

**用户确认模式**（用户明确要求时）：
停在 Gate B，提供选项：

1. **[推荐] 继续 Phase C** — 无 blocking findings
2. 记账放行继续 — 有 findings 但可接受
3. 停止并修复 — 需要人工介入

记录决策到 `spec/decision-ledger.md`。

---

## 5. Phase C: 功能 Spec 生成

Phase C 分析功能模块，生成功能级别的 Spec。

### Step C1: 分析功能模块

**基于代码结构识别功能模块**：

1. **扫描项目目录结构**，识别功能划分：
   ```
   App/
   ├── Data/        → 数据管理功能
   ├── Services/    → 系统服务功能
   ├── Navigation/  → 导航功能
   └── Views/       → (已在 Phase B 处理)
   ```

2. **分析关键技术栈**：
   - SwiftData/Core Data → 数据存储功能
   - URLSession → 网络请求功能
   - AVFoundation → 相机功能
   - UserDefaults/@AppStorage → 用户偏好功能

3. **识别系统集成**：
   - Info.plist 权限 → 对应的系统功能
   - 第三方 SDK → 集成功能

### Step C2: 生成 feature-index.md

**MUST READ**: [templates/feature-index-template.md](./templates/feature-index-template.md) 全文

生成 `spec/baseline/feature-index.md`：

**必须包含的内容**：
1. 功能命名规则（F001-F099, F100-F199, F200-F299）
2. 核心业务功能清单
3. 系统集成功能清单
4. 辅助功能清单
5. 功能依赖图
6. 复杂度统计
7. 优先级分配
8. 迁移时间预估
9. 技术栈映射总览
10. 风险评估

**功能编号规则**：
- F001-F099: 核心业务功能
- F100-F199: 系统集成功能
- F200-F299: 辅助功能

### Step C3: 生成分功能 Spec

**MUST READ**: [templates/feature-spec-template.md](./templates/feature-spec-template.md) 全文

**关键约束**：
- **只生成真实功能的 spec**，不生成 placeholder 文件
- **验收标准必须穷举**：每个操作、每个 UI 元素、每个错误路径都要单独成 AC
- **AC 原子性**：每条 AC 必须原子且可断言，禁止 "详见 xxx" 类延迟描述
- **AC 数量**：simple ≥8, medium ≥15, complex ≥25, very_complex ≥30

对每个**真实识别的功能**生成详细 spec：

**产出**: `spec/baseline/features/feat_XXX_feature_name.md`

**必填字段**（不得省略）：
- 基本信息（Feature ID、名称、源文件、技术栈、复杂度、优先级）
- ios_source_anchors（high/very_complex 功能必填）
- iOS 实现分析（非空行 ≥ 5）
- HarmonyOS 迁移方案（非空行 ≥ 5）
- 实现步骤（至少 5 步）
- 代码示例（可运行的 ArkTS 示例）
- **对接点（与 UI 页面的接口）** — 必填，说明 UI 如何调用本功能
- **验收标准（Acceptance Criteria）** — 必填，必须穷举
  - simple: ≥ 8 个 AC
  - medium: ≥ 15 个 AC  
  - complex: ≥ 25 个 AC
  - very_complex: ≥ 30 个 AC
  - 每个 AC 格式：`- [ ] FXXX-AC{N} {描述}\n      源: → 标: | 判: | 真:`
- 依赖关系
- 占位策略
- 测试策略
- 风险评估

**穷举要求**（验收标准）：
1. **CRUD 完整性**：每个操作（Create/Read/Update/Delete）单独成 AC
2. **UI 元素穷举**：每个按钮、列表、输入框单独成 AC
3. **错误路径穷举**：每种错误情况单独成 AC
4. **关系管理**：每种关系操作单独成 AC
5. **集成验证**：每个 UI 集成点单独成 AC

**禁止**：
- ❌ 不生成 `feat_XXX_placeholder.md` 文件
- ❌ 不用 "支持各种操作" 这样的笼统描述
- ❌ 不用 "详见 xxx.md" 延迟描述
- ❌ AC 数量不足最低要求

**验证**：
- [ ] 每个 feature spec 文件都有实质内容（不是 placeholder）
- [ ] 验收标准数量 ≥ 最低要求
- [ ] 每个 AC 都有完整的 `源: → 标: | 判: | 真:` 格式
- [ ] 每个 AC 都是原子的、可独立测试的

**示例验收标准**（数据存储功能至少 25 个 AC）：
```markdown
### 初始化（3 个）
- [ ] F001-AC01 应用启动时 BrewStore 自动初始化数据库
- [ ] F001-AC02 数据库文件创建在正确位置
- [ ] F001-AC03 表结构创建成功

### CRUD - 创建（5 个）
- [ ] F001-AC04 addBean() 成功插入新咖啡豆记录
- [ ] F001-AC05 插入咖啡豆后数据库包含该记录
- [ ] F001-AC06 插入时自动设置 createdAt 时间戳
- [ ] F001-AC07 插入时自动生成 UUID
- [ ] F001-AC08 插入重复 ID 时报错

### CRUD - 读取（5 个）
- [ ] F001-AC09 getBeans() 返回所有未归档的咖啡豆
- [ ] F001-AC10 getBeans() 按创建时间升序排序
- [ ] F001-AC11 getBean(id) 返回指定 ID 的咖啡豆
- [ ] F001-AC12 查询不存在的 ID 返回 null
- [ ] F001-AC13 查询已归档的咖啡豆不在默认列表中

### CRUD - 更新（4 个）
- [ ] F001-AC14 updateBean() 成功更新咖啡豆属性
- [ ] F001-AC15 更新后查询得到新值
- [ ] F001-AC16 更新不存在的咖啡豆返回错误
- [ ] F001-AC17 更新时保持 createdAt 不变

### CRUD - 删除（3 个）
- [ ] F001-AC18 deleteBean() 成功删除指定咖啡豆
- [ ] F001-AC19 删除咖啡豆时级联删除关联的配方记录
- [ ] F001-AC20 删除不存在的咖啡豆不报错

### UI 集成（3 个）
- [ ] F001-AC21 HomeView 显示 store.beans 列表
- [ ] F001-AC22 点击咖啡豆卡片跳转到详情页
- [ ] F001-AC23 添加咖啡豆后 UI 自动刷新

### 错误处理（2 个）
- [ ] F001-AC24 数据库初始化失败时抛出错误
- [ ] F001-AC25 并发访问时数据一致性保证
```

### Step C4: 生成 feature-base.md

**MUST READ**: [templates/feature-base-template.md](./templates/feature-base-template.md) 全文

**目的**：统一说明共享基础设施，避免在各 feature spec 中重复描述。

**产出**: `spec/baseline/feature-base.md`

**执行时机**：所有 feature spec 生成完成后

**提取内容**：
1. **数据模型**：从各 feature spec 提取共享的数据模型
   - 遍历所有 feat_*.md，提取数据模型定义
   - 去重，只保留唯一的模型定义
   
2. **数据层**：提取 Store/Repository 的核心接口
   - 提取所有 Store 类的接口定义
   - 汇总为统一的数据层说明
   
3. **网络层**：统一的网络请求架构（如适用）
   - 如果有网络请求，提取 HTTP 封装
   
4. **事件系统**：跨组件通信机制
   - 如果使用 @EnvironmentObject 或 EventBus
   
5. **导航系统**：全局路由管理（如 AppRouter）
   - 从各 page spec 和 feature spec 提取导航逻辑
   - 汇总为统一的导航系统说明
   
6. **公共组件库**：从 ui-manifest.md 提取共享组件
   - 读取 ui-manifest.md § 共享组件
   - 列出所有可复用组件
   
7. **权限声明**：从 info-plist-analysis.json 汇总
   - 读取 `.i2h/info-plist-analysis.json`
   - 列出所有权限及其用途
   
8. **第三方依赖**：列出所有第三方 SDK
   - 从 project-skeleton.json 提取依赖

**生成步骤**：
1. 读取所有 feature spec，识别共享部分
2. 读取 ui-manifest.md，提取公共组件
3. 读取 info-plist-analysis.json，提取权限
4. 按模板生成 feature-base.md
5. 验证内容完整性

### Step C5: 功能覆盖率审计

检查：
- [ ] 所有识别的功能都有 feature spec
- [ ] **没有生成 placeholder 文件**（feat_XXX_placeholder.md）
- [ ] 所有 feature spec 都有验收标准和对接点
- [ ] 验收标准数量符合最低要求（simple ≥8, medium ≥15, complex ≥25, very_complex ≥30）
- [ ] 每个 AC 都有完整格式（`源: → 标: | 判: | 真:`）
- [ ] 依赖关系明确
- [ ] 复杂度评估完整
- [ ] 所有 complex 功能都有详细的 ios_source_anchors
- [ ] feature-base.md 已生成

**Findings 报告**：
- 功能 spec 缺失 → `SPEC.FEATURE_SPEC_MISSING`（精确类，blocking）
- 生成了 placeholder 文件 → `SPEC.PLACEHOLDER_FILE_GENERATED`（精确类，blocking）
- 验收标准缺失 → `SPEC.AC_MISSING`（精确类，blocking）
- 验收标准数量不足 → `SPEC.AC_INSUFFICIENT`（精确类，blocking）
- AC 格式不完整 → `SPEC.AC_FORMAT_INVALID`（精确类，blocking）
- 对接点缺失 → `SPEC.INTERFACE_MISSING`（精确类，blocking）
- 依赖关系不明确 → `SPEC.DEPENDENCY_UNCLEAR`（推断类，warning）
- 功能覆盖率 < 85% → `SPEC.FEATURE_COVERAGE_LOW`（推断类，warning）

**验证脚本示例**：
```bash
# 检查是否有 placeholder 文件
if ls spec/baseline/features/*_placeholder.md 2>/dev/null; then
  echo "ERROR: 发现 placeholder 文件，应删除"
  exit 1
fi

# 检查验收标准数量
for file in spec/baseline/features/feat_*.md; do
  ac_count=$(grep -c "^- \[ \] F[0-9]\+-AC[0-9]\+" "$file")
  complexity=$(grep "复杂度:" "$file" | awk '{print $2}')
  
  case $complexity in
    simple) min_ac=8 ;;
    medium) min_ac=15 ;;
    complex) min_ac=25 ;;
    very_complex) min_ac=30 ;;
  esac
  
  if [ "$ac_count" -lt "$min_ac" ]; then
    echo "ERROR: $file AC 数量不足（$ac_count < $min_ac）"
  fi
done
```

### Gate C（可选确认）

**检查项**：
- [ ] `spec/baseline/feature-index.md` 存在
- [ ] 功能覆盖率 >= 85%（推断类）
- [ ] 所有功能都有 feature spec
- [ ] 无 blocking findings（或已记账）

**默认行为**：无人值守，自动通过

**用户确认模式**（用户明确要求时）：
停在 Gate C，提供选项：

1. **[推荐] 完成 Spec 生成** — 无 blocking findings
2. 记账放行完成 — 有 findings 但可接受
3. 停止并修复 — 需要人工介入

记录决策到 `spec/decision-ledger.md`。

---

## 6. 完成门禁

### Gate: SPEC-COMPLETE

**MUST READ**: [references/outputs-and-layout.md](./references/outputs-and-layout.md) § 产物验证

检查所有必需产出：

**必需文件**：
- [ ] `spec/baseline/ui-manifest.md`
- [ ] `spec/baseline/ui/page_*.md` (至少 1 个)
- [ ] `spec/baseline/feature-index.md`
- [ ] `spec/baseline/feature-base.md`
- [ ] `spec/baseline/features/feat_*.md` (至少 1 个)
- [ ] `spec/baseline/spec-complete.txt`
- [ ] `spec/decision-ledger.md`

**门禁条件**：
- ✅ UI 覆盖率 >= 90%
- ✅ 功能覆盖率 >= 85%
- ✅ 没有 blocking findings（或已记录决策）
- ✅ 所有文件路径已验证存在
- ✅ 命名规范一致

**失败处理**：按 [references/gate-handling.md](./references/gate-handling.md) 处理

---

## 7. 生成辅助文档

### 7.1 生成 placeholder-registry.md

**MUST READ**: [templates/placeholder-registry-template.md](./templates/placeholder-registry-template.md)

从所有 feature spec 中提取占位策略，统一汇总到 `spec/placeholder-registry.md`。

### 7.2 生成 ui-coverage-report.md

**MUST READ**: [templates/ui-coverage-report-template.md](./templates/ui-coverage-report-template.md)

生成 UI 覆盖率报告到 `spec/ui-coverage-report.md`，统计：
- 页面覆盖率
- 组件覆盖率
- 导航覆盖率
- 系统功能覆盖率
- 缺失项分析

---

## 8. 完成标记

创建 `spec/baseline/spec-complete.txt` 作为 **schema-2 JSON marker**。必须
调用 [marker-contract.md](../i2h-plan/references/marker-contract.md) 中的
`marker_contract.write_marker()`，传入 `stage="i2h-spec"`、当前
`target_input_sha256` 和实际生成的 spec 产物（至少
`spec/.i2h/resources-inventory.json`、`spec/baseline/ui-manifest.md`、
`spec/baseline/feature-index.md` 中存在的文件）。调用必须在所有产物写完
之后执行；不要再写 `i2h-spec completed at ...` 纯文本，也不要把 marker
自身放入 `artifact_paths`。

---

## 9. 输出最终报告

生成人类可读的最终报告：

```markdown
# i2h-spec 完成

## ✅ 产出物

- `spec/baseline/ui-manifest.md` — UI 总清单
- `spec/baseline/ui/page_*.md` — {数量} 个页面详细 spec
- `spec/baseline/feature-index.md` — 功能索引
- `spec/baseline/features/feat_*.md` — {数量} 个功能详细 spec

## 📊 统计

- **SwiftUI Views**: {数量} 个
- **UIKit ViewControllers**: {数量} 个
- **功能模块**: {数量} 个
- **代码行数**: {数量} 行

## 🔍 Findings

- **Blocking**: {数量}
- **Warnings**: {数量}
- **Deferred**: {数量}（推到下游阶段）

{如果有 findings，列出关键的几个}

## ⏭️ 下一步

运行 `/i2h-plan` 生成执行计划。

---

**所有产出物已保存到**: `{HarmonyOS 项目根目录}/spec/`
```

---

## 10. 收尾：上报阶段用量

```bash
.migbot/bin/i2h mark-stage i2h-spec
```

标记阶段水位、刷新用量快照（忽略退出码，不阻断）。

---

## 附录：降级路径

### 脚本不存在或失败

如果 Python 脚本不存在或调用失败：

1. **不阻断流程**
2. **LLM 执行等价的确定性提取**（扫描文件、提取类名）
3. **LLM 补充所有语义字段**
4. **记账"工具缺口，已降级"**
5. **Confidence 标记为 medium**

### 源文件缺失

如果部分源文件无法访问：

1. **标记 Confidence 为 low**
2. **在 meta.json 中记录缺失项**
3. **不阻断后续阶段**
4. **在 spec 中添加 TODO 标记**（这是唯一允许 TODO 的情况）

### 格式错误

如果生成的产物格式错误：

1. **重试生成（最多 2 次）**
2. **2 次后仍失败 → 记账放行**
3. **标记 Confidence 为 low**

---

## 质量保证

### 自检清单

生成每个产物后，LLM 自检：

- [ ] 所有必填字段非空
- [ ] 文件路径已验证存在
- [ ] 命名规范一致
- [ ] 代码示例可运行
- [ ] 没有用 TODO 占位（除非源文件确实缺失）

### 产物质量标准

**必需达到**：
- ✅ 结构完整
- ✅ 关键字段非空
- ✅ 命名一致

**优秀标准**：
- ⭐ 语义丰富
- ⭐ 示例详细
- ⭐ 风险评估充分

---

**最后更新**: 2024-11-03  
**版本**: v2.0（重写版，LLM 主导 + Python 辅助）

## 可选源端真值与状态覆盖

当计划选择高风险功能或 selected smoke 时，可用 `scripts/source_oracle.py` 校验源端预期值。Oracle 只验证当前源文件、行号和引用摘要，不能替代目标侧通过，也不要求为每个页面生成完整用例。未选择或未解析的 case 保留为 `unresolved`。

`ui_obligations` 还会记录嵌入页面候选、条件分支、Sheet/Alert/ConfirmationDialog/Popover/ContextMenu、加载/空态/错误状态标记。它们是交付覆盖输入，不能直接当作运行时状态已观察。
