---
name: i2h-verify
description: 第四步：验证 iOS→HarmonyOS 迁移产出，执行静态分析与 App 身份校验，并由用户选择视觉对齐、单元测试和行为验证，汇总所选范围内的真实结果。当用户说"验证迁移结果""跑一下验证"或在迁移上下文中说"验证""测试"时触发。不要用于生成迁移规格或执行迁移代码（分别用 i2h-spec、i2h-execute）。
metadata:
  type: pipeline
  domain: migration
  tags:
  - pipeline
  - migration
  - verification
---
# i2h-verify

Pipeline 第四步，负责基础检查与可选检查的编排和结果汇总。静态分析与 App 身份校验在主对话执行；用户选中的视觉、UT、行为验证委托对应 verifier。行为验证只报告，具体测试、源码修复、构建和设备执行按各 skill 契约完成。

## 开始前：选择可选检查项

开始任何 CHECK 前，先确定本次执行范围。CHECK-1/2 固定执行；CHECK-3/4/5 可任选、组合或全部不选。

若用户已明确指定（如"只跑 UT""跑 3、4""全部执行"），直接采用该可选检查选择。否则先用多选交互询问，选项仅显示检查编号和名称，不追加括号说明：

> 本次要执行哪些可选检查？可多选：CHECK-3 视觉对齐、CHECK-4 单元测试、CHECK-5 行为验证。也可以回复"全部"或"都不选，仅做 CHECK-1/2"。

无多选工具时用普通文本提问，接受编号或名称组合。收到有效选择后再开始执行；未回复不默认全选。选择只决定执行哪些 CHECK，各 verifier 的修复模式仍按当前任务意图确定。

未选项记为 SKIP（用户未选择），不检查其前置条件、不启动其 verifier、不复用其旧报告。未选 CHECK-5 也不创建 run、不调用 adapter、不读取历史 check12/check5 目录。选择在本次修复和复检中保持不变；用户明确调整时再更新。

"只跑 UT"选 4，"行为验证 / Behavior Verify / 跑效果检查"选 5，"全部执行"选 3/4/5，固定 1/2 始终执行。全选不授权 CHECK-5 第二轮。只验证、不改产品代码的任务选中 CHECK-5 时记 DEFERRED（当前能力与只读约束不兼容），不调用默认修复流程或虚构 verify_only。

## 启动检查 — 待办 findings

读取 `spec/.i2h/open-findings.json`：

| 情况 | 行动 |
|---|---|
| 有 `owner_stage: verify` 的条目 | 先处理这些 |
| 有上游 blocking findings | 🔴 拒绝开工 |

如果存在未解决的上游 blocking findings，停止并提示用户先解决这些问题。

## 输入与范围

- 确认鸿蒙工程根目录、待验证模块和用户指定范围；默认验证当前迁移产出。
- 仅为本次执行项从当前任务、工程记录或 `spec/baseline/` 定位所需的 iOS 源码根目录、页面清单、UI Spec 与功能 Spec，不要求额外的执行报告作为启动凭证。
- **迁移阶段放行项**：存在 `spec/gate-release/verify-focus.json`（i2h-spec `scripts/gate_ledger.py check` 产出）时，读其中每条（工具缺口 / 未达标放行 / 阶段不可判定）。把条目涉及的页面与流程并入已选 verifier 的验证范围（视觉 / 行为验证优先覆盖），在报告「迁移放行项核实」段逐条写结论：`已核实正常`（工具判错，实际行为正确）/ `确认缺陷`（转入失败与建议项）/ `未覆盖`（附原因与恢复条件）。未选设备类检查时整段记 `未覆盖`，不得写成通过。
- 某项输入、设备或 verifier 缺失时，记录该项受影响范围和恢复条件，继续其他可执行项。CHECK-3/4 的输入和设备要求见 [设备验证](references/device-verification.md)；CHECK-5 见 [行为验证](references/check5-behavior-verify.md)，设备/签名缺失不阻止其可行的源码工作。

## 五项检查

执行 CHECK-1/2，再按 CHECK-3 → CHECK-4 → CHECK-5 的相对顺序执行已选项；每项结束后立即读取实际产物并记录结论。

