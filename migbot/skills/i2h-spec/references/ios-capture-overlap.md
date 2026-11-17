# iOS 采集与静态分析并行

在已经确认 iOS 源、指定模拟器和采集状态后，由可访问 CoreSimulator 的宿主启动作业。每个作业使用单独的输出目录和临时 DerivedData。仍由原批量采集器执行真实导航、控件锚点和前台截图握手。

诊断或补采前使用 `ios_runtime_capture_plan.py --output-manifest-only`，将状态回执留在本次输出目录。正式采集交接沿用项目内原文件。补采需要进入批准范围时，按逐状态导入合同提交本次输出清单。

直接调用 `ios_runtime_capture_plan.py` 采集夹具时，先在同一组参数末尾追加
`--validate-only`。这一步校验计划及合批参数、源工程与测试文件、状态输出路径，
在启动设备或准备夹具之前返回 JSON。取得 `status=validated` 后，去掉该参数执行采集。
模拟器在线、构建与实际到态由采集阶段检查。

```bash
python3 .claude/skills/i2h-spec/scripts/ios_capture_job.py start \
  --reuse-existing \
  --job source-baseline --plan spec/.i2h/ios-runtime-capture-plan.json \
  --source-root ../cuike-ios --xcode-project Cuike.xcodeproj --scheme Cuike \
  --device-id "$CUIKE_SIMULATOR_ID" --bundle-id com.cuike.brew \
  --configuration-id Cuike.Debug.uitesting --scenario-id cuike-smoke \
  --xctest-target CuikeUITests --xctest-test-source Tests/UITests/CuikeUITests.swift
```

作业启动后继续处理不依赖源端截图的静态提取与分析。独立工作保持原写入范围，不改已冻结的采集计划或作业输出。需要运行时树时用同一作业名等待并发布。
断点恢复时，使用同样的 `start --reuse-existing` 参数。冻结计划、源路径和字节摘要、设备和采集器摘要
一致时返回原启动回执或已有终态。再用 `join` 观察活动状态、读取结果或发布。
输入变化时用新的作业名安排已批准的采集。原有作业没有启动或终态回执时，返回诊断，保留其现场。
新作业在采集开始和正式交接时复核 Swift、XCTest 与其余源文件字节。旧回执可沿用原有
`join` 入口查看；它的历史输入范围以原回执为准。

```bash
python3 .claude/skills/i2h-spec/scripts/ios_capture_job.py join \
  --job source-baseline --publish
```

退出码 124 表示本次观察到期，保留原作业继续等待。受限调用方无法查看宿主进程时，状态为 `AWAITING_RECEIPT`。退出码 2 时读取 `worker.log` 和结果，保留阻断状态。完整与部分完成的正式作业均通过摘要校验后发布原始清单到规范交接路径。部分完成仍返回 2。Execute 复核冻结作业回执及全部状态，仅使用已采齐的状态，原样保留每个受阻项。后续补采使用不同作业和正式补充清单。判图仍需签名目标包、实际到达和原图证据，按原有门禁进入。


对加载中等瞬时状态，可在采集计划的对应状态设置 `"capture_mode": "xctest_app"`，并提供实际导航和至少一个状态锚点。批量探针在应用前台采图和取树，随后复查锚点，主机核对回执绑定的两份文件摘要。锚点消失或摘要不匹配时保留阻断。稳定状态可沿用 Simulator 全屏抓图。应用级取证用于应用内状态，系统 UI 仍使用原设备取证流程。

批量采集同样绑定设备实际安装的 App 摘要。Simulator 抓图前后核对安装路径和构建身份；应用内抓图在前台回执到达后、校验图树前后核对。后一种回执明确记录 `before_artifact_validation` 和 `after_artifact_validation`，不把主机观测时间写成应用抓图时间。安装身份无法读取或在校验期间变化时不发送 ACK，也不发布成功状态。

对于点按后等待业务异步结果的状态，在该状态的 `navigation` 内添加 `anchor_wait_seconds`，范围大于 0 且最多 8 秒。锚点同时满足时立即继续采图和取树，采图后仍复查原锚点。瞬时状态省略该字段以沿用立即检查。可对开关等锚点额外声明字符串 `value`，例如 `"0"` 表示关闭。应用锚点超时保留缺口，系统权限弹窗由操作者处理。

依赖持久化存储的状态可在同一批次指定 `"launch_mode": "standard"`。探针按原应用方式启动，既有状态省略时沿用 `--uitesting`。如显式指定，主机校验前台回执的启动模式与计划一致，并将该模式写入状态清单。普通启动的运行输入由实际应用夹具提供，状态仍需满足批准的原生锚点。
