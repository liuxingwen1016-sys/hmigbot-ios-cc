<!-- when: 任何门禁 FAIL、轮次用完、连续未收敛、Gate 审批或决策卡提问时加载（a2h-spec / a2h-plan / a2h-execute / arkts-structural-closure 及其子代理共用） -->
<!-- topics: 门禁分类, 工具缺口, 未达标放行, 阶段不可判定, 无人值守, 放行记账, verify 重点核实 -->

# 门禁失败处置规则（无人值守）

本文件是**初始迁移流水线**（a2h-spec → a2h-plan → a2h-execute，含 arkts-structural-closure 与两个覆盖率审计）的
**门禁失败处置唯一规则**，各 skill 正文里的「阻断 / HARD-GATE / 🔴 / 拒绝开工 / 出决策卡」在 FAIL 之后怎么走，一律按本文件执行；
本文件与正文冲突时以本文件为准。派发的子代理同样适用。
**不适用**：增量演进（arkts-spec-evolver、a2h-incremental-migration）里专门设计给用户审核的确认点，照旧等用户确认；
a2h-verify 的检查项选择照旧由用户定。

**用户批准的 Stage 1 根因处置例外**：项目 ledger 明确批准时，Stage 1 先执行 [stage1-gate-policy.md](../../a2h-execute/references/stage1-gate-policy.md)：产物缺陷修复后仍不过就阻断，有证据信息/环境/工具缺口在有界恢复耗尽后带缺口放行；未知根因不放行。本规则覆盖 strict_wiring 原先一律拦截及本文件 Stage 1 真问题可未达标放行的旧表述。流程放行不改变原 FAIL/BLOCKED，也不能写验证通过；其他阶段规则不变。

**为什么**：交付给客户的工具是二进制，客户改不了。检测器是正则加词法分析，遇到没见过的写法就会判错；
如果每个 FAIL 都停下等人，一次误判就能让整条流水线卡住（实测：弹窗闸卡 1 小时以上、组间门原地 19 轮）。
所以检测照跑、照修，修不掉的**记账放行**，由报告首屏、a2h-verify 真机核实和工具维护方回放兜底。

## 1. 先查门禁类别

登记表：`scripts/gate-registry.json`（本 skill 的 scripts 目录，CI 保证与下表一致）。查单条：

```bash
python3 <a2h-spec>/scripts/gate_ledger.py classify <门禁ID 或 规则ID>    # 例：classify C4_BUILDER_NOT_FOUND
```

| 类别 | 判什么 | FAIL 之后 |
|---|---|---|
| 精确类 exact | 真实编译器；或我们自己定义的格式、存在性（AC 格式、`$r` 资源、批大小、ledger 字段） | **必须修过**，不得记工具缺口 |
| 推断类 inference | 工具重新推断安卓/鸿蒙代码的语义：弹窗闭合、接线 C2/C4、孤儿、沉浸式、ArkUI 安全、尺寸复核、ESCALATED 比例 | 有限轮修复；工具看错记「工具缺口」，修不掉记「未达标放行」，继续 |
| 管线类 plumbing | 环节之间的约定：文件名、格式、时机、上游产物 | 同推断类 |
| 环境类 env | 需要设备、服务器或账号才能判断（登录探针、需真机的验收） | 记「阶段不可判定」，推到 a2h-verify |

