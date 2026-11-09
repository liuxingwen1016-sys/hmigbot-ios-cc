---
name: visual-verify-speed
description: 安卓→鸿蒙 UI 迁移的快速视觉验证与修复闭环。安卓真值直接用 android_fast_traverse 的产物（android_traverse_screenshots），鸿蒙侧由执行器按安卓遍历树逐边找对应控件、点击、确认落点、采集，并按安卓单元编号当场配对；结构 oracle 与度量表自动预筛，只有疑似有差异的对子交给并行的判图子代理；产物写在 spec/visual-verify/，问题单写在 spec/fix/round-N/{ui,feat}（标准问题单格式，带 _index/_summary/_delta 和 spec/fix/_state.yaml），修复按文件冲突分组并行，统一编译装机后只复验改过的单元。用于"快速版视觉验证""用 android_fast_traverse 产物验鸿蒙""鸿蒙和安卓截图对比并修复""visual-verify-speed"。
---
# visual-verify-speed

三段：**安卓真值**（android_fast_traverse 已采好的 `android_traverse_screenshots`）→ **鸿蒙按安卓树走查**（执行器自己找控件、点、认落点、采集，模型只在开头、结尾和少数未知弹窗时参与）→ **配对、预筛、判图、出单、修复、复验**。

运行需要 Python 3.10+、Pillow、`hdc`（一台已连接的鸿蒙设备或模拟器，被测 HAP 已安装）。脚本入口 `scripts/vvs.py`，所有命令都可加 `--work <目录>`；不加时在当前目录找 `spec/visual-verify/config.json`。

## 第 0 步：安卓真值

已经有 `android_traverse_screenshots/index.json` 就直接用（安卓安装包不变就一直复用，不重跑）。先找再跑：鸿蒙工程、安卓工程目录下，以及用户提到的目录里，找 `android_traverse_screenshots/_aft/state.json` 里 `package` 等于安卓包名、`status` 不是 `running` 的那一份。都没有才按 android_fast_traverse skill 跑一遍安卓遍历；那是它的事，本 skill 不碰安卓设备。

**等安卓遍历跑完（`_aft/state.json` 的 `status` 为 `completed` / `completed_with_gaps` / `halted`）再进第 1 步。**鸿蒙走查照着安卓遍历树走，半棵树上走会漏掉后来才采到的单元；`init` / `walk` 在 `status=running` 时会拒绝（`--allow-partial` 可强行）。等待期间可以先读安卓工程、看鸿蒙工程结构。

## 第 1 步：绑定与鸿蒙 profile

```bash
python3 scripts/vvs.py init --android-out <.../android_traverse_screenshots> --hmos-project <鸿蒙工程> \
    --android-project <安卓工程> --target <hdc 设备号>
python3 scripts/vvs.py inspect --launch
```

`init` 从 `AppScope/app.json5` 读包名、从 `entry/src/main/module.json5` 读入口 Ability，产物目录默认 `<鸿蒙工程>/spec/visual-verify`；起始轮次取 `spec/fix/_state.yaml` 的 `current_round`，已有的 `spec/fix/round-N` 不会被覆盖。同时输出安卓计划摘要（单元数、哪些单元需要手驱）。然后看 `inspect` 的画面大纲，写 `<work>/cache/input/profile.json`（格式见 [hmos-walk.md](references/hmos-walk.md)，示例 [hmos_profile.example.json](assets/hmos_profile.example.json)）：

- `root`：**以安卓基线的根单元为准**（`init` 输出的计划摘要里的根单元，看它的截图和选中的 Tab），写鸿蒙冷启动后同一屏上一定在的文字；不要照设备当前画面写——设备可能停在上次留下的别的 Tab。安卓根单元选中的是哪个 Tab，鸿蒙的 root 和 `start_recipe` 就停在哪个 Tab。冷启动回不到根页，整轮就废了；`walk` 采到的根页和安卓根单元文字重合不到 0.4 时会打警告，按警告核对 profile 后 `walk --fresh`。
- `start_recipe`：协议、引导这类首次启动才出现的画面，写成"出现某控件就点某控件"。
- `business_readings`：当前账号、当前选中项这类一变就说明数据被改了的文字。

