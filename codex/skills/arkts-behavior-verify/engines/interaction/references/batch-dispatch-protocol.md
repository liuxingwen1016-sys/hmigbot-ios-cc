<!-- when: 派发或恢复 Baseline、Quick、Round 1/2 的批次时读取 -->
<!-- topics: dynamic refill, claims, read/write conflicts, accepted manifest -->

# 批次完成即补位

新 Review 使用 [公共证据、依赖/复杂度分包与全槽位启动](review-efficiency-protocol.md)。初始化后先 `claim-ready`，派发所有返回批次再等待；同一 batch 中断沿用原 Agent，不把该恢复要求扩大到后续新 batch。

本协议替换阶段内部的整 wave 等待，不增加业务步骤。主会话等待任意一个 worker 返回，立即校验、封存该批并补满可用槽位；仍运行的批次继续执行。Baseline 全部收口才进入 Round 1，Round 1 全部收口才运行唯一一次中审，Quick 全部收口才进入 Round 2。`waves` 仅保留计划展示与旧产物兼容用途，不是新计划的运行屏障。

## Baseline / Quick Review

两者统一使用 `review_dispatch.py`，每次命令都传 `--plan <plan> --fragments-dir <fragments>`；默认状态在 plan 同目录的 `review-dispatch.json`，非默认位置需始终传相同的 `--state`。

1. `init` 验证 plan 与已发布产物；`claim-ready` 一次预留当前可用槽位，资源受限时使用 `claim --limit N`。
2. 只为返回的 `claimed_batches` 启动 worker；用 `attach-agent --batch-id B --claim-token T --agent-id A` 登记身份。每个 worker 仍只处理一个 packet，禁止再次委派。
3. 任一 worker 结束后，沿原协议校验并 `publish` 或保守封存；随后 `complete --batch-id B --claim-token T` 验证 fragment/seal，释放该槽位。立即再次 `claim-ready`（资源受限用 claim），不等其余 worker。

`progress` 区分 running、pending、ready 和空闲槽位。不能把 pending 或旧的 ready 列表当作新派发许可；`claim` 的 token 才代表成功预留。`release` 仅用于尚未绑定 Agent 且没有产物的预留，不能用它清除一个慢 worker。新 CLI 的 Baseline 分包按证据体积均衡利用并发槽位，仍遵守每包数量/字节上限和 exactly-once；Quick 保持原分包上限。

业务重审先保守封存并 complete，再用 `reopen --batch-id B --reason <内容失败原因>` 统一归档旧产物、恢复 pending；状态机械限制一次重审，保留历史 Agent。已有 dispatcher 时不再单独调用旧 reopen 命令。恢复此前已消耗重审的阶段时，在 init 中以 `--used-business-retry B` 导入累计，不能重新清零。只有工具明确证明旧身份丢失/不可恢复时才可 `replace-agent --batch-id B --claim-token T --prior-agent-id A --agent-id NEW --reason agent_unrecoverable --evidence <工具证据>`；仍受外层模型恢复预算约束。

## Round 1 / Round 2 Repair

新建 init 默认走[直接发布协议](direct-repair-protocol.md)：最多六个修复 worker，同文件单 writer，submit 后确定性 publish，不追加逐批 AI 复核。以下读写锁、四批上限及回滚语义仅用于已有 repair-dispatch 状态或显式 --execution-mode shared；不要将其套用到新 direct 模式。

### shared 兼容模式

新计划可含 [organization](repair-organization-protocol.md) 生成的公共前置批和局部入口批。
`SHARED_COMPONENT_ONLY` 代表回执不计作独立入口结论；隔离 incident 使用其
`affected_contract_ids`。局部入口使用 claim 的公共 receipt 引用并回填独立依赖检查。

`fast_interaction_repair.py plan` 的新 CLI 计划带 `dispatch_version=1`。由 `repair_dispatch.py` 完成登记、快照、差分与发布；每次命令传 `--plan <repair-plan>`，非默认状态需始终传相同的 `--state`。

普通批最多 3 个 contract；显式证明生成的 `shared_repair_unit` 按 [共享修复单元](shared-repair-protocol.md) 派发一个 worker，模式为 `SINGLE_SHARED_REPAIR_WITH_ENTRY_CHECKS`。共享批最终 UTF-8 JSON 不超过 180000 bytes；超限时同因分片，后片继续使用最新可信源码与有效共享补丁证据。所有模式仍每 contract 最多 6 个路径、每批最多 10 个 ownership paths，逐入口回执和下面的读写锁规则保持。worker 在本批内完成公共修复与全部入口检查，不另开核验阶段。

1. `init --execution-mode shared --source-manifest <latest-accepted-manifest> --results-dir <repair-results>`。Round 1 使用初始 snapshot；Round 2 使用 Round 1 dispatcher 最终返回的可信 manifest。
2. `progress` 取 ready；`claim --batch-id B` 逐批预留，随后启动 worker 并 `attach-agent --batch-id B --claim-token T --agent-id A`。claim 在任何源码阅读/编辑前冻结该批精确字节与读取证据，返回 baseline；worker 不再自行重新 snapshot。
3. 任一 worker 停止写入并交回 draft 后，`complete --batch-id B --claim-token T --draft <draft> --agent-stopped` 运行本批差分、preservation 和原发布器，只有通过后才推进 manifest、释放槽位。需要目标 scope 的批次仍传 `--scope-target` 与 `--scope-guard`。立即 claim 新的依赖就绪批次，无需等同 wave 的慢批。
4. 无法发布且本批修正额度已耗尽时，先确认 worker 停止写入，使用 `fail --batch-id B --claim-token T --reason <具体原因> --agent-stopped`。它精确恢复本批字节、验证清洁差分并封存 FAILED；越权改动无法归属或恢复时仍硬停。失败不授权全仓回滚。

