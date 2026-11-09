<!-- when: §4 给 task 标注 suggested_skills 时加载 -->
<!-- topics: suggested_skills, task→skill 映射, Domain Skill 绑定, 特殊领域追加 -->
<!-- 分工: 本表是 task→skill 映射数据的唯一权威(plan 期标注 + execute runtime 漏标兜底共用同一张表); execute 派发前的覆盖/注入/降级行为规则见 i2h-execute references/skill-binding-override.md -->

# suggested_skills 主映射表（iOS → HarmonyOS）

根据 task 内容 / 业务类别匹配到对应 Domain Skill。一个 task 可标注多个 skill（按执行顺序排列）。

「典型 iOS 框架 / SDK」列同时供 i2h-plan §Step 4.1 三方 SDK 决策树使用：feature spec 中提到的 SDK 命中本列任一关键词 → 直接 `suggested_skills` 追加对应 skill，**不登记 placeholder-registry**；未命中 → 登记 `kind=thirdparty-sdk` 等待适配方案到位。

---

## Core 映射表（基础设施）

| Task 内容 / 业务类别（关键词） | suggested_skill | 典型 iOS 框架 / SDK |
|------------------------------|----------------|-------------------|
| **UI 页面转换（SwiftUI）** | `i2h-swiftui-converter` (agent) | SwiftUI, View, @State, @Binding |
| **UI 页面转换（UIKit）** | `i2h-uikit-converter` (agent) | UIKit, UIViewController, UIView |
| 项目结构 / 模块配置 | `arkts-project-scaffolder` | Xcode project, workspace |
| 第三方库替换 | `arkts-library-migration` | CocoaPods, SPM, Carthage |
| 三方 SDK 集成事实（初始化/API 签名/权限/ohpm 包名版本） | `hmos-sdk-docs` | 极光推送 / 微信 SDK / 支付宝 / Firebase |
| **数据库 / DAO / Model** | `arkts-data-layer` | CoreData, SwiftData, Realm, SQLite |
| **网络请求 / HTTP** | `arkts-data-layer` | URLSession, Alamofire, Moya |
| 网络层联调 / 拦截器签名（HMAC）/ 响应 unwrap / API contract 对账 / 抓包验证 / 启动期初始化排障 | `arkts-network-troubleshoot` | URLProtocol, NetworkInterceptor |
| **文件操作 / 权限 / 扫码 / 震动 / 相机 / PhotoPicker / 系统能力** | `arkts-system-capabilities` | FileManager, AVFoundation, Photos |
| **导航框架 / 路由** | `arkts-navigation-builder` | NavigationView, NavigationStack, Coordinator |
| **状态管理 / 数据绑定 / 全局状态 / 持久化偏好** | `arkts-state-manager` | @State, @ObservedObject, @EnvironmentObject, Combine |
| **页面组件 / 列表** | `arkts-component-builder` | List, ScrollView, LazyVGrid |
| 音频播放 / AVPlayer / 后台播放 | `arkts-media-playback` | AVAudioPlayer, AVPlayer |
| 大文件下载 / 断点续传 | `arkts-download-manager` | URLSession download tasks |
| **动画 / 转场** | `arkts-animation-builder` | withAnimation, .transition(), .animation() |
| Lottie / 帧动画 / 共享元素转场 / matchedGeometryEffect | `arkts-animation-migrate` | Lottie, matchedGeometryEffect |
| **编译修复** | `hmos-builder` (agent)；仅由 i2h-execute 的 Base-7 / Stage 3 gate / FV-2 集中派发 | Xcode build |
| API 验证 | `arkts-knowledge-verifier` | — |
| App 身份配置 | `arkts-app-identity` | Info.plist, Bundle Identifier |
| **资源转换** | `ios2hmos_resources_convert` | Assets.xcassets, Localizable.strings |
| **公共组件库** | `arkts-component-builder`, `arkts-pattern-library` | 自定义 SwiftUI View / UIKit 组件 |
| 客服 / IM / 在线聊天 | `arkts-customer-service` | 七鱼 / 网易云信 / 腾讯云 IM |
| 沉浸式 / 安全区 / 状态栏 / 全屏背景 / NavDestination 模板 | `arkts-immersive-safearea` | .ignoresSafeArea(), .statusBar() |
| **任一涉及 page** 的 Slice，且该 page 的 meta.json 含 `needs_immersive_safearea: true` | **强绑** `arkts-immersive-safearea` | — |

