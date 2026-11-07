# Changelog

`hmigbot-ios` 是从 `../hmigbot-1.8.0` 派生的 iOS → HarmonyOS 改造分支。原版 Android → HarmonyOS 的完整变更记录保存在 [`docs/archive/source-android/CHANGELOG-ANDROID-REFERENCE.md`](docs/archive/source-android/CHANGELOG-ANDROID-REFERENCE.md)，不作为本项目的版本说明。

## [Unreleased] - 2026-11-06

### 文档与工程治理

- 重组根目录过程文档，按 i2h-spec、i2h-plan、i2h-execute、i2h-verify、Cuike 试点和会话历史归档。
- 新增文档归档索引、改造方法论和实现审计，区分历史报告、当前实现和已验证事实。
- 修正根目录状态文档中把 Android 版本能力、历史估算和原型结果当成 iOS 生产能力的问题。

### 已确认的实现风险

- 安装脚本没有安装 `i2h` / `i2h-tool` 运行时入口，但命令和 Skill 仍会调用它们。
- 修正 `i2h-run` 的 plan 完成标记，使其读取当前 indexed-v1 Markdown 计划阶段的 `complete.txt`。
- `i2h-execute` 的部分脚本是导向编译二进制的包装器，测试直接导入这些文件会触发进程替换；部分测试依赖的 Python 模块也未随源码提供。
- `i2h-verify` 依赖的 `gate_ledger.py` 和 `i2h-execute` 的若干依赖清单路径目前不存在。

## [0.4.0] - 2024-11-04

### i2h-verify

- 完成 iOS 静态分析、Info.plist/图标配置解析、设备探测和双端截图对比脚本。
- 增加 gate-release 读取工具和 CHECK-4 参数适配脚本。
- CHECK-5 行为验证仍明确标记为非门控/适配中；CHECK-3 为简化实现，需要真实项目设备验证。

## [0.3.0] - 2024-11-03

### i2h-execute

- 建立 iOS 版本的执行规范、资源 sweep、writeback、Stage 1 接线和编译闭环文档。
- 增加 `apply_writeback.py`、`sweep_resources.py` 及相关门禁脚本和测试样例。
- 这些交付物完成了设计与部分工具实现，不等于已在任意 iOS 项目上端到端通过。

### i2h-plan

- 从扁平计划升级为 indexed-v1：UI 计划、Base 计划和 Slice 计划分离。
- 增加 templates、references、覆盖率 linter、placeholder registry 和决策门。

### i2h-spec

- 建立 LLM 主导、确定性脚本辅助的 iOS Spec 生成流程。
- 增加 SwiftUI/UIKit、iOS API、资源、权限和 ArkUI 语义映射资料。
- 根据早期真实产物差异补充 feature-base、placeholder、UI 覆盖率和验收标准约束。

## [0.2.0] - 2024-11-02

- 完成 iOS 插件安装、i2h 命令和基础 SwiftUI → ArkUI 原型。
- 加入 UIKit 映射、iOS property wrapper 映射和资源转换入口。
- Cuike 试点报告形成第一版转换率估算；该数字只代表当时的原型统计，不是通用质量承诺。

## [0.1.0] - 2024-11-01

- 完成原版架构研究、iOS 改造方案和 SwiftUI 转换器原型。
- 明确以 `hmigbot-1.8.0` 作为 Android → HarmonyOS 参考基线，并保留 iOS 平台差异。

## 版本说明

版本条目只记录已经存在于仓库中的改动。除非有真实项目、编译日志或可重复脚本输出作为证据，否则不把“预计”“理论对齐度”“自动转换率估算”写成验证结果。
