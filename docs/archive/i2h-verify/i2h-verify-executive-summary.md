# i2h-verify 改造执行摘要

**日期**: 2024-11-03  
**阶段**: i2h-verify 优化准备完成  

---

## 📊 核心发现

### 原版 a2h-verify 架构

**五项检查体系**（完全适用于 iOS）：
```
CHECK-1: 静态分析（主对话）          ← 需要新增 9 项 iOS 特有检查
CHECK-2: App 身份校验（主对话）       ← 需要改写配置读取逻辑
CHECK-3: 视觉对齐（arkts-visual-verify）  ← 参数适配
CHECK-4: 单元测试（arkts-ut-verifier）    ← 参数适配
CHECK-5: 行为验证（arkts-behavior-verify）← 参数适配
```

**关键特性**：
- ✅ 用户可选择 CHECK-3/4/5
- ✅ 失败修复回环（最多 3 轮）
- ✅ 完整的状态判定逻辑
- ✅ 非门控的 CHECK-5（只报告）

---

## 🔍 关键差异点

### 1. CHECK-1 静态分析

**Android 版**：6 项检查（Java/Kotlin 特性）

**iOS 版需要**：6 项通用 + **9 项 iOS 特有** = **15 项**

#### iOS 新增检查项

| 检查项 | 原因 | 级别 |
|--------|------|------|
| 强制解包 `!` | 可能导致崩溃 | WARN |
| `@escaping` 闭包 | 生命周期管理 | WARN |
| `weak`/`unowned` | ArkTS 不需要手动管理 | WARN |
| `@objc` / `@objcMembers` | 迁移遗留 | WARN |
| `#available` / `@available` | iOS 版本检查已无意义 | WARN |
| `DispatchQueue` | 需改为 TaskPool/Worker | ERROR |
| `NotificationCenter` | 需改为 Emitter | WARN |
| `UserDefaults` | 必须改为 Preferences | ERROR |
| `UIKit` / `SwiftUI` 导入 | 迁移未完成 | ERROR |

### 2. CHECK-2 App 身份校验

**配置文件差异**：

| 项目 | Android 来源 | iOS 来源 | 差异 |
|------|-------------|----------|------|
| 应用名 | AndroidManifest.xml | Info.plist `CFBundleDisplayName` | ⚠️ 文件不同 |
| 包名 | `<manifest package="">` | `CFBundleIdentifier` | ⚠️ 字段不同 |
| 版本 | `versionName` / `versionCode` | `CFBundleShortVersionString` / `CFBundleVersion` | ⚠️ 字段不同 |
| 图标 | `mipmap-*/ic_launcher.png` | `Assets.xcassets/AppIcon.appiconset/` | ⚠️ 结构完全不同 |

### 3. CHECK-3/4/5 设备管理

**命令体系完全不同**：

| 操作 | Android | iOS 模拟器 | iOS 真机 |
|------|---------|-----------|---------|
| 列出设备 | `adb devices` | `xcrun simctl list` | `idevice_id -l` |
| 安装应用 | `adb install` | `xcrun simctl install` | `ideviceinstaller -i` |
| 启动应用 | `adb shell am start` | `xcrun simctl launch` | 手动/ios-deploy |
| 截图 | `adb shell screencap` | `xcrun simctl io screenshot` | `idevicescreenshot` |

**关键点**：
- iOS 需要区分**模拟器 vs 真机**
- iOS 真机需要额外工具链：`libimobiledevice`

---

## 📋 改造方案总览

### 文件改动统计

| 文件 | Android 版 | iOS 版规划 | 改动量 | 优先级 |
|------|-----------|-----------|--------|--------|
| SKILL.md | 106 行 | ~450 行 | +324 行 (重写 60%) | ⭐⭐⭐⭐⭐ |
| static-and-identity.md | 34 行 | ~150 行 | +116 行 (重写 80%) | ⭐⭐⭐⭐⭐ |
| device-verification.md | 47 行 | ~80 行 | +33 行 (调整 50%) | ⭐⭐⭐⭐⭐ |
| check5-behavior-verify.md | 105 行 | ~130 行 | +25 行 (调整 30%) | ⭐⭐⭐⭐ |
| failure-loop.md | 37 行 | ~40 行 | +3 行 (保持 95%) | ⭐⭐ |
| verify-report-template.md | 84 行 | ~90 行 | +6 行 (保持 90%) | ⭐⭐⭐ |
| **新增** ios-specific-checks.md | - | ~200 行 | NEW | ⭐⭐⭐⭐ |

### 新增脚本