---

## 系统集成类（iOS 系统框架）

| Task 内容 / 业务类别 | suggested_skill | 典型 iOS 框架 / SDK |
|-------------------|----------------|-------------------|
| **登录 / 授权 / OAuth / Sign in with Apple** | `arkts-login` | Sign in with Apple, ASAuthorizationController |
| **第三方登录（微信、支付宝、Facebook）** | `arkts-login` | 微信 SDK, 支付宝 SDK, Facebook SDK |
| **支付 / 收银台 / 订单 / IAP / 订阅签约** | `arkts-payment` | StoreKit, Apple Pay, 微信支付, 支付宝 |
| **推送通知 / APNs / 本地通知** | `arkts-notification` | UNUserNotificationCenter, UserNotifications |
| **相机 / 相册 / 图片选择** | `arkts-camera`, `arkts-media` | AVFoundation, PhotoKit, UIImagePickerController |
| **定位 / 地图** | `arkts-location`, `arkts-map` | CoreLocation, MapKit |
| **第三方地图（高德、百度）** | `arkts-map` | 高德地图 SDK, 百度地图 SDK |
| **广告 SDK / 开屏 / 插屏 / 信息流 / 激励视频 / Banner** | `arkts-ad` | AdMob, 穿山甲, 优量汇 |
| **视频 / 视频播放 / 横屏播放器 / PiP** | `arkts-video-playback` | AVPlayer, AVPlayerViewController |
| **WebView / Web 组件 / 网页加载 / JS 注入** | `arkts-webview` | WKWebView, WebKit |
| **分享 / 社交分享** | `arkts-share` | UIActivityViewController |
| **扫码 / 二维码 / 条形码** | `arkts-system-capabilities` | AVFoundation (AVCaptureMetadataOutput) |

---

## 数据存储类（iOS 数据持久化）

| Task 内容 / 业务类别 | suggested_skill | 典型 iOS 框架 / SDK |
|-------------------|----------------|-------------------|
| **CoreData / NSManagedObject / NSFetchRequest** | `arkts-data-layer` | CoreData, NSPersistentContainer |
| **SwiftData / @Model / @Query** | `arkts-data-layer` | SwiftData, ModelContext |
| **UserDefaults / @AppStorage** | `arkts-data-layer` | UserDefaults, @AppStorage |
| **Keychain / 安全存储** | `arkts-secure-storage`（待定） | Keychain Services |
| **文件存储 / FileManager** | `arkts-system-capabilities` | FileManager, DocumentDirectory |
| **Realm 数据库** | `arkts-data-layer` | Realm Swift |

---

## 网络请求类（iOS 网络层）

| Task 内容 / 业务类别 | suggested_skill | 典型 iOS 框架 / SDK |
|-------------------|----------------|-------------------|
| **URLSession / dataTask / uploadTask / downloadTask** | `arkts-data-layer` | URLSession, URLRequest |
| **Alamofire / HTTP 封装库** | `arkts-data-layer`, `arkts-network-troubleshoot` | Alamofire |
| **Moya / 网络抽象层** | `arkts-data-layer` | Moya |
| **WebSocket** | `arkts-websocket`（待定） | URLSessionWebSocketTask |
| **网络监控 / Reachability** | `arkts-network-troubleshoot` | Network framework, NWPathMonitor |

---

## 状态管理类（iOS 响应式）

