<!-- Phase C: 分功能 Spec 模板 -->
<!-- 用于生成每个功能的详细规格文档 -->

# {FeatureID}: {功能名称}

## 基本信息

**必填字段**（不得省略）：

- **Feature ID**: `{FXXX}` — 功能唯一标识符，格式：F001, F002, ...
- **功能名称**: `{中文名称}` — 如"数据存储"、"相机扫描"
- **源文件**: `{文件路径列表}` — 相对于 iOS 项目根目录
- **技术栈**: `{iOS 使用的框架/技术}` — 如 SwiftData, AVFoundation
- **复杂度**: `low` | `medium` | `high` | `very_complex`
- **优先级**: `P0` (必须) | `P1` (重要) | `P2` (增强) | `P3` (可选)

## iOS 源码锚点 (ios_source_anchors)

**强约束**：`complexity=high` 或 `very_complex` 的功能**必须**填写此 YAML。

```yaml
ios_source_anchors:
  primary_files:
    - "App/Data/BeanStore.swift"
    - "App/Models/Bean.swift"
  key_types:
    - "BeanStore"
    - "Bean"
    - "Recipe"
  key_functions:
    - "BeanStore.fetchBeans()"
    - "BeanStore.addBean(_:)"
    - "BeanStore.deleteBean(_:)"
  frameworks:
    - "SwiftData"
  permissions:
    - "NSCameraUsageDescription"  # 如果需要系统权限
```

## iOS 实现分析

### 架构概览

描述 iOS 中此功能的实现架构（至少 3-5 行实质内容）：

```
BeanStore (ObservableObject)
  ↓ 管理
ModelContext (SwiftData)
  ↓ 操作
BeanRecord (Model)
  ├─ 属性: name, origin, roastLevel, ...
  └─ 关系: hasMany recipes
```

### 核心代码结构

列出关键的类/结构体及其职责：

| 类/结构体 | 类型 | 职责 | 代码行数 |
|----------|------|------|---------|
| `BeanStore` | `class` | 数据管理器，提供 CRUD 接口 | 150 |
| `Bean` | `struct` | 数据模型，定义咖啡豆属性 | 30 |
| `Recipe` | `struct` | 配方模型，关联咖啡豆 | 25 |

### 关键功能点

列出功能的具体能力：

1. **数据持久化**
   - 使用 SwiftData `@Model` 宏定义模型
   - 自动生成数据库表和关系
   - 支持查询、过滤、排序

2. **CRUD 操作**
   - 创建: `addBean(_ bean: Bean)`
   - 读取: `fetchBeans() -> [Bean]`
   - 更新: `updateBean(_ bean: Bean)`
   - 删除: `deleteBean(_ bean: Bean)`

3. **关系管理**
   - Bean ↔ Recipe 一对多关系
   - 级联删除支持

### 数据模型

详细列出数据模型的字段：

**Bean 模型**:
```swift
@Model
class Bean {
    var id: UUID
    var name: String
    var origin: String
    var roastLevel: RoastLevel
    var purchaseDate: Date
    var notes: String?
    
    @Relationship(deleteRule: .cascade)
    var recipes: [Recipe]
}
```

## HarmonyOS 迁移方案

### 目标框架

- **HarmonyOS 框架**: `@ohos.data.relationalStore`
- **映射类型**: 关系型数据库（非 ORM）
- **API 风格**: SQL-based + TypeScript

### 迁移策略

选择适用的迁移策略：

- **直接映射**: iOS 和 HarmonyOS API 相似，可直接对应
- **重新设计**: 需要根据 HarmonyOS 特性重新设计实现
- **完全重写**: iOS 特有功能，HarmonyOS 无等价物，需从头实现
- **替代方案**: 使用不同的技术实现相同功能

**本功能选择**: {策略及理由}

### 实现步骤

详细列出在 HarmonyOS 中实现此功能的步骤（至少 5 步）：

1. **定义数据表结构**
   - 创建 Bean 表：`id, name, origin, roast_level, purchase_date, notes`
   - 创建 Recipe 表：`id, bean_id, name, ...`
   - 定义外键关系

