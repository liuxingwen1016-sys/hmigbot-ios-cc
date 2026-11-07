# i2h-plan 使用指南

**目标读者**: iOS 开发者、迁移工程师  
**前置条件**: 已完成 i2h-spec  
**预计时间**: 2-4 小时（取决于项目规模）

---

## 快速开始

### 1. 前置检查

确保已完成 i2h-spec 阶段：

```bash
# 检查必需文件
ls spec/baseline/feature-index.md
ls spec/baseline/ui-manifest.md
ls spec/baseline/features/
ls spec/baseline/ui/
```

✅ 如果这些文件都存在，可以继续  
❌ 如果缺少文件，先运行 `i2h-spec`

### 2. 运行 i2h-plan

```bash
# 在项目根目录运行
cd ~/Projects/Cuike02

# 调用 i2h-plan
# 方式 1: 通过 LLM
/i2h-plan

# 方式 2: 直接调用（如果已配置）
.migbot/bin/i2h plan
```

### 3. 验证产物

检查生成的产物：

```bash
# 查看生成的文件
ls -lh spec/baseline/plans/

# 应该包含：
# - ui-plan.md
# - feature-plan.md
# - base-plan.md
# - slices/
# - coverage-matrix.md
# - complete.txt
```

### 4. 运行校验脚本

```bash
cd migbot/skills/i2h-plan/scripts

# 1. 覆盖率校验（核心）
python3 lint_plan_coverage.py ~/Projects/Cuike02

# 2. UI Plan 校验
python3 lint_ui_plan.py ~/Projects/Cuike02

# 3. Feature Plan 校验
python3 lint_feature_plan.py ~/Projects/Cuike02

# 4. 完成门禁
python3 gate_plan_complete.py ~/Projects/Cuike02
```

---

## 详细步骤

### Phase 0: 准备工作

#### 0.1 检查 spec 质量

```bash
# 检查 spec 是否已审批
grep "status: approved" spec/decision-ledger.md

# 检查是否有 blocking findings
cat spec/.i2h/open-findings.json | jq '.[] | select(.severity == "blocking")'
```

#### 0.2 检查 iOS 源码

确保 iOS 源码可访问：

```bash
# SwiftUI 项目
ls iOS/Sources/**/*.swift

# UIKit 项目
ls iOS/Sources/**/*.{swift,h,m}

# 混合项目（两者都有）
```

### Phase 1: 生成双计划

#### 1.1 运行 i2h-plan

```bash
# 启动 i2h-plan
/i2h-plan
```

**LLM 会执行以下步骤**：

1. **P0: Kernel 裁决**
   - 读取 feature-index.md 和 ui-manifest.md
   - 拓扑排序功能依赖
   - 归属消歧（owning_slice 裁决）
   - Slice 定号