| Task 内容 / 业务类别 | suggested_skill | 典型 iOS 框架 / SDK |
|-------------------|----------------|-------------------|
| **@State / @Binding / SwiftUI 状态** | `arkts-state-manager` | SwiftUI property wrappers |
| **@ObservedObject / @StateObject / ObservableObject** | `arkts-state-manager` | SwiftUI, Combine |
| **@EnvironmentObject / 全局状态** | `arkts-state-manager` | SwiftUI environment |
| **@Published / Combine / Publisher** | `arkts-state-manager` | Combine framework |
| **ViewModel 模式 / MVVM** | `arkts-state-manager` | 自定义 ViewModel |
| **NotificationCenter / 事件总线** | `arkts-state-manager` | NotificationCenter |
| **RxSwift / 响应式编程** | `arkts-state-manager` | RxSwift, RxCocoa |

---

## UI 组件类（iOS UI 框架）

### SwiftUI 组件

| Task 内容 / 业务类别 | suggested_skill | 典型 iOS 组件 |
|-------------------|----------------|-------------|
| **列表 / List / ForEach** | `arkts-component-builder` | List, ForEach |
| **网格 / LazyVGrid / LazyHGrid** | `arkts-component-builder` | LazyVGrid, LazyHGrid |
| **滚动视图 / ScrollView** | `arkts-component-builder` | ScrollView |
| **Tab / TabView** | `arkts-component-builder` | TabView |
| **导航 / NavigationView / NavigationStack** | `arkts-navigation-builder` | NavigationView, NavigationStack |
| **Sheet / 模态弹窗** | `arkts-component-builder` | .sheet(), .fullScreenCover() |
| **Alert / 警告框** | `arkts-component-builder` | .alert() |
| **Form / 表单** | `arkts-component-builder` | Form, Section |
| **Picker / 选择器** | `arkts-component-builder` | Picker |
| **TextField / 文本输入** | `arkts-component-builder` | TextField, TextEditor |
| **Toggle / 开关** | `arkts-component-builder` | Toggle |
| **Slider / 滑块** | `arkts-component-builder` | Slider |
| **Stepper / 步进器** | `arkts-component-builder` | Stepper |

### UIKit 组件

| Task 内容 / 业务类别 | suggested_skill | 典型 iOS 组件 |
|-------------------|----------------|-------------|
| **UITableView / 表格视图** | `arkts-component-builder` | UITableView, UITableViewCell |
| **UICollectionView / 集合视图** | `arkts-component-builder` | UICollectionView |
| **UIScrollView / 滚动视图** | `arkts-component-builder` | UIScrollView |
| **UITabBarController / Tab 控制器** | `arkts-navigation-builder` | UITabBarController |
| **UINavigationController / 导航控制器** | `arkts-navigation-builder` | UINavigationController |
| **UITextField / 文本输入** | `arkts-component-builder` | UITextField, UITextView |
| **UIButton / 按钮** | `arkts-component-builder` | UIButton |
| **UIImageView / 图片视图** | `arkts-component-builder` | UIImageView |
| **UILabel / 文本标签** | `arkts-component-builder` | UILabel |
| **UISwitch / 开关** | `arkts-component-builder` | UISwitch |
| **UISlider / 滑块** | `arkts-component-builder` | UISlider |
| **UIAlertController / 警告框** | `arkts-component-builder` | UIAlertController |

---

## 特殊功能类

| Task 内容 / 业务类别 | suggested_skill | 典型 iOS 技术 |
|-------------------|----------------|-------------|
| **多设备 / 平板 / iPad 适配** | `arkts-multi-device` | Size classes, horizontalSizeClass |
| **深色模式 / Dark Mode** | `arkts-dark-mode` | @Environment(\\.colorScheme) |
| **国际化 / 多语言** | `arkts-i18n` | Localizable.strings, NSLocalizedString |
| **无障碍 / VoiceOver** | `arkts-accessibility` | Accessibility modifiers, UIAccessibility |
| **大字体 / 动态字体** | `arkts-large-font` | Dynamic Type, .dynamicTypeSize() |
| **手势 / Gesture** | `arkts-gesture` | .gesture(), UIGestureRecognizer |
| **拖放 / Drag & Drop** | `arkts-gesture` | .onDrag(), .onDrop() |
| **图表 / Charts** | `arkts-canvas`（待定） | Swift Charts, third-party charts |
| **自定义绘制 / Canvas** | `arkts-canvas`（待定） | Canvas, Path, Shape |