<!-- gate-table:start -->
| 门禁 ID | 类别 | 工具 / 判据 |
|---|---|---|
| spec.coverage | inference（逐规则见登记表，格式类为 exact） | a2h-spec/scripts/lint_coverage.py |
| spec.dialog-closure | inference（纯索引格式类为 exact） | a2h-spec/scripts/dialog_closure.py |
| spec.divergence | exact | a2h-spec/scripts/lint_divergence.py |
| spec.addenda-closure | exact | a2h-spec/scripts/lint_addenda_closure.py |
| spec.traceability-index | exact | a2h-spec/scripts/build_traceability_index.py |
| spec.ui-coverage | inference | skill:arkts-ui-coverage-auditor |
| spec.feature-coverage | inference | skill:arkts-feature-coverage-auditor |
| spec.package-coverage | exact | 重要包认领 |
| spec.hygiene | exact | Step C4.7 spec 卫生闸 |
| spec.exit-artifacts | plumbing | Gate B/C 出口硬闸 |
| spec.login-probe | env | arkts-network-troubleshoot 场景 E |
| spec.login-chain | plumbing | 登录链路 chain-auth.md 产物 |
| plan.input | plumbing | baseline 就绪 + ui-coverage-report PASS |
| plan.coverage | exact | a2h-plan/scripts/lint_plan_coverage.py |
| plan.thresholds | exact | §7 覆盖率阈值 / 批大小 / 分组 |
| plan.grill2 | exact | §7.2 技术侧决策清零 |
| execute.ledger-startup | plumbing | decision-ledger 存在且 approved |
| execute.plan-format | plumbing | feature-plan.md indexed-v1 布局 |
| execute.resources | exact | a2h-execute/scripts/sweep_resources.py |
| execute.layout-dims | inference | a2h-execute/scripts/layout_dims_gate.py |
| execute.writeback | plumbing | a2h-execute/scripts/apply_writeback.py |
| execute.coverage | plumbing（CLAIM_STALE / CLAIM_UNPLANNED 为 exact） | a2h-execute/scripts/lint_execute_coverage.py |
| execute.build | exact | hmos-builder（Base-7 / Stage 3 集中门 / FV-2） |
| execute.entry-nav | exact | §3a-bis 入口装配 |
| execute.stage1-wiring | inference（按根因处置） | 必需 UI 接线 + 当前包设备冒烟 |
| execute.stage1-g0 | plumbing（按根因处置） | 首次生成交接 |
| execute.stage1-g1 | inference（按根因处置） | UI 装配 |
| execute.stage1-visual | env（按根因处置） | 视觉范围与设备验证 |
| execute.stage1-prerequisite | env | 信息/环境缺口有界恢复后放行 |
| execute.stage1-tool | inference | 已证实的检测能力缺口 |
| execute.stage2-base | exact | Stage 2 brief 任务行 |
| execute.escalated-ratio | inference | ESCALATED Slice 占比 ≤10% |
| execute.fv1-final | inference | FV-1 final_state=PASS |
| closure.skeleton | exact（fake-content / empty-body / orphan-vm / dead-route 为 inference） | arkts-structural-closure/scripts/audit_skeletons.py |
| closure.wiring | inference（C3_FWD_REF_NOT_REMOVED 为 exact） | arkts-structural-closure/scripts/verify_slice_wiring.py |
| closure.orphans | inference | structural_loop orphans detector（ref_graph_lib） |
| closure.immersive | inference | check-fullscreen-immersive-safearea.sh |
| closure.icon-sizing | inference | arkts-icon-sizing 自愈 |
| closure.ledger | inference（ledger-unassembled-dependency、ledger-chain-identity-source-missing 为 hard） | arkts-structural-closure/scripts/verify_closure_ledger.py |
| closure.arkui-safety | inference（ROUTE_PARAM_KEY_MISMATCH 为 hard） | arkts-structural-closure/scripts/verify_arkui_safety.py |
| closure.detector-incomplete | plumbing | detector 超时 / 崩溃 / 缺 JSON / 未跑齐 |
| findings.queue | plumbing | open-findings 队列：连续未收敛刹车 / 队列读不了 |
| gate.release-ledger | exact | a2h-spec/scripts/gate_ledger.py |
<!-- gate-table:end -->

## 2. FAIL 之后怎么走

按顺序判断，一条 FAIL 只走一条路：

