---
name: arkts-structural-closure
description: ArkTS 工程结构性验证 skill — 检测 skeleton 占位 / orphan VM / wiring 4 类闭包 / dangling FWD-REF / 沉浸式安全区四件套 + icon-sizing 图标尺寸自愈（pipeline 模式委托 arkts-icon-sizing）；支持一次性 sanity 与迭代收敛 loop 两种调用形态。被 a2h-execute §3c (stage 末尾 sanity) / §5e (Slice loop) / §6 (Pipeline-end loop) 三处调用。即使用户只说"做结构性验证"、"跑 wiring 检查"、"扫骨架"，也应触发此 skill。
tags: [verification, structural-audit]
type: domain
domain: migration
---

# arkts-structural-closure

## 关键约束（Critical）

- **loop 调用前 MUST 读完本 SKILL.md §3** —— 5 类 verdict 处置 + 收敛常量 + repair worker 派发规则缺一不可
- **检测分层**：Stage 1/2 末尾 = **一次性 audit_skeletons sanity + ArkUI 静态陷阱检查**（§2.1，非 loop）；Slice = **structural_loop slice 模式**（§2.2）；Pipeline-end = **structural_loop pipeline 模式**（§2.3）
- **3 套 verdict 处置完全一致**（slice / pipeline 共用 §3.3 表格），调用方差异仅在 mode 参数 + 作用域
- **不引入 `--mode=repair`**：repair worker 复用原 worker 完整上下文，仅追加 `dispatch_prompt` 字段作 findings 提示
- **FAIL 之后怎么走看门禁类别**（[a2h-spec references/gate-handling.md](../a2h-spec/references/gate-handling.md)；登记表 `../a2h-spec/scripts/gate-registry.json`）：本 skill 的检测器除 skeleton 的 naked-TODO / throw-stub / dangling-fwd-ref / 资源占位未登记、wiring 的 `C3_FWD_REF_NOT_REMOVED` 外都是**推断类**——有限轮修复，修不掉或能证明误报的记账放行，不卡死流水线；`ROUTE_PARAM_KEY_MISMATCH` 标 hard（回放 0 误报），只能修过或带证据放行

---

## 1. 定位

ArkTS 迁移工程的结构性验证统一 skill：

- **检测维度**：skeleton 10 子类（L1-L4）/ wiring 4 类闭包（C1-C4）/ 跨 Slice orphan VM + 组件孤儿（E1）/ immersive 四件套 / icon-sizing 图标尺寸自愈（pipeline）/ 债务终结闸（registry 残留 + deferred_items 对账，pipeline）
- **执行形态**：一次性 sanity（Stage 末尾）+ 迭代收敛 loop（Slice / Pipeline-end）
- **解耦原则**：与 `a2h-execute` 编排逻辑解耦，可被任何 a2h pipeline 阶段或独立场景调用

```
a2h-execute 编排
    │
    ├─ Stage 1/2 末尾 (§3c) ──→  arkts-structural-closure §2.1 一次性 sanity
    ├─ Stage 3 每 Slice (§5e)   ──→  arkts-structural-closure §2.2 slice 模式 loop
    └─ Stage 3 完成后 (§6)      ──→  arkts-structural-closure §2.3 pipeline 模式 loop
```

---

## 2. 三种调用入口

### 2.1 Stage 末尾 sanity（一次性 audit，**非 loop**）

适用 Stage 1 / Stage 2 末尾——99% iter 0 PASS，loop 5 类 verdict 在此无对应失败模式。Stage 1 与 Stage 2 重叠推进时（a2h-execute §3d），Stage 1 末尾改用 `--scope slice --scope-files <Stage 1 文件清单>`，避免 git diff 混入尚在书写的 Base 文件。

```bash
python3 scripts/audit_skeletons.py --project-root . --scope stage \
    --diff-base <STAGE_START_SHA> \
    --handoffs <Stage 产出 brief 路径> \
    --output-json spec/execution/autofix-log/round-<R>/audit-stage-<N>.json
```

