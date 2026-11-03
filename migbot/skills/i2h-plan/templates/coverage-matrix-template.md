<!-- when: 覆盖率校验（§7）输出 coverage-matrix.md 时加载 -->
<!-- topics: coverage-matrix, Feature Gaps, UI Page Gaps, Wiring Ownership Map, 分层校验 -->

# coverage-matrix.md 完整模板

§7 覆盖率校验通过后输出 `spec/baseline/plans/coverage-matrix.md`。各失败表（Placeholder / Complex Slice anchor / 对接点归属）只在对应校验不通过时填行，通过则留空表头。

```markdown
# Coverage Matrix

Generated: {ISO 8601 时间戳}

## Summary
- Feature 覆盖率:
  - P0: X/Y (Z%) — 必须 100% {✅/❌}
  - P1: X/Y (Z%) — 建议 >= 80% {✅/⚠️}
  - P2 / Skip: X 个 GAP（允许）
- UI 页面覆盖率: X/Y (Z%) {✅/❌}
- Placeholder trigger 白名单率: 100% ✓（直接对 spec/placeholder-registry.md 校验——plan 期占位直写 registry，无中转副本）
- Complex Slice anchor 完整率: 100% ✓（直接读 feature spec 顶部 anchors 校验路径存在性）
- 对接点归属率: X/Y (Z%) {✅/❌}
- 组件嵌入归属率: X/Y (Z%) {✅/❌}
- 分层校验 5 项（索引对应 / spec_refs 存在 / 快照一致 / 零复述 / 状态交叉）: {PASS/FAIL} {✅/❌}
- 功能分组校验: {PASS/FAIL} {✅/❌}

## Feature Gaps
| F-ID | 功能名 | 优先级 | 状态 | 原因 |
|------|--------|--------|------|------|
| F-xxx | ... | P1 | MISSING | 未在任何 Slice 中覆盖 |

## UI Page Gaps
| 序号 | 页面 | iOS 来源 | 优先级 | 状态 | 原因 |
|------|------|---------|--------|------|------|
| 00XX | XxxView | XxxView.swift | P1 | MISSING | 未在 ui-plan 中覆盖 |

## Placeholder 校验失败
| P-ID | 所属 Slice/Base | Location | 失败原因 |
|------|-----------------|----------|---------|
| P-S3-002 | Slice 3 | services/PaymentService.ets | trigger_condition 含黑名单关键词"待定" |
| P-B1-001 | Base-6 | components/CustomChart.ets | kind=forward-ref 但缺少 resolve_by |

## Complex Slice anchor 校验失败
| Slice | Feature | 失败原因 |
|-------|---------|---------|
| Slice 5 | F-007 VIP 会员 | complexity=complex 但 ios_source_anchors 为空 |
| Slice 8 | F-010 支付 | anchor path 指向的 iOS 源文件不存在 |

## Deferred
| F-ID | 功能名 | 优先级 | 原因 |
|------|--------|--------|------|
| F-xxx | ... | P2 | P2 允许 GAP |
| F-yyy | ... | P0 | 已记账决策 (D-005) |

## Full Feature Matrix
| F-ID | 功能名 | 优先级 | 覆盖 Slice | 状态 |
|------|--------|--------|-----------|------|
| F001 | 咖啡豆管理 | P0 | Slice 1 | ✅ COVERED |
| F002 | 冲煮记录 | P0 | Slice 2 | ✅ COVERED |
| F003 | 数据统计 | P1 | Slice 3 | ✅ COVERED |
| F004 | 用户偏好 | P1 | Slice 4 | ✅ COVERED |

## Full UI Page Matrix
| 序号 | 页面 | iOS 来源 | 优先级 | 覆盖 Batch | owning_slice | 状态 |
|------|------|---------|--------|-----------|--------------|------|
| 0001 | MainContainer | MainTabBarController.swift | P0 | Batch 1 | F001 | ✅ COVERED |
| 0002 | HomeView | HomeView.swift | P0 | Batch 1 | F001 | ✅ COVERED |
| 0003 | BeanListView | BeanListView.swift | P0 | Batch 1 | F001 | ✅ COVERED |
| 0004 | BeanDetailView | BeanDetailView.swift | P0 | Batch 1 | F001 | ✅ COVERED |
| 0005 | BrewHistoryView | BrewHistoryView.swift | P0 | Batch 1 | F002 | ✅ COVERED |
| 0006 | StatsView | StatsView.swift | P1 | Batch 2 | F003 | ✅ COVERED |
| 0007 | SettingsView | SettingsView.swift | P1 | Batch 2 | F004 | ✅ COVERED |

## Wiring Ownership Map
> 由 §7 第 8 项跨切片接线归属检测产出。供 i2h-execute §3a converter 计算 forward-ref `resolve_by`。

| 文件 | Handler | Slot | Owning Slice | 类型 | 说明 |
|------|---------|------|--------------|------|------|
| pages/BeanListView.ets | onBeanSelect | - | Slice 1 | owned | 首切片创建 |
| pages/MainContainer.ets | onTabChange | - | Slice 1 | owned | 首切片创建 |
| pages/BeanDetailView.ets | onAddToBrewHistory | - | Slice 2 | cross_slice | 文件由 Slice 1 创建，Slice 2 添加 handler |
| pages/MainContainer.ets | beanListTab | beanListContent | Slice 1 | embed | Tab 槽位填充 |
| pages/MainContainer.ets | historyTab | historyContent | Slice 2 | embed | Tab 槽位填充 |

> slot 可选：仅同 `(文件,handler)` 落在不同槽位（Tab 槽位 / @Builder 名）时填，作 P2 撞键区分；留空时退化为二元键，行为不变。

## Component Embed Coverage（组件嵌入覆盖率）
> 从 ui-manifest.md 子组件表 + page_NNNN.md 嵌入关系提取，每条「父页 ⊇ 子页」须在子页 owning Slice 的 wires embed 条目中体现。

| 父页面 | Slot | 嵌入子组件 | Owning Slice | 状态 | 来源 |
|--------|------|-----------|--------------|------|------|
| MainContainer | beanListContent | BeanListView | Slice 1 | ✅ 已归属 | ui-manifest 子组件表 |
| MainContainer | historyContent | BrewHistoryView | Slice 2 | ✅ 已归属 | ui-manifest 子组件表 |
| BeanDetailView | recipeSheet | RecipeFormView | Slice 1 | ✅ 已归属 | page_0004.md 嵌入关系 |
| StatsView | chartView | ChartView | Slice 3 | ✅ 已归属 | page_0006.md 嵌入关系 |

## Skill Routing Map（各 slice Step 行 `suggested_skills+` 增量汇总）
> 派生视图：从 `slices/*.md` 的 Step 行 `suggested_skills+:` 汇总，供一处审阅 skill 分布（L1 索引不承载 skill 路由）。默认映射（i2h-plan §4 表：3a=i2h-swiftui-converter/3b=arkts-state-manager/3c=arkts-data-layer/3d=arkts-state-manager）**不列**，只列差异化增量；无增量的 slice 省略。

| Slice | Feature | Step | suggested_skills+（增量） |
|-------|---------|------|--------------------------|
| Slice 1 (F001) | 咖啡豆管理 | 3c | arkts-data-layer |
| Slice 2 (F002) | 冲煮记录 | 3c | arkts-data-layer |
| Slice 3 (F003) | 数据统计 | 3b | arkts-chart（待定） |

## 对接点归属校验失败
| Feature Spec | 对接点 | 失败原因 |
|--------------|--------|---------|
| F-005.md | TabComponent.onSearchClick | owning Slice 的 integration_points_ref 未指向该 spec 段，且无 cross_slice_edits 认领 |

## 分层校验失败（§7 分层校验 5 项，通过则留空表头）
| 检查项 | 对象 | 失败原因 |
|--------|------|---------|
| 索引↔文件对应 | Slice 12 | detail 指针指向的 slices/slice-12-F012.md 不存在 |
| spec_refs 存在 | Slice 10 | spec_refs 指向的 features/F008-api.md 不存在 |
| 快照一致性 | Slice 4 | 索引 complexity=simple 与 spec 顶部 complex 不一致 |
| 零复述 | Slice 6 | 条目超行数上限（疑似复制 spec 正文） |
| 状态交叉 | F007 | feature-index status=implemented 但 owned 页 0034 仍 pending |

## 功能分组校验
| 检查项 | 状态 | 说明 |
|--------|------|------|
| 最早可行组 | ✅ PASS | 所有 slice 已排入最早可行组 |
| 组容量上限 | ✅ PASS | 所有组 ≤ GROUP_HARD_LIMIT(8) |
| size-1 组处理 | ✅ PASS | 无 size-1 组或已正确处理（并组/附挂） |

size-1 组例外（无则省略本节）:
- Group 5: Slice 10 (附挂至 Group 4)
  - 理由: 无同层可并候选，双向依赖判据满足
```

---

## iOS 特定说明

### iOS 页面来源标注

**格式**：相对于项目根目录的路径

**SwiftUI 示例**：
- `App/Views/HomeView.swift`
- `Features/Beans/Views/BeanListView.swift`
- `Shared/Components/CustomButton.swift`

**UIKit 示例**：
- `App/ViewControllers/HomeViewController.swift`
- `Features/Profile/ProfileViewController.swift`
- `App/Controllers/MainTabBarController.swift`

### 覆盖率计算

#### Feature 覆盖率

**计算公式**：
```
覆盖率 = (已覆盖功能数 / 总功能数) × 100%
```

**来源**：
- 总功能数：从 `spec/baseline/feature-index.md` 提取所有 F-ID
- 已覆盖功能数：从 `plans/slices/*.md` 提取所有 feature_id

**分级统计**：
- P0 功能：必须 100% 覆盖（阻断）
- P1 功能：建议 ≥ 80% 覆盖（警告）
- P2 功能：允许 GAP（不阻断）

#### UI 页面覆盖率

**计算公式**：
```
覆盖率 = (ui-plan 中的页面数 / ui-manifest 中的非 skipped 页面数) × 100%
```

**来源**：
- 总页面数：从 `spec/baseline/ui-manifest.md` 提取所有页面（排除 status=skipped）
- 已覆盖页面数：从 `plans/ui-plan.md` 提取所有页面序号

**要求**：必须 100% 覆盖（阻断）

#### 对接点归属率

**计算公式**：
```
归属率 = (已归属对接点数 / 总对接点数) × 100%
```

**来源**：
- 总对接点数：从所有 feature spec 的「## 对接点」段提取
- 已归属对接点数：从 slice 文件的 `integration_points_ref` + `cross_slice_edits` 统计

**要求**：必须 100% 覆盖（阻断）

#### 组件嵌入归属率

**计算公式**：
```
归属率 = (已归属嵌入关系数 / 总嵌入关系数) × 100%
```

**来源**：
- 总嵌入关系数：从 `ui-manifest.md` 子组件表 + 各 `page_NNNN.md` 嵌入关系提取
- 已归属嵌入关系数：从 slice 文件的 `wires` embed 条目统计

**要求**：必须 100% 覆盖（阻断）

### iOS 特定 Anchor 类型

在 Complex Slice anchor 校验中，iOS 源码锚点类型：

| 角色 (role) | iOS 示例 | 说明 |
|------------|---------|------|
| view | HomeView.swift | SwiftUI View |
| view_controller | HomeViewController.swift | UIKit ViewController |
| viewmodel | BeanViewModel.swift | ViewModel 类 |
| store | BeanStore.swift | Store 类（SwiftUI） |
| service | NetworkService.swift | 服务类 |
| repository | BeanRepository.swift | 数据仓库 |
| manager | LocationManager.swift | 管理类 |
| coordinator | AppCoordinator.swift | 协调器 |
| delegate | TableViewDelegate.swift | 委托类 |
| util | DateFormatter+Extension.swift | 工具类 |
| data_model | Bean.swift | 数据模型 |

### Placeholder 白名单（iOS）

**trigger_condition 白名单**：

1. **三方 SDK 类**（kind=thirdparty-sdk）：
   - `{SDK 类别} SDK 入仓`
   - 示例：`微信 SDK 入仓`、`Firebase SDK 入仓`、`Alamofire SDK 入仓`

2. **Forward-ref 类**（kind=forward-ref）：
   - `Slice {N} Step {3c|3d}`
   - 示例：`Slice 5 Step 3c`、`Slice 10 Step 3d`

3. **决策前置类**：
   - `D-{N} chosen`
   - 示例：`D-005 chosen`（引用 decision-ledger 的决策编号）

**黑名单关键词**（禁止出现）：
- "待定"、"TODO"、"未实现"、"延后"
- "等真机"、"等环境"、"等配置"
- "后续"、"将来"、"未来"

### Skill Routing Map（iOS 特定）

**默认映射**（不列入增量）：

| Step | 默认 suggested_skills |
|------|---------------------|
| Step 3a | i2h-swiftui-converter / i2h-uikit-converter |
| Step 3b | arkts-state-manager |
| Step 3c | arkts-data-layer |
| Step 3d | arkts-state-manager |

**常见增量**（列入 Skill Routing Map）：

| iOS 功能 | suggested_skills+ |
|---------|-------------------|
| Sign in with Apple | arkts-login |
| Apple Pay / StoreKit | arkts-payment |
| CoreLocation | arkts-location |
| MapKit | arkts-map |
| AVFoundation | arkts-camera, arkts-media |
| WKWebView | arkts-webview |
| URLSession (复杂网络) | arkts-network |
| CoreData / SwiftData | arkts-data-layer（已包含在默认，特殊情况才列） |

### 完整示例（iOS 咖啡记录应用）

```markdown
# Coverage Matrix

Generated: 2024-11-03T10:30:00Z

## Summary
- Feature 覆盖率:
  - P0: 2/2 (100%) ✅
  - P1: 2/2 (100%) ✅
  - P2 / Skip: 0 个 GAP
- UI 页面覆盖率: 7/7 (100%) ✅
- Placeholder trigger 白名单率: 100% ✓
- Complex Slice anchor 完整率: N/A（无 complex slice）✓
- 对接点归属率: 4/4 (100%) ✅
- 组件嵌入归属率: 4/4 (100%) ✅
- 分层校验 5 项: PASS ✅
- 功能分组校验: PASS ✅

## Feature Gaps
（无 GAP）

## UI Page Gaps
（无 GAP）

## Placeholder 校验失败
（无失败）

## Complex Slice anchor 校验失败
（本项目全部为 simple slice）

## Deferred
（无 Deferred）

## Full Feature Matrix
| F-ID | 功能名 | 优先级 | 覆盖 Slice | 状态 |
|------|--------|--------|-----------|------|
| F001 | 咖啡豆管理 | P0 | Slice 1 | ✅ COVERED |
| F002 | 冲煮记录 | P0 | Slice 2 | ✅ COVERED |
| F003 | 数据统计 | P1 | Slice 3 | ✅ COVERED |
| F004 | 用户偏好 | P1 | Slice 4 | ✅ COVERED |

## Full UI Page Matrix
| 序号 | 页面 | iOS 来源 | 优先级 | 覆盖 Batch | owning_slice | 状态 |
|------|------|---------|--------|-----------|--------------|------|
| 0001 | MainContainer | App/MainTabBarController.swift | P0 | Batch 1 | F001 | ✅ COVERED |
| 0002 | HomeView | App/Views/HomeView.swift | P0 | Batch 1 | F001 | ✅ COVERED |
| 0003 | BeanListView | App/Views/BeanListView.swift | P0 | Batch 1 | F001 | ✅ COVERED |
| 0004 | BeanDetailView | App/Views/BeanDetailView.swift | P0 | Batch 1 | F001 | ✅ COVERED |
| 0005 | BrewHistoryView | App/Views/BrewHistoryView.swift | P0 | Batch 1 | F002 | ✅ COVERED |
| 0006 | StatsView | App/Views/StatsView.swift | P1 | Batch 2 | F003 | ✅ COVERED |
| 0007 | SettingsView | App/Views/SettingsView.swift | P1 | Batch 2 | F004 | ✅ COVERED |

## Wiring Ownership Map
| 文件 | Handler | Slot | Owning Slice | 类型 | 说明 |
|------|---------|------|--------------|------|------|
| pages/BeanListView.ets | onBeanSelect | - | Slice 1 | owned | 首切片创建 |
| pages/MainContainer.ets | onTabChange | - | Slice 1 | owned | 首切片创建 |
| pages/BeanDetailView.ets | onAddToBrewHistory | - | Slice 2 | cross_slice | Slice 2 回改 |
| pages/MainContainer.ets | beanListTab | beanListContent | Slice 1 | embed | Tab 槽位填充 |
| pages/MainContainer.ets | historyTab | historyContent | Slice 2 | embed | Tab 槽位填充 |
| pages/MainContainer.ets | statsTab | statsContent | Slice 3 | embed | Tab 槽位填充 |
| pages/MainContainer.ets | settingsTab | settingsContent | Slice 4 | embed | Tab 槽位填充 |

## Component Embed Coverage
| 父页面 | Slot | 嵌入子组件 | Owning Slice | 状态 | 来源 |
|--------|------|-----------|--------------|------|------|
| MainContainer | beanListContent | BeanListView | Slice 1 | ✅ 已归属 | ui-manifest 子组件表 |
| MainContainer | historyContent | BrewHistoryView | Slice 2 | ✅ 已归属 | ui-manifest 子组件表 |
| MainContainer | statsContent | StatsView | Slice 3 | ✅ 已归属 | ui-manifest 子组件表 |
| MainContainer | settingsContent | SettingsView | Slice 4 | ✅ 已归属 | ui-manifest 子组件表 |

## Skill Routing Map
| Slice | Feature | Step | suggested_skills+（增量） |
|-------|---------|------|--------------------------|
| Slice 1 (F001) | 咖啡豆管理 | 3c | （无增量，使用默认 arkts-data-layer） |
| Slice 2 (F002) | 冲煮记录 | 3c | （无增量，使用默认 arkts-data-layer） |

## 对接点归属校验失败
（无失败）

## 分层校验失败
（无失败）

## 功能分组校验
| 检查项 | 状态 | 说明 |
|--------|------|------|
| 最早可行组 | ✅ PASS | Group 1: 3 个 Slices (F001, F002, F004) |
| 组容量上限 | ✅ PASS | Group 1: 3 ≤ 8, Group 2: 1 ≤ 8 |
| size-1 组处理 | ✅ PASS | Group 2 为 size-1 但符合例外（依赖 Slice 1/2） |

---

## 结论
✅ **全部覆盖率指标达标，plan 可输出。**
```

---

## 模板版本

**版本**: v1.0  
**适配平台**: iOS → HarmonyOS  
**基于**: Android a2h-plan coverage-matrix-template.md  
**最后更新**: 2024-11-03
