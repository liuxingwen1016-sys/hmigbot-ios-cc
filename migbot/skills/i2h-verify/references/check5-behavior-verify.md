# 行为验证（CHECK-5）

## 已提供原生 UITest runner 的项目

用 `/i2h-verify behavior` 运行首轮功能验证。需要修复时，按失败场景定位并修复，再用
`/i2h-verify recheck` 指定要复测的场景。两条命令都可汇总项目已有的原生设备回执。
runner 的每份 `results.json` 必须提供
`device`、`hap_sha256`、`planned_cases` 及带 `status` 和 `passed_steps` 的 `cases`，
原始 HarmonyOS UITest 布局和对应回执同目录。首次使用完整范围的 runner 回执。
原生 runner 优先使用稳定控件 ID。图标或自定义 Button 的文案只暴露在子节点时，
可复用 `scripts/uitest_action.py` 的 `label_action_center`，从当前原始树找到
同窗口、可见且包含该文案的实际 Button。定位冲突时保留失败，点击后继续核对目标状态。
自绘动作由可点击 Row 承载时，传入明确的 `container_id`，例如
`label_action_center(tree, "保存档案", container_id="saveBean")`。仅在唯一可见容器内查找，
拒绝裁切的动作和重复容器。调用前仍须校验应用前台，并核对点击后的目标状态。
原生 TabBar 将 `selected` 暴露在标签父节点时，可用同一模块的
`selected_tab_label` 读取真正选中项，再与实际页面到达断言一起判断。
自绘底栏传入其稳定容器 ID，例如 `selected_tab_label(tree, labels, container_id="rootFloatingTabBar")`。
工具从容器内的选中节点及其可见文案核对当前标签，容器外文本和隐藏节点不参与判断。
滚动后从 `visible_tab_bar_bounds` 取得可见 TabBar，再用 `overlaps_obstruction` 核对整个控件框是否与栏相交。原生树省略页签 ID 时仍可核对。遇到原生树已经裁切的控件框，应比较首屏和滚动后尺寸，并用截图复核。
`fully_visible_control` 可作为滚动停止条件。有 `origBounds` 时要求可见框与原框一致，并避开已确认的底栏等遮挡框。这样被父滚动区裁切的控件即使显示为可见、且框未碰到底栏，也不会被提前点按。

Plan 验收的 `fully_visible` 使用与 `present` 相同的控件选择器。
当同一行或卡片必须同时展示多个字段，在断言中使用
`"within":[{"ancestor":{"type":"Row","clickable":"true"},"present":[{"text":"标题"},{"text":"评分"}]}]`。
一组选择器必须在同一个可见祖先的子树中全部匹配。隐藏子树以及分散到不同卡片的字段不满足该断言。
在首次进入页面时保存未滚动布局，并将该布局和对应步骤写入断言。滚动后可达使用另一个步骤和布局。
门禁要求每个选择器唯一匹配，可见框与 `origBounds` 一致，原框完整落在根视口内，并避开可见原生 TabBar。
键盘、自定义浮层等已知遮挡可用 `obstructions` 声明。每条声明必须在同一份树中匹配到可见遮挡框。
布局缺少对应几何信息时保留未通过。图层未暴露在树中时仍须复核截图。

同名列表项用同一个可点击行内的组合字段定位。就绪判断和点击都限制在选定行内，避免全量回归新增同名数据后点到另一条记录。长详情中的分数、标签和笔记分别等待并记录所在视口。只有源验收要求同屏可见时，才在同一份树上要求全部匹配。

有多个稳定子标签的自绘记录行可用 `grouped_row_action_center(tree, labels, bundle=...)`。
传入至少两个原生树中的精确文本，选填列表 `container_id` 和自绘遮挡层
`obstruction_ids`。定位只接受当前前台窗口内唯一、完整可见且能单独点击的记录行。
汇总文案、日期拼接格式和历史控件 ID 可以变化。点击后继续断言实际到达状态。

对分享等由宿主桥接的操作，定位和滚动到入口只算到达证据。点按真实入口并断言约定的系统面板或用户可见结果后才记行为通过。检查分享内容时使用测试数据，核对面板预览或明确授权的测试接收端，再取消返回应用。设备无法观测面板或载荷时分别记录证据缺口。

系统分享也可能以 `UIExtensionComponent` 嵌在已聚焦的应用窗口中。记录点按前面板未显示，点按后在系统面板子树查找独立的标题和预览锚点，取消后同时确认面板消失与应用原页面恢复。UITest 的 `uiInput keyEvent Back` 区分大小写，遇到 stdout 的 `Invalid parameters` 应按命令失败处理，即使退出码为 0。
取树后、截图或按控件触控前，用 `require_focused_app` 确认当前包拥有前台页面。
遇到其他包、无有效前台或焦点冲突，结束本轮设备操作，保留已完成场景和未跑分母。

