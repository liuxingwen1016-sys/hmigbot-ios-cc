<!-- when: 新建 Repair 调度、交稿发布、补位或恢复 direct 批次时读取 -->
<!-- topics: six repair slots, single writer, deterministic publication, one quick review -->

# 并行修复与直接发布

新 CLI `repair_dispatch.py init` 默认 `publication_policy=direct`，最多 6 个修复
执行名额，不预留 reviewer。两轮均采用本协议；Baseline 与一次 Quick Review
仍由真实独立 Agent 审查。逐批发布只做确定性检查，不创建 AI 合并复核回执。

新 Repair plan 标记 `repair_execution_version=2`、`max_parallel=6`，dispatcher
与其共用默认配置；`waves` 的旧四批展示不限制 isolated 执行并发，也不沿用
Baseline Review 的并发值。平台总名额包含主 Agent：可用于修复的容量需扣除主 Agent
及其它实际占用。默认不传 `--max-parallel`；只有平台容量不足或用户指定时才显式降低，
并简述依据。既有 plan/state 不改写，新建 direct dispatcher 也不从旧 plan 的 4 推导上限。

行为效果统一入口只创建直接发布状态。使用新的输出目录，既有其它模式由原 skill 处理，不在本入口恢复。

## 规划与并行边界

重复热点 writer、跨批 handler 证据与尾部空闲 Quick 按[重叠执行协议](overlap-execution-protocol.md)。
符合热点条件时从原始 plan 做 target writer 分配，不叠加 organization；不同入口语义仍分别保留。
启动 start-worker 只检查租约与初始差分，不能执行 finish；finish 仅在确认 worker 停写后调用。

先完成 [organization](repair-organization-protocol.md)：同一真实断点及公共修法
只生成一个 owner；不同 anchor 写法使用显式源码映射，不机械拆成重复修复。
逐入口义务和回执保留，入口独有修复放到公共修复之后。

不同 ownership 文件可并行；同一文件从 claim 到正式终态只有一个 writer，
包括已交稿尚未发布的批次。后继 claim 冻结最新可信字节，避免多个旧副本反复合并。
读取仍来自独立快照，登记 read_paths，但读写交叉本身不封锁全部并发。
确需另一批业务结果的依赖继续等待。发布记录依赖字节变化及受影响旧入口，
交 Quick 在整轮稳定源码上做语义判断；机械合并成功不证明行为兼容。

## 主会话补位循环

每次收到 Agent 完成事件，先处理交接，再处理补位；不要先等待其它 worker。

1. 核对平台实际 Agent 状态与 dispatcher `progress`。
   `RUNNING` 只是已登记，不证明 Agent 活着。已完成且有完整 draft 的批次立即
   `finish --agent-stopped`（串行完成 submit、publish 并返回 progress）；无 draft 的局部失败按恢复预算处理。普通等待超时不能推定已停止。
2. 对 `publication_queue` 立即运行 `publish`，每批只执行短命令检查，不插入
   AI 读代码步骤。某批需要 refresh 时移交恢复，其它无关批次继续发布和补位。
3. 按 `claim_slots` 和当前 `ready_batches` 逐个 claim；每次成功 claim 后立即
   创建独立新 Agent 并 attach，不能只绑定已完成 Agent 的 ID。
   `pending_agent_batches` 必须派发，或对没有 Agent/改动的 claim 执行 release。
   新 dispatcher 在有未 attach 的 claim 时拒绝继续领取；不要批量 claim 后再准备派发。
   worker 通用说明应在领取前准备好，领取后只填本批路径与身份并立即 spawn/attach。
