<!-- when: 派发 Stage 1 Batch 收尾（a2h-closer, mode=batch，每 Batch 末尾一次）时加载本段 + _common.md -->
<!-- topics: Batch 收尾派发参数, mode=batch, a2h-closer -->

# §2. Stage 1 Batch 收尾派发（a2h-closer, mode=batch）

> **收尾协议单源 = `a2h-closer` agent 定义**（mode=batch 三步：资源残量兜底 → 源布局尺寸复核 → writeback manifest；批内无编译，统一编译在 Base-7）；本文件只是派发参数模板。公共占位规则 §2.1 + 单写者纪律见 [`_common.md`](./_common.md)，派发时一并 Read。

```
Agent(
  prompt="mode=batch。你是 Stage 1 Batch [{batch_n}] 的收尾者，本批所有并发 converter 已完成（已按直写纪律 append 资源键，你只补漏不重写）。按你的 agent 定义 mode=batch 两步协议执行。

  本批页面: {batch_pages}                    # 序号 + ArkTS 文件路径清单
  本批生成/改动的 .ets: {batch_ets_files}
  Android 源根: {android_source_dir}
  HarmonyOS 工程根: {harmony_project_dir}",

  subagent_type="hmigbot:a2h-closer"
)
```

**HARD-GATE**（主线程侧）：writeback manifest 必产 → 主线程跑 `apply_writeback.py` 成功（brief 落盘 + 账本翻转）才进下一 Batch（批间无编译门）；崩溃恢复 = manifest 在则重跑 apply。
**尺寸复核回派**（主线程侧）：信封 `layout_dims_fail[]` 非空 → apply 之后、进下一 Batch 之前，对这些页各重派一次 converter（prompt 只附该页的 gate 输出，要求补齐或写「尺寸偏差」段）；重派后仍 FAIL → 记入迁移报告风险，不阻断。

## full-ui-v2 装配（与旧模式逐批收尾分开）

本模式等所有生成批的原始 G0 归档并汇总后，只派一个 mode=batch closer，参数给完整 inventory 和全部单元输出。
按 unit.output/integration 统一装配，保留真实业务门槛，受控 Preview 使用正式组件；继续资源 sweep 和源尺寸复核。
writeback intent 必填 `stage1: {phase: assembled}`；返回 ASSEMBLED/STRUCTURAL_ONLY，不报告 Stage 1 完成。
主线程随后归档 G1、构建并做强制 S1-V；完整完成写回由验收脚本判断。
