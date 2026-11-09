# 重复创建资源与异步终态证据

本次 `sdk_review_context` 引用内容含 `operation_evidence_version=1` 才启用新要求；旧冻结运行沿用原契约。只检查已入选候选的现有风险，不新增候选、阶段、轮次或恢复额度。脚本校验来源与结论一致性，不证明任意源码语义或运行正确性。

## 重复创建资源

当前由已有 `DOWNLOAD_DIRECTORY_CREATE_COLLISION` 触发。规则检查创建资源的前置条件，不按项目名、页面名或 URL 判断。无论未决类别叫什么，相关 `scope_hazard_reviews` 都提交顶层 `sdk_check` 和 `resource_creation_check`：

```json
{
  "resource_creation_check": {
    "operation": "mkdirSync",
    "existing_resource_policy": "REUSE",
    "repeat_safety": "UNRESOLVED",
    "existing_target": "资源缺失、同类型资源已存在、其他类型占用路径时的实际分支及 Android/产品预期",
    "concurrent_creation": "检查与创建之间的竞争处理；确实不能并发则列源码约束",
    "other_errors": "已有资源异常的判定；权限、路径、空间等其他异常如何继续传播",
    "source_evidence": [{"path":"Service.ets","sha256":"文件SHA256","line":1,"excerpt":"实际创建操作及防护分支"}],
    "remaining_gap": {"owner_paths":["Service.ets"],"missing_fact":"具体尚缺事实","next_action":"既有预算内的查证或明确外部依赖"}
  }
}
```

`existing_resource_policy` 是双端行为要求：`REUSE / REJECT / REPLACE / UNRESOLVED`，不把所有创建操作都改成复用。`repeat_safety` 为 `SAFE / DEFECT / UNRESOLVED`，不能只由 SDK 的 throws 列决定。SDK 可能没有保证每种组合必然抛错，但仍应审查**已声明异常分支**：若业务要求复用已有目录，而创建操作的已有资源异常会终止业务且没有处理，评估该路径是否违反预期；不必先证明所有设备每次都会失败。故意拒绝覆盖的创建操作不适用复用修法。

核对所有已指出的创建位置，包括开始前和完成落盘阶段。修复可验证目标类型、条件创建，并在并发创建冲突后再次确认；不能一律吞掉 `File exists`、把普通文件当目录、删除有效数据，或把任意 I/O 错误转为成功。仅有 `exists/access` 检查不证明类型和竞争安全。

确认缺陷沿用 `DEFECT_CONFIRMED → repair_owner_paths/edit_targets/repair_target_indices`；`repeat_safety=DEFECT` 不能继续挂成笼统未决。真正缺证据时使用 `UNRESOLVED` 并填写 `remaining_gap`，保留实际 owner，不自动授权修复未知语义。已授权、可归属当前任务的运行失败证据可以补充判断；不自动读取其他项目或历史任务日志。

已校验 `NO_DEPENDENCY` 排除证明且没有未闭合全局责任的入口可免填；局部不适用不能替代全局 steward 判断。

## 异步成功和失败分别追到消费者

新 Baseline packet 含 `repair_coverage_version=1` 时，终态交付结论还须与已有 `effect_obligations` 的消费者现状一致，按[消费者与修改目标](scope-ownership-protocol.md#成功失败消费者的现状与修改目标)填写。确认 consumer 断开须绑定该 consumer 的真实修复目标，不能只授权 producer；`DELIVERED` 不得与对应角色的 `BROKEN/UNRESOLVED` 并存。此要求不改变旧冻结运行或 Repair 的原交稿协议。

当前由已有 `DOWNLOAD_PRECREATE_FAILURE_ORPHAN`、`DOWNLOAD_PREMATURE_TERMINAL_BEFORE_COMMIT` 触发。检查方法适用于同类异步保存、导入、上传等生产/消费链，但不扩展本轮候选。相关 `scope_hazard_reviews` 填写 `terminal_delivery_checks`，恰好两行，`outcome` 分别为 `SUCCESS`、`FAILURE`：

```json
{
  "outcome": "SUCCESS",
  "delivery": "DROPPED",
  "sequence": "任务终态、持久化提交、移除进度项、发布通知和消费者读取的顺序；实际接收的状态或独立终态查询",
  "producer_evidence": [{"path":"Service.ets","sha256":"文件SHA256","line":1,"excerpt":"实际终态发布路径"}],
  "consumer_evidence": [{"path":"Page.ets","sha256":"文件SHA256","line":1,"excerpt":"实际消费条件和刷新/错误呈现路径"}]
}
```

`delivery` 为 `DELIVERED / DROPPED / UNRESOLVED / NOT_APPLICABLE`。多个受影响消费者合并列入对应行，不扩展无关页面。`UNRESOLVED` 另附上述 `remaining_gap`，保留生产者及已定位的消费 owner；不适用须有实际产品行为或独立等价路径。未找到消费者时引用已搜索的真实源码并保留未决，不能伪造消费点。

重点核对：设为完成后从集合删除再发布，消费者却只等待集合中的完成项；启动函数返回受理/任务 ID 后，后台失败仅写日志或清理任务，页面的启动 `try/await` 收不到失败。必须检查真实终态查询、通知或返回通道；有订阅不代表接通。源码丢失结果属于静态问题，不能写成“只缺真机证据”。网络、文件内容和 UI 实际表现仍属于运行验收，不增加默认测试环节。

## Repair 与 Quick

含 `terminal_delivery_checks` 的相关工单在 Repair 结果中同样交付该字段，引用当前私有候选源码，不复制旧行号/SHA。共享服务批只在既有 ownership 内修改；消费者缺陷超出范围时留下具体缺口，不越权。

`DROPPED/UNRESOLVED` 不得交 `APPLIED`；成功通路对应 `READBACK`，失败通路对应 `FAILURE_STATE`，相关角色保留 `STATIC_UNRESOLVED`。真实运行未测另行记录，不能覆盖源码断链。`FAILED` 批沿用原保守封存。Quick 仅在已启用时依当前源码重判；纠正、重试和最终未决沿用原预算。
