<!-- Phase B: UI 清单总览模板 -->
<!-- 用于生成 spec/baseline/ui-manifest.md -->

# UI 清单

**项目**: {项目名称}  
**生成时间**: {ISO 8601 时间戳}  
**数据来源**: Phase A - iOS 项目扫描  
**Confidence**: {overall confidence: high/medium/low}

---

## 1. 全局约定

### 页面 ID 命名规则

- **格式**: `page_NNNN_ClassName`
- **示例**: `page_0001_HomeView`, `page_0002_SettingsView`
- **规则**: 
  - NNNN 从 0001 开始递增
  - ClassName 是 iOS 源码中的实际类名
  - SwiftUI View 和 UIKit ViewController 共用序列

### 复杂度评级标准

| 级别 | 条件 | 特征 | 预估转换率 |
|------|------|------|-----------|
| `simple` | 代码 < 50 行 | 纯展示、无状态或简单状态、无系统功能 | 85%+ |
| `medium` | 50-150 行 | 有状态管理、列表交互、简单导航、UserDefaults | 60-85% |
| `complex` | 150-300 行 | 复杂状态、数据库、网络请求、系统功能 | 30-60% |
| `very_complex` | > 300 行 | UIKit 集成、自定义动画、第三方 SDK、iOS 独有功能 | < 30% |

### Confidence 评级说明

| 级别 | 数据来源 | 说明 |
|------|---------|------|
| `high` | Python 脚本提取 + LLM 验证 | 所有字段完整、源码路径已验证 |
| `medium` | LLM 扫描生成 | 基于代码推断，可能有遗漏 |
| `low` | 部分源文件缺失 | 需要人工补充或实际运行验证 |

---

## 2. SwiftUI Views 清单

| # | Page ID | View 名称 | 文件路径 | 属性数 | 复杂度 | 行数 | Confidence |
|---|---------|----------|---------|--------|--------|------|-----------|
| 1 | page_0001 | HomeView | App/Views/HomeView.swift | 5 | medium | 80 | high |
| 2 | page_0002 | SettingsView | App/Views/SettingsView.swift | 3 | simple | 45 | high |
| 3 | page_0003 | BeanDetailView | App/Views/BeanDetailView.swift | 4 | medium | 120 | medium |

**说明**：
- **属性数**：包含 @State、@Binding、@ObservedObject 等状态管理属性的总数
- **复杂度**：按上述评级标准判定
- **Confidence**：数据准确度评级

### 复杂度分布

```
simple (< 50行):        5 个 (45%)
medium (50-150行):      4 个 (36%)
complex (150-300行):    2 个 (18%)
very_complex (> 300行): 0 个 (0%)
```

---

## 3. UIKit ViewControllers 清单

| # | Page ID | ViewController | 文件路径 | 复杂度 | 行数 | Confidence |
|---|---------|---------------|---------|--------|------|-----------|
| 1 | page_0012 | ScanViewController | App/Services/ScanViewController.swift | complex | 200 | medium |

**说明**：
- UIKit ViewControllers 通常评级为 `complex` 或 `very_complex`
- 需要完全重写为 ArkTS，无法使用模板转换器

### 迁移策略

UIKit ViewControllers 的迁移策略：

1. **分析功能**: 理解 ViewController 的核心功能
2. **设计 ArkTS 方案**: 使用 ArkTS 组件重新设计
3. **手动实现**: 无法自动转换，需要完全手动编写
4. **功能验证**: 确保行为与 iOS 版本一致

---

## 4. 页面关系图

### 导航层次

```
App (根入口)
 ├─ TabView
 │   ├─ HomeView (tab 1)
 │   │   └─ BeanDetailView (NavigationLink)
 │   │       └─ EditBeanView (sheet)
 │   ├─ RecipesView (tab 2)
 │   │   └─ RecipeDetailView (NavigationLink)
 │   └─ SettingsView (tab 3)
 │       └─ AboutView (NavigationLink)
 └─ ScanViewController (modal, UIKit)
```

### 导航方式统计

| 导航方式 | iOS 实现 | 数量 | HarmonyOS 映射 |
|---------|---------|------|---------------|
| Tab 切换 | `TabView` | 1 处 | `Tabs` |
| 页面跳转 | `NavigationLink` | 6 处 | `NavPathStack.push()` |
| 模态弹窗 | `.sheet()` | 3 处 | `.bindSheet()` |
| 全屏模态 | `.fullScreenCover()` | 1 处 | `.bindContentCover()` |

---

## 5. 状态管理总览

### 状态管理模式统计

| 模式 | iOS 包装器 | 使用次数 | HarmonyOS 映射 |
|------|-----------|---------|---------------|
| 局部状态 | `@State` | 23 | `@State` |
| 双向绑定 | `@Binding` | 12 | `@Link` |
| 对象观察 | `@ObservedObject` | 5 | `@ObjectLink` |
| 对象所有权 | `@StateObject` | 3 | `@State` + `@Observed` |
| 环境注入 | `@EnvironmentObject` | 2 | `@Provide` / `@Consume` |
| 持久化状态 | `@AppStorage` | 4 | `@StorageLink` |

