<!-- when: 需要记录决策、门禁放行时加载 -->
<!-- topics: decision-ledger.md 格式、记录规范、追溯要求 -->

# Decision Ledger 格式规范

`spec/decision-ledger.md` 记录所有重要决策、门禁放行、技术选型等内容，是追溯和审计的关键文档。

## 1. 文档结构

```markdown
# Decision Ledger

**项目**: {项目名称}  
**生成时间**: {ISO 8601 时间戳}

---

## 决策记录

### Finding 处理

{每个放行的 finding 一个条目}

### Gate 审批

{每个 Gate 的审批决策}

### 技术选型

{关键的技术选择}

---

## 统计摘要

- 总决策数: {数量}
- Finding 放行: {数量}
- Gate 通过: {数量}
- 技术选型: {数量}
```

## 2. Finding 处理记录格式

```markdown
## Finding F001: IOS.MISSING_REQUIRED_FILE

**Category**: precise | inferred | pipeline | environment  
**Severity**: blocking | warning | info  
**Discovered**: Phase {X}, Step {Y}  
**Decision**: {停止执行 | 记账放行 | 推到下游阶段}  
**Rationale**: {决策理由，必须详细说明}  
**Retry Count**: {尝试修复次数}  
**Decision Date**: {ISO 8601 时间戳}  
**Approval Source**: auto-policy | user-confirmed | default-policy

**Details**:
- {问题详情}
- {尝试的修复措施}
- {最终结果}

---
```

### 字段说明

| 字段 | 说明 | 必填 |
|------|------|------|
| `Category` | Finding 类别（精确/推断/管线/环境） | ✅ |
| `Severity` | 严重程度 | ✅ |
| `Discovered` | 发现位置 | ✅ |
| `Decision` | 决策结果 | ✅ |
| `Rationale` | 决策理由（必须详细） | ✅ |
| `Retry Count` | 重试次数 | ✅ |
| `Decision Date` | 决策时间 | ✅ |
| `Approval Source` | 审批来源 | ✅ |
| `Details` | 详细信息 | 推荐 |

### Approval Source 说明

- **auto-policy**: 自动按规则处理（如推断类自动放行）
- **default-policy**: 无人值守模式的默认选择
- **user-confirmed**: 用户明确确认的决策

## 3. Gate 审批记录格式

```markdown
## Gate B Approval

**Gate**: Gate B (Phase B 后)  
**Decision**: 通过 | 有条件通过 | 失败  
**Rationale**: {理由}  
**Blocking Findings**: {数量}  
**Deferred Findings**: {数量}  
**Approval Source**: auto-policy | default-policy | user-confirmed  
**Date**: {ISO 8601 时间戳}

**Details**:
- UI 覆盖率: {百分比}%
- 所有页面都有 spec: {是/否}
- {其他关键检查项}

**放行理由**:
{如果有 blocking findings 但仍放行，必须详细说明理由}

---
```

### 示例

```markdown
## Gate B Approval

**Gate**: Gate B (Phase B 后)  
**Decision**: 通过  
**Rationale**: 无 blocking findings，所有检查项通过  
**Blocking Findings**: 0  
**Deferred Findings**: 2  
**Approval Source**: auto-policy  
**Date**: 2024-11-03T14:30:00Z

**Details**:
- UI 覆盖率: 95%
- 所有页面都有 spec: 是
- 页面 ID 命名一致: 是

---
```

## 4. 技术选型记录格式

```markdown
## Tech Decision: 数据存储方案

**Feature**: F001 数据存储  
**Decision**: 使用鸿蒙关系型数据库 (@ohos.data.relationalStore)  
**Alternatives Considered**:
1. 使用 Preferences（轻量级键值对）— 功能不足
2. 使用文件存储 — 无查询能力
3. 使用关系型数据库 — ✅ 选择此方案

**Rationale**:
- iOS 使用 SwiftData（关系型 ORM）
- 需要支持复杂查询和关系
- 鸿蒙关系型数据库是最接近的等价物
- 社区成熟，文档完善

**Trade-offs**:
- ✅ 优势: 功能完整、性能好、官方支持
- ⚠️ 劣势: 相比 SwiftData 需要手动编写 SQL、无 ORM

**Decision Date**: 2024-11-03T14:35:00Z  
**Approval Source**: auto-policy (基于映射规则)

---
```

