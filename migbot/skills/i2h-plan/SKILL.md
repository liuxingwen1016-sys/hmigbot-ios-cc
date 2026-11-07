---
name: i2h-plan
description: iOS→HarmonyOS 迁移的执行计划生成（Pipeline 第二步）：读已审批的 spec/baseline/，产出 UI 转换计划 ui-plan.md 和功能执行计划 feature-plan.md。当用户说"生成计划""怎么做这个迁移""下一步怎么做"时触发。不要用于：生成 Spec（用 i2h-spec）或执行代码（用 i2h-execute）；spec/baseline/ 未就绪时提示先跑 i2h-spec。
tags: [pipeline, migration]
type: pipeline
domain: migration
---

# i2h-plan

## 启动检查 — 待办 findings

读 `spec/.i2h/open-findings.json`（不存在 = 首轮，直接开工）：

| 情况 | 行动 |
|---|---|
| 有 `owner_stage: plan` 的条目 | 先处理这些，再做本轮正常工作；处理完重跑 `scripts/lint_plan_coverage.py` 确认消失 |
| 有 `owner_stage` 属**上游阶段**且 `severity: blocking`、未带 `decision_ref` 的条目 | 🔴 **拒绝开工**，列出条目并回到该阶段（i2h-spec）处理；上游按序：spec > plan > execute > verify |

---

## 关键约束（Critical）

以下任一违反均 **plan FAIL**：

- **indexed 布局唯一**：feature-plan.md = 纯调度索引（无状态列、无复述、无依赖 ASCII 树）；Base 层正文外置 `plans/base-plan.md`（只读无 checkbox/evidence，仅 Stage 2 消费）；逐 slice 账本在 `plans/slices/slice-NN-<fid>.md`。模板见 [templates/feature-plan-template.md](./templates/feature-plan-template.md) §必填规则。
- **slice 文件三铁律**（模板见 [templates/slice-plan-template.md](./templates/slice-plan-template.md)）：① 调度表非详案（scope 名字级、spec_refs 指针）；② 生成后只读（无 checkbox/evidence/状态字段，完成性由机械校验+组 brief 记录）；③ 不持有占位（plan 期占位直写 `spec/placeholder-registry.md`）。
- **编排派发（§3.0，HARD-GATE）**：P0 kernel → P1 三写并行（A=ui-plan / B=base-plan / C=slices+registry）→ P2 收拢（定组/索引/coverage/审批）。单线程降级时按序自跑、零行为差异。详见 [references/plan-dispatch.md](./references/plan-dispatch.md)。
- **覆盖率阈值（§7，12 项校验）**：P0 功能 100% / P1 ≥80% / UI 页面 100% / Placeholder 白名单 100% / Complex anchor 100% / 对接点归属 100% / 组件嵌入 100% / 数据链路扇出 100% / 分层 5 项 / 功能分组符合规则。任一失败 → 阻断。
- **Final Verification 必带 2 task**（模板见 [templates/feature-plan-template.md](./templates/feature-plan-template.md) §FV）：FV-1（Final Structural Closure，调 arkts-structural-closure pipeline 模式）+ FV-2（终态全量编译，调 hmos-builder agent）；顺序固定。
- **References / Templates 强制加载（HARD-GATE）**：本 skill body 中所有 `[references/X.md]` / `[templates/Y.md]` 引用，在对应步骤执行时**必须** Read 整个文件作为执行规范，不得仅靠 body 摘要或字段名提示执行。跳过加载 = PROCESS_VIOLATION。

---

## 1. 定位

Pipeline 第二步（在 i2h-spec 之后、i2h-execute 之前）：spec 已审批 → 生成双计划（UI / 功能）→ 交 i2h-execute 执行。

**禁止代码生成**：本阶段只产出计划，不写任何 `.ets` 代码（代码生成是 i2h-execute 职责）。

---

## 2. 输入

读取 spec 产出物：

```
spec/baseline/
├── ui-manifest.md              # UI 页面清单
├── feature-index.md            # 功能列表 + 依赖关系
├── feature-base.md             # Base 层公共能力清单
├── features/                   # 逐功能 spec
│   └── F<NNN>-*.md
└── ui/                         # 逐页面 spec
    └── page_<NNNN>.md
```