### 全局数据存储

| Store | 类型 | 说明 | 迁移目标 |
|-------|------|------|---------|
| `BeanStore` | SwiftData | 咖啡豆数据管理 | 鸿蒙关系型数据库 (F001) |
| `RecipeStore` | SwiftData | 配方数据管理 | 鸿蒙关系型数据库 (F001) |
| `Settings` | UserDefaults | 用户偏好设置 | Preferences (F003) |

---

## 6. 系统功能使用

### 系统功能清单

| 功能 | iOS API | 使用位置 | HarmonyOS 映射 | 权限要求 |
|------|---------|---------|---------------|---------|
| 相机 | `AVFoundation` | ScanViewController | `@ohos.multimedia.camera` | Camera |
| 通知 | `UNUserNotificationCenter` | NotificationService | `@ohos.notificationManager` | Notification |
| 定位 | (未使用) | - | - | - |

### Info.plist 权限映射

| iOS 权限 | 说明 | HarmonyOS 权限 |
|---------|------|---------------|
| `NSCameraUsageDescription` | 相机访问 | `ohos.permission.CAMERA` |
| `NSUserNotificationsUsageDescription` | 通知权限 | `ohos.permission.NOTIFICATION` |

---

## 7. 转换批次规划

### 批次划分原则

- **Batch 1**: 简单页面，无依赖，优先转换（验证工具链）
- **Batch 2**: 中等复杂度，有基础依赖
- **Batch 3**: 复杂页面，依赖数据层和系统功能
- **Batch 4**: UIKit 页面，需要完全重写

### 批次清单

| 批次 | 页面数 | 页面列表 | 依赖 | 预计用时 |
|------|--------|---------|------|---------|
| Batch 1 | 3 | SettingsView, AboutView, HelpView | 无 | 2-3 小时 |
| Batch 2 | 4 | HomeView, RecipesView, ProfileView, StatsView | UserDefaults (F003) | 4-6 小时 |
| Batch 3 | 3 | BeanDetailView, RecipeDetailView, EditBeanView | SwiftData (F001), Camera (F101) | 8-12 小时 |
| Batch 4 | 1 | ScanViewController | 完全重写 | 6-8 小时 |

---

## 8. 共享组件

### 自定义组件清单

| 组件名称 | 文件路径 | 使用次数 | 复杂度 | 说明 |
|---------|---------|---------|--------|------|
| `BeanCard` | Components/BeanCard.swift | 2 | simple | 咖啡豆卡片展示 |
| `RecipeCard` | Components/RecipeCard.swift | 1 | simple | 配方卡片展示 |
| `AddButton` | Components/AddButton.swift | 3 | simple | 统一样式的添加按钮 |

**迁移策略**：
- 共享组件在 Stage 1 优先转换
- 作为独立的 `@Component` 供多个页面复用

---

## 9. 资源清单

### 图片资源

- **位置**: `Assets.xcassets/`
- **数量**: 15 个 .imageset
- **类型**: 图标、logo、占位图
- **迁移**: 需要转换为鸿蒙资源格式（.png → resources/base/media/）

### 颜色资源

- **位置**: `Assets.xcassets/Colors/`
- **数量**: 8 个 .colorset
- **包含**: 主题色、深色模式适配
- **迁移**: 转换为 ArkTS 颜色变量或资源文件

### 本地化字符串

- **支持语言**: 英语 (en), 中文 (zh-Hans)
- **位置**: `Localizable.strings`
- **迁移**: 转换为鸿蒙多语言资源

---

## 10. 统计摘要

### 页面统计

- **SwiftUI Views**: 11 个
- **UIKit ViewControllers**: 1 个
- **总页面数**: 12 个

### 代码规模

- **总代码行数**: 1,878 行
- **SwiftUI 代码**: 1,200 行 (64%)
- **UIKit 代码**: 200 行 (11%)
- **其他代码**: 478 行 (25%)

### 转换预估

- **预估自动转换率**: 68% (基于复杂度加权平均)
- **需要人工调整**: 32%
- **预计总用时**: 20-29 小时

---

## 11. 风险提示

### 高风险项

- ⚠️ **SwiftData 迁移**: 需要完全重新设计数据层（F001）
- ⚠️ **UIKit 重写**: ScanViewController 需要完全手动实现
- ⚠️ **导航复杂度**: NavigationStack 映射到 NavPathStack 需要仔细处理

### 技术债务

- iOS 版本中已知的 bug 或性能问题
- 可以在迁移时修复的设计缺陷

---

## 12. 下一步

1. ✅ Phase A 完成 — iOS 项目数据准备
2. ✅ Phase B 完成 — UI 清单生成（本文档）
3. ⏭️ **Phase B.2** — 生成分页 spec（`spec/baseline/ui/page_*.md`）
4. ⏭️ **Phase C** — 功能 Spec 生成（`spec/baseline/features/`）

---

**文档版本**: v1.0  
**最后更新**: {时间戳}
