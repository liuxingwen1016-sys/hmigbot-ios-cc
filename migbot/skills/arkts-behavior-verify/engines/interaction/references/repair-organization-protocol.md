<!-- when: 每轮 Repair plan 冻结前、已确认工单含重复 callable 时读取 -->
<!-- topics: canonical shared cause, common prerequisite, local ownership, organization receipts -->

# 共享根因归并与公共/入口拆分

同文件不同语义导致至少三个批次争用、又无法证明同因时，先评估
[target writer 分配](overlap-execution-protocol.md)，从原始计划转换，不与本协议叠加。

在 Baseline 质量闸或 Quick merge 完成后、该轮 Repair claim 前执行。主会话只裁决
已经获准修复的重复目标，不重做逐入口双端审计、不增加修复轮次。原始 findings 保持不变。

```text
python <skill-dir>/scripts/repair_organization.py plan \
  --findings <out>/baseline/baseline-findings.json \
  --project-root <arkts_root> --round 1 \
  --out <out>/round-1/organization-input.json
```

Round 2 使用 `--round 2 --quick-review <out>/quick-review/findings.json` 和 round-2
输出目录；必须依据当前 Quick targets、当前 detector 入口与源码重新确认，不能复用 Round 1 证明。

先运行 `workflow_packets.py organization --input <organization-input.json>`，读取去重后的
候选索引、工单目标与 `closure_map`；完整条目加 `--contract-id <id>` 回读。
同一工单不再随每个候选重复展开。按真实公共断点确定主要共享修法；公共生产者到
消费者之间的责任在动手前核对，已有代码已满足的环节无需新增 owner。
缺失目标的角色仅是注意项，不能自动升级缺陷或授权新文件；确认缺口写入原有
工单证据/后续回执，越过当前 ownership 的残留交既有 Quick，不临时扩写。

`base_plan` 保留完整工单以供按需回读，
不要整份重复塞入模型上下文。新 candidate_version=2 按 SOURCE 路径聚合候选，
让不同 callable 描述与 anchor 写法有机会对照；文件相同不证明同因，必须检查真实函数和断点。
没有候选时直接运行原 Repair plan；有候选时主会话在现有规划上下文完成一次紧凑裁决。
沿共享目标读取必要源码，确认相同公共断点、修法和参数语义。先逐 target 判断公共子集，再判断入口剩余目标；入口动作、参数或终态不同本身不能否定公共子集。统一采用一份公共描述，
避免独立 reviewer 的措辞差异阻止合并；各入口检查仍独立。

把真实裁决写入 `<round>/organization-draft.json`，格式由 input 的 instructions 给出：

- `input_sha256` 绑定输入；`decisions` 按 candidate 顺序逐项覆盖。
- 每个 decision 有 `candidate_id / groups / unshared`；所有候选成员恰好出现一次。
- group 的 `contract_ids` 至少两个；`targets` 是各成员已经获准的公共 SOURCE 目标子集。
  canonical target 必须来自某成员已获准的目标；expected_change 可使用统一描述。
  原 anchor/callable 不一致时，每个成员提供 target_mapping：
  `reviewed_target_indices` 是本成员 edit_targets 的零基索引；equivalence_evidence 是
  当前源码的 path/line/excerpt，必须覆盖原 anchor 和 canonical anchor。
  映射保持原路径和角色，不增加写范围；语义等价由真实规划上下文裁决，脚本不推断。
- `proof` 包含共同的 `cause/correction/command_semantics/shared_evidence`。
  `members` 按 ID 顺序分别提供真实 `entry_evidence` 和五项 `entry_checks`。
  引用必须命中当前源码，入口位置由可信 Detector 派生。
- 同一入口在本次组织中最多归入一个公共组；选择主要共享断点，其余已获准目标留在入口工单。
  多目标 callable 可保留多个公共 target。同文件公共/局部修改允许拆分，但局部批依赖公共批
  发布后才启动，并保留公共补丁。普通配置目标、behavior replacement、无可信当前入口位置
  或无法证明等价的项写入 unshared 并给具体原因。不能只写“anchor 不同”作为未归并理由。

```text
python <skill-dir>/scripts/repair_organization.py publish \
  --input <out>/round-1/organization-input.json \
  --draft <out>/round-1/organization-draft.json \
  --out <out>/round-1/organization.json
python <skill-dir>/scripts/fast_interaction_repair.py plan \
  --findings <out>/baseline/baseline-findings.json \
  --project-root <arkts_root> --round 1 \
  --organization <out>/round-1/organization.json \
  --out <out>/round-1/repair-plan.json
```

