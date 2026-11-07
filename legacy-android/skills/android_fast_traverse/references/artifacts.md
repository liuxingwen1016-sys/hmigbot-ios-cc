# 产物与账本

## 目录与命名规则（与下游约定，固定不变）

一次任务只有一个产物根目录，名字固定为 **`android_traverse_screenshots`**，放在任务所在目录下（默认是执行命令时的当前目录，即 `./android_traverse_screenshots`）。下文记作 OUT。所有命令的 `--out` 默认就是它；传别的名字会被拒绝。OUT 就是交付给下游的产物根目录。

```
android_traverse_screenshots/                      OUT；顶层只有下面四类东西
  index.json                                       当前有效的全部采集单元（下游唯一入口）
  page_NNNN_<Activity>/                            自动遍历的单元
  manual_NNNN_<Activity>/                          drive 手驱补采的单元
    screenshot.png          view.xml               首屏
    screenshot_scroll_<k>.png  view_scroll_<k>.xml 之后各屏，k = 1, 2, …（先竖向滚动，再接只读横向条）
    meta.json                                      单元说明（字段见下文）
  _aft/                                            过程记录与模型输入，不是交付产物
    input/
      profile.json        模型写的 profile（run 默认读这里）
      review.json         模型写的审阅（`run --review` 传这个文件）
    profile.json          执行器实际生效的 profile（含沿用下来的 allow/deny），自动生成，不要手改
    state.json            断点：页面注册表、DFS 栈、已探索控件、跳过项、缺口、基线读数、计数器
    sessions.jsonl        每次命令的开始/结束记录
    edges.jsonl           每一次真实点击与返回：forward / known / up / self / view_state / view_known /
                          view_base / external / return（含 recover_back，带实际落点 landed）/ replay / navigate /
                          restart / restore_toggle / manual
    events.jsonl          运行事件（冷启动、瞬态处理、缺口、漂移、失败、path_blocked）
    report.md  report.json  gallery.html  drive_counters.json
    popup_rules.json      已验证、允许记忆的弹窗规则
    inspect/inspect_<会话号>_<序号>.png|.xml      inspect 的截图与 XML（准备阶段的现场）
    anomalies/<缺口代码>_<序号>.xml|.png          异常时保留的现场
    model_requests/<请求号>/
      request.json  before.xml  before.png       运行时模型请求与处理前原始证据
      decision.json                              模型写的决策（再用 respond 提交）
      response.json                              respond 原子提交的决策
      result.json  after.xml  after.png          生命周期结果；有后置观察时保存处理后证据
    revisions/<PAGE_ID>/rev_NNNN/                新修订及 previous_meta.json；index.json 可引用这里的文件
    attempts/<PAGE_ID>/rev_NNNN/                 没替换原有效版本的较差/失败补采证据，不进 index.json
    previous/NNN/                                run --fresh 归档的上一次遍历（页面目录含手驱单元、index.json 与它的 _aft 账本；
                                                 input/、popup_rules.json、sessions.jsonl、inspect/、bursts/ 留在原处）
    bursts/<名称>/burst.json  screenshot_NNN.png  view_NNN.xml   定时连拍（每次一个新子目录）
```

命名细则：

- `NNNN` 是 4 位全局序号，`page_` 和 `manual_` 共用一套编号，只增不减，不复用；`--fresh` 归档后新遍历也接着编号。
- `<Activity>` 是 Activity 的类名短名（去掉包名，只保留字母、数字、下划线），例如 `MainActivity`。它只是可读后缀，不唯一：同一个 Activity 下会有页面、视图态、实例等多个单元。单元是什么、从哪来，看 `index.json` / `meta.json` 的 `label`、`aft.kind`、`aft.parent`、`click_path`，不要从目录名推断。
- 帧文件名固定：首屏 `screenshot.png` / `view.xml`，其余 `screenshot_scroll_<k>.png` / `view_scroll_<k>.xml`，PNG 与 XML 一一对应。哪些帧是横向条，见 `meta.json` 的 `aft.capture.extra`。
- 路径都相对 OUT。单元被重采得更好时，`index.json` 会指向 `_aft/revisions/` 下的文件，下游要跟随 `index.json` 的路径，不能假设 `PAGE_ID/screenshot.png` 一定是最新版。
- `_aft/` 整个目录下游都不读。模型自己写的文件只放 `_aft/input/`（profile、review）和 `_aft/model_requests/<请求号>/decision.json`；OUT 顶层不放任何其他文件，报告会列出顶层多出来的东西。
- `<名称>`（连拍）只用字母、数字、下划线和连字符；不给时用 `burst_<年月日_时分秒>`。

`burst` 的输出固定在 `OUT/_aft/bursts/<名称>/`（不写 `--out` 时按 `--label` 自动取名，写了也必须在这下面），包含 `burst.json`、`screenshot_NNN.png`、`view_NNN.xml`；
它是时间序列原始证据，不进入上面的 `index.json`，也不计作页面或滚动视口。
逐帧状态、配对限制、错误和审阅方式见 [burst.md](burst.md)。

