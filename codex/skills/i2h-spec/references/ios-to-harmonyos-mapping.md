<!-- when: Phase A/B/C 分析 iOS 组件、框架、API 时加载，判断 HarmonyOS 等价物 -->
<!-- topics: SwiftUI → ArkTS 映射、UIKit → ArkUI 映射、iOS Framework → HarmonyOS SDK 映射 -->

# iOS → HarmonyOS 核心映射规则

本文档定义 iOS 到 HarmonyOS 的核心映射关系，供 LLM 在分析和生成 spec 时参考。

## 1. SwiftUI → ArkTS UI 组件映射

### 布局容器

| iOS (SwiftUI) | HarmonyOS (ArkTS) | 映射说明 |
|--------------|------------------|---------|
| `VStack` | `Column` | 垂直布局，参数名不同 |
| `HStack` | `Row` | 水平布局，参数名不同 |
| `ZStack` | `Stack` | 层叠布局，对齐方式语法不同 |
| `List` | `List` | 列表组件，数据源方式不同 |
| `ScrollView` | `Scroll` | 滚动容器，轴向参数不同 |
| `LazyVStack` | `Column` + `LazyForEach` | 懒加载需要配合数据源 |
| `LazyHStack` | `Row` + `LazyForEach` | 懒加载需要配合数据源 |
| `Grid` | `Grid` | 网格布局，API 相似 |

**映射细节**：

```swift
// iOS SwiftUI
VStack(alignment: .leading, spacing: 20) {
  Text("Hello")
  Text("World")
}
```

```typescript
// HarmonyOS ArkTS
Column({ space: 20 }) {
  Text("Hello")
  Text("World")
}
.alignItems(HorizontalAlign.Start)
```

### 基础组件

| iOS (SwiftUI) | HarmonyOS (ArkTS) | 映射说明 |
|--------------|------------------|---------|
| `Text` | `Text` | 基本相同，修饰符不同 |
| `Button` | `Button` | 事件处理语法不同 |
| `Image` | `Image` | 资源引用方式不同 |
| `TextField` | `TextInput` | 绑定方式不同 |
| `SecureField` | `TextInput({ type: InputType.Password })` | 类型参数指定 |
| `Toggle` | `Toggle` | 基本相同 |
| `Slider` | `Slider` | 基本相同 |
| `Stepper` | 无直接等价 | 需自定义组合 |
| `Picker` | `Select` | API 差异较大 |
| `DatePicker` | `DatePicker` | API 相似 |
| `ProgressView` | `Progress` / `LoadingProgress` | 根据类型选择 |

### 导航组件

| iOS (SwiftUI) | HarmonyOS (ArkTS) | 映射说明 |
|--------------|------------------|---------|
| `NavigationStack` | `Navigation` | 导航容器，API 差异大 |
| `NavigationLink` | `NavDestination` | 导航目标，需配合 Navigation |
| `TabView` | `Tabs` | 选项卡容器，API 相似 |
| `.sheet` | `.bindSheet` | 模态弹窗，绑定方式不同 |
| `.alert` | `.alertDialog` | 警告弹窗，参数不同 |
| `.confirmationDialog` | `.actionSheet` | 动作表单，API 不同 |

**导航映射示例**：

```swift
// iOS SwiftUI
NavigationStack {
  NavigationLink("Detail", value: item) {
    Text("Go to detail")
  }
  .navigationDestination(for: Item.self) { item in
    DetailView(item: item)
  }
}
```

```typescript
// HarmonyOS ArkTS
@Entry
@Component
struct HomePage {
  pathStack: NavPathStack = new NavPathStack()
  
  build() {
    Navigation(this.pathStack) {
      Button("Go to detail")
        .onClick(() => {
          this.pathStack.pushPathByName("DetailPage", item)
        })
    }
  }
}

@Builder
function DetailPage(item: Item) {
  // Detail page content
}
```

## 2. 状态管理映射

