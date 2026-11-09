# app-relationship-tree CHANGELOG

## 2026-09-15 覆盖闸：非 walkable 剔出分母 + E3 默认 92% + 放宽阈值须用户批准（`scripts/tree_coverage_report.py`）
病（0915 AntennaPod 插件实跑）：E1 分母把 walkability 为 abstract / external_entry / dead 的节点算进去（11 条缺口全是这类），
E3=100% 在压栈子页上不可达；模型两次 FAIL 后自写 override 标记降阈值过闸（visual-verify Step 1.0.7 铁律 4/5 双违）。
- `dead(r)`（walkability ∈ {dead, abstract, external_entry} / dead_code / truly_isolated）不再进 E1/E3 分母，另报 `nonwalkable_excluded`；
  它们本就不能当活入边的起点（E1 判据）、2.5 契约豁免 LLM 补全，留在分母里只会逼模型放水。
- 默认 `--min-e3` 1.0 → 0.92（用户拍板）；`DEFAULTS` 集中定义。
- 任一 `--min-*` 低于默认 → 必须 `--hints`（默认 `<tree 同目录>/tree_hints.json`）里有 `coverage_gate_approved`
  `{by: "user", min_*: …, reason}` 且批准值 ≤ 命令行值，否则 `--gate` 打 `GATE: REFUSED` exit 3（不带 --gate 只警告）。
  `--json` 产物新增 `thresholds / defaults / relaxed / approved_by / gate`，下游可审计。
- `_tests/test_tree_coverage_report_0915.py` 6 例（分母 / 默认值 / 拒绝 / 批准通过 / 更松或非用户批准拒绝 / --hints 路径）。

## 2026-09-11 Phase 1.7 方法现场节点归位（`scripts/fold_call_site_nodes.py`，未 commit）
病：节点 id 的 `$` 被赋两种意思（JVM 内部类 vs toolkit 方法现场），方法现场被当独立的屏入树 → 与真弹窗类节点重复
（0910r3 树 8/30 个 dialog）。下游三次付账：安卓归因「已消费不可再现」盖住 / 鸿蒙回放按影子节点排放行步卡死 /
判读"两道门鸿蒙一道"误判。反哺契约不许删节点、tree_dup 只查边 → 无回路，故树侧根治。
- 新脚本 + `run_all_phases.sh` Phase 1.7（排 1.6 之后，`--tree-feedback` 可选）+ SKILL.md 阶段表与新节。
- 规则：读方法体判真身 → 纯复制 merge 删影子 / 共享参数化弹窗状态保留并继承布局+调用点文案 / 平台 UI 与解不出标 uncertain；
  死调用点只删不合边；auto 触发按 (from_page,"auto") 去重；全树引用改指并去重；幂等。
- 真树实跑：dialogs 30→26（合并 2 / 死删 2 / 状态 4），pages/fragments 不变，容器/向导页零误合，flow_graph 边数不变。
- 干跑期间修掉三处：`dead_code_hint` 误当死判据（8/8 合成节点都带这串提示）；Java 式声明正则把换行后的调用当声明；
  `merge_edges` 原地改名不去重致 shows_dialogs 出现重复。
- 测试 `_tests/test_fold_call_site_nodes.py` 12 例（零 app 常量）。
- **整链 A/B 实跑**（用户追问"有没有真跑 ART"后补做，此前只单跑过脚本）：`run_all_phases.sh --skip-llm-check` 带 1.7 对 0910r3 树副本
  跑通八个确定性 phase（exit 0，5.6s），与同树不带 1.7 的 B 组逐项对比。抓出两处再修：
  ① 合并补空把影子节点 auto 触发上的放行键 `trigger_view_id` 灌进了真节点 → auto 触发补空只认 wait_hint/证据类字段；
  ② fold 给状态节点填了 `parent_in_nav` → Phase 2.4 据它补一条无控件 `dialog_show` 裸边，与真触发边构成"一站点两目标"噪音
  → 不填（宿主只记在 `call_site.from_page`）。修后 A 比 B **恰好少 2 条触发**（被折叠的两条）、零新增边、guard_flags 零新增，
  B 组 `tv_success_operate` 那条"一站点两目标"标记在 A 组消失——它标的正是重复节点本身。下游 2.4/2.3/2.6/2.8 统计差异全部可由
  "少 4 个节点 + 4 个状态节点继承布局"解释。终树 11 条 flow_graph 悬空边 A/B 相同，是 toolkit 原有的 `$1/$2` 匿名类噪音。