> **注意**: `uitest_action.py` 是仅供导入的库模块，不支持命令行调用。
> 应在测试脚本中 `import` 后使用其提供的函数。

捕获 `ForegroundError` 时，把 `windows` 写入场景的 `focused_windows`，正式汇总保留窗口的包名和页面路径，便于区分首次启动的系统页面、
应用退出后返回桌面和其他应用抢占。应用退出时检查本轮应用故障日志。若出现系统首次
使用或授权页面，保持当前状态，等待操作者完成系统设置。

原生 runner 执行 HDC 安装或应用启动后，使用 `uitest_checkpoint.py` 的
`hdc_failure_details` 同时检查退出码和 HDC 错误正文。锁屏、设备离线需要作为
对应环境阻断保留，终止本次应用就绪等待。回执保存设备 ID、命令和原始错误供回看。

原生 runner 在冷启动或操作后可用 `scripts/uitest_checkpoint.py` 的
`capture_checkpoint`。提供项目自己的布局采集函数和业务就绪断言，使用返回的同一份原始树
执行后续断言。传入批准的截图名集合，只有匹配成功且在集合内才保存原图，空集合只保存树。
超过就绪期限才返回的布局样本不能让检查点通过。注册正式到态回执回调时，截图后再检查
一次前台和同一状态断言，通过才绑定截图后的原始树；状态变化时回执回调不会运行。
HDC 取证回调使用同模块的 `capture_uitest_artifact`。例如将
`capture_uitest_artifact(path / f'{name}.json', kind='layout', send=send)` 作为
`read_layout` 的实现，截图回调使用 `kind='image'`。目标目录应已创建。`send` 继续绑定本轮授权设备，
检查退出码和 HDC 错误正文，保留实际命令并为每次调用设超时。下载并校验后，工具原子替换本地证据，
再删除本次生成的唯一远端文件。下载失败保留原有本地证据，异常的 `remote_uitest_artifact` 可用于诊断；
清理失败发出包含远端路径的警告，已校验的本地证据仍可使用。
布局函数为单次设备命令设置超时。状态等待耗尽时报告场景失败，设备命令超时时报告
`ERROR`，填写 `device_timeout.seconds` 并结束本轮设备操作，保留已完成和未运行的场景。
失败后若清理了该场景创建的测试数据，可在原回执写入 `fixture_recovery.status` 和失败原因。
汇总保留清理结果、原始失败及后续场景的实际终态。
若开始执行前已检查或恢复测试夹具，可在运行回执记录 `fixture_setup.status`。
准备失败时填写 `fixture_setup.reason`，保留完整 `planned_cases` 并停止执行，场景结果保持为空。
正式汇总保留准备失败原因，计划场景记为 `NOT_RUN`。

分段运行从明确的场景边界写出 `PAUSED_AT_SCENARIO_BOUNDARY` 检查点，保留完整
`planned_cases`、已有通过场景和 `next_scenario`。恢复前重新检查该边界的设备夹具。
继续运行的回执记录 `resume_from` 的路径、摘要、`prior_passes`，并仅列出本次运行的剩余场景。
汇总按顺序传入检查点和续跑回执，核对设备、签名包、runner、夹具、批准范围及场景顺序。
设备中断、夹具失败或已开始变更数据的场景不能当作已完成边界恢复。

