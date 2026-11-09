---
name: app-relationship-tree
description: 在 `toolkit-fact-indexer` 已产出的 `spec/toolkit-fact-tree.json` 上做**多源补全**——把 Android 源码、a2h-spec 的 `spec/baseline/ui/page_*.md` / `feature-index.md`、android-ui-graph-builder 产物等作为 toolkit 产物的补充，把 toolkit 漏掉 / 不准 / 不全的字段都补上，包括：补 purpose、补 inbound_triggers 触发链、补 preconditions 业务前置态、补 dependency_graph 架构分层、补 reach_paths 孤儿。**必要时甚至可以新增 node**（toolkit 没识别但 spec / 源码明确描述的页面或弹窗）。**原地修改 fact-tree.json，不产新文件**。当用户说"补充 fact-tree"、"补 description"、"补 purpose"、"完整化关系树"、"app-relationship-tree"、"丰富 toolkit 产物"、"产 dependency_graph"、"补导航链"、"补登录态"、"补前置条件"时触发。
metadata:
  type: domain
  tags:
  - analysis
  - enrichment
  - fact-tree
---
> **路径约定**：下文 `$SKILLS_ROOT` = 本套 skills 的安装根目录。执行任何脚本前先设一次：`SKILLS_ROOT="$(cd "$(dirname 本SKILL.md)/.." && pwd)"`（用户级安装=`~/.agents/skills`；项目级=`<project>/.agents/skills` 或 `<project>/skills`）。

# app-relationship-tree — toolkit-fact-tree 多源补全器（v6.3）

## 1. 定位（v6.3 重定位 — 2026-05）

**核心使命**：**完善 toolkit-fact-indexer 产出的 fact-tree**。toolkit 是确定性脚本，受限于"只能从 toolkit 的 12 个 JSON 抽事实"——任何 toolkit 没追到 / 没识别 / 没语义化的内容都是本 skill 的补全对象。

**补全的 4 种基本动作**：

| 动作 | 例子 | 用什么数据源 |
|---|---|---|
| **(a) 补字段** | toolkit 给的 record 有 `purpose=null` / `inbound=[]` / 缺 `preconditions[]` | 源码 + page_*.md + LLM 推断 |
| **(b) 校正字段** | toolkit 错误填值（fq_class 错包、自循环 inbound 等） | 源码反查正确值 + 启发式 |
| **(c) 新增节点** | toolkit 没识别的 page / dialog / fragment，但 spec / 源码明确描述 | 扫 a2h-spec `page_*.md` 找 toolkit 缺失的 record 名，按真实 source file 创建 record |
| **(d) 删除节点** | toolkit 误识别（`_promoted_page_*` 这种合成 ID 不对应真实 Activity） | grep AndroidManifest 验证；不在 manifest 的 promoted Activity 删 |

| 这个 skill | 做 | 不做 |
|---|---|---|
| 输入 | `spec/toolkit-fact-tree.json`（必须先跑 toolkit-fact-indexer）+ Android 源码根 + `spec/baseline/ui/page_*.md`（如有）| — |
| 输出 | **原地修改** `spec/toolkit-fact-tree.json` | 产新 JSON 文件 |
| LLM 补 `purpose` | ✅（page / fragment / dialog / component 全级别） | — |
| LLM 补 `inbound_triggers` 导航触发链 | ✅ 读源码反查 `startActivity(B)` 调用点 → 抽 onClick / button label / view id | — |
| LLM 补 `preconditions` 业务前置态 | ✅（toolkit-fact-indexer enhancer 已经补部分，本 skill 用 spec 校验 + 扩充：免费次数 / VIP 等级 / 必填参数等）| — |
| LLM 推 `dependency_graph.layers` | ✅（feature → 架构层级映射） | — |
| 启发式补 `reach_paths` 孤儿 | 🟡 可选 | — |
| **新增 node**（page/fragment/dialog） | ✅ 扫 a2h-spec page_*.md / 源码命名，发现 toolkit 漏识的 record | — |
| **删除假节点**（toolkit 误识别） | ✅ 用 AndroidManifest 校验 Activity 真实性，剔除 `_promoted_*` 等不对应真实类的 record | — |
| 校正 fq_class 错包路径 | ✅ 反查源码 `package xxx` 行确定真实包路径 | — |
| 改 toolkit 真正的事实字段（toolkit 已正确给出的，不能瞎改） | — | ❌ **铁律：toolkit 给的对的不能改** |
| 重新算 reach_paths 全图 / 重新建 nav graph | — | ❌ 已由 fact-indexer 完成；本 skill 只补漏不重算 |
| 产 `spec/app-relationship-tree.json` | — | ❌ **v6 删除该文件**，下游直接读 fact-tree |

> **核心原则（v6.3 落地）**：toolkit 产物是基础，本 skill 利用源码 + spec 把任何缺失 / 错误 / 不完整都补全。**fact-tree 的最终质量由本 skill 负责**——下游读到的版本是经过本 skill 校准的。

> **删除的旧 v6 误解**：早期 SKILL 把本 skill 限定为"只补 purpose"。这个限定 v6.3 已经撤销。

## 1.1 为什么要补 inbound_triggers（v6.2 关键变化）

toolkit 的 `navigation_graph.json` 在反射 / 间接 startActivity / FragmentTransaction 等场景下追不到边，导致 `inbound = []` 的 record 在 AIPPT 里高达 44 / 57。下游 visual-verify Phase Alpha 没办法做"点击优先、指令兜底"的 BFS——因为不知道**从哪个屏点哪个按钮**能到达本 record。

`am start` 直跳虽能拉起 Activity，但会**跳过 button 链路的验证**——HMOS 端那个按钮根本可能没接逻辑，visual-verify 却拿不出差异。

所以 app-relationship-tree 必须读源码反查触发链，填到一个新字段 `inbound_triggers[]`：

```jsonc
"AccountInfoActivity": {
  ...
  "inbound_triggers": [
    {
      "from_page": "MineFragment",
      "trigger_method": "onAccountClick",      // 调用栈源头方法
      "trigger_view_id": "tv_account_entry",   // 触发它的 View id（layout xml）
      "trigger_label": "账号信息",              // 该 View 的 text/content-desc
      "evidence_file": "MineFragment.kt",
      "evidence_line": 142,
      "source": "llm_source_read"
    }
  ]
}
```

下游 visual-verify 拿到 `inbound_triggers[0]` 就能在 host 屏上找"账号信息"clickable 节点点击。点不到再 fallback `am start`。

---

## 2. 执行流程（5 个 phase）

```
Phase 1:   探测 fact-tree                                       ~1s
    ↓
Phase 1.5: 节点级校准（v6.3 新增）                              ~30s
    ↓
Phase 1.6: 源码 popup 类正向扫描（v6.5 新增）                    ~1s
    ↓
Phase 1.7: 方法现场节点归位（2026-09-11 新增 — 确定性脚本）        ~1s
            scripts/fold_call_site_nodes.py --android-root <root> [--tree-feedback <json>]
            - `Outer$showXxx` 方法现场节点：读方法体判真身（纯复制→merge 进真弹窗节点并删；
              共享参数化弹窗的状态→保留、继承布局+调用点文案；解不出→uncertain）
            - 必须在 1.6 之后（目标类常由 1.6 补进树）；幂等
    ↓
Phase 2:   LLM 补 purpose                                       ~分钟级
    ↓
Phase 2.4: 机械候选边（2026-09-08 新增 — 确定性脚本，零 app 常量）  ~10s
            scripts/synthesize_candidate_edges.py --android-root <root> [--toolkit-out <dir>]
            - 宿主归属：toolkit fragments.json > 源码实例化点（X( / X.newInstance / X.show…）
              > 通用命名（含 1 编辑距离）；全仓零引用 → dead_code_hint，不猜宿主
            - 宿主→子页 host_attach 边 / 每个实例化宿主一条 dialog_show 边 / Activity 打开边
              （Intent(..X.class) / X::class.java / X.start…()）；非页面类里打开的一跳归属到引用它的页面
            - 机械候选 inbound_triggers（source=mechanical_candidate）：点击上下文直接 → 所在函数
              调用点一跳 → layout/menu XML 文案（覆盖 platform-res 等额外 res 根）
            - 幂等；LLM 阶段 2.5 只需核实 / 补占位文案，不再从零写边
    ↓
Phase 2.3: 多源 BFS reach_path（v6.3 复活 — 确定性脚本）         ~1s
            scripts/compute_reach_paths.py
            - 多源 BFS（launcher + 所有 page 当 entry）
            - outbound + inverse-inbound 取并集
            - 隐式 contains/shows_dialogs → 边
            - 名字启发式 + Tier 2 不动点迭代
            - 输出 reach_path = page-id + trigger token 交替序列
            - 标 truly_isolated（无源码调用方）
    ↓
Phase 2.5: LLM 补 inbound_triggers 导航触发链                   ~分钟级
    ↓
Phase 2.6: LLM 补 navigation_contract（v6.4 新增 — 根因解）     ~分钟级
            scripts/compute_navigation_contract.py
            - 给每个 Fragment / Dialog 输出精确 UI 导航合同
            - 字段：relationship_kind / trigger_action / verify_signal
                    / wizard_index / exit_action_to_next（仅 wizard）
            - 数据源：page_md + Android 源码（ViewPagerAdapter /
                     FragmentTransaction / DialogFragment.show）
            - 输出 + 确定性源码验证（不通过标 contract_uncertain）
            - 下游 visual-verify v3.9 按合同精确点击 + 强 verify_signal
            - 详见 §2.6
    ↓
Phase 2.7: LLM 扩充 preconditions 业务前置态（v6.3）            ~分钟级
    ↓
Phase 3 (可选): 启发式补 reach_paths 孤儿                        ~1s
    ↓
Phase 4:   LLM 推 dependency_graph.layers                       ~30s
    ↓
Phase 5:   自检 + 写回 fact-tree.json                            <1s
```

### Phase 1: 探测 fact-tree

```python
import json, sys
F = "spec/toolkit-fact-tree.json"
if not os.path.exists(F):
    print("❌ 缺 spec/toolkit-fact-tree.json，请先跑 toolkit-fact-indexer")
    sys.exit(2)
ft = json.load(open(F))
assert ft["$schema_version"] == 1
```

如果 fact-tree 不存在，**自动调起 toolkit-fact-indexer**（它内部处理"toolkit 产物是否存在"逻辑）。

### Phase 1.5: 节点级校准（v6.3 新增 — 重点）

**目的**：toolkit 产出有 3 类节点级别问题，必须先清洗才能保证后续 phase 工作的语义是干净的：