可选输入（存在时读取）：
- `spec/baseline/api-inventory/` — API 事实源（Step 3c scope 与 suggested_skills+）
- `spec/baseline/api-inventory/data-chains/chain-auth.md` — 登录链路契约（Step 4.3 数据链路扇出）
- `spec/decision-ledger.md` — 决策记录（grill #1 产出的 D0 + 可选前置决策）
- `spec/.i2h/ui-coverage-report.md` — UI 覆盖报告（存在时校验 status=PASS）

---

## 3. 双计划生成

### 3.0 编排协议（P0 → P1 → P2，HARD-GATE）

**完整规范见 [references/plan-dispatch.md](./references/plan-dispatch.md)**（本节仅摘要）。

**P0: 内核裁决**（主线程）
1. 读取输入（feature-index / ui-manifest / feature specs）
2. 拓扑排序（计算 depends_on）
3. **归属消歧**（owning_slice 裁决，4 条规则，见 [templates/ui-plan-template.md](./templates/ui-plan-template.md) §归属消歧）
4. hub / 横切判定（见 §3b Step 5 隐式关系兜底）
5. Slice 定号（Slice N ↔ F-ID 1:1）

**P1: 三写并行**（3 个 agents，单写者纪律）
- Agent A: 生成 `ui-plan.md`（写权：仅此文件）
- Agent B: 生成 `base-plan.md`（写权：仅此文件；P-B 行信封带回）
- Agent C: 生成 `slices/*.md` + 直写 `placeholder-registry.md`（写权：plans/slices/* + spec/placeholder-registry.md）

派发 prompt 模板见 [references/plan-dispatch.md](./references/plan-dispatch.md) §P1-A/B/C。

P1 使用 `scripts/parallel_dispatch.py` 的依赖组调度，默认最多 4 个 worker。每个
worker 只写自己的临时目录和 checkpoint，checkpoint 位于
`spec/.i2h/checkpoints/plan/group-N/`，包含真实 UTC 起止时间、排队时间、retry、cache
hit 和 usage。DeepSeek 单请求异常只重试失败 worker，并保留其他 worker 的结果。主线程
按 feature/slice ID 稳定排序后一次性 merge，再执行 lint 和 gate。

**P2: 收拢**（主线程）
1. 定组（parallel_group 分配，§3b Step 5）
2. 生成索引（feature-plan.md L1）
3. 覆盖率校验（§7，12 项）
4. grill #2 技术决策（§7.2）
5. 审批门控（§8）

**降级方案**：Agent 派发不可用时，只允许把失败 worker 重新排入同一 bounded queue。禁止
因单个 worker 异常把完整 P1 三写降级成单线程，除非记录明确的基础设施 finding 和
checkpoint。产物格式、校验标准必须保持一致。

### 3a. UI 转换计划（ui-plan.md）

**MUST Read**: [templates/ui-plan-template.md](./templates/ui-plan-template.md)

**Step 1: 读取 UI 清单**

从 `spec/baseline/ui-manifest.md` 和 `spec/baseline/ui/*.md` 读取：
- 页面列表（page_id / name / source / priority / confidence）
- 依赖关系（导航目标、嵌入子组件）

**Step 2: 分批规则**

```
批数 = ceil(页数 ÷ BATCH_MAX)
BATCH_MAX 按宿主取表（见模板）：
- Claude Code = 20（目标区间 [12,20]）
- Codex = 8（目标区间 [6,8]）
- DevEco Code = 10（目标区间 [8,10]）
```

**关键原则**：
- 页面依赖**不参与**分批（FWD-REF 机制兜底）
- 批内默认全并行（单写者纪律，各写各文件）
- size-1 Batch 禁止（并入前一批）
- confidence: low 行内标 `⚠️low`（不输出 confidence 列）

**Step 3: 生成 ui-plan.md**

Markdown 表格格式：

```markdown
# UI Conversion Plan

## Context
- Source: spec/baseline/ui-manifest.md
- Style: <style_set 值>
- Total pages: <N>
- Batches: <M>

## Batch 1: P0 Core Pages

| 序号 | 页面 | iOS 来源 | owning_slice |
|------|------|---------|--------------|
| 0001 | HomeView | HomeView.swift | F001 |
| 0002 | FeedView | FeedView.swift | F001 |

结算检查点: Batch 1 完成后（batch closer 结算 → brief，见 i2h-execute §3b）

## Summary
- P0 pages: X (Batch 1-2)
- P1 pages: Y (Batch 3)
- ⚠️ Low confidence: W pages（W=0 时省略）
```

**关键字段**：
- `owning_slice`: 裸 F-ID（如 F001），由 P0 kernel 归属消歧裁决

### 3b. 功能执行计划（feature-plan.md + base-plan.md + slices/*.md）

**MUST Read**: 
- [templates/feature-plan-template.md](./templates/feature-plan-template.md)（L1 索引 + base-plan）
- [templates/slice-plan-template.md](./templates/slice-plan-template.md)（L2 slice 文件）

**Step 1: 读取功能依赖**

从 `spec/baseline/feature-index.md` 读取：
- 功能列表（F-ID / name / priority / complexity）
- 排序依赖（sort_depends_on）
- 功能描述、涉及页面

**Step 2: 拓扑排序**

```python
# 伪代码
def topological_sort(features):
    sorted_list = []
    visited = set()
    
    def visit(f):
        if f in visited:
            return
        for dep in f.depends_on:
            visit(dep)
        visited.add(f)
        sorted_list.append(f)
    
    for f in features:
        if f not in visited:
            visit(f)
    
    return sorted_list
```

**循环检测**：如果检测到循环依赖 → 阻断，提示修正 feature-index.md

**Step 3: 生成 Base 层任务列表（写入 plans/base-plan.md）**

**MUST READ**: [templates/feature-plan-template.md](./templates/feature-plan-template.md) 文件二段

Base-0~7 任务清单、各任务 suggested_skills / input / blocking 的**权威 = 模板文件二段**（生成时 MUST 加载，本 body 不复述）；输入来源 = feature-base.md 公共能力清单 + feature-index.md 共享组件/服务 + Base-0 的全 spec 资源 ID 全集扫描。

**iOS 特定 Base 层任务**（8 个）：

- **Base-0: 资源前置扫描与迁移**
  - suggested_skills: [ios2hmos_resources_convert]
  - input: 所有 spec 中引用的资源 ID 全集
  - output: entry/src/main/resources/ + spec/baseline/plans/resource-mapping.md
  - blocking: true

- **Base-1: Models（数据模型）**
  - suggested_skills: [arkts-data-model]
  - input: feature-base.md Models 段
  - output: entry/src/main/ets/models/*.ets
  - parallel_group: 1
  - iOS 映射: Swift struct/class → ArkTS @Observed class

- **Base-2: Database（数据库）**
  - suggested_skills: [arkts-data-layer]
  - input: feature-base.md Database 段
  - output: entry/src/main/ets/database/*.ets
  - parallel_group: 2
  - iOS 映射: CoreData/SwiftData → RelationalStore

- **Base-3: Network（网络层）**
  - suggested_skills: [arkts-data-layer, arkts-network-troubleshoot]
  - input: feature-base.md Network 段
  - output: entry/src/main/ets/network/*.ets
  - parallel_group: 3
  - iOS 映射: URLSession/Alamofire → @ohos.net.http

- **Base-4: Events（事件系统）**
  - suggested_skills: [arkts-state-manager]
  - input: feature-base.md Events 段
  - output: entry/src/main/ets/events/*.ets
  - parallel_group: 2
  - iOS 映射: NotificationCenter/Combine → EventHub/emitter

- **Base-5: Preferences（偏好设置）**
  - suggested_skills: [arkts-data-layer]
  - input: feature-base.md Preferences 段
  - output: entry/src/main/ets/preferences/*.ets
  - parallel_group: 2
  - iOS 映射: UserDefaults/@AppStorage → Preferences

- **Base-6: 公共组件库**
  - suggested_skills: [arkts-component-builder, arkts-pattern-library]
  - input: ui-manifest.md 共享组件表 + feature-base.md 公共组件段
  - output: entry/src/main/ets/components/common/*.ets
  - parallel_group: 2
  - iOS 映射: SwiftUI 自定义 View / UIKit 组件 → @Component

- **Base-7: 编译验证**
  - suggested_agents: [hmos-builder]
  - blocking: true
  - parallel_group: 4（末组独占）

**parallel_group 默认分配**（iOS）：
- Base-1 (Models): group 1（无依赖）
- Base-2, Base-4, Base-5, Base-6: group 2（可并行）
- Base-3 (Network): group 3（可能依赖 Preferences 的 token）
- Base-7 (编译): group 4（独占末组）

**产出格式**（base-plan.md）：
- 只读态：无 `- [ ]` checkbox、无 `evidence:` 槽
- 完成性由 execute `stage2_brief.md` 记录

**Step 4: 生成 Feature Slice 任务列表（写入 plans/slices/*.md）**

按拓扑排序的顺序，为每个功能生成一个 Slice。每个 Slice 包含：

**Slice 文件结构**（slice-NN-<fid>.md）：

```
## Slice 1: 功能名 (F001)
parallel_group: 1 | complexity: simple
depends_on: [base]

ios_source_anchors_ref: {count: 0, source: spec/baseline/features/F001-*.md}

integration_points_ref: spec/baseline/features/F001-*.md#对接点

wires:
  - page: entry/src/main/ets/pages/HomeView.ets
    viewmodel: entry/src/main/ets/viewmodels/HomeViewModel.ets
  - page: entry/src/main/ets/pages/MainContainer.ets
    slot: homeTab
    embed: HomeView()
    resolve_by: Slice 1 Step 3a

modifies_files:
  - entry/src/main/ets/pages/MainContainer.ets
  cross_slice_edits:
    - file: entry/src/main/ets/pages/MainContainer.ets
      handler: onShare
      resolve_by: Slice 2 Step 3d

- Step 3a: UI 补充 — scope: 0001, 0002 (HomeView, FeedView)（名字级）| input: ui-manifest 对应行
- Step 3b: ViewModel — scope: HomeViewModel | input: spec_refs: features/F001-*.md#状态管理
- Step 3c: 数据层 — scope: DataStore | suggested_skills+: arkts-data-layer | input: spec_refs: features/F001-*.md#数据存储
- Step 3d/3e: 接线 + 验证 — 契约见 i2h-execute §5e（本文件零复述）
```

**Step 4.0: 复杂度判定**

读取 feature spec 顶部 `complexity` 字段（由 i2h-spec Step C4-pre 写入）：

| complexity | Slice 流程 | Step 3b prompt 形态 | 校验 |
|-----------|-----------|---------------------|------|
| `simple` | 现有 4 步流程 | 仅第三段（ViewModel 实现） | — |
| `complex` | 现有 4 步流程 | **三段式**（源码理解 + 差异清单 + ViewModel 实现） | **必须含 ≥ 1 个 `ios_source_anchors`**，否则 plan 输出 FAIL |
| 未标 | 按白名单关键词自动推断 | — | 推断为 complex 必须回填 spec |

**Step 4.1: 三方 SDK 处理（四判据，按序短路）**

**MUST READ**: [references/skill-binding-rules.md](./references/skill-binding-rules.md)

```
对每个 feature spec 提到的 iOS Framework / 三方 SDK：
0. ledger 前置：spec/decision-ledger.md 已有 C8 决策 → owned task（suggested_skills 由决策指定），跳过
1. skill-binding-rules 映射：命中 → suggested_skills+（追加到 Step 行），跳过
2. 未命中 → 直接 append placeholder-registry.md：
   - P-ID: P-S{N}-{序号}（N = Slice 编号）
   - kind: thirdparty-sdk
   - trigger_condition: <业务类别> SDK 入仓（见模板白名单）
3. 白名单 trigger：格式合规检查（见 [templates/placeholder-registry-template.md](./templates/placeholder-registry-template.md)）
```

**iOS 三方 SDK 判据示例**：
- 微信 SDK → 命中 skill-binding-rules（arkts-login）→ suggested_skills+
- Alamofire → 命中 skill-binding-rules（自建封装）→ 不占位
- 自研埋点 SDK → 未命中 → 登记 placeholder（trigger: 埋点 SDK 入仓）

**Step 4.2: 接线点提取（零复制，指针引用）**

从 feature spec「## 对接点」段提取接线关系，写入 slice 文件 `wires` 账本：

**Wires 结构**：

```yaml
wires:
  # VM 入边（ViewModel 接线）
  - page: <page_path>
    viewmodel: <viewmodel_path>  # null 表示页面级 @Local 状态
  
  # 组件嵌入入边（子组件嵌入）
  - page: <parent_page>
    slot: <slot_name>
    embed: <child_page>()
    resolve_by: Slice N Step 3a
```

**跨切片编辑**（modifies_files / cross_slice_edits）：
- 只列**他切片所建**的已存在文件
- **本切片自建文件禁列**
- 去双登：槽位填充只登 wires embed 条，cross_slice_edits 只收非 embed 的 handler 回改

**iOS 特定场景**：
- SwiftUI TabView → MainContainer 各 Tab 槽位
- SwiftUI Sheet → 模态弹窗嵌入
- UIKit Child ViewController → addChild() 嵌入

**Step 4.3: 数据链路契约扇出（可选，chain-auth 存在时）**

如果 `spec/baseline/api-inventory/data-chains/chain-auth.md` 存在：

读取 chain-auth §5.1 层清单（L0-L7），逐层注入某 Base/Slice 任务的 `data_chain_refs:` 字段（字段名必须如此，§7 第 10 项按字段名校验）。

**注入示例**：
- L0 (应用身份) → Base-3 Network: `data_chain_refs: chain-auth L0`
- L2-L3 (认证令牌) → Base-3 Network: `data_chain_refs: chain-auth L2-L3`
- L4 (隐私门控) → Slice 涉及用户数据的功能
- L7 (下游服务) → Slice 涉及外部 API 调用的功能

**Step 5: 标注并行组（parallel_group 分配）**

按 depends_on 关系分组，满足：
1. **最早可行组**：每个 Slice 排入 max(依赖组号)+1 组
2. **组容量上限**：每组 ≤ GROUP_HARD_LIMIT (8)
3. **size-1 组处理**：
   - 同层可并：并入邻近组
   - 无法并组：附挂（不计入组内 slice 数）
   - 记录 size1_exceptions

**隐式关系兜底**（覆盖优先）：
- hub 页（Tab 容器）→ 归最早承载任一 Tab 的切片
- 横切切片（埋点/遥测）→ 排最末组

**Step 6: Final Verification 段注入（模板见 [templates/feature-plan-template.md](./templates/feature-plan-template.md) §FV）**

在 feature-plan.md 索引末尾添加 2 个必填 blocking task：

```markdown
## Final Verification

- FV-1: Final Structural Closure
  - suggested_skills: [arkts-structural-closure]
  - blocking: true
  - details: 调 arkts-structural-closure (mode=pipeline target=final)
  - acceptance: final_state == PASS

- FV-2: 终态全量编译
  - suggested_agents: [hmos-builder]
  - blocking: true
  - details: FV-1 通过后跑终态全量编译
  - acceptance: BUILD_STATUS=PASS
```

**顺序固定**：FV-1 在前（会改码），FV-2 在后（兜底编译）。

---

## 4. suggested_skills 标注规则

根据 task 内容自动标注应使用的 Domain Skill。完整的 task→skill 主映射表（含登录 / 支付 / 推送 / 相机 / 地图 / 视频等 100+ 领域条目）见 [references/skill-binding-rules.md](./references/skill-binding-rules.md)，标注时读。下方两表是 body 必备的 Core 决策规则。

**承载字段（三层，单一权威源）**：① Base / FV 任务 → stanza `suggested_skills:`（base-plan.md / 索引）；② Slice 4 步默认映射 → **权威 = 下表**，slice 文件零复述；③ **per-slice 差异化追加 → slice 文件对应 Step 行 `suggested_skills+:` 字段（delta-only；命名含 `suggested_skills` 词根便于检索、`+` 表增量）**——plan 期读 spec 做出的语义判断（登录→arkts-login / 支付→arkts-payment / WebView→arkts-webview 等），必须落字段，不得只靠 execute runtime 兜底。

### Feature Slice 步骤的默认 suggested_skills

| Step | suggested_skills |
|------|-----------------|
| Step 3a: UI 补充 | `i2h-swiftui-converter` / `i2h-uikit-converter` (agent) |
| Step 3b: ViewModel + 状态管理 | `arkts-state-manager` |
| Step 3c: 数据层接入 | `arkts-data-layer` |
| Step 3d/3e: 页面接线 + 切片级验证 | `arkts-state-manager`（worker 自身页内接线）；跨文件接线 / 结构验证由 i2h-closer 承担（group 模式），集中编译由 i2h-execute §5f 的 hmos-builder 承担；这些绑定均不在 plan 重复标注 |

当功能涉及特殊领域时，把追加 skill 写入该 slice 文件对应 Step 行的 `suggested_skills+:`（例如登录功能的 Step 3b 行 `suggested_skills+: arkts-login`）。

### 风格 Skills 追加

`style_set != none` 时按 task 领域从风格集选取追加（domain=ui/state/navigation/data/engineering/system 匹配表 + 选取依据见 [references/skill-binding-rules.md](./references/skill-binding-rules.md)「风格 Skills 追加」节）；`none`（含字段缺失）不追加。风格 skills 追加在 domain skills 之后（叠加而非覆盖基线）。

---

## 5. Plan 格式

### 5a. UI 转换计划格式（ui-plan.md）

完整模板见 [templates/ui-plan-template.md](./templates/ui-plan-template.md)（生成 ui-plan.md 时读）。

Core：批数 = ceil(页数 ÷ BATCH_MAX)、按表序均分（页面依赖不参与——FWD-REF 兜底）；无逐批 `hard_limit/actual_pages` 自声明。`owning_slice` 列填**裸 F-ID**（`^F\d{3}$` 契约——Slice↔F-ID 1:1，编号见索引），供 converter 算 forward-ref `resolve_by` + §7 归属校验消费。**Summary 不再输出 owning_slice 全量映射段**（Batch 表行内已有，第三份副本禁止）。

### 5b. 功能执行计划格式（L1 索引 + L2 slice 文件）

**MUST 加载**两个模板：[templates/feature-plan-template.md](./templates/feature-plan-template.md)（L1 索引 + base-plan.md：Context 含 `plan_format: indexed-v1` / Base 层 stub（Base-0..7 正文写 `plans/base-plan.md`，只读无 checkbox/evidence）/ slice 头部按 parallel_group `## Group N` 分节、每组末尾 `> group-closer @ GN` 插入行、每 slice 头部含 `detail:` 指针 / FV / Summary，"必填规则"段不得删减）+ [templates/slice-plan-template.md](./templates/slice-plan-template.md)（L2 slice 文件：三铁律 / `ios_source_anchors_ref` / `integration_points_ref` 指针（对接点零搬移——spec 唯一权威）+ 结构化接线账本 `wires`·`modifies_files`·`cross_slice_edits`（含两条降噪规则），"字段规则"段不得删减）。

索引**不含**：依赖 ASCII 树、步骤契约文本、账本内容、状态列。slice 文件由 Step 4.0–4.3 生成账本；4 步任务行只写差异化 scope + input 指针（验收契约权威在 i2h-execute §5b–5e，plan 零复述）。

---

## 6. 存储

所有 plan 存储在 `spec/baseline/plans/` 目录下；占位符注册表在 `spec/` 根目录（plan 期直写）：

```
spec/
├── placeholder-registry.md       # ← 占位唯一写入位（plan Step 4.1 直写 + 执行期铸号）
└── baseline/plans/
    ├── ui-plan.md
    ├── feature-plan.md           # L1 调度索引（plan_format: indexed-v1）
    ├── base-plan.md              # Base 层任务正文（只读无 checkbox/evidence）
    ├── slices/                   # L2 逐 slice 只读调度账本
    │   └── slice-NN-<fid>.md
    ├── coverage-matrix.md
    └── resource-mapping.md       # ← Stage 0 资源前置产出（execute §3.0）
```

execute 阶段的过程记录（brief，落 `spec/execution/briefs/`）由 i2h-execute 启动时自建目录并填充——**plan 不创建任何执行域目录**（过程记录是执行域产物）。

---

## 7. 覆盖率校验（Plan 生成后自动执行）

Plan 生成完毕后，必须执行覆盖率校验，确保所有功能都被 plan 覆盖，并校验 placeholder / complex anchor 完整性。

**MUST Read**: [templates/coverage-matrix-template.md](./templates/coverage-matrix-template.md)

校验算法：
1. 从 `feature-index.md` 提取所有功能 ID（F-xxx）及其优先级
2. 从 `feature-plan.md` 所有 Slice 的功能 ID 收集已覆盖集合
3. 从 `ui-plan.md` 所有 Batch 的页面收集已覆盖的 UI 页面集合
4. 交叉比对 `ui-manifest.md` 的页面清单，确认无遗漏
5. 计算覆盖率
6. **Placeholder 完整性校验（对 registry 本体跑）**：扫 `spec/placeholder-registry.md` 全部 plan 期写入条目，逐项验证：
   - `P-ID` 是否符合 `P-S{N}-{seq}` 或 `P-B{N}-{seq}` 格式
   - `location` 是否为有效文件路径形态
   - `trigger_condition` 是否命中 [templates/placeholder-registry-template.md](./templates/placeholder-registry-template.md) 中的白名单格式（含第 6 类 `Slice {N} Step {3c|3d}`），且不含黑名单关键词
   - `kind` 必须是 `thirdparty-sdk` 或 `forward-ref`；`kind=forward-ref` 必须含 `resolve_by`
7. **Complex Slice anchor 校验（直接读 feature spec）**：对全部 `complexity: complex` 的 feature：
   - spec 顶部必须含 `ios_source_anchors` 段且非空；slice 文件的 `ios_source_anchors_ref.count` 与之一致
   - 每条 anchor 的 `path` 在 iOS 源码目录下必须实际存在（逐路径 `test -f`）
   - role 必须是 i2h-spec Step C4-pre 定义的 iOS 角色类型之一（view/view_controller/viewmodel/store/service/repository/manager/coordinator/delegate/util/data_model）
8. **跨切片接线归属检测**：交叉读全部 feature spec「## 对接点」段，产出全局 `(文件, handler, slot?) → owning_slice` 接线归属映射（slot 仅撞键时填），写入 coverage-matrix `Wiring Ownership Map` 段、供 converter 算 `resolve_by`：
   - 非首切片 handler 必须在其 owning Slice 生成显式 `cross_slice_edits:` 条目 `{file, handler, slot?, resolve_by}`；**slot 填充类例外**——归属由 `wires` embed 条（含 resolve_by）体现，不入 cross_slice_edits（禁双登）
   - 校验：每个含「## 对接点」段的 feature，其 owning Slice 的 `integration_points_ref` 必须指向该 spec 段；非首切片 handler 另须 `cross_slice_edits` 显式认领
   - **组件嵌入归属**：`ui-manifest.md` 子组件表 ∪ `ui/page_NNNN.md` 嵌入关系（两源并集），每条「父页 ⊇ 子页」须在子页 owning Slice 的 `wires:` embed 条体现
9. **骨架审计预演（plan 期静态，仅 WARN 不阻断）**：扫 registry plan 期条目 location，同 .ets 文件 ≥5 个 P-ID → WARN（整页占位嫌疑，建议拆 Slice 或标 deferred）
10. **数据链路层扇出校验（chain-auth.md 存在时）**：chain-auth §5.1 层清单逐层确认已被 Step 4.3 注入某任务 `data_chain_refs:`（每层 ≥1 落点）；任一层无落点 → 阻断
11. **分层校验（5 项，indexed 布局专有）**：
    1. 索引条目 ↔ `plans/slices/` 文件一一对应；Base 层 stub → `plans/base-plan.md` 指针存在，且 base-plan 每任务（Base-0 除外）含 `parallel_group`
    2. slice 文件内 `spec_refs` 路径逐条存在
    3. 索引 `complexity` 快照与 feature spec 顶部一致
    4. slice 文件零 spec 复述（行数上限启发式）
    5. 状态交叉：feature-index status=implemented 的 feature，其 owned 页不得仍 pending
12. **功能分组校验**：按各 slice `depends_on` 复算，核 Step 5 三条分组规则；size-1 例外与 Summary 结构化块比对

<HARD-GATE>
覆盖率 / 完整率校验阈值——任一指标不达标即阻断 plan 输出：

| 指标 | 阈值 | 失败动作 |
|------|------|---------|
| P0 功能覆盖率 | = 100% | 阻断，自动补充缺失的 Slice |
| P1 功能覆盖率 | ≥ 80% | 警告，列出缺失项（不阻断） |
| P2 / Skip | 允许 GAP | 仅记录 |
| UI 页面覆盖率 | ui-plan ⊇ ui-manifest 全部非 skipped 页 | 阻断，补漏页 |
| Placeholder trigger 白名单率 | = 100% | 阻断（trigger_condition 不合规） |
| Complex Slice anchor 完整率 | = 100% | 阻断（缺 anchor 或路径无效） |
| 对接点归属率 | = 100% | 阻断（「## 对接点」无 Slice 归属） |
| 组件嵌入归属率 | = 100% | 阻断（ui-manifest 子组件表 ∪ page_NNNN.md 嵌入关系未在 Slice `wires:` embed 条目中体现） |
| 数据链路层扇出完整率（chain-auth 存在时） | = 100% | 阻断（§5.1 某层无 `data_chain_refs:` 落点） |
| 分层校验 5 项 | 全通过 | 阻断（见第 11 项） |
| 功能分组符合规则 | 最早可行组 + 组容量 ≤8 + size-1 处理 | 阻断（见第 12 项） |
</HARD-GATE>

**输出**：`spec/baseline/plans/coverage-matrix.md`（包含 Summary / Feature Coverage / UI Coverage / Wiring Ownership Map / Component Embed Coverage / Skill Routing Map / 失败表段）

### 7.2 grill #2：技术侧决策清零（HARD-GATE）

**完整规范见 [references/grill-2-decision-gates.md](./references/grill-2-decision-gates.md)**（本节仅摘要）。

覆盖率校验通过后、§8 门控之前，**立即以 Skill 工具直接调用 `grill-with-docs`**，传入技术侧类目（C6–C11、C13–C14、C17）。

**必问 vs 自答分流**：
- **用户预知优先**（C6/C8）：先批量问用户已知信息 → 残余项查文档 → 仍残余按默认策略
- **实时拷问**（C7/C9/C13/C14）：架构决策、平台行为差异、签名、密钥
- **模型自答**（C10/C11）：后台行为、失败降级

**HARD-GATE 校验**：
- registry 中 plan 期写入的 `kind=thirdparty-sdk` 条目在 ledger 中均有对应 C8 决策
- 所有 `complexity: complex` 的 Slice 在 ledger 中有对应 C7 决策
- `uncertainties[]` 无 `status: open` 遗留（C17）
- Plan 待修订项段 ≠ 空时提示用户

---

## 8. 审批（可选）

**MUST Read**: [templates/gate-output-template.md](./templates/gate-output-template.md)

双计划生成后输出审批摘要；默认无人值守按 i2h-spec gate-handling.md §5 自动确认后进入 i2h-execute，用户要求逐个确认时等人工审批。

摘要包含：
- UI 转换计划（总页面 / 批次 / low confidence 页面）
- 功能执行计划（Base 层任务 / Feature Slices / 可并行组）
- 覆盖率（P0/P1 功能 / UI 页面）
- Placeholder Registry（总条目）
- 骨架审计预演（WARN）
- grill #2 决策清单

用户可以：
- 直接确认 → 进入 i2h-execute
- 修改后确认 → 进入 i2h-execute
- 要求重新生成 → i2h-plan 重新执行

---

## 9. 完成标记

在写入 plan 完成标记前，必须从 feature 验收条件和已生成的 slice
确定性生成 execute 消费的两个索引。禁止手写空文件或由模型猜测 requirement 映射。

```bash
python3 .claude/skills/i2h-plan/scripts/generate_execute_coverage.py \
  --project-root .
```

脚本会写入 `spec/.i2h/requirements-index.json` 和
`spec/.i2h/plan-coverage.json`。任一 feature 缺少验收条件或 plan slice 时失败。
execute coverage lint 只消费这两个索引，并从 packet 的
`requirement_digests` 回填实现声明。

创建 `spec/baseline/plans/complete.txt` 作为 **schema-2 JSON marker**。按照
[marker-contract.md](./references/marker-contract.md) 调用
`marker_contract.write_marker()`，传入 `stage="i2h-plan"`、当前
`target_input_sha256`，以及最终 plan 和已审批的 schema-2 UI delivery JSON
（文件必须已落盘）。不要再写 `i2h-plan completed at ...` 纯文本；marker
本身不能作为 artifact。

---

## 10. 收尾：上报阶段用量

```bash
.migbot/bin/i2h mark-stage i2h-plan
```

---

**最后更新**: 2024-11-03  
**版本**: v2.0（重写版，indexed-v1 架构 + iOS 适配）

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
