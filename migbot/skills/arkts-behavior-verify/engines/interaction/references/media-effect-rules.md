<!-- when: scope、Review、Repair 或交付涉及播放/下载能力时读取 -->
<!-- topics: media lifecycle, request agent, terminal state, observable stability -->

# 媒体域效果规则

按实际能力适用，普通点击不承担媒体义务。以下规则从主流程按需加载，语义保持不变。

## 作用域候选

播放/下载 scope 仍只在依赖闭包内检查条件挂载、平台请求/文件路径和 WebView
origin；编辑完成后对同一目标重跑 post scope。WebView synthetic-origin 既检查
拦截回调自身是否直接驱动播放/下载，也检查同一页面是否同时存在目标入口和
真实命令：shownotes 的 `loadData`/intercept 若把 `data:` 或内部 origin 转给
`startAbility(viewData)`，会阻断该页面的播放/下载前置，即使命令在 sibling
handler 中。完全无目标入口的独立 WebView 仍只作为 REVIEW_REQUIRED 证据，不得
阻断目标修复。播放 scope 还检查最终 observable
host：沿组件实例追踪实际宿主、层级与命中区域，确认播放器条/展开播放器不会被
Navigation/SideBar 遮挡。父组件提供的有效 overlay 可以承载子组件，不要求每个
子页面重复创建根级 Stack；无法证明实际遮挡时保留 Review 提示。展开播放器时，
折叠 mini-player bar 也必须按 `playerExpanded` 从组合树
移除（优先 `Visibility.None`）或明确设置为不参与命中；`Visibility.Hidden` 在
Navigation 切换期间仍可能保留遮挡/命中层，不能直接视为安全。仅按
`playbackState.visible` 保持显示会遮挡展开页控制区，并作为阻断 hazard 送审。
WebView `loadData` 的 intercept 若把 `data:`/内部 origin 转给
`startAbility(viewData)`，且拦截回调或其所在页面具备目标播放/下载入口时，才是
确定的 `WEBVIEW_SYNTHETIC_ORIGIN_FORWARD` blocker，必须先修复。下载 scope 还审查
request.agent 的确定性 `saveas` 是否在 create 前处理旧 task/文件冲突；局部别名
展开后含 Date.now/UUID/random 等唯一目标时不触发 blocker；只有仍为固定目标且
无旧 task/文件处理才产生 `DOWNLOAD_AGENT_STALE_TARGET_COLLISION` blocking hazard，
送入 Review，确认当前调用关系与 Android 后置条件后形成含真实 owner 的修复工单。合法 BACKGROUND 模式或
相对 cache 路径本身仍不是缺陷。blocking hazard 只否决对应 contract 的 `APPLIED`，
不阻止无关 interaction 批次。

## 审查与修复

播放/下载目标使用两轨准入：入口、实体/媒体 identity、真实领域命令、错误投影、
播放器可见宿主（播放）和 task/文件冲突处理（下载）属于静态必修项；平台回调、
AVPlayer prepared/playing、最终文件非空、设备网络或跨进程时序属于运行时延后项。
对 AVPlayer 的 `play/pause/setSpeed`、音频中断
处理和状态投影，必须有显式 `INITIALIZED → PREPARING → PREPARED → PLAYING`
门控；不得在未达到平台允许状态时执行控制操作，也不得把 `createAVPlayer`、设置
URL 或进入回调当成播放成功。若 SDK/真机报“not prepared/playing/paused/...”，
该状态顺序视为未闭合，必须保留为 `PARTIAL` 或进入 Round 2。下载同样必须把
agent `completed`、最终绝对文件路径、持久化记录和下载页回读作为同一后置条件，
不能以 `create/start` 或按钮变化代替完成。
`request.agent` 的后台模式可合法监听 Task 事件，且相对 `saveas: './name'` 明确落在
调用方 cache；不得为了通过错误门禁强制改成前台模式或绝对路径。播放时必须区分
`audioRendererInfo` 的 initialized 合法态与 `audioInterruptMode` 的 prepared 及以后
合法态，不能把两者合并到 initialized。若静态断点明确且已有命令可复用，即使延后项
暂时无法证明，也必须尝试有界编辑并报告 `PARTIAL`，不能仅因缺少真机证据报
`NO_CHANGE`。只有根因依赖未知平台签名、没有可复用命令或 ownership 无法界定
时才允许 `NO_CHANGE+EVIDENCE_GAP/NO_SAFE_PATCH`。

播放成功不能只凭 `prepared/playing` 或 service Promise 判断完成，必须同时核对根级
player bar/route 的稳定可见性和当前 item identity。下载固定临时目标若没有 create
前的旧 task 停止/删除或有文档依据的幂等替换，Review 必须把它作为潜在 `File exists`
断点，要求修复处理冲突而不是只改按钮文案。

播放的稳定可见性包含一个不可省略的返回后重开序列：
`playItem(itemId) → 返回来源页 → 播放条仍可见且 itemId 不变 → 点击播放条 →
展开播放器 → 3 秒后仍可见且 itemId 不变`。静态 scope guard 会把生命周期或
shell observer 对 `playerExpanded`/`playerSheetState` 的条件重投影（包括三元表达式、
`=== EXPANDED` 和 setter）送入 Review；若来源可能是旧的 `COLLAPSED/HIDDEN/false`，
必须修复或保留为 `ROUND2_REQUIRED`，不能仅凭首次闪现、handler 调用或 `playing` 日志
关闭 contract。

