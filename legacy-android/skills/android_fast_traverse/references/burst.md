# burst：时间序列取证

适用于等待加载、观察模式切换、用户持续操作期间的截图与 XML 留档。普通页面和长页覆盖仍用 `run` / `drive capture`；不要默认给每个页面都开一轮连拍。

## 执行方式

输出固定在 `android_traverse_screenshots/_aft/bursts/<名称>/`：`<名称>` 取 `--label`（只保留字母、数字、下划线和连字符），不给时用 `burst_<年月日_时分秒>`；`--out` 也可以显式给，但必须在这个位置下，而且是新的或空的子目录。

纯观察，用户可在设备上操作：

```bash
python3 scripts/android_fast_traverse.py burst --serial SERIAL --package PKG \
  --duration 10 --interval 1 --label interaction-01
```

自动触发一个明确动作：

```bash
python3 scripts/android_fast_traverse.py burst --serial SERIAL --package PKG \
  --duration 10 --interval 1 \
  --trigger "tap rid:details" --label interaction-02
```

启动前应用应已在目标起点。被动模式不会自动打开应用或恢复页面，离开目标包仍记录现场。自动触发前重新定位控件并确认目标包在前台；首帧不完整、触发失败或目标未找到时，不猜坐标、不继续动作。

`--trigger` 只接受**一个**动作：

- `tap <文字|rid:ID|desc:文字|@x,y>`；
- `long <同上>`，有限时长的长按，不是持续按住同时抓帧；
- `back`；
- `swipe up|down|left|right [rid:ID|@x1,y1,x2,y2]`。

不支持动作宏、输入文本、重启或循环点击。危险词行为与 `drive` 一致，`!` 只能在用户明确授权后使用。用户物理操作可与被动连拍配合；不要同时运行另一个 `drive` / `run` 或其他 ADB 操作器。CLI 用 serial 互斥，进程退出自动释放，无需删除锁文件。

## 采集与时长

1. 校验有限正数的 duration / interval 和新目录（空目录也可），拒绝覆盖已有文件。
2. 每帧顺序执行新 XML dump → PNG 截图 → 轻量窗口焦点核对。PNG 校验完整块、CRC 和压缩流后才计作成功；分块验证，声明的解压扫描线数据超过 256 MiB 则拒绝。分别保存成功的文件，失败不拿上一帧 XML 顶替。
3. 如带 trigger，在完整首帧后串行执行一次。首帧已耗尽窗口则跳过触发；触发成功后至少尝试一帧结果证据，即使因此超过目标时长。
4. 从前一帧开始时刻计算下一帧：一帧比 interval 快才等待，慢了就继续，不积压补拍。达到窗口后不再开启普通新帧；已开始的操作允许完成。
5. 增量原子写入 `burst.json`。Ctrl-C 尽量写出中断记录并保留已成功文件，不把半成品报成成功。

`duration` 从第一帧开始计，不是硬超时；dump 重试、已开始的帧和触发后的结果帧可让实际耗时超过它。触发后结果帧也遵守 interval，所以 interval 大于 duration 时可能明显超时；通常应让 interval 小于 duration。`interval=1` 表示期望至少隔一秒开始下一帧，不代表 1 fps。如果单次 dump 就要数秒，实际帧率也只有数秒一帧，以清单中实际间隔为准。连拍不是视频，不能保证抓到短暂弹窗、Toast 或亚秒级动效；尤其是 trigger 执行期间不同时截图。

## 产物和判断边界

```text
BURST_DIR/
  burst.json
  screenshot_001.png
  view_001.xml
  screenshot_002.png
  view_002.xml
  ...
```

- `frames[]` 保存逐帧状态、XML/PNG 相对路径、时间、包名、Activity、窗口、内容变化提示与配对检查。序号代表采样次序，不代表页面或滚动序号；缺失的一半留空并记错误，编号不挪用。
- `trigger` 保存动作状态、执行时间和结果；`failures[]` 列出异常。`actual_duration_s`、`actual_intervals_s`、`counters` 和 `device_counters` 都是实际记录值，不拿配置估算性能。
- 顶层 `status`：`completed` 为本轮采样完成；`partial` 表示保留了部分证据但有失败（包括触发失败/跳过）或帧内窗口不一致；`failed` 表示未保存任何 PNG/XML；`interrupted` 为中断。CLI 分别返回 0、1、1、130；参数/目录/设备占用拒绝返回 2。`partial` 不保证有完整配对，具体看 `stop_reason` 和逐帧记录。
- **XML 和 PNG 不是原子快照。** 焦点改变可暴露串窗，焦点不变却不能证明两者是同一瞬间或同一页面；同 Activity 内切换仍需读图和 XML。逐帧内容变化也不自动等于新页面，实时数值、时钟、滚动、模式切换都可能引起变化。

burst 不修改主遍历的 `index.json`、`state.json`、页面数量或原有截图。审阅时先排除失败、帧内跨窗、空白/加载未完成帧，再选操作前后稳定且有意义的帧，说明“动作前 → 动作 → 动作后”并引用文件。不把所有时间帧直接升格成新页面，不将跨页帧伪装成滚动帧。本命令不自动去重或晋升主索引。
