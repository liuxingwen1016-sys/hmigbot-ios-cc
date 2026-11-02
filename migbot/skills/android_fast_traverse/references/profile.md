# profile 与 review 格式

profile 是模型在开跑前写的输入，固定写到 `android_traverse_screenshots/_aft/input/profile.json`（`run` 默认读这里）；审阅写到同目录的 `review.json`。只写应用特有的事实。运行中未知弹窗另走 [popups.md](popups.md) 的请求/响应协议，不必为每次弹窗重写 profile 或重启遍历。执行器会校验字段，未知字段直接报错。

```json
{
  "package": "com.example.app",
  "launch_component": "com.example.app/.SplashActivity",
  "start_recipe": [
    {"when": {"text": "测试环境说明"}, "tap": {"rid": "btn_continue"}, "note": "示例用途：关闭环境说明；使用前由模型核对实际控件、动作后果和任务授权"},
    {"when": {"text": "选择你感兴趣的内容"}, "tap": {"text": "跳过"}, "note": "首次进入的兴趣引导；文字按 inspect 的 XML 照抄"},
    {"when": {"text_contains": "跳过"}, "tap": {"text_contains": "跳过"}, "note": "开屏广告"}
  ],
  "root": {"rid": "bottom_nav"},
  "deny": [
    {"activity": "RegionPickerActivity", "rid": "tv_leaf_region", "reason": "最末一级，点了就保存所选地区；上一级只进入列表，不拦"},
    {"activity": "DetailActivity", "rid": "btn_follow", "reason": "点了就关注"}
  ],
  "allow": [],
  "extra_danger_words": ["一键清理"],
  "business_readings": [
    {"name": "region", "selector": {"rid": "tv_current_region"}},
    {"name": "login", "selector": {"rid": "tv_user_name"}, "activity": "MainActivity"}
  ],
  "extra_containers": [
    {"activity": "MainActivity", "selector": {"rid": "rv_category_tabs"}, "axis": "horizontal", "max_swipes": 6}
  ],
  "limits": {"max_pages": 150, "max_depth": 8},
  "names": {"page_0001_MainActivity": "首页"}
}
```

## 字段

| 字段 | 必填 | 含义 |
|---|---|---|
| `package` | 是 | 目标包名 |
| `launch_component` | 否 | 冷启动用的入口，必须属于目标包；不填时用 `cmd package resolve-activity` 解析出的 LAUNCHER Activity。不要填未导出的内部 Activity，adb 会拒绝启动 |
| `start_recipe` | 否 | 冷启动后到根页之间的条件步骤：画面上出现 `when` 选择器，就执行 `tap`、`back` 或 `wait`（秒）。每次冷启动都会按需应用；这是模型已经确认的动作，不是脚本现场推理 |
| `root` | 否 | 根页上一定可见的选择器。根页是首次启动走完之后、每次冷启动都会落到的那一页（通常是带底部导航的首页）；协议、引导、首次必选项这类首次启动才出现的页面写进 `start_recipe`，不能当根页。不填时，以配方执行完后连续两次结构相同的画面作为根页 |
| `deny` | 否 | 不自动点击的控件规则，匹配字段有 `activity`、`rid`、`text`、`text_contains`、`desc`、`class`，`reason` 写原因。只拦点一下就会保存、添加、关注、收藏的那个控件；危险词、确认类按钮、id 里带 delete/del/clear/remove 的图标默认就不点，“编辑”“设置”这类只进入模式或页面的入口不要拦，选择类列表只拦最末一级 |
| `allow` | 否 | 放行规则，覆盖危险词、广告和 deny，主要用于审阅后整列补点被抽样的列表。确认类按钮（确定、完成、保存）不放行：点了只会提交当前选择，采不到新页面。危险操作入口只有用户已授权、且只会打开确认框时放行，执行器点到确认框为止，截图后取消 |
| `extra_danger_words` | 否 | 追加危险词 |
| `business_readings` | 否 | 业务读数：名称、选择器，可选 `activity`。首次读到的值作为基线；之后只在它所在的那一页、那个位置上核对（同 Activity 的其他 tab、列表里同 id 的文字不算）。冷启动后仍不等于基线时整轮停下（`halted_drift`）。续跑时改了某一项的定义，这一项重新取基线；删掉某一项会记 `reading_removed` 缺口，不要用删除来绕过漂移 |
| `extra_containers` | 否 | 主滚动容器以外需要逐屏采集的容器，例如带可点格子的横向条。主滚动容器自动选择；没有可点格子的只读横向内容条（逐小时预报、48 小时空气质量）也会自动发现，都不用写 |
| `grant_permissions` | 否 | 默认 true：首次 `run` 前授予 App 申请的运行时权限（定位除外），运行中的系统权限弹窗由执行器处理：一般权限点“允许”，定位点“拒绝”。false 时权限弹窗都交给模型 |
| `grant_location` | 否 | 默认 false。true 时定位权限也预授权、弹窗点“允许”；只在要测定位功能时打开，定位可能改掉当前城市这类业务读数 |
| `limits` | 否 | 见下表 |
| `names` | 否 | 给采集单元改名：`page_id` 对应名称 |
| `skip_confirm_in_overlay` | 否 | 默认 true：任何页面上的确认类按钮都不自动点，列入审阅：“确定 / 确认 / 完成 / 保存 / 提交 / Done”、“总是 / 仅此一次 / Always / Once”、系统对话框里取消以外的按钮、有输入框的页面上的登录和注册按钮 |