| 脚本 | 作用 | 行数 | 工作量 | 优先级 |
|------|------|------|--------|--------|
| `ios_device_checker.py` | 检测 iOS 设备（模拟器/真机）| ~150 | 3-4h | ⭐⭐⭐⭐⭐ |
| `ios_config_parser.py` | 解析 Info.plist 和 Assets | ~200 | 4-5h | ⭐⭐⭐⭐⭐ |
| `ios_static_analyzer.py` | iOS 特有静态分析 | ~300 | 6-8h | ⭐⭐⭐⭐ |
| 测试文件 | 单元测试 | ~200 | 4-6h | ⭐⭐⭐ |

---

## ⏱️ 工作量估算

### 按 Phase 分解

| Phase | 内容 | 工作量 | 关键产出 |
|-------|------|--------|---------|
| **Phase 1** | 核心文档改造 | 11-16h | SKILL.md + 核心 references |
| **Phase 2** | 辅助文档和模板 | 3.5-6h | 完整 references |
| **Phase 3** | 核心脚本实现 | 17-23h | 3 个核心 Python 脚本 + 测试 |
| **Phase 4** | 外部 Skills 协调 | 3-18h | 调研 + 临时方案（如需）|
| **Phase 5** | 验证和文档 | 9-14h | 对比报告 + 真实测试 |
| **总计** | | **43.5-77h** | **完整可用的 i2h-verify** |

### 务实估算

- ✅ **乐观**: ~45 小时（外部 Skills 完全支持 iOS）
- ⚠️ **现实**: ~60 小时（需要少量 workaround）
- ❌ **悲观**: ~75 小时（需要完整实现临时方案）

**推荐按现实场景规划：60 小时**

---

## 🚨 关键风险

### 风险 1: 外部 Skills 依赖 ⚠️⚠️⚠️⚠️⚠️

**问题**：`arkts-visual-verify`、`arkts-ut-verifier`、`arkts-behavior-verify` 可能不支持 iOS

**影响**：CHECK-3/4/5 无法执行

**缓解方案**：
1. ⭐⭐⭐⭐⭐ **立即调研** - 查看这些 Skills 是否支持 iOS
2. ⭐⭐⭐⭐ **参数传递** - 尝试 `--ios-*` 参数适配
3. ⭐⭐⭐ **临时方案** - 实现简化版或标记 DEFERRED
4. ⭐⭐ **提交 PR** - 向上游 Skills 贡献 iOS 支持

### 风险 2: iOS 工具链依赖 ⚠️⚠️⚠️

**问题**：iOS 真机需要 `libimobiledevice`（非系统标准工具）

**缓解方案**：
- ✅ 优先支持模拟器（`xcrun simctl` 是标准工具）
- ✅ 真机作为可选功能
- ✅ 文档清晰说明安装步骤

### 风险 3: 配置文件复杂性 ⚠️⚠️

**问题**：Info.plist 格式复杂（XML/Binary），Assets.xcassets 结构多样

**缓解方案**：
- ✅ 使用 Python `plistlib`（标准库）
- ✅ 简化检查（只验证关键字段）
- ✅ 提供配置示例

---

## 🎯 立即行动项

### 今天必须完成 ⭐⭐⭐⭐⭐

1. **调研外部 Skills iOS 支持**
   ```bash
   # 检查 arkts-visual-verify
   Read ~/Codes/ios2harmony/hmigbot-ios/migbot/skills/arkts-visual-verify/SKILL.md
   
   # 检查 arkts-ut-verifier（如果存在）
   find ~/Codes/ios2harmony/hmigbot-ios/migbot/skills -name "*ut*verif*"
   
   # 检查 arkts-behavior-verify
   Read ~/Codes/ios2harmony/hmigbot-ios/migbot/skills/arkts-behavior-verify/SKILL.md
   ```

2. **确认 i2h-spec 的 gate-release 支持**
   ```bash
   find ~/Codes/ios2harmony/hmigbot-ios/migbot/skills/i2h-spec -name "*gate*"
   ```

3. **创建基础目录结构**
   ```bash
   mkdir -p ~/Codes/ios2harmony/hmigbot-ios/migbot/skills/i2h-verify/{references,scripts,templates}
   mkdir -p ~/Codes/ios2harmony/hmigbot-ios/migbot/skills/i2h-verify/scripts/tests
   ```

### 本周目标 ⭐⭐⭐⭐

4. **完成 Phase 1: 核心文档改造**
   - SKILL.md (~450 行)
   - static-and-identity.md (~150 行)
   - device-verification.md (~80 行)
   - ios-specific-checks.md (~200 行)