原生失败回执可附 `failure_diagnostic`，包含稳定的 `stage` 和可选的原生错误码字符串 `code`。
例如 OCR 可记录 `image_load`、`image_decode`、`recognition`、`camera_setup`、
`result_wait` 或 `editor_verification`。调用签名 HAP 内的固定样本时，可在场景上附
`"package_input":{"member":"resources/rawfile/sample.png","sha256":"<64 位小写十六进制>"}`。
行为报告从签名 HAP 的 ZIP 成员复算摘要。成员缺失、重复或摘要不符时拒绝回执。
以选图或实时取帧为输入的场景不填写这个字段。该字段用于确认样本身份，识别与回填结果仍需各自的运行证据。
保留原始 `reason` 和场景状态。图片 OCR 返回原生识别失败时，按 `recognition` 保存
失败和原生错误码。页面可能复用「实时扫描不可用」一类提示，归因以本场景调用与原始日志为准。
只有设备证据确认缺失具体能力时，才使用 `BLOCKED` 和对应的 `device_capability`。
场景依赖 Core Vision Kit OCR 时，在启动识别前调用 `uitest_checkpoint.py` 的
`core_vision_ocr_preflight(send)`。沿用当前已授权设备的 HDC 回调，并保存探测命令与原始输出。
设备明确报告 `emulator` 时，使用返回的场景阻断记录。场景与 AC 保留在各自的分母中。
行为报告保留 `failure_diagnostic.device_model` 和 `failure_diagnostic.reference`。
其余型号仍执行识别并保留真实失败诊断。相机权限、后摄档位和手动输入继续各自验收。
华为的设备限制见 [Core Vision Kit 文档](https://developer.huawei.com/consumer/en/doc/doccenter-capabilities/core-vision-introduction/)。
只观察到点击后的页面时继续等待相机预览、明确的错误或权限结果，等待耗尽则保留未验证。
回到扫描页可作为回退行为的证据，不能抵消识别失败。
只有部分场景依赖某项夹具时，在执行相应场景前检查条件。将结果写入
`case_fixture_setup`，以 `planned_cases` 中的场景名为键。失败项写
`{"status":"FAIL","reason":"所需记录未创建"}`，该场景在 `cases` 中留空，
其余具备条件的场景照常执行。汇总将失败准备项保留在分母内，状态为 `NOT_RUN`，
并在该场景的 `fixture_setup` 中写出原因。禁止同时报告该场景已执行。

```bash
python3 .claude/skills/i2h-plan/scripts/acceptance_plan.py behavior \
  --signed-hap path/to/signed.hap --device DEVICE_ID --run path/to/results.json
```

批准计划包含 Hypium 逻辑绑定时，在同一次汇总调用中附加
`--hypium-run path/to/hypium/results.json --signed-test-hap path/to/signed-test.hap`。
工具核对两类回执来自同一设备和应用 HAP。严格续跑重读原始逐用例日志，已绑定用例失败、缺席或日志失效都会影响功能验收。

修复并重新签名后，把首轮回执用于保留场景分母。当前包的场景结果来自本次实跑。

```bash
python3 .claude/skills/i2h-plan/scripts/acceptance_plan.py behavior \
  --baseline path/to/first/results.json --case save_rejected \
  --signed-hap path/to/rebuilt.hap --device DEVICE_ID --run path/to/recheck/results.json
```

同包同设备的局部复测可按时间顺序重复传 `--run`。合并时各回执须提供相同的
`runner_sha256`、`fixture_sha256`，以及一致的版本、数据库和采集配置字段。
`fixture_sha256` 应取实际测试数据和初始化配置的摘要。场景以最后一次计划执行为准，
缺少执行结果时记 `NOT_RUN`。新版 HAP 的待测项也记 `NOT_RUN`。

汇总写入 `spec/verify/check5/behavior-summary.json`。场景分母包含首轮计划场景和验收绑定
里的场景，AC 分母取当前完整规格。Plan 完成标记包含有效的 `acceptance-plan.json` 摘要时，
才按该绑定检查场景是否通过、计划步骤是否存在、原始控件树是否匹配。
缺少已批准绑定时保留 `NO_BINDING`，证据不足时保留 `UNVERIFIED`。
对已绑定但未验证的条款，`criteria[].issues` 标明场景未通过、步骤缺失、控件树缺失或不可读、格式错误、断言不匹配。布局问题附步骤及原始文件名，便于只复跑受影响场景。
退出码 `0` 表示全部场景与 AC 通过，`1` 表示已出报告但存在失败或未完成项，
`2` 表示输入或工具错误。功能汇总只写自己的报告，完整流水线验收按原 CHECK 执行。
原 `evaluate` 子命令继续输出 `spec/verify/check5/acceptance-evidence.json`。

选择正式 `--require-behavior` 时，完整验证报告的 CHECK-5 必须为 PASS，并用独立行
`behavior-summary-sha256: <report_sha256>` 引用行为命令返回的摘要。恢复检查会重算
该报告的输入。保留本轮签名 HAP 和原始布局证据供复核。重签名后用新包执行并重建报告。

> CHECK-5 是可扩展的行为验证总入口，技术名称为 `arkts-behavior-verify`。子 verifier 可以在自身契约内修改源码，但任何结果都只进入报告，不参与 CHECK-1/2 与已选 CHECK-3/4 的整体判定、页面 verified 回写或外层失败回环。


## 尚无原生回执的范围

原生CHECK-5通过项目已有UITest回执汇总。没有原生runner、设备或有效原始证据的范围保持未验证/DEFERRED，并报告恢复条件。不得启动Android Oracle替代原生证据，也不得把上述已可执行的原生路径整体标为“iOS尚未实现”。

本次补丁仅接入模态**视觉**取证，见[模态视觉合同](native-modal-visual.md)。没有引入`uitest_scenario.py`、v2场景记录器或`layout_from_step`；已有行为断言、批准范围、需求索引和覆盖校验均保持线上实现。严格视觉的`within`是单次原生观察的容器范围，不能与CHECK-5既有断言绑定混为同一升级。