---

## 图片处理类

| Task 内容 / 业务类别 | suggested_skill | 典型 iOS 库 / SDK |
|-------------------|----------------|-----------------|
| **Kingfisher / 图片缓存加载** | `arkts-component-builder`（自建缓存） | Kingfisher |
| **SDWebImage / 图片缓存** | `arkts-component-builder`（自建缓存） | SDWebImage |
| **图片编辑 / 裁剪 / 滤镜** | `arkts-media` | Core Image, Core Graphics |

---

## 三方 SDK 专项（需要特殊适配）

| SDK 类别 | suggested_skill | 典型 SDK |
|---------|----------------|---------|
| **微信 SDK（登录/分享/支付）** | `arkts-login`, `arkts-payment`, `arkts-share` | WechatOpenSDK |
| **支付宝 SDK（登录/支付）** | `arkts-login`, `arkts-payment` | AlipaySDK |
| **Firebase（分析/推送/认证）** | `hmos-sdk-docs`（待适配） | Firebase iOS SDK |
| **友盟（统计/推送/分享）** | `hmos-sdk-docs`（待适配） | 友盟 SDK |
| **极光推送（JPush）** | `arkts-notification` | JPush iOS SDK |
| **个推推送** | `arkts-notification` | 个推 SDK |
| **高德地图** | `arkts-map` | AMapFoundationKit |
| **百度地图** | `arkts-map` | BaiduMapKit |
| **穿山甲广告** | `arkts-ad` | BUAdSDK |
| **腾讯云 IM** | `arkts-customer-service` | TXIMSDK |
| **融云 IM** | `arkts-customer-service` | RongIMKit |
| **Lottie 动画** | `arkts-animation-migrate` | lottie-ios |

---

## 匹配规则

**优先级**（由高到低）：

1. **精确匹配**: feature spec 中提到的具体框架名（如 "SwiftUI", "CoreData", "WKWebView"）
2. **类别匹配**: 业务类别关键词（如 "登录", "支付", "地图"）
3. **SDK 匹配**: 典型 SDK 名称（如 "微信 SDK", "Alamofire", "Kingfisher"）

**未命中本表的 SDK**（如自研、小众厂商、埋点、风控等本仓尚未覆盖类别）：
- 登记 `kind=thirdparty-sdk` placeholder
- `trigger_condition = <业务类别> SDK 入仓`（描述业务类别即可，不强依赖具体 skill 名；开发者后续可通过任一形式提供适配方案）
- 例：`trigger_condition = 埋点 SDK 入仓` / `trigger_condition = 风控 SDK 入仓` / `trigger_condition = TalkingData SDK 入仓`
- 适配方案到位的多种形式（任一命中即 resolved）：
  ① 新 skill 入仓 arkts-skills/skills/
  ② 私仓 har 包入仓 oh_modules/
  ③ 官方 SDK 适配文档发布
  ④ 团队内部决策完成（记入 spec/migration-decisions.md）

---

## 基于 meta.json 字段的强绑规则（HARD-RULE）

以下规则**基于 meta.json 字段而非词汇匹配触发**，比词汇触发更可靠（不依赖 spec 文档措辞）。这类规则用于解决「iOS 源码无信号但 HarmonyOS 必须显式」的范式差异。

### Rule IS-1: 全屏页 ⇒ 必须绑 arkts-immersive-safearea

**触发条件**：Slice 涉及的任一 page 的 `meta.json` 满足：

```json
{
  "page_type": "full_screen_page",
  "needs_immersive_safearea": true
}
```

**强绑 skill**：`arkts-immersive-safearea`

**说明**：
- `page_type` 由 `ios-ui-graph-builder/scripts/synthesize_meta_json.py` 的 `detect_page_type()` 自动判定（4 类：`full_screen_page` / `modal_overlay` / `sheet` / `sub_component`）
- 不依赖词汇匹配——即使 spec / Slice 任务描述里完全没出现「沉浸式」「安全区」等关键词，只要任一 page 是 `full_screen_page`，本 skill 必须出现在 suggested_skills
- 设计依据：iOS SwiftUI 默认自动处理安全区（.safeAreaInset），源码层面无信号；HarmonyOS 全屏页必须显式四件套，否则系统栏遮挡内容

