<!-- when: Baseline packet 含 global_hazard_ids，或冻结已确认 scope 缺陷的修复目标时读取 -->
<!-- topics: scope hazard 承接, 首断点 owner, edit_targets 完整性 -->

# 风险承接与关键修复文件

冻结 SDK 上下文含 `operation_evidence_version=1` 时，相关资源创建和异步终态风险另按[操作证据](operation-evidence.md)交付；改变未决类别不能免除检查，旧冻结运行不追加要求。

本协议只补充现有 Baseline Review 和工单冻结校验，不新增 Reviewer 阶段、修复后复核、应用测试或自动修复轮次。设置候选筛选、每批预算、默认单轮及显式 Quick/Round 2 均沿用原流程。没有 `scope_ownership_version=1` 的旧冻结计划继续按原契约执行。

## 新运行的完整效果链裁决

新计划另冻结 `scope_followthrough_version=1`，经工单传给 Repair；没有该字段的旧运行不追补新必填项。先判断 Android 预期动作接通后必经的调用、状态和宿主，再定位当前第一处断链。空回调、禁用按钮或缺路由只说明当前执行停在哪里，不能证明修通后所需的服务、目录前置、订阅或宿主不适用。沿预期链核对既有候选，不扩展到无关功能。

局部 `NOT_APPLICABLE` 或 `APPLICABLE + NO_DEFECT` 必须提供 `exclusion_proof`：

- `scope=EXPECTED_EFFECT_PATH`；`basis=NO_DEPENDENCY` 或 `OWNER_GUARDED`。
- `evidence` 解释接通后为何仍无依赖，或实际执行分支上的保护条件。仅“当前 handler 未调用”不成立。
- `source_bindings=[{path, sha256}]` 覆盖 hazard 原有绑定，并补上排除依据依赖的调用/状态文件。脚本验证来源和复用时的字节一致性，不替模型证明语义。

`global_review.status=NO_DEFECT` 的 `exclusion_proof` 使用 `scope=SELECTED_SCOPE`，还须有 `callers_evidence`，说明共享 owner 在本次所选调用者中的安全依据。局部点击不相关、不新增该风险，不能作为共享实现无缺陷的证据。

局部未决或全局缺陷尚未证实的 `UNRESOLVED` 提供 `evidence_gap={kind, checked_sources, missing_fact}`。`kind` 为 `SDK_SEMANTICS_UNCONFIRMED / OWNER_NOT_FOUND / CONFLICTING_EVIDENCE`；列实际查过的源码/SDK 声明位置与仍缺的事实。先查已提供的 SDK 路径和相关 owner；SDK 只列 throws、目录 recursive 参数或附近出现错误码，都不能单独当作已确认安全或已确认缺陷。确实无法证明时仍保留未决，不为通过格式校验捏造证据。新计划中已确认缺陷但未分配修复 owner 的情况使用下文 `ownership_gap`，不能改写成 SDK 证据不足。

## 每条风险有明确的裁决责任

Planner 将所选领域的去重 scope hazards 分配给已有候选 contract，各一名 steward。新计划 `repair_coverage_version=1` 优先选择原有 `command_domains` 匹配的入口，再按源码路径关联、负载与 contract ID 排序；旧计划仍按路径关联、负载排序。这是读取和交代归属的责任，不代表缺陷成立或获得编辑权限。明确限定 contract 的定向审查仍先限定结构化路径关联，其余记入 `outside_selected_scope`，不因命令领域匹配扩大范围。不新增候选 contract，不恢复全量设置送审。

当前 packet 的 `global_hazard_ids` 必须在对应 `scope_hazard_reviews` 中补 `global_review`，与原来的局部 `relation/defect_status/evidence` 并存：

| status | 填写要求 |
|---|---|
| `OWNED` | `evidence` 说明共享断点及真实调用关系；`owner_contract_id` 指向已入选且独立确认该 hazard 为 `APPLICABLE + DEFECT_CONFIRMED`、状态为 `FIX_REQUIRED` 的工单；`repair_owner_paths` 列出该 hazard 源码绑定中的实际必改文件，且这些文件在 owner 的 `edit_targets` 中。 |
| `NO_DEFECT` | `evidence` 说明该风险在所审领域为何不成立，绑定被审源码 SHA；“不属于当前点击”只支持局部排除，不能作为全局排除理由。 |
| `UNRESOLVED` | `evidence` 写清待确认的 owner、源码位置或缺失证据；不伪造修复工单。 |

