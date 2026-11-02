---
name: i2h-plan
description: iOS→HarmonyOS 执行计划生成（Pipeline 第二步）：读 spec/baseline/，产出 ui-plan.json 和 feature-plan.json
tags: [pipeline, migration]
type: pipeline
domain: migration
---

# i2h-plan

Pipeline 第二步：基于 spec 生成详细的执行计划。

## 启动检查 — 待办 findings

读取 `spec/.i2h/open-findings.json`：

| 情况 | 行动 |
|---|---|
| 有 `owner_stage: plan` 的条目 | 先处理这些 |
| 有上游 `blocking` findings 无 `decision_ref` | 🔴 拒绝开工，回到上游 |

## 1. 前置检查

检查 spec 产出物：
- [ ] `spec/baseline/ui-manifest.md` 存在
- [ ] `spec/baseline/feature-index.md` 存在

缺失 → 停止，提示先运行 `/i2h-spec`

## 2. 生成 UI Plan

### Step 1: 读取 UI 清单

读取 `spec/baseline/ui-manifest.md` 和所有 `spec/baseline/ui/page_*.md`

提取信息：
- View/VC 列表
- 复杂度分类
- 代码行数
- 依赖关系

### Step 2: 批次划分策略

按复杂度和类型分组：

**SwiftUI Views**:
- `simple` (< 50行): 批次大小 20-30 个
- `medium` (50-150行): 批次大小 10-15 个
- `complex` (> 150行): 批次大小 5-8 个

**UIKit ViewControllers**:
- 单独批次，每批 2-5 个

**并行度**:
- 总 Agent 数: min(页面总数, 25)
- Batch 内并行：是
- Batch 间串行：是

### Step 3: 生成 ui-plan.json

```json
{
  "version": 1,
  "total_pages": 11,
  "total_batches": 3,
  "estimated_time_minutes": 45,
  "parallel_agents": 11,
  "batches": [
    {
      "batch_id": "UI_001",
      "type": "swiftui_simple",
      "parallel": true,
      "pages": [
        {
          "page_id": "page_0001",
          "name": "HomeView",
          "file": "App/Views/HomeView.swift",
          "output": "pages/HomeView.ets",
          "estimated_minutes": 3,
          "converter": "swiftui-template"
        },
        ...
      ],
      "closer": {
        "task": "处理共享文件",
        "estimated_minutes": 2
      },
      "estimated_minutes": 15
    },
    {
      "batch_id": "UI_002",
      "type": "swiftui_medium",
      "parallel": true,
      "pages": [...],
      "estimated_minutes": 20
    },
    {
      "batch_id": "UI_003",
      "type": "uikit",
      "parallel": false,
      "pages": [...],
      "estimated_minutes": 10
    }
  ]
}
```

输出到 `spec/baseline/plans/ui-plan.json`

### Step 4: 验证 UI Plan

```bash
python3 .migbot/bin/scripts/linters/lint_ui_plan.py "$PROJECT_ROOT"
```

检查：
- [ ] 所有页面都分配到批次
- [ ] 批次大小合理
- [ ] 并行度设置正确
- [ ] 估时合理

## 3. 生成 Feature Plan

### Step 1: 读取功能索引

读取 `spec/baseline/feature-index.md` 和所有 `spec/baseline/features/feat_*.md`

提取信息：
- 功能列表
- 复杂度
- 依赖关系

### Step 2: 依赖分析

构建依赖图：

```
F001 (数据存储) ─┐
                 ├─→ F002 (导航路由)
F003 (用户偏好) ─┘

F101 (通知) [独立]

F102 (OCR) [可选]
```

分组策略：
- **Group 1** (优先级1，无依赖): F001, F003
- **Group 2** (优先级2，依赖 Group 1): F002
- **Group 3** (优先级3，独立): F101

### Step 3: 生成 feature-plan.json

