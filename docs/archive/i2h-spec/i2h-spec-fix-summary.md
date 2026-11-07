# i2h-spec 修复工作摘要

**分析完成时间**: 2024-11-03  
**完整报告**: `i2h-spec-gap-analysis.md` (15,000+ 字)

---

## 🔴 核心问题

iOS 版本的 i2h-spec 产物**缺失 47% 的关键文件**，导致后续流水线无法正常运行。

### 严重性评级

| 级别 | 问题数 | 影响 |
|------|--------|------|
| 🔴 **致命** | 4 个 | 阻塞 i2h-plan 和 i2h-execute |
| 🟡 **重要** | 6 个 | 降低转换质量 |

---

## ❌ 致命问题 (P0)

### 1. 缺失 `toolkit-fact-tree.json` ⚠️
- **影响**: 整个流水线的数据源头缺失
- **后果**: i2h-plan 无法生成正确的执行计划
- **修复**: 创建/修复 ios-fact-tree skill (8-12 小时)

### 2. 缺失 `api-inventory/` 目录 ⚠️
- **影响**: 无法识别 API 调用和网络层
- **后果**: 网络层迁移混乱
- **修复**: 创建 ios-api-scanner skill (4-6 小时)

### 3. 缺失 `feature-base.md` ⚠️
- **影响**: 无基础设施定义 (数据模型、Repository、公共组件)
- **后果**: i2h-plan 无法生成 Base 层任务
- **修复**: 添加基础设施分析阶段 (3-5 小时)

### 4. `plans/` 目录职责混乱 ⚠️
- **影响**: spec 和 plan 阶段边界不清
- **后果**: 无法独立运行各阶段
- **修复**: 明确阶段职责 (2-3 小时)

**P0 总计**: 17-26 小时 (2-3 个工作日)

---

## 🟡 重要问题 (P1)

5. 缺失 `placeholder-registry.md` (1-2 小时)
6. 缺失 `ui-coverage-report.md` (1-2 小时)
7. `ui-manifest.md` 格式简化，缺失 owning_slice 列 (2-3 小时)
8. `feature-index.md` 格式简化 (1-2 小时)
9. 页面 spec 过于简化 (37 行 vs 原版 150+ 行) (6-10 小时)
10. feature spec 缺失验收标准 (4-6 小时)

**P1 总计**: 15-25 小时 (2-3 个工作日)

---

## 📊 对比数据

| 维度 | 原版 | iOS 版本 | 状态 |
|------|------|---------|------|
| 总文件数 | 36 个 | 19 个 | ❌ 缺失 47% |
| toolkit-fact-tree.json | ✅ 1700 行 | ❌ 缺失 | 🔴 致命 |
| api-inventory/ | ✅ 3 文件 | ❌ 缺失 | 🔴 致命 |
| feature-base.md | ✅ 详细 | ❌ 缺失 | 🔴 致命 |
| plans/slices/ | ✅ 4 slices | ❌ 缺失 | 🔴 致命 |
| ui-manifest 格式 | ✅ 7 列表格 | 🟡 简化 | 🟡 需改进 |
| 页面 spec 行数 | 150+ 行 | 37 行 | 🟡 需改进 |

---

## 🎯 修复路线图

### Phase 1: P0 修复 (Day 1-3)

**Day 1**: toolkit-fact-tree.json
- 创建/修复 ios-fact-tree skill
- 在 i2h-spec 中调用
- 生成完整的项目结构分析

**Day 2**: api-inventory/ + feature-base.md
- 创建 ios-api-scanner skill
- 添加基础设施分析阶段
- 生成两个核心产物

**Day 3**: plans/ 架构修复
- 明确 spec/plan 职责边界
- 修复产物目录组织

### Phase 2: P1 修复 (Day 4-6)

**Day 4**: 清单文件格式
- 重写 ui-manifest.md (7 列表格)
- 重写 feature-index.md
- 生成验证报告

**Day 5-6**: spec 深化
- 页面 spec 增加到 100+ 行
- feature spec 添加验收标准 (AC)

---

## 🔧 关键修复任务

### 任务 1: 创建 ios-fact-tree skill ⭐⭐⭐⭐⭐

