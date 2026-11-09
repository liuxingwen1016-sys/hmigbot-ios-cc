<!-- when: baseline detector 完成后读取 -->
<!-- topics: compact review, exactly-once, work order -->

# Baseline 点击效果紧凑审计

packet 含 `global_hazard_ids` 时按[风险承接与关键文件协议](scope-ownership-protocol.md)在本批裁决共享风险归属，并核对已确认首断点文件进入 `edit_targets`；不新增审查阶段。

候选固定按[核心策略](candidate-policy.md)送审；领域发现用于确定义务，不自动扩大核心候选。入选后所有证据与质量要求保留。

新 Review 使用 [公共证据、依赖/复杂度分包与全槽位启动](review-efficiency-protocol.md)。初始化后先 `claim-ready`，派发所有返回批次再等待；同一 batch 中断沿用原 Agent，不把该恢复要求扩大到后续新 batch。

`compact_interaction_review.py plan` 默认对 `detector_findings` 候选与明确的领域动作入口 exactly-once 分批，每批最多 16 项、默认不超过 180000 UTF-8 bytes，最多六批并行。CLI 分包器按最终序列化 packet 体积均衡分配到可用并发槽位，仍不突破上限；普通无 finding 点击不消耗 AI Review。用户按领域指定目标时使用 `--target-domains playback,download`，送审已有命令与具备当前控件动作意图的阻断候选；不能先手工筛选已有命令再传 IDs。用户明确指定精确 `--contract-ids` 时才只处理该范围。packet 标记 `kind=interaction` 与 `facets=[interaction]`。plan 自动记录 Review coverage，并为所选播放/下载动作生成带 SHA 的 scope guard；显式传入的 guard 也须覆盖这些领域。每个 contract 的 `effect_domains` 决定其专用义务，共享 packet 不使普通点击承担媒体后置条件。Worker 读取双端源码，只写自己的 review draft。

异步命令或共享服务审计先读 [依赖审计](effect-dependency-review.md)。即使入口无 finding，也要追踪它等待的资源如何生成、关键参数能否传到最终命令，以及 hazard 的真实 owner。能力命中与 guard 都是审计证据，不直接确认缺陷。merge 自动消费 plan 绑定的 guard 并保留证据，不合成 oracle、根因或 `FIX_REQUIRED`，不提升 `UNREVIEWED`。

Packet 的 `effect_scope_guard` 按本批路径内嵌相关证据，`full_guard` 以路径和 SHA 指向完整 guard；`hazard_index` 保留未内嵌记录的 JSON pointer，`unassigned_hazard_ids` 标出无 owner 项。先检查内嵌证据和索引，需要核对关系时按引用打开记录，无需每批重读全仓 closure。索引可能涉及计划内其它领域，须确认实际依赖，不能把“未内嵌”解释为无风险。merge 保留完整正式证据，候选集合与 exactly-once 不变。

## Review 调度硬约束

播放/下载 worker 同时读取 [媒体域规则](media-effect-rules.md)，普通点击无需加载。
解释事件 consumer、route-result、variant、`OVERWRITTEN_SHEET_BINDING` 或 `SILENT_NULL_SELECTION_GUARD` 时读取 [候选解释](detector-candidate-rules.md)。UI 终端候选包含宿主/选择器证据：逐个检查显示状态对应的实际组件链、空数据前置态与确认后继动作，不能用 `STATE_CHANGE` 或其它分支有命令判当前分支闭合。

冻结 edit targets 前，在现有九角色审计内沿完整 REQUIRED 链核对 owner：区分已满足
环节、公共命令修法、入口独有修改、实际缺失的静态责任。不能找到第一处断点就停止
检查下游终态与消费者；用同一组已有 evidence/obligations 描述各项，不额外写第二份
九角色报告。只有真实源码证据确认的缺口进入 targets；不按角色名称机械新增文件。
预算无法覆盖时明确剩余 owner，交既有修复/Quick 流程，不扩大范围或增加审计轮次。

