<!-- when: 启动、恢复或结束 fast_fix 时读取 -->

Baseline 合并后、修复组织或注册前，先执行[局部规划恢复](planning-recovery-protocol.md)：已有证据协调归属，必要时一次少量补证并独立封存；最终只挂起受影响工单，其余继续。独立点击流程同样适用。

<!-- topics: stage order, same-agent model-error resume, non-gating, build, install -->

# Interaction-handler 双轮快速流程

固定修复顺序：`result init → minimal preflight → baseline full detector → compact review → Round 1 → one full detector + quick review → Round 2 → post-edit scope guard（仅 playback/download 目标）→ build → install`。常规流程可在用户授权范围记录目标 runtime evidence 后 finalize；用户要求独立验收时，先 finalize/validate 封存，再在独立目录只读验收并报告，不回灌修复或改写原结果。

阶段内部按 [动态批次调度](batch-dispatch-protocol.md) 完成即补位：Review 使用运行态槽位；direct Repair 使用同文件单 writer 与业务依赖。新计划不用整 wave 屏障；主会话逐批收口，阶段间顺序不变。

Baseline `plan` 固定使用[核心候选](candidate-policy.md)。领域定向使用 `--target-domains` 与核心范围取交集，精确目标用 `--contract-ids`；正式 packet 消费计划绑定的 scope guard。Round 1 后的全量 detector 只运行一次，固定输出到 `<out>/post-round1/report.json`。Quick `plan` 根据待复核工单的领域扫描当前源码，并绑定新的 guard 与 `adapter_profile`。未知实现保留 `ADAPTER_UNRECOGNIZED` 证据缺口。Reviewer 在冻结 Round 2 前确认 hazard 的调用/状态依赖与 owner，将必要共享服务纳入 targets；脚本不凭同属一个领域就生成修复工单。

Round 2 后不追加 Detector、AI Review、Admission、preservation contract、Closure、correction、Round 3、tests 或 final gate。只完成既定 post-edit scope、构建安装，以及用户已授权的目标运行时场景；用户禁止 UI 操作时跳过场景并保留未验证状态。

只复用 hash 与 schema 均可机械验证的正式产物。Review draft 先经 `validate-draft`：机械格式失败在原上下文纠正，不消耗语义重试；真实内容审计失败或质量闸拒绝才在剩余业务重试额度内用新上下文重审。模型服务故障按下节独立计数并续跑原 Agent；等待超时或无 draft 不能直接触发重建。业务重试额度耗尽仍有内容失败时以 `UNREVIEWED`/`REVIEW_FAILED` 封存并继续其它批次。普通 `fast_fix` 合并这些保守状态，planner 只消费质量合格的 `FIX_REQUIRED`；只有用户显式要求参考标准审计时，才重开失败/模板化批并要求 `progress --require-complete`。产物漂移只重做对应阶段，不从聊天记录推断完成。Baseline merge 后必须执行 review `quality-check`；若发现局部质量失败，在剩余业务重试额度内重开并重试对应 batch，仍失败就封存为 `UNREVIEWED` 后重新 merge/quality-check，禁止把失败记录送入 Round 1。源码 manifest 按修复 batch 递进：每个通过或失败隔离并封存的 batch 产出/确认当前 manifest，后续 batch 及 Round 2 只绑定最近的可信 manifest，不得把初始 manifest 当作整个流程的永久基线。

## 子 Agent 模型故障续跑

本规则覆盖 Baseline Review、Quick Review 和两轮 Repair 的子 Agent。仅依据调度工具返回的模型服务错误识别暂时限流 `429/rate limit`、`Selected model is at capacity. Please try a different model.` 或同类服务中断；应用自身的 HTTP 429 不属于本规则。