两端都只跑应用当前能访问的那一个状态（不分未登录 / 已登录两趟）：安卓基线是什么账号状态，鸿蒙就保持同样的状态。只用设备上现有账号和数据。清数据（`drive --allow-clear "clear; ..."`）、重装、登录、造数据需要用户明确要求。

## 第 2 步：鸿蒙走查

```bash
python3 scripts/vvs.py walk [--max-minutes N] [--model-timeout 180]
```

用 Bash 的 `run_in_background` 启动 `walk`（不要前台等它跑完），用 Monitor 盯输出里的 `VVS_MODEL_REQUEST` 和进程结束；没有 Monitor 时按间隔读后台输出。执行器按安卓深度优先顺序：先到父单元（已在→按 BACK→冷启动后重放安卓点击路径），在鸿蒙上找安卓这一步点的控件（同 id→同文字→同文字忽略数字→包含关系→改过文案的相似文字→同一高度的横向标签行里左右滑着找→向下滑着找→无文字图标看它旁边的文字→同屏幕位置的图标→列表项按同类列表同位置；规则与原则见 [hmos-walk.md](references/hmos-walk.md)），避开底栏、浮层等遮挡点下去，确认画面变了，采集首屏和滚动帧，再核对落点是不是安卓那一页（落到安卓另一单元那一页记 `wrong_target`），记在安卓同一编号下。找不到控件、被盖住点不到、点了没反应、落错页、离开应用，记成缺口（之后自动出单）并跳过其下级，走查继续；连续 3 次恢复失败才停（`halted_breaker`），再跑一次 `walk` 就从断点续。

- 出现 `VVS_MODEL_REQUEST id=... dir=...`：读该目录的 `request.json` 和 `before.png`，按 [hmos-walk.md](references/hmos-walk.md) 的弹窗协议写 `decision.json`，再 `vvs.py respond --request-id <id> --decision <dir>/decision.json`，继续读原进程输出。只有不是这次点击该出现的层（启动广告、更新提示、挡住首页的页面）才会来问。
- 运行期间不要再跑 `drive`/`inspect` 或任何 hdc 命令（设备锁会拒绝）；可以同时做不碰设备的事：按计划摘要里的 `needs_drive` 写好第 3 步的手驱命令；单元多、走查长时可以**边走边判**——先对已采到的单元跑 `pairs` 并派判图，走查结束后再跑一次 `pairs`，同一轮已判过且证据没变的对子直接沿用，不重判。
- `halted_start`：冷启动到不了根页，输出里写明是哪一种。应用一启动就离开前台（启动崩溃，输出里带最新的设备故障日志路径）：不是 profile 的问题，直接跑 `pairs` + `tickets`，会出一张启动崩溃单（P0），其余页面记成被它挡住的占位单；这一轮到此为止，修好、重新编译安装后再走查。应用停在别的画面：按安卓根单元截图核对 profile 的 `root` / `start_recipe` 后 `walk --fresh`。
- `halted_drift`：业务读数变了且冷启动后仍没恢复。把改数据的操作查清（看 `cache/events.jsonl`），用 `drive` 把数据改回，再 `walk` 续跑。

## 第 3 步：手驱补采

只补走查到不了的单元：报告"需要手驱补采"一节列出的（安卓那边要输入文字的、首次启动画面、按安卓手驱步骤回放不通的——例如两端列表内容不同），以及确实需要登录/手势的。一条 `drive` 串完一组状态，每个状态一个 `capture pair=<安卓单元号>`：

```bash
python3 scripts/vvs.py drive "start; tap 我的; tap 搜索; text abc; wait 1; capture pair=manual_0031_SearchActivity 搜索结果"
```

步骤语法见 [hmos-walk.md](references/hmos-walk.md)。某一步失败时 `drive` 停在那里（输出 `STOPPED at step N`，退出码 1），从失败处接着写。一条 `drive` 串很多步时可能超过两分钟，Bash 调用把 `timeout` 设到 `600000`（10 分钟）。`text` 输入到当前焦点输入框（没有焦点时输入到上一次点击的位置），中文也可以。危险词控件（删除、支付、退出登录等）要写 `tap !文字` 才会点，且只在用户授权后这样做。

