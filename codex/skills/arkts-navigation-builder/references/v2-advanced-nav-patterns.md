# V2 高级导航模式

> 本文件为 **V2 主参考**（API 12+，`@ComponentV2 / @Local / @Param / @ObservedV2 / @Trace / AppStorageV2`），基于 AntennaPod ArkTS 播客应用实战总结的 5 种导航模式：路由参数类、routerMap、FullPlayer 隐藏 Tab、onReady 参数接收、路由常量管理。**本项目锁 V2**。
>
> V1 历史写法请见 [`advanced-nav-patterns.md`](./advanced-nav-patterns.md)（已加 legacy 标识）。
>
> 源码参考：`entry/src/main/ets/common/AppRouter.ets`、`entry/src/main/ets/pages/Index.ets`

---

## 1. 路由参数类定义（V2 推荐 `@ObservedV2`）

每个需要参数的 NavDestination 都有一个对应的参数类。V2 推荐用 `@ObservedV2` 包装，需观察的字段加 `@Trace`，使后续在子组件 / ViewModel 中也能响应式访问。字段必须有默认值（ArkTS 严格模式要求）。

```typescript
// 文件: common/AppRouter.ets
@ObservedV2
export class FeedDetailParam {
  @Trace feedId: number = 0
}

@ObservedV2
export class EpisodeDetailParam {
  @Trace episodeId: number = 0
  @Trace feedId: number = 0
}

@ObservedV2
export class FeedSettingsParam {
  @Trace feedId: number = 0
}

@ObservedV2
export class FeedInfoParam {
  @Trace feedId: number = 0
}

@ObservedV2
export class OnlineFeedViewParam {
  @Trace feedUrl: string = ''
}

@ObservedV2
export class VideoPlayerParam {
  @Trace episodeId: number = 0
}

@ObservedV2
export class OpmlImportParam {
  @Trace filePath: string = ''
}

@ObservedV2
export class FullPlayerParam {
  // No params needed — reads from AppStorageV2
}
```

**设计要点**：
- 每个参数类对应一个 NavDestination 页面
- 所有字段必须有默认值（ArkTS 不允许未初始化的字段）
- V2 推荐用 `@ObservedV2 + @Trace`，便于后续在组件 / ViewModel 中作为 `@Local` 持有时也能响应式
- `FullPlayerParam` 不需要参数（数据来自 AppStorageV2），但仍定义空类用于类型一致性
- 取参时先 `as Object` widening 再 `instanceof` 窄化（见 §4）；`pathInfo.param` 静态类型是 `unknown`，裸取（`const p = ctx.pathInfo.param`）会触发 `arkts-no-any-unknown`

---

## 2. routerMap @Builder — 路由映射（API 不变，V2 装饰器）

在 `Index.ets` 中定义 `@Builder routerMap`，将路由名映射到对应的组件。
使用 `if/else` 链（ArkTS 不支持 `switch` 在 @Builder 中直接用）。

```typescript
// 文件: pages/Index.ets
@Builder
routerMap(name: string) {
  if (name === RouteName.FEED_DETAIL) {
    FeedDetailComponent()
  } else if (name === RouteName.EPISODE_DETAIL) {
    EpisodeDetailComponent()
  } else if (name === RouteName.FEED_SETTINGS) {
    FeedSettingsComponent()
  } else if (name === RouteName.FEED_INFO) {
    FeedInfoComponent()
  } else if (name === RouteName.ONLINE_FEED_VIEW) {
    OnlineFeedViewComponent()
  } else if (name === RouteName.ADD_FEED) {
    AddFeedComponent()
  } else if (name === RouteName.PLAYBACK_HISTORY) {
    PlaybackHistoryComponent()
  } else if (name === RouteName.DOWNLOADS) {
    DownloadsComponent()
  } else if (name === RouteName.STATISTICS) {
    StatisticsComponent()
  } else if (name === RouteName.SETTINGS) {
    SettingsComponent()
  } else if (name === RouteName.VIDEO_PLAYER) {
    VideoPlayerComponent()
  } else if (name === RouteName.OPML_IMPORT) {
    OpmlImportComponent()
  } else if (name === RouteName.FULL_PLAYER) {
    FullPlayerComponent()
  } else if (name === RouteName.EPISODES) {
    AllEpisodesComponent()
  } else if (name === RouteName.SEARCH) {
    SearchComponent()
  }
}
```

