---
name: a2h-execute
description: Android→ArkTS 迁移代码的三阶段执行引擎（Pipeline 第三步）：按 ui-plan.md/feature-plan.md 派发 subagent 完成页面转换、基础设施、功能切片，含编译闭环。当用户说"执行迁移""开始执行""按 plan 开始做"或"重跑 S1-V 接线验收"时触发，支持部分执行/重试/断点续跑。不要用于：生成 Spec（用 a2h-spec）或计划（用 a2h-plan）；plan 未就绪时先跑 a2h-plan。
tags: [pipeline, migration]
type: pipeline
domain: migration
---

# a2h-execute

## 启动检查 — 待办 findings

读 `spec/.a2h/open-findings.json`（不存在 = 首轮，直接开工）：

| 情况 | 行动 |
|---|---|
| 有 `owner_stage: execute` 的条目 | 先处理这些，再做本轮正常工作；处理完重跑 `scripts/lint_execute_coverage.py` 确认消失 |
| 有 `owner_stage` 属**上游阶段**且 `severity: blocking`、未带 `decision_ref` 的条目 | 🔴 **拒绝开工**，列出条目并回到该阶段（a2h-spec / a2h-plan）处理；上游按 [a2h-spec references/gate-handling.md](../a2h-spec/references/gate-handling.md) 记账放行后再开工 |
| 条目带 `decision_ref`（已记账放行） | ⚪ 照常开工；同源 FAIL 引用该 D 编号，不再新开修复轮次 |
| 条目标记 `escalate: true`（同一问题连续 3 轮） | 🔴 停止自动重试，按 gate-handling §2 记账（工具缺口 / 未达标放行），不出卡等人 |
| 本阶段 section 标记 `halted`（进度停滞 3 轮 / 累计 10 轮） | 🔴 **停止修复尝试**，按 gate-handling §2 记账后 `python3 ../a2h-spec/scripts/gate_ledger.py release` 解除，继续 |
| 无条目 | ✅ 正常开工 |

路由不靠猜：每个 linter 比对两份产物，**哪一侧缺条目就由哪一侧负责**。责任无法机械判定时
（典型：AC 按当前描述实现不了），用决策卡上报——选项与 owner 的对应关系写死在卡里，避免推诿；
无人值守时取卡上「← 推荐」项，写 ledger（`approval_source: default-policy`）后继续。

**findings 只能由「原 linter 重跑后不再报」来关闭**，不能由任何一方声明「已修复」而关闭。

## 关键约束（Critical）

- **Stage 1 按根因处置**：项目 ledger 已批准时，Stage 1 任意闸门 FAIL/BLOCKED 先加载 [references/stage1-gate-policy.md](./references/stage1-gate-policy.md)。产物质量缺陷必须修，预算耗尽仍阻断；有证据的信息/环境/工具缺口按统一脚本累计有界恢复次数，耗尽后 RELEASE_WITH_GAPS，原闸仍未通过。根因未明不放行。本规则优先于 Stage 1 的通用未达标放行和 strict_wiring 一律拦截；其他 Stage 不变。
- **显式 strict_wiring 例外**：已批准的 `spec/execution/stage1-wiring-contract.json`（`policy=strict_wiring`）按 [references/stage1-wiring.md](./references/stage1-wiring.md)执行。清单冻结，词法 PASS 只表示静态通过；最终接线 PASS 仍须全部实际证据。失败按上条归因，部分验收完成或带缺口放行后均返回，不自动进入 Stage 2/3。
- **门禁失败处置（无人值守）**：Stage 1 已批准根因协议时使用上条；以下通用规则适用于其余情况。任何门禁 FAIL、轮次用完、连续未收敛、ESCALATED 超比例，按 [a2h-spec references/gate-handling.md](../a2h-spec/references/gate-handling.md) 处理——先查类别（`../a2h-spec/scripts/gate-registry.json`）：精确类（编译、`$r` 资源、自定义格式）必须修过，**编译门用完轮次是唯一停点**；推断 / 管线 / 环境类有限轮修复，修不掉记「工具缺口 / 未达标放行 / 阶段不可判定」放行继续。禁止改工具、改门禁报告、为迁就检测器改产物。本规则优先于正文里的「阻断 / 不允许进入 / 用户裁决」表述，派发的子代理同样适用。
- **执行铁律**：execute 按 `spec/decision-ledger.md` 查表推进、**不交互式追问**；未命中 → 按 `../a2h-spec/references/default-policy.md` 或决策卡推荐项裁定，写 D 编号（`approval_source: default-policy`）后继续，同时在迁移报告「决策缺口」段登记供事后复核（gate-handling §5）。启动先 Read 项目指令文件（宿主别名 `PROJECT_INSTRUCTIONS_FILE`：Claude Code=项目根 `CLAUDE.md` / Codex=项目根 `AGENTS.md`）+ ledger 顶部「决策索引」段（status 须 `approved`；正文按需 grep D-编号，不整份吞全文）。
- **Stage 0 UI 前置产物与资源校验最先跑**（§3.0，HARD-GATE）：校验目标输入、资源事实和选定页面证据；全部 `$r(...)` 引用可解析或显式 MISSING_xxx 才进 Stage 1。可选静态 sidecar 缺失不阻断。
- **合法占位 = 已登记的 7 类 kind 占位**（§2.1）：命中规范 marker（`// FWD-REF:` / `// PLACEHOLDER:` / 已登记 `// TODO:` / 资源 `[TODO: translate]`）**且** registry 6 字段齐全；未登记 / 自由文本（裸 `// TODO`、空回调、空 try-catch、假 `console.info('TODO')`、prose defer）一律 FAIL。§2.1 列 3 大延迟**归属**类（owned task / placeholder / 禁止自由文本），placeholder 一类内部细分 7 类 kind（含无代码 marker 的 registry-only 类 `deferred-work`）。
- **共享文件单写者纪律**（Stage 1 §3b-bis / Stage 3 §5a）：并发 converter / slice worker **只写自身 page/VM/repository 文件**，共享文件禁碰（`feature-plan.md` 等 plan 产物、跨文件接线），**仅两项 append-only 例外**——① `placeholder-registry.md` 登记行 append（§2.1c 发号协议）② 共享资源 JSON 直写（写前 Read + 只 append 缺失键，纪律见 `_common.md`）；跨文件接线与状态账本回写一律由 **Batch 收尾 subagent** / **group-closer** 唯一作者（账本变更经 **writeback manifest** 由主线程 `apply_writeback.py` 落盘，§3b-bis 协议），收尾者对资源只做**残量兜底 + 只读校验**（冲突由编译门自曝）。
- **编译闭环**：**Stage 1 页面批次与 Stage 3 各 group 内均无编译**（批内 / 组内零编译依赖，收尾 subagent 不调 `hmos_fix_build_errors`）；S1-V 若要启动当前页面，允许单独派一次 `hmos-builder` 生成带来源的验证 HAP，但它不替代正式门。正式三道门仍全部派 Agent `hmos-builder`——Base-7（§4d，Stage 1+2 首道门，失败阻断后续全部 Slice）/ Stage 3 集中门（§5f）/ FV-2 终态全量编译（§6 之后）。**主线程禁止直接调底层 build skill**。
- **结构性验证 = `Skill({skill: "arkts-structural-closure", args: "mode=<stage|group|pipeline> target=<...>"})`**（§3c-bis stage / §5e group（含 size-1 组）/ §6 pipeline）：**禁止 grep / 自跑 scripts 替代**。中间步骤看 skill 返回的 verdict 即可；**§6 收尾 evidence 必产 brief 文件**，缺失不允许进 a2h-verify。
- **接线完成性机械判定**（§5e 配套）：plan 产物（索引 + slice 文件）只读、零回填——完成性由 verify_slice_wiring.py C2 按结构化对从代码直接判定（调用方页面存在 + handler 已接 + target 被实例化，孤儿 VM 防线不变；完整契约见 §9a）。
- **References / Templates 强制加载**（HARD-GATE）：body 中所有 `[references/X.md]` / `[templates/Y.md]` 引用，在对应步骤执行时**必须** Read 被引文件作为执行规范，不得仅靠 body 摘要执行（占位禁令 / FWD-REF 规则不得简化）。**派发 prompt 已按段拆分**：`references/agent-prompts/` 下 `1-converter.md` … `8-group-closer.md` 每个是对应派发点的完整模板，派发时 **Read 对应单段文件 + `agent-prompts/_common.md`（公共占位规则）即可**——**不要整份加载所有段**（旧单文件 413 行已废，索引见 `references/agent-prompts.md`）。跳过加载 = PROCESS_VIOLATION。规则适用于 LLM 主线程和派发的 subagent。

---

## 1. 定位

Pipeline 层第三步，**三阶段执行引擎**。读取 a2h-plan 生成的双计划（ui-plan.md + feature-plan.md），按三阶段顺序执行迁移。

```
a2h-spec → a2h-plan → a2h-execute（本 skill）
                          │
                          ├─ Stage 1: 页面迁移与最小接线
                          │   └─ 资源与快照校验 + 页面转换 + 接线 + 按交付契约执行双端对比
                          │
                          ├─ Stage 2: Feature Base
                          │   └─ a2h-migration-worker × Base 任务
                          │
                          └─ Stage 3: Feature Slices（按 parallel_group 批粒度）
                              └─ 组内 slice worker 并行 → group-closer（接线+资源校验+结构 fix-forward+brief；无编译）→ 主线程仅处置冒泡
```

