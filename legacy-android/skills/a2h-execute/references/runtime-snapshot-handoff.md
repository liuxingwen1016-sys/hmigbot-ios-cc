full-ui-v2 时先读 ui-integration-1030.md 与 ui-delivery-contract.md，使用 frozen ui-inputs 和 runtime-refs；以下 runtime_evidence_by_state 说明用于 1030 原有冒烟入口。已声明 full-ui-v2 却缺 index 必须失败，不回退旧入口。

<!-- when: Stage 1 页面派发前确认真机遍历已经接管到 snapshots 时加载 -->

# 真机 snapshots 在 Execute 的消费契约

按本次 ui-capture-policy 分流：runtime_required 必须真实审计证据；source_only 允许源码支持的合成 view，无截图要求；progressive 仅允许有 fallback_reason 的明确合成兜底。两类兜底不标 runtime captured；选择 S1-V 时仍因缺真实基线返回 visual_blocked。新运行缺策略时回到 Spec 完成用户选择，不自行代选。

Spec 阶段的 `android_fast_traverse` 运行目录是只读证据库。Execute 不直接扫描
`spec/.a2h/android-fast-traverse`，也不从运行目录临时挑图；它只消费已经按 page/state
审计并接管到 `spec/baseline/ui-snapshots/<page_id>/` 的快照。

## 接管后的目录

```text
spec/baseline/ui-snapshots/<page_id>/
  meta.json                 # 含 runtime_evidence.status=audited
  visual.json              # 可选静态事实投影；缺失不阻断真实快照消费
  fixture.json             # 可选展示候选；缺失不阻断真实快照消费
  view.xml                 # 接管的真实 UIAutomator XML
  view.static.xml          # 接管前的静态结构备份（可选）
  android-runtime.png      # 接管的真实帧
```

`meta.json.runtime_evidence` 必须保存 `run_id`、`unit_id`、`state`、`frame_id`、
`pairing_contract`、原始 unit 相对路径、report/audit 相对路径及 PNG/XML SHA256；优化版还保留 device_serial/package/activity/captured_at。业务 state 来自已审核映射，不来自 capture_kind。Execute
converter 用真实 `view.xml`、真实 PNG 和静态 `visual/fixture` 的组合；静态结构不再覆盖
真实节点，但静态来源链仍是样式、资源和展示数据的权威输入。

## Execute 门禁

在每个 Stage 1 batch 派发 converter 前，生成当前 batch 的 page 列表并运行：

```bash
python3 $SKILLS_ROOT/a2h-execute/scripts/validate_runtime_snapshots.py \
  --project-root "$PROJECT_ROOT" \
  --pages-file spec/execution/runtime-pages-batch.json \
  --ui-facts-policy <legacy|static-v1-shadow|static-v1>
```

真实采集项缺 `runtime_evidence`、截图/XML、哈希不匹配或状态不是 `audited` 时阻断该 batch。多状态按 runtime_evidence_by_state[state_id] 逐一检查。source_only/progressive 兜底按上文检查 synthesized 与失败来源，不因没有 PNG 阻断代码迁移。不得
回退到 Execute 现场采集、合成截图或从模型描述补图。没有被本 batch 选中的页面仍按
`ui-plan` 的既有状态执行，不把其他页面的帧冒充当前页面。

## 与 Stage 1 生成的关系

- 真实 PNG 用于 converter 理解首屏比例、间距、裁剪和运行时可见状态；它不是业务数据来源。
- 真实 XML 用于结构和 bounds 参照；存在时才使用 `visual.json` 补充源码资源、样式链和 obligations。
- `fixture.json` 仅提供有来源的预览值；有真实截图不代表业务 wiring 已完成。两类 sidecar 缺失只写 warning。
- 滚动帧、诊断帧和未审计帧不进入主 snapshot；它们留在原始 run 目录供后续验证追溯。
- 页面状态必须与 `unit_id/state` 对账；同一个 PNG 不得复用于不同 page/state。