| exit | 处置 |
|---|---|
| 0 | FAIL=0 → 进入下一 Stage |
| 1 | 有 FAIL findings → LLM Read JSON 的 `findings[]` → 派本 Stage primary worker 修一次 → 重跑本命令验证；连续 2 次仍 FAIL → 标 BLOCKED，按 gate-handling 处置（精确类子类型继续修，推断类子类型记账放行） |

Stage 3 末尾自动启用 L4.dangling-fwd-ref 检测（`kind=forward-ref` 占位 `status=resolved` 但代码 marker 残留 → FAIL）。

> **registry 解析护栏（各 scope 通用）**：registry 文件存在且含 P-ID 数据行、但解析器加载 0 行 → 自动跳过 dangling 扫描，只发 1 条 `registry-parse-degraded` FAIL（工具链问题，**勿派 worker 改业务代码**，修表格式或 `skeleton_lib/registry_resolver.py` 后重跑）。解析按表头列名映射，兼容 status 列位漂移与 `**resolved**（批注）` 式单元格。

### 2.2 Slice 模式 loop（per-Slice 接线验证）

适用 Stage 3 每个 Slice Step 3e。**作用域 = 本 Slice modifies_files + cross_slice_edits**。

```bash
bash scripts/run_loop.sh --mode slice --target <N> --round <R> --project-root .
```

Loop 内部跑：
- `verify_slice_wiring.py --slice <N>` — C1 orphan / C2 integration_point / C3 cross_slice / C4 parent_replacement。C1 对 plan `wires.viewmodel` 路径缺失但类名可在 ref graph 定位者记 `DIVERGENCE`，对有 usage_evidence（extends / 静态访问 / 文件内自用 / 类型位）的类记 `EXEMPT`，两者不计 FAIL、不进指纹
- `audit_skeletons.py --scope=slice` — skeleton + dangling-fwd-ref（限本 Slice 文件）

CONVERGED 后由调用方追加非 loop 校验（placeholders / source-notes / deferred-work 登记 —— 见 a2h-execute §5e）。

### 2.2b Group 模式 loop（per parallel-group 接线验证）

适用 Stage 3 **以 parallel_group 为粒度**收尾时（a2h-execute §5e：group-closer 完成接线与资源校验后，在**无组内编译**条件下自跑并 fix-forward ≤3 轮直到 CONVERGED，非收敛才冒泡主线程；编译统一在 execute §5f）。**作用域 = 组内全部 slice 的 modifies_files + cross_slice_edits + wires 页/VM 文件 + `--scope-files` 并集**（`--scope-files` = closer 派发参数 group_ets_files，即各 slice 自建文件——plan 账本按规则不列自建文件，不传则自建文件不在审计范围）。

```bash
bash scripts/run_loop.sh --mode group --target <groupId> --slices <N,M,...> --round <R> --project-root . --scope-files <group_ets_files...>
```

Loop 内部跑（复用 slice 模式 primitive，只是一次覆盖整组）：
- `verify_slice_wiring.py --slice <每个组内切片>` — 逐切片 C1-C4，合并 categories + repair_actions
- `audit_skeletons.py --scope=slice --scope-files <组并集>` — 对整组文件**一次** skeleton + dangling-fwd-ref

verdict / dispatch_prompt / state 与 slice 模式同构（合并后的 wiring 喂同一套下游）。CONVERGED 后同样追加非 loop 校验（对组内每个 slice 逐一核 placeholders / source-notes / deferred_items）。**收益**：组内多切片共写的文件（如 HomePage 各 Tab 槽位）在终态一次性验，比 per-slice 看半成品更准；本 skill 不依赖组内构建产物，编译只在 execute §5f 集中跑一次。

### 2.3 Pipeline 模式 loop（整工程兜底）

适用 Stage 3 全部 Slice 完成后**一次性**整工程兜底。**作用域 = 整工程 .ets**。

```bash
bash scripts/run_loop.sh --mode pipeline --target final --round <R> --project-root .
```

