# iOS 技能与说明文件（0.14.1）

范围：报告《ios-0.14.1-功能报告 1102》中的 11 个 iOS 核心技能及对应说明资料。

来源：0.14.1 历史提交 `f967de1d139b439f6a9f6738036c820556f85868`，与报告版本一致。

## 11 个核心技能

| 技能目录 | 对应能力 |
|---|---|
| `skills/ios-source-analysis/` | iOS 源码分析总入口与 MCP 接入 |
| `skills/ios-project-inspector/` | Xcode 工程、Target、Scheme 与构建配置分析 |
| `skills/ios-ui-analyzer/` | SwiftUI/UIKit 页面与状态分析 |
| `skills/swiftui-fact-tree/` | SwiftUI 事实树兼容合同 |
| `skills/ios-feature-analyzer/` | iOS 功能、业务逻辑与数据流分析 |
| `skills/ios-api-inventory/` | iOS SDK API 与第三方库清单 |
| `skills/ios-ui-graph-builder/` | iOS UI 导航关系图构建 |
| `skills/ios-ui-graph-query/` | iOS UI 图查询及组件、布局、交互映射 |
| `skills/ios-ui-to-arkui/` | iOS UI 到 ArkUI 的语义映射 |
| `skills/ios-resources-convert/` | iOS Asset Catalog、本地化与资源映射 |
| `skills/ios-fact-tree/` | iOS 事实关系树投影合同 |

## 配套说明资料

- `skills/`：上述 11 个技能的 SKILL.md 与原有参考说明，共 41 个 Markdown 文件；MCP 接入和 UI 组件/布局/交互映射说明均在其中。
- `vendor/ios-expertise/`：报告对应的 SwiftUI、Swift Concurrency、UIKit 知识库说明及许可，共 66 个文件。
- `providers/swift-syntax/README.md`：SwiftSyntax 解析能力说明。
- `文件清单.txt`：本包实际文件路径。

本包为技能与说明资料集。只收录 Markdown 文档及知识库许可，保留原文和目录；未加入 Python 实现、通用流程技能、二进制、工程模板或运行依赖。

`ios-ui-to-arkui/references/android-to-arkui-mapping.md` 沿用历史文件名，其实际内容是 iOS/SwiftUI/UIKit 到 ArkUI 的映射说明，因此保留。
报告中不存在的独立脚本、未来新增建议及 Android 能力没有扩充进入本包。