格式/证据错误在同一上下文纠正；确实不能合并时如实裁决 unshared，不删除原工单。
超出批次字节预算时缩短非必要叙述或减少每个确认组成员，其余成员走原路径。
组织产物、输入、draft、seal 全部位于该轮 out 内。已初始化 dispatcher 的 plan 不重写，
运行中 claim、锁与源码 manifest 不迁移到新计划。

## 生成的两种形态

纯公共修法使用现有 `SINGLE_SHARED_REPAIR_WITH_ENTRY_CHECKS`，仍逐入口返回完整结果。
若组内已有只需公共修法的入口，由这些入口批拥有公共文件；含局部修改的成员只保留局部
ownership，依赖公共批。公共/局部边界按已经确认的 targets 划分，不按 service 文件名猜测。

若组内所有入口都同时需要公共和局部修改，生成一个
`execution_scope=SHARED_COMPONENT_ONLY` 前置批，然后生成局部入口批。
前置批仅以一条代表工单回执描述公共修改，`affected_contract_ids` 指明全部依赖入口。
它只允许 `PARTIAL/NO_CHANGE/FAILED`，完整入口的 observable 义务保持未决；不能报 APPLIED。
公共源码差分计入最终 changed_files，公共代表回执不重复计入 contract 数、执行次数或最终 verdict。
公共修改实际影响的入口仍计入 unique_changed_contract_ids。

局部批保留原 Android 期望、完整效果链、九项义务及独有 targets。
`shared_dependency` 提供公共 target、逐入口证明和前置 batch IDs；claim 返回
`shared_dependency_receipts`，绑定发布状态与 receipt SHA。读取当前可信公共实现，
每条入口回执补充 `shared_dependency_checks`，按 batch_ids 顺序写
`batch_id / receipt_sha256 / status(CLOSED或UNRESOLVED) / evidence`。
公共回执不能替代本入口参数、variant、consumer 和 observable 的检查。
前置批失败后，局部批仍可执行自己的有界修复，公共依赖保留 UNRESOLVED，结果最多 PARTIAL；
缺失公共修法交既有 Quick 重新分配 owner，不让局部 worker 越权补写公共文件。

新批使用[直接发布协议](direct-repair-protocol.md)的 claim/extend-reads/submit/publish/fail，
不同 ownership 文件最多六个修复并行。同文件公共/局部任务依赖有序，避免重复写入。
旧 dispatcher 保持自己的并发与复核协议。公共批初始登记公共引用文件；新增依赖先 extend-reads。
入口批读取公共文件且只写自己的局部文件，因此公共批完成后可并行。
Quick 的 `review_focus.shared_patch_artifacts` 同时提供公共与局部补丁证据；逐入口审查覆盖不减少。

## 公共目标与只读入口核对

新 input 的 `execution_policy=TARGET_SHARED_V1` 提供 `planning_hints.repeated_sites`：
按路径和去空白的 anchor 列出重复目标及原 target_index。它只是结构提示，不证明同因；
真实规划上下文仍读取源码并填写公共 proof。unshared 必须解释公共子集为何不能归并，
不能仅以入口动作或完整工单不同作结。对 repeated_sites 中本 candidate 的每个重复 target，
unshared 需填写 `target_assessments:[{target_index,reason,evidence:[{path,line,excerpt}]}]`；
发布器校验索引覆盖和当前源码证据，不以结构相同自动判定等价。
不得按应用名、已知文件名或历史 verdict 归并。

确认组超过普通每批入口上限时，新计划自动生成公共前置批和入口批，防止公共文件
随着逐入口回执被多次持有写锁。小组也可显式指定
`execution_strategy=COMMON_THEN_ENTRY_CHECKS`。无 execution_policy 的冻结 input 保留旧分区。

只剩公共 targets 的入口移入 `execution_scope=ENTRY_CHECK_ONLY` 批：ownership 为空，
完整原义务、公共 target 证明和前置回执仍在。它只输出逐入口 `NO_CHANGE/FAILED`，
不能继承公共批的通过结论。普通每批入口上限和字节边界不变。
含局部 targets 的入口继续修局部文件；同文件局部修改仍遵守单 writer。

只读批在公共批终态后领取当前快照。先核对 SHA 有效的公共回执和当前实现，再独立
检查本入口 binding、identity、variant、consumer、observable 及九角色；共用事实可引用，
结论不可复制。实际编辑会被 ownership 检查拒绝。提交与发布间读取集有变化时拒绝发布，
refresh 后只重新核对变化影响和入口结论；失败前置不能被声明为 CLOSED。
公共前置回执不计入入口结果，入口仍 exactly-once。