| 问题 | 怎么发现 | 怎么处置 |
|---|---|---|
| **假 Activity**（`_promoted_*` 等合成 ID 不对应真实 class） | grep AndroidManifest，看 record.id / record.fq_class 是否在 `<activity>` 节点里 | 删除该 record；同时清掉其它 record 中指向它的 inbound/outbound 边 |
| **fq_class 错包路径**（如 `cn.sanfate...page.X` 实际类在 `cn.sanfate...dialog.X`）| 在 source 里 grep `class XClassName` 得到真实文件路径，反推真实 package | 把 `fq_class` 改为正确 FQ；同时 `android_file` 也改 |
| **toolkit 漏识的节点** | 扫 `spec/baseline/ui/page_*.md` 的标题/章节，匹配 fact-tree 没有的 record id；或扫源码 `class .*Activity\|class .*Fragment\|class .*Dialog : ` 找 toolkit 漏的 | 新增 record：从源码 + page_*.md 抽 id / type / fq_class / android_file / purpose 模板字段；标 `source: "app_relationship_tree_added"` |

```pseudocode
# 1. 假 Activity 校验
manifest_activities = read_AndroidManifest("AndroidManifest.xml")
for r in fact_tree.pages[:]:
  if r.type == "Activity" and r.id.startswith("_promoted_"):
    # 用 fact-tree 里另一条同样 source-file 的真 record 兜底
    real = find_other_record_by_android_file(r.android_file)
    if real:
      merge_edges(real, r)  # 把 r 的 inbound/outbound 转给 real
      fact_tree.pages.remove(r)

# 2. fq_class 错包校正
for r in records:
  if r.fq_class and "." in r.fq_class:
    if not source_file_has_package(r.android_file, r.fq_class.rsplit(".",1)[0]):
      # 不匹配，反查真实 package
      real_pkg = grep_package_in_source(r.android_file)
      r.fq_class = real_pkg + "." + r.id

# 3. 漏识节点补充
spec_records = scan_page_md_titles("spec/baseline/ui/page_*.md")
for spec_id in spec_records:
  if spec_id not in [r.id for r in records]:
    # 扫源码找 class
    src = grep_class_definition(spec_id)
    if src:
      records.append({
        "id": spec_id,
        "type": classify_type(src),
        "fq_class": extract_fq(src),
        "android_file": src.file,
        "source": "app_relationship_tree_added",
        ...
      })
```

**重要约束**：只删 / 改 / 加节点本身的 metadata，不要改 toolkit 已正确填的字段（components / behaviors / source_anchor 等）。被删除的 record 如果有 inbound/outbound 引用，要 merge 到等价的真 record 上（按 android_file 同一性）。

### Phase 1.6: 源码 popup 类正向扫描（v6.5 新增）

**目的**：补 Phase 1.5 "page_*.md 反查" 的鸡生蛋盲区。Phase 1.5 line 154-168 的反向逻辑要求"spec 里已有 page_md → 才补 fact-tree"——如果 toolkit 没识别 → fact-tree 没记录 → a2h-spec 没生成 page_*.md → 永远触发不了。本 phase 改成**正向独立扫描**：源码有但 fact-tree 没有，**直接**补，不依赖 spec。

**实现**：脚本 `scripts/scan_popup_classes.py`，~1 秒跑完。

**扫描规则**：

1. `rg --files` 列所有 `(DialogFragment|BottomSheetDialogFragment|BottomSheetDialog|BottomDialog|Dialog|Popup|Window|Sheet).(kt|java)$` 候选文件
2. 路径过滤：排除 `src/test/`、`src/androidTest/`、`build/`、`generated/`、`xpopup/core/` 等
3. 文件名排除：XPopup 库自身（`BasePopupView` 等）+ 业务侧 Base 抽象基类（`BaseDialog`、`BaseDialogFragment`、`CenterBottomFragmentDialog`、`BaseBottomFragmentDialog` 等）
4. 对每个候选文件抽 `class Name [(...)] : Parent(...)` 子句（含 Kotlin 主构造器括号平衡处理）
5. **继承链传递闭包**：扫所有 .kt/.java（不止候选文件）建 `child→parent` 全图 → 闭包传递。`ColorPickerDialog → BubbleDialog → DialogBase` 能跨文件追到根
6. **白名单匹配**：祖先链中只要有以下任一即入选：
   - Dialog 系：`Dialog` / `AlertDialog` / `AppCompatDialog` / `DialogFragment` / `AppCompatDialogFragment` / `BottomSheetDialog` / `BottomSheetDialogFragment` / `DialogBase`
   - XPopup 系：`BasePopupView` / `AttachPopupView` / `CenterPopupView` / `BottomPopupView` / `FullScreenPopupView` / `DrawerPopupView` / `ConfirmPopupView` / `ImageViewerPopupView` / `PartShadowPopupView` / `PositionPopupView` / `HorizontalAttachPopupView` / `BubbleAttachPopupView`
   - 原生：`PopupWindow`
7. **命名兜底（uncertain=true）**：白名单未命中、但类名以 `Dialog/Popup/Window/Sheet/BottomDialog` 结尾 **且** 文件路径包含 `/dialog/`、`/popup/`、`/popwindow/`、`/bottomsheet/`、`/sheet/`、`/widget/`、`/view/` 之一 → 入选
8. **去重**：与已有 `pages + fragments + dialogs` 的 id 比对，已存在则跳过
9. **layout 检测**：`setContentView(R.layout.x)` / `LayoutInflater.inflate(R.layout.x)` / XPopup `getImplLayoutId()` 返回 `R.layout.x`
10. **construction_mode**：layout 命中 → `"layout_xml"`，否则 `"code_only"`

**新增字段**：
- `source: "app_relationship_tree_added_class_scan"`（区别于 Phase 1.5 的 `app_relationship_tree_added`）
- `construction_mode: "layout_xml" | "code_only"`（下游 a2h-spec Phase B 按此分支选页面结构模板）
- `uncertain: true`（仅命名兜底入选时）

**与 Phase 1.5 + fact-indexer 的互补关系**：

| 机制 | 覆盖场景 | 落地层 |
|---|---|---|
| fact-indexer 主链 | toolkit JSON 已识别的 page/fragment/dialog | fact-indexer |
| fact-indexer v1.3 popup-layout-prefix promotion | layout 文件名带 `dialog_/popup_/pop_` 前缀（与类名无关） | fact-indexer |
| Phase 1.5 反向 page_md 扫描 | spec 已写 page_md 但 fact-tree 漏的 | app-relationship-tree |
| **Phase 1.6 正向类名扫描（本 phase）** | **源码有 popup 类但 fact-tree 和 spec 都没有的** | **app-relationship-tree** |

三层互补，可同时命中同一 popup（按 id 去重），无重复。**Phase 1.6 是补漏的最后一道兜底，必须跑。**

**已知漏识**（留给后续 LLM phase 兜底）：
- XPopup 匿名子类：`new XPopup.Builder().asCustom(object : CenterPopupView{...})` —— 无独立类名
- factory 工厂构造：无独立 `*Dialog/*Popup` 类，靠运行时 `DialogFactory.create(type)`
- 命名不含 Dialog/Popup/Window/Sheet 后缀的（如 `ColorPicker`、`FontSettings`）

**自检（写入 stats.enhancers.app_relationship_tree_class_scan）**：
```json
{
  "candidates_total": 108,
  "added": 65,
  "skipped_existing": 43,
  "by_match": {"whitelist": 64, "naming_fallback": 1},
  "by_construction": {"layout_xml": 29, "code_only": 36}
}
```

### Phase 1.7: 方法现场节点归位（2026-09-11 新增 — 确定性脚本，零 app 常量）

**病**（AIPPT 0910r3 树实测 8/30 个 dialog 节点）：节点 id 里的 `$` 被两套代码赋了两种意思——JVM 的 `Outer$Inner`（真内部类）
和 toolkit 的 `SplashActivity$showPrivacyDialog`（**方法现场**，不是类）。方法现场被当成独立的屏入树，于是同一个弹窗有两个节点：
类节点（有布局事实）+ 影子节点（`layout_file=None`、无文案）。下游代价已付过三次：安卓遍历给影子节点一条「已消费不可再现」归因
自洽地盖住；鸿蒙回放按它排放行步、零介入两趟卡死第 5 步；判读把"两道门鸿蒙一道"当成发现（错的，源码只有一道）。
反哺契约不许删节点、`tree_dup` 只查边——**没有回路送回树侧**，所以在树侧根治。

**实现**：`scripts/fold_call_site_nodes.py <tree> --android-root <root> [--dry-run] [--report <json>] [--tree-feedback <json>]`，~1s。

**判据**（全部机械；只看源码与树字段，不看名字像不像；通用性复审后定稿 2026-09-11）：
命中 = id 含 `$` **且** `$` 后缀在外层类源文件里是方法声明（`fun <后缀>(` / Java `<type> <后缀>(...) {`；
是 `class <后缀>` 就是真内部类，不碰）。声明必须在行首、`)` 后紧跟 `{`/`=`/`: 返回类型`——换行后的**调用**不算（真树踩过）。
注释先抹掉再读方法体。
- **真身候选**：方法体里的类引用 `X(` / `X.xxx(`（**不设工厂名清单**：newInstance/Builder/open… 换项目必漏），
  再与树里的**弹窗记录**取交集——`XActivity.start(ctx)` 这类页面类调用不成目标（否则影子会并进 Activity）。
- **布局三向比较**（布局**不是**"真面"判据——915 版 toolkit 给方法现场挂的是宿主 Activity 的布局）：
  等于宿主布局 → 视同无布局；等于真身布局 → 照常；第三个布局且有真身 → `layout_conflict` 标 uncertain；
  有自己布局却无弹窗真身 → `code_built_dialog_own_layout`（AlertDialog.Builder + 自定义 view），原样留、不标 uncertain。
- **文案判据**（决定"纯复制"还是"状态"）只认**流入实例**的文案：构造/工厂实参；`val d = X()` 后的 `d.setTitle("…")` /
  `d.title = "…"`；`X().apply { title = "…" }` 块里的**顶层赋值与裸调用**。嵌套 lambda 与对别的接收者的调用
  （`EventUpload.track("vippop_3")`）里的字面量**不算**——真树实测埋点事件名就是这样混进来的。

| 结论 | 处置 |
|---|---|
| 真身有布局/文案，无文案流入 → **纯复制** | navigation / inbound_triggers / reach_paths / screenshots / functional_checks / 黑盒账全部 merge 进真身（复用 1.5 的 `merge_edges`），真身记 `call_sites[]`，删影子；全树引用（features / flow_graph / contains / shows_dialogs / reach_path / from_page…）改指真身并去重。auto 触发按 `(from_page,"auto")` 去重，补空**只补** wait_hint/证据类字段，绝不补控件身份（A/B 实跑抓出放行键 rid 被灌进 auto 触发） |
| 有文案流入 → **共享参数化弹窗的一个状态** | 不删：`variant_of=X`、`construction_mode=shared_dialog_state`、`call_site{file,line,method,from_page}`、`call_site_texts[]`；`layout_file`/`view_ids` 继承真身（空或等于宿主布局时覆盖）。**不填 `parent_in_nav`**（2.4 会据它补一条无控件 dialog_show 裸边，与真触发边构成"一站点两目标"噪音）。2.4 重算 layout_facts 会冲掉文案 → `tree_generic.merge_call_site_texts` 在重算后并回 `static_texts`，状态节点才有独有判别词 |
| `system_ui` / 类不在树 / 多候选 / 解不出 / `layout_conflict` | 保留、`uncertain=true` + `call_site_resolution{kind,…}`，留给 1.6 类扫描或人复核 |
| 影子 `walkability.status=dead`（调用点已注释） | 只删不 merge 边，`call_sites[]` 记 `dead:true`。★只认 walkability 的死判定，`dead_code_hint` 在合成节点上是通用提示串，不算 |

