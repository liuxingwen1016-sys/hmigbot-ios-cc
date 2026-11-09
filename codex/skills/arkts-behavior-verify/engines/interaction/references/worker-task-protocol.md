<!-- when: 启动或恢复单批 Repair/Quick worker 时读取 -->
<!-- topics: role boundary, task packet, mechanical template, source evidence -->

# 单批任务与恢复

主会话持有调度、发布与交付；worker 只负责派发消息指定的一个 batch。
新 batch 按[CC 调度映射](../../../references/unified-dispatch.md#Codex-host-mapping)新建独立上下文；同批中断恢复原 Agent。
压缩上下文后先重读自己的任务包与未完成 draft，继续已有工作。
项目根 handoff 是主流程记录，不能据此接管其它批、Round 2、构建或 finalize。

## Repair worker

工单含 target_writer_base、writer_dependency，或 handler 已由前置修复时，先读
[重叠执行协议](overlap-execution-protocol.md)，依其完整入口引用与 handler_dependency_checks 交稿。

新 direct claim/refresh 返回 `task_packet.path/sha256` 和 `draft_template`。
主会话传这两个字段、plan、batch、token、状态路径与 worker_root，无需重写工单。

```text
python <skill-dir>/scripts/workflow_packets.py read-task --task <task_packet.path> --task-sha256 <task_packet.sha256>
```

该命令检查任务与计划 SHA。开始或恢复编辑前仍执行 dispatcher `check`，验证当前
token、worker_root 与 live state；任务包不是租约证明。extend-reads 后以 live state
为准。refresh 后使用新任务包、新 worker_root 和 draft_path；旧稿仅作恢复线索，
先核对新副本与已有补丁，再继续修复。

ENTRY_CHECK_ONLY 使用 [入口核对规则](entry-check-protocol.md)，无需加载通用修复和组织流程；
其它 Repair 读取 [修复规则](fast-repair-protocol.md) 与本批双端源码/SDK。公共单元或依赖才读取
[共享证明](shared-repair-protocol.md) 和[公共/局部责任](repair-organization-protocol.md)；
异步命令或共享服务才读取 [依赖审计](effect-dependency-review.md)。无需加载整个主流程
协议或其它批的工单。本批涉及的特殊域规则仍须读取。
命中播放/下载能力时读取 [媒体域规则](media-effect-rules.md)，保留 SDK 合法状态与稳定可见性检查。
解释具体结构 finding 时按需读取 [候选解释](detector-candidate-rules.md)。

动手前用 `closure_map` 一次检查完整 REQUIRED 链：已有实现如何满足、公共前置
负责什么、本批负责什么、是否有明确缺失 owner。索引仅提示目标角色；没有 target
不等于断链，响应式状态也可能完成失效/回读。证据写回既有九角色字段，不另做一轮
审计或报告。ownership 外静态断点写出 owner 与证据交既有 Quick，不越权修复。

从 `draft_template` 复制到树外 `draft_path` 再填写。模板只预填身份、SHA、字段名；
状态为 null、证据为空，不能直接发布。所有结论与 NOT_APPLICABLE 均须核对源码。
公共依赖、scope、改动、平台契约仍按原规则填写。完成后返回 batch、token、draft
绝对路径和“已停止写入”；停写后不改原稿。主会话负责 submit/publish 和补位。

## Quick reviewer

若收到 early-quick-preparation，按[提前 Quick](overlap-execution-protocol.md)只写准备稿后返回；
恢复同一入口时必须读取最终 packet 并正常校验，准备稿不能作为最终结论。

读取本批 packet、[快速审查](quick-review-protocol.md) 与适用域规则。
`workflow_packets.py quick-template --plan P --batch-id B` 输出机械空骨架；
主会话准备模板时不覆盖已有 draft。空骨架不含任何有效语义裁决。

先看 patch、未决角色、新 owner，再按 full_record 的 SHA 回读双端证据。
公共分析格式见 [Review 提速协议](review-efficiency-protocol.md)。不等待其它 reviewer：
无已封存证据就读源码。每个入口仍独立填状态、九角色与输入/分支/消费者证据。
只返回本批 draft；不自行 publish、修复代码、组织下一轮、构建、安装或 finalize。

## 通用启动与交稿检查

新 packet 含 `startup_command` 和 `pre_submit_command`，均为 argv 数组。
在返回的 worker_root 执行启动命令，阅读本角色规则后工作；结束前执行提交前校验，
修正全部错误后才报告停写。不要把 argv 数组直接当 shell 字符串插值。
ENTRY_CHECK_ONLY 没有写权限：读取公共回执和当前源码，复用事实证据，逐入口完成
完整义务回执。缺口如实保留，不为产生 APPLIED 添加差分，不要求重新审查未变化的
公共链。读集漂移需 refresh；旧 packet 没有这些命令时沿用原协议。