**核心原则**：a2h-execute 是编排层。Stage 1 消费前置 UI 事实，通过 `a2h-activity-converter` 迁移页面、通过 `a2h-migration-worker` 完成选定接线；已有可用页面产物则复用。Stage 2/3 的功能实现通过 `a2h-migration-worker` agent 委托。

---

## 1.1 执行铁律 — 决策来源与禁止交互

**用户选择例外（1030 冒烟模式）**：S1-V 的执行 / 跳过由用户明确选择，不属于技术歧义的默认裁定范围。已有本次运行选择则复用；缺失时仅在 S1-V 收口点询问并等待，不由 default-policy 代选。本例外优先于无人值守规则，其他门禁分类处置保持原契约。完整 UI 模式的 Plan 已批准 visual_policy=required，执行 S1-V 并保留失败/阻断，不能将无人值守放行当成验收 PASS。

execute 期歧义已清零，本阶段只**按决策推进、不再交互式追问**。事实源 = `spec/decision-ledger.md`。遇范围 / 技术替代 / UX 行为差异 / 工程配置 / 数据策略类判断、或与 plan/spec 冲突、或既有段落写有「提示用户三选一 / 除非用户指定 blocking / 要求人工补 plan」等交互动作时，**必先 grep ledger 对应类目**：命中 → 按之执行**严禁询问**；**未命中 → 按 default-policy / 推荐项裁定并写 D 编号（`approval_source: default-policy`）后继续**，同时把缺口写入 `spec/migration-report.md`「决策缺口」段、**严禁交互式追问**；ledger 与他文档冲突 → ledger 优先。
完整 HARD-GATE 规则 + **启动必读**（先 Read 项目指令文件 `PROJECT_INSTRUCTIONS_FILE` + `decision-ledger.md` 决策索引段，校验 `status=approved`，正文按需 grep）+ 决策缺口 schema + 与各段落关系表 → **MUST READ** [references/execution-discipline.md](./references/execution-discipline.md)。

---

## 2. 输入

自动读取 `spec/baseline/plans/` 下已审批的功能计划，并读取 `spec/baseline/` 下的 UI 前置产物：

| 文件 | 用途 | 消费阶段 |
|------|------|---------|
| `spec/baseline/plans/ui-plan.md` | 页面批次与输出映射；已有可用页面产物可复用，否则按批派发 converter | Stage 1 |
| `spec/baseline/plans/feature-plan.md` | **L1 调度索引**（`plan_format: indexed-v1`）：Base 层 stub + 按 Group 分节的 slice 头部（每组末尾 group-closer 插入行）+ detail 指针；主线程只读索引 | Stage 3 |
| `spec/baseline/plans/base-plan.md` | **Base 层任务正文**（索引 stub 的 detail 指向处；旧 plan 无此文件时回退读 feature-plan.md 旧 Phase 0 段） | Stage 2 |
| `spec/baseline/plans/slices/slice-NN-<fid>.md` | **L2 逐 slice 只读调度账本**（接线账本）；**worker 派发直接给文件路径，不读索引** | Stage 3 |

启动时检查：
- `spec/baseline/plans/` 目录是否存在
- `ui-plan.md`、`feature-plan.md`、`base-plan.md`（或兼容旧 plan）是否存在
- 沿用 Spec 本次运行的 ui_facts_policy（默认 legacy）；仅 static-v1 要求 `spec/.a2h/target-input.json` 和 canonical `spec/baseline/res-index/`，并校验该模式的 Gate B。legacy/static-v1-shadow 按原资源迁移流程执行，不要求新索引，也不消费 shadow 目录。
- 功能计划不存在或为空时回到 a2h-plan；资源输入按所选模式在 Stage 0 校验和落地，不把 legacy 未生成的新索引列为缺失。
- feature-plan.md 无 `plan_format: indexed-v1` / slice 段无 `detail:` 指针（旧 monolith）→ **阻断**，重跑 a2h-plan 升级布局（管线类 `execute.plan-format`：无人值守时自动回到 a2h-plan 重跑一次，仍不是新布局按 gate-handling 记「工具缺口」）（执行进度存于 ui-manifest / feature-index / brief，重排零损失）
- 启动时创建 `spec/execution/{briefs, source-understanding, conversion-reports}` 目录——执行域过程记录落点，由 execute 拥有（brief = 阶段小结，旧称 handoff；SESSION-HANDOFF / `// HANDOFF:` 责任移交 marker 不受此改名影响）
- **contract_mode 检查**：若存在 `spec/.a2h/pipeline-state.json`，读其 `contract_mode`（`legacy|shadow|v2`）；文件或字段缺失 → 按 `legacy` 运行（即现行为）。`spec/.a2h/` 下存在其他 v2 残留文件**不改变行为、不作为输入**（mode 只认 pipeline-state.json 显式声明）。**例外**：evidence-coverage 家族（`open-findings.json` / `requirements-index.json` / `plan-coverage.json` / `impl-claims.json` / `verification.json`）**独立于 contract_mode 始终生效**，不属本条「残留」范围

辅助文件（执行过程中读取）：

| 文件 | 用途                                               |
|------|--------------------------------------------------|
| `spec/baseline/ui-manifest.md` | 页面状态追踪（pending/converted/verified）               |
| `spec/baseline/feature-base.md` | Base 层公共能力定义                                     |
| `spec/baseline/features/F-xxx.md` | 各功能详细 Spec（complex 的 AC 带二型锚点：`源→标` parity / `决→标` 平台差异，worker 一律以 `标` 定位实现落点；`决:` 锚的行为契约查 decision-ledger） |
| `spec/baseline/ui/page_NNNN.md` | 各页面详细 UI Spec                                    |
| `spec/placeholder-registry.md` | 占位符注册表                                           |
| `spec/baseline/cross-module-contracts.md` | 多子仓专有：跨模块 seam 语义契约，跨子仓调用的权威依据                   |
| `spec/baseline/module-dep-graph.json` | 多子仓专有：被依赖子仓的接口签名桩                                |

---

## 2.1 延迟 / 待接工作分类法（贯穿全 Stage）

| 类别 | 适用                                                           | 归属机制                                                             | 闭环 gate                                                                 |
|---|--------------------------------------------------------------|------------------------------------------------------------------|-------------------------------------------------------------------------|
| ① **owned task** | 接线 / 集成工作（**首选**）                                            | 某 Slice 的 Step 3d/3e 页面接线                                        | Step 3d/3e 接线闭环维度（§5e）                                                  |
| ② **placeholder** | 指定后续 Slice 的代码桩 / 三方 SDK / 资源占位 / 不确定区域                      | placeholder-registry 5 类 `kind` 枚举                               | trigger_condition 满足 → resolved（§5e / §6） |
| ③ **deferred-work（并入 ②）** | 既非接线 task 又非代码桩的**残余**（如 `module.json5` 配置、需另一 skill 的工作） | **registry 登记 `kind=deferred-work`**（§2.1c 发号；registry-only 行，免代码 marker；`resolve_by`=归属步骤 或 `trigger_condition`=白名单闭环条件） | 债务终结闸机械对账（依赖工件缺失 / resolve_by 到期未清 → FAIL；open → WARN）；残余工作**未登记 registry** → Slice `BLOCKED`（§5e）                                       |
| ④ **自由文本「已知不完整」** | ——                                                           | ——                                                               | **禁止**——§3c-bis 骨架审计扫到「由 verify / fixer / 后续接通 / a2h-fixer 完成」等措辞即 FAIL |

**marker 形态约定**（一切 marker 必先登记 registry 6 字段，未登记一律 FAIL）：

- `// FWD-REF: <P-ID> resolve_by=...` — `kind ∈ {forward-ref, resource-pending-asset}`；`// PLACEHOLDER: <P-ID> trigger=...` — `kind = thirdparty-sdk`（两者**不含 `TODO` 字样**）
- `// TODO: <description>` — `kind = forward-ref-uncertain`；`console.info('TODO:<ACTION>:<COMPONENT>')` — component-builder L3 签名占位专用
- 资源 JSON `"value": "[TODO: translate] ..."` — `kind=resource-pending-translation`
- **无 marker** — `kind=deferred-work`（registry-only 行：残余延迟工作无代码落点，登记即形态；location 填受影响文件）
- 未登记 TODO / 空回调 / 空 try-catch / 未注册 `[TODO: ...]` → FAIL

---

## 3.0 Stage 0: UI 前置产物与环境校验（HARD-GATE，必须最先执行）

**env-prewarm（与 Stage 0 并行，后台 1 个 subagent）**：Stage 0 起跑的同时派发，一次完成 ① env-doctor（read-first 只补缺：local.properties 已有有效 `hwsdk.dir` 即跳过）② 依赖解析（ohpm install / hvigorw --sync）③ daemon 预热（assembleHap）——细则复用 `hmos_fix_build_errors` 环境段。**预热构建结果丢弃：不 gate、不修复、不记录**（与 Stage 0 产物校验并行可能产生假编译错，无视）。此后全程禁冷启，首编（Base-7）即热 daemon。

完整流程 **MUST 加载** [references/stage-0-resources.md](./references/stage-0-resources.md)。按本次 Spec 的 ui_facts_policy 分流；仅 static-v1 再加载 [references/resource-facts-handoff.md](./references/resource-facts-handoff.md)，不从磁盘残留文件推断启用新模式。

