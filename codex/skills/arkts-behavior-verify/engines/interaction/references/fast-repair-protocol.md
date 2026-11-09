<!-- when: Baseline findings 完成后读取 -->

Baseline 合并后、修复组织或注册前，先执行[局部规划恢复](planning-recovery-protocol.md)：已有证据协调归属，必要时一次少量补证并独立封存；最终只挂起受影响工单，其余继续。独立点击流程同样适用。

<!-- topics: bounded batches, ownership, two repair rounds -->

# 双轮点击效果修复

工单包含 `terminal_delivery_checks` 时，按[操作证据](operation-evidence.md)核对成功/失败的实际生产与消费，并在本次结果中保留当前源码证据；不追加修复轮次。

新工单冻结前按[风险承接与关键文件协议](scope-ownership-protocol.md)校验已确认必改文件的覆盖；缺失回到原 Review 交稿，不自动扩权或追加修复轮次。

对已确认的 UI 终端断链，按[候选解释](detector-candidate-rules.md#ui-终端与数据前置态)修复具体 Sheet 宿主或数据失败反馈，并保留协议、确认和真实命令。多个弹窗使用不同稳定宿主，涉及 Sheet 的修复执行下方[关闭与再次打开检查](#sheet-关闭与再次打开)。空数据的反馈增强仍须遵循该入口的 Android oracle 或用户明确授权，不能凭静态候选改业务政策。

热点文件无法按同因归并时，依[重叠执行协议](overlap-execution-protocol.md)使用 target writer，
不再叠加下方 organization。前置已修 handler 依 SHA 绑定回执与当前入口证据验证，不重复改文件。

冻结每轮 Repair plan 前按 [repair-organization-protocol.md](repair-organization-protocol.md)
归并重复公共断点并拆出局部 ownership。该步骤复用已完成 Review，不改变准入结论和两轮上限。

Round 1 仅消费 `FIX_REQUIRED`；Round 2 仅消费 quick review 中的 `ROUND2_REQUIRED`。普通批最多 3 个 contract；仅符合 [共享修复单元](shared-repair-protocol.md) 的显式证明才采用 `SINGLE_SHARED_REPAIR_WITH_ENTRY_CHECKS`，允许超过三个入口。所有模式仍每 contract 最多 6 个路径、每批最多 10 个 ownership paths。共享批最终 UTF-8 JSON 最多 180000 bytes，超限按同因分片，单项已超限则走普通批。新隔离模式从可信 source manifest 冻结私有副本，最多六批不同 ownership 文件并行、同文件单 writer、确定性串行发布。公共 shell/service 路径的传递闭包本身不构成共享修复证明。

Round 2 先读工单的 `round2_review_context`：当前剩余效果链、根因裁决及证据、平台结果和中审证据是本轮修复依据；必要时按其中的 SHA 引用回读完整 Quick 记录。顶层 `effect_chain` 使用当前剩余链，`baseline_effect_chain` 保留原链。Baseline 的 `root_cause` 是原始诊断，Android 期望、义务与平台要求仍是验收依据；中审的 `MATCHED/CLOSED` 不代替本轮修复结果，逐项核验后再发布。

入口修复会改变旧 stable ID；Planner 用绑定当前源码的唯一语义入口映射核对第二次 Detector，不依赖旧 ID 恰好存在。当前报告已证实解除的旧禁用/占位义务不要求重复改入口；零匹配、歧义、源码漂移或当前仍禁用时保留具体缺口。编辑前检查发布所需目标是否都在 ownership 内，避免完成补丁后才发现无法满足旧义务；不可执行项隔离到 `deferred_work_orders`，保留具体缺失目标与原因；`requested_contract_count` 保留请求总数，`contract_count` 表示可执行数，两者差额必须与去重的 deferred 项一致。Quick 和 exporter 继续展示这些项，不误伤其它 contract。

Planner 可把共享 ownership/callable 的 sibling contracts 优先放入普通批；`shared_cause_analysis` 只是分析提示，不能单独启用数量例外。显式共享模式中，一个 worker 只实施一次公共 owner 修法；当前源码已等价时复用有效补丁证据，不重复改动。按 plan 的 `findings`/`findings_sha256` 和 `contract_id` 回读双端证据及 `source_command_context`，逐入口独立核对 binding、input identity、variant、consumer、observable，并逐项完成既有九角色与结果回执。相同路径、领域或相似文案不证明同因；每条完整 `edit_targets` 都必须是这一个公共修法的共有 targets，夹带入口独有修改时回到普通批。共享补丁不让所有入口自动继承 `APPLIED`；各自残留按 `PARTIAL/NO_CHANGE` 交既有 Quick Review，不能扩 scope、加轮次或跳过候选。

遇到异步前置、跨层参数或共享 owner 时读取 [依赖审计](effect-dependency-review.md)。先修 app-owned 的资源生产顺序、参数丢失和额外失败前置，再把实际平台/网络完成留作运行时证据。发现 ownership 外静态断点时，`PARTIAL` 明确写出断点、owner 与源码证据，供唯一一次 Quick Review 在 Round 2 冻结前纳入。未解决角色沿用现有 evidence，分别以 `STATIC:` 或 `RUNTIME:` 标明静态缺口与设备/网络待证；不能确定时直写证据缺口。脚本据此派生 `partial_classification=STATIC_UNRESOLVED/RUNTIME_UNVERIFIED/MIXED/UNKNOWN`，未知不会被猜成运行时问题，也不改变原修复状态。

接通前置断链后，在当前批的编辑自查中核对原排除依据是否仍成立，尤其是新接入的服务 API 与状态消费者。`platform_contract_results` 描述修后实现：修前未调用平台 API，不允许修后仍用同一理由记 `NOT_APPLICABLE`。新发现的确定静态问题记录 `static_handoffs`，每项为 `{kind, reference, owner_paths, evidence}`：`kind=SCOPE_HAZARD` 时 reference 是既有 hazard_id；`kind=PLATFORM_CONTRACT` 时 reference 是修后 platform_contract_results 中真实 API 名，且该 API 必须是 `UNRESOLVED`。owner_paths 是具体项目相对文件，evidence 写源码/SDK 依据。只是未确认的候选仍留在 scope_review_gaps，不能写成已确认交接。

新工单 `scope_followthrough_version=1` 下，显式标为 `STATIC_UNRESOLVED`（或 evidence 以 `STATIC:` 开头）的未决平台项必须有上述交接。范围内按当前已确认工单修复，范围外不越权；交稿带交接不得报 APPLIED。脚本保留 `unowned_paths` 与下一步建议，导出和已启用 Quick 都携带新证据；它不修改原 Baseline、不自动增加批次或授权另一次审查。旧模式缺新字段继续按旧契约处理。

模型服务错误按 [快速流程](fast-workflow-protocol.md) 使用独立模型恢复预算在同一 Agent、同一 batch 上续跑，不消耗业务重试。已成功冻结的快照与 claim 保留，按动态调度检查本批和运行中 ownership 后再继续；尚未成功冻结才执行首次快照。不要因 429/capacity 立即回滚、重做基线或另开修复轮次；模型恢复预算耗尽后再执行既有失败隔离规则。

Repair Agent 只能编辑 packet ownership 在 claim 返回 worker_root 下的文件。新计划按[直接发布协议](direct-repair-protocol.md)执行：claim 冻结副本；worker 停止后 submit，主会话立即 publish，脚本完成候选合并和原发布检查，不追加逐批 AI 复核。同文件单 writer，其它文件最多六批并行；真实业务前置仍等待。fail 丢弃副本而不回滚正式源码。已有状态按自己的[兼容调度](batch-dispatch-protocol.md)或复核协议续跑，不热迁移。正式源码外部变化或可信证据漂移时停止发布。

必要平台权限可以作为精确配置目标进入 ownership：`target_kind=CONFIG_KEY`，
`path=<module>/src/main/module.json5`，`operation=ADD`，
`config_keys=["module.requestPermissions[name=ohos.permission.NAME]"]`，并提供
`required_by`、`evidence` 及原有 `role/callable/anchor/expected_change`。只允许审查
确认必需的权限新增；发布器比较完整配置树，拒绝权限替换、无关字段、bundle、签名、
依赖和环境修改。配置不是 blanket 文件授权，未进入计划不能临时补加。

错误 route 改成 Android 对应真实命令时，可在 Review/Quick 冻结
`behavior_replacements`：每条含 `id/path/entry_anchor/before_excerpt/required_after_call/
source_sha256/android_evidence/reason`，Android evidence 含真实路径、SHA、行和片段。
每个 span 仅替换一个已证明错误的 route 激活，不包含点击/事件/dialog，也不改变导航
成员、模式或顺序。Repair 在 draft 顶层回填 `behavior_replacement_results` 的 `id/before_sha256/
after_sha256/after_excerpt`；dispatcher 按精确 span 和命令核验。其余点击、事件、路由及
dialog 仍受 preservation 保护；不得通过放宽全文件 route 计数放行删除。
不得扩张到 Android、测试、Spec、导航拓扑或无关页面；不得把局部按钮状态、临时数组或 toast 当成持久化/集合/目标页面结果。优先调用项目已存在的领域 writer/service，并补齐终态确认、失败传播、活动状态清理、事件失效、真实回读和 observable 稳定性。调用现有 service/writer 时必须保持 Android oracle 的命令模式和关键参数；不能因为方法名称相近就把用户主动即时命令替换为后台受约束/计划命令，也不能混淆 GET 与额外 HEAD 前置、add/remove/toggle、delete/archive 或强制/默认约束。存在多个候选变体但证据不足时输出 `NO_CHANGE+EVIDENCE_GAP`。

执行完整性规则统一见 [fast-workflow-protocol.md](fast-workflow-protocol.md)。本协议只补充
修复语义：真实 Agent 逐 batch 产出；已有精确 `edit_targets` 时必须给出具体阻塞或提交
`APPLIED/PARTIAL`，不能用模板化 `NO_CHANGE + EVIDENCE_GAP` 代替。

效果链进入 `@kit.*`、`@ohos.*` 或项目封装的异步平台 API 时，必须读取当前项目实际 SDK 的 `.d.ts`/声明文件，核对 mode 与 listener/callback 是否兼容、参数和 headers 容器类型、认证/cookie/redirect/proxy、URL 规范化、文件落点及成功/失败终态。对 changed files 运行 `platform_effect_guard.py`；其 `BLOCKED` 是 `APPLIED` 的确定性否决项。播放/下载的编辑后 scope 检查由发布器在实际候选上完成：新 direct 默认自动覆盖整批工单领域，不需 worker 重跑同一 scope 扫描，也不手选 --scope-target。旧 direct/complete 继续按原 --scope-target 与 --scope-guard 规则；覆盖双域时使用 all。最终阶段的整轮 scope 检查仍按原流程执行。`blocking_hazards` 是待结合实际调用关系裁决的候选；确认适用后，工单才纳入真实 owner。播放器宿主沿父子组件实例定位，不为每个叶页面重复创建容器；下载枚举或配置不是执行命令。发布器按当前 contract 的调用关系与源码绑定裁决检查候选：有效的 `NOT_APPLICABLE/NO_DEFECT` 不重复阻断；缺失、漂移、未决或仍适用的 blocker 保留静态缺口，不能报 `APPLIED`。`CONDITIONAL_RISK` 同样要求裁决，不能静默忽略；不得因此阻止同批其它可编辑 contract。

对 `request.agent`，不得把 SDK 支持且推荐的 `Mode.BACKGROUND + Task.on(...)` 改成
`FOREGROUND` 来消除不存在的冲突；相对 `saveas: './name'` 与调用方 `cacheDir/name`
是同一平台位置，除非 literal basename 确实不同，不得改成绝对路径或判 mismatch。
不得在 Android 只有真实 GET/下载时新增或保留一个会先行失败的无条件 HEAD 前置；若
HEAD 是既有实现，也必须用 Android oracle 证明它必要且失败不会阻断有效 GET。

对 AVPlayer，`audioRendererInfo` 只能在 initialized 设置，而 API 12+
`audioInterruptMode` 只能在 prepared/playing/paused/completed 设置并应早于第一次 play。
不能因为两者都是音频属性就放在同一 initialized 分支；平台报
`current state is not prepared/playing/paused/completed` 时必须把该赋值位置作为根因，
不能只在页面层增加 catch、toast 或重试。

播放/下载必须把义务分成两条轨道：

- `STATIC_REQUIRED`：真实实体/媒体 identity、精确领域命令及参数、入口/事件绑定、错误分支和 app-owned 状态投影。这些能从当前源码和 SDK 声明确定时，Repair Agent 必须先做有界修复。
- `RUNTIME_DEFERRED`：平台回调实际触发、AVPlayer prepared/playing、最终文件非空、设备网络/音频焦点、跨进程事件时序等只能在设备或外部能力上确认的条件。缺少这类证据不能声称 `APPLIED`，但也不能把它当成“没有安全补丁”的理由。确定性 `DOWNLOAD_AGENT_STALE_TARGET_COLLISION` 不属于此轨道；若 `saveas` 会复用固定目标而 create 前没有 stop/delete 或幂等替换，必须先做静态修复（唯一目标名或安全清理旧任务/文件），再把最终文件存在性留给运行时确认。

如果第一处断链在 app-owned handler、route、ViewModel、repository 或已有 service 调用之前，且真实命令和输入 identity 已可从源码确定，即使平台契约或运行时终态仍为 `UNRESOLVED`，也应编辑并报告 `PARTIAL`，列出已解决的静态角色和剩余 runtime obligations；只在根因本身依赖未知平台签名、没有现有命令可复用、或无法限定 ownership 时报告 `NO_CHANGE+EVIDENCE_GAP/NO_SAFE_PATCH`。不得因为“没有真机证据”跳过一个确定的空 handler、缺失 binding、错误参数、错误 route 或未接入既有命令。

对于 `EVENT_BINDING_DISABLED` 或 `CLICK_DISABLED_CONTROL`，禁用门本身就是断链的一部分，不能当作运行时证据缺口。如果被审计的组件实例仍传入字面量 `gate: false`（例如 `mediaActionsAvailable: false`），修复必须修改该实例门控，或以确定性代码事实证明点击前已赋值为 true；只改回调不算 `PARTIAL`。发布器会拒绝在字面量禁用门仍存在时发布 `APPLIED`、`PARTIAL` 或基于证据缺口的 `NO_CHANGE`；动态门控仍需 Review 明确证明，不能猜测。

相对下载路径和合成 origin 变体属于 `RUNTIME_DEFERRED`，不能升级成无证据的硬阻塞，也不能被静态 `APPLIED` 当作已解决；`loadData` intercept 把 `data:` 内部文档送到外部 `startAbility`，只要拦截回调自身或其所在页面同时具备本次播放/下载入口，就属于 `WEBVIEW_SYNTHETIC_ORIGIN_FORWARD` 静态 blocker。完全独立、没有目标入口的 shownotes 外链只保留为 review/runtime 证据。播放宿主还必须把根级 overlay 的层级与命中明确化：展开播放器时 mini-player 应使用 `Visibility.None`（或等价的不参与命中方式），仅使用 `Visibility.Hidden` 不能自动视为安全。修复结果必须填写 `root_cause_resolution/root_cause_evidence/platform_contract_results`。仅增加等待、toast、异常捕获、失败清理或按钮回退，原始平台失败原因仍未闭合时，只能 `PARTIAL/NO_CHANGE`。

播放的 `playing` 终态还必须有可达且稳定的用户承载：实际宿主中的 player bar 或播放器 route 能显示当前 item；沿父组件和具体实例检查遮挡与命中，确认宿主断链后才把真实 owner 纳入 edit target。下载使用确定性临时 `saveas` 时，若 create 前未处理旧 task/文件冲突，必须优先修复幂等清理或唯一目标策略；不得只把失败按钮改成成功态。

下载修复还必须从最早失败点向后处理：目录创建需幂等；active map/持久化队列建立后的任何 destination/config/create 异常必须进入统一失败清理；后台 request.agent 任务不能由页面固定超时同步等待；最终文件和数据库 commit 成功前不得发布 `COMPLETED`。当多个下载 hazard 同时命中时，它们属于同一下载 owner 工单，必须全部保留在 `scope_hazards` 和 edit targets 中，不能用最后一个 hazard 覆盖前面的根因。

失败投影必须区分“领域会话/实体仍存在”和“当前处于 playing/downloading/success”。不得为消除假 active 状态而直接隐藏整个媒体会话、下载实体或错误后的重试入口；也不得让失败项目继续显示为成功或正在执行。若用户仍应能看到错误、重试或当前媒体实体，则 `active/visible/existence` 不能机械与 `playing/downloading` 同步清零。

每个 contract 必须按 packet 的九个 `effect_obligations` 回填 `effect_role_results`，状态为 `IMPLEMENTED / ALREADY_SATISFIED / NOT_APPLICABLE / UNRESOLVED`，并引用具体代码事实。以下情况不能报 `APPLIED`：

- handler `await` 的方法只完成初始化、URL 赋值、任务创建或 listener 注册，且缺少匹配任务的真实终态处理与消费者更新证据；受理返回后的回调/订阅链可以提供这些证据，无需强制点击等待整个任务；
- error/failed 分支仍保留 active、playing、downloading、visible 或 success 投影；
- 下载/导出没有最终文件、大小或数据库回读；
- observable 会被随后到达的 observer、订阅事件或 shell 同步立即覆盖；
- 页面初始化或 WebView 拦截还会产生与目标交互无关的外部 Ability 副作用。

这些角色有任一 `UNRESOLVED` 时只能报 `PARTIAL`（已安全修改）或 `NO_CHANGE`（确实没有可界定的安全修改），让快审决定 Round 2，不能用“已接入真实 service”概括为完成。对播放/下载，`UNRESOLVED` 若只属于 `RUNTIME_DEFERRED`，不得阻止先完成 `STATIC_REQUIRED` 的修复。

每个 contract 输出 `APPLIED/PARTIAL/NO_CHANGE/FAILED`。`APPLIED` 需要实际 changed files、根因 `CLOSED/NOT_APPLICABLE`、所有平台契约 `MATCHED/NOT_APPLICABLE`、无 unresolved 且九个效果角色均非 `UNRESOLVED`；`PARTIAL` 要列 changed files、已解决的静态角色、剩余静态 owner 或 runtime/platform obligations，并至少标出一个 `UNRESOLVED` 角色；`NO_CHANGE/FAILED` 不得声明 changed files，并从 `DEPENDENCY_MISSING / OWNERSHIP_INSUFFICIENT / NO_SAFE_PATCH / ALREADY_EQUIVALENT / EVIDENCE_GAP / COMPILER_FAILURE / BATCH_EXECUTION_FAILED / BLOCKED_BY_FAILED_DEPENDENCY` 选择 `reason_code`。发布前由 dispatcher `complete` 调用 source guard 检查越权与 preservation；除前述精确审查的错误 route 替换外，不得删除点击入口、事件 binding、route/dialog 激活，也不得新增占位标记、当前未安装的第三方 package import、ArkTS 禁止的 `any/unknown`、未收窄 catch 参数的原值 rethrow、新的 `implements` 声明，或引入新的结构分隔符失衡。点击效果修复通常不应重塑类型体系；确需新增接口实现时留给编译纠偏或项目专门重构。对新增 SDK API、可空值和重载调用必须读取当前 SDK/项目签名，不得凭 Android API 名称猜 ArkTS 类型。保护失败时用 `repair_dispatch.py fail` 回滚当前批并生成正式结果后继续，不终止整轮。

快速审查可在 Round 2 前给出一组新的精确 targets；计划一旦生成不得再次扩张。Round 1 源码未变且原拒绝仍成立时不重复执行；只有中审按 [证据解锁约定](quick-review-protocol.md#新证据解除旧拒绝) 确认原阻塞已消除，或证明同入口存在独立新根因，或已有 scope 归属规则允许时，才保留有界修复。没有有效解锁时清空 repair-shaped 字段；ownership 不足仍必须新增 ownership path。Round 2 只消费 `ROUND2_REQUIRED`。运行时验证仅在用户授权范围执行；没有完整设备后置条件时保留未验证状态，安装不证明功能可用。

新工单含 `evidence_contract_version=1` 时，执行 `scope_repair_targets/shared_scope_repair_targets` 中保留的具体要求，静态未解决 role/API 与 `static_handoffs` 需引用当前 worker 源码 `source_evidence`。依赖回执和当前源码优先于旧缺陷描述；字段及既有纠正预算见 [风险承接协议](scope-ownership-protocol.md#sdk-依据具体修改与当前源码)。这不增加独立复核阶段。

**当批已有权限的确定断点应当批处理。** 已确认属于现有 `REQUIRED` 角色、且修改落在本批 ownership 内的静态缺口，应在当前修复和原预算中完成；不能一边报告明确缺失，一边只以“未真机验证”“已接入命令”结束本批。确实无法安全处理时，仍可如实报告 `PARTIAL/NO_CHANGE`，但须在原有 `effect_role_results.evidence` 或未决说明中写明具体阻碍（如需要未授权 owner、SDK/接口事实不足、依赖未就绪、需求冲突或原预算已耗尽）。已有证据并非已经存在安全修法，不得为清零猜测实现。此要求不改变 `ENTRY_CHECK_ONLY` 的只读权限，不扩大 ownership，不创建新一轮或反复修改循环。

异步 `INVALIDATION/READBACK/OBSERVABLE_STABILITY` 的结论需沿“终态通知 → 实际状态写入 → 当前渲染属性”追踪。命令刚受理时的 reload、service 单例状态改变、另一个页面刷新，都不能证明当前页面的缓存数组/克隆模型会更新。页面使用快照时，找出完成、失败、取消如何更新这份快照以及订阅的建立/释放；使用真实响应式绑定时引用该绑定即可，不强制添加冗余 observer。对照 Android 当前动作，确认缺口后只修有证据且已授权的目标。

## Sheet 关闭与再次打开

本次工单涉及 Sheet 宿主、绑定、显隐状态或关闭/确认链时，由当前 Repair Agent 在已有批次内检查；共享补丁的 `ENTRY_CHECK_ONLY` 同样适用。同文件中无关的 Sheet 不扩大本次范围。

1. 定位当前入口实际使用的宿主、显示状态及写入者，确认打开动作能使对应 Sheet 显示。
2. 根据当前 SDK 默认行为和实际 options，列出允许的关闭方式：自定义关闭/取消、确认后的关闭，以及适用的遮罩点击、系统返回、手势退场。逐条追踪关闭后的状态回写；关闭按钮中的赋值不能代替系统退场路径的证据。关闭按钮或拖动条隐藏也不能单独证明系统退场被禁用。
3. 对这些可达关闭路径，检查同一页面实例内再次触发打开能否重新展示正确 Sheet，并保留原输入和确认顺序。明确被禁用的关闭方式在证据中注明配置/SDK 依据，不要求实现该能力或改变既有交互政策。

接受当前状态模型与 SDK 支持的双向绑定（如 `$$`），或经实际调用链证明有效的关闭/生命周期回调同步。核对回写的是同一宿主消费的状态；仅看到回调名称或局部关闭赋值不构成通过证据。

复用 `effect_role_results` 中 `OBSERVABLE_STABILITY.evidence`，简要记录各适用关闭路径的源码锚点、状态回写和再打开结论；共享根因只分析一次，各入口核对绑定关系。无需新增字段、表单或重复长报告。

源码已证实关闭后状态残留时，将该角色标为 `UNRESOLVED` 并记录 `STATIC:` 断点；在既有 ownership 内修复后重新核对，越界按原协议保留缺口。SDK 行为或回写链尚未查明时保留证据缺口，不能仅以宿主已拆分、首次能显示或原 Detector 信号消失认定完成，也不能把可静态确认的缺失归为仅待真机验证。

这是现有修复批次的源码自查，不增加 Baseline 候选、Agent、扫描或修复轮次，也不默认执行真机；授权真机验收时再验证相同的打开、关闭、再打开序列。
