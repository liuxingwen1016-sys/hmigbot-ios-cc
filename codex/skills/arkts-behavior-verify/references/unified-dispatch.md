<!-- when: registering, dispatching, recovering or publishing any unified batch -->
<!-- topics: global cap, native publication, stage handoff, model recovery -->

# Unified dispatcher

`scripts/unified_dispatch.py` coordinates the vendored setting and interaction
engines without importing either engine into the coordinator process. Native
plans, packets, receipts and seals remain authoritative and are validated again
at publication time.

New states freeze `orchestration_version=2`, `lane_order=[interaction,setting]`,
`publication_policy=direct`, `direct_dispatch_version=2` and use [direct publication](direct-repair-protocol.md)
for **both** repair lanes. No per-batch reviewer is allocated. Start a fresh
output directory; old skill running states are not a supported entrypoint.
The order is bound into run config, dispatcher, registrations and batches.

## Codex host mapping

脚本与冻结证据沿用 `new_agent_options={"fork_turns":"none"}`，表示本批需要独立上下文；它不是 CC 工具参数，也没有改名为 `worker_options`。在 Codex 中使用当前宿主实际提供的 Agent/Task 接口，新 batch 新建子任务，仅带本批任务包及必要协议，不 resume 其它批次或拷贝主会话历史。不要向接口传入未支持的 `fork_turns` 或 `context_inheritance`。

同批恢复使用宿主支持的恢复接口及原 Agent ID，保留现有次数与退避预算；只有接口明确表明原身份丢失/不可恢复时，按既有替代流程处理。宿主不支持必要能力时如实报告限制，不通过修改调度 JSON 或批次身份绕过。

## Concurrency contract

统一调度锁沿用原锁文件和一字节互斥协议；竞争时非阻塞轮询，最多等 10 秒。仍未获得锁时，统一 CLI 返回退出码 `75` 和 JSON `status=BUSY, reason_code=LOCK_BUSY, retryable=true`（stderr），不会进入受锁保护的状态修改。主会话先处理已完成事件，稍后用同一参数重试本条命令；连续 BUSY 时检查持锁进程并报告等待，不紧密轮询、不释放其他 worker 的 claim、不删锁、不消耗业务修复轮次。普通 I/O 或契约错误仍按 ERROR 处理，不能据此盲目重试。

For new unified runs, `max_agents` defaults to **6 child Agent execution slots
shared globally**. Both setting and interaction Baseline/Quick reviews and both
Repair rounds can use all six slots when enough eligible batches and host
capacity exist. It is neither six per lane nor a requirement to run six workers
when fewer batches are ready. Review prioritizes interaction and fills spare
slots with settings. Repair may execute and submit setting batches early when
the frozen overlap protocol proves independence; official setting publication
waits for interaction to finish. Without early setting initialization, rebase its
manifest at that handoff before starting it. All direct Repair slots are repair
workers, with no reviewer reserve.

Use `effective_cap = min(max_agents, host_child_capacity)`. Derive
`host_child_capacity` from the host's counting rules: subtract the coordinator
and other occupied slots only when the host reports a total including them.
Do not subtract the coordinator again from a reported child-only capacity.
Include this run's existing workers when enforcing the cap; a frozen dispatcher
limit is not proof that the host has that many available slots. Lower the init
parameter when needed, and do not rewrite an existing run's frozen cap.

The setting engine's four-wide native plans are preserved input formats, not
the unified execution limit; follow the [setting override](setting-adapter.md).
This entry accepts only new direct-publication runs; do not import legacy states.


## Workflow

`unified_pipeline.py init` already creates `U/dispatch.json`; do not initialize it
again. All commands below are subcommands of `python <skill-dir>/scripts/unified_dispatch.py`.
The default frozen stages are `baseline-review`, `round-1`. Runs initialized
with `unified_pipeline.py init --full-repair` additionally freeze
`quick-review`, `round-2`, in that order.
Register both lanes before sealing each stage. A genuinely empty native plan is
still registered; `--allow-empty` is not a substitute for missing review work.

