# 原版 hmigbot-1.8.0 与 hmigbot-ios 对比分析

**分析日期**: 2026-11-06  
**原版**: `../hmigbot-1.8.0`，Android → HarmonyOS  
**当前版本**: `hmigbot-ios`，iOS → HarmonyOS

## 原版的 UI 完备度提升来自什么

原版的提升来自一条由 Spec 持有的证据链。它把“页面是否完整”拆成结构、样式、语义、资源、对话框、导航和真实运行时状态，之后由 Execute 和 Verify 消费同一批证据。

### Spec 阶段先拿到真实 UI 证据

`a2h-spec/SKILL.md` 的 Phase A-0 先选择 `ui_facts_policy` 和 runtime 策略。`runtime_required` 或 `progressive` 模式必须由主线程调用 `android_fast_traverse`，采集页面截图、UIAutomator `view.xml`、动作收据、SHA256、设备信息和包身份。结果落在 `spec/baseline/ui-snapshots/page_NNNN_<ClassName>/`，缺设备、包身份或路线证据时阻断。

这条规则解决了代码静态分析无法回答的问题。页面是否真的能到达、弹窗是否覆盖内容、状态切换是否改变布局、动态菜单和 RecyclerView item 是否出现，都有运行时证据。历史运行不会被覆盖，snapshot 带有 `run_id` 和 provenance。

### 使用三源数据生成页面 Spec

原版明确规定三源数据职责：

- `view.xml` 负责结构和可见层级；
- 源码 layout XML、`visual.json` 和资源事实负责尺寸、颜色、字体和样式；
- `meta.json` 负责页面语义、状态、导航、动态菜单、BottomSheet、RecyclerView item 和来源锚点。

`a2h-spec/references/three-source-and-scale.md`、`static-ui-facts.md`、`phase-a-scan-strategies.md` 共同约束字段、confidence 和降级路径。真实采集缺失时只能标记 `source_only` 或 `progressive`，不能伪装成真实截图。

### 对话框和覆盖率单独闭合

原版把 DialogFragment 子类、Dialog 使用点、宿主页面、layout owner 和变体都纳入 inventory。`prepare_dialog_artifacts.py` 生成 dialog snapshots，Gate C 检查 snapshot 引用和宿主关系。Phase C 还强制调用 `arkts-ui-coverage-auditor` 和源码 coverage auditor，页面、导航、Dialog、系统集成和源码 ownership 任何一层缺口都要进入报告或回到上游补齐。

### 资源不是文件复制，而是闭包迁移

`android2hmos_resources_convert` 先尝试从 Gradle/APK/AAR 解析合并资源，失败后才回退到源代码，并记录 `build_status` 和 `resource_source`。资源转换覆盖 strings、colors、dimens、drawable、vector、selector、自适应图标、多语言和 qualifiers。

资源索引还记录 `@refs` 依赖、layout/menu 使用、未解析引用、SVG 可渲染性和缺失源。Execute Stage 0 消费 `res-index/{values,drawables,usage,design-tokens}.json`，Stage 1 的 resource sweep 再检查生成代码的实际资源引用，避免只迁移 `res/` 目录却漏掉代码和布局使用到的资源。

### Verify 复用同一份基线并增量复验

`visual-verify-speed` 复用 Spec 的 Android traverse 产物。鸿蒙端按同一棵页面树逐边走查，先用结构和度量预筛 `auto_pass`、`carried`，剩余项按 Activity 和 resource-id 分批并行 judge。修复按不相交文件组并行，统一编译后只复验改动单元，避免全量重复采集。

## 原版的性能提升来自什么

### Spec 侧的真实并行

原版不是只提高 Agent 数量。它把 Spec 分成互不写冲突的后台轨：模块依赖、API inventory、auth probe、UI 分页和 feature 分页。`references/subagent-prompts.md` 规定空回执、等待、停滞和重派行为，主线程在 join 点合并结果。

API inventory 可以和 UI 分析重叠，auth probe 可以和后续 Gate B/C 工作重叠，页面和 feature 任务按写入目录隔离。这样并行减少的是关键路径，而不是让更多 Agent 同时修改同一份文件。

### 机械批次规划和宿主并发上限

`a2h-spec/scripts/plan_batches.py` 根据页面规模和 anchored LOC 生成 batch plan，使用 LPT 等策略平衡任务长度。宿主并发参数按 Claude、Codex、DevEco Code 分开配置，超出上限的任务排队，批内完成后补位。

### Execute 按依赖就绪派发

Stage 1 按 `BATCH_MAX` 派发页面，Batch closer 负责共享文件和 writeback。Stage 2 Base 任务按 `parallel_group` 派发。Stage 3 不等待整个上游 Group，而是等每个 Slice 的 `depends_on` 就绪后立即派发。Worker 只写自己的文件，group-closer 负责跨文件接线和结构收口。

### 编译集中到三道门

