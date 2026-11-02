---
name: a2h-spec
description: Android→ArkTS 迁移的 Spec 生成入口（Pipeline 第一步，决策差异 AC 管线 + 契约级实现映射 + 证据驱动的覆盖判定）：扫描 Android 源码产出 UI 清单与功能 Spec。当用户要"分析这个 Android 项目""开始迁移""生成迁移方案"时触发。不要用于：生成执行计划（用 a2h-plan）、转换代码（用 a2h-execute）；baseline 已存在后的增量功能/bug 由本 skill 自动转交 spec-evolver。
tags: [pipeline, migration]
type: pipeline
domain: migration
---

# a2h-spec

开始前先跑 `Bash: .migbot/bin/a2h verify-access`；退出码非 0 则把它的输出转述给用户并停下，不再继续。

## 启动检查 — 待办 findings

读 `spec/.a2h/open-findings.json`（不存在 = 首轮，直接开工）：

| 情况 | 行动 |
|---|---|
| 有 `owner_stage: spec` 的条目 | 先处理这些，再做本轮正常工作；处理完重跑对应 linter 确认消失 |
| 条目标记 `escalate: true`（同一问题连续 3 轮） | 🔴 停止自动重试，按 [references/gate-handling.md](./references/gate-handling.md) §2 记账（工具缺口 / 未达标放行），不出卡等人 |
| 本阶段 section 标记 `halted`（进度停滞 3 轮 / 累计 10 轮） | 🔴 **停止修复尝试**，按 gate-handling §2 记账后 `scripts/gate_ledger.py release` 解除，继续 |
| 条目带 `decision_ref`（已记账放行） | ⚪ 照常列出，不再修、不阻断；原 linter 不再报才算关闭 |
| 无条目 | ✅ 正常开工 |

**findings 只能由「原 linter 重跑后不再报」来关闭**，不能由任何一方声明「已修复」而关闭。
这条规则是整套追溯机制成立的前提。

## 关键约束（Critical）

- **门禁失败处置（无人值守）**：任何门禁 FAIL、轮次用完、连续未收敛，按 [references/gate-handling.md](./references/gate-handling.md) 处理——先查类别（`scripts/gate-registry.json`），精确类必须修过；推断 / 管线 / 环境类有限轮修复，修不掉记「工具缺口 / 未达标放行 / 阶段不可判定」放行继续，`scripts/gate_ledger.py check` 核对证据。禁止改工具、改门禁报告、为迁就检测器改产物。本规则优先于正文里的「阻断 / 用户裁决」表述，派发的子代理同样适用。
- **两道审批门**：Phase B 后 **Gate B**、Phase C 后 **Gate C**（Phase A → Phase B 自动衔接，无需审批）。默认无人值守：按 gate-handling §5 自动确认（无 🔴 选 [1]，🔴 已全部记账选 [2]）；用户在对话里明确要求逐个确认时，停在 Gate 等确认。
- **提问一律选项式**：任何需要用户拍板的时刻（Gate A/B/C、grill、阻塞上报），必须给
  2–4 个具体选项 + `其他`，恰好一个标「← 推荐」并给理由，用户回复编号即可。无人值守时直接取「← 推荐」项写 ledger（`approval_source: default-policy`），不等待回复。
  禁止填空式 / 开放式提问（「你希望 X 怎么处理？」「请提供 Y 的取值」）。格式见
  [templates/decision-card.md](./templates/decision-card.md)。
- **AC 数量无门槛**：没有下限、上限或偏差带；充分性由 Step C4.6f 的 `lint_coverage.py`
  按源码证据判定行为**种类**覆盖。多写的 AC 永远不会导致失败。
- **baseline 已存在 → 转 spec-evolver**：不重复初始迁移；增量功能 / bug 由本 skill 自动委托。
- **三源数据**：结构以 view.xml 为准、样式以源码为准、语义以 meta.json 为准；`layout_sources` / `style_sources` 路径写入前逐条验证存在。
- **下游强约束**：`complexity=complex` 的 feature 必填 `android_source_anchors`；stub 缺 anchor → 下游 converter FAIL，不得占位。
- **References / Templates 强制加载（HARD-GATE）**：本 skill body 中所有 `[references/X.md]` / `[templates/Y.md]` 引用，在对应步骤执行时**必须** Read 整个文件作为执行规范，不得仅靠 body 摘要或字段名提示执行（templates 中"必填字段"段不得删减或简化）。跳过加载 = PROCESS_VIOLATION。规则适用于 LLM 主线程和派发的 subagent。

---

## 1. 定位

Pipeline 层第一步，**用户唯一的 Spec 入口**。

本 skill 直接执行三阶段分析（Phase A 调用 android-ui-graph-builder 的 Python 脚本做确定性提取，Phase B/C 直接生成 Spec）。用户只需要说"分析项目"或"开始迁移"，本 skill 自动判断当前阶段（初始/增量），执行对应流程。

```
用户
  │
  ▼
a2h-spec（Pipeline 层 — 路由 + 分析 + 生成）
  │
  ├─ 初始迁移 → 三阶段直接执行:
  │   ├─ Phase A: 三源数据准备（双模式：批量前置 + 按需触发）
  │   ├─ Phase B: UI 清单生成（ui-manifest + 分页 spec + 页面状态生命周期）
  │   └─ Phase C: 功能 Spec 生成（总分结构：index + base + 按功能分文件）
  │
  └─ 增量演进 → spec-evolver（Domain 层）
```

**核心原则**：a2h-spec 直接执行所有分析和生成工作。UI 数据来自三源（view.xml + meta.json + 源码 layout XML），Feature 数据来自源码静态分析。

继续前确认授权状态：跑 `Bash: .migbot/bin/a2h verify-consent`；退出码非 0 则把它的输出转述给用户（提示其 `/a2h-privacy accept`）后停下。

---

## 2. 智能路由

启动时自动检查 `spec/baseline/` 目录是否存在：

- `spec/baseline/` 不存在 → 初始迁移流程（Section 3）：直接执行 Phase A → Phase B → Phase C。
- `spec/baseline/` 已存在 → 增量演进流程（Section 4）：委托 spec-evolver。

判断细节：
- `spec/baseline/ui-manifest.md` + `spec/baseline/feature-index.md` 两个文件都存在 → baseline 已完成
- 只有部分文件存在 → 提示用户 baseline 不完整，建议重新生成
- 完全不存在 → 初始迁移

---

## 3. 初始迁移流程

当 `spec/baseline/` 不存在时执行此流程。共三个阶段，顺序执行。

### 3.0 前置：确认源码路径

- 询问用户 Android 项目的源码路径（如果未提供）
- 验证路径有效性：检查 `AndroidManifest.xml` 或 `build.gradle` 是否存在
- 记录源码根路径 `$ANDROID_SRC`，后续所有相对路径以此为基准
- **多子仓 / 超大仓检测**：若 `settings.gradle(.kts)` 声明 ≥2 个 `include` 模块、或用户提供了多个子仓路径、或源码总 LOC ≥ 500k → 置 `$MULTI_MODULE=true`，**先执行 Phase 0（§3.0d），再进入 Phase A**；否则直接进入 Phase A（单仓流程不变）。
- 检查 `spec/ref/` 是否已有参考文档（`*_spec.md` 和 `*_design.md`）
  - 如果有 → 记录 `$REF_SPEC` 和 `$REF_DESIGN` 路径，Phase B/C 分析时参考并执行交叉验证
  - 如果没有 → 询问用户选择（无人值守 = 选推荐项 A）：
    - **选项 A【推荐】**: 自动生成 — 调度 `a2h-android-analyzer` agent 从 Android 源码分析生成参考文档
    - **选项 B**: 手动放置 — 用户自行将参考文档放入 `spec/ref/` 后继续
    - **选项 C**: 跳过 — 不生成参考文档（不影响核心流程，仅缺少 Phase B/C 交叉验证）
  - 如果用户选择 A → 调度 `a2h-android-analyzer` agent 生成参考文档（完整派发 prompt 见 [references/subagent-prompts.md](./references/subagent-prompts.md) § a2h-android-analyzer）；等待完成后记录 `$REF_SPEC` / `$REF_DESIGN` 路径，继续 Phase A

### 3.0b 风格配置

- 扫描 skills 目录中所有 SKILL.md 的 frontmatter，筛选 `type: style` 的条目
- 提取去重后的 `style-set` 值列表
- 根据发现结果决定交互方式：
  - 无风格 skills → 自动设为 `style_set = none`，不询问
  - 有 1 个风格集 → 询问用户："检测到 **{style-set-name}** 风格，是否使用？(Y/n)"（无人值守 = Y）
    - Y → `style_set = {style-set-name}`
    - n → `style_set = none`
  - 有多个风格集 → 列表供用户选择，默认 `none`
- 记录 `$STYLE_SET` 变量，后续 Phase A/B/C 输出中携带此字段

### 3.0c HarmonyOS 参考文档收集（用户预知阶段一·可选）

> 用户内部已知的 HarmonyOS 文档 / 厂商手册 / 私有镜像在 api-inventory 跑之前收集，使 api-inventory 阶段就能利用；配套模板 `templates/hmos-references-template.md`。

