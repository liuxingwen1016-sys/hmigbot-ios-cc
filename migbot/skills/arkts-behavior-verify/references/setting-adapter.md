<!-- when: planning or executing a setting review/repair batch -->
<!-- topics: candidate coverage, native setting contracts, affinity, consumer closure -->

# 设置 adapter：保留行为约束，优化证据读取

[设置领域说明](../engines/setting/ENTRY.md)定义审查范围；按当前阶段读取下表协议。

| 当前阶段 | 必须读取的协议 |
|---|---|
| 初始化/结果 | [快速流程](../engines/setting/references/fast-workflow-protocol.md)、[结果](../engines/setting/references/fast-result-contract.md) |
| Baseline | [紧凑审查](../engines/setting/references/compact-review-protocol.md) |
| 已启用的 Repair 轮次 | [修复](../engines/setting/references/fast-repair-protocol.md)、[统一直接发布](direct-repair-protocol.md) |
| Quick | [快速审查](../engines/setting/references/quick-review-protocol.md) |

Baseline、Repair 自查与 Quick 均执行[效果反馈与副作用](effect-feedback-safety.md)：consumer 到达平台 setter 后，继续追踪通知是否回写源头，核对重复通知与共享调用方，并保留原生逐 key 证据。

## 统一并发覆盖

先按[全局并发口径](unified-dispatch.md#concurrency-contract)确定本轮额度，再读取原生协议。计划分组宽度与实际执行额度分别按下表处理：

| 阶段 | 统一新运行使用的调度 |
|---|---|
| Baseline / Quick Review | `setting_review_plan.py` 默认 `max_parallel=6`，分包和计划额度均由 wrapper 设置；与点击共用统一队列，不另开原生四槽队列。 |
| Round 1 / Round 2 Repair | 原生 planner 保留每 wave 最多四批的合法格式；统一 dispatcher 展开所有 waves，按同文件 writer 锁和真实业务前置派发，执行器使用统一额度，默认可运行六批。 |

不要向原生 `fast_repair_plan.py plan` 传 `--max-parallel 6`，该参数仍只接受 `1..4`。六槽额度传给统一 init、设置 Review wrapper 和统一初始化的修复执行器；不修改原生 plan 的宽度、不等待整个 wave 完成。每批 settings/paths、foundation 分组和逐 key 审查规则保持原样。恢复时遵循运行记录中冻结的协议。

Detector 保持完整 `report.settings`，满足 `settings_discovered = settings_selected = settings_parsed` 且 `performance.completion_status=COMPLETED`。Baseline 只把其中 `findings` 非空的项交给 Review；无 finding 的 `CLOSED_STATIC/NOT_APPLICABLE/DEFERRED` 项均不入选。plan 和 findings 的 `review_coverage` 保留入选与排除 key，排除不等于 NO_DEFECT；完成标记仅针对入选候选。设置 publisher、seal、key 顺序和候选 exactly-once 由原生脚本校验。

`setting_review_plan.py` 按候选装包并共享证据读取。所有入选候选都需要真实审查，Detector finding 不直接授权修复；默认每包 8 个 setting，Quick 默认 6 个。读取公共方法一次后，逐 key 核对全部 Android 活动 consumer、对应 ArkTS consumer、生效时机、持久化与临时覆盖优先级、默认/fallback、enum/list 值、逻辑设置组以及平台/observable 末端。索引缺少方法意味着继续源码搜索，不能推出没有 consumer。

工单的 Android inventory 与 ArkTS mapping 保持 exactly-once；不得只保留一个 service 调用。两套同名实现用当前 active implementation map 定位，不能对未被应用引用的 shadow target 下补丁。

原生 `FIX_REQUIRED/NO_DEFECT/UNCERTAIN/UNREVIEWED` 不改变。Quick 的 `CLOSED_LIKELY` 仍要求全部 consumer、terminal chain、precedence、setting group 和 active target 满足且无 reachable blocker；其它状态继续原生定向 Round 2，包括 `REVIEW_FAILED` 的 Baseline targets 回退。导航拓扑机械拒绝，已有 route/dialog 激活保持允许。

设置本身不增加 scope guard、九角色 schema 或目标真机 PASS 门。共用媒体服务时阅读相关交互工单只为保护参数、状态与已有补丁，不把 interaction 成功推导成 setting 成功。设置结果始终 `correctness_verified=false`、`correctness_claim=NONE`；统一安装证据不改变这一点。

共享预检由统一主流程在 IO 执行并引用到 SO，不是全程只读：按[预检协议](../engines/interaction/references/preflight-protocol.md)，仅对项目已声明且已锁定的缺失依赖做一次有界恢复。设置 lane 不重复安装或另跑预检；恢复后仍不可构建时保留降级原因，继续可行的源码工作。dispatcher 使用安全就绪队列，每批 setting 数量和 ownership 路径上限不扩大；并发执行数按上节使用统一额度。

新修复由统一层显式传 `--publication-policy direct` 到 `scripts/setting_repair_pipeline.py`：字节副本、交稿冻结、候选哈希和确定性事务发布在原生 per-key publisher 外实现。不预留 reviewer、不派逐批复核。逐 key consumer、precedence、terminal effect、默认值和活动目标仍由 Repair 自查；启用第二轮时再由唯一一次独立 Quick 审查；结果不转换为 interaction 九角色 schema。

没有完整的 read dependency contract 时，按全部 authored files 保守记录依赖变化。`<batch>.safety.json` 保存 `dependency_changes/affected_keys`，标 `semantic_review=NOT_PERFORMED`；不是发布前语义通过。Quick planner 显式传 `--publication-policy direct`，将 sidecar 和原生回执按 SHA 绑定到每个相关 packet，Quick 读取后在当前整轮源码上逐 key 核对；Baseline 全部候选和 Quick 全部 FIX_REQUIRED 各自 exactly-once。不能照抄点击引擎 窄依赖来省略设置检查。

默认同文件从 claim 到终态单 writer；仅 setting 通道内已通过[方法体范围检查](function-scoped-repair.md)的独立方法体可组成最多两批的并发窗口。interaction 同文件和跨通道同文件仍串行，正式发布仍逐批进行；后批读最新可信字节，不同文件修复可使用可用槽位。读写依赖按[补位协议](repair-overlap.md)判断，不能仅凭不同方法名认定独立。按 logical setting group/foundation 分组；可复用共同源码及已证明的共同修复，但每个 key 独立出结果，不按共享路径继承修复成功。

每个已启用修复轮次按[补位协议](repair-overlap.md)允许已确认独立的设置批提前领取，自动绑定最新源码；其正式发布等待点击收口。未提前初始化时才执行显式 manifest rebase。worker 以返回副本里的最新消费者/命令实现为准，沿原工单自查全部 consumer 与末端效果，保护已有点击修复；不能因共同链路被点击批修改就跳过设置、继承 APPLIED，或盲目按旧 anchor 重写共享方法。锚点不再对应时按原生失败/Quick 回退边界报告，不扩大 ownership。

派发和交稿采用统一直接发布协议：新状态 `direct_dispatch_version=2` 有未绑定 claim 时先 attach/release；每个新批使用[CC 独立上下文映射](unified-dispatch.md#claude-code-host-mapping)；draft 只写分配的树外 `draft_path`，refresh 后用新路径。CLI 默认返回逐 key 摘要与原生回执/SHA，`--verbose` 保留完整输出。设置使用自身的消费者核验与状态准入规则。

新版分包、公共 Quick 分析、草稿预校验和提前审查见[性能协议](behavior-performance.md)，覆盖各阶段入选设置及其消费者。
