<!-- when: 派发任何 converter / worker subagent 时【始终随读】——所有 agent-prompts/N-*.md 的公共前置 -->
<!-- topics: 占位规则 §2.1, 7 类 kind, HANDOFF 移交, deferred-work, Stage 3 单写者纪律, forward-ref -->

# Agent 派发 prompt — 公共规则（所有派发点必读）

> 本文件是 `agent-prompts/` 下各单段 prompt（`1-converter.md` … `8-group-closer.md`）的**公共前置规则**。
> 派发任一 worker 时，**先 Read 本文件 + 对应单段文件**两个即构成完整派发规范——不必再读其它段。

> 命令里写的 `python3` 在 Windows 上换成 `python`（或 `py -3`）；两种写法跑的是同一个脚本。

## §0 门禁 FAIL 之后（所有派发点统一遵循）

本次任务里跑的检查脚本 FAIL 时，按 [a2h-spec references/gate-handling.md](../../../a2h-spec/references/gate-handling.md) 处置：
先查类别（`python3 <a2h-spec>/scripts/gate_ledger.py classify <规则ID>`）——精确类（编译、`$r` 资源、占位登记格式）必须修过；
推断类修到派发给你的轮次为止，修不掉或能证明工具看错的**不要硬凑**，在信封里如实回报（规则 ID、工具输出位置、证据 `文件:行` + 符号），
由主线程 / 收尾者记账放行。**禁止**改、替换或另写脚本顶替工具，禁止改工具输出，禁止为迁就检测器改产物
（嵌套 `NavDestination`、伪造类或空方法、凑尺寸数值、把正确实现改错）。

## §2.1 占位延迟分类法（所有派发点统一遵循）

合法占位 = 已登记的 **7 类 kind** 占位：
- `// FWD-REF:` → forward-ref / resource-pending-asset
- `// PLACEHOLDER:` → thirdparty-sdk
- 已登记 `// TODO:` → forward-ref-uncertain
- 资源 `[TODO: translate]` → resource-pending-translation
- **`// HANDOFF:` → handoff（把责任移交给另一个 skill / 另一处调用点，见 §2.1b）**
- **无 marker → deferred-work（registry-only：既非接线 task 又非代码桩的残余工作，如 module.json5 配置 / 需另一 skill 的工作——登记即形态，`resolve_by`=归属步骤 或白名单 trigger；债务终结闸对账）**

**未登记 / 自由文本一律 FAIL。**

### §2.1b `// HANDOFF:` —— 责任移交必须带机械断言

<HARD-GATE>

**什么时候用**：你的代码**结构完整、编译通过**，但你知道它要靠**别处**才算真正完成 —— 典型两类：

1. **交给另一个 skill 处理**（如"尺寸交 icon-sizing 自愈"）
2. **交给另一处调用点**（如"由启动序列在 EntryAbility.onCreate 调 setDebug()"）

**为什么必须机械化**（AIPPT 2026-07 两次真实事故，同一根因）：
- `// ...固有尺寸交 icon-sizing 自愈` → 那轮 icon-sizing 根本没跑 → 图标撑满父容器，整页塌陷
- `// 由启动序列在 EntryAbility.onCreate 调 setDebug()` → 没人调 → release 正则拦掉测试账号，登录不通

两处**都写了注释**，但注释是**散文**：skeleton / wiring / dangling-fwd-ref 全查不出（代码结构本就完整），编译 / 结构审计 / 债务闸 / 终态编译四道门**一致放行**，只有真机跑才暴露。

**形态**（`verify=` 必填，缺了直接 FAIL）：

```
// HANDOFF: owner=<谁负责> what=<做什么> verify=<断言>
```

**三种断言，都由 `verify_closure_ledger.py` 在 pipeline 末尾机械对账**：

| 断言 | 语义 | 用于 |
|---|---|---|
| `grep:<正则>` | 全工程 `.ets` 必须存在匹配（marker 行自身不计，防自证） | 启动期初始化、跨文件调用点 |
| `artifact:<文件>#<字段>` | 产物存在且该字段非空/非零（文件名可不带路径，自动取 `spec/execution/autofix-log/` 下最新同名（旧项目 docs/autofix-log 兜底）） | 委托给别的 skill 自愈 |
| `slice:<N>` | 归属切片；该切片终态仍未兑现 → GAP(FAIL) | 业务接线（等价 FWD-REF） |

**示例**：
```ets
// HANDOFF: owner=arkts-icon-sizing what=补图标尺寸 verify=artifact:icon-pipeline-iter1.json#fixed_count
Image($r('app.media.icon_mine_right_arrow'))

// HANDOFF: owner=EntryAbility.onCreate what=调setDebug verify=grep:HttpLog\.setDebug\(
static setDebug(value: boolean): void { ... }
```

**判定**：断言成立 → INFO；不成立 → **FAIL**（`ledger-handoff-unmet`）；无 `verify=` → **FAIL**（`ledger-handoff-no-assertion`）。

⚠️ **不要用散文替代**。"待接入 xxx 后替换"、"由 xxx 负责"这类注释若不写成本 marker，等于把缺陷交给运气。