## 第 4 步：配对、预筛、判图

```bash
python3 scripts/vvs.py pairs
```

对每个安卓单元，脚本先做三件不用模型的事：

- **结构 oracle**：对比两端 dump，得出缺失、多余、兄弟顺序不同；两端都有列表内容时内容不同的文字不算，鸿蒙一项列表内容都没有时报"整块列表内容缺失"。另加**字号比对**：同一段文字两端墨迹的宽和高按同一比例变大或变小 8% 以上，记为"字号疑似不同"（输入框的提示文字也比，鸿蒙从 dump 的 hint 读；框的描边、圆角外侧、框内图标和光标不算墨迹）。
- **度量表**：两端元素各按自己的密度换算成 dp/vp 再比；安卓用屏幕适配库时，按 `design_width_in_dp` 算出实际密度。文字用截图里的墨迹框；离屏边 24dp 以内的元素按贴着的那条边算偏移，其余按左/中/右里最接近的对齐方式；底部栏从可用底边算（安卓到导航栏上沿，鸿蒙扣掉 28vp 手势条）；网页内容按屏宽比例换算。这一步还会找出"节点存在但画不出来"的元素（前景色等于背景色）。
- **对比图**：两边缩放到同一 dp 比例，每 50dp 一条网格线，写在 `screenshots/sbs/round-N/<page_id>.jpeg`（后续帧在 `blocks/`）；只用来看颜色、图标、样式，不在图上量尺寸。安卓基线、鸿蒙截图和 dump 也同时复制到 `screenshots/android/`、`screenshots/harmony/round-N/`，问题单只引用这几处。

结构、度量、文字都一致且首屏相似的对子直接通过（`auto_pass`）；上一轮判过、鸿蒙证据没变且判图管线版本相同的，沿用结论（`carried`）——判图口径、oracle 或度量改过（`PIPELINE_VERSION` 变了）就全部重判；沿用的对子每轮按约 10% 抽样重判（任务书标"抽样复核"），翻出上轮漏判说明管线有洞。缺对比图或截图的对子不送判，记成占位单。其余的按"同 Activity、同 resource-id 集合"分组打包，每批最多 4 对，写在 `rounds/round-N/judge/batch_XX.md`。批次文件里带着结构 oracle 差异（编号 O1…）、度量表，以及本页 resource-id 对应的**安卓布局 XML 文件行号和属性**（源码真值）。

然后**每个批次派一个判图子代理，全部并行**（用平台的子代理工具一次派完，再等全部返回）。任务书就是批次文件路径加上 [judge.md](references/judge.md)。判图口径：

- 只有系统栏可以豁免，不许自己判"平台差异"；
- 随机或动态内容必须给出安卓源码证据；
- 流程不同用固定类别（如 `dialog_extra_on_android`）；
- 每条 oracle 差异都要表态；
- 图标、兄弟顺序检查必填；
- 尺寸只认度量表和源码。

主会话不读截图。全部返回后：

```bash
python3 scripts/vvs.py tickets
```

它先机械复核每个结果文件：缺文件、字段不合格（包括 oracle 差异没表态、数据类差异没给源码证据）时退出码 2，只对列出的单元重派判图。然后对判图结论做二次核对：

- 说某元素"消失"，但鸿蒙截图里它明明画出来了 → 撤回；
- 布局类结论引用的元素，度量位移只有几 dp → 撤回或降为低级。

判图确认的 oracle 差异会自动出单（已被流程类问题解释的除外）。问题单写在 `<鸿蒙工程>/spec/fix/round-N/`：

- 文件名即 id：`ALIGN_P<页号>_<差异类型>_<slug>`（差异类型 layout_drift / layout_bug / color_mismatch / font_mismatch / spacing_drift / component_mismatch / icon_mismatch / missing_element / extra_element / text_mismatch / scroll_overflow）；页号取安卓基线单元号（`page_0024_*` → `P0024`）；
- frontmatter 字段和顺序、severity 映射（high→P0、medium→P1、low→P2）、正文 1 / 1.5 / 2–7 段固定（§1 附安卓源码行，§7 是安卓点击路径）；
- 图标语义、兄弟顺序检查不一致的也出单（与判图结论重复的不再出）；同一问题出现在 ≥3 页时另出 `ui/_systemic/SYSTEMIC_<slug>.md` 并在成员单写 `systemic_root`；
- 每轮写 `_index.md`、`_summary.md`（总计 / 页面维度 / checks performed / Top 10）、第 1 轮起写 `_delta.md`，并更新 `spec/fix/_state.yaml`。

