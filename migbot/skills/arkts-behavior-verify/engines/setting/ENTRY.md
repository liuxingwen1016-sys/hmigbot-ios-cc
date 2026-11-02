# 设置效果审查与修复

设置领域检查持久化值是否经活动消费者到达预期效果，由行为效果审查流程统一调度。

## 审查义务

Baseline 仅覆盖 Detector `findings` 非空的设置；全量 Detector 报告保留，无 finding 的项记录为未审查，不赋予 NO_DEFECT。每个入选 key 独立核对 Android consumer inventory、ArkTS consumer mapping、终端效果链、生效时机、持久化与临时覆盖优先级、默认值、enum/list 分支及活动实现；逐 key exactly-once。

## 按阶段读取

- [领域流程](references/fast-workflow-protocol.md)与[结果契约](references/fast-result-contract.md)。初始化、阶段顺序、共享构建及并发额度以顶层入口为准。
- Baseline：[紧凑审查](references/compact-review-protocol.md)。
- 两轮 Repair：[修复协议](references/fast-repair-protocol.md)，隔离执行与发布遵循顶层直接发布协议。
- Quick：[快速审查](references/quick-review-protocol.md)。

Baseline 只修复经真实双端审查确认的 FIX_REQUIRED。唯一一次 Quick 覆盖 Baseline 全部 FIX_REQUIRED；Round 2 对非 CLOSED_LIKELY 项按导航、ownership 和失败回退规则定向修复。共享源码事实不代替逐 key 裁决。

设置结果保持 correctness_verified=false、correctness_claim=NONE。安装成功或点击目标的运行时验收不能提升设置结论；Round 2 后不追加审查或测试轮次。
