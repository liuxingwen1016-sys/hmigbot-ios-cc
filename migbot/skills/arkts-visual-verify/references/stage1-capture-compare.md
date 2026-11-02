<!-- when: scope=stage1_wired 时加载，独立于完整 Phase 1–7 -->
<!-- topics: S1-V, restricted scope, baseline, capture_compare, fix=none -->
# S1-V 受限截图比较入口

仅接受 execute 已获用户选择的 `scope=stage1_wired mode=capture_compare fix=none scope_manifest=<path>`。加载本文件后执行本分支并返回；不运行完整 Phase 1–7、round_budget、fact-tree 生产、Android 重采、全量队列、fixer 或应用数据清除。未提供有效 scope 不回退全量模式，返回 visual_blocked。本模式依赖调用方已有的 a2h-execute scripts；缺失则明确报前置缺失。

## 1. 冻结本次范围和包

scope 中每个 `units[].pages[]` 是唯一 `page_id/state_id/output_file`，含已经审计的 `android_png/android_xml` 相对路径和 SHA256。Android 只读复用这些证据；不拼 screenshots/android/{trip_id} 路径、不扫描原始 traverse run。

由 execute 调用 hmos-builder 构建当前 HAP，安装到指定 HarmonyOS 设备。准备/编译失败或安装失败记录阻塞，不拿旧包继续。构建修复如改变源码，重建 scope 并重新准备本次报告；不重新生成 Android 基线。

对每个 unit 按 a2h-execute 的回执契约记录真实 build/install 回执（可绑定同一次实际构建和同一个 HAP；不是每 unit 重编）。安装成功不证明页面已经显示。

然后执行（所有路径以 project root 为准）：

```bash
python3 "$SKILLS_ROOT/a2h-execute/scripts/stage1_capture_scope.py" prepare \
  --project-root "$PROJECT_ROOT" --scope-manifest "$SCOPE_MANIFEST" \
  --report "$PROJECT_ROOT/spec/execution/stage1-visual/manifest.json"
```

prepare 写入 run_id、当前 source_sha256 和精确 case 清单，不执行设备动作。恢复同一次捕获时使用该 manifest，不重复 prepare 清空证据；输入版本变化才重新准备。

## 2. 按范围捕获和比较

主会话只读取 manifest，逐个委托已有视觉 batch agent，任务严格限于其中的 case 和本分支。沿 wiring manifest 的正式入口/已接通路径进入；Preview 可用已接入的受控 host 和冻结参数，不临时改 Index、不新建展示页。

复用 phase4-navigation 的 HarmonyOS 设备操作与原导航知识，但不触发其 Android 分支或全量 reset。每个 page/state 都重新确认唯一 landmark；到达不了即 BLOCKED，不按目的地给错误截图命名。记录观察身份和具体 landing_evidence（dump 文本/节点/截图区域引用）。

按 prepare 返回的 `capture_dir=spec/execution/stage1-visual/<run_id>` 保存 HMOS PNG 和 UI dump，并对真实 Android 配对帧做多模态比较；主会话不读图。每个 case 回写到同一 manifest：

- status：PASS / DIFF / BLOCKED；后两者附 reason，DIFF 写可见差异。
- build_receipt、install_receipt：项目相对路径；device_id。
- capture_run_id：准备时的 run_id。
- observed_page_id、observed_state_id、landing_evidence。
- harmony_png、harmony_xml：本次非空捕获的项目相对路径。

逐 case 记录真实结果；BLOCKED 的归因用设备、应用、接线、捕获分类，不用无变化页面或工具超时直接推断崩溃。不得删未完成 case 获得 PASS。

## 3. 收口并退出

```bash
python3 "$SKILLS_ROOT/a2h-execute/scripts/stage1_capture_scope.py" finalize \
  --project-root "$PROJECT_ROOT" --scope-manifest "$SCOPE_MANIFEST" \
  --report "$PROJECT_ROOT/spec/execution/stage1-visual/manifest.json"
```

finalize 对账 scope、当前源码、包/安装、设备、本次 run 与完整 case 集合；缺证据得 visual_blocked。它校验证据绑定，不替代模型对页面身份与视觉差异的判断。仅真正观察到的 Preview case 可在结果中记 visibility=preview_ready；不批量翻 wiring manifest，不写页面 verified。

返回 PASS / DIFF / visual_blocked 及 manifest 路径后立即退出此 skill；不启动自动修复或轮次循环。DIFF 保留为用户可审查的对比结论，由 execute 记录并选择继续或后续处理，不冒充全域视觉通过。
