# iOS 改造方法论与过程提取

本文把归档文档中的过程还原成可复用的工程步骤，并把“原版设计”“iOS 适配”“当前验证”分开。

## 一、背景和边界

`hmigbot-1.8.0` 是 Android → HarmonyOS 工具。它提供了成熟的流水线、门禁、产物契约、并发调度和回滚思路，但它的输入事实是 AndroidManifest、Java/Kotlin、Compose/View、ADB 和 Android 资源。`hmigbot-ios` 的工作不是改名复制，而是保留这些控制机制，同时替换平台事实：

| 原版事实 | iOS 版本事实 |
|---|---|
| AndroidManifest、Gradle、Java/Kotlin | `.xcodeproj` / `Package.swift`、Info.plist、Swift/Objective-C |
| Compose/View、Activity/Fragment | SwiftUI View、UIViewController、Storyboard |
| Android API、权限、资源目录 | UIKit/SwiftUI、Entitlements、Assets.xcassets、Localizable.strings |
| ADB / Android baseline | `xcrun simctl` / iOS 真机工具与 HarmonyOS 设备 |
| Android 行为 Oracle | iOS 源码、iOS 设备证据和已批准的平台差异 |

因此，Android 原版只能作为结构和质量基线；任何 Android 专有假设都必须在 i2h 文档或代码中有明确的 iOS 等价物。

## 二、归档文档还原出的实际改造步骤

### 1. 先理解原版，而不是先写转换器

早期文档先研究了原版为什么有 Batch、Slice、Closer、findings 和编译门。这一步的正确产出不是“复制多少文件”，而是回答每个机制解决什么风险：

- findings 防止 Agent 自称修复成功；
- 单写者纪律防止并行任务覆盖共享文件；
- Batch/Slice/Group 把并行边界和依赖关系显式化；
- 编译门阻止错误向下游扩散；
- placeholder registry 记录无法立即落地的差异；
- 产物索引和 digest 让执行可以恢复、复核和增量重跑。

### 2. 先做输入差异矩阵

每个 Android 组件都需要对应的 iOS 输入、目标产物、缺口策略和验证方式。差异矩阵至少覆盖：

- 项目发现：多 target、workspace、Package.swift、Scheme；
- UI 发现：SwiftUI、UIKit、Storyboard、动态容器和导航；
- 业务发现：SwiftData/Core Data、Combine、async/await、UserDefaults、第三方 SDK；
- 资源发现：Assets.xcassets、颜色、字体、字符串、SF Symbols；
- 身份和权限：Info.plist、Entitlements、URL Scheme、相机/通知等权限；
- 设备验证：simctl、真机工具、hdc 和截图/行为证据。

早期 `i2h-spec-gap-analysis.md`、`product-comparison-report.md` 和 `references-integration-analysis.md` 主要完成了这一步，但部分分析仍把“与 Android 对齐”误当成“iOS 已实现”。

### 3. 采用 LLM 主导、脚本确定性辅助

归档中的 `SESSION_SUMMARY.md` 已经纠正了最初的错误方向：Python 正则不应该直接生成完整 Spec。推荐分工是：

- 脚本负责扫描文件、提取确定性字段、统计行数、解析 plist、校验 schema、生成索引和报告；
- LLM 负责理解 Swift 语义、数据流、状态、异常路径、UI 行为和平台差异；
- 任何 LLM 推断必须带源码锚点、confidence 和后续验证方式；
- 脚本失败时可以走受限降级，但必须把降级原因写入 findings，不能静默生成“看起来完整”的产物。

### 4. 以 Spec 产物作为唯一事实源

i2h-spec 应该先生成输入事实，再生成 UI 和功能规格：

1. 项目和 target 清单；
2. UI manifest 与页面 Spec；
3. API、权限、资源和第三方 SDK 清单；
4. feature-index、feature-base 和功能 Spec；
5. placeholder registry、UI/源码覆盖率报告；
6. decision ledger 和 gate-release。