Loop 内部跑：
- `audit_skeletons.py --scope=all` — 全工程 skeleton + dangling-fwd-ref + intentional-default 反查
- 跨 Slice **orphan VM 检测**（候选 = `viewmodels/` / `store/` / `repository/` / `service/` 下所有导出类）+ **组件孤儿检测（E1）**（候选 = `components/` / `views/` / `widgets/` / `dialogs/` 下嵌入式组件：无任何 .ets `import` 的 `NO_IMPORTER` 阻断级 FAIL，`import` 了却从未渲染的 `IMPORTED_BUT_NOT_RENDERED` 浮为 WARN 复核）。**盲区豁免（fail-tight）**：orphan 检测基于实例化（`new X` / `X.getInstance()`），会误报"被用但非 new"的类——经 `extends`/`implements`（抽象基类/接口）、静态访问 `X.method()`（静态门面 / 常量路径 holder）、文件内自用（私有 helper）使用的类，由 `ref_graph_lib.usage_evidence()` 带**证据**移入 `exempted` 段、不进 fingerprint/不驱动循环；**零使用证据的类仍保留为 FAIL**（真孤儿 / 未接线绝不豁免）。宿主的 skill 安装目录（`.claude/` `.agents/` 等全部隐藏目录）里的模板 .ets 不属项目代码，fswalk 一律剪掉。
- 沉浸式/安全区四件套（范式差异类）— structural_loop 内置 Python 单遍扫描（判定逻辑与 `check-fullscreen-immersive-safearea.sh` 一致，`.sh` 留 CI/手工；Python 版免每文件 grep 进程 spawn，Windows 上单轮 ~10s → <0.1s）
- **icon-sizing 自愈**（委托兄弟 skill `arkts-icon-sizing/scripts/icon_autofix.py`）— static under-constrained `Image` 自动补尺寸：审计→测量(px÷density)→修复 --apply→复审，一次收敛、**无人工介入、非阻断**（动态源 / 无 raster 仅记录）。**可选 `--android-res <res 根>` 提升密度精度，缺省回退 `--density 3`**
- **`verify_arkui_safety.py` — ArkUI 安全与高信号 ArkTS 陷阱**（只读词元分析，不是编译器）：`BUILDER_THIS_REBIND`（@BuilderParam 收到裸方法引用且 builder 体依赖父组件独有成员）/ `NAV_MISSING_DESTINATION` `NAV_ROOT_COUNT` `NAV_NESTED_DESTINATION` `NAV_WRAPPER_ATTRIBUTES` `NAV_CONDITIONAL_ROOT`（路由目标的 `build()` 根随条件在 `NavDestination` 与其他根之间切换） / 带槽位组件的 `LAYOUT_UNGUARDED_INDEX` / `HITTEST_BLOCK_INTERACTIVE`（无条件 `HitTestMode.Block` 的节点子树含交互后代——Block 连子节点一起阻断，面板/对话框应保持 `Default`）/ `ROUTE_PARAM_KEY_MISMATCH`（目标页从 `pathInfo.param` 读的键没有任何调用方提供，且调用方给了它从不读的键——典型改名对不上；导航参数运行时是普通对象，`as T` 不检查，读到的是 undefined。修法：两侧用同一个键名，最好共用一个参数类）/ 源码解析失败 → FAIL 进指纹；`HITTEST_BLOCK_CONDITIONAL_UNKNOWN`（条件式 Block 且子树含交互后代）/ `NAV_SHAPE_UNKNOWN` `BUILDER_BINDING_UNKNOWN` `LAYOUT_COVERAGE_UNKNOWN` `LAYOUT_NONEMPTY_EARLY_RETURN` `HORIZONTAL_LIST_CONSTRAINT` `STACK_FULL_HEIGHT_OVERLAY` / `ROUTE_PARAM_KEY_MISMATCH`（只缺键、无多余键：可能是可选参数）→ WARN
- **`verify_closure_ledger.py` — 债务终结闸**（registry 残留分类 + deferred-work 对账（权威 = registry `kind=deferred-work` 行：依赖工件缺失 / resolve_by 归属步骤已终态未清 → FAIL、open → WARN；brief `deferred_items` 表为 legacy 兜底扫描，覆盖新旧 brief 路径）+ UI handoff 对账）：每条未解决 forward-ref，若 `resolve_by` 指向**终态切片**（PASS/ESCALATED/ROLLED_BACK）但仍 registered → GAP（FAIL）；`resolve_by=集成期…`/非 Slice → 合法外部延迟（D-007/D-008/R-005，PASS）。各 brief 的 open `deferred_items` 若依赖一个无 `.ets` 的工件（如某 ViewModel 从未创建）→ FAIL，否则 WARN 浮出复核。判定语义见 `skeleton_lib/deferral_policy.py`。**堵的洞**：旧 dangling-fwd-ref 仅对 PASS 切片报错，ESCALATED 切片的未解决 marker 被赦免 → FV-1 假 PASS（见 a2h-plan `references/anchor-coverage-gate.md` 背景 RCA）。**依赖装配**（`ref_graph_lib/assembly.py`，看结构不看命名、不认 registry 登记；只扫 build-profile.json5 登记模块的 `src/main/ets`，工程里的备份 / 副本目录不扫）：用前判空的依赖字段（`x: T | null = null` / `T | undefined` / `x?: T`；实例字段要求所属类（或子类）在可达代码里被 `new` 或由框架构造，否则按数据对象跳过），判空 = if 条件里 `||` 连接的任一项为空检查，块内第一条终止语句是 throw / reject（硬）或 return（软）；`x!.` 算软，`x?.` 不算。入口 = struct 全部方法、祖先链继承框架基类或实现框架接口的类的实例方法、@Watch / @Monitor / @Builder 回调、被加载文件（入口文件的 import 闭包，或名字被可达代码引用）的模块顶层与静态字段初始化、被构造过的类的实例字段初始化。调用解析：局部变量 / 参数优先于同名全局类，解析不出接收者时按全工程同名方法算（宁可少报），重名类的同名方法一起算；`JSON.parse(…) as T` / `Object.assign(new T(), …)` / 解构赋值算整体填充。从入口走不到任何非空赋值 → T 有实现且硬判空 = `ledger-unassembled-dependency`（FAIL，hard：只能修过——在启动装配处创建实现、调用输出里 `breakpoints` 的注入函数）；只软判空 = `ledger-unassembled-dependency-soft`（WARN，功能静默失效）；只有接口没有实现 = `ledger-dependency-no-implementation`（WARN，迁移报告如实列为不可用能力）；判空处本身走不到（死代码）不报。分析出错 = `ledger-assembly-analysis-error`（FAIL，管线类，不能被未达标放行整体带过）。**chain-auth 契约断言**（`ref_graph_lib/chain_contract.py`，断言从 `api-inventory.json` 的 `base_urls` / `auth_model` 固定推导，不由实现方自写；离线应用（无 base_url、无取 token 端点、identity none）不适用）：L0 网关主机一个都不在代码字符串里 / L2 从平台网络模块（@kit.NetworkKit / @kit.RemoteCommunicationKit / @ohos/axios）导入的名字上发请求的调用不在可达代码里 / L5 取 token 端点一个都不在可达函数体（或被可达函数引用的常量 / 端点表）里 → `ledger-chain-assertion-unmet`（FAIL）；L3 身份绑设备且安卓用平台标识（优先 `auth_model.device_id_source`，否则读 identity_notes 与契约 L3 小节，否定句不算），但可达代码里没有在 @kit.AdsKit / @kit.PushKit / @kit.BasicServicesKit 导入的名字上取设备标识 → `ledger-chain-identity-source-missing`（FAIL，hard；自写同名桩方法不算；oh-package.json5 登记的远端三方包上名字像设备标识的成员被可达代码调用算满足，另报 WARN，未登记 / `file:` 本地包不算）；缺 golden、部分登录端点不可达、端点解析不出 → `ledger-chain-assertion-note`（WARN）。

