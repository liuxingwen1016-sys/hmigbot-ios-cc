---
name: arkts-behavior-verify
description: 联合审查并有界修复 Android→HarmonyOS/ArkTS 的设置与点击效果断链。用于要求同时检查持久化设置是否真正生效、点击命令是否到达业务结果的迁移工程；默认完成 Baseline Review 与一轮修复，支持首轮结束后继续 Quick Review 与 Round 2，也支持初始化时选择 full-repair。不要用于纯视觉对齐、导航拓扑重设计、通用迁移或仅解释代码。
metadata:
  type: codebase
  domain: migration
  tags:
    - setting
    - interaction
    - behavior-alignment
    - bounded-repair
---

# arkts-behavior-verify — 行为验证

审查设置与点击的完整效果链，一次初始化、联合阶段屏障、默认一轮修复、一次集中交付。用户在首轮结束后说“继续第二轮 / quick review 和修复”时，按[第二轮续跑](references/round2-continuation.md)调用 `continue-round2 --from-out <原U>`，直接衔接唯一一次 Quick Review 与 Round 2。用户一开始明确要求完整两轮时才使用 `init --full-repair`。集中交付只有一个阶段，但构建不是只能执行一次命令：首次构建失败后最多执行两次有界编译纠偏与复建，安装仍最多一次。各启用阶段点击优先；Repair 中确认无关的设置批可提前补位，设置正式发布等待点击收口，消费者使用最新已接受业务链路。设置与点击共用调度额度，分别记录工单和证据。

## 核心边界

