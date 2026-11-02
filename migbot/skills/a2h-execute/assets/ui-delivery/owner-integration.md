# Owner 接入片段与确认单

这些片段由原入口、Navigation 和页面 VM owner 手工接入。生成器不修改工程文件。
生成的四个 `.ets` 放入同一个**试点专用**目录；普通产物关闭所有开关并移除 owner 的测试分支。
不增加新的 `@Entry`，不替换 `main_pages.json`、`loadContent` 目标或原 `pageMap`。

## 1. 冷启动与新 Want：写入同一个 session

在**原** EntryAbility 的现有生命周期中合并下面语句，保留原初始化、窗口配置和 loadContent。
`onCreate` 在 WindowStage 创建前写 session，因此入口组件首次构建即可读取。
已有应用收到新 Want 时先更新 session；无效/缺省 Want 会清除旧 fixture，再走原正常分支。
例中导入路径由 owner 按实际放置目录调整，不新建第二个 EntryAbility。

```typescript
import { AbilityConstant, Want } from '@kit.AbilityKit';
import { verificationSession } from '../verification/VerificationSession';

// 合并到原 class，不粘贴第二份同名方法。
onCreate(want: Want, launchParam: AbilityConstant.LaunchParam): void {
  const isVerification: boolean = verificationSession.acceptWant(want);
  // 保留原无条件初始化；只有原“首页自动导航/页面数据启动”分支需要按此变量绕过。
  // 冻结 provider 在正式页面 VM 创建时选择，不能在这里覆盖全局生产 provider。
}

onNewWant(want: Want, launchParam: AbilityConstant.LaunchParam): void {
  if (verificationSession.acceptWant(want)) {
    return; // V2 session 驱动已经加载的原入口；不重复 loadContent。
  }
  // 原 onNewWant 正常路由处理原样保留在这里。
}

// onWindowStageCreate 中原 windowStage.loadContent('pages/OriginalEntry', ...) 不变。
// 若已有 onDestroy，加入 verificationSession.clear()；不要在 onBackground 清除。
```

## 2. 在原入口提供最小 Navigation 宿主

将原 `build()` 的主体抽到原 owner 的 `@Builder normalContent()`（仅机械移动，不重写），
加下面 V2 分支。原页面仍是相同 `@Entry @ComponentV2`，正常栈与 `pageMap` 保留。
需要做的结构调整由 owner 确认；脚本不根据 regex 改未知入口。

```typescript
import { VerificationNavigationHost } from '../verification/VerificationNavigationHost';
import { VerificationSession, verificationSession } from '../verification/VerificationSession';

@Local verification: VerificationSession = verificationSession;

@Builder
verificationPageMap(name: string, param: Object) {
  this.pageMap(name, param) // 调原 owner 的路由分发；不另写预览用页面。
}

build() {
  if (this.verification.context !== undefined) {
    VerificationNavigationHost({
      pageMap: (name: string, param: Object) => { this.verificationPageMap(name, param) }
    })
  } else {
    this.normalContent()
  }
}
```

若原 pageMap 仅接 `name`，仍直接调用原分发；正式 NavDestination 的 `onReady` 从
`context.pathInfo.param as Object` 读取 `ValidatedVerificationContext`，再交原 owner 的参数适配函数。
不得为方便将 Navigation 改为旧 router，或把同一个 NavDestination 再包一层 NavDestination。
`@BuilderParam` 必须用上面的箭头闭包逐一转发原参数，保留原 owner 的 `this`；
不要传 `pageMap: this.verificationPageMap` 裸引用，否则 builder 中的 `this.pageMap` 可能指向宿主。
正式目的页在 `NavDestination.onReady` 绑定实际所属栈；即使无跳转参数也保留回调：

```typescript
private navPathStack: NavPathStack = new NavPathStack();
// 接在唯一的 NavDestination 后，原参数适配保留在此回调内。
.onReady((context: NavDestinationContext) => {
  this.navPathStack = context.pathStack;
  // original owner parameter adapter(context.pathInfo.param)
})
// 页面按钮使用 this.navPathStack.pop()，不能捕获正常入口或 Consumer 的空默认栈。
```

