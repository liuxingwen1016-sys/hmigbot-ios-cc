---
description: 运行完整的 iOS → HarmonyOS 迁移流水线（spec → plan → execute → verify → retrospect）
---

`$ARGUMENTS` 可包含 `--require-runtime-plan`、`--require-visual-and-ut` 和 `--require-behavior`。每次前置检查均传入调用方指定的参数。指定视觉和 UT 门禁时，执行 CHECK-3/4。指定行为门禁时，CHECK-5 也必须有通过的实际行为证据才能完成正式验收。

## 目标

按顺序执行五个流水线阶段 skill，完成从 iOS 到 HarmonyOS 的端到端迁移。

## 1. 检测模式

从当前目录读取 `.migbot/config.json`。

- 如果文件不存在，停止：`"migbot 未安装。请先运行 /i2h-init。"`
- 如果 `confirmed != true`，停止：`"配置未确认。请先运行 /i2h-init。"`

## 2. 运行确定性前置检查

不能仅依据文件是否存在来判断完成。派发任何阶段前先运行可导入的确定性
检查器：

```bash
python3 "${CLAUDE_PLUGIN_ROOT:-.claude}/skills/i2h-plan/scripts/pipeline_resume.py" \
  --project-root . --summary \
  --out spec/.i2h/i2h-run-status.json
```

从命令输出的 JSON 读取 `resume_stage`、阶段检查结果与错误码。完整机器回执仍写入 `spec/.i2h/i2h-run-status.json`。诊断需要明细时，从该文件提取具体检查项。
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

如果 JSON 的 `status` 是 `incomplete`，派发 `resume_stage`。该阶段的检查错误说明
本阶段需要补齐的工作，包括缺少完成回执。后续阶段的检查在派发前仅用于诊断。
已经被检查器认定完成的阶段可能保留历史诊断，以 `complete` 字段为准。
执行阶段自身的准入规则，收尾复查仍未完成时停止向下推进。
过期的 UI 交付契约应在 Plan 处理，通过后再交 Execute。

## 3. 运行各个阶段

对于从恢复目标到阶段 5 的每个阶段：

1. 宣布：`"开始阶段 <N>/5: <id>"`
2. 调用 skill：`Skill(skill="<skill-name>")`
3. 总结结果（2-3 行）
4. 使用同一条带 `--summary` 的命令再次运行检查器，并检查当前阶段的 `checks`。
5. 只有当前阶段显示 `complete` 才能自动推进。

从 Spec 到 Verify 用同一预检命令和同一组门禁参数计时。阶段准备和 Skill 调用前，
追加 `--timing start --timing-stage <阶段>`。保存返回的 `timing.run_id`，
后续计时调用都加 `--timing-run <ID>`。设备、判图和本次返修都实际结束后，
第 4 步加 `--timing finish --timing-stage <阶段> --timing-run <ID>`。
有明确失败结果也正常记录结束。同一次调用中的重试继续使用同一 ID。
另一次调用使用新 ID。异常中断保留 running 和未知结束时间。
连续时间统计到 Verify 通过，包含阶段间耗时。跳过 Spec 或缺少任何严格门禁时只记录局部计时。

调用 `i2h-execute` 前，必须消费已批准的 UI delivery 契约并生成 ownership 回执：
使用 `stages[i2h-plan].checks.delivery.path` 中返回的路径；下面命令使用的是
canonical 示例。如果检查器选中了支持的旧路径，必须替换为 JSON 返回的路径，不能
硬编码 canonical 文件名：

```bash
python3 "${CLAUDE_PLUGIN_ROOT:-.claude}/skills/i2h-plan/scripts/ui_state_ownership.py" \
  --project-root . \
  --inventory spec/baseline/ui-delivery-approved.json \
  --out spec/execution/ui-state-ownership.json
```

回执中的 `status` 和前置检查 JSON 中的对应结果都必须为 `PASS`。execute skill
必须使用同一份已批准 inventory，不得重新生成 draft 或静默扩大状态范围。

失败时，停止：`"在 <id> 处停止，因为错误。使用 /i2h-run 恢复。"`

## 4. 五个阶段完成后

最后再次运行检查器。根据 JSON 打印五个阶段的结果，只有 `status: complete` 且
`resume_stage: complete` 时才可宣布流水线完成。

打印五阶段结果和 `verification.unpassed_checks`。运行时检查未通过时，明确当前静态范围和未通过项。报告门禁仅核对所选检查状态，产品行为、状态覆盖与端到端耗时依据实际证据验收。

提醒用户：
```
所有五个阶段完成。

下一步:
1. 查看 docs/ 中的报告
2. 在 HarmonyOS 设备上测试
3. 运行 /i2h-build 编译（如果尚未完成）
```
