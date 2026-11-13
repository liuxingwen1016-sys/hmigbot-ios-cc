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

每个断言的匹配字段必须出自真实 runner 的 HarmonyOS UITest 控件树，匹配只检查可见控件。多个断言由同一次场景回执提供。测试设计需另行说明输入和操作。

```bash
python3 .claude/skills/i2h-plan/scripts/acceptance_plan.py seal \
  --draft spec/baseline/plans/acceptance-bindings.draft.json
```

工具按原验收条件和 Slice 重建 AC 清单。它保存全部 AC ID、规格路径和正文摘要，写入 `spec/baseline/plans/acceptance-plan.json`。把该文件纳入 Plan 审批和原有 schema-2 完成标记。运行时证据生成、测试结果和页面状态继续由相应工具写入。
