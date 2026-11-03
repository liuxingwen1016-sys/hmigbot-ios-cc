<!-- Phase B: 分页 UI Spec 模板 -->
<!-- 用于生成每个页面的详细规格文档 -->

# {PageName} ({PageID})

## 基本信息

**必填字段**（不得省略）：

- **Page ID**: `{page_NNNN}` — 页面唯一标识符，格式：page_0001, page_0002, ...
- **iOS 类名**: `{ClassName}` — SwiftUI View 或 UIKit ViewController 名称
- **文件路径**: `{相对于 iOS 项目根的路径}` — 如 `Cuike/Views/HomeView.swift`
- **类型**: `SwiftUI View` | `UIKit ViewController`
- **复杂度**: `simple` | `medium` | `complex` | `very_complex`
- **行数**: `{实际代码行数}`
- **Confidence**: `high` | `medium` | `low` — 数据准确度评级

## iOS 源码锚点 (ios_source_anchors)

**强约束**：`complexity=complex` 或 `very_complex` 的页面**必须**填写此 YAML，不得占位。

```yaml
ios_source_anchors:
  primary_file: "Cuike/Views/HomeView.swift"
  related_files:
    - "Cuike/Models/Bean.swift"
    - "Cuike/Services/BeanStore.swift"
  key_symbols:
    - "HomeView.body"
    - "BeanStore.fetchBeans()"
  info_plist_keys:
    - "NSCameraUsageDescription"
```

**验证规则**：
- `primary_file` 必须是实际存在的文件路径
- `related_files` 中的路径必须逐条验证存在
- `key_symbols` 是重要的函数/属性名，供下游追溯

## 页面结构

**强约束**：本段非空行必须 ≥ 5 行，不得用 "TODO" 或 "待补充" 占位。

### 主容器

描述页面的主容器类型和布局方式：

```
iOS: VStack(alignment: .leading, spacing: 20)
HarmonyOS: Column({ space: 20 }).alignItems(HorizontalAlign.Start)
```

### UI 层次

列出完整的 UI 层级结构（至少 2 层嵌套）：

```
VStack
  ├─ NavigationBar (顶部导航)
  ├─ List (主内容区)
  │   └─ ForEach
  │       └─ BeanCard (自定义卡片组件)
  └─ Button (底部操作按钮)
```

### 关键组件

列出页面中的关键 UI 组件及其作用：

| 组件 | iOS 实现 | HarmonyOS 映射 | 作用 |
|------|---------|---------------|------|
| 列表 | `List` | `List` | 显示咖啡豆列表 |
| 卡片 | `BeanCard` (自定义) | 自定义 `@Component` | 单个咖啡豆展示 |
| 导航链接 | `NavigationLink` | `NavDestination` | 跳转到详情页 |
| 添加按钮 | `Button` | `Button` | 打开添加 sheet |

## 状态管理

### 状态变量

列出所有状态变量及其映射：

| iOS 变量 | 类型 | 包装器 | HarmonyOS 映射 | 说明 |
|---------|------|--------|---------------|------|
| `beanStore` | `BeanStore` | `@ObservedObject` | `@ObjectLink` | 咖啡豆数据存储 |
| `showingAddSheet` | `Bool` | `@State` | `@State` | 控制添加表单显示 |
| `selectedBean` | `Bean?` | `@State` | `@State` | 当前选中的咖啡豆 |

### 数据流

描述数据流向：

```
父组件 (App)
  ↓ @EnvironmentObject
HomeView (@ObservedObject beanStore)
  ↓ 传递
BeanCard (@Binding bean)
```

**HarmonyOS 映射**：
```
父组件
  ↓ @Provide
HomeView (@Consume beanStore)
  ↓ @Link
BeanCard (@Link bean)
```

## 交互行为

列出所有用户交互及其处理逻辑：

### 导航交互

| 触发 | iOS 实现 | 目标 | HarmonyOS 实现 |
|------|---------|------|---------------|
| 点击咖啡豆卡片 | `NavigationLink(value: bean)` | `BeanDetailView` | `NavPathStack.pushPathByName("BeanDetail", bean)` |
| 点击返回 | 自动 | 上一页 | `NavPathStack.pop()` |

### 操作交互

