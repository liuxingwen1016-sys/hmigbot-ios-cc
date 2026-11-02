---
name: android_fast_traverse
description: 安卓应用页面与交互态遍历采集：执行器自动发现控件、判断页面与视图态、返回和恢复，按边遍历逐个采集截图与 view.xml；运行中自己冒出来的未知弹窗交给调用 skill 的模型判断，执行器核验后原地继续。另有 burst 定时连拍。产物目录结构固定（index.json + 逐单元截图与 XML），可直接交给下游 UI 对齐或迁移流程。用于安卓全量/指定范围遍历、截图与 dump 采集、迁移前的安卓真值准备。
---

# android_fast_traverse

边遍历 + 自动发现：执行器点一个控件、认出落点、截图、返回，再点下一个，每个控件约 2 次 dump，不逐控件重启应用。普通恢复由执行器处理；模型只在开跑前、结束后和少数未知弹窗时参与。运行需要 Python 3.10+、ADB 和一台已授权设备（或模拟器），脚本只用标准库。

**产物目录固定叫 `android_traverse_screenshots`（下文 OUT），一次任务只用这一个。** 默认在当前目录下，所有命令不写 `--out` 就用它，写别的名字会被拒绝。首次遍历、续跑、审阅补跑、手驱补采都写这个目录；对原 `OUT` 再执行 `run` 会自动续跑。要从头重来（根页选错、换了安装包）用 `run --fresh`：当前遍历整体移到 `_aft/previous/NNN/` 留档（之前手驱采的单元也一起归档，已验证的弹窗规则和 `_aft/input/` 保留），按 `_aft/input/profile.json` 在同一目录重新开始。不要另建目录，也不要删断点。

**数据重置：** 任务开头按用户要求重装一次；之后要回到干净数据只用 `adb shell pm clear <包名>`（不改安装时间，同一 `OUT` 可续写）。中途重装会改安装时间，原 `OUT` 拒绝续写，只能 `--fresh`。

## 四步

1. **准备 profile。** 跑 `inspect` 看当前画面（应用不在前台时会先启动它），读文字大纲和候选清单（`D` 危险词，`X` 拒点或广告）。首次启动有协议、引导、必选项（城市、兴趣）时，用 `drive` 一路点到应用的正常首页，边点边记。然后把 profile 写到 `android_traverse_screenshots/_aft/input/profile.json`（`run` 默认读这里），格式见 [profile.md](references/profile.md)，示例见 [profile.example.json](assets/profile.example.json)：
   - **根页（`root`）** 是首次启动走完之后、每次冷启动都会落到的那一页，通常是带底部导航的首页；选择器写这页上一定在的控件。执行器迷路时靠“冷启动 → 根页 → 按记录路径重放”找回去，根页冷启动回不去，整轮就废了。
   - **启动配方（`start_recipe`）**：协议、引导、首次必选项这类首次启动才出现的页面，写成“出现某控件就点某控件”的规则，不能当根页。要这些页面的截图，开跑前用 `drive` 手动 `capture` 一张。
   - **拦截（`deny`）**：只拦“点这一下就保存、添加、关注、收藏”的那个控件。选择类列表（地区、分类、多级目录）只拦最末一级，中间层放行，拿不准时读该列表的点击处理源码。各层共用同一个 id、规则分不出哪一层是最末一级时，整列拦掉，并在第 4 步把每个中间层各手驱采一张。危险词控件、确认类按钮（确定、完成、保存）、id 里带 delete/del/clear/remove 的图标执行器默认就不点；“编辑”“设置”“筛选”这类只进入模式或页面的入口不要拦。`text` 按屏幕完整文字精确匹配。
   - **业务读数（`business_readings`）**：当前账号、所选地区这类一变就说明数据被改了的文字，选首页上固定显示的那个。
   - 带可点格子的横向内容条写 `extra_containers`（只读横向条执行器会自动采）；范围上限写 `limits`。