**为什么排在 1.6 之后**：目标类（如共享提示弹窗）常由 1.6 类扫描补进树，1.5 之前跑会整批落到"不在树里"。

**实跑**：0910r3 树 dialogs 30→26（纯复制 4：2 合并 + 2 死删；状态 4；容器/默认子页、设计同构向导页一个没合）；同一 app 另两版
toolkit 树（22 个 `$` 节点的旧树 / 915 树）分类完全一致（4/4），915 树的真内部类 `VideoPlayActivity$Landscape/Portrait` 与旧树 14 个
`$1` 匿名类原样不动；AntennaPod / DiceRoller 树无 `$` 节点 → no-op。**整链 A/B**（`run_all_phases.sh` 带/不带 1.7 同树对比）：
A 比 B 恰好少 2 条触发（被折叠的两条）、零新增边、guard_flags 零新增，B 里"`tv_success_operate` 一站点两目标"标记在 A 消失（它标的正是重复）。

**与 arkts-visual-verify 的回路**：`walk_finalize.py` 收尾产 `edgewalk/tree_feedback.json`（只报不删：影子节点 / 同屏对 / 同控件集），
`--tree-feedback` 读它给未解节点附 `walk_feedback` 注记；归位本身不依赖它。

### Phase 2: LLM 补 purpose（主任务）

> **铁律**：
> - LLM **只能填** `purpose` / `label`（兜底）/ `action` / `visible_when` / `items[].purpose` / `notes`
> - LLM **禁止改** navigation 边、source_anchor、id、type、parent_id、文件路径、flow_graph、features、stats、reach_paths
> - 改了 toolkit 事实字段 → 视为污染，重做

**遍历策略**：

```
读 spec/.cache/fact-tree/source-index.json (toolkit-fact-indexer 已产) 拿锚点

FOR EACH record IN pages + fragments + dialogs:
  IF record.purpose is null:
    优先级 1: 找 spec/baseline/ui/page_{record.id}.md 的 ## page structure 段，直接抄
    优先级 2: Read 源码片段（source_anchor.line ± 20 行）；缺锚点则 Read layout 前 60 行
    优先级 3: 启发式 fallback（从 id + label + type 推一句）
    立即落盘 fact-tree.json（断点续跑安全）

  FOR EACH component IN record.components:
    IF component.purpose is null:
      优先级 1: 同上，从 page_spec 找
      优先级 2: Read component.source_anchor 锚点 ±30 行源码
      优先级 3: 启发式 fallback（从 type + text + id 推一句）
      立即落盘
```

**LLM purpose 约束**：

```
12-30 字，动词开头；
不许写 ArkTS 实现细节（"应使用 Column 包裹"等）；
不许写假设性内容（"可能用于..." → 不确定就写"用途待确认"）；
不许翻译 type 名（不要写"按钮组件，名为 Button"）

例:
  Button text="登录"        → "触发登录流程，弹出登录页"
  RecyclerView id=rv_feed   → "Feed 信息流列表，垂直滚动"
  CustomShimmerWidget       → "骨架屏加载占位动画"
```

**LLM 还可以补 `notes` 字段**：toolkit 解不出的 trigger / 反射调用 / 业务怪点，写一句中文备注避免下次踩坑。

### Phase 2.3: 多源 BFS reach_path（v6.3 — 确定性脚本，复活自老版）

**为什么独立成 Phase**：toolkit-fact-indexer 给的 `reach_paths` 实际是 toolkit ui_paths.json 的 action segments（"在某屏调用了什么方法"），**不是"如何到达某屏"**。下游 visual-verify v3.8 要"点击优先"，需要真正的 root→leaf 可点击序列。本 phase 用一个 277 行的确定性 BFS 脚本计算干净 reach_path。

**怎么跑**：

```bash
python3 $SKILLS_ROOT/app-relationship-tree/scripts/compute_reach_paths.py \
    spec/toolkit-fact-tree.json
```

**算法摘要**（详见脚本顶部 docstring）：

```
1. 建有向图：
   - 显式 outbound + 反向 inbound 取并集（toolkit 数据不对称的容错）
   - 隐式 contains[] → fragment 边（"show_fragment_X"）
   - 隐式 shows_dialogs[] → dialog 边（"trigger_X"）
   - host 补漏识（2026-09-08 通用化，零 app 名）：parent_in_nav 优先（indexer / Phase 2.4 按
     toolkit 记录与源码实例化点填）→ 通用命名 FragmentX/XFragment/首词 → XActivity →
     允许 1 个编辑距离（吃掉 Activitiy 这类拼写错）。曾写死 Guide/Home/Mine/Works → *Activity。
   - fuzzy match $\\d+ 后缀（HomeActivity$showCampaignDialog ≡ ...$1）

2. 多源 BFS：launcher 优先 + 其它 page 兜底当 entry，
   合并各源 reach 结果（节点只取第一次被发现的最短路径）

3. Tier 2 不动点迭代（最多 20 轮）：
   父被 reach 后子节点（含启发式 host）跟上

4. 输出 reach_path[i].e["reach_path"] = 节点 id 与 trigger token 交替的数组：
   ["SplashActivity","goto","HomeActivity","tap","MineFragment",
    "trigger_AccountInfoActivity","AccountInfoActivity"]
```

**AIPPT 实测**：57/57 = 100% 覆盖。仅 2 个 single-node 是数据缺陷（promoted 假节点 / 没走 companion helper 的直 Intent），靠 Phase 1.5 / Phase 2.5 修。

**铁律**：
- 本 phase 是**纯脚本**，不调 LLM
- 只**新增** `reach_path` 字段，不动 toolkit 已有字段
- reach_path 长度 1 的 record 标 unreached，下游知道是孤儿

### Phase 2.5: LLM 补 inbound_triggers 导航触发链（v6.2 关键）

> **铁律**：
> - LLM 读源码 grep `startActivity(<target>)` 反查谁调它，并把触发条件（onClick 函数 / View id / button text）抽出
> - **★间接跳转下钻（2026-07-16，AIPPT 实证漏边）**：grep 目标启动点（`startActivity(B)` /
>   `B.openXxx()` / `B.openWebPage()` 等）反查时，若调用点**不在**点击监听里、而在一个**普通函数/
>   扩展函数/ViewModel 方法**体内 → **不要停**，继续反查「谁调这个函数」，逐层上溯直到落到
>   `onClick`/`setOnClickListener`/`OnMenuItemClick` 等真实触发点，再抽 view id + label。
>   真实事故：`mineSettingCustomerService` 的 onClick 里写 `requireActivity().showService(false)`，
>   而 `showService`（SaleCenterViewModel.kt 扩展函数）内部才 `CustomerServiceWebActivity.openWebPage`。
>   只反查一层 → 反查到「showService 函数」就断链 → 这条 →CSWeb 边被漏建（同页 mineFeedback/
>   tvAfterSaleService 因直接调 openWebPage 就建对了，两两对照即此盲区）。**"点击→中转函数→
>   startActivity" 的两层间接是常见写法，必须下钻**；中转函数内有分支（如 showService 按
>   `contactUsUrl` 空否走 H5 或 拨号/弹窗）→ 每个分支的落点都要如实记（trigger 一个、落点多态）。
> - 对每个 fact-tree 里 `inbound = []` 或 `inbound[].trigger == "click"` 但 `via_component=null` 的 record，必须补全
> - 输出写到 record 顶层的新字段 `inbound_triggers[]`（不污染 toolkit 的 `navigation.inbound[]`）
> - **注释代码不是证据（2026-07-11）**：grep 命中行若处于注释中（行内 `//` 之后、`/* */` 块内、
>   `<!-- -->` 内），**禁止**作为 inbound_trigger / 导航边 / 前置条件的依据——引用 evidence_line 前
>   必须确认该行是活代码。真实事故（AIPPT WorksPage）：唯一入口 `fl_my_collect → WorksPage.openPage`
>   整段被 `//` 注释、layout 里控件也已删，仍被当活证据写进树 → 下游每轮真机白试导航 ~2min 后
>   BLOCKED，直到源码对质才翻案。同理：入口代码活着但引用的 view id 在 layout 里不存在，也要降级
>   （trigger_label 保留、加注 `layout_missing`），不得按可点击处理

**起点素材：`navigation.inbound[].nav_edge_seed`（toolkit 机械追到的候选边）**

toolkit 已把它机械追到的导航边写进 `record.navigation.inbound[]`，其中带 `nav_edge_seed: true`
的条目是**候选边**，字段：`from`（调用方 record id）+ `trigger_fn`（触发函数，如 `fn: onClick` /
`hosts fragment (FragmentTransaction.replace)`）+ `nav_edge_evidence_file` / `nav_edge_evidence_line`
（源码锚点）+ `nav_edge_extractor`（`regex` / `ast_index` / `bytecode*`）。

**这些是候选，不是成品** —— 它们给了「谁→谁、在哪行、哪个函数」，但缺 visual-verify 真正要的
`trigger_view_id` + `trigger_label`（真机上点的**文案**）。你的职责是把每条候选核实并解析成
完整 `inbound_triggers` 条目；同时补 toolkit 没追到的入口。

**★2026-09-08 起：机械候选已经落成 `inbound_triggers` 条目（Phase 2.4 / indexer），你的活是"核实与升级"，不是从零写**

Phase 2.4 把 `navigation.inbound` 的候选（宿主边 host_attach / 弹窗边 dialog_show / Activity 打开边
activity_start / 普通点击边，全部带 `nav_edge_seed: true`）机械落成 `inbound_triggers[]` 条目。**机械层只产可核实的事实，
怎么消费由你按项目决定**——下面分三段：字段语义、不可违反的约束、可用的测量。

**字段语义（机械候选条目）**

```jsonc
{
  "from_page": "MineFragment",            // 起点 record id（已保证是 UI 类型且在树内）
  "trigger_method": "onClick",            // toolkit 边的 trigger_fn / via；宿主边是 host_attach/viewpager_*
  "trigger_view_id": "rl_account_info",   // 静态 id（可能为 null）；来源见 provenance.rule
  "trigger_label": "账号信息",             // 只从起点页 layout/menu XML + @string 解析；歧义宁缺（null）
  "evidence_file": "…/MineFragment.kt", "evidence_line": 142,
  "source": "mechanical_candidate",
  "provenance": {
    "status": "candidate",                // 你升级后改成 confirmed | corrected | disproven
    "rule": "click_context",              // toolkit_edge | pager_click_map | click_context | helper_hop
    "label_from": "layout",               // layout | none
    "attach_kind": "tab", "kind_uncertain": true,   // 仅宿主边：结构信号 + 是否拿不准
    "host_source": "toolkit_fragments"    // 仅宿主边：宿主怎么定出来的
  }
}
```