| 触发 | 动作 | iOS 代码片段 | HarmonyOS 实现 |
|------|------|------------|---------------|
| 点击添加按钮 | 打开添加表单 | `.sheet(isPresented: $showingAddSheet)` | `.bindSheet($showingAddSheet)` |
| 滑动删除 | 删除咖啡豆 | `.onDelete { beanStore.delete(...) }` | `.swipeAction() { ... }` |

### 生命周期

iOS 和 HarmonyOS 生命周期映射：

| iOS | HarmonyOS | 用途 |
|-----|-----------|------|
| `.onAppear { ... }` | `onPageShow()` | 页面显示时加载数据 |
| `.onDisappear { ... }` | `onPageHide()` | 页面隐藏时保存状态 |
| `.task { ... }` | `aboutToAppear() { ... }` | 异步任务初始化 |

## 转换策略

### 适用转换器

选择适用的转换器类型：

- **Template Converter**: ✅ 适用于结构简单、有标准映射的页面
- **Semantic Converter**: ⚠️ 适用于中等复杂度、需要语义理解的页面
- **Manual Conversion**: ❌ 需要完全手动重写（如深度 UIKit 集成）

**本页面选择**: {选择的转换器及理由}

### 预估转换率

- **自动转换率**: {百分比，如 85%}
- **需要人工调整**:
  - {调整项 1}
  - {调整项 2}
  - {调整项 3}

### 转换难点

列出预期的转换难点和应对策略：

| 难点 | 原因 | 应对策略 |
|------|------|---------|
| Sheet 弹窗 | API 差异大 | 使用 `.bindSheet()` 替代 `.sheet()` |
| NavigationLink 绑定 | 导航机制不同 | 使用 `NavPathStack` 手动管理 |

## 依赖关系

### 组件依赖

列出依赖的自定义组件：

- `BeanCard` — 咖啡豆卡片组件
- `AddBeanSheet` — 添加咖啡豆表单

### 数据依赖

列出依赖的数据层：

- `BeanStore` — 咖啡豆数据存储（SwiftData）
  - **迁移目标**: 鸿蒙关系型数据库
  - **依赖功能**: F001-数据存储

### 系统依赖

列出依赖的系统功能（如有）：

- 无 / {列出系统功能，如 Camera、Location}

## 风险评估

### 技术风险

| 风险 | 等级 | 说明 | 缓解措施 |
|------|------|------|---------|
| SwiftData 迁移 | 🟡 Medium | SwiftData 到关系型数据库需要重新设计 | 先完成 F001 功能 spec |
| 导航栈管理 | 🟡 Medium | NavigationStack 映射较复杂 | 使用 NavPathStack 统一管理 |

### 数据迁移风险

如果涉及数据库：

- **迁移策略**: {详细说明}
- **数据兼容性**: {是否需要数据转换}

### 性能风险

- **列表性能**: 如果列表很长，需要使用 `LazyForEach` 优化
- **图片加载**: 异步加载和缓存策略

## 占位策略

如果页面依赖未完成的功能模块，说明占位策略：

- **Kind**: `data-layer-pending` | `api-pending` | `system-feature-pending`
- **Trigger**: 在哪个 Stage 触发真实实现
- **Fallback**: Stage 1-2 期间的替代方案（Mock 数据、静态展示等）

## 验证清单

转换完成后的验证项：

- [ ] 布局结构与 iOS 版本一致
- [ ] 所有交互行为正常工作
- [ ] 状态管理正确（数据双向绑定）
- [ ] 导航流程完整
- [ ] 性能满足要求（列表滚动流畅）
- [ ] 适配深色模式（如 iOS 版本支持）

## 备注

其他需要说明的内容（可选）：

- 特殊的设计考虑
- 已知的 iOS 版本 bug
- 未来优化方向

---

**模板使用说明**：

1. **必填字段**：所有标记"必填"的字段不得省略或用 TODO 占位
2. **结构完整性**：`## 页面结构` 段落必须有实质内容（非空行 ≥ 5）
3. **ios_source_anchors**：复杂页面（complex/very_complex）必须填写完整的 YAML
4. **验证路径**：所有文件路径必须在写入前验证存在
5. **下游强约束**：此 spec 是 a2h-plan 和 a2h-execute 的输入，缺失关键字段会导致下游失败
