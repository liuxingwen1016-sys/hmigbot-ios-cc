# Cuike iOS→HarmonyOS 优化轮交接文档

## 交接范围

- 工具分支：`codex`
- 最新同步提交：`e4f3015 sync: apply latest main UI optimization gates to Codex`
- 源侧同步基线：`main_ui_optimize` 最新提交 `d626bd6`
- iOS 源码：`/Users/liuxingwen/Codes/ios2harmony/cuike-ios`
- 模板工程：`/Users/liuxingwen/DevEcoStudioProjects/CuikeTemp`
- 鸿蒙模拟器：`127.0.0.1:5555`

`CuikeTemp` 与 iOS 源码在本轮保持只读。新实验工程为 `Cuike03` 和 `Cuike03-Claude`。

## Codex 适配流程

Codex 目录是生成产物，`migbot/` 是源侧事实。后续同步必须按下面顺序执行，不能直接编辑 `codex/skills` 里的单个文件。

1. 在 `main_ui_optimize` 或源侧 `migbot/` 完成工具修改。
2. 在仓库根目录执行 `python3 codex-adapter/scripts/convert.py --dry-run`，检查生成差异。
3. 确认没有误删 Codex 顶层手写文件后执行 `python3 codex-adapter/scripts/convert.py`。
4. 执行 `python3 codex-adapter/scripts/verify.py` 和 `python3 codex-adapter/scripts/test_overlay.py`。
5. 运行相关 i2h 测试集，至少覆盖 execute、plan、spec、verify 的脚本测试。
6. 检查 `git diff --check`，提交 `migbot/` 源侧变化和重新生成的 `codex/` 产物，再推送 `origin/codex`。

本轮的同步提交是 `e4f3015`。它通过 `main_ui_optimize` 与旧 Codex 适配基线 `6a6c8c7` 的源侧差异生成，避免直接合并整个分支导致 Codex 产物目录被删除。

## 派生实验工作方式

每轮实验都要从模板新建目录，禁止在旧实验工程上继续写入。

```bash
cp -R /Users/liuxingwen/DevEcoStudioProjects/CuikeTemp \
  /Users/liuxingwen/DevEcoStudioProjects/Cuike03
```

Codex 派生工程需要安装当前分支的 `.agents/skills`、`.codex/agents`、`.codex/commands`、`.codex/hooks`、`.codex/bin` 和 `.codex/config.toml`，再写入 `.migbot/config.json`，其中 `ios` 使用 iOS 源的绝对路径，`confirmed` 为 `true`。Claude 派生工程使用 `migbot/install.sh` 安装 `.claude` 和 `.migbot`，并使用 `~/.claude/settings.deepseek.json`。

派生完成后必须检查以下条件。

- `CuikeTemp` 的时间戳和文件大小没有变化。
- 新工程的 `entry/src/main/ets` 只有模板文件，没有旧迁移页面。
- `spec/` 为空或只有初始化目录，没有 Cuike02/CuikeFinal 的报告和截图。
- iOS 源目录只读，不能把生成代码回写到 iOS 工程。

## 标准实验顺序

Codex 和 Claude 都按同一业务顺序执行，模型和插件不同，但证据要求相同。

1. `i2h-init` 读取并确认路径配置。
2. `i2h-spec` 生成源索引、UI manifest、页面规格、功能规格和 iOS runtime evidence。
3. `i2h-plan` 生成 UI/功能计划、切片、coverage、requirements index 和 approved UI delivery。
4. `i2h-execute` 生成 ArkTS，运行 capability、identity、safe-area、UI obligation gate，构建 HAP 并安装到模拟器。
5. `i2h-verify` 运行静态/身份检查，执行模拟器截图、UI tree 和交互 smoke，并运行 CHECK-3 双端视觉对比。
6. `pipeline_resume.py` 或对应恢复检查器复核 marker、输入哈希、产物哈希和阶段状态。

