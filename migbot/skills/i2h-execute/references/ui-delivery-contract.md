# Stage 1 UI 交付与消费契约

新生成必须使用 schema_version=2，并先读 [layout-fidelity.md](./layout-fidelity.md) 与 [ui-integration-1030.md](./ui-integration-1030.md)。
源码决定布局关系和尺寸，运行时证据选择状态、检查内容和验证结果；不能由 dump 坐标反推固定布局。
schema 1 仅供读取历史实验，不得用于绕过新项目的所有权和验收门。

## Plan：先固定完整交付分母

~~~sh
python3 <i2h-plan>/scripts/ui_delivery.py draft --project-root <project> \
  --out <project>/spec/baseline/ui-delivery-approved.json
~~~

草稿先按源码组件汇合 canonical snapshot 与 composition，再为每个组件生成一个单元。
独立 snapshot 提供真实 state IDs，composition 提供宿主关系；不得事后保留第一份重复单元。
unit_id 是不透明 ID，不携带宿主所有权；已有 host-bound 状态时不能虚构无证据的 default。
主线程根据源码补齐：
source_refs、required_states、输出符号、正式路由/受控 Preview、宿主 slot、owner、
必要底栏/弹层单元、source-backed input_alternatives 和排除项。
展示差异并处理，JSON 格式变化可继承，不增加重复的同内容审批。

full_ui 范围必须解释所有 canonical snapshots；排除需要 source_refs、reason、
decision_ref。缺截图不能自动排除。只交付 smoke path 时显式使用 selected_smoke。
Plan 已知项目原生 UITest 使用稳定目标控件 ID 时，将该单元的真实操作入口登记到
`source_obligations.runner_action_ids`。图标按钮可同时保留源无障碍名称。
静态门禁要求实际 `.id(...)` 修饰符，真机回执继续核对可点击和进入正确状态。

静态索引保存可直接定位的 SwiftUI 日期显示 `date_format_calls`，包括原表达式、显示槽位、
日期档位、时间档位及源码行。G0 和正式 UI 义务检查可定位同一显示槽位退化为
无参数 `toLocaleString()` 的实现。字段改名、共享格式函数和显式本地化配置仍以实际输出复核。

`share_link_calls` 保留 SwiftUI `ShareLink(item: ...)` 或 `ShareLink(items: ...)` 的
行号、入参形态和可直接读取的按钮文案。G0 和 UI 义务门禁检查可确定绑定到本地纯复制
处理器的同名按钮。共享服务、动态文案、分享数据和系统面板行为由实测核对。

生成单元包含 unit_id、page_id、component、presentation_role、required_states、
output={file,symbol,builder}、source_refs、generation_owner、integration_owner=closer。
draft 会从源码 modifier 生成可审查的 `presentation` 提示。`.sheet()` 使用
`presentation_role=hosted_destination` 和 `harmony_mapping=bindSheet`，
`.fullScreenCover()` 使用 `bindContentCover`，共享声明使用
`presentation_role=embedded`。主线程仍需依据完整源码确认宿主和正式路由。
宿主单元的 `source_obligations.presentations` 保留 `.sheet`/`.fullScreenCover` 的源码事实，
供 execute 门禁检查生成文件是否真的使用 `bindSheet`/`bindContentCover`。目标 SDK 不支持
原生绑定时，必须在宿主文件写入完整的 `presentation_fallback` 标记，声明 owner、state、
scrim、corner、detent、dismissal 和 safe_area，不能只用 pageKey 或普通导航页代替模态层。
页面已有关闭动作时，宿主应关闭 `bindSheet` 默认显示的关闭按钮。交付门禁在可解析的
宿主接线中检查重复按钮，动态选项由实际状态的视觉和交互回执核对。
嵌入单元增加 integration={host_file,host_builder,child_symbol}。
同一内容经多个独立宿主呈现时，`integration` 可为对象数组。每个槽位独立核对，模态槽位可声明 `mount=bindSheet` 或 `mount=bindContentCover`，并绑定实际 Swift `source_ref`。

每单元的 owned_ui_roles、每状态的 responsibility 明确 shell/content/overlay/behavior；
宿主采到不代表宿主实现正文。相同层级正文不能重复认领；跨层覆盖填写 layer/overlap_reason。
单独 verification_states 指定整页组合的验证 owner 和 implementation_units，不能把组合验证责任
混为正文实现责任。toolchain.sdk_definitions/product 指向实际 SDK；presentation 和 state_setup
固定设备、密度、窗口、字体、日夜/城市/渠道、Tab/月/滚动条件，实际到达必须逐项相同。

