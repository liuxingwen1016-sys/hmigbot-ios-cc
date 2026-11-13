# iOS 采集与静态分析并行

在已经确认 iOS 源、指定模拟器和采集状态后，由可访问 CoreSimulator 的宿主启动作业。每个作业使用单独的输出目录和临时 DerivedData。仍由原批量采集器执行真实导航、控件锚点和前台截图握手。

```bash
python3 .claude/skills/i2h-spec/scripts/ios_capture_job.py start \
  --job source-baseline --plan spec/.i2h/ios-runtime-capture-plan.json \
  --source-root ../cuike-ios --xcode-project Cuike.xcodeproj --scheme Cuike \
  --device-id "$CUIKE_SIMULATOR_ID" --bundle-id com.cuike.brew \
  --configuration-id Cuike.Debug.uitesting --scenario-id cuike-smoke \
  --xctest-target CuikeUITests --xctest-test-source Tests/UITests/CuikeUITests.swift
```

作业启动后继续处理不依赖源端截图的静态提取与分析。独立工作保持原写入范围，不改已冻结的采集计划或作业输出。需要运行时树时用同一作业名等待并发布。

```bash
python3 .claude/skills/i2h-spec/scripts/ios_capture_job.py join \
  --job source-baseline --publish
```

退出码 124 表示本次观察到期，保留原作业继续等待。受限调用方无法查看宿主进程时，状态为 `AWAITING_RECEIPT`。退出码 2 时读取 `worker.log` 和结果，保留阻断状态。完整作业通过摘要校验后发布到原先的规范交接路径。判图仍需签名目标包、实际到达和原图证据，按原有门禁进入。