任何 gate 失败都要写入报告并停止在真实阶段。不能用文件存在、旧截图或静态分析结果代替设备证据，不能把 `DEFERRED` 或 `BLOCKED` 改写成 PASS。

## 鸿蒙模拟器验收方式

当前固定设备是 `127.0.0.1:5555`。每个新工程都要显式使用该目标，避免误装到其它 HDC 设备。

```bash
HDC=/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/toolchains/hdc
"$HDC" list targets
"$HDC" -t 127.0.0.1:5555 install -r entry/build/default/outputs/default/entry-default-signed.hap
"$HDC" -t 127.0.0.1:5555 shell aa start -a EntryAbility -b <bundleName>
"$HDC" -t 127.0.0.1:5555 shell snapshot_display -f /data/local/tmp/page.jpeg
"$HDC" -t 127.0.0.1:5555 shell uitest dumpLayout -p /data/local/tmp/page.json
```

每个核心页面同时保存截图和 UI tree。至少覆盖 Home、豆档案、豆详情、配方、冲煮、风味记录。点击路径要记录起点、坐标或控件 id、终点状态和对应证据文件。

## 视觉验收的两层门禁

针对 iOS→HarmonyOS，交接时要区分两种视觉检查。

- `i2h-verify CHECK-3` 是本项目实际适用的双端流程。先采集 iOS Simulator PNG、accessibility JSON 和 foreground receipt，再采集 HarmonyOS 模拟器截图，最后运行 `run_check3.sh` 或 `compare_screenshots.py`，保存 comparison JSON/Markdown。
- `arkts-visual-verify` 是 Android-first 的通用闭环，要求 Android baseline、fact-tree、page scenarios、visual-fixer agents 和对应二进制。iOS-only 工程缺这些前置时必须记录真实 exit code 和 blocked 原因，不能把 HDC smoke 或 CHECK-3 结果冒充 formal PASS。

本轮 Codex03 的 CHECK-3 已真实执行，formal visual-verify 仍是 BLOCKED。后续同事应分别维护这两类结果。

## 本轮同步的工具优化

本轮将 `main_ui_optimize` 的 41 个源侧文件同步到 `migbot/`，再通过 `codex-adapter` 重新生成 `codex/` 产物。

- 新增签名身份预检和 bundle/profile 绑定检查。
- 新增 immersive safe-area L1/L2/L3 门禁。
- 强化 iOS runtime capture 的 accessibility、foreground receipt 和输入哈希握手。
- 强化 `pipeline_resume`、UI delivery、UI obligation 和 capability gate 的内容哈希与阻断契约。
- 强化 presentation lifecycle、资源/icon fidelity、resource delta 和视觉验收证据。
- 更新 CHECK-3 截图对比工具，输出 JSON、Markdown 和像素/感知指标。
- 增加对应单测、handshake 测试、签名预检测试和 safe-area 测试。

## Codex03 实验

工程路径为 `/Users/liuxingwen/DevEcoStudioProjects/Cuike03`。会话使用 GPT-6.1 Terra 系列模型，推理强度 high。直接使用 `gpt-6.1` 的 CLI 路由受 ChatGPT 账户限制，因此通过新的 Codex 会话完成。

### 已完成

- spec、plan、execute、verify、retrospect 产物生成。
- `hvigorw assembleHap` 构建成功。
- `hdc -t 127.0.0.1:5555 install` 成功。
- `aa start` 成功。
- HDC 截图和 UI tree 覆盖 Home、豆档案、豆详情、配方、冲煮、风味记录。
- 真实坐标点击完成核心导航和状态切换。
- iOS Home runtime baseline 成功采集，包含 PNG、accessibility JSON、foreground receipt 和 manifest。
- CHECK-3 双端对比真实执行。

### 验收结果