候选必须满足并行上限四批、前驱已收口，以及自己的写集合与运行中批次的读/写集合均无冲突。只读同一文件可以并行。`read_paths` 复用已有 Review 的源码锚点，不递归扫描全仓 imports，也不宣称推导出了完整读取集合。主会话在 claim 时用 `--read-path <项目相对文件>` 补充已知读取范围；无法限定时使用 `--exclusive` 等待独占执行。Android/SDK 证据保持只读。

Worker 只能编辑 ownership。读取未登记的项目文件前，主会话先执行 `extend-reads --batch-id B --claim-token T --read-path <文件>`；成功后使用返回的新 baseline 引用，原 ownership 字节不变。不能直接读取另一个批次的半成品。新增读取与运行中写入冲突时，交回当前有界结果并明确缺少的依赖证据，供既有中审处理；不能持锁互等、扩大 ownership 或绕过冲突。

源码基线始终是“已验证并发布的源码”：完成 A 时仅合入 A 的 ownership，B 正在写的文件保留原可信哈希。后批据此冻结；外部改动、读取漂移、重复 writer、plan/token/manifest 漂移均拒绝。涉及目标 scope 时，原发布检查只扫描一次“可信源码加本批最终改动”的临时只读视图，不读取其它批次半成品；原有阻断判据不变。旧 `diff-wave` 只供原静态计划恢复，不得与新 dispatcher 混用。

计划中的 `depends_on_batch_ids` 表示源码读写次序。前批失败且已精确回滚封存后，同文件 sibling 可从当前可信源码继续；claim 会提供失败前驱，worker 在既有修复中核实缺失补丁是否是实际业务前置。确实依赖失败补丁时保留 `DEPENDENCY_MISSING` 或 `BLOCKED_BY_FAILED_DEPENDENCY`，不能假设前批已修好。源码保护成功、批次 COMPLETE 与功能正确是不同证据。

## 共享补丁证据与耗时

`complete` 只从正式发布且实际有 diff 的 `APPLIED/PARTIAL` 回执生成
`sealed_patch_evidence`，绑定 receipt、source-diff、相关 ownership/read 源码 SHA 与
具体根因摘要。后批 `claim` 返回 `shared_patch_evidence` 的有效命中和失效原因。
先读相关命中摘要，必要时按引用回读；源码/回执变化或有活动 writer 时不复用。
同路径但根因、命令参数约束或 variant 语义不同只作上下文；相同根因也只复用分析与补丁证据，
每个入口的参数、事件、状态、消费者仍需独立核对。不能自动继承前批的 verdict。

显式共享单元的后片也遵守上述有效性检查：公共修法已经等价时不重复改 owner，仍需为
本片每个 contract 检查 binding、input identity、variant、consumer、observable 和九角色。
一个入口的残留不覆盖其它入口的结果，也不能省略该入口；按现有状态逐项发布并交既有 Quick。

Review 的 `progress.timing` 报告 UTC 时间、已测批次/contract 数和耗时；
样本不足为 `UNKNOWN_INSUFFICIENT_SAMPLES`，足够后给
`ESTIMATE_NOT_GUARANTEE` 与乐观/串行剩余区间。估计只基于同阶段已完成样本，
不能覆盖未知后续轮次、构建或模型等待；共享文件锁会降低实际并行度。
Repair 读取 claim 中的
`shared_patch_evidence` 和 state 的批次时间，不假设 progress 有 timing/reuse 字段。
不把命中次数换算成未经测量的节省时长。
不新增全仓扫描，不增加轮次，也不通过提高路径/并发上限追求速度。

## 恢复

主会话串行执行 claim、发布/失败收口与状态更新；worker 只写自己获准的源码或 draft。进程状态锁只覆盖短命令，不持有整个模型调用。只有确认 worker 停止写入后才能收口；模型错误和普通等待超时均不自动释放 claim、源码锁或 agent 身份。

Repair 续跑前可用 `check --batch-id B --claim-token T` 核对活动批次差分；它不推进 manifest，也不重新冻结 ownership。只有旧身份已被工具证实不可恢复时，Repair 才使用与 Review 相同的 `replace-agent` 参数并附 `--agent-stopped` 更换身份，保留 claim 与原快照。

429/capacity 继续原 Agent，使用 [模型恢复的独立预算](fast-workflow-protocol.md#子-agent-模型故障续跑)。同一 batch 的业务重试计数、模型恢复次数与退避累计在恢复或换上下文时保留；状态文件不可删除重建来清预算。Review 业务重审至多一次；isolated Repair 的代码适配至多两次 refresh。模型恢复仍至多三次/累计退避 180 秒，两轮修复与一次中审均不变。只恢复缺失的调度步骤，已封存批次不重复执行。
