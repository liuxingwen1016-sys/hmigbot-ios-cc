<!-- when: 新建 Repair 分配热点 writer、处理跨批 handler 证据或提前启动 Quick 时读取 -->
<!-- topics: target ownership, handler receipts, provisional Quick, final context -->
# 减少修复尾部串行等待

只对新 plan 使用；既有 dispatcher 不热迁移。保持 direct 确定性发布，不新增 AI 合并
复核 Agent，主会话不承担语义合并。同文件同时写仍然互斥，优化发生在派发前分配 ownership。

## 热点文件只有一个修复 owner

先生成未 organization 的原始 Repair plan。统计同一路径出现在多少个修复批次中。
没有重复 writer 时使用原计划；重复目标确属同根因时仍优先原 organization。
同文件涉及不同入口语义、无法归为同一修法且至少三个批次争用时，使用：

```text
python <skill>/scripts/target_writers.py --base-plan <out>/round-1/base-plan.json --out <out>/round-1/plan.json
```

base-plan 必须是原始未拆分计划，不能覆盖它。转换结果按文件唯一分配 writer，并保留每个
入口的独立义务；相关小文件在合同数与字节预算内合包。worker 通过绑定 SHA 的
`target_writer_base` 和 `full_entry_contract_id` 回读完整上下文，不能凭局部切片推断全入口已修复。
原始 read_paths 冻结继承，验证计划时不重新扫描当前源码改变分组。

writer 直接发布自己的文件，返回 PARTIAL/NO_CHANGE/FAILED；不允许 APPLIED。
后续 ENTRY_CHECK_ONLY 批次只检查各入口与已发布回执，不合并、不写代码、不做完整 Quick。
入口只在该批次计数一次。其相关 read_paths 上剩余 writer 结束后才领取，避免重复检查。
不同文件 writer 可并行；新接口必须保留兼容签名或明确记录未完成接口义务，不能猜测另一个
writer 已实现什么。未解决跨文件问题交原有 Quick 和 Round 2，不可宣称已关闭。

此分配会增加轻量入口回执，不能保证所有任务提速。规划时比较原始批次数、最大同文件
writer 数与转换后的 writer/入口批次数：只有确有多次热点写等待才启用，不为两批偶发冲突
扩大流程。脚本遇到超大工单、行为替换义务或显式成功依赖会拒绝，保留原 bounded plan，
不删除义务、不自行绕过。每轮从本轮原始 plan 重新生成。

## 前置已修 handler 的证据

初始化会拒绝 handler 既不属于本批也无已声明前置 owner 的不可发布计划。
前置已修 handler 时，后继不为满足 changed_files 再改一次。填写 `handler_dependency_checks`：
`path`、`batch_id`、`receipt_sha256`、`source_sha256`、`line`、`excerpt`、`evidence`。
同时保留原 `shared_dependency_checks`。成功前置的发布文件 SHA 必须等于当前源码 SHA，
且摘录匹配当前位置。旧回执缺少 `published_source_bindings`、前置失败或源码漂移都不能用来
证明关闭。该机械检查只验证证据绑定，worker 仍须独立检查当前入口是否执行正确命令。

## 提前开始同一次 Quick

修复尾部有空闲槽位时，先处理完成发布和就绪修复，再尝试稳定入口。修复优先；修复与
提前 Quick 合计不超过 dispatcher 的 max_parallel。无需等固定的剩余批次数。

先创建等待任务包的独立 Quick reviewer，取得真实 Agent ID 后领取；领取失败则结束该空闲
reviewer，不让其自行扫描项目。命令使用默认 dispatcher state（自定义 state 暂不适用）：

```text
python <skill>/scripts/early_quick.py claim --plan P --agent-id A
python <skill>/scripts/early_quick.py extend --plan P --contract-id C --read-path entry/src/main/ets/example.ets
python <skill>/scripts/early_quick.py complete --plan P --contract-id C --agent-stopped
```

脚本要求该入口相关修复终态、已知读取路径与所有剩余 writer 无交集。reviewer 只读领取的
源码快照；新增读取必须先 extend，若文件仍可被写则延期。读取 Android/SDK 真值并保存 SHA。
reviewer 完成补丁、根因、九角色和反例检查后写 provisional draft，立即返回，释放执行槽位。
不在 Agent 内等待 Round 1 结束。不产生最终结论，也不另加一轮完整审查。

Round 1 全部终态且提前 reviewer 都已返回后，只运行一次最终 Detector，按原协议生成
最终 Quick plan。已准备入口分成单独 final batch，原 reviewer 恢复自身入口：

```text
python <skill>/scripts/early_quick.py reconcile --plan P --final-quick-plan Q
```

先通过原 review dispatcher 领取对应 final batch，再恢复返回的原 Agent；这是同一入口
Quick 的两段执行，不适用跨入口复用 Agent。对照最终 packet 的身份映射、hazard、retry guard、
Android/SDK SHA 和 changed_sources 补查；最终结论仍走普通 Quick validate/publish。
草稿没有自动验收效力。原 Agent 无法恢复则完整复查该入口，不能由主会话代写结论。
其它入口正常分包。所有最终 Quick 回执封存前禁止启动 Round 2。