优先在当前审查中把可证明属于本效果链的共享断点纳入本工单。若指定其它 contract 承接，对方必须有自己的确认和目标；不能单凭 steward 的转交声明替对方授权。合并后缺承接、目标不齐或全局排除与已确认缺陷冲突，记录 `OWNER_INCOMPLETE`；全局未决记录 `UNRESOLVED`。两者进入 `scope_ownership.records` 和最终汇总，并使 `semantic_review_complete=false`，不让多条局部 `NOT_APPLICABLE` 汇成全局通过。

steward 的当前点击不相关时，继续从共享 owner 反查本次已选入口，不能就此结束全局审查。优先复用已有的双端/SDK 证据，在本批原有预算内完成 owner 裁决；读取线索不授权替其他入口生成结论。合并结果对未决风险生成 `review_handoff.related_contract_ids`，只列其他 Review 已明确判为 `APPLICABLE` 且未判无缺陷的入口，并区分其中已确认缺陷的入口。它用于准确交接剩余证据，不把候选自动升级为缺陷、不重开已封存批；规划时按[局部恢复协议](planning-recovery-protocol.md)协调已有证据，必要时生成一次有界补证和独立 seal。

新计划合并时，完整独立 owner 可以直接对账；多个完整 owner 必改路径一致且无相反裁决时，稳定选择主承接者并保留其他关联工单。不同目标或证据冲突不猜测等价，进入[局部恢复协议](planning-recovery-protocol.md)。这只协调责任，逐入口结论与实际修改要求仍独立保留。

原 Reviewer 交稿缺字段沿用既有验稿预算。规划仍发现缺口时允许一次局部补证；失败只挂起受影响工单，其余继续。旧计划保留原兼容行为。scope_ownership 表示 Baseline 裁决归属，不证明修复成功。

## 缺陷确认与修复归属分开记录

新计划 `repair_coverage_version=1` 的 `global_review` 另填 `defect_status=DEFECT_CONFIRMED/NO_DEFECT/UNRESOLVED`，与归属 `status` 分开：`OWNED` 必须确认缺陷，`NO_DEFECT` 必须有排除证据；缺陷已确认但尚无完整 owner 时使用 `status=UNRESOLVED, defect_status=DEFECT_CONFIRMED, ownership_gap="具体缺少的承接或目标"`，不用 `evidence_gap` 掩盖已确认事实。

Reviewer 在当前批交稿前从已选入口核对真实命令、共享宿主及消费者。宿主仅在子组件自己发布的状态成立后才创建、或订阅更新反复覆盖用户状态，都是应追到实际写入者的通用情形；不能仅以当前局部按钮无关结束共享风险判断。仍只给已独立确认的工单授权，不能把共享阅读责任当作修复权限。

Round 1 冻结前重新计算承接。已确认但归属不完整的风险返回结构化缺口，不拒绝整条修复计划。先复用已有 Review 协调，必要时按[局部恢复协议](planning-recovery-protocol.md)针对少量入口补证并独立封存；仍不足则保留 planning_deferred，继续无关批次。真正未确认的风险保留报告，不自动授予编辑权限，也不撤销已有完整授权。

## 成功、失败消费者的现状与修改目标

对新计划的 `FIX_REQUIRED`，在已有九项 `effect_obligations` 中，为 `FAILURE_STATE / INVALIDATION / READBACK / OBSERVABLE_STABILITY` 补充现状；沿接通入口后应完成的效果链判定，不因上游当前已断开就把下游标为不适用。无需另写第二份审计：

- `current_state=CONNECTED`：源码已经接通；给 `source_evidence=[{path,sha256,line,excerpt}]`，不增加编辑目标。
- `BROKEN`：已确认静态断开；给同格式源码证据、实际 `repair_owner_paths`、对应本条 `edit_targets` 的零基 `repair_target_indices`。路径须被引用覆盖，索引对应的路径集合与已确认 owner 一致，目标写明具体纠正。缺失 consumer 的修改目标时先纠正 Review，不能只给 producer 文件授权。
- `UNRESOLVED`：给已查源码引用与 `missing_fact`，保留真实运行时或外部证据缺口，不自动授权编辑。
- `NOT_APPLICABLE`：仅与原 obligation 的 `status=NOT_APPLICABLE` 一起使用，原 `expectation` 说明不适用依据；不授予目标。