> **已知边界（静态判不了或刻意取舍，1019 两轮独立审核留档）**——漏报方向：值依赖（调用点在、入参运行时恒空；取到设备标识却丢弃结果）、字符串查表 / 反射派发、HAR 包内完成的注入、从未被引用的组件里的注入、框架类从未被构造（入口按框架类全部实例方法算）、`x?.` 静默空转、重名类（同名方法合并后少报）、构造参数默认 null、解析不出接收者时按全工程同名方法算、文件加载按「名字被引用」判（`TAG` / `DOMAIN` 这类常见常量名会让大多数文件算加载）、注释或单引号字符串里的 `${…}` 会被当成代码；L5 端点表只要被可达代码引用就整表算发出；L2 三方网络包按包名 / 成员名（http / axios / request / net）兜底，占位包也会算。误报方向（均非 hard，除注明外）：L0 主机由几段拼成；kept 文本上抹正则字面量会误伤字符串里 `}/…`、`=/…` 后的路径（L5）；chain-auth 表格把 L3 行写成 `| L3 设备身份 … |` 时读不到 L3 小节、否定词判定按标识前 14 字（「无需登录：设备 OAID 绑定游客」会被当否定）；平台接口经工程内 barrel 再导出、或 `import * as ads from '@kit.AdsKit'` 后 `ads.identifier.getOAID()` 两级访问，会判 L2 / L3 不满足（L3 为 hard：须带证据记「工具缺口」）；auth_model 为 null 但有 base_url 的工程照跑 L0 / L2。其他：同一断点会按依赖类型拆成多条；单工程最慢约 6.5 秒、13 个工程合并约 77 秒。