**绑定到 Navigation**（API 不变）：

```typescript
Navigation(this.navPathStack) {
  // Tab 内容...
}
.navDestination(this.routerMap)  // 注册路由映射
.hideTitleBar(true)              // 隐藏 Navigation 自带的标题栏
.mode(NavigationMode.Stack)      // 使用栈模式
```

---

## 3. FullPlayer 隐藏 Tab（V2 — 用 AppStorageV2.connect 替代 @StorageLink）

下面示例适用于源端要求“普通子页面保留 MiniPlayer / Tab，FullPlayer 打开时隐藏”的宿主。按源端语义选择常驻元素，不要求所有应用添加播放条或隐藏 Tab；关键是常驻区域与 Navigation 的包含关系，单纯改用 Row 不会改变覆盖范围。

`isPlayerVisible` 由当前媒体/会话等源端显示条件驱动，`isFullPlayerVisible` 由全屏页生命周期驱动；初始化、订阅和返回恢复由原状态 owner 接线，不能只声明默认 false 而没有更新者。两者均不等同于 `isPlaying`。

**哪些目的地要盖住常驻元素**：Navigation 是路由页的显示容器，推入的页面只替换 Navigation 自身区域，放在 Navigation 外的常驻元素不会被盖住。按源端逐个判断目的地：源端在宿主内容区内切换的子页保留常驻元素；源端是独立 Activity 或全屏页的目的地，打开时要盖住常驻元素，与 FullPlayer 使用同一可见性状态，在其显示期间隐藏常驻元素；这类目的地可以叠加时按进入 / 退出计数，不用单个布尔值。窗口级弹窗优先由宿主用 `bindSheet`（默认 `SheetMode.OVERLAY`，显示在所有页面之上）或自定义弹窗挂载，选型见[弹窗选型速查](../../arkts-component-builder/references/v2-dialogs-and-sheets.md#选型速查)；选用路由弹窗时，它同样只覆盖 Navigation 区域。

**常驻元素宿主不是入口页时**：入口是启动页、分发页等，常驻元素位于随后进入的宿主页，宿主页本身是入口 Navigation 的一个目的地。宿主页内仍要为源端内容区放置 Navigation，与入口 Navigation 嵌套共存，不能把它当作重复的导航宿主移除。
- 结构按源端：各 Tab 各自保留返回栈的，用 [v2-nav-patterns.md §5](v2-nav-patterns.md) 每个 Tab 一个 Navigation；只有一个内容容器、切换时清空返回栈再替换的，用一个内容区 Navigation，切换时先 `clear()` 再 `pushPathByName()`（`replacePathByName()` 只替换栈顶，栈里有子页时不等价）。
- 宿主内的路由表登记它装载的页面；这些页面若也会从别处整页打开，入口路由表照常登记。
- 宿主用页面已在消费的同名 `@Provider` 提供内容栈，内容页的 `@Consumer` 取最近的 `@Provider`，不用改就在所在的栈上跳转，加入返回栈的子页因此保留常驻元素。
- 源端是独立 Activity 或全屏页的目的地，在入口栈上打开（内容页用 `getParent()` 取，见 §8c），整体覆盖宿主，不需要上一段的可见性状态。

V1 用 `@StorageLink('isFullPlayerVisible')` 控制 `if` 条件渲染。V2 移除了 `@StorageLink`，改用 `@ObservedV2` 类 + `AppStorageV2.connect()`。

```typescript
import { AppStorageV2 } from '@kit.ArkUI';   // ⚠️ 用 AppStorageV2.connect 的每个文件都要各自 import（编译硬规矩 1）；@ObservedV2/@Trace 等装饰器不 import

// 1. 定义全屏可见性的可观察状态类
@ObservedV2
export class PlayerVisibility {
  @Trace isPlayerVisible: boolean = false
  @Trace isFullPlayerVisible: boolean = false
}

// 2. 入口页面整体结构
@Entry
@ComponentV2
struct AppRoot {
  // V2 替代 V1 @StorageLink('isPlayerVisible') / @StorageLink('isFullPlayerVisible')
  @Local visibility: PlayerVisibility = AppStorageV2.connect(
    PlayerVisibility, 'playerVisibility', () => new PlayerVisibility()
  )!
  @Provider('navPathStack') navPathStack: NavPathStack = new NavPathStack()

  @Builder
  routerMap(name: string) { /* ... */ }

  build() {
    Column() {
      // Navigation — 始终存在
      Navigation(this.navPathStack) { /* Tab 内容 */ }
        .navDestination(this.routerMap)
        .layoutWeight(1)

      // MiniPlayer — 符合源端可见条件且非全屏时显示（暂停也可能保留）
      if (this.visibility.isPlayerVisible && !this.visibility.isFullPlayerVisible) {
        // MiniPlayer 组件...
      }

      // Tab 栏 — 仅在非全屏时显示
      if (!this.visibility.isFullPlayerVisible) {
        Row() {
          // 5 个 tab...
        }
        .height(56)
      }
    }
  }
}
```

**FullPlayerComponent 中设置标志（V2）**：

```typescript
@ComponentV2
export struct FullPlayerComponent {
  // V2：每个组件 connect 同一个 key 共享同一实例
  @Local visibility: PlayerVisibility = AppStorageV2.connect(
    PlayerVisibility, 'playerVisibility', () => new PlayerVisibility()
  )!

  build() {
    NavDestination() {
      // 全屏播放器 UI...
    }
    .onReady(() => {
      this.visibility.isFullPlayerVisible = true   // 进入时隐藏 Tab
    })
    .onDisAppear(() => {
      this.visibility.isFullPlayerVisible = false  // 退出时恢复 Tab
    })
  }
}
```

**为什么用 AppStorageV2.connect 而不是 @Local/@Event**：
- `isFullPlayerVisible` 需要跨组件通信（FullPlayer 组件 → AppRoot 页面）
- 它们不在同一组件树层级中（FullPlayer 在 NavDestination 内，与 Tab 栏是平行结构）
- AppStorageV2 通过 `connect()` 返回类实例，跨组件共享同一份内存数据，任意组件修改 `@Trace` 属性都会自动刷新所有引用方
- 等价 V1 模式：`@StorageLink('isFullPlayerVisible')`，但 V2 必须先抽出 `@ObservedV2` 类

**为什么这里用 AppStorageV2 而不是 `@Provider() / @Consumer()`**：`@Consumer` 取最近父节点的 `@Provider`，NavDestination 内的页面同样取得到（入口页注入 `navPathStack` 就依赖这一点）；这里的可见性标志是全应用状态，写入方可能是从任意宿主打开的全屏页，用 AppStorageV2 单例不必关心 Provider 放在哪一层。

---

## 4. onReady 参数接收（V2）

**关键规则**：NavDestination 参数必须在 `onReady` 回调中获取，不能在 `aboutToAppear` 中获取（此时参数尚未就绪）。

```typescript
@ComponentV2
export struct EpisodeDetailComponent {
  @Local episodeId: number = 0
  @Local feedId: number = 0
  private vm: EpisodeDetailViewModel = new EpisodeDetailViewModel()

  build() {
    NavDestination() {
      // UI 内容...
    }
    .onReady((ctx: NavDestinationContext) => {
      // pathInfo.param 是 unknown：先 `as Object` widening，再 instanceof 窄化
      const obj = ctx.pathInfo.param as Object
      if (obj instanceof EpisodeDetailParam) {
        this.episodeId = obj.episodeId
        this.feedId = obj.feedId
        this.loadData()
      }
    })
  }

  private loadData(): void { /* ... */ }
}
```

**发送参数**：

```typescript
// 跳转到剧集详情
const param = new EpisodeDetailParam()
param.episodeId = item.id
param.feedId = item.feedId
this.navPathStack.pushPathByName(RouteName.EPISODE_DETAIL, param)
```

**取参铁律：先 `as Object` widening，再 `instanceof` 窄化**（`pathInfo.param` 静态类型是 `unknown`）：

```typescript
// ✅ 正确 — `as Object` 强转 widening（合法），再 instanceof
const obj = ctx.pathInfo.param as Object
if (obj instanceof FeedDetailParam) {
  this.feedId = obj.feedId         // 字段只在 instanceof 块内访问
}

// ❌ 错误 1 — 裸 unknown 直接用：const param = ctx.pathInfo.param
//    → Use explicit types instead of "unknown" (arkts-no-any-unknown)
// ❌ 错误 2 — 隐式赋值：const param: Object = ctx.pathInfo.param
//    → Type 'unknown' is not assignable to type 'Object'
// 说明：`as Object` 是 widening、合法且必需；不推荐 `as FeedDetailParam` 直接下行断言（instanceof 更安全、且与构造侧 new XParam() 一致）
```

**常见错误**：

```typescript
// 错误：aboutToAppear 中参数尚未就绪
aboutToAppear(): void {
  // ctx.pathInfo.param 此时是 undefined！
  // 导致页面空白或崩溃
}

// 正确：使用 onReady
.onReady((ctx: NavDestinationContext) => {
  // 参数已就绪，可以安全读取
})
```

### 4a. 路由根形状与 Content / Page 拆分

**每个路由分支恰好产生一个 `NavDestination`**：可以由 pageMap 分支内联提供（`NavDestination() { PlainContent() }`），也可以由页面组件的 `build()` 根提供，但**不能两者同时提供**（双层嵌套：内层 `onReady` 的 `pathInfo.param` 为 `undefined`，内层生命周期不可靠），**也不能都没有**。页面 `build()` 根不能随条件在 `NavDestination` 与其他组件之间切换（如 `if (this.embedded)`）。`verify_arkui_safety.py` 对应 `NAV_NESTED_DESTINATION` / `NAV_CONDITIONAL_ROOT`（FAIL）。

**页面形态按 Android 加载关系判定，不是看到 tab 就拆**：

1. `FragmentTransaction` / NavHost / 返回栈 / 宿主内容容器装载 → 宿主内容区 `Navigation` 中的独立页面（以 `NavDestination` 为根），宿主做法见 §3「常驻元素宿主不是入口页时」。底部导航切换的各 tab 若源端是事务替换同一容器，也属此类。
2. ViewPager / `TabContent` / 布局中静态内嵌的 Fragment → 普通内容组件（无 `NavDestination`），经父页 `@Builder` 槽位嵌入。
3. 同一个内嵌 Fragment 还需要作为独立路由打开 → 拆成 `XxxContent`（普通组件）+ `XxxPage`（薄路由页，唯一根 `NavDestination`，内部包装 `XxxContent`）。

**拆分后的参数责任**：`XxxPage.onReady` 读取并校验 typed 路由参数，**参数就绪后再构建** `XxxContent`，经 `@Param` 显式传入；tab 使用 `XxxContent` 时显式传 tab 对应的默认状态。`XxxContent` 不从 `NavDestinationContext` 自取参数；不用 `getParamByName()` 兜底。

```typescript
@ComponentV2
export struct FeedListPage {
  @Local routeParam: FeedListParam | undefined = undefined
  @Local routeReady: boolean = false

  build() {
    NavDestination() {
      if (this.routeReady) {            // 条件在 NavDestination 内部，不改变页面根
        FeedListContent({ feedId: this.routeParam?.feedId ?? 0 })
      }
    }
    .hideTitleBar(true)
    .onReady((ctx: NavDestinationContext) => {
      const obj = ctx.pathInfo.param as Object
      this.routeParam = obj instanceof FeedListParam ? obj : undefined
      this.routeReady = true
    })
  }
}
```

`XxxContent` 在 `aboutToAppear` 里用 `@Param` 加载数据时，上面"就绪后再构建"保证它拿到的是真实参数；只有 Content 必须常驻、参数会变化时才改用 `@Monitor` 响应参数变化——不能让 `aboutToAppear` 先用默认参数加载一次。

---

## 5. 路由常量集中管理（API 不变）

所有路由名使用 `RouteName` 静态类集中定义，避免字符串硬编码。这一模式与 V1 完全一致；与 V2 装饰器无关。

```typescript
// 文件: common/AppRouter.ets
export class RouteName {
  static readonly HOME: string = 'home'
  static readonly SUBSCRIPTIONS: string = 'subscriptions'
  static readonly QUEUE: string = 'queue'
  static readonly EPISODES: string = 'episodes'
  static readonly SEARCH: string = 'search'
  static readonly FEED_DETAIL: string = 'feedDetail'
  static readonly EPISODE_DETAIL: string = 'episodeDetail'
  static readonly FEED_SETTINGS: string = 'feedSettings'
  static readonly FEED_INFO: string = 'feedInfo'
  static readonly ONLINE_FEED_VIEW: string = 'onlineFeedView'
  static readonly ADD_FEED: string = 'addFeed'
  static readonly PLAYBACK_HISTORY: string = 'playbackHistory'
  static readonly DOWNLOADS: string = 'downloads'
  static readonly STATISTICS: string = 'statistics'
  static readonly SETTINGS: string = 'settings'
  static readonly VIDEO_PLAYER: string = 'videoPlayer'
  static readonly OPML_IMPORT: string = 'opmlImport'
  static readonly FULL_PLAYER: string = 'fullPlayer'
  static readonly INBOX: string = 'inbox'
}
```

**总计 19 个路由**，可分为 4 类：

| 类别 | 路由 |
|------|------|
| Tab 页 (5) | HOME, QUEUE, INBOX, SUBSCRIPTIONS, EPISODES |
| 详情页 (4) | FEED_DETAIL, EPISODE_DETAIL, FEED_SETTINGS, FEED_INFO |
| 功能页 (6) | SEARCH, ADD_FEED, ONLINE_FEED_VIEW, DOWNLOADS, PLAYBACK_HISTORY, STATISTICS |
| 全屏页 (4) | FULL_PLAYER, VIDEO_PLAYER, SETTINGS, OPML_IMPORT |

**NavPathStack 操作速查（V2）**：

```typescript
// V2：NavPathStack 由 @Provider() 共享给所有子组件
@Provider('navPathStack') navPathStack: NavPathStack = new NavPathStack()

// 子组件通过 @Consumer() 获取（必须带括号 + 默认值）
@Consumer('navPathStack') navPathStack: NavPathStack = new NavPathStack()

// 推入页面（API 不变）
this.navPathStack.pushPathByName(RouteName.FEED_DETAIL, param)

// 返回上一页
this.navPathStack.pop()

// 清除栈（回到根页面）
this.navPathStack.clear()

// 替换当前页面
this.navPathStack.replacePath({ name: RouteName.HOME })
```

---

## 6. 路由拦截（setInterception — 登录守卫 / 权限校验 / 重定向）

`NavPathStack.setInterception(NavigationInterception)`（API 12+）在页面进入前拦截。三个回调：`willShow`（跳转前，可改栈重定向）、`didShow`（跳转后）、`modeChange`（Stack↔Split 模式变化）。

```typescript
@ComponentV2
struct MainNav {
  pageStack: NavPathStack = new NavPathStack()

  aboutToAppear(): void {
    this.pageStack.setInterception({
      // 跳转前：未登录访问受保护页 → 重定向到登录
      willShow: (from: NavDestinationContext | 'navBar',
                 to: NavDestinationContext | 'navBar',
                 operation: NavigationOperation, isAnimated: boolean) => {
        if (typeof to === 'string') return            // 'navBar'（主页）放行
        const name = to.pathInfo.name
        const auth = AppStorageV2.connect(Auth, 'auth', () => new Auth())!
        if (name === 'ProfilePage' && !auth.loggedIn) {
          this.pageStack.pop()                        // 取消本次进入
          this.pageStack.pushPathByName('LoginPage', name)  // 重定向，登录后可回跳
        }
      },
      didShow: (from, to, operation, isAnimated) => { /* 埋点 / 标题同步 */ },
      modeChange: (mode: NavigationMode) => { /* 适配单栏/双栏 */ }
    })
  }

  build() {
    Navigation(this.pageStack) { /* ... */ }
  }
}
```

**要点**：`to`/`from` 为 `'navBar'` 时代表主页（NavBar），需先判类型；重定向在 `willShow` 里改栈（`pop` + `pushPathByName`）；登录态用 `AppStorageV2` 全局读取。

---

## 7. 导航栈持久化与进程恢复（recoverable / getPathStack / setPathStack）

App 退到后台被系统回收后，用户回来希望**恢复到被回收前的多级页面层级**（如 列表→详情→评论 仍停在评论），而不是回首页。两条官方路径，按需选。

### 7a. 官方主范式：`recoverable(true)` 自动恢复（API14+，推荐）

给 Navigation 和它入栈的 NavDestination **都**配 `recoverable(true)`，进程异常退出冷启动时系统**自动重建并恢复整条路由栈**，不必手写持久化。

```typescript
Navigation(this.stack) {
  // ...
}
.id('mainNav')            // ⚠️ 前提：必须先设通用属性 id，否则 recoverable 无效
.recoverable(true)         // 进程被回收后冷启动自动恢复整条栈
.navDestination(this.pageMap)

// 每个入栈的 NavDestination 也要配：
NavDestination() { /* ... */ }
  .recoverable(true)       // 两处都配才生效
```
- 三个硬前提：① Navigation 先设 `id`；② Navigation 与 NavDestination **都**配 `recoverable(true)`；③ 恢复时**不可序列化的信息（复杂 param、`onPop` 回调）会被丢弃**。
- 进程级备份需配合 UIAbility 的 `onSaveState`/备份恢复才完整生效；单文件里配好这两个属性即为正解，UIAbility 协议细节见系统文档。

### 7b. 手动栈快照：`getPathStack` / `setPathStack`（API19+，需自定义持久化时）

要自己控制持久化内容（只存页面名、跨版本迁移等）时，用这对接口一次性存/取**整条栈**：

```typescript
// 取整条栈快照（Array<NavPathInfo>），存可序列化子集
const cur: Array<NavPathInfo> = this.stack.getPathStack()
this.snap.names = cur.map((info: NavPathInfo): string => info.name)

// 灌回整条栈（一次性批量入栈 + 转场；第二参 animated）
const infos: Array<NavPathInfo> = this.snap.names.map(
  (n: string): NavPathInfo => new NavPathInfo(n, new XxxParam())
)
this.stack.setPathStack(infos, false)
```
- 快照类用 `@ObservedV2 + @Trace` + `PersistenceV2.globalConnect` 落盘（重启后仍在），模板见 `v2-tab-navigation.md §5 方案 B`。
- ❌ **别自造平行数组（names/ids）+ 循环 `pushPathByName` 逐页重放**——能跑，但不是官方机制、丢批量入栈的转场/复用语义；`getPathStack`/`setPathStack` 一次性存取整条栈才是正解。

---

## 8. 进阶栈操作：单例复用 / 精确删栈 / 嵌套父栈

### 8a. 单例页复用（`LaunchMode.MOVE_TO_TOP_SINGLETON` + `onNewParam`，API19）

同一页面反复进入不想每次新建实例（如「消息详情」重复点开）：用单例启动模式，已在栈则移到栈顶、不新建；页面靠 `onNewParam` 刷新参数（此时 **`onReady` 不会再触发**）。

```typescript
// 跳转侧：pushPath(info, options)，launchMode 在 NavigationOptions（不是 pushPathByName 的 onPop 位）
const p = new DetailParam()
p.id = 42
this.stack.pushPath(new NavPathInfo('Detail', p),
  { launchMode: LaunchMode.MOVE_TO_TOP_SINGLETON })   // 已存在→移栈顶复用；否则同 STANDARD 新建

// 页面侧：单例被重新导航时靠 onNewParam 刷新（onReady 只在首次创建触发）
NavDestination() { /* ... */ }
  .onReady((ctx: NavDestinationContext) => { /* 首次创建取参 */ })
  .onNewParam((param: ESObject) => {                  // API19；回调形参类型是 ESObject
    const obj = param as Object
    if (obj instanceof DetailParam) { this.itemId = obj.id }
  })
```
- `LaunchMode`：`STANDARD`(默认新建) / `MOVE_TO_TOP_SINGLETON`(移栈顶复用) / `POP_TO_SINGLETON`(弹到该页) / `NEW_INSTANCE`(强制新建，用于 pop 再 push 同名却要新实例)。
- ❌ 别用「共享 `@Trace`/`AppStorageV2` state 手动刷参」冒充单例复用——那是另一路径、拿不到单例栈语义；单例复用就用 `launchMode` + `onNewParam`。

### 8b. 精确删栈：`removeByIndexes` / `removeByNavDestinationId`

删中间若干页（如向导完成后清掉中间步骤）比 `removeByName`（按名、会误删所有同名）更精确：

```typescript
const n: number = this.stack.removeByIndexes([1, 2])          // 按索引数组删，返回删除页数(number)
const ok: boolean = this.stack.removeByNavDestinationId('nd-42') // 按唯一 id 删，返回 boolean
// navDestinationId 在目标页 onReady 的 ctx.navDestinationId 或 NavDestinationInfo 里取
```
- `removeByName(name)` 删**所有**同名页；只删特定一个用 `removeByNavDestinationId`（id 全局唯一）。

### 8c. 嵌套导航拿父栈：`getParent()`（API11）

内层 Navigation 有自己独立的 `NavPathStack`；要从子栈做**整页级**跳转（覆盖外层）用 `getParent()` 直取外层父栈：

```typescript
// 子页（在内层 Navigation 里）
const parent: NavPathStack | null = this.childStack.getParent()   // 返回父栈或 null
if (parent !== null) {
  parent.pushPathByName('FullDetail', param)   // 用父栈跳 → 覆盖整个外层，而非只在子栈内
}
```
- ❌ 别一律用 `@Provider/@Consumer` 把外层栈注入子页来「跳父栈」——`getParent()` 是官方直取父栈方式、不必额外接线；`@Provider/@Consumer` 用于共享同一个栈、不是取父栈。

### 8d. 返回传值：`onResult`（API15，比 onPop 回调更新的官方推荐）

来源页 A 跳到 B 选值，B 返回时把值带回 A 并刷新——**当前官方推荐用 `onResult`**（NavDestination 事件），比旧的 `pushPathByName(name, param, onPop)` 回调更清晰（源页集中接收、不必在每个跳转处挂回调）：

```typescript
// 来源页 A（NavDestination）：onResult 接收返回值
NavDestination() { /* ... */ }
  .onResult((param: Object) => {          // API15；下游页 pop 或侧滑返回时触发
    if (param instanceof AddressParam) { this.address = param.text }
  })

// 目标页 B：pop 时带返回值
this.stack.pop(selectedAddress)           // pop(result) 回传
```
- `onResult` 回调形参用 `Object`（或 `ESObject`）+ `instanceof` 窄化，**别用 `as`**。
- 旧写法 `pushPathByName(name, param, onPop)` 仍可用、不算错；但新代码优先 `onResult`（prompt 若明求「更新的官方返回机制」须给 onResult，onPop 会被判过时）。

---

## V2 vs V1 速查表（高级导航场景）

| 用途 | V2 | V1（不推荐） |
|---|---|---|
| 路由参数类（用 ViewModel 持有时） | `@ObservedV2` 类 + `@Trace` 字段 | 普通 class（无装饰器） |
| 入口页面 struct | `@ComponentV2` | `@Component` |
| NavPathStack 注入 | `@Provider('navPathStack')` | `@Provide('navPathStack')` |
| NavPathStack 接收 | `@Consumer('navPathStack')`（必须默认值） | `@Consume('navPathStack')` |
| 子页面参数缓存 | `@Local episodeId: number = 0` | `@State episodeId: number = 0` |
| FullPlayer 隐藏 Tab 标志 | `@ObservedV2 + AppStorageV2.connect` | `@StorageLink('isFullPlayerVisible')` |
| 路由常量类 | `class RouteName { static readonly ... }` | 同 V1（无装饰器，无差异） |

---

## 跨文档参考

- [`v2-nav-patterns.md`](./v2-nav-patterns.md) — V2 Navigation 完整模式
- [`v2-tab-navigation.md`](./v2-tab-navigation.md) — V2 Tab 导航完整模式
- [`../SKILL.md`](../SKILL.md) — 决策树与陷阱总览
- `arkts-state-manager/references/v2-decorators.md` — V2 装饰器完整规则
- `arkts-state-manager/references/v2-global-state.md` — `AppStorageV2 / PersistenceV2` 完整模板