| iOS (SwiftUI) | HarmonyOS (ArkTS) | 映射说明 |
|--------------|------------------|---------|
| `@State` | `@State` | 组件内状态，语法相似 |
| `@Binding` | `@Link` | 双向绑定，名称不同 |
| `@ObservedObject` | `@ObjectLink` | 对象观察，需配合 @Observed |
| `@StateObject` | `@State` + `@Observed` | 对象所有权，组合实现 |
| `@EnvironmentObject` | `@Provide` / `@Consume` | 环境注入，机制不同 |
| `@Environment` | `@StorageLink` / `@Consume` | 系统环境，分情况映射 |
| `@AppStorage` | `@StorageLink` | 持久化状态，API 相似 |

**状态映射示例**：

```swift
// iOS SwiftUI
@State private var count: Int = 0
@Binding var message: String
@ObservedObject var store: DataStore
```

```typescript
// HarmonyOS ArkTS
@State count: number = 0
@Link message: string
@ObjectLink store: DataStore
```

## 3. 修饰符映射

### 布局修饰符

| iOS (SwiftUI) | HarmonyOS (ArkTS) | 映射说明 |
|--------------|------------------|---------|
| `.frame(width:height:)` | `.width().height()` | 分开设置 |
| `.padding()` | `.padding()` | 相似，单位不同（pt vs vp）|
| `.background()` | `.backgroundColor()` | 名称略不同 |
| `.cornerRadius()` | `.borderRadius()` | 名称不同 |
| `.shadow()` | `.shadow()` | API 相似 |
| `.offset()` | `.offset()` | 相同 |
| `.rotationEffect()` | `.rotate()` | 名称简化 |
| `.scaleEffect()` | `.scale()` | 名称简化 |

### 样式修饰符

| iOS (SwiftUI) | HarmonyOS (ArkTS) | 映射说明 |
|--------------|------------------|---------|
| `.font()` | `.fontSize().fontFamily()` | 分开设置 |
| `.foregroundColor()` | `.fontColor()` | 针对文本 |
| `.bold()` | `.fontWeight(FontWeight.Bold)` | 参数形式 |
| `.italic()` | `.fontStyle(FontStyle.Italic)` | 参数形式 |

## 4. 数据存储映射

| iOS | HarmonyOS | 映射说明 |
|-----|-----------|---------|
| `UserDefaults` | `@ohos.data.preferences` | 键值对存储 |
| `SwiftData` | `@ohos.data.relationalStore` | 关系型数据库 |
| `Core Data` | `@ohos.data.relationalStore` | 关系型数据库 |
| `FileManager` | `@ohos.file.fs` | 文件系统 |
| `Keychain` | `@ohos.security.keystore` | 密钥存储 |

**UserDefaults 映射示例**：

```swift
// iOS
UserDefaults.standard.set(value, forKey: "key")
let value = UserDefaults.standard.string(forKey: "key")
```

```typescript
// HarmonyOS
import preferences from '@ohos.data.preferences'

let prefs = await preferences.getPreferences(context, 'myStore')
await prefs.put('key', value)
let value = await prefs.get('key', '')
```

## 5. 网络请求映射

| iOS | HarmonyOS | 映射说明 |
|-----|-----------|---------|
| `URLSession` | `@ohos.net.http` | HTTP 请求 |
| `URLRequest` | `http.HttpRequest` | 请求对象 |
| `JSONDecoder` | `JSON.parse()` | JSON 解析 |
| `async/await` | `async/await` | 异步语法相同 |

**网络请求映射示例**：

```swift
// iOS
let url = URL(string: "https://api.example.com/data")!
let (data, _) = try await URLSession.shared.data(from: url)
let result = try JSONDecoder().decode(Model.self, from: data)
```

```typescript
// HarmonyOS
import http from '@ohos.net.http'

let request = http.createHttp()
let response = await request.request('https://api.example.com/data')
let result: Model = JSON.parse(response.result as string)
```