成功不能停在“服务发布了事件”，还须核对目标 consumer 订阅、真实数据回读、宿主首次创建与后续状态投影；失败须核对任务匹配、原因传播和活动状态清理。已有 `terminal_delivery_checks` 的 `DELIVERED` 不能与相应 consumer role 的 `BROKEN/UNRESOLVED` 并存；修改 producer 预期不能冒充 consumer 当前已接通。

Review 交稿时验证引用的当前源码；冻结为 `effect_repair_targets` 后保留具体纠正，共享分组与依赖移交也不能丢失原要求。Repair 合法改动后不重验旧 Baseline 引用哈希，不做新增语义复审。显式第二轮使用 Quick 当前目标，不把第一轮索引套入新目标。原六路径上限、单 writer、预算及默认单轮不变；只读 consumer 不进入 ownership。脚本约束交稿一致性，不能替模型发现尚未识别的语义缺陷。

## 已确认的关键文件必须进入工单

确认 hazard 为缺陷后，在其局部 review 的 `repair_owner_paths` 中明确源码绑定内的实际首断点文件，如共享宿主或 helper；`edit_targets` 仍须逐文件提供原契约要求的 callable、anchor 与预期修改。未单列 `repair_owner_paths` 时，至少纳入该已确认 hazard 的主文件。只读消费者不必进入编辑范围；不要把整条依赖链全部改成 ownership。

验稿和 Repair 规划阶段对这些必改文件与 `edit_targets` 做集合校验，缺失即报具体文件，在局部补证中补齐后冻结对应工单；仍不足只挂起该工单，不会替 Reviewer 自动扩权。显式第二轮沿用 Quick 的最新确认和 targets，不能用旧目标掩盖新首断点。原每 contract 六路径上限和共享 writer 规则保留。

该校验保证**已确认的必改文件不会在移交时遗漏**，不能证明模型已发现全部关键文件。模型尚未识别的断点、SDK 语义误判仍可能漏修。本次不增加 Repair 交稿后的风险复查，亦不承诺零额外成本：需要多读的共享源码、既有预算内返稿或新增确认缺陷仍有对应工作量。

## SDK 依据、具体修改与当前源码

新计划冻结 `evidence_contract_version=1` 并传入工单；没有该字段的旧冻结运行不追补必填项。以下要求由 Review/Repair 的验稿执行，不增加候选或修复轮次，格式纠正与依赖刷新共用原有预算。只有规划缺口可使用局部恢复协议的一次有界补证；不得通过任意临时计划绕过次数限制。

1. **SDK 未决须有查阅记录。** `platform_contracts` 的 `UNRESOLVED` 和 `evidence_gap.kind=SDK_SEMANTICS_UNCONFIRMED` 提供 `sdk_check`。先查工具链给出的实际声明，核对状态前置、调用顺序、参数/返回值和异常语义；声明已能判定时据此裁决，不能仅写“SDK 不确定”。`CHECKED` 仍允许有真实未决点，不自动代表契约匹配。
   - 已查到：`{status:"CHECKED", symbols:["实际声明符号"], reason:"仍缺的事实", citations:[{path:"声明绝对路径", sha256:"文件SHA256", line:1, excerpt:"包含符号及相关契约的原文"}]}`。支持 `.d.ts/.d.ets/.h/.hpp`，可以引用多处；API 名称以声明中实际出现的符号填写。
   - 确实不可用：`{status:"UNAVAILABLE", symbols:["查找符号"], reason:"查找范围与不可用原因", searched_paths:["实际查找的绝对目录或文件"]}`。已经找到的声明必须读取并用 `CHECKED`；不得把可读声明归为不可用。脚本校验明确文件是否存在，不遍历整个 SDK，也不替代 Reviewer 判断查找是否充分。