| 编号 | 检查项 | 执行方式 | 通过条件 |
|---|---|---|---|
| CHECK-1 | 静态分析 | 扫描并复核迁移代码中的类型、导入、SQL、动态执行和生命周期用法 | ERROR 为 0；WARN 附报告 |
| CHECK-2 | App 身份校验 | 检查应用配置、名称和图标资源 | FAIL 为 0；WARN 附报告 |
| CHECK-3 | 视觉对齐 | 双端截图对比（简化版实现）| 完成范围内实测且无未解决差异；纯 ALIGN 差异记建议项 |
| CHECK-4 | 单元测试 | `arkts-ut-verifier` | 全范围实际 GREEN，无未验证设计点 |
| CHECK-5 | 行为验证（可选） | `arkts-behavior-verify` 一次联合调用 | 只报告设置/点击稳定终态；不判全域 PASS，不参与整体判定 |

CHECK-1/2 的具体规则见 [静态分析与 App 身份](references/static-and-identity.md)。CHECK-3 的实现见 [设备验证](references/device-verification.md)。CHECK-4/5 的模式、产物和状态映射见 [设备验证](references/device-verification.md)。

## CHECK-1：静态分析

扫描本次范围内各模块的生产 `.ets` 文件，排除构建产物、缓存和第三方依赖。使用 `rg -n -g '*.ets'` 定位候选，再读取上下文确认；注释、字符串和普通同名标识符不作为违规。

执行 **15 项检查**（6 项通用 + 9 项 iOS 特有）：

### 通用检查（6 项）

| 检查项 | 定位与复核方式 | 级别 |
|--------|---------------|------|
| `any` 类型 | 搜索 `\bany\b`，确认是否为类型用法 | ERROR |
| 旧 `@ohos.*` 导入 | 搜索 `@ohos\.`，确认 import 来源，列出迁移建议 | WARN |
| SQL 拼接 | 搜索 SQL 关键字与数据库执行调用，复核是否通过字符串拼接构造 SQL | ERROR |
| `as` 类型断言 | 搜索 `\bas\b`，确认断言用法 | WARN |
| `eval()` | 搜索 `\beval\s*\(`，确认动态执行调用 | ERROR |
| `aboutToAppear` 中获取路由参数 | 定位 `aboutToAppear` 方法，复核其中的 `pathInfo` 参数读取 | ERROR |

### iOS 特有检查（9 项）

详见 [iOS 特有检查规则](references/ios-specific-checks.md)：

| 检查项 | 定位与复核方式 | 级别 | 原因 |
|--------|---------------|------|------|
| 强制解包 `!` | 搜索 `\w+!\.` 或 `\w+!\s*$`，确认强制解包 | WARN | 可能导致运行时崩溃 |
| `@escaping` 闭包 | 搜索 `@escaping`，复核是否已正确转换 | WARN | Swift 闭包生命周期管理 |
| `weak`/`unowned` | 搜索 `\bweak\b` / `\bunowned\b`，ArkTS 不需要手动内存管理 | WARN | 迁移遗留 |
| `@objc` / `@objcMembers` | 搜索 `@objc`，Objective-C 互操作标记 | WARN | 迁移遗留 |
| `#available` / `@available` | 搜索 `available`，iOS 版本检查已无意义 | WARN | HarmonyOS 不适用 |
| `DispatchQueue` | 搜索 `DispatchQueue`，需改为 TaskPool/Worker | ERROR | 必须改为 ArkTS 并发 |
| `NotificationCenter` | 搜索 `NotificationCenter`，需改为 Emitter | WARN | 需改为鸿蒙通知机制 |
| `UserDefaults` | 搜索 `UserDefaults`，必须改为 Preferences | ERROR | 必须改为鸿蒙本地存储 |
| `UIKit` / `SwiftUI` 导入 | 搜索 `import UIKit` / `import SwiftUI` | ERROR | 迁移未完成 |

每个有效命中记录文件、行号、规则和简短依据。ERROR 为 0 则 PASS；有 ERROR 则 FAIL。WARN 只附报告，不单独触发修复回环。没有找到应验证的源码时记录输入缺口，不能以零命中判 PASS。

## CHECK-2：App 身份校验

