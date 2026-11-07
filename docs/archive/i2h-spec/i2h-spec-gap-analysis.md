# i2h-spec 产物差异分析报告

**分析时间**: 2024-11-03  
**对比对象**: 
- **原版 (标准)**: hmigbot a2h-spec 产物 (`~/DevEcoStudioProjects/JetSnackHarmony/spec`)
- **iOS 版本**: hmigbot-ios i2h-spec 产物 (`~/DevEcoStudioProjects/Cuike01/spec`)

---

## 📊 执行摘要

### 核心发现

**结论**: iOS 版本的 i2h-spec 产物与原版存在**重大结构性差异**，缺失多个关键文件和规范组件，导致后续 i2h-plan 和 i2h-execute 阶段无法正确运行。

### 差异统计

| 维度 | 原版 (JetSnackHarmony) | iOS 版本 (Cuike01) | 差异 |
|------|----------------------|-------------------|------|
| **总文件数** | 36 个 | 19 个 | ❌ **缺失 17 个** (47%) |
| **核心产物完整性** | 100% | ~40% | ❌ **不合格** |
| **规范遵守度** | 100% | ~35% | ❌ **严重偏离** |

### 质量评级

| 类别 | 原版 | iOS 版本 | 状态 |
|------|------|---------|------|
| **toolkit-fact-tree.json** | ✅ 存在 (1700 行) | ❌ **缺失** | 🔴 **致命** |
| **api-inventory/** | ✅ 完整 (3 文件) | ❌ **缺失** | 🔴 **致命** |
| **feature-base.md** | ✅ 存在 (详细) | ❌ **缺失** | 🔴 **致命** |
| **placeholder-registry.md** | ✅ 存在 | ❌ **缺失** | 🟡 **重要** |
| **ui-coverage-report.md** | ✅ 存在 | ❌ **缺失** | 🟡 **重要** |
| **plans/slices/** | ✅ 完整 (4 slices) | ❌ **缺失** | 🔴 **致命** |
| **plans/*.md** | ✅ 4 个计划文档 | ❌ **缺失** | 🔴 **致命** |
| **ui-manifest.md** | ✅ 规范格式 | 🟡 简化版本 | 🟡 **需改进** |
| **feature-index.md** | ✅ 规范格式 | 🟡 简化版本 | 🟡 **需改进** |
| **页面 spec** | ✅ 详细 (150+ 行/页) | 🟡 简化 (50 行/页) | 🟡 **需改进** |

---

## 🔍 详细差异分析

### 差异 1: 缺失 `toolkit-fact-tree.json` ⚠️ **致命**

#### 原版产物
```
spec/toolkit-fact-tree.json (1700+ 行)
```

**内容**:
- 完整的项目结构分析（Android 项目）
- 所有页面的元数据 (Activity, Composable, 导航关系)
- 导航图谱 (NavHost 层次, route 定义)
- 组件依赖关系
- 启动入口识别
- 数据模型关系

**关键字段**:
```json
{
  "$schema_version": 1,
  "app": {
    "package": "com.example.jetsnack",
    "launcher_activity": "com.example.jetsnack.ui.MainActivity",
    "min_sdk": null,
    "target_sdk": null
  },
  "pages": [
    {
      "id": "MainActivity",
      "type": "Activity",
      "fq_class": "com.example.jetsnack.ui.MainActivity",
      "navigation": {...},
      "navigation_contract": {...}
    }
  ]
}
```

#### iOS 版本产物
```
❌ 完全缺失
```

#### 问题根因

**负责 skill**: `ios-fact-tree` (对应原版的 `compose-fact-tree` / `android-fact-tree`)

**问题**:
1. ❌ `ios-fact-tree` skill 未被 i2h-spec 调用
2. ❌ 或调用了但未生成到正确位置
3. ❌ 或生成失败但被忽略

**原版流程** (a2h-spec):
```
Step 1: 调用 compose-fact-tree
  ↓
生成 toolkit-fact-tree.json
  ↓
后续步骤基于此文件生成 baseline/
```

**iOS 版本流程** (推测):
```
i2h-spec 启动
  ↓
未调用 ios-fact-tree（或调用失败）
  ↓
直接跳到生成 baseline/
  ↓
缺失核心数据源，只能生成简化版本
```

#### 影响范围

**直接影响**:
- ❌ i2h-plan 无法读取项目结构
- ❌ 无法自动识别页面优先级
- ❌ 无法生成准确的依赖关系图
- ❌ 导航转换缺失关键信息

**间接影响**:
- ❌ i2h-execute 转换质量下降
- ❌ i2h-verify 缺失验证基准

#### 修复方案

**Priority: P0 (最高优先级)**

1. **检查 ios-fact-tree skill 是否存在**
   ```bash
   ls -la migbot/skills/ios-fact-tree/
   ```

2. **如果存在，检查 i2h-spec 是否调用它**
   - 读取 `migbot/skills/i2h-spec/skill.md`
   - 查找是否有类似 `invoke ios-fact-tree` 的步骤

3. **如果未调用，添加调用逻辑**
   - 参考 a2h-spec 如何调用 compose-fact-tree
   - 在 i2h-spec 的 Phase A 添加调用

4. **如果不存在 ios-fact-tree，创建它**
   - 基于原版 `compose-fact-tree` 和 `android-fact-tree` 的方法论
   - 适配 iOS 项目结构 (.xcodeproj, Info.plist, Storyboard, SwiftUI)
   - 输出格式**必须**与原版 toolkit-fact-tree.json 保持一致

---

### 差异 2: 缺失 `api-inventory/` 目录 ⚠️ **致命**

#### 原版产物
```
spec/baseline/api-inventory/
├── raw_apis.json (28 行 - 原始扫描结果)
├── api-inventory.json (30 行 - 结构化清单)
└── api-inventory.md (100+ 行 - 人类可读报告)
```

**内容**:
- 所有外部 API 端点
- 第三方 SDK 清单
- 网络层架构分析
- 数据模型与 API 的映射关系
- Deep Link 识别
- 迁移建议

**关键信息** (JetSnack 示例):
```json
{
  "platform": "android",
  "project_type": "offline_sample",
  "services": [],
  "hardcoded_urls": [
    {
      "url": "https://jetsnack.example.com/home/cart",
      "usage": "navigation_example"
    }
  ]
}
```

#### iOS 版本产物
```
❌ 完全缺失
```

#### 问题根因

**负责 skill**: `ios-api-scanner` (对应原版的 `android-api-scanner`)

**问题**:
1. ❌ i2h-spec 未调用 API 扫描逻辑
2. ❌ 或调用了但未生成到正确位置

**原版流程** (a2h-spec):
```
Step 2: 调用 android-api-scanner
  ↓
扫描所有 .kt/.java 文件
  ↓
识别 Retrofit/OkHttp/HttpClient 使用
  ↓
生成 api-inventory/ 三个文件
```

**iOS 版本需求**:
```
Step 2: 调用 ios-api-scanner
  ↓
扫描所有 .swift 文件
  ↓
识别 URLSession/Alamofire/Moya 使用
  ↓
生成 api-inventory/ 三个文件
```

#### 影响范围

**直接影响**:
- ❌ 无法识别需要迁移的 API 调用
- ❌ 无法评估网络层复杂度
- ❌ 占位符策略 (placeholder-registry) 缺失数据源
- ❌ feature-base.md 缺失网络层描述

**间接影响**:
- ❌ i2h-plan 无法规划网络层迁移任务
- ❌ i2h-execute 可能遗漏 API 转换

#### 修复方案

**Priority: P0 (最高优先级)**

1. **创建 ios-api-scanner skill**
   - 参考原版 `android-api-scanner` 方法论
   - iOS 特定识别:
     - URLSession 使用
     - Alamofire/Moya 等第三方网络库
     - Info.plist 中的 URL Schemes
     - App Transport Security 配置

2. **在 i2h-spec 中调用**
   - Phase B: 添加 API 扫描步骤
   - 输出格式**必须**与原版一致

3. **生成三个文件**
   - `raw_apis.json` - 原始扫描结果
   - `api-inventory.json` - 结构化清单
   - `api-inventory.md` - 人类可读报告

---

### 差异 3: 缺失 `feature-base.md` ⚠️ **致命**

#### 原版产物
```
spec/baseline/feature-base.md (100+ 行)
```

**内容**:
- 数据模型定义 (Snack, SnackCollection, Filter, OrderLine)
- 实体关系图
- 数据库架构 (如有)
- 网络层架构
- 事件系统
- 偏好设置
- 权限声明
- 公共组件库

**关键章节**:
```markdown
## 数据模型
### Snack (零食实体)
- id: Long
- name: String
- imageUrl: String
...

## 实体间关系
- SnackCollection 1:N Snack
- Cart 1:N OrderLine
...

## 网络层
本项目为离线示例应用...

## 公共组件库
### JetsnackBottomBar
- 源文件: ...
- 用途: 底部导航栏
...
```

#### iOS 版本产物
```
❌ 完全缺失
```

**影响**: feature-index.md 存在，但只是简单列出功能，**没有** feature-base.md 提供的基础设施定义。

#### 问题根因

**负责步骤**: i2h-spec 的 Phase C (生成 baseline 规范)

**问题**:
1. ❌ i2h-spec 未包含生成 feature-base.md 的步骤
2. ❌ 或生成了但未遵守原版格式

**原版流程** (a2h-spec):
```
Phase C: 生成 baseline 规范
  ↓
Step C1: 分析数据模型 (基于 fact-tree)
Step C2: 分析网络层 (基于 api-inventory)
Step C3: 识别公共组件
  ↓
生成 feature-base.md
```

#### 影响范围

**直接影响**:
- ❌ i2h-plan 无法生成 Base-1~6 任务 (模型、仓库、网络、事件、偏好、公共组件)
- ❌ 功能切片 (slices) 无法引用基础设施
- ❌ 执行阶段缺失"先建基础设施，再建功能"的架构

**间接影响**:
- ❌ 数据层转换混乱 (每个页面各自实现，无统一 Repository)
- ❌ 公共组件重复转换
- ❌ 代码质量下降

#### 修复方案

**Priority: P0 (最高优先级)**

1. **在 i2h-spec 添加 Phase C: 基础设施分析**
   ```markdown
   ## Phase C: 基础设施规范生成
   
   ### Step C1: 数据模型分析
   - 输入: toolkit-fact-tree.json
   - 扫描所有 SwiftData @Model 类
   - 识别实体关系
   - 生成数据模型章节
   
   ### Step C2: 网络层分析
   - 输入: api-inventory/api-inventory.json
   - 分析网络架构
   - 生成网络层章节
   
   ### Step C3: 公共组件识别
   - 输入: toolkit-fact-tree.json, ui-manifest.md
   - 识别被多个页面使用的组件
   - 生成公共组件库章节
   
   ### 输出: feature-base.md
   ```

2. **格式必须与原版对齐**
   - 参考 JetSnackHarmony 的 feature-base.md
   - 必须包含: 数据模型、实体关系、网络层、事件系统、偏好设置、权限、公共组件

---

### 差异 4: 缺失 `placeholder-registry.md` 🟡 **重要**

#### 原版产物
```
spec/placeholder-registry.md (30 行)
```

**内容**:
- 占位符注册表 (三方 SDK、延迟实现的功能)
- Schema 定义
- trigger_condition (何时解析)
- resolve_by (哪个 slice 负责)

**示例** (JetSnack 无三方 SDK，所以为空):
```markdown
## Registered Placeholders

**本项目无三方 SDK，无 placeholder 条目。**
```

**复杂项目示例** (如微信登录):
```markdown
| P-ID | location | kind | trigger_condition | resolve_by |
|------|----------|------|------------------|-----------|
| P-S02-001 | LoginPage.ets#wechat_login_button | thirdparty-sdk | stage:3 slice:S02 | slice-02-login |
```

#### iOS 版本产物
```
❌ 完全缺失
```

#### 问题根因

**负责步骤**: i2h-spec 的最后阶段 (占位符注册)

**问题**:
1. ❌ i2h-spec 未包含占位符扫描逻辑
2. ❌ 即使项目无三方 SDK，也应该生成空的注册表文件

#### 影响范围

**直接影响**:
- 🟡 复杂项目无法管理延迟实现的功能
- 🟡 i2h-plan 无法生成占位符解析任务

**间接影响**:
- 🟡 三方 SDK 迁移混乱
- 🟡 前向引用 (forward-ref) 无处登记

#### 修复方案

**Priority: P1 (高优先级)**

1. **添加占位符扫描步骤**
   - 即使当前项目无占位符，也生成空文件
   - 格式遵守原版 schema

2. **iOS 特定占位符识别**
   - CocoaPods / SPM 依赖扫描
   - 识别常见三方 SDK (微信、支付宝、推送、地图等)
   - 标记需要延迟实现的功能

---

### 差异 5: 缺失 `ui-coverage-report.md` 🟡 **重要**

#### 原版产物
```
spec/ui-coverage-report.md (47 行)
```

**内容**:
- Activity 覆盖率统计
- Page 覆盖率统计
- Dialog 覆盖率统计
- PASS/FAIL 判定

**示例**:
```markdown
## 覆盖率总览
- **Activity 覆盖率**: 1/1 (100%) ✅
- **Page 覆盖率**: 7/7 (100%) ✅
- **Dialog 覆盖率**: 1/1 (100%) ✅

## 详细清单
| Composable | Spec 状态 | Page Spec | 说明 |
|-----------|----------|-----------|------|
| Feed | ✅ 已覆盖 | page_0003_Feed.md | ... |
...

## 覆盖率判定
**结论**: ✅ **PASS**
```

#### iOS 版本产物
```
❌ 完全缺失
```

#### 问题根因

**负责步骤**: i2h-spec 的验证阶段

**问题**:
1. ❌ i2h-spec 未包含覆盖率验证步骤
2. ❌ 无法确保所有页面都生成了 spec

#### 影响范围

**直接影响**:
- 🟡 无法验证 spec 完整性
- 🟡 可能遗漏某些页面

**间接影响**:
- 🟡 i2h-execute 可能遗漏转换

#### 修复方案

**Priority: P1 (高优先级)**

1. **添加覆盖率验证步骤**
   - 输入: toolkit-fact-tree.json, baseline/ui/*.md
   - 对比发现的页面数 vs 生成的 spec 数
   - 生成覆盖率报告

2. **iOS 特定统计**
   - SwiftUI Views 覆盖率
   - UIKit ViewControllers 覆盖率
   - Storyboard 覆盖率

---

### 差异 6: 缺失 `plans/` 目录 ⚠️ **致命**

#### 原版产物
```
spec/baseline/plans/
├── base-plan.md (100+ 行 - Base 层任务)
├── ui-plan.md (规范格式)
├── feature-plan.md (规范格式)
├── coverage-matrix.md (覆盖率矩阵)
└── slices/
    ├── slice-01-F001.md (详细切片规范)
    ├── slice-02-F002.md
    ├── slice-03-F003.md
    └── slice-04-F004.md
```

#### iOS 版本产物
```
spec/baseline/plans/
├── ui-plan.json (简化版本，非标准格式)
├── feature-plan.json (简化版本，非标准格式)
├── execution-summary.md (执行报告，非 spec 产物)
└── complete.txt (执行标记，非 spec 产物)

❌ 缺失: base-plan.md
❌ 缺失: coverage-matrix.md
❌ 缺失: slices/ 目录 (致命)
❌ 格式错误: *.json 应该是 *.md
```

#### 问题根因

**负责阶段**: **这不应该是 i2h-spec 的产物！**

**严重设计错误**:

原版设计:
```
a2h-spec 产物:
  - baseline/ (规范)
  - toolkit-fact-tree.json (事实)
  - api-inventory/ (分析)
  - ui-coverage-report.md (验证)
  - placeholder-registry.md (注册表)
  ❌ 不包含 plans/ 目录！

a2h-plan 产物:
  ✅ baseline/plans/ (计划)
    ├── base-plan.md
    ├── slices/
    └── ...
```

iOS 版本混淆:
```
i2h-spec 产物:
  - baseline/
  - baseline/plans/ ← ❌ 错误！这应该由 i2h-plan 生成
```

**根本问题**: 
- ❌ i2h-spec 越权生成了本应由 i2h-plan 生成的文件
- ❌ 或者 i2h-plan 直接修改了 i2h-spec 的产物目录

#### 影响范围

**严重性**: ⚠️ **阶段边界混乱**

这个问题揭示了更深层的架构问题:
1. ❌ spec 和 plan 阶段职责不清
2. ❌ 产物目录组织混乱
3. ❌ 无法独立运行 i2h-spec 和 i2h-plan

#### 修复方案

**Priority: P0 (架构级别修复)**

1. **明确阶段职责**:
   ```
   i2h-spec 职责:
   - 分析 iOS 项目结构
   - 生成 baseline 规范 (页面、功能、基础设施)
   - 生成事实文件 (toolkit-fact-tree.json, api-inventory)
   - 生成验证报告 (ui-coverage-report.md)
   - ❌ 不生成任何 plans/
   
   i2h-plan 职责:
   - 读取 baseline 规范
   - 生成执行计划 (base-plan, slices)
   - 生成覆盖率矩阵
   - ✅ 所有 plans/ 内容由此生成
   ```

2. **重新组织产物目录**:
   ```
   spec/
   ├── baseline/ (i2h-spec 产物)
   │   ├── ui/
   │   ├── features/
   │   ├── api-inventory/
   │   ├── feature-base.md
   │   ├── feature-index.md
   │   └── ui-manifest.md
   ├── toolkit-fact-tree.json (i2h-spec 产物)
   ├── ui-coverage-report.md (i2h-spec 产物)
   ├── placeholder-registry.md (i2h-spec 产物)
   └── plans/ (❌ 移动到下一层级)
   
   plan/ (新增，i2h-plan 产物)
   ├── base-plan.md
   ├── ui-plan.md
   ├── feature-plan.md
   ├── coverage-matrix.md
   └── slices/
       ├── slice-01-*.md
       └── ...
   ```

3. **或保持原版结构** (推荐):
   ```
   spec/
   ├── baseline/
   │   ├── ui/
   │   ├── features/
   │   ├── plans/ (i2h-plan 写入，但路径在 spec/ 下)
   │   └── ...
   ├── toolkit-fact-tree.json
   └── ...
   ```

---

### 差异 7: `ui-manifest.md` 格式简化 🟡 **需改进**

#### 原版格式 (JetSnackHarmony)
```markdown
# UI Manifest

## 全局约定
- 导航架构: Navigation + NavPathStack (详细描述)
- 设计令牌: 
  - Primary: #FFA500 (Orange)
  - Secondary: #FF6347 (Tomato)
  ...
- 命名规范: 页面 XxxPage.ets，组件 XxxComponent.ets
- 图标方案: SVG 资源 $r('app.media.ic_xxx')
- **沉浸式 + 安全区**: 详细说明

## 页面清单
| 序号 | Android | ArkTS 产出 | 优先级 | confidence | 状态 | owning_slice |
|------|---------|-----------|--------|-----------|------|--------------|
| 0001 | MainActivity | pages/MainActivity/Index.ets | P0 | high | pending | F001 |
...

### 页面状态生命周期
pending → converted → verified

## 转换批次
- Batch 1 (P0): 0001-0005
- Batch 2 (P1): 0006-0007

## 共享组件
| 组件 | 用于页面 | Android 来源 | 说明 |
...

dialog_index_schema: 1

## 弹窗 / 面板索引
| dialog key | row kind | source FQN | call site | hosts | usage | ... |
...
```

**关键特征**:
- ✅ 全局约定 (导航、设计令牌、命名规范)
- ✅ 页面清单 (7 列表格，包含 owning_slice)
- ✅ 转换批次
- ✅ 共享组件表
- ✅ 弹窗索引 (dialog_index_schema)

#### iOS 版本格式 (Cuike01)
```markdown
# UI 清单

## SwiftUI Views
| # | View 名称 | 文件路径 | 属性数 | 复杂度 | 行数 |
...

### 复杂度分类
...

## UIKit ViewControllers
...

## 总计
...
```

**特征**:
- ❌ 缺失全局约定章节
- ❌ 缺失 owning_slice 列 (关键！)
- ❌ 缺失转换批次
- ❌ 缺失共享组件表
- ❌ 缺失弹窗索引
- 🟡 格式简化，只是简单统计

#### 问题根因

**问题**:
1. ❌ i2h-spec 未遵守原版 ui-manifest 格式规范
2. ❌ 缺失 owning_slice 导致无法与 feature 关联
3. ❌ 缺失弹窗索引导致 Dialog 转换遗漏

#### 影响范围

**直接影响**:
- 🟡 i2h-plan 无法识别页面所属功能 (owning_slice)
- 🟡 无法生成正确的 slices 依赖关系
- 🟡 弹窗/面板可能被遗漏

#### 修复方案

**Priority: P1 (高优先级)**

1. **重写 ui-manifest 生成逻辑**
   - 严格遵守原版格式
   - 必须包含 7 列表格 (owning_slice 列是关键)
   - 必须包含全局约定、转换批次、共享组件、弹窗索引

2. **iOS 特定调整**
   - 导航架构: NavigationStack vs TabView
   - 设计令牌: 从 Assets.xcassets 提取颜色
   - 弹窗识别: .sheet(), .alert(), .confirmationDialog()

---

### 差异 8: `feature-index.md` 格式简化 🟡 **需改进**

#### 原版格式 (JetSnackHarmony)
```markdown
# Feature Index

## 领域模型概览
核心实体: Snack, SnackCollection, Filter, OrderLine, Cart
关系: SnackCollection 1:N Snack, Cart 1:N OrderLine, ...

## 功能清单
| ID | 功能 | 优先级 | 排序依赖 | 契约依赖 | 涉及页面 | 状态 |
|----|------|--------|---------|---------|---------|------|
| F001 | 零食浏览与详情 | P0 | base | — | Feed, SnackDetail | pending |
...

## 依赖图
```
base → F001 → F003
base → F002
base → F004
```
```

**关键特征**:
- ✅ 领域模型概览 (实体 + 关系)
- ✅ 7 列表格 (包含排序依赖、契约依赖)
- ✅ 依赖图可视化

#### iOS 版本格式 (Cuike01)
```markdown
# 功能索引

## 核心功能

### F001: 数据管理
- 源文件: ...
- 技术: SwiftData
- 复杂度: medium
...

## 依赖关系
- F001 是基础...

## 迁移优先级
...
```

**特征**:
- ❌ 缺失领域模型概览
- ❌ 缺失标准表格 (排序依赖、契约依赖列)
- 🟡 依赖关系是文字描述，非图形化

#### 问题根因

**问题**:
1. ❌ i2h-spec 未遵守原版 feature-index 格式
2. ❌ 缺失排序依赖、契约依赖导致 i2h-plan 无法生成正确的执行序

#### 影响范围

**直接影响**:
- 🟡 i2h-plan 无法自动确定功能执行顺序
- 🟡 依赖关系不清晰

#### 修复方案

**Priority: P1 (高优先级)**

1. **重写 feature-index 生成逻辑**
   - 严格遵守原版格式
   - 必须包含领域模型概览
   - 必须使用 7 列表格
   - 依赖图使用代码块可视化

---

### 差异 9: 页面 spec 详细程度不足 🟡 **需改进**

#### 原版页面 spec (page_0003_Feed.md, 150+ 行)
```markdown
# page_0003: Feed

## 溯源
- Android Composable: com.example.jetsnack.ui.home.Feed
- 源码文件: app/src/main/java/...
- UI 快照: spec/baseline/ui-snapshots/page_0003_Feed/
- 输出文件: entry/src/main/ets/pages/Feed/Index.ets

## 页面结构
- 根布局: JetsnackSurface → Column
- 顶部栏: DestinationBar("Home")
...

## 转换决策
| Android 组件 | ArkUI 组件 | 决策理由 |
...

## 状态接口
| @Local 变量 | 类型 | 数据来源 | 关联功能 |
...

## 导航关系
| 触发 | 目标页面 | 类型 |
...

## 页内弹窗 / 面板
### FilterScreen
- 源码锚点: ...
- 呈现形态: overlay / AnimatedVisibility
- 触发入口与输入: ...
- 内容与初始值: ...
- 交互状态: ...
- 确认结果: ...
- 取消与关闭: ...

## 沉浸式 + 安全区
needs_immersive_safearea = true
```

**关键章节**:
- ✅ 溯源 (4 个锚点)
- ✅ 页面结构 (详细层次)
- ✅ 转换决策表
- ✅ 状态接口表
- ✅ 导航关系表
- ✅ 页内弹窗详细规范
- ✅ 沉浸式安全区标记

#### iOS 版本页面 spec (page_0001_BeanLibraryView.md, 37 行)
```markdown
# BeanLibraryView

## 基本信息
- ID: page_0001
- 文件: App/Views/BeanLibraryView.swift
- 类型: SwiftUI View
- 复杂度: simple
- 行数: 34

## 属性
- filtered: [BeanRecord]

## UI 结构
```swift
ScrollView {
  VStack { ... }
}
```

## 转换策略
- 使用模板转换器
- 预计自动转换率: 95%

## 依赖
- BrewStore

## 风险
- 低风险
```

**特征**:
- ❌ 缺失溯源锚点 (UI 快照、输出文件路径)
- ❌ 缺失转换决策表
- ❌ 缺失状态接口表
- ❌ 缺失导航关系表
- ❌ 缺失页内弹窗规范
- ❌ 缺失沉浸式安全区标记
- 🟡 只有基本信息和简单描述

#### 问题根因

**问题**:
1. ❌ i2h-spec 页面分析不够深入
2. ❌ 未遵守原版页面 spec 模板

#### 影响范围

**直接影响**:
- 🟡 i2h-execute 转换质量下降
- 🟡 缺失转换决策导致转换器不知道如何映射组件
- 🟡 缺失状态接口导致数据绑定错误
- 🟡 缺失导航关系导致路由转换错误

#### 修复方案

**Priority: P1 (高优先级)**

1. **创建标准页面 spec 模板**
   - 基于原版 page_*.md 格式
   - 必须包含: 溯源、页面结构、转换决策表、状态接口表、导航关系表

2. **iOS 特定分析**
   - SwiftUI View 层次解析
   - @State/@Binding/@ObservedObject 识别
   - NavigationLink 识别
   - .sheet/.alert 识别

---

### 差异 10: feature spec 详细程度不足 🟡 **需改进**

#### 原版 feature spec (F001-feed-and-detail.md, 82+ 行)
```markdown
# F001: 零食浏览与详情

```yaml
complexity: simple
tier: core
depth: full
android_source_anchors:
  - role: presenter, path: "..."
  - role: data_model, path: "..."
  - role: repository, path: "..."
```

## 范围
涉及页面: Feed, SnackDetail
依赖: feature-base

## 数据流
SnackRepo → @Local snackCollections → Feed 页面
  ├─ 零食分类列表
  └─ ...

## 服务层 (ArkTS 目标接口)
SnackRepo (singleton):
  - getSnacks(): SnackCollection[]
  - getSnack(id): Snack | undefined
  ...

## 状态管理
本功能使用页面级 @Local 状态...

## 对接点 (与 UI 页面的接口)
Feed 页面:
  - @Local snackCollections ← SnackRepo.getSnacks()
  - onSnackClick(snackId) → NavPathStack.pushPath(...)

## 验收标准
- [ ] F001-AC01 Feed 页面加载时显示所有零食分类
  `源:Feed.kt → 标:FeedPage.build()`
  `判:ui | LazyColumn 显示 SnackCollection 列表`
  `真:src:ui/home/Feed.kt:45`
...
```

**关键章节**:
- ✅ YAML frontmatter (complexity, tier, depth, source_anchors)
- ✅ 数据流图
- ✅ 服务层接口定义
- ✅ 对接点详细规范
- ✅ 验收标准 (12+ 条 AC)

#### iOS 版本 feature spec (feat_001_data_management.md, 74 行)
```markdown
# F001: 数据管理

## iOS 实现
- **框架**: SwiftData
- **模型**: BeanRecord, RecipeRecord, ...

## 核心数据结构
```swift
@Model class BeanRecord { ... }
```

## 迁移策略
1. 使用鸿蒙关系型数据库
...

## 实现步骤
1. 定义 ArkTS 数据模型
...

## 占位策略
- **Kind**: data-layer-migration
...

## 验证要求
- 单元测试...

## 风险评估
...

## 预估工作量
...
```

**特征**:
- ❌ 缺失 YAML frontmatter
- ❌ 缺失数据流图
- ❌ 缺失服务层接口定义
- ❌ 缺失对接点规范
- ❌ 缺失验收标准 (AC)
- 🟡 只是简单的迁移指南，不是执行规范

#### 问题根因

**问题**:
1. ❌ i2h-spec 功能分析不够深入
2. ❌ 未遵守原版 feature spec 格式
3. ❌ 缺失验收标准导致 i2h-verify 无法验证

#### 影响范围

**直接影响**:
- 🟡 i2h-execute 不知道如何实现功能
- 🟡 缺失对接点导致页面与功能集成困难
- 🟡 缺失验收标准导致 i2h-verify 无法验证功能

#### 修复方案

**Priority: P1 (高优先级)**

1. **创建标准 feature spec 模板**
   - 基于原版 F*-*.md 格式
   - 必须包含: YAML frontmatter, 数据流图, 服务层接口, 对接点, 验收标准 (AC)

2. **iOS 特定分析**
   - SwiftData → 关系型数据库映射
   - URLSession → @ohos.net.http 映射
   - 定义 ArkTS 接口签名

---

## 🎯 修复优先级和工作量评估

### Priority: P0 (必须修复，阻塞后续阶段)

| 序号 | 差异项 | 工作量 | 预计时间 | 前置依赖 |
|------|--------|--------|---------|---------|
| 1 | toolkit-fact-tree.json | **Large** | 8-12 小时 | 创建/修复 ios-fact-tree skill |
| 2 | api-inventory/ | **Medium** | 4-6 小时 | 创建 ios-api-scanner skill |
| 3 | feature-base.md | **Medium** | 3-5 小时 | #1, #2 完成后 |
| 6 | plans/ 目录架构 | **Small** | 2-3 小时 | 明确 spec/plan 职责边界 |

**P0 总计**: 17-26 小时 (约 2-3 个工作日)

### Priority: P1 (高优先级，影响质量)

| 序号 | 差异项 | 工作量 | 预计时间 |
|------|--------|--------|---------|
| 4 | placeholder-registry.md | **Small** | 1-2 小时 |
| 5 | ui-coverage-report.md | **Small** | 1-2 小时 |
| 7 | ui-manifest.md 格式 | **Medium** | 2-3 小时 |
| 8 | feature-index.md 格式 | **Small** | 1-2 小时 |
| 9 | 页面 spec 详细度 | **Large** | 6-10 小时 |
| 10 | feature spec 详细度 | **Medium** | 4-6 小时 |

**P1 总计**: 15-25 小时 (约 2-3 个工作日)

### 总工作量

**预计总时间**: 32-51 小时 (约 **4-6 个完整工作日**)

---

## 📋 修复执行计划

### Phase 1: 核心产物修复 (P0, Day 1-3)

#### Day 1: toolkit-fact-tree.json

**目标**: 创建/修复 ios-fact-tree skill，生成完整的项目结构分析文件

**步骤**:
1. **读取原版 compose-fact-tree / android-fact-tree**
   - 位置: `hmigbot-1.8.0/migbot/skills/compose-fact-tree/`
   - 理解其方法论、输出格式、关键算法

2. **检查 ios-fact-tree 是否存在**
   ```bash
   ls -la migbot/skills/ios-fact-tree/
   ```

3. **如果存在，分析问题**
   - 为什么未被调用？
   - 或调用了但输出位置错误？
   - 或生成失败但被忽略？

4. **如果不存在，创建它**
   - 基于原版方法论
   - iOS 特定分析:
     - 解析 .xcodeproj/project.pbxproj
     - 识别 SwiftUI Views
     - 识别 UIKit ViewControllers
     - 识别 NavigationStack/TabView 导航结构
     - 识别 @State/@Binding 状态管理
     - 识别 .sheet/.alert 弹窗

5. **在 i2h-spec 中调用**
   - 读取 `migbot/skills/i2h-spec/skill.md`
   - 添加 Phase A: 调用 ios-fact-tree
   - 确保输出到 `spec/toolkit-fact-tree.json`

6. **测试生成**
   - 在 Cuike01 项目上运行
   - 验证输出格式与原版一致

**验收标准**:
- ✅ `spec/toolkit-fact-tree.json` 存在
- ✅ 包含所有页面 (pages 数组)
- ✅ 包含导航关系 (navigation 字段)
- ✅ 格式与原版 JetSnackHarmony 一致

---

#### Day 2: api-inventory/ 和 feature-base.md

**上午: api-inventory/**

**步骤**:
1. **创建 ios-api-scanner skill**
   - 基于原版 android-api-scanner
   - iOS 特定扫描:
     - URLSession 使用
     - Alamofire/Moya/AFNetworking
     - Info.plist URL Schemes
     - CocoaPods/SPM 网络库依赖

2. **在 i2h-spec 中调用**
   - Phase B: API 扫描
   - 生成三个文件:
     - `spec/baseline/api-inventory/raw_apis.json`
     - `spec/baseline/api-inventory/api-inventory.json`
     - `spec/baseline/api-inventory/api-inventory.md`

3. **测试生成**
   - 在 Cuike01 项目上运行
   - 验证格式

**验收标准**:
- ✅ api-inventory/ 目录存在
- ✅ 三个文件齐全
- ✅ 格式与原版一致

**下午: feature-base.md**

**步骤**:
1. **在 i2h-spec 添加 Phase C: 基础设施分析**
   - Step C1: 数据模型分析 (基于 toolkit-fact-tree.json)
   - Step C2: 网络层分析 (基于 api-inventory)
   - Step C3: 公共组件识别

2. **生成 feature-base.md**
   - 必须包含章节:
     - 数据模型
     - 实体关系
     - 数据库架构
     - 网络层
     - 事件系统
     - 偏好设置
     - 权限声明
     - 公共组件库

3. **测试生成**

**验收标准**:
- ✅ `spec/baseline/feature-base.md` 存在
- ✅ 包含所有必需章节
- ✅ 格式与原版一致

---

#### Day 3: plans/ 目录架构修复

**步骤**:
1. **明确阶段职责**
   - 文档化 i2h-spec 和 i2h-plan 的职责边界
   - 更新 SKILL.md

2. **修复产物目录**
   - **选项 A**: 移动 plans/ 到顶层 (推荐)
     ```
     spec/ (i2h-spec 产物)
     plan/ (i2h-plan 产物)
     ```
   - **选项 B**: 保持原版结构
     ```
     spec/baseline/plans/ (i2h-plan 写入)
     ```

3. **修复 i2h-spec**
   - 移除任何生成 plans/ 的逻辑
   - 确保只生成 baseline 规范

4. **修复 i2h-plan**
   - 读取 baseline 规范
   - 生成 plans/ 内容 (base-plan.md, slices/, ...)

**验收标准**:
- ✅ i2h-spec 不再生成 plans/
- ✅ i2h-plan 正确生成 plans/
- ✅ 阶段职责清晰

---

### Phase 2: 格式规范修复 (P1, Day 4-5)

#### Day 4: 清单文件格式

**上午: ui-manifest.md**

**步骤**:
1. 重写 ui-manifest 生成逻辑
2. 严格遵守原版格式 (7 列表格, owning_slice 列)
3. 添加全局约定、转换批次、共享组件、弹窗索引

**下午: feature-index.md + 验证报告**

**步骤**:
1. 重写 feature-index 生成逻辑 (7 列表格)
2. 添加领域模型概览
3. 生成 placeholder-registry.md
4. 生成 ui-coverage-report.md

**验收标准**:
- ✅ 所有清单文件格式正确
- ✅ 与原版结构一致

---

#### Day 5-6: 页面和功能 spec 深化

**步骤**:
1. 创建标准页面 spec 模板
2. 创建标准 feature spec 模板
3. 重新生成所有页面 spec (包含转换决策表、状态接口表、导航关系表)
4. 重新生成所有 feature spec (包含数据流图、服务层接口、对接点、验收标准)

**验收标准**:
- ✅ 每个页面 spec ≥ 100 行
- ✅ 每个 feature spec 包含验收标准 (AC)
- ✅ 格式与原版一致

---

## 🔄 验证方法

### 完整性验证

**脚本** (创建 `verify-spec-completeness.sh`):
```bash
#!/bin/bash
SPEC_DIR="spec"

echo "=== i2h-spec 产物完整性验证 ==="

# P0 核心文件
FILES_P0=(
  "$SPEC_DIR/toolkit-fact-tree.json"
  "$SPEC_DIR/baseline/api-inventory/raw_apis.json"
  "$SPEC_DIR/baseline/api-inventory/api-inventory.json"
  "$SPEC_DIR/baseline/api-inventory/api-inventory.md"
  "$SPEC_DIR/baseline/feature-base.md"
)

# P1 重要文件
FILES_P1=(
  "$SPEC_DIR/placeholder-registry.md"
  "$SPEC_DIR/ui-coverage-report.md"
  "$SPEC_DIR/baseline/ui-manifest.md"
  "$SPEC_DIR/baseline/feature-index.md"
)

echo "检查 P0 核心文件..."
for file in "${FILES_P0[@]}"; do
  if [ -f "$file" ]; then
    echo "✅ $file"
  else
    echo "❌ $file - 缺失 (致命)"
    exit 1
  fi
done

echo "检查 P1 重要文件..."
for file in "${FILES_P1[@]}"; do
  if [ -f "$file" ]; then
    echo "✅ $file"
  else
    echo "🟡 $file - 缺失 (需补充)"
  fi
done

echo "=== 验证通过 ==="
```

### 格式验证

**检查点**:
1. toolkit-fact-tree.json 包含 `pages` 数组
2. ui-manifest.md 包含 7 列表格 (owning_slice 列)
3. feature-index.md 包含领域模型概览
4. 每个页面 spec 包含转换决策表
5. 每个 feature spec 包含验收标准 (AC)

---

## 📚 参考文档

### 需要深入阅读的原版文档

1. **hmigbot-1.8.0/migbot/skills/a2h-spec/skill.md**
   - 完整的 spec 生成流程
   - 各个 Phase 的职责
   - 产物格式规范

2. **hmigbot-1.8.0/migbot/skills/compose-fact-tree/skill.md**
   - Android 项目结构分析方法论
   - fact-tree 输出格式
   - 导航图谱构建算法

3. **hmigbot-1.8.0/migbot/skills/android-api-scanner/skill.md**
   - API 扫描方法论
   - 网络层识别规则
   - 输出格式规范

4. **JetSnackHarmony/spec/** (完整示例)
   - 所有产物的标准格式
   - 可直接作为模板

---

## 🎓 核心经验总结

### 经验 1: 产物完整性是质量的基础

❌ **错误做法**:
- 生成简化版本的产物
- "差不多就行"

✅ **正确做法**:
- 产物必须 100% 符合规范
- 缺失任何关键文件都会导致后续阶段失败
- 格式必须与原版完全一致

### 经验 2: toolkit-fact-tree.json 是核心中的核心

**重要性**: ⭐⭐⭐⭐⭐

这个文件是整个流水线的**数据源头**:
```
toolkit-fact-tree.json
  ↓
驱动 baseline/ 生成
  ↓
驱动 plans/ 生成
  ↓
驱动 execute 转换
  ↓
驱动 verify 验证
```

**没有它，一切都是空中楼阁。**

### 经验 3: 格式规范不是可选项

原版设计的格式规范(例如 7 列表格、owning_slice 列)不是"建议"，而是**强制要求**:
- i2h-plan 依赖这些列来生成 slices
- i2h-execute 依赖这些列来查找页面所属功能
- i2h-verify 依赖这些列来验证功能覆盖率

**简化格式 = 破坏流水线。**

### 经验 4: 阶段职责必须清晰

```
i2h-spec: 分析 + 规范生成
i2h-plan: 计划生成
i2h-execute: 执行转换
i2h-verify: 验证结果
i2h-retrospect: 生成报告
```

**每个阶段只做自己的事，不越权。**

---

## ✅ 修复完成验收标准

### 验收清单

修复完成后，必须满足以下所有标准:

#### P0 核心产物
- [ ] `spec/toolkit-fact-tree.json` 存在，≥ 500 行，包含所有页面
- [ ] `spec/baseline/api-inventory/` 目录存在，包含 3 个文件
- [ ] `spec/baseline/feature-base.md` 存在，≥ 100 行，包含所有必需章节
- [ ] `spec/baseline/plans/` 不由 i2h-spec 生成 (或明确职责边界)

#### P1 重要产物
- [ ] `spec/placeholder-registry.md` 存在
- [ ] `spec/ui-coverage-report.md` 存在，包含覆盖率统计
- [ ] `spec/baseline/ui-manifest.md` 遵守 7 列表格格式
- [ ] `spec/baseline/feature-index.md` 遵守 7 列表格格式
- [ ] 每个页面 spec ≥ 100 行，包含转换决策表
- [ ] 每个 feature spec 包含验收标准 (AC ≥ 5 条)

#### 整体质量
- [ ] 总文件数 ≥ 30 个
- [ ] 与原版 JetSnackHarmony 结构对齐 ≥ 90%
- [ ] i2h-plan 可以基于产物正确生成计划
- [ ] 所有产物使用 UTF-8 编码，markdown 格式正确

---

## 🚀 下一步行动

### 立即执行 (本会话)

1. ✅ **已完成**: 创建本分析报告
2. ⏳ **待执行**: 读取 a2h-spec skill，深入理解原版方法论

### 下次会话

**启动指令**:
```
我要修复 i2h-spec 阶段的产物问题。

请先读取:
1. 本报告 (i2h-spec-gap-analysis.md)
2. hmigbot 原版 a2h-spec skill
3. hmigbot 原版 compose-fact-tree skill

然后按照修复执行计划 Phase 1 开始工作:
- Day 1: 修复 toolkit-fact-tree.json
```

---

**报告完成时间**: 2024-11-03  
**下次会话主题**: 修复 i2h-spec - Phase 1: 核心产物  
**预计修复总时间**: 4-6 个完整工作日  
**准备就绪**: ✅