每个源码内容组件只生成一次，同一内容需要独立入口时用独立 wrapper 单元；
嵌入内容是普通 ArkUI struct，仅真实路由 wrapper 使用 NavDestination。
底栏和所有范围内 Tab 都是 Stage 1 UI 义务；宿主 required_builders 显式列出 tabBar 等
自持 UI builder，子组件的 integration 列出宿主槽位。composition 的 Fragment 不能无声消失，
排除组件必须在 component_exclusions 写来源和审批依据。Stage 3 Step 3a 复用和接入真实逻辑，
新增 UI 必须登记增量。fixture 只解决展示输入，不结清网络、登录、支付等业务义务。
对于可直接识别的 SwiftUI `TabView` 子页面，草稿在 `presentation.swiftui_tab_roots` 列出
宿主声明和 Swift 源锚点。确认每个目标 Tab 槽位并将该锚点写入 `integration.source_ref`。
审批前验证按源码重查锚点、宿主输出符号及路径。间接 builder、动态 Tab 和 UIKit 的宿主
关系继续按源码审阅并登记。运行时到达证据由 Stage 1 冒烟验收核对。

required_states 每项有 state_id、arrival_mode=formal/preview/behavior；
运行时绑定可有 evidence_page_id、evidence_state_id、region_px。
宿主内子组件必须绑定 reviewed region，引用可复用宿主证据。未采状态由 runtime-refs 的 zero_mapping
或 source-backed state_gaps 机械派生替代，保留视觉 BLOCKED。任意非空理由不能解锁 fallback；
已有 states/host_bindings 时禁止整页“未采集”，绑定不匹配必须报错。静态事实替代仍须真实源码依据。

~~~sh
python3 <i2h-plan>/scripts/ui_delivery.py validate --project-root <project> \
  --inventory <inventory> --receipt-only --out <validation-receipt>
~~~

确认后用 `ui_delivery.py approve --project-root <project> --inventory <inventory> --validation-receipt <validation-receipt> --confirmation-ref <ref> --out <inventory>`。
原地审批在 approved 清单保留候选和验证回执摘要。既有工程的历史清单路径继续兼容。
检查修订：`ui_delivery.py diff --project-root <project> --inventory <inventory> --out <diff.json>`。

### iOS 执行域解析路由

canonical baseline 冻结不变，原始槽位、source_refs hash 严格锁定。解析请求明确为 JSON：baseline_sha256、requests 数组。
集成诉求：unit_id、slot_index（可选，默认 0）、original_slot（原基线槽位对象）、integration（nested caller_file/caller_line/callee/expected_owner/targethost）。
源码替代：unit_id、source_only（state_id/alternative_kind/source_file/source_sha256/source_line/declaration）。
不涉及 required/states/roles/output/verification 分母改写。approved 类型化替代仅当确切状态冻结且当前运行确实缺失时应用；
格式错或已审核/不完整绑定禁止降级；任意理由不足为证。G0 SOURCE_ONLY 结构 PASS 但视觉 BLOCKED；G1 STRUCTURAL_ONLY PASS 不证明编译/到达/视觉/业务/stage1_complete。
保留完整视觉分母与历史尝试回执。

~~~sh
python3 <i2h-execute>/scripts/ui_inventory_resolution.py derive --project-root <absolute-project> --baseline spec/baseline/ui-delivery-approved.json --proof spec/execution/resolution-proof.json --out spec/execution/resolved-ui.json
python3 <i2h-plan>/scripts/ui_delivery.py validate --project-root <absolute-project> --inventory <absolute-project>/spec/execution/resolved-ui.json --receipt-only --out <absolute-project>/spec/execution/resolution-receipt.json
python3 <i2h-plan>/scripts/ui_delivery.py approve --project-root <absolute-project> --inventory <absolute-project>/spec/execution/resolved-ui.json --out <absolute-project>/spec/execution/resolved-ui.json --validation-receipt <absolute-project>/spec/execution/resolution-receipt.json --confirmation-ref <ref>
python3 <i2h-execute>/scripts/ui_delivery_inputs.py --project-root <absolute-project> --inventory <absolute-project>/spec/execution/resolved-ui.json
~~~

