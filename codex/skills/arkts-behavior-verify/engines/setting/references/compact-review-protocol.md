<!-- when: baseline detector 完成后、派发紧凑审计前读取 -->
<!-- topics: compact work order, review batch, exactly once -->

# Baseline AI 紧凑审计协议

## 目标

仅审计 `report.settings` 中 `findings` 非空的 Detector 候选，压缩成可直接交给单轮 Repair Agent 的工单。全量报告仍保留；plan 和合并结果的 `review_coverage` 记录入选/排除 key，排除项没有语义裁决。`semantic_review_complete` 只表示入选候选审查完成。这里仅“发现与定位”，不建立验证闭环。

## 分批命令

```text
python <skill-dir>/scripts/compact_review.py plan \
  --report <out>/baseline/report.json \
  --android-root <android_root> --arkts-root <arkts_root> \
  --packets-dir <out>/baseline/batches/packets \
  --out <out>/baseline/batches/review-plan.json
```

默认每批最多 8 个 setting、最多四批并行。每个 Agent 只处理一个 packet，不修改源码，不读取其他 batch 的 draft/fragment。

## 单项 schema

每个 setting 输出一个对象：

```json
{
  "key": "setting_key",
  "status": "FIX_REQUIRED | NO_DEFECT | UNCERTAIN | UNREVIEWED",
  "android_expected_behavior": "设置改变后的 Android 可观察行为",
  "arkts_break": "ArkTS 断链位置或无缺陷理由",
  "active_consumers": ["path::callable"],
  "android_consumer_inventory": [{"id":"稳定 consumer id","path":"...kt|java","callable":"...","effect":"用户可观察效果"}],
  "arkts_consumer_mapping": [{"android_consumer_id":"...","status":"MATCHED | MISSING | NOT_APPLICABLE","path":"entry/src/main/ets/...","callable":"...","anchor":"...","notes":"..."}],
  "terminal_effect_chain": [{"role":"SETTING_INPUT | PERSISTENCE | CONSUMER | ACTIVATION | OVERRIDE_PRECEDENCE | PLATFORM_EFFECT | OBSERVABLE_RESULT","status":"CONNECTED | BROKEN | MISSING | NOT_APPLICABLE","side":"android | arkts","path":"...","callable":"...","anchor":"...","effect":"..."}],
  "logical_setting_group": ["launcher/backing/temporary override 等同一语义组 key"],
  "logical_setting_group_complete": true,
  "persistence_backend": "backend/accessor",
  "persistence_precedence": ["temporary override > persisted value > default"],
  "persistence_precedence_complete": true,
  "activation_timing": ["HOT_CHANGE | NEXT_ACTION | NEXT_ITEM_OR_SESSION | COLD_START"],
  "default_and_fallback": "默认值与异常/覆盖 fallback",
  "value_branches": ["entryValue/枚举分支及语义"],
  "anchors": [{"side":"android|arkts","path":"...","callable":"...","anchor":"..."}],
  "domain": "playback | feed | download | appearance | ...",
  "edit_targets": [{"path":"entry/src/main/ets/...","role":"PERSISTENCE_FOUNDATION | CONSUMER | ACTIVATION | UI_SURFACE | STARTUP","callable":"...","anchor":"...","expected_change":"..."}],
  "edit_paths": ["兼容字段；由 edit_targets 的 path 派生"],
  "change_kinds": ["LOCAL_EFFECT | EXISTING_ROUTE_ACTIVATION | NAV_CONTAINER_MODE_CHANGE | NAV_TOPOLOGY_MUTATION"],
  "risk": "LOW | MEDIUM | HIGH",
  "uncertainty": "已知不确定性；没有则为空字符串"
}
```

`FIX_REQUIRED` 必须有 Android 行为、ArkTS 断链、完整 Android consumer inventory、按 inventory 顺序 exactly-once 的 ArkTS mapping、至少覆盖 `PERSISTENCE/CONSUMER/PLATFORM_EFFECT` 的终端链、逻辑设置组与优先级、至少一个 ArkTS anchor，以及最多 6 个存在于 `arkts_root` 内的精确 `.ets` edit target。mapping 不得因为已有一个 consumer 就漏掉 Android 的其他活动 consumer。终端链必须追到实际平台效果原语或用户可观察结果，不能停在 repository/service setter。`NO_DEFECT` 的 targets/paths 必须为空，且 mapping/chain 不得仍有 `MISSING/BROKEN`。`UNCERTAIN` 必须填写 uncertainty，不能伪造成缺陷。`UNREVIEWED` 只能由主 Agent 在同批两次失败后机械生成。

`plan` 会在 packets 目录生成 `active-implementation-map.json`，记录 EntryAbility、pages、viewmodels、components、dialogs、action button 等应用表面到相对 import graph 的最短链。发布时为 edit targets 和已匹配 ArkTS consumers 自动生成 `active_target_evidence`；存在可达同名替代实现时，未被活动链引用的 target 会被拒绝，Agent 必须重选实际调用链中的实现。两套同名实现若分别可达，不做全局唯一化猜测。

新 `FIX_REQUIRED` 工单还必须用非空 `change_kinds` 标明修改语义。打开已经存在的页面或 `TagSettingsDialog` 等弹窗使用 `EXISTING_ROUTE_ACTIVATION`，允许自动修复；只有改变导航容器模式，或增删、隐藏、重排静态导航目的地时，才分别使用 `NAV_CONTAINER_MODE_CHANGE` / `NAV_TOPOLOGY_MUTATION`。发布脚本会把后两类机械转成 `UNCERTAIN`、清空 edit targets，并记录 `NAVIGATION_TOPOLOGY_AUTO_REPAIR_FORBIDDEN`；不得通过改写 setting key 或降低 `risk` 绕过。

路径使用相对 `android_root` / `arkts_root` 的 `/` 分隔格式；拒绝绝对路径、`..`、目录和通配符。

## 审计关注点

每项最少回答：

1. Android 写入的是哪个 key/backend/default？
2. Android 有哪些活动 consumer；ArkTS 是否逐个映射，还是只接了其中一个？
3. 生效属于热更新、下一动作、下一 item/session 还是冷启动？可多选。
4. ArkTS 是否写入同一语义后端，consumer 是否读到最新值，最终是否到达音频/网络/通知/调度/页面弹窗等真实效果原语？
5. list/enum 的每个 Android `entryValue` 是否有对应分支？
6. launcher/backing key、临时 override、持久化值与默认值的优先级是否完整？
7. 若有同名 ArkTS 实现，哪一套能从应用表面沿 import chain 到达？
8. 若修复，覆盖完整终端链的最小 edit paths 与精确 anchor 是什么？

不要求六节点 Admission、Review cache、Closure 或 post-fix 证据；consumer inventory 与 terminal effect chain 本身是紧凑工单的必要内容，不属于被移除的重型复审。

## 发布与合并

Agent 写 `<batch-id>.draft.json` 后：

```text
python <skill-dir>/scripts/compact_review.py publish \
  --plan <review-plan.json> --batch-id <batch-id> \
  --draft <draft.json> --fragments-dir <fragments-dir>
```

两次 Agent 失败后：

```text
python <skill-dir>/scripts/compact_review.py mark-unreviewed \
  --plan <review-plan.json> --batch-id <batch-id> \
  --reason <reason> --fragments-dir <fragments-dir>
```

全部 batch 封存后：

```text
python <skill-dir>/scripts/compact_review.py merge \
  --plan <review-plan.json> --fragments-dir <fragments-dir> \
  --out <out>/baseline/baseline-findings.json
```

Merge 只保证覆盖与 schema，不把 AI 判断升级为已验证事实。
