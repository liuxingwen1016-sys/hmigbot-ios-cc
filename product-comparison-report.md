# iOS vs Android 版本产物对比分析报告

**对比时间**: 2024-11-03  
**iOS 试点**: ~/DevEcoStudioProjects/Cuike02  
**Android 试点**: ~/DevEcoStudioProjects/JetSnackHarmony

---

## 📊 产物结构对比

### Android 版本（hmigbot）产物
```
spec/
├── toolkit-fact-tree.json          ⭐ 核心骨架（54 KB）
├── placeholder-registry.md         ⭐ 占位符注册表
├── ui-coverage-report.md           ⭐ UI 覆盖率报告
├── baseline/
│   ├── api-inventory/              ⭐ API 清单（3 文件）
│   ├── feature-base.md             ⭐ 共享基础设施（5.4 KB）
│   ├── feature-index.md            
│   ├── features/F*.md              
│   ├── ui-manifest.md              
│   ├── ui/page_*.md                
│   └── plans/                      ⭐ 执行计划（4 文件）
├── .a2h/                           
│   ├── gate-*-approval.json        ⭐ 门禁审批记录
│   └── ui-capture-policy.json      
└── a2h/                            
    ├── functional_registry.json     ⭐ 功能注册表
    └── compose_host_map.json        
```

### iOS 版本（hmigbot-ios）产物
```
spec/
├── ❌ 缺失 toolkit-fact-tree.json
├── ❌ 缺失 placeholder-registry.md
├── ❌ 缺失 ui-coverage-report.md
├── baseline/
│   ├── ❌ 缺失 api-inventory/
│   ├── ❌ 缺失 feature-base.md
│   ├── feature-index.md             ✅ 已有
│   ├── features/feat_*.md           ✅ 已有（但缺少关键内容）
│   ├── ui-manifest.md               ✅ 已有
│   ├── ui/page_*.md                 ✅ 已有
│   ├── plans/                       ✅ 已有（空目录）
│   └── spec-complete.txt            ✅ 已有
├── .i2h/
│   ├── project-skeleton.json        ✅ 已有（相当于 toolkit-fact-tree）
│   ├── phase-a-report.md            ✅ 已有
│   ├── info-plist-analysis.json     ✅ 已有
│   └── resources-inventory.json     ✅ 已有
└── decision-ledger.md               ✅ 已有
```

---

## 🔍 关键差异分析

### 差异 1: ❌ 缺失 `toolkit-fact-tree.json`（致命）

**Android 版本**：
```json
{
  "$schema_version": 1,
  "app": {
    "package": "com.example.jetsnack",
    "launcher_activity": "com.example.jetsnack.ui.MainActivity"
  },
  "pages": [
    {
      "id": "MainActivity",
      "type": "Activity",
      "fq_class": "com.example.jetsnack.ui.MainActivity",
      "navigation": {...},
      "navigation_contract": {...},  // ⭐ 导航契约
      "reach_paths": [...]            // ⭐ 可达路径
    }
  ]
}
```

**iOS 版本**：
- ✅ 有 `project-skeleton.json` 但内容简化
- ❌ 缺少导航契约（navigation_contract）
- ❌ 缺少可达路径（reach_paths）
- ❌ 缺少页面关系图谱

**影响**：
- 🔴 下游 i2h-plan 无法生成准确的页面转换顺序
- 🔴 无法自动识别启动路径和深度链接
- 🔴 导航验证缺失

**改进建议**：
1. **重命名** `project-skeleton.json` → `toolkit-fact-tree.json`（保持与 Android 版本一致）
2. **补充字段**：
   - `navigation_contract`: 每个页面的导航契约
   - `reach_paths`: 从启动页到目标页的路径
   - `inbound_triggers`: 入口触发器
   - `verify_signal`: 验证信号（用于测试）

---

### 差异 2: ❌ 缺失 `feature-base.md`（重要）

**Android 版本**：
```markdown
# Feature Base: 共享基础设施

## 数据模型
### Snack (零食实体)
- 源文件: app/src/main/java/.../Snack.kt
- 字段: id, name, imageUrl, price, tagline, tags

## 数据库
使用 @ohos.data.preferences 存储...

## 网络层
使用 @ohos.net.http 封装...

## 事件系统
使用 @ObservedV2 + @Trace...

## 公共组件库
### JetsnackBottomBar
- 源文件: .../JetsnackScaffold.kt
- 功能: 底部导航栏
```

**iOS 版本**：
- ❌ 完全缺失此文件
- 功能分散在各个 feature spec 中（重复描述）

**影响**：
- 🟡 共享基础设施没有统一说明
- 🟡 数据模型在多个 feature 中重复描述
- 🟡 下游 i2h-execute 需要多次查找相同信息

**改进建议**：
**立即创建 `spec/baseline/feature-base.md`**，包含：

