# UI Migration Pitfalls — 静默映射陷阱

编译通过但运行时异常的 Android → ArkUI 映射陷阱。
a2h-activity-converter 在 Phase 2 加载此文件，转换时必须逐条检查；a2h-execute Stage 3 slice worker 改/加任何 UI（含弹窗、浮层、层叠布局）前同样必读。

## CRITICAL — 必须处理，否则页面不可用

### P-01: SideBarContainer 子组件顺序反转
- **Android**: DrawerLayout 第一个子组件 = 主内容，第二个 = 侧边栏（通过 layout_gravity 标识）
- **ArkUI**: SideBarContainer 第一个子组件 = 侧边栏，第二个 = 主内容
- **错误表现**: 侧边栏和主内容位置互换，侧边栏占据全屏，主内容被挤到侧边
- **修复**: 转换时交换子组件顺序

### P-02: Tabs + Navigation 全屏遮盖
- **Android**: TabLayout + ViewPager 可嵌套在任意布局中
- **ArkUI**: Tabs 放在 Navigation 内部时，NavDestination 会覆盖整个 Navigation 区域（含 Tabs）
- **错误表现**: 切换到子页面后 Tab 栏消失
- **修复**: 源端要求跨子页面保留的 Tab 栏/播放条，应由 Navigation 外的宿主区域承载；改为 Row 但仍放在 Navigation 内并不能解决遮盖。仅属当前页的元素不外提；常驻布局与可见状态接线见 [V2 宿主示例 §3](../../arkts-navigation-builder/references/v2-advanced-nav-patterns.md#3-fullplayer-隐藏-tabv2--用-appstoragev2connect-替代-storagelink)。

### P-03: CoordinatorLayout 滚动协调丢失
- **Android**: CoordinatorLayout + AppBarLayout + CollapsingToolbarLayout = 联动折叠
- **ArkUI**: 无直接等价物，Scroll + Column 不会自动联动
- **错误表现**: AppBar 不随滚动折叠，嵌套滚动可能冲突
- **修复**: 使用 Scroll 的 onScroll 回调手动计算 AppBar 高度和透明度

### P-17: 几何 ≠ 命中测试（层叠/浮层：尺寸位置 与 是否挡触摸 解耦，各用专属 API）
- **不变量**: ArkUI 中「尺寸/位置/层叠顺序」与「是否接收·拦截触摸」正交且各有专属属性。源端（Compose Box.align / FrameLayout layout_gravity）二者常被"盒子大小"耦合，迁移时**必须拆开**，否则一改俱错。
- **两条独立决策**:
  - **几何 = 源布局里它视觉覆盖的区域**：占满→`'100%'`，占半幅→`'50%'`/对应 weight，贴边小块→真实 wxh。**不得为"别挡触摸"而缩小，也不得为"贴边"而放大到全屏。**
  - **触摸 = hitTestBehavior（或 onClick 落位）**：纯展示、点击交底层→上层 `.hitTestBehavior(HitTestMode.Transparent)`；上层自身响应→给上层 onClick；独占（挡住下层，自身或子组件仍需交互，如源端 `setOnClickListener(null)` / `clickable` / `onTouch` 返回 true 的面板、对话框容器）→保持默认 `HitTestMode.Default`（自身及子节点响应，阻塞下层兄弟节点）。`HitTestMode.Block` 会同时阻塞子节点和祖先节点，包含可交互子组件的容器不能用。
- **双向错误表现**: 盒子太大且缺 hitTestBehavior→下层点不动/滚不动（"内容缺失/点不动"）；盒子太小→盖不住对应区域、底层透出（"选中态错位/两态混叠/背景缺一截"）。
- **修复**: 先按源布局把几何设成它该覆盖的区域，再按意图设 hitTestBehavior——二者分别表达，互不迁就。
- **自检**: 任一 Stack 上层子节点（背景/选中态/贴边浮层），核对两点：① 其 w/h 是否等于源布局该层覆盖区域（不是 wrap_content 也不是误铺全屏）；② 是否按"该不该挡触摸"显式设了 hitTestBehavior。grep 起点 `width\('100%'\).*height\('100%'\)` 仅查"过大"一类，"过小"一类需对源布局核对。

### P-30: Stack 子组件用 `.align()` 定位——不生效
- **Android**: FrameLayout `layout_gravity` / ConstraintLayout 约束让每个子 View 各自贴顶、贴底或居中
- **ArkUI**: Stack 里子组件的位置只由 Stack 的 `alignContent`（默认 `Center`）决定。子组件自己的 `.align()` 只排它**内部的内容**（且只对 Stack / Button / Text / TextInput 等少数组件生效），不会把子组件挪到 Stack 的顶部或底部
- **错误表现**: 本该贴顶的标题、贴底的按钮行都挤到 Stack 中心（或 alignContent 那个角），压在主视觉上（ds1030 引导页：按钮行压在气泡上；进度条贴左边，而安卓是水平居中）
- **修复**: 子组件位置各不相同时不要靠 Stack 定位。改用 `Column` + `Blank()` / `margin` 排上中下；或者让子组件撑满 Stack（`.width('100%').height('100%')`），再用它自己的 `justifyContent` / `alignItems` 排内容。和 alignContent 相同的 `.align()` 是冗余写法，删掉即可
- **自检**: Stack 的每个直接子组件写了 `.align(Alignment.X)`，X 与 alignContent 不同，且该方向上不是 `'100%'` 尺寸 → 必改

### P-31: 自绘弹窗/浮层常驻挂载——隐藏时仍挡住整页触摸
- **Android**: Dialog / PopupWindow 关掉就从窗口移除；`visibility=gone` 的浮层不占位、不拦截触摸
- **ArkUI**: 页面里自绘的弹窗、进度浮层（Stack 上层 + 全屏蒙层）只要还在 build 里，哪怕内容透明，根节点照样占满全屏，并按默认 `HitTestMode.Default` 拦截下层触摸
- **错误表现**: 页面看着正常，但整页点不动、返回键无效，用户被困（ds1030 大纲页：`OutlineProgressDialog` 无条件挂载，内层根 `Stack` 高 100%；hilog 报 `Touch test result is empty`）
- **修复**: 宿主用 `if (this.xxxVisible) { XxxDialog(...) }` 条件挂载；组件内部自控显隐的，隐藏态根节点必须设 `.visibility(Visibility.None)` 或 `.hitTestBehavior(HitTestMode.None)`。与 P-17 的分工：P-17 管**显示态**的几何与命中，本条管**隐藏态**不得占位
- **自检**: 每个 *Dialog / *Overlay / *Mask / *Loading / *Progress 组件实例，确认在宿主里被 `if (...)` 包住；没包的，确认组件根节点在隐藏态是 None

### P-32: 自绘弹窗开着时按返回键没有先关弹窗——直接退页或退出应用
- **Android**: Dialog 默认 cancelable：返回键先关弹窗，Activity 的 `onBackPressed` 收不到这一次返回（`setCancelable(false)` 的弹窗才不关）
- **ArkUI**: `if` 挂载的自绘弹窗只是页面里的普通组件，返回键直接交给 `NavDestination.onBackPressed` / `@Entry onBackPress`。只有系统弹窗（`CustomDialogController` / `openCustomDialog`）会自己处理返回
- **错误表现**: 弹窗开着按返回，宿主页直接退出；首页有"再按一次退出"时会直接退出应用（ds1030：首页按过一次返回后，到"我的"打开联系我们弹窗，再按返回，应用退出）
- **修复**: 宿主返回回调的第一步：检查本页所有弹窗的可见标志，有可见的就关掉并 `return true`。弹窗嵌在 Tab 或子组件里时，把可见标志或关闭方法通过共享 VM / 回调交给宿主页，由宿主的返回回调调用。源端 `setCancelable(false)` 的弹窗照旧拦住返回、不关
- **容易漏的一半**: 同一个组件既能被 push 成独立页、又被嵌进 Tab 当内容时，它自己 `NavDestination` 上的 `.onBackPressed` **只在独立页形态生效**；嵌在 Tab 里时返回键交给宿主页，组件里写的处理不会被调用（gpt1030_2：「我的」tab 的客服弹窗按返回不关）。嵌入形态必须由宿主处理
- **自检**: 每处 `if (this.xxx) { XxxDialog(...) }`，确认**实际接收返回键的那个宿主**的 `onBackPressed` / `onBackPress` 读到了 `xxx`（嵌入 Tab 的组件，看宿主页而不是组件自己）

### P-33: 安卓「每次回到页面」的回调映射成 `aboutToAppear`——只执行一次
- **Android**: `onResume` / `onStart` / `onRestart` 每次页面回到前台都会执行（从下一页返回、从登录页回来、App 回前台）
- **ArkUI**: `aboutToAppear` 只在组件**创建时执行一次**；从下一个页面 pop 回来、或 Tab 切回来时组件没有重建，它不会再执行。对应「每次可见」的回调是：路由页 `NavDestination.onShown`、`@Entry` 页 `onPageShow`、嵌入 Tab 的内容组件由宿主在 `onShown` / Tab `onChange` 里转发
- **错误表现**: 依赖「回来时刷新/复位」的逻辑失效。典型：防重复点击的锁在 `aboutToAppear` 里复位，用户点「立即生成」→ 跳登录页 → 登录回来，锁一直没复位，按钮永远无反应（gpt1030_2 `QuotaGate.entering`）；回来后列表、余额、登录态不刷新
- **修复**: 安卓 `onResume` 里的逻辑放进 `onShown`（或宿主转发的可见回调）；防重入标志在**每一条离开路径**都复位——跳转出去前、`finally` 里、或下次可见时，而不是只在创建时复位
- **自检**: grep `aboutToAppear` 里的「复位 / 刷新 / reload / reset」调用，对照安卓同名逻辑是不是在 `onResume`；grep 所有 `= true` 的防重入标志，确认每条 return / 跳转路径都有对应复位

### P-34: 根页面「再按一次退出」用 `pop()` 弹掉最后一页——留下空白页
- **Android**: 首页第二次按返回调用 `finish()`，Activity 结束，App 退到后台/桌面
- **ArkUI**: `Navigation` 的栈底下面是导航根（通常是空内容）。在首页的 `onBackPressed` 里调 `navPathStack.pop()` 只是把首页弹掉，露出一个**空白的导航根**，再按一次返回才真正退出
- **错误表现**: 首页按两次返回出现整屏白屏，第三次才退出（gpt1030_2）
- **修复**: 栈底页面要退出时结束 Ability：`(this.getUIContext().getHostContext() as common.UIAbilityContext).terminateSelf()`。不要 `pop()` 掉最后一个页面；在 `NavDestination.onBackPressed` 里 `return false` 交给系统也一样会把这一页弹掉
- **自检**: grep 首页/根页 `onBackPressed` 里的 `pop()`，确认它弹的不是栈底

### P-20: 百分比尺寸子节点（width/height('100%')）在 wrap-content / 无定高父级里向上解析 → 撑满
- **Android/Compose**: 背景层 `fillMaxSize()` 靠父约束定尺寸，与内容同大
- **ArkUI**: 子节点的 `width/height('100%')` 解析到**最近一个有确定尺寸的祖先**，不是"父内容大小"。父级若是 wrap-content（由内容定大小）或在 List 里无定高，该子层就撑满整片可用空间。常见两类：① **列表行**背景层铺满视口、行被撑成整屏高；② **chip/徽标/卡片**等本应由文字定大小的组件，被一个当"背景/描边"的 `100%` 子层撑成大色块（该层被状态门控移除后又恢复 → "默认态大、操作后变正常"）
- **错误表现**: 列表每行异常高/背景铺满；或标签、徽标在默认态是大色块、交互后恢复
- **修复**: 不要用 `100%` 子层去填父高/宽。背景/描边**画在容器自身**（`.linearGradient()`/`.backgroundColor()`/`.border()`），由内容定大小，露描边环用 `.padding(1)`；确需测量再定高的用 `onAreaChange`
- **grep 自检**: `grep -rnE "width\('100%'\)|height\('100%'\)" src/components`，命中后核查父级是否 wrap-content / 无定高

### P-22: 横向滚动容器（List/Scroll/Grid, Axis.Horizontal）缺显式定轴尺寸
- **Android/Compose**: LazyRow / 横向滚动高度由子项固有高度决定，自动 wrap 成内容高
- **ArkUI**: 滚动容器**不 wrap 内容**。横向时不显式 `.height()` → 有剩余空间就**撑满父级**（连带里面 `width('100%')` 的背景/渐变一起拉伸成大色块）、被同级抢空间就**塌成 0**。纵向滚动容器缺 `.width()` 同理
- **错误表现**: 横向卡片行/标签条变成大色块顶掉其它内容，或整条不可见
- **修复**: 显式 `.height(= 最高子项高 + 上下 margin)`；纵向同理显式 `.width()`
- **同根性能坑**: Scroll 嵌套 List 时内层 List 不设宽高 → **子项全部一次性加载，LazyForEach 懒加载失效**（官方最佳实践明文）——同样是"滚动容器尺寸不由内容定"的另一面；嵌套场景必须给内层 List 定高 / `layoutWeight`
- **grep 自检**: `grep -rnE "Axis.Horizontal|Scroll\(|Grid\(" src/`，逐处确认链式属性含 `.height(<数字>)`（非 `'100%'`、非缺失）

### P-29: 路由目的地根形状——NavDestination 双层嵌套 / 根随 embedded 切换
- **Android**: 同一 Fragment 可经事务装入宿主容器，也可被 ViewPager/Tab 内嵌，同一个类两用
- **ArkUI**: 每个路由分支必须**恰好产生一个** `NavDestination`——由 pageMap 分支内联提供，或由页面组件的 `build()` 根提供，二者不能同时提供，也不能都没有。`pageMap` 外层再包一层 `NavDestination` 而页面自身也以 `NavDestination` 为根 → 内层 `onReady` 拿到的 `pathInfo.param` 为 `undefined`（参数实际仍在 NavPathStack 里），内层 `onBackPressed` / `onShown` 等生命周期不可靠；页面 `build()` 根写成 `if (this.embedded) { 内容 } else { NavDestination() {...} }` → 被 push 时白屏
- **错误表现**: 进入详情页提示"参数无效"/空白页；tab 与独立页共用一个组件时独立页读不到参数或显示 tab 模式
- **修复**: 按 Android 加载关系决定形态（见 [v2-advanced-nav-patterns §4a](../../arkts-navigation-builder/references/v2-advanced-nav-patterns.md)）：事务 / NavHost / 返回栈 / 宿主内容容器装载 → 宿主内容区 `Navigation` 中的独立页面；ViewPager / TabContent / 静态内嵌 → 普通内容组件；同一内嵌 Fragment 还要独立打开 → 拆 `XxxContent` + 薄 `XxxPage`。**不要**用外包 `NavDestination` 修白屏，**不要**用 `getParamByName()` 兜底取参
- **机器闸**: `verify_arkui_safety.py` 的 `NAV_NESTED_DESTINATION`（双层）/ `NAV_CONDITIONAL_ROOT`（根随条件切换）均为 FAIL

## HIGH — 功能缺失或数据不更新

### P-04: NavDestination 参数时序
- **Android**: Intent extras 在 onCreate/onResume 中可用
- **ArkUI**: NavDestination 的 pathInfo.param 仅在 onReady() 中可用，aboutToAppear() 中为 undefined
- **错误表现**: 页面参数始终为空，页面显示默认状态
- **修复**: 参数读取放在 onReady() 回调中，不放在 aboutToAppear()

### P-05: ForEach / LazyForEach key 不完整导致 UI 不刷新
- **Android**: RecyclerView.Adapter notifyItemChanged(position) 精准更新
- **ArkUI（ForEach）**: keyGenerator 只含 id 时，属性变更（如 playState）不触发刷新
- **ArkUI（LazyForEach + V2 @Param）**: keyGenerator 返回 `item.id`，但 VM 用「同 id、新值」重建对象（如 `new Line({ item, count: n })`，`item.id` 不变）→ 框架按 key 判定为同一项、**复用旧子组件、不重派 `@Param`** → 子组件停在旧值（如数量加减后 count 不变）
- **错误表现**: 数据变了但 UI 不更新；列表项的 count / 选中态 / playState 停在旧值
- **修复**: ① key 必须含所有影响显示的可变字段：`item.id + '_' + item.count`（ForEach 与 LazyForEach 同理）；② 或保持对象引用稳定、用 `@ObservedV2` + `@Trace` 原地改字段（而非整体 `new`），让 `@Param` 沿响应链派发

### P-24: 抽可复用渲染时，把**动态**值当 @Builder【值参】传 → 定格首帧不刷新
- **适用范围**: 只约束「值会随 `@Local`/`@Trace` 变化、且**期望 UI 跟着刷新**」的**动态**数据。**静态/不变的值（含静态标签文字、写死的常量）走 @Builder 值参完全正常、不受本条约束**——不要为静态内容改写或拆组件。典型触发 = 同一布局里**内联重复**几个「标签 + 实时数值」块（各绑 ViewModel 实时字段、非 `<include>`/非 RecyclerView item），转换器为去重抽可复用渲染方式时。
- **陷阱**: 抽 `@Builder` 时把**动态数值当值参**传（`@Builder statRow(label, value: number)` + `this.statRow('余额', this.balance.toString())`）→ `@Builder` **默认按值传递**、传入是**调用时刻的快照**；`@Local`/`@Trace` 之后再变，builder 内那段 UI **不刷新**、定格首帧。**最隐蔽**：数据源即使是 `@ObservedV2 + @Trace`，一旦取出它的**属性值**（`item.value` 这个 number）作值参传，传的仍是 number 快照、不是可观测对象，照样不刷新。
- **错误表现**: 编译通过、首帧数值正确，但运行时数值**永不变**（定时器/网络/推送更新了状态、界面纹丝不动）。
- **修复（从轻到重，别过度拆组件）**:
  - ① **首选、最轻**：`@Builder` **内直读** `this.` 上被订阅的状态（`this.balance`），动态值不走参数、静态标签仍可走值参。**@Builder 本身没问题**，改的只是「动态值别当参数」。
  - ② **仅当各块确有共享结构、值得独立组件时**：抽 `@ComponentV2` 子组件，动态值用 `@Param value` 接入（`@Param` 变化刷新其 UI）。**别为响应式硬拆组件**——单页少量块用 ① 即可。
  - ③ **ForEach / 各块数据源不同时**：传**整个** `@ObservedV2 + @Trace` 对象（**非**它的属性值），builder/子组件内读其 `@Trace` 属性。（`@Builder` 单参且直接传对象字面量才按引用生效，≥2 参不刷新。）
- **grep 自检**: `grep -rnE "@Builder" src/` 逐个核对——参数是否承载**会随状态变化的动态值**、调用处是否传 `xxx.toString()`/某属性值快照。**只有动态值中招才改**（走 ①/②/③）；**静态值参一律不动**。

### P-06: AppStorage 绑定时序
- **Android**: SharedPreferences 首次访问自动创建
- **ArkUI（V1）**: `@StorageLink('key')` 在组件实例化时绑定，如果 key 未预注册则绑定失败
- **ArkUI（V2，API 12+ 推荐）**: 用 `AppStorageV2.connect(Cls, key, () => new Cls())` 配合 `@ObservedV2` 类，**首次 connect 时自动用 `defaultCreator` 初始化**，无需在 EntryAbility 预注册即可工作；如需提前从持久层加载，仍可在 `EntryAbility.onCreate` 调用 `AppStorageV2.connect` 预热
- **错误表现**: V1 组件始终显示默认值，后续更新也无响应（V2 不会出现此问题，因为有 `defaultCreator` 兜底）
- **修复（V1）**: 在 `EntryAbility.onCreate` 中预注册所有 AppStorage key（如 `AppStorage.setOrCreate('key', initValue)`）
- **修复（V2）**: 升级到 V2 `AppStorageV2.connect` 模式，从根本上消除此类时序错误
- **grep 兼容检索**: `grep -E '@StorageLink|AppStorageV2' src/`（同时覆盖 V1 / V2 写法）

### P-07: ConstraintLayout 表达力缺口
- **Android**: ConstraintLayout 支持 chain、ratio、bias、barrier、guideline
- **ArkUI**: RelativeContainer 仅支持基本 alignRules
- **错误表现**: 复杂约束布局塌陷或错位
- **修复**: 复杂约束改用 Row/Column 嵌套 + Flex 布局模拟，或 onMeasureSize 自定义。改成 Stack 时，子组件各自贴顶/贴底不能靠 `.align()`（见 P-30）

### P-08: RecyclerView Adapter 模式丢失
- **Android**: Adapter 有粒度通知：notifyItemChanged/Inserted/Removed + DiffUtil
- **ArkUI**: 简单 ForEach(array) 丢失通知粒度，全量重渲染，动画消失
- **错误表现**: 列表无插入/删除动画，性能下降
- **修复**: 使用 LazyForEach + IDataSource 接口，实现 DataChangeListener

### P-09: NavigationView 语义丢失
- **Android**: NavigationView 集成抽屉头部、菜单项、选中状态管理
- **ArkUI**: 无等价物，需自定义 Column + List
- **错误表现**: 抽屉动画、选中高亮、头部滚动行为丢失
- **修复**: 自行实现选中状态管理和动画同步

### P-18: Scroll 内可点击元素的点击被父级手势抢占
- **Android/Compose**: `Modifier.clickable{}` 嵌在 `verticalScroll` 内，tap（无位移）与滚动（有位移）天然区分，点击正常触发
- **ArkUI**: 默认**子组件手势优先**，Scroll 内 Button/可点元素的 tap 通常能触发；但当祖先额外绑了竞争性自定义手势（`PanGesture` / `SwipeGesture` / `priorityGesture`）、或元素处于 Swiper / 嵌套滚动容器、或 `responseRegion` 不准时，父级 Pan 抢走手势 → 子 `onClick` / `TapGesture` 不响应
- **错误表现**: 列表/详情页里「SEE MORE」「展开更多」「行内按钮」点不动，但页面能滚
- **修复**: 先排除 Z-order 遮挡（见 P-17：贴底/全屏 overlay 盖住点击区）；确属手势竞争再按场景选——父子都要响应→子元素 `parallelGesture`（或父级 Pan 改 `parallelGesture`）；仅子响应→子元素 `priorityGesture` / `monopolizeEvents(true)`；嵌套【滚动】手势冲突见 P-25；命中区不准→校正 `responseRegion`

### P-25: 嵌套【滚动】手势被父容器吞——同向可滚子组件放进 Swiper/Scroll/Tabs 内层滑不动
- **Android**: `ViewPager` / `HorizontalScrollView` / `NestedScrollView` 内嵌同向 `RecyclerView` / `ScrollView`，嵌套滚动由框架自动分发，内外都能滑
- **ArkUI**: 内层 `List` / `Scroll` / `Grid` 直接放进 `Swiper` / `Scroll` / `Tabs` 后，**默认 `NestedScrollMode.SELF_ONLY`（不联动）**——同向手势被外层抢走：外层翻页 / 滚动、内层滑不动。编译不报错、纯运行时（典型：Swiper banner 内嵌横向分类 List，手指横滑触发的是 Swiper 翻页、分类条滚不动）
- **错误表现**: 内嵌的横向条 / 二级列表拖不动；或内层滚一点就带着外层一起动、方向错乱
- **修复方向**: 内层可滚组件显式配 `.nestedScroll(…SELF_FIRST)`（内层先滚、到边缘再交父级）+ 有界外尺寸（见 P-22）。**各容器 nestedScroll API / 枚举值 / worked example 见 arkts-component-builder/references/v2-scroll-and-form-components.md §3.5（规则正文以它为准，此处不复写）**
- **负向守卫**: 仅**同向【滚动】**冲突需要——**不同向**嵌套（横滑 Swiper 内竖滑 List 等）默认不冲突、别硬配；**点击 / tap** 被抢是 **P-18** 非本条；外层需先滚（下拉刷新头 / 折叠工具栏）用 `PARENT_FIRST` 非 `SELF_FIRST`
- **区别 P-18**: P-18 是内层元素**点击**被抢（页面能滚、按钮点不动）；P-25 是内层容器**滚动**被父吞（内层根本滑不动）。机制不同、可同页并存

### P-26: 多页/列表内多个 Lottie 全量同播——回收语义丢失
- **Android**: `RecyclerView` / `ViewPager` 有视图回收，屏幕外 item **不渲染、不播动画**；`lottie_autoPlay="true"` 写在 item 布局上，实际只有可见项在播
- **ArkUI**: `Swiper` / 普通 `ForEach` **全量创建所有子项**，把 `LottieAnimationView` 逐格直译成 `autoplay:true` 后**所有分页的动画同时播放**——编译不报错、单帧截图也正常；多页多格时 GPU/内存陡增 → 卡顿、耗电，密集场景有闪退风险
- **修复**: 只播当前可见项——Lottie 组件留 `playing` 控制口，由当前页索引或可见性回调驱动 play/pause；方案选择与组件模板见 **arkts-animation-migrate/references/lottie.md §6.1**（规则正文以它为准，此处不复写）
- **负向守卫**: 仅「全量创建容器 × 多实例 Lottie」需要；**单个/全屏常驻 Lottie（欢迎页、签到弹层）**、以及本身有回收语义的 **`LazyForEach` 列表**，不要硬塞可见性机关
- **区别 P-25**: P-25 是滚动**手势**被父吞（交互层）；P-26 是动画**播放生命周期**没有回收语义（渲染/性能层）。可同页并存

### P-27: Android 页面级 Dialog 直译成全局弹窗——路由跳转后弹窗盖住新页
- **Android**: `Dialog` / `DialogFragment` 是页面级——弹窗开着 `startActivity`，新页天然盖住弹窗、弹窗随宿主销毁，返回后仍在
- **ArkUI**: `@CustomDialog` / `openCustomDialog` / `showDialog` 默认**全局级**（弹窗节点挂页面根节点下，层级高于所有路由/导航页）：路由跳转不自动关闭，弹窗**恒盖在新页之上**。编译不报错、纯运行时
- **错误表现**: 弹窗里点「查看详情/规则」push 新页后，弹窗仍浮在最上层挡住新页；被迫把弹窗改写成页面级组件
- **修复方向**: `openCustomDialog` options 设 `levelMode: LevelMode.EMBEDDED`（API 15+、仅非子窗模式）；或透明弹窗页 `NavDestinationMode.DIALOG`。**规则正文见 arkts-component-builder/references/v2-dialogs-and-sheets.md §2c（以它为准，此处不复写）**
- **负向守卫**: 用完即关、不跨路由跳转的普通确认框 / Toast / Sheet 不需要页面级——别硬套

### P-23: @ObservedV2 / @Trace / @Observed 实例不能 JSON.stringify
- **Android**: Gson（或同类反射序列化库）`toJson(obj)` / `fromJson` 基于反射，序列化全部字段，与字段声明方式无关
- **ArkUI**: `@ObservedV2` / `@Trace` / `@Observed` 把字段转为访问器属性，`JSON.stringify(实例)` 枚举不到这些字段 → 产出空或残缺 JSON；再 `JSON.parse` + `fromJson` 还原即得空对象
- **错误表现**: 经序列化的对象字段全空——跨页传参（NavPathStack param）/ 持久化（Preferences）/ 跨线程（emitter）后，接收端拿到空值、必填校验失败、页面无数据
- **修复**: 不要对观察类实例直接 `JSON.stringify`。给模型显式写 `toJson()` 逐字段构造 plain object / Record，与 `fromJson()` 配对；序列化用 `obj.toJson()`，反序列化用 `Cls.fromJson(JSON.parse(s))`
- **grep 自检**: `grep -rnE "JSON.stringify\(" src/`，逐处确认实参不是 @ObservedV2/@Trace 类实例（应为 `.toJson()` 结果或 plain 对象）

## MEDIUM — 视觉偏差

### P-10: ViewPager → Swiper 生命周期差异
- **Android**: OnPageChangeCallback 在页面可见时触发
- **ArkUI**: Swiper onChange 触发时机与动画阶段关系不同
- **错误表现**: 页面初始化代码在错误时机执行
- **修复**: 关键初始化逻辑放在页面组件的 aboutToAppear 中，不依赖 onChange 回调

### P-11: BottomNavigationView → Tabs 底栏不可见（高度约束问题，非容器约束）
- **Android**: BottomNavigationView 可放在任意位置
- **ArkUI**: `Tabs({ barPosition: BarPosition.End })` 官方**没有**"必须放 Column"之类容器约束；底栏不可见的实际根因通常是 **Tabs 没拿到确定高度**——被放进 wrap-content / 滚动父级，或被同级组件挤压，TabBar 被顶出可视区
- **错误表现**: Tab 栏位置错误、不可见，或整个 Tabs 区域高度异常
- **修复**: 让 Tabs 获得确定高度并占满剩余空间——典型安全形态 `Column(){ Tabs(...).layoutWeight(1) }`，或对 Tabs 显式定高；不要把 Tabs 嵌进无定高的滚动容器

### P-12: 默认 padding/margin 差异
- **Android**: Button 等组件有默认 padding（约 12dp），gravity 从父容器继承
- **ArkUI**: Text / 容器类组件默认 padding 为 0，对齐也不从父容器继承，需显式设置（Button 等带主题预设样式的组件有自带内边距，以官方样式/实测为准，勿一概按 0 处理）
- **错误表现**: 自定义容器拼的"按钮"文字紧贴边框，文本左对齐而非居中
- **修复**: 显式设置 .padding() 和 .textAlign()

### P-13: RelativeLayout z-order 反转
- **Android**: RelativeLayout 子组件顺序不影响布局（由规则决定），但影响绘制顺序
- **ArkUI**: RelativeContainer 的子组件声明顺序决定 z-order
- **错误表现**: 需要在上层的组件被遮挡
- **修复**: 按 z-order 从底到顶排列子组件，或使用 .zIndex()

### P-14: Text 不折行的真因是横向无界约束（默认并非单行截断）
- **Android**: TextView 默认多行显示
- **ArkUI**: Text **默认同样自动折行**（官方 Text.maxLines：「默认情况下，文本是自动折行的」；溢出默认 `TextOverflow.Clip` 裁切，省略号**必须显式设置**）。真正的坑在**约束**：Text 处于横向无界容器（Row 未限宽、横向 Scroll、Flex 不换行）时拿到无限宽 → 单行延伸出屏，看起来像"只显示一行"
- **错误表现**: 文本不折行、单行被裁出屏幕右侧；或误信"默认单行"给正常多行文本加 `.maxLines(N)`，反而把内容截断了
- **修复**: 先给 Text 可达的宽度约束（父级定宽 / `layoutWeight(1)` / 视场景 `.width('100%')`），它即自动折行；确需截断时才显式 `.maxLines(N).textOverflow({ overflow: TextOverflow.Ellipsis })`

### P-15: Image 缩放默认值
- **Android**: ImageView 默认 ScaleType.FIT_CENTER（适应边界，保持比例，居中）
- **ArkUI**: Image 默认 ObjectFit.Cover（填满裁切）
- **错误表现**: 图片裁切方式不同
- **修复**: 设置 .objectFit(ImageFit.Contain)

## 入口配置

### P-16: 入口页面未注册
- **问题**: 迁移后 main_pages.json 仍指向 pages/Index（Hello World）
- **错误表现**: 启动应用显示 Hello World 而非迁移后的主页
- **修复**: a2h-execute Stage 1 全部 Batch 完成后（§3d 收口入口装配），更新 main_pages.json 的 src 数组


## Source-driven layout verification

Source constraints determine layout and sizing. Runtime frames select states and verify values/visibility. Never bake bounds into fixed geometry. Stack child placement uses source-equivalent wrappers, RelativeContainer or API-20 layoutGravity, not an ineffective align on an intrinsic-size child. See a2h-execute/references/layout-fidelity.md.
