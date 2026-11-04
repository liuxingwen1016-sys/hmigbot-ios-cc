# 验证报告模板

输出到 `spec/verify-report.md`。更新当前报告正文，状态与数字取自本次实际验证结果；不适用的明细可省略。五项总表始终保留，未选可选项填写 SKIP（用户未选择），证据填"—"，不读取旧结果充数。

---

# 迁移验证报告

- **工程**: {鸿蒙工程路径}
- **iOS 源码**: {iOS 源码路径}
- **验证范围**: {模块、页面、功能及排除范围}
- **执行项**: CHECK-1/2 + {用户选择的可选项；都不选时注明仅基础检查}
- **未选项**: {CHECK-3/4/5 中用户未选的项目；全选时写"无"}
- **代码与实测依据**: {工作树状态/相关改动、verifier 轮次与测试包标识}
- **基础及已选视觉/UT 范围结论**: {PASS / FAIL / PARTIAL；仅 CHECK-1/2 + 已选 CHECK-3/4}
- **行为验证结果（非门控）**: {CHECK-5 SKIP/WARN/DEFERRED/ERROR；不计入上述结论}

---

## 五项结果

| 编号 | 检查项 | 状态 | 结果摘要 | 证据 |
|---|---|---|---|---|
| CHECK-1 | 静态分析 | {PASS/FAIL} | {ERROR 为 0 → PASS；有 ERROR → FAIL} | {违规文件数、ERROR 数、WARN 数} |
| CHECK-2 | App 身份校验 | {PASS/FAIL/PARTIAL} | {FAIL 为 0 → PASS；有 FAIL → FAIL} | {检查项通过数/总数} |
| CHECK-3 | 视觉对齐 | {PASS/FAIL-visual/FAIL-functional/PARTIAL/DEFERRED/SKIP} | {平均相似度、匹配页面数} | {截图路径、对比报告} |
| CHECK-4 | 单元测试 | {PASS/FAIL/PARTIAL/DEFERRED/SKIP} | {通过率、设计验证率} | {UT 报告路径、轮次} |
| CHECK-5 | 行为验证（非门控）| {WARN/DEFERRED/ERROR/SKIP} | {当前状态说明} | {行为报告路径（如有）} |

**注**：
- 状态含义见下方"结果判定"章节
- CHECK-5 不参与整体判定（非门控）

---

## CHECK-1：静态分析

### 执行概况

- 扫描文件数: {数量}
- 扫描代码行数: {行数}
- 执行规则数: 15 项（6 通用 + 9 iOS 特有）

### 检查结果

| 规则 | 级别 | 命中数 | 状态 |
|------|------|--------|------|
| `any` 类型 | ERROR | {数量} | {✅/❌} |
| 旧 `@ohos.*` 导入 | WARN | {数量} | {✅/⚠️} |
| SQL 拼接 | ERROR | {数量} | {✅/❌} |
| `as` 类型断言 | WARN | {数量} | {✅/⚠️} |
| `eval()` | ERROR | {数量} | {✅/❌} |
| `aboutToAppear` 路由参数 | ERROR | {数量} | {✅/❌} |
| **iOS: 强制解包 `!`** | WARN | {数量} | {✅/⚠️} |
| **iOS: `@escaping` 闭包** | WARN | {数量} | {✅/⚠️} |
| **iOS: `weak`/`unowned`** | WARN | {数量} | {✅/⚠️} |
| **iOS: `@objc` 互操作** | WARN | {数量} | {✅/⚠️} |
| **iOS: `#available` 检查** | WARN | {数量} | {✅/⚠️} |
| **iOS: `DispatchQueue`** | ERROR | {数量} | {✅/❌} |
| **iOS: `NotificationCenter`** | WARN | {数量} | {✅/⚠️} |
| **iOS: `UserDefaults`** | ERROR | {数量} | {✅/❌} |
| **iOS: `UIKit`/`SwiftUI` 导入** | ERROR | {数量} | {✅/❌} |

**汇总**:
- ✅ ERROR 总数: {数量}（必须为 0）
- ⚠️ WARN 总数: {数量}（建议修复）

### ERROR 详情（如有）

#### 1. {规则名称}

**文件**: {文件路径}:{行号}  
**代码片段**:
```typescript
{违规代码}
```

**问题**: {问题描述}  
**建议修复**:
```typescript
{修复示例}
```

---

### WARN 详情（如有）

#### 1. {规则名称}

**影响文件**: {数量} 个  
**代表性示例**: {文件路径}:{行号}  
**建议**: {修复建议}

---

### CHECK-1 判定

- **状态**: {PASS / FAIL}
- **结论**: {ERROR 为 0 则 PASS，否则 FAIL}

---

