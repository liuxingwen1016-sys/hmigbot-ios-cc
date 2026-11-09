<!-- when: Round 1 与第二次全量 detector 完成后读取 -->
<!-- topics: quick review, Round 2 routing, blockers -->

# Round 1 后一次快审

允许按[重叠执行协议](overlap-execution-protocol.md)在 Round 1 尾部准备稳定入口。
最终 Detector、正式 Quick 校验和 Round 2 全部回执屏障保持；准备与收口由同一 reviewer 完成。

worker 先读[单批任务与恢复](worker-task-protocol.md)。新 affinity 按共同 callable 分包，
公共分析可引用一次；逐入口裁决保留，格式见 Review 提速协议。
确认剩余断点时，在既有九角色检查中沿生产者、终态、状态写入、失效、消费者
核对完整 REQUIRED 链，再列齐有证据的缺失 owner targets；已满足环节保留证据，
不增加无意义改动。Round 2 从完整责任划分开始，不只修最前面的 handler。

仅在已经启用 Quick/Round 2 时执行本协议。Baseline 含 `evidence_contract_version=1` 时，SDK scope 未决继续提供 `sdk_check`，`ROUND2_REQUIRED` 已确认 hazard 的 `repair_target_indices` 必须指向本条新的 `round2_edit_targets`，不能引用旧编号；结构见 [风险承接协议](scope-ownership-protocol.md#sdk-依据具体修改与当前源码)。

新 Review 使用 [公共证据、依赖/复杂度分包与全槽位启动](review-efficiency-protocol.md)。初始化后先 `claim-ready`，派发所有返回批次再等待；同一 batch 中断沿用原 Agent，不把该恢复要求扩大到后续新 batch。

批次调度复用 [动态批次调度](batch-dispatch-protocol.md)：主会话 claim 后派发独立 worker，任一批 publish/保守封存并 complete 后立即补位，不等待全部并行批结束。Quick 全部收口后才进入 Round 2。

只复查 Baseline `FIX_REQUIRED`。每批默认 8 项、最多六批并行。按 packet 的 `review_focus` 先读原始根因、Round 1 实际修改证据、未解决角色与当前 blocker，回答“补丁是否解除断点、是否引入相邻问题、Round 2 还缺哪个 owner”。完整工单、Detector 和修复记录通过各摘要的 `full_record` 在 `artifacts` 中定位路径与 SHA，再按 selector 回读；不因已有摘要而跳过双端证据与当前源码核对。`scope_hazard_catalog` 保存共享 hazard 正文，逐项 hazard 引用须据此解析。

`patch_catalog` 中实际 diff 复用 Round 1 已有 source-diff 和 batch-baseline，只比较冻结 ownership 内的文件。引用缺失或绑定失效时保留 patch 证据缺口，`changed_files` 列表不能代替补丁；共享文件后继批的改动应按当前累计源码解释，不能冒充某一批独立修复。先处理未关闭的静态角色和新 owner，再列出运行时待证条件；`round1_partial_classification` 仅描述上一轮回执，不能覆盖当前 blocker，角色名称含异步、文件或回读不意味着只能运行时确认。以上均在本次 Quick Review 内完成，不增加扫描轮次或审计步骤。

Round 2 共享分组只使用本次 `ROUND2_REQUIRED` 的可选 `shared_repair`，格式见 [共享修复证明](shared-repair-protocol.md)。直接严格读取当前源码，重新证明剩余共享断点、统一修法、命令语义、完整相同 targets 及本条入口检查；不能继承 Baseline proof，也不能把已修好的公共 owner 用作新的共享断点。共享证据须覆盖本次全部 targets，入口证据须定位当前 contract/实际 consumer。只有入口独有残留时走普通修复批；guard 将结论降级或清空修复目标时同时清除该 proof。Quick 的逐项裁决与分包上限保持，不增加独立核验 Agent。

结合实际补丁，每个独立根因核对一条最相关且源码可达的反例序列，例如失败后重试、重复触发或旧回调晚到；普通同步点击只核对适用的分支。补丁改变 `await` 边界或状态订阅时，优先将“终态尚未到达时观察或再次操作”选为这条反例，核对 Android 原有的执行中状态与操作入口。在现有 `effect_role_checks.evidence` 或 `evidence` 中写 `COUNTEREXAMPLE: 触发序列 → 当前源码分支 → 保持或违反的 Android 后置条件`。确属相同根因时复用这条分析，各入口仍核对参数、绑定与消费者；没有适用的异常分支时说明依据。发现具体断点才进入修复，证据不足保留缺口；不新增测试阶段、独立表单或另一轮审计。

涉及 Sheet 的工单（含共享补丁的入口复核），由当前 Quick Agent 独立执行[关闭与再次打开检查](fast-repair-protocol.md#sheet-关闭与再次打开)。优先以“打开 → 当前允许的一种系统退场 → 同页再次打开”为反例，并核对其余适用关闭路径的回写；所有系统退场均被禁用时使用实际允许的关闭方式。把结论写入现有 `OBSERVABLE_STABILITY` 角色的 `effect_role_checks.evidence`。不能继承 Repair 的通过结论，也不能仅因宿主冲突消失而 `CLOSED_LIKELY`；源码证实缺少回写时标 `BLOCKED`，存在有界修法则进入 `ROUND2_REQUIRED`，证据不足则保留 `UNCERTAIN`。已有 `ALREADY_EQUIVALENT` 拒绝时，按下方“新证据解除旧拒绝”提交不同关闭分支的新根因证据，不绕过原有 guard。本检查复用本次 Quick，不另开 Agent、阶段或默认真机验收。

`plan` 从工单 `effect_domains` 延续领域范围，自动扫描当前源码并绑定新 scope guard；`[]` 表示普通点击。显式传入 guard 不能漏域。packet 区分有路径依赖证据的 blocker 与 `unassigned_scope_hazards`；后者需要 Reviewer 读源码确定关系，不能按领域、页面名或 summary 猜测归属。异步共享链按 [依赖审计](effect-dependency-review.md) 核对资源生产顺序和参数传递。未裁决的相关 blocker 不能 `CLOSED_LIKELY`，但不阻止对其它已确定断点生成有界 Round 2 修复。

对适用的静态 hazard，在冻结 Round 2 之前显式提出 owner targets。Round 1 只因 ownership 不足留下的服务缺口应在此补齐；不能写成“只剩 runtime”。无关 hazard 用实际调用/状态独立性证据排除，不能为清零而修改无关服务。

对 packet 的全部 blocking 与 conditional 候选（包括路径命中与未归属项），回填 `scope_hazard_reviews`：每项使用原 `hazard_id`，`relation` 为 `APPLICABLE / NOT_APPLICABLE / UNRESOLVED`，`evidence` 写当前调用、状态依赖或父宿主依据。`APPLICABLE` 只确认关系；所有候选还需 `defect_status=DEFECT_CONFIRMED / NO_DEFECT / UNRESOLVED` 区分缺陷、已有保护与证据缺口，省略时按未决处理。路径命中或 throws 清单不能直接确认缺陷。缺少裁决保留静态 scope gap、阻止 `CLOSED_LIKELY`；独立已确定的 `ROUND2_REQUIRED` 仍可执行。脚本不自动追加 owner。

裁决绑定 `source_bindings=[{path,sha256}]`，工具按当前源码冻结与校验。此前的 `NOT_APPLICABLE/NO_DEFECT` 仅在相关源码字节和证据绑定有效时复用；漂移后重新裁决。目录存在性保护应检查真实控制流、实际调用的 helper 和匹配的异常处理；不能以附近出现错误码或其它分支有检查作为排除依据。

Packet 的 `retry_guard` 默认复用未解除的旧拒绝：源码未变且 `NO_CHANGE` 原因为依赖缺失、无安全补丁、证据缺口或已等价时，封存为 `UNCERTAIN`。只有下述可核验的新证据，或已有 scope 归属规则能消除该阻塞时才保留修复。`OWNERSHIP_INSUFFICIENT` 仍要求 Round 2 targets 新增路径。只有 `ROUND2_REQUIRED` 会进入 Round 2。

每项必须逐一回填九个 `effect_role_checks`，状态为 `SATISFIED / NOT_APPLICABLE / BLOCKED / EXTERNAL_EVIDENCE_REQUIRED`，并提供当前源码证据。角色与 Baseline 的 `effect_obligations` 一致：页面进入副作用、输入 identity、领域命令、异步成功终态、失败状态、持久化/真实文件、失效通知、回读和 observable 稳定性。

`CLOSED_LIKELY` 必须同时满足所有角色均为 `SATISFIED/NOT_APPLICABLE`，且：真实 handler 可达；有效输入/identity；真实领域命令；异步成功终态确实发生；失败不会继续投影为活动/成功；持久化、集合或最终文件真实变化；失效/刷新；真实回读；用户 observable 在后续通知后仍稳定；且无可达 skeleton/TODO/FWD-REF/无条件 throw/固定空返回 blocker。Detector 转绿或 `APPLIED` 单独不够。确定性工具会沿“点击入口 → 同文件方法 → 全仓唯一实现、类名限定实现或 receiver 显式类型限定实现”最多追踪 3 层跨文件调用；命中的 blocker 是关闭否决项。Reviewer 还必须从 observable 反向 `rg` 其状态字段、事件类型或 setter 的其他写入点，捕获不在 handler 向下调用链上的覆盖者。能用不超过 6 个精确 ownership 修复时输出 `ROUND2_REQUIRED`，否则 `UNCERTAIN`，不得忽略提示写成 `CLOSED_LIKELY`。

每项还必须填写 `root_cause_resolution/root_cause_evidence/platform_contract_results`。`CLOSED_LIKELY` 要求根因已 `CLOSED/NOT_APPLICABLE`，且平台契约没有 `UNRESOLVED`。失败投影要分别检查实体/会话存在性、执行中状态、错误和重试入口；把 `playing/downloading=false` 扩大成 `active/visible=false` 不能自动算闭合。

快审还必须逐字核对 Android 证据中的领域命令变体与关键参数。只接到同类 service 不代表闭合；即时/受约束、前台/计划、GET 与额外 HEAD 前置、add/remove/toggle、delete/archive、强制/默认参数不一致时必须进入 `ROUND2_REQUIRED` 或 `UNCERTAIN`。对基于 listener/callback 的状态机，先辨明 `await load/start/createTask` 返回的是任务受理还是 Android 所需成功终态。受理返回不能单独证明异步完成，应继续追踪匹配任务的终态回调/订阅及回读；源码证实终态确认链缺失或断开时才将 `ASYNC_TERMINAL=BLOCKED`，仅缺外部运行证据时保留 `EXTERNAL_EVIDENCE_REQUIRED`。按依赖审计核对执行中交互，不强制把点击 Promise 改成等待整个任务。

其他状态必须给出 `remaining_break`、`remaining_effect_chain`、合法 `change_kinds` 与最多 6 个 Round 2 精确目标。导航拓扑目标不进入修复。单批业务重审仍最多一次；模型服务错误按 [快速流程](fast-workflow-protocol.md) 的独立恢复预算续跑原 Agent，不消耗业务重试，不因缺少 draft 直接新建。对应类别的预算耗尽仍失败时用 `mark-failed` 封存为 `REVIEW_FAILED`；这些 contract 进入 deferred 而不进入 Round 2，其余批次继续。

快审只为 Round 2 定向，不生成 Admission/Closure/cache/final gate，也不声明正确性。

## 新证据解除旧拒绝

仅在申请解除旧拒绝时填写可选 `retry_resolution`，其余工单省略。先按 packet 的原回执引用检查拒绝原因，再说明新发现如何消除原未决项；单纯重新表态或换路径不构成新证据。

- `prior_reason_code`、`prior_rejection_fingerprint`：原回执的真实绑定。
- 原阻塞已消除时 `resolution=RESOLVED`，`resolved_objections` 为已消除的原回执 `unresolved` 原文，`explanation` 逐项说明依据和修法。
- 同入口发现不同根因时 `resolution=NEW_CAUSE`，以 `retained_objections` 保留旧拒绝原文；`new_cause` 包含 `target`、`evidence_index`、有界源码 `branch`、`trigger`、`violated_postcondition`、`distinction`。真实不同 callable 或同 callable 中不相交的条件分支需有新源码证据。旧 `ALREADY_EQUIVALENT` 不撤销，也不封锁这个新根因。
- `new_evidence`：1–6 条具体源码或 SDK 声明证据，每条含 `path/sha256/line/excerpt`，以及与现有 Round 2 目标唯一匹配的 `target={path,role,callable,anchor}`。项目内路径相对源码根，外部声明使用具体绝对文件路径。

脚本校验原回执绑定、引用片段和 SHA、证据增量及目标匹配，并为新根因绑定指纹；只换措辞、路径或重复原片段不能解锁。是否解除旧阻塞或证明相邻新缺陷，由 Reviewer 结合调用关系判断，哈希正确本身不能证明修法成立。仍须提供至少一个 `BLOCKED` 角色、当前剩余链及既有预算内的目标；scope、导航拓扑和闭合否决继续生效。原绑定缺失、证据仍旧或结论不充分时沿用原封存规则，不增加第三轮。

## 播放返回后重开（强制后置条件）

当目标域为 playback 时，不能只检查首次点击后出现过播放器或日志进入
`playing`。必须把以下顺序作为同一个 effect chain 审查，并在 Review/修复工单中
保留对应的状态字段、写入者和消费者：

`playItem(itemId) → 返回来源页 → player bar 仍可见且 itemId 不变 → 点击 bar →
展开播放器 → 等待 3 秒仍可见且 itemId 不变`。

从静态代码反向追踪 `playerExpanded`、`playerSheetState`、播放器可见性和导航
栈的所有写入点，尤其是 `@Monitor`、`onPageShow/onPageHide`、shell sync/refresh
和异步回调。把 `playerExpanded = shellState.playerSheetState === EXPANDED`、
三元投影或 setter 重投影视为潜在覆盖：如果其来源可能仍是
`COLLAPSED/HIDDEN/false`，必须进入 `ROUND2_REQUIRED`，不能因点击 handler 已调用
或底部条短暂出现而 `CLOSED_LIKELY`。只有能证明返回后展开状态由同一播放会话
稳定承载，且没有后续生命周期覆盖，才可关闭该 contract。

同时检查展开播放器与折叠播放器条的互斥可见性：当 `playerExpanded` 为真时，
根级 mini-player bar 必须隐藏或让位，不能只按 `playbackState.visible` 保持显示。
否则底部条会覆盖展开页的后退、播放和前进控制，即使页面本身已经展开也必须
保持 `ROUND2_REQUIRED`。



草稿交付前运行 `quick_interaction_review.py validate-draft --plan <plan> --batch-id <id> --draft <draft>`；此命令只读校验，不发布。按 packet 的 review_focus 和实际 diff 优先审查变化与未闭合链，未变化公共源码事实按 SHA 复用；九角色仍逐入口独立裁决。
