# Phase 2 执行计划: P1 格式规范修复

**目标**: 修复 i2h-spec 产物的格式规范问题  
**时间**: 2024-11-03  
**优先级**: P1 (重要)  
**预计用时**: 4-6 天

---

## 📊 任务概述

根据 `i2h-spec-gap-analysis.md`，Phase 2 需要修复以下差异项：

| 差异 | 问题 | 优先级 | 预计时间 |
|------|------|--------|---------|
| **差异 5** | placeholder-registry.md 缺失 | P1 | 1-2 小时 |
| **差异 6** | ui-coverage-report.md 缺失 | P1 | 1-2 小时 |
| **差异 7** | ui-manifest.md 格式简化 | P1 | 2-3 小时 |
| **差异 8** | feature-index.md 格式简化 | P1 | 1-2 小时 |
| **差异 9** | 页面 spec 详细度不足 | P1 | 6-10 小时 |
| **差异 10** | feature spec 缺失验收标准 | P1 | 4-6 小时 |

**总计**: 15-25 小时 (2-3 个工作日)

---

## 🎯 Phase 2 整体策略

### 分批执行

**Batch 1: 简单文档生成** (Day 4)
- 差异 5: placeholder-registry.md
- 差异 6: ui-coverage-report.md
- 预计: 2-4 小时

**Batch 2: 清单格式优化** (Day 5)
- 差异 7: ui-manifest.md
- 差异 8: feature-index.md
- 预计: 3-5 小时

**Batch 3: Spec 深化** (Day 6-7)
- 差异 9: 页面 spec
- 差异 10: feature spec
- 预计: 10-16 小时

---

## 📋 详细任务分解

### 差异 5: placeholder-registry.md 缺失

**现状**: iOS 版本完全缺失

**目标**: 生成占位符注册表

**原版内容** (JetSnackHarmony):
```markdown
# 占位符注册表

本文档记录迁移过程中使用的占位符，标记暂时无法转换的部分。

## 占位符类型

### API_PLACEHOLDER
- **用途**: 标记待实现的 API 调用
- **替换时机**: 后端接口就绪后

### UI_PLACEHOLDER
- **用途**: 标记待完善的 UI 组件
- **替换时机**: 设计细节确认后
```

**实施**:
- 扫描已生成的 spec
- 识别需要占位符的场景
- 生成注册表
- 时间: 1-2 小时

---

### 差异 6: ui-coverage-report.md 缺失

**现状**: iOS 版本完全缺失

**目标**: 生成 UI 覆盖率报告

**原版内容** (JetSnackHarmony):
```markdown
# UI 覆盖率审计报告

## 统计摘要
- 总页面数: 7 个
- 已生成 spec: 7 个
- 覆盖率: 100%

## 页面清单
| 页面 ID | 源文件 | Spec 文件 | 状态 |
|---------|--------|-----------|------|
| MainActivity | MainActivity.kt | page_0001_MainActivity.md | ✅ |
...
```

**实施**:
- 基于 toolkit-fact-tree.json
- 统计页面覆盖率
- 生成报告
- 时间: 1-2 小时

---

### 差异 7: ui-manifest.md 格式简化

**现状**: iOS 版本只有 6 列简单表格

**目标**: 对齐原版 7 列格式，添加全局约定

**原版格式**:
```markdown
# UI 清单

## 全局约定

### 导航架构
- 使用 Navigation + NavPathStack
- 页面间传参通过路由参数

### 设计令牌
- 颜色: 使用 Theme.swift 定义的颜色
- 字体: 使用系统字体

## 页面清单

| 序号 | iOS View | ArkTS 产出 | 优先级 | confidence | 状态 | owning_slice |
|------|---------|-----------|--------|------------|------|--------------|
| 1 | HomeView | pages/home/Index | P0 | high | pending | F001-main |
...

## 转换批次
- Batch 1 (P0): 0001-0005 (核心页面)
- Batch 2 (P1): 0006-0010 (功能页面)

## 共享组件
| 组件 | 用于页面 | iOS 来源 | 说明 |
...
```

**关键点**:
- ✅ 添加 owning_slice 列 (最重要！)
- ✅ 添加全局约定
- ✅ 添加转换批次
- ✅ 添加共享组件表

**实施**:
- 重写 ui-manifest 生成逻辑
- 基于 toolkit-fact-tree + feature-base
- 时间: 2-3 小时

---

### 差异 8: feature-index.md 格式简化

**现状**: iOS 版本缺失排序依赖和契约依赖列

**目标**: 对齐原版 7 列格式

**原版格式**:
```markdown
# 功能索引

## 领域模型概览
(业务域说明)

## 功能清单

| ID | 功能名 | 页面 | 优先级 | 排序依赖 | 契约依赖 | 状态 |
|----|--------|------|--------|---------|---------|------|
| F001 | 主功能 | HomeView | P0 | - | feature-base | pending |
| F002 | 子功能 | DetailView | P1 | F001 | F001 | pending |
```

**关键点**:
- ✅ 7 列表格
- ✅ 排序依赖 (前置功能)
- ✅ 契约依赖 (接口依赖)

**实施**:
- 重写 feature-index 生成
- 分析功能依赖关系
- 时间: 1-2 小时

