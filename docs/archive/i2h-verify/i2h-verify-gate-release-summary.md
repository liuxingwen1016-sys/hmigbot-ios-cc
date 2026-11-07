# i2h-verify gate-release 功能总结

**日期**: 2024-11-03  
**调研人**: Claude Opus 5.5

---

## ✅ 核心发现

### i2h-spec 已完整实现 gate-release 功能

**证据文件**：
- ✅ `i2h-spec/references/gate-handling.md` (309 行)
- ✅ `i2h-spec/references/decision-ledger-format.md` (451 行)

**功能状态**：完全可用，无需额外开发

---

## 📋 功能概述

### 1. Decision Ledger（决策账本）

**文件**: `spec/decision-ledger.md`

**作用**: 记录所有重要决策、门禁放行、技术选型

**内容结构**：
```markdown
# Decision Ledger

## 决策记录
  ### Finding 处理
  ### Gate 审批
  ### 技术选型

## 统计摘要
```

### 2. Open Findings（开放问题）

**文件**: `spec/.i2h/open-findings.json`

**作用**: 跟踪所有未解决的 findings

**格式**：
```json
{
  "findings": [
    {
      "id": "F001",
      "code": "IOS.MISSING_REQUIRED_FILE",
      "category": "precise",
      "severity": "blocking",
      "owner_stage": "spec",
      "decision_ref": "spec/decision-ledger.md#finding-f001",
      "status": "deferred"
    }
  ]
}
```

---

## 🔍 Findings 分类体系

### 精确类（Precise）

**特征**：
- ✅ 确定性检查失败（文件缺失、格式错误）
- ✅ 有明确对错标准
- ✅ 可自动验证

**处理策略**：
- 🔴 **必须修复**
- ❌ 不允许记账放行
- 🔄 最多重试 3 次
- ⛔ 失败后停止并上报

**示例**：
- `IOS.MISSING_REQUIRED_FILE` — Info.plist 不存在
- `SPEC.DUPLICATE_PAGE_ID` — 页面 ID 重复

### 推断类（Inferred）

**特征**：
- ⚠️ 基于启发式规则或 LLM 推断
- ⚠️ 没有绝对对错标准
- ⚠️ 可能误报

**处理策略**：
- 🔄 尝试修复 2-3 次
- ⚪ 修不掉 → **记账放行**
- 📝 记录原因

**示例**：
- `IOS.UNSUPPORTED_SYNTAX` — 可能不支持的语法
- `SPEC.COMPLEXITY_MISMATCH` — 复杂度评估可能不准

### 管线类（Pipeline）

**特征**：
- 📋 跨阶段约束检查
- 📋 依赖下游阶段验证
- 📋 当前无法完全确定

**处理策略**：
- 📋 记录 findings
- ⏭️ **推到执行/验证阶段**
- 🏷️ 标记 `owner_stage: execute/verify`

**示例**：
- `SPEC.CONVERSION_RATE_LOW` — 预估转换率低（需实际执行）
- `SPEC.DEPENDENCY_UNVERIFIED` — 依赖未验证（需运行时确认）

### 环境类（Environment）

**特征**：
- 🔧 工具链、环境配置问题
- 🔧 非业务逻辑错误
- 🔧 可能临时性

**处理策略**：
- 🔧 尝试降级方案
- 📝 记账"工具缺口"
- ⚠️ 不阻断流程

**示例**：
- `ENV.SCRIPT_NOT_FOUND` — Python 脚本不存在
- `ENV.PERMISSION_DENIED` — 权限问题

---

## 🚦 门禁处理流程

### 处理策略矩阵

| 类别 | Severity=blocking | Severity=warning/info |
|------|------------------|----------------------|
| **精确类** | 必须修复，修不掉 → 停止 | 尝试修复，修不掉 → 记账放行 |
| **推断类** | 尝试修复 2 次 → 记账放行 | 记账放行 |
| **管线类** | 记账 + 推到下游阶段 | 记账 + 推到下游阶段 |
| **环境类** | 尝试降级方案 → 记账"工具缺口" | 记账"工具缺口" |

### 无人值守模式（默认）

i2h-spec 默认**无人值守**：
- ✅ 门禁失败时自动按规则处理
- ✅ 不等待用户手动确认
- ✅ 所有决策记录到 `decision-ledger.md`

**自动通过条件**：
1. 无 blocking findings → 自动通过
2. 所有 blocking findings 已记账 → 放行通过

---

## 📝 迁移放行项（verify-focus.json）

### 文件位置

`spec/gate-release/verify-focus.json`

### 生成方式

由 `i2h-spec` 的 gate 处理流程自动产出：
- 工具缺口
- 未达标放行
- 阶段不可判定

### 格式（推测基于 a2h-verify）

```json
{
  "items": [
    {
      "decision_id": "D-001",
      "type": "tool_gap",
      "gate": "gate_b",
      "verify_question": "UI 覆盖率 92%，是否符合要求？",
      "finding_ref": "spec/decision-ledger.md#finding-f002",
      "pages": ["AboutView"],
      "flows": []
    }
  ]
}
```

### i2h-verify 消费方式

在 `CHECK-3` 视觉对齐和 `CHECK-5` 行为验证中：
1. 读取 `spec/gate-release/verify-focus.json`
2. 将涉及的页面/流程纳入验证范围
3. 逐条核实：
   - ✅ 已核实正常（工具判错，实际正确）
   - ❌ 确认缺陷（转入失败项）
   - ⏸️ 未覆盖（附原因和恢复条件）