每个页面和功能都必须能追溯到 iOS 文件、符号和行号；每个差异行为都必须能追溯到已批准的决策，而不是让模型自由发挥。

### 5. 以 indexed-v1 计划拆分并发边界

i2h-plan 的有效方向是把计划分为：

- L1 `feature-plan.md`：调度索引；
- `base-plan.md`：共享基础设施任务；
- `slices/*.md`：每个功能切片的来源锚点、依赖、接线账本和差异化 Skill；
- `ui-plan.md`：页面批次、优先级和输出路径；
- coverage matrix：覆盖率和接线归属的机械结果。

计划文件不应该重复 Spec 正文，也不应该由执行阶段回填状态。执行进度应进入 execute brief 和 writeback manifest。

### 6. execute 只做编排和可验证落地

目标执行顺序应保持原版的风险隔离：

- Stage 0：验证目标工程、资源事实和输入闭包；
- Stage 1：按页面批次生成 UI，closer 负责共享接线和资源残量；
- Stage 2：实现 Base 层并通过首道编译门；
- Stage 3：按依赖 Group 并行实现 Feature Slice，集中编译并收口；
- Final：结构闭合、全量编译和最终报告。

Worker 不写共享文件，Closer 通过 writeback manifest 回写账本；任何门禁 FAIL 都要按精确、推断、管线和环境类别处理，不能改报告迎合检测器。

### 7. verify 必须报告真实范围

验证阶段固定做静态分析和 App 身份校验，设备类检查由用户选择。报告必须区分 PASS、FAIL、PARTIAL、DEFERRED、SKIP：

- 未选择的 CHECK 记为 SKIP，不参与结论；
- 设备或依赖缺失记为 DEFERRED，不得写成通过；
- CHECK-5 行为验证如果仍依赖 Android Oracle，就必须保持非门控并说明恢复条件；
- 修复后只复检受影响范围，旧结果不能自动覆盖新代码。

### 8. retrospect 只消费实测数据

回顾报告可以总结自动化率、耗时、token、覆盖率和缺陷，但所有数字必须来自本次运行的产物。Cuike 的数字只能放在历史试点章节，不能写进通用模板作为固定事实。

## 三、这次改造过程暴露出的模型失真模式

归档文档显示了几种典型的低质量模型行为：

1. **提前宣布完成**：同一阶段同时出现“40%”“75%”“100%”“生产就绪”，没有统一证据门。
2. **复制 Android 文案**：根目录 `CHANGELOG.md` 直接变成 Android 原版变更记录，说明平台语义没有经过审查。
3. **用统计数字代替验收**：90.8%、100%、95% 等数字反复出现，却没有对应的编译、设备或行为证据。
4. **生成骨架后忘记运行**：脚本和 wrapper 文件数量很多，但依赖路径、入口命令和测试导入关系没有跑通。
5. **把“对齐设计”写成“已实现”**：文档宣称与 Android 100% 对齐，代码却缺少同等的 helper、ledger 和测试模块。
6. **过程文档互相覆盖**：计划、总结、交接文档不断重复生成，旧版本没有标记 superseded，导致读者无法判断现状。

## 四、以后每个阶段必须遵守的验收纪律

1. 先列出本阶段输入、输出和完成标记。
2. 每写一个脚本，立即运行 `--help`、最小正例和最小反例。
3. 每个引用路径都做存在性检查；缺失时 FAIL 或 DEFERRED，不能静默继续。
4. 每个“完成”结论必须附命令、退出码和产物路径。
5. 统计数字必须注明来源文件、计算方式和适用范围。
6. 每轮只保留一个当前状态文档，旧文档进入归档并标注时间。
7. 真实项目至少覆盖一个 SwiftUI 项目和一个 UIKit/混合项目。
8. 归档后再更新 README、CHANGELOG 和 HANDOVER，避免入口文档继续引用历史路径。
