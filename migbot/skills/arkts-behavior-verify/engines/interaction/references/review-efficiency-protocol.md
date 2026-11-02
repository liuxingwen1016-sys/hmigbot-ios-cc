<!-- when: Baseline/Quick 创建计划、领取并行批次、读取公共证据时读取 -->
<!-- topics: shared source evidence, affinity grouping, complexity, full-slot startup -->

# Review 提速协议

新 Baseline 和 Quick CLI 默认 `--grouping affinity`。它只改变证据读取与任务分配，
不删除已选入口、不减少九角色/Android oracle/SDK 核验，不改变逐入口结果。初始候选固定按[核心策略](candidate-policy.md)确定。
已有冻结计划继续按原分包运行，不覆盖运行任务的 plan、packet、catalog 或 skill。
Baseline 的 `balanced/sequential` 和 Quick 的 `sequential` 保留作兼容。

## 一次派满，再完成即补位

主会话初始化 dispatcher 后，执行：

```text
python <skill-dir>/scripts/review_dispatch.py claim-ready --plan <plan> --fragments-dir <fragments>
```

自定义状态必须始终传相同 `--state`。`claim-ready` 一次预留全部可用槽位，最多六批。
主会话为返回的 **所有 claimed_batches** 启动独立 reviewer 并分别 attach-agent，
之后才等待任意一个返回。不能只启动第一批便等待，也不能让 Quick 的第一批成为
其余批次的前置。收口一批后再次 claim-ready；已登记 claim 不会重复领取。

`dispatch_advice` 给出空闲且可领取槽位、待绑定 claims 与下一步建议。
已有未绑定 claim 时按它原 token 派发，不再 claim 同批。平台剩余容量不足或用户限制资源时，
使用原 `claim --limit N`；没有可用上下文时保留缺口，禁止编造 Agent 身份。

