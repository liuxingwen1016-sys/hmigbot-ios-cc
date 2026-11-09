<!-- when: planning or dispatching either repair round, including click-tail setting refill -->
<!-- topics: certified read closure, peer CAS, queued setting publication -->
# 修复轮次尾部补位

第一轮与第二轮使用同一规则：先派可领取的点击批，空闲槽再派已确认独立的设置批。设置修改隔离副本、停写后 submit，立即释放执行名额；保留 ownership 锁和未发布副本额度。正式设置 publish 等本轮点击全部发布或失败收口。返回 WAITING_FOR_INTERACTION_PUBLICATION 时跳过该队列项，继续点击完成事件和 claim-ready；不占 Agent 空等，不在主循环反复等待设置发布。

## 完整读集来自已有审查

Baseline 和 Quick 审查时，随既有逐入口分析记录修复会读取的完整 ArkTS 依赖：消费者、导入方法、公共服务、状态/持久化、配置与反向消费者；同时记录文件 SHA。只知道 edit_paths、直接 import 或同文件/不同文件，不能声明完整。动态寻址、全局注册或未追完的间接依赖标为未知。此记录是已有审查的附属数据，不新增一轮审查，也不减少设置原生消费者核验。

Baseline/Quick 的 `review_authoring.py scaffold` 为每项生成 `repair_read_set` 空骨架；在同一个原生 item 内填写以下附属字段，再用现有 `update-item` 保存。`reads` 是实际读取的 ArkTS 依赖；`writes` 只列本项确实需要编辑的目标，必须等于 `edit_targets`（Quick 为 `round2_edit_targets`）的路径集合。仅查看的 consumer/service 放 reads，不为方便把全部消费者都列为 edit target。

```json
{
  "repair_read_set": {
    "reads": ["entry/src/main/ets/Feature.ets", "entry/src/main/ets/Service.ets"],
    "writes": ["entry/src/main/ets/Feature.ets"],
    "reads_complete": true,
    "completion_basis": "已追踪当前消费者、间接调用和反馈路径；说明完整性依据",
    "unknown_dependencies": [],
    "source_sha256": {
      "entry/src/main/ets/Feature.ets": "<审查时的 SHA256>",
      "entry/src/main/ets/Service.ets": "<审查时的 SHA256>"
    }
  }
}
```

`source_sha256` 恰好覆盖 reads ∪ writes；使用真实读源得到的 SHA（可用 `review_authoring.py cite`），不能在未重读变更源码时更新哈希。未追完时写 `reads_complete=false`，在 `unknown_dependencies` 列出具体未知项。完整性不是脚本从 imports 或 targets 推断出来的。

统一 `complete` 在原生 Review 发布前读取声明，发布后将其与原生 receipt/seal、plan 和 draft SHA 一起封存到 fragments 下的 `repair-resources/`，外层 batch 保存引用。不改变原生 verdict/schema，也不把读集完整等同于行为正确。缺失或无效声明保留具体原因，原生审查结果仍按原规则发布。

注册 Repair plan 时默认**省略 `--resource-map`**。脚本自动按 batch 汇总本轮对应 Review 的封存证据：Round 1 只取 Baseline，Round 2 只取本次 Quick，并生成 `<repair-plan-stem>.review-resources.json`。所有 item 必须有可信完整读集，源根与 SHA 一致，声明写集的并集必须等于原生 ownership，且哈希覆盖原生追加 read_paths。任何缺失、源码漂移或 shared-owner/entry-only 重新规划导致的范围变化，都保持未认证并在诊断中解释，不能为凑并发缩小原生范围。手工 `--resource-map` 仅兼容已有完整证据流程；不要再自动填一份全 false 的文件覆盖默认汇总。

旧运行没有这些附属证据时继续保守执行。当前运行不能修改已封存记录来补认证；在下一次已启用的 Review 自然产出新证据。不另派 Agent 补审，不追加业务轮次。

## 判定和执行

待启动设置批必须与本轮所有尚未收口点击批满足：设置写集不碰点击读/写集，设置读集不碰点击写集。点击两端的完整读集声明和源码哈希也必须有效；包含 pending、running、queued 和等待封存批。不同文件但共享消费者/配置仍可能冲突。缺证据、独占批、哈希过期均不提前启动。先前成功依赖、全局名额照常生效。跨域同文件仍单 writer；setting 通道内部的同文件独立方法体可按[有限并发](function-scoped-repair.md)声明 function_scope，随当前封存读集自动交接。

提前 worker 以外层 claim 的 `reads` 和 `native_claim.overlap_read_paths` 为本批已声明读取范围；原生 `read_paths=all-authored-files` 是保守失效检测范围，不是扩大补位读集的授权。仅在已声明读取范围内使用 ArkTS 修复依据；若发现还需读取其它应用源码，停止修复、保留草稿，交主会话 `complete --failure-reason <原因> --agent-stopped` 排队失败意图并释放执行槽；点击收口后、失败尚未正式封存时可 `refresh --agent-stopped` 恢复原 Agent 以完整最新源码继续，不能私自扩读集。源码工具不能拦截任意 Agent 的读取，因此完整声明与遵守读取范围是该优化的前提；发布器仍机械保护正式源码和 ownership。

第一次提前领取设置时自动生成当前设置 manifest，冻结 peer plan/state/round/source root；每个 claim 的 base/worker 副本从最新 accepted_inventory 创建。点击继续发布后，设置适配器只接纳由原生 terminal receipt、source diff 和 accepted manifest 绑定的变化，记录 peer_publications；正式源码出现额外变化就停止，不能把外部编辑当新基线。已运行设置批声明读取的文件若被 peer 修改也拒绝接纳。点击发布未完成或待恢复时暂不接纳，先完成/恢复点击发布再重试。

设置原有 whole-source dependency_changes 与逐 key 结果保持，不把资源映射变成语义通过证据。设置 publish 的原生入口也检查 peer 已终止，不能绕过统一队列提前写正式源码；fail 在 peer 未结束时只封存失败意图并释放执行槽，待 peer 终止后再发布无源码改动的失败回执。点击 COMMITTING 时暂停新领取，恢复点击 journal 优先于设置 CAS 同步，避免恢复互相等待。第二轮收口仍不追加 Quick、Detector 或第三轮修复。
