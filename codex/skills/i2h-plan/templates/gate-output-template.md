<!-- when: 双计划生成完成、向用户输出审批门控摘要时加载 -->
<!-- topics: 门控, 审批摘要, Placeholder Registry, briefs 落点 -->

# 双计划审批门控输出模板（§8）

双计划生成后输出以下摘要；默认无人值守按 [i2h-spec gate-handling.md](../../i2h-spec/references/gate-handling.md) §5 自动确认后进入 i2h-execute，用户要求逐个确认时等人工审批。

```
## 双计划生成完成

### UI 转换计划 (ui-plan.md)
- 总页面: X 个
- 批次: Y 个 Batch
- ⚠️ Low confidence 页面: W 个（W=0 时省略本行）

### 功能执行计划 (feature-plan.md, plan_format: indexed-v1)
- Base 层任务: N 个 / M 组
- Feature Slices: N 个（slice 文件在 plans/slices/）
- 可并行组: M 组（size-1 组非 0 时附理由）

### 覆盖率
- P0 功能: 100% ✓
- P1 功能: XX%
- UI 页面: XX%

### Placeholder Registry
- 写入位置: spec/placeholder-registry.md（plan 期占位**直接写入**，无 coverage-matrix 中转）
- 总条目: N（全部 status=registered；执行期铸号遵守 _common.md §2.1c 发号协议，登记即占号）

### 骨架审计预演（仅 WARN）
- placeholder 密度 ≥ 5/file 的文件: K 个
- 建议: <列表 / 或 "无"，K=0 时显示无>

### Execute 阶段 brief 落点
- spec/execution/briefs/（由 i2h-execute 启动时自建，填充 batch_NN / stage2 / group_NN brief）

### grill #2 决策清单（追加至 spec/decision-ledger.md）
- 新增 D 编号决策: N 条（C6–C11 / C13–C14 / C17 类目）
- **默认原则确认表**（C6 / C8 无鸿蒙对等残余项，默认阻断；每行改判为 降级 / 留桩 / 砍 / 换 后 [1] 才可选）
  | # | 类目 | 实例 | 默认裁定 | 可改为 |
  |---|---|---|---|---|
- 三方 SDK 策略覆盖率: 100% ✓（所有 thirdparty-sdk placeholder 有对应 C8 决策）
- Gate A 级架构决策覆盖率: 100% ✓（所有 complex Slice 有对应 C7 决策）
- Plan 待修订项: K 条（execute 阶段将按 ledger 覆盖 plan 原文）
- escape 候选: J 条（待 retrospect 评审）

请审阅 spec/baseline/plans/、spec/placeholder-registry.md、**spec/decision-ledger.md**，确认后执行 i2h-execute。

可调整项:
- 调整 Batch 分组或页面排序
- 调整 Slice 执行顺序或并行组
- 修改 suggested_skills
- 增删 Slice 或 Base 任务
- 移动页面到不同 Batch
- **修订 ledger 中的 D 编号决策**（修订后 Plan 待修订项段需同步更新）
```

用户可以：
- 直接确认 → 进入 i2h-execute（execute 按 ledger 查表执行，不再交互式追问）
- 修改后确认 → 进入 i2h-execute
- 要求重新生成 → i2h-plan 重新执行

---

## iOS 特定说明

### iOS 项目审批关注点

#### UI 转换计划审查

**SwiftUI 项目**：
- 检查是否所有 SwiftUI View 都已覆盖
- 确认复杂的 View（使用 GeometryReader、PreferenceKey）是否标记为 low confidence
- 验证 @State/@Binding 依赖关系是否清晰

**UIKit 项目**：
- 检查是否所有 ViewController 都已覆盖
- 确认使用了 XIB/Storyboard 的页面是否标记为 low confidence
- 验证复杂的 Auto Layout 约束是否需要人工审查

**混合项目**：
- 确认 SwiftUI 和 UIKit 混合容器（UIHostingController）的处理策略
- 验证导航衔接（SwiftUI NavigationView + UIKit UINavigationController）

#### 功能执行计划审查

**Base 层检查**：
- Base-2 (Database): CoreData/SwiftData 迁移策略是否合理
- Base-3 (Network): URLSession/Alamofire 封装是否足够
- Base-5 (Preferences): UserDefaults/@AppStorage 迁移是否完整
- Base-6 (公共组件): 是否包含所有共享的自定义 View/Component

**Slice 分组检查**：
- 依赖关系是否正确（特别是数据层依赖）
- 并行组是否合理（避免过度并行导致资源竞争）

#### Placeholder Registry 审查

**三方 SDK 策略**：
- 微信 SDK、支付宝 SDK：是否有明确的迁移方案
- Firebase、统计 SDK：是否有替代方案或记账决策
- 地图 SDK（高德、百度）：是否有适配计划

**Forward-ref 合理性**：
- 跨 Slice 引用是否必要（能否通过调整 Slice 顺序避免）
- resolve_by 归属是否正确

**Uncertain 区域**：
- 不确定区域是否真的需要二次确认
- 是否可以在 plan 阶段就确定下来

### 完整示例（iOS 咖啡记录应用）