消费者默认选用同标准原生 index.inventory_source 路径与原始 SHA，严格审批链条与重放；格式错或陈旧闭合失败；显式选择器优先；无原生索引时保留历史基线路径语义，历史尝试不变。

## Execute：脚本先声明输入

使用 `ui_delivery_inputs.py --supplemental-capture-manifest <capture-plan-manifest.json>`
在主采集清单基础上导入补采。可重复传入多个清单。成功行逐态校验原图和控件树摘要，
同时核对主采集的源码摘要、设备、配置及 App。补采失败项继续显式记录，对应状态仍需真实证据。
已有采集内容与补拍冲突时应先审定采用哪份正式证据，补采入口不会覆盖旧帧。
重复导入会复核已落盘的取证。补采回执中的 state_count 包含本次导入和已验证复用的状态，
imported_state_count 只统计新导入，reused_states 列出原样保留的状态。

依赖隔离数据夹具的 `behavior` 状态可使用单独的 `spec/baseline/plans/ui-fixture-captures.json`。
其中 `schema_version` 为 1，`inventory_sha256` 绑定现有批准清单，`confirmation_ref` 记录本次取证的批准，
`bindings` 逐行给出 `page_id`、`state_id` 和状态目录内 `manifest.json` 的 `fixture_capture_sha256`。
批准后将绑定文件和原批准清单一并写入 Plan 标记。原 UI 清单摘要保持不变。补采可以使用该状态的
独立模拟器和配置，且必须使用相同 iOS 源码与 App。补采校验普通启动回执、原图、控件树和握手文件的
摘要，只接受批准的页和状态。已有帧按原规则保留。后续输入冻结和视觉基线读取会再次校验。

派发前只核对输入是否齐备时，运行 `ui_dispatch.py check-inputs --project-root . --unit-id <unit>`。
该命令校验源码、截图和控件树摘要并报告缺项，不创建尝试、对象或派发事件。
以 `--all-required` 替换 `--unit-id` 可一次返回所有必交单元的就绪数及缺项；需要证据细节时再按单元检查。
批量检查共用一次冻结输入读取。带续跑查询时也共用一次派发事件链校验。如果冻结输入、
批准清单或此次使用的事件链在检查期间变化，当前结果作废，重新读取后再决定续跑。
主线程确认此前转换器已退出后，可在同一只读命令追加 `--resume-pending`。
当 `pending_attempt` 返回最近一次已收口之后最早的等价 READY 派发，续用其中的
dispatch ID、原始 prompt 和 packet 摘要，并在真实转换完成后按原 ID 收口。
检查不重写已存在的输出、派发或归档。没有等价派发时，确定转换器接手后再用 `prepare` 创建尝试。

当缺口仅涉及带独立 iOS 源码锚点的 behavior 状态，且本单元已有完整的运行态截图和树时，
两条命令会报告 `conversion_scope=SOURCE_ONLY_BEHAVIOR_GAPS` 和 `source_only_states`。
只在已采用 Stage 1 缺口策略的项目中，主线程可将该 packet 交给 converter，按源实现未采集的行为。
未批准类型化 `input_alternatives` 时，准备状态和退出码仍为 BLOCKED/2；原样归档 G0，缺证条目仍阻断 G0/G1 与正式验收。
已批准的确切状态类型化替代按前述执行域解析路由复验，只有真正缺失的运行态可返回 SOURCE_ONLY/0；
它可进入 G1 结构验收，视觉仍为 BLOCKED，不能替代到达或 Stage 1 完整验收。
当缺少正式/预览状态、显式要求的证据或证据校验失败时，不给出此范围。

G1 对尚未完成的新尝试可沿用最近已完成的通过回执。新旧包除尝试号和派发 ID 外须完全一致，
且现有输出与转换报告须与原始归档逐字节一致。新尝试已归档失败、输入或输出已变时须重做；
G1 同时记录上述两个尝试 ID。

~~~sh
python3 <i2h-execute>/scripts/ui_delivery_inputs.py --project-root <project> --inventory <inventory>
python3 <i2h-execute>/scripts/validate_runtime_snapshots.py --project-root <project>
~~~

