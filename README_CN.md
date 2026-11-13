# iOS MigBot

`hmigbot-ios` 是面向 Claude Code 的 iOS → HarmonyOS（ArkTS）迁移工具包。它以 [`../hmigbot-1.8.0`](../hmigbot-1.8.0) 的 Android → HarmonyOS 流水线为参考，并将输入、扫描、映射和验证改造成 iOS 版本。

## 当前状态

仓库已经包含 i2h 五阶段 Skill、iOS 参考 Skill、模板、脚本和 Cuike 试点记录。设计和文档改造已经形成体系，但目前还不能把它描述为“任意项目生产就绪”：安装运行时入口、阶段标记、部分脚本依赖和端到端验证仍有缺口，详见 [`docs/IMPLEMENTATION_AUDIT.md`](docs/IMPLEMENTATION_AUDIT.md)。

历史文档中的“90.8% 自动转换率”是 Cuike 原型阶段的统计估算，不代表编译通过率、行为等价率，也不是通用验收标准。

## 流水线

```text
iOS 项目
  ↓
i2h-spec       扫描源码，生成 UI 与功能规格
  ↓
i2h-plan       生成 indexed-v1 UI / Base / Slice 计划
  ↓
i2h-execute   生成 ArkTS、完成接线并执行门禁和编译闭环
  ↓
i2h-verify     执行静态、身份和用户选择的设备验证
  ↓
i2h-retrospect 汇总真实指标和交付证据
```

设计原则是“LLM 负责语义理解，脚本负责确定性提取和校验”。并行执行遵循单写者纪律：Worker 只修改自己的文件，Closer 负责共享接线和账本，findings 只能由对应检查重新运行后关闭。

## 安装

Claude Code 插件模式应直接加载 `migbot/` 目录。该目录包含插件清单以及
`commands/`、`agents/`、`skills/` 和 `hooks/`：

```bash
claude --plugin-dir /path/to/hmigbot-ios/migbot
```

命令会出现在 `hmigbot-ios` 命名空间下，例如 `/hmigbot-ios:i2h-init` 和
`/hmigbot-ios:i2h-run`。

也可以直接安装 marketplace 版本：

```text
/plugin install hmigbot-ios --marketplace liuxingwen1016-sys/hmigbot-ios-cc
```

```bash
cd /path/to/hmigbot-ios
./install.sh --project /path/to/HarmonyOSProject --ios /path/to/iOSApp
```

需要 Python 3.8+、Claude Code、带 `.xcodeproj` 或 `Package.swift` 的 iOS 项目，以及可供 DevEco Studio 使用的 HarmonyOS 工程。设备验证还需要 Xcode 工具、`hdc` 和实际设备或模拟器。

安装后使用 `/i2h-init` 和 `/i2h-run` 作为主要入口。`/i2h-build` 使用已安装的 `i2h-tool` 辅助程序；设备和 DevEco 检查仍需要真实运行环境。

用 `/i2h-verify behavior` 做首轮功能验证。修复后用 `/i2h-verify recheck` 复测指定场景，
保留首轮场景和当前 AC 的分母。完整 Verify 使用 `/i2h-verify full`。
见[原生行为验证命令与回执格式](migbot/skills/i2h-verify/references/check5-behavior-verify.md)。

## 目录

```text
hmigbot-ios/
├── README.md / README_CN.md       当前入口文档
├── CHANGELOG.md                   iOS 版本变更记录
├── HANDOVER.md                    当前交接和下一步
├── QUICK_REFERENCE.md             当前导航和证据规则
├── PROJECT_STATUS.md              当前状态快照
├── docs/
│   ├── METHODOLOGY.md             提取出的改造方法论
│   ├── IMPLEMENTATION_AUDIT.md    基于证据的问题清单和方案
│   ├── ARCHIVE_INDEX.md            文档索引
│   ├── current/                   仍有效的设计说明
│   └── archive/                   阶段报告和会话历史
├── migbot/                        可安装的命令、Agent 和 Skill
└── references/                    iOS 参考资料
```

`docs/archive/` 中的报告保留了每个阶段的真实过程；它们用于追溯，不直接代表当前实现状态。

## 参考关系

`hmigbot-1.8.0` 是 Android 基线。它的架构、门禁、产物契约和并发纪律可以复用，但 Android 输入和 API 假设必须先翻译成 iOS 语义。iOS 特有能力位于 `migbot/skills/ios-*` 和 `migbot/skills/i2h-*`。

推荐阅读：

- [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md)：改造步骤和方法论。
- [`docs/ORIGINAL_VS_IOS_ANALYSIS.md`](docs/ORIGINAL_VS_IOS_ANALYSIS.md)：原版 UI、资源、并行机制与 iOS 实际方案对比。
- [`docs/IMPLEMENTATION_AUDIT.md`](docs/IMPLEMENTATION_AUDIT.md)：当前问题、证据和修复顺序。
- [`docs/current/UNDERSTANDING.md`](docs/current/UNDERSTANDING.md)：原版架构理解。
- [`docs/current/TECHNICAL_DECISION.md`](docs/current/TECHNICAL_DECISION.md)：Swift 解析技术决策。

## CI 契约检查

GitHub Actions 会在 Ubuntu、macOS 和 Windows 上运行离线 SwiftUI/UIKit fixture、i2h-execute 测试、spec/plan 契约测试和 Python 编译检查。fixture 将设备与 DevEco 检查记录为 `DEFERRED`，不会伪造运行时证据。