static-v1 读取 `spec/.a2h/target-input.json`、`spec/baseline/res-index/` 和该模式的 Gate B findings；legacy/static-v1-shadow 沿用 Base-0 扫描源码及已审批 Spec、批量转换资源和 resource-mapping 的原流程，不要求新索引。页面的 `visual.json` / `fixture.json` 若存在则作为增强输入，不存在不阻断。static-v1 校验目标身份、schema、输入 hash 和资源事实并消费 `usage.json`；legacy/shadow 扫描已审批资源引用；两分支均调用资源转换并写入 `entry/src/main/resources/` → 运行资源保真检查 → 自动派 `arkts-app-identity`（`scope=dev-identity`）落地 app_name / versionName / 图标（**跳过 bundleName / vendor**，属部署期 D-009、与签名 / AGC 强绑定）。**app_name 输入源仍以 init 锁定值优先**。校验和资源落地通过后进入 Stage 1。

---

## 3. Stage 1: UI Pipeline

**先确定交付契约**：Plan 的 `stage1-ui-delivery.json` 声明 `delivery_contract=full-ui-v2`（schema 2）时，
本轮进入**完整 UI 交付模式**，MUST READ [references/ui-integration-1030.md](./references/ui-integration-1030.md)、
[references/ui-delivery-contract.md](./references/ui-delivery-contract.md) 和 [references/layout-fidelity.md](./references/layout-fidelity.md)。
按该模式完成组件/状态生成、全量 G0、统一装配/G1、构建与强制 S1-V，再进入 Stage 2；以下按 Batch/冒烟路径的旧流程不再执行。
S1-V 只保接线、跳转和关键显示，按 ui-delivery-contract.md「视觉修复」与「S1-V 编排」执行：差异分 critical/normal/只记录三档，
第 1 轮修 critical+normal、第 2 轮只修 critical；修复后只重采受影响单元、其余沿用并以整包冒烟收尾；比较报告由 `stage1_visual_report.py` 生成。
`visual_policy=required` 是 Plan 已批准的本次选择，不在收口时再次提供跳过项。
没有该清单时，沿用以下 1030 冒烟/Preview 契约及其 S1-V 用户选择，不把旧流程的 SKIP 记成完整 UI 交付通过。
两种模式共用 1030 的导航、资源、门禁分类、实际构建/安装/到达验证；完整模式另有严格状态分母和验收结果。

> **前置依赖**：资源前置阶段已经完成，并将资源映射和资源文件写入约定目录。Stage 1 不再执行资源转换；双端运行验证由后续验证阶段负责。

Stage 1 固定分为三个子阶段：

```text
S1-R 资源前置产物校验（只读）
  ↓
S1-G 批量页面迁移
  ↓
S1-W 最小可运行接线
```

Stage 1 不重新采集 Android 基线；这些事实由前置阶段写入 `spec/baseline/`。S1-W/S1-P 收口后提供可选的 S1-V 验证钩子；仅在用户选择执行时：启动 HarmonyOS 设备，安装当前 Stage 1 产物，按 wiring manifest 只走已接线页面，获取 HarmonyOS 截图并与已有 Android 对应 baseline 比对。S1-V 委托 `arkts-visual-verify`，不复制第二套采集器；完整页面遍历和修复循环仍由后续 `a2h-verify` 发起。

### 3a. S1-R 资源前置产物校验（HARD-GATE）

资源事实由前置阶段完成；execute 按 handoff 契约消费事实并完成目标资源落地。S1-R 只校验 Stage 0 的资源闭包和保真结果。以下事实索引仅 static-v1 必需；legacy/static-v1-shadow 使用 Stage 0 原流程的 resource-mapping 和目标资源：

```text
<harmony_project_dir>/spec/.a2h/target-input.json
<harmony_project_dir>/spec/baseline/res-index/values.json
<harmony_project_dir>/spec/baseline/res-index/drawables.json
<harmony_project_dir>/spec/baseline/res-index/usage.json
<harmony_project_dir>/spec/baseline/res-index/design-tokens.json
<harmony_project_dir>/entry/src/main/resources/
```

static-v1 缺少事实索引或该模式的 Gate B 仍有 blocking finding 时阻断；所有模式资源闭包未落地或保真检查失败时按门禁分类处置；不得从截图或模型记忆创建替代资源。Stage 0 的完整校验规则见 [references/stage-0-resources.md](./references/stage-0-resources.md)。

### 3b. S1-G 批量页面迁移

1. 读取 `ui-plan.md` 的页面批次与本次 ui-capture-policy。派发前按 [runtime-snapshot-handoff](./references/runtime-snapshot-handoff.md) 运行 `validate_runtime_snapshots.py --project-root <project> --pages-file <batch.json> --ui-facts-policy <沿用 Spec 的模式>`：runtime_required 要求审计后的真实 PNG/XML/SHA256；source_only 允许有 meta、源码来源与 synthesized view.xml 的低 confidence 页面；progressive 只对 meta 已有 fallback_reason 的合成页放行。不得要求这两类兜底页提供不存在的截图。`visual.json/fixture.json/facts-manifest.json/visual-facts.md/view.static.xml` 均为可选增强产物，不以缺失阻断。
2. 页面 converter 优先消费前置阶段提供的真实截图、真实视图树和 meta；存在时再消费 `visual.json`、`fixture.json`、源码锚点和 `design-tokens.json`。真实运行时证据优先于合成 view；可选静态投影缺失时回退到 view、源码和资源索引，不得因为空转 sidecar 阻断。
3. 页面批次调用 `a2h-activity-converter` 生成 ArkTS；按 §3b-bis 由 Batch closer 产 writeback manifest，主线程 apply 回写账本。入口装配和结构审计在批次完成后的收口点执行。
4. 批次之间不编译，统一由 Base-7 编译门处理。

派发前 **MUST 加载** [references/stage1-dispatch.md](./references/stage1-dispatch.md)，保留 converter 的上下文加载、槽位控制、空信封重派和停滞回收规则。

每个页面必须保留 `meta.json`、`view.xml` 和源码来源；真实采集页另保留截图路径、`runtime_evidence`（多态使用 runtime_evidence_by_state）及其 SHA256。source_only/progressive 合成兜底页保留 synthesized 标记、较低 confidence 和适用的失败原因，不虚构截图；S1-V 仍只接受真实审计基线。页面生成失败、资源引用无法解析或 converter 返回非法占位时阻断该批次。

### 3b-bis. Batch 收尾与入口装配

**关键不变量**：`main_pages.json` 的 `"src"` 最终**只保留入口页一项**——NavDestination 子页面由入口页 `pageMap` 路由，不逐页登记（Navigation 模型与旧 router 模型的关键差异）。

完整分步流程（grep 特征 / 三联清理 / 字段读取来源 / Navigation 外壳模板）**MUST 加载** [references/entry-navigation-setup.md](./references/entry-navigation-setup.md)。

全部页面 Batch 完成后一次性装配正式入口：入口页加入 `main_pages.json`，同步 `EntryAbility.loadContent`，装配 Navigation 外壳与路由表，按 entry-navigation-setup 清理 Hello World 模板。Preview 使用 §3c 的受控入口，不替代正式入口。

以下协议用于 S1-G 每批收尾。

（per-Batch, HARD-GATE）

本批所有并发 converter 完成后，派**一个**Batch 收尾 subagent（**`a2h-closer`，mode=batch**——收尾协议单源固化于 agent 定义；派发参数模板 **MUST 加载** [references/agent-prompts/2-batch-closer.md](./references/agent-prompts/2-batch-closer.md) + [_common.md](./references/agent-prompts/_common.md)）。该 subagent 是本批 **brief 与账本变更的唯一作者 + 资源残量兜底者**（converter 已按 `_common.md` 直写纪律 append 资源键；收尾只补漏不重写），依次串行三步（**批内无编译**——页面间零编译依赖，统一编译在 Base-7）：

1. **资源 sweep（残量兜底，只读校验为主；`scripts/sweep_resources.py`）**：grep 本批生成/改动的 .ets 全部静态 `$r('app.<type>.<name>')` 引用（**完整性来自 grep 穷举，不依赖 converter 申报**），与 `resources/` 比对解析性，并校验被引用的 SVG 能否在鸿蒙渲染（`invalid_svg`：命名空间带前缀、残留未解析的安卓引用等；`--fix-svg` 做无损修复）→ 仍缺失的（converter 直写漏网），调 `android2hmos_resources_convert` 扫 Android 源补齐 → 仍无源写 `MISSING_xxx`（复用 Stage 0 契约）。
2. **源布局尺寸复核（只读；`scripts/layout_dims_gate.py`）**：查本批页 `meta.json.layout_sources` 里写死的 dp/sp 值是否落进页面代码或转换报告「尺寸偏差」段；FAIL 页记入信封 `layout_dims_fail[]`。主线程在 apply 之后对这些页各重派一次 converter（只附该页 gate 输出）；仍 FAIL 按 gate-handling 记一条「未达标放行」（门禁 `execute.layout-dims`，同批多页合成一条、剩余 FAIL 列页号），不阻断——这样它们会出现在报告首屏和 a2h-verify 重点核实清单里。
3. **产 writeback manifest**：本批页 `pending → converted` 记入 manifest（结算即翻——converted = 转换产出完成）；起草 batch brief 全文（schema 见 [references/brief-schemas.md §1](./references/brief-schemas.md)，只写结构化字段）+ 账本翻转集合，一次写 `spec/execution/writeback/writeback-batch-NN.json`（schema：brief-schemas §4）后 return——closer turn 内**不直写** brief / 账本。

**writeback 协议（三模式通用，§5e/§6 同此）**：closer 返回后主线程跑 `python3 <a2h-execute>/scripts/apply_writeback.py <manifest> --project-root .`——确定性落盘 brief + 翻账本（registry / ui-manifest / feature-index），幂等可重放；**崩溃恢复 = manifest 在则重跑 apply，绝不重做接线 / 结构收口**。closer 仍是全部账本变更与 brief 的**唯一作者**，脚本只是落盘手。