`model_requests/` 是弹窗处理的原始证据，不分配页面编号，不进入 `index.json`，不算完成业务弹窗的探索。模型决定 `continue` 后，该业务弹窗仍按正常遍历采集和登记；请求中已有 PNG/XML 不替代有效页面证据。文件协议与语义见 [popups.md](popups.md)。

## 一个任务，一份有效产物

同一应用基线的首次遍历、续跑、review 补跑、手驱补采共用固定 `OUT`。自动遍历已有断点时，`run` 自动续跑；`--resume` 保留为显式写法。手驱开始的目录也可继续自动遍历，手驱证据不会使尚未探索的控件被标为完成。

- 全局编号跨 `page_` / `manual_` 共用，分配时同时检查账本与磁盘冲突；Activity 后缀只是可读名称，不是唯一身份。
- 输出目录锁保护编号、断点和索引；设备锁保护真实操作，二者分别约束不同冲突。原 `run` 在等模型时仍持有两把锁；`respond` 不获取这些锁或写会话，只向当前请求独占发布 `response.json`。
- 已记录包名、应用版本/安装更新时间、密度不匹配或无法确认时拒绝续写，不把不同安装的截图混成一份真值。同一任务要从头重来（重装、换包、根页选错）时用 `run --fresh`：当前遍历移到 `_aft/previous/NNN/` 留档，在同一 `OUT` 重新开始，不另开目录。包名不同属于另一个任务，才在另一个父目录下另建 `android_traverse_screenshots`。
- 不自动整理既有多个 run，也不覆盖它们。历史整理需要单独校验身份、保留有效证据并重建索引。

### 复用、补充与修订

自动与手驱共用登记逻辑，采集尝试和当前有效单元分开记账：

| 情况 | 结果 |
|---|---|
| 唯一匹配的已有单元，成对 XML/PNG 全部相同，原证据质量不低 | 复用原单元，追加来源/访问记录 |
| 同一身份、原有 XML/PNG 对完整包含在新证据中 | 保留原文件路径，只存新增帧并修订该单元 |
| 同一身份，整组新证据合格但画面有更新 | 整组修订，不把不同快照的滚动帧拼成一组 |
| 补采截断、质量下降或帧数减少 | 原有效单元不变；本次证据保存在 `attempts/` |
| 无唯一匹配 | 分别保留；有多个匹配候选时记录 `suspected_duplicate` 供审阅，不强行合并 |

身份匹配要求包、Activity、层级、密度、应用基线、业务读数/漂移上下文一致，并有精确应用层级重叠（包含原文、控件状态和位置）。自动遍历的不同交互入口/类型还受其语义分类约束。**不按文件名、Activity、裸 XML 哈希或数字归一化单独合并。** 同模板不同城市、数字更新、WebView/自绘画面等没有充分证据时可能仍保留为独立单元；这不是通用视觉近重复消除器。

手驱 `capture` 先用新 dump 和首帧 PNG 尝试快速复用；要求已有范围覆盖本次请求、证据未截断/降级且首帧唯一匹配。WebView/不透明自绘内容禁用这条捷径。没有命中才滚动采集并登记；不为去重额外做一轮专门的设备检查。

需要明确更新指定单元时，在真实到达其画面后执行 `recapture <PAGE_ID> [名称]`。它跳过采前快速复用，仍要求当前证据与目标身份唯一匹配；不能用它强行将无关画面归入旧 ID。旧截图不覆盖，新修订保留旧 meta；单元的 ID、原始分类与路径来源稳定，`meta.json` 和 `index.json` 指向当前有效文件。**读取者要跟随这些路径，不能假设 `PAGE_ID/screenshot.png` 总是最新版。**

## meta.json

路径都相对 OUT：

- `page_id`、`label`、`timestamp`、`device`、`dpi`、`density_factor`
- `activity_info.current_focus`、`activity_info.resumed_activity`
- `clickable_count`、`clickable_elements`（含 `scroll_index`、危险词、拒点标记）
- `scroll_container_bounds`
- `screenshot`、`view_xml`、`screenshots[]`、`view_xmls[]`
- `click_path[]`：从根页到这里的真实点击路径，每步含 `from`、`element`、`center`、`resource-id`、`text`、`content-desc`、`scroll_info`。视图态的最后一步就是切换到它的那个控件
- `came_from`、`trigger_element`
- `aft`：
  - `kind`：`page`、`view_state`、`instance`、`danger_dialog` 或 `manual`；
  - `parent`、`activity`、`layer`（同窗口浮层或弹窗窗口）；
  - `capture`：帧数、停止原因（`screen_changed` 表示采集中检测到换页/换窗/浮层变化；`identity_unconfirmed` 表示焦点、原容器或页面外壳连续性不足，不能确认为原页滚动；两者都拒收该帧并停止后续容器）、`proof_degraded`、`container`、`extra`（profile 声明的容器，以及 `auto` 标出的自动发现的只读横向条）、各帧的滚动判据；
  - `capture.observations[]`：每张已保存帧对应的真实 dump 序号、Activity、窗口/token 与浮层信息；
  - `capture.last_observation`：最后一次实际 dump，可能是未保存的到底帧或被拒收的异页，不能直接当作本单元的最后截图；dump/输入失败时为空；
  - `capture.interruption`：身份中断的原因、容器、步骤与前后身份。实际异常 XML 由 `capture_truncated` 缺口的 `evidence` 引用，放入 `_aft/anomalies/`，不进入页面索引或候选；
  - `readings`：这一单元画面上的业务读数；
  - `drift`：采集时尚未恢复的业务读数漂移；
  - `via`：从父页过来时点的那个控件（手驱为 null）；
  - `registry`：产物身份与修订信息。`frame_keys` 保存应用层级/XML/PNG/成对文件指纹，`context` 保存基线上下文；`sources` / `visits` 记录自动或手驱来源、时间、会话、名称与访问路径；`last_action` 为 `created` / `reused` / `revised` / `retained`；`revisions` / `retained_attempts` 指向历史证据；`suspected_duplicate` 是无法唯一决定时的候选 ID，不是已确认重复。