未解析的动态值继续读源码，不许由截图测量补成“源码值”。每个单元在 G0 交接前检查实际 SDK
枚举、兼容 API 和代码数值来源；这些检查不等于完整类型检查，也不证明布局保真。
脚本声明必需内容，Converter 禁改 packet/index、减少列表或自行声明零输入。
输入变更须回到准备步骤重新审阅，受影响单元 STALE，不能手写脚本批量重绑旧报告 hash。
冻结命令先同步标准 iOS 批量采集清单，逐状态合并运行证据到 `ui-snapshots`，保留已有静态事实。
只有 ui_dispatch.py reuse-metadata --dispatch-id <id> --packet <new-packet> 自动确认同内容后可复用。
已有新清单派发时，可运行 `ui_dispatch.py recovery-review --project-root <project>`。
输出按单元列出当前回执、上一份通过的历史 G0、派发字段差异、单元契约差异以及 ArkTS 字节是否变化。
以该结果确定审阅范围，审阅完成后仍经 `complete` 生成当前回执。

每个单元运行 `ui_dispatch.py prepare --project-root <project> --unit-id <id> --attempt <N>`，将 prompt_path
内容完整加入 task prompt。该段列出准确 component/page/output、packet digest 和 resolved absolute image paths。
这是图片发现的主要机制；--no-working-copies 可验证直接原图模式。持久引用仍相对 spec/，绝对路径只用于当前派发。
dispatch/events.jsonl 追加记录 previous_sha256；Converter 自行校验 packet digest，并报告 dispatch_id。
哈希链提供改写检测，不保证不可篡改；整链重写须与会话中已发出的 prompt digest 独立核对。

存在的 visual.json、fixture.json、usage、design tokens 会被选择并封入输入；
visual_node_keys/fixture_fields 用于组件聚焦，无 selector 时保留完整数据。
缺失 sidecar 不单独成为阻断项；实际需要的事实无法获得时，必须有来源替代或 BLOCKED。
source_refs 定点源码必须读取；动态分支不能仅靠 dump 推断。

runtime XML 全量由共享解析器读取，模型按独立 JSON 窗口消费。每片包含 input_id、JSON pointer 和完整值，
不能拼接字符切片；超大单值保留完整并标注超预算。默认窗口预算约 12k 文本 token
和最多 4 张 PNG，字符估算只是预估；记录实际累计 token、工具调用和时间。
先读每状态/区域的代表图片；新交互控件、可见性或树结构变化进入 required_expansion，重复/数据滚动帧按需读取。
所有原始帧仍保留引用，选择规则与结果可审查。宿主仅保留 reviewed 子区域之外的 shell/底栏，子组件消费自己的区域。
snapshot/runtime/<state_id>/frame-NNN.png 与 visual-inputs.md 是可重建便利缓存，记录原图 hash、裁剪变换与派生 hash；
不进入静态 facts-manifest，不覆盖静态 view.xml。prepare/B2 重跑须保留缓存且能由 refs 和批准的 unit 确定性重建。
parsed bounds_px/vp 保留屏幕坐标，bounds_local_px/vp 减去 ROI 原点；图像明确 screen/local 坐标，parent_id 不指向区域外节点。
MainActivity 是首次预算试点；源码额外读取的成本也计入累计成本。

## Converter 和 Closer

Converter 接受 unit_id、dispatch_id、ui_inputs_packet、packet_sha256；只写自己的 output 文件。
按 states 实现内容/切换，读取每个必需 PNG 并与该状态完整解析树交叉核对。
不选择最低编号 snapshot、不寻找固定截图文件名、不假定 density。
宿主负责外壳/slots/底栏，子内容负责 region 内 UI；真实业务门槛保持原语义。
共享接线、registry 登记与翻转由 closer 经现有 writeback 机制统一提交。

除原 markdown 报告外，产出 conversion-reports/<unit_id>.json：

~~~json
{
  "unit_id": "<冻结单元>",
  "dispatch_id": "<脚本派发 attempt>",
  "packet_sha256": "<派发 packet 哈希>",
  "image_observations": [{"state_id": "<已查看状态>", "comparison_id": "<已查看图片区域 ID>"}],
  "input_applications": [
    {"input_id": "<required_inputs 中的 ID>",
     "code_anchor": {"file": "<本单元输出文件>", "line": 12}}
  ],
  "state_implementations": [
    {"state_id": "<required state>", "symbol": "<实际实现符号>"}
  ]
}
~~~

