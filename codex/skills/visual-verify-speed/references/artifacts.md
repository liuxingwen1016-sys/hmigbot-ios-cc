# 产物目录与字段

```
<鸿蒙工程>/
├── spec/
│   ├── fix/                                       ★ 问题单（跨轮保留，按轮建目录）
│   │   ├── _state.yaml                            schema_version / current_round / last_verifier_* （其它键原样保留）
│   │   └── round-N/
│   │       ├── _index.md  _summary.md  _delta.md   索引、统计（总计 / 页面维度 / checks performed / Top 10）、与上一轮差异（第 1 轮起）
│   │       ├── _source.json                       本轮由本 skill 写入的标记 + 被机械复核撤回/降级的判图结论
│   │       └── ui/
│   │           ├── ALIGN_P<页号>_<差异类型>_<slug>.md
│   │           ├── ALIGN_P<页号>_page_missing_hmos.md
│   │           ├── ALIGN_P<页号>_android_baseline_blocked_<slug>.md
│   │           ├── CRASH_P<父页号>_nav_failed_<From>_to_<To>_P<目标页号>.md
│   │           ├── CRASH_P<页号>_app_crash_on_nav.md   CRASH_P<根页号>_app_crash_on_launch.md（启动即崩溃）
│   │           ├── BLOCKED_P<页号>.md                  占位：本轮没采到（不是缺陷，不派修复）
│   │           └── _systemic/SYSTEMIC_<slug>.md       同一问题 ≥3 页
│   └── visual-verify/                             ★ 本 skill 的工作目录（--work 默认值）
│       ├── config.json                            安卓产物、鸿蒙工程、安卓工程、包名、Ability、hdc 设备
│       ├── progress.json                          当前轮次；每轮走查范围（scope：null=全部，列表=只重走这些安卓单元）
│       ├── report.md                              最近一轮的报告（每轮覆盖）
│       ├── screenshots/                           ★ 问题单只引用这里
│       │   ├── android/<页号>.png  <页号>.android.xml  <页号>_seg_NN.png（后续帧）
│       │   ├── harmony/round-N/<页号>.jpeg  <页号>.hmos.json
│       │   │   └── _evidence/<页号>__f<k>.jpeg|.hmos.json  <页号>__failed.jpeg|.hmos.json（走不通那一步的现场）
│       │   └── sbs/round-N/<页号>.jpeg     blocks/<页号>_block_NN_sbs.png（后续帧）
│       ├── walk/                                  走查工作区（问题单不引用）
│       │   ├── index.json                         每个安卓单元当前有效的鸿蒙采集（pair.android = 安卓单元号）
│       │   └── round-N/<安卓前缀_号>_<鸿蒙页面>/   screenshot.png view.json screenshot_scroll_<k>.png view_scroll_<k>.json meta.json
│       ├── rounds/round-N/                        轮次工作区
│       │   ├── pairs.json                         配对与预筛结论（auto_pass / judge / judged / carried / not_paired），canonical 路径
│       │   ├── metric/<安卓单元>__f<k>.oracle.json 结构 oracle、度量表（dp/vp）、整体偏移、画不出来的元素、字号疑似不同
│       │   ├── metric/<安卓单元>__f<k>.mdiff.json  度量差异
│       │   ├── coverage.json                      覆盖账
│       │   ├── judge/batches.json  batch_XX.md    判图批次与任务书；judge/results/<安卓单元>.json 判图结果
│       │   └── fix/schedule.json  snapshot.json  fixcheck.json  修复排程、修复前源码快照、修复复核结果
│       └── cache/                                 走查状态与账本
│           ├── input/profile.json                 鸿蒙 profile
│           ├── state_round-N.json                 走查断点：单元状态、缺口、计数、设备时间
│           ├── events.jsonl  edges.jsonl  sessions.jsonl
│           ├── model_requests/<id>/               弹窗请求与决策
│           ├── popup_rules.json  android_layout_index.json  anomalies/
└── docs/autofix-log/round-N/batch.md  fixcheck.md  修复批次（每组写集与问题单）、修复复核（flag 与改动文件）
```

页号 = 安卓基线单元号（`page_0024_*` / `manual_0024_*` → `P0024`），跨轮稳定。两端只跑应用当前能访问的一个状态，截图不按账号状态分目录。

## 问题单

frontmatter（顺序固定）：

```yaml
id / title / source: visual-verify / layer / kind / severity
fixer_layer / category_pattern / suggested_files / related / systemic_root / affects
v4_edge / blocks_subtree / reason_slug              # 仅 nav_failed
evidence                                            # 只写 screenshots/ 下的 canonical 路径（相对工程根）
page_id / capture_mode / similarity / multimodal_severity / is_migration_bug
disposition / disposition_reason / disposition_set_at_round
```