手驱单元的 `click_path` 是上次 `start` 之后的手驱步骤（点击、返回、滑动、输入长度）。

## 缺口代码（state.json 的 gaps）

常见的有 `not_found`、`unreachable`、`proof_degraded`、`capture_truncated`、`drift`（附当时的 `suspects` 嫌疑点击）、`side_effect`、`commit_like`、`view_cap`、`page_cap`、`anr_closed`（ANR 两次等待无效，已关闭应用重启，附现场 XML；触发它的控件结果记 `anr`，不自动重试）、`reading_removed`（续跑时删掉了某个业务读数），以及 `webview_blank`：点开后 WebView 一直没有文档内容（标题栏 `about:blank`，或 WebView 下除文档标题外没有网页文字），等过之后仍是空白，不收成页面，只记缺口和现场 XML。

`scroll_interrupted` 表示候选定位或采集前回顶中断，`purpose` 区分阶段；这些动作不生成滚动截图，但同样保留异常 XML（有可用 dump 时），清空操作缓存后由恢复流程重新定位。`capture_truncated` 的停止码还可能是 `input_failed`、`dump_failed`、`png_failed`；不能把这些结果当作已采到底。

## 计数口径

- `report.delivered` 来自当前 `index.json`：有效单元数、按类型分布、有效截图/XML 帧数。目录里的归档、较差尝试和 burst 不计入其中。
- `state.artifact_stats` / `report.capture_stats`：登记尝试 `captures_attempted`，结果分别为 `created` / `reused` / `revised` / `retained`；`ambiguous` 为累计身份歧义次数，与前述结果可重叠。它们不是唯一页面数，也不是所有设备命令失败的次数。旧账本未记录时报告为未知，不从现有文件量反推。
- `report.suspected_duplicates` 单列当前有效单元里带疑似重复标记的项，供模型审阅；不把累计 `ambiguous` 当作当前待审单元数。
- 自动遍历的 `counters.captures` / `counters.frames` 是历次自动采集工作量，与当前有效交付量分开显示。手驱补图不等于自动覆盖。
- `manual_device_counters` / `manual_elapsed_s` 累计手驱设备工作量与墙钟时间，报告单列 `manual_device_seconds`；不混进自动 `device_counters`。旧账本没有单独记录的手驱时间显示为未知。
- `state.popup_stats` / `report.popup_stats`：`requests`、`cache_hits`、`actions`、`continues`、`handoffs`、`timeouts`、`failures`、`stale` 和 `wait_s`。主动中断另计 `interrupted`，不混入决策失败次数。`report.model_wait_s` 单列模型响应的等待墙钟，已包含在 `elapsed_s` 中，不计入设备时间；它包含宿主读证据、推理及提交等等待，不能等同于推理时长。`model_inference_s` 为未知，不填 0。旧账本没有弹窗计数时保持未知。
- `state.model_request` / `report.model_request` 保存最近一次请求的 ID、绝对请求路径、会话、指纹、阶段和状态。`waiting_model` 是原进程的中间状态；`paused_model` 是等待超时或决策未完成的断点，`blocked_user` 只用于模型明确交接，均不应报成已完成或恢复熔断。
- `explored`：对候选控件的真实点击次数，不含返回、重放、冷启动、复位。
- 设备时间按用途拆分（`device_counters.purpose_time`）：
  - `identify`：点击后识别落点；
  - `verify`：返回后核对；
  - `locate_scroll`：为找控件而滑动；
  - `capture_first` / `capture_scroll`：采集；
  - `rewind`：视图态采集前回到顶部；
  - `restart`、`replay`、`return`、`transient`、`start`；弹窗留证、核验与动作按实际用途计入设备工作，不因模型决策而隐去。
  
  `focus:` 开头的计时包含在就绪等待（`ready_wait`）里，汇总时不能重复相加。

