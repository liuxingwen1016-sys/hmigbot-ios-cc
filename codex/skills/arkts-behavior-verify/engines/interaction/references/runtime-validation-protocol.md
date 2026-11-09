<!-- when: fast_fix 准备验收计划或已完成目标源码修复并安装时读取 -->
<!-- topics: independent entry/action/state acceptance, immutable seal, runtime evidence -->

# 目标交互真机验证契约

验收限定在正式 Review 的目标及必要依赖，按实际入口、动作和状态分别报告。普通点击只使用对应后置条件；以下播放/下载场景在领域适用时使用。运行前确认 signed HAP 已安装，记录设备、bundle 和 HAP SHA-256。安装成功不能代替行为验证；未决 scope hazard 绑定到对应场景，不能凭其它入口成功宣告关闭。

## 独立验收：先封存，后只报告

用户要求“跑完 Skill 再真机验证，只报告不修复”时使用本节。修复阶段不读取设备
诊断来调整补丁；两轮结束、构建及一次安装后，先运行 exporter `finalize/validate`。
保留 `result.json/result.lock.json`，验收产物写到 sealed run 目录之外。
用户未授权设备操作时只生成计划，不执行设备步骤。

`acceptance_plan.py` 从正式产物派生验收矩阵，不依赖用户补充问题列表：

```text
python <skill-dir>/scripts/acceptance_plan.py plan --review-plan <out>/baseline/review-plan.json --findings <out>/baseline/baseline-findings.json --repair-plan <out>/round-1/repair-plan.json --repair-plan <out>/round-2/repair-plan.json --out <acceptance>/plan.json
```

只有存在的 repair plan 才传入，不能为凑命令制造空计划。每个真实 consumer 实例、
事件及已知动作/状态保留独立证据；未能推导的条件记为缺口，不猜测业务状态或补造
产品功能。共享 service 修复证据可以引用，但入口可达、按钮状态、动作一致性和
实体身份必须逐项检查。矩阵中未执行项保留 `NOT_TESTED`。

验收前后各冻结一次，以 `--plan <acceptance>/plan.json` 绑定同一矩阵：

```text
python <skill-dir>/scripts/acceptance_plan.py freeze --project-root <arkts_root> --run <out> --plan <acceptance>/plan.json --hap <signed.hap> --identity <acceptance>/identity-before.json --authorization-reference <本次用户验收授权> --out <acceptance>/before.json
```

验收后改用 `identity-after.json` 和 `after.json`。identity 包含 `device/bundle/
version_code/version_name/uid/install_time/update_time` 及原始只读设备证据文件
`evidence`。freeze 重新读取全部受保护源码与构建输入字节，不能复用 size/mtime
哈希缓存；按固定 UTF-8 路径顺序聚合，绑定安装包、结果锁和安装身份。

在 `observations.rows` 中按 `row_id` 记录每个 check 的
`status=PASS/FAIL/BLOCKED/NOT_TESTED` 与证据文件。可达及具体控制操作需记录实际
`target_identity/target_hit_evidence`；数据库回读使用真实 schema/DAO 构造查询，
记录 `dao_schema_evidence/matched_entity_count/identity_predicate`，没有匹配实体
不能解释为空字段。任务输入可用脱敏稳定身份或 URL SHA 与实际 task 身份比对，
不要求系统日志输出原始 URL。一次 toast 只证明失败，不证明底层根因。

```text
python <skill-dir>/scripts/acceptance_plan.py report --plan <acceptance>/plan.json --before <acceptance>/before.json --after <acceptance>/after.json --observations <acceptance>/observations.json --out <acceptance>/report.json
```

report 核对源码/构建输入、HAP、安装身份及 Skill 封存结果未改变，缺行/缺证据不能
通过。验收不修改应用源码，不重新构建、安装、清数据或采取临时绕过后报成功；
发现失败只报告入口、状态、证据和未决原因。不得调用 `record-runtime` 或再次
`finalize` 把独立验收结果写回已封存 Skill 结果。后续修复需新的明确任务范围。

## 播放后置条件