- 主会话在现有调度记录中保留 `stage/batch_id → agent_id`。原 Agent 仍运行时继续等待；等待调用超时不等于任务失败。已因模型错误停止当前 turn、但 Agent 仍存在时，使用当前 CC 宿主实际提供的 Agent/Task 恢复接口，以原 Agent ID 续跑当前 batch，见[CC 调度映射](../../../references/unified-dispatch.md#claude-code-host-mapping)。仅发送消息不代表已启动续跑；恢复接口不可用时保留缺口，不伪造恢复成功。
- 两类预算按 `stage/batch_id` 分开累计，stage 区分 Baseline、Quick、Round 1 和 Round 2：业务重试（内容质量重审）仍最多一次；模型故障独立允许最多 3 次恢复调用、累计退避等待最多 180 秒。模型恢复不消耗业务重试，也不增加修复轮次。同 Agent 续跑、因身份丢失创建替代或业务重审换 Agent，都继承该 batch 的累计计数；一次服务恢复成功也不重置模型预算。
- 尊重服务返回的重试时间；未提供时等待 30 秒再续跑，长等待拆成不超过 60 秒的片段，期间可处理独立批次。下一次退避若会超过剩余模型等待预算，就停止本批自动恢复，不提前调用。每次模型恢复 turn 或替代创建尝试在调用前计入恢复次数，调用失败也计数；普通运行中等待不计恢复次数。容量不足不授权切换模型，也不以 `Agent` 绕过预算。
- 续跑仅恢复原 batch；新 batch 仍创建独立上下文，不继承“中断 Agent 不新建”的限制。模型故障续跑沿用同一 batch、plan/packet、ownership、draft 路径和已成功冻结的 baseline/manifest；代码恢复 refresh 则使用返回的新 worker_root/draft_path，两者不可混用。先核对已有产物；已有效发布的不重复执行或发布。Repair 已有改动时，用 dispatcher `check` 和原快照核对活动 ownership diff 后继续，不能重新 `batch-snapshot` 把半成品当基线；模型错误本身不触发立即回滚。
- 模型故障恢复时，只有没有成功创建 Agent 身份，或工具明确报告原 Agent 已不存在/不可恢复时，才在剩余模型恢复预算内创建替代并交接正式产物；连续 capacity、429、无 draft 或一般 `errored` 状态不能证明身份不可恢复。模型恢复次数或等待预算不足以继续时，按既有批次隔离流程记录模型服务原因；不扣业务重试，也不得把仍因模型故障产生的无 draft 改判为业务失败，借业务重试继续调用模型。Repair 仍须经 dispatcher `fail` 丢弃隔离副本并封存，不得把服务故障伪装成业务审计结论。

`fresh_context_per_batch` 只要求不同 batch 隔离，不要求同一 batch 的模型错误恢复另开上下文；Quick 的 `retry_guard/retry_resolution` 仍只处理旧修复拒绝与新代码证据，不参与模型服务重试。

## 批次隔离与交付

引用提取/JSON 组装使用已安装工具或 stdin；必须落盘的临时辅助脚本放在操作系统临时目录，位于 run、应用源码和 worker 树之外。联合封存按[封存前目录检查](../../../references/unified-workflow.md#7-所有终点保守导出)执行；可纠正的辅助脚本落点问题先处理再重试同一 run 的 finalize，不重跑审查修复。目录阻塞尚未纠正时保留未封存状态并明确报告，这是下述“全局硬停仍需 finalize”的前置限制，不能删除证据或结果锁强行封存。

执行完整性是逐项准入门：`<out>` 只存证据，Review/repair/quick review 必须由真实 Agent
逐 batch 产出；脚本、模板、重复的 `UNCERTAIN` 占位文案或“有精确 edit target 却无具体阻塞”的
`NO_CHANGE + EVIDENCE_GAP` 均拒绝。单批拒绝只冻结该批：Baseline 用 `UNREVIEWED`，repair 用 dispatcher `fail` 丢弃隔离副本并封存，Quick Review 用 `REVIEW_FAILED`；失败项不进入后续自动修复，无关批次和构建交付继续。

每次隔离都用 `export_fast_result.py record-incident` 记录 stage、batch/contract、reason code 和 downstream action。默认采用 **continue-on-local-failure**：模型错误、429/capacity、普通超时、worker 无 draft、单批质量失败、合并冲突、单批 scope 失败、单个 worker 误写但差分可归属且可精确恢复，都不得停止后续批次；先分类处理：参数、路径和检查范围错误先修正命令重试；真实代码/draft 问题才恢复原身份或刷新 worker，必要时 `fail` 封存本批并立即补位。worker 启动前验证 `cwd == worker_root`，启动后运行 dispatcher `check`；正式源码出现可归属越权差分时，只恢复受影响文件到 accepted manifest，保留 worker 提案并重新在隔离副本处理。只有以下全局安全条件允许停止后续编辑：Android/ArkTS 源码根不可读、输出目录不可写、初始 source snapshot 无法建立、plan/manifest/artifact SHA 失真使 ownership 不可信、或越权源码修改无法精确回滚。全局硬停也不得遗漏 `finalize`；它应生成保守终态而不是留下未封存的 provisional 结果。

主会话每次收到完成事件先交接再补位：Review 使用 claim-ready；新 Repair 使用“核对实际 Agent 状态 → submit 已停写 draft → publish 待发布批 → progress → 按 claim_slots 逐个 claim/独立派发/attach → 再次检查完成事件”，见[直接发布协议](direct-repair-protocol.md)。RUNNING 只是登记，不证明 Agent 活跃；不能把只登记未启动的批次当作有效并发。没有可立即领取的 batch 时先检查活动批、依赖和恢复队列，全部批次终态后继续规定的后续阶段。

Preflight 不编译、不连设备。源码和输出安全是硬前置；工具链、签名、HDC 或设备只是 build readiness。使用 `build_preparation.py` 自动提取现有构建参数并扫描依赖；声明与 lock 齐全但 `oh_modules` 入口缺失时，最多恢复一次既有依赖，默认 60 秒超时，然后重扫。恢复失败或仍有缺口才记录 build-blocked 并跳过最终构建。Harmony 已生成 alias 标 `GENERATED_ALIAS`；冷构建的 `BuildProfile` 在模块/Hvigor 配置可证明生成来源时标 `GENERATABLE`；未知 bare import 不获得豁免或新增依赖。准备器及低层命令见[预检产物协议](preflight-protocol.md)。仅允许恢复依赖安装产物；不得改变源码、`local.properties`、bundle、依赖声明/锁文件、签名或用户环境。

问题数量、高风险/不确定、单批失败、无 diff、Round 2 未闭合均不构成 correctness gate；但 playback/download 的适用 blocker、未裁决 conditional 风险或失效的排除证据会阻止对应 contract `APPLIED`；源码绑定有效的排除裁决应复用。common interaction 不运行媒体/文件 scope，也不因缺少目标运行证据阻塞普通点击修复。已开始的源码修复不得因构建环境不足而回滚。

构建最多三次 attempt：首次加两次编译纠偏。纠偏只处理编译器明确指向、且位于两轮 ownership 并集的文件。安装最多一次；只有已授权的运行时场景才启动应用。
