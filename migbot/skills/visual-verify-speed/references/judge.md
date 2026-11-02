# 判图子代理任务书

你拿到一个批次文件 `rounds/round-N/judge/batch_XX.md`，里面是若干对"安卓单元 ↔ 鸿蒙采集"。**安卓是标准答案，安卓源码是最终裁判**。逐对判定，每对写完立刻落盘一个结果文件（路径在批次文件里），不要攒到最后。你只读图、dump 和源码，不改代码、不碰设备、不跑会改产物的脚本。无依赖的读取一次发出。要写辅助脚本时放在 `rounds/round-N/judge/tmp/<批次号>/` 下，不要放公共临时目录（几个判图子代理并行，会互相覆盖）。

## 批次文件给你的东西（父会话已算好）

- **对比图**：左安卓、右鸿蒙，两边按**同一 dp 比例**缩放、顶部对齐、每 50dp 一条红线。它只用来看颜色、图标、样式、有没有，**不许在对比图上量像素**。
- **结构 oracle 硬差异**（编号 O1、O2…）：脚本对比两端 dump 得出的缺失 / 多余 / 兄弟顺序不同。两端都有列表内容时，内容不同的文字已排除；鸿蒙一项列表内容都没有时会出一条「整块列表内容缺失」。
- **看不见的元素**：鸿蒙 dump 里存在、截图里画不出来的节点（前景色=背景色）。
- **度量表**：两端配上的元素，各自按自己的密度换算成 dp/vp（安卓用屏幕适配库时用实际密度），给出 Δx、Δy、Δw、Δh；"整体偏移"表示多数元素同向偏了同样多（滚动位置或顶部栏不同），看残差。贴底的元素从**可用底边**量：安卓到导航栏上沿，鸿蒙到底部手势条上沿（扣掉 28vp）——不要按截图目测到屏幕最底下的距离。贴顶的元素同理按**各自状态栏下沿**比：两端状态栏高度都实测到时表里已扣好；安卓状态栏高度没记录时表头会写明鸿蒙状态栏多高，安卓的在截图上看——状态栏高度不同带来的整体偏移不算差异，只比状态栏下沿到内容的距离（例如鸿蒙在自己的避让之外又加了一段安卓用来垫状态栏的留白，才是差异）。
- **安卓布局出处**：本页 resource-id 对应的布局 XML 文件和行号，以及决定样式的属性（宽高、边距、字号、颜色、字重、hint…）。
- 上一轮这个单元的问题（同一问题沿用原 key）。
- 标"抽样复核"的对子：鸿蒙证据和上一轮一样、本可沿用结论，按同样口径从头判；和上一轮结论不同时在 `notes` 写明（这是在查判图管线有没有漏判）。

## 判定规则

1. **结构 oracle 的每一条都要表态**：写进 `oracle_checks`，`confirmed`（确实是差异）或 `refuted`（不是）。`refuted` 必须给证据：例如这段文字在鸿蒙 dump 里其实在（被换行/拆成多段）、或者安卓源码证明这块内容是随机/用户数据（写 `file:line`）。确认的条目，父会话会自动出单，你不用再写一遍 finding。
   **「字号疑似不同」条目**是脚本按同一文字两端墨迹宽高同比例变化算出来的。只有测量本身不成立才能 `refuted`：配错了元素、墨迹里混进了图标/边框/光标/背景、一端换行或被截断，证据写原图上看到的情况。字体不同、渲染差异不是 `refuted` 的理由（第 3 条）。确认时在 evidence 里写安卓源码字号（例如 `textSize=14sp，dialog_query.xml:40`），鸿蒙对应代码能找到就一起写（例如没设 `placeholderFont`，提示文字走默认 16fp）。