2. **创建数据库管理器**
   - 使用 `relationalStore.getRdbStore()` 初始化数据库
   - 实现表创建和版本迁移逻辑

3. **实现 CRUD 接口**
   - `addBean(bean: Bean): Promise<number>` — 插入记录
   - `getBeans(): Promise<Bean[]>` — 查询所有
   - `updateBean(bean: Bean): Promise<void>` — 更新记录
   - `deleteBean(id: string): Promise<void>` — 删除记录

4. **实现查询和过滤**
   - 使用 SQL predicates 实现筛选
   - 支持排序和分页

5. **实现关系管理**
   - 级联删除逻辑（删除 Bean 时同时删除关联 Recipe）
   - 关联查询（获取 Bean 时同时加载关联 Recipe）

6. **集成到 UI 层**
   - 使用 `@State` 管理数据
   - 实现数据变更通知机制

### 代码示例

提供关键实现的 ArkTS 代码示例：

```typescript
// HarmonyOS 数据管理器示例
import relationalStore from '@ohos.data.relationalStore'

export class BeanStore {
  private rdbStore: relationalStore.RdbStore | null = null
  
  async init(context: Context) {
    const config = {
      name: 'CuikeDB.db',
      securityLevel: relationalStore.SecurityLevel.S1
    }
    this.rdbStore = await relationalStore.getRdbStore(context, config)
    await this.createTables()
  }
  
  private async createTables() {
    const createBeanTable = `
      CREATE TABLE IF NOT EXISTS bean (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        origin TEXT,
        roast_level INTEGER,
        purchase_date INTEGER,
        notes TEXT
      )
    `
    await this.rdbStore.executeSql(createBeanTable)
  }
  
  async addBean(bean: Bean): Promise<number> {
    const valueBucket = {
      'id': bean.id,
      'name': bean.name,
      'origin': bean.origin,
      'roast_level': bean.roastLevel,
      'purchase_date': bean.purchaseDate.getTime(),
      'notes': bean.notes
    }
    return await this.rdbStore.insert('bean', valueBucket)
  }
  
  async getBeans(): Promise<Bean[]> {
    const predicates = new relationalStore.RdbPredicates('bean')
    const resultSet = await this.rdbStore.query(predicates)
    const beans: Bean[] = []
    
    while (resultSet.goToNextRow()) {
      beans.push({
        id: resultSet.getString(resultSet.getColumnIndex('id')),
        name: resultSet.getString(resultSet.getColumnIndex('name')),
        origin: resultSet.getString(resultSet.getColumnIndex('origin')),
        roastLevel: resultSet.getLong(resultSet.getColumnIndex('roast_level')),
        purchaseDate: new Date(resultSet.getLong(resultSet.getColumnIndex('purchase_date'))),
        notes: resultSet.getString(resultSet.getColumnIndex('notes'))
      })
    }
    resultSet.close()
    return beans
  }
}
```

## 数据迁移（如适用）

如果涉及数据库或持久化数据，说明迁移策略：

### 数据兼容性

- **iOS 数据格式**: SwiftData 存储（Core Data 派生）
- **HarmonyOS 数据格式**: SQLite 关系型数据库
- **兼容性**: ❌ 不直接兼容，需要转换

### 迁移工具

提供数据迁移方案：

1. **导出 iOS 数据**
   - 从 SwiftData 导出为 JSON 格式
   - 包含所有 Bean 和 Recipe 记录

2. **转换格式**
   - JSON → HarmonyOS 数据库格式
   - 处理日期、枚举等类型转换

3. **导入 HarmonyOS**
   - 使用批量插入 API
   - 保持数据关系完整性

### 迁移脚本示例

```typescript
async function migrateiOSData(jsonData: string) {
  const data = JSON.parse(jsonData)
  const beanStore = new BeanStore()
  
  for (const bean of data.beans) {
    await beanStore.addBean({
      id: bean.id,
      name: bean.name,
      origin: bean.origin,
      roastLevel: bean.roastLevel,
      purchaseDate: new Date(bean.purchaseDate),
      notes: bean.notes
    })
  }
}
```

