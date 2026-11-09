<!-- when: starting or resuming a unified run -->
<!-- topics: joint phases, native commands, preflight, single delivery, conservative export -->

# 一条联合流程

新点击计划的[风险承接与关键文件校验](../engines/interaction/references/scope-ownership-protocol.md)只发生在已有 Baseline Review 与工单冻结阶段。封存时展示 `scope_ownership`：它记录 Baseline 的承接未决项，未闭合则 `semantic_review_complete=false`，不自动补审或加轮。

命令中的 `S/I/U/SO/IO` 含义见主入口。它们是路径占位符，不是要求设置系统环境变量。每个命令用当前 shell 的安全引用语法；不改变 CODEX_HOME、HOME 或用户环境。

`unified_pipeline.py` 的 out、evidence 和初始化源码根可使用相对路径，均以调用命令时的工作目录解析；传给引擎子进程前固定为绝对路径。evidence 不相对于 out 或引擎目录解释。

收到“继续第二轮”时先读[续跑入口](round2-continuation.md)；以下 init 只用于新建从 Baseline 开始的运行。

## 0. 初始化、源码保护和共享预检

第一条产物写入命令：

```text
python <skill-dir>/scripts/unified_pipeline.py init --android-root <android_root> --arkts-root <arkts_root> --out <U>
```

它创建统一保底结果、冻结 run-config 与 hash、两类原生结果和全局 dispatch；默认冻结 `repair_mode=single-round`，只执行 `baseline-review → round-1`，Round 1 收口后直接进入集中构建/安装。只有用户在新运行开始时明确要求完整两轮，才在同一条 init 命令末尾添加 `--full-repair`，才冻结 `baseline-review → round-1 → quick-review → round-2`。模式不允许在已有 run 中热切换。默认 run 完成后收到“继续第二轮”的 prompt，先转到[第二轮续跑](round2-continuation.md)，调用 `continue-round2 --from-out <原U>` 创建关联续跑；不要执行本节 init 或重做第 1–3 节。不覆盖非空输出目录；恢复读取原 run-config/dispatch/plan/seal，不重新 init 清空计数。不要复用其它实验的修复结果或媒体日志当本轮通过证据。