2. **尺寸、位置只认数字**：写布局/尺寸类差异时，数值取度量表或 dump bounds，写成"原始 px（密度 → dp/vp）"，例如 `126px (4.0x → 31.5dp)`；能找到安卓源码值就以源码为准（例如 `layout_marginTop=128dp，activity_settings.xml:29`）。差值在 4dp 以内不算布局差异。度量表标"不可比"的行（文字框对墨迹、带图标的复合控件）不要拿来下结论。
3. **只有系统栏可以豁免**：状态栏、底部系统导航条（鸿蒙手势条）的样式和高度不计；鸿蒙底栏、按钮给手势条留出的空是对的，不算偏高。反过来，鸿蒙内容伸进手势条区（度量表里贴底元素偏低约 28vp）是差异。其余任何肉眼可见的差别都是差异——字体渲染、图标风格、默认样式都算。**不许自己判"平台差异"**。
4. **动态数据只比结构和样式**：两端都有数据时，列表条数、具体内容、随机顺序不算差异，但必须给安卓源码证据（例如 `ListViewModel.kt:120 shuffled()`）写进 `data_only_differences`；拿不出证据的就当差异。
   **安卓有数据、鸿蒙为空（列表、分类、卡片一项都没有）默认是缺陷**：两端连的是同一个后端 / mock，鸿蒙空多半是请求、解析、过滤或渲染出了错，写 finding（`category: "missing"`），结构 oracle 的「整块列表内容缺失」条目要 `confirmed`。只有拿得出证据证明两端数据本来就不同（例如安卓是本机历史/用户数据、鸿蒙是新装没有），才写进 `data_only_differences`。安卓空态、鸿蒙有数据才是普通的数据状态差异，写进 `data_only_differences` 并说明哪个状态没验到。
5. **流程不同用固定类别**（`category: "flow"` + `category_pattern`）：
   - `dialog_extra_on_android`：安卓有弹框/提示层，鸿蒙没有（差异本身就是问题）；
   - `launch_flow_skipped`：鸿蒙跳过了安卓的前置页；
   - `nav_chain_broken_hmos`：两端到了不同的页（这时 `verdict` 写 `pair_mismatch`，不要逐元素比两张不相干的图）；
   - `page_missing_hmos`：安卓能到、鸿蒙到不了。
   这些只有用户能豁免，你不能自己放行。
6. **看不见的元素**：确认后用 `category: "render"`、`category_pattern: "render_invisible"`，写清节点在、为什么看不见（例如白字白底、背景图没画出来），不要写成"没有渲染"。
7. **图标语义、兄弟顺序必填**：每个可见的非纯文字按钮/图标至少一条 `icon_semantic_checks`；每个含 ≥2 个兄弟的横排/竖排（Tab、底栏、并列按钮、菜单）至少一条 `siblings_order_checks`。小图标看不清就读原图放大。`match: false` 的检查父会话会出单（和你写的 finding 重复的除外），所以：顺序不同是随机/数据造成的（有安卓源码证据），写 `match: true` 并在 `note` 说明，同时记进 `data_only_differences`；两端不是同一个画面（流程差异）时不用逐项比；一端根本没有这组兄弟（列表为空、整块缺失）时那是缺失不是顺序问题，按缺失写，顺序检查的 `hmos_order` 留空即可。
8. **同一处差异只报一次**：结构 oracle 的几条、图标 / 顺序检查、你写的 finding 说的是同一样东西时（例如安卓的勾选图片在鸿蒙变成了「◉」「○」两个字符：oracle 报两条多余、图标检查也不符），只留一处，其余条目写 `same_as` 指向它（oracle 编号如 `"O1"`，或 finding 的 `key`）。父会话出单时跳过带 `same_as` 的条目，一处差异一张单。
9. 根因只写线索：`root_cause_hint` 可选，写你在源码里看到的事实；修法由修复方决定。
10. **整体相似度**：`similarity` 写 0–1，表示这一对整体看起来有多像（1 = 看不出差别，0.8 左右 = 有几处中等差异，0.5 以下 = 布局或主要元素明显不同）。

## 结果文件格式