同一起点可以有多条候选（一实例化点一条：tab 与菜单项都进同一页就是两条）；承载类边一宿主一条。
`rule` 告诉你这条的 id 是怎么来的：`click_context` 是按代码块归属追的点击上下文，`helper_hop` 经过了一跳
函数调用点（相对更容易错），`pager_click_map` 是宿主的 tab 点击→索引映射。`provenance` 里还可能有四个
**证据行标记**（只是线索，你去读）：`in_comment`（证据行在注释里）、`dead_branch`（上方有 `if (false && …)`）、
`companion_scope`（跳转写在 companion object 工厂方法里——真正的起点是调用这个工厂的页面）、
`from_dead_file`（起点类本身零活引用）；`evidence_line_guess` 是 toolkit 没给行号时按目标类名猜的一处。

**record 级机械事实（2026-09-08 晚试点后新增，你消费它们、不必自己再扫）**

- `walkability: {status: walkable|external_entry|dead|abstract, source: "mechanical", evidence, facts{abstract, manifest, instantiation_sites, instantiation_examples, sites_in_dead_files}}`——
  由 manifest（exported / intent-filter / activity-alias）、abstract 声明、去注释去 import 的活引用计数（引用落在死类文件里不算，两遍传递）机械推出。
  试点 27/27 与 LLM 一致。你确认或改判：改判写 `status` + `source: "llm"` + `evidence` + `mechanical_value`。
  **分母只算 walkable**：记分卡、计划器、preflight 都不再把抽象基类 / 外部拉起 / 死码当缺口。
- `layout_facts: {file, static_texts[], tools_texts[], view_ids[], root_id, edit_ids[], clickable_ids[], includes[], variants[], hosted_texts[{record, static_texts}]}`——
  页面**自己** layout 的静态文案（已解 @string、已还原 `\n`、`tools:` 占位另列、textColorHint 之类不算），
  同名 layout 多副本全列在 variants（`file` 是启发式选的，可改）；宿主的 `hosted_texts` 并上被承载子页/弹窗的文案
  并标来源——**向导步的「下一步/是/继续」在上一步子 fragment 的 layout 里，弹窗按钮在弹窗 layout 里**。
  `layout_file_conflict` 表示 toolkit 给的 layout 与源码 `R.layout` 引用不一致（layout_facts 按源码算）。
  **`edit_ids`（2026-09-09）**＝标签名以 `EditText` 结尾的节点 id（`AppCompatEditText` / `TextInputEditText` /
  自定义 `*EditText` 都算）——「某输入框非空」类前置的 `input.view_id` **只能**从这里取（guard 机械校验）。
  **`clickable_ids`**＝`android:clickable="true"` 或带 `android:onClick` 的节点，加上 Button / ImageButton /
  CheckBox / RadioButton / Switch / Chip / FloatingActionButton 结尾的控件。⚠️ 它只看布局：
  代码里 `setOnClickListener` 上去的普通 View **不在**其中——id 不在 `clickable_ids` 里只是"布局没写死可点"，
  不等于不可点，别据此证伪一条边。
- `list_item_roots[{item_layout, root_id, layout_file}]`——适配器 item layout 的**根元素** id（根无 id 就是 null，不降级取子节点）。
- `span_sites[{line, text, host_view_id, form}]`——`replaceSpan("X")` 的可点子串与宿主 TextView；`manual_span` 只报站点。
- `runtime_text_writes[{line, view, view_id, expr}]`——`x.text = …` 赋值点（多行语句已拼完整），布局静态文案可能被它覆盖，你判断覆盖成什么。

**语义字段（试点契约，每条活条目必填；这是「路径能否不靠现场探索就走」的承载，不许只写在 notes）**

```jsonc
"trigger_kind": "tap | auto | list_item | span | back | async_after_tap",
"trigger_kind_evidence": "file:line — 机制一句话（如 CountDownTimer(5110L).onFinish → goHomeActivity）",
// 按 kind 附加：
//  tap             trigger_label 取控件所在页 layout 的静态文案（tools_texts 不算；被 runtime_text_writes 覆盖的写覆盖后的值并 notes 说明）
//  list_item       trigger_view_id = item 根 id（list_item_roots），label_dynamic: true
//  span            span_text = 可点子串，trigger_view_id = 宿主 TextView id（span_sites.host_view_id）
//  auto            wait_hint = "countdown_ms:<n>" | "until_text:<文案>" | "immediate"（进入 from_page 后无需点击）
//  async_after_tap 触发点击在 from_page 上、靠异步结果才跳：trigger_label/trigger_view_id 是那个点击 + wait_hint
//  back            trigger_method = "onBackPressed"（系统返回；页内返回按钮按 tap 记）
"trigger_owner_page": "<控件所在页 record id>",   // 可选；与 from_page 不同时必填（向导步按钮在兄弟 fragment、companion 工厂在调用页、宿主内弹窗按钮在弹窗上）
"edge_preconditions": [{"kind": "<preconditions 白名单里的 kind>", "polarity": "required|absent", "evidence": "file:line — 一句话"}],   // 这条边被状态门住时必填（登录 / 会员 / 列表非空 / 输入非空），不许只写 notes；
                                                                                                               // ★polarity：「未登录/非会员才显示」的入口写 absent（record 级 preconditions[] 同样带 polarity），trip 分派据此排登出态——0909 实爆会员中心一族被排进 VIP 态
"disproven": true, "disproven_reason": "…"      // 证伪只要求理由，不要求 trigger_kind
```

`evidence_line` 是条目级字段（不在 record 保护字段里）：机械行号错（注释行 / 猜的）可以改，原值写进
`provenance.mechanical_value.evidence_line`。同一 TextView 上多个可点子串各一条，唯一键含 `span_text`。

**编排与留痕（2026-09-08 夜）**
- Phase 2（purpose）与 Phase 4（dependency_graph）不依赖 2.5～2.7，可与 2.5 并行派；2.6 必须在 2.5 之后（它消费裁决后的条目），
  2.7 在 2.6 之后。2.5 建议按 `evidence_file` 分组切 batch（AIPPT 103 条候选分布在 33 个文件，一文件读一次判完组内全部），
  batch 由主会话收口（android-fact-tree §2A.2 的 fork 规则）。
- 每个 phase 结束往树根写 `_phase_markers.<phase> = {ran, at, seconds, counts, strategy, completion_criteria, left}`：
  策略（范围 / 分组 / 抽样依据）、完成口径、剩了什么，用你自己的话写清；机械阶段也写自己的（2.4 / 2.7b）。preflight 只打印不判。
- 节点完备性：`stats.node_completeness`（manifest 声明但不在树 / 继承 Fragment·Dialog·Activity 但不在树）是 1.5 补 record 的依据，
  抽象类单列不补。

**不可违反的约束（guard 机械校验，违反即 FAIL）**

1. **原地升级或证伪，不删**：核实通过 → 在同一条目上填/改 `trigger_label` / `trigger_view_id` /
   `trigger_method`，`source` 改 `"llm_source_read"`，`provenance.status` 改 `confirmed`（机械值对）或
   `corrected`（你改了值，把机械原值留在 `provenance.mechanical_value`），并加 `verified_from_candidate: true`。
   核实为死码 / 注释 / view 不存在 → `disproven: true` + `provenance.status: "disproven"` + `notes`，条目保留
   （计划器按 disproven 跳过；删了下一次机械阶段会重新长出来）。
2. **唯一键是 (from_page, trigger_view_id 或 evidence_line, span_text)**，不是 from_page——同起点多个真触发各自一条
   （含同一 TextView 上的多个 Span），但不得复制出同键条目。
3. **事实字段不改**：`navigation` / `source_anchor` / `evidence_file` / `evidence_line` 是机械证据，你只能在
   `notes` 里说它不对，不能改写。
4. 文案顺着**字符串资源**走：`context.getString(R.string.x)` / `NavigationNames.getLabel(tag)` 这类代码拼
   出来的标签追到 strings.xml 取默认 locale 文案；追不到填 `trigger_label_unknown`，不要想象。
5. `kind_uncertain: true` 的宿主边由你在 Phase 2.6 定 tab / sub_tab / host_default（`attach_kind` 只是结构信号）。

**可用的测量（不是完成判据）**

- `tree_coverage_report.py <tree> --json`：E0/E1/E2/E3/K1/D 与 `llm_todo`（无文案边 / kind 不确定的宿主边 /
  无候选入边页 / 死码线索）。它量的是"有没有"，不量"对不对"。
- **`edge_lint.py <tree> [--write] [--json r.json]`（2026-09-09，机械注解器，幂等）**：给每条活边算
  `guard_flags[]`——`owner_mismatch`（`trigger_owner_page` ≠ `from_page`：控件根本不在起点页上）、
  `site_two_targets`（同一站点键无条件同时进两个目标，至多一条真）、`rid_not_in_from_layout`
  （id 不在起点页可见 id 域＝自身 layout ∪ include 链 ∪ 宿主/被宿主 record ∪ `list_item_roots` 根 id）、
  `rid_no_click_evidence`（不在起点页 `clickable_ids` 里且 `provenance.status != confirmed`）、
  `compressed_path`（同站点另一条边指向 B、而目标 C 有一条 from_page==B 的入边 ⇒ 这条多半是把
  A→B→C 压成一跳）。**这是线索不是判决**：0909 安卓边遍历 36 次熔断里 12 次归树数据，六种假边/
  弱哨兵形态都能在计划阶段被这五条拦住——命中即优先核实，核实后按约束 1 原地升级或证伪，
  **不要因为带 flag 就删边**。已 `disproven` 的边不再注解。
- `llm_phase_guard.py snapshot/verify`：上面约束 1–3 的机械校验。
- preflight 2.5b 只打印"未核实且无文案的候选数 + E2"，不再判 INCOMPLETE。

**你自己定的策略要写进 Phase 报告**：核实范围（全量 / 只核 `llm_todo` / 只核 `rule=helper_hop` 之类的高风险
子集）、抽样比例与依据、什么算完成、剩了什么没核。换项目时 E2 的可达上限不同（菜单/抽屉/动态文案多的项目
机械上限可能只有个位数），阈值由你按项目给出并说明，不用固定 90%。

**遍历策略**：

