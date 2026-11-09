<!-- when: executing a new unified direct repair round in either lane -->
<!-- topics: repair-only slots, frozen proposals, single writer, deterministic publication, Quick evidence -->

# 修复直接发布

新运行冻结 `publication_policy=direct`、`direct_dispatch_version=2`。每个已启用 Repair 轮次都执行此协议；默认仅 Round 1，full-repair 另含 Round 2；关联续跑仅执行 Round 2。设置与点击分别保留原生工单、准入和结果 schema。缺版本的既有 direct 状态保留原领取/交稿约束；仅支持当前直接发布运行目录。

## 调度与交接

每轮收口前及恢复遗漏工单时使用[工单对账](unified-dispatch.md#repair-work-order-reconciliation)。它只补回有冻结依据且尚未执行的原队列记录，并复用现有 claim；已有提案/回执继续发布或封存。终态缺口不触发新 Repair 或 Review，缺语义依据时只报告。

`max_agents` 默认 6、可配置 `1..6`，是两类各阶段共用的子 Agent 执行上限，不是每类各六个。按[全局并发口径](unified-dispatch.md#concurrency-contract)核对宿主容量，不把配置值当作实际可用额度。Repair 不预留 reviewer，设置与点击在各自修复期间都能使用全部可用槽位。每批按[CC 调度映射](unified-dispatch.md#Codex-host-mapping)创建独立上下文，新 ID 本身不证明上下文独立。worker 不委派；同批模型恢复沿原身份。私有副本未发布批最多 `2 * max_agents`。

默认同文件从 claim、RUNNING、QUEUED 到终态只允许一个 writer；设置同文件已有方法体满足[有限并发契约](function-scoped-repair.md)时允许双批窗口。不同文件可并行；单纯读写交集不封锁全部工作。真实 `requires_success_batch_ids` 必须成功；普通路径顺序不意味着前批失败就跳过后批。设置保留原 logical setting group/foundation 与逐 key 结果，不能用点击的九角色/shared-component schema 替换。点击共享根因使用当前 organization 的源码路径候选、真实裁决与显式 target_mapping；不同 callable/anchor 不阻止证明同源，但共享文件不自动证明同根因。

新运行冻结 `repair_overlap_version=1`；每个已启用轮次按[补位协议](repair-overlap.md)让无跨域读写冲突的设置批提前修复并 submit。设置正式发布仍等点击全部收口；未提前启动时按 [manifest handoff](unified-dispatch.md) rebase 后领取。运行仅使用当前目录内冻结的状态。所有注册先冻结本轮 fresh manifest。后一个 lane 从前一个 lane 已接受字节起步；修改共享方法前读取其现有参数、状态、消费者和后置条件，保护先前补丁，不凭旧工单覆盖新实现。发布成功不是语义等价证明。

以下均为 `python <skill-dir>/scripts/unified_dispatch.py` 的子命令；每批操作传 `--state U/dispatch.json --batch-id <外层ID> --claim-token <外层TOKEN>`。

1. 先读取平台完成事件/实际 Agent 状态。对真实停写并有 draft 的批执行 `submit --draft D --agent-stopped`，冻结 worker 字节和 draft SHA。只登记 RUNNING 不证明 Agent 还活着；已完成的批不得继续空等。
2. 主会话逐个处理 `publication_queue`：`publish --agent-stopped`。设置返回 `WAITING_FOR_INTERACTION_PUBLICATION` 时保留队列、跳过它，继续处理点击完成事件和补派；不循环阻塞等待该设置发布。新点击 claim 返回整批推导的 `required_scope_target`，默认省略 `--scope-target`；显式范围只会扩大，混合播放/下载为 all，普通点击为 null。设置不接受媒体 scope。只消费冻结 draft，不传新 draft/merge-review，不创建 reviewer。成功后校验原生回执并封存外层 claim；不隐式补位。
3. 处理完当前完成事件与待发布队列，再 `progress`，按 `claim_slots` 逐个 `claim-ready --limit 1`、启动独立 Agent、立即 `attach --agent-id A`。两层 dispatcher 遇到未 attach 的 claim 都停止继续领取，先派发或释放。attach 后继续领取至实际可用槽位填满或无就绪批，不等待本批完成；每次派发后检查完成事件。`--limit 1` 是单次领取数，不是同时执行数。
4. 未成功 attach 不开始源码工作；真正未启动的 clean claim 才可 `release --reason ...`。核实宿主是否把已完成 Agent 计入名额，并按宿主机制释放；不创建额外 reviewer，也不复用不同批上下文。

worker 唯一可写源码根是 claim 返回的 `native_claim.worker_root`；启动先核对 cwd 和绝对路径，Android/SDK/project_root/base/candidate 只读。新两类 claim 都返回已分配的 `native_claim.draft_path`，派发消息带上该绝对路径，worker 只在该路径交稿。父目录已建立，不能把 draft/log 放 worker/base 树内，即使其 spec 子目录也不允许。完整遵循对应 lane 原生 Repair 义务并运行 `check`。

`progress --agent-status <平台快照.json>` 接受含 `agents` 数组的观测快照，返回交稿/检查/派发提示；它不证明停写、不自动释放槽位。新发布默认返回逐项状态、改动文件、完整回执路径/SHA和依赖变化计数，完整义务证据保存在回执中。排障用子命令前的全局 `--verbose`，例如 `unified_dispatch.py --verbose progress --state ...`；原生发布 CLI 也支持 `--verbose`。

## 修复自查

设置 worker 编辑前先运行交接中的逐 key intent 检查，整批 ownership 不能代替该 key 的 edit_paths；优先复用 packet 中源码未变化的审查锚点。worker 在编辑前后按[效果反馈与副作用](effect-feedback-safety.md)核对新增/改动的回调和共享 writer，把收敛条件及重复事件推演写入原生逐项证据。默认单轮不能把这项义务推迟到未启用的 Quick；存在已知不安全回路的补丁先在私有副本内修正，再交稿。

## 发布不是语义审查

发布器机械执行冻结字节/草稿、ownership、来源 SHA、CAS、三方合并、原生结果/平台/scope 规则和事务校验。安全 sidecar 标 `DETERMINISTIC_PUBLICATION`、`semantic_review=NOT_PERFORMED`，不制造独立复核通过或 `ALREADY_EQUIVALENT`。

不同文件补丁可能改变本批读取的依赖。点击记录依赖变化与 affected entries；设置无完备 read contract，按全部 authored files 保守记录 `dependency_changes/affected_keys`。这些都是 Quick 输入，不是发布前 AI 审查，也不允许缩减 Quick 覆盖。已认证的方法体并发另在发布前检查所读方法与结构是否变化；变化则拒绝直接发布，按有限并发协议交原 worker 处理。

full-repair 或关联续跑在联合 Round 1 收口后，于整轮稳定源码上执行唯一一次 Quick。设置用 `setting_review_plan.py quick plan --publication-policy direct` 将安全 sidecar 和原生回执 SHA 绑定到 packet；逐 key 读取相关 sidecar 并审查全部消费者/优先级/末端效果。点击原生 Quick 消费直接发布证据并维持领域义务。两类都 exactly-once 覆盖 Baseline 全部 FIX_REQUIRED。Round 2 结束只保留静态未验证结果，不追加语义 Review。默认模式不创建 Quick 计划，Round 1 依赖变化只作审计证据。

## 正式项目源码保护范围

设置与点击的正式项目 inventory / CAS 排除项目根目录的 `.migbot/**`，包括指标、水位、配置及 `bin` 工具文件；这些内容不复制到新 worker 的源码副本。应用源码、资源、工程配置、依赖锁文件和其他原有保护范围保持不变；应用子目录内同名 `.migbot` 不在此例外中。此排除不授权 worker 修改正式项目的工具文件。

该例外仅用于正式项目快照。base / worker / candidate 私有树仍使用全量 inventory，worker 新增 `.migbot` 文件也必须通过原有 ownership 检查；计划、草稿、发布回执及事务绑定的独立 SHA 校验不变。指标更新不需要发布回执，真正的源码变更仍须经过受控发布器。

旧 run 的 `accepted_inventory` 若已包含根目录 `.migbot`，更新脚本不会自动改写历史快照或接纳当前工作区；调度明确报告 `legacy source inventory includes project .migbot; explicit recovery required`。先保留现场并按受控恢复方案处理旧运行，不手工过滤历史回执或重算整仓哈希来绕过保护。

## 有界失败与恢复

- worker/draft 需改：先确认原 worker 已停止，`refresh --agent-stopped`，最多两次；保留旧副本、旧稿、计数和原修复身份。将返回的新 worker_root/draft_path 交给原 Agent 续跑。排队批恢复前须有空执行槽。改完重新 submit，不编辑已冻结 draft 后直接 publish。
- 发布参数错误：先纠正参数重试，不消耗源码 refresh。新点击范围先归一化为实际检查域；写入事务开始前允许纠正，COMMITTING/终态必须保持相同实际域。缺版本旧状态继续绑定原始 scope 参数。代码保护拒绝时先读具体 violation/report，区分真实越界、源码破坏和检查器误报，不为迎合误报改变业务逻辑。
- 模型 429/服务中断：外层 `recover --agent-id <原ID> --backoff-seconds ...` 记录预算后沿原身份恢复，最多三次/累计 180 秒；不是事务恢复，不换模型或新 Agent 绕过。
- 本批无法安全完成：`complete --failure-reason <真实原因> --agent-stopped`，原生安全失败回执收口，再显式 claim-ready。可安全隔离的本地失败不停止其它批；真实成功依赖继续受阻。
- COMMITTING 中断：`recover-publication --agent-stopped`，只依据可信 before/after journal 恢复；第三态外部编辑保留并报 blocker。回到 QUEUED 后重新 publish，不派 reviewer。原生已终态时重试 publish/complete 只验现有回执，不重复写源码；检查域按上一条保持绑定。
- worker 误写正式项目：先停责任 Agent、保存差分/哈希。manifest 只有哈希不是字节备份；无可靠归因/可信恢复字节时停相关写入并报告，不能整仓 reset 或用旧快照覆盖。已有事务仅精确恢复可归属文件。

脚本锁 busy 保留同 batch/token 重试；不消耗业务轮次。所有安全判断都不把安装成功、测试脚本通过或 Detector 转绿提升为应用正确性证明。
