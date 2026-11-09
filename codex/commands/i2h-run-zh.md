---
name: i2h-run-zh
description: 运行完整的 iOS → HarmonyOS 迁移流水线（spec → plan → execute → verify → retrospect）
---
`$ARGUMENTS` 被忽略。

## 目标

按顺序执行五个流水线阶段 skill，完成从 iOS 到 HarmonyOS 的端到端迁移。

## 1. 检测模式

从当前目录读取 `.migbot/config.json`。

- 如果文件不存在，停止：`"migbot 未安装。请先运行 $i2h-init。"`
- 如果 `confirmed != true`，停止：`"配置未确认。请先运行 $i2h-init。"`

## 2. 运行确定性前置检查

不能仅依据文件是否存在来判断完成。派发任何阶段前先运行可导入的确定性
检查器：

```bash
python3 "${CODEX_PLUGIN_ROOT:-.agents}/skills/i2h-plan/scripts/pipeline_resume.py" \
  --project-root . \
  --out spec/.i2h/i2h-run-status.json
```

读取 `spec/.i2h/i2h-run-status.json`，其中的 `resume_stage` 是唯一的恢复依据。
流水线未完成时检查器会返回退出码 `1`，这是正常的恢复场景；应继续读取 JSON，
不能仅凭退出码把它当作阶段失败。
检查器会先解析 canonical indexed-v1 路径，再解析明确支持的旧路径别名。旧路径
会出现在 `legacy_paths` 和对应阶段的 `marker.legacy` 中；探测时不要静默复制或
覆盖旧标记。需要强制所有阶段迁移到 canonical 路径时，使用 `--strict`。

只有以下检查全部通过，阶段才算完成：

- schema-2 marker 的目标输入哈希、`content_sha256` 和每个产物哈希都匹配；
- `i2h-plan` 存在已批准的 schema-2 UI delivery，且其
  `target_input_sha256` 与 spec 证据一致，ownership 检查器返回 `PASS`；
- execute、verify、retrospect 报告包含可识别的身份/状态证据；static-only 运行必须
  明确记录 deferred 的运行时或设备检查以及验证标记。

如果 JSON 的 `status` 是 `incomplete`，严格从 `resume_stage` 开始。如果任一阶段
的 `checks` 含有 `errors`，停止并报告错误码，不得继续推进。仅存在的文件、没有
内容哈希的旧 marker 或过期的 UI delivery 都不能作为完成证据。

## 3. 运行各个阶段

对于从恢复目标到阶段 5 的每个阶段：

1. 宣布：`"开始阶段 <N>/5: <id>"`
2. 调用 skill：`Skill(skill="<skill-name>")`
3. 总结结果（2-3 行）
4. 再次运行确定性检查器并检查当前阶段的 `checks`；不能直接检查标记文件是否存在。
5. 只有当前阶段显示 `complete` 才能自动推进。

调用 `i2h-execute` 前，必须消费已批准的 UI delivery 契约并生成 ownership 回执：
使用 `stages[i2h-plan].checks.delivery.path` 中返回的路径；下面命令使用的是
canonical 示例。如果检查器选中了支持的旧路径，必须替换为 JSON 返回的路径，不能
硬编码 canonical 文件名：

```bash
python3 "${CODEX_PLUGIN_ROOT:-.agents}/skills/i2h-plan/scripts/ui_state_ownership.py" \
  --project-root . \
  --inventory spec/baseline/ui-delivery-approved.json \
  --out spec/execution/ui-state-ownership.json
```

回执中的 `status` 和前置检查 JSON 中的对应结果都必须为 `PASS`。execute skill
必须使用同一份已批准 inventory，不得重新生成 draft 或静默扩大状态范围。

失败时，停止：`"在 <id> 处停止，因为错误。使用 $i2h-run 恢复。"`

## 4. 五个阶段完成后

最后再次运行检查器。根据 JSON 打印五个阶段的结果，只有 `status: complete` 且
`resume_stage: complete` 时才可宣布流水线完成。

打印最终摘要，列出所有五个阶段和输出。

提醒用户：
```
所有五个阶段完成。

下一步:
1. 查看 docs/ 中的报告
2. 在 HarmonyOS 设备上测试
3. 运行 $i2h-build 编译（如果尚未完成）
```