默认全局 `max_agents=6`，覆盖两类 Baseline 及启用的 Repair/Quick 阶段。需要因宿主容量或用户要求降低时，在 init 显式传 `--max-agents <1..6>`，后续命令使用冻结的 `<max_agents>`；按[并发口径](unified-dispatch.md#concurrency-contract)计算容量，不继承其它实验的单 Agent 设置。

新编排冻结 `orchestration_version=2` 和 `lane_order=[interaction,setting]`；初始化、Detector 提交、计划/审查优先级及每个已启用修复轮次均按点击在前。Baseline 与 full-repair 的 Quick 只读队列保留并发补位，Repair 冻结 `repair_overlap_version=1`，支持有完整依赖证明的设置批提前补位，正式发布仍等点击收口。缺版本的旧 run 保持原顺序，不向其中添加新字段。

读取两类结果契约。用 `I/scripts/source_guard.py snapshot --project-root <arkts_root> --out <IO>/initial-source-manifest.json --fresh` 记录用户当前源码哈希清单（不是可恢复字节备份）；setting 另用 `S/scripts/source_guard.py snapshot --project-root <arkts_root> --out <SO>/initial-source-manifest.json` 建立自己的原生基线，禁止把 interaction manifest 作为 setting manifest。修改前对 `SO`、`IO` 各执行原生 `export_fast_result.py mark-editing --out <lane-out>`。两个结果只是同一次联合源码变更的分域记录，不授权重复修改。

共享预检放 `IO`，保证当前点击 exporter 的所有正式 evidence 均在其输出范围内。先使用当前 `I/scripts/resolve_hmos_toolchain.py` 解析 lock，再调用 `build_preparation.py`；先完整读取 [预检协议](../engines/interaction/references/preflight-protocol.md)。准备器自动读取现有 product/module/target/签名定位，恢复符合条件的缺失依赖，并串行执行 scan/discover/assemble/validate，不手拼最终 preflight。缺 SDK 时仍产出合法降级结果。

最终文件固定为 `IO/preflight.json`。解析 lock 后调用：

```text
python <I>/scripts/build_preparation.py --project-root <arkts_root> --toolchain-lock <IO>/toolchain-lock.json --out-dir <IO>
python <I>/scripts/fast_preflight.py validate --input <IO>/preflight.json
```

准备器可能安装项目既有依赖及运行 Hvigor tasks，不能在其它活动实验的仓库执行；开发评估使用临时工程副本。用户禁止网络或依赖安装时传 `--no-install-deps`；该开关只禁用依赖恢复，不能据此宣称工程全程只读，Hvigor tasks 仍可能写入缓存。要求工程严格只读时，不运行完整准备器或 tasks，按[预检低层降级协议](../engines/interaction/references/preflight-protocol.md#低层接口与旧运行兼容)仅采集允许读取的证据，缺少 discovery 的实际原因保留为未执行/不可构建。

缺少工具链 lock 文件时，只省略 `--toolchain-lock <IO>/toolchain-lock.json`，保留用户要求的 `--no-install-deps`。多个可选配置无法唯一确定时传用户指定的 `--product/--module/--module-target`，不猜签名或改配置。

已有 `preflight.json` 只校验；已有 `dependency-recovery.json` 包括失败/中断记录均复用，不再启动安装。脚本按输出目录记录一次恢复，但同一运行不得通过删除回执、改 `--out-dir` 或重新 init 重置次数。独立的新准备只用于用户已要求的新运行，或已明确追加第二轮的关联续跑；本轮失败保留降级原因，继续可行的源码审查。

```text
python <skill-dir>/scripts/unified_pipeline.py share-preflight --out <U>
```

此命令先校验 IO 的正式预检，再生成 SO 的兼容引用。当前依赖缺失 `BLOCKED_PREEXISTING` 在设置旧 schema 中明确映射为 `UNAVAILABLE + SHARED_PREFLIGHT_BUILD_BLOCKED`，不伪造可构建、不触发额外预检、不会读取签名密码。共享签名/构建配置只决定集中交付，不降低源码审计覆盖。

## 1. 两个全量 Detector，一次联合阶段

```text
python <skill-dir>/scripts/unified_pipeline.py detect --out <U> --phase baseline
```

输出 `IO/baseline/report.json`、`SO/baseline/report.json` 与 `U/baseline/detector-run.json`。interaction 检查 files_skipped=0 与 contract 计数；setting 检查所有发现/选择/解析数一致。按冻结顺序提交两次确定性扫描，可以同时运行，不要求完成时间顺序；它们不是模型子 Agent。重复执行已成功命令只验证冻结产物，不再次扫描。失败/中断保留原记录和部分产物，先诊断失败。

## 2. Baseline 两种 packet，同一个队列

```text
python <I>/scripts/compact_interaction_review.py plan --report <IO>/baseline/report.json --android-root <android_root> --arkts-root <arkts_root> --packets-dir <IO>/baseline/packets --out <IO>/baseline/review-plan.json
python <skill-dir>/scripts/setting_review_plan.py baseline plan --report <SO>/baseline/report.json --android-root <android_root> --arkts-root <arkts_root> --packets-dir <SO>/baseline/packets --out <SO>/baseline/review-plan.json --max-parallel <max_agents>
```

点击原生 plan 无 `--max-parallel` 参数；它的计划额度仍受外层全局 cap 限制。设置 Review 必须使用上面的 wrapper，它仅选择 Detector `findings` 非空的设置，并将原生四槽计划适配为本轮额度；不要另开原生 Review 队列或重写已经冻结的 plan。用户指明领域时只在点击 plan 添加 `--target-domains`，不因此进一步过滤设置候选。全量设置发现记录保留，未入选项记录为未审查。

setting affinity source 是原始 Detector/settings 或 findings/items 的 **逐记录完全相同、仅顺序变化** 的副本。`adapter_source_binding` 保留原 SHA 和排列，不能删记录或改 verdict。原 Detector 与 Baseline findings 不被改写。wrapper validate 检查排列与证据，原生 validator/publisher/merge 同时仍能直接消费最终计划。

按 [调度](unified-dispatch.md) 注册两类 `baseline-review` 计划，seal 后 claim-ready。worker 只处理对应 packet，读取 [setting](setting-adapter.md) / [interaction](interaction-adapter.md) 的当前阶段协议与真实双端源码。每包公共 catalog 读取一次，缺失的 consumer/声明按原协议搜索。审查时同时记录[完整修复读集](repair-overlap.md)与对应源码哈希，作为本轮证据的附属记录；未知依赖明确标为不完整，不另开审查批。

设置使用 wrapper `baseline publish/mark-unreviewed/merge`（参数保持原生）以校验新增 provenance；点击先 native `validate-draft`、再 `publish`，统一收口验证 seal。全部批终止后分别 merge 到 `SO/IO/baseline/baseline-findings.json`。点击必须额外 `quality-check --findings <IO>/baseline/baseline-findings.json`；质量不合格项不能进入修复。

## 3. Round 1 的联合 ownership 调度

新点击计划在 organization/target writer/Repair 注册前按[局部规划恢复协议](../engines/interaction/references/planning-recovery-protocol.md)协调共享风险归属；必要时一次小范围补证并独立封存。以最终 findings 规划和导出，未解决项局部挂起，其余批次继续；不因归属缺口全局停止，不重开原成功封存批，不增加 Repair 轮次。

先运行点击原生 [organization](../engines/interaction/references/repair-organization-protocol.md)；有候选时完成真实共享根因裁决、publish，并将 organization 传入 `fast_interaction_repair.py plan`。没有候选时不制造共享证明。输出 `IO/round-1/repair-plan.json`。再生成设置原生计划：

```text
python <S>/scripts/fast_repair_plan.py plan --findings <SO>/baseline/baseline-findings.json --project-root <arkts_root> --round 1 --out <SO>/round-1/repair-plan.json
```

设置原生 planner 保留最多四批一波的格式，不向它传 `--max-parallel 6`。统一执行器展开 waves 后使用全局额度，六槽不会被原生 wave 宽度限制；Round 2 同理。详见[设置并发覆盖](setting-adapter.md)。

每个已启用修复轮次均按[修复补位](repair-overlap.md)从本轮 Review 的封存读集自动生成资源映射，注册时默认省略 `--resource-map`；显式手工映射仅用于已有完整证据流程。点击优先派发；完整读集有证据、且与所有剩余点击批无冲突的设置批可提前修复交稿。设置首次提前领取会自动绑定最新 manifest，后续逐 claim 取最新已接受源码。若没有提前启动，点击收口后仍按 [manifest 交接](unified-dispatch.md) 执行 `rebase-manifest --lane setting`。两类工单均保留，点击修改不自动关闭设置工单。设置读取副本里更新后的完整业务链，不按过期片段覆盖新实现。

先注册两类计划再封阶段。新状态按[修复直接发布](direct-repair-protocol.md)交稿、确定性发布，再补位；两类 registration 都传本轮新冻结的 `--source-manifest`。setting 使用隔离 adapter，保留原 native plan/packet/key result；interaction 使用原生 direct publisher。两个 lane 均无逐批 reviewer；仅支持新的直接发布运行。默认每个文件从 claim 到终态只有一个 writer；仅 setting 内已通过[方法体范围检查](function-scoped-repair.md)的独立方法体允许最多两批窗口，interaction 同文件与跨 lane 同文件仍串行。正式发布逐批执行，后批以先前已接受补丁为基线。跨 lane 共享方法在既有修复分析内核对先前参数、consumer、状态和 postcondition；已等价仍须有真实证据，发布器不代写语义结论。

有权的全部静态目标不能只因缺少设备证据被放弃；按原生两轨义务保留 PARTIAL。无法在 ownership 内安全编辑的剩余 owner 不得扩 scope：默认模式如实 deferred，full-repair 交唯一一次 Quick。

每个已启用 Repair 轮次收口前执行一次[工单对账](unified-dispatch.md#repair-work-order-reconciliation)：`python <skill-dir>/scripts/unified_dispatch.py reconcile-repairs --state <U>/dispatch.json --stage <round-1|round-2> --dispatch`。补派原计划中明确未执行的完整工单，已有 worker/提案/回执按返回 action 续接；完成这些原有工作后才集中构建或进入已启用的下一阶段。终态 PARTIAL/FAILED/NO_CHANGE 只报告，不自动重审或重修。无法证明可恢复的 GAPS 按原流程保留未完成结果，不创建替代计划。

## 4. 联合 post-round1 与 Quick（full-repair 或第二轮续跑）

两个 Round 1 lane 均收口后：

```text
python <skill-dir>/scripts/unified_pipeline.py detect --out <U> --phase post-round1
python <I>/scripts/quick_interaction_review.py plan --findings <IO>/baseline/baseline-findings.json --detector <IO>/post-round1/report.json --round1-plan <IO>/round-1/repair-plan.json --round1-results-dir <IO>/round-1/results --project-root <arkts_root> --packets-dir <IO>/quick-review/packets --out <IO>/quick-review/plan.json
python <skill-dir>/scripts/setting_review_plan.py quick plan --findings <SO>/baseline/baseline-findings.json --detector <SO>/post-round1/report.json --round1-plan <SO>/round-1/repair-plan.json --round1-results-dir <SO>/round-1/results --project-root <arkts_root> --packets-dir <SO>/quick-review/packets --out <SO>/quick-review/plan.json --max-parallel <max_agents> --publication-policy direct
```

注册统一 `quick-review` 队列，所有 Baseline FIX_REQUIRED 仍出现一次，不以新 Detector 结果、未修改文件或前次 APPLIED 做过滤。读取整轮稳定源码、新 catalog、真实累计补丁及 SHA 绑定的直接发布 sidecar（依赖变化、受影响项，不是语义通过）。点击保留 patch/scope catalog、SDK 根因、反例序列及九角色；设置保留全部 consumer/precedence/terminal chain。分别 merge 为各自 `quick-review/findings.json`。设置公共分析及提前准备按[性能协议](behavior-performance.md)执行；在本次 Quick 内刷新下一轮修复读集与哈希。

## 5. Round 2（full-repair 或第二轮续跑）

按点击、设置顺序调用两个原生 Repair planner，分别传各自 Baseline findings、Quick findings、`--round 2`。点击重新组织当前剩余根因，不复用编辑前证明。分别用 interaction `source_guard.py snapshot --fresh` 和 setting `source_guard.py snapshot` 新建本轮各自 manifest（不覆盖初始快照），registration 只引用本领域文件。重新注册 `round-2`，按同样的补位协议执行，使用 Quick 的新读集与源码哈希，不沿用第一轮的独立性证明，所有 batch 的确定性发布/诚实失败收口才进入构建。

setting 非 CLOSED_LIKELY 的旧回退规则和 interaction 仅 ROUND2_REQUIRED 的规则保持不同。Round 2 后不再运行 Detector、AI Review、第三轮或测试；每批既有 source/scope/platform 发布检查不等于新增审计轮次。

## 6. 一次集中构建阶段、一次安装

本节的“一次”表示最后一个已启用 Repair 阶段后只进入一个集中交付阶段，不表示只能运行一次构建命令。默认模式在 Round 1 后进入；full-repair 和关联续跑在 Round 2 后进入。主会话使用 IO 预检冻结的 lock/process_env/build command。READY 才构建；UNAVAILABLE/BLOCKED_PREEXISTING 记录未安装并继续导出。

构建 attempt 总上限为 3：首次构建加最多两次编译纠偏后的复建。每次失败都要在 build draft 的对应 attempt 中写 `failure_kind`；ArkTS/CompileArkTS 失败使用 `COMPILER`，并写编译器明确报告的、相对 `arkts_root` 的 `compiler_error_paths`。下一次 attempt 的 `changed_files` 必须非空，且只能来自上一失败 attempt 的 `compiler_error_paths` 与本 run 已启用 repair-plan `ownership_paths` 并集的交集。不能趁纠偏重新设计业务、增加业务修复轮次、扩张 ownership，或改签名/依赖。

最后一次仍失败时，只有以下三种情况允许发布并封存：

- 已执行 3 个 attempt，纠偏预算耗尽；
- 最后一次失败没有落在本 run 已启用 repair-plan ownership 并集内的编译错误；
- 尚未耗尽预算，但每个仍可纠偏路径都在顶层 `correction_waivers` 中逐文件记录 `path`、`reason_code` 与非空 `detail`。`reason_code` 只允许 `NO_SAFE_CORRECTION`、`REQUIRES_BUSINESS_REDESIGN`、`REQUIRES_SCOPE_EXPANSION`。

只要最后一次失败仍有 ownership 内编译错误、attempt 少于 3 且没有完整结构化豁免，`share-build`、`finalize` 和 `validate` 都必须拒绝。不得用自然语言 summary、“Round 2 后禁止第三轮”或“一次集中交付”绕过编译纠偏；编译纠偏不是第三轮业务修复。

每个已获上述 attempt 预算的构建，用单次执行器启动，避免手工 shell 漏传冻结环境；`N` 为本次 attempt 序号：

```text
python <I>/scripts/run_frozen_build.py --preflight <IO>/preflight.json --log <U>/delivery/build-attempt-N.log
```

执行器校验 READY 及工具链绑定，将 lock 的 `process_env` 覆盖到子进程环境副本，在冻结工程根执行原 `build_command`，不修改用户环境。每次只执行一次、不自动重试/修复/安装，日志拒绝覆盖；退出 0 只表示命令成功，stdout 执行回执不等同 build draft 或 HAP 验收。保留该日志，按原规则分类失败；进程未启动等 ERROR 也保留诊断，不通过删除日志重复执行来隐藏尝试。

用真实执行日志及回执写 interaction-schema build draft（含原 IO preflight SHA），放 `U/delivery/`，再：

```text
python <skill-dir>/scripts/unified_pipeline.py share-build --out <U> --evidence <U>/delivery/build-draft.json
```

此命令仅把同一次执行证据映射到两个原生 exporter，不重复构建。PASS HAP 必须等于预检目标并冻结 SHA；不能使用旧 HAP。仅设备没有其它活动实验占用时，主会话执行一次 `hdc install -r`，真实 install draft 用 `share-install` 同样发布。

用户明确授权点击目标真机验证时，使用 [运行时协议](../engines/interaction/references/runtime-validation-protocol.md)。若要求先封存再独立验收，先完成下节，在 U 之外生成矩阵及前后 hash；验收不回灌修改或重写结果。未授权、不具备设备条件或设备忙时保留 NOT_TESTED/BLOCKED，不争抢设备。

## 7. 所有终点保守导出

封存前先执行下面的只读目录检查（`finalize` 内部也会自动执行，显式调用用于提前定位文件）：

```text
python <skill-dir>/scripts/unified_pipeline.py check-output --out <U>
```

复用点击原生 exporter 的目录规则，不新增领域审查。若返回 `BLOCKED/EXECUTABLE_HELPER`，主会话逐文件读取，核实它仅用于本批已完成真实审查后的引用提取或 JSON 组装，且不是正式证据/工具依赖后，将该临时辅助脚本移至 U 与应用源码/worker 树之外的操作系统临时目录，保留原文件内容；不自动删除，不批量搬走未知文件。若发现脚本替代真实 Agent 生成裁决、`SYNTHETIC_REPAIR_EVIDENCE` 或来源不明，保留证据并报告阻塞，不能靠移动/改名证据或删除锁绕过检查。

`finalize` 在导出任一 lane 前发现目录问题时返回 `OUTPUT_INTEGRITY_BLOCKED`，不新建分域或统一终态封存。纠正已核实的临时文件落点后，在同一未封存 run 重试下方命令；不重做 Detector、Review、Repair 或构建。暂时无法纠正时明确报告未封存/阻塞，不宣称完整；既有已封存 run 仍只验证，不因此获得解锁或改写权限。

```text
python <skill-dir>/scripts/unified_pipeline.py finalize --out <U>
python <skill-dir>/scripts/unified_pipeline.py validate --out <U>
```

脚本自动发现约定的原生产物，分别原生 finalize/validate，再绑定 SHA。缺失计划/批次不能表示“零缺陷”；安装成功不能覆盖 REVIEW_INCOMPLETE/PROCESS_INCOMPLETE。已经封存的结果只验证，不手改统计或历史证据。硬错误保留具体 lane 错误；主会话报告真实尚未完成的步骤，不把缺少脚本产物当成功。

运行时接管继续原 batch 与冻结参数；封存结束后的独立验收使用单独报告。后续“继续第二轮”按关联续跑入口执行；明确重新审查的请求才创建全新 Baseline 运行。原 run 的锁、产物和次数保持封存。
