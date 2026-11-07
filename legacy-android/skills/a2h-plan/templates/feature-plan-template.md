<!-- when: 生成 feature-plan.md（L1 调度索引）+ plans/base-plan.md（Base 层正文）时加载 -->
<!-- topics: feature-plan 索引, plan_format, Base 层 stub, base-plan.md, Group 分节, group-closer 插入点, slice 头部, FV, indexed 布局 -->

# feature-plan.md（L1 调度索引）+ base-plan.md 完整模板

**indexed 布局唯一**：feature-plan.md 是纯调度索引——无状态列、无 spec 复述、无步骤契约样板、无依赖 ASCII 树；Base 层正文外置 `plans/base-plan.md`（仅 Stage 2 消费）；逐 slice 账本在 `plans/slices/slice-NN-<fid>.md`（模板见 [slice-plan-template.md](./slice-plan-template.md)）。

## 文件一：feature-plan.md（索引）

```markdown
# Feature Execution Plan

## Context
- plan_format: indexed-v1                  # 版本标记（消费脚本检测旧 monolith 的依据）
- Source: spec/baseline/feature-index.md, spec/baseline/feature-base.md
- Style: <style_set 值，none 或具体风格名>
- Total features: <N>
- Total slices: <N>
- Base tasks: <Base 层任务数>
- 定位 / 工程锚点: <decision-ledger D0 摘要一行，不复述 ledger 正文>

## Base 层（<N> tasks；执行序 Phase 0；Base-0/Base-7 blocking）
detail: plans/base-plan.md

<Base 层到此为止——正文在 base-plan.md，索引不展开任何 Base 任务行>
```

## 文件二：plans/base-plan.md（Base 层正文，与索引同批生成）

**只读态**：与 slice 文件同律——无 checkbox、无 evidence 槽（完成性由 execute `stage2_brief.md` HARD-GATE 记录，plan 不承载执行态）。

```markdown
# Base 层任务（执行时序 Phase 0，先于所有 Slice）

所有 Feature Slices 共用的基础设施，必须先完成。

- Base-0: 资源前置扫描与迁移
  - suggested_skills: [android2hmos_resources_convert]
  - input: 所有 spec 中引用的资源 ID 全集（扫描 spec/baseline/ui/page_*.md、spec/baseline/features/F-*.md、feature-base.md）
  - output: entry/src/main/resources/ 全量资源 + spec/baseline/plans/resource-mapping.md
  - acceptance: 缺失资源显式标 `$r('app.media.MISSING_xxx')`（编译期失败暴露而非静默 fallback）
  - blocking: true

- Base-1: Models — 所有 entity / DTO 定义
  - suggested_skills: [arkts-data-layer]
  - input: feature-base.md Models 段
  - output: entry/src/main/ets/models/*.ets
  - parallel_group: 1

- Base-2: Database — Schema + DAO
  - suggested_skills: [arkts-data-layer]
  - input: feature-base.md Database 段
  - output: entry/src/main/ets/database/*.ets
  - parallel_group: 2

- Base-3: Network — HttpClient + interceptors
  - suggested_skills: [arkts-data-layer, arkts-network-troubleshoot]
  - input: feature-base.md Network 段
  - output: entry/src/main/ets/network/*.ets
  - parallel_group: 3
  - data_chain_refs: chain-auth L2-L3    # 仅 chain-auth 项目填（Step 4.3 注入；字段名必须如此，§7 第 10 项按字段名校验）

- Base-4: Events — EventHub 常量 + pub/sub wrapper
  - suggested_skills: [arkts-state-manager]
  - input: feature-base.md Events 段
  - output: entry/src/main/ets/events/*.ets
  - parallel_group: 2

- Base-5: Preferences — SharedPreferences 迁移
  - suggested_skills: [arkts-data-layer]
  - input: feature-base.md Preferences 段
  - output: entry/src/main/ets/preferences/*.ets
  - parallel_group: 2

- Base-6: 公共组件库
  - suggested_skills: [arkts-component-builder, arkts-pattern-library]
  - input: ui-manifest.md 共享组件表 + feature-base.md 公共组件段
  - output: entry/src/main/ets/components/common/*.ets
  - parallel_group: 2

- Base-7: 编译验证 — Base 层全量编译
  - suggested_agents: [hmos-builder]
  - blocking: true
  - parallel_group: 4
```

> Base 任务的 input 一律写**指针**（feature-base.md 对应段），不复述能力清单内容。
> `parallel_group:` 是 execute Stage 2 编排依据（同组并行、组间串行、末组 = Base-7 编译；Base 层的组无 closer）：默认 Base-1 = 1，Base-2 / 4 / 5 / 6 = 2，Base-3 = 3（Network 常依赖 Preferences 的 token 与 Events 的登出广播），Base-7 = 4。**默认值是待确认项**：writer 必须逐任务核对 feature-base.md 对应段，确认不 import 同组其他任务的产出才可留在默认组，否则拆到下一组并在行尾 `#` 注原因；概念上的先后不算依赖。Base-0 属 Stage 0，不标组。