```markdown
# Feature Base: 共享基础设施

## 数据模型
### BeanRecord, RecipeRecord, BrewRecord
（从 feat_001 提取）

## 数据层：BrewStore
（从 feat_001 提取核心接口）

## 权限声明
（从 info-plist-analysis.json 提取）

## 公共组件库
### BeanBag, Metric, PrimaryButton...
（从 ui-manifest.md 提取）

## 导航系统
### AppRouter 全局路由
（从 page spec 提取）
```

---

### 差异 3: ❌ 缺失 `api-inventory/`（阶段性差异，可接受）

**Android 版本**：
```
api-inventory/
├── api-inventory.json      # 结构化 API 清单
├── api-inventory.md        # 人类可读文档
└── raw_apis.json           # 原始扫描结果
```

**iOS 版本**：
- ❌ 完全缺失
- 网络请求分散在 feature spec 中描述

**分析**：
- ✅ **合理差异**：iOS 版本处于 Phase 1，api-inventory 属于 Phase 2+
- ⚠️ 但应该在 SKILL.md 中明确说明何时补充

**改进建议**：
- 📋 在 `feature-index.md` 中标注：`API Inventory: 待 Phase 2 补充`
- 📋 创建占位符 `spec/baseline/api-inventory/README.md`：
  ```markdown
  # API Inventory
  
  **状态**: Phase 2 待补充
  
  当前网络请求说明分散在各 feature spec 中。
  Phase 2 将统一提取到此目录。
  ```

---

### 差异 4: ⚠️ Feature Spec 缺少关键内容

#### 4.1 缺少"验收标准"（Acceptance Criteria）

**Android 版本**：
```markdown
## 验收标准

- [ ] F001-AC01 Feed 页面加载时显示所有零食分类
      `源:Feed.kt → 标:FeedPage.build()`
      `判:ui | LazyColumn 显示 SnackCollection 列表`
      `真:src:ui/home/Feed.kt:45`

- [ ] F001-AC02 每个分类显示分类名称和水平滚动的零食列表
      `源:SnackCollection composable → 标:SnackCollectionComponent`
      `判:ui | 分类标题 + LazyRow 零食卡片`
      `真:src:ui/home/Feed.kt:120`
```

**iOS 版本**：
```markdown
## 验证清单

功能实现完成后的验证项：

- [ ] 所有 CRUD 操作正常工作
- [ ] 数据持久化成功（重启应用后数据仍存在）
- [ ] 关系管理正确（级联删除、关联查询）
```

**对比分析**：
| 维度 | Android 版本 | iOS 版本 | 差距 |
|------|------------|---------|------|
| **粒度** | 细粒度（每个 UI 元素） | 粗粒度（整体功能） | 🔴 巨大 |
| **可验证性** | 可自动化测试 | 需要人工判断 | 🔴 巨大 |
| **源码追溯** | 精确到文件和行号 | 无追溯 | 🔴 致命 |
| **判定标准** | 明确（ui/visual/route/contract） | 模糊 | 🔴 严重 |

**影响**：
- 🔴 **致命**：无法自动化验证
- 🔴 **致命**：无法精确追溯到源码
- 🔴 **严重**：测试人员无法编写测试用例

**改进建议**：
**必须补充详细的验收标准**，格式：

```markdown
## 验收标准

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
```

每个 AC 必须包含：
- ✅ `源`: iOS 源码锚点（类名.方法名）
- ✅ `标`: HarmonyOS 目标（类名.方法名）
- ✅ `判`: 判定类型（ui/visual/route/contract）
- ✅ `真`: 源码文件路径和行号

---

#### 4.2 缺少"对接点"（与 UI 页面的接口）

**Android 版本**：
```markdown
## 对接点（与 UI 页面的接口）

Feed 页面:
  - @Local snackCollections ← SnackRepo.getSnacks()
  - onSnackClick(snackId: number) → NavPathStack.pushPath('SnackDetail', { snackId })

SnackDetail 页面:
  - 路由参数: snackId (number)
  - @Local snack ← SnackRepo.getSnack(snackId)
  - onAddToCart(snack: Snack, quantity: number) → 触发 F003-cart
```

**iOS 版本**：
- ❌ 完全缺失

**影响**：
- 🔴 **严重**：UI 和功能层对接不清晰
- 🔴 **严重**：开发者不知道如何在 UI 中调用功能接口
- 🟡 **中等**：代码审查困难（无法验证接口是否正确实现）

**改进建议**：
**必须补充对接点**：

```markdown
## 对接点（与 UI 页面的接口）

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

---

### 差异 5: ⚠️ 包含"预估工时"（应删除）

**iOS 版本**：
```markdown
## 基本信息
- 预估用时: 12-16 小时
```

**问题**：
- ❌ 预估工时容易过时
- ❌ 对实际执行没有指导意义
- ❌ 增加维护负担

**改进建议**：
**删除所有"预估用时"字段**：
- 从 `feature-spec-template.md` 中移除
- 从所有生成的 `feat_*.md` 中移除
- 只保留"复杂度"和"优先级"

---

### 差异 6: ❌ 缺失 `placeholder-registry.md`

**Android 版本**：
```markdown
# Placeholder Registry

