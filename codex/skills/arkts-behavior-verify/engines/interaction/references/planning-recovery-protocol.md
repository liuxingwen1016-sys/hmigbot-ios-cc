# 修复规划的局部恢复

Baseline merge/quality-check 后、organization/target writer/Repair 注册之前使用本协议；独立点击与统一调度均适用。归属或证据缺口不是整条点击 lane 的停止条件。正常候选策略、六路径上限、默认单轮和 Repair 预算不变。

## 先协调已有证据

`scope_ownership` 重新核对现有 Review：同一 hazard 有多个独立确认的 FIX_REQUIRED，且各自的必改路径相同、均有源码绑定及 edit_targets、没有相反裁决时，按 contract ID 稳定选主承接者，保留 related_owner_contract_ids。仅统一归属记账；不合并入口结论、不删除各自修改要求、不推断修法等价。共享文件仍交既有 organization/target writer 或串行依赖协调。

单个完整 owner 沿用原对账。目标不同、缺文件或裁决矛盾时，保留具体 gap 进入下面的局部补证。真正未确认的风险继续报告，不凭风险标签撤销其他已经完整授权的修复；已确认但归属不完整的风险，只挂起相关入口及修改其实际 owner 文件的工单。steward 的阅读责任本身不使它的无关修复挂起。

```sh
python <interaction-scripts>/scope_recovery.py inspect --findings <baseline-findings.json> --project-root <arkts-root>
```

若 `supplement_contract_ids` 为空，直接继续规划。否则先运行一次下面的补证。已有 plan 产生 `planning_deferred` 或 `deferred_work_orders` 时也先消费具体原因，不以“无法冻结”终止整条流程。

## 只补规划所缺证据，独立封存

```sh
python <interaction-scripts>/scope_recovery.py prepare --findings <baseline-findings.json> --review-plan <original-review-plan.json>
```

脚本在原 Review plan 同级的 `scope-supplement/` 固定目录生成补证计划。新计划冻结 `recovery_version=2`：最多 5 条已确认归属缺口，另最多 5 条有明确缺失事实的未决风险，共用总计 6 个已选入口和同一次补证。未决风险须有已审查为 APPLICABLE 的 FIX_REQUIRED 调用方及源码 SHA 绑定；不把全量 UNRESOLVED 都送回 Review。优先 SDK 缺口、跨文件证据，再按风险 ID 稳定排序。另可在入口上限内纳入局部规划校验失败项。`NO_SUPPLEMENT` 直接继续；`RESUME` 续用返回的原计划，旧计划保留原选择规则与次数，不升级重跑。

用现有 review_dispatch、任务包、validate-draft/publish/complete 流程执行返回的计划。每个 packet 含原 Review、具体 planning_gaps/planning_deferrals；只查缺失事实、调用关系、SDK 或必改文件，复用其他字段，提交选中入口的完整记录。沿用机械验稿纠正和模型故障恢复预算；补证只有一次，不再允许业务 reopen，也不因本次失败另开目录或换 findings 名字追加补证。

packet 的 `evidence_tasks` 给出缺失事实、相关调用方及源码绑定，按以下顺序处理：

1. 从实际 APPLICABLE 调用方沿 Android 预期的接通后链路定位共享 owner。当前入口为空、禁用或断在上游，不足以把下游确定的状态循环、通知丢失留作“需运行才知道”；核对相关父子组件的初始化、挂载、订阅与状态写入点。不要求证明所有其他调用方，读集与修改集分别列出。
2. SDK 缺口先复用已查声明与本地配套文档，明确业务对于重复操作、资源已存在和异常分支的要求。结合调用源码判断已声明异常是否会中断必要结果；不把“不能证明所有设备必现”当作否定静态缺陷的理由，也不单凭 throws 列确认缺陷。尤其区分业务已有资源策略未查清，和 SDK 语义确实未知。适用时按 [operation-evidence](operation-evidence.md) 补全 `resource_creation_check`。
3. 当前任务已有、可绑定版本及操作的日志或失败记录可作为补充证据。不得引用其他项目的故障来确认本项目。最小运行验证仅在当前任务已有授权及可用环境、且静态资料不足时使用；默认不安装应用、不新增真机验收阶段、不修改应用来制造证据。证据仍不足则保留具体缺失事实，不能伪造确认。
4. 确认后同时补齐 hazard 的 `DEFECT_CONFIRMED`、实际 `repair_owner_paths/edit_targets/repair_target_indices`，以及 steward 的全局归属记录。已有入口因另一缺陷进入 Repair，并不代表本风险得到修复。仅有 owner 路径或工单状态也不能自动授予修改权限。复用未选风险结论，保留已有修复目标；新增必改文件仍受原路径上限和组织流程约束。