## 5. 记录时机

### 必须记录的情况

1. **Finding 放行**
   - 推断类、管线类、环境类 findings 放行时
   - 精确类尝试修复失败（但不停止）时

2. **Gate 通过**
   - 每个 Gate 的审批结果

3. **技术选型**
   - 关键框架选择（数据存储、网络请求等）
   - 重大架构决策
   - 替代方案讨论

4. **降级处理**
   - 脚本失败，切换到 LLM 手动扫描
   - 工具链缺失，使用替代方案

### 不需要记录的情况

- 正常通过的检查（无 findings）
- 自动修复成功的 findings
- 常规的代码分析过程

## 6. 追溯要求

每条记录必须包含：

1. **Who**: 谁做的决策（auto-policy/user/default-policy）
2. **What**: 决策内容
3. **When**: 决策时间（精确到秒）
4. **Why**: 决策理由（必须详细）
5. **How**: 如何执行（尝试了什么、最终结果）

## 7. 统计摘要格式

在文档末尾添加统计摘要：

```markdown
---

## 统计摘要

**生成时间**: 2024-11-03T15:00:00Z

### Findings 处理

- **总 Findings**: 5
  - Blocking: 0
  - Warnings: 3（已放行）
  - Info: 2（已推到下游）

### Gate 审批

- **Gate A**: 自动通过（无 findings）
- **Gate B**: 自动通过（2 deferred findings）
- **Gate C**: 自动通过（无 findings）

### 技术选型

- **数据存储**: 鸿蒙关系型数据库
- **导航**: Navigation + NavPathStack
- **状态管理**: ArkTS 标准状态管理

### 审批来源分布

- auto-policy: 4 次
- default-policy: 1 次
- user-confirmed: 0 次

---

**文档版本**: v1.0  
**最后更新**: 2024-11-03T15:00:00Z
```

## 8. 审计和验证

### 完整性检查

所有 `spec/.i2h/open-findings.json` 中标记为 `deferred` 或 `resolved` 的 findings 必须在 decision-ledger.md 中有对应记录。

### 一致性检查

decision-ledger.md 中的 finding ID 必须与 open-findings.json 中的 ID 一致。

### 时间顺序

记录必须按时间顺序排列，后面的记录时间不能早于前面的。

## 9. 最佳实践

### DO（推荐）

- ✅ 决策理由必须详细、可验证
- ✅ 记录尝试的修复措施
- ✅ 说明为什么选择放行而不是修复
- ✅ 技术选型列出备选方案
- ✅ 保持时间戳精确

### DON'T（避免）

- ❌ 不要用"已处理"等模糊描述
- ❌ 不要省略决策理由
- ❌ 不要遗漏重要的 finding
- ❌ 不要在未记账的情况下放行 blocking finding

## 10. 示例：完整的 decision-ledger.md

