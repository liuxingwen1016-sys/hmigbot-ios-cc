# i2h-verify 调研完整总结

**日期**: 2024-11-03  
**调研人**: Claude Opus 5.5  
**状态**: ✅ 调研完成

---

## 📋 调研概览

### 调研目标

1. ✅ 分析原版 a2h-verify 的实现逻辑
2. ✅ 识别 Android vs iOS 的差异点
3. ✅ 评估外部 Skills 的 iOS 支持情况
4. ✅ 确认 gate-release 功能可用性
5. ✅ 制定完整改造方案

### 调研结果文档

| 文档 | 大小 | 内容 |
|------|------|------|
| **i2h-verify-analysis.md** | 23,000+ 字 | 完整差异分析和改造方案 |
| **i2h-verify-executive-summary.md** | 6,000+ 字 | 执行摘要 |
| **i2h-verify-investigation-report.md** | 8,000+ 字 | 外部 Skills 调研 |
| **i2h-verify-gate-release-summary.md** | 3,000+ 字 | gate-release 功能总结 |
| **本文档** | - | 完整总结 |

---

## 🎯 核心发现

### 1. 原版 a2h-verify 架构

**五项检查体系**（完全适用于 iOS）：

```
CHECK-1: 静态分析（主对话）          ← 需新增 9 项 iOS 检查
CHECK-2: App 身份校验（主对话）      ← 需改写配置读取
CHECK-3: 视觉对齐（arkts-visual-verify）   ← 需独立实现
CHECK-4: 单元测试（arkts-ut-verifier）     ← 参数适配
CHECK-5: 行为验证（arkts-behavior-verify） ← 暂时 DEFERRED
```

**关键特性**：
- ✅ 用户可选 CHECK-3/4/5（固定执行 CHECK-1/2）
- ✅ 失败修复回环（最多 3 轮）
- ✅ 完整状态判定逻辑
- ✅ CHECK-5 非门控（只报告）

### 2. 外部 Skills iOS 支持评估

| Skill | iOS 支持 | 状态 | 推荐方案 | 额外工作量 |
|-------|---------|------|---------|-----------|
| `arkts-visual-verify` | 0% | ❌ 不支持 | **独立实现简化版** | +15-20h |
| `arkts-ut-verifier` | 60% | ⚠️ 部分支持 | 参数映射 + 跳过 Oracle | +4-6h |
| `arkts-behavior-verify` | 60% | ⚠️ 部分支持 | 标记 DEFERRED | +2h |
| `i2h-spec` gate-release | 100% | ✅ 已支持 | 直接使用 | +4h |

### 3. 关键差异点

#### CHECK-1: 静态分析

**Android**: 6 项检查  
**iOS**: 15 项检查（6 通用 + 9 iOS 特有）

**iOS 新增检查项**：
1. 强制解包 `!` (WARN)
2. `@escaping` 闭包 (WARN)
3. `weak`/`unowned` (WARN)
4. `@objc` / `@objcMembers` (WARN)
5. `#available` / `@available` (WARN)
6. `DispatchQueue` (ERROR)
7. `NotificationCenter` (WARN)
8. `UserDefaults` (ERROR)
9. `UIKit` / `SwiftUI` 导入 (ERROR)

#### CHECK-2: App 身份校验

**配置文件差异**：

| 项目 | Android | iOS | 差异程度 |
|------|---------|-----|---------|
| 配置文件 | AndroidManifest.xml | Info.plist | ⚠️⚠️⚠️ |
| 图标结构 | mipmap-*/ | Assets.xcassets/ | ⚠️⚠️⚠️ |
| 读取方式 | XML 解析 | plist 解析 | ⚠️⚠️ |

#### CHECK-3: 视觉对齐

**最大变化点**：

| 对比维度 | Android | iOS | 差异 |
|---------|---------|-----|------|
| 设备命令 | `adb devices` | `xcrun simctl list` | ⚠️⚠️⚠️ |
| 截图方式 | `adb shell screencap` | `xcrun simctl io screenshot` | ⚠️⚠️⚠️ |
| Skill 依赖 | android-fact-tree | 无（需独立实现）| ⚠️⚠️⚠️⚠️⚠️ |

---

## 📊 工作量估算（最终版）

### 原估算 vs 最终估算