## 依赖关系

### 功能依赖

此功能依赖的其他功能：

- 无 / {列出依赖的功能 ID}

### 被依赖关系

依赖此功能的其他功能或页面：

- F002 (导航路由) — 需要数据才能导航到详情页
- HomeView, BeanDetailView — UI 层需要此数据

### 权限依赖

需要的系统权限：

| iOS 权限 | HarmonyOS 权限 | 用途 |
|---------|---------------|------|
| 无 / {权限键} | 无 / {权限名} | {说明} |

## 对接点（与 UI 页面的接口）

**必填段落**：说明 UI 页面如何调用本功能的接口。

格式：

```
PageName (page_XXXX):
  - @State/@ObjectLink 变量 ← 数据来源
  - 方法调用 → 功能接口
  - 路由参数 → 传递数据
```

**示例**：

```
HomeView (page_0001):
  - @ObjectLink store: BrewStore ← 从 RootView 传递
  - store.pending ← BrewStore.pending (computed)
  - store.lastRecipe ← BrewStore.lastRecipe (computed)
  - resumeBrew() → AppRouter.shared.showBrew = true
  - openRecipe(recipe) → AppRouter.shared.openRecipe(recipe, store: store)

BeanLibraryView (page_0002):
  - @ObjectLink store: BrewStore
  - store.beans ← BrewStore.beans (filtered by !archived)
  - addBean(draft: BeanDraft) → store.addBean(draft)
  - archiveBean(bean: BeanRecord) → store.archiveBean(bean)
```

## 验收标准（Acceptance Criteria）

**必填段落**：详细的、可验证的验收标准。每个 AC 必须包含：
- ✅ `源`: iOS 源码锚点（类名.方法名）
- ✅ `标`: HarmonyOS 目标（类名.方法名）
- ✅ `判`: 判定类型（ui/visual/route/contract/data）
- ✅ `真`: 源码文件路径和行号

**格式**：

```markdown
- [ ] FXXX-AC01 {验收标准描述}
      `源:{iOS 源码锚点} → 标:{HarmonyOS 目标}`
      `判:{判定类型} | {判定条件}`
      `真:{源码文件路径}:{行号}`
```

**判定类型说明**：
- `ui`: UI 元素存在性和状态（按钮可见、列表渲染）
- `visual`: 视觉效果（布局、样式、动画）
- `route`: 导航和路由（页面跳转、参数传递）
- `contract`: 接口契约（方法返回值、数据格式）
- `data`: 数据正确性（数据库查询、状态更新）

**示例**：

```markdown
- [ ] F001-AC01 应用启动时 BrewStore 自动初始化数据库
      `源:BrewStore.init() → 标:BrewStore.init(context)`
      `判:contract | ModelContainer 创建成功，返回 BrewStore 实例`
      `真:App/Data/BrewStore.swift:45`

- [ ] F001-AC02 调用 addBean() 成功插入咖啡豆记录
      `源:BrewStore.addBean(_:) → 标:BrewStore.addBean(bean)`
      `判:contract | 返回插入的 BeanRecord，数据库包含新记录`
      `真:App/Data/BrewStore.swift:120`

- [ ] F001-AC03 删除咖啡豆时级联删除关联的配方记录
      `源:cascade delete 逻辑 → 标:deleteBean 触发级联删除`
      `判:contract | 删除 Bean 后，关联 Recipe 也被删除`
      `真:App/Data/BrewStore.swift:180`

- [ ] F001-AC04 HomeView 显示 store.beans 列表
      `源:HomeView.body → 标:HomeView.build()`
      `判:ui | List 显示 BeanRecord 数组，每项显示名称和产地`
      `真:App/Views/HomeView.swift:60`

- [ ] F001-AC05 点击咖啡豆卡片跳转到详情页
      `源:NavigationLink(value: bean) → 标:NavPathStack.pushPath('BeanDetail', bean.id)`
      `判:route | 跳转到 BeanDetailView 且传递正确的 bean.id`
      `真:App/Views/BeanLibraryView.swift:85`
```