> **ArkUI 判定边界**：仅已解析的 BuilderParam 裸方法引用且依赖父组件独有成员时阻断，无 this 依赖不报，修法是箭头闭包并按原签名转发参数；允许路由直接包或页面自身以 NavDestination 为根，不强制统一 owner、不比较 manifest 页数与目的地数；带 BuilderParam 的自定义布局无可证明守卫的常量下标阻断，固定子节点、有效长度守卫和有界遍历不禁；解析失败阻断工具检查，不让 owner 瞎改源码。
> **`review_findings`**（WARN）：iterate / finalize 始终输出，不计指纹、不派修复。mode=final closer 逐条按原源码 / AC 复核写 brief `review_findings` 段（迁移偏差 → 交原 owner 修后重跑；证明不了 → `to-verify` 交 a2h-verify；无问题 → 记依据），不能把静态 PASS 写成渲染通过。

> ⚠️ **icon-sizing 是唯一会改源码的 detector**（自愈），其余 detector 只读。它确定性、幂等（重复跑无副作用）、git 可整体回滚；正常永远 `passed=true` 不进 verdict，仅脚本执行异常才计入（safety net）。缺 `arkts-icon-sizing` 时优雅跳过。

#### ⚠️ 降级执行：必须逐项跑齐（2026-07 事故教训）

`run_loop.sh` 若因环境问题跑不起来，**不允许"挑一两个 detector 补跑就宣告完成"**。
pipeline 的 6 项里 **icon-sizing 会改源码**，漏跑 = 图标尺寸缺陷（ArkUI 下无尺寸 `Image` 撑满父容器）静默流入产物，而编译 / 结构审计 / 债务闸 / 终态编译**四道静态门全部查不出来**——只有真机渲染才暴露。

各 detector 的独立入口（降级时照表逐项跑，一项不能少）：

| detector | 独立入口 | 产物 |
|---|---|---|
| skeleton | `audit_skeletons.py --project-root . --scope all --output-json <p>` | `audit-pipeline-iterN.json` |
| orphan VM | 内置（`structural_loop._run_pipeline_orphans`），无独立 CLI | `orphans-pipeline-iterN.json` |
| 沉浸式四件套 | 内置 Python；等价 shell 版 `check-fullscreen-immersive-safearea.sh` | `immersive-pipeline-iterN.json` |
| **icon-sizing 自愈** | `../arkts-icon-sizing/scripts/icon_autofix.py --project-root . --apply --android-res <res根...> --output-json <p>` | `icon-pipeline-iterN.json` |
| 债务终结闸 | `verify_closure_ledger.py --project-root . --output-json <p>` | `ledger-pipeline-iterN.json` |
| ArkUI 安全与静态陷阱 | `verify_arkui_safety.py --project-root . --output-json <p>` | `arkui-safety-<mode>-iterN.json` |

> **机械兜底**：`finalize` 会核对 `history[-1].detectors_run` 是否覆盖本 mode 的必需集（`_REQUIRED_DETECTORS`）。缺项直接判 `final_state: INCOMPLETE` 并列出 `missing`，**不会给 PASS**。所以降级跑完后仍须让 state 反映真实执行情况，不要手写一份"看起来通过"的 loops JSON。
>
> **另注**：单个 detector 崩溃现在由 `_safe_detector` 隔离（记 `passed:false` + 计入 FAIL），**不再中断同一轮的其余 detector** —— 上述事故中 `_run_audit` 抛异常直接带走了后面 4 项。

