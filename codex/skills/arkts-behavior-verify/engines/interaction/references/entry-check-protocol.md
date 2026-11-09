# 已发布公共补丁的逐入口核对

仅用于任务包 `execution_scope=ENTRY_CHECK_ONLY`。遵循任务包的 startup/pre-submit
命令、worker_root、读集和 token；先读任务包及其绑定的公共发布回执，再核对当前源码。
本批只写指定 draft，不改源码，不运行 organization、publish、build 或 install。

- 公共补丁事实只核对一次；确认回执绑定和当前源码一致，不继承公共批的结论。
- 每个入口独立核对 binding、输入身份、variant、消费者和 observable；将证据填入
  template 已有的全部九角色、平台契约及 shared_dependency_checks，不能省略字段。
- 未变化且有有效回执的公共链不重新做整套 Baseline 审查；本入口有反例或未决义务时
  继续追踪相关源码，并如实保留缺口。不得将未审查写成 NOT_APPLICABLE。
- 本批没有 changed_files；按原生规则使用 NO_CHANGE，不能因为公共批改过源码就填 APPLIED。
- 源码或读集漂移交主会话 refresh；发现需修改的入口向主会话报告，不能扩大 ownership。
- 只读本批工单和明确绑定的前置回执，不读取其他批草稿来猜 schema。

特殊条件仍加载对应规则：target_writer_base/writer_dependency 使用
[重叠执行协议](overlap-execution-protocol.md)；播放/下载使用
[媒体域规则](media-effect-rules.md)；异步或共享服务义务使用
[依赖审计](effect-dependency-review.md)。共享回执字段需要解释时读
[共享证明](shared-repair-protocol.md)。完整批次校验通过后停写并返回主会话。