| Phase | 原估算 | 最终估算 | 变化 | 说明 |
|-------|--------|---------|------|------|
| Phase 1 | 11-16h | 11-16h | 无变化 | 核心文档改造 |
| Phase 2 | 3.5-6h | 3.5-6h | 无变化 | 辅助文档和模板 |
| Phase 3 | 17-23h | 17-23h | 无变化 | 核心脚本实现 |
| **Phase 4** | **3-18h** | **25-32h** | **+22-14h** | 外部 Skills + gate-release |
| Phase 5 | 9-14h | 9-14h | 无变化 | 验证和文档 |
| **总计** | **43.5-77h** | **65.5-91h** | **+22-14h** | |

### Phase 4 细分（外部依赖处理）

| 任务 | 工作量 | 优先级 | 说明 |
|------|--------|--------|------|
| CHECK-3 简化版实现 | 15-20h | ⭐⭐⭐⭐⭐ | 独立实现双端截图对比 |
| CHECK-4 参数适配 | 4-6h | ⭐⭐⭐⭐ | 参数映射 + 跳过 Oracle |
| CHECK-5 标记 DEFERRED | 2h | ⭐⭐⭐ | 生成说明文档 |
| gate-release 集成 | 4h | ⭐⭐⭐⭐ | 读取并处理迁移放行项 |
| **小计** | **25-32h** | | |

### 最终估算（三种场景）

| 场景 | 工作量 | 说明 | 推荐 |
|------|--------|------|------|
| 乐观 | ~65h | CHECK-3 开发顺利 | |
| **现实** | **~78h** | **CHECK-3 需要调试** | ✅ **推荐** |
| 悲观 | ~91h | 遇到意外问题 | |

---

## 🎯 最终方案

### CHECK-1: 静态分析 ✅

**方案**: 在主对话中执行，新增 iOS 特有检查

**实现**：
- ✅ 保留 6 项通用检查（`any`、旧 API、SQL 拼接等）
- ✅ 新增 9 项 iOS 检查（强制解包、DispatchQueue、UserDefaults 等）
- ✅ 使用 `rg` 搜索 + 上下文确认

**工作量**: 6-8h

### CHECK-2: App 身份校验 ✅

**方案**: 在主对话中执行，重写配置读取逻辑

**实现**：
- ✅ 使用 Python `plistlib` 解析 Info.plist
- ✅ 解析 Assets.xcassets 图标结构
- ✅ 验证 bundleName、版本、应用名、图标

**工作量**: 8-10h

**脚本**:
- `scripts/ios_config_parser.py` (~200 行)
- `scripts/ios_icon_checker.py` (~150 行)

### CHECK-3: 视觉对齐 ⭐⭐⭐⭐⭐

**方案**: 在 i2h-verify 中独立实现简化版

**实现**：
- ✅ iOS 设备检测（模拟器 + 真机）
- ✅ 双端截图（iOS + HarmonyOS）
- ✅ 相似度计算（Python PIL + imagehash）
- ✅ 生成详细对比报告

**不包含**：
- ❌ 自动修复（交给后续阶段）
- ❌ 功能验证（由 CHECK-5 处理）

**工作量**: 15-20h

**脚本**:
- `scripts/ios_device_checker.py` (~150 行)
- `scripts/ios_screenshot.py` (~200 行)
- `scripts/compare_screenshots.py` (~250 行)

**产物**:
- `spec/verify/screenshots/ios/`
- `spec/verify/screenshots/harmonyos/`
- `spec/verify/ui-comparison.md`

### CHECK-4: 单元测试 ✅

**方案**: 参数映射 + 跳过 Oracle

**实现**：
```bash
Skill(arkts-ut-verifier) {
  ios_source_root: "/path/to/ios",
  harmonyos_root: "/path/to/harmonyos",
  skip_oracle: true,  # 跳过 Android Oracle 采集
  mode: "verify_fix"
}
```

**限制**：
- ⚠️ 不自动生成测试用例（需手动或基于 Spec）
- ⚠️ 以 Spec 为准（而非 iOS 行为）

**工作量**: 4-6h

### CHECK-5: 行为验证 ⏸️

**方案**: 标记 DEFERRED（非门控，不影响整体判定）

**理由**：
- CHECK-5 是**非门控**检查
- 主要依赖 Android Oracle
- 可在后续版本完善

**工作量**: 2h（生成说明文档）

### gate-release 集成 ✅

**方案**: 读取并处理迁移放行项

**实现**：
1. 读取 `spec/.i2h/open-findings.json`
   - 处理 `owner_stage: verify` 的条目
   - 检查上游 blocking findings