2. **P1: 三写并行**（可能使用 Agents）
   - Agent A: 生成 ui-plan.md
   - Agent B: 生成 base-plan.md
   - Agent C: 生成 slices/*.md + placeholder-registry.md

3. **P2: 收拢**
   - 分配 parallel_group
   - 生成 feature-plan.md 索引
   - 运行覆盖率校验（12 项）
   - 执行 grill #2 技术决策
   - 输出审批摘要

#### 1.2 理解产物

**ui-plan.md**：
```markdown
# UI Conversion Plan

## Context
- Source: spec/baseline/ui-manifest.md
- Style: none
- Total pages: 7
- Batches: 2

## Batch 1: P0 Core Pages

| 序号 | 页面 | iOS 来源 | owning_slice |
|------|------|---------|--------------|
| 0001 | MainContainer | MainContainer.swift | F001 |
| 0002 | HomeView | HomeView.swift | F001 |
| 0003 | BeanListView | BeanListView.swift | F001 |
```

**feature-plan.md**（索引）：
```markdown
# Feature Execution Plan

plan_format: indexed-v1

## Base 层

detail: plans/base-plan.md

## Group 1

### Slice 1: 咖啡豆管理 (F001)
parallel_group: 1 | complexity: simple
depends_on: [base]
detail: plans/slices/slice-01-F001.md
```

**base-plan.md**（只读）：
```markdown
# Base 层任务

- Base-0: 资源前置扫描与迁移
  suggested_skills: [ios2hmos_resources_convert]
  parallel_group: 0
  blocking: true

- Base-1: Models
  suggested_skills: [arkts-data-model]
  parallel_group: 1
```

**slices/slice-01-F001.md**（只读账本）：
```markdown
## Slice 1: 咖啡豆管理 (F001)
parallel_group: 1 | complexity: simple
depends_on: [base]

ios_source_anchors_ref: {count: 0, source: spec/baseline/features/F001-*.md}

integration_points_ref: spec/baseline/features/F001-*.md#对接点

wires:
  - page: entry/src/main/ets/pages/HomeView.ets
    viewmodel: entry/src/main/ets/viewmodels/HomeViewModel.ets

- Step 3a: UI 补充 — scope: 0001, 0002, 0003, 0004
- Step 3b: ViewModel — scope: BeanViewModel
- Step 3c: 数据层 — scope: BeanStore
- Step 3d/3e: 接线 + 验证
```

### Phase 2: 校验和修复

#### 2.1 运行覆盖率校验

```bash
python3 scripts/lint_plan_coverage.py ~/Projects/Cuike02
```

**常见问题和修复**：

**问题 1: P0 功能覆盖率不足 100%**
```
❌ P0 功能覆盖率: 3/4 (75%)
   缺失 P0 功能: F004
```

**修复**：
```bash
# 检查 feature-index.md 中的 F004
grep "F004" spec/baseline/feature-index.md

# 在 feature-plan.md 中添加对应的 Slice
# 或调整 feature-index.md 中的优先级
```

**问题 2: Placeholder trigger 不合规**
```
❌ Placeholder trigger 白名单率: 2/3 (66%)
   - P-S3-001: 包含黑名单关键词 "待定"
```

**修复**：
```bash
# 编辑 placeholder-registry.md
vim spec/placeholder-registry.md

# 修改 trigger_condition
# 错误: "待定后续处理"
# 正确: "埋点 SDK 入仓"
```

**问题 3: UI 页面覆盖率不足 100%**
```
❌ UI 页面覆盖率: 6/7 (85%)
   缺失页面: 0007
```

**修复**：
```bash
# 检查 ui-manifest.md 中的 page_0007
grep "page_0007" spec/baseline/ui-manifest.md

# 在 ui-plan.md 中添加该页面
# 或在 ui-manifest.md 中标记为 skipped
```

#### 2.2 运行 UI Plan 校验

```bash
python3 scripts/lint_ui_plan.py ~/Projects/Cuike02
```

**常见问题和修复**：

**问题 1: size-1 批次**
```
❌ Batch 3 只有 1 个页面（size-1 批次）
   建议: 应并入前一批次末尾
```

**修复**：
```bash
# 编辑 ui-plan.md
vim spec/baseline/plans/ui-plan.md

# 将 Batch 3 的页面移到 Batch 2 末尾
# 删除 Batch 3 标题
```

**问题 2: owning_slice 格式错误**
```
❌ owning_slice 格式错误: Feature F001 (序号 0005) (行 28)
   建议: 应为裸 F-ID 格式（如 F001），而非 'Feature F001'
```

**修复**：
```bash
# 编辑 ui-plan.md
vim spec/baseline/plans/ui-plan.md

# 修改第 28 行
# 错误: | 0005 | SettingsView | SettingsView.swift | Feature F001 |
# 正确: | 0005 | SettingsView | SettingsView.swift | F001 |
```

#### 2.3 运行 Feature Plan 校验

```bash
python3 scripts/lint_feature_plan.py ~/Projects/Cuike02
```

**常见问题和修复**：

**问题 1: slice 文件包含 checkbox**
```
❌ [readonly] slice 文件不应包含 checkbox [slice-02-F002.md:45]
   建议: slice 文件应为只读态，移除 - [ ]
```

**修复**：
```bash
# 编辑 slice 文件
vim spec/baseline/plans/slices/slice-02-F002.md

# 移除第 45 行的 checkbox
# 错误: - [ ] Step 3a: UI 补充
# 正确: - Step 3a: UI 补充
```

**问题 2: Base 层任务展开在索引中**
```
❌ [format] Base 层不应展开任务行 [feature-plan.md:23]
   建议: Base 层任务应在 base-plan.md 中，索引只保留 stub
```

**修复**：
```bash
# 编辑 feature-plan.md
vim spec/baseline/plans/feature-plan.md

# 移除展开的任务行
# 只保留：
## Base 层
detail: plans/base-plan.md
```

#### 2.4 运行完成门禁

```bash
python3 scripts/gate_plan_complete.py ~/Projects/Cuike02
```

**成功输出**：
```
🎉 门禁通过: 所有检查通过，可以进入 i2h-execute！

✅ 完成标记已创建: spec/baseline/plans/complete.txt
```

### Phase 3: 审批（可选）

如果需要人工审批：

#### 3.1 审查双计划

```bash
# 1. 查看 UI 转换计划
cat spec/baseline/plans/ui-plan.md

# 2. 查看功能执行计划
cat spec/baseline/plans/feature-plan.md

# 3. 查看 Base 层任务
cat spec/baseline/plans/base-plan.md

# 4. 查看 Slice 文件
ls spec/baseline/plans/slices/
cat spec/baseline/plans/slices/slice-01-F001.md
```

#### 3.2 审查覆盖率

```bash
# 查看覆盖率矩阵
cat spec/baseline/plans/coverage-matrix.md

# 关注：
# - P0 功能覆盖率 = 100%
# - UI 页面覆盖率 = 100%
# - Placeholder 白名单率 = 100%
```

#### 3.3 审查决策

```bash
# 查看 grill #2 决策
cat spec/decision-ledger.md | grep "grill #2" -A 50

# 关注：
# - 三方 SDK 策略
# - 架构决策
# - 平台行为差异
```

#### 3.4 确认或修改

如果需要调整：

```bash
# 修改 ui-plan.md
vim spec/baseline/plans/ui-plan.md

# 修改 feature-plan.md
vim spec/baseline/plans/feature-plan.md

# 修改 slice 文件
vim spec/baseline/plans/slices/slice-01-F001.md

# 重新运行校验
python3 scripts/lint_plan_coverage.py ~/Projects/Cuike02
```

---

## iOS 特定场景处理

### 场景 1: SwiftUI + UIKit 混合项目

**问题**: 如何分批处理？

**方案**：
```markdown
## Batch 1: SwiftUI Views (P0)

| 序号 | 页面 | iOS 来源 | owning_slice |
|------|------|---------|--------------|
| 0001 | HomeView | HomeView.swift | F001 |
| 0002 | FeedView | FeedView.swift | F001 |

## Batch 2: UIKit ViewControllers (P0)

| 序号 | 页面 | iOS 来源 | owning_slice |
|------|------|---------|--------------|
| 0003 | ProfileViewController | ProfileViewController.swift | F002 |
| 0004 | SettingsViewController | SettingsViewController.swift | F002 |
```

**理由**: SwiftUI 相对简单，优先迁移；UIKit 需要更多调整，后续处理。

### 场景 2: CoreData 数据模型

**问题**: 如何处理 CoreData 实体关系？

**方案**：

1. **在 Base-1 定义模型**：
```markdown
- Base-1: Models
  suggested_skills: [arkts-data-model]
  input: spec/baseline/feature-base.md Models 段
  output: entry/src/main/ets/models/*.ets
  parallel_group: 1
  iOS 映射: CoreData NSManagedObject → @Observed class
```

2. **在 Base-2 处理数据库**：
```markdown
- Base-2: Database
  suggested_skills: [arkts-data-layer]
  input: spec/baseline/feature-base.md Database 段
  output: entry/src/main/ets/database/*.ets
  parallel_group: 2
  iOS 映射: CoreData → RelationalStore
  注意: 关系映射、级联删除、Fetch Request 迁移
```

### 场景 3: @EnvironmentObject 全局状态

**问题**: 如何处理 @EnvironmentObject 注入？

**方案**：

1. **强绑 arkts-state-manager**（自动触发）：
```markdown
# Rule iOS-1 自动触发
@EnvironmentObject → arkts-state-manager
```

2. **在 Base-4 创建全局状态**：
```markdown
- Base-4: Events
  suggested_skills: [arkts-state-manager]
  包含: @EnvironmentObject → 全局 @ObservedV2 class
```

3. **在 Slice wires 中体现注入**：
```yaml
wires:
  - page: HomeView.ets
    viewmodel: null  # 使用全局状态，无独立 ViewModel
```

### 场景 4: TabView 容器页

**问题**: TabView 归属哪个 Slice？

**方案**：

1. **归属第一个 Tab 的 Slice**：
```markdown
# ui-plan.md
| 0001 | MainTabView | MainTabView.swift | F001 |  ← 容器归 F001
| 0002 | HomeView | HomeView.swift | F001 |        ← Tab 1
| 0005 | HistoryView | HistoryView.swift | F002 |    ← Tab 2
```

2. **在 Slice wires 中体现嵌入**：
```yaml
# slice-01-F001.md
wires:
  - page: entry/src/main/ets/pages/MainTabView.ets
    slot: homeTab
    embed: HomeView()
    resolve_by: Slice 1 Step 3a

# slice-02-F002.md
wires:
  - page: entry/src/main/ets/pages/MainTabView.ets
    slot: historyTab
    embed: HistoryView()
    resolve_by: Slice 2 Step 3a

modifies_files:
  - entry/src/main/ets/pages/MainTabView.ets
  cross_slice_edits:
    - file: entry/src/main/ets/pages/MainTabView.ets
      handler: historyTab
      resolve_by: Slice 2 Step 3a
```

### 场景 5: 三方 SDK（微信 SDK）

**问题**: 如何处理微信 SDK？

**方案**：

1. **检查 skill-binding-rules.md 映射**：
```markdown
| 微信 SDK（登录/分享/支付） | arkts-login, arkts-payment, arkts-share | WechatOpenSDK |
```

2. **自动追加到 suggested_skills+**：
```markdown
# slice-02-F002.md (登录功能)
- Step 3b: ViewModel
  scope: LoginViewModel
  suggested_skills+: arkts-login
  input: spec_refs: features/F002-*.md#登录
```

3. **无需占位**（命中本表）：
```markdown
# placeholder-registry.md 不会包含微信 SDK 条目
```

---

## 常见问题排查

### Q1: 覆盖率校验一直失败

**症状**：
```
❌ P0 功能覆盖率: 3/4 (75%)
   缺失 P0 功能: F004
```

**排查步骤**：
1. 检查 feature-index.md 是否包含 F004
2. 检查 F004 的优先级是否为 P0
3. 检查 feature-plan.md 是否有 F004 的 Slice
4. 检查 F004 的 spec 文件是否存在

**解决方案**：
```bash
# 方案 1: 添加缺失的 Slice
# 在 feature-plan.md 中添加 F004 的 Slice 条目

# 方案 2: 调整优先级
# 如果 F004 不是 P0，在 feature-index.md 中改为 P1

# 方案 3: 标记为 skipped
# 在 feature-index.md 中添加 status: skipped
```

### Q2: Placeholder trigger 不合规

**症状**：
```
❌ Placeholder trigger 白名单率: 2/3 (66%)
   - P-S3-001: 包含黑名单关键词 "等真机"
```

**排查步骤**：
1. 检查 placeholder-registry.md 中的 P-S3-001
2. 查看 trigger_condition 是否包含黑名单关键词
3. 理解占位的真实触发条件

**解决方案**：
```bash
# 修改 placeholder-registry.md
vim spec/placeholder-registry.md

# 错误的 trigger:
trigger_condition: 等真机联调时处理

# 正确的 trigger:
trigger_condition: 蓝牙 SDK 入仓
```

**白名单格式参考**：
- `D-5 chosen` - 决策编号
- `BeanStore.ets 实现 saveBatch` - 实现符号
- `埋点 SDK 入仓` - SDK 入仓
- `Slice 3 Step 3c` - Slice 步骤

### Q3: UI Plan 有 size-1 批次

**症状**：
```
❌ Batch 3 只有 1 个页面（size-1 批次）
   建议: 应并入前一批次末尾
```

**解决方案**：
```bash
# 编辑 ui-plan.md
vim spec/baseline/plans/ui-plan.md

# 将 Batch 3 的页面移到 Batch 2 末尾
# 删除 Batch 3 的标题和结算检查点

# 修改前:
## Batch 2: P1 Pages
| 0005 | StatsView | ... | F003 |

## Batch 3: P1 Pages
| 0006 | SettingsView | ... | F004 |

# 修改后:
## Batch 2: P1 Pages
| 0005 | StatsView | ... | F003 |
| 0006 | SettingsView | ... | F004 |
```

### Q4: 门禁检查失败

**症状**：
```
❌ 存在 blocking findings
   3 个阻断级别的 findings 未解决
```

**解决方案**：
```bash
# 查看 open-findings.json
cat spec/.i2h/open-findings.json | jq

# 处理每个 blocking finding:
# 1. 补充缺失信息
# 2. 添加决策引用 (decision_ref)
# 3. 或降级为 warning

# 重新运行 gate
python3 scripts/gate_plan_complete.py ~/Projects/Cuike02
```

---

## 最佳实践

### 1. 迭代式生成

**不要一次性生成全部**，建议分阶段：

**第 1 轮**：只生成 P0 功能
```bash
# 在 feature-index.md 中暂时标记 P1/P2 为 skipped
# 运行 i2h-plan
# 验证 P0 产物质量
```

**第 2 轮**：添加 P1 功能
```bash
# 恢复 P1 功能的 skipped 标记
# 重新运行 i2h-plan
# 增量验证
```

**第 3 轮**：添加 P2 功能（可选）

### 2. 及早发现问题

**在每个阶段运行校验**：

```bash
# 生成后立即校验
python3 scripts/lint_plan_coverage.py .

# 不要等到最后才校验
```

### 3. 利用脚本加速

**使用脚本而非 LLM 校验**：

```bash
# ✅ 快速（2-3 秒）
python3 scripts/lint_plan_coverage.py .

# ❌ 慢（2-3 分钟）
# 让 LLM 手动检查覆盖率
```

### 4. 保持 plan 只读

**不要在 plan 文件中添加执行状态**：

```bash
# ❌ 错误: 添加 checkbox
- [ ] Step 3a: UI 补充

# ✅ 正确: 保持只读
- Step 3a: UI 补充
```

**状态记录在 brief 中**（由 i2h-execute 生成）：
```
spec/execution/briefs/
├── batch_01_brief.md
├── stage2_brief.md
└── group_01_brief.md
```

### 5. 明确占位触发条件

**使用白名单格式**：

```bash
# ❌ 模糊
trigger_condition: 后续处理

# ✅ 明确
trigger_condition: 支付 SDK 入仓
```

---

## 下一步

Plan 生成并通过校验后，进入 i2h-execute 阶段：

```bash
# 确认 plan 完成
cat spec/baseline/plans/complete.txt

# 运行 i2h-execute
/i2h-execute
```

---

## 附录

### A. 文件清单

**输入**（来自 i2h-spec）:
- spec/baseline/feature-index.md
- spec/baseline/ui-manifest.md
- spec/baseline/features/*.md
- spec/baseline/ui/*.md
- spec/baseline/feature-base.md
- spec/decision-ledger.md

**输出**（i2h-plan 生成）:
- spec/baseline/plans/ui-plan.md
- spec/baseline/plans/feature-plan.md
- spec/baseline/plans/base-plan.md
- spec/baseline/plans/slices/*.md
- spec/baseline/plans/coverage-matrix.md
- spec/placeholder-registry.md
- spec/baseline/plans/complete.txt

### B. 校验脚本清单

| 脚本 | 功能 | 耗时 |
|------|------|------|
| lint_plan_coverage.py | 12 项覆盖率校验 | 2-3 秒 |
| lint_ui_plan.py | UI Plan 专项校验 | 1-2 秒 |
| lint_feature_plan.py | Feature Plan 专项校验 | 1-2 秒 |
| gate_plan_complete.py | 完成门禁 | 1 秒 |

### C. 常用命令

```bash
# 查看 plan 统计
grep "Total pages:" spec/baseline/plans/ui-plan.md
grep "Feature groups:" spec/baseline/plans/feature-plan.md

# 查看覆盖率
grep "覆盖率" spec/baseline/plans/coverage-matrix.md

# 查看 Slice 数量
ls spec/baseline/plans/slices/ | wc -l

# 查看 Placeholder 数量
grep "^| P-" spec/placeholder-registry.md | wc -l
```

---

**文档版本**: v1.0  
**最后更新**: 2024-11-03  
**作者**: Claude Opus 5.5