4. 新 batch 使用新 Agent；原 Agent 只可恢复原 batch。attach 会拒绝跨批复用 ID。
   按[CC 调度映射](../../../references/unified-dispatch.md#Codex-host-mapping)创建独立上下文；新 Agent ID
   不代表空白上下文。claim 的 `new_agent_options` 是内部元数据，不直接传给 CC 工具；同批恢复仍用原 Agent。
   派发消息只带本批 plan/身份、worker_root、draft_path、工单与必要
   协议路径。先准备通用说明，再 claim，spawn 返回后立即 attach，不在两者之间做其它审查。
   平台 Agent 配额未释放时，先确认平台完成/关闭状态，不把写 JSON 当释放配额。
5. 重读 progress，继续处理已完成事件、发布队列和就绪项。
   总执行名额不超过实际平台容量与配置上限的较小值；未发布副本最多 `2*max_parallel`。

命令均使用同一 `--plan P`，自定义状态均加同一 `--state S`：

```text
repair_dispatch.py init --plan P --source-manifest M
repair_dispatch.py claim --plan P --batch-id B
repair_dispatch.py attach-agent --plan P --batch-id B --claim-token T --agent-id A
repair_dispatch.py submit --plan P --batch-id B --claim-token T --draft D --agent-stopped
repair_dispatch.py publish --plan P --batch-id B --claim-token T --agent-stopped
repair_dispatch.py progress --plan P
```

worker 只读本批工单、适用修复规则、双端源码/SDK 和必要依赖，不重新执行 Baseline、
organization 或 Quick。启动先在绝对 worker_root 执行 check；完成时返回
batch ID、token、draft 绝对路径及“已停止写入”。原 draft 交稿后不可修改。
派发消息必须带上 claim 返回的 `draft_path`，worker 直接写到该绝对路径；它在
worker/base 源码树外，父目录已创建。draft、日志都不能写进 worker 源码树，
即使是其中的 `spec/` 子目录也不允许。refresh 返回新的 draft_path，旧稿保留，
新交稿不得复用旧路径。dispatcher 只把平台实际 spawn 返回的身份用于 attach，
路径检查和 attach 均不能替代真正启动 Agent。

新 claim/refresh 自动生成带 SHA 的 `task_packet` 与 `draft_template`，按
[单批任务协议](worker-task-protocol.md) 派发，省去重抄计划与手填机械字段。
任务包含本批工单、公共回执和完整链责任提示；既有 claim 不回写。
模板无语义默认值；恢复同批先读自己的任务包与旧稿。两轮修复使用相同机制。

CLI 默认不输出完整 inventory、journal 和历史副本；必要时用 `--verbose` 或按路径
读取状态文件。主会话只消费紧凑摘要，不重复打印全量 manifest。
新 direct 发布默认只返回状态计数、逐入口状态和 `result_path/result_sha256`；完整九角色、
根因和证据仍在原回执，`--verbose` 返回全文。发布成功不需主会话逐项重读完整回执。
可把刚取得的平台 list_agents 响应写入证据目录，运行
`progress --agent-status <snapshot.json>`，生成 SUBMIT_OR_RECOVER / DISPATCH_OR_RELEASE
提示。该命令不重置任何名额，也不把快照或超时当作停写证明。

## 发布与局部恢复

publish 冻结交稿哈希，内部 prepare 三方候选、绑定原 draft 并调用原发布器。
只补 candidate 身份，不合成根因、九角色、入口通过或 ALREADY_EQUIVALENT 结论。
ownership、外部源码 CAS、preservation、平台/目标 scope、结果 schema 与事务日志继续生效。
新 dispatcher 按整批工单的 `current_scope_blockers` 自动决定检查范围，claim 返回
`required_scope_target`：播放与下载并存时为 all，纯单域取对应值，普通点击为 null。
publish 默认省略 `--scope-target`；显式参数只可扩大检查范围，较窄参数会与工单范围
取并集。公共修复也要包含入口工单的跨域证据，不能仅按本批修改文件或 batch 名选域。
发布器仍对实际候选重算 scope，保留真实 blocker 与逐入口结果校验；普通点击不做无关
媒体扫描。旧 direct 状态仍使用原 scope 参数规则。

交稿释放执行名额；同文件写名额在正式 complete/fail 后释放。
publish 的唯一发布预约只跨短命令检查，不跨 AI 思考。

- 短锁 busy：相同命令稍后重试，不算业务失败。
- 参数、证据路径或检查域不足：先修正命令后重试，不刷新源码、不消耗修复额度。
  仅“报告没覆盖已有 blocker”不证明代码或 draft 错误；显式检查范围需覆盖双域时传 all。
- preservation 拒绝时先读错误中返回的 report 路径及具体 violation，再决定恢复动作；
  不把 guard 的通用报错直接当作源码错误。确认工具误判时保留证据并报告 skill 缺陷，
  不在运行工程临时放宽 guard，也不让 worker 为迎合误判改写等价业务代码。
- 冲突、去重后差分与 draft 不符、或需改语义：确认 worker 停止，运行
  `refresh --agent-stopped`，让原修复 Agent 在新 worker_root 有界适配并重新交稿。
  最多两次 refresh；不覆盖旧 proposal，也不强制 ours/theirs。
- 检查拒绝需修 draft 时也走 refresh；不能编辑已 submit 的原稿。
- 恢复额度耗尽：`fail --reason ... --agent-stopped` 封存并丢弃副本，其它批继续。
- COMMITTING 中断用 publish 重试或 recover；PREPARED 中断重试 publish。
  正式源码外部变化仍保护原字节；不通过重置 manifest 吞掉用户改动。

## 审查与交付边界

回执写 `DETERMINISTIC_PUBLICATION / semantic_review=NOT_PERFORMED`，保存依赖变化
和受影响入口。它不是 AI 兼容性复核，也不改变修复 Agent 的逐入口结果。
Round 1 后仍执行一次 post-round1 Detector 和一次 Quick Review，重点读取这些变化
及公共修复，在最终组合上验证效果链。Round 2 不新增全量 AI 复审；保留
STATIC_UNVERIFIED，随后按原流程构建/安装、适用的已授权真机场景和 finalize/validate。

## 启动、提交前校验与一次收口

新 worker 进入 claim 返回的 `worker_root` 后运行 packet 的 `startup_command`
（`repair_dispatch.py start-worker`），一次核对真实 cwd、plan/claim、packet SHA 和
ownership。启动检查不代替角色规则阅读，不创建或冒充平台 Agent。

草稿完成后运行 packet 的 `pre_submit_command`（`validate-draft`）。该命令在原隔离
副本执行与 publisher 共用的结果正规化、字段/角色/平台/scope 校验、真实 diff 与
preservation 检查；不冻结 proposal、不发布结果、不修改主源码。失败时仍在原副本
修正，不消耗 refresh。新 direct state 的 `pre_submit_validation=1` 在 submit 前再次
确认这些检查；旧 state 不自动补字段，原 submit 行为保持。

主会话确认真实停写后运行：

```text
python <skill-dir>/scripts/repair_dispatch.py finish --plan <plan> --batch-id <batch> --claim-token <token> --agent-stopped
```

省略 draft 时读取 claim 分配路径。finish 可重试：已交稿不重复冻结，已完成返回原
receipt 与最新 progress；不绕过 publish 的候选合并、源码保护和串行事务。失败只影响
当前批，主会话继续处理其它完成事件。需要源代码纠偏或已提交稿修正时仍按 refresh
协议执行；不能用 validate-draft 的 PASS 替代正式发布。