读取 iOS 源码的 `Info.plist` 和 HarmonyOS 的 `AppScope/app.json5`、模块配置及实际引用的字符串/图标资源；名称以 **init 锁定的 `.migbot/config.json` 的 `app_name`（即 ArkTS 应用显示名）** 为依据（名称修改权已锁定前移到 init；无 `.migbot/config.json` 或 `app_name` 为空时才回退项目已有 Spec 中的 App 名称）。

| 项目 | 检查规则 | 判定 | iOS 数据源 |
|------|---------|------|-----------|
| bundleName | 仍匹配 `com.example.*` | FAIL | 对比 iOS `CFBundleIdentifier` |
| vendor | 仍为 `example` | FAIL | - |
| versionName | 与 iOS `CFBundleShortVersionString` 不一致 | WARN | Info.plist |
| versionCode | 与 iOS `CFBundleVersion` 不一致 | WARN | Info.plist |
| app_name | 与锁定名称（无锁定时为 Spec 已明确记录的名称）不一致 | FAIL | iOS `CFBundleDisplayName` |
| 应用图标 | `layered_image.json` 不存在或引用错误 | FAIL | 对比 iOS `Assets.xcassets/AppIcon.appiconset/` |
| 图标尺寸 | 对实际使用的 foreground/background PNG 检查大小，≤ 1 KB 时提示疑似默认图 | WARN | - |

**iOS 配置解析**：
- 使用 Python `plistlib`（标准库）解析 `Info.plist`（支持 XML 和 Binary 格式）
- 解析 `Assets.xcassets/AppIcon.appiconset/Contents.json` 获取图标信息
- 验证图标文件实际存在并检查尺寸

路径与资源名按当前工程解析，避免把示例文件名当作唯一合法配置。未记录预期 App 名称（无锁定值且 Spec 未记录）时注明未做名称一致性比较；无法读取必要配置或资源时记录相应缺口。

有明确 FAIL 则 CHECK-2 为 FAIL；仅因缺失输入无法完成必要判断时为 PARTIAL/DEFERRED；其余为 PASS，附 WARN 和不适用项说明。

## CHECK-3：视觉对齐（简化版实现）

**实现方式**：在 i2h-verify 主对话中执行双端截图对比（不依赖 arkts-visual-verify）

### 设备可用性检测

在执行前自动检测双端设备：

```bash
# iOS 设备检测
# 1. 模拟器：xcrun simctl list devices | grep Booted
# 2. 真机：idevice_id -l（需要 libimobiledevice）

# HarmonyOS 设备检测
# hdc list targets
```

**检测结果处理**：
- 两端设备都可用 → 继续执行
- 任一端设备不可用 → 记 DEFERRED，生成说明文档，退出 CHECK-3

### 执行流程

1. **准备工作**：
   - 创建截图目录：`spec/verify/screenshots/{ios,harmonyos,comparison}/`
   - 读取页面列表（从 `spec/baseline/ui-manifest.md` 或配置）
   - 扩展验证范围（纳入 gate-release 迁移放行项）

2. **iOS 端截图**（Baseline）：
   - 模拟器：`xcrun simctl io <device> screenshot <file>`
   - 真机：`idevicescreenshot <file>`
   - 每个页面截图后验证文件存在

3. **HarmonyOS 端截图**：
   - 确保应用已安装：`hdc install <hap>`
   - 启动应用：`hdc shell aa start -a EntryAbility -b <bundle>`
   - 截图：`hdc shell snapshot_display -f /data/local/tmp/<page>.png`
   - 传输：`hdc file recv /data/local/tmp/<page>.png <local>`

4. **图像相似度对比**：
   - 使用 Python PIL + imagehash
   - 计算感知哈希（perceptual hash）
   - 汉明距离转换为相似度百分比
   - 阈值：≥95% 为高度匹配，≥85% 为良好，<85% 为差异较大

5. **生成详细报告**：
   - 一次性生成完整报告：`spec/verify/ui-comparison.md`
   - 包含每个页面的截图路径、相似度、差异分析
   - 总体统计：匹配页面数、平均相似度、匹配率

### 状态判定

| 实际结果 | CHECK-3 状态 |
|---|---|
| 范围内验证完成，平均相似度 ≥ 95% | PASS |
| 平均相似度 85-95%，无功能性问题 | FAIL-visual，附建议项 |
| 平均相似度 < 85% 或存在功能性差异 | FAIL-functional |
| 设备不可用 | DEFERRED，注明恢复条件 |
| 截图失败 | PARTIAL，保留已确认失败 |