```
## 双计划生成完成

### UI 转换计划 (ui-plan.md)
- 总页面: 7 个
- 批次: 2 个 Batch
  - Batch 1: 5 个 SwiftUI Views（P0）
  - Batch 2: 2 个 SwiftUI Views（P1）

### 功能执行计划 (feature-plan.md, plan_format: indexed-v1)
- Base 层任务: 8 个 / 4 组
  - Base-1 (Models): SwiftData 模型定义
  - Base-2 (Database): SwiftData → RelationalStore
  - Base-6 (公共组件): 自定义 SwiftUI 组件
  - Base-7 (编译检查点)
- Feature Slices: 4 个（slice 文件在 plans/slices/）
  - Slice 1: 咖啡豆管理 (F001)
  - Slice 2: 冲煮记录 (F002)
  - Slice 3: 数据统计 (F003)
  - Slice 4: 用户偏好 (F004)
- 可并行组: 2 组
  - Group 1: 3 个 Slices（F001, F002, F004）并行
  - Group 2: 1 个 Slice（F003）串行（依赖 F001, F002）

### 覆盖率
- P0 功能: 2/2 (100%) ✓
- P1 功能: 2/2 (100%) ✓
- UI 页面: 7/7 (100%) ✓

### Placeholder Registry
- 写入位置: spec/placeholder-registry.md
- 总条目: 0（纯离线 SwiftData 应用，无三方 SDK，无占位）

### 骨架审计预演（仅 WARN）
- placeholder 密度 ≥ 5/file 的文件: 0 个
- 建议: 无

### Execute 阶段 brief 落点
- spec/execution/briefs/（由 i2h-execute 启动时自建）

### grill #2 决策清单
- 新增 D 编号决策: 0 条（纯 SwiftUI + SwiftData，技术栈清晰，无需额外决策）
- 三方 SDK 策略覆盖率: N/A（无三方 SDK）
- Gate A 级架构决策覆盖率: 100% ✓（所有 Slice 为 simple，无需 C7 决策）
- Plan 待修订项: 0 条
- escape 候选: 0 条

请审阅 spec/baseline/plans/、spec/placeholder-registry.md，确认后执行 i2h-execute。

可调整项:
- ✅ Batch 分组合理（SwiftUI simple views，可并行）
- ✅ Slice 执行顺序合理（F003 依赖 F001/F002）
- ✅ Base 层任务完整（Models、Database、公共组件、编译）
- ⚠️ 如需调整 SwiftData 迁移策略，可修改 Base-2 任务
```

### 常见调整场景

#### 场景 1：调整 Batch 分组

**原因**：发现某些页面之间有强依赖关系，希望同批处理

**操作**：
1. 修改 `spec/baseline/plans/ui-plan.md`
2. 调整 Batch 表格中的页面分配
3. 重新运行 coverage 校验

#### 场景 2：调整 Slice 并行组

**原因**：发现某些 Slice 之间有隐式依赖，需要串行执行

**操作**：
1. 修改 `spec/baseline/plans/feature-plan.md` 索引
2. 调整 Slice 的 `parallel_group` 编号
3. 同步更新对应的 slice 文件头部
4. 重新运行分组校验

#### 场景 3：添加三方 SDK 决策

**原因**：plan 阶段识别出未覆盖的三方 SDK，需要补充决策

**操作**：
1. 在 `spec/decision-ledger.md` 添加 D 编号决策
2. 选择策略：降级 / 留桩 / 砍 / 换
3. 更新 `spec/placeholder-registry.md` 的对应条目
4. 重新运行 placeholder 校验

#### 场景 4：修改 Base 层任务

**原因**：发现某些 Base 层能力缺失或冗余

**操作**：
1. 修改 `spec/baseline/plans/base-plan.md`
2. 添加/删除/修改 Base 任务
3. 调整 `parallel_group` 分配
4. 重新运行 Base 层校验

### 审批决策流程

```
生成双计划
  ↓
输出审批摘要
  ↓
用户审阅
  ↓
  ├─ 直接确认 → 进入 i2h-execute
  ├─ 修改后确认 → 重新校验 → 进入 i2h-execute
  └─ 要求重新生成 → 返回 i2h-plan
```

### 无人值守模式

**默认行为**（无用户交互）：
1. 自动执行所有校验
2. 如果全部通过 → 自动确认，进入 i2h-execute
3. 如果有阻断性问题 → 停止，输出错误报告

**触发条件**：
- 用户未明确要求逐个确认
- 覆盖率全部达标
- 无 blocking findings
- Placeholder 白名单 100%

### 用户确认模式

**触发条件**：
- 用户明确要求审批每个阶段
- 存在 low confidence 页面
- 存在复杂 Slice（complexity: complex）
- 存在三方 SDK 占位

**确认内容**：
1. UI Plan：页面分批是否合理
2. Feature Plan：Slice 执行顺序是否合理
3. Placeholder：占位策略是否可接受
4. Decision Ledger：技术决策是否认可

---

## 模板版本

**版本**: v1.0  
**适配平台**: iOS → HarmonyOS  
**基于**: Android a2h-plan gate-output-template.md  
**最后更新**: 2024-11-03
