<!-- when: i2h-plan §3.0 编排派发（P1 三写 A∥B∥C）时加载 -->
<!-- topics: plan 派发参数, kernel 内联, ui-plan writer, base-plan writer, slice writer, 信封契约 -->

# i2h-plan 派发参数模板（编排 P1 三写并行）

> 编排协议与阶段划分单源 = SKILL.md §3.0；本文件只收三个派发的参数模板 + 公共纪律。规则权威在各模板 / SKILL 正文——派发 prompt 不复述规则，只带 MUST-Read 清单与 kernel 数据。

## 公共纪律（三派发通用）

- **MUST-Read**：各派发列出的模板 / references 必须整文件 Read（SKILL Critical 强制加载条款适用于 subagent，跳过 = PROCESS_VIOLATION）。
- **单写者分配**：A→ui-plan.md；B→plans/base-plan.md；C→plans/slices/* + spec/placeholder-registry.md（P1 窗口唯一 registry 写者——B 的 P-B 行信封带回，无并发）；索引 / coverage-matrix 主线程写，agent 禁碰。
- **kernel 只抄不判**：归属消歧 / hub / 横切 / 定号已由主线程 P0 裁决并随 prompt 内联下发；agent 发现 kernel 与 spec 冲突 → 信封报告，禁自行改判。
- **返回 = 信封 ≤30 行**：状态 + 计数 + 路径；禁贴产物正文。
- **派发 prompt 禁复述**模板 / SKILL 已载规则——一行 MUST-Read 指针即可；但任务专属参数（kernel 表 / 清单）不得省略。

---

## P1-A：ui-plan writer

派发一个通用子代理，任务提示词：

```
生成 spec/baseline/plans/ui-plan.md。MUST 先 Read: i2h-plan/templates/ui-plan-template.md（整文件，分批规则与表格形态以其为准）。
  页面归属表（kernel，只抄不判，含 hub 裁决结果）: {page_owning_map}    # 页 id → 裸 F-ID
  分批输入: spec/baseline/ui-manifest.md（优先级 / confidence / 依赖三源见模板生成规则）
  batch_max: {BATCH_MAX}                              # 主线程按宿主取表（SKILL Step 2 规则 2）
  写权: 仅 ui-plan.md。
```

### 信封契约

```json
{
  "status": "success",
  "batches_count": 2,
  "pages_total": 7,
  "low_confidence_pages": [],
  "kernel_conflicts": [],
  "output_path": "spec/baseline/plans/ui-plan.md"
}
```

### iOS 特定参数

**BATCH_MAX 宿主表**（与模板一致）：
- Codex = 20（目标区间 [12,20]，`run_in_background`）
- Codex = 8（目标区间 [6,8]）
- DevEco Code = 10（目标区间 [8,10]，`background: true`）

**page_owning_map 示例**（iOS 项目）：
```json
{
  "0001": "F001",  // MainContainer → F001
  "0002": "F001",  // HomeView → F001
  "0003": "F001",  // BeanListView → F001
  "0004": "F001",  // BeanDetailView → F001
  "0005": "F002",  // BrewHistoryView → F002
  "0006": "F003",  // StatsView → F003
  "0007": "F004"   // SettingsView → F004
}
```

**hub 裁决结果**（容器页归属）：
- MainContainer（Tab 容器）→ 归最早 Tab 的 Slice（F001）
- UITabBarController → 同上规则

---

## P1-B：base-plan writer

派发一个通用子代理，任务提示词：

```
生成 spec/baseline/plans/base-plan.md。MUST 先 Read: i2h-plan/templates/feature-plan-template.md（整文件，「文件二」段为生成规范）+ i2h-plan/references/skill-binding-rules.md。
  输入: spec/baseline/feature-base.md + feature-index.md 共享组件/服务；chain-auth 存在时按 SKILL Step 4.3 表注入 Base 侧 data_chain_refs（L0 / L2-L3 行）；每任务写 `parallel_group:`（模板默认分组为待确认项：逐任务核对 feature-base.md 确认不 import 同组产出，否则拆组，判据见模板）
  写权: 仅 base-plan.md；如产生 P-B 占位 → 行全文写入信封带回，禁直写 registry。
```

### 信封契约

```json
{
  "status": "success",
  "base_tasks_count": 8,
  "registry_rows_pending": [],
  "chain_auth_injected": "N/A",
  "output_path": "spec/baseline/plans/base-plan.md"
}
```

### iOS 特定 Base 层任务

**默认 8 个任务**：
- Base-0: 资源前置（ios2hmos_resources_convert）
- Base-1: Models（Swift struct/class → @Observed class）
- Base-2: Database（CoreData/SwiftData → RelationalStore）
- Base-3: Network（URLSession/Alamofire → @ohos.net.http）
- Base-4: Events（NotificationCenter/Combine → EventHub/emitter）
- Base-5: Preferences（UserDefaults/@AppStorage → Preferences）
- Base-6: 公共组件库（SwiftUI/UIKit 组件 → @Component）
- Base-7: 编译验证（hmos-builder）

**parallel_group 默认分配**（iOS）：
- Base-1 (Models): group 1（无依赖）
- Base-2, Base-4, Base-5, Base-6: group 2（可并行）
- Base-3 (Network): group 3（可能依赖 Preferences 的 token）
- Base-7 (编译): group 4（独占末组）

**P-B 占位场景**（iOS）：
- 使用了自定义图片资源但未提供 → P-B1-001
- 使用了第三方 SDK（如 Kingfisher）但未决策 → P-B6-001

---

## P1-C：slice writer（全量；参数 `{slice_list}` 天然支持将来分片为 K=ceil(N/4) 个同构 writer，协议不变）

派发一个通用子代理，任务提示词：

```
按 i2h-plan SKILL §3b Step 4.0–4.3 生成全部 slice 文件。MUST 先 Read: i2h-plan/SKILL.md（Step 4.0–4.3 为执行规范）+ templates/slice-plan-template.md + templates/placeholder-registry-template.md + references/skill-binding-rules.md；**必读 spec/baseline/api-inventory/**（apis/ 逐服务契约——Step 3c scope 与 suggested_skills+ 的 API 事实源；data-chains/chain-auth.md——Step 4.3）。
  slice 清单（kernel 定号，只抄）: {slice_list}       # Slice N ↔ F-ID ↔ spec 路径 ↔ depends_on
  页面归属表: {page_owning_map}
  对接点归属映射: {wiring_owner_map}                  # cross_slice_edits 的 owner 与 resolve_by 依据
  写权: plans/slices/slice-NN-<fid>.md（每文件恰写一次）+ placeholder-registry.md 直写（Step 4.1 原文执行）。
```

### 信封契约

```json
{
  "status": "success",
  "slices_written": 4,
  "per_slice": {
    "1": {"placeholders": 0, "fwd_refs": 0},
    "2": {"placeholders": 0, "fwd_refs": 1},
    "3": {"placeholders": 0, "fwd_refs": 0},
    "4": {"placeholders": 0, "fwd_refs": 0}
  },
  "kernel_conflicts": [],
  "output_paths": [
    "spec/baseline/plans/slices/slice-01-F001.md",
    "spec/baseline/plans/slices/slice-02-F002.md",
    "spec/baseline/plans/slices/slice-03-F003.md",
    "spec/baseline/plans/slices/slice-04-F004.md"
  ]
}
```

### iOS 特定参数

**slice_list 示例**（iOS 项目）：
```json
[
  {
    "slice_id": 1,
    "feature_id": "F001",
    "feature_name": "咖啡豆管理",
    "spec_path": "spec/baseline/features/F001-bean-management.md",
    "depends_on": ["base"],
    "complexity": "simple",
    "priority": "P0",
    "pages_owned": ["0001", "0002", "0003", "0004"]
  },
  {
    "slice_id": 2,
    "feature_id": "F002",
    "feature_name": "冲煮记录",
    "spec_path": "spec/baseline/features/F002-brew-history.md",
    "depends_on": ["base"],
    "complexity": "simple",
    "priority": "P0",
    "pages_owned": ["0005"]
  },
  {
    "slice_id": 3,
    "feature_id": "F003",
    "feature_name": "数据统计",
    "spec_path": "spec/baseline/features/F003-statistics.md",
    "depends_on": ["base", "F001", "F002"],
    "complexity": "medium",
    "priority": "P1",
    "pages_owned": ["0006"]
  },
  {
    "slice_id": 4,
    "feature_id": "F004",
    "feature_name": "用户偏好",
    "spec_path": "spec/baseline/features/F004-preferences.md",
    "depends_on": ["base"],
    "complexity": "simple",
    "priority": "P1",
    "pages_owned": ["0007"]
  }
]
```

**wiring_owner_map 示例**（iOS 项目）：
```json
{
  "pages/BeanListView.ets#onBeanSelect": {
    "owner": "F001",
    "type": "owned"
  },
  "pages/MainContainer.ets#onTabChange": {
    "owner": "F001",
    "type": "owned"
  },
  "pages/BeanDetailView.ets#onAddToBrewHistory": {
    "owner": "F002",
    "type": "cross_slice",
    "original_owner": "F001"
  },
  "pages/MainContainer.ets#beanListTab": {
    "owner": "F001",
    "type": "embed",
    "slot": "beanListContent"
  },
  "pages/MainContainer.ets#historyTab": {
    "owner": "F002",
    "type": "embed",
    "slot": "historyContent"
  }
}
```

**iOS 特定嵌入场景**：
- **SwiftUI TabView**: MainContainer 的各 Tab 槽位 → 各 Slice 的 wires embed 条目
- **SwiftUI Sheet**: 模态弹窗嵌入 → wires embed 条目（slot: detailSheet）
- **UIKit Child ViewController**: addChild() 嵌入 → wires embed 条目

---

## 降级方案（子代理派发不可用时）

**触发条件**：
- 无派发工具
- 用户要求单线程
- 局部复跑

**降级行为**：
主线程按 §3a→§3b 原序自跑全部步骤，**零行为差异**：
1. P0: 执行 kernel 裁决（归属消歧、hub、横切、定号）
2. 生成 ui-plan.md（原地）
3. 生成 base-plan.md（原地）
4. 生成 slices/*.md（循环）
5. P2: 收拢（定组、索引、coverage、审批）

**质量保证**：
- 单线程执行时，所有规则和校验与并行派发一致
- 产物格式完全相同
- 覆盖率校验标准不降低

---

## 信封处理（主线程 P2 收拢）

### 汇总统计

```json
{
  "ui_plan": {
    "batches": 2,
    "pages": 7,
    "low_confidence": 0
  },
  "base_plan": {
    "tasks": 8,
    "pending_placeholders": 0
  },
  "slices": {
    "total": 4,
    "placeholders": 0,
    "fwd_refs": 1
  }
}
```

### 冲突处理

**kernel_conflicts 非空时**（agent 发现 kernel 与 spec 冲突）：
1. 记录冲突详情
2. 主线程复核
3. 修正 kernel 或 spec
4. 重新派发相关 agent

**示例冲突**：
```json
{
  "type": "page_ownership_conflict",
  "page_id": "0005",
  "kernel_owner": "F001",
  "spec_claimed_by": ["F001", "F002"],
  "resolution": "按拓扑序归 F001，F002 走 cross_slice_edit"
}
```

---

## iOS 特定注意事项

### SwiftUI vs UIKit 混合项目

**分批策略**：
- SwiftUI Views 优先（相对简单）
- UIKit ViewControllers 后续（需要更多调整）

**示例 page_owning_map**（混合项目）：
```json
{
  "0001": "F001",  // HomeView (SwiftUI) → F001
  "0002": "F001",  // FeedView (SwiftUI) → F001
  "0003": "F002",  // ProfileViewController (UIKit) → F002
  "0004": "F002"   // SettingsViewController (UIKit) → F002
}
```

### CoreData/SwiftData 依赖

**Base-2 特殊处理**：
- CoreData: 需要生成 Schema + DAO
- SwiftData: @Model 直接映射到 @Observed class

**parallel_group 调整**：
- 如果多个 Base 任务依赖 Models → 确保 Base-1 在 group 1
- 如果 Network 需要 token（存储在 Preferences）→ Base-3 在 group 3

### 容器页归属

**TabBarController / TabView 规则**：
- 容器页归属第一个 Tab 的 Slice
- 其他 Tab 通过 wires embed 条目体现

**示例**：
```
MainTabBarController (page_0001) → F001
  ├─ Tab 1: HomeView (page_0002) → F001 (owned)
  ├─ Tab 2: HistoryView (page_0005) → F002 (embed)
  ├─ Tab 3: StatsView (page_0006) → F003 (embed)
  └─ Tab 4: SettingsView (page_0007) → F004 (embed)
```

---

## 完整示例（iOS 咖啡记录应用）

### P0 Kernel 裁决结果

```json
{
  "page_owning_map": {
    "0001": "F001",
    "0002": "F001",
    "0003": "F001",
    "0004": "F001",
    "0005": "F002",
    "0006": "F003",
    "0007": "F004"
  },
  "slice_list": [
    {"slice_id": 1, "feature_id": "F001", "depends_on": ["base"]},
    {"slice_id": 2, "feature_id": "F002", "depends_on": ["base"]},
    {"slice_id": 3, "feature_id": "F003", "depends_on": ["base", "F001", "F002"]},
    {"slice_id": 4, "feature_id": "F004", "depends_on": ["base"]}
  ],
  "wiring_owner_map": {
    "pages/MainContainer.ets#beanListTab": {"owner": "F001", "type": "embed"},
    "pages/MainContainer.ets#historyTab": {"owner": "F002", "type": "embed"},
    "pages/MainContainer.ets#statsTab": {"owner": "F003", "type": "embed"},
    "pages/MainContainer.ets#settingsTab": {"owner": "F004", "type": "embed"}
  }
}
```

### P1 派发执行

**并行执行**：
- Agent A: 生成 ui-plan.md（2 批次，7 页面）
- Agent B: 生成 base-plan.md（8 任务）
- Agent C: 生成 4 个 slice 文件 + placeholder-registry.md

### P2 收拢结果

```json
{
  "status": "success",
  "ui_plan": {"batches": 2, "pages": 7},
  "base_plan": {"tasks": 8},
  "slices": {"total": 4, "placeholders": 0},
  "conflicts": [],
  "ready_for_coverage": true
}
```

---

## 模板版本

**版本**: v1.0  
**适配平台**: iOS → HarmonyOS  
**基于**: Android a2h-plan plan-dispatch.md  
**最后更新**: 2024-11-03
