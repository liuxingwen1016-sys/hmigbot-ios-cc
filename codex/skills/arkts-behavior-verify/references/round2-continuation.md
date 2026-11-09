<!-- when: 用户在单轮交付后要求继续第二轮、Quick Review 和修复 -->
<!-- topics: continue-round2, sealed parent, inherited evidence, resume, Quick, Round 2 -->

# 第一轮结束后继续第二轮

“继续第二轮 / 接着 quick review 和修复”表示承接已有第一轮。先从当前任务记录及 `run-config.json` 找到已完成的 `single-round` 原运行，不按目录最新时间选中误开的 full-repair 运行。用户明确要求从头重新审查时，按[新运行入口](unified-workflow.md#0-初始化源码保护和共享预检)执行 `init`，默认仍为 single-round；只有同时明确要求完整两轮时才添加 `--full-repair`。从头重跑本身不授权增加轮次。

```text
python <skill-dir>/scripts/unified_pipeline.py continue-round2 --from-out <原U>
```

默认输出为原目录的同级 `<原目录名>-round-2`。也可用 `--out` 指定独立同级目录；同一原运行只建立一个续跑。命令返回实际 `out` 和 `current_stage`，此后 `U/SO/IO` 都使用返回的新路径。重复执行会恢复已有续跑；返回 `ALREADY_FINALIZED` 表示第二轮已结束，不再追加下一轮。原运行仍未完成时，先恢复原运行到第一轮封存。

需要只检查可续跑条件时追加 `--check-only`；它不写产物、不启动 Detector、模型、构建或安装。

## 证据与源码

脚本校验原运行的配置锁、结果锁、两类结果、前两阶段收口及已记录发布哈希。以原始字节复制两个 lane 的 `baseline/`、`round-1/`，在 `continuation.json` 冻结来源、SHA 和当前源码快照。复制品是继承证据，内部路径仍指向原运行；保持原目录可读，不手改路径、SHA 或历史 verdict。新 dispatcher 只有 `quick-review → round-2`，没有伪造的前两阶段完成批。

新版本封存时记录 `terminal-source.json`。Android oracle 已变化时拒绝沿用旧 Baseline；ArkTS 变化列表交 Quick 对当前完整链路复核。旧版没有终态快照时明确标记 `LEGACY_*`，能读取末 lane 的 accepted inventory 时列出相对差异；它可能早于编译纠偏，不能声称源码等同第一轮结束状态。所有续跑都审查原 Baseline 的全部 `FIX_REQUIRED`，不因 APPLIED 或当前 Detector 变绿而排除。新增功能不自动纳入旧 Baseline 的覆盖声明。

缺证据或哈希不符时报告具体缺口，保留已存在记录，不自动退回从头完整跑。已误开的 full-repair 输出不能冒充原 Round 1；有其它修复 writer 活动时，先解决同一工程的写入冲突。

## 从 Quick 开始

1. 首次进入新续跑时，为 SO/IO 各建立当前源码的 `initial-source-manifest.json` 并按原生协议 mark-editing。按[统一流程第 0 节](unified-workflow.md#0-初始化源码保护和共享预检)在新 IO 重新生成及共享预检；这是交付准备，不执行 init 或 Baseline。旧构建、安装、运行时成功证据不复制为本次交付结果。
2. 按[统一流程第 4 节](unified-workflow.md#4-联合-post-round1-与-quickfull-repair-或第二轮续跑)执行 `detect --phase post-round1`，随后使用新 SO/IO 下继承的 Baseline findings、Round 1 plan/results 创建两类 Quick 计划。这次扫描是 Quick 的正常输入，不是新 Baseline。
3. 注册 `quick-review`、seal-stage、派发独立审查 Agent、发布和 merge。向审查 Agent 说明 `continuation.json` 的 source_audit 与历史范围；读取最新双端源码。对 Round 1 的漂移说明、原生发布 sidecar、scope/SDK 证据仍使用原协议。
4. 按[统一流程第 5 节](unified-workflow.md#5-round-2full-repair-或第二轮续跑)生成新的 Round 2 工单、manifest、ownership 及读集，注册 `round-2` 后修复。只恢复新续跑自己的 batch，不派发继承目录中的 Round 1 工单。
5. 执行本次集中构建/安装和 finalize/validate。编译纠偏权限取本次 Round 2 ownership；历史 Round 1 ownership 不扩大本次编辑范围。报告分别列出 `inherited_stages` 与 `executed_stages`，前两阶段的历史统计不能计成本次执行批数或耗时。

恢复时根据已有 `dispatch.json`、Detector marker、plan 和 seal 跳过已完成准备，沿原 Agent/batch 继续；不要重复生成冻结计划。Quick 已结束时直接恢复 Round 2，第二轮封存后结束。

由 a2h-verify 等外层入口调用时（CHECK 编号以调用方当前契约为准），同样优先按用户“继续第二轮”的意图走本入口；更新其汇总时引用返回的新 U，并注明 parent_out。宿主入口若仍要求重开完整 run，以本续跑入口承接用户范围，并报告宿主文档版本不一致；运行期间不临场重写已部署 Skill。
