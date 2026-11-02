---
description: 运行完整的 iOS → HarmonyOS 迁移流水线（spec → plan → execute → verify → retrospect）
---

`$ARGUMENTS` 被忽略。

## 目标

按顺序执行五个流水线阶段 skill，完成从 iOS 到 HarmonyOS 的端到端迁移。

## 1. 检测模式

从当前目录读取 `.migbot/config.json`。

- 如果文件不存在，停止：`"migbot 未安装。请先运行 /i2h-init。"`
- 如果 `confirmed != true`，停止：`"配置未确认。请先运行 /i2h-init。"`

## 2. 探测完成标记

检查阶段完成情况：

| # | 阶段 | 标记 |
|---|------|------|
| 1 | `i2h-spec` | `spec/baseline/ui-manifest.md` 和 `spec/baseline/feature-index.md` |
| 2 | `i2h-plan` | `spec/baseline/plans/ui-plan.json` 和 `spec/baseline/plans/feature-plan.json` |
| 3 | `i2h-execute` | `spec/migration-report.md` |
| 4 | `i2h-verify` | `spec/verify-report.md` |
| 5 | `i2h-retrospect` | `docs/retrospect-report-*.md` |

从第一个未完成的阶段恢复。

## 3. 运行各个阶段

对于从恢复目标到阶段 5 的每个阶段：

1. 宣布：`"开始阶段 <N>/5: <id>"`
2. 调用 skill：`Skill(skill="<skill-name>")`
3. 总结结果（2-3 行）
4. 验证完成标记存在
5. 自动推进到下一阶段

失败时，停止：`"在 <id> 处停止，因为错误。使用 /i2h-run 恢复。"`

## 4. 五个阶段完成后

打印最终摘要，列出所有五个阶段和输出。

提醒用户：
```
所有五个阶段完成。

下一步:
1. 查看 docs/ 中的报告
2. 在 HarmonyOS 设备上测试
3. 运行 /i2h-build 编译（如果尚未完成）
```