页面批次和 Group 内不重复编译，正式编译集中到 Base-7、Stage 3 gate 和 FV-2。资源 sweep、writeback、结构审计和编译结果有清晰的职责边界。空信封、卡死和停滞会触发催询、取消、重派或降并发，避免主线程无限等待。

## iOS 版本实际完成到什么程度

| 能力 | iOS 当前实现 | 与原版差距 |
|---|---|---|
| iOS 项目和 SwiftUI/UIKit 语义 | `i2h-spec` 文档、模板和 iOS mapping 已有 | 基础设计已建立 |
| Spec 阶段真实双端采集 | 没有等价的 simctl/真机 runtime facts 闭环 | 缺少 Spec-owned screenshot、XML、状态和 provenance |
| 三源 UI facts | 有 meta/页面 Spec 设计，缺少完整生成器和统一 schema | 不能证明页面结构、样式和语义都来自同一份事实 |
| Dialog/导航/源码 coverage | 有覆盖率文档和模板 | 缺少原版级别的运行时枚举、dialog artifact 和机械审计链 |
| iOS 资源闭包 | `ios2hmos_resources_convert/SKILL.md` 有设计说明 | 其引用的 `scripts/scan_ios_resources.py` 等不存在，只有零散扫描脚本 |
| `resources-inventory` 与 `res-index` | i2h-spec references 要求 `spec/.i2h/resources-inventory.json`，execute 要求 `spec/baseline/res-index/*.json` | 两套契约没有生成器或 schema 转换，Stage 0 无法稳定消费 |
| CHECK-3 视觉验证 | i2h-verify 有独立简化截图对比 | 没有复用 Spec 阶段的 UI facts，也没有原版的按页面树增量复验闭环 |
| CHECK-5 行为验证 | 明确 deferred | 行为层尚未形成 iOS oracle |
| Spec 并行 | i2h-plan 文档有 P0/P1/P2、Batch、Group 设计 | i2h-spec 没有可运行的 batch planner 和后台采集轨 |
| Execute 并行 | i2h-execute 文档有 Worker/Closer、HOST_MAX、动态依赖描述 | 实际 dispatcher runtime、helper 依赖和测试链不完整 |
| 智能调度器 | `migbot/bin/scripts/scheduler/intelligent_scheduler.py` 已支持依赖就绪派发、全局/宿主并发上限、未知依赖/环检测和失败后重取；仍未被 i2h pipeline 主入口调用 | 调度算法已具备原版关键约束，但必须接入 Spec/Execute dispatcher 并用真实项目基准验证性能 |
| 编译闭环 | 文档写有 Base-7、Stage 3 gate、FV-2 | 运行时入口、依赖 manifest 和 execute 测试仍有断裂 |

## 判断

iOS 版本在设计层面已经借鉴了原版的几个核心思想，包括 indexed-v1、Worker/Closer、资源 sweep、writeback、并发上限和集中编译门。UI 完备度和性能提升目前主要停留在文档层，不能沿用原版的“已大幅提升”结论。

当前最关键的缺口是两个事实源没有接上：

1. iOS Spec 没有生成与页面状态绑定的真实 UI facts 和双端 baseline。
2. iOS 资源 inventory 没有转换成 Execute Stage 0 消费的 res-index 闭包。

并行机制也缺少可执行的调度链。`intelligent_scheduler.py` 不能替代原版的批次规划、依赖就绪派发、空回执处理和停滞回收。

## 建议的实现顺序

### P0：先补 UI facts 和资源索引

- 用 `xcrun simctl` 和 iOS 真机工具采集页面截图、Accessibility/UI hierarchy、动作收据、状态 ID、设备和包身份。
- 生成 `ui-snapshots/page_*` 的 `meta.json`、`visual.json`、`fixture.json` 和 provenance。
- 扫描 SwiftUI/UIKit、Storyboard、Assets.xcassets、Localizable.strings、颜色、字体、SF Symbols 和代码资源引用。
- 定义一个 schema，把 `resources-inventory.json` 转换为 execute 的 `res-index/values|drawables|usage|design-tokens.json`。
- 把 UI snapshot、资源闭包和 coverage report 设为 Gate B 输入。

### P1：把现有并行文档接到运行时

- 为 iOS Spec 增加 batch planner 和可恢复的后台 worker。
- 按 HOST_MAX、任务长度、目录写权限和依赖关系派发，不等待无依赖的上游任务全部结束。
- 把空回执、超时、取消、降并发和重派做成统一 runtime。
- 将 Stage 0 资源闭包、Stage 1 Batch closer、Stage 3 group closer 接入同一套 writeback 和 brief schema。

### P1：形成真实基准

至少准备一个 SwiftUI + SwiftData 项目、一个 UIKit/Storyboard 项目和一个混合项目，分别记录 Spec 阶段耗时、页面并行利用率、资源遗漏率、首编错误数、截图相似度和复验次数。没有这些数据时，README 只能描述设计目标，不能写性能提升百分比。
