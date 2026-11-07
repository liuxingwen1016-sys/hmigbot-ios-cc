# i2h-plan 改进执行计划

**基于**: tool-optimization 方法论 + 实际产物验证  
**生成时间**: 2024-11-03  
**目标**: 将 iOS i2h-plan 与 Android a2h-plan 对齐

---

## 执行摘要

### 当前状态
- iOS i2h-plan: 351 行，输出 JSON 格式
- Android a2h-plan: 491 行，输出 Markdown + indexed-v1 架构
- 差距：缺少模板、references、核心机制

### 改进目标
按 tool-optimization 方法论，分 6 个阶段执行：
1. ✅ 理解原版设计（已完成）
2. ✅ 分析当前问题（已完成）
3. ✅ 对比产物差异（已完成，见 i2h-plan-gap-analysis.md）
4. ⏭️ 制定改进计划（本文档）
5. ⏭️ 执行改进
6. ⏭️ 验证和文档

---

## Phase 1: 创建 Templates（Week 1, Day 1-2）

### 目标
创建 6 个模板文件，为 LLM 提供详细的产物格式指导。

### 任务清单

#### 1.1 ui-plan-template.md（4 小时）

**参考**：Android a2h-plan/templates/ui-plan-template.md

**内容**：
```markdown
# UI 转换计划

## 计划概览
- 总页面数: {N}
- 批次数: {M}（页面数 ≤ BATCH_MAX=20）
- 优先级分布: P0={x}, P1={y}
- Confidence 分布: high={a}, medium={b}, low={c}

## 转换批次

### Batch 1
| 序号 | iOS | ArkTS 产出 | 优先级 | owning_slice | 说明 |
|------|-----|-----------|--------|--------------|------|
| 0001 | HomeView | pages/HomeView/Index.ets | P0 | F001 | 主页 |

**Batch 说明**:
- 批内全部页面并行转换
- 页面间导航依赖由 FWD-REF 机制兜底
```

**关键字段**：
- owning_slice：每个页面归属的 Feature ID
- converter：使用的转换器（i2h-swiftui-converter / i2h-uikit-converter）
- confidence 低的页面行内标 ⚠️

**适配 iOS**：
- Android/Kotlin → iOS/Swift
- Activity/Fragment → View/ViewController
- ArkTS 产出路径相同

#### 1.2 feature-plan-template.md（6 小时）

**参考**：Android a2h-plan/templates/feature-plan-template.md

**内容结构**：
```markdown
# Feature 执行计划

```yaml
plan_format: indexed-v1
project: {ProjectName}
generated_at: {ISO 8601}
```

## Context
- **架构**: SwiftUI / UIKit 混合
- **数据源**: {CoreData / SwiftData / 网络}
- **功能数量**: {N}
- **Base 层任务**: 8 个（Base-0~7）

## Base 层（执行序 Phase 0）
**任务数**: 8
**Blocking**: Base-0, Base-1, Base-2, Base-6, Base-7
**Detail**: spec/baseline/plans/base-plan.md

## Group 1（并行组）
### Slice 01: F001 {功能名}
**Detail**: spec/baseline/plans/slices/slice-01-F001.md
**涉及页面**: {页面列表}
**Complexity**: simple/complex
**Depends on**: base

## Final Verification
### FV-1: Final Structural Closure
### FV-2: 终态全量编译
```

