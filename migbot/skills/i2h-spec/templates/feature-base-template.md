<!-- Phase C: 功能基础设施模板 -->
<!-- 用于生成 spec/baseline/feature-base.md -->

# Feature Base: 共享基础设施

**项目**: {项目名称}  
**生成时间**: {ISO 8601 时间戳}

---

## 1. 数据模型

### 核心实体

列出所有核心数据模型及其关系。

#### {ModelName1} ({中文名称})

- **源文件**: `{iOS 源文件路径}`
- **类型**: SwiftData @Model | struct | class
- **字段**:
  - `id: UUID` - 唯一标识符
  - `name: String` - 名称
  - `{字段名}: {类型}` - {说明}
  - ...

**HarmonyOS 映射**:
```typescript
interface {ModelName} {
  id: string
  name: string
  {字段名}: {类型}
}
```

#### 实体间关系

```
ModelA 1:N ModelB
  ├─ A.items → [B]
  └─ B.parentId → A.id

ModelB N:1 ModelC
  └─ B.categoryId → C.id
```

---

## 2. 数据层

### 核心 Store/Repository

#### {StoreName} (iOS: {iOS 类名})

- **源文件**: `{iOS 源文件路径}`
- **职责**: {核心职责说明}
- **技术**: SwiftData | UserDefaults | FileManager

**核心接口**:

| iOS 方法 | HarmonyOS 映射 | 说明 |
|---------|---------------|------|
| `fetchItems() -> [Item]` | `getItems(): Promise<Item[]>` | 获取所有项目 |
| `addItem(_: Item)` | `addItem(item: Item): Promise<void>` | 添加项目 |
| `updateItem(_: Item)` | `updateItem(item: Item): Promise<void>` | 更新项目 |
| `deleteItem(_: Item)` | `deleteItem(id: string): Promise<void>` | 删除项目 |

**HarmonyOS 实现技术**:
- 使用 `@ohos.data.relationalStore` (关系型数据库)
- 使用 `@ohos.data.preferences` (键值对存储)
- 使用 `@ohos.file.fs` (文件存储)

---

## 3. 数据库设计（如适用）

### 表结构

如果 iOS 使用 SwiftData/Core Data，说明 HarmonyOS 对应的表结构：

```sql
-- {table_name} 表
CREATE TABLE {table_name} (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  {字段名} {类型},
  created_at INTEGER,
  FOREIGN KEY ({外键字段}) REFERENCES {关联表}(id)
);
```

### 索引

```sql
CREATE INDEX idx_{table}_{field} ON {table}({field});
```

### 数据迁移

如果需要从 iOS 迁移数据：

1. **导出策略**: 从 SwiftData 导出为 JSON
2. **转换策略**: 类型转换（Date → timestamp、枚举 → string）
3. **导入策略**: 批量插入 + 验证完整性

---

## 4. 网络层（如适用）

### API 基础设施

如果项目有网络请求：

#### iOS 实现
- 使用 `URLSession`
- 使用 `async/await`
- JSON 解码器

#### HarmonyOS 映射
- 使用 `@ohos.net.http`
- 使用 `Promise<T>`
- `JSON.parse()` + 类型断言

### 通用网络工具

```typescript
// HttpClient 封装
export class HttpClient {
  async get<T>(url: string): Promise<T>
  async post<T>(url: string, data: any): Promise<T>
  async put<T>(url: string, data: any): Promise<T>
  async delete(url: string): Promise<void>
}
```

### 错误处理

- 网络错误
- 超时处理
- 重试机制

---

## 5. 事件系统（如适用）

### iOS 实现
- 使用 `@Published` + `Combine`
- 使用 `NotificationCenter`
- 自定义 Observable

### HarmonyOS 映射
- 使用 `@ObservedV2` + `@Trace`
- 使用 `@Provide` / `@Consume`
- 自定义 EventBus

**事件定义示例**:

```typescript
// 事件类型
enum AppEvent {
  DataUpdated = 'data_updated',
  UserLoggedIn = 'user_logged_in',
  NavigationChanged = 'navigation_changed'
}

// 事件总线
export class EventBus {
  emit(event: AppEvent, data?: any): void
  on(event: AppEvent, callback: (data: any) => void): void
  off(event: AppEvent, callback: (data: any) => void): void
}
```

---

## 6. 偏好设置

### iOS 实现
- 使用 `@AppStorage`
- 使用 `UserDefaults`

### HarmonyOS 映射
- 使用 `@StorageLink`
- 使用 `@ohos.data.preferences`

**键值映射**:

| iOS Key | HarmonyOS Key | 类型 | 说明 |
|---------|--------------|------|------|
| `theme_mode` | `theme_mode` | string | 主题模式（light/dark/auto）|
| `language` | `language` | string | 语言偏好 |
| `{key}` | `{key}` | {type} | {说明} |

---

## 7. 权限声明

### iOS 权限（Info.plist）