**HARD-GATE**：writeback manifest 必产 + apply 成功才进入下一 Batch（**批间无编译门**）；manifest 缺失 → closer 重产；apply 报错 → 重跑一次（幂等），仍失败属管线类（`execute.writeback`），按 gate-handling 记「工具缺口」继续，manifest 留盘供修复后重放。

### 3c. S1-W 最小可运行接线

存在已批准 strict_wiring 契约时，用其必需清单扩展本节的最小范围：主壳全部 Tab 和选定二级页的内容挂载、本地点击均需完成；验收与修复协议见同一 wiring reference。仍复用既有页面与有来源的展示数据，业务网络/SDK 不在本次接线范围。

S1-W 只接通一条经过批准的正式页面冒烟路径，不提前实现完整 Feature Slices；正式入口暂时接不上的页面转入 S1-P Preview 接线。完整执行契约见 [references/stage1-wiring.md](./references/stage1-wiring.md)，执行时 MUST 加载。

- 入口链至少包含一个真实启动路径（例如 `Splash → Front → Main`）。
- 主页至少填充一个选定 Tab 或内容槽位，并接通一个代表性详情页。
- 页面需要动态内容时补最小正式 ViewModel；存在 `fixture.json` 时可将其作为带来源的 `preview-fixture`，缺失时必须回到源码/运行时证据或登记待补数据，不得用无来源的硬编码业务成功数据。
- 只接通本单元所需的本地点击、状态切换和页面跳转；支付、广告、登录、完整网络链路和其他 Slice 保持 registered/pending。
- S1-W 收口时运行 `scripts/stage1_reachability.py --project-root <project> --wiring-manifest <manifest> --output-json spec/execution/stage1_reachability.json` 生成 `spec/execution/stage1_reachability.json`；选定 wiring manifest 中的目标文件不可达时阻断，未选页面可保留 `skeleton_ready`。
- S1-W 使用 `a2h-migration-worker` 施工、`arkts-structural-closure` 做结构审计；完成事实写入 `spec/execution/briefs/stage1-wiring.md` 和结构化 wiring manifest。
- S1-W 完成状态为 `smoke_wired`，不等价于 `business_ready`；S1-P 在无设备验证时为 `preview_prepared`，同样不等价于业务完成。两者选择进入 S1-V 时只验证页面可见性和 UI 对齐，不宣称业务链路完成。

#### S1-P Preview 接线（页面可见性兜底）

当页面代码已生成，但正式入口、业务容器或真实 provider 尚未接通时，允许为该 `page × state` 创建受控 Preview 入口。Preview 只负责展示正式页面组件和有来源的 `preview-fixture`，不改变正式导航语义、不声明业务完成，双端对比仅在用户选择 S1-V 时执行。

- 使用固定 `page_id + state_id + fixture_id` 启动目标页面；不得临时修改 `Index.ets` 或复制一套截图专用页面绕过接线。
- Preview 使用正式页面组件、正式 ViewModel/fixture adapter 和共享组件；验证入口只能在 Preview 包或受控验证配置中启用。
- Preview 无法解析正式页面、实际使用的 provider/adapter 或关键依赖时，页面保持 `skeleton_ready` 并登记阻塞；不能用空回调、无来源硬编码或假业务成功强行变成 `preview_ready`。
- Preview manifest 使用与 S1-W 相同的 `pages:[{page_id,state_id,output_file}]` 绑定；冻结后运行 `scripts/stage1_preview.py`。无回执为 `preview_prepared`，真实构建/安装回执分别只证明 `preview_buildable` / `preview_installed`；实际确认目标页显示才可记 `preview_ready`。
- `preview_ready` 只表示页面可通过验证入口显示；`business_ready` 仍必须由 Stage 3 真实 provider、业务事件和正式入口完成。
- 完成后运行 `stage1_reachability.py` 和结构审计，产出 `spec/execution/briefs/stage1-preview.md`；不派发 `a2h-verify`。

### 3c-bis. 骨架审计 gate



按各 Stage 的收口时点**调 `Skill({skill: "arkts-structural-closure", args: "mode=stage target=<1|2|3>"})`** 做骨架兜底：Stage 1 在无编译条件下先做静态结构审计；Stage 2/3 在各自集中编译门 PASS 后执行。绝大多数情况 0 findings 直接 PASS；CONTINUE 时按 dispatch_prompt 派 repair worker 修后重调，≤ 2 轮仍 CONTINUE → BLOCKED。BLOCKED 后，Stage 1 先按 stage1-gate-policy.md 区分真实产物缺陷和前置/工具缺口；其他 Stage 按 gate-handling 处置：精确类子类型（naked-TODO / throw-stub / dangling-fwd-ref / 资源占位未登记）必须修过；推断类子类型（fake-content / empty-body / orphan-vm）记账放行。

Stage 3 末尾自动启用 L4.dangling-fwd-ref 检测。
### 3d. Stage 1 完成标志

所有 S1-G 批次和批准的 S1-W/S1-P 单元完成后：入口装配或 Preview 入口 → 最小接线 → §3c-bis 结构审计 → 输出页面与 wiring 统计。结构审计使用 `--scope slice --scope-files <Stage 1 页面与组件文件及所选 wiring 单元文件>` + 全部 `batch_NN_brief.md`，不按 git diff 划界；FAIL 按 §3c-bis 分类处置。未纳入接线单元的页面标记为 `skeleton_ready`，无设备证据的 Preview 页面标记为 `preview_prepared`，不能声称已完成业务接线。

Stage 1 页面生成批次仍不编译；S1-V 需要当前源码的可安装 HAP 时，调用 `hmos-builder` 产出一次带来源的 Stage 1 验证包，该构建不替代 Stage 2 Base-7 编译门。S1-V 完成或用户明确跳过后，Stage 2 Base-7 仍按原契约执行，完整双端验证和修复循环仍由后续 `a2h-verify` 独立发起。

#### S1-V Stage 1 双端视觉检查（可选）

**严格接线分支先行**：若命中 strict_wiring 例外，先执行 wiring reference 的「静态检查 → S1-W 修复 → 单次编译/安装 → 设备冒烟」闭环。它不依赖 Android 截图，不能被下方视觉 SKIP、缺 baseline 或 `fix=none` 跳过。接线通过后，原视觉比较仍按下方流程单独记 PASS/DIFF/visual_blocked。用户说「只重跑接线验收」时，设备冒烟完成即返回，不派发视觉比较或 Stage 2/3。

S1-W/S1-P 收口后，先读取本次运行已有的用户选择；未明确选择时询问：“Stage 1 已完成，是否现在启动鸿蒙设备，对已接线页面做双端截图对比？执行 / 跳过并继续 Stage 2。”等用户回答，不默认执行，也不因未回答提前记为跳过。

- 用户选择执行：按下述流程构建、安装和比较；结果写入当前 Stage 1 brief 的 `stage1_visual_check`（choice=run，status=PASS|DIFF|visual_blocked）。
- 用户选择跳过：在同一 brief 记 choice=skip、status=SKIP、reason=用户选择；不运行 scope/gate、启动设备、构建验证包或读取历史比较报告，直接进入 Stage 2。SKIP 不表示验证通过。
- 断点续跑复用本次运行的选择；用户可明确更改。S1-V 的选择不替代后续 a2h-verify 的检查项选择。

以下步骤仅适用于 choice=run。

先运行 `scripts/ui_stage1_gate.py --project-root <project> --wiring-dir spec/execution/wiring --output-json spec/execution/ui-stage1-gate.json`，按 manifest 的显式 page/state/output_file 检查输出与依赖，FAIL 先修缺口；Tab/Image regex 只记 WARN，不因命名猜测硬阻断。然后运行 `scripts/stage1_visual_scope.py --project-root <project> --wiring-dir spec/execution/wiring --out spec/execution/stage1-visual-scope.json`，收录 smoke_wired 与已准备的 Preview，排除 skeleton_ready/未选项。scope 的 Android 路径来自已审计 snapshots meta，逐 state 对账；不按两个独立数组猜配对。

```text
Skill({ skill: "arkts-visual-verify", args: "scope=stage1_wired scope_manifest=spec/execution/stage1-visual-scope.json mode=capture_compare fix=none" })
```

验证器必须确保当前 HarmonyOS 源码已构建并安装到目标设备（不得拿旧 HAP 截图），自动启动或复用 HarmonyOS 模拟器；Android 侧只复用 scope 内解析出的审计后 `android_png/android_xml` 路径及 SHA256，缺 baseline 直接阻断该页；HarmonyOS 侧在 `spec/execution/stage1-visual/<run_id>/` 按本次准备报告截图并立即 resize，随后执行截图和 UI dump 配对比较。结果写入 `spec/execution/stage1-visual/`，至少包含 manifest、每页截图引用、Android/HarmonyOS 配对关系、比较 verdict 和阻塞原因。

S1-V 只验证已接线或准备齐备的 Preview 页面，不启动 visual-fixer、不修改 `.ets`、只对真实确认显示的 Preview case 记录 `preview_ready`，不把任何页面改写成 `verified`。任一页面无法启动、安装、到达或缺 Android baseline 时，Stage 1 收口为 `visual_blocked`，不能静默跳过；该执行分支 PASS，或 DIFF 已向用户呈现并明确后续处理，或按 visual_blocked 升级后才进入 Stage 2。用户明确改选跳过时保留失败记录并记 SKIP，按跳过分支继续。

