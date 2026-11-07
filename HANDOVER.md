# 会话交接文档

**项目**: `hmigbot-ios`  
**更新时间**: 2026-11-06  
**参考基线**: `../hmigbot-1.8.0`（Android → HarmonyOS）  
**目标**: iOS → HarmonyOS（ArkTS）

## 当前工作结论

本仓库已经完成主要 i2h 设计和文档改造，但历史报告把“文件已生成”“理论对齐”“原型统计”多次写成了“生产就绪”。当前以 [`docs/IMPLEMENTATION_AUDIT.md`](docs/IMPLEMENTATION_AUDIT.md) 的证据清单为准。

最近完成的治理和运行时改造：

- 根目录只保留入口、状态、交接、导航和 iOS 变更记录。
- 过程文档移入 `docs/archive/`，按阶段和主题分类。
- `CHANGELOG.md` 已改为 iOS 版本记录，旧 Android 记录保存在归档。
- 新增 [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md) 和 [`docs/IMPLEMENTATION_AUDIT.md`](docs/IMPLEMENTATION_AUDIT.md)。
- 修复 Claude Code 插件目录/Skill 命名兼容性；新增 `migbot/.claude-plugin/plugin.json`，并通过 `claude plugin validate --strict`。
- 安装器现在提供可移植 `.migbot/bin/i2h`、`i2h-tool`、`i2h-bootstrap`，并保留用户自定义 `.claude/skills`。
- i2h-spec/plan 已有可执行的 UI/资源证据、`res-index`、schema-2 delivery、源码布局和所有权门禁；资源 worker 支持变体、主题、PDF/SVG、重复文件名和多语言记录。
- 调度器已支持依赖就绪派发、宿主并发上限和失败重取；尚未接入主 pipeline。

## 工程结构理解

```text
hmigbot-1.8.0
  └─ Android → HarmonyOS 原版：流程、门禁、产物契约和并发纪律的参考

hmigbot-ios
  ├─ i2h-spec       iOS 源码理解与 Spec 生成
  ├─ i2h-plan       indexed-v1 UI/Base/Slice 计划
  ├─ i2h-execute    ArkTS 生成、接线、资源和编译闭环
  ├─ i2h-verify     静态、身份、截图和可选设备验证
  └─ i2h-retrospect 指标、报告和交付回顾
```

## 已核对的实现问题

1. 旧安装结果缺少 `.migbot/bin/i2h` 和 `.migbot/bin/i2h-tool`；当前已由安装器补齐，需保留 smoke test 防回归。
2. `i2h-run` 的旧 JSON 完成标记已在本轮改为读取 indexed-v1 计划的 `complete.txt`，仍需补端到端 marker 测试。
3. execute 测试导入 launcher 会触发二进制替换；测试依赖的 `stage1_contract`、`stage1_wiring_checks` 等源码模块未随仓库提供。
4. execute 的 `build-dependencies.json` 依赖已补齐，但完整 Stage-1 仍需要真实 HarmonyOS 工程验证。
5. verify 现在可以读取最小 iOS `gate_ledger.py`；完整 detector registry 和真实证据校验仍待扩展。
6. retrospect 和多个根目录历史文档硬编码 Cuike 示例数据，把估算值写成了通用结果。

详细证据、优先级和修复建议见 [`docs/IMPLEMENTATION_AUDIT.md`](docs/IMPLEMENTATION_AUDIT.md)。

## 推荐下一步

### P0：恢复可测试执行链

- 把 execute 的业务实现从打包 launcher 拆到可导入的 `lib/`，保留 launcher 作为薄 CLI。
- 安装后自动执行三个入口的存在性、help、最小 fixture smoke test。

### P0：统一产物契约

- 以 i2h-plan 的 indexed-v1 Markdown 为唯一计划格式。
- 更新 `i2h-run` 的恢复标记，并让每个阶段只使用一个完成标记。
- 对不存在的 helper 使用明确的 DEFERRED 状态，禁止静默跳过。

### P1：恢复可测试性

- 把 launcher 变成薄 CLI，把业务实现放在可导入模块。
- 补齐或删除测试依赖的缺失模块。
- 在 macOS ARM64 和 Windows x64 上分别跑同一套 fixture。

### P1：真实项目验收

- Cuike：验证 SwiftUI、SwiftData、UIKit/OCR 混合输入。
- 最小 UIKit fixture：验证 ViewController、Info.plist、资源和导航。
- 记录编译、安装、截图、行为和回归证据后，再更新“生产就绪”结论。

## 文档导航

- 方法论：[`docs/METHODOLOGY.md`](docs/METHODOLOGY.md)
- 实现审计：[`docs/IMPLEMENTATION_AUDIT.md`](docs/IMPLEMENTATION_AUDIT.md)
- 归档索引：[`docs/ARCHIVE_INDEX.md`](docs/ARCHIVE_INDEX.md)
- 当前设计笔记：[`docs/current/`](docs/current/)
- 旧会话交接：[`docs/archive/session-history/HANDOVER-2024-11-03.md`](docs/archive/session-history/HANDOVER-2024-11-03.md)
