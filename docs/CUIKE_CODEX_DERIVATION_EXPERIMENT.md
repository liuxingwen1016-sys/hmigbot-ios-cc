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

## 真实运行验收

- Claude 基线报告记录的模型为 `deepseek-flash`，不使用 `deepseek-v4-pro`。
- Codex 侧按 GPT-6.1、高思考深度配置执行适配与验收。
- 本机没有连接 HarmonyOS 真机，使用 DevEco Mate 90 Pro 模拟器，HarmonyOS 7.0.0 / API 26，HDC `127.0.0.1:5555`。
- 两个 HAP 均完成安装和启动，`aa start -b com.example.cuiketemp -a EntryAbility` 成功。
- 实际运行了 Home、豆档案 Tab、豆详情导航，并导出 UI tree。
- 归一化后 app subtree hash 一致。
  - Home `51f14d466a9fca3265709b5b55bbfd7384f0c65d0d2da5f0213ce19b3f4d83e5`
  - 豆档案 `2e60e016ab740cb71e5f7474134b3fa484acb19b62155811ffae2c5ebb3d1650`
  - 豆详情 `d318886e52489941f74d1752e22161466cdfe7b689be5f713b016165d4cf6c76`

## 尚未完成的流水线门禁

这次真实运行验收不等于完整 spec→plan→execute→verify 通过。两套派生工程的 `stage5-status.json` 仍为 `BLOCKED`，`ui-delivery-gate-repaired.json` 仍为 `BLOCKED`。原因是本轮没有重新启动 Claude/Codex 模型 agent 生成新一轮 spec/plan/execute 产物，而是使用已经验证的 `CuikeFinal` 实现作为共同参考。真实安装和运行结果证明了产物可启动和关键导航可执行，但不能把它表述为两套 agent 独立完成了全流水线。