```text
register --state U/dispatch.json --stage <stage> --lane <setting|interaction> --plan PLAN --artifacts-dir DIR [options]
seal-stage --state U/dispatch.json --stage <stage>
claim-ready --state U/dispatch.json
attach --state U/dispatch.json --batch-id ID --claim-token TOKEN --agent-id AGENT
complete --state U/dispatch.json --batch-id ID --claim-token TOKEN \
  --agent-stopped [--draft DRAFT] [--scope-target playback|download|all --scope-guard GUARD]
```

Use `SO/baseline/fragments` and `IO/baseline/fragments` for Baseline artifacts;
use `SO/quick-review/fragments` and `IO/quick-review/fragments` for Quick.
Repair artifacts are `SO/round-N/results` and `IO/round-N/results`.
New setting and interaction repair registrations both need
`--source-manifest <this-round-source-manifest.json>`
and their own `--native-state <lane-out>/round-N/isolated-dispatch.json`; `--results-dir` defaults
to artifacts-dir. Snapshot once before each repair round (after the previous
round has closed); retain that evidence, then rebase the second lane registration
at the repair handoff as below (setting in new runs, interaction in old runs).

`claim-ready` and `complete` return `claimed_batches`: spawn exactly one fresh
context per returned claim using the [Codex host mapping](#Codex-host-mapping)
and immediately attach its actual Agent ID. Do not
spawn a worker for a batch absent from these claims, or put multiple batches into
one Agent. New direct Repair claims carry only `role=repair`; `role=review` is legacy only.
The configured cap applies across both lanes, roles and all stages, not per lane.
For Review, dispatch every returned claim before waiting for any completion;
when one finishes, process its handoff/publication before dispatching replacements. The native
interaction repair claim contains its private worker_root and native token;
only that private root is writable by its repair worker.
Read-only Baseline/Quick prioritize interaction packets, then fill available
slots with setting packets; they do not add a cross-lane completion barrier.
Both repair rounds refill independent setting proposals under the [overlap contract](repair-overlap.md);
only official setting publication waits for interaction to finish.

Worker task inputs include the lane/stage, native and unified batch IDs, native
plan/packet, exact roots, ownership, artifact directory, and current protocol
paths. Workers read their required protocol and actual source, produce native
drafts, and do not delegate. The main session owns claim transitions and release
of runtime Agent slots. Confirm the worker really finished before asserting
`--agent-stopped`; close a completed Agent if the host counts it toward its live
Agent limit before spawning the next fresh batch.

For Baseline/Quick, `complete` accepts a `RUNNING` claim with an attached agent and requires
`--agent-stopped`. It invokes the native publisher/isolated dispatcher before
sealing the outer claim. Interaction repair scope options are forwarded
unchanged to native isolated completion. A failed worker can call `recover`
with `--backoff-seconds 0..60`; each batch has at most three recoveries and 180
seconds cumulative requested backoff. `reopen` is the bounded interaction
business retry and does not reset model-recovery counters.

For Review, validate/publish with the lane's native commands (setting uses the
wrapper) and then call outer `complete` without `--draft` to verify the resulting
fragment/seal. Alternatively, outer `complete --draft` invokes the native
publisher. Legacy setting repair should hand its draft to outer `complete --draft` so
the source guard runs before publishing. Legacy interaction repair follows native
prepare/candidate checks/merge review; pass its native draft, `--merge-review`
when required, and applicable `--scope-target/--scope-guard` to outer complete.
Do not call native repair complete and then ask outer complete to publish the
same draft again. With no draft the outer layer verifies existing publication.

