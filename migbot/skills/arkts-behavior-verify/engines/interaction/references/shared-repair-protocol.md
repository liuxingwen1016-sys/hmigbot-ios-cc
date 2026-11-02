<!-- when: Review 确认多个入口共有一个修法，或 Repair plan 含 shared_repair_unit 时读取 -->
<!-- topics: shared_repair proof, cause key, bounded shared unit, entry checks -->

# 共享修复单元

每轮规划先用 [共享根因组织](repair-organization-protocol.md) 处理重复 callable。
下面的 per-entry `shared_repair` 继续兼容；没有该可选字段时，组织步骤仍能从真实裁决生成
统一公共证明。混合公共/局部 targets 由组织步骤拆分，不要求删除入口独有修改来满足此协议。

普通修复批最多 3 个 contract。只有 AI 明确确认多个入口命中同一个共享断点、采用同一修法和命令语义，且完整 `edit_targets` 相同，才生成一个 `shared_repair_unit`，模式为 `SINGLE_SHARED_REPAIR_WITH_ENTRY_CHECKS`。每条 target 都必须属于这一个公共修法；含任一入口独有修改时仍走普通批。共享文件、领域、callable 提示或相似文案本身不构成证明。

## Review 可选证明

Baseline `FIX_REQUIRED` 或 Quick `ROUND2_REQUIRED` 可填写 `shared_repair` 对象。此例外只支持已有 `.ets` 的 `SOURCE` targets；配置权限目标继续走普通批。未确认时省略；旧 records 无此字段仍兼容。

| 字段 | 内容 |
|---|---|
| `schema_version` | 固定 `1` |
| `status` | 固定 `CONFIRMED` |
| `cause` | 精确共享机制、源码符号及触发断点 |
| `correction` | 一个可同时解除这些入口公共断点的修法 |
| `command_semantics` | 共同命令约束，包括必须保持的参数与 variant 语义 |
| `shared_evidence` | 非空 `[{path,line,excerpt}]`，逐 target 覆盖其 path 及 anchor/callable 的精确源码位置 |
| `entry_evidence` | 非空 `[{path,line,excerpt}]`，定位本条 contract、实际 binding 或 consumer |
| `entry_checks` | 对象，`binding/input_identity/variant/consumer/observable` 五个字段分别填本条非空字符串核验描述 |

证据使用项目相对源码路径、真实行号和该位置的精确片段。Baseline 两类证据必须是本条 `arkts_evidence` 的成员，不能借用另一个 contract 的入口证据。Quick 直接严格读取当前源码，对本次剩余断点重新填写 proof；Baseline proof 只作历史上下文，不继承到 Round 2。guard 降级或清空 repair-shaped 字段时同时清除 proof。

脚本从当前 `contract.path/line` 和具体 `consumer.instance_path/instance_line` 派生 `entry_locations`（不由 AI 填写，也不进入公共 key）；`entry_evidence` 必须覆盖本入口的绑定/实例行，同文件另一按钮的证据不能借用，无可信行定位时不声明共享 proof，普通修复仍可继续。

脚本校验片段与 targets，为每条引用绑定 `source_sha256`，为 proof 绑定 `cause_key`；AI 负责判断共享机制成立。公共 key 保留完整 targets、共享证明和源码绑定，不包含入口个别证据或检查描述；完整 proof 仍逐 contract 保留。`cause/correction/command_semantics` 的自然文本须严格一致才自动分组，可复用精确源码符号描述同因；不得为了合并而抹去参数、variant 或独立断点差异。源码漂移、证据不足或完整 targets 不同不享受共享数量例外。

## 计划与执行

共享单元不按三个入口拆批；以最终 batch 的序列化 UTF-8 JSON 计算体积，上限为 180000 bytes。超过时按同因分片；单项已超限则回到普通批，不删除证明或丢弃候选。所有模式仍每 contract 最多 6 个路径、每批最多 10 个 ownership paths。新 direct 模式最多六个修复执行名额，同文件单 writer，交稿后确定性串行发布（见[直接发布协议](direct-repair-protocol.md)）。同因后片冻结最新可信 source manifest，并按有效性检查复用已封存共享补丁证据。

共享 proof 仅使用现有动态 dispatcher，CLI `plan` 默认已启用，无新参数；库调用 `make_plan(..., dynamic_dispatch=False)` 遇 proof 会明确拒绝。普通旧格式保持兼容。

一个 worker 在同一 batch 完成公共修复与逐入口核验，不增加独立核验 Agent。先核对当前公共 owner，只实施一次共享修法；源码已等价时不重复改。然后逐 contract 核对 binding、input identity、variant、consumer、observable 与既有九个效果角色，分别记录具体源码证据和 `APPLIED/PARTIAL/NO_CHANGE/FAILED`。批次中的每个 contract 都必须有独立结果，公共补丁不能让全体继承 `APPLIED`。

按既有 changed files、根因、平台契约和角色规则发布：已等价且无新改动的入口不能为了报 `APPLIED` 制造差分；各自未闭合项按实际修改与缺口给出 `PARTIAL/NO_CHANGE`。独立残留交既有 Quick Review 定向，Round 2 残留照常封存；不扩大 scope、不增加轮次，也不因共享 owner 已修而跳过候选。