## CHECK-2：App 身份校验

### 配置来源

- **iOS**: {iOS Info.plist 路径}
- **HarmonyOS**: {HarmonyOS app.json5 路径}
- **锁定名称**: {.migbot/config.json 中的 app_name}

### 检查结果

| 项目 | iOS 值 | HarmonyOS 值 | 判定 | 说明 |
|------|--------|-------------|------|------|
| bundleName | {CFBundleIdentifier} | {bundleName} | {✅ PASS / ❌ FAIL} | {是否为示例值} |
| vendor | - | {vendor} | {✅ PASS / ❌ FAIL} | {是否为 example} |
| versionName | {CFBundleShortVersionString} | {versionName} | {✅ PASS / ⚠️ WARN} | {是否一致} |
| versionCode | {CFBundleVersion} | {versionCode} | {✅ PASS / ⚠️ WARN} | {是否一致} |
| app_name | {CFBundleDisplayName} | {实际显示名} | {✅ PASS / ❌ FAIL} | {与锁定名称比较} |
| 应用图标 | {Assets.xcassets 路径} | {layered-image.json} | {✅ PASS / ❌ FAIL} | {是否存在且引用正确} |
| 图标尺寸 | - | 前景: {size} KB, 背景: {size} KB | {✅ PASS / ⚠️ WARN} | {≤ 1 KB 为疑似默认图} |

### FAIL 详情（如有）

#### 1. {项目名称}

**问题**: {详细描述}  
**当前值**: {实际值}  
**期望值**: {期望值}  
**影响**: {为什么这是问题}  
**修复建议**: {如何修复}

---

### CHECK-2 判定

- **状态**: {PASS / FAIL / PARTIAL}
- **结论**: {判定依据}
- **FAIL 数**: {数量}
- **WARN 数**: {数量}

---

## CHECK-3：视觉对齐（简化版）

### 执行概况

- **iOS 设备**: {设备类型} - {设备 ID}
- **HarmonyOS 设备**: {设备 ID}
- **验证页面数**: {总数}
- **截图成功数**: iOS {数量} / HarmonyOS {数量}

### 对比结果

| 页面 | 相似度 | 判定 | 说明 |
|------|--------|------|------|
| {页面名} | {百分比}% | {✅ 匹配 / ⚠️ 轻微差异 / ❌ 差异大} | {差异说明} |
| ... | ... | ... | ... |

**统计**:
- 高度匹配 (≥95%): {数量} / {总数} ({百分比}%)
- 良好 (85-95%): {数量}
- 差异较大 (<85%): {数量}
- 平均相似度: {百分比}%

### 差异分析

#### 功能性差异（如有）

1. **{页面名}** - 相似度 {百分比}%
   - 问题: {具体差异描述}
   - 影响: {功能影响}
   - 建议: {修复建议}

#### 视觉差异（如有）

1. **{页面名}** - 相似度 {百分比}%
   - 差异类型: {字体/间距/颜色/布局}
   - 建议: {优化建议}

### 截图证据

- **iOS 截图**: `spec/verify/screenshots/ios/`
- **HarmonyOS 截图**: `spec/verify/screenshots/harmonyos/`
- **对比报告**: `spec/verify/ui-comparison.md`

### CHECK-3 判定

- **状态**: {PASS / FAIL-visual / FAIL-functional / PARTIAL / DEFERRED}
- **平均相似度**: {百分比}%
- **结论**: {判定依据}

**或**（如未选择或设备不可用）:

- **状态**: SKIP（用户未选择）/ DEFERRED（设备不可用）
- **原因**: {原因说明}
- **恢复条件**: {如何恢复}

---

## CHECK-4：单元测试

### 执行概况

- **iOS 源码**: {iOS 源码路径}
- **测试框架**: XCTest
- **模式**: {verify_fix / verify_only}
- **Oracle**: {跳过 iOS Oracle 采集}

### 测试结果

- **总用例数**: {数量}
- **通过**: {数量} ({百分比}%)
- **失败**: {数量}
- **跳过**: {数量}
- **错误**: {数量}

### 设计验证率

- **设计点总数**: {数量}（来自 Spec）
- **已验证**: {数量}
- **未验证**: {数量}
- **验证率**: {百分比}%

### 失败详情（如有）

#### 1. {测试用例名}

**文件**: {测试文件路径}  
**失败原因**: {RED / ERROR / 环境问题}  
**预期**: {预期结果}  
**实际**: {实际结果}  
**影响**: {功能影响}

### 修复历史（如有）

- **轮次**: Round {N}
- **修改文件**: {数量} 个
- **本轮通过**: {数量} 个测试

### 证据