写完先跑一遍格式自检（文件名 = id、必填字段、正文分段、similarity 范围、evidence 路径存在、导航单字段、占位单指向），不通过退出码 1。报告 `spec/visual-verify/report.md` 包含：撤回或降级的结论、只比了结构的差异（附安卓源码依据）、**覆盖账**（安卓源码里的 Activity 和弹框清单 → 安卓基线没采到和没点的 → 鸿蒙配上的），以及**安卓缺、鸿蒙有**的分类：

- **鸿蒙多出的帧**：安卓页面可滚动 → 安卓少截了，是安卓基线欠账；安卓一屏放得下 → 鸿蒙内容溢出，算差异。
- **鸿蒙多出的可点控件**：安卓源码里有 → 先用 android_fast_traverse 补采安卓再比；安卓源码里没有 → 鸿蒙独有，请用户确认（只在无障碍描述里的会单独标出）。
- **手驱额外截图**：没有安卓对应，单独列出。

走查缺口也在这一步出单：安卓走通、鸿蒙没走通的边（找不到入口、点了没反应、被盖住点不到、跳错页） → `CRASH_P<父页>_nav_failed_<From>_to_<To>_P<目标页>`（带 `v4_edge` 和 `blocks_subtree`；上级已失败的下级只出占位单）；安卓点的列表项鸿蒙列表里没有 → `BLOCKED` 占位（列表缺失由上级页对比单负责）；离开应用 → `CRASH_P<页>_app_crash_on_nav`；本轮没采到的页（被上游挡住、需要手驱、采集失败） → `BLOCKED_P<页>` 占位单（不是缺陷，不派修复）。

## 第 5 步：修复与复验（默认最多 3 轮；用户只要验证时跳过）

```bash
python3 scripts/vvs.py fixplan [--max-parallel 4]
```

按问题单的建议文件做并查集：共用文件的单归一组，组与组写集不相交；多个单元共用的宿主页（Navigation 根页、Tab 容器）只在单子没有别的候选文件时才进写集，免得把不相干的单粘成一个大组（真要改宿主页的，修复子代理报 `needs_file`）；占位单、已转人工（`manual_review`）和人工豁免（`skipped` / `wont_fix`）的不修。排程写在 `rounds/round-N/fix/schedule.json`，摘要写在 `<鸿蒙工程>/docs/autofix-log/round-N/batch.md`，同时给鸿蒙源码拍一份快照。每一波里**每组派一个修复子代理并行**（任务书 [fix.md](references/fix.md)），`unlocated` 组最后单独跑。修复子代理只改本组写集，改完在问题单 §6 追加一条修复记录即返回，不编译、不装机、不截图。

全部返回后先机械复核：

```bash
python3 scripts/vvs.py fixcheck
```

对照快照和 §6 修复记录，查空改（声明的文件没变）、和以前重复的假设、改动类型与问题不符、漏写修复记录、改了任何一组写集以外的文件、新引入"显示时 HitTestMode.Block"这类会挡住整棵子树点击的写法。后两类（退出码 1）要先处理：把越界改动还原或交回对应组重派，危险写法让该组修掉；其余 flag 写进 `docs/autofix-log/round-N/fixcheck.md`，下一轮会带进对应问题单 §6，要求修复方换方向。修复方在组结果文件里报 `blocked` / `needs_file` / `refuted` 的单不算漏写，单列为"修复方未改"并带上原因；`needs_file` 在这一波结束后由你按原因派补修子代理（任务书同 fix.md，写集 = 它要的文件），结果写 `rounds/round-N/fix/followup_<名>.json`（同格式），它报的 `changed_files` 计入允许写集、它的 `status` 覆盖原组的。