5. **开始 Phase 3: 核心脚本**
   - ios_device_checker.py (~150 行)

---

## 📈 成功标准

### Milestone 1: 文档完整 ✅

- [ ] SKILL.md 完整且与 Android 版 100% 对齐
- [ ] 所有 references 完整
- [ ] iOS 特有检查规则清晰定义

### Milestone 2: 脚本可用 ✅

- [ ] iOS 设备检测脚本可用（模拟器 + 真机）
- [ ] iOS 配置解析脚本可用（Info.plist + Assets）
- [ ] iOS 静态分析脚本可用（15 项检查规则）
- [ ] 单元测试覆盖核心逻辑

### Milestone 3: 端到端可用 ✅

- [ ] CHECK-1/2 完整可用
- [ ] CHECK-3/4/5 可用或明确 DEFERRED
- [ ] 修复回环可用
- [ ] 生成正确的 verify-report.md
- [ ] 真实项目测试通过

---

## 📚 关键文档

| 文档 | 路径 | 作用 |
|------|------|------|
| **本分析** | `docs/i2h-verify-analysis.md` | 完整的差异分析和改造方案 |
| 执行摘要 | `docs/i2h-verify-executive-summary.md` | 本文档 |
| Android 原版 | `~/hmigbot-1.8.0/migbot/skills/a2h-verify/` | 参考实现 |
| iOS 当前版 | `~/hmigbot-ios/migbot/skills/i2h-verify/` | 待改造（仅 1 个骨架文件）|
| HANDOVER | `HANDOVER.md` | 项目整体进度 |

---

## 🔄 与其他阶段的对比

| 阶段 | 工作量 | 难度 | 状态 |
|------|--------|------|------|
| i2h-spec | ~40h | ⭐⭐⭐⭐ | ✅ 完成 |
| i2h-plan | ~75h | ⭐⭐⭐⭐⭐ | ✅ 完成 |
| i2h-execute | ~26h | ⭐⭐⭐⭐⭐ | ✅ 完成 |
| **i2h-verify** | **~60h** | **⭐⭐⭐⭐** | **⏸️ 待开始** |

**i2h-verify 难度评估**：⭐⭐⭐⭐ (4/5)

**原因**：
- ✅ 架构清晰（五项检查体系完全适用）
- ✅ 文档齐全（Android 版提供完整参考）
- ⚠️ iOS 特有检查项多（15 项 vs 6 项）
- ⚠️ 设备管理复杂（模拟器 vs 真机，两套工具链）
- ⚠️ 外部 Skills 依赖（可能需要适配或临时方案）

**相比 i2h-execute 的优势**：
- ✅ 不需要大量模板文件（i2h-execute 有 7 个 agent-prompts）
- ✅ 不需要复杂的派发体系
- ✅ 脚本逻辑相对独立

**相比 i2h-plan 的优势**：
- ✅ 不需要多层索引架构
- ✅ 产物结构简单（主要是报告）

---

## 💡 经验教训（from i2h-execute）

### 从 i2h-execute 学到的

1. ⭐⭐⭐⭐⭐ **批量操作前先测试**
   - 不要一次性改所有文件
   - 用 git 保护现场

2. ⭐⭐⭐⭐⭐ **生成后立即验证**
   - 检查文件大小
   - 抽查内容完整性
   - 不要过度相信自动化

3. ⭐⭐⭐⭐ **建立"生成-验证-提交"工作流**
   - 每个 Phase 独立验证
   - 及时提交，保持可回退

4. ⭐⭐⭐⭐ **详细记录错误和解决方案**
   - 方便后续查阅
   - 避免重复踩坑

### 应用到 i2h-verify

1. **分文件改造**
   - 先改 SKILL.md
   - 再逐个改 references
   - 最后实现 scripts

2. **每个文件改完立即验证**
   - 检查字数和行数
   - 对比 Android 版结构
   - 确认 iOS 特性覆盖完整

3. **频繁提交**
   - 每完成一个文件提交一次
   - 写清晰的 commit message
   - 保持 main 分支干净

---

## 🚀 开始！

**准备就绪**：
- ✅ 完整分析完成
- ✅ 改造方案明确
- ✅ 工作量已估算
- ✅ 风险已识别
- ✅ 缓解方案已制定

**下一步**：立即执行调研和 Phase 1

---

**文档版本**: v1.0  
**创建时间**: 2024-11-03  
**作者**: Claude Opus 5.5  
**状态**: ✅ 分析完成，待执行