- **通用性复审**（用户追问「确定通用吗」后再改四处，均有真树/合成用例）：① 目标限定树里的**弹窗记录**（此前页面类的静态调用
  只是碰巧因工厂名清单没匹配上才没被并进 Activity）；② 工厂名不设清单，`X.xxx(` 任意静态调用宽取再与弹窗记录交集；
  ③ 文案判据扩到 setter / 属性赋值 / apply 块，但只认顶层赋值与裸调用，嵌套 lambda 与别的接收者的调用不算（真树 `vippop_3`
  埋点事件名混入实测）；④ 布局改三向比较（915 版 toolkit 给方法现场挂的是**宿主**布局，"有布局=真面"在那版失效，8 个重复原样漏过）。
  ⑤ A 链实跑再抓一处：2.4 `enrich_layout_facts` 按布局文件**整体重算**冲掉调用点文案 → 新增 `call_site_texts` 字段 +
  `tree_generic.merge_call_site_texts` 重算后并回（`_tests/test_merge_call_site_texts.py`）。三版 AIPPT 树分类一致 4/4。
- 未做（无可验证实例，按「先验证可行」不动）：tree_generic 三处 `split("$")` 的内部类串台改法——AntennaPod 现树已无 `$` 节点、无同名撞车，复现不了。



# app-relationship-tree — 待验收变更（树生成侧，2026-09-09）

> 独立于共享 `CHANGELOG.md`，验收通过后再并入。本批未 commit / 未 push / 未动模拟器。
>
> 动机：0909 安卓边遍历 36 次熔断，12 次归树数据（六种假边/弱哨兵形态）、6 次归
> `vip_required` 没有极性（它的真语义常常是「**非**会员才显示」）、2 次归空输入守卫没有结构化输入配方。
> 这三类全部能在**计划阶段**用机械规则拦住，不必烧设备时间去撞。
> 机械层原则不变：**只产事实、不下判断**；契约字段由 SKILL.md 规定；闸只证伪不代判。

## D1 新增 `scripts/edge_lint.py`（边级机械注解器，幂等）

`edge_lint.py <tree> [--dry-run] [--write] [--json report.json]`。对每条**活**边（`disproven` 的不再注解）
算 `guard_flags[]`，一条都不中时删掉该字段；`--write` 另在树根写
`_phase_markers.edge_lint = {ts, counts}`。除这两处不碰任何字段，退出码恒 0（注解器不判定）。

| flag | 判据 |
|---|---|
| `owner_mismatch` | `trigger_owner_page` 非空且 ≠ `from_page`（控件不在起点页上） |
| `site_two_targets` | 同一站点键 `(from_page, trigger_view_id\|evidence_line, span_text)` 落在两个不同目标 record，且两条边都没有 `branch_condition` / `edge_preconditions` |
| `rid_not_in_from_layout` | `trigger_view_id` 不在起点页可见 id 域＝自身 `layout_facts.view_ids` ∪ 可解析 `includes` 链 ∪ 宿主/被宿主 record（`contains` / `parent_id` 双向）∪ `list_item_roots[].root_id`。起点无 record 或无 `view_ids` → 不标 |
| `rid_no_click_evidence` | 起点页有 `layout_facts.clickable_ids` 但 id 不在其中，且 `provenance.status != "confirmed"`。无该字段 → 不标 |
| `compressed_path` | 同站点键的两条边指向 B 与 C，而 C 的 inbound 里有一条 `from_page == B` ⇒ →C 那条多半是把 A→B→C 压成一跳 |

**两处对规格的收窄（都为消除成族误报，均为通用规则、零 app 常量）**

1. `disproven` 的边不注解、也不参与站点成组。实测树里 24/139 条 disproven，其中数条 `trigger_view_id`
   与 `evidence_line` 全空，按站点键会聚成一个假的「同站点多目标」组（该项使命中从 30 条降到 22 条）。
2. `list_item_roots[].root_id` 算进 rule 3 的可见 id 域。适配器 item 的根 id 不在页面自己的 layout 里，
   但运行时确实渲染在这一页、也确实是点击目标；不并入则每条 `trigger_kind: list_item` 的边必误报
   （该项使命中从 22 条降到 18 条）。