## F001: 零食浏览与详情
- Kind: mock-data
- Trigger: Stage 2
- Fallback: 硬编码零食列表
- Location: SnackRepo.kt:85
```

**iOS 版本**：
- ❌ 完全缺失
- 占位策略分散在各 feature spec 中

**影响**：
- 🟡 无法统一查看所有占位符
- 🟡 Stage 切换时容易遗漏

**改进建议**：
**创建 `spec/placeholder-registry.md`**：

```markdown
# Placeholder Registry

## F001: 数据存储与管理
- Kind: full-implementation
- Trigger: Stage 2
- Fallback: 无（Stage 1-2 使用 Mock 数据）
- Location: N/A

## F101: 相机扫描
- Kind: system-feature-pending
- Trigger: Stage 3
- Fallback: Stage 1-2 手动输入咖啡豆信息
- Location: page_0004_ScanView
```

---

### 差异 7: ❌ 缺失 `ui-coverage-report.md`

**Android 版本**：
```markdown
# UI Coverage Report

## 页面覆盖率
- 总页面: 7
- 已分析: 7
- 覆盖率: 100%

## 组件覆盖率
- 自定义组件: 12
- 已分析: 12
- 覆盖率: 100%
```

**iOS 版本**：
- ❌ 完全缺失
- 覆盖率信息在 `ui-manifest.md` 中简单提及

**影响**：
- 🟡 无法快速查看覆盖率状态
- 🟡 无法追踪覆盖率变化

**改进建议**：
**创建 `spec/ui-coverage-report.md`**（可由 linter 生成）

---

## 📋 改进优先级

### P0（立即修复，阻断下游）

1. ✅ **补充验收标准**（每个 feature）
   - 细粒度（精确到每个 UI 元素和操作）
   - 源码追溯（精确到文件和行号）
   - 判定标准（ui/visual/route/contract）

2. ✅ **补充对接点**（每个 feature）
   - UI 页面如何调用功能接口
   - 数据流方向
   - 路由参数

3. ✅ **创建 feature-base.md**
   - 共享数据模型
   - 公共组件库
   - 导航系统

4. ✅ **增强 toolkit-fact-tree.json**
   - 补充 navigation_contract
   - 补充 reach_paths
   - 补充 verify_signal

### P1（重要，影响质量）

5. ✅ **创建 placeholder-registry.md**
   - 统一管理所有占位符
   - 明确触发时机

6. ✅ **创建 ui-coverage-report.md**
   - 统计覆盖率
   - 追踪变化

7. ✅ **删除"预估工时"**
   - 从模板移除
   - 从所有产物移除

### P2（可选，锦上添花）

8. ⚪ **创建 api-inventory/ 占位符**
   - 说明 Phase 2 补充
   - 当前分散位置索引

9. ⚪ **补充 gate 审批记录**
   - 结构化 JSON 格式
   - 便于审计追溯

---

## 🎯 总体评价

### iOS 版本的优势
- ✅ 基础结构完整（ui-manifest, feature-index, page spec）
- ✅ decision-ledger 清晰
- ✅ project-skeleton 信息丰富
- ✅ phase-a-report 详细

### iOS 版本的不足
- 🔴 **致命**：feature spec 缺少验收标准和对接点
- 🔴 **严重**：缺少 feature-base.md
- 🔴 **严重**：toolkit-fact-tree 内容简化
- 🟡 **中等**：缺少 placeholder-registry 和 ui-coverage-report
- 🟡 **中等**：预估工时应删除

### 合理的差异
- ✅ 缺少 api-inventory（Phase 2+）
- ✅ 缺少 plans/（由 i2h-plan 生成）
- ✅ .i2h/ 与 .a2h/ 命名不同（平台差异）

---

## 📝 下一步行动

1. **更新模板** (`feature-spec-template.md`)
   - 补充"验收标准"段落（详细格式）
   - 补充"对接点"段落
   - 删除"预估用时"字段

2. **更新 SKILL.md**
   - Phase C3 必须生成验收标准
   - Phase C3 必须生成对接点
   - Phase C 完成后生成 feature-base.md

3. **补充产物**
   - 创建 feature-base.md
   - 创建 placeholder-registry.md
   - 创建 ui-coverage-report.md
   - 增强 toolkit-fact-tree.json

4. **重跑 i2h-spec**
   - 验证新模板是否正确生成
   - 检查产出质量

---

**报告生成时间**: 2024-11-03  
**下次验证**: 完成上述改进后重跑 i2h-spec