然后主会话**只编译一次**（按项目的构建方式出签名 HAP）。编译失败时派**一次**修编译错误的子代理（只给编译错误输出和本轮改动文件清单，只修编译错误，不做视觉修改），再编一次；仍失败就停下交给用户，不来回折腾。编译通过后：

```bash
python3 scripts/vvs.py install --hap <签名 HAP>
python3 scripts/vvs.py next-round          # 下一轮重走有问题单/缺口的单元和修复改到的页；改到公共组件/资源/路由则全部重走；current_round 同步推进
python3 scripts/vvs.py walk
python3 scripts/vvs.py pairs               # 没重走的单元沿用上一轮结论
```

再派判图、`tickets`，循环到没有问题单或用完轮次。跨轮时同一问题单 id 的 §6 修复记录、人工处置（`skipped` / `manual_review` / `wont_fix`）和上轮复核 flag 自动带进新单；同一 id 出现满 3 轮或修复满 3 次的标为**顽固问题**（单里写明必须换假设，`_summary.md` 单列），修复满 5 次仍未通过的转人工（`manual_review`），不再派修复。收尾时如有时间跑一次 `next-round --full` + `walk` + `pairs`，把改动可能波及的其它页面也过一遍（证据没变的对子不会再判）。

## 交付

- `<鸿蒙工程>/spec/fix/round-N/`：问题单、`_index.md`、`_summary.md`、`_delta.md`（第 1 轮起）；`spec/fix/_state.yaml`。
- `<鸿蒙工程>/spec/visual-verify/report.md`：配对数、自动通过/判过/沿用、没配上的单元及原因、需要手驱的单元、配对把握低的单元、复核撤回/降级、只比结构的差异、覆盖账、安卓缺鸿蒙有、问题单清单、走查耗时与设备时间。
- `<鸿蒙工程>/spec/visual-verify/screenshots/`：`android/`（安卓基线与 dump）、`harmony/round-N/`（鸿蒙截图与 dump）、`sbs/round-N/`（对比图）。
- `<鸿蒙工程>/docs/autofix-log/round-N/`：`batch.md`（修复批次）、`fixcheck.md`（修复复核）。

## 质量底线

1. **不确认就不记账。** 每张鸿蒙截图都来自点击后新做的 dump；找不到控件、点了没变化，记缺口，不拿父页面冒充子页面。配对把握（文字重合度）写进 meta 和报告，把握低的交判图确认。
2. **结论要有证据。** 尺寸和位置只认 dump 换算的 dp/vp 和安卓源码，不认截图像素；判图的"缺失""偏移"会被脚本对照 dump 和度量表再核一遍；"平台差异""随机内容"不能自判，后者必须附安卓源码出处，前者只有用户能豁免。
3. **鸿蒙不比安卓多点。** 只点安卓执行器点过的控件；鸿蒙同位置控件是删除/确认类而安卓不是，拒点并记 `danger_refused`。弹层只用取消/关闭/返回关掉，从不点确认类。
4. **业务数据变了就停。** `business_readings` 在冷启动到根页时核对，冷启动后仍不对就 `halted_drift`。
5. **结论要有复验。** 修复只改代码，不写 disposition；修复记录先过 `fixcheck` 机械复核，问题单关闭只看下一轮真实走查和判图，不看修复者自报。
6. **不改本 skill 脚本。** 执行器行为不对时记下现象和证据（命令、`cache/events.jsonl`、`cache/state_round-N.json`），停下来报告。

## 命令速查

```bash
python3 scripts/vvs.py init --android-out A --hmos-project H [--android-project S] [--target T] [--work W]
python3 scripts/vvs.py inspect [--launch]
python3 scripts/vvs.py walk [--max-minutes N] [--model-timeout 180] [--fresh] [--only ID1,ID2]
python3 scripts/vvs.py respond --request-id R --decision PATH
python3 scripts/vvs.py drive "STEPS" [--allow-clear]
python3 scripts/vvs.py pairs | tickets | fixplan | fixcheck | report | status
python3 scripts/vvs.py install --hap PATH
python3 scripts/vvs.py next-round [--full]
```

产物目录与字段见 [artifacts.md](references/artifacts.md)。