**数量要求**：
- simple 功能：至少 5 个 AC
- medium 功能：至少 8 个 AC
- complex 功能：至少 12 个 AC
- very_complex 功能：至少 15 个 AC

## 占位策略

如果功能复杂，需要分阶段实现，说明占位策略：

- **Kind**: `full-implementation` | `mock-data` | `stub-interface`
- **Stage 1-2 占位**: 使用 Mock 数据，提供固定的咖啡豆列表
- **Stage 3 真实实现**: 实现完整的数据库和 CRUD 操作
- **Trigger**: 当 UI 基本完成后，优先实现此功能

### Mock 数据示例

```typescript
// Stage 1-2 占位实现
export class BeanStoreMock {
  private mockBeans: Bean[] = [
    { id: '1', name: 'Ethiopian Yirgacheffe', origin: 'Ethiopia', ... },
    { id: '2', name: 'Colombian Supremo', origin: 'Colombia', ... }
  ]
  
  async getBeans(): Promise<Bean[]> {
    return this.mockBeans
  }
  
  async addBean(bean: Bean): Promise<void> {
    this.mockBeans.push(bean)
  }
}
```

## 测试策略

### 单元测试

需要测试的关键功能点：

- [ ] `addBean()` — 成功插入数据
- [ ] `getBeans()` — 正确查询所有记录
- [ ] `updateBean()` — 更新成功
- [ ] `deleteBean()` — 删除成功，级联删除关联数据
- [ ] 并发安全 — 多线程访问测试

### 集成测试

与其他模块的集成测试：

- [ ] UI 层集成 — HomeView 正确显示数据
- [ ] 导航集成 — 选择 Bean 后正确跳转
- [ ] 数据一致性 — 增删改后 UI 实时更新

### 性能测试

性能要求和测试：

- [ ] 插入 1000 条记录的性能
- [ ] 查询大数据集的响应时间
- [ ] 内存占用是否合理

## 风险评估

### 技术风险

| 风险 | 等级 | 说明 | 缓解措施 |
|------|------|------|---------|
| 数据库设计 | 🟡 Medium | 关系型数据库需要手动设计表结构 | 参考 SwiftData 模型，保持一致 |
| 级联删除 | 🟡 Medium | 需要手动实现级联逻辑 | 使用外键约束或代码层实现 |

### 迁移风险

| 风险 | 等级 | 说明 | 缓解措施 |
|------|------|------|---------|
| 数据丢失 | 🔴 High | 迁移过程可能导致数据丢失 | 充分测试，提供备份恢复 |

### 时间风险

- **预估**: 8-12 小时
- **风险**: 如果遇到技术难点可能延期
- **缓解**: 优先实现核心功能，次要功能可延后

## 验证清单

功能实现完成后的验证项：

- [ ] 所有 CRUD 操作正常工作
- [ ] 数据持久化成功（重启应用后数据仍存在）
- [ ] 关系管理正确（级联删除、关联查询）
- [ ] 与 UI 层集成无问题
- [ ] 性能满足要求
- [ ] 单元测试全部通过
- [ ] 集成测试通过

## 备注

其他需要说明的内容（可选）：

- 技术选型的考虑因素
- 已知的限制或约束
- 未来优化方向
- 与 iOS 版本的差异说明

---

**模板使用说明**：

1. **必填字段**：所有标记"必填"的字段不得省略或用 TODO 占位
2. **结构完整性**：各主要段落必须有实质内容（非空行 ≥ 3）
3. **ios_source_anchors**：复杂功能（high/very_complex）必须填写完整的 YAML
4. **代码示例**：必须提供可运行的 HarmonyOS 实现示例
5. **下游强约束**：此 spec 是 a2h-plan 和 a2h-execute 的输入，缺失关键字段会导致下游失败