调用 Skill 的主会话必须亲自持有 Review 编排，禁止把整个 Review 阶段委派给一个“审计协调子 Agent”。每个 Review worker 只能读取并完成一个 packet，且禁止再次派生 Agent。主会话先从 `ready_batches` 领取 claim，再按 plan 的 `max_parallel` 并行派发；每个 packet 使用独立上下文。主会话按 claim-ready 返回的 packet 派发并 attach 独立 reviewer；同一 Agent 不能跨批次复用上下文，也不能伪造 Agent ID 来满足检查。缺少可用审查上下文时按流程保留未审项，不把它记为审查完成。

每批按 [动态批次调度](batch-dispatch-protocol.md) 先 `review_dispatch.py claim-ready` 预留可用槽位（资源受限用 `claim --limit N`），再派发并 `attach-agent`。单批发布/封存后立即 `complete` 并 claim-ready 补位，不等同组慢批。`progress` 中 running 不重复派发；`max-contracts=16` 与 `max-packet-bytes` 是单包上限，总批数读取 plan。Worker 返回 draft 后先运行 `validate-draft --out <normalized-draft>`，再发布 normalized draft。SHA 大小写、schema、identity、必填字段、evidence 行号或 excerpt 等机械失败在同一上下文修正，不占用语义重试；确认缺少真实源码审计、模板化结论或工作已失败且无 draft 时，才在剩余业务重试额度内用新上下文重审。先按 [快速流程](fast-workflow-protocol.md) 区分模型服务故障与等待超时：模型故障使用独立恢复预算续跑原 Agent，不扣业务重试，仍运行的 Agent 继续等待；`fresh_context_per_batch` 不表示同 batch 恢复必须新建 Agent。对应类别的预算耗尽仍失败时执行 `mark-unreviewed` 并继续其它独立批次，避免丢失后续有效工作。

普通 `fast_fix` 在单批业务重试额度耗尽仍有内容失败，或独立模型恢复预算耗尽仍无法完成时，保留 `UNREVIEWED` 封存，待其它批次完成便可 merge；planner 会忽略这些记录，它们只进入 deferred。参考标准审计不能把 `UNREVIEWED` 当作完成：其余批次结束后，对失败批次运行 `reopen-unreviewed --reason <reason>`；对 `progress.quality_failed_batch_ids` 运行 `reopen-quality-failed --reason <reason>`。已初始化 dispatcher 时由其 `reopen` 统一归档旧 fragment/seal 并恢复该批待派发状态，保留重试累计；不要单独归档后让状态失配。所有缺口补审成功前，不得 merge 为参考数据或进入修复。每次 `publish`/`mark-unreviewed`/reopen 后重新运行 `progress`；其中 accepted/unreviewed/quality-failed/pending 是实时权威统计。只有参考标准审计在 merge 前追加 `--require-complete`；普通 `fast_fix` 不追加。

每项必须绑定 `contract_id/stable_id/source_fingerprint`，状态为 `FIX_REQUIRED / NO_DEFECT / UNCERTAIN`。同批首次内容审计及一次业务重审均失败时，由主 Agent 写 `UNREVIEWED`；模型故障按独立恢复预算处理。

Detector finding 的 `signal_level` 只用于审计顺序：先看 `HIGH_SIGNAL`，再看
`CONDITIONAL_RISK`，最后看 `STRUCTURAL_ONLY`；不得按层级跳过 contract，也不得把
`HIGH_SIGNAL` 直接抄成 `FIX_REQUIRED`。动态 action 差集、字面量禁用、恒定 guard、
混用状态 gate、逐调用方 route result、重复终止导航、local-only durable、写后无刷新、
缺确认/导航后置条件、错误替代命令、弹窗无 owner invalidation 和存储状态未加载都只是
要求 Reviewer 打开对应证据窗口的结构候选。