Closer 核对所有单元和状态，填满必交付 slots，组装真实路由与受控 Preview。
临时批间 FWD-REF 可以存在，Stage 1 收口不能把必交付 UI 留给 Stage 3。
converted、正式到达、Preview 到达、业务接入、视觉验证分别记录。
输入应用记录只提供可追溯性，不能代替视觉结果。
code_anchor 和描述符号仅诊断 WARN，不能因空行/行号漂移修改原始报告来换取 PASS。
实际输出组件、非空 builder、host slots、输入/状态清单仍为严格结构检查。

每个 converter 写完原始代码/报告立即 `ui_dispatch.py complete --project-root <project> --dispatch-id <id>`。
它保留逐 attempt G0、packet/批准清单快照和派发 prompt；归档失败即 BLOCKED，成功前禁止 closer 修改该单元。
schema 2 同时保存输入字节的内容寻址副本及 preflight 报告；便利缓存重建不能覆盖已消费的 G0 证据。
全批结束 `stage1_acceptance.py --kind g0` 原子汇总首次归档；失败不得跳过。后续修复使用新 attempt，保留旧 G0。
首次归档按批准清单的 SHA-256 和最早已有真实 complete 事件的尝试选取。仅 prepare 的历史记录保留原状；早于首次归档时，G1 单独标示其 ID。汇总写入 `dispatch/g0/<sha256>.json`。清单获批更新后，旧清单的回执保留供追溯，当前清单无派发的单元保持 STALE。首份 `dispatch/g0.json` 同样保留为不可覆写历史；当前结构结果单独报告 `structural_status`，SOURCE_ONLY 不使视觉通过。

iOS Python 派发入口保存 `spec/execution/dispatch/<dispatch_id>/` 和 `dispatch/events.jsonl`。
准备结果会列出缺失的状态证据，converter 按 packet 给出的 `comparison_id` 报告图片观察。
G0 校验本单元原始输出、转换报告、输入和状态引用；宿主装配、编译、设备到达和视觉留给后续门禁。
已有 SDK 映射的字面量标签要求文字和符号同在一个可达布局。G0 和 Stage 5 UI 事实门禁
都会指出遗漏或错配，并附原 Swift 行。缺映射的标签进入符号选型复核。

## 验收和修复

项目 ledger 批准 Stage 1 按根因处置时，任何 G0/G1/编译/视觉失败先加载 [stage1-gate-policy.md](stage1-gate-policy.md)。产物缺陷必须修复；有证据的前置/环境/工具缺口经有界恢复后可带缺口继续，但 G0/G1 原始归档、验收分母和 stage1_complete 的真实判据不变。缺失归档或截图不能补造成成功。

~~~sh
python3 <i2h-execute>/scripts/ui_stage1_gate.py --project-root <project> --output-json <gate.json>
python3 <i2h-execute>/scripts/stage1_visual_scope.py --project-root <project> --out <scope.json>
~~~

安装后的正式命令位于 `.claude/skills/i2h-execute/scripts/ui_stage1_gate.py`。
历史名称 `ui_delivery_gate.py` 运行同一 Python 门禁。两者默认读取
`spec/baseline/ui-delivery-approved.json`，也可用 `--inventory` 或历史的 `--wiring-dir <清单文件>`
指定已批准清单。`--inputs-index` 校验冻结输入，`--wiring-contract` 追加明确的接线约束。
历史命令把已批准清单传给 `--wiring-contract` 时仍可运行。
`--output-json` 或 `--output` 指定报告路径，省略时写标准输出。

门禁按必交单元检查实际文件、声明的组件和可达 builder、宿主挂载及转换报告的逐状态记录。
批准清单未声明必需的宿主槽位时报告 `required_host_slot_missing`。已声明但目标宿主未挂载实际输出时
报告 `required_host_slot_unbound`，并列出宿主文件及 builder。
`wired_units` 只包含通过上述结构检查的单元。`PASS` 退出 0，schema-2 项目缺陷或缺输入为
`BLOCKED` 并退出 2。无法写入报告等工具执行错误写 `tool_error` 并退出 3。显式 schema-1 历史
wiring 清单保留原退出 0/1 契约。结构结果固定为 `STRUCTURAL_ONLY`，实际到达、视觉及 G0/G1
原始归档继续由现有验收流程核对。

import 统计只表示依赖。完整交付要求 100% required units/states 有实现；
正式路径与 Preview 各自按批准清单达到 100%，Preview 不计入正式业务完成。

