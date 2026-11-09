<!-- when: Baseline 工单完成后、Round 1/2 编辑前读取 -->
<!-- topics: bounded batches, ownership waves, per-key result, two rounds -->

# 双轮轻量修复协议

## Planner 边界

Round 1 只消费 Baseline `FIX_REQUIRED`：

- `NAV_CONTAINER_MODE_CHANGE`、`NAV_TOPOLOGY_MUTATION` 永不进入自动修复；Planner 会再次机械过滤，作为 Review 发布门的第二道防线；

- 普通批最多 3 个 settings、10 个 ownership paths；仅当所有项 `logical_setting_group` 相同且共享同一 foundation path 时，允许最多 4 项的 foundation 批；
- 单 setting 最多 6 个精确 ownership paths；
- 最多四批并行，ownership 相交的批由 planner 放入不同 wave；
- 共享文件只形成调度冲突，不触发传递闭包合并。

Round 2 只消费快速审查中的非 `CLOSED_LIKELY`：

- 每批最多 3 个 settings、10 个 paths，单 setting 最多 6 个 paths；
- 使用快速审查给出的精确 `round2_edit_targets` 与闭集 `change_kinds`；
- 替换 Round 2 targets/change kinds 后再次机械过滤 `NAV_CONTAINER_MODE_CHANGE`、`NAV_TOPOLOGY_MUTATION`，不得只依赖 Baseline 分类；
- `REVIEW_FAILED` 回退 Baseline targets；
- 目录、通配符、`..` 或不存在的路径全部拒绝。

Planner 生成 Round 1 packet 后不允许 Repair Agent 自行扩张 ownership。需要额外文件时，对该 key 记录 `PARTIAL/FAILED`；快速审查可在 Round 2 编辑前对该 key 做一次受控扩张：`ownership_expansion.revision=1`、新增 target 必须是存在的精确 `.ets` 文件，并且新增路径集合必须与 Round 2 targets 相对 Baseline ownership 的差集完全一致。Round 2 packet 写入 `ownership_expansion_locked=true`；Agent 编辑后不得再扩张或请求 revision=2。

Repair Agent 必须按工单的 `android_consumer_inventory`、`arkts_consumer_mapping`、`terminal_effect_chain`、`persistence_precedence` 和 `logical_setting_group` 修到末端。完成 repository setter、launcher 或中间 service 不等于完成；只有本批 ownership 内声明的全部 consumer/override/activation/platform-effect 节点均已接通，才能把该 key 写为 `APPLIED`。否则写 `PARTIAL` 并逐项列入 unresolved，交给快速审查形成一次精确扩张。

## 编辑和 source guard

第一轮源码编辑前：

1. `source_guard.py snapshot` 冻结全工程源码 manifest；
2. `export_fast_result.py mark-editing` 把保底终态切为源码风险；
3. 每批用 `source_guard.py batch-snapshot` 冻结 ownership 文件原文。

每个 wave 使用进入 wave 前的 rolling manifest。并行 wave 一次运行 `diff-wave`，其 `--next` 作为下一 wave baseline。出现 unowned file 时停止相应批并记录完整性异常，不通过扩张 ownership 将越权合法化。

## 逐 key 结果

每个 Repair Agent draft 使用：

```json
{
  "schema_version": 1,
  "mode": "fast-repair-result",
  "batch_id": "round-1-repair-001",
  "key_results": [
    {
      "key": "prefTheme",
      "status": "APPLIED | PARTIAL | NO_CHANGE | FAILED",
      "implemented": ["实际完成项"],
      "unresolved": ["剩余断链或失败原因"],
      "changed_files": ["entry/src/main/ets/..."]
    }
  ],
  "correctness_verified": false
}
```

`key_results` 顺序与 packet 完全一致。`APPLIED` 必须有 implemented 与 changed files 且 unresolved 为空；`PARTIAL` 必须有 changed files 与 unresolved；`NO_CHANGE/FAILED` 不得列 changed files，必须说明 unresolved。脚本按 key 状态派生 batch 状态，Agent 不得自行声明 batch 已完成。

结果发布前运行 source guard，PASS 后才调用 `fast_repair_plan.py publish-result`。这些状态只说明编辑执行情况，不说明行为正确。

## 两轮终点

Round 1 完成后只允许一次快速审查和一次 Round 2。Round 2 完成后立即构建安装，禁止：

- 再跑 Detector 或 AI correctness review；
- Admission、Closure、cache、preservation contract；
- Round 3、final static gate；
- 单元/UI/Skill/ArkTS 测试。

Round 2 结果无论为何都不阻止构建安装。