Baseline/Quick `complete` can refill slots automatically; use `--no-refill`
to drain multiple completed events first. Direct Repair `submit/publish/complete`
never implicitly refill: drain stopped-worker submissions and publication_queue,
then repeat `claim-ready --limit 1`, spawn/attach, and check completion events
until the effective cap is filled or no eligible batch remains. `--limit 1`
limits each claim call, not simultaneous workers; do not wait for that worker
to finish before claiming the next ready batch.
For new direct states, `claim_slots=0` while any claim lacks an attached Agent;
attach or release it before claiming another. Both native lanes enforce this.
The worker handoff must use `native_claim.draft_path` returned by claim/refresh,
outside the private source trees; after refresh forward the new worker and draft
paths to the original Agent, retaining the old draft as evidence.
All direct execution slots are repair slots; queued batches retain writer locks,
not model slots. Dispatcher RUNNING is bookkeeping, not observed Agent liveness.
Optional `progress --agent-status <snapshot.json>` produces observational hints only.
CLI output is compact; publication summaries retain per-item status and the full
receipt path/SHA. Full output requires global `--verbose` before the subcommand.
New interaction claims include native `required_scope_target`; omitted publish
scope uses it and explicit scope may only widen it. The outer layer binds the
normalized domain, permits pre-transaction argument correction without refresh,
and keeps COMMITTING/terminal retry identity immutable. Settings have no media scope.
After every stage, merge the original fragment directories into the filenames in
unified-workflow.md before planning the next stage. Publication and phase
completion do not replace Baseline quality checks or Quick admission rules.

Agent identities are globally bound by durable batch history. The same agent may
retry or recover its original batch, but cannot attach to a different batch.

## Recovery and terminal gaps

`recover --state ... --batch-id ... --claim-token ... --agent-id <same-agent>
--backoff-seconds <0..60>` records one model recovery before the actual bounded
wait/follow-up. It does not itself sleep or restart the model. 429/capacity,
transient disconnect, and formatting correction stay in the same batch context.
A timeout alone does not mean the worker stopped. `replace-agent` requires a
proven unrecoverable old Agent and an available slot; ordinary 429 is not such
proof. Preserve original claim and counters. Never start a replacement while the
old worker is still active.

When review recovery is exhausted, use the lane's native `mark-unreviewed` or
`mark-failed` with true attempts/reason, then outer complete. A `REVIEW_GAP` may
hold a stage open: interaction can consume its single business retry via
`reopen`, or `finalize-gap --reason ...` retains the honest terminal gap.
Setting gaps follow the setting-specific two-attempt marking, not interaction retry
schema. For repair, retain actual changed_files and use the native failed result;
interaction uses outer `complete --failure-reason ... --agent-stopped` for its
native rollback. A pending dependent batch uses `block` with the failed dependency
reason. `release` is only for an unattached clean claim, not a running or failed
Agent. Do not fabricate a passing receipt to free a slot.

Before unified result finalization, every active worker must be stopped and its
claim published or honestly terminated. If an external edit makes safe failure
publication impossible, leave the provisional result and report that exact
blocker; do not force a seal over mutable source.

## Repair work-order reconciliation

Repair 临近收口、恢复任务或发现“有完整工单却没有执行者”时，运行一次机械对账；该命令不调用模型、不重读应用业务语义：

```text
reconcile-repairs --state U/dispatch.json --stage <round-1|round-2> --dispatch
```

新 direct registration 同时冻结 SHA 绑定的 `repair_ledger`，记录该原生计划的初始队列与权限。对账比较原生计划、账本、统一队列、原生执行状态和已有回执；`--dispatch` 仅补回**能证明尚未开始**的缺失队列记录/成员，然后通过既有 scheduler 领取当前阶段允许执行的原工单。原 ID、目标、ownership、依赖、并发上限、writer 锁和所有恢复预算保持不变。默认最多领取一批，按原 claim→创建/attach 握手补位，不把账本当作新的审查或修复授权。

消费返回值时按 batch ID 去重：`claimed_batches` 是本次新领取，`actions` 是各原工单的状态与下一步；已有 claim 的执行上下文可在返回的 `progress.active_batches` 读取。`ATTACH_EXISTING_CLAIM` 先核对本任务已创建的 Agent 记录，续接同一 claim；有 `attach_agent_id` 时续接该 Agent 的 attach，不再创建一个。`WAIT_OR_RECOVER_EXISTING_AGENT` 等待或按原恢复预算处理；`PUBLISH_EXISTING_PROPOSAL / SEAL_EXISTING_RECEIPT / RECOVER_EXISTING_PUBLICATION` 沿已有交稿/发布恢复路径处理，均不派新 Repair。对账完成本身不代表修复成功。