**注意**：
- 此简化版**不包含自动修复**功能
- 仅做双端截图对比和相似度分析
- 发现的差异记录到报告，由后续阶段处理

详细实现见 [设备验证](references/device-verification.md) 的 CHECK-3 章节。

## CHECK-4：单元测试

调用 `arkts-ut-verifier`，传入：
- `--ios-source-root <ios-project-root>`（参数名适配，实际传 iOS 路径）
- `--harmonyos-root <harmonyos-project-root>`
- `--mode verify_fix` / `verify_only`（默认 `verify_fix`）
- `--skip-oracle true`（跳过 Android Oracle 采集，或设置 `UT_ANDROID_ORACLE=off`）
- `--test-framework xctest`（指定测试框架）

**iOS 特性适配**：
- iOS 测试位置：`<Project>Tests/` (单元测试)、`<Project>UITests/` (UI 测试)
- 文件命名：`*Tests.swift`
- 测试框架：XCTest

读取 `spec/verify/ut/ut-report.md`、`_state.yaml` 和当前轮 `_ut_summary.md`；进入修复循环且已有退出摘要时一并读取 `round-N/final-summary.md`。不要要求 `verify_only` 生成修复循环专属产物。

**判定**：
- 全范围实际 GREEN，且无未验证设计点、待补测或复核项 → PASS
- 有实际 RED、ERROR 或最终 FAIL → FAIL，分别记录产品、测试和环境原因
- CONVERGED、缺证据、外部前置阻塞或尚未复测的修复 → PARTIAL；保留原始退出状态，已确认失败仍按 FAIL 报告

通过率、设计验证率和 AC 完成率按报告原口径引用，不能把已执行用例通过率当作全设计范围已验证。

**限制**：
- 由于跳过 Oracle 采集，测试用例需要手动编写或基于 Spec
- 不自动生成测试用例
- 以 Spec 为准（而非 iOS 实际行为）

详细见 [设备验证](references/device-verification.md) 的 CHECK-4 章节。

## CHECK-5：行为验证（可选，非门控）

**当前状态**：DEFERRED

**原因**：`arkts-behavior-verify` 主要基于 Android Oracle，iOS 适配进行中

**执行条件**（如未来支持）：
- 调用 `$arkts-behavior-verify`
- 传入：`ios_root`、`arkts_root`、`out`、`max_agents`、`ios_device_type`
- 默认 `repair_mode=single-round`
- 明确授权才执行 `--full-repair` 第二轮

**状态映射**（参考）：
- WARN：已修改并安装，但正确性未验证
- DEFERRED：前置不满足（当前 iOS 不支持）
- ERROR：构建/安装/流程失败

**非门控特性**：
- CHECK-5 的全部状态均不加入基础及已选视觉/UT 范围结论
- 不触发 `failure-loop.md` 的 i2h-execute 回环
- 不决定 `ui-manifest.md` 的 `verified` 回写
- 源码修复后需复检 CHECK-1/2 及已选 CHECK-3/4

详细见 [行为验证](references/check5-behavior-verify.md)。

## 执行与修复

1. 执行 CHECK-1/2，记录文件位置、复核依据与问题级别。
2. 将工程路径、验证范围和当前任务的修复约束传给已选 verifier。UT 默认 `verify_fix`，仅验证时使用 `verify_only`。
3. 按 CHECK-3 → CHECK-4 → CHECK-5 的相对顺序串行执行已选项；设备交接前确认前一 verifier 真实退出并释放设备，静默 5 秒。CHECK-5 按 [行为验证](references/check5-behavior-verify.md) 只联合调用一次，默认 single-round；未选项保持 SKIP，全部不选则汇总基础检查。
4. 每段结束后读取本次报告、当前轮摘要和必要证据，保留原始状态。verifier 的内部修复由其自身调度，i2h-verify 不另派同类 fixer，也不重置内部轮数。
5. 仍需由执行阶段处理的失败按 [失败处理](references/failure-loop.md) 回到 `i2h-execute`；CHECK-5 状态不触发该回环。包括 CHECK-5 在内的源码修复结束后，复检 CHECK-1、受影响的 CHECK-2 及已选 CHECK-3/4；未复测的受影响设备项记 PARTIAL，已确认失败保留。
6. 汇总到 `spec/verify-report.md`，使用 [报告模板](references/verify-report-template.md)。