## D2 `tree_generic.py`：`layout_facts.edit_ids` / `clickable_ids`

`LayoutTextResolver` 新增 `input_click_ids(xml)` 类方法，`layout_facts()` 产出两个新列表，
`enrich_layout_facts()` 的 key 列表同步复制：

- `edit_ids`：标签名以 `EditText` 结尾的有 id 节点（`AppCompatEditText` / `TextInputEditText` /
  自定义 `*EditText` 全限定名都以简单类名收尾，后缀判定即可覆盖）。
- `clickable_ids`：`android:clickable="true"` 或带 `android:onClick` 的节点，加上标签名以
  `Button` / `ImageButton` / `CheckBox` / `RadioButton` / `Switch` / `Chip` / `FloatingActionButton`
  结尾的节点。**只看布局**——代码 `setOnClickListener` 上去的普通 View 不在其中，所以「不在 clickable_ids 里」
  只是线索，不是"不可点"的证据（这一句同时写进了 SKILL.md 与 edge_lint 的规则说明）。

用的是 Android 平台控件词汇，不含任何应用的页名/控件 id/文案/包名。
两份副本（`toolkit-fact-indexer/scripts/` 与 `app-relationship-tree/scripts/`）改后 `diff` 为空、sha 一致。

## D3 契约与守卫

**SKILL.md Phase 2.5**（机械事实清单）：`layout_facts` 字段表补 `edit_ids` / `clickable_ids` 及其口径与
「布局没写死可点 ≠ 不可点」的告诫；「可用的测量」补 `edge_lint.py` 一条（五个 flag 的含义 +
**带 flag 不等于删边**，仍走「原地升级或证伪」）。

**SKILL.md Phase 2.7**：新增「★契约三条」——

1. `kind ∈ {login_required, vip_required, login_conditional}` 必须带 `polarity: "required" | "absent"`
   （record 级与边级 `edge_preconditions` 一视同仁），附源码判定依据对照表：守卫**拦住**继续往下走 = required；
   取反条件**里面就是**那个入口本身（`if (!isVip()) showUpgradeEntry()`）= absent。
2. `kind == "state_required"` 且守卫是「某输入框非空」时必须带
   `input: {"view_id": <该页 edit_ids 之一>, "text_hint": <ASCII 或 null>}`。
3. 门弹窗（`relationship_kind == lifecycle_modal` 且前置 kind 以 `first_launch` 开头）必须有
   `trigger_kind: "auto"` 的 inbound 边并带 `wait_hint`。

**`llm_phase_guard.py`**：`verify()` 新增两项 FAIL 级检查（第 3 条是 SKILL 契约，本批未做机械强制，见"未做项"）。
新增 `check_preconditions_contract()`，record 级与边级共用；`verify()` 多一个可选 `warns` 出参，
`main()` 打印 WARN 段并写进 `--json`。`ART_ALLOW_MISSING_POLARITY=1` 把**缺失** polarity 降为 WARN
（取值拼错恒 FAIL —— 那是笔误不是过渡）。`input.view_id` 查「输入框所在页」（边级＝`from_page`，
record 级＝该 record）的 `layout_facts.edit_ids`，该字段缺席则不判。

**`preflight_check.sh`**：
- 新增「Phase 2.7 极性覆盖」段：统计 login/vip 类前置（record 级 + 边级）带 polarity 的比例，
  <100% 记 NEED（沿用 NEED/MESSAGES 机制），=100% 打印 ℹ️ 测量行。
- 新增 edge_lint `--json` 的 flag 计数信息行（不判定）。
- 顺手修：`ℹ️` 测量行原来只在有欠账时才打印（OK 分支直接 `exit 0`），树干净时反而看不到测量；
  OK 分支现在补印所有 ℹ️ 行。

## 测试

新增 `app-relationship-tree/scripts/_tests/test_edge_lint.py`（6 例：五条规则各一例含豁免路径，
外加 `--write` 幂等 + 陈旧 flag 被剪掉）；扩 `test_llm_phase_guard.py` 3 例（极性缺失 record/边级双 FAIL、
环境变量降级为 WARN、`input.view_id` 不在 `edit_ids` FAIL）；扩 `test_tree_generic.py` 2 例
（`input_click_ids` 平台控件词汇覆盖、`enrich_layout_facts` 端到端带出两个新列表）。全部用合成小树 /
合成 layout XML。