“中断的子 Agent 在原来那个继续”仅作用于 **同一个 batch 的恢复**。
新 batch 继续独立派发；不能由此推导所有后续批次都交给同一 Agent。
按[CC 调度映射](../../../references/unified-dispatch.md#claude-code-host-mapping)创建新 reviewer；派发消息
只包含本批 packet、必要协议、输出路径与 Agent 职责。独立身份不能替代独立上下文。
Quick 使用独立于 Repair 的新审查上下文。用户明确要求全局复用/禁止创建时遵从用户，
说明并行与独立审查的限制，不把降低的并行误称为文件依赖。

## 共享源码与 SDK 定位证据

新 packet 的 `shared_review_evidence` 指向阶段独立、带 SHA 的 catalog。
catalog 只收集工单中明确引用的源码/SDK 声明路径，不按领域词猜依赖，不生成
FIX_REQUIRED、NO_DEFECT 或 CLOSED 公共结论。

同一文件在本阶段只保存一份精确字节快照，逐入口引用该文件及行号。
首次读取时，把 **本批全部 contract_id** 一并传给：

```text
python <skill-dir>/scripts/review_efficiency.py read --catalog <catalog.path> --catalog-sha256 <catalog.sha256> --contract-id <id1> --contract-id <id2>
```

工具会校验 catalog、快照和当前源码/SDK 哈希，每个相关文件只输出一次定位窗口。
窗口最多展示本批每文件前 12 个定位点，`additional_locations` 表示仍需回读的部分；
完整字节在返回的 snapshot，原文件路径和哈希同时保留。窗口仅用于定位，不能把
首行/声明头当作完整方法审计。未命中声明、缺少 Android 根或找不到文件会保留
`unresolved`，按原协议继续搜索，不能从“未收集到证据”推断没有问题。

Reviewer 在同一批内只需理解公共方法/SDK 声明一次，然后逐入口检查：绑定、输入身份、
参数和 variant、真实 Android 对应行为、消费者回读、可观察结果。公共方法相同不代表
入口同因，不省略入口特有分支，不复制其它入口的裁决或拼造模板证据。

claim 和正常 publish 都检查相应当前源码；变化即拒绝使用旧证据。保守失败封存仍可用，
不因当前源码变化伪造成功。历史 plan 校验只检查已冻结证据完整性，因此后续正常 Repair
不会破坏 Baseline 的历史证据。Quick 重新建立 Round 1 后的 catalog，绝不复用旧源码快照。
公共索引不能替代原有 patch_catalog、scope_hazard_catalog 或 full_record 引用。

## 分包策略

Baseline 的 `AFFINITY_COST_V2` 成本单位是公开启发式：源码路径数、独立 edit target 数、平台契约数、未解决角色数、动作 variant 数、Android
定位歧义、scope hazard 数和证据体积；它不是预测分钟数，也不评估缺陷严重程度。
先分派估计较重的批次，同成本入口按依赖族交错播种。只有在当前最轻批成本的
25% 容差内才优先共享依赖，避免把整个公共服务的入口堆成一个长尾批。
所有入口都共享的路径不能区分分组，不用于强制聚集。

新 Quick 使用历史兼容协议标识 `CALLABLE_FAMILY_COST_V3`（不是 Skill 名）：先把同一 SOURCE 路径和 callable 的入口
作为阅读族，按数量及估算负载切分，再调度；同文件不同 callable 不强制归并。
多族入口只选一个主族，不重复派发。大族为数量/负载上限与可用槽位拆开，
单个超重入口独立保留；正常批成本上限取目标批数对应平均成本的 1.25 倍与
按平均入口成本向上取整的批成本之较大值，避免 13 项因不能均分六批而硬拆第七批。
目标批数同时考虑六个槽位与每批数量限制，避免用六槽平均值低估多波次长尾。
先运行较重批次并持续补位，不为“只读一次”设置公共 reviewer 或减少可用并行。

Baseline 仍保持原 contract 数量和 **实际序列化 packet 字节**上限；单个超大工单
仍显式标记，不截断证据。Quick 保持每批数量上限，不宣称有新的 packet 字节硬门。
两者尽量使用六个槽位，允许为数量/字节限制生成更多批；最终合并恢复原入口顺序。

## Quick 公共分析与逐入口裁决

新 affinity packet 的 `shared_chain_catalog` 只表示共同 callable，尚未证明同因。
核对命令、参数与后置条件后，可在 draft 顶层写一份公共源码分析：

```json
{"shared_chain_reviews":[{"chain_id":"<catalog key>","analysis":"<当前公共链分析>",
  "evidence":[{"path":"<project-relative source>","line":1,"excerpt":"<真实源码片段>"}]}]}
```

适用入口增加 `shared_chain_refs:["<catalog key>"]`，无需反复复制公共段落；原有
`evidence` 写入口特有身份、参数/variant、Android oracle、consumer 和 observable，
状态、九角色、根因、scope 决策与 Round 2 targets 仍逐入口填写。公共记录不能含
status/verdict/角色结果，不转移通过结论。证据至少引用一次公共 callable。
发布器校验当前源码后展开公共文字，继续逐条执行原有 normalize/闭合否决。

`workflow_packets.py quick-shared --plan P --batch-id B --fragments-dir F` 只读取本计划
已有合法 seal 的公共分析。先核对入口关系再引用；记录冲突则重新分析。
没有记录就自行读源码，不等待其它批、不设首批前置。因此跨批去重是机会性复用，
同时启动的 reviewer 仍可能重复分析；主要收益来自同族分包和批内一次分析。

新 Quick 计划绑定应用源码及 JSON/JSON5 配置（排除构建、依赖、spec 和工具目录），
新增文件或字节变化都会拒绝复用及正常发布。Android/SDK 引用另由原 catalog 校验。
绑定不是语义证明；范围外仍按原协议搜索。源码变化后重新建 Quick 证据，
不扩大到 Round 2 后复审。旧冻结计划继续原有语义，不补写缓存或更改运行批次。

Baseline affinity 同样使用按实际目标批数计算的软负载上限：在保留数量与序列化字节
硬边界时，过重组合另开批次，单个超重入口不截断。成本来自当前工单的结构特征，
不使用某次运行的耗时标签、应用名或文件名，也不将成本换算为固定分钟数。
较重批优先派发；公共源码/SDK 证据按当前 SHA 引用，变化失效时才重新读取对应证据。
上述调度版本只写入新计划，不重新分包或改写正在执行的冻结计划。