构建、签名和安装由所选 verifier 按自身契约处理；构建或运行失败按实际结果记录，不新增独立编译检查。后续修复改变已测代码或配置时，复检受影响项；未复检的旧结果注明未覆盖当前改动。

## 结果判定

| 单项状态 | 含义 |
|---|---|
| PASS | 约定范围内验证完成且通过；非阻塞 WARN 可随附 |
| FAIL | 已确认检查失败或验证执行失败，注明产品、测试或环境原因 |
| PARTIAL | 已执行一部分，但仍有未验证、待复核或未覆盖当前改动的范围 |
| DEFERRED | 因输入、设备或 skill 等前置缺失而未执行，注明恢复条件 |
| SKIP | 用户未选择的 CHECK-3/4/5，不参与本次结论计算 |
| FAIL-visual | CHECK-3 仅有 ALIGN 纯视觉差异，作为建议项 |
| FAIL-functional | CHECK-3 存在功能性问题 |
| WARN / ERROR | CHECK-5 的未验证修复 / 流程或结果错误；仅报告，其 SKIP/DEFERRED 同样不参与整体判定 |

基础及已选视觉/UT 范围结论仅根据 CHECK-1/2 和已选 CHECK-3/4 计算；排除 CHECK-5 的全部状态：

- 存在 FAIL 或 FAIL-functional → **FAIL**
- 没有上述失败，但存在 PARTIAL 或 DEFERRED → **PARTIAL**，明确尚未验证的范围
- 其余情况 → **PASS**；存在 WARN 或 FAIL-visual 时标注"通过，附建议项"

已选项未生成报告、修复文件已写入或问题文件目录为空，都不能据此判 PASS。报告明确写出执行项与未选项；PASS 仅表示本次范围通过，存在未选项时不能描述为所有五项均已验证。CHECK-5 单列"行为验证结果（非门控）"；安装成功或局部点击通过仍为 WARN，设置正确性未验证。

## 收尾：上报本阶段用量与迁移完成信号

verify 成功产出 `spec/verify-report.md` 后，作为本 skill 的最后一步依次执行（均为纯本地 Bash，**忽略退出码、绝不阻断**）：

```bash
# 1. 统计 iOS + HarmonyOS 两侧代码行，上传"迁移完成信号"
.migbot/bin/i2h count-lines

# 2. 上报本阶段 token 用量（usage.v2 快照）
.migbot/bin/i2h mark-stage i2h-verify
```

- **`count-lines`** 现在是迁移"已完成"的判定点（从 retrospect 前移到此）：它采集两侧行数并记为 fact（含 `ios_app_name` / `ios_version` / `harmonyos_app_name` + `code_lines`），服务端凭其中的 HarmonyOS total 判定完成。此刻两侧代码都已就位，是行数盘库的第一个有效时点——i2h-init 那次盘库跑在迁移之前，HarmonyOS 侧尚不存在。i2h-retrospect 结尾还会再盘一次（覆盖同一 run 的 fact），两次都跑不会重复计数。
- **`mark-stage i2h-verify`** 写出本阶段的 stage-marks fact；生命周期 hook 上传的会话切片在服务端据此归属到 verify 阶段，供性能看板的事件时间轴使用。

---

## 参考文件

| 文件 | 用途 |
|---|---|
| [静态分析与 App 身份](references/static-and-identity.md) | CHECK-1/2 执行规则（含 iOS 特有检查）|
| [iOS 特有检查规则](references/ios-specific-checks.md) | iOS 特有的 9 项静态分析规则详解 |
| [设备验证](references/device-verification.md) | CHECK-3 简化版实现 + CHECK-4 调用 |
| [行为验证](references/check5-behavior-verify.md) | CHECK-5 执行契约、状态映射和非门控边界 |
| [失败处理](references/failure-loop.md) | 外层修复范围、退出条件和复检 |
| [报告模板](references/verify-report-template.md) | 五项结果与证据汇总 |

---

**版本**: v2.0  
**最后更新**: 2024-11-03  
**更新人**: 模型 Opus 5.5  
**状态**: ✅ iOS 完整适配版本

Co-Authored-By: 模型 Opus 5.5 <noreply@anthropic.com>