1. **精确类**：修。轮次按登记表 `rounds`（正文另有规定从正文；都没写 = 修 1 轮复检 1 次）。
   - 编译门 `execute.build` 用完轮次仍不过 → **停下**，迁移报告写明剩余编译错误。这是唯一的停点：没有可构建产物，后续阶段没有意义。
   - 其他精确类用完轮次仍不过：按定义它总能诚实修过，修不过说明闸自身有缺陷——按管线类记「工具缺口」放行，报告里该行标 🔴。
2. **工具看错了**（推断类 / 管线类）：能拿出证据说明工具漏认或误报 → 立刻记「工具缺口」放行，**不消耗修复轮次**。
3. **真问题**（推断类 / 管线类）：按 `rounds` 修；用完仍不过 → 记「未达标放行」，继续下一步。
4. **当前阶段判断不了**（环境类，或推断类里要动态运行才能判定的项）→ 记「阶段不可判定」，推到 a2h-verify。
5. **登记表标 `hard` 的推断规则**（回放证实 0 误报、且总能修过，例如 `ROUTE_PARAM_KEY_MISMATCH`）：只能修过或用带证据的「工具缺口」放行，不能记「未达标放行」。

**同源复用**：下游阶段遇到由已记录条目引起的同一批 FAIL，直接引用原 D 编号（brief / 报告写「复用 D-0NN」），
不再新开修复轮次。同一门禁的同源 FAIL 不新记条目；落在**另一个门禁**的同源 FAIL（例如 FV-1 未收敛导致的
`EXECUTE.REQUIREMENT_UNCLAIMED`）补一条该门禁的放行记录，正文写「同源：D-0NN」，不重新修——release 只认条目自身门禁的段。
不是同源的新 FAIL 照常处理。

## 3. 三种放行记录

写进 `spec/decision-ledger.md` 的「D 编号决策」区，并在「决策索引」表加一行（类目列写类型名，审批来源 `default-policy`）。
字段名固定，`gate_ledger.py check` 按字段机械核对。

### 3.1 工具缺口

````markdown
### D-0NN Group1 接线检测不认 Content 嵌入
- **类型**：工具缺口
- **门禁**：closure.wiring / C4_BUILDER_NOT_FOUND
- **审批来源**：default-policy（gate-handling）
- **工具输出**：`spec/execution/autofix-log/round-1/wiring-1-iter0.json:199`
- **证据**：`entry/src/main/ets/pages/HomePage.ets:83` `RecommendFragmentContent`；`app/src/main/java/com/x/RecommendFragment.kt:34` `RecommendFragment`
- **漏认写法**：只认字面 `XxxFragmentPage()` 调用，不认按 P-29 拆出的 `XxxContent` 嵌入
- **涉及条目**：5 / 8
- **选定**：放行；同源 FAIL 复用本条
````

- **门禁**：登记表里的门禁 ID，可加 ` / 规则ID`（同一门禁的多条规则用「、」分隔，类别按其中最严的一条核）。精确类不得记工具缺口（§2 第 1 条的闸缺陷例外除外，此时**门禁**写规则 ID 并在**漏认写法**写明为何修不过）。
- **工具输出**：工具 FAIL 所在的报告文件（`路径[:行]`），必须存在，且不能是 ledger 或 `spec/gate-release/` 本身。
- **证据**：至少一处 `` `路径:行` ``，**每处**后面都跟一个 `` `符号` ``；该行（±2 行）必须真的含这个符号。路径相对鸿蒙工程根或安卓工程根（`--android-root`），也可写绝对路径。证据说明「实际写法在这里，工具没认出来」。
- **涉及条目**：`本条覆盖的 FAIL 数 / 该门禁 FAIL 总数`，覆盖数 ≥1 且不超过总数。
- **已修轮次**（仅精确类规则的闸缺陷需要）：≥1 的数字，说明确实修满了轮次。
- 一条工具缺口只说一种漏认写法；同一写法在多处出现写在同一条里。
- 证据或漏认写法里写明涉及的对象（类名、页面、AC 编号）：release 只放条目点到的对象；一个都没点到时，
  「涉及条目」的覆盖数必须恰好等于段里该规则的条数，才整批放。