**关键约束**：
- 必须包含 plan_format: indexed-v1
- Base 层只保留 stub，详情在 base-plan.md
- 每个 Slice 只保留头部，详情在 slices/*.md
- 必须包含 FV-1 和 FV-2

#### 1.3 slice-plan-template.md（5 小时）

**参考**：Android a2h-plan/templates/slice-plan-template.md

**内容结构**：
```markdown
# Slice {NN}: F{XXX} {功能名}

```yaml
feature_id: F{XXX}
feature_name: {功能名}
priority: P0/P1/P2
parallel_group: {N}
complexity: simple/complex
tier: core/standard/peripheral
depth: full/partial/stub
depends_on: [base, F{YYY}]
```

## Scope
涉及页面: {页面列表}
spec_refs:
  - spec/baseline/features/F{XXX}-*.md
  - spec/baseline/ui/page_{NNNN}.md

## Integration Points
integration_points_ref: spec/baseline/features/F{XXX}-*.md#对接点

## Wires（接线账本）
### VM 入边
- page: {PageName}, viewmodel: {ViewModelName / null}

### 组件嵌入入边
- page: {ParentPage}, slot: {slotName}, embed: {ChildPage}(), resolve_by: slice-{NN}-F{XXX}

## Modifies Files
本 Slice 自建文件，无需回改他切片产物。
（或列出需要回改的文件）

cross_slice_edits:
  - file: {path}, handler: {name}, resolve_by: slice-{NN}-F{XXX}

## Tasks

### Step 3a: UI 补充（页面 + 嵌入子组件）
**suggested_skills**: i2h-swiftui-converter / i2h-uikit-converter
**input**: spec/baseline/ui/page_{NNNN}.md
**scope**: {页面名称}

### Step 3b: ViewModel + 状态管理
**suggested_skills**: arkts-state-manager
**input**: spec/baseline/features/F{XXX}-*.md § 状态管理
**scope**: {@State, @ObservedObject, @EnvironmentObject 转 @Local / @ObservedV2}

### Step 3c: 数据层接入
**suggested_skills**: arkts-data-layer
**input**: spec/baseline/features/F{XXX}-*.md § 数据流
**scope**: {Store.method() 调用}

### Step 3d: 页面接线
**suggested_skills**: arkts-state-manager
**input**: integration_points_ref
**scope**: {导航、数据传递、回调}

### Step 3e: 切片级结构验证
由 i2h-closer (group 模式) 承担。
```

**适配 iOS**：
- SwiftUI: @State / @Binding / @ObservedObject → @Local / @ObservedV2
- UIKit: ViewModel 模式
- CoreData / SwiftData → RelationalStore

#### 1.4 coverage-matrix-template.md（3 小时）

**参考**：Android a2h-plan/templates/coverage-matrix-template.md

**内容结构**：
```markdown
# Coverage Matrix

## Summary
- **P0 功能覆盖率**: {x}/{total} ({percent}%) {✅/❌}
- **P1 功能覆盖率**: {x}/{total} ({percent}%) {✅/❌}
- **UI 页面覆盖率**: {x}/{total} ({percent}%) {✅/❌}
- **Placeholder trigger 白名单率**: {状态}
- **Complex anchor 完整率**: {状态}
- **对接点归属率**: {x}/{total} ({percent}%) {✅/❌}
- **组件嵌入归属率**: {x}/{total} ({percent}%) {✅/❌}

## Feature Coverage
## UI Coverage
## Wiring Ownership Map
## Component Embed Coverage
## Placeholder Registry
## Complex Slice Anchors
## 分层校验
## 功能分组校验
```

#### 1.5 placeholder-registry-template.md（4 小时）

**参考**：Android a2h-plan/templates/placeholder-registry-template.md

**内容结构**：
```markdown
# Placeholder Registry

占位唯一写入位，由 i2h-plan Step 4.1 直写 + i2h-execute §8b trigger 检测。

## 格式

| P-ID | Location | Kind | Trigger Condition | Status | resolve_by |
|------|----------|------|-------------------|--------|------------|
| P-S{N}-{seq} | {file}#{anchor} | thirdparty-sdk | {SDK 类别} SDK 入仓 | registered | - |
| P-B{N}-{seq} | {file}#{anchor} | forward-ref | Slice {M} Step {3c} | registered | slice-{M}-F{XXX} |

## 白名单 Trigger Conditions
1. `{业务类别} SDK 入仓`（三方 SDK）
2. `Slice {N} Step {3c|3d}`（forward-ref）
3. `D-{N} chosen`（决策前置）

## 黑名单关键词
- "待定" / "TODO" / "未实现" / "延后"

## Kind 定义
- `thirdparty-sdk`: 三方 SDK 占位
- `forward-ref`: 前向引用（跨 Slice 依赖）

## resolve_by 规则
- kind=thirdparty-sdk: 无 resolve_by
- kind=forward-ref: 必须有 resolve_by: slice-{N}-F{XXX}
```

**适配 iOS**：
- iOS 常见三方 SDK：微信 SDK、支付宝 SDK、Firebase、Alamofire 等
- 对应 HarmonyOS 的替代方案

#### 1.6 gate-output-template.md（2 小时）

**参考**：Android a2h-plan/templates/gate-output-template.md

**内容**：审批摘要格式模板

---

## Phase 2: 创建 References（Week 1, Day 3-4）

### 目标
创建 3 个 reference 文档，为 SKILL.md 提供详细的执行规范。

### 任务清单

#### 2.1 skill-binding-rules.md（6 小时）

**参考**：Android a2h-plan/references/skill-binding-rules.md

**内容结构**：
```markdown
# Skill 绑定规则

## Core 决策规则

### Feature Slice 步骤的默认 suggested_skills

| Step | suggested_skills |
|------|-----------------|
| Step 3a: UI 补充 | i2h-swiftui-converter / i2h-uikit-converter |
| Step 3b: ViewModel + 状态管理 | arkts-state-manager |
| Step 3c: 数据层接入 | arkts-data-layer |
| Step 3d: 页面接线 | arkts-state-manager |

### Base 层任务的 suggested_skills

| 任务 | suggested_skills |
|------|-----------------|
| Base-1: Models | arkts-data-model |
| Base-2: Repository | arkts-data-layer |
| Base-6: 公共组件库 | i2h-swiftui-converter |
| Base-7: 编译检查点 | hmos-builder |

## 领域特化 Skills（30+ 条目）

### 系统集成类
| 领域 | iOS 技术栈 | suggested_skills+ |
|------|-----------|-------------------|
| 登录 | Sign in with Apple | arkts-login |
| 支付 | StoreKit / Apple Pay | arkts-payment |
| 推送通知 | UNUserNotificationCenter | arkts-notification |
| 相机相册 | AVFoundation / PhotoKit | arkts-camera, arkts-media |
| 地图定位 | CoreLocation / MapKit | arkts-location, arkts-map |
| 网络请求 | URLSession / Alamofire | arkts-network |
| 数据存储 | CoreData / SwiftData | arkts-data-layer |
| 视频播放 | AVPlayer | arkts-media-playback |
| 音频 | AVAudioPlayer | arkts-audio |
| WebView | WKWebView | arkts-webview |
| 分享 | UIActivityViewController | arkts-share |
| 广告 | AdMob | arkts-ad |

### UI 特性类
| 特性 | iOS 实现 | suggested_skills+ |
|------|---------|-------------------|
| 导航 | NavigationView / UINavigationController | arkts-navigation |
| Tab | TabView / UITabBarController | arkts-tabs |
| 列表 | List / UITableView | arkts-list |
| 网格 | LazyVGrid / UICollectionView | arkts-grid |
| 动画 | withAnimation / UIView.animate | arkts-animation |
| 手势 | .gesture / UIGestureRecognizer | arkts-gesture |

## SDK 业务类别 → HMOS 适配 skill 映射

| SDK 类别 | 示例 | suggested_skills+ |
|---------|------|-------------------|
| 社交登录 | 微信登录 SDK | arkts-login |
| 移动支付 | 支付宝 SDK | arkts-payment |
| 广告 | AdMob, 穿山甲 | arkts-ad |
| 推送 | JPush, 个推 | arkts-notification |
| 埋点统计 | Firebase Analytics | arkts-analytics |
| 地图 | 高德地图 | arkts-map |
| IM | 融云 | arkts-im |
| 视频 | 七牛云 | arkts-media |
```

**适配 iOS**：
- 映射表完全基于 iOS 技术栈
- 覆盖 iOS 常见的系统框架和三方 SDK

#### 2.2 plan-dispatch.md（4 小时）

**参考**：Android a2h-plan/references/plan-dispatch.md

**内容**：
- P0/P1/P2 三段编排协议
- 单写者分配规则
- 降级方案
- Agent 派发参数

**适配 iOS**：
- 参数基本通用，无需大改

#### 2.3 grill-2-decision-gates.md（4 小时）

**参考**：Android a2h-plan/references/grill-2-decision-gates.md

**内容**：
- 审批决策规则
- 无人值守 vs 用户确认
- 决策记录格式

---

## Phase 3: 重写 SKILL.md（Week 1, Day 5 - Week 2, Day 2）

### 目标
将当前 351 行的简化版 SKILL.md 重写为 indexed-v1 架构，对齐 Android 原版的 491 行。

### 3.1 整体结构（参考 Android 原版）

```markdown
---
name: i2h-plan
description: iOS→HarmonyOS 执行计划生成（Pipeline 第二步）...
---

# i2h-plan

## 启动检查 — 待办 findings
（findings 处理逻辑）

## 关键约束（Critical）
- indexed 布局唯一
- slice 文件三铁律
- 编排派发（§3.0，HARD-GATE）
- 覆盖率阈值（§7）
- Final Verification 必带 2 task
- References / Templates 强制加载

## 1. 定位
（Pipeline 位置说明）

## 2. 输入
（spec/baseline/ 产物清单）

## 3. 双计划生成
### 3.0 编排协议（P0-P2）
### 3a. UI 转换计划
### 3b. 功能执行计划
  - Step 1: 读取功能依赖
  - Step 2: 拓扑排序
  - Step 3: 生成 Base 层任务
  - Step 4: 生成 Feature Slice 任务
    - Step 4.0: 复杂度判定
    - Step 4.1: 三方 SDK 处理
    - Step 4.2: 接线点提取
    - Step 4.3: 数据链路契约扇出（可选）
  - Step 5: 标注并行组
  - Step 6: FV 任务注入

## 4. suggested_skills 标注规则

## 5. Plan 格式
### 5a. UI 转换计划格式
### 5b. 功能执行计划格式

## 6. 存储

## 7. 覆盖率校验（12 项）

## 8. 审批（可选）

## 9. 完成标记

## 10. 收尾：上报阶段用量
```

### 3.2 关键修改点

#### 修改 1: 产物格式从 JSON 改为 Markdown
**当前**：
```markdown
### Step 3: 生成 ui-plan.json
```json
{
  "version": 1,
  "total_pages": 11,
  ...
}
```
```

**改为**：
```markdown
### Step 3: 生成 ui-plan.md

**MUST READ**: [templates/ui-plan-template.md](./templates/ui-plan-template.md)

生成 Markdown 表格：
| 序号 | iOS | ArkTS 产出 | 优先级 | owning_slice | 说明 |
...
```

#### 修改 2: 采用 indexed-v1 架构
**当前**：
```markdown
### Step 3: 生成 feature-plan.json
```json
{
  "execution_order": [...]
}
```
```

**改为**：
```markdown
### Step 3: 生成 Base 层任务列表（写入 plans/base-plan.md）

**MUST READ**: [templates/feature-plan-template.md](./templates/feature-plan-template.md) 文件二段

Base-0: 资源前置
Base-1: Models
...
Base-7: 编译检查点

### Step 4: 生成 Feature Slice 任务列表（写入 plans/slices/*.md）

**MUST READ**: [templates/slice-plan-template.md](./templates/slice-plan-template.md)

每个 Slice 包含：
- YAML 头部
- Integration Points
- Wires（接线账本）
- Tasks（4 步）
```

#### 修改 3: 新增接线账本机制
**新增**：
```markdown
### Step 4.2: 接线点提取

从 feature spec「## 对接点」段提取接线关系。

**Wires 账本**：
- VM 入边：page + viewmodel
- 组件嵌入入边：page + slot + embed + resolve_by

**Modifies Files**：
- 跨切片编辑：cross_slice_edits

提取粒度：页面 + 其嵌入子组件
```

#### 修改 4: 新增 Placeholder 注册表
**新增**：
```markdown
### Step 4.1: 三方 SDK 处理

四判据（按序短路）：
0. ledger 前置：已有决策 → owned task
1. skill-binding-rules 映射：命中 → suggested_skills+
2. 未命中 → 直接 append placeholder-registry.md
3. 白名单 trigger（见 template）

P-ID 格式：P-S{N}-{seq} / P-B{N}-{seq}
```

#### 修改 5: 新增 FV 任务
**新增**：
```markdown
### Step 6: Final Verification 段注入

两个必填 blocking task：
- FV-1: Final Structural Closure
  - suggested_skills: arkts-structural-closure (pipeline 模式)
- FV-2: 终态全量编译
  - suggested_skills: hmos-builder (agent)

顺序：FV-1 在前（会改码），FV-2 在后（兜底编译）
```

#### 修改 6: 新增覆盖率校验（12 项）
**扩展当前的简单检查**：
```markdown
## 7. 覆盖率校验（Plan 生成后自动执行）

<HARD-GATE>
覆盖率阈值——任一指标不达标即阻断：

| 指标 | 阈值 | 失败动作 |
|------|------|---------|
| P0 功能覆盖率 | = 100% | 阻断，补充缺失 Slice |
| UI 页面覆盖率 | = 100% | 阻断，补漏页 |
| Placeholder trigger 白名单率 | = 100% | 阻断 |
| Complex Slice anchor 完整率 | = 100% | 阻断 |
| 对接点归属率 | = 100% | 阻断 |
| 组件嵌入归属率 | = 100% | 阻断 |
| 分层校验 5 项 | 全通过 | 阻断 |
| 功能分组校验 | 符合规则 | 阻断 |
| ... | ... | ... |
</HARD-GATE>
```

#### 修改 7: iOS 特定适配

**SwiftUI 特性**：
```markdown
## iOS 特定处理

### SwiftUI 状态管理
- @State → @Local
- @Binding → 父子组件传参
- @ObservedObject / @StateObject → @ObservedV2
- @EnvironmentObject → AppStorage / PersistentStorage

### UIKit 特性
- ViewController → Page
- Segue / present → Navigation.pushPath
- Delegate 模式 → Callback / Lambda
```

**iOS 系统框架映射**：
```markdown
### 数据存储
- UserDefaults → Preferences
- CoreData / SwiftData → RelationalStore
- Keychain → 安全存储

### 网络
- URLSession → @ohos.net.http
- Alamofire → http + 封装层
```

---

## Phase 4: 实现脚本（Week 2, Day 3-5）

### 4.1 Linter 脚本（可选）

**参考**：Android a2h-plan/scripts/lint_plan_coverage.py

**功能**：
- 检查 plan 产物完整性
- 校验覆盖率
- 生成 findings

**实现**：
```bash
migbot/skills/i2h-plan/scripts/
├── lint_plan_coverage.py    # 覆盖率校验
├── lint_ui_plan.py           # UI Plan 校验
├── lint_feature_plan.py      # Feature Plan 校验
└── gate_plan_complete.py     # 完成门禁
```

**优先级**：P1（重要但不阻断，LLM 可替代）

---

## Phase 5: 验证（Week 3, Day 1-2）

### 5.1 产物验证

在 Cuike02 项目实际运行 i2h-plan，检查：
- [ ] ui-plan.md 格式正确（Markdown 表格）
- [ ] feature-plan.md 包含 plan_format: indexed-v1
- [ ] base-plan.md 包含 Base-0~7 任务
- [ ] plans/slices/*.md 每个功能一个文件
- [ ] coverage-matrix.md 包含 12 项校验
- [ ] spec/placeholder-registry.md 存在（如有三方 SDK）

### 5.2 字段验证

- [ ] ui-plan 包含 owning_slice 列
- [ ] slice 文件包含 integration_points_ref
- [ ] slice 文件包含 wires 接线账本
- [ ] slice 文件包含 cross_slice_edits
- [ ] Base 任务包含 suggested_skills
- [ ] Slice 任务包含 suggested_skills+（差异化）

### 5.3 覆盖率验证

- [ ] P0 功能覆盖率 = 100%
- [ ] UI 页面覆盖率 = 100%
- [ ] 对接点归属率 = 100%
- [ ] 组件嵌入归属率 = 100%

### 5.4 下游验证

- [ ] i2h-execute 可消费 base-plan.md
- [ ] i2h-execute 可消费 slices/*.md
- [ ] i2h-execute 可识别 suggested_skills
- [ ] i2h-execute 可处理 placeholder-registry

---

## Phase 6: 文档（Week 3, Day 3）

### 6.1 改进总结

创建 `i2h-plan-improvement-summary.md`：
- 完成的改进清单
- 新增的文件
- 更新的文件
- 预期效果
- 验证清单

### 6.2 对比报告

更新 `i2h-plan-gap-analysis.md`：
- 标记已完成的改进
- 记录实际效果
- 未来优化方向

### 6.3 README

创建 `migbot/skills/i2h-plan/README.md`：
- Skill 简介
- 产物说明
- 使用示例
- 常见问题

---

## 工作量估算

| Phase | 任务 | 工作量 | 优先级 |
|-------|------|-------|--------|
| Phase 1 | 创建 6 个 Templates | 24 小时 | P0 |
| Phase 2 | 创建 3 个 References | 14 小时 | P0 |
| Phase 3 | 重写 SKILL.md | 20 小时 | P0 |
| Phase 4 | 实现脚本（可选） | 12 小时 | P1 |
| Phase 5 | 验证 | 8 小时 | P0 |
| Phase 6 | 文档 | 4 小时 | P1 |
| **总计** | | **82 小时** | |

**P0（必做）**: 58 小时  
**P1（重要）**: 24 小时

---

## 执行顺序

### Week 1
- Day 1-2: Phase 1（Templates）
- Day 3-4: Phase 2（References）
- Day 5: Phase 3 开始（SKILL.md 结构）

### Week 2
- Day 1-2: Phase 3 继续（SKILL.md 内容）
- Day 3-5: Phase 4（脚本，可选）+ Phase 5 开始

### Week 3
- Day 1-2: Phase 5（验证）
- Day 3: Phase 6（文档）

---

## 下一步行动

立即开始 Phase 1.1：创建 ui-plan-template.md

```bash
# 创建目录
mkdir -p migbot/skills/i2h-plan/templates
mkdir -p migbot/skills/i2h-plan/references

# 开始创建第一个模板
# Read Android 原版模板 → 适配 iOS → Write
```

---

**计划版本**: v1.0  
**制定时间**: 2024-11-03  
**预计完成**: 2024-11-24（3 周）