2. 读取 `spec/gate-release/verify-focus.json`
   - 扩展验证范围
   - 生成核实报告

3. 记录验证结果
   - 已核实正常 / 确认缺陷 / 未覆盖

**工作量**: 4h

---

## 📅 时间线（最终版）

### Week 1: 文档 + 核心脚本（31.5-45h）

**Phase 1: 核心文档改造** (11-16h)
- Day 1-2: SKILL.md + static-and-identity.md
- Day 3: device-verification.md + ios-specific-checks.md

**Phase 3: 核心脚本实现** (17-23h)
- Day 4-5: ios_device_checker.py + ios_config_parser.py
- Day 6-7: ios_static_analyzer.py + 测试

### Week 2: CHECK-3 简化版（15-20h）

**Phase 4.1: 视觉对齐实现**
- Day 1-2: iOS 截图逻辑
- Day 3: 相似度对比
- Day 4: 报告生成和调试

### Week 3: 收尾（21-26h）

**Phase 4.2: 其他外部 Skills** (6-8h)
- Day 1: CHECK-4 参数适配
- Day 2: CHECK-5 DEFERRED 文档 + gate-release 集成

**Phase 2: 辅助文档** (3.5-6h)
- Day 3: check5-behavior-verify.md + failure-loop.md

**Phase 5: 验证和文档** (9-14h)
- Day 4: 对比报告 + 完成报告
- Day 5: 真实项目测试 + 使用指南

---

## ✅ 可行性评估

### 整体可行性：完全可行 ✅

### 关键成功因素

1. **架构清晰** ✅
   - 五项检查体系完全适用
   - Android 版提供完整参考

2. **核心功能独立** ✅
   - CHECK-1/2 无外部依赖
   - CHECK-3 可独立实现简化版
   - CHECK-4/5 可降级处理

3. **gate-release 已就绪** ✅
   - i2h-spec 完整实现
   - 格式明确，易于集成

4. **工作量可控** ✅
   - 现实场景 ~78h（约 2-3 周）
   - 分阶段交付，风险可控

### 风险等级（最终评估）

| 风险 | 等级 | 缓解措施 | 状态 |
|------|------|---------|------|
| 外部 Skills 依赖 | ⚠️⚠️⚠️ | CHECK-3 独立实现 | ✅ 已规划 |
| iOS 工具链 | ⚠️⚠️ | 优先模拟器，真机可选 | ✅ 已规划 |
| 配置文件复杂性 | ⚠️⚠️ | 使用标准库 plistlib | ✅ 已规划 |
| 时间压力 | ⚠️ | 分阶段交付 | ✅ 已规划 |

**总体风险等级**: ⚠️⚠️ (低-中)

---

## 📊 与其他阶段对比

| 阶段 | 工作量 | 难度 | 外部依赖 | 状态 |
|------|--------|------|---------|------|
| i2h-spec | ~40h | ⭐⭐⭐⭐ | 无 | ✅ 完成 |
| i2h-plan | ~75h | ⭐⭐⭐⭐⭐ | 无 | ✅ 完成 |
| i2h-execute | ~26h | ⭐⭐⭐⭐⭐ | 少量 | ✅ 完成 |
| **i2h-verify** | **~78h** | **⭐⭐⭐⭐** | **中等** | **📋 待开始** |

**i2h-verify 特点**：
- ✅ 工作量适中（比 i2h-plan 少，比 i2h-execute 多）
- ✅ 难度可控（有完整参考实现）
- ⚠️ 外部依赖较多（但有替代方案）
- ✅ 分阶段交付（降低风险）

---

## 🚀 立即行动计划

### 今天完成 ✅

1. ✅ **调研完成** - 本系列文档
2. ✅ **外部 Skills 评估** - 完成
3. ✅ **gate-release 确认** - 完成

### 明天开始 ⭐⭐⭐⭐⭐

4. **Phase 1: 开始核心文档改造**
   - 创建 `i2h-verify/SKILL.md`
   - 创建 `references/static-and-identity.md`
   - 创建 `references/ios-specific-checks.md`

### 本周目标

5. **完成 Phase 1** (11-16h)
6. **开始 Phase 3** (ios_device_checker.py)

---

## 📚 交付物清单

### 文档（Phase 1 + Phase 2）