---

## 4. Stage 2: Feature Base（水平基础设施）

> **前置依赖**：Stage 0 UI 前置产物校验、Stage 1 导入已完成，且 S1-V 已通过、用户明确跳过（SKIP）、DIFF 已呈现并明确后续处理或已按 `visual_blocked` 升级。本阶段直接从 Base-1 开始。

Stage 2 读取 `plans/base-plan.md`（索引 Base 层 stub 的 `detail:` 指向处）的 Base 层任务（Base-1..Base-7），按 `parallel_group` 分组执行公共基础设施建设。旧 plan 无 base-plan.md → 回退读 feature-plan.md 旧 Phase 0 段（兼容层）。

### 4a. 执行流程

读 `plans/base-plan.md`，按各任务 `parallel_group` 编排派发 `a2h-migration-worker`：**组内任务在同一条消息里一次派出并行，组间串行**，上一组全部 PASS 才起下一组（默认组 1 = Base-1 Models；组 2 = Base-2 Database ∥ Base-4 Events ∥ Base-5 Preferences ∥ Base-6 公共组件库；组 3 = Base-3 Network；末组 = Base-7 编译验证，派 hmos-builder §4d）。Base 层的组无 closer，组末只有 Base-7 这一道正式编译门。UI 页面已由前置产物导入，不再与 Base 任务重叠派发；**Base-7 的 join 条件 = Stage 1 §3d + S1-V 收口完成（PASS、用户选择的 SKIP、DIFF 已呈现并明确后续处理，或明确 `visual_blocked` 已升级）∧ Base-1..6 全部 PASS**。Stage 1 的槽位调度见 references/stage1-dispatch.md；Base 在 S1-V 收口后按本节调度。

### 4b. Agent 派发方式（Stage 2/3 通用）

Stage 2 和 Stage 3 的 **codegen worker** 统一使用 `a2h-migration-worker`；**收尾** `a2h-closer` 仅 batch / group / final 三模式（§3b-bis/§5a/§6）——Stage 2 末尾由 hmos-builder + 骨架审计收口，**不派 closer**：

完整 Base worker prompt **MUST 加载** [references/agent-prompts/3-worker.md](./references/agent-prompts/3-worker.md) + [_common.md](./references/agent-prompts/_common.md) 作为派发模板（占位禁令 / FWD-REF marker 规则等**不得简化为 body 摘要**）。**派发 prompt 禁复述** agent 定义 / _common.md 已载纪律（单写者 / 占位禁令 / 信封等）——一行指针即可、稳定内容走 MUST-Read 通道；但**任务专属 scope（锚点 / 契约差异 / 文件清单）不得省略**——瘦身只砍跨派发不变内容。占位 / 前向引用规则：合法占位遵循 §2.1（已登记的 5 类 kind）；worker 阶段常用——Base signature 桩登记 `kind=forward-ref` + `resolve_by=Slice {N} Step 3c`；**skill 库未覆盖的三方 SDK** 登记 `kind=thirdparty-sdk` + `trigger=<业务类别> SDK 入仓`（已有适配 skill 的 SDK 直接走 task suggested_skills，不进 registry）；fallback 资产登记 `kind=resource-pending-asset`。每个占位 6 字段齐全；未登记 TODO / 假 console.info / 空回调一律禁止。

### 4c. Base 层任务详情

任务内容与 `suggested_skills` 的权威 = `plans/base-plan.md` 各任务 stanza（本 body 不复述）。执行须知两条：**Base-6 公共组件库**是 Stage 3 全部 UI 工作的样式锚点（Design Tokens + 原子/复合组件，Stage 3 必须引用）；**Base-7** 派 Agent hmos-builder（CALLER=a2h-execute, STAGE_HINT=stage-2-base-7）。

### 4d. 编译检查点（per-phase）

> 编译派发 + placeholder 回填完整流程与**构建操作纪律**（cache / checkpoint / CLI→IDE 降级）**MUST 加载** [references/build-loop.md](./references/build-loop.md)——纪律注入所有构建 subagent 的派发 prompt。

Stage 1 §3d 收口完成且 Base 层所有任务完成后（Base-7）：

1. **派发 Agent `hmos-builder`**（CALLER=a2h-execute, STAGE_HINT=stage-2-base-7, ROUND=1，最多 20 轮自动修复）——这是 Stage 1 + Stage 2 的首道编译门，Stage 1 页面的真错在此一并修
2. agent 返回 BUILD_STATUS=PASS → **执行 §3c-bis 骨架审计 gate**（扫描范围 = Stage 2 git diff 改动的 .ets + `stage2_brief.md`，重点抓 Base signature 桩 `throw ...'Slice N'`）；FAIL 按 §3c-bis 末句处置（精确类修过才进 Stage 3）
3. 骨架审计通过 → Stage 2 完成，进入 Stage 3
4. agent 返回 BUILD_STATUS=FAIL（20 轮用完）→ 阻断（Base 层是所有 Slice 的前置依赖；编译门是 gate-handling 里唯一的停点），把 REMAINING_ERRORS 摘要写入 `stage2_brief.md` 与迁移报告

### 4e. Stage 2 brief（主线程直写，HARD-GATE）

每个 Base worker 返回后，主线程按 base-plan 该任务 `output:` 通配核对文件存在且非空 → 记入 `spec/execution/briefs/stage2_brief.md` 任务行（schema 见 [references/brief-schemas.md § 2](./references/brief-schemas.md)；主线程直写，不派 closer、不经 manifest）；缺文件 → 该任务 FAIL，原 prompt 重派一次。占位登记校验由 §4d 步骤 2 骨架审计覆盖。

<HARD-GATE>
任务行未 PASS → 下一组不启动；Base-7 编译未 PASS 或骨架审计有未修过的精确类 FAIL → 阻断 Stage 3 启动（推断类子类型按 gate-handling 记账后放行）。resume 判据 = 本 brief 任务行。
</HARD-GATE>

### 4f. Stage 2 完成标志

输出 Stage 2 统计（Base 任务 7 项成功/失败计数 / 组数 / 公共组件库组件数 / 编译状态——FAIL 阻断）。

**产 `spec/execution/base-contracts.md`（as-built 接口摘要，一页内）**：主线程从各 worker 信封 `generated_files` + grep 产出文件 `export` 行汇总——Base 各任务实际落盘的类名 / 公开 API / 常量 / 组件名。Stage 3 全部 worker 派发**传此指针、禁内联 Base 契约正文**（agent 读一次即前缀缓存命中；Base 冻结后基本不 stale）。

---

## 5. Stage 3: Feature Slices（垂直切片）

Stage 3 读取 `feature-plan.md` 的 Slice 任务，按拓扑排序逐功能执行。每个 Slice 内部有 4 个步骤（3a/3b/3c + 3d/3e 接线验证合一）。

### 5a. 执行流程

读 `feature-plan.md` **索引**拓扑排序后的 Slice 列表（主线程只读索引头部——账本在 slice 文件，worker 派发直接给 `detail:` 指向的文件路径），**worker 按运行时依赖驱动派发、closer 按 `parallel_group` 收口**（`parallel_group` 是 closer 的 checkpoint，不是 worker 的派发闸；类比 Stage 1 Batch 的「并发产出 + 单写者收尾」）。每个 parallel_group 三步：

1. **组内 worker 派发（每 slice 恒 1 个 worker + 长杆先行）**：组内按 pages_owned **降序**派发——最长链路最早开跑；每个 slice worker 跑 Step 3a/3b/3c + **自身页内**接线——派发模板 **MUST 加载** [references/agent-prompts/4-slice-worker.md](./references/agent-prompts/4-slice-worker.md) + [_common.md](./references/agent-prompts/_common.md)（3a–3d 一份 prompt，不得简化为 body 摘要）。**安全阀（判断式，默认不拆）**：编排者判断某 slice 明显过大（页数 / 锚点异常多）→ 可按**依赖断面**拆 2~3 个 worker（如 VM/model 层 ∥ service+接线层），文件集不相交、各自报信封，closer 照常收口；**禁止按 Step 3b/3c/3d 逐步拆 subagent**（步骤横切丢上下文、不买墙钟）。
   - 所有 worker 只写自身 scope 文件，禁碰共享文件（单写者纪律、两项 append-only 例外与 plan 产物只读契约见 agent-prompts/_common.md）。
   - 派发 prompt 附 `Base 契约: spec/execution/base-contracts.md`（§4f as-built 摘要）**指针，禁内联契约正文**。
2. **group-closer（单写者，1 个）**：本组 worker 全部完成后，派一个 group-closer（**`a2h-closer`，mode=group**——五步协议单源固化于 agent 定义；派发参数模板 **MUST 加载** [references/agent-prompts/8-group-closer.md](./references/agent-prompts/8-group-closer.md) + [_common.md](./references/agent-prompts/_common.md)；**末组**——索引 FV 前最后一个 Group——追加参数 `defer_structural_to_fv: true`，其结构验证由紧随的 FV-1 全工程扫描覆盖、免一次重复 group 扫描，中间组禁用）：跨文件接线（各 slice 的 cross_slice_edits + HomePage embed wires；registry 状态变更记 writeback manifest，plan 产物零回填）→ 资源 sweep → **组内无编译**（`build_status: deferred-to-stage3-gate`）→ 普通组执行**结构 fix-forward**（自调 `mode=group` + 自修 ≤3 轮直到 CONVERGED，非收敛才冒泡），末组 defer 分支跳过并记 `structural_verdict: deferred-to-FV` → 产 writeback manifest（group brief 全文 + 账本变更集合，主线程 apply 落盘，协议同 §3b-bis）。全工程编译仅由 §5f 的 `hmos-builder` 执行。
3. **主线程仅处置冒泡**：结构验证（`mode=group`）已合入 group-closer 自身 fix-forward（§5e）；主线程**只在 closer 回传 escalation（STALLED/REGRESSED/EXHAUSTED）时**介入——按 dispatch_prompt 派专家 repair worker（feat→worker / ui→converter） / 标 BLOCKED。