---

### 差异 9: 页面 spec 详细度不足

**现状**: iOS 版本只有 37 行简单描述

**目标**: 扩展到 150+ 行，包含完整的转换规范

**原版格式** (page_0003_Feed.md):
```markdown
# Page Spec: Feed (0003)

## 溯源
- iOS 源文件: `App/Views/HomeView.swift`
- UI 快照: screenshots/home.png
- 输出文件: pages/home/Index.ets
- FQ class: com.cuike.HomeView

## 页面结构
(详细的 UI 层次)

## 转换决策表
| iOS 组件 | ArkTS 目标 | 理由 | 置信度 |
|---------|-----------|------|--------|
| VStack | Column | 垂直布局 | high |
| List | List | 列表组件 | high |
...

## 状态接口表
| @State | @Local | 类型 | 初值 |
...

## 导航关系表
| 目标页面 | 触发方式 | 参数 |
...

## 页内弹窗
(Sheet/Alert 规范)

## 依赖
- feature-base (数据模型)
- 公共组件 (PrimaryButton)

## 风险
- 无
```

**关键点**:
- ✅ 溯源 (4 个锚点)
- ✅ 转换决策表
- ✅ 状态接口表
- ✅ 导航关系表
- ✅ 依赖声明

**实施**:
- 为每个页面生成详细 spec
- 参考映射表填充转换规则
- 时间: 6-10 小时

---

### 差异 10: feature spec 缺失验收标准

**现状**: 功能 spec 缺少 AC (Acceptance Criteria)

**目标**: 添加验收标准，完善功能规范

**原版格式** (F001-feed-and-detail.md):
```markdown
# Feature Spec: F001 - 主功能

## 功能概述
(描述)

## 数据流图
(流程)

## 服务层接口
(API 定义)

## 验收标准 (AC)

### AC1: 数据加载
**Given** 用户进入页面
**When** 数据加载完成
**Then** 显示完整列表

### AC2: 错误处理
**Given** 网络异常
**When** 请求失败
**Then** 显示错误提示

(至少 5 条 AC)

## 对接点
- feature-base (数据模型)
- 页面 (HomeView, DetailView)
```

**关键点**:
- ✅ 验收标准 (AC >= 5 条)
- ✅ Given-When-Then 格式
- ✅ 数据流图
- ✅ 服务层接口

**实施**:
- 为每个 feature 添加 AC
- 完善功能规范
- 时间: 4-6 小时

---

## 🔧 实施策略

### Day 4: Batch 1 - 简单文档生成

**任务**:
1. 生成 placeholder-registry.md
2. 生成 ui-coverage-report.md

**工作量**: 2-4 小时

**产出**:
- 2 个新文档
- 完善 spec/ 目录

---

### Day 5: Batch 2 - 清单格式优化

**任务**:
1. 重写 ui-manifest.md (7 列表格)
2. 重写 feature-index.md (7 列表格)

**工作量**: 3-5 小时

**产出**:
- 优化后的清单文件
- 符合原版规范

---

### Day 6-7: Batch 3 - Spec 深化

**任务**:
1. 深化所有页面 spec (20 个)
2. 完善所有 feature spec (3-5 个)

**工作量**: 10-16 小时

**产出**:
- 20+ 个详细的页面 spec
- 3-5 个完整的 feature spec

---

## ⏱️ 时间规划

| Day | 任务 | 预计时间 | 累计 |
|-----|------|---------|------|
| Day 4 | placeholder-registry + ui-coverage-report | 2-4 小时 | 2-4 小时 |
| Day 5 | ui-manifest + feature-index | 3-5 小时 | 5-9 小时 |
| Day 6 | 页面 spec 深化 (10 个) | 5-8 小时 | 10-17 小时 |
| Day 7 | 页面 spec 深化 (10 个) + feature spec | 5-8 小时 | 15-25 小时 |

**总计**: 15-25 小时 (2-3 个工作日)

---

## ✅ 验收标准

### Batch 1

- [ ] placeholder-registry.md 存在
- [ ] ui-coverage-report.md 存在
- [ ] 覆盖率统计正确

### Batch 2

- [ ] ui-manifest.md 使用 7 列表格
- [ ] 包含 owning_slice 列
- [ ] 包含全局约定
- [ ] feature-index.md 使用 7 列表格
- [ ] 包含排序依赖和契约依赖

### Batch 3

- [ ] 每个页面 spec >= 100 行
- [ ] 包含转换决策表
- [ ] 包含状态接口表
- [ ] 每个 feature spec 有 AC >= 5 条
- [ ] AC 使用 Given-When-Then 格式

---

## 🎯 Phase 2 完成标志

完成后，iOS 版本的 spec/ 将与原版高度对齐：

| 指标 | 原版 | 当前 | 目标 |
|------|------|------|------|
| 文件数 | 36 个 | 19 个 | 30+ 个 |
| 格式规范度 | 100% | 35% | 90%+ |
| 页面 spec 平均行数 | 150+ | 37 | 100+ |
| 功能 spec 完整度 | 100% | 60% | 90%+ |

---

**创建时间**: 2024-11-03  
**状态**: 计划就绪，准备执行 Day 4