- `kind`：`ALIGNMENT_DIFF` / `CRASH` / `BLOCKED`（占位，`status: blocked`、`severity: P3`、`suggested_fix_owner: noop`、`blocked_by` 指向挡住它的问题单或基线截图）/ `SYSTEMIC`。
- `severity`：high + 迁移缺陷 → P0，high + 非迁移缺陷 → P1，medium → P1，low → P2；CRASH 一律 P0；`android_baseline_blocked` 一律 P1。
- `title`：`[页号] 类别: 描述`，类别 布局 / 颜色 / 字体 / 间距 / 组件 / 图标 / 文案 / 缺失 / 多余 / 顺序 / 滚动 / 导航，总长 ≤ 60 字。
- `slug`：判图的 `key`（3–30 位 `a-z0-9-`）；没有可用英文时按页内顺序 `idx01`、`idx02`…；字号单用鸿蒙文件名 + `font`。
- `similarity`：判图给出的整体相似度；没有时用"结构匹配度 ×（0.5 + 0.5 × 度量在 4dp 内的比例）"。
- `capture_mode`：`single` / `long`（多帧）/ `web`（网页）。
- `v4_edge`：`from_page`、`to_page`、`trigger{label, resource_id, type}`、`android_verified: true`、`hmos_failed_reason`（trigger_not_found / click_failed / verify_timeout）、`nav_mismatch_type`（missing_handler / wrong_target / semantic_diff）。
- nav_failed 的 `suggested_files`：显示入口文字的鸿蒙文件（字面量或 `$r('app.string.…')`，多个时取同时显示安卓同屏其它文字最多的）；入口文字在源码里找不到（图标、列表数据）才退到上级页面文件。
- 走查缺口怎么出单：控件找不到 / 点了没变化 / 被上层盖住点不到 / 落到了安卓另一页 → `CRASH_*_nav_failed_*`；上级已出导航单或被判成另一页 → 下级只出 `BLOCKED`；安卓点的是列表内容而鸿蒙同一列表里没有这一项也没有同类项 → `BLOCKED`（列表本身缺失由上级页的对比单负责）。

正文：

```
# {title}
> 🔴 修复前必读（视觉类才有）：先读 sbs 对比图
## 1. Spec 引用          来源: 安卓基线截图；> 来源: 安卓源码 file:line；> android_anchor
## 1.5 必用参考（机械生成，禁编辑）
## 2. 期望
## 3. 实际              description / harmony / 证据 / root_cause_hint / element / region
## 4. 源码缺口           <鸿蒙文件>:<行号或 unknown> — …；安卓对照行
## 5. 修复建议
## 6. 尝试过的修复方案（仅由修复方追加，禁删历史条目）
## 7. 实际可达路径（reach_path，由安卓基线自动注入，禁手工编辑）
```

每轮写完自动跑格式自检（文件名 = id、必填字段、fixer_layer、正文 1–5 段、SYSTEMIC 的 affects、页面字段、similarity 范围、ID 唯一、evidence 存在且不指向工作区、nav_failed 字段、BLOCKED 的 blocked_by）。

## 鸿蒙 meta.json（walk/round-N/<单元>/meta.json）

- `pair`：`android`（安卓单元号）、`method`（id / text / pattern / partial / similar / beside / position / family / context / root / manual，对应 hmos-walk.md 的认控件证据）、`matched_label`、`confidence`（confirmed / weak / unconfirmed / unknown）、`text_overlap`、`path_methods`
- `label`、`kind`：抄自安卓单元
- `harmony`：`bundle`、`ability`、`page_path`、`overlay`（'' / layer / win）
- `density_factor`、`app`（versionName 等）
- `sig`：页面身份（页面路径、弹层、结构、文字、选中项），后续轮次回位用
- `capture`：帧数、停止原因（bottom / no_container / small_move / screen_changed / identity_unconfirmed / …）、是否退化、主容器、横向条、`max_swipes`
- `screenshots[]`、`view_jsons[]`（相对 `walk/`）、`round`、`timestamp`

## 轮次

- 第一轮从 `spec/fix/_state.yaml` 的 `current_round` 开始（已有的 `round-N` 不覆盖）。`next-round` 把下一轮范围设为上一轮问题单涉及的页（含 `blocks_subtree`）和缺口单元，`--full` 设为全部，并把 `current_round` 推进一位。
- 不在范围内的单元沿用 `walk/index.json` 里的旧采集（状态 `carried`），`pairs` 对它们沿用上一轮结论；鸿蒙证据（截图哈希 + 文字）没变的单元即使重走了也沿用结论，不再判图。
- 问题单 id 跨轮稳定，`_delta.md` 按 id 列 fixed / new / unchanged。同 id 的 §6 修复记录、人工处置（skipped / manual_review / wont_fix）和上轮 `fixcheck` flag 带进新单；出现满 3 轮或修复满 3 次标为顽固问题（`_summary.md` 单列），修复满 5 次仍未通过转 `manual_review`。
- `pairs.json` 每项记 `pipeline`（判图管线版本）、`evidence_hash`；沿用上一轮结论要求两者都相同，约 10% 的沿用对子标 `sentinel` 重判；同一轮重跑 `pairs` 时已判过且证据不变的对子沿用（`judged`）；缺交付截图的对子记 `not_paired` / `missing_artifacts`。
- `next-round` 的范围 = 上轮问题单涉及的页 + 缺口单元 + 修复改到页面文件的单元 + 屏上显示了被改文件里文字（字面量或字符串资源）的单元（Navigation 工程所有单元同一个页面路径，靠这一条缩小范围）；改到的文件没有文字（样式、资源）或它的文字哪个单元都没显示时全部重走。