| iOS 权限键 | 说明 | 用途 |
|-----------|------|------|
| `NSCameraUsageDescription` | 相机访问 | F101 相机扫描功能 |
| `NSLocationWhenInUseUsageDescription` | 位置访问 | F102 位置服务 |
| `{权限键}` | {说明} | {用途} |

### HarmonyOS 权限（module.json5）

```json5
"requestPermissions": [
  {
    "name": "ohos.permission.CAMERA",
    "reason": "$string:camera_reason",
    "usedScene": {
      "abilities": ["EntryAbility"],
      "when": "inuse"
    }
  },
  {
    "name": "ohos.permission.APPROXIMATELY_LOCATION",
    "reason": "$string:location_reason",
    "usedScene": {
      "abilities": ["EntryAbility"],
      "when": "inuse"
    }
  }
]
```

---

## 8. 导航系统

### iOS 导航架构

描述 iOS 的导航实现：

- **技术**: NavigationStack | TabView | Sheet | FullScreenCover
- **路由管理**: 使用全局 `AppRouter` 单例 / 分散在各页面
- **深度链接**: 支持 / 不支持

**AppRouter 接口**（如适用）:

```swift
class AppRouter: ObservableObject {
  @Published var tab: Int = 0
  @Published var showBrew: Bool = false
  @Published var path: NavigationPath = .init()
  
  func openRecipe(_ recipe: RecipeRecord, store: BrewStore)
  func showSettings()
}
```

### HarmonyOS 导航映射

```typescript
// 全局路由管理器
@ObservedV2
export class AppRouter {
  @Trace currentTab: number = 0
  @Trace showBrew: boolean = false
  navPathStack: NavPathStack = new NavPathStack()
  
  openRecipe(recipe: RecipeRecord, store: BrewStore): void {
    this.navPathStack.pushPathByName('RecipeEdit', { recipe, store })
  }
  
  showSettings(): void {
    this.navPathStack.pushPathByName('Settings', null)
  }
}
```

**导航模式**:
- Tab 切换：修改 `currentTab`
- 页面跳转：`navPathStack.pushPathByName()`
- Modal：`.bindSheet()` / `.bindContentCover()`

---

## 9. 公共组件库

### 自定义组件清单

列出所有可复用的自定义组件：

#### {ComponentName} ({中文名称})

- **源文件**: `{iOS 源文件路径}`
- **用途**: {组件用途说明}
- **使用次数**: {X} 处

**iOS 接口**:
```swift
struct {ComponentName}: View {
  let {param1}: {Type}
  let {param2}: {Type}
  var body: some View { ... }
}
```

**HarmonyOS 映射**:
```typescript
@Component
export struct {ComponentName} {
  {param1}: {Type}
  {param2}: {Type}
  
  build() {
    // 组件实现
  }
}
```

**使用位置**:
- page_0001_HomeView
- page_0002_LibraryView
- ...

---

## 10. 资源管理

### 图片资源

- **位置**: `Assets.xcassets/`
- **数量**: {X} 个 .imageset
- **类型**: 图标、logo、占位图

**迁移策略**:
- 导出为 .png 格式
- 放置到 `entry/src/main/resources/base/media/`
- 使用 `$r('app.media.{name}')` 引用

### 颜色资源

- **位置**: `Assets.xcassets/Colors/`
- **数量**: {X} 个 .colorset
- **支持**: 深色模式适配

**迁移策略**:
- 提取颜色值（hex/rgba）
- 定义为 ArkTS 常量或资源文件
- 使用 `$r('app.color.{name}')` 引用

### 本地化字符串

- **支持语言**: 英语 (en), 中文 (zh-Hans), ...
- **位置**: `Localizable.strings`

**迁移策略**:
- 转换为 `entry/src/main/resources/*/element/string.json`
- 使用 `$r('app.string.{key}')` 引用

---

## 11. 第三方依赖（如适用）

如果项目使用第三方 SDK：

| iOS 依赖 | 版本 | 用途 | HarmonyOS 替代方案 |
|---------|------|------|--------------------|
| Alamofire | 5.x | 网络请求 | @ohos.net.http (官方) |
| SDWebImage | 5.x | 图片加载 | 自定义图片缓存 |
| {SDK 名称} | {版本} | {用途} | {替代方案} |

---

## 12. 环境配置

### 开发环境

- **iOS 版本**: iOS 17+
- **Swift 版本**: Swift 5.9+
- **Xcode 版本**: Xcode 15+

### HarmonyOS 环境

- **API 版本**: API 12+
- **SDK 版本**: HarmonyOS NEXT
- **DevEco Studio**: 5.0+

---

## 13. 统计摘要

- **数据模型**: {X} 个
- **Store/Repository**: {X} 个
- **公共组件**: {X} 个
- **权限声明**: {X} 项
- **第三方依赖**: {X} 个

---

**文档版本**: v1.0  
**最后更新**: {时间戳}  
**维护**: 从各 feature spec 提取共享基础设施，避免重复描述
