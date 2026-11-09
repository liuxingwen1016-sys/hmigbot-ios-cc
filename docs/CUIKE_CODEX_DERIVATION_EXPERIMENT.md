# CuikeTemp → Cuike01 Codex 派生实验

日期：2026-11-09

## 实验隔离

- 模板：`/Users/liuxingwen/DevEcoStudioProjects/CuikeTemp`
- Codex 派生工程：`/Users/liuxingwen/DevEcoStudioProjects/Cuike01`
- Claude 基线派生工程：`/Users/liuxingwen/DevEcoStudioProjects/Cuike01-Claude`
- iOS 源：`/Users/liuxingwen/Codes/ios2harmony/cuike-ios`
- 模板未写入任何 `.migbot`、`.agents`、`.codex`、`spec` 或构建产物

两套派生工程使用同一个 iOS source digest。Codex 工程安装了 `codex/skills`、`.codex/agents`、commands、hooks 和 runtime。Claude 工程安装了 `migbot` 的 `.claude` 形态。

## 输入证据

- `target_input_sha256`: `8f4783152e86fb56e5e6d3be9bd2042f3afe9863e2723bd55503011d0f279a87`
- Swift source files: 21
- 静态视图/组件声明: 22
- 页面候选: 12
- iOS style triggers: 29
- 资源颜色: 5
- 代码引用资源: 28

两套工程生成的 `resources-inventory.json`、`project-skeleton.json` 和 `ios-style-triggers.json` 输入摘要一致。

## 结果对比

| 指标 | Codex Cuike01 | Claude Cuike01-Claude |
|---|---:|---:|
| ArkTS 文件 | 41 | 41 |
| ArkTS 行数 | 5,664 | 5,664 |
| 页面文件 | 16 | 16 |
| clean + assembleHap real time | 11.83 s | 11.84 s |
| ArkTS warnings | 103 | 103 |
| 构建结果 | BUILD SUCCESSFUL | BUILD SUCCESSFUL |
| HAP 大小 | 1,059,138 bytes | 1,059,138 bytes |
| 静态检查 | 15/15 PASS | 15/15 PASS |

HAP SHA256 因签名过程不同而不同，源代码树和资源树逐文件一致。

已有 Cuike Claude 基线报告记录了以下覆盖结果，Codex 派生工程沿用同一份已验证实现并完成相同构建与静态检查。

- UI 页面覆盖率 13/13，100%
- 共享组件覆盖率 7/7，100%
- 导航边覆盖率 20/20，100%
- 系统能力分析覆盖率 9/9，100%
- 功能切片状态分布为 3 PASS、3 PARTIAL、5 STATIC-ONLY、3 BLOCKED

## 适配分支

`main_ui_optimize` 的 30 个 i2h 优化文件已应用到 `codex` 源侧，包含 UI 证据协议、风格触发、资源 delta、repair triage、视觉 rubric、stale bundle 拒绝和 stage-1 契约修复。随后重新运行 `codex-adapter/scripts/convert.py` 生成 Codex 产物。

## 限制

本次对比隔离的是 Claude→Codex 适配和构建/静态验证效果。CuikeFinal 的既有 HarmonyOS 实现被作为 Claude 参考基线复制到两个派生工程，以避免把“模型生成差异”和“插件形态差异”混在同一次实验中。未在本轮重新执行 Simulator 截图、真机安装、相机/OCR、通知、服务卡片或实况窗验证，因此这些功能仍沿用基线报告中的 PARTIAL/BLOCKED 状态。
