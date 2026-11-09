<!-- when: 生成 ui-plan.md 时加载 -->
<!-- topics: ui-plan, Batch 分批, owning_slice -->

# ui-plan.md 完整模板

body 只留分批规则（批数 = ceil(页数 ÷ BATCH_MAX)、按表序均分，BATCH_MAX 按宿主取表）；Batch 表格形态与下列生成规则在此模板。

## 生成规则

**页面依赖不参与分批**——导航 / 嵌入目标未建一律由 FWD-REF 机制兜底，批内无编译，跨批依赖零编译代价。**批内不标逐页并行关系**——批内默认全并行派发（单写者纪律各写各文件，导航目标未建由 FWD-REF 兜）。

**size-1 Batch 禁止**：孤页批并入**前一批**末尾，行内保留其原优先级标注（此并批不视为违反优先级单调性；§7 校验 size-1 批 = 0）。

**confidence 同为分批输入**（读 ui-manifest，high 在前）：**不输出 confidence 列**；仅 `low` 页在行内标 `⚠️low`（需人工补充 Xcode View Hierarchy dump 数据，异常才显性）。

**结算检查点**：每 Batch 末尾注入一个（批收尾结算：资源 sweep + brief，**无编译**；统一编译在 i2h-execute Base-7）。

**BATCH_MAX 宿主表**（与后台派发参数对应）：
- Codex = 20（目标区间 [12,20]，`run_in_background`，默认即后台）
- Codex = 8（目标区间 [6,8]，后台参数待确认→按同步）
- DevEco Code = 10（目标区间 [8,10]，`background: true`，默认可用）

```markdown
# UI Conversion Plan

## Context
- Source: spec/baseline/ui-manifest.md
- Style: <style_set 值，none 或具体风格名>
- Total pages: <总页面数>
- Batches: <批次数>

## Batch 1: P0 Core Pages

| 序号 | 页面 | iOS 来源 | owning_slice |
|------|------|---------|--------------|
| 0001 | HomeView | HomeView.swift | F001 |
| 0002 | FeedView | FeedView.swift | F002 |
| 0003 | ProfileView | ProfileView.swift | F003 |

结算检查点: Batch 1 完成后（batch closer 结算 → brief，见 i2h-execute §3b）

## Batch 2: P0 Detail Views

| 序号 | 页面 | iOS 来源 | owning_slice |
|------|------|---------|--------------|
| 0004 | DetailView | DetailView.swift | F004 |
| 0005 | SettingsView | SettingsView.swift | F005 |
| 0006 | SearchView | SearchView.swift | F006 |

结算检查点: Batch 2 完成后（同上）

## Batch 3: P1 Secondary

| 序号 | 页面 | iOS 来源 | owning_slice |
|------|------|---------|--------------|
| 0007 | LoginViewController | LoginViewController.swift | F007 |
| 0008 | AboutView | AboutView.swift | F008 |

结算检查点: Batch 3 完成后

## Batch N: P2 Low Priority

| 序号 | 页面 | iOS 来源 | owning_slice |
|------|------|---------|--------------|
| 00XX | AboutView ⚠️low | AboutView.swift | F0NN |

`owning_slice` 列填**裸 F-ID**（如 `F001`），从 `feature-index.md` 的 feature→涉及页面 映射推导。**必须是裸 F-ID 而非「Slice N」**（`^F\d{3}$` 契约；Slice↔F-ID 1:1，编号见 feature-plan 索引）。converter 据此 + §7 接线归属映射，为 forward-ref 钩子算 `resolve_by`。

**归属消歧**（按序机械判定，禁 LLM 自由裁量）：
1. 恰一 feature 声明 → 归它（常态）
2. 零声明 → 取 `page_NNNN.md` 关联功能；再无 → 归拓扑最早在其 spec「## 对接点」段 / `wires` 中引用它的 feature；**仍无主 → 阻断**（spec 缺口，回补 feature-index，禁止硬猜掩盖）
3. 多 claim → 归**拓扑最早者**（= 文件创建者 = 单写者），其余 feature 对自己的 handler 走 cross_slice_edit
4. hub/壳容器页 → 覆盖优先，按 SKILL Step 5「隐式关系兜底」（归最早承载任一 Tab 的切片）

> 执行者：本链由主线程编排 P0（kernel）判定，ui-plan writer 只抄结果表（SKILL §3.0）；单线程降级时由生成者自判，规则同此。

结算检查点: Batch N 完成后 + Stage 1 统一收口（入口装配 → 骨架审计，无编译，i2h-execute §3d；编译在 Base-7）

## Summary
- P0 pages: X (Batch 1-2)
- P1 pages: Y (Batch 3-4)
- P2 pages: Z (Batch 5+)
- ⚠️ Low confidence: W pages（W=0 时省略本行）
```

