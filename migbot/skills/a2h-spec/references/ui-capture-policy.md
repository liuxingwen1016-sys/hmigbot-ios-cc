# Spec 阶段 UI 采集策略选择

Phase A 开始前必须检查 `spec/.a2h/ui-capture-policy.json`。文件不存在时不能直接进入静态合成，必须向用户给出以下三项选择：

1. **runtime_required（推荐）**：页面清单和状态计划完成后，自动调用 `android_fast_traverse`。按 `inspect → profile → run → report → review/resume` 执行，并审核选定页面与业务状态的映射；设备、包身份或路线前置缺失时阻断，不静默合成。
2. **progressive**：自动优先执行真实遍历；已采集状态进入 baseline，暂时无法采集的状态保留 pending 和阻塞原因。只有具备明确失败证据并经过兜底校验的页面才允许合成，合成结果不能标成真实采集。
3. **source_only**：用户明确选择不使用设备，Phase A 只做源码/资源事实和合成 view.xml；所有页面 confidence 降级，不能声称有真实截图或运行时 bounds。

选择结果写入：

```json
{
  "schema_version": 1,
  "policy": "runtime_required",
  "selected_by": "user",
  "selected_at": "<UTC>",
  "reason": "<用户选择或原始指令>"
}
```

已有文件沿用本轮策略；用户明确改变策略时生成新 revision，不覆盖历史采集账本。`ui_facts_policy=static-v1` 只控制静态事实生成方式，不能覆盖上述采集策略；只有 `source_only` 才允许完全不调用设备遍历。

## 执行闸

`runtime_required` 和 `progressive` 按优化版 CLI 执行；page/state 清单用于结束后的审核映射，不作为执行器的逐页 plan：

```bash
# <out> = spec/.a2h/android-fast-traverse/<run_id>/android_traverse_screenshots（目录名固定）
python3 <skills>/android_fast_traverse/scripts/android_fast_traverse.py inspect \
  --serial <serial> --package <package> --out <out>
# 根据 inspect 写 <out>/_aft/input/profile.json，范围上限放入 profile.limits。
python3 <skills>/android_fast_traverse/scripts/android_fast_traverse.py run \
  --serial <serial> --out <out>
python3 <skills>/android_fast_traverse/scripts/android_fast_traverse.py report --out <out>
# 仅有待审阅/重试项时，审核写入 <out>/_aft/input/review.json 后补跑并刷新 report（同一 <out> 自动续跑）：
python3 <skills>/android_fast_traverse/scripts/android_fast_traverse.py run \
  --serial <serial> --out <out> --review <out>/_aft/input/review.json
```

不调用旧版 validate/audit/--plan。完成后按 [遍历交接](android-fast-traverse-handoff.md) 审核每条 page/state 映射，调用 promotion，再运行 Execute 的策略感知输入检查；report 完成不等于每张帧都已审计。缺少真实执行和映射审核证据，不能写 runtime captured。

`source_only` 必须记录用户选择、`view_xml_synthesized=true` 和降低的 confidence；不要求截图。progressive 的合成兜底还须在该页 meta 保留非空 `fallback_reason`（实际采集失败及证据引用），未经说明的缺失不能自动降级。上述页面可进入代码迁移；用户选择 S1-V 时，缺真实 Android baseline 的 case 仍返回 visual_blocked，不能冒充对比通过。

## 新工程的双维度选择与 refs 交接

先 `ui_pipeline.py preflight --project-root <project>`；缺失项给选项，已明确的选择复用。
静态事实推荐 static-v1，运行时采集推荐 runtime_required；progressive/source_only 仍按 1030 原规则保留真实失败和降级。
configure --facts <mode> --runtime <policy> --reason <实际选择引用> 写入两项，不能由静态模式推断是否使用设备。
无人值守只有现有授权允许 default-policy 选择时才使用该来源，不能标成用户亲自确认。
新完整 UI 管线读取 runtime-refs.json，promotion 使用 schema_version=3，见 runtime-refs.md。
上文状态副本契约仅用于未采用 full-ui-v2 的 1030 旧入口；两种策略的生成与消费必须成对选择。