---

## 3. structural_loop 协议（slice + group + pipeline 共用）

<HARD-GATE>
调 `run_loop.sh` 后，按 exit code 处置。FAIL 不直接 BLOCK——按 verdict 升级。
</HARD-GATE>

### 3.1 收敛常量

常量见 `scripts/loop_runner.py`：

```
MAX_ITER             = 8     # 单 loop 最大迭代数（默认上限）
STALLED_THRESHOLD    = 2     # 连续 N 轮 findings fingerprint 相同 → 停滞
REGRESSION_THRESHOLD = 1.5×  # findings 数 > 前轮 × 此倍率 → 退化
```

> **风险域条件化迭代上限（item6）**：`MAX_ITER=8` 是默认上限，可经 `run_loop.sh … --max-iter <N>`（透传至 `structural_loop.py iterate`）按目标风险域下调——低风险 / 纯 UI 切片传 `--max-iter 2` 封顶 iter2 省迭代；**支付 / 会员 / 双签名 / 成环(pay↔basic) 等高危域保留默认 8**。封顶后若仍有未决 finding，照常 STALL→ESCALATED 浮出复核，**不静默放行**（迭代上限只省"空转轮次"，不降"问题暴露度"）。

### 3.2 调用契约

每次 `bash scripts/run_loop.sh --mode <slice|pipeline> --target <N|final> --round <R> --project-root .` 执行 **1 轮迭代**：
- state 文件自动累积 history：`spec/execution/autofix-log/round-<R>/loop-state-<mode>-<target>.json`
- latest result JSON：`spec/execution/autofix-log/round-<R>/loop-result-latest-<mode>-<target>.json`
- 各 detector 详细 JSON 由 structural_loop 内部产出：`audit-<target>-iter<N>.json` / `wiring-<target>-iter<N>.json` 等
- CONVERGED 后 finalize 收尾产物：`spec/execution/autofix-log/round-<R>/loops-<mode>-<target>.json`（stage/slice）/ `loops-final-structural-closure.json`（pipeline 收尾，即 Final Structural Closure）（含 `final_state`）—— 下游 a2h-execute §6 / a2h-plan FV-1 的 gate 对象

> **产物路径铁律**：全部 loop / audit / wiring JSON **只落 `spec/execution/autofix-log/round-<R>/`**。Windows 无 bash 时可手动驱动 `python structural_loop.py init/iterate/finalize`（等价 run_loop.sh 时序），但 `--state-file` / `--output-json` 必须仍指向上述目录——**`docs/autofix-log` 是已废弃落点，三脚本对其硬拒**（exit 2）。

调用方按 exit code 决定下一步：

### 3.3 verdict 处置表

| exit | verdict | 触发条件 | 调用方动作 |
|---|---|---|---|
| 0 | `CONVERGED` | findings 全 clean | 调 `python3 scripts/structural_loop.py finalize --state-file ... --output-json ...` 产 `loops.structural` JSON → 嵌入 brief `final_state: PASS` |
| 1 | `CONTINUE` | findings 仍存在 | Read 最新 result JSON 的 `dispatch_prompt` → 派 repair worker（按 fixer_layer 分轨：feat→`a2h-migration-worker` / ui→`a2h-activity-converter`）**原 prompt 末尾整段追加 dispatch_prompt** → 回 `run_loop.sh` |
| 2 | `STALLED` | 连续 2 轮 fingerprint 相同 | 调 finalize → brief `final_state: ESCALATED` + pipeline 继续（本单元停止自动重试，按下文复核） |
| 2 | `REGRESSED` | findings 数 > 前轮 × 1.5 | 调 finalize → `git stash` 本单元改动 + brief `final_state: ROLLED_BACK` + 阻断下游 `depends_on` |
| 2 | `EXHAUSTED` | 满 8 轮未 CONVERGED | 同 STALLED |

