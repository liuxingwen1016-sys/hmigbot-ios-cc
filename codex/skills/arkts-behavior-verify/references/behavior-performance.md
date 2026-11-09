<!-- when: 规划分包、派发 worker、复用设置 Quick 分析或提前准备 Quick 时读取 -->
<!-- topics: global concurrency, setting parity, shared evidence, early Quick -->
# 双域性能协议

优化不改变设置发现与审查分母、原生状态准入、逐 consumer 核验或已冻结阶段边界。默认单轮不创建 Quick/Round 2；full-repair 保留两轮边界；已封存单轮追加第二轮按[关联续跑](round2-continuation.md)执行。点击固定核心候选；不提供其它候选模式。以下操作都受顶层统一调度器控制。

## 分包与 worker

设置 Repair 先按显式 logical setting group 和实际共享写路径聚合，再应用原生项数/路径上限；不把版本展示等无关项填进仍与其它批争锁的热点批；仅把完全不含跨组热点的独立小组适度合并，减少启动与发布次数。逐 setting exactly-once、foundation 例外及原生 ownership 上限保持不变；设置独立方法体按[有限并发](function-scoped-repair.md)允许双批窗口，其余同文件单 writer。分包可能增加小批数量，按真实耗时评估，不能承诺固定提速比例。

Review 的读写声明按[修复补位](repair-overlap.md)随原生 item 保存并绑定发布证据；Repair register 默认自动汇总。缺证据继续等待，不能以减少排队为由声明独立或删必要 edit target。

Baseline 使用 AFFINITY_COST_V2：按路径、目标、平台义务及证据体积估计负载，重批优先，共享依赖仅在负载容差内聚合。设置候选仍全部 exactly-once，普通修复每批最多三个设置、每 key 最多六个文件；原生 foundation 特例保持不变。

Quick 使用历史兼容标识 `CALLABLE_FAMILY_COST_V3`（它是 callable 分组调度协议名，不是 Skill 名），将同路径和 callable 的共同阅读族按数量、负载和实际槽位切分。设置每批最多六项，点击每批最多八项。公共路径/方法不是共享缺陷或通过结论。

统一全局最多六个子 Agent；完成一个立即处理交稿、发布并补位。新批新上下文，只传 packet、角色协议、输出路径、worker_root 和身份；同批恢复继续原 Agent。修复不预留发布 reviewer，writer 锁或已认证的双批窗口保持到发布或失败终态；可发布队列达到两批就限流，等待点击的设置草稿不阻塞点击派发。设置使用原生 per-key 结果，不套用点击九角色。

设置 worker 先使用 `setting_repair_pipeline.py check --plan P --state N --batch-id B --claim-token T` 核对私有副本；完成 draft 后运行：

```text
python <skill-dir>/scripts/setting_repair_pipeline.py validate-draft --plan P --state N --batch-id B --claim-token T --draft D
```

该命令只校验真实私有差分、ownership 和原生结果，不发布、不释放槽位、不证明正确。格式错误在原上下文修正；停写后仍由统一调度器 submit/publish。点击使用任务包给出的原生 start-worker/validate-draft。

## 设置 Quick 公共分析

packet 的 shared_chain_catalog 是阅读提示。可在 draft 顶层写 `shared_chain_reviews:[{chain_id,analysis,evidence:[{path,line,excerpt}]}]`，逐 setting 写 shared_chain_refs。每项仍必须保留自己的 evidence、完整 consumer_closure、terminal chain、覆盖优先级、逻辑组、剩余链和 Round 2 targets。

发布必须经过 setting_review_plan.py quick publish 或统一 complete。适配器核对源码引用和全应用源码绑定，展开公共分析后再调用原生设置发布器；缺 consumer、未解决链、活动目标或覆盖优先级均按原有规则拒绝闭合。公共记录不得包含状态或角色裁决。

后续批次可以机会性读取已经封存的公共事实：

```text
python <skill-dir>/scripts/setting_review_plan.py quick shared --plan Q --batch-id B --fragments-dir F
```

它检查同一计划、原生 fragment/seal、公共分析确实出现在封存证据中及当前源码 SHA。没有可复用事实就自行审查，不等待首批。冲突分析不复用；新增反向 writer 或配置变化使旧分析失效。session、spec、构建与工具目录不计入应用源码绑定。

## 提前准备同一次 Quick

提前 reviewer 同样读取[效果反馈与副作用](effect-feedback-safety.md)，其反向回调路径计入实际读集；最终 Quick 重新核对稳定源码，不能仅凭提前推演声明收敛。

两域修复都优先。尾部没有可领取修复且有空闲槽位时，创建独立 reviewer 得到真实身份，使用统一入口领取：

