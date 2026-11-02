<!-- when: 执行 a2h-verify CHECK-5、汇总行为 verifier 稳定终态或注册 CHECK-5 新子项时读取 -->
<!-- topics: CHECK-5, Behavior Verify, candidates, output integrity, result.json, non-blocking gate -->
# CHECK-5 行为验证（Behavior Verify）

> CHECK-5 是可扩展的行为验证总入口，技术名称为 `arkts-behavior-verify`。子 verifier 可以在自身契约内修改源码，但任何结果都只进入报告，不参与 CHECK-1/2 与已选 CHECK-3/4 的整体判定、页面 verified 回写或外层失败回环。

## 0. 选择与前置边界

- 未选：外层记 `SKIP`（用户未选择），不检查 roots/设备/skill，不新建 run、不调用引擎或 adapter、不读取历史 check12/check5 结果。SKIP 不伪造原生 result.json。
- 已选但无法初始化：源码或 skill 缺失记 `DEFERRED`。已经初始化的运行按适配器校验结果报告，不因后来缺环境而覆盖已有失败。SDK/JBR/Hvigor、依赖、签名、HDC 或设备不足仅降级构建/安装，不阻止可行的 Detector、Baseline 和已启用源码修复。
- 本能力会修改生产源码。任务明确「仅验证、不修产品代码」时记 `DEFERRED`（只读约束与当前能力不兼容），继续其他项；统一入口没有 `MODE=verify_only`，不得伪造该模式。
- 普通「全选/完整验证/运行 CHECK-5」只选择本项，不授权第二轮。repair_mode 与续跑按下文执行。
- 历史 CHECK-12 的原始结果保持不动；明确续跑且原生校验通过时可作为 parent，汇总使用 continue-round2 实际返回的 out。

## 1. 子项注册表

| 子项 | 名称 | Skill | 模式 | 输出目录 |
|---|---|---|---|---|
| CHECK-5.1 | 设置候选审查与修复 | `arkts-behavior-verify` 的 setting lane | 联合流程 | `<run-dir>/setting/` |
| CHECK-5.2 | 点击 core 候选审查修复 | 同次运行的 interaction lane | 联合流程 | `<run-dir>/interaction/` |

两项只调用统一 skill 一次，共享调度、阶段屏障、隔离发布和集中交付。集中构建首次失败后按内层 ownership 契约最多两次纠偏与复建，总构建 attempt 上限为 3；安装最多一次。不单独执行旧设置 skill。新增独立能力从 CHECK-5.3 起扩展。当前不调用 `a2h-alignment`，也不把 UI structure 或像素视觉对齐纳入 CHECK-5。

## 2. CHECK-5 联合执行契约

**先区分新运行与续跑**：用户在已完成的单轮之后要求“继续第二轮 / quick review 和修复”时，读取子 Skill 的 `references/round2-continuation.md`，执行 `unified_pipeline.py continue-round2 --from-out <原run-dir>`，以返回的新 `out` 继续 Quick Review → Round 2 → 本次构建/安装与封存。不执行下面的新运行初始化，不重做 Baseline / Round 1。原 run 保持封存；已有续跑则恢复当前阶段，已封存续跑不再追加轮次。缺证据或校验失败时报告缺口，不自动改为从头运行。