**升级后复核**：先区分检测器异常、可复现误报与真实实现缺口。超时 / 崩溃 / JSON 缺失属于工具未完成，不派 worker 按缺陷建议改业务代码；保留命令与错误，修工具后重跑。页面别名、已有 Builder 或共享实例争议须给出实际注册 / 声明 / 调用证据及最小复现，修检测器后仍以原范围的新扫描为准。真实缺口交原 owner / 领域专家；缺少已批准决策时按 execute §1.1 记录缺口。仅增加重试次数、重置 history、手改 verdict 或把 finding 改为 WARN 都不构成修复。只有重扫 CONVERGED 且调用方非 loop 校验通过，才可恢复 PASS 与实现认领。

**复核结论怎么落账**（{GH} §2–§3）：可复现误报 → 记「工具缺口」（证据 = 实际写法所在的 `文件:行` + 符号，工具输出 = 本轮 result JSON 对应项），同源 finding 在后续 slice / group / FV-1 里引用该 D 编号、不再新开修复轮次；真实缺口修完轮次仍在 → 记「未达标放行」，`final_state` 保持 ESCALATED，不改写成 PASS；要动态运行才能判定的 → 记「阶段不可判定」。三者都进 a2h-verify 重点核实清单。不得为迁就检测器改产物（嵌套 `NavDestination`、伪造类 / 空实现、凑调用）。

**单次检测有界**：外部 detector 默认最多 900 秒，可用 `ARKTS_DETECTOR_TIMEOUT_S` 调整；icon-sizing 保留 120 秒较紧上限（取两者较小值）。运行前作废旧输出；超时、异常退出或未产出有效 JSON 均按未完成计 FAIL，不能复用旧 PASS。`run_loop.sh` 同样在启动前归档旧 latest result；启动失败不能把上一轮结论当成本轮结果。

### 3.4 Stage 末尾闸

ESCALATED Slice 累计 > 10%（按 Slice 去重计，不按 finding 条数）→ 先按 §3.3 复核；复核后仍超比例，按 gate-handling 记「未达标放行」（门禁 `execute.escalated-ratio`）后继续进下一 Stage / FV-1 / FV-2 / a2h-verify，报告首屏标出。该判定由 a2h-execute 主流程做，本 skill 不持有累计统计。

### 3.5 Repair worker 派发原则

- **复用原 worker 完整上下文**（spec + Android 源 + plan），**不引入 `--mode=repair`**
- 仅在原 prompt 末尾追加 `dispatch_prompt` 字段作 findings 提示
- 指令统一："按 suggested_action 修复，不做无关变更"
- 路由按 fixer_layer 分轨：feat 类（services / viewmodels / repository / store / utils）→ `a2h-migration-worker`；ui 类（pages / components / widgets / resources）→ `a2h-activity-converter`
- pipeline 模式按 finding/orphan 的 `file` 路径推断所属层

---

## 4. 实现脚本对照

| 文件 | 职责 |
|---|---|
| `scripts/run_loop.sh` | loop 入口；包装 structural_loop iterate 一轮，stderr 输出 verdict + 路径；自动派生 state/result 路径 |
| `scripts/structural_loop.py` | 单轮 iterate（detector 调度 + verdict 计算 + dispatch_prompt 生成）；finalize 子命令收尾 |
| `scripts/loop_runner.py` | 收敛 verdict 计算核心（5 类 verdict + 常量定义） |
| `scripts/audit_skeletons.py` | 被 structural_loop 内部调用（slice/all scope）；亦被 §2.1 直接一次性调用（stage scope） |
| `scripts/verify_slice_wiring.py` | 被 structural_loop slice 模式（单切片）/ group 模式（逐切片后合并）内部调用 |
| `scripts/check-fullscreen-immersive-safearea.sh` | 沉浸式判定逻辑权威源（CI/手工用）；pipeline 模式内由 structural_loop 的 Python 等价实现执行 |
| `scripts/fswalk.py` | 剪枝式文件遍历（audit / ref_graph / ledger 共用，跳过 oh_modules 等不再全树枚举） |
| `scripts/tests/` | Track-1 单测（registry 解析双列序/批注归一 + degraded 护栏 CLI 集成）；`test_verify_arkui_safety.py` 覆盖命中测试 / 路由根形状规则 |
| `scripts/verify_arkui_safety.py` | ArkUI 安全检测 — 被 structural_loop **pipeline 模式**经 `_run_arkui_safety()` 调用（FAIL 进指纹，WARN 进 `review_findings`）；可独立跑 |
| `scripts/verify_closure_ledger.py` | 债务终结闸 — 被 structural_loop **pipeline 模式**经 `_run_pipeline_ledger()` 调用（registry 残留分类 + deferred_items 对账）；亦可独立跑做回归 |
| `../arkts-icon-sizing/scripts/icon_autofix.py` | **跨 skill** — pipeline 模式经 `_run_icon_sizing()` 调用，图标尺寸自愈（唯一会 mutate 源码的 detector；缺失则跳过） |
| `scripts/skeleton_lib/` | taxonomy + patterns + classifier + registry_resolver + **deferral_policy**（外部延迟 vs 在管线内债务判定，P2/P3 共用） |
| `scripts/ref_graph_lib/` | 全工程 import + instantiation 引用图（orphan 检测）|
| `scripts/plan_lib/` | feature-plan 解析器（indexed 布局：索引 detail 指针 → plans/slices/ 文件；旧 monolith 报错提示重跑 a2h-plan） |
| `scripts/README.md` | CLI 与 sub-package 详细对照 |