```text
python <skill-dir>/scripts/behavior_early_quick.py claim --state <U>/dispatch.json --lane setting|interaction --agent-id A
python <skill-dir>/scripts/behavior_early_quick.py extend --state <U>/dispatch.json --lane L --identity ID --read-path relative/path.ets
python <skill-dir>/scripts/behavior_early_quick.py complete --state <U>/dispatch.json --lane L --identity ID --agent-stopped
```

领取失败便结束空闲 reviewer，不让其自行扫描。设置返回 setting_key，点击返回 contract_id，作为后续 ID。worker 只读返回的 source_root 快照；需要额外 ArkTS 路径先 extend，Android/SDK 原始证据正常读取并记录 SHA。所有剩余双域 writer 都参与冲突检查，不能自行绕过统一层调用原生 early_quick。正在运行的准备占用全局执行名额，也阻止跨过 Round 1 阶段屏障。

只提交 provisional draft，返回后停止，不在 worker 内等待。它不是 CLOSED_LIKELY，也不进入 Round 2。异常时确认 reviewer 已停止后执行 `defer`（参数同 complete），封存失败和快照、释放槽位；该入口交最终完整 Quick，不制造通过证据。

两域 Round 1 和全部提前 reviewer 结束后，运行唯一一次联合 Detector，生成两个最终 Quick plan。准备过的设置/点击入口单独分包；然后执行：

```text
python <skill-dir>/scripts/behavior_early_quick.py reconcile --state <U>/dispatch.json --lane L --final-plan Q
```

reconcile 将原 reviewer 与对应的单入口最终 batch、plan/packet SHA 持久绑定；该身份不能用于其它修复或审查批。通过统一 dispatcher 领取返回的最终 batch，恢复原 reviewer，核对最终 packet 的身份、hazard、消费者/角色、Android/SDK SHA 及 changed_sources。原 Agent 无法恢复时新建独立 reviewer 完整重审该入口。最终仍走正常校验与封存；所有 Quick 回执完成后才进入 Round 2。

## 热点修复

点击保留 target_writers、organization、共享根因证据及逐入口回执，遵循其原生协议。设置保持原生逻辑组/foundation 和 ownership 规则，不把同文件设置转换为点击 contract；采用文件锁/已认证方法体双批窗口、动态补位、共享证据、Quick 阅读族和上述提前准备减少等待。公共实现已经修复时，设置 worker 仍逐 key 核对完整效果链并如实输出 APPLIED/PARTIAL/NO_CHANGE/FAILED，不能重复修改仅为凑 changed_files。

封存也检查提前 reviewer 的活跃状态，并与派发共用 dispatcher 锁；仍有运行中的提前 reviewer 时不能创建结果锁。

## 任务交接与草稿生成