Scope 的 blocking 与 conditional 候选都回填 `scope_hazard_reviews`，字段与
[快速审查](quick-review-protocol.md)一致：先裁决关系，再显式裁决是否为缺陷（`APPLICABLE` 本身不确认缺陷），
并保留当前源码绑定。确认缺陷才给精确 owner，已有保护或无依赖时用真实证据排除；
不允许某个下载风险被裁决后静默覆盖同 owner 的其它风险。未决项如实保留，不制造
Android oracle 或为清零而编辑。必要权限与错误 route 的语义替换均在本次 Review
冻结，格式与边界见 [双轮修复](fast-repair-protocol.md)。

新 packet 的 `scope_followthrough_version=1` 要求按[完整效果链裁决](scope-ownership-protocol.md#新运行的完整效果链裁决)填写排除证明或证据缺口。不要因修前第一处断链就排除修后必经的 owner，也不要把局部无关写成全局无缺陷。

新 packet 的 `repair_coverage_version=1` 另按[缺陷与归属分离](scope-ownership-protocol.md#缺陷确认与修复归属分开记录)填写全局 `defect_status`，并在原有四项消费者 obligation 中填 `current_state`、源码引用及确认断链对应的精确目标。已确认缺陷不能因尚未分配 owner 变成证据未决；发布事件本身不能证明 consumer 已接通。常规验稿仍使用原有纠正预算及六路径上限；合并后的规划缺口按[局部恢复协议](planning-recovery-protocol.md)处理，最多一次少量补证。

`FIX_REQUIRED` 必须包含 Android 预期、ArkTS 实际、双端精确证据、从点击到 observable 的有序 `effect_chain`、非空 `change_kinds`、风险和最多 6 个精确 edit targets（`.ets` 或经审查的 manifest `CONFIG_KEY` 权限新增，格式见双轮修复协议），并定义九个 `effect_obligations`。每个 obligation 标记 `REQUIRED/NOT_APPLICABLE` 并写出可验证后置条件：

若本条与其它入口明确命中同一共享断点，按 [共享修复证明](shared-repair-protocol.md) 可选填写 `shared_repair`；只在统一修法、命令语义和完整 `edit_targets` 均相同且没有入口独有修改时声明 `CONFIRMED`。`shared_evidence` 与 `entry_evidence` 必须引用本条 `arkts_evidence` 成员的精确源码片段，分别覆盖全部公共 targets 和当前入口/实际 consumer；五项 `entry_checks` 保留本条 identity、参数和 variant 差异。同因描述可复用精确源码符号，但不能把双端 oracle、效果链或入口证据模板化。未知时省略，旧无 proof 记录继续走普通修复批；该字段不改变 Baseline Review 的分包上限。

若 packet 含 `repair_admission.mode=TWO_TRACK`（播放/下载），Review 必须额外把每个 obligation 标成 `STATIC_REQUIRED` 或 `RUNTIME_DEFERRED` 并说明理由。`STATIC_REQUIRED` 是可由源码、仓内领域命令和 SDK 声明确定的入口、identity、命令、错误投影；`RUNTIME_DEFERRED` 仅限设备、网络、平台回调、最终文件或跨进程时序。后者不能让一个确定的 app-owned 空 handler、缺失 binding、错误参数或错误 route 变成 `UNCERTAIN`，也不能阻止 Repair Agent 报 `PARTIAL` 并修复静态断点。

同时必须填写唯一、可证伪的 `root_cause`，并填写非空 `platform_contracts`。效果链未进入平台 API 时使用一项 `NOT_APPLICABLE`；进入 `@kit/@ohos` 或项目 SDK 封装时必须读取当前 SDK/项目声明，记录 `MATCHED/UNRESOLVED` 及具体声明证据。若 scope guard 提供 `adapter_profile`，必须引用实际 capability 的 `adapter_id` 和 evidence；未知框架使用 `ADAPTER_UNRECOGNIZED`/`REVIEW_REQUIRED`，不得套用别的框架模板或直接判 `NO_DEFECT`。不得把异常处理、toast、等待、按钮状态回退写成导致原始命令失败的 root cause。

1. `ENTRY_SIDE_EFFECTS`：进入页面、初始化 WebView/媒体/弹窗时不会额外触发错误外部能力或遮挡目标交互。对 `loadData` 页面，intercept 必须把 `data:` 和内部 synthetic origin 留在 WebView 内；转发到 `startAbility(viewData)` 是阻断项。即使播放/下载命令位于 sibling handler，只要同一页面存在目标入口，该错误转发仍会破坏目标前置；只有完全没有目标入口的独立 shownotes WebView 才降为 REVIEW_REQUIRED。
2. `INPUT_IDENTITY`：实体 ID、URL、route payload 和媒体身份有效。
3. `DOMAIN_COMMAND`：调用 Android 语义等价的真实领域命令及参数变体。
4. `ASYNC_TERMINAL`：通过匹配任务的 Promise、回调或订阅确认真正成功终态；仅创建任务、赋值 URL、注册 listener 或返回 Promise 不等于成功。
5. `FAILURE_STATE`：失败会传播且不会继续投影为 active、playing、downloading 或 success。
6. `DURABLE_EFFECT`：数据库、集合或真实文件发生变化；下载/导出需有最终文件而非临时状态。
7. `INVALIDATION`：发布正确事件、刷新或缓存失效。
8. `READBACK`：消费者从真实数据源回读，不依赖局部假状态。
9. `OBSERVABLE_STABILITY`：后续 observer/订阅通知不会覆盖用户展开、选择、路由或已完成状态；播放还必须沿具体组件实例确认播放器条/播放器页的实际宿主不被 Navigation/SideBar 遮挡；父组件已有有效 overlay 时不要求子页面再建同类容器。展开播放器时 mini-player 必须从组合树移除（优先 `Visibility.None`）或明确不参与命中；`Visibility.Hidden` 不能直接视为安全。

Review 既要从 handler 顺向追踪，也要从最终 observable 反向搜索所有写入者。链路至少回答：输入 identity 是否有效、是否调用真实领域命令、异步终态是否有可信确认来源、失败状态是否清理活动投影、持久化/文件是否真实变化、事件/失效是否触发、目标消费者是否回读，以及后续通知是否会把可见结果立即覆盖。

领域命令不能只按“同属下载/保存/订阅”归为等价。Android 证据出现具体方法、HTTP 方法、参数或执行模式时，Review 必须把它写入预期并核对 ArkTS 的具体变体：用户主动即时命令与后台受约束/计划命令、GET 与额外 HEAD 前置、add/remove 与 toggle、delete 与 archive、强制与默认约束均不等价。平台额外前置请求或能力调用可能在真实命令前失败，必须进入 effect chain；无法证明语义等价时判 `UNCERTAIN`，不得给出可随意替换同类 API 的工单。

对 `request.agent` 下载，SDK 明确允许后台任务监听 Task 事件并推荐后台模式；不得把
`Mode.BACKGROUND + task.on(...)` 本身判为缺陷。`saveas: './name'` 明确解析到调用方
cache，也不能仅因代码用 `cacheDir/name` 做清理或合并就判路径不一致。真正需要核对的
是两端最终 basename/目录、事件绑定时机、GET 成功终态和最终文件回读。若稳定的
episode/segment `saveas` 在 create 前没有停止/删除旧 task 或文档化的幂等替换，
必须把潜在 `File exists` 作为具体断点审计。若 ArkTS 在真实
GET/下载前无条件增加 HEAD 等额外网络前置，而 Android 没有该前置，必须把其失败可达性
作为具体断点审计，不能用“下载预检”概括为等价。

下载闭包还必须按实际发生顺序审查四个通用静态断点，不能因为页面已经调用 service 就提前闭合：

1. 下载目录重复创建：`mkdirSync(path, true)` 没有存在性守卫或幂等处理时，先核对当前 SDK 对“已有目录 + recursive”的行为；throws 列表出现 `13900015` 不足以证明这组参数必然失败。工具仅给 `CONDITIONAL_RISK`，确认冲突可达后才开修复工单。
2. 预创建失败清理：active task/持久化队列若先于 destination/config/create 建立，则这些步骤的任意异常都必须进入统一 fail cleanup；只记录日志会留下空 system task id 的孤儿任务。
3. 后台传输不能由页面固定超时等待：页面应启动命令并观察 task 状态；固定 30 秒等整段网络完成会把正常慢下载错误投影成点击失败。
4. 完成顺序：最终文件落盘及 `commitCompleted` 成功后，才能发布 `COMPLETED` 或写 terminal map；否则页面回读可能早于数据库提交。

经源码与平台依据确认的上述断点属于 app-owned `STATIC_REQUIRED`；未确认的目录风险保留条件性证据。最终网络成功、系统 callback 是否实际触发及文件内容非空仍属于 `RUNTIME_DEFERRED`。

`NO_DEFECT` 仍需双端证据，且不能带修复目标。`UNCERTAIN` 必须包含双端搜索证据，并具体说明已检查的 Android 候选、ArkTS 链路和仍无法裁决的断点；缺少精确 oracle 不等于无需打开 Android 源码。整批重复同一不确定文案会触发 `TEMPLATED_REVIEW_UNCERTAINTY`。导航容器模式或静态目的地集合/顺序变化自动转为 `UNCERTAIN`；已有 route/dialog 激活不在禁区。

## 已完成参考审计的 UNCERTAIN 二次裁决

当用户要求继续裁决已完成参考审计中的 `UNCERTAIN`，不要重跑 Detector，也不要重新
审查 `FIX_REQUIRED/NO_DEFECT`。用原 detector report 和完整 findings 建立独立输出：

```text
python <skill-dir>/scripts/compact_interaction_review.py plan-uncertain \
  --report <out>/baseline/report.json \
  --findings <out>/baseline/merged-findings.json \
  --android-root <android_root> --arkts-root <arkts_root> \
  --packets-dir <out>/uncertain-resolution/review-packets \
  --out <out>/uncertain-resolution/review-plan.json
```

新建二次裁决计划沿用最多六批并行，资源限制在 claim 时应用；已冻结的四批旧计划按原值续跑。
第二遍 packet 默认最多 8 项，并包含 `previous_uncertain_findings`。旧结论只说明上次卡点，
不得复制成新结论。Reviewer 必须从可见 label/action、所在 ArkTS 页面语义和实际 handler
重新搜索 Android XML/string→view id→listener/action branch，再顺向追 ArkTS callee、
持久化/路由/事件和最终 consumer。若静态源码已经足以证明，应改判
`FIX_REQUIRED` 或 `NO_DEFECT`。

当 packet 的 `android_oracle_hint_strength=WEAK_TOKEN_HINT_ONLY` 时，packet 中的
`android_search_hints` 只能用于导航。若改判 `FIX_REQUIRED/NO_DEFECT`，Android evidence
必须至少包含一条 Reviewer 从源码新建立的当前控件→listener/dispatch/command 链接，不能
全部原样复制 Detector hint；否则 `validate-draft` 以
`WEAK_ANDROID_HINT_REUSED_AS_ORACLE` 拒绝。`Source review completed; handler chain
inspected` 等只描述“做过审查”、不描述具体动作和后置条件的 summary 同样拒绝。

只有源码穷尽后仍缺平台、运行时、外部依赖或唯一产品映射时才保留 `UNCERTAIN`，并填写：

- `uncertainty_class`：`ANDROID_ORACLE_UNAVAILABLE / ARKTS_CLOSURE_UNRESOLVED /
  PLATFORM_CONTRACT_UNAVAILABLE / RUNTIME_STATE_REQUIRED /
  EXTERNAL_DEPENDENCY_REQUIRED / PRODUCT_SEMANTICS_UNRESOLVED` 之一。
- `search_exhaustion`：至少两条不重复字符串，必须同时包含 `ANDROID:` 和 `ARKTS:` 前缀，
  写明搜索词、实际检查路径和为何仍不能形成后置条件；平台契约、运行时、外部依赖类
  还必须分别增加 `PLATFORM:`/`SDK:`、`RUNTIME:`、`EXTERNAL:` 证据。

全部第二遍 fragment/seal 通过 `progress --require-complete` 后执行：

```text
python <skill-dir>/scripts/compact_interaction_review.py merge-uncertain \
  --base-findings <out>/baseline/merged-findings.json \
  --plan <out>/uncertain-resolution/review-plan.json \
  --fragments-dir <out>/uncertain-resolution/review-fragments \
  --out <out>/uncertain-resolution/resolved-findings.json
```

该命令只覆盖原 UNCERTAIN contract，并校验 base/plan SHA、目标集合、sealed coverage、
残留 UNCERTAIN 结构和本次目标质量；不得手工拼接 JSON。旧 findings 若因 Skill 后续新增
规则出现非目标质量告警，只记录到 `quality.legacy_non_target_warnings`，不能阻断已完整封存的
二次裁决，也不能被解释为旧记录已通过新规则。最终再对
`resolved-findings.json` 运行 `quality-check --require-complete`。批内 UNCERTAIN 比例达到
80% 且没有逐项结构化穷尽证据时触发 `EXCESSIVE_UNRESOLVED_BATCH`；路径、contract id、
序号变化但语义相同的兜底话术仍按模板拒绝；`???` 或替换字符触发
`GARBLED_REVIEW_TEXT`。

`android_oracle_hints` 只含当前控件精确 label/action 且落在单一 Android 源码上下文的结构证据；token 命中、相邻控件、配置/preview 代码和跨多个源码上下文的歧义证据放在 `android_search_hints`。`android_oracle_hint_strength=WEAK_TOKEN_HINT_ONLY` 时，两类 hint 都只能帮助搜索，不能证明映射；`STRUCTURALLY_LINKED_BOUNDED_HINT` 才表示 detector 已通过当前 XML string→view id→listener/command、单义状态标签→Android action onClick，或 action id→dispatch branch 连接到有界源码。Reviewer 必须同时查看 `android_oracle_scope` 和 `android_oracle_ambiguity`，不能把 search hint 提升为 oracle。

`ui_action_labels` 非空时必须逐状态标签读取 `ui_action_label_android_hints[label]`。如果 ArkTS 同一可见按钮按状态投影 Download/Cancel/Delete 等动作，缺失的父级 `@Event` binding 会同时截断这些动作；Reviewer 至少用与用户报告对应的状态标签建立一条具体 Android 后置条件，不得只取字典序第一个标签代表整个按钮。

Reusable `@Event` contract 必须优先读取 packet 的 `event_consumer_bindings` 与 `bounded_consumer_paths`：直接调用和经同文件 helper 间接调用的 `@Event` 使用同一套 consumer 审计；按具体实例分别判断父 callback，存在多个消费者时不得把某一个消费者的效果推广到全部实例。`active_instance_count=0` 才表示当前源码没有实例。`override_present=false` 表示实例省略覆盖，`binding_source=COMPONENT_DEFAULT` 表示有效回调来自组件默认声明；按执行源 `path/line` 追链，同时用 `instance_path/instance_line` 定位具体实例。`binding_present` 表示有效回调是否存在，未知默认保留 `null`；旧 packet 缺少新字段时也须读取 `@Event` 默认函数体，不把省略覆盖等同空回调。默认空体或占位且 Android 对应动作有可观察后置条件时才形成缺陷。默认函数已有真实业务行为时沿其调用链审查，不要求父实例重复覆盖。一个实例转发多个事件时分别保留每个事件及条件分支，不能按实例位置去重后只审其中一个。**`binding_present=true` 也不能单独证明效果成立：必须读取 `binding`/`reachable_source` 的实际函数体。若回调落入 `unavailable*`、`unsupported*`、`notImplemented`、`noOp`、空体或无领域效果的 placeholder，detector 会标记 `EVENT_BINDING_NOOP`；若实例化调用把 action-gate 类型的 `@Param`（如 `available/enabled/interactive/click/action/allow/can/support`）显式设为 `false`，detector 会标记 `EVENT_BINDING_DISABLED`。两者都必须判为 `FIX_REQUIRED`（或在 Android 明确无后置条件时给出具体 `NO_DEFECT` 证据），编辑目标必须包含实际禁用该实例的父调用点和真实领域 handler；不得以“事件已绑定”“父组件存在”或“组件内部 enabled 表达式”闭合。**

`UNCONSUMED_ROUTE_RESULT` 表示具体点击链执行了带值 `navigation.pop(result)`，且至少一个能按字面 route 定位的具体 push site 没有自己的结果回调。另一个调用方已消费结果不能替这个调用方闭合。Review 必须继续检查结果页在 pop 前是否已独立完成持久化、事件发布或刷新：若结果只是可选通知且领域效果已完成，可判 `NO_DEFECT`；只有 Android 依赖返回结果形成后置条件、而 ArkTS 既无调用方消费也无等价本地效果时，才判 `FIX_REQUIRED`。

`action_variants` 非空时，必须逐 variant 检查共享 dispatch handler，并优先读取 `action_variant_android_hints[action_id]`。只要某个可见 action 在 Android 有具体 branch，而 ArkTS 共享 handler 对该 variant 落入 placeholder/no-op，就可以把该 contract 判为 `FIX_REQUIRED`；summary、effect chain 和 edit target 必须点明缺失的 variant，不能用菜单总标签或另一个同名“更多”入口替代。

当 `ACTION_VARIANT_DISPATCH_GAP` 给出 `missing_dispatch` 时，逐项确认 typed 数据源中的
可见 variant 是否真的缺少 branch；给出 `unrendered` 时还需核对 Android linked action
证据，避免把仅声明但产品上故意隐藏的 enum 成员误判为缺陷。共享 dispatcher 的
`INVALIDATION/READBACK` 必须按 binding 中的具体 enum variant 审计，不能用其他 branch
的 reload、route 或错误处理闭合当前点击。

新 packet 的 `evidence_contract_version=1` 要求 SDK 未决填写 `sdk_check`，确认 hazard 填写 `repair_target_indices`；结构见 [风险承接协议](scope-ownership-protocol.md#sdk-依据具体修改与当前源码)。在第一次交稿前准备这些证据，不增加一次审查。

packet 含 `sdk_review_context` 时，先按 path/SHA 读取本次冻结的实际 SDK 位置，再定位声明；不得只搜索猜测目录。SDK 时序 hazard 不论填写哪种未决类别，都按同一协议提供与具体 setter 对应的 `api_state_checks`。已有声明位置可复用，入口适用性仍独立判断。

发布：`validate-draft` → `publish`；机械校验失败先原上下文纠正，对应类别的预算耗尽仍失败才 `mark-unreviewed`；参考审计后续按动态调度的 `reopen` 定向补审。全部批次正式发布或保守封存后才 `merge`。Merge 自动使用 plan 绑定的 scope guard，若另传不同路径或内容则拒绝。工单的 oracle、根因、owner 与状态来自真实 Reviewer；merge 保留 guard 证据但不自动提升状态，仅保证 schema/coverage，不产生正确性声明。随后必须运行：

```text
python <skill-dir>/scripts/compact_interaction_review.py quality-check \\
  --findings <out>/baseline/baseline-findings.json
```

质量闸会确认每条 evidence 的 excerpt 确实命中所引用源码行，并检测跨 contract 的重复双端证据/效果链。`FAIL` 时不得使用 FIX_REQUIRED/NO_DEFECT 计数进入修复。普通 `fast_fix` 对失败 batch 在剩余业务重试额度内用新上下文重试，仍失败才封存为 `UNREVIEWED` 并完成其余批次；参考标准审计则按前述执行完整性状态立即终止。质量闸不是语义正确性证明，但能阻止“406/406 覆盖、证据模板化”的假完整审计。