```
FOR EACH record IN pages + fragments + dialogs:
  IF record.id == launcher_short:
    record.inbound_triggers = [{from_page: null, trigger: "boot", source: "launcher"}]
    continue

  candidates = [e for e in record.navigation.inbound if e.nav_edge_seed == true]

  # ── 先消费候选边（有锚点，定位快）──
  FOR EACH cand IN candidates:
    读 cand.nav_edge_evidence_file : cand.nav_edge_evidence_line 上下 30 行（AST/bytecode 来源
      注释安全可直接信；regex 来源已过 toolkit 注释校验，但你**仍须自查该行是活代码**）
    从 cand.trigger_fn 顺到真实触发控件：
      · fn: <onClick 名>          → 反查该函数体里的 view id（findViewById(R.id.X)/binding.X）
      · hosts fragment (Transaction.add/replace) → host 的 ViewPager/事务里该 fragment 的
        触发 tab/step（含 wizard_step 的 下一步/是/否 按钮）
      · menu <resId> / l2:localIntent → 按锚点定位
    从 layout xml / @string 抽 view 的真实 android:text/content-desc 当 trigger_label
    产出 inbound_trigger 条目（见下方 schema），source="llm_source_read"，
      并带 verified_from_seed: true（留痕：源自 toolkit 候选、经核实）
    ★ 候选核实为死码/注释/view 不存在 → **不删**：`disproven: true` + `disproven_reason`（guard 强制；删了下次机械阶段会重新长出来）

  # ── 再补漏（候选没覆盖到的入口）──
  搜 Android 源码：grep -rn "startActivity.*${record.id}\|startActivityForResult.*${record.id}"
                 grep -rn "Intent.*${record.id}\.class\b"
  对每条**候选未覆盖**的命中：
    定位到所在 .kt / .java 文件 + 行号
    读上下 30 行：识别 onClick 函数 / view.setOnClickListener / lambda 触发点
    从同 file 反查 view id：findViewById(R.id.X) / databinding.X.setOnClickListener
    从同 module layout xml 找 R.id.X 的 view → 抽 android:text / content-desc
    LLM 推断 caller page (Activity/Fragment) 的 fact-tree id
  
  生成 inbound_trigger entry:
    {
      from_page:        <caller page id>,
      trigger_method:   <onClick 函数名>,
      trigger_view_id:  <R.id.X>,
      trigger_label:    <button text / content-desc / 推断>,
      evidence_file:    <相对路径>,
      evidence_line:    <行号>,
      source:           "llm_source_read"
    }

  Dialog / DialogFragment 特殊：
    搜 ${record.id}().show() / DialogFragment.show(...)
    同样反查到触发的 onClick / lifecycle hook
```

**约束**：

```
- trigger_label 必须从 layout xml / @string 资源真实抽出，不要 LLM 想象
- LLM 不确定时填 "trigger_label_unknown" + notes 说明，**不要瞎猜**
- 同一 record 可能有多个 inbound_triggers（多个屏都能跳到）——全列出，按调用频次 / 主流程优先排序
- launcher Activity 唯一 trigger 是 boot，特殊标 source: "launcher"
- `navigation.inbound[].nav_edge_seed` 是 toolkit 机械候选（带 from + trigger_fn + 锚点行），
  **必须逐条核实**再产出 inbound_trigger：注释/死码/view 不存在 → 标 disproven 保留；活代码 → 解析出
  trigger_view_id + trigger_label（真机文案），标 verified_from_seed: true。候选只是省你定位，
  不是免核实——直接原样抄会把 toolkit 的注释盲/无 label 缺陷带进最终真值
```

**输出例（AccountInfoActivity）**：

```jsonc
{
  "id": "AccountInfoActivity",
  ...
  "inbound_triggers": [
    {
      "from_page": "MineFragment",
      "trigger_method": "initView$1$1.onClick",
      "trigger_view_id": "rl_account_info",
      "trigger_label": "账号信息",
      "evidence_file": "app/src/main/java/cn/sanfate/pub/platform/page/MineFragment.kt",
      "evidence_line": 142,
      "source": "llm_source_read"
    }
  ]
}
```

下游 visual-verify Phase Alpha 拿到该字段后：
1. 把 inbound_triggers[0].from_page 当 host
2. am-start host → 在 host 屏 dump 里找含 "账号信息" 文本的 clickable → tap
3. 失败则用 trigger_view_id 找节点 tap
4. 仍失败 → 才回落 am-start AccountInfoActivity（cheat 路径）

> **2026-09-08 晚（试点后）verify_signal 的三种形态**：`{"text_contains": …}` 取本页 `layout_facts.static_texts`
> 里有判别力的一条（别选起点页也有的文案）；本页无静态文案时 `{"view_id": …}` 取 `layout_facts.view_ids` 里唯一的一个；
> 向导步 layout 完全相同（只差图片）时 `{"ordinal_in_wizard": n}`。`trigger_actions[0]` 必须带
> `from_trigger: {from_page, evidence_line}` 指向 2.5 裁决后的条目，不许从宿主源码另起炉灶重推。
> 非 walkable 的 record 按 `walkability` 归类，不再挂在 `contract_uncertain` 里。

### Phase 2.6: navigation_contract（v6.4 — 根因解，wizard / sub_tab / modal 精确导航）

**为什么需要**：下游 walk_android_tree.sh 的 Fragment 兜底逻辑是"找不到关键词就 fake-pass 截 host as-is"——结果 4 个 GuideXxxFragment 截到同一张 Step 1 图。根因是 **Fragment 的实际触发动作没结构化数据描述**。

本 phase 给每个 Fragment / Dialog 输出**精确 UI 导航合同**（`navigation_contract`），让 walk 脚本按合同精确点击 + 强验证，彻底消灭 fake-pass。

#### 合同结构（写到 record 顶层）

```jsonc
{
  "id": "GuideInitFragment",
  ...
  "navigation_contract": {
    "relationship_kind": "wizard_step",       // tab | sub_tab | wizard_step | lifecycle_modal | dialog_trigger | host_default
    "wizard_index": 0,                        // 仅 wizard_step 必填，从 0 开始
    "from_state": "GuideActivity_just_opened", // 前置态描述（人类可读，walk 用 reach_path 倒数第二节点判断匹配）
    "trigger_actions": [                      // 多入口数组（多数情况只 1 条）
      {
        "type": "auto_default" | "tap_text" | "tap_resource_id" | "back" | "swipe",
        "label": "下一步",                    // type=tap_text 时填
        "label_regex": null,                  // 运行时拼接文本用，如 "上传文档.*"
        "label_dynamic": false,               // true 表示文本来自运行时变量，walk 用 tap_first_clickable_button 兜底
        "resource_id": null,                  // type=tap_resource_id 时填
        "verify_after_tap": true              // 是否在 tap 后等 verify_signal
      }
    ],
    "verify_signal": {                        // 必填：到达本 Fragment 的标识
      "text_contains": "你常使用的PPT演示场景" // 单 primary（HMOS 一致铁律 §1.2，不需 fallback）
    },
    "exit_action_to_next": {                  // 仅 wizard_step：到下一 step 的动作
      "type": "tap_text", "label": "下一步",
      "leads_to": "GuideDifficulty1Fragment"
    },
    "contract_uncertain": false,              // LLM 推断未通过源码验证时标 true
    "generated_from": [                       // 锚点列表（追溯用）
      "spec/baseline/ui/page_0003_GuideActivity.md:38",
      "app/src/main/java/.../GuideActivity.kt:142"
    ]
  }
}
```

#### relationship_kind 6 类

| kind | 含义 | 例子 | trigger_action 模式 |
|---|---|---|---|
| `host_default` | host 启动后直接显示，无需 tap | HomeFragment 在 HomeActivity 默认 tab | `auto_default` |
| `tab` | 底部 / 顶部导航 tab | "我的" / "首页" 底部 tab | `tap_text` (tab label) |
| `sub_tab` | 容器内 ViewPager 子 tab | HomeDocFragment 是 HomeFragment 内的"导入文档"子 tab | `tap_text` (sub-tab label) |
| `wizard_step` | 顺序多步流程的某一步 | GuideInitFragment → Difficulty1 → Status → Details | 上一步的 `exit_action_to_next` |
| `lifecycle_modal` | 页面生命周期自动弹出 | LaunchAgreementDialog | `auto_default` |
| `dialog_trigger` | 特定业务按钮触发 | "联系客服" 按钮 → CustomerServiceDialog | `tap_text` |

#### 数据源 + LLM Prompt 模板

输入给 LLM 的上下文（每个 Fragment / Dialog 一次调用）：

```
context: {
  record_id: "GuideInitFragment",
  record_type: "Fragment",
  android_file: "app/src/main/java/.../GuideInitFragment.kt",  # 源码内容 ±30 行
  page_md_content: "..."  # spec/baseline/ui/page_*.md 匹配段
  host_record_id: "GuideActivity",   # parent_in_nav
  host_android_file: "...GuideActivity.kt",  # 源码 ±50 行
  host_layout_xml: "guide_activity.xml",  # 解析后的 button text
  sibling_fragment_ids: ["GuideDifficulty1Fragment", "GuideStatusFragment", ...]
}

task: 输出 navigation_contract，结构严格按 schema
```

#### 确定性源码验证（消除 LLM 错率）

LLM 输出后**必须**跑这些验证，不通过 → 标 `contract_uncertain: true`：

