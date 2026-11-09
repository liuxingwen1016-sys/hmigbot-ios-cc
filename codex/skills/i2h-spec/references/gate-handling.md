<!-- when: 门禁失败、findings 需要处理时加载 -->
<!-- topics: 门禁处理策略、findings 分类、自动放行规则、记账流程 -->

# 门禁处理与 Findings 管理

## 1. 门禁处理原则

### 无人值守模式（默认）

i2h-spec 默认采用**无人值守模式**，即：
- 门禁失败时，自动按规则处理（修复或记账放行）
- 不等待用户手动确认
- 所有决策记录到 `spec/decision-ledger.md`

### 用户确认模式（可选）

用户明确要求时，才切换到确认模式：
- 门禁失败时，停下并询问用户
- 提供 2-4 个具体选项 + "其他"
- 用户回复编号后继续

## 2. Findings 分类

### 精确类（Precise）

**特征**：
- 确定性检查失败（如文件缺失、重复 ID、格式错误）
- 有明确的对错标准
- 可以通过代码自动验证

**示例**：
- `IOS.MISSING_REQUIRED_FILE` — Info.plist 不存在
- `SPEC.DUPLICATE_PAGE_ID` — 页面 ID 重复
- `SPEC.INVALID_YAML` — YAML 格式错误

**处理策略**：
- ✅ **必须修复**
- ❌ 不允许记账放行
- 🔄 最多重试 3 次，失败后停止并上报

### 推断类（Inferred）

**特征**：
- 基于启发式规则或 LLM 推断
- 没有绝对的对错标准
- 可能误报（false positive）

**示例**：
- `IOS.UNSUPPORTED_SYNTAX` — 可能不支持的 Swift 语法
- `SPEC.COMPLEXITY_MISMATCH` — 复杂度评估可能不准确
- `SPEC.MISSING_DESCRIPTION` — 描述过于简略

**处理策略**：
- 🔄 尝试修复 2-3 次
- ⚪ 修不掉 → 记账放行（"推断类，可能误报"）
- 📝 记录到 decision-ledger.md

### 管线类（Pipeline）

**特征**：
- 跨阶段的约束检查
- 依赖下游阶段才能验证
- 当前阶段无法完全确定

**示例**：
- `SPEC.CONVERSION_RATE_LOW` — 预估转换率过低（需实际执行才知道）
- `SPEC.DEPENDENCY_UNVERIFIED` — 依赖关系未验证（需运行时确认）

**处理策略**：
- 📋 记录到 findings，标记 `owner_stage: execute`
- ⏭️ 推到执行阶段验证
- 📝 记账："阶段不可判定，推到 execute/verify"

### 环境类（Environment）

**特征**：
- 工具链、环境配置问题
- 非业务逻辑错误
- 可能是临时性问题

**示例**：
- `ENV.SCRIPT_NOT_FOUND` — Python 脚本不存在（工具缺口）
- `ENV.PERMISSION_DENIED` — 文件访问权限问题
- `ENV.NETWORK_TIMEOUT` — 网络请求超时

**处理策略**：
- 🔧 尝试降级方案（如脚本失败 → LLM 手动扫描）
- 📝 记账："工具缺口，已降级"
- ⚠️ 不阻断流程

## 3. 门禁失败处置流程

### Step 1: 分类 Finding

运行 linter 后，按类别分类所有 findings：

```
findings = [
  {id: "F001", category: "precise", severity: "blocking", ...},
  {id: "F002", category: "inferred", severity: "warning", ...},
  {id: "F003", category: "pipeline", severity: "info", ...}
]
```

### Step 2: 按类别处理

| 类别 | Severity=blocking | Severity=warning/info |
|------|------------------|----------------------|
| **精确类** | 必须修复，修不掉 → 停止 | 尝试修复，修不掉 → 记账放行 |
| **推断类** | 尝试修复 2 次 → 记账放行 | 记账放行 |
| **管线类** | 记账 + 推到下游阶段 | 记账 + 推到下游阶段 |
| **环境类** | 尝试降级方案 → 记账"工具缺口" | 记账"工具缺口" |

### Step 3: 记账格式

记录到 `spec/decision-ledger.md`：

```markdown
## Finding F001: IOS.MISSING_REQUIRED_FILE

**Category**: precise  
**Severity**: blocking  
**Discovered**: Phase A, Step A1  
**Decision**: 停止执行，要求用户提供 Info.plist  
**Rationale**: 精确类 blocking finding，无法放行  
**Decision Date**: 2024-11-03T12:34:56Z
**Approval Source**: auto-policy

---

## Finding F002: IOS.UNSUPPORTED_SYNTAX

**Category**: inferred  
**Severity**: warning  
**Discovered**: Phase A, Step A2  
**Decision**: 记账放行  
**Rationale**: 推断类，可能误报；已尝试修复 2 次，未成功；不阻断后续阶段  
**Decision Date**: 2024-11-03T12:35:12Z  
**Approval Source**: default-policy
```