```markdown
# Decision Ledger

**项目**: Cuike  
**生成时间**: 2024-11-03T12:00:00Z

---

## 决策记录

### Finding 处理

## Finding F001: IOS.UNSUPPORTED_SYNTAX

**Category**: inferred  
**Severity**: warning  
**Discovered**: Phase A, Step A2b  
**Decision**: 记账放行  
**Rationale**: 推断类 finding，可能误报；已尝试修复 2 次，未成功；不影响核心功能  
**Retry Count**: 2  
**Decision Date**: 2024-11-03T12:15:30Z  
**Approval Source**: auto-policy

**Details**:
- 位置: `HomeView.swift:45`
- 问题: 使用了较新的 Swift 语法（if-let 短语法）
- 修复尝试 1: 尝试改写为传统语法 → 失败（语法仍被标记）
- 修复尝试 2: 检查 Swift 版本兼容性 → 确认语法合法
- 结论: 误报，语法实际上是 Swift 5.9+ 标准语法

---

## Finding F002: SPEC.UI_COVERAGE_LOW

**Category**: inferred  
**Severity**: warning  
**Discovered**: Phase B, Step B3  
**Decision**: 记账放行  
**Rationale**: UI 覆盖率 92%（标准 90%），接近但未达到推荐的 95%；缺失的页面是辅助性页面（AboutView）  
**Retry Count**: 0  
**Decision Date**: 2024-11-03T13:20:15Z  
**Approval Source**: default-policy

**Details**:
- 覆盖率: 92% (11/12 页面)
- 缺失: AboutView（简单静态页面）
- 决策: 可在后续补充，不阻断 Phase C

---

### Gate 审批

## Gate A Approval

**Gate**: Gate A (Phase A 后)  
**Decision**: 通过  
**Rationale**: 无 blocking findings，所有检查项通过  
**Blocking Findings**: 0  
**Deferred Findings**: 0  
**Approval Source**: auto-policy  
**Date**: 2024-11-03T12:30:00Z

---

## Gate B Approval

**Gate**: Gate B (Phase B 后)  
**Decision**: 通过  
**Rationale**: 无 blocking findings，UI 覆盖率符合最低标准（92% > 90%）  
**Blocking Findings**: 0  
**Deferred Findings**: 2 (F001, F002)  
**Approval Source**: auto-policy  
**Date**: 2024-11-03T13:30:00Z

**Details**:
- UI 覆盖率: 92%
- 所有页面都有 spec: 否（缺 1 个）
- 页面 ID 命名一致: 是

---

## Gate C Approval

**Gate**: Gate C (Phase C 后)  
**Decision**: 通过  
**Rationale**: 无 blocking findings，功能覆盖率 100%  
**Blocking Findings**: 0  
**Deferred Findings**: 2 (F001, F002 - 从 Phase B 继承)  
**Approval Source**: auto-policy  
**Date**: 2024-11-03T14:45:00Z

---

### 技术选型

## Tech Decision: 数据存储方案

**Feature**: F001 数据存储  
**Decision**: 使用鸿蒙关系型数据库 (@ohos.data.relationalStore)  
**Alternatives Considered**:
1. Preferences — 轻量级键值对，功能不足
2. 文件存储 — 无查询能力，维护困难
3. 关系型数据库 — ✅ 功能完整，是 SwiftData 的最佳等价物

**Rationale**:
- iOS 使用 SwiftData（关系型 ORM）
- 需要支持 CRUD、查询、关系映射
- 鸿蒙关系型数据库提供完整的 SQL 支持
- 官方推荐，社区成熟

**Trade-offs**:
- ✅ 功能完整、性能好
- ⚠️ 无 ORM，需要手动编写 SQL

**Decision Date**: 2024-11-03T14:10:00Z  
**Approval Source**: auto-policy (基于映射规则)

---

## Tech Decision: 导航方案

**Feature**: F002 导航路由  
**Decision**: 使用 Navigation + NavPathStack  
**Alternatives Considered**:
1. Router 模式 — 自定义路由管理器
2. Navigation + NavPathStack — ✅ 官方推荐

**Rationale**:
- iOS 使用 NavigationStack（官方组件）
- 鸿蒙 Navigation + NavPathStack 是官方推荐的对应方案
- API 相似度高，迁移成本低

**Decision Date**: 2024-11-03T14:15:00Z  
**Approval Source**: auto-policy (基于映射规则)

---

---

## 统计摘要

**生成时间**: 2024-11-03T15:00:00Z

### Findings 处理

- **总 Findings**: 2
  - Blocking: 0
  - Warnings: 2（已放行）
  - Info: 0

### Gate 审批

- **Gate A**: 自动通过
- **Gate B**: 自动通过（2 deferred findings）
- **Gate C**: 自动通过（2 deferred findings）

### 技术选型

- **数据存储**: 鸿蒙关系型数据库
- **导航**: Navigation + NavPathStack
- **状态管理**: ArkTS 标准状态管理

### 审批来源分布

- auto-policy: 6 次
- default-policy: 1 次
- user-confirmed: 0 次

---

**文档版本**: v1.0  
**最后更新**: 2024-11-03T15:00:00Z
```

## 11. 下游消费

decision-ledger.md 被以下阶段消费：

- **i2h-plan**: 读取技术选型，生成执行计划
- **i2h-execute**: 读取放行的 findings，避免重复报告
- **i2h-verify**: 验证决策的合理性，审计追溯链

所以格式规范和完整性至关重要。