| 文件 | 预估行数 | 优先级 |
|------|---------|--------|
| SKILL.md | ~450 | ⭐⭐⭐⭐⭐ |
| references/static-and-identity.md | ~150 | ⭐⭐⭐⭐⭐ |
| references/device-verification.md | ~80 | ⭐⭐⭐⭐⭐ |
| references/ios-specific-checks.md | ~200 | ⭐⭐⭐⭐ |
| references/check5-behavior-verify.md | ~130 | ⭐⭐⭐⭐ |
| references/failure-loop.md | ~40 | ⭐⭐ |
| references/verify-report-template.md | ~90 | ⭐⭐⭐ |

### 脚本（Phase 3 + Phase 4）

| 文件 | 预估行数 | 优先级 |
|------|---------|--------|
| scripts/ios_device_checker.py | ~150 | ⭐⭐⭐⭐⭐ |
| scripts/ios_config_parser.py | ~200 | ⭐⭐⭐⭐⭐ |
| scripts/ios_icon_checker.py | ~150 | ⭐⭐⭐⭐ |
| scripts/ios_static_analyzer.py | ~300 | ⭐⭐⭐⭐ |
| scripts/ios_screenshot.py | ~200 | ⭐⭐⭐⭐⭐ |
| scripts/compare_screenshots.py | ~250 | ⭐⭐⭐⭐⭐ |
| scripts/read_gate_release.py | ~100 | ⭐⭐⭐⭐ |
| scripts/tests/* | ~300 | ⭐⭐⭐ |

### 项目文档（Phase 5）

| 文件 | 内容 | 优先级 |
|------|------|--------|
| docs/i2h-verify-gap-analysis.md | Android vs iOS 对比报告 | ⭐⭐⭐⭐⭐ |
| docs/i2h-verify-complete-report.md | 完成报告 | ⭐⭐⭐⭐ |
| docs/i2h-verify-usage-guide.md | 使用指南 | ⭐⭐⭐⭐ |

---

## 💡 关键经验（从调研中学到的）

### 1. 外部依赖评估很重要

**教训**：
- ✅ 不要假设外部 Skills 支持 iOS
- ✅ 提前调研，避免后期发现阻塞
- ✅ 准备替代方案（如 CHECK-3 独立实现）

### 2. 简化版也能满足需求

**教训**：
- ✅ CHECK-3 不需要完全复制 arkts-visual-verify
- ✅ 简化版（双端截图 + 相似度对比）足够
- ✅ 自动修复可以交给后续阶段

### 3. 非门控功能可降级

**教训**：
- ✅ CHECK-5 是非门控，暂时 DEFERRED 不影响整体
- ✅ 优先完成核心功能（CHECK-1/2/3/4）
- ✅ 可选功能可以逐步完善

### 4. 分阶段交付降低风险

**教训**：
- ✅ Week 1: 文档 + 核心脚本（可独立验证）
- ✅ Week 2: CHECK-3 实现（最大风险点）
- ✅ Week 3: 收尾 + 测试（确保质量）

---

## 🎉 调研结论

### ✅ i2h-verify 完全可行

**关键指标**：
- ✅ 架构适用性：100%
- ✅ 核心功能可实现：100%
- ⚠️ 外部依赖覆盖：60%（有替代方案）
- ✅ 工作量可控：~78h（现实场景）
- ✅ 风险可控：低-中等

### 📈 推荐执行路径

1. **立即开始 Phase 1**（核心文档）
2. **并行 Phase 3**（核心脚本）
3. **重点攻克 Phase 4.1**（CHECK-3 简化版）
4. **快速完成 Phase 4.2 & Phase 2**（其他依赖）
5. **真实项目测试**（Phase 5）

### 🎯 预期成果

3 周后交付：
- ✅ 完整可用的 i2h-verify
- ✅ CHECK-1/2/3/4 全部可用
- ✅ CHECK-5 有明确说明（DEFERRED）
- ✅ gate-release 集成完成
- ✅ 完整文档和使用指南

---

## 📞 需要帮助时

如果遇到问题，参考：
1. **i2h-verify-analysis.md** - 完整技术分析
2. **i2h-verify-investigation-report.md** - 外部依赖详情
3. **i2h-execute-错误记录与经验总结.md** - 避免重复踩坑
4. **本文档** - 整体方向和决策依据

---

**报告版本**: v1.0  
**创建时间**: 2024-11-03  
**作者**: Claude Opus 5.5  
**状态**: ✅ 调研完成，准备开始实施  

**下一步**: 开始 Phase 1 - 创建 SKILL.md