### Step 4: 更新 open-findings.json

同步更新 `spec/.i2h/open-findings.json`：

```json
{
  "findings": [
    {
      "id": "F002",
      "code": "IOS.UNSUPPORTED_SYNTAX",
      "category": "inferred",
      "severity": "warning",
      "owner_stage": "spec",
      "decision_ref": "spec/decision-ledger.md#finding-f002",
      "status": "deferred"
    }
  ]
}
```

## 4. 修复策略

### 精确类修复

```
1. 识别问题根因
2. 自动修复（如生成缺失文件）
3. 重跑 linter 验证
4. 如果仍失败，重复 1-3（最多 3 次）
5. 3 次后仍失败 → 停止并上报
```

### 推断类修复

```
1. 尝试修复（如补充描述、调整复杂度）
2. 重跑 linter
3. 如果仍失败，再尝试 1 次
4. 2 次后仍失败 → 记账放行
```

### 环境类降级

```
1. 尝试主方案（Python 脚本）
2. 失败 → 切换降级方案（LLM 手动）
3. 记账"工具缺口，已降级"
4. 继续执行
```

## 5. 阻断规则

### 必须停止的情况

1. **精确类 blocking finding**，3 次修复失败
2. **上游阶段遗留 blocking finding**（未记账）
3. **关键文件完全缺失**（如 iOS 项目根目录不存在）

### 可以放行的情况

1. 推断类 findings（记账后）
2. 管线类 findings（推到下游）
3. 环境类 findings（降级后）

## 6. 门禁检查点

### Gate A（Phase A 后，自动）

检查项：
- [ ] `spec/.i2h/project-skeleton.json` 存在
- [ ] 至少识别出 1 个 SwiftUI View 或 UIKit ViewController
- [ ] 所有源文件路径已验证存在

失败处理：
- 精确类 → 停止
- 推断类 → 记账放行

### Gate B（Phase B 后，可选确认）

检查项：
- [ ] `spec/baseline/ui-manifest.md` 存在
- [ ] UI 覆盖率 >= 90%（推断类）
- [ ] 所有页面都有 page spec

失败处理：
- UI 覆盖率低 → 记账放行（推断类）
- 页面 spec 缺失 → 补充生成

### Gate C（Phase C 后，可选确认）

检查项：
- [ ] `spec/baseline/feature-index.md` 存在
- [ ] 功能覆盖率 >= 85%（推断类）
- [ ] 所有 complex 功能都有详细 spec

失败处理：
- 功能覆盖率低 → 记账放行
- 功能 spec 缺失 → 补充生成

## 7. 无人值守自动确认

### 自动确认条件

在无人值守模式下，符合以下任一条件自动通过门禁：

1. **无 blocking findings** → 自动选 [1] 继续
2. **所有 blocking findings 已记账** → 自动选 [2] 放行继续

### 记录决策

自动确认时，记录到 decision-ledger.md：

```markdown
## Gate B Approval

**Decision**: 自动通过  
**Rationale**: 无 blocking findings  
**Approval Source**: default-policy  
**Date**: 2024-11-03T12:40:00Z
```

## 8. 连续失败处理

### 连续未收敛检测

如果同一 finding 连续 3 轮仍未解决：

1. 标记 `escalate: true`
2. 停止自动重试
3. 记账"工具缺口 / 未达标放行"
4. 不等待人工，继续后续流程

### 进度停滞检测

如果某个 section 累计 10 轮仍未完成：

1. 标记 `halted: true`
2. 停止修复尝试
3. 记账后 `release` 解除
4. 继续后续流程

## 9. 最佳实践

### DO（推荐）

- ✅ 明确区分 findings 类别
- ✅ 精确类必须修复，推断类可以放行
- ✅ 所有决策都记录到 decision-ledger.md
- ✅ 降级方案优于停止阻断

### DON'T（避免）

- ❌ 不要改工具、改门禁报告、改产物来迁就检测器
- ❌ 不要为了通过门禁而删减必填字段
- ❌ 不要用 TODO 或占位符糊弄门禁
- ❌ 不要无限重试（最多 3 次）

## 10. 调试和追溯

所有 findings 必须可追溯：

- **源头**：哪个 linter 在哪个步骤报告的
- **处理**：尝试了几次修复，使用了什么策略
- **结果**：修复成功 / 记账放行 / 停止阻断
- **证据**：decision-ledger.md 中的完整记录

这是整套追溯机制成立的前提。