## 文件一（续）：Slice 索引（按 parallel_group 以 `## Group N` 分节；每组末尾一行 group-closer 插入点）

```markdown
## Slice 索引

## Group 1

## Slice 1: <功能名> (F001)
parallel_group: 1 | complexity: complex
depends_on: [Base]
pages_owned: 2 | placeholders: 1
detail: plans/slices/slice-01-f001.md

> group-closer @ G1：落地本组 cross_slice_edits + embed 槽位 → 资源校验 → 结构 fix-forward → 各 slice brief（组内无编译；全工程编译见 a2h-execute §5f）

## Group 2

## Slice 2: <功能名> (F002)
parallel_group: 2 | complexity: complex
depends_on: [Slice 1]
pages_owned: 1 | placeholders: 2
detail: plans/slices/slice-02-f002.md

> group-closer @ G2：同上（每 parallel_group 末尾恰一个 group-closer，size-1 组亦然）

<每 slice 头部固定 4 行字段，除此之外不写任何账本内容——账本在 slice 文件；
 Group 标题与 group-closer 行都是分节排列（parser 按 `## Slice` 头切段、二者天然容忍），slice 编号才是身份>

---

## Final Verification（Stage 3 全部 Slice 完成后顺序执行）

- FV-1: Final Structural Closure（a2h-execute §6）
  - suggested_skills: [arkts-structural-closure]
  - blocking: true
  - details: 调 `Skill({skill: "arkts-structural-closure", args: "mode=pipeline target=final"})` 跑整工程兜底。**禁止 grep / 自跑脚本替代**。CONTINUE 派 repair worker 重调；其他 verdict 处置见该 skill SKILL.md §3.3。
  - acceptance: `final_state == PASS`（完成性凭据由 execute §6 落 loops JSON + fv brief，plan 零回填）

- FV-2: 终态全量编译
  - suggested_agents: [hmos-builder]
  - blocking: true
  - details: FV-1 通过后（其修复可能改码）跑终态全量编译（≤20 轮）；编译修复仅限编译级小改，**不回跑 FV-1**。
  - acceptance: BUILD_STATUS=PASS（真实构建，非 up-to-date 空转；凭据落 fv brief）

## Summary
- Base 层: <N> tasks（执行序 Phase 0）
- Feature Slices: <N>
- 并行组: <M> 组
  size1_exceptions:                      # 无 size-1 组时省略
    - { group: <N>, merge_candidates: [] }   # 同层可并候选；附挂可行性由 lint 自算
- Final Verification: 2 tasks
```

## 必填规则

1. 每 slice 头部字段齐全：`parallel_group / complexity / depends_on / pages_owned / placeholders / detail`（**无 priority**——优先级权威在 feature-index，调度只由 parallel_group + depends_on 驱动，快照即冗余）。`detail:` 必须指向实际生成的 slice 文件（§7 校验索引 ↔ 文件一一对应）。**`placement:` 仅横切 / hub / 附挂三类例外时写**。
1b. **Base 层 stub 恰 3 行**（`## Base 层` 标题含任务数与 blocking 标注 + `detail: plans/base-plan.md`，执行序 Phase 0 作括注）；指针指向同批实际生成的 base-plan.md；索引内**禁止展开任何 Base 任务行**（正文只在 base-plan.md 一处）。
1c. **Slice 索引按 parallel_group 以 `## Group N` 分节**（子组 2a/2b 各自分节）；Group 标题是排列不是身份——slice 编号才是引用键（P-S{N} / resolve_by / briefs），parser 按 `## Slice` 头切段、Group 行天然容忍。
1d. **每个 `## Group N` 末尾一行 `> group-closer @ GN`**（blockquote 插入点：落地本组 cross_slice_edits + embed → 资源校验 → 结构 fix-forward → brief；**组内无编译**，全工程编译由 execute §5f 的 hmos-builder 承担）；对称 ui-plan 的「结算检查点」行——plan 只标插入点 + 指向 execute §5e，**不复述 closer 五步**（单一权威源）。
1e. **base-plan.md 只读**：Base 任务行无 `- [ ]` checkbox、无 `evidence:` 槽（对齐 slice 文件三铁律②；Base 完成性由 execute `stage2_brief.md` 记录）。
2. `complexity` 为一词级快照（spec 为权威，§7 校验一致性）。
3. `placeholders:` 为 registry 派生显示值（plan 期占位直接写 `spec/placeholder-registry.md`，索引不持有占位内容）。
4. **禁止**：依赖 ASCII 树（feature-index 已有，此处只留 depends_on/parallel_group 可执行编码）、步骤契约文本、integration_points / wires 等账本内容、任何状态列（执行状态在 feature-index / ui-manifest / briefs）。