## 6. 系统功能映射

| iOS 功能 | HarmonyOS 模块 | 映射说明 |
|---------|---------------|---------|
| Camera | `@ohos.multimedia.camera` | 相机 |
| Photo Library | `@ohos.file.photoAccessHelper` | 照片访问 |
| Location | `@ohos.geoLocationManager` | 位置服务 |
| Notifications | `@ohos.notificationManager` | 通知 |
| Background Tasks | `@ohos.resourceschedule.backgroundTaskManager` | 后台任务 |
| App Lifecycle | `UIAbility` lifecycle | 应用生命周期 |

## 7. 权限映射

| iOS (Info.plist) | HarmonyOS (module.json5) | 说明 |
|-----------------|--------------------------|------|
| `NSCameraUsageDescription` | `ohos.permission.CAMERA` | 相机权限 |
| `NSPhotoLibraryUsageDescription` | `ohos.permission.READ_MEDIA` | 照片读取 |
| `NSLocationWhenInUseUsageDescription` | `ohos.permission.APPROXIMATELY_LOCATION` | 位置权限 |
| `NSUserNotificationsUsageDescription` | `ohos.permission.NOTIFICATION` | 通知权限 |

## 8. 不支持的功能

以下 iOS 功能在 HarmonyOS 中**没有直接等价物**，需要替代方案：

| iOS 功能 | 状态 | 替代方案 |
|---------|------|---------|
| `UIViewRepresentable` (UIKit 集成) | ❌ 不支持 | 必须完全重写为 ArkTS |
| `AppIntents` | ❌ 不支持 | 使用 HarmonyOS 意图框架 |
| `WidgetKit` | ❌ 不同机制 | 使用 HarmonyOS 卡片框架 |
| `StoreKit` (IAP) | ❌ 不同机制 | 华为应用内支付 SDK |
| `iCloud` | ❌ 不支持 | 华为云服务或自建后端 |

## 9. 映射复杂度评估规则

LLM 在分析组件时，按以下规则评估迁移复杂度：

### Simple（简单）
- 纯展示型 View（只有 Text、Image、基础布局）
- 无状态或只有简单 @State
- 无导航或只有简单 NavigationLink
- 无系统功能调用
- **预估自动转换率**: 85%+

### Medium（中等）
- 有状态管理（@State、@Binding）
- 有列表和交互（List、Button、TextField）
- 有简单导航（NavigationStack、.sheet）
- 有简单数据存储（UserDefaults）
- **预估自动转换率**: 60-85%

### Complex（复杂）
- 复杂状态管理（@ObservedObject、@EnvironmentObject）
- 有数据库操作（SwiftData、Core Data）
- 有网络请求
- 有系统功能（Camera、Location、Notifications）
- 有 UIKit 集成（UIViewRepresentable）
- **预估自动转换率**: 30-60%

### Very Complex（极复杂）
- 深度 UIKit 集成
- 自定义动画和手势
- 复杂的并发逻辑
- 第三方 SDK 集成
- iCloud、StoreKit 等 iOS 独有功能
- **预估自动转换率**: < 30%，可能需要完全重写

## 10. 使用指南

### Phase A（数据准备）
- 识别 iOS 组件类型（SwiftUI/UIKit）
- 查表确定 HarmonyOS 等价物是否存在
- 标记不支持的功能

### Phase B（UI 清单）
- 为每个组件标注对应的 HarmonyOS 组件
- 评估映射复杂度（simple/medium/complex）
- 标记需要替代方案的功能

### Phase C（功能 Spec）
- 详细说明映射策略
- 对于不支持的功能，提出替代方案
- 评估数据迁移需求（如 SwiftData → 关系型数据库）

## 11. 更新机制

本映射表基于：
- HarmonyOS NEXT API 12
- iOS 17+ SwiftUI

随着 HarmonyOS SDK 更新，映射关系可能变化。发现新的映射关系或变更时，应更新本文档。