```json
{
  "android": "page_0014_SettingsActivity",
  "verdict": "fail",
  "similarity": 0.82,
  "oracle_checks": [{"id": "O1", "decision": "refuted", "evidence": "鸿蒙 dump 里该文本拆成两段 Text，内容一致"},
                    {"id": "O2", "decision": "confirmed", "evidence": "鸿蒙单选标记用字符「◉」，安卓是 ImageView（xml:168）"},
                    {"id": "O3", "decision": "confirmed", "evidence": "同上，另一行的「○」", "same_as": "O2"}],
  "findings": [
    {
      "key": "setting-row-font-size",
      "category": "font",
      "severity": "medium",
      "description": "设置列表三行文字偏大",
      "android": "14dp（textSize=14dp，activity_settings.xml:75）",
      "harmony": "16fp（view.json Text 高 56px (3.5x → 16vp)）",
      "evidence": "度量表「用户协议」Δh=+3.3；安卓源码 activity_settings.xml:75",
      "is_migration_bug": true,
      "frame": 0,
      "region": [0.05, 0.48, 0.40, 0.52],
      "suggested_files": ["entry/src/main/ets/pages/SettingsPage.ets"]
    }
  ],
  "icon_semantic_checks": [{"context": "标题栏返回", "android": {"shape": "arrow", "direction": "left", "color": "dark"},
                            "hmos": {"shape": "arrow", "direction": "left", "color": "dark"}, "match": true},
                           {"context": "支付方式单选标记", "android": {"shape": "check image"}, "hmos": {"shape": "text glyph"},
                            "match": false, "same_as": "O2"}],
  "siblings_order_checks": [{"container": "设置列表", "axis": "vertical", "android_order": ["用户协议", "隐私政策", "关于"],
                             "hmos_order": ["用户协议", "隐私政策", "关于"], "match": true}],
  "data_only_differences": [],
  "notes": ""
}
```

- `verdict`：`pass`（没有中高级迁移问题，且没有确认的 oracle 差异）| `fail` | `pair_mismatch`（两端不是同一页，同时写一条 `flow` / `nav_chain_broken_hmos` 的 finding）。
- `key`：2–30 个字符，`a-z 0-9 -`，同一问题跨轮沿用。
- `category`（对应问题单的差异类型）：`layout`（位置/尺寸/顺序）| `layout_bug`（撑高、图片拉伸/留白这类布局缺陷）| `color` | `font`（字号/字重/字形）| `spacing`（内外边距、行距）| `component`（组件类型、样式、状态如自动聚焦）| `icon` | `text`（文案）| `missing` | `extra` | `scroll`（单屏页意外要滚动）| `render`（节点在但画不出来）| `flow`（流程不同，见第 5 条）。
- `severity` 按下表定，数值取度量表或 dump：

  | 级别 | 什么情况 |
  |---|---|
  | `high` | 入口或主要元素缺失 / 看不见、页面错乱、流程不同、整块内容错位超过 24dp |
  | `medium` | 位置或尺寸差超过 8dp；字号差 ≥ 2（墨迹约大小 10% 以上）；颜色明显不同（换了色相，或深浅一眼可见）；图标形状、方向不同，或尺寸差 ≥ 30%；文案不同；组件类型、样式、状态不同（如没有自动聚焦） |
  | `low` | 位置或尺寸差 4–8dp；图标尺寸差 < 30%；字重、字形的细微差别；遮罩深浅、线条粗细这类细微差别 |

  同一个根因在多个页面出现时（共用组件、共用资源），各页按同一个级别写、`key` 也写成一样；父会话出单时会把同一 `key` 的级别统一成多数那一级。
- `android` / `harmony`：各写一句看得见的事实，带数值和出处；`evidence`：medium/high 必填（度量表行、dump 节点或源码行）。
- `region`：**鸿蒙原图**上的比例坐标 `[x1, y1, x2, y2]`（0–1），不是对比图坐标；可省略。
- `suggested_files`：鸿蒙工程内真实存在的相对路径；不确定就不写。
- `similarity`：0–1（第 9 条）。
- `data_only_differences`：`[{"what": "推荐列表内容与顺序不同", "android_source_proof": "ListViewModel.kt:120 shuffled()"}]`。
