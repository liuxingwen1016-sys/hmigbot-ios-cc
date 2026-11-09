# 点击效果审查与修复

点击领域检查用户操作是否到达预期业务结果，由行为效果审查流程统一调度。

## 范围与角色

全量 Detector 发现所有 contract；AI 默认只审[固定核心候选](references/candidate-policy.md)。没有候选模式选择。领域目标与核心候选取交集；用户明确点名的 contract 保留原生精确目标与依赖闭包能力。

每个入选入口仍保留完整链路：页面进入副作用、输入身份、领域命令、异步成功、失败状态、持久化/文件结果、失效通知、回读、稳定 observable。播放/下载规则按源码能力启用，不强加给普通点击。保留禁用事件、动作分支、路由参数、默认 binding、scope、SDK、真实根因及行为替换保护。

## 按阶段读取

| 阶段 | 必读协议 |
|---|---|
| 预检与结果 | [预检](references/preflight-protocol.md)、[流程](references/fast-workflow-protocol.md)、[结果](references/fast-result-contract.md) |
| Detector 与范围 | [候选解释](references/detector-candidate-rules.md)、[adapter 发现](references/adapter-discovery.md)、[契约](references/adapter-contract.md) |
| Baseline | [紧凑审查](references/compact-review-protocol.md)、[审查提速](references/review-efficiency-protocol.md) |
| 共享与异步依赖 | [依赖审查](references/effect-dependency-review.md)、[媒体规则](references/media-effect-rules.md) |
| 规划缺口与局部补证 | [局部恢复](references/planning-recovery-protocol.md) |
| 已启用的 Repair 轮次 | [修复](references/fast-repair-protocol.md)、[组织](references/repair-organization-protocol.md)、[共享修复](references/shared-repair-protocol.md)、[直接发布](references/direct-repair-protocol.md) |
| 热点与提前审查 | [热点 writer](references/overlap-execution-protocol.md)，统一运行的提前 Quick 使用顶层 behavior_early_quick.py |
| Quick（已启用第二轮时） | [快速审查](references/quick-review-protocol.md) |
| worker | [任务包与恢复](references/worker-task-protocol.md) |
| 授权真机验收 | [运行时验证](references/runtime-validation-protocol.md) |

## 不变的语义

Baseline 只有真实双端审查确认的 `FIX_REQUIRED` 进入修复；quality-check 与逐入口证据不可省略。共享分析只复用源码事实，不共享裁决。默认单轮在 Round 1 后直接进入集中交付，不执行 post-round1 Detector 或 Quick。只有冻结为 full-repair，或用户明确追加第二轮并创建关联续跑时，才执行一次 post-round1 全量 Detector 与一次 Quick；提前 Quick 仅在启用该阶段时准备，最终必须对照正式 packet 再发布。

已启用的 Round 2 只接收 `ROUND2_REQUIRED`，其余不确定项报告为缺口；结束后不再运行 Detector、AI 复审、第三轮或应用测试。只在主会话统一构建、安装。安装与静态修复都不证明效果正确；仅用户授权的目标真机证据可以支持对应范围的运行时结论。设置领域永不继承点击领域的运行时结论。