</HARD-GATE>

### §2.1c P-ID 发号协议（所有铸号者——converter / worker / closer / repair）

<HARD-GATE>

1. 前缀 = slice 命名空间：`P-S{N}-{seq}`（converter 用页面 `owning_slice` 的 Slice 编号；Base 任务 `P-B{N}-{seq}`）；禁止自造前缀。
2. registry 唯一发号处，**登记即占号**：写 marker 前先向 `spec/placeholder-registry.md` append 该行（6 字段齐全）。
3. 发号前 `grep "P-S{N}-"` 取本前缀 max seq，新号 = max+1。

</HARD-GATE>

## 单写者纪律（全 Stage 无条件；Stage 3 任意组大小含 size-1 组）

Stage 1 converter 同样只写自身页面文件，享受同样两项 append-only 例外；batch-closer 对资源仅残量兜底。

Stage 3 一律以 parallel_group 为粒度执行，`4-slice-worker.md`（§4）的 slice worker **只写自身 page / VM / repository 文件**，**禁止编辑共享文件**（包含但不限于 `spec/baseline/plans/feature-plan.md`）。Step 3d 的**跨文件接线**一律移交 **`8-group-closer.md`（§8）group-closer** 统一单写；slice worker 只接自身页内的 VM/handler。

**仅两项 append-only 例外**（其余共享文件仍绝对禁碰）：
1. `spec/placeholder-registry.md` 的 **P-ID 登记行 append**（§2.1c 发号协议——登记即占号）；
2. **共享资源 JSON 直写**（见下方资源直写纪律）。

**plan 产物只读**：feature-plan.md 索引与 `plans/slices/` 文件生成后只读——任何 agent 不得回填 checkbox / evidence / 状态（完成性 = verify_slice_wiring 机械判定 + brief 记录）。**拆分越界禁令**：按依赖断面拆分派发的 worker（§5a 安全阀）只写划给自己的文件集，禁碰兄弟 worker 文件。

## 资源直写纪律（converter / worker）

共享资源 JSON（`color/string/float.json` 等）允许直写，仅限：写前 Read 最新文件、只 append 缺失键（禁重排 / 重写 / 删除既有条目）；键已存在即复用。冲突由后续集中 `hmos-builder` 编译门自曝。

## 返回报告信封契约（所有 agent）

判据：主线程是否据此做分支决策？是 → 进报告；否 → 落 brief / 产物文件，报告只留指针。
- 最终报告 = 结构化信封 ≤30 行：状态枚举、计数、失败项（仅 ID/路径）、产物与 brief 路径、≤3 条短句风险。
- 禁止粘贴：逐文件清单全文、evidence 明细、资源核对清单、修复叙述、build 日志、dispatch_prompt 全文（一律以路径传递）。
- 各单段 prompt 的"返回报告必须含"即信封字段；超出部分写对应 brief（落 `spec/execution/briefs/`；**closer 的 brief 与账本变更经 writeback manifest 由主线程 apply 落盘**，turn 内不直写——协议见 a2h-closer 定义）。

## 校验性读取纪律（grep-first，所有 agent）

作者性读取不受限（spec / anchors 源码 / 快照 / 自己要改的文件）。校验性读取一律 grep 定位 + 窗口读：
- 查页面状态 / 复用组件：grep ui-manifest 对应行（禁整读、禁扫 components/ 目录）
- 查占位：按本 slice 前缀 `grep "P-S{N}-"` registry
- 定位 marker / handler / @Builder 槽位：grep 后 Read ±30 行窗口，禁整读 .ets

## impl: 指针语义（Step 3b / 3c worker 定向精读 addenda）

feature spec `## 验收标准` 的 `###` 组标题（或单条 AC）尾部 `impl: <addendum>.md §<节>` = 该组实现细节的权威归宿（组级默认、单条覆盖、多目标逗号分隔；addendum 位于 feature spec 同目录）。worker 实现某 AC 组前：

- 该组带 `impl:` 且目标 addendum 的 `consumed_at`（frontmatter，缺省按 a2h-spec C4-pre 第 5 项 slug 默认表：state-machine/races/lifecycle→3b，api/persistence→3c，mapping→随组）匹配本步骤 → **按标题 grep 目标 §节精读**（`grep -A 40 "<节标题>" <addendum 路径>`），随 spec / 源码一并纳入理解
- **禁止整目录扫读 addenda**；每次派发精读 **≤3 节 / 总量 ≤150 行**，超出按 AC 组顺序取前 3、其余写入返回报告 `deferred_addenda` 字段
- AC 断言本身以主文件为准（指针不转移断言）；无指针的组照旧只依据主文件
- **无 `impl:` 指针 ≠ 材料缺失**：证据义务可由主文件里的同名章节（`## state-machine` 等）就地兑现，
  这种内联材料不产 sibling、不登记 frontmatter、也不指向自己。主文件已在上下文里，无需额外精读动作；
  不要因为找不到 addendum 文件就判定专项材料缺失或回头要求 spec 补文件。