2. **跑。** 用 Bash 的 `run_in_background` 启动 `run`（不要前台等它跑完），用 Monitor 盯输出里的 `AFT_MODEL_REQUEST` 和进程结束；没有 Monitor 时按间隔读后台输出。出现 `AFT_MODEL_REQUEST` 时读 [popups.md](references/popups.md)，把决策写到该请求目录下的 `decision.json` 再 `respond`，继续读原进程输出。运行期间不要执行 `drive`、`inspect` 或任何 ADB 命令；可以同时做不碰设备的事：预拟审阅（名称、看到的副作用控件），把第 4 步要补的状态写成 `drive` 命令。
   - `halted_drift`：业务数据被改动、冷启动后仍没恢复，执行器已停下。按报告“漂移嫌疑点击”（排最前、标“点完页面自己关闭”的最可能）把改数据的控件写进 `_aft/input/profile.json` 的 `deny`，用 `pm clear` 或 `drive` 把数据恢复，再执行 `run` 续跑；执行器先复核读数，没恢复会再停。审阅或续跑时加过的 allow/deny 之后一直生效（只增不减），要取消某条 deny 就用 allow 放行。因拦截规则到不了的页面，报告单独列出，不要写进 retry。不要删 `business_readings` 来绕过。
   - `paused_model` / `blocked_user` 见 popups.md；`halted_breaker` 是连续恢复失败，排查原因后续跑。设备掉线先恢复设备，同一原因重复失败时先定位，不要反复重启遍历。
3. **一次性审阅。** 读 `_aft/report.md`，把审阅写到 `_aft/input/review.json`，执行 `run --review android_traverse_screenshots/_aft/input/review.json`：
   - 被抽样的列表：各项是不同功能入口（指数、设置项、分类入口）才把报告给的整列规则放进 `allow`；内容数据（关键词、商品、地名、日期）保持抽样。
   - 确认类按钮（确定、完成、保存、对话框里的回答、表单页的登录）不放行：点了只会提交当前选择，采不到新页面。危险操作入口只有在用户已授权、且只会打开确认框时放行，确认框只截图后取消。
   - 新发现的副作用控件写 `deny`；不可达或失败的页面写 `retry`（page_id）；要改名的写 `labels`。
4. **手驱补采与交付。** 只补自动遍历到不了的状态：要输入、登录、复杂手势的，以及第 1 步因分不出层级而整列拦掉的选择列表的中间层（每层一张；报告“整列拦截的列表”会列出这些列表）。用第 2 步写好的命令，一条 `drive` 串完一组状态（每个状态一个 `capture`），不要一步一调；某一步失败时 `drive` 会停在那里（输出 `STOPPED`），按提示从失败处接着写。`start` 会按启动配方走到首页，之后不要再写配方里的点击（例如“同意”），否则找不到控件会停下。`text` 只能输入英文、数字（adb 限制），搜索用英文或拼音关键词。交付：产物目录 `android_traverse_screenshots`、`_aft/gallery.html`、`_aft/report.md`。

**模型回合预算：** 开跑前 2–4 回合，结束后 1–3 回合，运行中只处理弹窗请求。

## 弹窗

执行器自己这一下点击打开的弹层（日期面板、筛选面板、确认框、滚轮）是被测页面的一个状态：照常截图、探索、用取消/关闭/返回关掉，从不点确认类按钮，不问模型。已登记成页面的弹层也不问。系统权限框由执行器处理：一般权限允许，定位拒绝（`grant_location: true` 时允许）。只有不是当前点击造成的未知弹层（广告、评分、更新提示、启动时挡住根页的页面）才产生 `AFT_MODEL_REQUEST`。普通引导、信息提示、广告关闭由模型按内容和后果自行处理，不转给用户；真实支付、敏感数据外传或任务外破坏性操作缺少授权时才交接。

## 质量底线

1. **不确认身份就不记账。** 每张截图、每条边都基于点击后新做的 dump；认不出来就走恢复梯：返回 → 从祖先页面重放 → 冷启动后从根页重放；仍失败记为不可达，不按猜测命名。
2. **业务状态变了就先恢复。** 能看到读数的 dump 都核对 `business_readings`；变了先冷启动一次，仍不对就 `halted_drift`。返回和复位不点“确定 / 保存 / 提交”。
3. **连续失败就熔断。** 连续 3 次恢复失败或回不到根页，整轮停下并保留断点。

输入框草稿和数字变化不算新状态；同模板不同内容只补一张实例截图；重复控件（列表行、关键词、日期格）按控件族抽样，被抽样或拉黑的都列进报告。滚动证明不出来、找不到控件、截图失败只记缺口继续跑；当时没读到画面的失败（空白 WebView、点后 dump 失败）在收尾前自动重试一次。

## 安全