---

## 5. 输出 JSON schema 速查

> **MUST**：各阶段（slice / pipeline / loop verdict）输出 JSON schema 速查见 `references/output-schema.md`。

---

## 6. 调用方对照（a2h-execute）

| 调用点 | a2h-execute 章节 | 本 skill 入口 |
|---|---|---|
| Stage 1 末尾骨架 sanity | §3c | §2.1（一次性 audit） |
| Stage 2 末尾骨架 sanity | §4d 编译验证后 → §3c | §2.1（一次性 audit） |
| Stage 3 每 parallel-group 接线验证（group-closer 收尾） | §5e group 收尾 | §2.2b（group 模式 loop） |
| Stage 3 size-1 组接线验证（串行降级 / 重试单 slice / 只执行 Slice N） | §5e Step 3e | §2.2b（group 模式，slices 单元素；复用 §2.2 slice primitive） |
| Stage 3 末尾整工程兜底 | §6 Final Structural Closure | §2.3（pipeline 模式 loop） |

a2h-plan 同步在 `feature-plan-template.md` 的 Step 3e 与 FV-1 task 中以 `suggested_skills: [..., arkts-structural-closure]` 显式声明。

> **icon-sizing 自愈随 §2.3 自动运行**：a2h-execute §6 已调本 skill `mode=pipeline`，故图标尺寸自愈无需额外接线即生效。**可选**：调用时给 args 追加 `android_res=<android>/app/src/main/res`（多模块传多个，空格分隔），透传给 `run_loop.sh --android-res` → `icon_autofix.py`，按 Android 源逐图取精确密度；不传则回退 `--density 3`（xxhdpi），多数单桶工程已足够。

---

> **Remember**：调本 skill 前必读 §3 协议；slice / group / pipeline 三种 loop 共享 verdict 处置表；一次性 sanity 仅用于 Stage 1/2 末尾这种"99% PASS"场景，不走 loop。

## 交互候选审查（非门控）

FV-1 前对稳定源码运行一次 `python3 scripts/audit_interaction_candidates.py --project-root <root>`，将候选摘要纳入现有 brief；输出 JSON 可选。该脚本提示渲染空数组无已识别写入、空点击 handler、按 store/key 区分的 Preferences 无已识别 writer。它不做完整数据流分析，不给 C1–C4 新编号，不影响 structural_loop verdict，也不自动派 fixer。候选须回源码或批准的行为契约复核后才成为缺陷；无候选不代表业务通过。动态键、未知包装 API、外部生产者和跨文件注入属于扫描盲区。

C2 对描述性 Tab/Draw 等名词仅在项目没有同名导出时豁免；真实缺失类仍 FAIL。字面量 Navigation 路由仅在当前文件内同一导航栈已挂载的本地 @Builder 分支解析到目标组件时作为接线证据，不把路由字符串注入实例化索引。常量/动态路由、跨模块注册等未支持形态交 `arkts-router-verify` 复核，不凭名称消除 finding。