2. **确认风险绑定具体修改。** `APPLICABLE + DEFECT_CONFIRMED` 的 review 提供 `repair_target_indices`，指向本条 `edit_targets` 的零基下标；显式 Quick 使用本条 `round2_edit_targets`。索引须覆盖 `repair_owner_paths`（省略时为 hazard 主文件），对应目标的 `expected_change` 须写明实际纠正要求。工单冻结为 `scope_repair_targets`。共享分组可以统一表达，但会把被映射的原始要求一起送给共享 writer，保存在共享组/依赖的 `scope_repair_targets` 或工单的 `shared_scope_repair_targets` 中；不因同路径、同 anchor 而丢掉不同修改，不因措辞不同而强制拆批。
3. **静态剩余缺口引用当前源码。** Repair 的 `UNRESOLVED` role/API 结果中，`gap_kind=STATIC_UNRESOLVED` 或 `STATIC:` 证据，以及 `static_handoffs`，填写 `source_evidence=[{path:"项目相对路径", sha256:"当前文件SHA256", line:1, excerpt:"当前源码原文"}]`。handoff 引用须覆盖各个 owner。静态结论写入上述结构化字段，不能只藏在 `unresolved` 自由文本中。先消费依赖回执并读 worker 当前源码，不能把 Baseline 或旧补审的缺陷原样当作当前缺陷；依赖改变时按原刷新预算处理。`FAILED` 不强求新证据，纯运行时待验证项不要求静态引用。

引用校验只保证文件、行文和哈希一致；目标绑定只保证明确要求传给执行者，均不能机械证明业务语义或真机效果正确。无法在已有预算内证明时如实留缺口，不伪造引用，也不自动扩大写入范围。

### 绑定 SDK 与按风险类型作答

新计划还冻结 `sdk_review_context={path,sha256}`，指向同 run 的 SDK 位置记录；优先复用项目匹配的预检，未取得有效位置时调用既有只读工具链发现器。不安装 SDK、不改变项目配置、不扫描旧运行目录。记录通过 packet、findings、Quick 基线和 Repair 工单传递；没有此引用的旧冻结计划不追补新要求。

读取记录里的 `declaration_roots` 后定位真实声明。`sdk_check.status=UNAVAILABLE` 的 `searched_paths` 必须覆盖各个声明目录；若未找到声明目录但已有 SDK 根，则覆盖该根。校验会在绑定声明目录查找所填符号，找到后拒绝“不可用”并返回文件位置。`CHECKED` 引用来自绑定工具链；SDK 没有安装、声明确实缺失时仍可保留 `UNAVAILABLE`，不得为了通过校验把无关同名声明当作目标 API。SDK 存在不意味着 API 一定适用或功能正确。

对于 `MEDIA_PLAYER_LIFECYCLE_ORDER` 和 `AVPLAYER_AUDIO_INTERRUPT_MODE_STATE`，证据要求由原始 hazard 类型及 `setters` 决定。无论局部/全局决定、`SDK_SEMANTICS_UNCONFIRMED`、`CONFLICTING_EVIDENCE` 或 `OWNER_NOT_FOUND`，同一条 `scope_hazard_reviews` 均提供：

- 顶层 `sdk_check`：引用覆盖该 hazard 的所有 setter 及其状态约束。
- `api_state_checks`：每个 setter 一项，含 `symbol`、`allowed_states`（声明允许的状态列表）、`observed_state`（源码可证的当前调用状态/顺序）、`conclusion=MATCHES/VIOLATES/UNRESOLVED`、`reason` 与 `source_evidence`。源码引用使用 `{path,sha256,line,excerpt}`，必须命中真实 hazard owner 中的 setter，并补充足以判断状态的调用/回调位置。

`allowed_states` 必须有 SDK 原文支持；确实 SDK 不可用时用空列表并保留 `UNRESOLVED`。声明已查到但调用状态仍有歧义时，具体写出缺少的状态路径证据。宿主显隐、覆盖层、命中区域不是 API 时序问题的回答，不能替代上述证据。确认缺陷仍须完成原有首断点 owner 与 `repair_target_indices` 绑定；类型化证据本身不授权修改，也不由脚本自动判为缺陷。未决不应伪装成全局无缺陷，已确认安全也不应强制修复。

这是现有验稿的一部分：错误回执只消耗原有纠正预算；类型化检查本身不新增 Review 或修复轮次；规划缺口仅使用上述有界补证。机械校验约束证据类型、具体符号、来源和状态文字，仍不声称能证明任意自然语言解释的语义正确性。