测试宿主的 Provider 只为兼容已有页面；Consumer 存在不能证明目的页实际用对栈。
返回/系统返回从目标页 pop 到**测试宿主**；“Exit verification”清 session 才恢复正常入口。

## 3. 在原 pageMap/VM owner 接类型化 context

下面 `FormalDetailParam`、`FormalPageVM`、`FormalDetailPage`、`realProvider`、`frozenProvider`
都是原工程既有类型或本次正式 converter 的产物，不是生成器创建的预览实现。
以下语句放进原 owner 的 VM 工厂/路由参数适配函数，而不是在每次 build 内新建 VM。

```typescript
// routeParam 来自既有 Navigation 路由，不把任意 Object 强转后直接信任。
if (routeParam instanceof ValidatedVerificationContext) {
  const p: FormalDetailParam = new FormalDetailParam();
  p.code = routeParam.stringParam('code');       // 字段须在冻结 whitelist 中逐一声明
  p.latitude = routeParam.numberParam('lat');
  // 其余必需字段都从 context 的 typed getter 读取，缺字段/错类型抛错，不补猜值。
  const provider: FormalProvider = routeParam.visualFixture
    ? frozenProvider.forFixture(routeParam.fixtureId) : realProvider;
  // frozenProvider 必须核 ui_delivery_inputs 的 fixture_id/page/state/content digest，
  // 其 DTO 与正式 provider 接口一致；使用同一 FormalPageVM 与 FormalDetailPage。
  const vm: FormalPageVM = new FormalPageVM(p, provider, routeParam.displayClock);
  verificationSession.retain(vm); // 原 VM 实现 dispose(): void，释放订阅及本态 provider。
  // 交给原 owner 持有并注入同一个正式页面，按原生命周期释放订阅。
}
```

fixture 关闭时 `fixtureId` 为空，不能仅凭 Debug/测试宿主/非空 stateId 选择测试数据。
`DisplayClock.displayNow()` 只接入需要“今天/当前月份”等**显示**逻辑；enabled 时格式化器使用
`timeZone` 和 `locale`，不能只固定时间戳而仍用设备时区。业务数据自己的日期来自冻结 DTO，
不从此时钟、截图 mtime 或采集时间推断。若该页无显示时钟调用点，保持关闭。
真实 timeout、重试、预算、性能统计继续使用原实时/单调时钟；不替换 Date.now 或全局定时器。

## 4. Owner 必须逐项记录确认，运行结果单列

- [ ] 记录本配置原字节 SHA-256 与 fixture_id/page_id/state_id/content digest 的绑定。
- [ ] 记录原 EntryAbility、正常入口、pageMap、正式页面、VM、provider 和适配函数的 file:line。
- [ ] cold `onCreate` 与 warm `onNewWant` 都调用同一 `verificationSession.acceptWant`。
- [ ] 验证请求不触发原首页自动导航；缺参数/非法参数清旧 session 并走正常路径。
- [ ] `loadContent`、main_pages 正常入口及原 pageMap 目标未替换；owner 提供真实 pageMap。
- [ ] pageMap 的 BuilderParam 用箭头闭包保持原 owner 的 this，并转发 name 与 param。
- [ ] 正式目的页 onReady 用 context.pathStack 绑定实际栈；普通/测试/嵌套入口按钮及系统返回均检查终态。
- [ ] 同一 Want 重复送达不累加栈；从宿主重发可再次进入；不同白名单状态替换旧测试栈。
- [ ] fixture 显式关闭时用真实 provider，普通产物所有开关关闭，Debug 不改变开关。
- [ ] 显示时钟只影响显示，旧 VM/订阅在退出测试或换状态时销毁，不污染正常 VM。
- [ ] SDK 编译结果、精确包安装、冷/热启动、目标页截图、返回及正常入口回归分别填写。

本轮生成与离线回归不会勾选最后一项。类型/源码核验不代表真实编译、安装或运行通过。