选择器字段：`rid`（完整 id 或末段名称）、`text`（精确匹配，对可点容器取第一个子文字）、`text_contains`、`desc`、`class`。

弹窗分工见 [SKILL.md 的弹窗一节](../SKILL.md#弹窗)。`start_recipe.when` 尽量用弹窗特有标题或内容定位，`tap` 用实际控件的 rid / 完整文字；`allow` 尽量同时限定 Activity、rid 和文字。`note` / `reason` 记录用途及判断依据，不是自动授权。未知字段会报错，不添加未经实现的“自动接受所有弹窗”开关。

`start_recipe` 是已确认的启动步骤，先于运行时未知弹窗判断。`allow` / review 仍用于普通候选与结束后的补跑；运行中的弹窗决策用 `respond`，其中的 `selector` 只支持精确 `rid` / `text` / `desc` / `class`，不支持 `text_contains`、坐标或脚本。允许缓存的成功动作另存 `_aft/popup_rules.json`，不变成全局 `allow`。

启动配方的 `tap.text` 精确匹配失败后有包含文字的容错回退（事件 `start_recipe_loose`），该回退不保留其他选择器条件。需要固定控件时，优先使用唯一 rid 的 `tap`，由 `when` 限定弹窗；不要把 rid 加 text 误当作不可放宽的组合闸。

## limits（默认值）

| 名称 | 默认 | 说明 |
|---|---|---|
| `max_pages` | 150 | 采集单元上限：页面、视图态、弹窗合计 |
| `max_depth` | 8 | 页面深度上限，到达后只采集，不继续深入 |
| `max_scrolls` | 8 | 每个容器最多滑动的次数 |
| `max_hscrolls` | 12 | 自动发现的只读横向内容条最多滑动的次数；0 表示关闭自动发现 |
| `max_list_items` | 3 | 同构列表抽样：每个列表里连续这么多项都去了同一类页面（或都没反应），其余项就不再点；异构菜单逐项点 |
| `max_candidates_per_page` | 80 | 每页最多探索的控件数 |
| `max_views_per_page` | 15 | 每页最多记录的视图态 |
| `max_instances_per_page` | 2 | 同一模板（例如同一种详情页换了内容）最多补采几张内容不同的实例截图（只采首屏）；审阅放行的列表项不受这个上限 |
| `max_minutes` | 0 | 墙钟预算，0 表示不限；包含模型等待；超出后保存断点并以 `paused` 结束。每次模型响应等待上限另由 CLI `--model-timeout` 设置 |
| `stall_minutes` | 5 | 连续这么多分钟没有新采集单元就结束本轮（记缺口 `stalled`），等模型处理弹窗的时间不算；0 表示关闭 |
| `breaker` | 3 | 连续几次恢复失败后熔断 |
| `settle_s` | 0.35 | 滑动后的稳定等待（秒） |
| `match_threshold` | 0.8 | 页面结构包含率阈值 |
| `volatility_check_s` | 2.5 | 新出现的文字只有一两条时，隔多少秒再读一次屏幕，用于区分轮播文字和真正的视图态 |

## review（结束后一次性审阅）

```json
{
  "allow": [{"activity": "SettingsActivity", "text": "清除缓存", "reason": "用户授权；只会弹出确认框，确认框会被取消"}],
  "deny": [{"activity": "FeedbackActivity", "rid": "btn_submit", "reason": "会真的提交反馈"}],
  "retry": ["page_0012_SettingsActivity"],
  "labels": {"page_0003_MainActivity": "首页·列表模式"}
}
```

`retry` 写 report.md 里显示的 `page_id`（内部键 `P12` 也接受）；报告里“因拦截规则到不了”的页面不要写进来，重试只会撞上同一条规则。review 里的 allow/deny 生效后会保存在 `_aft/profile.json`，之后的续跑一直沿用（只增不减）。`labels` 会同时改写已采页面的 `meta.json` 和 `index.json`。`report.json` 里的 `allow_suggestions` 列出了所有被跳过和被抽样掉的控件，并附好了现成的规则，模型只挑确实需要的那几条复制过来。被抽样的列表另见 `list_allow`：每个列表一条（或一组）整列补点的规则和建议（12 项以内、每项点进去是一个页面、标签不是数字的，建议整列补点）。放行规则按匹配范围生效：写 rid 加 text 只补那一项，只写 rid 补整列。review 只追加规则，不删除已有记录。执行 `run --review android_traverse_screenshots/_aft/input/review.json` 后（同一 OUT 自动续跑），执行器会把新放行的控件重新排进队列，在补跑阶段完成。

显式 `retry` 也用于设备离线等异常留下的失败候选：即使该候选已有探索记录，`observe_failed` 等明确失败结果仍会在指定页重新排队；成功候选不重试，已成功采集的页面不重采。历史 `gaps` 保留，不用删除失败记录制造完整覆盖。

设备离线时，模型先对已有测试设备做有界检查和恢复，确认设备可用后，将有失败候选的页面写入 `retry`，执行 `run --review android_traverse_screenshots/_aft/input/review.json` 定向补缺口（同一 OUT 自动续跑）。重复出现同一故障时先查原因，不无界续跑；无法恢复才报告阻塞与未完成范围。`completed_with_gaps` 不能单独证明请求范围已全部达成，需结合最新补跑结果核对剩余缺口。