检查 `spec/ref/hmos-references.md`：已存在 → 记 `$HMOS_REFS_FILE`、进 Phase A；不存在 → 询问三选一（**A** 引导逐类填写 / **B** 拷模板建空文件待用户编辑 / **C** 跳过，记 `$HMOS_REFS_FILE=null`；用户全部"暂不提供"= 选 C；无人值守 = 选 C）。**完全可选、不阻断**——`$HMOS_REFS_FILE=null` 时 Step B0 不传该参数。
完整三选一流程 + 引导话术 + 各选项落地动作 → **MUST 读** [references/hmos-references-collection.md](./references/hmos-references-collection.md)。

### 3.0c2 后端契约预知收集（用户预知阶段一 · 可选 · v1.3）

> 与 3.0c 同构的第二份用户预知：**后端契约事实**（接口文档 / Postman / Swagger 链接、响应壳约定、业务成功码与 token 失效码、关键接口必填字段与 enum、后端联系人）。这些信息**只有用户或后端团队知道**、公开渠道查无可查；前置收集使 api-inventory Phase 3 能对 `uncertainties[]` 预销账，plan grill #2 C17 只追问残余项。配套模板 `templates/backend-facts-template.md`。

检查 `spec/ref/backend-facts.md`：已存在 → 记 `$BACKEND_FACTS_FILE`、进 Phase A；不存在 → 三选一（**A** 引导逐类填写 / **B** 拷模板建空文件待用户编辑 / **C** 跳过，记 `$BACKEND_FACTS_FILE=null`；无人值守 = 选 C）。**完全可选、不阻断**——为 null 时 Step B0 不传该参数，所有不确定项留给 grill #2 C17 临时收集。
完整流程与 3.0c 共用一份执行规范 → **MUST 读** [references/hmos-references-collection.md](./references/hmos-references-collection.md) §后端契约预知收集。

**测试访问 → `spec/baseline/dev_info.json`（强化，probe 前置）**：收集后端契约时，把其中的**测试访问子集**（测试 `base_url` + 业务成功码 + 测试账号）另**结构化落 `spec/baseline/dev_info.json`**（机器可读，供 spec 收尾的 auth-chain probe 与 execute 期联调消费）；模板 `templates/dev-info-template.json`。它与 `backend-facts.md` §4 是**同一事实的单一源**——测试访问只存 `dev_info.json`，backend-facts §4 只引用、不重复填（防两处互斥）。**仅测试环境凭证、非生产，建议 `.gitignore`**。缺失不阻断——留给 spec 收尾 probe（缺则建 `U-ENV`/`U-ACCOUNT`）与 grill 兜底问。

### 3.0c3 预派发 B-API 轨（api-inventory 提前启动，延迟隐藏）

**3.0c2 一结束就派发**后台子 agent 执行 `android-api-inventory`——不等到 Phase B。依据：该子 agent
只需 `$ANDROID_SRC`（加两个此刻已确定的可选参数 `hmos_references_file` / `backend_facts_file`），
**不依赖 Phase 0/A/B 的任何产物**；而它是全管线最长的单体子任务（实测 ~27 分钟），从 Phase B 才
起跑会让页面 spec 干等它收口。提前到此处，其墙钟完全隐藏在 Phase 0 + Phase A + B-UI 轨之后
（实测这段 ≈35+ 分钟 > 27 分钟），Step B-join 到点即收、Gate B 不再被它卡住。

完整派发 prompt 不变，仍见 [references/subagent-prompts.md](./references/subagent-prompts.md)
§ android-api-inventory。记录句柄 `$API_INVENTORY_JOB`，主线继续 3.0d / Phase A。

> **降级**：环境不支持后台子 agent → 本步跳过（`$API_INVENTORY_JOB=null`），沿用 Step B0 的
> 降级路径（B-join 处前台串行跑）。**并行安全**：该子 agent 只写 `spec/baseline/api-inventory/`，
> 与 Phase 0（`module-dep-graph.json`）、Phase A（`ui-snapshots/`）产物目录不相交，无竞态。

### 3.0d Phase 0：多子仓 / 跨模块依赖桥接（仅 `$MULTI_MODULE=true` 触发）

超大仓单次生成会上下文饱和「产出收缩」、纯按子仓分片又丢跨子仓依赖（A 调 B 接口 / 共享模型 / 事件绑定）。Phase 0 把**依赖发现**（脚本穷尽抽 seam 签名）与**详情生成**（按子仓分片、注入依赖骨架）解耦，复用「确定性脚本骨架 + LLM 语义补充」范式：

1. **P0.1**（脚本）`extract_module_deps.py` 抽模块 DAG + 跨模块引用边 + 共享数据模型 + seam 签名 → `spec/baseline/module-dep-graph.json`
2. **P0.2**（LLM）在骨架上补静态看不到的耦合（事件 / DI / 反射）+ 每条边语义契约 → `spec/baseline/cross-module-contracts.md`
3. **P0.3** 生成全局 `feature-base.md`（共享契约只规约一次）+ `feature-index.md`（子仓级 DAG + 拓扑序）
4. **P0.4** 按子仓拓扑序跑 Phase A→C，每片注入「触及它的边 + 依赖子仓的 seam 桩 + 全局共享契约」
5. **P0.5** seam 一致性审计 → 见 **Step C4.6d**

完整五步（脚本穷尽提取项 / 注入细节 / 子仓成环退化处理）→ **MUST 读** [references/phase-0-multimodule.md](./references/phase-0-multimodule.md)。产出 `module-dep-graph.json` + `cross-module-contracts.md`；单仓（`$MULTI_MODULE=false`）跳过整个 Phase 0。

### Phase A: 数据准备【双模式】

Phase A 负责为每个 Android 页面准备三源数据（view.xml + meta.json + 源码 layout XML），并标记 confidence 评级。

#### Phase A-0 UI 采集策略选择（必须先做）

开始 Phase A 前 MUST READ [references/ui-capture-policy.md](./references/ui-capture-policy.md)，运行
`scripts/ui_pipeline.py preflight --project-root <project>`。静态事实模式（static-v1 / static-v1-shadow / legacy）
与运行时策略（runtime_required / progressive / source_only）分别确认，缺哪项只询问哪项；已有明确指令沿用。
用 configure 持久化两项及实际选择来源，再执行前置 gate；完整 UI 证据交接采用 schema 3 的 runtime-refs，
原始 PNG/XML 不覆盖静态 view.xml。1030 旧映射入口保留，不能混用两种主记录。


**静态 UI 事实分支**：读取上一步明确记录的 `ui_facts_policy`（旧版策略文件通过 preflight 补齐缺失字段）；它只控制静态事实生成方式，不决定是否执行 Android 设备采集。

- legacy：执行以下原流程。
- static-v1-shadow：先按 [references/static-ui-facts.md](./references/static-ui-facts.md) 生成隔离旁路产物，再执行以下原流程；Phase B 不消费 shadow 数据。
- static-v1：按该 reference 运行选定 target 的静态提取，替代 Step A1 的跨 flavor 扫描及 A2a/A3 的旧合成调用；A2b 语义补充、A4、B-API、Phase B/C 和审批时序沿用。结构读 view.xml，数值样式读 visual.json，源码用于解释动态行为，语义读 meta.json。

`static-v1` 分支必须使用 `spec/.a2h/target-input.json`；只有 Phase A-0 选择 `source_only` 时才禁止设备、截图、UI dump 或像素采样依赖。
构建目标含动态 Gradle DSL 时使用有 resolution_evidence 的显式模型，不把所有 flavor 混合扫描。

#### Phase A 运行时 UI 证据（Spec-owned，runtime_required/progressive 必跑）

当 Phase A-0 选择 `runtime_required` 或 `progressive` 时，在页面清单和状态计划完成后 MUST 由主线程调用优化版 `android_fast_traverse`；不得把设备控制委托给通用 subagent。完整交接契约 MUST READ [references/android-fast-traverse-handoff.md](./references/android-fast-traverse-handoff.md)。执行器采用 `inspect → profile → run → report → review/resume` 闭环，不再使用旧的逐段 `needs_review` plan/resume 流程。

- 先 inspect 并编写应用 profile，在唯一授权设备上运行；结束后审核 source_page_id → page_id/state_id 映射并接管。不调用旧版 validate/audit/--plan，不得把未执行的页面或状态写成已采集。
- 每次运行新建 `spec/.a2h/android-fast-traverse/<run_id>/`，原始 PNG/XML/动作收据/审计结果写在它下面固定名为 `android_traverse_screenshots/` 的产物目录里，不得覆盖历史运行。
- 只接管审计通过且明确选定的观察到 `spec/baseline/ui-snapshots/<page_id>/`；保留 `run_id`、SHA256、设备和包身份 provenance。
- 真机证据用于补充或校验三源事实，不替代源码、资源索引和静态决策；冲突必须进入 findings/decision。
- `runtime_required` 没有设备、包身份或路线前置时阻断并写明缺口；`progressive` 才允许在具体失败证据下保留 pending 或走受控合成；不在 Execute 阶段补采 Android 页面。

#### 批量模式（a2h-spec 阶段触发）

这是初始迁移时的标准执行模式。

**Step A1: 提取页面清单 + Dialog inventory（两套分母，禁止混算）**

