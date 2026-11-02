---
name: i2h-spec
description: iOS→HarmonyOS 迁移的 Spec 生成（Pipeline 第一步）：扫描 iOS 源码产出 UI 清单与功能 Spec
tags: [pipeline, migration]
type: pipeline
domain: migration
---

# i2h-spec

Pipeline 第一步：分析 iOS 项目，生成完整的迁移规格。

## 启动检查 — 待办 findings

读取 `spec/.i2h/open-findings.json`（不存在 = 首轮，直接开工）：

| 情况 | 行动 |
|---|---|
| 有 `owner_stage: spec` 的条目 | 先处理这些，再做本轮正常工作 |
| 有 `owner_stage` 属上游阶段且 `severity: blocking`、未带 `decision_ref` | 🔴 拒绝开工，提示修复上游问题 |
| 有 `LOOP.NOT_CONVERGING` | 需要人工决策，记录到 decision-ledger.md |

## 1. 前置检查

检查 `.migbot/config.json`:
- `ios` 路径存在
- `harmonyos` 路径存在
- `confirmed == true`

失败 → 停止，提示运行 `/i2h-init`

## 2. 智能路由

检查 `spec/baseline/` 目录状态：

| 状态 | 行动 |
|------|------|
| 不存在 | 初始迁移（执行 Section 3-5） |
| 已存在 | 增量演进（暂不支持，提示 baseline 已存在） |

## 3. Phase A: iOS 项目数据准备

### Step A1: 扫描项目结构

运行 iOS 项目扫描器：

```bash
python3 .migbot/bin/scripts/ios_scanner/scan_project.py "$IOS_PATH" \
  --output spec/.i2h/project-info.json
```

扫描内容：
- Xcode 项目文件识别
- Swift 源文件清单
- SwiftUI View 识别
- UIKit ViewController 识别
- Assets.xcassets 资源
- Storyboard/XIB 文件
- 代码行数统计

**验证产出**：
- [ ] `spec/.i2h/project-info.json` 存在
- [ ] 包含 `swift_files` 列表
- [ ] 包含 `swiftui_views` 列表

**Findings 报告**：
- 缺少必需文件 → `IOS.MISSING_REQUIRED_FILE`
- 项目结构异常 → `IOS.INVALID_PROJECT_STRUCTURE`

### Step A2: 提取 SwiftUI View 清单

对每个 SwiftUI View 文件运行解析器：

```bash
for view_file in $SWIFTUI_VIEWS; do
  python3 .migbot/bin/scripts/swiftui_converter/simple_parser.py \
    "$IOS_PATH/$view_file" \
    --output "spec/.i2h/views/$(basename $view_file .swift).json"
done
```

提取内容：
- View 名称
- 属性列表（@State, @Binding 等）
- body 结构
- 依赖的自定义组件

**验证产出**：
- [ ] `spec/.i2h/views/*.json` 文件存在
- [ ] 每个 JSON 包含 `name`, `properties`, `body_source`

**Findings 报告**：
- 解析失败 → `IOS.VIEW_PARSE_ERROR`
- 语法错误 → `IOS.INVALID_SWIFT_SYNTAX`
- 不支持的语法 → `IOS.UNSUPPORTED_SYNTAX` (推断类)

### Step A3: 分析资源文件

扫描 Assets.xcassets：

```bash
python3 .migbot/bin/scripts/ios_scanner/scan_assets.py \
  "$IOS_PATH/Resources/Assets.xcassets" \
  --output spec/.i2h/resources.json
```

提取内容：
- 图片资源（.imageset）
- 颜色资源（.colorset）
- 数据资源（.dataset）
- 本地化字符串（Localizable.strings）

**验证产出**：
- [ ] `spec/.i2h/resources.json` 存在
- [ ] 包含资源清单

### Step A4: 生成 Phase A 报告

生成 `spec/.i2h/phase-a-report.md`:

```markdown
# Phase A: iOS 项目数据准备完成

## 统计
- Swift 文件: 21 个
- SwiftUI View: 10 个
- UIKit ViewController: 1 个
- 资源文件: 3 组

## 代码规模
- 总代码行数: 1,878 行
- SwiftUI 代码: 1,200 行 (64%)
- UIKit 代码: 200 行 (11%)
- 其他: 478 行 (25%)

## 下一步
Phase B: 生成 UI 清单
```

**Linter 运行**：

```bash
python3 .migbot/bin/scripts/linters/lint_phase_a.py "$PROJECT_ROOT"
```

报告 findings 到 `spec/.i2h/open-findings.json` section `spec/phase-a`

## 4. Phase B: UI 清单生成

### Step B1: 生成 ui-manifest.md

基于 Phase A 数据，生成完整清单：

```markdown
# UI 清单

## SwiftUI Views

| # | View 名称 | 文件路径 | 属性数 | 复杂度 | 行数 |
|---|----------|---------|--------|--------|------|
| 1 | HomeView | App/Views/HomeView.swift | 5 | medium | 80 |
| 2 | SettingsView | App/Views/SettingsView.swift | 3 | simple | 45 |
...

### 复杂度分类
- simple (< 50行): 5 个
- medium (50-150行): 3 个
- complex (> 150行): 2 个

## UIKit ViewControllers

| # | ViewController | 文件路径 | 复杂度 | 行数 |
|---|---------------|---------|--------|------|
| 1 | ScanViewController | App/Services/ScanVC.swift | complex | 200 |

## 总计
- SwiftUI Views: 10 个
- UIKit ViewControllers: 1 个
- 总页面: 11 个
```

输出到 `spec/baseline/ui-manifest.md`

### Step B2: 生成分页 spec

对每个 View/ViewController 生成详细 spec：

```markdown
# HomeView

## 基本信息
- ID: page_0001
- 文件: App/Views/HomeView.swift
- 类型: SwiftUI View
- 复杂度: medium
- 行数: 80

## 属性
- @State count: Int = 0
- @State message: String = "Hello"

## UI 结构
\`\`\`swift
VStack(spacing: 20) {
  Text("Count: \\(count)")
  Button("Increment") { ... }
}
\`\`\`

## 转换策略
- 使用模板转换器
- 预计自动转换率: 92%
- 需要人工调整: Button action 闭包

## 依赖
- 无外部依赖

## 风险
- 低风险
```

输出到 `spec/baseline/ui/page_0001_HomeView.md`

### Step B3: 运行 UI 覆盖率审计

```bash
python3 .migbot/bin/scripts/linters/audit_ui_coverage.py "$PROJECT_ROOT"
```

检查：
- [ ] 所有 SwiftUI View 都有 spec
- [ ] 所有 UIKit VC 都有 spec
- [ ] 没有遗漏的 UI 文件

报告 findings 到 section `spec/ui-coverage`

### Step B4: UI 清单门禁

检查 UI 清单质量：

```bash
python3 .migbot/bin/scripts/linters/gate_ui_manifest.py "$PROJECT_ROOT"
```

门禁条件：
- ✅ UI 覆盖率 >= 95%
- ✅ 所有页面都有复杂度评估
- ✅ 没有重复的 View 名称

**失败处理**：
- 精确类错误（重复名称）→ 必须修复
- 推断类问题（复杂度评估缺失）→ 可以记账放行

## 5. Phase C: 功能 Spec 生成

### Step C1: 分析功能模块

基于代码结构识别功能模块：

```
App/
├── Data/        → F001-F003: 数据管理
├── Services/    → F101-F103: 系统服务
├── Navigation/  → F002: 导航功能
└── Views/       → (已在 Phase B 处理)
```

运行功能分析器：

```bash
python3 .migbot/bin/scripts/analyzers/analyze_features.py \
  "$IOS_PATH" \
  --output spec/.i2h/features-raw.json
```

### Step C2: 生成 feature-index.md