```json
{
  "version": 1,
  "total_features": 4,
  "total_groups": 3,
  "estimated_time_minutes": 90,
  "execution_order": [
    {
      "group_id": "FEAT_G1",
      "priority": 1,
      "parallel": true,
      "name": "数据层",
      "features": [
        {
          "feature_id": "F001",
          "name": "数据存储",
          "file": "features/feat_001_data_storage.md",
          "complexity": "high",
          "estimated_minutes": 60,
          "dependencies": [],
          "output": [
            "services/DataStore.ets",
            "models/BeanRecord.ets"
          ]
        },
        {
          "feature_id": "F003",
          "name": "用户偏好",
          "file": "features/feat_003_preferences.md",
          "complexity": "low",
          "estimated_minutes": 15,
          "dependencies": [],
          "output": ["utils/Preferences.ets"]
        }
      ],
      "closer": {
        "task": "Group 1 收尾，处理接线",
        "estimated_minutes": 5
      },
      "estimated_minutes": 65
    },
    {
      "group_id": "FEAT_G2",
      "priority": 2,
      "parallel": false,
      "name": "导航层",
      "features": [
        {
          "feature_id": "F002",
          "name": "导航路由",
          "complexity": "medium",
          "estimated_minutes": 30,
          "dependencies": ["F001"],
          "output": ["services/Router.ets"]
        }
      ],
      "estimated_minutes": 30
    },
    {
      "group_id": "FEAT_G3",
      "priority": 3,
      "parallel": false,
      "name": "系统集成",
      "features": [
        {
          "feature_id": "F101",
          "name": "通知",
          "complexity": "medium",
          "estimated_minutes": 20,
          "dependencies": [],
          "output": ["services/Notification.ets"]
        }
      ],
      "estimated_minutes": 20
    }
  ],
  "optional_features": [
    {
      "feature_id": "F102",
      "name": "OCR",
      "reason": "鸿蒙 OCR API 不同，标记为可选"
    }
  ]
}
```

输出到 `spec/baseline/plans/feature-plan.json`

### Step 4: 验证 Feature Plan

```bash
python3 .migbot/bin/scripts/linters/lint_feature_plan.py "$PROJECT_ROOT"
```

检查：
- [ ] 依赖关系无环
- [ ] 优先级合理
- [ ] 所有功能都分配
- [ ] 估时合理

## 4. 生成执行摘要

生成 `spec/baseline/plans/execution-summary.md`:

```markdown
# 执行计划摘要

生成时间: 2024-11-01T23:59:59Z

## UI 转换计划
- 总页面: 11 个
- 批次数: 3
- 预计时间: 45 分钟
- 并行 Agents: 11

### 批次分配
- Batch UI_001 (SwiftUI simple): 5 个页面, 15 分钟
- Batch UI_002 (SwiftUI medium): 5 个页面, 20 分钟
- Batch UI_003 (UIKit): 1 个页面, 10 分钟

## 功能实现计划
- 总功能: 4 个（+ 1 个可选）
- 优先级层级: 3
- 预计时间: 115 分钟

### 执行顺序
1. Group 1 - 数据层 (2 个功能, 65 分钟)
2. Group 2 - 导航层 (1 个功能, 30 分钟)
3. Group 3 - 系统集成 (1 个功能, 20 分钟)

## 总体预估
- **总时间**: 160 分钟（约 2.7 小时）
- Token 消耗: 约 350K-450K
- 成本: 约 $6-8
- 并行度: 最高 11 agents 同时工作

## 关键路径
1. UI 批次 1-3 (45 分钟) + Base 层 (15 分钟)
2. 编译门 Base-7 (5 分钟)
3. Feature Group 1 (65 分钟)
4. Feature Group 2 (30 分钟)
5. Feature Group 3 (20 分钟)
6. 集中编译门 (5 分钟)

## 风险评估
- 低风险: UI 转换（模板成熟）
- 中风险: 数据层（需要重新设计）
- 低风险: 其他功能
```

## 5. 完成门禁

### Gate: PLAN-COMPLETE

```bash
python3 .migbot/bin/scripts/linters/gate_plan_complete.py "$PROJECT_ROOT"
```

检查：
- [ ] ui-plan.json 存在且有效
- [ ] feature-plan.json 存在且有效
- [ ] execution-summary.md 存在
- [ ] 没有 blocking findings

## 6. 完成标记

创建 `spec/baseline/plans/complete.txt`:

```
i2h-plan completed at 2024-11-01T23:59:59Z
UI batches: 3
Feature groups: 3
Estimated time: 160 minutes
```

## 7. 输出报告

```
✅ UI Plan 生成完成
   - 11 个页面分为 3 个批次
   - 预计 45 分钟

✅ Feature Plan 生成完成
   - 4 个功能分为 3 组
   - 预计 115 分钟

✅ 执行摘要生成完成
   - 总时间: 2.7 小时
   - 成本: $6-8

下一步: 运行 /i2h-execute 开始转换
```

## 收尾：上报阶段用量

```bash
.migbot/bin/i2h mark-stage i2h-plan
```
