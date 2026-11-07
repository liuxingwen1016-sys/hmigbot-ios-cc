# 验证报告模板

输出到 `spec/verify-report.md`。更新当前报告正文，状态与数字取自本次实际验证结果；不适用的明细可省略。五项总表始终保留，未选可选项填写 SKIP（用户未选择），证据填“—”，不读取旧结果充数。

---

# 迁移验证报告

- 工程：<工程路径>
- 验证范围：<模块、页面、功能及排除范围>
- 执行项：<CHECK-1/2 + 用户选择的可选项；都不选时注明仅基础检查>
- 未选项：<CHECK-3/4/5 中用户未选的项目；全选时写“无”>
- 代码与实测依据：<工作树状态/相关改动、verifier 轮次与测试包标识>
- 基础及已选视觉/UT 范围结论：<PASS / FAIL / PARTIAL；仅 CHECK-1/2 + 已选 CHECK-3/4>
- 行为验证结果（非门控）：<CHECK-5 SKIP/WARN/DEFERRED/ERROR；不计入上述结论>

## 五项结果

| 编号 | 检查项 | 状态 | 结果摘要 | 证据 |
|---|---|---|---|---|
| CHECK-1 | 静态分析 | <状态> | <ERROR/WARN 数量> | <文件位置与复核依据> |
| CHECK-2 | App 身份校验 | <状态> | <FAIL/WARN 与缺失输入> | <配置/资源路径> |
| CHECK-3 | 视觉对齐 | <状态> | <功能性问题与纯视觉差异分别统计> | <report 与当前轮问题文件> |
| CHECK-4 | 单元测试 | <状态> | <原始退出状态、实测结果与未验证点> | <ut-report 与当前轮摘要> |
| CHECK-5 | 行为验证（可选，非门控） | <SKIP/WARN/DEFERRED/ERROR> | <原生终态、实际修复阶段与未验证范围> | <本次 adapter；未选填 —> |

## 失败与建议项

| 来源 | 级别/失败分类 | 问题 | 位置与证据 | 处理结果 |
|---|---|---|---|---|
| <CHECK> | <ERROR / WARN / verifier 原始分类> | <实际问题> | <路径/用例 ID> | <仍失败 / 已复测通过 / 建议项> |

## 迁移放行项核实

来源 `spec/gate-release/verify-focus.json`；每条一行，不得省略。

| 决策 | 类型 | 门禁 | 核实问题 | 结论 | 证据 |
|---|---|---|---|---|---|
| <D-0NN> | <工具缺口 / 未达标放行 / 阶段不可判定> | <门禁 ID> | <verify_question> | <已核实正常 / 确认缺陷 / 未覆盖> | <截图 / 用例 / 原因与恢复条件> |

## 未验证范围

此处记录已选范围内的未完成验证。用户未选项已在总表标 SKIP，不因此判 PARTIAL；已选 CHECK-3/4 前置缺失仍为 DEFERRED，影响基础范围结论；CHECK-5 的未执行和未验证缺口也写明，但不改变该结论。

| 来源 | 未验证范围 | 原因 | 恢复或复检条件 |
|---|---|---|---|
| <CHECK> | <页面/功能/改动> | <输入缺失、未执行、缺证据或结果已过期> | <具体条件> |

UT 引用原报告的统计口径，区分已执行通过率与计划范围完成情况，不把未执行项计为通过。

## 修复与复检结果

<如有修复，说明实际修复范围、外层轮数、已完成复检和未覆盖当前改动的结论；无修复时省略本节。>

## CHECK-5 行为验证明细（非门控）

未选时仅保留总表 SKIP（用户未选择），不读取历史报告、不生成本节的虚构原生结果。已选项读取本次 `spec/verify/check5/CHECK5_SUMMARY.md` 与 `<run-dir>/behavior-effect-adapter.json`；无法初始化或写出 summary 时直接记录实际 DEFERRED/ERROR 和原因。

