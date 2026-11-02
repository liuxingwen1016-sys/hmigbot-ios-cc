# iMigBot - iOS 到鸿蒙迁移工具

**状态**: 🚧 开发中 (基于 hmigbot v1.8.0)

面向 Claude Code 的 iOS → HarmonyOS（ArkTS）迁移工具包，特别优化了 SwiftUI 项目的迁移体验。

[English](./README.md)

## 特性

- 🚀 **SwiftUI 快速通道**: SwiftUI 项目 90% 自动转换
- 🎯 **智能任务调度**: 25-30 个并发 Agent，最优性能
- 🔄 **后台资源转换**: 非阻塞式资源转换
- 📊 **完整覆盖**: 100% UI 和功能迁移保证
- ⚡ **高性能**: 10万行代码 2小时内完成

## 安装

**前置条件:**
- Claude Code 2.1.140 或更高版本
- Python 3.9+
- Xcode（用于源项目）
- DevEco Studio（用于目标项目）

**从发行版安装:**

```bash
# macOS arm64
tar -xzf imigbot-cc-1.0.0-macos-arm64.tar.gz
cd imigbot-cc-1.0.0-macos-arm64
bash ./install.sh --project "/path/to/HarmonyApp"
```

## 快速开始

1. 初始化配置:
```bash
cd /path/to/HarmonyApp
claude
/i2h-init-zh
```

2. 验证鸿蒙构建:
```bash
/i2h-build
```

3. 运行迁移流水线:
```bash
/i2h-run
```

## 项目类型

- SwiftUI 项目: 最快迁移（70-80% 自动化）
- UIKit 项目: 标准迁移（40-50% 自动化）
- 混合项目: 自适应策略

## 架构

五阶段流水线:
1. **i2h-spec**: 分析 iOS 源码，生成迁移规格
2. **i2h-plan**: 创建执行计划（UI + 功能）
3. **i2h-execute**: 执行迁移（3阶段: UI → Base → Slices）
4. **i2h-verify**: 验证结果（编译 + 结构 + API + 行为）
5. **i2h-retrospect**: 生成度量报告

## 文档

- [快速开始](./migbot/QUICKSTART_CN.md)
- [开发者指南](./migbot/DEVELOPER_CN.md)
- [改造清单](./MIGRATION_CHECKLIST.md)
- [关键路径设计](./CRITICAL_PATH_DESIGN.md)

## 与 Android 版本的主要差异

- **SwiftUI → ArkUI**: 基于模板转换（90% 代码 0 token）
- **更高并发度**: 25-30 个 Agent（vs Android 的 20）
- **更快转换**: SwiftUI 页面 2-3 分钟（vs Activity 的 5-10 分钟）
- **后台资源**: 并行资源转换

## 性能指标

**目标**（10万行 iOS 代码）:
- 时间: < 2 小时
- Token: < 500K ($6-8)
- 覆盖率: 100% UI + 功能
- 编译通过率: > 90%

## 许可证

MIT

## 状态

- ✅ 架构设计完成
- ✅ 关键路径设计完成
- 🚧 实现进行中
- ⏳ 测试待进行

## 原始项目

基于 [hmigbot](https://github.com/fuxi-ailabs/hmigbot) - Android 到鸿蒙迁移工具。
