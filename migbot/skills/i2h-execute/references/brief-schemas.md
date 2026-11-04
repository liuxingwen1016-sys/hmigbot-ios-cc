<!-- when: 产出 Batch / Stage 2 / Group brief 文档（§3b / §4e / §5e）时加载 -->
<!-- topics: brief schema, Batch brief, Stage 2 brief, Group brief, loops 段, final_state -->

# i2h-execute brief 文档 schema

> 由 `i2h-execute/SKILL.md` 的 §3b / §4e / §5e 引用。本文件收三类 brief 的 markdown 模板 + 字段读取来源；HARD-GATE 规则（何时强制产出、缺失如何阻断、BLOCKED 判定）留在 SKILL.md 对应章节。

i2h-execute 三阶段各产一类 brief，统一落 `spec/execution/briefs/`：

| brief | 产出时机 | SKILL.md 章节 |
|---|---|---|
| Batch brief | Stage 1 每个 Batch 结算后（批内无编译） | §3b |
| Stage 2 brief | Stage 2 全部 Base 任务完成后，**主线程直写**（非 closer 产物、不经 manifest） | §4e |
| Group brief | Stage 3 每个 parallel_group 收尾（§5e）后——组粒度单文件，per-slice 小节 | §5e |


## 0. 跨 brief 通用：`final_state` 与按阶段出现的 `loops`

每个 brief 必含 `final_state`；`loops` 只允许记录该收口点实际执行的 loop，是否出现按各 brief 模板。Batch brief 无 loop；普通 Group brief 只有 structural loop，末组 defer 分支也无 loop（编译延后到 execute §5f，结构延后到 FV-1）；Stage 2/FV 的编译证据由对应 `hmos-builder` gate 记录，不得伪造成 Batch/Group compile loop。

**`final_state` 枚举**：

| 值 | 含义 | 下游影响 |
|---|---|---|
| `PASS` | 当前 brief 所属收口点的必需检查均通过；若 `build_status` 为 deferred，则不代表编译已通过 | 正常进入下一编排单元；仍受后续集中编译门约束 |
| `ESCALATED` | structural_loop 返回 STALLED / EXHAUSTED | 标记 + pipeline 继续（该 Slice 不记 implemented、不写 impl_claims）；§5f 末尾 ESCALATED Slice 数 / 本次执行 Slice 总数 > 10% → 阻断 FV-1 / i2h-verify；复核与恢复见 arkts-structural-closure §3.3 |
| `ROLLED_BACK` | structural_loop 返回 REGRESSED | git stash 本单元改动；阻断所有 `depends_on` 本单元的下游 |
| `BLOCKED` | placeholder / source-notes / deferred-work 登记校验 FAIL（不走 loop） | Slice 标 BLOCKED，要求人工补 plan |

**`loops` 段格式**（YAML；只写实际执行的子段，禁止为未运行的 compile/structural loop 填零冒充证据）：

```yaml
loops:
  compile:                             # 仅执行了 hmos-builder 的 Stage/FV 收口点填写
    iterations: 3
    converged: true
    final_errors: 0

  structural:                          # 执行了 structural-closure 时填写；Group 通常仅有此段
    iterations: 4
    converged: true
    final_state: PASS                  # PASS | ESCALATED | ROLLED_BACK
    final_audit_fail: 0
    final_wiring_repair_actions: 0
    verdict: CONVERGED                 # CONVERGED | CONTINUE | STALLED | REGRESSED | EXHAUSTED
    escalation: NONE                   # NONE | MANUAL | ROLLED_BACK
    reason: "all checks pass at iteration 3"
    history:
      - { iter: 0, audit_fail: 0, wiring_repair_actions: 7,  brief_escape_hatches: 0 }
      - { iter: 1, audit_fail: 0, wiring_repair_actions: 3,  brief_escape_hatches: 0 }
      - { iter: 2, audit_fail: 1, wiring_repair_actions: 1,  brief_escape_hatches: 0 }
      - { iter: 3, audit_fail: 0, wiring_repair_actions: 0,  brief_escape_hatches: 0 }
```

**`escalation` 段**（仅 final_state 为 `ESCALATED` / `ROLLED_BACK` 时填；`deferred-to-FV` 不是 escalation）：

```yaml
escalation:
  category: structural_loop_stalled    # 或 _regressed / _exhausted
  unresolved_findings: <spec/execution/autofix-log/round-N/audit-X-iterY.json + wiring-X-iterY.json 路径>
  recommended_human_action: |
    上一轮 structural_loop 在第 N 轮停滞，verify_slice_wiring.py C2 仍报 3 个
    integration_point evidence 违规。建议检查 spec/baseline/features/F-xxx.md
    的「## 对接点」段是否描述格式正确（含 `<handler> ← <target>` 箭头）。
```

**`review_findings` 段**（仅 final brief；来源 = structural_loop finalize 输出的 ArkUI WARN，closer 复核后填结论）：

