<!-- when: Round 1 全部结果发布后、Round 2 规划前读取 -->
<!-- topics: one quick review, conservative routing, no correctness claim -->

# Round 1 后一次快速审查协议

## 目的与输入

快速审查只回答“哪些 Baseline `FIX_REQUIRED` 还值得进入 Round 2、下一步改哪里”。它不是完整静态复审，更不是正确性验证。

先对当前 ArkTS 源码运行一次全量 `setting_effect_verify.py`，不得按 key 过滤。然后：

```text
python <skill-dir>/scripts/quick_repair_review.py plan \
  --findings <out>/baseline/baseline-findings.json \
  --detector <out>/quick-review/detector/report.json \
  --round1-plan <out>/round-1/repair-plan.json \
  --round1-results-dir <out>/round-1/results \
  --project-root <arkts_root> \
  --packets-dir <out>/quick-review/packets \
  --out <out>/quick-review/plan.json
```

默认每批最多 6 个 key、最多四批并行。每个 Agent 只读自己的 packet：Baseline 完整 consumer/terminal-chain 工单、Round 1 逐 key 结果、新 Detector 对应项、当前 active implementation evidence、确定性 skeleton/throw blocker，以及为裁决所需的精确 Android/ArkTS anchor 周边。禁止重新建立六节点证明或全项目漫游。

## 单项结果

```json
{
  "key": "prefTheme",
  "status": "CLOSED_LIKELY | ROUND2_REQUIRED | UNCERTAIN | REVIEW_FAILED",
  "evidence": ["简短、可定位的静态证据"],
  "remaining_break": "CLOSED_LIKELY 时为空；否则为剩余断链",
  "consumer_closure": [{"android_consumer_id":"...","status":"MATCHED | MISSING | NOT_APPLICABLE","evidence":"..."}],
  "terminal_effect_chain_complete": true,
  "active_target_confirmed": true,
  "persistence_precedence_complete": true,
  "logical_setting_group_complete": true,
  "reachable_blockers": [],
  "remaining_effect_chain": [],
  "change_kinds": ["LOCAL_EFFECT | EXISTING_ROUTE_ACTIVATION | NAV_CONTAINER_MODE_CHANGE | NAV_TOPOLOGY_MUTATION"],
  "round2_edit_targets": [
    {
      "path": "entry/src/main/ets/...",
      "role": "PERSISTENCE_FOUNDATION | CONSUMER | ACTIVATION | UI_SURFACE | STARTUP",
      "callable": "精确函数/类/组件",
      "anchor": "精确定位文本",
      "expected_change": "该 target 要完成的剩余修改"
    }
  ],
  "ownership_expansion": {"revision":0,"reason":"","targets":[]}
}
```

`CLOSED_LIKELY` 必须同时满足：Baseline Android consumer inventory exactly-once 覆盖且全为 `MATCHED|NOT_APPLICABLE`；终端效果链到平台原语完整；当前 edit/mapping/terminal targets 可从应用表面到达；launcher/backing/temporary override/default 的优先级完整；逻辑设置组完整；`reachable_blockers=[]`；`remaining_effect_chain=[]`；`remaining_break=""`、`change_kinds=[]`、targets 为空。脚本会扫描精确 anchor 周边的明显 `Not implemented/skeleton/stub/TODO` throw；这些 blocker 未消除时拒绝 `CLOSED_LIKELY`。Detector 转绿或 Round 1 声明 `APPLIED` 单独都不能闭合。

其他状态必须给出剩余断链、非空 `remaining_effect_chain`、至少一个合法 `change_kinds` 与至少一个存在的精确 `.ets` target。若所有 Round 2 targets 都在 Baseline ownership 内，使用 revision 0；若终端链需要额外文件，只允许一次 revision 1，`ownership_expansion.targets` 必须正好等于新增路径且总 target 不超过 6 个文件。拒绝 revision 2、目录、通配符、`..` 和推测路径。打开已有 route/dialog 使用 `EXISTING_ROUTE_ACTIVATION`；只有容器模式或静态目的地成员/顺序变化才使用机械阻止的导航 change kind。

## 失败与发布

Agent draft 用 `quick_repair_review.py publish` 发布。同批第一次失败只重试一次；第二次仍失败：

```text
python <skill-dir>/scripts/quick_repair_review.py mark-failed \
  --plan <plan.json> --batch-id <batch-id> --reason <reason> \
  --fragments-dir <fragments-dir>
```

`mark-failed` 将该批标为 `REVIEW_FAILED`，并回退到 Baseline targets 与 `change_kinds`，使其保守进入 Round 2。全部批封存后运行 `merge` 生成 `<out>/quick-review/findings.json`。

## 明确不做

- 不生成 Admission、Closure、cache 或 final gate。
- 不运行测试、设备、UI 或截图。
- 不把 Detector 状态或 `CLOSED_LIKELY` 当作正确性证明。
- 不在快速审查阶段编辑源码。