- 设置 Baseline 仅审查 **Detector `findings` 非空的 setting**；入选 setting 逐项 exactly-once。Detector 仍全量发现，未入选项记录为未审查，不赋予 NO_DEFECT。保留 consumer inventory、逐 consumer mapping、终端效果链、持久化/临时覆盖优先级、生效时机、默认值及 enum/list 全分支。
- 点击 Baseline 固定采用核心规则候选策略（core）；没有候选模式开关。全量 Detector 保留全部发现，未选入口只记录覆盖与排除原因，不宣称已审查。明确用户目标通过领域或精确 contract 参数限定，不把“未接入命令”误当无目标。
- 审查与修复按[效果反馈与副作用](references/effect-feedback-safety.md)核对通知回写、重复副作用及共享调用方；涉及后台任务或多展示面宿主时，核对提交后终态刷新及相关展示面的挂载。这属于每批按需自查，默认单轮也执行。
- 只有真实双端源码审查确认的缺陷才能修复。共享源码、SDK 定位或补丁证据可复用，逐设置/入口结论不能互相继承。
- `APPLIED`、Detector 转绿及安装成功都不证明行为正确。设置始终未验证；播放/下载的授权真机结果仅对实际验收范围有效，不能提升为全应用通过。
- 主会话直接调度，新 batch 按[CC 调度映射](references/unified-dispatch.md#claude-code-host-mapping)创建独立上下文；worker 不再委派。两类 Baseline、已启用的 Quick 和 Repair 均使用统一 `max_agents`，默认全局共用 6 个子 Agent 槽位，不是每类各 6 个。实际额度取配置与宿主可用于本轮子 Agent 的容量之较小值，见[并发口径](references/unified-dispatch.md#concurrency-contract)。不同 batch 不复用同一 Agent，Quick Agent 独立于 Repair；新修复不创建逐批 reviewer。
- 保留用户未提交修改、正在执行的计划和已部署 Skill。仅在新输出目录开启实验，不热替换其它会话正在读取的文件。

## 输入、路径与协议优先级

输入 `android_root`、`arkts_root`、`out`、`max_agents`。默认输出 `<arkts_root>/spec/verify/behavior-effect/<run-id>`；新运行使用空目录。Android oracle 只读。初始化不传控制参数时冻结 `repair_mode=single-round`，阶段仅为 `baseline-review → round-1`，Round 1 收口后直接进入集中构建/安装；仅在用户明确要求时传 `--full-repair`，冻结完整四阶段。模式一经初始化不可热切换。已封存单轮追加第二轮使用 `continue-round2` 创建关联续跑，冻结 `repair_mode=round-2-continuation`，仅调度 `quick-review → round-2`；历史 Baseline/Round 1 按 SHA 继承。已有续跑或 full-repair 运行则恢复其当前阶段；只有明确要求“从头重新跑”才重新 init。

`S=<skill-dir>/engines/setting`，`I=<skill-dir>/engines/interaction`；`U=<out>`，`SO=<out>/setting`，`IO=<out>/interaction`。引擎文档的 `<skill-dir>/<out>` 分别映射到对应 `S/SO` 或 `I/IO`。运行脚本使用独立进程，不能把两套同名模块同时加到 `sys.path`。

先读 [统一流程](references/unified-workflow.md) 和 [调度与恢复](references/unified-dispatch.md)。对应阶段再读 [设置契约](references/setting-adapter.md) 或 [点击契约](references/interaction-adapter.md) 链接的领域协议。

统一协议覆盖调度、隔离执行、输出路径、共享构建和资源上限。领域审查与修复的 schema、状态准入和保护不变。新运行只使用直接发布，冻结编排身份。先读[修复直接发布](references/direct-repair-protocol.md)。设置通过隔离 adapter 保留原生结果语义；点击使用内置直接发布器。初始化、阶段顺序与并发额度以本入口为准。

## 联合阶段

以下步骤用于新运行。收到首轮结束后的续跑请求时，按第二轮续跑协议进入步骤 4–7，步骤 1–3 的历史不重新执行。

1. **初始化及共享预检**：用 `scripts/unified_pipeline.py init` 首先建立保守结果，冻结 roots/cap，再初始化两套结果。用当前 interaction 的 resolver 和 `build_preparation.py` 完成预检：自动提取现有构建参数，缺失的已声明且已锁定依赖最多恢复一次，默认超时 60 秒；详见[预检协议](engines/interaction/references/preflight-protocol.md)。源码/输出/初始保护失败才阻止源码工作；恢复后仍缺 SDK、依赖或签名仅降级构建。保护快照须在编辑前完成；不改变依赖声明/锁定版本、用户环境、签名、bundle 或 Android。
2. **联合 Baseline**：用 `unified_pipeline.py detect --phase baseline` 各跑一次全量 Detector。先点击 `compact_interaction_review.py plan`，再设置 `setting_review_plan.py baseline` 的候选 affinity packet（仅 `findings` 非空）。注册两类计划，统一 claim-ready，真实 Agent 审查、原生发布及 merge。点击优先派发，只读审查保留并发补位；点击质量闸、scope/SDK/根因准入不变。随本次审查记录[完整修复读集](references/repair-overlap.md)，未知依赖不声明完整。
3. **Round 1**：点击仅取质量合格 `FIX_REQUIRED` 并先做当前 organization，设置只取自己的 `FIX_REQUIRED`。重复点击断点按原生 organization 或热点 writer 规划，不叠加两者；登记所有批并按[修复补位](references/repair-overlap.md)绑定完整读集；空闲槽提前启动与全部剩余点击批无冲突的设置修复。未提前启动时，点击收口后 rebase 设置 manifest；已启动时适配器仅接纳有回执的点击发布。不同文件并行；设置同文件的独立方法体按[有限并发](references/function-scoped-repair.md)组成双批窗口，其余同文件仍单 writer。交稿冻结后主会话确定性串行发布。设置读取最新消费者实现并保护已有点击补丁，不以点击修复成功代替逐设置裁决。
4. **一次 Quick（完整模式或第二轮续跑）**：Round 1 尾部的空闲槽可按[性能与提前审查](references/behavior-performance.md)准备稳定入口，包含设置入口；仍受全局名额、修复优先和双域剩余 writer 约束。两类 Round 1 和提前 reviewer 都终止后，联合运行唯一一次 `detect --phase post-round1`。点击 Quick 优先，设置 Quick 随后按空闲槽补位；两类均覆盖各自 Baseline 全部 `FIX_REQUIRED`，不按 Detector 是否仍报错或文件是否变化过滤。使用整轮稳定源码、新索引及发布依赖变化证据；真实 Quick Agent 独立于 Repair，并更新下一轮修复读集及源码哈希。仅用于下一轮，不声明正确。
5. **Round 2（完整模式或第二轮续跑）**：点击只接受 `ROUND2_REQUIRED`，`UNCERTAIN/REVIEW_FAILED` deferred；设置准入规则：非 `CLOSED_LIKELY` 项（含原生失败回退）经导航与 ownership 校验后进入。同样支持独立设置批提前补位，依赖来自本轮 Quick 和新 targets；发布仍点击收口后再设置，不互换准入规则。执行完不追加 Detector、AI Review、第三轮或应用测试。默认模式从 Round 1 直接进入集中交付。
6. **集中交付**：共享冻结命令构建 signed HAP；首次失败后必须按[统一流程的构建纠偏契约](references/unified-workflow.md#6-一次集中构建阶段一次安装)分类编译错误，最多执行两次限于 ownership 的纠偏与复建，总构建 attempt 上限为 3。这里的“一次”只表示一个集中交付阶段，绝不表示只能运行一次构建命令。仍有可纠偏的 ownership 内错误时，不得以单次失败证据封存；只有纠偏预算耗尽、无 ownership 内错误，或逐文件记录结构化安全豁免后才可停止。由主会话最多安装一次。设备被其它实验使用时不抢占、不停止它，记录安装/验收待办。用户明确授权的点击目标验收使用当前运行时契约；设置不新增运行时验收阶段。
7. **封存**：任何正常或异常终点用 `unified_pipeline.py finalize`、`validate`，保留分 adapter 结果、SHA、未审项、静态残留与运行时缺口。结果不完整时如实保留，不用 0 批次或安装成功掩盖缺失。随后用 `scripts/run_summary.py --out <U>` 一次提取[最终汇总](references/behavior-performance.md#最终汇总)，如实区分批次跨度、近似运行时长与宿主任务总耗时。

## 性能与失败

临时辅助脚本使用系统临时目录，不放入运行证据、应用源码或 worker 树。封存前遵循[目录检查与纠正](references/unified-workflow.md#7-所有终点保守导出)：误放文件先核实再移出，重试同一未封存 run 的导出，不重跑 Review/Repair，不修改已封存结果。

新点击计划按[风险承接与关键文件协议](engines/interaction/references/scope-ownership-protocol.md)给已有 scope 风险指定本次 Review 内的裁决责任，并在工单冻结前校验已确认必改文件。按[局部恢复](engines/interaction/references/planning-recovery-protocol.md)处理已确认归属缺口及少量有调用方、源码绑定的未决证据；最终计划逐风险核对承接，不以入口已入批替代。未承接风险保留在结果与汇总中；不新增完整 Review 阶段或修复轮次。

新运行同时冻结 `scope_followthrough_version=1`：风险排除依据覆盖接通后的预期链，全局排除不能只引用局部点击；未确认的平台语义列出实际查询与缺失事实。Repair 新确认的静态问题以 `static_handoffs` 保留具体 owner 与证据，不扩大写权限或自动续跑。旧冻结运行不追补新字段。

Baseline 与已启用的 Quick 均按共享依赖和成本分包，公共源码/SDK 证据按阶段 SHA 绑定；分包只减少重复读取，不减少各阶段已入选审查项。先派满实际可用槽位，再等待任意完成并补位。直接转交 claim 的 `worker_context`，用[草稿生成与验稿工具](references/behavior-performance.md#任务交接与草稿生成)生成固定字段和精确引用；模型只补充真实判断。运行额度遵循[设置并发覆盖](references/setting-adapter.md)，不改每批项数或 ownership 上限。

新 Repair 两类均使用隔离副本，未发布副本上限 `2 * max_agents`。先处理完成事件和发布，再按 `claim_slots` 逐个领取、启动、attach；attach 后继续领取至可用槽位填满或无就绪批，不等本批完成。有未绑定 claim 时先派发或释放，不再空占下一批。worker 写返回的树外 `draft_path`，refresh 后使用新路径。发布自动覆盖点击工单所需检查域，默认返回摘要与完整回执路径/SHA。队列释放执行名额但保留 writer 锁或已认证双批窗口；可发布队列达到两批时先发布再补位。方法体并发若依赖变化，发布前交回原 worker 定向处理；依赖变化在 full-repair 模式作为 Quick 输入，默认模式只保留为审计证据，均不产生语义通过。

429/capacity 在原 batch、原 Agent 续跑；格式纠正也保留上下文。业务内容重审至多一次，模型恢复至多三次且累计退避不超过 180 秒，各自持久化计数。等待超时不释放正在运行的 claim；不能用新 Agent 绕限流。耗尽后只封存真实缺口，继续不受影响的批。

耗时来自实际完成批次与工具日志；单元测试仅验证 Skill 脚本，不是应用修复成功或墙钟提速证明。开发本 Skill 时可以运行自测；运行迁移实验不自行添加应用测试轮次。

开发与发布使用 `scripts/package_skill.py` 记录文件哈希，校验包内引用与清单。默认 `package` 只导出运行文件，排除开发测试和夹具；仅开发归档使用 `--include-tests`。