临时辅助脚本优先通过已安装工具或 stdin 完成。必须落盘时使用操作系统临时目录，位于 run 输出、应用源码和 worker 树之外；只有规定的 JSON 草稿、引用与日志进入指定证据路径。不要把 `review-*.author.py` 等脚本写进 baseline/round 目录，也不能用脚本替代真实语义裁决。此纪律随 `worker_context.temporary_helper_policy` 一起交给每批 worker；封存前按[统一目录检查](unified-workflow.md#7-所有终点保守导出)处理误放文件。

CLI 默认仅对新领取/刷新批返回完整必要交接；`active_batches` 只含身份和状态摘要，恢复时使用原 claim/recover 的交接结果，不能从活跃摘要猜 token。大型原生 `read_paths` 返回 `read_paths_ref`（原生 state 路径、batch ID、字段、条数、JSON 值 SHA）；需要展开时读取所指字段并核对值哈希，或用全局 `--verbose`。正式 state、原生副本及实际读集没有缩减。设置提前修复仍只使用外层 `reads`/`overlap_read_paths`，不能把原生全源码失效范围当实际获准读集。

`progress` 的 `diagnostics.pending_waits` 区分同文件 writer、成功依赖、读集不完整/过期、跨域冲突、manifest rebase、未 attach、执行额度及未发布副本额度，列出阻塞批和共享写路径。它是当前状态解释，不是原因持续时长；宿主容量未观测时保持 `UNOBSERVED`。不要把调度上限当宿主实际并发。

`diagnostics.stage_timings` 和 `run_summary.py` 的 `timing.dispatch_performance` 输出已完成批的阶段跨度/平均在途数、原生 claim/submit/publish 等命令累计调用数、失败数和耗时。命令计时覆盖调用整体，不能把 claim 全部耗时归因于复制；中断前未持久化的调用可能缺失。并行批时长不能相加当墙钟总时长。本次保持全量快照和 CAS，不采用硬链接或缩小保护范围。

需要字段枚举时执行 claim 的 `schema_hints_command`（`review_authoring.py schema-hints --plan P`）。它从当前安装校验器的字面常量提取取值及源码 SHA，不运行领域引擎，不选择状态；仍以本阶段的原生准入条件为准。不要为了找例子读取其它 batch 草稿。设置/点击 schema 不混用。

主会话直接转交 claim 返回的 `worker_context` 和 Repair 的 `task_packet`，包含本次安装的绝对协议路径、计划及命令。派发时不重新拼接长路径；子 Agent 不搜索全局 skill、历史运行或备份来猜字段。Repair 原样执行 task 的 startup/pre-submit argv，已绑定实际隔离 state。

保持既有 affinity/callable family 分组、包大小及动态补位；不为增加包数而拆散共享上下文。包数与执行槽位分别管理，完成即领取待处理包。公共证据沿用 catalog/阅读族引用，逐入口裁决不继承。

设置和点击 reviewer 先用 `scripts/review_authoring.py scaffold --plan <plan> --batch-id <id> --out <draft>` 生成身份、计划 SHA 和空义务骨架。该命令拒绝覆盖已有稿件；状态、完整性与判断留空，必须真实审查后填写。设置 Quick 只预填已绑定 consumer ID，不继承闭合结论。Repair 使用 task 自带 template。不要手写 SHA 或复制其它 batch 的草稿。

同一 worker 保留整个 batch 的共享上下文，每完成一个入口就更新指定 draft，不等全部完成后生成巨型 JSON。可用 `review_authoring.py update-item --plan P --batch-id B --draft D --expected-draft-sha H --item-json -` 从 stdin 接收一个完整 item；命令仅替换本批同身份项，原子落盘，返回新 SHA 和已填写数量。初始 H 用文件哈希工具取得，后续使用返回值；拒绝旧 SHA，不覆盖其它项。它不校验业务结论，已填写数量也不代表已通过。Review 两域与点击 Repair 均可使用；设置 Repair 保持原生模板。不得在停写交稿后继续更新。恢复时读现有 draft 的未完成项，不重新生成已有审查。

引用源码使用 `scripts/review_authoring.py cite --root <Android或ArkTS根> --path <相对路径> --line <行号>`，返回真实摘录和 SHA。复用已读证据时附加 `--expected-sha <已读SHA>`；漂移即拒绝，回读并重新判断受影响链后再更新引用，不能只刷新哈希。公共证据使用已有 catalog/共享分析引用，逐入口 verdict 独立。

Quick 使用 `quick_interaction_review.py validate-draft --plan <plan> --batch-id <id> --draft <draft>`。它与 publish 使用同一校验链但不写 fragment/seal；通过后停止写入、交主会话发布。Baseline/Quick 校验会汇总本批各失败入口的首个错误，一次处理所有返回项再校验，不必逐入口调用。格式校验不替代语义审查。

审查期间正式源码应保持稳定；发现外部编辑时记录影响路径并重新核对相关引用，不覆盖他人修改，不把旧快照的语义结论套到新源码。恢复上下文优先读取当前 packet 和已有 draft 的未完成项，按阶段加载已列出的协议。

设置 Baseline/Quick 使用 `review_authoring.py validate-setting --plan P --batch-id B --draft D`，只读调用本安装版本的原生设置验证函数并检查当前计划/catalog；不写正式 fragment 或 seal。逐 consumer 映射、终端链、优先级、默认值及原生规则保持不变。统一 claim 返回各 lane 的 `scaffold_command_prefix` 与 `validate_command_prefix`，分别追加 `--out D` 或 `--draft D` 执行；不要试用另一领域的校验器，不跨目录导入其它 skill 副本。

ENTRY_CHECK_ONLY 的 task 指向专用入口核对规则，只加载本批工单、绑定公共回执及适用域规则；不加载主调度/组织全流程。共享补丁事实读一次，逐入口独立核对，依赖发布和源码漂移检查保持不变。

修复模板按本批依赖顺序提供 `shared_dependency_checks` 的 batch_id 与领取时绑定的 receipt_sha256；状态仍为 null、证据为空。核对绑定回执及当前源码后独立填 CLOSED/UNRESOLVED，不能把预填身份解释为闭合。refresh 后使用新模板，不能保留旧回执哈希。

## 最终汇总

完成既有 finalize 后，运行 `python <skill-dir>/scripts/run_summary.py --out <U>`。
它只读执行原有完整结果校验，输出两域计数、改动文件、缺口和耗时，不发起修复或构建。
使用这份结构化摘要直接生成答复，不再临时编写多轮 PowerShell 字段提取命令。
`recorded_batch_span_seconds` 仅涵盖领取到完成，不包含 Detector/规划，不相加并行批次。
初始化到 result 文件 mtime 只是近似，复制文件会影响它，不能称为用户总等待时间。
宿主有明确的任务起止时间时可传 `--task-started-at <带时区ISO时间> --task-finished-at <带时区ISO时间>`；
没有可靠结束时间时 whole_task_seconds 保留 null，不能用当前时间冒充已结束任务时间。
