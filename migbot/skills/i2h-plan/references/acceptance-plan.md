# 原生 UITest 验收绑定

从已确认范围和现有 UITest runner 的场景契约选择可观察的 AC。每个绑定至少需要一个有明确断言的步骤和一份原始控件树。对于持久化、拒绝、二次确认等行为，选择实际发生该行为的证据。仅到达页面不足以绑定这类 AC。未找到直接验证方法的 AC 留在清单中，由工具标记未绑定。

编写 `spec/baseline/plans/acceptance-bindings.draft.json`，示例：

```json
{
  "schema_version": 1,
  "bindings": [
    {
      "requirement_id": "F001-AC01",
      "scenario": "invalid_name_save",
      "assertions": [
        {
          "step": "save_rejected",
          "layout": "invalid-name-after-save.json",
          "present": [{"id": "nameError", "text": "名称不能为空"}],
          "absent": [{"id": "successNotice"}]
        }
      ]
    }
  ]
}
```

每个断言的匹配字段必须出自真实 runner 的 HarmonyOS UITest 控件树，匹配只检查可见控件。断言默认使用绑定的场景。验收条件需要跨场景证据时，可在断言内指定 `scenario`，例如分别验证边界内保存和边界外拒绝。每个断言从对应通过场景的回执读取步骤和图树。涉及多个回执时要求同设备、同签名包、同 runner 和同夹具摘要。测试设计需另行说明输入和操作。
外观切换可用可见节点的 `backgroundColor` 核对渲染结果。从原生运行前后的树分别绑定颜色值，同时核对选择控件的当前值。颜色值沿用 UITest 导出的格式。
原生页签把选中状态和标签放在不同节点时，断言可增加 `descendants`。每项包含 `ancestor`
和 `descendant` 两个选择器。例如祖先为 `{"type":"Column","selected":"true"}`，后代为
`{"type":"Text","text":"豆档案"}`。两个节点都须可见，标签必须位于匹配祖先的子树中。
`present` 可为空数组，此时至少需要一项父子关系断言。

```bash
python3 .claude/skills/i2h-plan/scripts/acceptance_plan.py seal \
  --draft spec/baseline/plans/acceptance-bindings.draft.json
```

工具按原验收条件和 Slice 重建 AC 清单。新封存的 `spec/baseline/plans/acceptance-plan.json` 使用 schema 2，保留 AC ID、规格路径和既有标题摘要，另用 `criterion_sha256` 绑定标题及缩进续行。把该文件纳入 Plan 审批和原有 schema-2 完成标记。Verify 及历史回执重放会重新计算条款摘要；改过判定条件时应复核绑定、重新封存，并按当前 Plan 流程审批。已批准的 schema 1 计划仍可按原标题摘要读取，覆盖安装不会改写计划。运行时证据生成、测试结果和页面状态继续由相应工具写入。

沿用既有场景设计前，可用 `acceptance_plan.py --project-root <当前工程> compare-draft --previous-project-root <历史工程> --previous-draft <历史草稿> --draft <当前草稿>` 对账。
报告比较验收条款的标题与归属于该条款的缩进续行，包括「源」「判」「真」，区分 ID 缺失、同 ID 正文变化与原文一致。仅标题相同的不同编号不会列为同文。
报告中的 `digest` 沿用正式 Plan 的标题摘要。续行单独列为 `continuation`，供对账和人工审阅。
历史绑定、目标场景及断言仍须由当前测试设计核对。命令只读，结果输出到 stdout。

已有本轮原生回执时，可用 `acceptance_plan.py evaluate --draft <草稿> --run <回执> --signed-hap <签名包> --device <设备>` 预检绑定。报告输出到 stdout，标记为 `DRAFT`，包括已匹配证据与失败步骤、控件树或断言。退出 0 表示成功生成预检报告。正式步骤仍由 Plan 审批与 Verify 回执决定。

逻辑契约可用 `evaluate-hypium` 预检。草稿使用 `schema_version: 1`，每条 `bindings` 包含 `requirement_id`、Hypium 的 `suite` 和 `test`。用例由测试设计者按源行为绑定。传入 `--draft`、`--run`、`--device`、`--signed-hap` 和 `--signed-test-hap`。原生回执包含两个包的摘要、设备、进程退出码及同目录 `hypium.log` 的摘要。工具重读逐用例开始和结束状态，并核对终态与汇总计数。

正式 Plan 草稿可在 `bindings` 中使用 `{"requirement_id":"F001-AC02","hypium":{"suite":"StoreContract","test":"readsPersistedName"}}`，与 UITest 绑定一同 seal 和审批。每条 AC 只能绑定一次。正式 `behavior` 同时传入 `--hypium-run` 和 `--signed-test-hap`，工具按同一设备和应用包匹配证据。绑定用例缺席时标为未验证，失败或错误会阻断功能门禁。严格续跑会重新读取原始日志和两个包。

审批前可用 `evaluate --draft` 加同一组 Hypium 参数，在一份只读报告中预检混合计划。报告只写 stdout，保留完整 AC 分母。新签名包需要本次安装的两类回执，上一包的 UI 回执会被拒绝。

同一 AC 同时要求 UI 与逻辑证据时，在同一条绑定中写明 `scenario`、`assertions` 与 `hypium`。三字段按各自契约校验，两类证据均通过才记一条 `DIRECT_EVIDENCE`。