1. 仅本轮已选 CHECK-5 才运行；在已选 CHECK-3/4 结束后、统一验证报告前串行执行。前一 verifier 真实退出并释放设备，设备交接静默 5 秒；不得与其他 verifier 同时修改源码或操作设备。
2. 主对话调用 `Skill(arkts-behavior-verify)` 一次，传 `android_root`、`arkts_root`、`out=<hmos-project>/spec/verify/check5/behavior-effect/<run-id>` 和共享 `max_agents`（默认 6，受真实宿主额度约束）。新 run 使用空目录，不向统一入口传旧 `mode=fast_fix`。按子 Skill 的统一调度协议为每批创建独立 worker，使用当前 Claude Code 的 Agent/Task 工具，只传该批任务、协议路径和必要上下文；工具参数按实际宿主接口填写。
3. 子 Skill 负责初始化、最小 Preflight、全量 Detector、Baseline 紧凑审计和 Round 1，并在环境允许时构建 signed HAP 和单次安装。**默认初始化不传 `--full-repair`，冻结 `repair_mode=single-round`；Round 1 后直接集中构建/安装与封存，不执行 Quick Review 或 Round 2。** 只有用户在新运行开始时明确要求完整两轮，才在初始化时传 `--full-repair`，冻结完整模式并追加一次 Quick Review 与 Round 2。“运行 CHECK-5”“完整验证”“修复问题”以及两条 lane 均不构成第二轮授权，不得自行推断并添加该参数。模式初始化后不可中途切换；后续要求继续第二轮须走上述关联续跑入口，不改写原 run，也不重新 init。签名、SDK/JBR/Hvigor、HDC 或设备缺失不阻止 Detector 与已启用轮次的源码修复。a2h-verify 不另派 fixer、不改写中间证据，也不持有第二套修复循环。
4. 按内层契约区分发现、审查和预检：
   - **Detector 全量发现**设置与点击入口。设置 Baseline Review 仅接收 Detector `findings` 非空的候选，并对入选 setting 逐项 exactly-once；点击 Baseline Review 固定使用 core 候选。未入选项保留未审/排除原因，不赋予 `NO_DEFECT`，不将 Detector 覆盖量当作 AI 审查量。
   - **Quick Review 仅在启用时按内层既定范围执行**：设置与点击分别覆盖各自 Baseline 全部 `FIX_REQUIRED`，不按 Detector 是否仍报错或文件是否变化过滤。默认单轮不执行 Quick；第二轮的准入继续使用各 lane 原生规则。
   - **修复前局部规划恢复**由内层按 `engines/interaction/references/planning-recovery-protocol.md` 执行：先协调已有归属证据，必要时在同一次有界预算内补证并独立封存，以最终 findings 规划和导出。它属于原 Baseline 到 Round 1 之间的恢复，不是 Quick Review，不重开原成功封存批、不新增完整审查阶段或修复轮次。未解决项只挂起受影响工单，其余继续；Repair 开始后不补审旧基线。外层不另派 reviewer，也不因交接记录自行扩大补证范围或次数。
   - **Repair 工单对账**由内层按 `references/unified-dispatch.md#repair-work-order-reconciliation` 在每个已启用修复轮次收口前执行。只恢复有冻结依据且可证明尚未执行的原工单，已有 claim、Agent、提案和回执沿原恢复路径续接；完成原有可恢复工作后再集中构建或进入已启用的下一阶段。终态 `PARTIAL/FAILED/NO_CHANGE/BLOCKED` 不自动重审或重修，无法恢复的 `GAPS` 保留真实未完成结果；对账不启用 Quick/Round 2，外层不增加第二套队列或重试循环。
   - **依赖恢复**按内层 `engines/interaction/references/preflight-protocol.md` 执行：仅对已有声明且已锁定的依赖允许一次有界恢复，默认超时 60 秒；不得新增依赖、调整版本或更改签名环境。用户禁网或禁止安装依赖时传 `--no-install-deps`；缺工具链 lock 时只省略 `--toolchain-lock`，保留 `--no-install-deps`。该开关不阻止 Hvigor tasks 写缓存，不能将其当作工程全程只读模式。严格只读或不修产品代码的任务仍按第 0 节记 `DEFERRED`，不启动默认修复流程、完整准备器或 tasks。同一运行已有恢复回执（包括失败/中断）时不重复安装，不为重获安装次数另建输出；仍有缺口只降级构建，不阻止可行的源码审查。
   - 最后一个已启用修复轮次结束后，内层行为流程不追加 Detector、AI Review 或应用测试；集中构建纠偏按内层既定预算执行。仅用户明确授权的点击目标按原生运行时契约验收。外层对源码变更引起的 CHECK-1/2 及已选 CHECK-3/4 复检另按第 4 节执行，不重启内层行为流程。安装成功不代表行为正确。