现有 `test_llm_phase_guard.py` 的 `_tree()` fixture 补了 `"polarity": "required"`——它原本就是一条
`login_required` 前置，按新契约必须带极性；这是让 fixture 合规，不是放宽断言。

`python3 -m pytest -q app-relationship-tree/scripts/_tests toolkit-fact-indexer/scripts/_tests` → **37 passed**。

## 未做项

- **契约第 3 条（门弹窗自动入边 + wait_hint）只写进 SKILL.md，未加机械检查**：本批交办的 guard 检查清单
  只含极性与 input 两项；该条涉及 `navigation_contract` × `preconditions` × `inbound_triggers` 三处联查，
  且现有树里首启弹窗的 kind 拼法尚未统一（`first_launch_onboarding` 之外还有别的写法），先不上闸避免误伤。
- **`run_all_phases.sh` 未接入 `edge_lint.py`**：该文件不在本批可改范围内。接线建议——Phase 2.4
  （机械候选落成）之后、Phase 2.5 派 sub-agent 之前跑一次 `edge_lint.py <tree> --write`，让 LLM 读到
  带 `guard_flags` 的边。目前 preflight 只做只读测量。
- **`rid_no_click_evidence` 尚无真实数据**：`clickable_ids` 要重跑一次 tree_generic 才会进树，
  现有 0909 树上该 flag 恒 0。等下一棵树产出后回看误报率。
## 2026-09-08 去 AIPPT 硬编码 + 机械覆盖最大化（分支 exp/plan-tab-rule，待验收合入）

动机：用户铁律「skill 不能有 hard code，换项目必须通用」。AntennaPod / AIImage 实测：contract 的 tab
判定写死 AIPPT 的 HomeActivity 文案表，抽屉页全判 host_default；wizard 步序写死 Init/Difficulty/Status；
reach_path 宿主推断写死 Guide/Home/Mine/Works → *Activity 与 "Activitiy" 拼法；LLM 阶段不跑时树对
下游零边（planner 全孤儿）。

- `compute_navigation_contract.py`：删 `TAB_TYPICAL_LABELS_ZH` 与 Sub/Doc/Tab/LongTxt/Examples/List 后缀
  表；Fragment 的 tab/sub_tab/wizard_step 只采信树证据（宿主 wizard_steps → 宿主入边 attach_kind 且
  非 kind_uncertain），其余 host_default + contract_uncertain；`_heuristic_wizard_index` 改读入边
  wizard_index（源码 fragmentList 顺序），字母序兜底；宿主已有 wizard_steps 时不再按 setCurrentItem
  把所有子页判成 wizard。
- `compute_reach_paths.py`：`infer_host_page` 改通用命名 + 1 编辑距离，零 app 名。
- 新增 `synthesize_candidate_edges.py`（Phase 2.4）+ `tree_generic.py`（与 toolkit-fact-indexer 同源副本）：
  宿主归属 / 宿主边 / 弹窗边（每个实例化宿主一条）/ Activity 打开边 / 非页面类一跳归属 /
  机械候选 inbound_triggers（点击上下文 → 函数调用点一跳 → layout/menu XML 文案，覆盖额外 res 根）。
- 新增 `tree_coverage_report.py` 记分卡（E0/E1/E2/E3/K1/D + LLM 待补清单，`--gate`）；
  `preflight_check.sh` 末尾打印；`run_all_phases.sh` 接入 Phase 2.4。
- 实测（纯机械，无 LLM 阶段；AIPPT 830 intermediate + AIPPT_mock 源码 / AntennaPod 0806 intermediate +
  AntennaPod-develop 源码）：inbound_triggers 0→111 / 0→186；E1 0%→72% / 0%→73%；E3 0%→100% / 0%→100%；
  K1 75%→100%（AIPPT）；planner 目标 22 全孤儿 → 36 目标 gap 0（AIPPT，剩 4 页为死码）/ 54 全孤儿 →
  61 目标 gap 0（AntennaPod）。E2（文案）机械上限 42% / 13%，其余是 LLM 阶段的活。