---

## 🔗 与 i2h-verify 的集成

### 在 i2h-verify 中的使用

#### 启动检查

```markdown
## 启动检查 — 待办 findings

读取 `spec/.i2h/open-findings.json`：

| 情况 | 行动 |
|---|---|
| 有 `owner_stage: verify` 的条目 | 先处理这些 |
| 有上游 blocking findings | 🔴 拒绝开工 |
```

#### 迁移放行项核实

```markdown
## 迁移放行项核实

来源 `spec/gate-release/verify-focus.json`；每条一行，不得省略。

| 决策 | 类型 | 门禁 | 核实问题 | 结论 | 证据 |
|---|---|---|---|---|---|
| D-001 | 工具缺口 | gate_b | UI覆盖率92% | 已核实正常 | spec/verify/ui-comparison.md |
| D-002 | 未达标放行 | gate_c | 功能A未实现 | 确认缺陷 | spec/verify/ut-report.md |
```

---

## ✅ i2h-verify 实现要点

### 1. 读取 gate-release 信息

```python
# scripts/read_gate_release.py
import json
from pathlib import Path

def read_gate_release(project_root):
    """读取迁移放行项"""
    gate_file = Path(project_root) / "spec/gate-release/verify-focus.json"
    
    if not gate_file.exists():
        return []
    
    with open(gate_file) as f:
        data = json.load(f)
    
    return data.get("items", [])
```

### 2. 纳入验证范围

```python
def expand_verification_scope(base_pages, gate_items):
    """扩展验证范围，包含迁移放行项"""
    pages = set(base_pages)
    
    for item in gate_items:
        # 将放行项涉及的页面加入验证
        pages.update(item.get("pages", []))
    
    return list(pages)
```

### 3. 生成核实报告

```markdown
## 迁移放行项核实

### D-001: UI 覆盖率未达标

**类型**: 未达标放行  
**门禁**: Gate B  
**问题**: UI 覆盖率 92%，低于推荐的 95%  
**涉及页面**: AboutView  

**验证结果**: ✅ 已核实正常  
**证据**: 
- AboutView 已在 CHECK-3 中验证
- UI 对比相似度 96%
- 功能正常，无缺陷

---

### D-002: 功能复杂度评估偏低

**类型**: 工具缺口  
**门禁**: Gate C  
**问题**: 数据同步功能复杂度评估为 medium，实际可能更高  
**涉及功能**: F003 数据同步  

**验证结果**: ❌ 确认缺陷  
**证据**:
- CHECK-4 单元测试发现 3 个未实现的边界条件
- 需要补充实现
- 详见 spec/verify/ut-report.md

---
```

---

## 📊 对 i2h-verify 的影响

### 工作量评估

| 任务 | 工作量 | 优先级 |
|------|--------|--------|
| 读取 gate-release 文件 | 1h | ⭐⭐⭐⭐ |
| 扩展验证范围 | 1h | ⭐⭐⭐⭐ |
| 生成核实报告 | 2h | ⭐⭐⭐⭐ |
| **总计** | **4h** | |

### 集成点

1. **SKILL.md**:
   ```markdown
   ## 输入与范围
   
   - 读取 `spec/.i2h/open-findings.json`，处理 `owner_stage: verify` 的条目
   - 读取 `spec/gate-release/verify-focus.json`（如存在），纳入验证范围
   ```

2. **references/device-verification.md**:
   ```markdown
   ## CHECK-3: 视觉对齐
   
   验证范围包括：
   - 基础页面清单
   - 迁移放行项涉及的页面（来自 verify-focus.json）
   ```

3. **references/verify-report-template.md**:
   ```markdown
   ## 迁移放行项核实
   
   来源 `spec/gate-release/verify-focus.json`；每条一行。
   
   | 决策 | 类型 | 门禁 | 核实问题 | 结论 | 证据 |
   ```

---

## 🎯 结论

### ✅ i2h-spec gate-release 功能完整

1. **Decision Ledger** - 完整实现
2. **Open Findings** - 完整实现
3. **Findings 分类体系** - 4 类（精确/推断/管线/环境）
4. **无人值守模式** - 默认开启
5. **verify-focus.json** - 自动产出（推测）

### 📝 i2h-verify 需要做的

1. **读取** `spec/.i2h/open-findings.json`
   - 处理 `owner_stage: verify` 的条目
   - 检查上游 blocking findings

2. **读取** `spec/gate-release/verify-focus.json`（如存在）
   - 扩展验证范围
   - 生成核实报告

3. **记录** 验证结果
   - 每个放行项逐条核实
   - 结论：已核实正常 / 确认缺陷 / 未覆盖

### 🚀 无额外阻塞

gate-release 功能**不影响** i2h-verify 的核心工作流程：
- ✅ 可选功能（文件存在才处理）
- ✅ 只扩展验证范围（不改变验证逻辑）
- ✅ 工作量很小（~4h）

---

## 📚 参考文档

| 文档 | 路径 | 作用 |
|------|------|------|
| gate-handling.md | i2h-spec/references/gate-handling.md | 门禁处理策略 |
| decision-ledger-format.md | i2h-spec/references/decision-ledger-format.md | 决策账本格式 |
| a2h-verify SKILL.md | hmigbot-1.8.0/migbot/skills/a2h-verify/SKILL.md | Android 版参考实现 |

---

**报告版本**: v1.0  
**创建时间**: 2024-11-03  
**状态**: ✅ 调研完成，无阻塞