**校验时机**：i2h-plan §7 coverage-matrix 输出前；缺绑 → plan FAIL。

---

## iOS 特定强绑规则

### Rule iOS-1: SwiftUI @EnvironmentObject ⇒ 必须绑 arkts-state-manager

**触发条件**：feature spec 或 page spec 中包含 `@EnvironmentObject` 使用

**强绑 skill**：`arkts-state-manager`

**说明**：需要正确处理全局状态的注入和传递

### Rule iOS-2: CoreData / SwiftData ⇒ 必须绑 arkts-data-layer

**触发条件**：feature spec 中提到 CoreData 或 SwiftData

**强绑 skill**：`arkts-data-layer`

**说明**：数据模型迁移和关系管理需要专门处理

### Rule iOS-3: WKWebView ⇒ 必须绑 arkts-webview

**触发条件**：feature spec 中包含 WKWebView 或 WebKit 使用

**强绑 skill**：`arkts-webview`

**说明**：需要处理 JS 交互、Cookie 管理、导航控制等

---

## 风格 Skills 追加（style_set != none 时）

读取 spec 文档 `style_set` 字段（缺失视为 `none`）：`none` → 不追加；非 none（如 `wfhc-standard`）→ 按 task 领域从风格集选取追加：

| Task 内容 | 追加的风格 Skill |
|-----------|-----------------|
| UI 页面 / 组件 | style-set 中 domain=ui 的风格 skill |
| 状态管理 / ViewModel | domain=state |
| 导航 / 路由 | domain=navigation |
| 网络请求 | domain=data |
| 项目结构 / 配置 | domain=engineering |
| 特殊领域（扫描等） | domain=system |

选取依据：扫描 skills 目录中 frontmatter `style-set` 值匹配的条目，按 `domain` 字段与 task 领域匹配；一个 task 可追加多个。风格 skills 追加在 domain skills 之后（风格规则叠加而非覆盖基线）。

---

## 使用示例

### 示例 1: SwiftUI 页面转换

**Feature Spec 内容**：
```markdown
## 技术栈
- SwiftUI View
- @State 本地状态
- List 列表展示
```

**匹配结果**：
- Step 3a (UI 补充): `i2h-swiftui-converter` ✅ 默认
- Step 3b (ViewModel): `arkts-state-manager` ✅ 默认
- Step 3c (数据层): `arkts-data-layer` ✅ 默认

### 示例 2: CoreData 数据存储

**Feature Spec 内容**：
```markdown
## 数据存储
- CoreData
- NSManagedObject 模型
- NSFetchRequest 查询
```

**匹配结果**：
- Step 3c (数据层): `arkts-data-layer` ✅ 命中 "CoreData"
- **强绑**: `arkts-data-layer` (Rule iOS-2)

### 示例 3: 微信登录

**Feature Spec 内容**：
```markdown
## 登录方式
- 微信 SDK 登录
- WechatOpenSDK
```

**匹配结果**：
- Step 3b (ViewModel): `arkts-state-manager` ✅ 默认
- Step 3b (suggested_skills+): `arkts-login` ✅ 命中 "微信 SDK 登录"
- **不登记 placeholder**（命中本表）

### 示例 4: 未知 SDK（需要占位）

**Feature Spec 内容**：
```markdown
## 统计分析
- TalkingData SDK
- 自定义埋点
```

**匹配结果**：
- ❌ 未命中本表
- ✅ 登记 placeholder:
  - P-ID: P-S3-001
  - kind: thirdparty-sdk
  - trigger_condition: `TalkingData 统计 SDK 入仓`

---

## 模板版本

**版本**: v1.0  
**适配平台**: iOS → HarmonyOS  
**基于**: Android a2h-plan skill-binding-rules.md  
**最后更新**: 2024-11-03