- 回归：LLM 阶段跑过的 AIPPT 830 树记分卡 E1 100% / E2 93%，本次改动不动它；AIPPT_0906 树暴露 D=19
  （有入边却判死）——记分卡抓到的真缺陷。

## 2026-09-08（下午）LLM 阶段接线审计后的修正（已落本地 + ~/.claude）

- SKILL.md Phase 2.5 新增「机械候选已落成 inbound_triggers，LLM 的活是核实与升级」六条规则（待办=记分卡 llm_todo；
  原地升级不重复；死码标 disproven 不删；静态 id 需确认可点；字符串资源要追到 strings.xml；完成判据边级）。
- `preflight_check.sh` 新增 Phase 2.5b：待核实候选（candidate=true 且文案占位）> 0 或记分卡 E2 < 90% → 未完成。
- `synthesize_candidate_edges.py` 合成的 navigation.inbound 边带 `nav_edge_seed: true`（进 LLM 候选面）。
- 新增 `llm_phase_guard.py`（snapshot / verify）：受保护字段、候选不消失、同起点不重复、kind 白名单、
  relationship_kind 枚举——LLM phase 前后必跑；`_tests/test_llm_phase_guard.py` 3 例。
- SKILL.md Phase 3 启发式去 app 名；Phase 4 层级表 "Core AI" → "Core"，去 PPT 领域例子。
- 审计遗留未做：2.6 契约 LLM 输入未带机械证据（attach_kind/pager 顺序/点击映射）、2.7 仍依赖 page_*.md、
  各 LLM phase 无 _phase_markers、记录/边输出顺序不确定。

## 2026-09-08（傍晚）机械精度修正（AIPPT 全流程实测 47 条机械文案错 17 条之后）

以 LLM 核实过的树为基准建精度账（`~/.agents/exp/aippt_tree_0908_analysis/precision.py`）：
- 修前：文案 19 对 / 12 错、控件 id 28 对 / 15 错；修后：**文案 29 对 / 4 错、控件 id 32 对 / 7 错**。
  剩下 4 条文案分歧全是"同一起点有两个真触发到同一落点"（登录态分支 / 取消订阅与申请退款 / 两份协议），
  是"一起点一条目"的建模上限，不是判错。
- `tree_generic.py`：点击上下文改**按代码块归属 + 函数作用域截止**（不再"最近上方"）；when 多控件分支取
  第一个；adapter/holder/itemClick 上下文放弃猜控件；ClickableSpan 模式限定含 Span/click 的行；容器 id 改
  分词判定（`tv_privacy_content` 不再被当容器）；同名 id 跨 layout 只认起点页自己的 layout（起点 layout 由
  layout_file / R.layout / XxxBinding 推），歧义宁缺；文案属性扩到 `*text/*title/*label/*hint`（含
  `app:bar_leftText`）；一跳归属按 helper **函数名**找调用行、跳过 import/package；新增
  `reattribute_static_entries`（Companion/static 入口归到调用页）；起点必须是 UI 类型记录。
- `synthesize_candidate_edges.py`：清掉起点已被 1.5 删掉/非页面类型的候选；接 static 入口归属。
- `compute_reach_paths.py`：证伪边不建链。
- `tree_coverage_report.py`：E2 分母剔 disproven 与结构自动边（lifecycle_modal / host_default / activity_root /
  auto|observer|host_attach|viewpager_wizard），另报 E2_raw；`live_in`/D 认 disproven；容器判定同上。
- SKILL.md：自检"from_page 可达"豁免 disproven；relationship_kind 口径统一（Fragment/Dialog 6 类 + Activity 3 类 +
  blackbox_discovered/callback）。
- 实测：AIPPT E2 42%（诚实口径）；AntennaPod E2 7%（抽屉/菜单文案全是 LLM 的活）。

## 2026-09-08（晚）机械层只产可核实事实，消费策略交 LLM（用户拍板：「机械脚本只做自己的工作，后续怎么消费交给 LLM」）
- 候选条目唯一键 `from_page` → **`(from_page, trigger_view_id | evidence_line)`**：同起点多个真触发各一条（tab 与菜单项
  都进同一页就是两条）；承载类边（attach_kind ∈ tab/sub_tab/wizard_step/host_default，或 FragmentTransaction /
  hosts fragment）一宿主一条；同起点同证据行视为同一实例化点（1.6 popup 重扫把 `hosts fragment` 改成 `dialog_show`
  不再长出重复条目）。树里已有的非机械条目（同证据行或同控件）不再造候选。