5. 正常或异常终点按内层 `references/unified-workflow.md` 的目录检查与保守导出规则处理，不把“必须封存”当作绕过阻塞的理由：
   - 封存前运行 `unified_pipeline.py check-output --out <run-dir>`。若目录检查阻塞或 `finalize` 返回 `OUTPUT_INTEGRITY_BLOCKED`，逐文件核实；只有确认是已完成真实审查后的引用提取/JSON 组装临时辅助脚本，且不是正式证据或工具依赖，才保留原字节移至运行目录、应用源码及 worker 树之外的系统临时目录。不能批量搬走未知文件或自动删除证据。
   - 纠正后继续**同一未封存运行**的 `finalize`、`validate`，不重新 init，不重跑 Detector、Review、Repair 或构建。无法确认或纠正、发现合成修复证据、或仍有活动 worker 时保留现场，如实报告“未封存/阻塞”及恢复条件，不强行封存、不删锁绕过，也不重启全流程。已封存结果始终只校验。
   - 初始化已产生的 `<out>/result.json` 可能仍为 provisional，不能人工改成 finalized。调用结束或本次恢复阻塞后，运行 ArkTs-Core 适配器记录真实结果：

   ```text
   python <a2h-verify>/scripts/check5_result_adapter.py \
     --skill-root <arkts-behavior-verify> \
     --out <run-dir> \
     --summary <run-dir>/behavior-effect-adapter.json
   ```

   适配器内部先运行子 Skill 的 `unified_pipeline.py validate`，验证成功后才读取稳定字段并机械映射状态。校验失败时适配器写出 `status=ERROR/result_validation=FAIL` 并以进程退出码 0 返回，保证报告型失败不打断外层流程。不得依据自然语言日志、编译记录或 HAP 存在性猜测结果。
6. `behavior-effect-adapter.json` 是本次 CHECK-5 唯一机器汇总输入。适配器调用 `unified_pipeline.py validate` 后仍要求 finalized、两条 lane、已知身份及结果 hash；validate exit 0 不等于流程完成。保留原始结果及 artifacts。真实活动 worker 未停止时不得伪造 agent-stopped 或强行封存，provisional 结果如实记 ERROR；目录阻塞原因另外写入报告，不消费未校验的业务字段。编译版适配器可用 `ARKTS_PYTHON` 指定真实 Python 3.10+。技术名称更新不改变原生结果 schema、`behavior-effect` 证据目录或 adapter 文件名，历史续跑仍按原生校验处理。

若适配器自身无法启动或无法写入 summary，a2h-verify 直接记 CHECK-5 `ERROR` 并继续生成报告；不得因适配器进程非零而中止流水线。

已选 CHECK-5 时，Android oracle 缺失、环境缺失或子 Skill 未安装不得改记 SKIP。尚未初始化且 Skill 未安装、无法调用或缺 oracle 时，两项直接记 `DEFERRED` 并说明缺口；已经产生本次 `result.json` 时必须经过适配器，不得人工改写终态。

## 3. 状态映射