```yaml
review_findings:                       # 无 WARN 时写 []
  - { rule_id: STACK_FULL_HEIGHT_OVERLAY, at: pages/AboutPage.ets:165, verdict: no-issue, basis: "对话框遮罩层，与源端 scrim 一致" }
  - { rule_id: NAV_SHAPE_UNKNOWN, at: pages/MainPage.ets:82, verdict: to-verify, basis: "pageMap 动态路由，静态不可判" }
```

`verdict` ∈ `owner-repair`（迁移偏差，已交原 owner 修后重跑）/ `to-verify`（交 i2h-verify 实测）/ `no-issue`。

> 旧字段 `unresolved_placeholders` / `unregistered_skeletons` / `resource_dependencies_unresolved` 已废弃——loops.structural 段已含其所有信息（structural_loop 既扫骨架也校接线，state 文件持有完整 history）。如旧版 brief 仍含这些段，可读但不再要求新版 brief 写出。


## 1. Batch brief（§3b）

full-ui-v2 的 batch 结算只标 STRUCTURAL_ONLY，manifest 必有 stage1.phase=assembled。全部必需状态的真实 S1-V 结果归档后方可 assessed；只有 stage1_acceptance 汇总当前结构/构建/视觉全部 PASS，才可 complete。原 1030 模式的用户 SKIP 不满足此条件。


落点：`spec/execution/briefs/batch_NN_brief.md`

````markdown
# Batch NN Brief
- 完成时间: YYYY-MM-DD HH:mm
- final_state: PASS | BLOCKED          # PASS = 结算完成（资源 sweep + manifest）

## generated_pages
| 页面 | 状态 | 行数 |
|------|------|------|
| MainPage | converted | 245 |

## next_batch_prerequisites
- 前一 Batch manifest 已 apply
- 跨 Batch 间的 placeholder / resource 状态从 spec/placeholder-registry.md 与 resource-mapping.md 取
````

（Stage 1 无编译 → 无 loops / escalation 段；Stage 1 末的骨架审计由 execute §3d 主线程执行，结果入统计不入 batch brief）

读取来源：
- `generated_pages` 列：从 ui-manifest.md 本 Batch status: converted 的页面


## 2. Stage 2 brief（§4e，主线程直写）

落点：`spec/execution/briefs/stage2_brief.md`——每个 Base worker 返回后主线程追加一行；Base-7 编译与 §3c 骨架审计结果写在表后。resume 判据 = 本表状态列。

````markdown
# Stage 2 Brief
- final_state: PASS | BLOCKED          # Base 任务 + Base-7 编译 + §3c 骨架审计的合并结论

| 任务 | 状态 | 产出文件数 | 备注 |
|------|------|-----------|------|
| Base-1: Models | PASS | 5 | |
| Base-3: Network | FAIL | 0 | output 通配无文件，已重派 1 次 |

- 编译状态（Base-7）: PASS / FAILED（FAIL 时附 REMAINING_ERRORS 摘要）
- 骨架审计（§3c）: PASS / FAIL
- evidence: base-contracts.md 路径 / checkpoint commit
````

读取来源：状态 = 主线程按 base-plan `output:` 通配核对文件存在且非空；产出文件数 = worker 信封 `generated_files`。


## 3. Group brief（§5e，Stage 3 组粒度单文件）

落点：`spec/execution/briefs/group_NN_brief.md`——**任意组大小含 size-1 组**（串行降级 / 重试单 slice 同样按组文件写，slices 单元素）。由 **group-closer 唯一起草**（brief 全文进 writeback manifest `brief.content`，经 `apply_writeback.py` 落盘，见 §4——作者唯一 = closer，脚本只是落盘手）；ESCALATED 单 slice 重跑**只更新对应小节**（重跑 closer 读旧 brief 改该小节后给全文）。

**机器契约**：per-slice 小节头 = `## Slice N (F-xxx)`（deferral_policy / verify_closure_ledger 按小节切分归属 final_state；首个小节之前为组共享头部，不参与逐 slice 判定）。**残余延迟工作的权威在 registry `kind=deferred-work` 行**，brief 小节只留一行引用 `deferred_work: [P-ID…]`（派生显示，无独立生命周期；旧版 `### deferred_items` 表由债务终结闸作 legacy 兜底扫描）。

````markdown
# Group NN Brief
- group_id: N | slices: [Slice X, Slice Y] | 完成时间: YYYY-MM-DD HH:mm
- build_status: deferred-to-stage3-gate              # 组内无编译，结论由 execute §5f 编译门给出
- structural_verdict: CONVERGED | ESCALATED | deferred-to-FV（仅末组）  # 组共享
- wired_shared_files: [...]                           # 组级跨文件接线改动清单
- resolved_fwd_refs_group: [P-S{N}-..., ...]          # 本组解除的 forward-ref（本组翻 resolved 的行）