| 项目 | 结果 |
|---|---|
| HOS 安装/启动 | PASS |
| HOS 核心交互 | PASS |
| CHECK-1 静态分析 | PASS |
| App identity | PARTIAL，模板 signing profile 仍绑定 `com.example.cuiketemp` |
| CHECK-3 双端视觉 | FAIL-visual，3 组相似度为 50.00%、55.47%、46.88%，平均 50.78% |
| formal `arkts-visual-verify` | BLOCKED，缺 macOS-arm64 bundled binary，且 Android-first oracle 不适配 iOS-only 输入 |
| pipeline_resume | PARTIAL，`SAFEAREA_GATE_FAIL` 阻止 execute 完整闭环，3 个 immersive L3 单元缺失 |

详细证据：

- `/Users/liuxingwen/DevEcoStudioProjects/Cuike03/spec/migration-report.md`
- `/Users/liuxingwen/DevEcoStudioProjects/Cuike03/spec/verify-report.md`
- `/Users/liuxingwen/DevEcoStudioProjects/Cuike03/spec/verify/comparison/comparison-results.json`
- `/Users/liuxingwen/DevEcoStudioProjects/Cuike03/spec/verify/comparison/ui-comparison.md`
- `/Users/liuxingwen/DevEcoStudioProjects/Cuike03/spec/verify/screenshots/harmonyos/`
- `/Users/liuxingwen/DevEcoStudioProjects/Cuike03/spec/execution/pipeline-timings.json`

## Claude03 实验

工程路径为 `/Users/liuxingwen/DevEcoStudioProjects/Cuike03-Claude`。会话使用 `~/.claude/settings.deepseek.json` 中的 `deepseek-flash[1m]`，没有使用 v4-pro。

### 已完成到的阶段

- spec marker 已生成。
- plan marker、UI delivery 和 feature plan 已生成。
- 生成 34 个 ETS 页面、组件、服务和数据层文件。
- 运行了 capability gate 和 immersive safe-area gate。
- 在 HOS 模拟器生成 Home、豆档案、豆详情截图和 UI JSON。

### 当前阻断

Claude Code 在继续 execute 时收到 DeepSeek API `402 Insufficient Balance`，进程停止，未完成最终 build/install/execute/verify 报告。本轮不能把 Claude03 的静态产物或部分截图宣布为完整迁移结果。

已知门禁：

- capability gate：`PARTIAL`，F102 live form 缺失，通知回退可用。
- immersive safe-area gate：`FAIL`，`widget/pages/WidgetCard.ets` 缺少 L3 safe-area 响应。
- Claude03 的 HOS 部分证据位于 `/Users/liuxingwen/DevEcoStudioProjects/Cuike03-Claude/spec/verify/screenshots/harmonyos/`。

## 当前转换效果判断

Codex 分支已具备较完整的流水线门禁和真实模拟器验收能力，但转换结果仍未达到 `main_ui_optimize` 目标效果。

- Codex03 的核心路径可运行，页面入口仍偏集中，视觉相似度平均 50.78%。
- safe-area、签名身份、iOS 基线完整性和 formal visual-verify 仍未闭合。
- Claude03 的页面/服务/数据层覆盖更广，但本轮因模型余额不足未完成闭环，不能作为完整对照通过样本。

## 下一位同事的恢复顺序

1. 为 DeepSeek API 补充可用余额，继续 Cuike03-Claude 的 execute→verify，不要复用旧工程产物。
2. 修复 Cuike03 和 Cuike03-Claude 的 `immersive_safearea_gate` L3 缺口，重点检查全屏入口和 widget page。
3. 修正 signing profile，使 bundleName 与目标工程身份一致。
4. 补采 iOS BeanLibrary、Recipe 等页面的 accessibility/foreground receipt，重新运行 CHECK-3。
5. 保持 `arkts-visual-verify` Android-first formal gate 为独立 blocked 记录，不能将 i2h CHECK-3 结果冒充其 PASS。
6. 重新运行完整测试集和 adapter verify，再提交修复提交。

## Git 交接状态

工具优化已提交并推送到 `origin/codex`。本轮外部实验工程没有复制回仓库，交接依据是上述报告和绝对路径证据。
