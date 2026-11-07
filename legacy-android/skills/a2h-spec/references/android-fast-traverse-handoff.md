# Android 真机遍历交接（Spec Phase A）

## 定位

`android_fast_traverse` 是 Spec 阶段的 Android 运行时事实采集器。它使用 ADB 在已授权真机/模拟器上按 page × state 遍历，保存真实 PNG、UI XML、窗口/密度信息、动作收据和覆盖缺口。

它不生成 ArkTS、不修改 Android 工程、不做 HarmonyOS 验证，也不属于 Execute。

## 执行边界

1. Phase A 先完成页面清单、Dialog inventory 和源代码语义计划。
2. 模型先根据 `inspect` 输出编写一份应用特有的 profile（启动配方、业务读数、危险/副作用控件、额外滚动容器和范围上限）；禁止把全量页面计划硬编码进 profile。
3. 设备遍历由 a2h-spec 主线程独占；不要把设备控制交给通用 subagent。先 `inspect → profile → run`，执行器自动发现页面、视图态、返回和恢复；中途只有安全熔断或危险浮层无法关闭才停下。结束后读取 report，写一次 review，再用 `run --review` 补跑（对同一产物目录再执行 `run` 即续跑）。
4. 每次运行新建 `spec/.a2h/android-fast-traverse/<run_id>/`（下文 `<run>`），不得覆盖历史 run。遍历产物固定写在 `<run>/android_traverse_screenshots/`（下文 `<out>`；目录名不能改，执行器拒绝其他名字），包含 `page_NNNN_*`、`manual_NNNN_*`、`index.json` 和 `_aft/` 账本；profile 和 review 写在 `<out>/_aft/input/`。
5. 完成后必须检查 `_aft/report.json` / `report.md`、`index.json` 和 gap；只有真实 PNG/XML 配对且没有未处理的安全熔断，才允许进入 snapshot promotion。

## 命令入口

```bash
python3 <repo>/arkts-skills/skills/android_fast_traverse/scripts/android_fast_traverse.py \
  inspect --serial <serial> --package <package> --out <out>
# 根据 inspect 写 <out>/_aft/input/profile.json（run 默认读这里）
python3 <repo>/arkts-skills/skills/android_fast_traverse/scripts/android_fast_traverse.py \
  run --serial <serial> --out <out>

python3 <repo>/arkts-skills/skills/android_fast_traverse/scripts/android_fast_traverse.py \
  report --out <out>
```

运行要求 Python 3.10+、ADB 和已授权设备。缺设备、包身份或关键业务前置时如实记录阻塞，不用静态猜测替代真实截图。

## 产物分层

原始遍历证据必须保留：

```text
spec/.a2h/android-fast-traverse/<run_id>/
  android_traverse_screenshots/
    index.json
    page_NNNN_<Activity>/{screenshot.png,view.xml,meta.json}
    manual_NNNN_<Activity>/{screenshot.png,view.xml,meta.json}
    _aft/{input/profile.json,input/review.json,state.json,edges.jsonl,events.jsonl,report.json,report.md}
  snapshot-promotion.json     # 接管结果，写在 <run> 下，不进产物目录
```

选定的、report 已完成且真实配对的 page/state 才映射到：

```text
spec/baseline/ui-snapshots/<page_id>/
  view.xml       # 来自真实 UI XML
  visual.json    # 由 Spec 事实渲染器绑定真实观察与来源
  fixture.json   # 仅保存有 source_ref 的展示字段
  meta.json      # 保留运行时 activity/window/density/source 证据
```

映射必须记录 `run_id`、unit/state ID、PNG/XML SHA256、设备 serial、包身份和采集时间。原始证据只读，不能为了通过下游校验修改截图/XML。

## 与静态事实的关系

- 静态 `res-index`、源码 layout 和 source facts 仍由 Spec 负责；真机遍历只补运行时状态、真实 bounds、动态文字和截图/XML。
- 静态推导与运行时观察冲突时，两者都保留，写入 decision/open-findings；不静默覆盖来源。
- 没有真实运行证据的页面仅在 source_only 或 progressive 的有证据兜底分支使用 synthesized `view.xml`；保留 `view_xml_synthesized=true`、较低 confidence，progressive 另存 fallback_reason。runtime_required 不允许此降级。
- Execute 只消费接管后的 `spec/baseline`，不得在 Execute 内重新运行 Android 遍历器。

## 映射审核与接管

读 report/index 和源页面语义后，每条映射必须显式给出业务 `state_id`，不能把 aft.kind（page/view_state 等采集类型）当成业务状态。例：

```json
{"pages":[
  {"page_id":"page_0027_MainActivity","state_id":"main_weather","source_page_id":"page_0001_MainActivity"},
  {"page_id":"page_0027_MainActivity","state_id":"main_15day","source_page_id":"page_0003_MainActivity"}
]}
```

```bash
python3 <skills>/a2h-spec/scripts/promote_android_fast_traverse.py \
  --project-root <project> --run <run> --mapping <reviewed-mapping.json>
```

`--run` 传 `<run>`（也接受 `<out>`），`run_id` 取 `<run>` 的目录名；证据里的帧、unit、report 路径都相对 `<run>`。

调用前确认映射对应实际可见页面/状态；接管脚本检查完成状态、原始设备/包身份、activity、时间戳、PNG/XML 与 drift。同页多态分别写 `states/<state_id>/`，meta.runtime_evidence_by_state 保存逐态路径和哈希。主 runtime_evidence 只提供 converter 的默认帧，不能替代其他状态。原始 run 不修改；meta 同时保留来源设备、包身份、采集时间和 capture_kind。

## full-ui-v2 的引用交接

完整 UI 交付采用 [runtime-refs.md](runtime-refs.md)：先调用 promotion --draft 输出 schema 3 候选，
按完整 Activity 类名、click_path、trigger_element、文字/Tab 和源码审阅状态及宿主绑定；混淆 ID 不作 join key。
同一状态可保留多 capture/scroll frame；子组件通过 host_bindings 指向宿主状态与审核区域。
逐页填 states、host_bindings 或有依据的 zero_mapping/state_gaps，随后 promotion --mapping <schema3> --output <report>。
所有真实帧与元数据仍在 run 中，静态 view.xml 保留合成树；runtime/ 缓存由 Execute 按 refs 重建。
旧 schema 映射继续使用上文状态副本 API；新工程无需迁移旧实验的副本。