---

## iOS 特定说明

### 页面类型识别

| iOS 类型 | 示例 | ArkTS 产出路径 |
|---------|------|---------------|
| SwiftUI View | `HomeView.swift` | `pages/HomeView/Index.ets` |
| UIKit ViewController | `HomeViewController.swift` | `pages/HomeViewController/Index.ets` |
| Container View | `TabBarController.swift` | `pages/MainContainer/Index.ets` |
| Navigation Controller | `NavigationController.swift` | 通常不单独转换，逻辑并入页面 |

### 命名规范

**iOS → ArkTS 映射**：
- `HomeView.swift` → `pages/HomeView/Index.ets`
- `HomeViewController.swift` → `pages/HomeViewController/Index.ets`
- `MainTabBarController.swift` → `pages/MainContainer/Index.ets`

**保留原名**：页面名称保持与 iOS 源码一致，便于追溯。

### SwiftUI vs UIKit 混合项目

**分批策略**：
- SwiftUI Views：优先转换（相对简单，fact-tree 支持好）
- UIKit ViewControllers：后续批次（需要更多手工调整）
- 混合容器（hosting controller）：跟随主要内容类型

**批次分配示例**：
```markdown
## Batch 1: SwiftUI Core Views (P0)
| 序号 | 页面 | iOS 来源 | owning_slice |
|------|------|---------|--------------|
| 0001 | HomeView | HomeView.swift | F001 |
| 0002 | FeedView | FeedView.swift | F001 |

## Batch 2: UIKit Core ViewControllers (P0)
| 序号 | 页面 | iOS 来源 | owning_slice |
|------|------|---------|--------------|
| 0003 | ProfileViewController | ProfileViewController.swift | F002 |
| 0004 | SettingsViewController | SettingsViewController.swift | F003 |
```

### Confidence 特殊标记

**Low confidence 场景**（需标 ⚠️low）：
- 使用了自定义 UIView 子类，无法自动推断布局
- 复杂的 Auto Layout 约束，需要人工验证
- 大量使用 UIViewController containment
- XIB/Storyboard 文件，缺少布局元数据
- 第三方 UI 组件库（如 SnapKit、Masonry）

**标记示例**：
```markdown
| 0010 | CustomChartView ⚠️low | CustomChartView.swift | F008 |
```

### 导航模式映射

| iOS 导航模式 | HarmonyOS 对应 | 处理方式 |
|-------------|---------------|---------|
| NavigationView / NavigationStack | Navigation | 逻辑并入页面，路由统一管理 |
| TabView / UITabBarController | Tabs + BarPosition.End | 转为 MainContainer + Tab 切换 |
| Sheet / .sheet() | BindSheet | 模态弹窗 |
| FullScreenCover | Navigation.pushPath | 全屏跳转 |
| UINavigationController.push | Navigation.pushPath | 压栈导航 |
| present (modal) | BindSheet / BindContentCover | 模态展示 |

### 容器页面处理

**TabBarController → MainContainer**：
```markdown
| 0001 | MainContainer | MainTabBarController.swift | F001 |
```

**说明**：
- 容器页本身归属第一个 Tab 的 feature
- 各 Tab 内容页归属各自的 feature
- 容器页在 `wires` 中记录嵌入关系

### 优先级分配建议

**P0（核心页面）**：
- 应用入口页（如 HomeView、MainTabBarController）
- 核心业务流程页面（如列表、详情、购物车、订单）
- 登录/注册页面

**P1（重要页面）**：
- 个人中心、设置
- 搜索、筛选
- 次要业务流程