**参考**: hmigbot 原版 `compose-fact-tree` / `android-fact-tree`

**输出**: `spec/toolkit-fact-tree.json`

**必须包含**:
- 所有页面元数据 (SwiftUI Views, UIKit ViewControllers)
- 导航关系 (NavigationStack, TabView)
- 状态管理 (@State, @Binding, @ObservedObject)
- 弹窗识别 (.sheet, .alert, .confirmationDialog)

### 任务 2: 创建 ios-api-scanner skill ⭐⭐⭐⭐

**参考**: hmigbot 原版 `android-api-scanner`

**输出**: `spec/baseline/api-inventory/` (3 个文件)

**必须扫描**:
- URLSession 使用
- Alamofire/Moya 等第三方库
- Info.plist URL Schemes
- CocoaPods/SPM 网络依赖

### 任务 3: 重写 ui-manifest.md 生成 ⭐⭐⭐

**必须包含**:
- 全局约定 (导航架构、设计令牌、命名规范)
- 7 列页面表格 (**owning_slice 列是关键**)
- 转换批次
- 共享组件表
- 弹窗索引

### 任务 4: 深化页面 spec ⭐⭐⭐

**必须包含**:
- 溯源 (4 个锚点)
- 转换决策表 (SwiftUI → ArkUI 映射)
- 状态接口表 (@State → @Local 映射)
- 导航关系表
- 页内弹窗详细规范

---

## ✅ 验收标准

修复完成后，必须满足:

### 文件完整性
- [ ] toolkit-fact-tree.json ≥ 500 行
- [ ] api-inventory/ 包含 3 个文件
- [ ] feature-base.md ≥ 100 行
- [ ] placeholder-registry.md 存在
- [ ] ui-coverage-report.md 存在

### 格式规范
- [ ] ui-manifest.md 使用 7 列表格，包含 owning_slice
- [ ] feature-index.md 使用 7 列表格，包含排序依赖/契约依赖
- [ ] 每个页面 spec ≥ 100 行，包含转换决策表
- [ ] 每个 feature spec 包含验收标准 (AC ≥ 5 条)

### 整体质量
- [ ] 总文件数 ≥ 30 个
- [ ] 与原版结构对齐 ≥ 90%
- [ ] i2h-plan 可以基于产物正确运行

---

## 📚 必读文档

在开始修复前，必须深入阅读:

1. ⭐⭐⭐⭐⭐ `hmigbot-1.8.0/migbot/skills/a2h-spec/skill.md`
   - 完整的 spec 生成流程
   - 各 Phase 职责
   - 产物格式规范

2. ⭐⭐⭐⭐⭐ `hmigbot-1.8.0/migbot/skills/compose-fact-tree/skill.md`
   - 项目结构分析方法论
   - fact-tree 输出格式

3. ⭐⭐⭐⭐ `hmigbot-1.8.0/migbot/skills/android-api-scanner/skill.md`
   - API 扫描方法论

4. ⭐⭐⭐⭐⭐ `JetSnackHarmony/spec/` (完整示例)
   - 所有产物的标准格式
   - 直接作为模板

---

## 🎓 核心经验

### 1. toolkit-fact-tree.json 是核心中的核心
**没有它，一切都是空中楼阁。**

### 2. 格式规范不是可选项
原版设计的格式 (如 7 列表格、owning_slice 列) 是**强制要求**，不是"建议"。

### 3. 产物完整性 = 质量基础
缺失任何关键文件都会导致后续阶段失败。

### 4. 阶段职责必须清晰
```
i2h-spec: 分析 + 规范生成 (不生成 plans/)
i2h-plan: 计划生成 (生成 plans/)
```

---

## 🚀 下次会话启动指令

```
我要修复 i2h-spec 阶段的产物问题。

请先读取:
1. i2h-spec-gap-analysis.md (完整报告)
2. hmigbot 原版 a2h-spec skill
3. hmigbot 原版 compose-fact-tree skill

然后按照修复执行计划 Phase 1 Day 1 开始工作:
目标: 修复 toolkit-fact-tree.json 生成
```

---

**预计修复总时间**: 32-51 小时 (4-6 个完整工作日)  
**准备就绪**: ✅