```markdown
# 功能索引

## 核心功能

### F001: 数据存储
- 源文件: App/Data/BrewStore.swift
- 技术: SwiftData
- 复杂度: high
- 目标: 鸿蒙关系型数据库

### F002: 导航路由
- 源文件: App/Navigation/AppRouter.swift
- 技术: NavigationStack
- 复杂度: medium
- 目标: Navigation 组件

### F003: 用户偏好
- 源文件: 使用 @AppStorage
- 技术: UserDefaults
- 复杂度: low
- 目标: Preferences

## 系统集成

### F101: 通知
- 源文件: App/Services/NotificationService.swift
- 复杂度: medium

### F102: OCR（可选）
- 源文件: App/Services/OCRService.swift
- 复杂度: high
- 备注: 标记为可选功能

## 依赖关系
- F002 依赖 F001 (导航需要数据)
- F101 独立
- F102 独立（可选）
```

输出到 `spec/baseline/feature-index.md`

### Step C3: 生成分功能 spec

对每个功能生成详细 spec：

```markdown
# F001: 数据存储

## iOS 实现
- 使用 SwiftData
- 模型: BeanRecord, RecipeRecord, BrewRecord
- 支持: CRUD, 查询, 关系

## 迁移策略
- 使用鸿蒙关系型数据库
- 重新设计数据模型（保持结构相似）
- 数据迁移（如需要）

## 实现步骤
1. 定义 ArkTS 数据模型
2. 创建数据库表
3. 实现 CRUD 操作
4. 实现查询接口
5. 测试数据一致性

## 占位策略
- Kind: `data-layer-migration`
- Trigger: Stage 3 优先级 1
- Fallback: Mock 数据（Stage 1-2）

## 验证
- 单元测试
- 数据完整性测试
```

输出到 `spec/baseline/features/feat_001_data_storage.md`

### Step C4: 运行功能覆盖率审计

```bash
python3 .migbot/bin/scripts/linters/audit_feature_coverage.py "$PROJECT_ROOT"
```

检查：
- [ ] 所有功能模块都有 spec
- [ ] 依赖关系明确
- [ ] 复杂度评估完整

报告 findings 到 section `spec/feature-coverage`

## 6. 完成门禁

### Gate: SPEC-COMPLETE

检查所有产出物：

```bash
python3 .migbot/bin/scripts/linters/gate_spec_complete.py "$PROJECT_ROOT"
```

必需产出：
- [ ] `spec/baseline/ui-manifest.md`
- [ ] `spec/baseline/ui/page_*.md` (至少 1 个)
- [ ] `spec/baseline/feature-index.md`
- [ ] `spec/baseline/features/feat_*.md` (至少 1 个)

门禁条件：
- ✅ UI 覆盖率 >= 95%
- ✅ 功能覆盖率 >= 90%
- ✅ 没有 blocking findings（或已记录决策）

**失败处理**：
- 检查 `spec/.i2h/open-findings.json`
- 按 gate-handling 规则处理
- 精确类 → 必须修复
- 推断类 → 可以记账放行
- 阶段不可判定 → 推到 verify

## 7. 完成标记

创建 `spec/baseline/spec-complete.txt`:

```
i2h-spec completed at 2024-11-01T23:59:59Z
UI pages: 11
Features: 5
Findings: 0 blocking, 2 warnings
```

## 8. 输出报告

```markdown
# i2h-spec 完成

## 产出物
✅ spec/baseline/ui-manifest.md
✅ spec/baseline/ui/page_*.md (11 个)
✅ spec/baseline/feature-index.md
✅ spec/baseline/features/feat_*.md (5 个)

## 统计
- SwiftUI Views: 10 个
- UIKit ViewControllers: 1 个
- 功能模块: 5 个
- 代码行数: 1,878 行

## Findings
- Blocking: 0
- Warnings: 2
  - IOS.UNSUPPORTED_SYNTAX: 2 处（已记账放行）

## 下一步
运行 /i2h-plan 生成执行计划
```

## 收尾：上报阶段用量

```bash
.migbot/bin/i2h mark-stage i2h-spec
```

标记阶段水位、刷新用量快照（忽略退出码，不阻断）。