原成功封存批不重开、不覆盖。补证仍无法形成有效结论时，停止对应 worker，按既有流程封存 UNREVIEWED 并 complete；它只表示补证失败，不覆盖原来的 FIX_REQUIRED。所有补证 worker 已结束后：

```sh
python <interaction-scripts>/scope_recovery.py merge --plan <scope-supplement/review-plan.json> --fragments-dir <scope-supplement/fragments>
```

输出 `supplemented-findings.json` 及独立 seal，绑定原 findings、补证 plan 和每个补证回执的 SHA。只替换校验合格的选中入口；未选入口和失败补证保留原记录。原 `edit_targets` 保持原序原值，新目标追加，避免既有索引指向不同修复要求；未选 hazard 决策保持原值，已确认 BROKEN 的消费者义务不得降级。禁止将已确认缺陷降为无缺陷或未决来消除归属警报。部分补证失败也能合并；重复 merge 返回同一封存结果。

以返回的 findings 重新执行 quality-check、局部归属规划，再进入原组织与 Repair 流程。后续所有计划和 finalize 都使用这份 findings。若补证基础设施失败而没有可用合并结果，保留错误，用原 findings 规划可执行项；不能因补证无法完成让其他批次停工。确保没有仍在写入的补证 worker，再启动 Repair；不在应用已开始修改后重新补审旧基线。

## 未解决项挂起，其余执行

organization/target writer 生成最终 Round 1 plan 后、注册 Repair 前，再机械对账一次（不调模型）：

```sh
python <interaction-scripts>/scope_recovery.py inspect --findings <final-findings.json> --project-root <arkts-root> --repair-plan <round-1/repair-plan.json>
```

检查 `hazard_repair_coverage`，逐 hazard 区分 `PLANNED / REPLAN_REQUIRED / DEFERRED / UNRESOLVED / REVIEWED_NO_DEFECT`。`PLANNED` 要求实际 owner 进入批次且该批工单覆盖所有已审查必改路径，仅表示已安排。发现 `REPLAN_REQUIRED` 时消费已有审查目标，重建尚未注册的相关组织/计划；不重审完整入口、不手填 frozen ownership。证据不足则仅在尚未使用的同一次补证预算内回到上述补证。预算耗尽、超过路径上限或无法形成合法工单时，保留具体挂起原因，其余批次继续；Repair 开始后不补审旧基线，不新增修复轮次。

Round 1 新计划将未解决归属、缺少有效目标等逐入口规划失败写入 `planning_deferred`，已知发布 ownership 不足沿用 `deferred_work_orders`。不为这些项生成可执行 batch。每个 FIX_REQUIRED 必须恰好落在可执行批、planning_deferred 或 deferred_work_orders 之一，重复/漏项会被机械校验发现。

`planning_gaps` 保留完整未决风险，`reviewed_fix_count` 是确认缺陷总数；`requested_contract_count` 保持原含义（已生成的工单数），不能拿它冒充全部确认缺陷都已派发。最终导出显示挂起项为 NOT_ATTEMPTED 和具体静态缺口，不报告已解决。无依赖批次继续修复、构建和原交付流程，最终整体状态依实际剩余缺口如实报告。

现有修复队列的丢项仍使用 unified_dispatch 的 reconcile-repairs；它不替代本协议，也不自动为挂起项编造修改权限。证据哈希异常、越权修改等完整性问题继续保护受影响产物，不伪装成成功；归属缺口本身不再触发全局硬停。