1. 冷启动应用并通过已有到态步骤进入“单集”列表。
2. 打开一个有有效媒体 URL 的单集，记录 `itemId/mediaId`。
3. 点击播放一次；从 `hdc shell hilog` 或应用诊断日志确认同一 `itemId/mediaId` 依次进入 `INITIALIZING/PREPARING` 后到达 `PREPARED` 或 `PLAYING`，且没有紧接着 `ERROR/STOPPED`。
4. 音频必须按固定交互序列验证：播放开始后返回上一页，确认底部播放器条仍存在；再点击播放器条，确认展开播放器出现并显示同一 `itemId/mediaId`。不能用首次播放后的底部条、短暂闪现或日志中的 `playing` 代替展开页。
5. 点击播放器条后等待至少 3 秒再次 dump/截图，确认展开播放器仍可见、仍显示同一单集，且没有被 observer、生命周期回调或共享状态同步重新折叠。视频则确认播放器路由在同样的等待后仍可见。
6. 证据必须分别记录：播放成功、返回后的来源页、返回后播放器条、点击播放器条、展开页及 3 秒后展开页；缺少任一步即不得判定 PASS。

用户报告多个入口时，分别覆盖详情页、列表、队列等实际被报告的入口；记录每条
入口的来源页、动作、item/media 身份、按钮可用状态、命令终态和证据文件。共享
服务通过一次不能替代其它入口的绑定验证。页面初始化不得误弹外部打开方式；
若出现，保留弹窗证据，关闭后再次核对按钮与动作，不能把 dismiss 当成修复。
对多状态按钮同时记录当前 label/icon 和命令事件：显示播放却创建下载任务时，
该播放入口判为失败，不以下载日志或父级播放回调的存在代替播放终态。
先尝试原来失败的对象；换用已知有效测试媒体只用于区分数据和平台问题，不能
用替代对象通过覆盖原场景失败。

## 下载后置条件

1. 使用同一个有有效媒体 URL 的单集，点击下载一次。
2. 从日志确认请求使用目标 URL，request agent 到达 `completed`，没有 `failed/cancelled` 或 `File exists`；若有旧 task，记录其停止/删除及新 task 的身份。
3. 从日志或诊断接口记录最终文件路径，并在设备侧确认文件存在且字节数大于 0；路径必须与代码提交给 repository 的路径相同。
4. 回到下载页面，使用 `hdc shell uitest dumpLayout` 确认该单集出现在已完成下载列表；必要时离开页面再返回，确认仍存在。
5. 再次点击该条目的操作按钮，确认显示的是删除/播放等已下载后的动作，而不是“下载失败”或“出了点问题”。

失败时保留底层错误码、发生阶段、task 身份和目标路径；`File exists` 要区分目录
创建、旧任务目标、预创建文件和最终重命名冲突。检查当前 SDK 与实际文件状态，
不能把递归 mkdir 的 throws 清单单独当成必现证明。应用已持久化错误时读取该
单集相关记录；只得到通用 toast 时，运行时结论仍是 FAIL，根因保持未决。
若静态补丁涉及解析或刷新合并，再验证正常获取的数据以及刷新后同一单集的
媒体身份、下载记录、本地文件和播放来源，不用临时测试 URL 绕开上游缺口。

## 结果状态

- `RUNTIME_VERIFIED`：所有目标后置条件均有设备证据。
- `RUNTIME_FAILED`：设备场景执行且至少一个后置条件失败；保留入口、底层错误与依赖证据作为下一次定向修复的输入，不在 Round 2 后另开修复轮次。
- `RUNTIME_BLOCKED`：设备、网络、测试数据、权限或平台日志不可用；不得将其降级为通过。

源码审计/修复按既有 packet 调度；真机操作只由主流程串行执行。坐标点击须来自当前 dump/截图，并保留点击前后的状态证据；不得让多个 worker 并行操作设备。

## 结构化记录

以下是原有、用户已授权的流程内目标验证接口。独立验收使用上节矩阵；不要将
多个入口合并成一个 domain PASS。流程内完成目标场景后写入 `runtime-draft.json`，
再由确定性脚本校验并封存：

```json
{
  "schema_version": 1,
  "mode": "interaction-handler-runtime",
  "status": "PASS",
  "hap_sha256": "<the-installed-signed-hap-sha256>",
  "targets": ["playback", "download"],
  "checks": {
    "playback": {
      "same_item": true,
      "prepared_or_playing": true,
      "origin_page_returned": true,
      "bar_persists_after_return": true,
      "bar_clicked": true,
      "expanded_player_visible": true,
      "player_visible": true,
      "stable_after_3s": true
    },
    "download": {
      "same_item": true,
      "agent_completed": true,
      "file_nonempty": true,
      "db_readback": true,
      "downloads_page_visible": true,
      "post_action_correct": true
    }
  },
  "evidence": ["hilog.txt", "ui-dump.xml", "download-file-stat.json"]
}
```

`status=PASS` 时每个目标的所有检查必须为 `true`；任何一个失败使用 `FAIL`，设备/网络/测试数据不可用使用 `BLOCKED`。脚本会把它绑定到本次安装的 HAP，防止复用旧设备证据。
