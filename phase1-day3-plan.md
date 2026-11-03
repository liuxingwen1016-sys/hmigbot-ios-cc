# Phase 1 Day 3 执行计划: feature-base.md 生成

**目标**: 生成基础设施规范文档 (feature-base.md)  
**时间**: 2024-11-03  
**优先级**: P0 (最高)  
**预计用时**: 3-4 小时

---

## 📊 任务概述

### 需要生成的文件

```
spec/baseline/feature-base.md
```

### 内容要求

根据原版 JetSnackHarmony 的 feature-base.md，需要包含：

1. **数据模型和实体关系** (Models & Entities)
2. **数据库架构** (Database Schema)
3. **网络层架构** (Network Layer)
4. **事件系统** (Event System)
5. **偏好设置** (Preferences)
6. **权限声明** (Permissions)
7. **公共组件库** (Common Components)
8. **依赖注入** (Dependency Injection)

---

## 📚 数据源

### 已有的产物

1. ✅ **toolkit-fact-tree.json** (Day 1)
   - 20 个页面
   - 3 个 features
   - 项目结构

2. ✅ **api-inventory.json** (Day 2)
   - 4 个 iOS 框架
   - SwiftData 数据存储
   - 权限和 Entitlements

### 需要额外扫描

1. **数据模型** - 扫描 SwiftData @Model
2. **公共组件** - 识别复用的 Views
3. **服务层** - 识别 Service 类

---

## 🎯 实施策略

### 方案选择

**Phase 3.1: 基于已有数据生成基础版本** (推荐)
- 使用 toolkit-fact-tree.json 和 api-inventory.json
- 快速生成 80% 的内容
- 时间: 2-3 小时

**Phase 3.2: 深度扫描增强** (可选)
- 扫描 @Model 定义
- 分析数据关系
- 时间: 1-2 小时

**决策**: 先实现 Phase 3.1，根据需要添加 Phase 3.2

---

## 🔧 实施步骤

### Step 1: 创建生成脚本

**文件**: `~/.migbot/bin/scripts/ios/generate_feature_base.py`

**核心功能**:
```python
def analyze_data_models(ios_root, api_inventory)  # 分析数据模型
def analyze_network_layer(api_inventory)          # 分析网络层
def analyze_permissions(api_inventory)            # 分析权限
def identify_common_components(fact_tree)         # 识别公共组件
def generate_feature_base_md(data)                # 生成 Markdown
```

### Step 2: 分析数据模型

**从 api-inventory.json 提取**:
- SwiftData 使用 (11 次)
- 相关文件: App/Data/Models.swift, App/Data/BrewStore.swift

**需要扫描**:
- @Model 定义
- 属性和关系
- 数据库操作

### Step 3: 分析网络层

**从 api-inventory.json 得知**:
- 项目类型: hybrid
- 无复杂网络层
- 主要是本地存储

### Step 4: 分析权限和系统能力

**从 api-inventory.json 得知**:
- 相机权限 (NSCameraUsageDescription)
- App Groups (Entitlements)
- 通知 (UserNotifications)

### Step 5: 识别公共组件

**从 toolkit-fact-tree.json 分析**:
- PrimaryButton (设计组件)
- SectionHeading (设计组件)
- TagPill (设计组件)
- Metric (设计组件)
- 等等...

### Step 6: 组装和生成

将所有分析结果组装成 feature-base.md

---

## 📋 feature-base.md 结构

基于原版格式，包含以下章节：

```markdown
# Feature Base: 基础设施

## 1. 数据模型和实体关系

### 1.1 核心实体
- Bean (咖啡豆)
- Brew (冲泡记录)
- Recipe (配方)
- Tasting (品鉴记录)

### 1.2 实体关系
- Brew → Bean (多对一)
- Brew → Recipe (多对一)

## 2. 数据库架构

### 2.1 存储方案
- **技术**: SwiftData
- **HarmonyOS 映射**: @ohos.data.relationalStore

### 2.2 数据表
- beans
- brews
- recipes

## 3. 网络层架构

### 3.1 概述
- 项目类型: hybrid (主要离线)
- 无复杂 API 集成

## 4. 偏好设置

### 4.1 UserDefaults
- 应用设置
- HarmonyOS 映射: @ohos.data.preferences

## 5. 权限声明

### 5.1 系统权限
- 相机 (扫描咖啡豆袋)

## 6. 公共组件库

### 6.1 设计组件
- PrimaryButton
- SectionHeading
- TagPill

## 7. 系统服务

### 7.1 通知服务
- UserNotifications

### 7.2 文件管理
- FileManager
```

---

## ⏱️ 时间估算

| 步骤 | 时间 | 说明 |
|------|------|------|
| Step 1: 脚本架构 | 30 分钟 | 设计函数结构 |
| Step 2: 数据模型分析 | 1 小时 | 扫描 @Model |
| Step 3: 网络层分析 | 15 分钟 | 基于 api-inventory |
| Step 4: 权限分析 | 15 分钟 | 基于 api-inventory |
| Step 5: 组件识别 | 30 分钟 | 基于 fact-tree |
| Step 6: Markdown 生成 | 45 分钟 | 组装输出 |
| Step 7: 测试验证 | 15 分钟 | 验证输出 |
| **总计** | **3-3.5 小时** | |

---

## ✅ 验收标准

### 必须满足

- [ ] `spec/baseline/feature-base.md` 存在
- [ ] 文件大小 >= 100 行
- [ ] 包含 7 个主要章节
- [ ] 数据模型章节包含核心实体
- [ ] 网络层章节说明项目类型
- [ ] 权限章节列出所有权限
- [ ] 公共组件章节列出设计组件
- [ ] Markdown 格式正确

### 内容质量

- [ ] 数据模型准确（基于 SwiftData）
- [ ] 系统能力完整（基于 api-inventory）
- [ ] HarmonyOS 映射清晰
- [ ] 适合作为 Base 层任务的输入

---

## 🎯 与前两天的协同

### Day 1 贡献
- toolkit-fact-tree.json
- 识别了 20 个页面
- 识别了公共组件 (PrimaryButton 等)

### Day 2 贡献
- api-inventory.json
- 识别了 SwiftData (数据存储)
- 识别了权限和 Entitlements
- 识别了系统框架

### Day 3 任务
- 整合 Day 1 + Day 2 数据
- 深入分析数据模型
- 生成基础设施规范

---

**创建时间**: 2024-11-03  
**状态**: 计划就绪，开始执行