1. **全部模块** manifest 的 `<activity>`（glob `$ANDROID_SRC/*/src/main/AndroidManifest.xml`，
   **不是只读 app/**——子模块 manifest 构建期合并进 APK，只扫 app/ 会整块漏页且不留记录）
2. **Fragment** —— 经 Step A2b 加载关系发现（FragmentTransaction / ViewPager / NavComponent）
3. **Dialog/Panel** —— 运行 `android-ui-graph-builder/scripts/dialog_inventory.py` 确定性提取
   完整继承闭包、匿名实例、source-only host、show/add/replace usage 与 layout owner，落
   `spec/.a2h/spec-run/dialog-inventory.json`。以 `show/showNow` 呈现的 Dialog **不进入页面清单**；
   其规格写进宿主页/共享正文，结构证据落 `spec/baseline/dialog-snapshots/`。经
   `add/replace` 或 nav `<fragment>` 嵌入的同一类仍按页面内容登记；两种用法都有时两边登记。
4. 无源码 SDK 壳页 / 仓内 0 调用死码 → 三类处置，**跳过是决策，沉默是事故**。

**命名硬约束**：页面 spec 与页面 snapshot 一律 `page_NNNN_<ClassName>`；禁止用 `frag_` /
`dialog_` 冒充页面 spec。Dialog snapshot 是另一产物族，固定落
`dialog-snapshots/dlgsnap_<hash>_<LayoutOwner>/`，不参与 page glob/page batch。

漏项由 Step C4.6f 的 `SPEC.MANIFEST_ACTIVITY_UNACCOUNTED` / `SPEC.DIALOG_UNACCOUNTED`
兜底阻断。四类枚举源的完整扫描规则 / 三类处置判据 / 命名约束理由 → **MUST 读**
[references/phase-a-page-enumeration.md](./references/phase-a-page-enumeration.md)

**Step A2: 逐页分析**

**Step A2a: 确定性骨架生成（脚本）**

对每个页面运行 `synthesize_meta_json.py --mode scaffold`。随后运行
`a2h-spec/scripts/prepare_dialog_artifacts.py --prepare-all`：按 inventory 的唯一 layout owner 生成
Dialog meta/view snapshot；Variant/host-inline 子类复用 owner snapshot，layout-less helper 记
`snapshot_ref=none`。完整调用见 [references/phase-a-scripts.md](./references/phase-a-scripts.md)。

**Step A2b: LLM 语义分析（在脚本骨架基础上补充）**

读取脚本生成的 meta.json 骨架，验证确定性字段是否正确，并补充以下语义字段：

对每个页面执行以下分析；Dialog 行为依据 inventory/index 注入实际宿主页分析批次，不单独派成 page：

```
Activity 源码
  │
  ├─ setContentView(R.layout.xxx) → 定位 layout XML 路径
  │
  ├─ Fragment 加载关系:
  │   ├─ FragmentTransaction.replace/add → 定位子 Fragment
  │   ├─ ViewPager + FragmentPagerAdapter → 定位分页 Fragment
  │   └─ Navigation Component → nav_graph.xml → 定位 NavHostFragment
  │
  └─ 导航关系:
      ├─ Intent(this, XxxActivity::class) → 页面跳转
      ├─ NavController.navigate(R.id.xxx) → Navigation 跳转
      ├─ startActivity / startActivityForResult → 系统/外部跳转
      └─ Fragment 回退栈操作
```

**扩展分析项（增强 UI 还原精度）**：对每个页面额外分析动态菜单 / BottomSheet 行为 / RecyclerView item layout / Fragment TAG 常量 / 导航模式（互斥判断），结果写入 meta.json 对应字段。完整扫描策略 + 字段清单见 [references/phase-a-scan-strategies.md](./references/phase-a-scan-strategies.md)。

**Step A3: 检查 ui-snapshots 数据**

对每个页面检查 `spec/baseline/ui-snapshots/page_NNNN_XxxActivity/` 目录：

| 检查项 | 存在 | 缺失时处理 | confidence |
|--------|------|-----------|-----------|
| `view.xml`（UIAutomator dump） | 标记 high | 从 layout XML 合成简化版 view.xml | medium |
| `meta.json` | 读取并扩展 | 从源码分析自动生成 | 按 view.xml 情况 |
| `screenshot.png` | 记录存在 | 不影响 confidence | — |
| 部分 layout XML 缺失 | — | 标记该页面 | low |

**合成 view.xml（仅 source_only，或 progressive 的具体失败兜底）**：用 `synthesize_view_xml.py` 从 layout XML 合成近似 UIAutomator 格式 view.xml（根 `<hierarchy synthesized="true">`、bounds 留空、递归展开 `<include>`/`<merge>`）；成功标 `view_xml_synthesized:true` 并记录 `fallback_reason`，不能标成真实采集；`runtime_required` 缺真实 dump 时直接阻断。再跑 `--mode enrich` 补 `clickable_elements`。完整脚本调用 + 合成版特征见 [references/phase-a-scripts.md](./references/phase-a-scripts.md)。

**Dialog snapshot 完整性**：同时运行 `prepare_dialog_artifacts.py --check`。非 `none` 的
`snapshot_ref` 必须存在、`meta.activity == layout_owner_fqn`，有 layout_sources 时必须有 view.xml。
该检查遍历 Dialog inventory/index，不从 page-list 推导。

扩展/生成的 meta.json 完整 schema（含 `dynamic_menus` / `bottom_sheet_config` / `recycler_item_layouts` / `navigation_mode` 等字段示例）见 [templates/meta-json-schema.md](./templates/meta-json-schema.md)。

**confidence 三级评级与 Agent 行为策略**：

| 级别 | 数据来源 | Agent 行为（可验证动作） |
|------|---------|-----------|
| `high` | 有真机 UIAutomator dump（view.xml） + 截图 | 按 view.xml `bounds` 精确布局，允许硬编码尺寸 / 可见性 |
| `medium` | 从源码 layout XML 静态合成 view.xml | 按层级结构布局；运行时尺寸 / visibility 用自适应或状态驱动，**不硬编码 bounds** |
| `low` | 部分 layout 缺失或高度动态页面 | 缺失处写**显式 TODO 占位**，不臆测布局，等待人工补充 |

**源码映射可靠性规则**：`layout_sources` / `style_sources` 的填充口径与「写入 meta.json 前逐路径验存在、
不存在则移除 + 告警（不降 confidence）」的验证步骤 **→ MUST 读**
[references/phase-a-scripts.md](./references/phase-a-scripts.md) § Step A3 源码映射可靠性规则。

**Step A4: 输出准备报告**

输出「Phase A: 数据准备完成」摘要（页面清单 + confidence 分布 + 数据质量 + 建议），格式见 [templates/gate-summaries.md](./templates/gate-summaries.md) § Phase A。

#### 按需模式（a2h-execute Stage 3 切片执行时触发）

当 a2h-execute 的 Stage 3（Feature Slices）执行到某个切片时，如果发现目标页面的 ui-snapshots 数据缺失：

1. 自动对该单个页面执行上述 Step A2 + Step A3
2. 增量更新 `spec/baseline/ui-manifest.md`（新增页面条目 + confidence 标记）
3. 增量生成对应的 `spec/baseline/ui/page_NNNN.md`
4. 继续切片执行，无需中断整个 Pipeline

按需模式必须完成以下全部产出后才返回：
- [ ] `meta.json` — 含 `layout_sources`, `style_sources`（已验证路径存在）
- [ ] `view.xml` — 合成版（调用 `synthesize_view_xml.py`）
- [ ] `ui-manifest.md` 增量更新 — 新页面条目 + confidence 标记 + status: `pending`
- [ ] `ui/page_NNNN.md` 增量生成 — 分页 spec
- [ ] `menu_sources` — 从 onCreateOptionsMenu 和 app:menu 属性提取
- [ ] `fragment_tags` — 从源码 TAG 常量提取
- [ ] `dynamic_menus` — 动态菜单构建逻辑分析
- [ ] `bottom_sheet_config` — BottomSheet 行为配置
- [ ] `recycler_item_layouts` — Adapter item layout 追踪

按需模式的触发条件：
- `a2h-execute` Stage 3 Step 3a（UI 补充）检查到目标页面 status 不是 `converted`
- 且 `ui-snapshots/page_NNNN/` 目录不存在或数据不完整

---

### Phase B: UI 清单

Phase B 基于 Phase A 的页面清单和三源数据，生成结构化的 UI Spec 文档。

ui_facts_policy=static-v1 时，B1 设计令牌由 res-index/design-tokens.json 投影；B2 worker 同时读 visual.json、fixture.json、templates/ 和 Dialog 的对应 sidecar。
worker 只填写有源码引用的行为解释和 disposition，不改写已解析数值；主线程在 B2-join 运行 ui_facts.py render 和 lint --require-specs，调用与决策格式见 [references/static-ui-facts.md](./references/static-ui-facts.md)。
该 lint 的 blocking 必须清零才呈现 Gate B。legacy/shadow 不启用新门禁。静态事实分支的默认开启依赖 V2 回归和 execute 消费后的 V5 A/B 结果。

Phase B 分**两条并行轨**：**B-UI 轨**（Step B1/B2/B2.5，a2h-spec 主线执行 UI 清单生成）与 **B-API 轨**（Step B0 启动，android-api-inventory 子 agent 执行 API 清单提取）。两轨并行，Step B-join 收口后再进入 Gate B。

**Step B0: 确认 API 清单并行轨（兜底派发点）**

**常规路径下 B-API 轨已在 Step 3.0c3 提前起跑**（延迟隐藏：其 ~27 分钟墙钟藏在 Phase 0/A + B-UI
之后）。本步只做确认与兜底：

- `$API_INVENTORY_JOB` 非空 → 确认子 agent 仍在运行或已完成，主线直接进 B1；
- `$API_INVENTORY_JOB=null`（3.0c3 被跳过 / 环境当时不支持 / 中断恢复）→ **此刻补派发**，
  prompt 同 [references/subagent-prompts.md](./references/subagent-prompts.md) § android-api-inventory
  （含 `platform: android` 固定模式 / 输出目录 / 分支 C 输入源模式 /
  `hmos_references_file` + `backend_facts_file` 透传 / 7 字段 summary），记录句柄后进 B1。

> **降级**：若环境不支持后台子 agent，退化为「B-UI 轨全部完成后、Step B-join 处前台串行调用一次 android-api-inventory」——丢失并行收益但功能等价。

**Step B1: 生成 ui-manifest.md**

在 `spec/baseline/ui-manifest.md` 生成 UI 总览文档。完整模板（全局约定 / 页面清单 / 状态生命周期 / 转换批次 / 共享组件）+ 推导逻辑 + 优先级分配规则见 [templates/ui-manifest-template.md](./templates/ui-manifest-template.md)。

Dialog index 必须从 Phase A inventory 逐 required row 生成，禁止手工省略。写完立即运行：

```bash
python3 scripts/dialog_index.py --project-root "$PROJECT_ROOT" --skeleton \
  --output spec/.a2h/spec-run/dialog-index-skeleton.md
# 将 skeleton 的整张固定十列表复制到 ui-manifest；只填写 TODO 的
# usage/presentation、body spec location、instance spec location、closure。
python3 scripts/dialog_index.py --project-root "$PROJECT_ROOT" \
  --output spec/.a2h/spec-run/dialog-index.json
```

`--skeleton` 已机械选择现存宿主页：同 snapshot group 取 usage 次数最多的可映射 host，平局按
source FQN；无 page spec 的 host 留 `TODO`，不得猜。解析失败即阻断 B2；后续 page worker、auditor、
execute precheck 均消费该机器 sidecar。

**Step B2: 生成分页 UI Spec（按 batch-plan 并行派发）**

先跑 `python3 <A2H_SPEC_SKILL_ROOT>/scripts/plan_batches.py --project-root $PROJECT_ROOT`
产出 `spec/.a2h/batch-plan.json`，然后**对其 `b2_batches` 的每个批次派发一个 `b2-page-worker`**
（prompt 见 [references/subagent-prompts.md](./references/subagent-prompts.md) § b2-page-worker），
全部并行，主线在此等待汇合（等待 / 空回执 / 卡死回收见 subagent-prompts.md § 派发纪律）；worker 对本批产出 `spec/baseline/ui/page_NNNN_XxxActivity.md`。
降级路径（主线串行）与写权围栏同 § b2-page-worker 末尾的降级注。

**MUST 加载** [templates/page-spec-template.md](./templates/page-spec-template.md) 全文作为字段基底
（`android_source_anchors` YAML / 溯源 / 页面结构 / 转换决策 / 状态接口 / 导航关系等"必填字段"段
**不得删减或简化**，且每段须有**实质内容**——`## 页面结构` 非空行 ≥ 5，项目级塌陷由 Step C4.6f 的
`SPEC.PAGE_DEPTH_COLLAPSE` 确定性阻断）。沉浸式条件注入规则见该模板 § 沉浸式条件注入。

**Step B2.5: 参考文档交叉验证（条件执行）**

仅当 `$REF_SPEC` 或 `$REF_DESIGN` 存在、且用户未在 3.0 前置选「跳过」时执行；否则跳过本步。
按四维度（页面覆盖 / 导航路径 / 对话框 / 系统集成页面）比对 ref 文档与 `ui-manifest.md` + 分页 spec：
**P0 级缺失页面自动补充**（加入页面清单 + 生成分页 spec，报告中标 `[已自动补充]`），P1/P2 仅报告。
**完整执行步骤（读取章节清单 / 四维比对表 / 自动补充规则）+ UI 覆盖率报告格式
（附加到 Step B3 审批摘要）→ MUST 读**
[references/cross-validation-reports.md](./references/cross-validation-reports.md) § Step B2.5。

**Step B-join: API 清单并行轨汇合**

B-UI 轨（Step B1/B2/B2.5）完成后，在此等待 Step B0 派发的 `$API_INVENTORY_JOB` 子 agent 完成（等待与卡死回收见 subagent-prompts.md § 派发纪律），**读子 agent summary 的 5 个字段**（`services_count` / `endpoints_count` / `feature_candidates_count` / `coverage_mode` / `hmos_hint_section_present`），并校验产物，判定两个状态：

**1. `api_inventory_status`（必填）**

| 校验 | 结果 |
|------|------|
| `spec/baseline/api-inventory/api-inventory.json` 不存在 | `api_inventory_status = absent` |
| 存在且 `coverage._mode == "candidate"` | `api_inventory_status = ready` —— Phase C 全程消费 |
| 存在但 `coverage._mode` 非 `candidate`，或子 agent summary 标 `degraded`（离线项目 / RN·Flutter 壳） | `api_inventory_status = degraded` |

**2. `hmos_hint_status`（条件填）**

| 校验 | 结果 |
|------|------|
| `$HMOS_REFS_FILE == null` 或 文件不存在 | `hmos_hint_status = not_applicable` —— Phase 2.5 整段未触发 |
| `$HMOS_REFS_FILE` 存在 且 summary `hmos_hint_section_present == true` | `hmos_hint_status = present` —— `api-inventory.md` 已落「HarmonyOS 等价物提示」段，下游 a2h-plan grill #2 Step 0 优先读本段 |
| `$HMOS_REFS_FILE` 存在 但 summary `hmos_hint_section_present == false` | `hmos_hint_status = empty` —— 文件存在但与扫描结果零交集（Phase 2.5 已记降级），下游仍需在 grill #2 Step 0 全量问 |

**非阻塞原则**：`api_inventory_status` 为 `absent` 或 `degraded` 时，**不阻塞** Gate B 与 Phase C；Phase C 的所有 api-inventory 消费点（Step C1/C2/C3/C4/C4-pre）回退到「自行扫描」的原有行为。

**登录链路例外（HARD-GATE · 覆盖上面的非阻塞原则）**：检出**登录 / 鉴权 feature**（复用 Step C4-pre complex 白名单 `login / auth / vip / member / pay / oauth / subscribe`）时，`spec/baseline/api-inventory/data-chains/chain-auth.md` 是该链路的承重契约、不走非阻塞放行：请求 Gate B 前**必须**确认 `$API_INVENTORY_JOB` 真正完成（不接受"子 agent 未回就放行"）且 chain-auth 已生成并投影；缺失则先补跑 `android-api-inventory` Phase 2.8 再进 Gate B（管线类 `spec.login-chain`：补跑一次仍产不出，按 gate-handling 记「工具缺口」后进 Gate B）。非登录项目仍走非阻塞原则。两个状态（`api_inventory_status` + `hmos_hint_status`）记入 Phase C 上下文，并在 Step C4.8 grill #1 完成后落入 `spec/decision-ledger.md` 的「事实」段——供 a2h-plan grill #2 Step 0 决定是否重复追问 HarmonyOS 等价物、Step 0-C17 收口 API 契约不确定项。

**Step B-probe（B-join 尾）: 派发 auth-chain 活性探针并行轨**

chain-auth（上条已确认落盘）+ `spec/baseline/dev_info.json` 就位时，即派发后台子 agent 跑 `arkts-network-troubleshoot` 场景 E probe（有界自愈循环 N≤10 轮），**前置齐即跑、不询问用户**；**前置缺失同样不征询**——缺 `dev_info.json` 以无凭证降级模式跑连通性子集并建 `U-ENV`/`U-ACCOUNT`（走 C15 后端环境问，产 grill 问题）。对用户只发**一行单向提示**（「已派发探针」或「已降级 + 原因」），**不提问、不等待回复**。记句柄 `$AUTH_PROBE_JOB`，主线继续 Gate B → Phase C，**在 Step C4.7b `join`** —— probe 墙钟与 Gate B 审批 + C1–C4 完全重叠。完整派发 prompt（**并行安全三约束**：循环期只读 / 发现缓冲进返回值 / 落盘一律延到 join，违反即与 Phase C 竞态）见 [references/subagent-prompts.md](./references/subagent-prompts.md) § auth-chain-probe。

> **降级**：不支持后台子 agent → 此处不派发，改由 Step C4.7b 前台串行跑（功能等价，无并行收益）。**非登录项目**（无 chain-auth）跳过本步。

**Step B3: 人工审批 Gate**

输出「Phase B: UI 清单生成完成」摘要（页面总数 + 分批计划 + confidence 分布 + 全局约定 + 共享组件）等待审批，格式见 [templates/gate-summaries.md](./templates/gate-summaries.md) § Phase B。

<HARD-GATE>
Phase B 审批通过后才能进入 Phase C。
默认无人值守：按 [references/gate-handling.md](./references/gate-handling.md) §5 自动确认后进入 Phase C。
用户要求逐个确认时，须等用户明确说"确认"、"通过"、"继续"等肯定性语句。
如果用户有修改意见，先修改 ui-manifest.md / 分页 spec，重新请求审批。
</HARD-GATE>

---

### Phase C: 功能 Spec

Phase C 分析 Android 源码的非 UI 部分，生成功能层 Spec。

**Step C1: 源码分析**

扫描 Android 源码的以下层次：

| 分析目标 | 扫描策略 | 产出 |
|---------|---------|------|
| 数据模型 (Entity/POJO) | 扫描 `@Entity`, `data class`, POJO 模式 | 实体清单 + 字段定义 + 关系 |
| 数据库 (Room/SQLite) | 扫描 `@Dao`, `@Database`, `SQLiteOpenHelper`, ContentProvider | 表结构 + 查询方法 + 迁移 |
| 服务层 (Service) | 扫描 `Service`, `IntentService`, `JobService` | 服务清单 + 生命周期 + 接口 |
| 网络 (Retrofit/OkHttp) | **优先读取 `spec/baseline/api-inventory/api-inventory.json`**（B-API 轨已产出）的 `services` / `third_party_apis` / `base_urls`；每个 endpoint 为三段式 contract，**字段访问路径**：方法 / 路径 / 协议 / 描述 / 响应在 `services[].endpoints[].static.{http_method, path, protocol, description, response}`；`runtime` / `reconciled` 段在 spec 阶段恒为 `null`，由 `arkts-network-troubleshoot` 后续回填，本步骤**不消费**。`api_inventory_status` 为 `absent`/`degraded` 时才回退扫描 `@GET/@POST`, `OkHttpClient`, `HttpURLConnection` | API 端点 + 请求/响应模型 |
| 事件 (EventBus/LiveData/Flow) | 扫描 `@Subscribe`, `LiveData`, `StateFlow`, `SharedFlow` | 事件清单 + 发布者/订阅者 |
| 偏好设置 (SharedPreferences) | 扫描 `getSharedPreferences`, `PreferenceManager` | 偏好键值清单 + 类型 |
| 权限 | AndroidManifest.xml `<uses-permission>` | 权限清单 + 使用场景 |
| 第三方库 | `build.gradle` dependencies | 依赖清单 + HarmonyOS 替代方案 |

> **避免重复扫描**：网络层信息以 B-API 轨产出的 `api-inventory.json` 为准——它已覆盖 Retrofit + 裸 OkHttp + SSE/WebSocket + 三方 SDK，比此处自扫更全。`api_inventory_status = ready` 时本步骤的「网络」行直接复用 `api-inventory.json`，不再自行 Grep。

**Step C2: 生成 feature-index.md**

**C2-pre: 读取 API 清单 feature 候选（`api_inventory_status = ready` 时）**

生成功能清单**之前**，先读取 B-API 轨的产出作为功能拆分的输入源之一：

1. 读 `spec/baseline/api-inventory/api-inventory.json` 的 `coverage.feature_candidates` 数组（分支 C 输入源模式产出）。
2. 读 `spec/baseline/api-inventory/api-inventory.md` 的「Feature 候选建议」章节，理解每个候选的业务含义。
3. **逐条决策**：每个 `feature_candidate`（如 `suggested_id: F-pay`、`path_prefixes: ["/pay/*"]`）必须在功能清单中有明确归宿——要么独立成一个 F0xx，要么合理合并进/拆分到其他 F0xx，并记录该 F0xx 与候选 `suggested_id` 的对应关系（供 Step C4「## API 接口」段引用）。
4. `feature_candidates` 与 UI 侧 / 源码侧推导**互补**：候选擅长揭示「后端向」功能（支付、AI 能力、账号体系），但纯 UI 功能（设置页、关于页）不会出现在候选里，仍由 Phase B 页面清单推导。两个来源合并去重，不互相替代。
5. `api_inventory_status` 为 `absent` / `degraded` 时跳过本步骤，按原逻辑从源码分析推导功能清单。

**C2-main: 生成功能总览文档**

在 `spec/baseline/feature-index.md` 生成功能总览文档。完整模板（领域模型 / 功能清单两列依赖 / 依赖图）+ 功能拆分原则见 [templates/feature-index-template.md](./templates/feature-index-template.md)。

**Step C3: 生成 feature-base.md**

在 `spec/baseline/feature-base.md` 生成共享基础设施 Spec（数据模型 / 数据库 / 网络层 / 事件 / 偏好 / 权限 / 公共组件库）。完整模板见 [templates/feature-base-template.md](./templates/feature-base-template.md)。**网络层段**优先引用 `spec/baseline/api-inventory/common.md`（v1.2 分层公共约定文档），不在 feature-base 内重复展开公参 / 信封 / 状态码 / 鉴权头表 —— 避免与 common.md 漂移不一致；同时消费 `raw_apis.json` 的 **`api_related_constants` 五桶**（header / app_secret / code / param / other）作为结构化机器视图，落点见模板。

**交互与数据链补充**

生成功能 Spec 的数据流、对接点和 AC 时，按 [页面数据与交互契约](references/interaction-data-contract.md) 核对适用项。重点核对跨页入参、缓存/seed 的实际生产者、各 action 的可观察结果及启动有界终态；记录在已有章节，不新增固定类别硬门或必交 sidecar。

**Step C4: 生成按功能拆分的 Spec**

**按 batch-plan 并行派发**：读 `spec/.a2h/batch-plan.json` 的 `c4_batches`，**每批派发一个
`c4-feature-worker`**（prompt 见 [references/subagent-prompts.md](./references/subagent-prompts.md)
§ c4-feature-worker），全部并行，主线汇合后再进 C4.5（派发纪律同 § 派发纪律）；降级路径同该节末尾降级注。

对每个功能生成 `spec/baseline/features/F00x-xxx.md`，**主文件**大小遵循基于 `complexity` 的分层预算：

**生成即自检（并行 worker 内闭环，防串行返工尾巴）**：每个功能文档写完（含 addenda）后，
生成者（无论主线程还是并行 worker）**必须**在返回前跑一次本功能自检：

```bash
python3 <A2H_SPEC_SKILL_ROOT>/scripts/lint_coverage.py \
  --src $ANDROID_SRC --project-root $PROJECT_ROOT --only-feature F00x-xxx.md
```

- 退出码 2 → 按 findings 的 fix_hint **就地修复**（补 AC / `组:{…}` 合并声明 / skip-list 登记建议
  带回 summary），复跑；**至多自修 2 轮**，仍未清零则把残余 findings 原样写进 worker summary
  返回，交主线处理——不许在 worker 里无限磨。
- `--only-feature` 强制只读（不写 open-findings.json、不计修复轮次），并行 worker 各自自检
  **无竞态**；实测不自检时 7 个 worker 留下的缺口在 C4.6f 才集中爆出，追加了 ~19 分钟的
  **串行**修复尾巴——自检把这段时间折叠进本就并行的生成窗口。
- 主线 Step C4.6f 的全量 lint **仍是唯一权威门禁**（含 worker 看不到的工程级检查：
  manifest Activity 记账、无主文件、跨功能去重），自检不能替代它。

| complexity | 主文件预算 | 允许 addenda |
|---|---|---|
| simple | ≤200 行 | **由证据决定**：证据画像 `required_addenda` 非空即必须有对应专项材料——**sibling 文件 或 主文件里有实质内容的同名章节，二者等价**；内联不进 frontmatter `addenda` 数组、不需自指 `impl:`。complexity 不豁免 |
| complex | ≤500 行 | 是（证据触发 + section 溢出双通道，见 Step C4-pre 第 5 项） |

**MUST 加载** [templates/feature-spec-template.md](./templates/feature-spec-template.md) 全文作为字段基底（顶部 `complexity` / `tier` / `depth` + `android_source_anchors` YAML / 范围 / 数据流 / 服务层 / API 接口 / 状态管理 / 对接点 / 验收标准等"必填字段"段**不得删减或简化**）。

**AC 原子性 + 穷举铁律（无论 complexity）**：`## 验收标准` 必须**始终位于主文件**，每条 `- [ ]` 必须**原子且可断言**——禁止 "(详见 xxx.md §y)" 类延迟描述。若一条 AC 需要 addendum 才能理解，**拆成多条原子 AC**，每条独立可测。**每条 AC 带稳定 ID `F{编号}-AC{序号}`**（紧跟 `- [ ]`，如 `F001-AC07`；前缀 = 本文件 feature 编号）——**一次分配、永不复用**：删除不回收号、拆分/新增取新号、AC 随 feature 拆分迁移时按新 owner 前缀重新发号；唯二发号者 = 本步骤生成与 spec-evolver 增量。ID 供跨文件精确引用（verify fix-file / retrospect / brief evidence 不再靠引文或 file:line），并为后续 `fulfills_acs`/覆盖率统计预留 join key；格式・前缀・全局唯一性由 Step C4.6e linter 强制（缺失即 FAIL）。**（complexity=complex）每条 AC 末尾附实现追踪锚点，二型二选一**：`源:<Kotlin 符号> → 标:<ArkTS 方法>`（**parity AC**，默认——断言与 Android 行为一致）或 `决:<PD/D/G-ID> → 标:<ArkTS 方法>`（**差异 AC**——转写 decision-ledger 已批/待批决策的替代行为，仅当 ID 存在于 ledger 时合法；AC 作者是决策的转写者而非设计者，禁止自由发挥；仅真机可验证的断言行尾标 `[真机]`，且 `[真机]` 只允许出现在 决: 锚 AC 上）。锚点使 AC 既可断言又可实现，给 converter 明确落点、给 verify 双端校验依据；源或标暂缺写 `源:?` / `标:TBD`，但字段不得省略。**反幻觉不变量 = 可追溯性而非符号同一性**：parity AC 溯源到 Kotlin 符号；差异 AC 溯源到人批决策（决策再溯源到被替代的 Android 功能）——无锚 AC 一律非法。差异 AC 的产生入口唯一 = §实现映射 HARD-DIV 行 4 件套协议（见 feature-spec-template §实现映射），无对应决策 ID → 禁止发行差异 AC → fail-fast 走决策缺口。

**穷举要求**：同时**必须穷举**所有可枚举的分支——每种 brush 类型 / 每种 instrument / 每种 error 路径 / 每种 schema 字段 / 每种文档操作（add/delete/move/reorder/duplicate/...）各单独成 AC。"少而精"是 anti-pattern——一条 "支持各种 brush" 不可接受，必须拆成 "支持 PEN / 支持 BALLPOINT / 支持 HIGHLIGHTER / ..."。AC 数量应与 anchored source 复杂度成正比，见 Step C4-pre 第 6 项 Extraction depth floor。

### Step C4-pre: 复杂度判定、tier/depth 分档、anchor 自动填充与证据画像

**生成每个 feature spec 之前**，自动判定 complexity + tier/depth，扫描 anchor 候选，并按 Android 源码证据建立**功能画像**（不再推导 AC 数量预算）。下方为决策骨架；**完整信号表 / role 总结要点 / anchor glob 全集 / 护栏自检 / addendum slug 表 → MUST 读** [references/c4-pre-complexity-and-budget.md](./references/c4-pre-complexity-and-budget.md)。

**1. complexity 二级判定**

| 级别 | 判定规则 | 触发条件 |
|------|---------|---------|
| `complex` | 命中**任一**信号 | (1) feature 名/描述含白名单关键词 `login / vip / pay / member / auth / subscribe / push / share / payment / oauth` (2) 涉及状态机 / 拦截器 / 加密 / 鉴权 / token / header 注入 / 多通路 / 多入口 / 跨 App / 第三方 SDK / 回跳 等 (3) `api_inventory_status = ready` 时映射端点含**自定义签名认证 / SSE / WebSocket / 三方 SDK**，或 `migration_concerns` 非空 |
| `simple` | 全部不命中 | 仅 UI + 简单 list 数据绑定 |

边界 case **优先标 `complex`**（多读源码无破坏性）。

> **下游消费（item6 风险域条件化 rigor）**：`complexity` 复用为风险标记下传 execute——`simple`（低风险纯 UI）组在 a2h-execute group-closer 调 `arkts-structural-closure` 时附加 `--max-iter 2` 封顶迭代省成本；`complex`（含 pay / vip / member / auth / 双签名 / 成环 pay↔basic）保留默认 8 + 全套 seam 契约 / 多层覆盖 / 证据链。"边界优先 complex" 即 **fail-safe 向高 rigor 倾斜**——误判只多迭代、不漏审。

**2. role 类型（9 类）**：anchor 与 worker 源码总结按 9 类 role 归类——`presenter/viewmodel · service/repository · controller · manager · interceptor · base_class · util · data_model · partial_class`（各 role 命名约定 + 必总结内容见 reference）。

**3. anchor 自动填充**：按 9 类 role 命名 glob 扫描源码、命中 feature 关键词 → anchors；**必检** Kotlin 扩展函数伴随文件（`XxxPrivate_*.kt` → role=`partial_class`，漏锚会丢整域 80%+ LOC）；anchors 覆盖率 < 30% 时从 primary package 补到 ≥30%。路径相对 `$ANDROID_SRC`。

**4. anchor 校验**：逐路径验存在性，不存在则移除 + 警告；`complexity=complex` 但 anchors 空 → 警告（不阻断，plan/execute 二次校验）。

**6. 证据画像 + 覆盖判定（取代 AC 数量预算）**

> **AC 数量不再有下限、上限或偏差带。** 曾经的 tier floor（core 30 / standard 20 / stub 3–8）
> 与 ±40% 预算带已删除，且不得以任何形式复活。真实语料上的实测：12/12 功能的预算被 floor 主导，
> 实际产出却超预算 +80%，9/12 落在 ±40% 带外——这个门禁是**空转**的，不是保护性的。
> 更根本的是，一个数字说不出「这个功能漏了权限拒绝路径」。

两步机械流程（① `profile_feature.py` 建画像 → ② `coverage-rules.json` 推导必备义务种类，
覆盖与否由 Step C4.6f 的 `lint_coverage.py` 判定）、AC 质量护栏、广度保底、以及 **1b tier/depth 分档**
与 **5. Addendum 触发**（本节编号与 reference 一致，故跳过 1b/5）→ 均见上方 MUST 读的
[references/c4-pre-complexity-and-budget.md](./references/c4-pre-complexity-and-budget.md) §1b / §5 / §6。

**Step C4.5: 参考文档交叉验证（条件执行）**

仅当 `$REF_SPEC` 或 `$REF_DESIGN` 存在、且用户未在 3.0 前置选「跳过」时执行；否则跳过本步。
按五维度（功能覆盖 / 数据模型 / 偏好设置 / 服务接口 / 业务规则）比对 ref 文档与 `feature-base.md` +
`features/`：数据模型 / 偏好 / 业务规则缺项**自动追加到已存在文件**（不创建新 feature spec），
功能与服务接口缺项**仅报告**。**完整执行步骤（读取章节清单 / 五维比对表 / 自动追加规则）+
功能覆盖率报告格式（附加到 Step C5 审批摘要）→ MUST 读**
[references/cross-validation-reports.md](./references/cross-validation-reports.md) § Step C4.5。

**Step C4.6: 自动调用 arkts-ui-coverage-auditor（强制）**

Phase C 主体生成完毕后，**必须**自动调用 [arkts-ui-coverage-auditor](../arkts-ui-coverage-auditor/SKILL.md) 做三层覆盖率审计。
Dialog 维度的闭合结果只有一个来源：**先**运行 `python3 scripts/lint_coverage.py --src $ANDROID_SRC --project-root $PROJECT_ROOT --report-only`
（经 `dialog_closure.py` 写 `spec/.a2h/spec-run/dialog-closure-report.json`，不写 open-findings），
**再**调用 auditor——auditor 只渲染该报告，不再自行判定 Dialog 闭合：

```
lint_coverage.py --report-only  →  dialog-closure-report.json
  │
调用 arkts-ui-coverage-auditor
  │
  ├─ 输入：dialog-closure-report.json + Dialog inventory + page specs + page snapshots + ArkTS 端文件清单
  ├─ 输出：spec/ui-coverage-report.md
  │
  ├─ 通过条件：Activity/Fragment 沿原阈值；Dialog = 报告 blocking=0 且 closed+approved_skip=required
  │   且 invalid=unaccounted=0 且 inventory digest 与当前 inventory 一致
  │   └─ PASS → 继续 Step C5 人工审批
  │
  └─ FAIL（任一层覆盖率不达标）
      ├─ 读 ui-coverage-tasks.md 中的缺口清单
      ├─ 回到 Phase A/B 补缺失的 ui-snapshots + page spec
      └─ 重跑本步骤直到 PASS
```

**为什么强制**：spec 阶段就把二三层 UI 缺口暴露出来，避免一路漏到 verify 才发现（实证：Fitness 项目漏 100+ 二三层页，靠后续 9+ 条「补齐」commit 救火）。

**Step C4.6b: 源码侧功能覆盖审计（强制）**

C4.6 审 UI 侧覆盖；C4.6b 与之对称审**源码侧 ownership**——源码包有没有「无主」（不被任何 feature 锚定）。UI 薄、引擎为主体的项目最大遗漏风险就是「整包无认领」，只有源码侧普查能在 spec 阶段暴露。
- 有 `arkts-feature-coverage-auditor` 技能 → 调它做四层覆盖审计（脚本 `compute_feature_coverage.py`）→ `spec/feature-coverage-report.md`；**缺席** → 跑内置 ownership 兜底审计 → `spec/baseline/source-coverage-report.md`。
- **通过条件**：每个重要包（`file_count≥3` 或 `loc≥500`）要么被某 feature 认领（含 `tier:peripheral`/`depth:stub` 轻量认领），要么登记 skip-list；FAIL 至多自动重跑 1 次，仍 FAIL 升级 Gate C。

**Step C4.6c: stub feature 按需深挖（execute 阶段触发）**

`depth: stub`（peripheral）feature 在 spec 阶段只占位；a2h-execute slice 真正触及时**就地升级**到 standard/full（补 depth floor），增量更新 `feature-index.md` + `source-coverage-report.md`，**不回 spec 全量重跑**——「深度」被延迟而非丢弃。

**Step C4.6d: 跨模块 seam 一致性审计（仅 `$MULTI_MODULE=true`，强制）**

审**跨模块边两侧契约一致性**（分片生成最大的「错误逻辑」风险）。对每条边 `A.caller → B.symbol`：B（owner）须在某 feature 规约 symbol 签名 + 语义契约，A 的引用假设须与之一致；未规约 / 契约不一致 / 共享模型分叉 → **FAIL**（以 owner 为准收敛），DI/事件/反射边 → WARN。结果并入 `source-coverage-report.md`。

**Step C4.6e: Addenda 元数据收口（仅针对**已产出的 sibling 文件**；内联材料无需登记）**

C4.5 / C4.6 / C4.6b 完成后，对每个有 addenda 或证据要求 addenda 的 feature 收口元数据：主文件 frontmatter 写 `addenda` 数组，每个 addendum 文件写 `parent` / `slug` / `consumed_by` / `consumed_at`，交叉校验数组与实际文件**一一对应**、`## 验收标准` 无 "(详见…)" 延迟描述；**AC 组 `impl:` 指针与 addenda 的闭环（悬挂指针 / 孤儿 addendum / 超 400 行 / AC 稳定 ID 缺失・前缀不符・重复）由 `scripts/lint_addenda_closure.py` 确定性校验**（FAIL 至多自动重跑 1 次），供 a2h-execute Step 3b/3c 定向精读。

**同步跑 `scripts/lint_divergence.py`（决策差异闭环，确定性校验，FAIL 至多自动重跑 1 次）**
——本步是**结构性预检**：R1/R3/R4 只看 spec 内部形态，此时即有效；R2/R5 依赖 ledger 状态，
而决策要到 C4.8 才落地，故本步的 R2/R5 结论仅供提前发现明显缺口，**权威判定在 Step C5b 的
`--gate` 运行**。R1 HARD-DIV 4 件套齐全（决策 ID / §数据流 `PD-xxx 替代路径` / `supersedes:` 清单 / ≥1 条 决: 锚 AC；含「无 1:1 等价 / 无对等 / 替代方案 / 不可逆的产品行为差异」措辞但无决策 ID 的行同判 FAIL——散文式升级不许存在）；R2 每个 `决:` 锚可解析到 decision-ledger 条目（Gate C 出口要求 status=approved，`--gate` 模式下 proposed 即 FAIL）；R3 `supersedes:` 列出的 parity AC 均已就地标 `〔superseded by …〕`，且被替代源符号上无未标注的残留 parity AC；R4 `[真机]` 仅出现在 决: 锚 AC；R5 差异 AC 台账约束（HARD-DIV 行数 ≤ 差异 AC 数 ≤ ~5×）。

C4.6b 判定表 + skip-list 理由枚举 / C4.6c 升级步骤 / C4.6d seam 判定规则 / C4.6e addenda frontmatter schema、`consumed_by`/`consumed_at` 语义与 `impl:` 指针闭环校验 → **MUST 读** [references/c4-coverage-and-seam-audits.md](./references/c4-coverage-and-seam-audits.md)。

**Step C4.6f: 覆盖判定 + 可追溯索引（强制，取代 AC 预算对账）**

两条命令，都必须跑，结果都进 Gate C 摘要：

```bash
python3 scripts/lint_coverage.py --src $ANDROID_SRC --project-root $PROJECT_ROOT
```

- `lint_coverage.py` 比对「证据要求的行为种类 + 可枚举事实清单」与「已写的 AC」，结果写入
  `spec/.a2h/open-findings.json` 的 `spec/lint_coverage` 段。修复后的复跑加 `--after-repair`
  （计入修复轮次）；纯查看状态不加。
  - 🔴 **阻断**包括 `SPEC.UNCOVERED_ANCHOR_FILE` / `SPEC.INSTANCE_UNACCOUNTED` /
    `SPEC.MANIFEST_ACTIVITY_UNACCOUNTED` / `SPEC.DIALOG_UNACCOUNTED` /
    `SPEC.DIALOG_INVENTORY_DRIFT` / `SPEC.DIALOG_INDEX_INVALID` /
    `SPEC.DIALOG_SNAPSHOT_MISMATCH`，以及
    项目级 `SPEC.PAGE_DEPTH_COLLAPSE` / `SPEC.ADDENDA_COLLAPSE`，**必须清零或记账**：其中精确类
    （AC 格式、`MANIFEST_ACTIVITY_UNACCOUNTED` 等，见 `scripts/gate-registry.json`）必须修过；推断类
    （锚点行为信号、实例记账、Dialog 闭合、两个 COLLAPSE）修完轮次仍在、或能证明工具漏认的，按
    [references/gate-handling.md](./references/gate-handling.md) 记账后 `gate_ledger.py release` 放行；🟡 建议项含判断成分，
    进 Gate C 摘要（无人值守时随 [1]/[2] 自动确认）。逐条 finding code 的判定口径、配套披露与 🟡 枚举 **→ MUST 读**
    [references/c4-coverage-and-seam-audits.md](./references/c4-coverage-and-seam-audits.md) § Step C4.6f findings 判定目录。
**残余阻断的修复派发（并行，不串行）**：C4.6f 若仍有 🔴（多为工程级：manifest Activity、
无主文件，或个别 worker 自修 2 轮未清的项），修复按 **feature 分组并行派发**——finding 的
subject 以功能文件名开头，天然可按 feature 切分；一个串行"总修复 agent"会把本可并行的
零散小修串成长尾。工程级（跨 feature）findings 留主线处理（多数是 skip-list/决策登记，很快）。
修复完成后主线**加 `--after-repair` 复跑全量 lint** 确认收敛（配合 §循环熔断）。

- `requirements-index.json` **不在本步派生**：C4.8 的决策落地会新增 / 替代 / 重写 AC
  （`supersedes:` 就地标注、差异 AC 发号），C5 用户还可能再提修改意见——此处产出的
  `assertion_digest` 必然与最终 AC 不一致。改由 **Step C5b 出口序列**在最后一次内容
  修改之后生成一次，见下。总调用次数不增（本就只跑一次，只是挪到正确的时点）。

**Step C4.7 / C4.8 / C4.8b: spec 卫生闸 → grill #1 → CLAUDE.md 同步（HARD-GATE 三连）**

> 配套：`references/migration-decision-categories.md` C0–C17；`templates/decision-ledger-template.md`；同步算法 `templates/claude-md-decision-snippet.md`。

三步连续执行，全部通过才进 Step C5：

1. **C4.7 卫生闸**：先确保 spec 自身不矛盾（多套 spec 树 / F-ID 一致 / 完成度 vs 代码 / 计数漂移 / 废弃符号 / 报告过时）；任一 FAIL → 阻断本 Phase，先修 spec 再重跑；结论写 ledger「spec 卫生检查结论」段。
2. **C4.8 grill #1**：PASS 后**立即调用 `grill-with-docs`** Skill（传需求侧类目 C0–C5/C12/C15–C16）。C0 / C2 / C5 / C12 / C16 按 [references/default-policy.md](./references/default-policy.md) 裁定（ledger `approval_source: default-policy`，逐条进 Step C5 确认表）；检出登录 / 鉴权链路或外部 API 时 C15 仍逐条实时拷问、单条流式写 D 编号；🟢🔵🟡 模型自答 + Step C5 整体 veto。**HARD-GATE：ledger 必含 D0 产出定位，缺失即阻断 Step C5**；ledger 单文件全生命周期累积。
3. **C4.8b CLAUDE.md 同步**：ledger 产出后自动把三段独立 marker 块（决策段 / harmonyos-dev-skill 条件段 / Karpathy 基线段）幂等同步到项目根 `CLAUDE.md`；**marker 外内容永不动**；同步状态追加到 Step C5 摘要。

完整检查项 / 调用模式 / 分流表 / ledger 生命周期 / 同步算法 → **MUST 读** [references/grill-1-decision-gates.md](./references/grill-1-decision-gates.md)。

**Step C5: 人工审批 Gate**

输出「Phase C: 功能 Spec 生成完成 + grill #1 决策清单」摘要（spec 产出统计 + 决策清单概览 + 默认原则确认表）等待审批（同时审批 **spec + decision-ledger**），格式见 [templates/gate-summaries.md](./templates/gate-summaries.md) § Phase C。

<HARD-GATE>
Phase C 审批通过后才能进入 a2h-plan。
审批对象是 spec **和** decision-ledger。默认无人值守：先跑 `python3 scripts/gate_ledger.py check --project-root $PROJECT_ROOT --android-root $ANDROID_SRC`
（退出 0 才算记账成立），再按 [references/gate-handling.md](./references/gate-handling.md) §5 自动确认；用户要求逐个确认时等用户明确确认。
如果用户有修改意见，先修改相关 spec 文件 / ledger，重新请求审批。

摘要必须包含 Step C4.6f 的 🔴 阻断项与 🟡 建议项清单，以及 `spec/gate-release/summary.md` 的放行表。**存在未记账的 🔴 阻断项时选项 [1] 不可选**，
摘要须直接写明「本次不可选 [1]，因有 N 条阻断项」。选 [2]（记为例外）时，每条例外都要
写入 decision-ledger 并附**关闭条件**（工具缺口 / 未达标放行 / 阶段不可判定的关闭条件 = a2h-verify 核实）；没有关闭条件的例外不成立。
</HARD-GATE>

**Step C5b: 出口序列（Gate C 批准后、进 a2h-plan 前，一次性执行）**

决策落地与用户修改都可能改写 AC（`supersedes:` 就地标注、差异 AC 发号、按意见增删），
所以派生物与差异权威判定必须排在**最后一次内容修改之后**。顺序固定：

```
① 决策集中批准（C4.8 产出 ledger，PD-* 清零）
② 批量回写 feature / ledger —— 同一文件本轮只写一次
③ python3 scripts/lint_coverage.py --src $ANDROID_SRC --project-root $PROJECT_ROOT --report-only
   （全量：决策改写可能影响跨 feature 去重、instance 记账等**逐 feature 检查看不到**的规则）
④ 有 🔴 → 定点修复后加 --after-repair 复跑；修不掉的按 gate-handling 记账放行；无 🔴 → 直接进 ⑤
⑤ python3 scripts/lint_addenda_closure.py --spec spec/baseline
⑥ python3 scripts/lint_divergence.py --spec-dir spec/baseline/features --gate
⑦ python3 scripts/build_traceability_index.py --project-root $PROJECT_ROOT
⑧ 冻结 AC —— 此后不得再改 spec；进 a2h-plan
```

用户在 C5 提出修改意见时，修改落地后**从 ③ 重新走**，不是补跑 ⑦——否则 index 的
`assertion_digest` 与最终 AC 不一致，下游 plan/execute/verify 的 AC 粒度对账会全线错位。

⑦ 只在此处运行一次（C4.6f 已不再产），总调用次数不增。

---

## 4. 增量演进流程

当 `spec/baseline/` 已存在时，委托 `arkts-spec-evolver` 执行。

<HARD-GATE>
所有涉及代码变更的流程（含全流程模式），必须经过两道用户确认门禁：
  Gate 1: spec 生成后 → 用户确认 spec
  Gate 2: plan 生成后 → 用户确认 plan
两道门禁通过后才可进入 execute 阶段。绝对禁止跳过任何一道门禁。
（增量演进的这两道确认门不适用 gate-handling 的无人值守自动确认，照旧等用户确认。）
</HARD-GATE>

spec-evolver 支持 7 种工作模式，a2h-spec 根据用户意图自动选择：

| 用户意图 | 路由到的模式 | 说明 |
|---------|------------|------|
| "XX功能缺失" | create | 只生成 spec，等待用户确认 |
| "这个有 bug" | create | bugfix 类型，只生成 spec |
| "XX功能缺失，生成spec并实现" | create+plan+execute+verify | 全流程，自动在 Gate 1 和 Gate 2 暂停等待确认 |
| "修复 bug 并验证" | create+plan+execute+verify | 同上，两道门禁不可跳过 |
| "检查下还缺什么" | audit | 审计模式 |
| "查看 spec 状态" | status | 状态查询 |
| "为 F-xxx 生成计划" | plan | 为已有 spec 生成计划 |
| "执行 spec/features/..." | execute | 执行已审批的计划（需 status=planned） |
| "验证 F-xxx" | verify | 验证已完成的变更 |

---

## 5. 产出清单

### 产出落点

初始迁移逐 Phase 产出表、`spec/` 完整目录树、增量演进产出路径（`spec/features/` `spec/bugfixes/`
`spec/optimizations/`）**→ MUST 读** [references/outputs-and-layout.md](./references/outputs-and-layout.md)。
本节只保留跨 skill 契约字段（下方 Style Configuration）。

### Style Configuration

Spec 输出文档（`ui-manifest.md`、`feature-index.md`）顶部追加 `Style Configuration` 节：

```yaml
## Style Configuration
style_set: none          # 或 wfhc-standard 等
```

此字段由 3.0b 步骤确定，a2h-plan / a2h-execute / a2h-verify 读取此字段决定是否加载风格 skills。
`style_set` 缺失时视为 `none`（向后兼容）。

---

## 6. 门控

### 初始迁移门控

Phase A（数据准备，输出报告）→ 自动进入 Phase B（无需审批）→ Phase B 两轨并行（B-UI: ui-manifest + 分页 spec；B-API: android-api-inventory 子 agent）→ Step B-join 收口 → **★ Gate B 审批 UI 清单（默认无人值守自动确认）** → Phase C（消费 api-inventory.json，产 feature-index/base/features）→ **★ Gate C 审批功能 Spec（默认无人值守自动确认）** → a2h-plan。

Phase A 到 Phase B 自动衔接（数据准备报告仅供参考，不阻塞）。
Phase B 内 B-UI / B-API 两轨并行，Step B-join 收口；B-API 轨失败或降级不阻塞 Gate B。
Phase B 和 Phase C 各有独立审批门控。
**Gate C 批准后还有 Step C5b 出口序列**（全量 coverage → addenda closure → `lint_divergence --gate` → `build_traceability_index` → 冻结 AC），派生物与差异权威判定
一律排在最后一次内容修改之后；用户在 C5 提修改意见时，改完从 C5b ③ 重走。

**Gate B/C 出口硬闸（fan-out 可验证性）**：`spec/.a2h/batch-plan.json` 缺失 → FAIL；
`spec/.a2h/worker-receipts/` 中 `b2-*` 回执数 ≠ `b2_batches` 条数 → FAIL；任一 `page_*.md` 的
`generated_by` 不在批次集合内 → FAIL。Gate C 同理校验 `c4-*` 回执与 `F*.md` 的 `generated_by`。
降级为主线内联须落 `spec/.a2h/fanout-degraded.md` 交代原因，**深度门禁不因降级放宽**。

**Gate C 出口硬闸（产物存在性，先于一切内容判定）**：以下文件缺失 → **直接 FAIL，不进
Gate C**，且**不接受**「等价证据」「上游已覆盖」「本阶段不适用」等任何替代论证。唯一出口：产出它的审计工具
本身崩溃 / 超时、重跑 1 次仍产不出（管线类 `spec.exit-artifacts`）→ 按 [references/gate-handling.md](./references/gate-handling.md)
记「工具缺口」（工具输出 = 报错日志）后进 Gate C；「没跑」「来不及跑」不是理由：

- `spec/ui-coverage-report.md`（Step C4.6 产物）
- `spec/feature-coverage-report.md` 或 `spec/baseline/source-coverage-report.md`（C4.6b 产物）

C4.6 若因缺 `spec/baseline/ui-graph/*.json` 无法运行 → **不是跳过的理由**：按
[arkts-ui-coverage-auditor](../arkts-ui-coverage-auditor/SKILL.md)「ui-graph 不存在则先调
android-ui-graph-builder 生成」补齐前置，**不得改用其它审计替代**（B2.5 是 ref 文档交叉
验证，不读源码真值，与 C4.6 不等价——实证：以「B2.5 已等价覆盖」跳过 C4.6 那次，
20 个业务弹窗整层丢失且三道审计全绿）。

### 增量演进门控

```
spec-evolver → spec 生成 → ★ Gate 1 → plan 生成 → ★ Gate 2 → execute
```

---

## 7. 触发 Prompt 示例

- **初始迁移**：「分析这个 Android 项目」/「开始迁移」/「帮我分析下迁移难度」
- **增量演进**：「XX 功能缺失，需要补全」/「列表滚动有 bug，修复一下」
- **审计 / 状态**：「检查下 spec 和代码的差距」/「查看所有增量 spec 的状态」

---

## 8. 与 Domain Skill 的关系

a2h-spec **直接执行分析和生成**，Phase A 调用 android-ui-graph-builder 的 Python 脚本做确定性数据提取：

a2h-spec 直接执行：初始迁移 Phase A（扫 AndroidManifest + 调脚本）→ Phase B（B-UI 生成 ui-manifest + 分页 spec / B-API 派 android-api-inventory 子 agent）→ Phase C（分析源码 + 消费 api-inventory.json + 生成 feature spec）；增量演进委托 arkts-spec-evolver（7 种模式）。

### 使用的 Domain Skill

| Skill | 用途 |
|-------|------|
| `android-ui-graph-builder` | Phase A 调用其 Python 脚本（synthesize_meta_json.py, synthesize_view_xml.py）做确定性数据提取 |
| `android-ui-graph-query` | 可选：查询 UI 图谱上下文，供 a2h-activity-converter 使用 |
| `android-api-inventory` | Phase B 的 B-API 并行轨：以子 agent（固定 `platform: android`）提取外部 API 清单（分支 C 输入源模式），产出 `spec/baseline/api-inventory/{raw_apis.json, api-inventory.json, api-inventory.md}` 供 Phase C 的功能拆分与 feature-base 网络层消费。**v1.3 schema 要点**：每个 endpoint 为三段式 contract（`static / runtime / reconciled`），spec 阶段只消费 `static` 段（`runtime/reconciled` 由 `arkts-network-troubleshoot` 后续回填）；含 `project_profile` 项目画像段（http_stack/architecture/primary_auth）+ v1.3 顶层段 `auth_model`（鉴权链路）/ `data_flows`（数据链路）/ `uncertainties[]`（②③类不确定项，grill #2 C17 的输入）；当 Step 3.0c 提供 `hmos_references_file` 时触发 Phase 2.5「HarmonyOS 等价物提示段」，Step 3.0c2 提供 `backend_facts_file` 时 Phase 3 对 uncertainties 预销账；状态由 Step B-join 通过 `hmos_hint_status` 传给下游 a2h-plan grill #2 |
| `arkts-spec-evolver` | 增量演进：V1 后的 bug 修复、功能补全、优化 |

---

## 9. 三源数据原则 + 大型项目支持

三源数据核心原则——**结构以 view.xml 为准，样式以源码为准，语义以 meta.json 为准**——的逐信息类型对照表、a2h-activity-converter 消费顺序，以及大型项目（小/中/大/超大）Phase 策略，MUST参考 [references/three-source-and-scale.md](./references/three-source-and-scale.md)。

---

> **Remember**：门禁 FAIL 按 references/gate-handling.md 分类处置（精确类修过，其余记账放行、不卡死）；Gate B / Gate C 两道审批门不可省略（无人值守时自动确认）；baseline 已存在时转 spec-evolver（不重复初始迁移）；complex feature 必带 `android_source_anchors`。

---

## 收尾：上报本阶段用量

本 skill 的最后一步（无论经 `/a2h-run` 还是单独触发都要做）：上报本阶段 token 用量。

```bash
.migbot/bin/a2h mark-stage a2h-spec
```

它标记 `a2h-spec` 阶段水位、刷新精确的 usage.v2 快照并上传（受授权门控、尽力而为——拒绝/离线时只是空跑）。**忽略其退出码，绝不阻断流水线。**