visual scope 使用明确的 pair_id/page_id/state_id，每项直接引用 iOS PNG/XML。
未到达或缺基线的状态保留在分母并报告 BLOCKED，不按 wiring 成功项缩减 scope。
通过目标应用的原生 UITest 采集当前签名 HAP 的 HarmonyOS PNG/dump，复用状态就绪时的控件树。
每个状态逐帧/区域 comparison 记录 comparison_id、ios_png_sha256、ios_region_px、harmony_png、harmony_xml 和 verdict；
一个原图可覆盖多个区域，不能用一次宿主底栏比较代替子内容比较。
文件引用都是相对 spec/ 的 {path,sha256}。

arrival_receipt 有 pair_id、arrival_mode、status=PASS、build_receipt、install_receipt。
原生采集器须额外记录 capture_run_id、device_id、observed_page_id、observed_state_id、
landing_evidence 文件引用以及带图和树 SHA-256 的 frames。只有检查到业务状态后才写到达回执。
判图前先运行 `stage1_visual_report.py capture-index --project-root <project> --scope <scope.json>
--arrival <spec 相对路径> --out <capture-index.json>`，多份回执重复传 `--arrival`。
检查范围、源码、HAP、设备、源图、目标图和树摘要，逐状态输出缺项。READY 后使用同一份索引组装判图报告。
已有历史判图时，在派发前用 [review-worklist](ios-visual-acceptance.md#视觉返修的判图清单)
复核可沿用的判定。遇到单对超时或平台归属校验失败时，将原判图回执通过
`--review-receipt` 传入同一命令，并按 `labeled_recheck` 的状态处理定向补判。
正式组装仍覆盖完整批准范围。

Plan 为共享自绘组件选定目标实现时，可在批准清单保存 `drawing_component_bindings`。
每项的 `definition` 沿用 `drawing_component_calls` 中的 `file` 和 `line`；
`output` 指定目标 `.ets` 文件和它导出的 ArkUI `struct` 符号。Stage 5 的
`ui_obligation_gate.py` 从各必交宿主的批准入口检查可达调用和实际导入文件。
Plan 校验会列出跨页但尚未绑定的定义，拒绝重复、无来源或越界绑定。
派发只携带当前单元使用的绑定，页面源码按该目标接线。
页面调用改指同名私有副本，或只留下了未被入口调用的 builder，都会报出对应宿主。
实际尺寸、变体、可访问性和视觉差异继续由原有逐态验收确认。
`i2h-verify/scripts/uitest_checkpoint.py` 的 `capture_checkpoint` 在正式截图前后均检查目标应用前台和同一业务状态。
两次检查通过才调用 `record_arrival(name, matched_tree)`，其中 `matched_tree` 是截图后的原始树。
在回调中用 `write_visual_arrival` 绑定批准 pair、原图、该树及实际构建和安装回执。
只对已配置业务状态断言的检查点注册该回调。
构建/安装回执都有 status=PASS、scope_sha256、source_sha256、hap_sha256；必须来自实际操作。
Stage 1 派发 hmos-builder 时传 STAGE_HINT=stage-1-ui-delivery、MAX_ITER=1，
底层追加 --build-only。每次只构建一次，修代码/重建由外层统一计次，
不能在一次回执内隐藏 20 轮修复。需要安装时使用实际签名包。
source_sha256 统一使用 stage1_contract.source_digest(project)，覆盖 AppScope、多模块及构建输入；
build/install 必须对应相同 HAP，禁止拿旧包截图。

比较报告有 scope_sha256 和完整 pairs：
每项 pair_id、verdict=PASS/FAIL/BLOCKED、arrival_mode、arrival_receipt、comparisons；
FAIL 带 severity，BLOCKED 附 reason。失败比较也保留图片与到达收据。
不通过主 Agent 图片读取回执证明保真，交由视觉比较及完整覆盖表判断。
报告不手写：采集代理写采集索引、判图代理写判图结果（只写相对 spec/ 的路径和看到的结论），
由脚本补齐哈希、源图绑定和引用，并列出缺图、缺判图、空 dump 等需重采项：

~~~sh
python3 <i2h-execute>/scripts/stage1_visual_report.py assemble --project-root <project> --scope <scope.json> \
  --capture <capture-index.json> --judgements <judge-*.json> --out <comparison-report.json>
python3 <i2h-execute>/scripts/stage1_acceptance.py --project-root <project> \
  --scope <scope.json> --report <comparison-report.json> --kind visual
~~~

采集索引 `{"pairs":[{"pair_id","arrival_receipt","frames":[{"comparison_id","harmony_png","harmony_xml","harmony_region_px","harmony_density"}]}`
（到不了的写 `arrival_failure:{evidence,install_receipt,summary}`，环境阻断写 `blocked:{code,reason,evidence}`）；
判图结果 `{"comparisons":[{"comparison_id","verdict","severity","appearance_report","relationship_report","notes"}]}`。
两份判定工件必须分别绑定同一 comparison ID。`appearance_report` 绑定 `ios_png_sha256` 和 `harmony_png_sha256`。
`relationship_report` 绑定 `ios_ui_sha256` 和 `harmony_ui_sha256`。PASS 需要两份工件都提供 `verdict=PASS`。

布局返修时可单独运行 `ui_relationships.py --audit-viewport`。该诊断列出源端选定区域内
唯一且完整可见的锚点在目标树中缺失或超出视口的情况。唯一匹配的交互控件若可见矩形
被原始矩形包含且任一边裁去超过 1 个归一化 iOS 点，则同时报告两个矩形及
`target_control_clipped`。同名候选需要人工结合截图消歧。
正式 `relationship_report` 仍使用常规命令输出，由归档门禁重算。

G0 是 converter 的强制交接门；静态装配与修复后用 --kind g1 归档。两份不可覆写。
G1 验证每个必交单元首次归档仍可读，当前转换回执与最近的通过归档一致，当前组件及宿主槽位通过结构门。
归档按实际源码和回执内容寻址，源码修复保留先前的 G1。完整运行时计划在批准前填写宿主文件、builder 和子组件符号。
Stage 1 验证包 compile 最多两次 repair。BLOCKED 的环境恢复不消耗源码修复次数，但必须计入根因处置脚本的有界恢复预算，不能无限重试；
恢复时沿用已有预算，不能通过重建任务重置已经做过的修复。
archive 自动分配 round-0/1/2，记录首次结果，不能改任务 ID 或 candidate 名重置预算。

编译完成后用 `stage1_acceptance.py --kind compile --scope <scope.json> --build-receipt <spec 内构建回执>` 登记。
也可用 `--report` 传入 `{status,scope_sha256,build_receipt}`，其中 build_receipt 是相对 spec 的文件引用。
真实编译失败报告使用 `status=FAIL`，带 `source_sha256`、`exit_code`、`reason` 和 `evidence` 日志引用。
环境阻断报告使用 `status=BLOCKED` 并保留同样的源与诊断引用，单独计恢复次数。

### 视觉修复：只保接线和关键显示，不追细节

目标是接线通、页面能跳转、关键内容显示，不在 Stage 1 追 UI 细节。判图对每处差异定一档：

| 档 | 例子 | 处理 |
|---|---|---|
| 关键 critical | 白屏/空白页、缺组件或正文、内容严重裁切或被遮挡、点击/取消/滚动/跳转失效 | 必须修；App 自身导致到不了目标状态记 FAIL（`arrival_failure`），不记 BLOCKED |
| 普通 normal | 间距、尺寸、颜色、图标、对齐等外观差异 | 只在第 1 轮修一次 |
| 只记录 | 系统状态栏、手势条、字体抗锯齿、轻微字重 | 写进 notes，不算 FAIL |

轮次：round-0 全量采集。第 1 轮修 critical + normal；第 2 轮只修 critical。修过一轮后剩下的 normal
记入 accepted_differences，不再修，视觉记 PASS；critical 两轮修完仍在则终态 FAIL，按产物缺陷阻断。
`stage1_acceptance.py --kind next` 给出本轮 repair_scope。

复采：换包、换设备或批准范围变化后，为当前安装建立新原生采集索引。同一安装的局部补采可使用
`capture-index --base-capture`，由工具复核保留的图、树和回执。判图沿用走本轮索引的 `review-worklist`。
结束前在最终 HAP 上跑一次整包冒烟（冷启动、各 Tab、每个正式页面能到达），用
`--kind smoke` 登记，cases 覆盖全部正式 page_id；冒烟通过才算 Stage 1 完成。
冒烟输入使用 `--report`，包含 `scope_sha256`、同一套 `build_receipt` 和 `install_receipt`、
`cold_start` 及 `cases`。各 case 使用 `{page_id,arrived:true,evidence}`，evidence 引用真实到达回执。
cold_start 引用绑定本轮源、scope、HAP、设备和 capture_run_id 的 PASS 回执，并引用冷启动命令日志。
所有正式页面和已批准的 Tab 状态必须在同次安装、同一采集轮次观察到。Python 命令只登记与复验实际采集结果。

最终运行 `stage1_acceptance.py --kind summary --project-root <project> --scope <scope.json>`。
结构 PASS 只标 STRUCTURAL_ONLY；缺 G0/构建/比较不得报 Stage 1 完成。assessment_complete 仅表示全状态
都有 PASS/FAIL/BLOCKED；stage1_complete 还要求结构、当前源码构建、视觉 PASS（可带 accepted_differences）和必要时的冒烟 PASS。
源代码变化使旧比较 STALE；正式到达和 Preview 分别保留，Preview 不等于正式业务接入。
Python 汇总会重验当前 G1 原档、最新视觉归档及其源、HAP 和双端证据，可用 `--out` 保存 JSON。
旧版同一 scope 有多份无顺序索引的视觉归档时，通过 `--report` 选定已归档的比较报告。
有实际构建但暂无完整视觉结果时，可用 `--build-receipt <spec 内路径>` 核实当前构建，未采或未判的状态保留 NOT_RUN。
当前 iOS Python 汇总以同次安装的全量新采结果判定完成。达到原生视觉修复轮次后，普通残余差异同时写进
`accepted_differences` 和原始失败明细，后续严格视觉验收仍可消费原始 `raw_visual` 和逐状态结果。
跨包沿用仍需依赖文件核验，独立冒烟通过不会让未经核验的沿用比较进入完成判定。

### S1-V 编排

- 采集：一个代理独占设备逐项采集，同时派两个判图代理随采随判（按已采到的 pair 分批），不等全部截图结束。
- 修复：按问题单的文件归属分组并行，写集互不相交；公共布局/宿主/路由只给一个写入者。
- 公共布局改完：先在设备上试点击、取消、滚动三个动作，通过再大批采集（遮挡层这类问题在这一步就能发现）。
- 并发按宿主实际可用槽位补满；同一台设备上的操作仍然串行。
新契约要求 ui_relationships.py 对双端 dump 的文字/角色/语义上下文匹配后检查靠边、顺序、重叠、间距，
并有独立外观复核报告；模糊匹配保持 UNRESOLVED。缺实际步骤是 NOT_RUN，只有已记录的前置阻断
才可写 BLOCKED。最终 writeback 必带 stage1.phase=assembled/assessed/complete；脚本先验证再写 brief。

从已安装的 CC iOS skill 运行双端关系检查。作用域读取 iOS schema-2 的对应帧，源树使用 XCUITest 的
`debug_description` 或带 viewport 的结构化节点，鸿蒙树使用 UI Test 的原生 `dumpLayout` JSON。
坐标按两端实际 viewport 归一到 iOS 点；单独记录关系差异、未匹配节点和输入摘要。状态栏和系统键盘
由独立外观及状态到达检查取证。归档时按同一规则复算树并比对关系报告。关系 PASS 仍须独立外观 PASS。

~~~sh
python3 .claude/skills/i2h-execute/scripts/ui_relationships.py --project-root . \
  --scope spec/execution/stage1-visual/scope.json --comparison-id <id> \
  --harmony-tree spec/execution/stage1-visual/<run>/target.json \
  --out spec/execution/stage1-visual/<run>/relationship.json
~~~
`ui_consumption.py --project-root <project> --out <diagnostics.json>` 按 unit/state/region 输出消费声明，
共享原图在全局去重。声明仅诊断，不解析 transcript 当作确定的质量门，也不把 host 消费计成 child 消费。
后续 i2h-verify 的完整业务验收独立进行，不能提前写页面 verified。

## 验证方式

通用 A/B 在两个独立空项目中固定 spec、plan、源码、模型、证据、交付范围和设备条件；两组 XML 都完整可读。
当前局部 pilot 使用 1019 冻结 spec/plan/evidence 的副本和指定五单元原始 G0 控制，不改旧项目；
具体边界见 layout-fidelity.md。六行月新证据单列 new-only，增加截图数量的收益另做实验。

完整模式的 typed build/install、device/run/landing 回执字段以 ui-integration-1030.md 为准；不复用旧模式的 receipt_ok 或单一安装成功标记。