```python
case contract.relationship_kind:
  "wizard_step":
    # host 源码必须有 ViewPager.setCurrentItem 调用，或类似 step 切换逻辑
    assert grep("setCurrentItem|currentStep|step\s*\+\+", host_kt)
    
  "tab" | "sub_tab":
    # host layout xml 必须含 contract.trigger_action.label 文字
    assert label in extract_layout_strings(host_layout)
    
  "dialog_trigger":
    # host 源码必须有 `{record_id}.{...}.show(` 调用
    assert grep(f"{record_id}.*\\.show\\(", host_kt)
    
  "lifecycle_modal":
    # host 源码必须有 onCreate / onResume / onStart 里的 dialog.show()
    assert grep(f"override fun (onCreate|onResume|onStart)", host_kt)
    
  "host_default":
    # 无需验证
    pass
```

不通过的标 `contract_uncertain: true` + 输出到 `spec/visual-verify/contracts_uncertain.md` 供人工审。

#### 处理 4 个关键风险（建在 Phase 2.6 里）

| 风险 | 缓解 |
|---|---|
| **wizard 链失败传染**| Phase 5 自检：wizard_step 节点的 exit_action_to_next.leads_to 必须指向另一 wizard_step（同 host 内），形成有序闭环；**末步豁免**（末步出口指向宿主外的主页面，如 GuideInit → HomeActivity）。出口控件来自机械 `wizard_exit_controls`，抽不到时 contract 标 `exit_unresolved`，由你在 2.6 读子页源码定 |
| **LLM 推断错** | 上面的确定性源码验证 |
| **多入口同 Fragment** | trigger_actions[] 数组，walk 时按 reach_path 上文匹 from_state |
| **动态文本** | label_dynamic=true + label_regex 兜底 |

> **HMOS 端复用风险**：v6.4 起 SKILL.md §1.2（visual-verify）规定 contract 是双端唯一权威，HMOS 不一致 = 写 ALIGN findings，不在 contract 加 HMOS-side fallback。

### Phase 2.7: LLM 扩充 preconditions 业务前置态（v6.3 新增）

**为什么需要**：机械层（`tree_generic.scan_preconditions`，2026-09-08 夜重写）用语义族正则在**去注释**源码上抽了基础前置态，
并剔掉了 `if (false && …)` 死分支、本类 helper 定义行、类名裸命中；每条带 `provenance{status: candidate, rule,
enclosing_function, at_entry, condition}`——`at_entry=false` 的命中在某个处理器分支里，多半是「弹窗条件」而不是「页面门禁」
（AIPPT 实测机械 19 条错 10 条，重写后剩 14 条，其中 4 条仍是这类，靠这个标记交给你判）。另有 `intent_extras` 事实
（companion 写参 / 页面读参 / 缺参 finish 守卫）→ `param_required` 候选。业务语义（作品非空、已选模板、免费次数）机械抓不到，
page_md 已经写好。本 phase = **先裁决机械候选，再从 page_md 补缺**。

**输入**：
- record 现有 `preconditions[]`（机械候选，含 provenance）与 `intent_extras`
- 对应 page_*.md。**本代 a2h-spec 的 page_md 没有「前置条件 / 拦截器」这类章节**（二级标题只有 溯源 / 页面结构 / 转换决策 /
  状态接口 / 导航关系 / 功能检查锚点 / 沉浸式）；真正可用的语义源是 **`## 功能检查锚点` 的 FP_* 条目**。换项目先看章节名，
  别按固定标题 grep。
- 对应源码（`android_file` 锚点）

**遍历策略**：

```
FOR EACH record IN walkable pages + fragments + dialogs:
  # 1. 裁决机械候选（同 2.5 的约束：原地升级或证伪、不删）
  for pc in record.preconditions where pc.provenance.status == "candidate":
    读 pc.evidence_file:pc.evidence_line（含 provenance.condition / enclosing_function）
    页面门禁（进入前必须满足）→ 保留，provenance.status = confirmed | corrected（kind/evidence 改了留 mechanical_value）
    处理器里的分支条件 / 出边动作 / 弹窗自身条件 → disproven: true + disproven_reason，条目保留

  # 2. 从 page_md 补缺：功能检查锚点（或本项目等价章节）里描述的登录 / 会员 / 参数 / 数据 / 权限 前置
  for block in page_md 里描述前置/参数/拦截的段落:
    new_pc = {kind ∈ 白名单, evidence: "file:line — 一句话", source: "app_relationship_tree:<page_md 段落>"}
    合并（去重 by kind + evidence 片段）；给下游 scenario 配方留 data_hint（登录 / 会员 / 数据 三类）

  # 3. 边级前置：被状态门住的入边在 inbound_triggers 条目上写 edge_preconditions（见 2.5 契约），不许只写 notes
```

**Phase 2.7b: state_required 数据前置态推导（v6.8 新增，不依赖 page_md，全 record 必跑）**

> **为什么单列**：2.7 主循环 `if not page_md: continue` + 只抽入口拦截语义，会系统性漏掉
> **"入口不拦截、内容靠数据"** 的页面——典型如作品/收藏/历史列表页：列表空也能正常打开（空态占位），
> 源码无 `if (isEmpty()) return` 守卫可抓，但 (1) 空态截图对比价值低 (2) 下游"点条目进详情"的边
> 直接不可走（AIPPT 实测：PPTFilePage 依赖点击作品条目，账号无作品时该边永远走不通且会被误诊成
> nav_unreachable）。**数据前置是"测试可达性"属性，不是"入口拦截"属性——不要因为入口不拦截就跳过。**

对每条 record（不管有没有 page_md）按两个信号判：

```
信号 a（确定性，读树即可判，优先）:
  存在子页 child 满足: child.preconditions 含 param_required 且参数语义为"列表条目对象"
                     且 child.reach_path 途经本页的条目点击边
  → 本页补 state_required（evidence 写明 child 与边; unblocks=[child.id]）

信号 b（读源码，android_file 锚点）:
  布局含列表容器(RecyclerView/ListView/LazyColumn) 且 源码有空态分支
  （emptyView / list.isEmpty() 分支 / "暂无"占位文案）且 数据源来自 DB/接口（非静态写死）
  → 本页补 state_required（evidence 写空态分支出处）
```

产出条目**必须带 `data_hint`**（给下游 scenario-builder / visual-verify 预检器规划 fixture 的一句话数据需求）：

```jsonc
{"kind": "state_required",
 "evidence": "PPTFilePage(param_required: Intent 传入待预览作品) 经本页'我的创作'条目点击到达; 列表空则该边不可走",
 "data_hint": "账号内 ≥1 个已生成作品",
 "unblocks": ["PPTFilePage"],            // 仅信号 a 有; 预检器据此关联下游页面
 "source": "app_relationship_tree:state_required_rule_a"}   // rule_a / rule_b 标明推导来源
```

**★2.7b 收尾必须留痕（2026-07-10，机械闸依据）**：跑完后往树根写 marker——**找到 0 条也要写**：

```jsonc
"_phase_markers": {"state_required_rule": {"ran": true, "found": <N>, "at": "<ISO日期>"}}
```

出口闸（`dispatch.py::preconditions_gate`）凭"存在 `state_required_rule` source 的条目 **或** 此 marker"区分"跑了没发现"和"根本没跑"——缺痕迹直接 FAIL 不得交付。真实事故：本 phase 在一次 ART 崩溃抢救中被无声丢掉（手工补了 enrich patch 但没人对照 phase 清单核销），4 条数据前置态消失、下游 visual-verify 预检假绿放行，靠 trip_2 撞页才暴露。**崩溃抢救/断点续跑后必须重跑本 phase 或确认其痕迹仍在。**

**扩充的 kind 类别**（toolkit 抽不到的）：

| kind | 例子 | 通常出现在 |
|---|---|---|
| `param_required` | "需要 query 参数 + from 来源" / "intent extra 必传对象" | page_*.md §"传参"；源码 intent 读参 |
| `state_required` | "已上传文档" / "已选模板" / "作品列表非空" | page_*.md §"前置态" + **2.7b 树结构/源码信号（不依赖 page_md）** |
| `credits_required_amount` | "免费次数 ≥ 1" / "VIP 等级 ≥ 月会员" | page_*.md §"拦截器" |
| `nav_redirect_target` | "未登录 → 跳 LoginPage / 无余次 → 跳 MemberCenterPage" | page_*.md §"拦截器" |
| `feature_flag` | "interceptAuth=1 全局开关" / "服务端 userConfig/推送决定可见" | page_*.md §"全局配置"；服务端配置 |
| `permission_required` | "授予 MANAGE_EXTERNAL_STORAGE 后才可达" | 源码权限守卫（2026-07-10 收编） |
| `first_launch_onboarding` | "仅首启引导流程可达（MMKV 标记后不再出现）" | 源码首启守卫（2026-07-10 收编） |
| `business_state` | "productBean!=null 且 auditingStatus!=1 才弹" | dialog 变体节点可见性条件（2026-07-10 收编；**非 fixture 可造态，勿与 state_required 混用**） |
| `permission_not_granted` | "权限**未**授予时才弹提示 dialog" | dialog 变体节点（2026-07-10 收编） |

**★kind 白名单机械强制（2026-07-10）**：以上 kind + 基础层 `login_required`/`vip_required`/`login_conditional`/`intercept_dialog` 构成**封闭白名单**，由 `android-fact-tree/scripts/dispatch.py::preconditions_gate` 出口硬拦。真实事故：崩溃抢救的修复 agent 自造 `data_required`（还有 `server_config`/`intent_extra_required`）→ 2.7b rule_a 按 kind 字符串匹配链式失效 → state_required 全丢 → visual-verify 预检假绿。**语义已有近似 kind 的必须归并（intent 传参→param_required、服务端配置→feature_flag），确属新语义才扩表；扩表必须同时改本表和 gate 的 `PRECOND_KIND_WHITELIST`，只改一处 = 契约漂移。**

**输出例（CreateOutLinePage 扩充后）**：

```jsonc
"preconditions": [
  // toolkit-fact-indexer 抽的（基础）
  {"kind":"login_required","evidence":"UserData.isBinding() check",
   "evidence_file":"...CreateOutLinePage.kt","evidence_line":66,
   "source":"preconditions_enhancer"},
  // app-relationship-tree LLM 扩充的（业务）
  {"kind":"param_required","evidence":"query 非空",
   "source":"app_relationship_tree:page_0006_CreateOutLinePage.md"},
  {"kind":"credits_required_amount","evidence":"freeCount>=1 或 VIP",
   "source":"app_relationship_tree:page_0006_CreateOutLinePage.md §拦截器"},
  {"kind":"nav_redirect_target","evidence":"未登录→LoginPage / 无次数→MemberCenterPage",
   "source":"app_relationship_tree:page_0006_CreateOutLinePage.md §拦截器"}
]
```

**★契约三条（2026-09-09，前两条由 `llm_phase_guard.py verify` 机械强制，FAIL 级）**

0909 安卓边遍历 36 次熔断里，6 次源于账号态前置没有极性、2 次源于空输入守卫没有输入配方——
两类都是"字段写了但机器读不出该怎么做"，不是漏写。

1. **账号态前置必须带极性**：`kind ∈ {login_required, vip_required, login_conditional}` 的条目
   （record 级 `preconditions[]` 与边级 `edge_preconditions[]` 一视同仁）必须有
   `polarity: "required" | "absent"`：

   | polarity | 语义 | 源码判定依据 |
   |---|---|---|
   | `required` | **有**该态才可达/才显示 | `if (!isLoggedIn()) { goLogin(); return }`、`if (!isVip()) { showPaywall(); return }` —— 守卫**拦住**继续往下走 |
   | `absent` | **没有**该态才显示/才可达 | `if (!isVip()) showUpgradeEntry()`、`if (!isLoggedIn()) tvLogin.visible = true` —— 取反条件**里面就是**那个入口/页面本身 |

   `vip_required` 的字面意思只是"和会员有关"，**不是**"必须是会员"：两种形态在源码里都写成 `if (!isVip())`，
   差别只在花括号里是"拦截返回"还是"显示这个入口"。判不准就把 `evidence` 写成
   `file:line — if (!isVip()) 里面直接 show 了本入口` 这种能自证的一句话。
   下游 trip 分派据此排登出态/非会员态；缺极性 → 「非会员才显示」的一族入口被排进会员态 → 页面不出现 → 边走不通 → 熔断。
   过渡期可用 `ART_ALLOW_MISSING_POLARITY=1` 把**缺失**降为 WARN（取值拼错恒 FAIL）。

2. **输入守卫必须给结构化输入配方**：`kind == "state_required"` 且守卫是「某输入框非空 / 长度够」时必须带

   ```jsonc
   "input": {"view_id": "<该页 layout_facts.edit_ids 之一>", "text_hint": "<能过校验的最短 ASCII 串，无要求填 null>"}
   ```

   `view_id` 取值域就是机械事实 `layout_facts.edit_ids`（边级前置查 `from_page` 的、record 级查本 record 的），
   写了表外 id 直接 FAIL。`text_hint` 只写能过校验的最短串（长度/格式类校验写满足式样的 ASCII），
   不写业务真值。没有输入配方，执行器只知道"要填点什么"却不知道填到哪个框、填什么。

3. **门弹窗必须有自动入边**：`navigation_contract.relationship_kind == "lifecycle_modal"` 且
   preconditions 里有 kind 以 `first_launch` 开头的条目（首启引导/隐私协议这类**挡在前面**的弹窗）时，
   该 record 必须有一条 `trigger_kind: "auto"` 的 `inbound_triggers` 条目并带 `wait_hint`
   （`"countdown_ms:<n>"` / `"until_text:<文案>"` / `"immediate"`）——它不是点出来的，是进页面就弹的；
   没有这条边，计划器会去找一个不存在的按钮，或者把它当不可达页跳过，后面每一页都被它挡住。

**约束**：
- LLM 输出每条 precondition **必须**有 `evidence` 字段引述 spec 原文
- `source` 必须指明出处（页面 md / 源码行）
- 不要瞎猜——找不到证据就不写。toolkit 已有的不重复写
- preconditions 数组保持去重（kind+evidence_fragment 唯一）

### Phase 3 (可选): 启发式补 reach_paths 孤儿

> **触发条件**：用户显式要求"补完 reach_paths" 或 fact-tree 中 `reach_paths == []` 的 record > 0
>
> **承认现实**：toolkit-fact-indexer 已经从 toolkit 真实数据榨到 96% 覆盖（55/57 in AIPPT）。剩 4% 是 toolkit 的算法盲区——ViewPager 反射实例化的 Fragment / 自定义 widget 等。要拉到 100% 必须用命名启发式（不是 toolkit 事实，标 source 为 heuristic）。

启发式规则（2026-09-08 通用化；零 app 名，与 compute_reach_paths.infer_host_page 一致）：

```
parent_in_nav 已填（indexer / Phase 2.4 按 toolkit 记录与源码实例化点）→ 直接用
FragmentXxx        → 找 XxxActivity 当 host
XxxFragment        → 找 XxxActivity 当 host
首词 Xxx…Fragment  → 找 XxxActivity 当 host（GuideDifficulty1Fragment → GuideActivity 这类）
以上允许 1 个编辑距离（吃掉 Activitiy 类拼写错）
XxxFragment 嵌在 XxxParentFragment → 推 parent 当 host
```

匹配到 host 后：
```jsonc
record.reach_paths.append({
  "display": f"{host.reach_paths[0].display} > heuristic_host > {record.id}",
  "depth": host_depth + 1,
  "source": "heuristic_host_inference",   // 明确标 heuristic 不是 toolkit 事实
  "ref": null
})
```

### Phase 4: LLM 推 dependency_graph.layers

> **触发条件**：默认必跑（除非 fact-tree 已有 `dependency_graph` 字段表示之前跑过）。
>
> **背景**：toolkit-fact-indexer 给的 `features[]` 是 token 聚类（如 `generated.home.renew` / `generated.mine.about`），**没有架构语义**。下游 visual-verify 排序需要"先 Foundation 后 Shell"的层级提示，要 LLM 看每个 feature 的语义把 17 个聚类归到 6 个架构层。

#### 输入

```python
features = fact_tree["features"]          # toolkit 17 个聚类（id / label / screens / top_tokens）
records  = fact_tree["pages"] + fact_tree["fragments"] + fact_tree["dialogs"]
launcher = fact_tree["app"]["launcher_short"]    # 用于识别 Foundation
# 每个 feature 关联的 record 现在已经有 purpose（Phase 2 补好的）
```

#### 6 个架构层定义

| layer | 含义 | 典型 feature |
|---|---|---|
| 0 Foundation | App 启动 / 协议 / 引导 / 通用基础 | Splash / LaunchAgreement / Guide |
| 1 Auth | 登录 / 账号 / 三方认证 | Login / AccountInfo / AliAuth |
| 2 Monetize | 会员 / 支付 / 续费 / 退款 | MemberCenter / Pay / Renew / Refund |
| 3 Core | 主业务功能（app 的核心价值流程） | 创作 / 生成 / 播放 / 编辑等主流程页 |
| 4 Extended | 扩展功能 | 推荐 / 文件管理 / 视频播放 / WebView |
| 5 Shell | 聚合页 / 主导航 | Home / Mine / 主页 Tab 容器 |

#### LLM 任务

```
对每个 feature，根据：
  - representative_screens（toolkit 给的代表 screen 列表）
  - top_tokens（toolkit 聚类用的 token，如 ["login","auth","sms"]）
  - 关联 screen 的 purpose（Phase 2 已补的中文描述）
  - 关联 screen 的 android_file 包路径（如 .platform.page / .baseui.activity 可看出基础库）
  - 是否含 launcher

推断这个 feature 归属哪一层（0-5）。

特殊规则：
- 含 launcher_short 的 feature → 0 Foundation
- top_tokens 含 "login"/"auth"/"phone"/"account" → 1 Auth
- top_tokens 含 "pay"/"member"/"vip"/"refund"/"renew" → 2 Monetize
- screen 含 "Home"/"Mine"/"Main" 且其它 layer 都不匹配 → 5 Shell
- 其它业务功能 → 3 Core 或 4 Extended（看是否是主流程；判据是"launcher 后用户最常走的价值流程"，
  用 feature 的 representative_screens 与 purpose 判，不预设任何领域词）
```

#### 输出

往 fact-tree 顶层加 `dependency_graph` 字段：

```jsonc
"dependency_graph": {
  "layers": [
    { "layer": 0, "name": "Foundation", "features": ["generated.splash.app", "generated.launch.agreement", "generated.guide.app", "generated.again.confirm"] },
    { "layer": 1, "name": "Auth",       "features": ["generated.app.src"] },   // app.src 含 LoginActivity / AccountInfoActivity
    { "layer": 2, "name": "Monetize",   "features": ["generated.member.center", "generated.home.renew"] },
    { "layer": 3, "name": "Core",       "features": ["generated.choice.ppttemplate", "generated.fill.pptquery", "generated.ppttemplate.preview", "generated.works.app"] },
    { "layer": 4, "name": "Extended",   "features": ["generated.customer.app", "generated.file.upload", "generated.landscape", "generated.video.play", "generated.web.app"] },
    { "layer": 5, "name": "Shell",      "features": ["generated.mine.about"] }
  ]
}
```

#### 约束

- 每个 `fact.features[*].id` **必须**出现在某层的 `features[]` 里（覆盖完整，不允许遗漏）
- 同一 feature 只能在一层（互斥）
- layer 编号 0-5 严格递增，name 字段与上面定义表一致
- 不可改 `fact.features` 数组本身（toolkit 事实）

#### 增量重跑

如果 fact-tree 已有 `dependency_graph` 且 feature 集没变（同 fact.features 列表），直接复用，不重新 LLM 推。

---

### Phase 5: 自检 + 写回

退出前必须确认：

| 项 | 验证 | 严重度 |
|---|---|---|
| JSON 合法 | `jq empty < spec/toolkit-fact-tree.json` | HARD |
| schema_version=1 不变 | 没被改坏 | HARD |
| 所有 page/fragment/dialog `purpose` 非 null | 自检 | HARD |
| 所有 component `purpose` 非 null | 自检 | HARD |
| navigation / source_anchor / parent_id / flow_graph / features / stats 与 LLM 跑前**逻辑等价**（允许 Phase 1.5 删假 record / 改 fq_class）| diff with allowed-mutations whitelist | HARD |
| **Phase 1.5 删除节点的 inbound/outbound 已 merge 到等价 real record**（v6.3）| 扫所有 navigation.inbound/outbound，from/to 必须存在于当前 records | HARD |
| **Phase 1.5 新增节点字段齐全**（v6.3）| id / type / fq_class / android_file / source / purpose 不能 null（除了 source 字段标 added 的可接受首版 purpose=null）| HARD |
| reach_paths 字段保留（toolkit 96% 的不能丢） | 长度 ≥ Phase 1 时长度 | HARD |
| **reach_path 字段非空**（v6.3 Phase 2.3；2026-09-08 夜限定）| 每条 **walkable** record 都有 reach_path（launcher 时为 `[id]`，其它至少 3 元素：root + token + self）；`walkability.status` 为 dead / abstract / external_entry 的豁免（reach_path 由机械脚本产，LLM 无据可补） | HARD |
| **reach_path 中所有 page-id token 都在 fact-tree 里**（v6.3）| BFS 中间步骤不能引用不存在的 record | HARD |
| **dependency_graph.layers 覆盖所有 features** | 每个 `fact.features[*].id` 必须在某 layer.features 里 | HARD |
| **dependency_graph.layers feature 互斥** | 同一 feature_id 不能出现在两层 | HARD |
| **inbound_triggers 字段存在**（v6.2 新增；2026-09-08 夜限定）| 每条 **walkable** record 都有 inbound_triggers（≥1 条活条目；launcher 可只有 boot）；非 walkable 的写 record 级 notes 即可，**找不到入口不要造边**（试点实测 28 条 record 属此类，旧规则与「不要造」不可能同时满足） | HARD |
| **inbound_triggers.from_page 可达**（v6.2 新增；2026-09-08 放宽）| 引用的 page id 必须是 fact-tree 中存在的 record，或是 null（仅 launcher boot）；**`disproven: true` 的条目豁免**（证伪墓碑要保留） | HARD |
| **preconditions 扩充（v6.3）**| toolkit 已抽的基础 preconditions 必须保留；本 skill 扩充的条目 source 字段必须含 `app_relationship_tree:` 前缀 | HARD |
| **navigation_contract 字段存在**（v6.4）| 每条 Fragment / Dialog 都有 navigation_contract（host_default 类型可只填 relationship_kind + verify_signal） | HARD |
| **navigation_contract.relationship_kind 合法**（v6.4；2026-09-08 统一口径）| Fragment/Dialog 必须是 6 类之一（host_default / tab / sub_tab / wizard_step / lifecycle_modal / dialog_trigger）；Activity 为 activity_root / activity_jump / activity_data_required；另有 blackbox_discovered（黑盒发现节点）与 callback（外部回跳）。`llm_phase_guard.py` 的 RK_ENUM 是机械强制点 | HARD |
| **wizard chain 闭环**（v6.4）| 所有 relationship_kind=wizard_step 节点，按 wizard_index 排序应形成 0→1→2→...，相邻两节点 exit_action_to_next.leads_to 必须指向下一 index | HARD |
| **contract_uncertain 标记输出**（v6.4）| LLM 推断未通过确定性源码验证的，必须标 contract_uncertain=true + 写入 `spec/visual-verify/contracts_uncertain.md` | HARD |
| **新增 / 删除节点的 stats 字段对齐**（v6.3）| stats.total_pages/total_fragments/total_dialogs 必须 = 实际数组长度 | HARD |
| **inbound_triggers.evidence_file 真实存在**（v6.2 新增）| 抽样检查 5 条，evidence_file 路径必须在 android_root 下存在 | HARD |
| **Phase 1.6 新增节点 source 前缀正确**（v6.5）| 类扫描新增的 dialog record `source` 必须 == `"app_relationship_tree_added_class_scan"`，便于追溯/统计 | HARD |
| **Phase 1.6 新增节点 construction_mode 合法**（v6.5）| 必须是 `"layout_xml"` 或 `"code_only"` 二选一 | HARD |

任一 ❌ → skill 失败，向用户报错。写回 `spec/toolkit-fact-tree.json` 覆盖。

---

## 3. 输入 / 输出

| 项 | 路径 | 说明 |
|---|---|---|
| **唯一必选输入** | `spec/toolkit-fact-tree.json` | toolkit-fact-indexer 产物，若不存在则自动调起 |
| 中间锚点（Phase 2 LLM 增量读用） | `spec/.cache/fact-tree/source-index.json` | toolkit-fact-indexer 已产 |
| **必选**（v6.3）| `spec/baseline/ui/page_*.md` | a2h-spec 产物，Phase 1.5 校验漏识节点 / Phase 2.7 扩充 preconditions 必读 |
| **必选**（v6.2）| Android 源码（`{android_root}/`） | LLM 看源码补 purpose **+ inbound_triggers + Phase 1.5 节点校准**；要 grep startActivity / Intent / class 定义，必须有源码 |
| 可选 | `spec/baseline/feature-index.md` | 校准 dependency_graph.layers 时优先用 |
| **唯一输出** | `spec/toolkit-fact-tree.json` | **原地覆盖**，不产新文件 |

---

## 3.5 如何完整跑这个 skill（v6.4 编排）

本 skill 5 个 phase 里 4 个是 LLM 任务、3 个是脚本任务。**正确执行流程是**：

### 推荐路径 A：一键 orchestrator + 派 sub-agent 补 LLM phase

```bash
# 第 1 步：跑所有确定性 phase（脚本）
bash $SKILLS_ROOT/app-relationship-tree/scripts/run_all_phases.sh \
    --android-root <ANDROID_ROOT> \
    --tree spec/toolkit-fact-tree.json

# orchestrator 跑完会输出 LLM phase 待办，如：
#   ❌ fact-tree 未完成 2 个 LLM phase:
#   📌 Phase 2 (purpose): 30 record purpose=null
#   📌 Phase 2.6 (contract.label): 42 contract_uncertain=true

# 第 2 步：对话里跟 模型说 → 模型派 sub-agent 跑 LLM phase
#   "跑 app-relationship-tree Phase 2.6 LLM 补 contract.label"
#   "跑 app-relationship-tree Phase 2 LLM 补 purpose"
#   或一次性：
#   "跑 app-relationship-tree 全 LLM phase"
```

### 推荐路径 B：让 模型当 orchestrator（最常用）

直接说：
> "跑 app-relationship-tree 完整流程，目标 fact-tree 是 X"

模型会：
1. 自动跑 run_all_phases.sh（脚本部分）
2. 看 preflight 报告，识别哪些 LLM phase 未完成
3. 按需派 sub-agent 跑 LLM phase（一次跑完所有 / 单 phase 跑）
4. 跑完后再跑 preflight 确认 ✅

### 不推荐做法

❌ 只跑 calibrate_nodes.py / compute_reach_paths.py / compute_navigation_contract.py 单脚本 — 会跳过所有 LLM phase
❌ 跳过 preflight 直接进 visual-verify — walk_android_tree.sh v3.9 会卡住报错

### 检查当前状态

```bash
bash $SKILLS_ROOT/app-relationship-tree/scripts/preflight_check.sh \
    spec/toolkit-fact-tree.json
# exit 0 = 全完成，可下游消费
# exit 1 = 待 LLM phase，按提示派 sub-agent
```

下游 arkts-visual-verify Phase Alpha 启动时**自动**调这个 preflight，未完成会拒绝跑。

### LLM 阶段写树守卫（2026-09-08，机械闸）

LLM phase（2 / 2.5 / 2.6 / 2.7 / 4）改树前后必须过 `scripts/llm_phase_guard.py`：

```bash
python3 $SKILLS_ROOT/app-relationship-tree/scripts/llm_phase_guard.py snapshot spec/toolkit-fact-tree.json spec/.cache/tree_before_llm.json
# … 跑 LLM phase（直接改树或 apply batch patch）…
python3 $SKILLS_ROOT/app-relationship-tree/scripts/llm_phase_guard.py verify spec/.cache/tree_before_llm.json spec/toolkit-fact-tree.json
```

verify 只证伪不代判：record 集合不得增删（增删只准在 Phase 1.5/1.6）；每条 record 的
`navigation` / `source_anchor` / `parent_id` / `fq_class` / `android_file` / `flow_graph` / `features`
不得改；`inbound_triggers` 同 (from_page, view_id|evidence_line) 不得重复、机械候选（`provenance.status=candidate`）只准升级或标 disproven 不准消失；
`preconditions[].kind` 必须在白名单且带 evidence；`relationship_kind` 必须在枚举内。任一违规 exit 1
并列出 record / 字段。这是"toolkit 给的对的不能改"从散文变成机械闸。

---

## 4. 与上下游协议

### 上游：toolkit-fact-indexer

- 必须先跑 toolkit-fact-indexer（产出 fact-tree.json + source-index.json）
- fact-tree 中所有 `purpose=null` 是预期的——本 skill 来补
- fact-tree 中 reach_paths 已有 96% 真实数据——本 skill 不动那 96%，只**新增** heuristic 条目给剩 4% 兜底

### 下游：直接读 fact-tree.json（统一入口）

- **a2h-spec** Phase 0.5：直接读 fact-tree.pages[].navigation 等结构事实 + 用 purpose 写 spec 描述
- **visual-verify** / **a2h-fixer**：直接读 fact-tree.pages[].reach_paths 当测试队列 + 检索地图
- 不再有 `spec/app-relationship-tree.json` 这个文件——v6 删除

---

## 5. 触发场景

```
用户: 补一下 fact-tree 的 description
用户: 补 purpose
用户: 完整化关系树
用户: 给 toolkit 产物加业务语义
用户: app-relationship-tree
用户: 我跑完 fact-indexer 了，把 description 都填上
用户: 给 fact-tree 产 dependency_graph
用户: 让 fact-tree 能被 visual-verify 按架构层级排序
用户: 补导航触发链 / 补 inbound_triggers / 让 visual-verify 知道按钮怎么跳
```

---

## 6. 历史变更

| 版本 | 时间 | 主要变化 |
|---|---|---|
| **v6.5**（current）| 2026-06 | **Phase 1.6 新增**：源码 popup 类正向扫描——补 Phase 1.5 反向 page_md 扫描的鸡生蛋盲区。脚本 `scan_popup_classes.py`，~1 秒跑完，rg-based + 继承链传递闭包 + 命名兜底。在 jq50w/project1 实测：fact-tree dialogs 180→245（+65），覆盖 65 个已知漏识 popup 中的 59 个（90.8%，剩 6 个为 Base 抽象基类，正确排除）。新增字段 `construction_mode` 区分 layout_xml/code_only。自检 +2 项 |
| v6.4 | 2026-05 | **Phase 2.6 新增**：navigation_contract — 给每个 Fragment / Dialog 输出精确 UI 导航合同（relationship_kind / trigger_actions / verify_signal / wizard_index）。下游 visual-verify v3.9 按合同精确点击 + 强 verify_signal，消灭 fake-pass。配合 4 项风险缓解（wizard 链闭环 / 源码确定性验证 / 多入口数组 / 动态文本 regex）。自检 +4 项 |
| v6.3 | 2026-05 | **职责扩展**：从"补 purpose"升级为"toolkit-fact-tree 多源补全器"——可补字段 / 校正字段 / 新增节点 / 删除节点。新增 Phase 1.5（节点校准：剔除假 Activity / 校正 fq_class / 补漏识 record）+ Phase 2.7（LLM 扩充 preconditions 业务前置态，配合 toolkit enhancer 的基础抽取）。page_*.md 从可选变必选。自检 +5 项 |
| v6.2 | 2026-05 | Phase 2.5 新增：**LLM 读源码补 `inbound_triggers` 导航触发链** — 每条 record 列出从哪些屏点哪些按钮可到达自己，含 view_id / button_label / source line。下游 visual-verify Phase Alpha 据此做"点击优先、指令兜底"导航。Android 源码从可选变必选。自检 +3 项 |
| v6.1 | 2026-05 | Phase 4 新增：LLM 推 `dependency_graph.layers`（feature → 架构层级映射），下游 visual-verify 排序得以按 Foundation → Shell 顺序工作。自检加 2 项（覆盖 + 互斥） |
| v6.0 | 2026-05 | **彻底简化**：仅做 fact-tree 语义补充；删除 spec/app-relationship-tree.json 产物；删除 Phase 4D 字段映射 / 独立 schema / Phase 5 Fragment / Phase 6.5 reach_path 脚本；下游直接读 fact-tree.json |
| ~~v5~~ | 2026-05 短暂 | Phase 4.5.A/B + 严格自检 + 仍产 app-relationship-tree.json |
| ~~v4~~ | 2026-04 | reach_path 单独脚本算 |
| ~~v3 及更早~~ | — | 复杂的多 phase 流程 |

---

## 7. 局限性

| 局限 | 说明 |
|------|------|
| 依赖 toolkit-fact-indexer 先跑过 | 必须有 spec/toolkit-fact-tree.json |
| 不读 ArkTS 源码 | tree 是预期状态参照系，不描述 HMOS 现状（旧 SKILL §0 设计原则保留） |
| heuristic reach_paths 不是 toolkit 事实 | 标 `source: "heuristic_host_inference"` 让下游自行判断 |
| 没有"多源融合扩 sub_components 列表" | v6 简化，如要从 graph_builder / android-source 扩列表，请走 toolkit 端补充（重跑 toolkit + fact-indexer） |

## 覆盖率记分卡（2026-09-08）

`scripts/tree_coverage_report.py <tree> [--gate]`：E0 页有候选入边 / E1 页有活入边 / E2 边可机械执行
（真实文案或非容器 view id）/ E3 tab/宿主子页有宿主边 / K1 wizard 链自洽 / D 有入边却判死，外加
**LLM 待补清单**（占位文案边、kind 不确定的宿主边、无候选入边页、死码线索）。preflight_check.sh 末尾
会打印它；visual-verify Phase 1 用 `--gate`（默认 E1≥90% E2≥90% E3≥92% K1=100% D=0；E1/E3 分母剔除
walkability 为 dead/abstract/external_entry 的非 walkable 节点，2026-09-15）拦残树——E2 阈值按项目
在 `--gate` 参数里给，机械上限低的项目（菜单/抽屉型）由 LLM 阶段报告说明后调低。任何低于默认的阈值都要
**用户**在 `spec/tree_hints.json` 写 `coverage_gate_approved`（by=user + 阈值 + 理由）才被接受，否则 REFUSED（exit 3）。
原则：机械阶段（indexer 6 enhancer + Phase 1.5/1.6/2.4/2.3/2.6）先做到最佳，LLM 阶段（2/2.5/2.6 补全）
只处理记分卡列出的待补项。全部判据零 app 常量；项目专属模式放 `spec/tree_hints.json`
（precondition_patterns / tab_signals / wizard_signals）。