- **UT 报告**: `spec/verify/ut/ut-report.md`
- **状态文件**: `spec/verify/ut/_state.yaml`
- **当前轮摘要**: `spec/verify/ut/round-{N}/_ut_summary.md`

### CHECK-4 判定

- **状态**: {PASS / FAIL / PARTIAL / DEFERRED}
- **结论**: {判定依据}

**或**（如未选择）:

- **状态**: SKIP（用户未选择）

---

## CHECK-5：行为验证（非门控）

### 执行状态

- **状态**: {WARN / DEFERRED / ERROR / SKIP}
- **原因**: {状态说明}

### 设置验证（如执行）

- **验证项数**: {数量}
- **通过**: {数量}
- **失败**: {数量}

### 点击验证（如执行）

- **验证项数**: {数量}
- **通过**: {数量}
- **失败**: {数量}

### 证据（如有）

- **CHECK-5 摘要**: `spec/verify/check5/CHECK5_SUMMARY.md`
- **行为报告**: `spec/verify/check5/behavior-effect/<run-id>/`

### CHECK-5 判定

- **状态**: {WARN / DEFERRED / ERROR / SKIP}
- **非门控**: 不参与整体验证结论

**当前情况**（典型）:

- **状态**: DEFERRED
- **原因**: arkts-behavior-verify 主要基于 Android Oracle，iOS 适配进行中
- **恢复条件**: 实现 iOS Oracle 支持或使用 HarmonyOS 端行为作为验证基准
- **建议**: 通过 CHECK-3 视觉对齐观察 UI 行为问题；人工补充关键交互验证

---

## 迁移放行项核实

{如存在 `spec/gate-release/verify-focus.json`，则包含此节；否则省略}

来源 `spec/gate-release/verify-focus.json`；每条一行，不得省略。

| 决策 | 类型 | 门禁 | 核实问题 | 结论 | 证据 |
|---|---|---|---|---|---|
| {决策 ID} | {工具缺口/未达标放行/阶段不可判定} | {gate_a/b/c} | {核实问题描述} | {已核实正常/确认缺陷/未覆盖} | {证据路径或说明} |

**汇总**:
- 总放行项: {数量}
- 已核实正常: {数量}
- 确认缺陷: {数量}
- 未覆盖: {数量}

---

## 修复历史

{如发生修复回环，记录各轮历史；否则写"无修复回环"}

### Round 1

- **触发**: {CHECK-1/2 失败项}
- **修复计划**: `spec/plans/plan-fix-verify-{timestamp}.md`
- **改动文件**: {数量} 个
- **复检结果**: {通过/部分通过/仍有失败}

### Round 2

- **触发**: {剩余失败项}
- **修复计划**: `spec/plans/plan-fix-verify-{timestamp}.md`
- **改动文件**: {数量} 个
- **复检结果**: {通过/部分通过/仍有失败}

---

## 整体判定

### 基础及已选视觉/UT 范围结论

{仅根据 CHECK-1/2 和已选 CHECK-3/4 计算，排除 CHECK-5}

- **状态**: {PASS / FAIL / PARTIAL}
- **依据**: {判定依据}

**判定规则**:
- 存在 FAIL 或 FAIL-functional → **FAIL**
- 没有上述失败，但存在 PARTIAL 或 DEFERRED → **PARTIAL**
- 其余情况 → **PASS**（存在 WARN 或 FAIL-visual 时标注"通过，附建议项"）

### 未验证范围

{明确说明 SKIP 的项目和原因}

- CHECK-3: {SKIP / 已验证}
- CHECK-4: {SKIP / 已验证}
- CHECK-5: {SKIP / DEFERRED} （非门控）

### 建议项（如有）

1. {WARN 或 FAIL-visual 项目}
2. {优化建议}
3. ...

---

## 遗留问题（如有）

### 未解决的 ERROR

1. **{问题描述}**
   - 文件: {路径}
   - 尝试轮次: {数量}
   - 状态: {当前状态}
   - 建议: {下一步行动}

### 未解决的 FAIL

1. **{问题描述}**
   - 影响: {影响范围}
   - 建议: {下一步行动}

---

## 下一步

{根据验证结果建议下一步行动}

**如 PASS**:
- ✅ 验证全部通过
- 建议: 运行 `/i2h-retrospect` 生成最终报告

**如 FAIL**:
- ❌ 存在 {数量} 个未解决问题
- 建议: 
  1. 修复遗留问题
  2. 重新运行 `/i2h-verify` 复检

**如 PARTIAL**:
- ⚠️  部分验证完成
- 未覆盖范围: {说明}
- 建议: {根据具体情况}

---

**报告版本**: v1.0  
**生成时间**: {ISO 8601 时间戳}  
**生成工具**: i2h-verify v2.0