## loops
（§0 格式；普通 Group 只写 **structural** 子段并由全组共享一次，各 slice 小节不复制；末组 defer 分支省略 `loops`；compile 结论统一由 execute §5f 记录）

## escalation
（仅 structural_verdict 对应 ESCALATED / ROLLED_BACK 时填；`deferred-to-FV` 不填，见 §0）

## Slice X (F-xxx)
- final_state: PASS | ESCALATED | ROLLED_BACK | BLOCKED
- step_3a_ui_supplement: generated_files / status_changes（page_NNNN pending → converted）
- step_3b_viewmodel: generated_files / source_notes_path（complex 必含，缺失 → BLOCKED）
- step_3c_data_layer: generated_files
- step_3d_wiring: wired_files / integration_points_done: n/n / resolved_fwd_refs（本 slice）
- cross_slice_edits: | file | handler | 原 owning_slice | 落地 evidence | 表（有则填）
- pages_covered: [...]（本组触及页面，供 i2h-verify CHECK-5 核验）
- deferred_work: [P-ID…]（registry `kind=deferred-work` 行引用，权威在 registry）

deferred_work: [P-S8-003, …]        # registry kind=deferred-work 行的引用（权威在 registry，本行派生显示）

## Slice Y (F-yyy)
（同上结构）
````

读取来源：头部 = group-closer 自身结果（deferred build 状态 / structural / 共享文件改动 / 本组翻 resolved 集合）；各小节 `step_3a/3b/3c` = 该 slice worker 报告；`step_3d` 跨文件部分 = group-closer 步骤 1；`loops.structural` 组共享一份（各小节引用同一次，不复制）；per-slice 串行旧形态（`slice_NN_brief.md` 整文件）为 legacy 兜底，消费脚本双形态解析。


## 4. Writeback manifest（三模式通用，closer 唯一账本出口）

**原理**：closer 前四步改代码（落盘即持久），账本变更（registry 翻转/retag、ui-manifest / feature-index 状态翻转、brief 落盘）100% 可从结果推导——不该在 20 分钟长 turn 尾巴上由 LLM 手写。closer **turn 内一律不 Edit 账本**，全部变更记入一份 manifest 一次 Write，由主线程跑 `i2h-execute/scripts/apply_writeback.py` 确定性落盘（幂等可重放；**崩溃恢复 = 重跑 apply，绝不重做接线 / 结构收口**）。**唯一例外 = 新占位登记**（P-ID 发号 append-only，build-loop 即时消费，照旧直写）。

落点：`spec/execution/writeback/writeback-<mode>-<id>.json`（如 `writeback-group-03.json` / `writeback-batch-02.json` / `writeback-final.json`）。

```json
{
  "mode": "group",                        // group | batch | final
  "id": "03",
  "registry": {
    "resolve": ["P-S1-001", "P-S2-001"],  // 全部 kind → status→resolved，不删行（原地保留可追溯，Class 2 对账）
    "retag": [{"pid": "P-S6-004", "column": "resolve_by", "value": "D-003（忠实占位·永久保留）"}]
  },
  "ui_manifest": {"converted": ["0040"]},                                 // 键 = 序号
  "feature_index": {"implemented": ["F001"]},                             // 键 = F-ID
  "impl_claims": {                        // AC 级认领（modes: group/final；batch 无 AC 归属不产）
    "claims": [{"requirement_id": "F001-AC01", "packet_id": "slice-03-F001",
                "files": ["entry/src/main/ets/pages/HomePage.ets"],
                "requirement_digest": "sha256:…", "attempt": 1}],          // symbols 可选
    "executed_packets": ["slice-03-F001"]
  },
  "brief": {"path": "spec/execution/briefs/group_03_brief.md", "content": "<brief 完整 markdown，schema 见 §1–§3>"}
}
```

**生产端** = closer 写意图 JSON 后跑 `scripts/build_writeback.py`（透传账本段、从 plan-coverage 展开 impl_claims、brief 从草稿文件读入、group 模式校验 slice 小节齐全）；**消费端** = `apply_writeback.py`。

各段可省（mode=batch 通常仅 `ui_manifest.converted` + `brief`）；`feature_index.implemented` 只在结构 CONVERGED 时记入（编译结论由 execute §5f 门给出）（`ui_manifest.verified` execute 侧无生产者——`verified` 唯一写者 = i2h-verify §6.1）；defer 末组（`structural_verdict: deferred-to-FV`）不记该段，由 mode=final 的 manifest 补翻。`impl_claims` 与对应 mode 的收口前置一致：group 模式不伪造编译前置，仍受后续 §5f 集中门约束；`requirement_ids`/`requirement_digests` **抄自 plan-coverage.json 对应 packet，不由 LLM 手写**；落盘幂等键 = `(requirement_id, packet_id, attempt)`（apply_writeback.py §5，重跑 apply 不重复）。