- 标记字段收进 **`provenance{status, rule, label_from, attach_kind, kind_uncertain, host_source, attach_kind_hint}`**，
  扁平层只留事实（from_page / trigger_* / evidence_* / source）与既有的 disproven / notes / runtime；
  `status` 由 LLM 升级为 confirmed | corrected（原值留 `provenance.mechanical_value`）| disproven。
  guard / scorecard / synthesize / preflight / 精度账兼容旧式扁平 `candidate: true`。
- `llm_phase_guard.py`：重复判定改同键 `(from_page, view_id|evidence_line)`；候选存在性按同起点 + 同证据行/同控件/已升级；
  新增 `is_candidate`。
- `preflight_check.sh` 2.5b 改为**只报数**（未核实且无文案候选数 + E2），不再计 INCOMPLETE——E2 可达上限因项目而异，
  阈值由 LLM 阶段按项目在报告里给，`tree_coverage_report.py --min-e2` 承接。
- SKILL.md Phase 2.5 重写为「字段语义 + 不可违反的约束（原地升级/证伪不删、同键不重复、事实字段不改、文案走资源）+
  可用测量（记分卡 / guard / preflight 报数）」；核实范围、抽样、完成口径由 LLM 自定并写进 Phase 报告；删掉
  "待办=llm_todo 不要全树重扫" 与固定 E2≥90%。
- 新增 `_dev/precision_ledger.py`：开发用精度账（机械候选 vs 已核实树，按 vid → 证据行 → 起点唯一 对照），不在运行链路。
- 回归（AIPPT_830_test+AIPPT_mock / ant_arkts_0806+AntennaPod-develop，与改前 ~/.claude 旧副本同机同源对照）：
  候选 103 / 195、E1 28/39 · 59/81、E2 42/101 · 8/121、E3 5/5 · 45/45、K1 6/6 · 3/4、精度（AIPPT vs LLM 核实树）
  文案 29 对/4 错、控件 32 对/7 错、计划器 可执行1+投机31+缺口5+孤儿1 / 1+59+0+1——**逐项相同**，本次只改表示与契约；
  guard 自校验两树 PASS；测试 indexer 13 / guard 4 / vv 15+19 全绿。AntennaPod K1 3/4 在改前副本上就是 3/4（非本次引入）。

## 2026-09-08（夜）试点核定后落地：机械事实 M1~M3 + LLM 语义契约 L1 + 消费侧（用户拍板「先落地，不急着跑全树」）
- 目标口径改为**「每个可走页在树里有一条计划器可直接执行的路径」**（可执行页 / 可走页），不用 GT；E2 降为参考。
- `tree_generic.py`（与 indexer 同源）新增：`scan_manifests` / `SourceCorpus`（全仓一次读入 + 标识符倒排）/
  `compute_walkability`（abstract · manifest exported/intent-filter/alias · 去注释去 import 的活引用计数，落在死类文件里的引用不算，
  两遍传递；launcher 与 manifest 外部入口永远是活根；LLM 已判定的不覆盖）/ `layout_facts`（静态文案区分 `tools:` 占位、
  textColorHint 之类不算、还原 `\n`、@string 扫全部 `*res*/values*`、同名 layout 变体全列 + 启发式选择、根元素 id 不降级取子节点）/
  `enrich_layout_facts`（layout_file 仅缺失时回填、与源码 R.layout 不一致只留 `layout_file_conflict`；宿主并上被承载子页的
  `hosted_texts`）/ `list_item_roots` / `span_sites`（含宿主 TextView id）/ `runtime_text_writes`（多行语句拼完整）/
  候选证据行标记 `in_comment` · `dead_branch` · `companion_scope` · `from_dead_file` · `evidence_line_guess`。
  合并键含 `span_text`。**M5 机制先验不做**（试点一致率 56%）。
- `synthesize_candidate_edges.py`：2.4 幂等调用 `compute_walkability` + `enrich_layout_facts`（1.6 新增的弹窗也有事实）。
- `llm_phase_guard.py`：唯一键 `(from_page, view_id|evidence_line, span_text)`；`trigger_kind` / `walkability.status` 枚举；
  disproven 须有 `disproven_reason|notes|trigger_kind_evidence`。
