# toolkit-fact-indexer CHANGELOG

## 2026-09-08 去 AIPPT 硬编码 + 机械覆盖最大化（分支 exp/plan-tab-rule，待验收合入）

- 新增 `scripts/tree_generic.py`（零 app 常量判据库）+ `scripts/_tests/test_tree_generic.py`（7 例）。
- `toolkit_to_fact_tree_draft.py`：
  - `_PRECONDITION_PATTERNS` → 语义族正则 + `spec/tree_hints.json` 追加；evidence 带命中文本。
  - ViewPager 子页 kind → `classify_pager_kind`（结构信号），`wizard_steps[].kind_uncertain`；
    入边带 `attach_kind/kind_uncertain`；layout 查找改 module 相对 + 额外 res 根。
  - 宿主归属 `_heuristic_fragment_host` → toolkit fragments.json / 源码实例化点 / 通用命名 / 主容器猜测，
    记 `parent_in_nav_source`；全仓零引用 → `dead_code_hint`。
  - 新增 `enhance_host_edges`（宿主→子页 / 宿主→弹窗边 + outbound 镜像）与
    `synthesize_inbound_triggers`（机械候选 inbound_triggers，幂等）；stats.enhancers 记
    `host_edges_added` / `mechanical_inbound_triggers`。
- 实测见 app-relationship-tree/CHANGELOG.md 同日条目。

## 2026-09-08（下午）
- `enhance_host_edges` / viewpager enhancer 合成的 navigation.inbound 边带 `nav_edge_seed: true`，
  使 app-relationship-tree Phase 2.5 的候选消费面覆盖宿主边 / 弹窗边 / pager 边。

## 2026-09-08（傍晚）
- `tree_generic.py` 与 app-relationship-tree 同源升级（点击上下文按块归属、函数作用域截止、多控件分支取首、
  adapter 上下文放弃、容器 id 分词判定、layout 限定与歧义宁缺、文案属性扩展、helper 函数名一跳、静态入口归属、
  UI 类型起点）。精度账见 app-relationship-tree/CHANGELOG.md 同日条目。

## 2026-09-08（晚）
- `tree_generic.synthesize_inbound_triggers`：合并键改 `(from_page, trigger_view_id|evidence_line)`（承载边一宿主一条），
  标记字段收进 `provenance` 子对象，识别树内已有非机械条目不再重复造候选；与 app-relationship-tree 同源副本一致，
  细节与回归数据见其 CHANGELOG 同日「晚」条目。

## 2026-09-08（夜）
- `toolkit_to_fact_tree_draft.py` 在合成候选前调用 `compute_walkability` 与 `enrich_layout_facts`（record 级 `walkability` /
  `layout_facts` / `list_item_roots` / `span_sites` / `runtime_text_writes`，layout_file 缺失回填、冲突留痕）；
  `tree_generic.py` 细节与回归见 app-relationship-tree/CHANGELOG.md 同日「夜」条目。文案正则不再吃 textColorHint / tools:。

## 2026-09-08（深夜）
- `enhance_with_preconditions` 改调 `tree_generic.scan_preconditions`（M4：去注释 / 死分支 / 定义行 / 裸类名 / 自指全剔，带 provenance；
  intent 读参守卫 → param_required）；draft 阶段调 `node_completeness` 入 stats；候选合成加同分支兄弟条目与 span/list_item kind_hint。
  细节见 app-relationship-tree/CHANGELOG.md 同日「深夜」条目。
