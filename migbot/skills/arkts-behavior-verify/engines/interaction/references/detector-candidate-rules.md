<!-- when: 解释对应 Detector finding 或维护结构规则时读取 -->
<!-- topics: detector candidates, event consumers, action variants, scope boundaries -->

# Detector 候选解释

候选规则目录与默认启用范围不同；实际 findings 由当前 Detector profile 决定。
本文不新增送审范围或修改默认 profile。

Detector 除点击空 handler/占位/静默失败外，还可为具体点击 contract 提供通用结构候选：路由参数类型或类身份不匹配、带值 `navigation.pop(result)` 没有静态可见的调用方结果消费者、确认回调发生在 dismiss/close 之后、用户导出只写入私有沙箱、外部能力返回固定空结果。Android oracle 应优先建立 XML string→view id→listener/command 与 action id→dispatch branch 的结构链接；数据驱动菜单把可见 `action_variants` 送入 Review。对 reusable `@Event` 转发点击，必须沿同文件有界 helper 链识别最终 `@Event`，并解析所有具体组件实例：未找到实例才标 inactive；实例存在但事件参数省略时，先读取 `@Event` 默认实现：默认空体才记录 `EVENT_BINDING_MISSING`，占位默认行为记录 `EVENT_BINDING_NOOP`；有真实默认命令则沿默认调用链审查，不能要求父组件重复绑定。保留同一实例上的每个不同事件及其状态分支，并把父实例位置送入 Review。**即使事件参数存在，也要检查每个具体 consumer 的 `binding`/`reachable_source` 函数体；若实际调用 `unavailable*`、`unsupported*`、`notImplemented`、`noOp`、空体或无领域效果的 placeholder，记录 `EVENT_BINDING_NOOP`；若实例化调用把 action-gate 类型的 `@Param`（如 `available/enabled/interactive/click/action/allow/can/support`）显式设为 `false`，记录 `EVENT_BINDING_DISABLED` 并把父调用点作为 edit target。两者都必须送入 Review，不能把“事件已绑定”“函数被调用”或组件内部 `enabled` 表达式当作效果成立。** `UNCONSUMED_ROUTE_RESULT` 也只是结构候选：若页面已在 pop 前独立完成持久化/刷新，Review 可判 `NO_DEFECT`。跨文件调用最多跟踪三层，只跟踪同文件、全仓唯一实现，或由 `ClassName.method()` / receiver 的唯一显式类型与同名 ArkTS 文件确定的实现；这些候选仍必须经过 Android/ArkTS AI 审计，禁止直接转成 `FIX_REQUIRED`。若 `adapter_profile.status=ADAPTER_UNRECOGNIZED`，目标域必须进入 Review，不得因缺少已知 API 而转成 `NO_DEFECT`。

通用结构 Detector 还检查：typed action 数据源与 dispatcher 分支差集、对象构造参数传入的字面量禁用、恒定默认状态造成的不可达 guard、同一状态 gate 在选择态与页面态混用、逐 push site 的 route-result 消费、重复 pop/back、Android 持久化而 ArkTS 仅局部状态、写入后无失效/回读、Android 确认门或导航后置条件缺失、错误状态替代真实命令、弹窗状态变化无 owner invalidation、持久化状态进入页未加载。所有 finding 必须带 `signal_level=HIGH_SIGNAL/CONDITIONAL_RISK/STRUCTURAL_ONLY`；层级只决定 Review 顺序，不删候选、不确认缺陷，也不授权修复。共享 enum dispatcher 的完成性检查必须按当前 binding 的具体 variant 切片，不能用 sibling branch 的刷新/导航证明当前 action 已闭合。

## UI 终端与数据前置态

默认 profile 增加两类候选；它们不依赖支付、播放器等业务名称，也不修改设置候选策略：

- `OVERWRITTEN_SHEET_BINDING`（HIGH_SIGNAL）：同一组件连续属性链多次调用 `bindSheet`，且点击的同组件可达 helper 写入前一个、与最后绑定不同的显示状态。按属性链定位同宿主，分别绑定在两个组件、嵌套 builder 内的独立绑定、注释字符串以及仅打开最后绑定的点击均不因此送审。证据含点击与每个状态/builder/绑定位置。Review 需核对实际宿主和 SDK 语义；修复可把两张 Sheet 分配给现有独立稳定节点，并保持关闭回写与确认后继动作，不能用删除协议/确认门使候选消失。
- `SILENT_NULL_SELECTION_GUARD`（CONDITIONAL_RISK）：真实 `.onClick` 可达同组件 helper，先调用无参 nullable 读取选择器，然后遇到 null 仅 `return`，后面才执行状态/命令，控件没有与该选择器一致的可用性约束。仅接受可见的只读 `return condition ? value : null` 选择器；已有提示/重试、嵌套回调内部 guard、返回业务值的函数及未知服务返回值不据此提名。Review 必须区分空列表、加载中、失败、无选择与有选择；Android 同样静默时只能说明同源行为，不能单凭候选判迁移缺陷。只有用户已授权行为改进或双端 oracle 证明缺陷时才修复，并保留正常下单/提交的前置条件。

`STATE_CHANGE` 仅证明变量变化，不能证明对应弹层已出现。用户明确授权的真机验收应先证实数据前置态，再检查打开、取消后重开、确认与后续弹窗/请求；缺少后端时允许独立的契约 fixture 验证 UI，但必须标明 fixture 范围，不能据此声称真实支付或业务成功。