- 精确类规则的闸缺陷：门禁字段必须写到规则（`closure.skeleton / naked-TODO`），并写已修轮次。

### 3.2 未达标放行

`gate_ledger.py check` 会读「工具输出」里的检测结果 JSON（loop 结果会顺着 `detector_json_paths` 读当轮明细，
`loops-*.json` 自动换成同目录的 `loop-result-latest-*.json`），看工具实际还剩哪些 FAIL：剩下的精确类或 hard 规则，
必须已被某条成立的「工具缺口」在门禁字段里点名覆盖，否则这条未达标放行不成立——和条目正文怎么写无关。
FV-1、ESCALATED 比例和结构闭环各检测器的放行，「工具输出」必须给这种检测结果 JSON。

````markdown
### D-0NN FV-1 结构终审未达标放行
- **类型**：未达标放行
- **门禁**：execute.fv1-final
- **审批来源**：default-policy（gate-handling）
- **工具输出**：`spec/execution/autofix-log/round-2/loops-final-structural-closure.json`
- **已修轮次**：3
- **剩余 FAIL**：孤儿 4 项（PushPageInfo、…）；骨架 2 项复用 D-038
- **选定**：放行继续；剩余项进 a2h-verify 重点核实
````

### 3.3 阶段不可判定

只用于环境类，或推断类里要运行态才能判定的项；精确类、管线类、hard 规则不能记这一类。

````markdown
### D-0NN 登录探针缺可达后端
- **类型**：阶段不可判定
- **门禁**：spec.login-probe
- **审批来源**：default-policy（gate-handling）
- **工具输出**：`spec/baseline/auth-probe-result.json`
- **缺什么**：可达的测试后端与测试账号
- **选定**：放行；推到 a2h-verify 真机核实
````

## 4. 记账之后

1. **核对**：每记一条就跑一次（迁移报告生成前必跑）：

   ```bash
   python3 <a2h-spec>/scripts/gate_ledger.py check --project-root . [--android-root <安卓工程根>]
   ```

   退出 1 = 有条目不成立（字段缺失、门禁未登记、证据行不存在或不含符号、类别不允许这种放行、字段值不成立），
   或有疑似放行条目解析不出（`**类型**：` / `**类型：**` 两种写法都认；决策索引里登记成放行类型却找不到正文条目也算）。
   改正**条目本身**；证据核不过说明它不是工具缺口——按真问题处理，修完轮次后记「未达标放行」。
   通过后产出 `spec/gate-release/`：`summary.md`（迁移报告首屏三张表 + 每道门放行比例）、
   `verify-focus.json`（a2h-verify 重点核实清单）、`tool-gap-feedback.md`（发回工具维护方的缺口清单）。