- 默认不点危险词控件（删除、清空、注销、退出登录、支付、购买、加入购物车、充值、开通、订阅、拨打、举报、发送、发布、提交、分享、下载、重置、获取验证码、一键登录等）、广告入口、输入框和确认类按钮，全部列进报告。确认类包括：确定、完成、保存这类按钮；“总是 / 始终 / 仅此一次 / 不再提示”这类记住或执行选择的回答；系统对话框里取消以外的按钮；有输入框的页面上的登录、注册按钮（别处的登录入口照常点开）。词表只判断按钮文字：长段文字（标题、简介）不按词表判断，英文确认词只认开头（Save changes 是按钮，How to Save Money 是标题）。开关、复选框点过后会复位。
- 测试机：首次 `run` 预授权运行时权限（定位除外）；`grant_permissions: false` 时权限弹窗全部交给模型。App 退到桌面或别的应用时执行器自己冷启动回去。ANR 点两次“等待”无效就关闭应用重启。不要改系统设置来绕过弹窗。
- 只用当前账号和数据；重装、清数据、登录、造数据需要用户明确要求（`halted_drift` 后恢复本次运行自己改掉的数据例外）。
- 一台设备同一时间只能有一个 `inspect` / `run` / `drive` / `burst`；`respond` 不占设备锁，只提交一份响应。
- 不要修改本 skill 自带的脚本或安装目录。执行器行为不符合预期时，记下现象和证据（命令、`_aft/events.jsonl`、报告），停下来报告，不要自己打补丁绕过。

## drive

```bash
python3 scripts/android_fast_traverse.py drive --serial SERIAL --package PKG \
  "tap 我的; tap 设置; capture 设置页; back; tap rid:search_input; text snake; wait 2; capture 搜索结果; outline"
```

步骤：`outline`、`tap <文字|rid:..|desc:..|@x,y>`、`long`、`back`、`swipe up|down|left|right [rid:<id>|@x1,y1,x2,y2]`、`text <内容>`、`wait <秒>`、`capture [名称]`、`recapture <PAGE_ID> [名称]`、`start`。危险词控件要写 `tap !文字` 才会点，且只在用户授权后这样做。`capture` 与自动采集同一契约（滚主容器和横向条，`meta.json` 字段相同），写成 `manual_NNNN_<Activity>/`，与自动单元共用编号和 `index.json`。细节见 [artifacts.md](references/artifacts.md)。一条 `drive` 串很多步时可能超过两分钟，Bash 调用把 `timeout` 设到 `600000`（10 分钟）。

## 命令

```bash
python3 scripts/android_fast_traverse.py inspect  --serial SERIAL --package PKG
python3 scripts/android_fast_traverse.py run      --serial SERIAL [--max-minutes N] [--model-timeout 180]
python3 scripts/android_fast_traverse.py run      --serial SERIAL --review android_traverse_screenshots/_aft/input/review.json
python3 scripts/android_fast_traverse.py run      --serial SERIAL --fresh
python3 scripts/android_fast_traverse.py respond  --request-id REQUEST_ID --decision android_traverse_screenshots/_aft/model_requests/REQUEST_ID/decision.json
python3 scripts/android_fast_traverse.py report
```

以上命令都在产物目录的父目录下执行；产物目录要放到别处时，所有命令都加 `--out <父目录>/android_traverse_screenshots`（名字不能变），`run` 的 profile 默认跟着读 `<OUT>/_aft/input/profile.json`。定时连拍 `burst` 用于观察一段时间内的变化，不替代遍历，输出固定在 `OUT/_aft/bursts/<名称>/`，用法见 [burst.md](references/burst.md)。

## 产物

```
android_traverse_screenshots/
  index.json                 当前有效单元（下游唯一入口，路径都相对本目录）
  page_NNNN_<Activity>/      自动遍历单元：screenshot.png view.xml screenshot_scroll_<k>.png view_scroll_<k>.xml meta.json
  manual_NNNN_<Activity>/    手驱单元，结构相同
  _aft/                      过程记录与模型输入（input/profile.json、input/review.json 等），不是交付产物
```

NNNN 是 4 位全局序号，page_ 和 manual_ 共用、只增不减。顶层不放其他文件。下游跟随 `index.json` 的路径，不从目录名推断单元含义。完整命名规则见 [artifacts.md](references/artifacts.md)。