**编排规则**：
- **组容量约束**（计数口径与上限的权威 = a2h-plan Step 5，此处不复述）：plan 已据此拆分 parallel_group；execute 遇超限组可进一步拆分。plan 标注**附挂**的孤立 slice 搭宿主组的接线、资源与结构收口；编译仍只走 §5f 集中门。
- **组间 `depends_on`（运行时依赖驱动）**：slice worker **不等上游组 closer**——其 `depends_on` 列出的 slice 全部返回即可派发（并发上限沿用 §3a 宿主表）；closer 按组边界触发——**本组 worker 全返回即派，不等其他组**（组内无编译，故与在飞 worker 并行安全），closer 之间彼此严格串行。
- **同族子组（同数字前缀，如 2a/2b）**：worker 波**合并一波并行派发**（拆组只为控 closer 负载，互依为零由 plan 拆分规则保证）；closer 按字母序**链式串行**（C2a → C2b；共享接线与状态账本实行单写者，禁并行）。
- **group 内仅 1 个 slice** → 退化为「1 worker + 1 closer（=该 slice 接线 + 资源 / 结构收口 + brief；无组内编译）」。
- **`depends_on` 就绪判据**：被依赖 slice 的 worker 已返回且未标失败——其产出（类 / 服务）此刻已落盘，足够下游 codegen；跨组接线目标未定稿照常走 FWD-REF，由各自 closer 事后收口。

> **降级**：若某组共享文件耦合过紧、不宜并行，把该组**拆成按拓扑序串行的 size-1 组**——每组仍是「1 worker + 1 closer」，协议与执行者完全不变。group 编排是唯一执行路径，降级只改组的拆分粒度，不引入第二条协议。

**depth=stub feature 的按需升级**：派 slice worker 前先看该 feature spec 顶部 `depth` 字段。`depth: stub`（tier=peripheral，baseline 仅 3–8 条占位 AC）的 feature 在本 slice 真正执行时**就地升级**——补齐 standard 档深度（锚定覆盖率 ≥30%、穷举分支/常量/专属类 AC，对齐 a2h-spec Step C4.6c），更新该 feature spec 与 `source-coverage-report.md` 后再派 worker；**不回 a2h-spec 全量重跑**。`depth: full` 或字段缺失 → 直接执行，无需升级。

### 5b. Step 3a: UI 补充

主线程按 ui-manifest 中目标页面（**+ 子组件表内嵌子组件**）的 status 分支调度：

| status | 处置 |
|---|---|
| `converted` | 确认 .ets 存在，**不跳过 Slice**（接线移交 Step 3d——整体跳过是孤儿 VM 根因之一） |
| `pending` / 不在 ui-plan | ui-snapshots 存在 → 调 a2h-activity-converter；缺失 → 触发 §7 Phase A 按需模式；转换后 status→converted（group-closer 只收口、不编译；统一受 §5f hmos-builder 门约束） |
| `verified` | 跳过 |

UI 补充必须引用 Base-6 公共组件库（Design Tokens + 共享组件）。worker 改/加任何 UI（含 3b / 3d 新加的弹窗、浮层）前必读 `ui-migration-pitfalls.md`（派发参数 `references_dir` 同 Stage 1），信封回 `pitfalls_applied[]`。worker 同时承担 `forward-ref-uncertain` 二次审视（返回 `uncertain_regions_resolved[]/retained[]`，主线程据此更新 registry）——完整流程与占位禁令见 [references/agent-prompts/4-slice-worker.md](./references/agent-prompts/4-slice-worker.md) Step 3a 节。

### 5c. Step 3b: ViewModel + 状态管理（C7 三段式）

<HARD-GATE>
生成本切片 ViewModel。**complex 强制三段式**（源码理解 → 差异清单 → 实现，一次调用），simple 仅第三段；**anchors 经 `android_source_anchors_ref.source` 读 spec**（grep-first 定点消费，不整读源文件）；spec 已有『源码 5-role 摘要』时第一段只核对 + 产差异清单，source-notes.md 仅含差异清单；complex 必产 `spec/execution/source-understanding/{slice}-source-notes.md`。三段各自的判据（5-role 摘要含类名否则 FAIL / 二型锚点 `源:`·`决:` 落点规则 / `[真机]` 不豁免实现）见 [references/agent-prompts/4-slice-worker.md](./references/agent-prompts/4-slice-worker.md) Step 3b 节。
</HARD-GATE>

### 5d. Step 3c: 数据层接入

<HARD-GATE>
为该功能切片创建 Repository / Service、连接数据源，数据流 UI ← ViewModel ← Repository ← API/DB 闭环。完整任务清单（complex 的 source-notes 对齐 / impl: 指针精读 / **多子仓契约约束**）见 [references/agent-prompts/4-slice-worker.md](./references/agent-prompts/4-slice-worker.md) Step 3c 节。worker 报告的「决策缺口」由主线程按 §1.1 阻断。
</HARD-GATE>

### 5e. Step 3d 接线 + 3e 验证 + Slice brief（per-group，HARD-GATE）

> 3a/3b/3c（§5b/5c/5d）由组内 slice worker 跑；**3d 接线 + 资源 sweep + 3e 结构验证 + brief** 由本组 group-closer 统一收尾（**组内无编译**，首道编译门在 §5f）。**任意组大小同一协议**——size-1 组（串行降级 / 重试单 slice / 只执行 Slice N）同样适用。

<HARD-GATE>

**执行者（单一路径）**：slice worker 只做**自身页内** 3d 接线（[references/agent-prompts/4-slice-worker.md](./references/agent-prompts/4-slice-worker.md) Step 3d 节）；**跨文件 3d 接线 + 资源 sweep + 3e 结构 fix-forward + 组单文件 group brief 全部由 group-closer（`a2h-closer` mode=group）一手做完**（五步协议在 agent 定义；派发参数模板 [agent-prompts/8-group-closer.md](./references/agent-prompts/8-group-closer.md)）。**主线程仅在 closer 回传 escalation（STALLED/REGRESSED/EXHAUSTED）时介入**：派专家 repair worker（feat→worker / ui→converter）+ git rollback / 标 BLOCKED。

**不变契约（缺一即该 slice 标 BLOCKED、不 retry）**：
1. **3d 接线**：补 import + 实例化 ViewModel、grep `// FWD-REF:` marker 逐个换真实调用。**slice 文件只读，零回填**——接线完成性由 `verify_slice_wiring` C2 机械判定（对接点结构化对经 slice 的 `integration_points_ref` 顺链接从 feature spec 解析；判定 = 调用方页面存在 + handler 已接 + target 被实例化）；`resolve_by=本 slice` 的 forward-ref 必须全解除（marker 消失 + 真实实现存在）。
2. **3e 结构分支 + 非 loop 校验**：普通组须 structural CONVERGED；末组 `defer_structural_to_fv=true` 时允许 `structural_verdict=deferred-to-FV`，由 FV-1 全工程扫描接管。两分支都必须执行非 loop 校验：本 slice 前缀（grep registry `P-S{N}-`）的每个占位 P-ID 有对应 marker（**`kind=deferred-work` 为 registry-only 行，免 marker**）+ registry 6 字段 + trigger 白名单；complex slice 必有 `spec/execution/source-understanding/<slice>-source-notes.md`（差异清单）；残余延迟工作必须已登记 registry `kind=deferred-work`（含 resolve_by 或白名单 trigger），**未登记 → BLOCKED**。普通组 STALLED/REGRESSED/EXHAUSTED 处置见 `arkts-structural-closure` SKILL.md §3.3。
3. **Writeback manifest 必产**（`spec/execution/writeback/writeback-group-NN.json`，brief_content 含本组全部 slice 小节；schema MUST READ [brief-schemas.md §3/§4](./references/brief-schemas.md)；主线程 apply 落盘 brief——旧 per-slice `slice_NN_brief.md` 为 legacy 兜底，脚本双形态解析）
全契约 PASS（组内无编译——编译结论由 §5f 编译门给出）→ manifest 记 brief `final_state: PASS` + **本组解除集合**（`registry.resolve`——apply 翻 status=resolved、不删行；残留 marker 由 dangling-fwd-ref Class 2 直接 FAIL）。普通组同时记 **feature `pending → implemented`**（`feature_index.implemented`）；末组 defer 分支不记 implemented，等 FV-1 收尾后由 mode=final 补翻——FV-1 CONVERGED 时全组补翻；未收敛但已按 gate-handling 记「未达标放行」时也补翻，只剔除实现文件仍有 FV-1 剩余 FAIL 的 slice（`build_writeback.py` 意图带 `fv1_unconverged`，机械剔除）。**页面状态停在 `converted`——`verified` 是实测结论，唯一写者 = a2h-verify §6.1**。主线程 **apply 成功**（writeback 协议同 §3b-bis）后放行下一个 closer（下游 worker 已按运行时依赖自行起跑，不受本闸约束）。

</HARD-GATE>

### 5f. Stage 3 完成标志