2. **标记 open-findings**：放行项若在 `spec/.a2h/open-findings.json` 里（三个 lint 脚本写的），标上决策编号：

   ```bash
   python3 <a2h-spec>/scripts/gate_ledger.py release --project-root . --decision D-0NN [--rule <规则ID> ...]
   ```

   放行范围由条目决定：只放该条目覆盖的规则；门禁级条目（不点名规则）只覆盖其中非精确、非 hard 的规则；
   精确类规则须单独点名、以「工具缺口」记并写已修轮次；hard 规则须单独点名、以「工具缺口」记，
   而且工具输出里带编号的发现（`p_id` / `type`，如 `ledger-unassembled-dependency` 的依赖类型）要在条目正文里逐个点到——
   没点到的那几条仍算剩余 FAIL，「涉及条目」自报的条数不算数；同一条 FAIL 出现在几份结果 JSON 里只算一次。
   检测器分析出错（`ledger-assembly-analysis-error`）没有结论可言，不能被「未达标放行 / 阶段不可判定」整体带过，须单列「工具缺口」。
   段名按登记表自动取，写错段名、规则不在覆盖范围、或段里一条都没匹配上，都会报错退出 1。
   连续未收敛刹车（`LOOP.NOT_CONVERGING`）记在 `findings.queue` 门禁下，`release --section <段>` 只解除刹车，
   段里的实际 FAIL 仍要按各自门禁记账放行。

   只有三个 lint（`spec/lint_coverage` 含 Dialog 闭合 / `plan/lint_plan_coverage` / `execute/lint_execute_coverage`）
   的 FAIL 进 open-findings；结构闭环、覆盖率审计等门禁不需要这一步，记账即可。
   记账后 `lint_coverage.py --report-only` / `--only-feature` 同样把这些条目显示为 ⚪ 已放行、不计退出码。
   被标记的条目照常列出（标「已放行 D-0NN」），但不再让 linter 退出 2、不再让下游「拒绝开工」、不计入连续未收敛；
   该 section 的 halted 一并解除。条目只有原 linter 重跑后不再报才算关闭。
3. **放行比例**：同一道门禁里放行条目超过 FAIL 总数的 20%，`summary.md` 标 🔴「放行比例偏高」。不停下，但报告首屏要看得见：
   要么工具在这类工程上大面积失效，要么修复在偷懒。

## 5. 审批与提问（默认无人值守）

- **Gate A / B / C、a2h-plan §8 审批**：无 🔴 → 自动选 [1]；🔴 都已记账 → 自动选 [2]，例外列 D 编号（关闭条件 = a2h-verify 核实）；
  还有没记账的精确类 🔴 → 先修，修完再过 Gate。
- **决策卡**（grill、阻塞上报、开工前的三选一）：取标「← 推荐」的选项，写 ledger（审批来源 `default-policy`），不等待回复。
  没有推荐项的选项题按 `references/default-policy.md` 裁定。
- **连续未收敛**（`escalate: true` / section `halted` / loop STALLED、EXHAUSTED）：不出卡等人，直接按 §2 记「未达标放行」
  （或有证据时记「工具缺口」），再按 §4 第 2 步解除 halted。
- **execute 决策缺口**（ledger 未命中）：按 default-policy 或决策卡推荐项裁定，写 D 编号（审批来源 `default-policy`）后继续；
  迁移报告「决策缺口」段照样登记，供事后复核。
- **例外**：用户在对话里明确要求逐个确认（如「每个 Gate 都要我确认」）时，按用户要求停在 Gate。

## 6. 禁止

- 修改、替换或另写脚本顶替任何 skill 工具（包括复制一份改了再跑、写包装脚本过滤输出）；
- 修改门禁报告、工具输出、open-findings 的 verdict 或计数；
- 为迁就检测器改产物：嵌套 `NavDestination`、伪造类或空方法、凑尺寸数值、把正确的实现改错；
- 把真问题记成工具缺口；在一条工具缺口里塞多种不相干的写法。

## 7. 迁移报告首屏

a2h-execute §10 生成 `spec/migration-report.md` 时，把 `spec/gate-release/summary.md` 原样放在报告最前面（总览之前），
三张表：工具缺口 / 未达标放行 / 阶段不可判定。不得把放行项改写成 PASS，也不得省略「放行比例偏高」标记。

## 8. 维护方：新增门禁与回放

- 新门禁、新规则 ID、新的检测脚本先进 `scripts/gate-registry.json` 并标类别，CI `scripts/ci/check-gate-registry.sh` 强制。
- 推断类规则要标 `hard`：须在 ≥3 个真实工程上回放 0 误报（`build/release-replay/release_replay.py`），回放结果写进该规则的 `replay` 字段。
- 客户发回的 `tool-gap-feedback.md` 每条都带写法和源码位置：按条复现、修进工具、加进回放基线，再发包。