- `tree_coverage_report.py`：分母剔 walkability 非 walkable；`structural_auto` / `actionable` 优先读 `trigger_kind`
  （list_item 根 id、span 子串算可执行）。
- SKILL.md Phase 2.5：record 级机械事实说明 + 语义契约（`trigger_kind` 六类与附加字段、`trigger_owner_page`、
  `edge_preconditions`、`disproven_reason`、evidence_line 条目级可纠、唯一键含 span_text）；Phase 2.6：verify_signal
  三形态（text_contains / view_id / ordinal_in_wizard）+ `from_trigger` 必须指向 2.5 条目 + 非 walkable 按分类不挂 uncertain。
- 回归：AIPPT 机械树精度不变（29对4错 / 32对7错）；walkability 52/13/5/3；AntennaPod 110/10/6/3（全链 61s）；
  试点树（有语义字段）用落地后的计划器 = 切片 22 可走页 16 可执行（与 v5 模拟一致），不可走不再进目标；guard PASS；
  测试 indexer 17 / guard 5 / vv 17+19 全绿，两侧字节一致。

## 2026-09-08（深夜）「有效益的都做」：M4 + 六项机械杠杆 + L4~L6 规约清理
- **M4 前置态精度** `tree_generic.scan_preconditions`：只在去注释源码上匹配；剔 `if (false && …)` 死分支（只认包住证据行的块）、
  本类 helper 定义行（含单行 companion）、import/class 声明行、弹窗类名裸命中（要有调用）、本类自指；每条带
  `provenance{status: candidate, rule, enclosing_function, at_entry, condition}`；`intent_extras`（companion 写参 / 页面读参 /
  缺参 finish 守卫）→ `param_required` 候选。AIPPT 19→14 条，试点证伪的 10 条里 6 条不再产生，其余 4 条标 `at_entry=false`。
- **六项机械杠杆**（`tree_generic.py`，indexer 与 2.4 同源）：
  ① `node_completeness`（manifest 声明 / 继承 Fragment·Dialog·Activity 但不在树；抽象类单列；嵌套类 `A$B` 归一）→ `stats.node_completeness`，
     记分卡与 preflight 打印；② `layout_facts.discriminators`（全树唯一的文案 / view id，到达判据预算）；
  ③ `click_context_view_ids` 同分支多控件各出一条候选（`rule: click_context_sibling`）；④ `provenance.kind_hint` 只对结构确定的两类预填：
     span（证据行 4 行内的 replaceSpan 站点 → `span_text` + 宿主 id）、list_item（adapter 块内 → 唯一 item 根 id + `label_dynamic`）；
  ⑤ `wizard_exit_controls`（子页点击块里调 setCurrentItem/next*/goNext 的控件 + 子页 layout 文案）→ `compute_navigation_contract`
     的 `exit_action_to_next` 不再硬编码「下一步」（AIPPT 实测 Difficulty 步真值「是/否」、Details「跳过/继续」），抽不到标 `exit_unresolved`；
  ⑥ manifest 深链（VIEW + data，`${applicationId}`/manifestPlaceholders 只认 gradle 静态字面量，解不出标 `unresolved_placeholders`）。
- **L4~L6** SKILL：Phase 2.7 改「先裁决机械候选（读 provenance.at_entry / condition）→ 从 page_md 补缺（本代 a2h-spec 的语义源是
  「功能检查锚点」，换项目先看章节名）→ 边级 edge_preconditions」；自检三条限定/豁免（reach_path 与 ≥1 入边只对 walkable、wizard 末步
  豁免）；编排（2/4 与 2.5 并行、2.5 按文件切 batch 主会话收口）与 `_phase_markers` 约定；preflight 缺口只算 walkable、认 list_item/span/auto、
  删 ARouter 预设、加可走性/完备性信息行。
- 回归：AIPPT 候选 103→111（+8 同分支兄弟条目），精度账对旧「一起点一条」基准显示的新增不一致全部是兄弟条目（MineFragment 五控件同去向，
  皆为真触发），原有 4/7 不变；walkability 52/13/5/3；deeplink：PushDetailActivity 占位符未解析留账；AntennaPod 67s，
  深链 OnlineFeedViewActivity 可达；测试 indexer 21 / guard 5 / vv 18+19 全绿，两侧字节一致。