`PARTIAL / FAILED / NO_CHANGE` 与显式 `BLOCKED` 进入 `deferred_results`，仅报告，不自动重修；不能从这些状态推断仍有可修的静态缺陷。`GAPS` 表示无法机械补齐：缺少冻结账本、原生状态丢失、有执行/回执痕迹、后续阶段已经注册或没有原生计划时保留缺口。目标不足、缺陷判断冲突、未生成工单仍按原 Review/规划规则报告，不能据此扩权。旧 registration 不补造账本；没有结果文件本身不构成“没执行”的证明。

此命令不自动启用 Quick/Round 2，不越过失败依赖或发布事务；没有可领取批时根据返回的具体等待/缺口处理，不围绕 `PARTIAL` 或同一 `GAPS` 无限重复对账。通常在每轮收口前一次，以及处理恢复事件后按需调用。省略 `--dispatch` 只核对并同步已有原生状态，不恢复丢失队列或领取新批。

## Local-write recovery

Workers write only their `worker_root`, never `project_root`. If an edit escapes
the private copy, stop the responsible agent and preserve its proposal and the
observed hashes. A source manifest is a comparison baseline, not a byte backup
or proof of who changed a file. Ownership alone does not authorize restoration.

For an interrupted publisher with a trusted before/after transaction journal,
use outer `recover-publication --agent-stopped`. It delegates to the lane's
native recovery, restores only attributable bytes, and preserves an external
third state. Once native publication is terminal, retry outer `complete` to
verify and seal its existing receipt; it will not publish the draft twice.
If direct recovery rolls back to QUEUED, retry deterministic publish without a reviewer.

An arbitrary direct write with no trustworthy journal is not automatically
recoverable. Keep the exact source conflict and provisional result, halt further
writes against that source, and request a trusted recovery baseline/direction.
Do not call `source_guard restore-batch` blindly against an old snapshot.

For an ordinary private-copy failure while official source CAS remains clean,
use `refresh` (at most two times) to resume the original repair identity, or
outer `complete --failure-reason ... --agent-stopped` to discard this candidate
and publish an honest failed receipt. Record the incident and continue claiming
independent work. Setting repair cannot replace its identity: resume the original
agent or fail safely. Interaction replacement follows its native bounded
`agent_unrecoverable` evidence and stopped-agent checks.

## Repair lane manifest rebase and tail refill

New runs freeze `repair_overlap_version=1`. Both repair rounds use the
[certified overlap protocol](repair-overlap.md): dispatch interaction first,
then claim source-bound independent setting proposals into spare global slots.
All pending/running/queued interaction batches participate in the conflict test.

The first early setting claim binds a fresh lane-native manifest and a frozen
peer contract. Later setting claims snapshot current accepted source. The setting
adapter adopts only peer changes backed by terminal receipt hashes and source
diffs; external edits fail CAS. Private worker bases remain immutable. Settings
submit early, release execution slots, and wait for interaction to drain before
publication; skip waiting settings while draining other events.

If no setting native state was initialized early, the existing explicit handoff
still applies after interaction is terminal and no unified batch is active:

```text
rebase-manifest --state U/dispatch.json --stage round-1|round-2 --lane setting
```

Do not call this command after early native initialization. Its original manifest
is preserved. It is never a new Detector or Review pass. Runs without the frozen
overlap version keep their prior handoff rules; do not modify an active run's
identity to enable overlap retroactively.

## Sealed Round 1 continuation

For a later request to continue the second round, follow [round2-continuation.md](round2-continuation.md). The linked dispatcher enables only `quick-review` and `round-2`; inherited history is not registered or claimed again. Resume the returned output and original pending batches on repeated requests.