Stage 3 全部 group-closer 收口后，派 Agent `hmos-builder`（CALLER=a2h-execute, STAGE_HINT=stage-3-gate, ROUND=1，最多 20 轮自动修复）——**这是 Stage 3 的首道编译门**（组内无编译，错误累积至此一次结清；file:line 反查所属 slice 记入统计）。编译 PASS + §3c-bis 一次性骨架审计通过后，输出统计（Slice 总数成功/失败 / 编译轮次与修复数），然后进入 **§6 Final Structural Closure（FV-1）→ FV-2 终态全量编译** → a2h-verify。

**收口前置不被编译替代**：ESCALATED 比例 = 当前 brief 中 ESCALATED 的 Slice 数（去重）/ 本次执行范围内 Slice 总数——不按 finding 条数或组数计算；>10% 时先按 arkts-structural-closure §3.3 复核（区分检测器误报与真实缺口），复核后仍 >10% → 按 gate-handling 记「未达标放行」（门禁 `execute.escalated-ratio`，剩余 FAIL 列出各 ESCALATED Slice 及其工具缺口 D 编号）后继续 FV-1 / FV-2 / a2h-verify，报告首屏标出。编译成功、骨架 0 FAIL 或产出 HAP 都不能替代接线结论，ESCALATED Slice 也不能据此补写 `feature_index.implemented` / `impl_claims`。

---

## 6. Final Structural Closure（Stage 3 全部完成后 HARD-GATE）

**交互候选审查（非门控）**：FV-1 前对稳定源码运行 `arkts-structural-closure/scripts/audit_interaction_candidates.py --project-root <project>` 一次。结果并入现有 brief；候选只记 WARN，不进入自动修复循环、不改变 FV-1 verdict。根据数据/交互契约复核后才登记真实缺陷，不要求固定 sidecar。

<HARD-GATE>
Stage 3 全部 group brief 落地 + §5f 统计输出后，派 **`a2h-closer`（mode=final）**——其内部**调 `Skill({skill: "arkts-structural-closure", args: "mode=pipeline target=final"})`** 跑整工程兜底（与 Stage 3 解耦，独立一次性 loop），CONVERGED 后产 `writeback-final.json`（收尾 brief 全文 + defer 末组补翻集合，主线程 apply 落盘，协议同 §3b-bis）。**FV-1 未收敛、按下文记了「未达标放行」后同样要产 `writeback-final.json`**：意图带 `fv1_unconverged: {loop_result: <loop-result-latest-pipeline-final.json>, decision: <D 编号>}`，`build_writeback.py` 读剩余 FAIL 的文件，实现文件与之相交的末组 slice 不认领、不翻 implemented（记进 manifest `notes`，进报告与 a2h-verify 重点核实），其余末组 slice 照常补翻——否则末组验收项会因为一条与它无关的残留永远没人认领（gpt1030_3 D-025：23 条）。

> ⚠️ **禁止用 grep 替代**

**收尾 evidence（缺失 → 重跑 FV-1 一次，仍缺属管线类 `closure.detector-incomplete`；`final_state ≠ PASS` → 按 gate-handling 记「未达标放行」（门禁 `execute.fv1-final`），残留项进 a2h-verify 重点核实，再进 FV-2 / a2h-verify；不得改写成 PASS）**：

- `spec/execution/autofix-log/round-<R>/loops-final-structural-closure.json` — `final_state == PASS`（arkts-structural-closure finalize 产出）
- `spec/execution/briefs/final_structural_closure_brief.md` — 嵌入 loops.pipeline 段

CONVERGED + evidence 就位 → FV-1 完成。CONTINUE 时 closer 先自行 fix-forward（内部 ≤3 轮，与 mode=group 步骤 4b 同口径）；≤3 轮仍未收敛才回传，主线程再按 dispatch_prompt 派 repair worker（feat → `a2h-migration-worker` / ui → `a2h-activity-converter`）后重调；其他 verdict 处置见 skill 自身 SKILL.md §3.3。

**FV-2 终态全量编译**：FV-1 通过后（其 fix-forward / repair / icon-sizing 自愈可能改码），派 Agent `hmos-builder`（CALLER=a2h-execute, STAGE_HINT=fv-final-build，≤20 轮）确认可构建无回归——这是进 a2h-verify 前的最后 gate。**必须为真实构建**：`all tasks up-to-date` 秒级空转不构成 PASS 证据，命中则 touch 入口文件或动用本轮唯一 clean 强制重编（中间 closer 保持增量，发布门较真）。编译修复仅限编译级小改，**不回跑 FV-1**。

</HARD-GATE>

---

## 可选运行时交互冒烟