以下业务明细仅在 `result_validation=PASS` 时填写。校验失败时省略分域明细表及业务计数，只列 adapter 错误、实际目录检查诊断和恢复条件；原生终态、修复计数等标“未校验/不可用”。`--no-install-deps` 仅禁止依赖恢复，Hvigor tasks 仍可能写缓存；严格只读任务的 CHECK-5 记 DEFERRED，不启动完整准备器或默认修复流程。

| 子项 | 状态 | 原生 terminal_state | 正确性及实际范围 | attempted / changed | build / install | result_validation |
|---|---|---|---|---|---|---|
| CHECK-5.1 设置 | <WARN/DEFERRED/ERROR> | <原生终态> | NOT_PERFORMED，correctness_verified=false | <原始计数> | <状态> | <状态> |
| CHECK-5.2 点击 | <WARN/DEFERRED/ERROR> | <原生终态> | <未验证或具体目标证据；不扩大全域> | <原始计数> | <共享交付证据> | <状态> |

- 本次 run / result / adapter / artifacts：<实际路径；新运行默认 spec/verify/check5/behavior-effect/<run-id>>
- repair_mode / workflow_complete / semantic_review_complete / errors：<校验后的原值>
- source_changed / changed_files / source_integrity：<实际改动及证据版本>
- Detector 发现量 / Baseline 候选量 / 实际 review_counts / 未审与排除原因：<分别统计，不将全量发现等同于全量审查>
- repair_attempted_keys 或 contract_ids：<不将 attempted 改称 repaired/verified>
- coverage / static_gap_contract_ids / runtime_gap_contract_ids / 未审与排除项：<保留各域口径，共享安装不重复计数>
- scope_ownership：<校验后 adapter 顶层及点击域的 complete / unresolved_count / outside_selected_scope；同一份风险汇总只计一次，旧结果缺字段标“未提供”>
- 风险责任与审查交接：<按 records 列风险 ID / 归属状态 / defect_status / steward 与 owner 入口 / 已提供的 related_owner_contract_ids / 必改及缺失文件 / ownership_gap / evidence_gap；已确认缺陷但缺承接与证据未决分别说明。review_handoff 的相关入口与已确认缺陷入口分别列出；旧字段缺失标“未提供”>
- 局部规划挂起项：<按校验后 contract_summaries 的 latest_execution=NOT_ATTEMPTED 与 static_gaps[].kind/evidence 列未执行项及原始原因；不计为已派发、已修复或仅缺真机验证，不以已生成工单数冒充全部确认缺陷数>
- 静态修复交接：<从 contract_summaries[].static_gaps 中 CONFIRMED_STATIC_HANDOFF 的 evidence 列 owner_paths / unowned_paths / 当前 source_evidence / next_action；与运行时未验证范围分开说明>
- reason_codes / build_readiness / dependency-recovery：<环境缺口、失败原因、是否尝试有界恢复；只读/禁网时不恢复>
- finalized / 目录检查：<未封存阻塞时记录检查证据、临时文件纠正结果、剩余原因及同一 run 的恢复条件；不消费未校验业务字段>
- 默认 single-round：Quick / Round 2 标“未启用”；full-repair 或关联续跑按内层既定范围记录实际阶段。续跑另列 parent_out、inherited_stages、executed_stages，历史阶段不计为本次执行。
- 源码变更后的复检：<CHECK-1、受影响 CHECK-2/3/4 的实测结果；未覆盖当前改动的设备项 PARTIAL，已有失败保留>

风险 `OWNED` 或责任 `complete=true` 不表示修复完成或行为正确；局部补证、owner 协调、工单已安排或机械对账完成也不表示修复成功。审查/静态交接不授予额外修改权限，外层不据此自行补审或追加修复轮次。内层修复前的一次有界局部补证及已启用轮次收口前的原工单对账按 CHECK-5 执行契约处理，不是 Quick/Round 2，也不由报告生成触发；Repair 开始后不补审旧基线，终态失败不自动重修。保留原始状态与 semantic_review_complete。

CHECK-5 全部状态均未参与基础结论、verified 回写或外层回环。安装成功、Detector 转绿及目标运行时通过都不能推导为整个行为域 PASS。
