<!-- when: 初始化、构建、安装或结束时读取 -->
<!-- topics: result.json, unverified terminal states, artifacts -->

# Interaction fast_fix 稳定结果

新 finalize 在 `candidate_scope` 中保留 Baseline 的候选模式、选择方式、目标领域、
筛选前候选数、实际送审数、排除数及排除 IDs，并与绑定的 Baseline findings 校验。
排除项不进入 NO_DEFECT、已修复或 deferred 计数。旧产物没有 coverage 时标记
`NOT_RECORDED`，不推定为已审查；元数据不一致时标记 `INVALID`，不能宣称全量覆盖。
这里的 筛选前候选数限于本次用户指定范围，不代表全应用入口数。

`result.json` 从第一步存在。固定 `domain=interaction_handler`、`mode=fast_fix`、`adapter=interaction-handler`、`test_status=NOT_RUN`。contract 使用 `kind=interaction`；未执行目标真机验证时使用 `verification_status=NOT_PERFORMED`、`correctness_claim=NONE`；目标真机记录完整通过/失败/阻塞后，分别使用 `RUNTIME_VERIFIED/TARGET_RUNTIME_VERIFIED`、`RUNTIME_FAILED/NONE` 或 `RUNTIME_BLOCKED/NONE`。

终态：`RUNTIME_VERIFIED`、`RUNTIME_FAILED`、`RUNTIME_BLOCKED`、`INSTALLED_UNVERIFIED`、`NO_REPAIR_INSTALLED_UNVERIFIED`、`REPAIR_FINISHED_NOT_INSTALLED_UNVERIFIED`、`REPAIR_FINISHED_BUILD_BLOCKED_UNVERIFIED`、`BUILD_FAILED_NOT_INSTALLED`、`INSTALL_FAILED_UNVERIFIED`、`PREFLIGHT_FAILED_NOT_INSTALLED`、`BASELINE_FAILED_NOT_INSTALLED`、`WORKFLOW_INCOMPLETE`。没有结构化真机证据时禁止使用 `RUNTIME_VERIFIED` 或任何 GREEN/PASS/STATIC_GREEN 结论。按[预检协议](preflight-protocol.md)完成有界依赖恢复后仍确定入口缺失/为空时，使用 build-blocked 终态，不执行最终构建；未安装不表示源码工作失败。

交付摘要从正式 Review plan/findings 的 coverage、scope binding 和逐 contract 结果区分：领域入口是否已审、仍未修复的静态 owner、等待的运行时条件。`PARTIAL`、未归属 hazard 或仅安装成功都不能概括为“播放/下载已修好”。 逐条列出用户报告入口的对应 contract 与未完成原因，区分命令能力和仅动作意图候选；某个可用入口不能替代另一个仍禁用的入口。scope 候选数量不能直接作为已确认缺陷数量。自动能力发现是有界源码启发式，不保证识别所有框架；显式目标与真实源码审计用于补足未知包装。

结果列出 Baseline review counts/contract IDs、两轮执行 counts/attempted contract IDs、quick review counts、changed files、build/install 状态、runtime evidence、reason codes、`incidents` 与 artifact path+SHA。每个 incident 固定包含 `stage / scope / batch_id / contract_ids / reason_code / downstream_action`；`CONTRACT/BATCH` 必须列出 contract，`BATCH` 必须列出 batch id。`repair_execution_counts` 是逐轮执行次数；`unique_repair_outcome_counts` 以较晚一轮为最终 outcome 对 contract 去重，`unique_changed_contract_ids` 表示至少一次产生源码 diff 的 contract，`deferred_contract_ids` 汇总未完成、未审、不确定以及 incident 隔离项。除 signed HAP 外，所有 artifact 必须位于当前 `out` 目录；依赖扫描、Review、plan 或 runtime evidence 指向上一轮目录时，`finalize`/`validate` 必须拒绝该结果。只有 `runtime-evidence.json` 的所有目标后置条件为真时，才允许写 `RUNTIME_VERIFIED/TARGET_RUNTIME_VERIFIED`；安装成功本身仍不能视为行为正确。子 Agent 只能提交 Round 2 handoff，最终 build/install/runtime evidence 和 `finalize` 由主 Agent 写入。无论流程正常结束、存在局部 deferred 还是触发全局安全硬停，主 Agent 都必须调用 `finalize`；局部失败不得把 `result.json` 留在 provisional 状态。

## 分开显示审查、修复与验收

组织计划中的 `SHARED_COMPONENT_ONLY` 回执只表示公共补丁，保留来源和保护证据；不进入
逐 contract 执行计数或覆盖入口 verdict。公共 changed_files 正常汇总，实际受其修改影响的
入口计入 unique_changed_contract_ids；最终 outcome 仍来自每条入口自己的正式回执。

`static_confidence_counts/contract_ids` 区分 `STATIC_NO_DEFECT`、`STATIC_APPLIED`、
`STATIC_PARTIAL`、`STATIC_NO_CHANGE`、`STATIC_FAILED` 和 `UNCERTAIN`。
`NO_DEFECT` 表示已审查无缺陷，不能并入不确定；`FAILED` 表示执行失败，不能并入未改。
这些均为静态证据维度，不证明设备功能已经通过。

`contract_summaries` 保留 `baseline_verdict/latest_execution/latest_round`，分别列
`static_gaps/runtime_gaps/runtime_verdict`；汇总对应的 `static_gap_contract_ids` 与
`runtime_gap_contract_ids`。依赖 owner 未修、scope 未决、失败批次和无法执行的
`deferred_work_orders` 属于静态缺口；明确运行时待证条件单列，分类未知不能猜成
“只剩真机”。某条新有效证据已替代旧 Quick 剩余原因时，不再把旧原因当当前待办；
仍未解除的其它根因/角色/scope 继续展示。历史 incident 保留，不能抹去执行失败记录。

`review_incident_recoveries` 只解除同一 run/stage/batch/contract 的局部审查错误：
必须有正式 fragment/seal、完整 SHA 绑定、dispatcher `COMPLETE` 及一致的合并结果。
当前 gap 和 reason 不再重复计算已恢复的审查错误，历史记录仍保留。全局完整性、
源码/ownership 风险和修复失败不能凭后来的审查成功解除。

`changed_files` 仅说明实际源码变化；`source_protection` 引用正式 source-diff 与
preservation 证据说明范围和状态。构建成功不能代替保护证据，预期修改也不是
preservation 失败。独立验收的前后完整哈希比较是另一项只读证据。

用户要求先封存再验收时，`result.json` 保留 Skill 结束时的静态/安装状态；
独立 `acceptance_plan.py report` 按入口、动作和状态列出真实结果，不调用
`record-runtime` 或再次 `finalize` 改写原结果。缺少设备证据写 `NOT_TESTED/BLOCKED`，
设备失败写 `FAIL`；报告不得将其中一个入口通过提升为整个领域已修好。