用户明确要求点击/冷启冒烟时，在 FV-2 后复用 `arkts-ui-verifier`（默认 verify_only），仅选已接通关键路径；准备、断言和归因按 [交互验证边界](../a2h-spec/references/interaction-data-contract.md#验证边界)。未选择不启动设备，不新增 FV-3 执行器或必交报告，不隐式选择 a2h-verify 的 CHECK-3/4/5。

## 7. Phase A 按需触发机制

Stage 3 Step 3a 发现目标页面 ui-snapshots 数据缺失（status 非 converted/verified **且** `ui-snapshots/page_NNNN/` 缺失或不完整）→ 自动触发 a2h-spec Phase A 按需模式：单页源码分析 → 最小数据集 → 增量更新 ui-manifest + page spec → 继续 converter，不中断 Pipeline。完整触发条件 / 流程 / 降级处理（无静态 layout 时骨架 + registry 占位）**MUST 加载** [references/phase-a-ondemand.md](./references/phase-a-ondemand.md)。

---

## 8. Skill 绑定机制

### 8a. 主路径：plan 标注（三层承载）

- **Base / FV 任务**：读 base-plan.md / 索引 stanza 的 `suggested_skills:`。
- **Slice 4 步默认映射**：3a=`a2h-activity-converter` / 3b=`arkts-state-manager` / 3c=`arkts-data-layer` / 3d=`arkts-state-manager`（跨文件接线 / 结构由 a2h-closer 承担，编译由 §5f hmos-builder 集中门承担；权威在 a2h-plan §4 表，plan 不复述）。
- **Slice 差异化增量**：slice 文件 Step 行 `suggested_skills+:` 字段（plan 期语义判断的确定性产出）——**必须并入派发**。

### 8b. 覆盖 / 注入 / 降级

派发前 runtime 上下文检查可**覆盖** plan 建议（触发词追加表：动画/视频/网络救火/knowledge-verifier 等）、按 `style_set` **注入**风格 skills、对不存在的 skill **降级**（语义匹配→migration tag 优先→无增强执行）。原则：**只升级不降级**——不得移除 plan 已建议的 skill（缺失降级除外），覆盖发生时记录进迁移报告覆盖记录表。完整覆盖表 / 注入逻辑 / 降级流程 **MUST 加载** [references/skill-binding-override.md](./references/skill-binding-override.md)。

---

## 9. 状态追踪与完成性契约

### 9a. 机械完成性契约（plan 零回填）

**plan 产物（索引 + slice 文件）生成后只读**——execute 不在其中打 `[x]`、不回填 evidence。完成事实的凭据分两层：

- **接线完成性**：`verify_slice_wiring.py` C2 按对接点结构化对（page.handler ← Target；经 slice 的 `integration_points_ref` 顺链接从 feature spec「## 对接点」段解析）**直接从代码机械判定**——调用方页面存在 + handler 已在页面接线 + target 被调用方实例化（`new` / `getInstance` / typed field / render call）。**孤儿 VM 根因防线不变**：VM 存在 ≠ 被接上，判定对象始终是调用方。
- **过程记录**：每 slice 的完成事实（final_state / deferred-work 引用 / 未解占位 / pages_covered）写入 brief；Base/FV 等索引 task 的 evidence 仍按 brief 记录（build log / loops JSON 路径）。

### 9b. 页面状态生命周期（ui-manifest.md）

`pending → converted → verified`：

| 状态 | 含义 | 更新时机 |
|------|------|---------|
| `pending` | 待转换 | Spec 生成时 |
| `converted` | UI 转换产出完成 | Stage 1 批结算 / Stage 3 Step 3a 后 |
| `verified` | 实测验证通过 | a2h-verify §6.1 门控通过后（execute 全程不置位） |

### 9c. feature 状态生命周期（feature-index.md 状态列——feature 级产物状态唯一账本）

`pending → implemented → verified`：

| 状态 | 含义 | 写者与时机 |
|------|------|---------|
| `pending` | slice 未完成 | Spec 生成时初始值 |
| `implemented` | slice brief `final_state: PASS` | **group-closer 记入 writeback manifest，主线程 apply 翻**（与 ui-manifest 页面回写同 manifest，§5e） |
| `verified` | FV-1 + FV-2 通过 | FV 收尾时批量翻（a2h-verify 逐 feature 细化为开放项） |

**读者**：§11 部分执行 / resume 按它判断哪些 slice 已完成（slice:feature 1:1）；gate 摘要与 a2h-verify 范围选择按它分支。**交叉护栏**：feature=implemented 时其 owned 页不得仍 pending（structural closure / a2h-plan §7 校验）。

---

## 10. 迁移报告

<HARD-GATE>
所有 Stage 与 §6 Final Structural Closure 执行完毕后生成 `spec/migration-report.md`。

**生成前先跑**（完整执行时）`python3 scripts/lint_execute_coverage.py --project-root . --final` 做终态认领结算，
未认领项按「收尾 — 实现认领」处置后，再跑 `python3 ../a2h-spec/scripts/gate_ledger.py check --project-root . --android-root <安卓工程根>`：退出 1 = 有放行条目不成立，先改正条目；
通过后把 `spec/gate-release/summary.md` **原样放在报告最前面**（总览之前：工具缺口 / 未达标放行 / 阶段不可判定三张表 + 放行比例），
`spec/gate-release/verify-focus.json` 交 a2h-verify，`spec/gate-release/tool-gap-feedback.md` 随报告交付（发回工具维护方）。

**报告完整模板**见 [templates/migration-report-template.md](./templates/migration-report-template.md)。含：总览 / Stage 1 导入详情（+页面产物清单）/ Stage 2 详情 / Stage 3 详情 / Skill 使用统计 / 覆盖记录 / 产出文件清单 / FAILED 列表 / 页面状态汇总 / 最终编译 / Final Structural Closure（§6 收尾，取自 `loops-final-structural-closure.json` + brief）。

</HARD-GATE>

---

## 11. 触发 / 部分执行

- **完整执行**：「执行迁移」/「开始执行」/「Plan 我看过了没问题，开始执行」
- **部分执行**：「只执行 Stage 1」/「从 Stage 2 开始」/「只执行 Slice 3」/「只执行 Stage 1 的 Batch 2」
- **重试与继续**：「重试 FAILED 的 slice」/「继续执行（从上次中断的地方继续）」

自然语言触发时，a2h-execute 会列出待执行的 Stage 和任务数量，确认后开始执行。

### 11a. 部分执行的实现

| 用户指令 | 行为 |
|---------|------|
| "重跑 S1-V 接线验收" / "只重跑接线验收" | 加载 wiring reference 的严格接线分支，复用既有页面；从静态检查开始，允许返回 S1-W 修复，单次编译/安装和设备冒烟；完成或预算耗尽即返回，不重跑 Stage 0/S1-G，不进入 Stage 2/3。需项目已批准的 strict_wiring 契约；缺失时明确报告前置缺失，不回退旧视觉检查 |
| "只执行 Stage 1" | full-ui-v2 执行批准的组件/状态生成、G0/G1、装配、构建和强制 S1-V；旧冒烟模式按其已选 UI/接线与 S1-V 策略执行。结构 PASS 不代表完整 UI 完成 |
| "只执行 Stage 2" | 只读 plans/base-plan.md（旧 plan 回退 feature-plan.md 旧 Phase 0 段） |
| "只执行 Stage 3" | 只读 feature-plan.md 的 Slice 列表（前提：Stage 2 已完成） |
| "从 Stage 2 开始" | 跳过 Stage 1 导入，从 Base 层开始；Base-7 前先确认 UI 前置产物已经导入并通过 Stage 1 §3d |
| "从 Stage 2 续跑" | 读 `stage2_brief.md` 任务行，只重派未 PASS 的任务（同组的一次派出并行） |
| "重试 FAILED 的 slice" | 扫描迁移报告中的 FAILED slice，每个按 **size-1 组**重跑（1 worker + 1 closer） |
| "只执行 Slice N" | 把该 Slice 作为 **size-1 组**执行其 4 步（前提：其依赖已完成） |
| "继续执行"（resume） | **读 feature-index 状态列**判定已完成 slice（implemented/verified 跳过；slice:feature 1:1），从首个 pending 的 parallel_group 续跑；组内细节看该组 brief |

---

> **Remember**：结构性验证唯一入口 = `Skill({skill: "arkts-structural-closure", ...})`，禁止 grep / 自跑 scripts 替代；中间步骤看 verdict 即可，§6 收尾必产 `loops-final-structural-closure.json` (PASS) + brief md；Stage 0 UI 前置产物与资源校验最先跑；plan 产物只读、接线完成性由 verify_slice_wiring 机械判定；跨文件接线与状态账本由 Batch 收尾 / group-closer 单写；资源 JSON / registry 是 worker 的两项 append-only 例外（直写纪律 + 发号协议见 `_common.md`），收尾者只做资源残量兜底；合法占位 = 已登记的 5 类 kind 占位（§2.1），未登记 / 自由文本一律 FAIL；execute 按 §1.1 铁律查 decision-ledger 推进、不交互式追问（未命中按 default-policy 裁定、写「决策缺口」段后继续）；Stage 1 失败先按已批准的根因协议处置，其余 Stage 按 a2h-spec references/gate-handling.md 的通用规则执行。

---

## 收尾 — 实现认领（强制，写者协议对齐 §3b-bis writeback 单写者纪律）

**谁写 `impl-claims.json`：没有随机写者。** 账本唯一作者 = closer，唯一落盘手 = `apply_writeback.py`
——与 registry / ui-manifest / feature-index 同一条纪律：

1. 并发 worker **不直写**本账本，也无需逐 AC 汇报——认领由 closer **从 plan-coverage.json 机械
   派生**（该 packet 的 requirement_ids + requirement_digests 即认领集合；实现文件 = 单元产出
   清单，symbols 可选增补）——与「账本变更 100% 可从结果推导」同一原则；
2. 各收口 closer 在单元达完成条件时（普通 group = 该 slice `final_state: PASS`；base-plan / FV-N /
   defer-to-FV 残余 = mode:final 补记）写入 writeback manifest 的 **`impl_claims` 段**
   （schema：brief-schemas §4，与 feature_index.implemented 同守对应 mode 收口前置：普通 group 须结构 CONVERGED + 非 loop 校验通过，编译由 §5f 集中门给出；defer 末组的 PASS 不提前认领）；
3. 主线程跑 `apply_writeback.py` 统一落盘 `spec/.a2h/impl-claims.json`——append 语义、幂等可重放
   （同 `(requirement_id, packet_id, attempt)` 不重复；崩溃恢复 = 重跑 apply）。

manifest `impl_claims` 段形态：

```json
"impl_claims": {"claims": [{"requirement_id": "F001-AC01", "packet_id": "slice-03-F001",
                            "files": ["entry/src/main/ets/…/HomeCreateComponent.ets"],
                            "symbols": ["HomeCreateComponent.changeItem"],
                            "requirement_digest": "sha256:…", "attempt": 1}],
                "executed_packets": ["slice-03-F001"]}
```

`packet_id` 词汇与 plan §7.3 同源钉死：`slice-NN-<fid> | base-plan | FV-N`，**禁止自造编号**。

每个阶段收口（batch / group / slice 的 apply 成功后）跑：

```bash
python3 scripts/lint_execute_coverage.py --project-root $PROJECT_ROOT          # 批 / 组收口：只查已收口单元
python3 scripts/lint_execute_coverage.py --project-root $PROJECT_ROOT --final  # FV-1 之后、§10 报告前（完整执行时）
```

不带 `--final` 时只核对 `executed_packets` 里已收口的单元——Stage 1 批结算时还没有任何认领，这是正常的；
`--final` 把 plan 里全部 packet 纳入（部分执行「只执行 Slice N」时不带）。

- 🔴 `EXECUTE.REQUIREMENT_UNCLAIMED`：执行单元已收口但该需求无任何实现认领——**这就是
  「execute 跳过了 AC」的检出点**。确实无法按现描述实现时，用决策卡上报（无人值守取推荐项），
  不要静默跳过。认领只在单元收口时写，未收敛单元（ESCALATED / defer）的需求按 gate-handling 记「未达标放行」并引用该单元的 D 编号（同源复用），不另开修复轮次。
- 🔴 `EXECUTE.CLAIM_STALE`：AC 在 Spec 侧已变更，认领绑定的是旧断言。
- 🟡 `EXECUTE.DUPLICATE_IMPLEMENTATION`：同一需求被多个不同符号认领——**同一业务行为只保留
  一个主实现**，其余改为调用它；两套实现会让后续每次修改都要先判断运行时走哪条路。

---

## 构建修复循环操作纪律

本阶段执行期间，`hmos_fix_build_errors` 或 `hmos-builder` 的任何构建 subagent 必须遵守以下构建纪律：

### Cache Cleanliness

- `hvigorw clean` 最多执行 **1 次**。禁止 `rm -rf entry/build`（会破坏 hvigor daemon 增量状态）。
- `ohpm install` 只在构建循环开始前执行一次，不在循环内部重复执行。

### Checkpoint 提交

- 每次 `BUILD SUCCESSFUL` 之后必须立刻 `git commit`，提交消息格式：`checkpoint(base-N): build pass after K fixes`。
- 若 linter 回改导致文件变更，用 `git checkout -- <file>` 恢复而非重新编辑。

### CLI 构建降级策略

出现以下情况时禁止继续 CLI 构建，必须**升级到 IDE 构建**：
- `hvigorw` 在 <1 秒内退出且无编译错误行 → Daemon 僵死，重试 1 次后仍失败则升级
- SDK 路径错误 `00303208`/`00303217` 连续出现 2 次 → 升级
- `module.json5` 语法损坏（`00305008`）连续出现 2 次 → 升级且禁止手动修改 module.json5
- 单个文件被 linter 回改超过 3 次 → 升级，由 IDE 环境验证最终状态

### 降级时输出

```
构建环境已不稳定，无法继续 CLI 构建验证。
请在 DevEco Studio IDE 中 Build → Build HAP(s) 验证项目完整性。
```

---

## 收尾：上报本阶段用量

本 skill 的最后一步（无论经 `/a2h-run` 还是单独触发都要做）：

```bash
.migbot/bin/a2h mark-stage a2h-execute
```

标记 `a2h-execute` 阶段水位、刷新 usage.v2 快照并上传（受授权门控、尽力而为）。**忽略退出码，绝不阻断。**

---
