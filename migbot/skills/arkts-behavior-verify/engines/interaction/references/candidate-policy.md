<!-- when: 解释点击候选范围或修改候选筛选脚本时读取 -->
# 固定核心候选策略

标准范围固定为 core，不提供 full、balanced、critical 或 `--candidate-mode` 开关。全量 Detector 的发现与依赖证据保留；筛选仅决定送入 AI 的初始入口。规则由 scripts/candidate_policy.py 的 CORE_KINDS 定义。

| 保留组 | 具体规则 | 保留理由 |
|---|---|---|
| 空/占位命令 | CLICK_HANDLER_EMPTY、CLICK_PLACEHOLDER、CLICK_HANDLER_NOOP | 有直接源码证据；仍需区分合法空拦截与遗漏功能 |
| 事件未接通 | EVENT_BINDING_MISSING、EVENT_BINDING_NOOP、EVENT_BINDING_DISABLED | 定位具体 consumer/default binding，不能仅看事件已声明 |
| 明确不可触发 | CLICK_DISABLED_CONTROL、STATIC_DISABLED_ACTION_VARIANT、UNREACHABLE_STATE_GUARD | 字面禁用或确定性不可达状态 |
| 动作分支缺失 | ACTION_VARIANT_DISPATCH_GAP | 当前可见动作集合与 dispatcher 不匹配 |
| 导航直接冲突 | ROUTE_PAYLOAD_TYPE_MISMATCH、ROUTE_PAYLOAD_CLASS_IDENTITY_MISMATCH、DUPLICATE_TERMINAL_NAVIGATION | 参数生产/消费或终止导航有具体冲突；即使信号级别为 conditional 仍保留 |
| 能力未实现 | EXTERNAL_CAPABILITY_EMPTY_RESULT、ERROR_ONLY_HANDLER_NO_COMMAND、USER_EXPORT_TO_PRIVATE_SANDBOX | 返回固定空结果、错误代替命令或导出落点不满足用户访问；仅在当前 profile 产生时入选 |
| UI 终端断链 | OVERWRITTEN_SHEET_BINDING、SILENT_NULL_SELECTION_GUARD | 点击写入被同宿主后续 Sheet 覆盖的显示状态，或已启用点击因 nullable 选择器无数据而静默返回；已有 STATE_CHANGE 不抵消这些证据 |


没有核心 finding 的领域命令不自动送审；领域目标与核心集合取交集。精确 contract IDs 保留用户明确点名的范围和顺序，且仍需完整双端审查，不能以原本未入选拒绝检查明确目标。

入选后不缩减九角色、Android oracle、SDK、scope、修复保护或 Quick。未知新规则不自动进入核心集合。结果固定记 candidate_mode=core，并保留候选全集、选中及排除原因；排除不是 NO_DEFECT。不存在旧模式恢复或模式切换。

新计划冻结 `policy_version=2`，包含 UI 终端两项规则。历史 `policy_version=1` 继续按原有规则校验，不能将新规则热加进已冻结批次。具体检测边界与修复要求见[Detector 候选解释](detector-candidate-rules.md#ui-终端与数据前置态)。