**P2（低优先级）**：
- 关于页面、帮助文档
- 调试工具页面
- 第三方服务集成页面

---

## 必填字段规则

### 表格必填列

1. **序号**：4 位数字，从 0001 开始递增
2. **页面**：ArkTS 页面名称（保持与 iOS 源码名称一致）
3. **iOS 来源**：源文件路径（相对于项目根目录）
4. **owning_slice**：归属的 Feature ID（裸 F-ID，如 F001）

### Context 必填字段

- **Source**: 固定为 `spec/baseline/ui-manifest.md`
- **Style**: style_set 值（none 或具体风格名）
- **Total pages**: 总页面数
- **Batches**: 批次数

### Summary 必填字段

- **P0 pages**: P0 页面数量 + 批次范围
- **P1 pages**: P1 页面数量 + 批次范围
- **P2 pages**: P2 页面数量 + 批次范围（如有）
- **⚠️ Low confidence**: 低置信度页面数量（0 时省略）

---

## 常见错误和注意事项

### ❌ 错误示例 1：使用 Slice 编号而非 F-ID

```markdown
| 0001 | HomeView | HomeView.swift | Slice 01 |  ❌ 错误
```

**正确**：
```markdown
| 0001 | HomeView | HomeView.swift | F001 |  ✅ 正确
```

### ❌ 错误示例 2：添加 confidence 列

```markdown
| 序号 | 页面 | iOS 来源 | confidence | owning_slice |  ❌ 不应有 confidence 列
```

**正确**：
```markdown
| 序号 | 页面 | iOS 来源 | owning_slice |  ✅ 正确
```

（confidence: low 的页面在页面名后标 ⚠️low）

### ❌ 错误示例 3：size-1 批次

```markdown
## Batch 5: P2 About
| 0008 | AboutView | AboutView.swift | F008 |  ❌ 单页批次
```

**正确**：应并入前一批次末尾

### ❌ 错误示例 4：按依赖关系排序

**错误思路**：DetailView 依赖 ListView，所以 ListView 要排在前面

**正确做法**：按优先级和 confidence 排序，依赖关系由 FWD-REF 机制兜底

### ⚠️ 注意事项

1. **不要省略结算检查点**：每个 Batch 末尾必须有结算检查点说明
2. **保持表格对齐**：使用合适的列宽，便于阅读
3. **iOS 来源路径**：使用相对路径，从项目根目录开始
4. **owning_slice 一致性**：确保与 feature-index.md 中的 F-ID 一致

---

## 完整示例（iOS 项目）

```markdown
# UI Conversion Plan

## Context
- Source: spec/baseline/ui-manifest.md
- Style: none
- Total pages: 8
- Batches: 2

## Batch 1: P0 Core Views

| 序号 | 页面 | iOS 来源 | owning_slice |
|------|------|---------|--------------|
| 0001 | MainContainer | App/MainTabBarController.swift | F001 |
| 0002 | HomeView | App/Views/HomeView.swift | F001 |
| 0003 | BeanListView | App/Views/BeanListView.swift | F001 |
| 0004 | BeanDetailView | App/Views/BeanDetailView.swift | F001 |
| 0005 | BrewHistoryView | App/Views/BrewHistoryView.swift | F002 |

结算检查点: Batch 1 完成后（batch closer 结算 → brief，见 i2h-execute §3b）

## Batch 2: P1 Secondary + Settings

| 序号 | 页面 | iOS 来源 | owning_slice |
|------|------|---------|--------------|
| 0006 | SettingsView | App/Views/SettingsView.swift | F003 |
| 0007 | ProfileView | App/Views/ProfileView.swift | F004 |
| 0008 | AboutView ⚠️low | App/Views/AboutView.swift | F004 |

结算检查点: Batch 2 完成后 + Stage 1 统一收口（入口装配 → 骨架审计，无编译，i2h-execute §3d；编译在 Base-7）

## Summary
- P0 pages: 5 (Batch 1)
- P1 pages: 3 (Batch 2)
- ⚠️ Low confidence: 1 pages
```

---

## 模板版本

**版本**: v1.0  
**适配平台**: iOS → HarmonyOS  
**基于**: Android a2h-plan ui-plan-template.md  
**最后更新**: 2024-11-03