| validated lane `terminal_state` | 分域报告状态 | 报告含义 |
|---|---|---|
| `INSTALLED_UNVERIFIED` | `WARN` | 已修改并安装，但正确性未验证 |
| `NO_REPAIR_INSTALLED_UNVERIFIED` | `WARN` | 已安装但没有实际修复，正确性未验证 |
| `REPAIR_FINISHED_NOT_INSTALLED_UNVERIFIED` | `WARN` | 已完成当前模式启用的源码修复轮次，但签名或工具链等构建前置不可用，未构建/安装且正确性未验证 |
| `PREFLIGHT_FAILED_NOT_INSTALLED` | `DEFERRED` | 源码/输出/稳定结果/源码保护等硬前置不满足；不得用于签名或工具链缺失 |
| `BASELINE_FAILED_NOT_INSTALLED` | `DEFERRED` | Detector/紧凑审计未形成合法 Baseline |
| `BUILD_FAILED_NOT_INSTALLED` | `ERROR` | 构建失败或构建证据无效 |
| `INSTALL_FAILED_UNVERIFIED` | `ERROR` | HAP 已构建但安装失败/证据无效 |
| `WORKFLOW_INCOMPLETE` | `ERROR` | 流程或稳定产物不完整 |
| interaction: `REPAIR_FINISHED_BUILD_BLOCKED_UNVERIFIED` | `WARN` | 构建前置不可用，未验证 |
| interaction: `RUNTIME_VERIFIED` | `WARN` | 保留实际目标证据，不能提升为全域通过 |
| interaction: `RUNTIME_FAILED` / `RUNTIME_BLOCKED` | `ERROR` / `DEFERRED` | 目标验收失败或阻塞 |
| `result.json` 缺失、未 finalized、schema/证据校验失败 | `ERROR` | 不消费不可信字段，只记录适配器错误 |
| Skill 未安装或无法调用 | `DEFERRED` | 记录调用缺口 |

统一终态仅接受 `INSTALLED_UNVERIFIED`、`FINISHED_NOT_INSTALLED_UNVERIFIED`、`WORKFLOW_INCOMPLETE`。前两者仍消费分域状态，不能掩盖 build/install 失败。统一 WORKFLOW_INCOMPLETE、workflow_complete 非 true 或 errors 非空时总状态 ERROR；其中 lane 前置失败仍可显示 DEFERRED。缺 lane、未知终态、未 finalized 或校验失败记 ERROR。本接入不产生全域 PASS，设置始终未验证，点击 TARGET_RUNTIME_VERIFIED 只保留在其实际范围。总状态按 `ERROR > WARN > DEFERRED > PASS` 展示，仅是报告排序。

## 4. 非门控与源码复检

- CHECK-5 的 `SKIP/WARN/DEFERRED/ERROR` 均不加入主 SKILL「结果判定」的基础及已选视觉/UT 范围结论；当前 adapter 不产生全域 PASS。
- CHECK-5 不触发 `failure-loop.md` 的 a2h-execute 三轮旧回环。
- CHECK-5 不决定 `ui-manifest.md` 的 `verified` 回写。
- Baseline 或已启用 Quick Review 中的不确定项、已启用轮次的修复失败或未修项全部只写报告，不提升为外层阻断。
- 签名、SDK/JBR/Hvigor、HDC、设备、构建或安装问题只影响 CHECK-5 分域报告状态，不阻止设置效果 Detector 与已启用轮次的源码修复。
- CHECK-5 修改生产源码后重跑 CHECK-1 静态分析；涉及身份配置时重跑 CHECK-2；影响已选 CHECK-3/4 时按 failure-loop.md 复测，无法复测则相应项 PARTIAL。构建/安装结果留在 CHECK-5，本分支不新增独立编译 CHECK，也不把 CHECK-1 当编译检查。

## 5. 报告与扩展

先汇总到 `spec/verify/check5/CHECK5_SUMMARY.md`，再把摘要写入统一的 `spec/verify-report.md`。只有 `result_validation=PASS` 才填写下面的业务字段；校验失败只写 adapter 错误、已实际取得的目录诊断和恢复条件，未校验的 lane 终态/计数标“不可用”，不强行补齐明细。未初始化时按前置缺口报告。校验通过的结果至少列出：

