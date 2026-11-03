# References 目录

此目录包含 i2h-spec 执行过程中的详细指导文档。

## 核心设计理念

i2h-spec 采用 **LLM 主导 + Python 辅助** 的混合架构：

- **LLM 负责**：语义分析、复杂度评估、转换策略、风险评估
- **Python 负责**：确定性提取（文件列表、类名、属性名、类型信息）

## References 列表

### 核心映射规则

- **ios-to-harmonyos-mapping.md** — iOS → HarmonyOS 完整映射表
  - SwiftUI → ArkTS 组件映射
  - 状态管理、数据存储、网络请求映射
  - 复杂度评估规则

### Phase A：数据准备

- **phase-a-ios-scan.md** — iOS 项目扫描策略
  - Python 脚本 vs LLM 的职责分工
  - 骨架生成 + 语义补充流程
  - Confidence 评级规则

### 产物规范

- **outputs-and-layout.md** — 产物目录结构和命名规范
  - 完整的目录树
  - 文件命名规则（page_NNNN_ClassName）
  - 必需产物清单
  - 与原版 a2h-spec 的对应关系

### 门禁和质量控制

- **gate-handling.md** — 门禁处理与 Findings 管理
  - Findings 分类（精确类、推断类、管线类、环境类）
  - 自动放行规则
  - 记账流程

- **decision-ledger-format.md** — Decision Ledger 格式规范
  - Finding 处理记录格式
  - Gate 审批记录格式
  - 技术选型记录格式
  - 追溯要求

### 其他参考

- **api-inventory-format.md** — API 清单格式（Phase 2+）
- **swift-syntax-guide.md** — Swift 语法参考
- **ios-to-arkui-semantic-mapping.md** — 语义映射参考

## 使用方式

在 SKILL.md 中通过 `**MUST READ**` 指令强制加载：

```markdown
**MUST READ**: [references/phase-a-ios-scan.md](./references/phase-a-ios-scan.md) 全文
```

**关键约束**：所有引用的 reference 文档都必须完整读取，不得仅凭 SKILL.md 的摘要执行。

## 更新机制

随着 HarmonyOS SDK 更新或发现新的映射关系，应及时更新这些 reference 文档。
