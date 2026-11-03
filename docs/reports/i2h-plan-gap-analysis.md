# i2h-plan 差距分析报告

**基于**: tool-optimization 方法论  
**对比版本**: Android a2h-plan (hmigbot-1.8.0) vs iOS i2h-plan (当前)  
**生成时间**: 2024-11-03  
**分析者**: Claude Opus 5.5

---

## 执行摘要

### 核心差异统计

| 维度 | Android 原版 | iOS 当前版 | 差距 |
|------|-------------|-----------|------|
| SKILL.md 行数 | 491 行 | 351 行 | -28% |
| Templates 数量 | 6 个 | 0 个 | -100% ❌ |
| References 数量 | 3 个 | 0 个 | -100% ❌ |
| 产物文件数 | 5+ 个 | 3 个 | -40% ❌ |
| 架构复杂度 | indexed-v1 (3层) | flat (1层) | 严重简化 ❌ |

### 严重程度分布

- 🔴 **P0（致命）**: 8 项 — 缺失核心产物和机制
- 🟡 **P1（重要）**: 12 项 — 影响质量和下游消费
- 🟢 **P2（可选）**: 5 项 — 优化改进

---

## 1. 架构层面差异

### 1.1 产物架构 🔴 P0

| 方面 | Android 原版 | iOS 当前版 | 影响 |
|------|-------------|-----------|------|
| **计划格式** | indexed-v1 (三层架构) | flat (单层) | 🔴 致命 |
| **Base 层** | 独立文件 base-plan.md | ❌ 不存在 | 🔴 致命 |
| **Slice 文件** | plans/slices/*.md | ❌ 不存在 | 🔴 致命 |
| **覆盖率矩阵** | coverage-matrix.md | ❌ 不存在 | 🔴 致命 |
| **占位注册表** | placeholder-registry.md | ❌ 不存在 | 🔴 致命 |

**Android 原版架构**：
```
spec/baseline/plans/
├── ui-plan.md              # L1: UI 批次调度
├── feature-plan.md         # L1: 功能索引 (plan_format: indexed-v1)
├── base-plan.md            # L2: Base 层任务正文
├── slices/                 # L2: 逐 slice 只读调度账本
│   ├── slice-01-F001.md
│   ├── slice-02-F002.md
│   └── ...
└── coverage-matrix.md      # 覆盖率校验
spec/placeholder-registry.md # 占位唯一写入位
```

**iOS 当前版架构**（过度简化）：
```
spec/baseline/plans/
├── ui-plan.json            # ❌ 应该是 .md
├── feature-plan.json       # ❌ 应该是 .md + slices/
└── execution-summary.md    # ⚠️ 不在原版中
```

**根本问题**：
1. ❌ 使用 JSON 而非 Markdown（违反原版设计）
2. ❌ 缺少 indexed-v1 三层架构
3. ❌ 缺少 Base 层独立产物
4. ❌ 缺少 Slice 文件（调度账本）
5. ❌ 缺少覆盖率校验机制

### 1.2 执行编排 🔴 P0

| 方面 | Android 原版 | iOS 当前版 | 影响 |
|------|-------------|-----------|------|
| **Subagent 派发** | P0/P1/P2 三段编排 | ❌ 无 | 🔴 致命 |
| **单写者分配** | A→ui-plan, B→base-plan, C→slices | ❌ 无 | 🔴 致命 |
| **降级方案** | 主线程按序自跑 | ❌ 无 | 🟡 重要 |

**Android 原版编排**（§3.0）：
- P0: 主线程执行内核裁决（归属、定号、hub、横切）
- P1: 三个 subagent 并行生成（A=ui-plan, B=base-plan, C=slices+registry）
- P2: 主线程收拢（定组、FV、coverage、grill、审批）

**iOS 当前版**：
- 全部在主线程，无派发机制
- 无单写者纪律

---

## 2. 产物层面差异

### 2.1 UI Plan 🟡 P1

| 字段/特性 | Android 原版 | iOS 当前版 | 状态 |
|----------|-------------|-----------|------|
| **格式** | Markdown | JSON | ❌ 错误 |
| **owning_slice** | ✅ 每页标注 F-ID | ❌ 无 | 🔴 致命 |
| **批次分配** | ceil(页数÷BATCH_MAX) 均分 | 简单分组 | 🟡 可改进 |
| **依赖处理** | FWD-REF 兜底，无需排序 | ❌ 不清晰 | 🟡 重要 |
| **并行标注** | 批内默认全并行 | parallel: true | ✅ 类似 |
| **confidence 展示** | low 页行内标 ⚠️ | 单独列 | 🟢 可接受 |

**关键缺失**：
1. ❌ **owning_slice 列**：每个页面必须标注归属哪个 Feature Slice（F001/F002...）
2. ❌ **Markdown 格式**：应该用表格，不是 JSON
3. ❌ **converter 字段**：应指定使用的转换器

**示例对比**：

**Android 原版**（ui-plan.md）：
```markdown
| 序号 | Android | ArkTS 产出 | 优先级 | owning_slice | 说明 |
|------|---------|-----------|--------|--------------|------|
| 0001 | MainActivity | pages/MainActivity/Index.ets | P0 | F001 | Activity 入口 |
| 0003 | Feed | pages/Feed/Index.ets | P0 | F001 | 零食浏览主页 |
```

**iOS 当前版**（ui-plan.json）：
```json
{
  "pages": [
    {
      "page_id": "page_0001",
      "name": "HomeView",
      "file": "App/Views/HomeView.swift",
      "output": "pages/HomeView.ets",
      "estimated_minutes": 3,
      "converter": "swiftui-template"
    }
  ]
}
```

### 2.2 Feature Plan 🔴 P0

| 字段/特性 | Android 原版 | iOS 当前版 | 状态 |
|----------|-------------|-----------|------|
| **格式** | Markdown (indexed-v1) | JSON | ❌ 错误 |
| **Base 层** | 独立 base-plan.md | ❌ 无 | 🔴 致命 |
| **Slice 文件** | plans/slices/*.md | ❌ 无 | 🔴 致命 |
| **plan_format** | indexed-v1 | ❌ 无 | 🔴 致命 |
| **接线账本** | wires 结构化字段 | ❌ 无 | 🔴 致命 |
| **对接点指针** | integration_points_ref | ❌ 无 | 🔴 致命 |
| **源码锚点** | android_source_anchors_ref | ❌ 无 | 🔴 致命 |
| **跨切片编辑** | cross_slice_edits | ❌ 无 | 🔴 致命 |
| **组件嵌入** | wires embed 条目 | ❌ 无 | 🔴 致命 |

**Android 原版结构**：

**feature-plan.md**（L1 索引）：
```yaml
plan_format: indexed-v1
```
```markdown
## Base 层
**任务数**: 8
**Detail**: spec/baseline/plans/base-plan.md

## Group 1
### Slice 01: F001 零食浏览与详情
**Detail**: spec/baseline/plans/slices/slice-01-F001.md
```

**base-plan.md**（L2 Base 层正文）：
```markdown
## Base-1: Models
**suggested_skills**: arkts-data-model
**input**: spec/baseline/feature-base.md § 数据模型
**blocking**: 是
**parallel_group**: 1
**scope**: Snack, SnackCollection, Filter...
```

**slice-01-F001.md**（L2 Slice 调度账本）：
```yaml
feature_id: F001
parallel_group: 1
complexity: simple
depends_on: [base]
```
```markdown
## Integration Points
integration_points_ref: spec/baseline/features/F001*.md#对接点

## Wires（接线账本）
### VM 入边
- page: Feed, viewmodel: null

### 组件嵌入入边
- page: MainContainer, slot: contentArea, embed: Feed(), resolve_by: slice-01-F001

## Tasks
### Step 3a: UI 补充
**suggested_skills**: a2h-activity-converter
**input**: spec/baseline/ui/page_0001~0003.md
```

**iOS 当前版**（feature-plan.json）：
```json
{
  "execution_order": [
    {
      "group_id": "FEAT_G1",
      "features": [
        {
          "feature_id": "F001",
          "estimated_minutes": 60,
          "dependencies": [],
          "output": ["services/DataStore.ets"]
        }
      ]
    }
  ]
}
```

**根本问题**：
1. ❌ 完全扁平化，丢失 indexed-v1 三层架构
2. ❌ 无 Base 层独立产物
3. ❌ 无 Slice 文件（调度账本）
4. ❌ 无接线账本（wires、cross_slice_edits、integration_points_ref）
5. ❌ 无源码锚点引用
6. ❌ 无 suggested_skills 标注规则

### 2.3 Base 层产物 🔴 P0

**Android 原版**：base-plan.md（110 行）
- Base-0: 资源前置（全 spec 资源 ID 全集）
- Base-1: Models（数据模型）
- Base-2: Repository（数据仓库）
- Base-3: Network（网络层）
- Base-4: Events（事件系统）
- Base-5: Preferences（偏好设置）
- Base-6: 公共组件库
- Base-7: 工程级编译检查点

每个任务包含：
- suggested_skills
- input（指向 spec 段落）
- blocking（是否阻断）
- parallel_group（组号）
- scope（详细范围）

**iOS 当前版**：❌ 完全缺失

**影响**：
- 🔴 下游 a2h-execute 无法知道 Base 层任务
- 🔴 Base-0 资源前置无法执行
- 🔴 Base-7 编译检查点缺失

### 2.4 Slice 文件 🔴 P0

**Android 原版**：plans/slices/slice-NN-<fid>.md
- YAML 头部（feature_id, priority, complexity, parallel_group, depends_on）
- Integration Points（integration_points_ref 指针）
- Wires（结构化接线账本）
  - VM 入边（page + viewmodel）
  - 组件嵌入入边（page + slot + embed + resolve_by）
- Modifies Files（跨切片编辑清单）
- Tasks（4 步：UI补充、ViewModel、数据层、接线）

**iOS 当前版**：❌ 完全缺失

**影响**：
- 🔴 下游 a2h-execute 无法按 Slice 执行
- 🔴 接线关系无法追溯
- 🔴 跨切片编辑无法管理
- 🔴 无法机械校验完成性

### 2.5 覆盖率矩阵 🔴 P0

**Android 原版**：coverage-matrix.md
- P0/P1/P2 功能覆盖率
- UI 页面覆盖率
- Placeholder 完整性校验
- Complex Slice anchor 校验
- 对接点归属率
- 组件嵌入归属率
- 数据链路层扇出校验

**iOS 当前版**：❌ 完全缺失

**影响**：
- 🔴 无法保证功能 100% 覆盖
- 🔴 无法校验 placeholder 白名单
- 🔴 无法校验接线归属
- 🔴 质量保证缺失

### 2.6 Placeholder 注册表 🔴 P0

**Android 原版**：spec/placeholder-registry.md
- 占位唯一写入位
- P-ID 格式：P-S{N}-{seq} / P-B{N}-{seq}
- kind: thirdparty-sdk / forward-ref
- trigger_condition 白名单
- resolve_by 字段

**iOS 当前版**：❌ 完全缺失

**影响**：
- 🔴 三方 SDK 占位无法管理
- 🔴 forward-ref 机制无法工作
- 🔴 下游 a2h-execute 无法识别占位

---

## 3. 流程层面差异

### 3.1 启动检查 🟡 P1

| 检查项 | Android 原版 | iOS 当前版 | 状态 |
|--------|-------------|-----------|------|
| **open-findings** | ✅ 完整处理 | ❌ 无 | 🔴 致命 |
| **ui-coverage-report** | ✅ HARD-GATE | ❌ 无 | 🔴 致命 |
| **spec 就绪检查** | ✅ 完整 | ✅ 简单 | 🟡 可改进 |
| **contract_mode** | ✅ 支持 | ❌ 无 | 🟢 暂不需要 |

**Android 原版**（§启动检查）：
1. 读取 open-findings.json，处理待办 findings
2. 检查 ui-coverage-report.md 是否 PASS
3. 检查 spec/baseline/ 就绪
4. 检查 contract_mode

**iOS 当前版**：
1. 简单检查 spec 产出物存在

### 3.2 拓扑排序 🟡 P1

| 方面 | Android 原版 | iOS 当前版 | 状态 |
|------|-------------|-----------|------|
| **依赖来源** | feature-index 排序依赖列 | ✅ 类似 | ✅ 正确 |
| **循环检测** | ✅ 完整 | ✅ 有 | ✅ 正确 |
| **多子仓支持** | ✅ module-dep-graph | ❌ 无 | 🟢 暂不需要 |
| **并行组分配** | ✅ 复杂规则 | ✅ 简单 | 🟡 可改进 |

**Android 原版规则**（§3b Step 5）：
- 组容量上限：GROUP_HARD_LIMIT = 8
- size-1 组禁止（需并组或附挂）
- 共享容器页（hub）归最早 Tab 切片
- 横切切片（埋点/遥测）排最末组
- 附挂不计入组内 slice 数

**iOS 当前版**：
- 简单按依赖关系分组
- 无组容量限制
- 无 hub/横切特殊处理

### 3.3 suggested_skills 标注 🔴 P0

| 方面 | Android 原版 | iOS 当前版 | 状态 |
|------|-------------|-----------|------|
| **规则文档** | references/skill-binding-rules.md | ❌ 无 | 🔴 致命 |
| **三层承载** | Base/Slice默认/Slice差异化 | ❌ 无 | 🔴 致命 |
| **领域映射** | 30+ 领域条目 | ❌ 无 | 🔴 致命 |
| **SDK 处理** | 四判据 + registry | ❌ 无 | 🔴 致命 |

**Android 原版**（§4）：
- 完整的 task→skill 映射表
- 三层承载字段：
  1. Base/FV 任务 → suggested_skills
  2. Slice 4 步默认 → 权威=表格
  3. per-slice 差异化 → suggested_skills+（delta-only）
- 三方 SDK 四判据（ledger前置→skill映射→registry→白名单）

**iOS 当前版**：
- ❌ 无规则文档
- ❌ 无 suggested_skills 字段
- ❌ 无 SDK 处理机制

### 3.4 接线点提取 🔴 P0

**Android 原版**（§3b Step 4.2）：
- integration_points_ref 指针（零复制）
- wires 统一接线账本
  - VM 入边（page + viewmodel）
  - 组件嵌入入边（page + slot + embed + resolve_by）
- modifies_files（本 Slice 需回改的他切片文件）
- cross_slice_edits（跨切片编辑子集）

**iOS 当前版**：❌ 完全缺失

**影响**：
- 🔴 UI 和功能层对接关系不清晰
- 🔴 跨切片编辑无法管理
- 🔴 组件嵌入关系无法追溯

### 3.5 Final Verification 🔴 P0

**Android 原版**（§3b Step 6）：
- FV-1: Final Structural Closure
  - suggested_skills: arkts-structural-closure (pipeline 模式)
  - acceptance: final_state == PASS
- FV-2: 终态全量编译
  - suggested_skills: hmos-builder (agent)
  - acceptance: 编译 exit 0

**iOS 当前版**：❌ 完全缺失

**影响**：
- 🔴 无结构完整性兜底
- 🔴 无终态编译保证

---

## 4. 模板和 References 差异

### 4.1 Templates 🔴 P0

| 模板 | Android 原版 | iOS 当前版 | 状态 |
|------|-------------|-----------|------|
| ui-plan-template.md | ✅ 3601 字节 | ❌ 无 | 🔴 致命 |
| feature-plan-template.md | ✅ 8680 字节 | ❌ 无 | 🔴 致命 |
| slice-plan-template.md | ✅ 4406 字节 | ❌ 无 | 🔴 致命 |
| coverage-matrix-template.md | ✅ 4150 字节 | ❌ 无 | 🔴 致命 |
| placeholder-registry-template.md | ✅ 13521 字节 | ❌ 无 | 🔴 致命 |
| gate-output-template.md | ✅ 2687 字节 | ❌ 无 | 🟡 重要 |

**影响**：
- 🔴 无法保证产物格式一致
- 🔴 LLM 无详细示例指导
- 🔴 必填字段无法强制

### 4.2 References 🔴 P0

| Reference | Android 原版 | iOS 当前版 | 状态 |
|----------|-------------|-----------|------|
| skill-binding-rules.md | ✅ 9869 字节 | ❌ 无 | 🔴 致命 |
| plan-dispatch.md | ✅ 4067 字节 | ❌ 无 | 🔴 致命 |
| grill-2-decision-gates.md | ✅ 11471 字节 | ❌ 无 | 🟡 重要 |

**影响**：
- 🔴 无 suggested_skills 标注规则
- 🔴 无派发机制说明
- 🔴 无审批决策规则

---

## 5. 质量保证差异

### 5.1 覆盖率校验 🔴 P0

**Android 原版**（§7，12 项校验）：
1. P0 功能覆盖率 = 100%
2. UI 页面覆盖率 = 100%
3. Placeholder trigger 白名单率 = 100%
4. Complex Slice anchor 完整率 = 100%
5. 对接点归属率 = 100%
6. 组件嵌入归属率 = 100%
7. 数据链路层扇出完整率 = 100%
8. 分层校验 5 项
9. 功能分组校验
10. 骨架审计预演
11. 跨切片接线归属检测
12. 依赖关系验证

**iOS 当前版**：
- ✅ 简单的功能覆盖检查
- ❌ 无其他 11 项校验

### 5.2 门禁机制 🔴 P0

**Android 原版**：
- HARD-GATE 标注
- findings 分类处理
- 阈值强制（见§7表格）
- gate-handling.md 引用

**iOS 当前版**：
- ❌ 无 HARD-GATE 机制
- ❌ 无 findings 处理
- ❌ 无阈值校验

---

## 6. 关键概念差异

### 6.1 indexed-v1 架构 🔴 P0

**Android 原版核心设计**：
- L1: 索引层（feature-plan.md）— 轻量级调度表
- L2: 详情层（base-plan.md + slices/*.md）— 完整任务账本
- 好处：
  1. 索引小，易于人类阅读
  2. 详情分文件，便于机械消费
  3. 单写者纪律，避免冲突
  4. 只读态，避免状态污染

**iOS 当前版**：
- 扁平 JSON，全部内容在一个文件
- 缺失 indexed-v1 的所有优点

### 6.2 接线账本 (Wires) 🔴 P0

**Android 原版设计理念**：
- 接线是关键集成工作
- 必须结构化追溯
- VM 入边 + 组件嵌入入边分开管理
- resolve_by 明确归属

**iOS 当前版**：
- ❌ 无接线账本概念
- ❌ 无法追溯集成关系

### 6.3 单写者纪律 🔴 P0

**Android 原版**（§3.0 编排派发）：
- A → ui-plan.md
- B → base-plan.md
- C → plans/slices/* + placeholder-registry.md
- 主线程 → feature-plan.md 索引
- 避免并发写冲突

**iOS 当前版**：
- ❌ 无单写者分配
- ❌ 全部主线程写

### 6.4 Placeholder 白名单 🔴 P0

**Android 原版**：
- trigger_condition 必须命中白名单
- kind 限定：thirdparty-sdk / forward-ref
- forward-ref 必须含 resolve_by
- 阻断不合规占位

**iOS 当前版**：
- ❌ 无 placeholder 机制

---

## 7. 下游影响分析

### 7.1 对 i2h-execute 的影响 🔴 致命

| 缺失 | 影响 |
|------|------|
| base-plan.md | 无法执行 Base 层任务（Models、Repository、公共组件） |
| slices/*.md | 无法按 Slice 执行功能 |
| wires 账本 | 无法知道如何接线（VM 入边、组件嵌入） |
| cross_slice_edits | 无法管理跨切片编辑 |
| suggested_skills | 无法路由到正确的 Domain Skill |
| placeholder-registry | 无法处理三方 SDK 和 forward-ref |
| FV 任务 | 无结构完整性和编译兜底 |

### 7.2 对 i2h-verify 的影响 🔴 致命

| 缺失 | 影响 |
|------|------|
| coverage-matrix.md | 无法验证覆盖率 |
| integration_points_ref | 无法验证对接点完整性 |
| wires 账本 | 无法验证接线完成性 |

---

## 8. 改进建议（优先级排序）

### P0（立即修复，阻断下游）

1. **创建完整的 Templates 目录**（6 个模板）
   - ui-plan-template.md
   - feature-plan-template.md
   - slice-plan-template.md
   - coverage-matrix-template.md
   - placeholder-registry-template.md
   - gate-output-template.md

2. **创建 References 目录**（3 个 reference）
   - skill-binding-rules.md
   - plan-dispatch.md
   - grill-2-decision-gates.md

3. **重写 SKILL.md 采用 indexed-v1 架构**
   - 明确三层架构（L1 索引 + L2 详情）
   - Base 层独立产物
   - Slice 文件机制
   - 接线账本设计

4. **实现 Base 层生成**（Step 3）
   - Base-0: 资源前置
   - Base-1~6: Models/Repository/Network/Events/Preferences/公共组件
   - Base-7: 编译检查点

5. **实现 Slice 文件生成**（Step 4）
   - YAML 头部（feature_id, complexity, parallel_group, depends_on）
   - integration_points_ref 指针
   - wires 接线账本
   - modifies_files / cross_slice_edits

6. **实现覆盖率校验**（§7，12 项）
   - P0 功能覆盖率 100%
   - UI 页面覆盖率 100%
   - Placeholder 白名单率 100%
   - Complex anchor 完整率 100%
   - 对接点归属率 100%
   - 组件嵌入归属率 100%
   - 分层校验 5 项
   - 功能分组校验

7. **实现 Placeholder 注册表**
   - 三方 SDK 四判据
   - P-ID 格式规范
   - trigger_condition 白名单
   - kind / resolve_by 字段

8. **实现 FV 任务注入**（Step 6）
   - FV-1: Final Structural Closure
   - FV-2: 终态全量编译

### P1（重要，影响质量）

9. **实现 suggested_skills 标注规则**（§4）
   - 创建 skill-binding-rules.md
   - 三层承载字段
   - 30+ 领域映射表
   - SDK 处理机制

10. **实现编排派发机制**（§3.0）
    - P0/P1/P2 三段编排
    - 单写者分配
    - 降级方案

11. **完善启动检查**
    - open-findings.json 处理
    - ui-coverage-report.md HARD-GATE
    - contract_mode 检查

12. **完善并行组分配**（Step 5）
    - 组容量上限 (GROUP_HARD_LIMIT=8)
    - size-1 组处理
    - hub/横切特殊规则

13. **实现接线点提取**（Step 4.2）
    - integration_points_ref 指针
    - wires 结构化账本
    - cross_slice_edits 管理

14. **UI Plan 格式转换**
    - JSON → Markdown
    - 添加 owning_slice 列
    - 添加 converter 字段

15. **Feature Plan 格式转换**
    - JSON → Markdown (indexed-v1)
    - 索引 + 详情分离
    - plan_format 字段

16. **实现数据链路契约扇出**（Step 4.3）
    - data_chain_refs 字段
    - L0-L7 层注入

17. **完善拓扑排序**
    - 多子仓支持
    - 隐式关系兜底（hub/横切）

18. **实现骨架审计预演**
    - 同文件 ≥5 P-ID 警告

19. **创建 coverage-matrix.md**
    - Wiring Ownership Map
    - 各项覆盖率统计

20. **实现审批机制**（§8）
    - 无人值守 vs 用户确认
    - 决策记录到 decision-ledger

### P2（可选，锦上添花）

21. **支持 contract_mode**
    - legacy/shadow/v2 模式

22. **支持风格 Skills**
    - style_set 追加规则

23. **完善错误处理**
    - findings 分类
    - 熔断机制

24. **优化并行度估算**
    - Agent 数量计算
    - 时间估算优化

25. **添加进度追踪**
    - 生成进度报告

---

## 9. 改进工作量估算

| 改进项 | 工作量 | 复杂度 | 依赖 |
|-------|-------|-------|------|
| P0-1: 创建 Templates | 6-8 小时 | 中 | 无 |
| P0-2: 创建 References | 4-6 小时 | 中 | 无 |
| P0-3: 重写 SKILL.md | 8-10 小时 | 高 | P0-1,2 |
| P0-4: Base 层生成 | 4-6 小时 | 中 | P0-1,2,3 |
| P0-5: Slice 文件生成 | 6-8 小时 | 高 | P0-1,2,3 |
| P0-6: 覆盖率校验 | 6-8 小时 | 高 | P0-3,4,5 |
| P0-7: Placeholder 注册表 | 4-6 小时 | 中 | P0-1,2,3 |
| P0-8: FV 任务注入 | 2-3 小时 | 低 | P0-3 |
| P1 全部 | 20-30 小时 | 中-高 | P0 完成 |
| P2 全部 | 10-15 小时 | 低-中 | P1 完成 |

**总工作量**：
- P0（核心）: 40-55 小时
- P1（重要）: 20-30 小时
- P2（可选）: 10-15 小时
- **总计**: 70-100 小时

---

## 10. 执行路线图

### Phase 1: 基础设施（P0-1,2）— Week 1
1. 创建 templates/ 目录，6 个模板
2. 创建 references/ 目录，3 个 reference
3. 适配 iOS 特性（Swift → SwiftUI, Kotlin → UIKit）

### Phase 2: 核心架构（P0-3,4,5）— Week 2
1. 重写 SKILL.md，采用 indexed-v1
2. 实现 Base 层生成逻辑
3. 实现 Slice 文件生成逻辑

### Phase 3: 质量保证（P0-6,7,8）— Week 3
1. 实现覆盖率校验（12 项）
2. 实现 Placeholder 注册表
3. 实现 FV 任务注入

### Phase 4: 优化完善（P1）— Week 4
1. 实现 suggested_skills 标注
2. 完善启动检查和并行组分配
3. 实现接线点提取和编排派发

### Phase 5: 锦上添花（P2）— Week 5（可选）
1. 支持高级特性
2. 优化用户体验

---

## 11. 验证清单

改进完成后，必须验证：

### 产物验证
- [ ] ui-plan.md 存在且格式正确（Markdown 表格）
- [ ] feature-plan.md 存在且包含 plan_format: indexed-v1
- [ ] base-plan.md 存在且包含 Base-0~7 任务
- [ ] plans/slices/*.md 存在且每个功能一个文件
- [ ] coverage-matrix.md 存在且包含全部校验项
- [ ] spec/placeholder-registry.md 存在

### 字段验证
- [ ] ui-plan 包含 owning_slice 列
- [ ] slice 文件包含 integration_points_ref
- [ ] slice 文件包含 wires 接线账本
- [ ] slice 文件包含 cross_slice_edits
- [ ] Base 任务包含 suggested_skills
- [ ] Slice 任务包含 suggested_skills+

### 覆盖率验证
- [ ] P0 功能覆盖率 = 100%
- [ ] UI 页面覆盖率 = 100%
- [ ] Placeholder 白名单率 = 100%
- [ ] Complex anchor 完整率 = 100%
- [ ] 对接点归属率 = 100%
- [ ] 组件嵌入归属率 = 100%

### 实际执行验证
- [ ] 在 Cuike02 项目实际运行 i2h-plan
- [ ] 生成的产物下游 i2h-execute 可消费
- [ ] 所有 HARD-GATE 校验通过

---

## 12. 与 i2h-spec 改进的对比

| 维度 | i2h-spec v2.2 改进 | i2h-plan 需要改进 |
|------|-------------------|------------------|
| **模板数量** | 8 个 → 完整 | 0 → 需要 6 个 |
| **references 数量** | 13 个 → 完整 | 0 → 需要 3 个 |
| **架构偏离** | Python主导 → LLM主导 | 扁平JSON → indexed-v1 |
| **产物数量** | 完整 | 严重缺失 |
| **改进难度** | 中等（主要是补充） | 高（需要重构） |

i2h-plan 的改进难度**更高**，因为：
1. 架构需要从扁平重构为三层
2. 产物格式需要从 JSON 改为 Markdown
3. 需要新增多个核心机制（wires、placeholder、FV）

---

## 13. 总结

### 当前状态
iOS 版本 i2h-plan 是 Android 原版的**过度简化**版本：
- ❌ 缺失 indexed-v1 三层架构
- ❌ 缺失 6 个核心产物
- ❌ 缺失 12 项覆盖率校验
- ❌ 缺失接线账本和 placeholder 机制
- ❌ 与原版设计理念严重偏离

### 核心问题
**根本原因**：没有深入理解原版的设计理念
1. indexed-v1 三层架构的价值（索引/详情分离）
2. 接线账本的重要性（集成追溯）
3. 单写者纪律的必要性（避免冲突）
4. Placeholder 白名单的作用（质量保证）

### 改进策略
参考 i2h-spec 改进经验：
1. ✅ **深入理解原版** — 不要重新发明轮子
2. ✅ **系统性对比** — 找出所有差异
3. ✅ **分级改进** — P0 优先，按依赖排序
4. ✅ **完整验证** — 实际执行，收集反馈
5. ✅ **持续迭代** — 根据反馈优化

### 预期效果
改进后，i2h-plan 应达到：
- ✅ 架构对齐（indexed-v1 三层）
- ✅ 产物完整（6+ 个文件）
- ✅ 可追溯性（接线账本、源码锚点）
- ✅ 质量保证（12 项校验）
- ✅ 下游可消费（i2h-execute 可直接使用）
- ✅ 与原版对齐（95%+ 一致性）

---

**报告版本**: v1.0  
**基于方法论**: tool-optimization v1.1  
**下一步**: 执行 Phase 1（创建 Templates 和 References）