- 总状态与两条 lane 的状态、原始终态、workflow_complete、semantic_review_complete、errors；
- `correctness_verified=false`、`result_validation`；
- `source_changed`、`source_integrity`、`changed_files`；
- Detector 发现量、Baseline 候选量、实际审查量及未审/排除原因分别列出；保留 Baseline `review_counts`。设置候选口径从已校验 adapter 的 `lanes.setting.artifacts.baseline_findings` 所绑定的 `review_coverage` 读取（核对路径/SHA），旧产物缺该字段时标为未提供，不补造计数或宣称全量设置均已审查；
- 初始化时冻结的 `repair_mode` 与实际启用阶段；完整模式和 `round-2-continuation` 汇总 Quick Review / Round 2 计数。续跑还须记录 `parent_out`、`inherited_stages` 与 `executed_stages`，历史 Baseline / Round 1 不计为本次执行。默认单轮模式将后二者标为“未启用”，不得为补齐报告而运行，也不得将未启用阶段视为流程缺失；
- `repair_attempted_keys`，不得改称 `repaired_keys` 或 `verified_keys`；
- build readiness、build/install status、reason_codes；依赖恢复是否尝试及受只读/禁网约束的情况；
- 是否已封存；若目录检查阻塞，记录检查证据、已确认临时文件的纠正结果、剩余阻塞原因与同一 run 的恢复条件；
- 点击 coverage、contract_summaries、static_gap_contract_ids、runtime_gap_contract_ids、未审/排除项及 incidents；设置 key 与点击 contract 分别统计，共享安装不重复计数；
- 风险责任明细取 adapter 顶层及 `lanes.interaction.scope_ownership` 的原值：列出 `complete`、`unresolved_count`、`outside_selected_scope`，按 `records` 说明风险 ID、归属状态、独立的 `defect_status`、审查责任入口 `steward_contract_id`、修复责任入口 `owner_contract_id`、已提供的 `related_owner_contract_ids`、必改/缺失文件、`evidence`、`ownership_gap` 与 `evidence_gap`。`DEFECT_CONFIRMED` 但归属未闭合表示已确认缺陷尚缺修复承接，不能写成缺陷尚未确认或 SDK 证据不足；多 owner 协调只统一归属记账，不合并入口结论。顶层与点击域是同一份风险汇总，不重复计数；旧结果缺字段时标“未提供”，不补造空记录或已闭合结论。`OWNED` 表示已有确认的修复责任入口，`complete=true` 表示 Baseline 风险裁决责任已闭合，均不表示修复完成或效果验证通过；保留原始 `semantic_review_complete` 和状态映射。
- 未承接风险的 `review_handoff` 分别列出相关入口 `related_contract_ids`、已确认缺陷入口 `confirmed_contract_ids` 和后续处理条件，不能把所有相关入口都算作缺陷。Repair 新确认的静态交接从 `contract_summaries[].static_gaps` 中 `kind=CONFIRMED_STATIC_HANDOFF` 的 `evidence` 读取，保留 `owner_paths`、`unowned_paths`、当前源码 `source_evidence` 和 `next_action`；它属于静态剩余问题，不能归为仅缺真机验证。这两类交接的 `grants_repair_authority=false` 不授予额外修改权限；外层不据此自行补审、扩大 ownership 或追加修复轮次。内层修复前的局部补证只按第 2 节既定协议执行，不能根据最终报告重启补证；后续第二轮续跑仍按已有授权与第二轮协议执行。
- 局部规划挂起项读取已校验 `contract_summaries` 的 `latest_execution=NOT_ATTEMPTED` 及 `static_gaps[].kind/evidence`，保留原始原因和相关风险，不计为已派发、已修复或仅缺运行时验证。局部补证、owner 协调和机械对账本身不构成修复成功；不能用已生成工单数代替全部确认缺陷数，也不能用入口进入批次代替该风险的必改目标已被承接。报告不为补齐这些明细而触发恢复命令。
- `result.json`、适配结果与关键 artifacts 路径。

以后新增其他效果 verifier 时，为新子项定义独立模式、终态适配和报告字段；不得假定它与 CHECK-5.1 共用结果 schema。
