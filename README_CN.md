# iOS MigBot

`hmigbot-ios` 是面向 Claude Code 的 iOS → HarmonyOS（ArkTS）迁移工具包。它以 [`../hmigbot-1.8.0`](../hmigbot-1.8.0) 的 Android → HarmonyOS 流水线为参考，并将输入、扫描、映射和验证改造成 iOS 版本。

## 当前状态

仓库已经包含 i2h 五阶段 Skill、iOS 参考 Skill、模板与脚本。流程交接命令、原生符号关系和已安装验收入口通过了下文列出的 macOS 工具合同回归；应用的签名、设备能力、视觉保真和完整行为仍须逐项目真实验证。历史问题与证据保留在 [`docs/IMPLEMENTATION_AUDIT.md`](docs/IMPLEMENTATION_AUDIT.md)。

历史文档中的“90.8% 自动转换率”是 Cuike 原型阶段的统计估算，不代表编译通过率、行为等价率，也不是通用验收标准。

## 2026-11-28 更新：流程交接与原生符号验收

本次以 `c919b99` 为源码基线，整合四项流程交接修复及经过复审的原生符号关系验收。

| 范围 | 更新后的行为 |
| --- | --- |
| Init → Execute | 统一读取 `.migbot/config.json.ios`，按项目根解析相对路径；空路径、失效目录或源绑定不一致在执行前诊断。 |
| Plan → Execute | 统一消费 indexed UI、feature、base 三计划和 slices；旧单计划仅通过显式 legacy 选项启用。 |
| Spec → 资源执行 | 按生产者真实的 `target_input_sha256`、`inventory` 和资源索引核对当前批准范围；缺失资产与仍需目标映射的系统符号分别处理。 |
| Retrospect | 从两侧实际文件和本轮回执统计；缺输入或读取失败保留 `UNKNOWN/null`，有效空输入才记为零。 |
| 原生符号关系 | 显式启用 XCUI Image identifier 与可见、未裁剪的 SymbolGlyph 叶节点匹配；父按钮、页签上下文及重复组必须可消歧，说明冲突阻断；最终几何阈值保持 **4 pt**。 |
| 活动源导航 | 只有批准谓词、可标识的目标模态、唯一源主窗口和标题/控件绑定均成立时，才限定到独立呈现的源导航容器。 |
| 正式验收与升级 | 正式入口按批准 pair 和已绑定原树重放新模式，篡改报告不能通过；保留截图/安装身份、独立外观证据和旧 G0/G1 回执兼容。 |

安装后的 `ui_relationships.py` 需显式传入 `--native-control-roles --native-symbol-anchors`。自定义页签配合 `--audit-viewport --tab-bar-id <id>`，批准的独立源导航使用 `--approved-source-navigation`。未选择新选项的旧项目保持原匹配行为。详见[关系验收合同](migbot/skills/i2h-execute/references/ui-delivery-contract.md)。

**验证结果：**macOS 本机 848 项合同回归通过，0 失败/跳过（原有 777 + 流程交接 48 + 原生关系 23）；最终安装版另有 63 项相关回归、14 项独立 CLI 检查通过。干净安装、保留配置的升级、旧模式关系回执重放和旧 G0/G1 升级检查通过。Windows/Linux 保留为可选检查，本轮未实跑。

本次提交包含可复用工具、修改说明及通用合成回归；不包含应用实例工程、设备采集、安装包或本机维护日志。应用完成度和视觉保真仍由各项目验收。

逐文件原因与复跑命令：[流程交接](docs/patches/20261126-flow-handoff.md)、[原生符号验收](docs/patches/20261128-check3-native-symbols.md)。已有项目在阶段断点使用正常安装器升级。

## 2026-11-24 更新：原生模态视觉验收与门禁一致性（R3）

本次将经过独立复审的 **modal-visual R3** 合入 `main_ui_optimize`，线上基线为 `e057f483540fd98d36d1541bbfecb00a36b6b4e3`。优化对象是可复用的工具和正式验收入口，不把工具回归通过写成 Cuike 等应用的设备验收通过，也不宣称全流水线已达到两小时目标。

### 合并后具体优化了哪些能力

| 能力 | 合并后的实际行为 |
|---|---|
| 原生活动层识别 | 从唯一聚焦的应用窗口识别当前 SheetPage / ModalPage。隐藏控件、异包窗口、UIExtension 和被遮挡底层控件不能满足严格状态谓词。多分支模态只按有明确原生证据的自身焦点关系消歧，不能按遍历顺序或“哪层能通过”猜测。 |
| 截图前后状态一致 | 截图前后都执行同一个批准谓词；业务 is_ready 只是附加条件。同包、同路由下，截图后才出现或已经消失的弹层不能产出可通过正式回放的严格回执，底层重复 ID 也不能蒙混通过。保留前后原树与观察。 |
| 实际安装包身份绑定 | 读取构建 HAP 的 module.json、安装成功日志和 bm 包身份日志。批准谓词包名、实际前台包名与已核验安装包名必须一致；身份缺失、错包、版本不符或畸形数据均阻断。 |
| 截图与原树摘要核验 | capture-index、assemble、visual archive、正式 smoke 重新读取原件及 SHA。缺图、换图、改树不能只靠旧标签通过。严格采集汇总校验采集时保存的图像摘要，不会在换图后重新计算摘要并放行。 |
| 批准清单与逐 pair 验证 | 按当前批准清单重建 scope，按 pair_id 读取对应谓词。同页同状态多条 pair 逐条校验并保留完整分母；删谓词、删 pair 或把传入 scope 改成旧 schema，不能退回标签验收。 |
| 汇总状态、范围与安装一致 | 严格 case 必须已成功到态，build/install 回执绑定当前 scope，同一汇总使用同一 HAP 和设备；原件必须在当前采集目录。BLOCKED 场景的遗留文件不会被升级成 PASS。 |
| 活动层匹配与原诊断共存 | 控件关系仅在活动层匹配；坐标继续使用原始视口，状态栏裁剪/重叠诊断继续读取完整原树。避免底层控件补齐缺失锚点，也避免过滤活动层时误丢系统状态栏。 |
| Plan 空值与类型处理 | 先确认 verification_states 为列表再遍历。旧版非严格清单的字段缺失/null 可继续读取；非列表输入、严格运行时缺项返回结构化错误。 |
| macOS验收与可选跨平台CI | 默认push/PR只验收macos-latest。保留Windows/Linux代码与全部测试，通过手动cross_platform选项才执行，失败不阻塞本次交付。继续保留通用回归、ripgrep依赖和UTF-8（含隔离子进程显式参数）。 |
| 旧项目升级 | 保留原配置及原 G0 归档。e057f48 原工具产生的 G0 PASS 升级后逐字节保留，可原样重新汇总，并通过 G1 结构验收。 |

首轮远端 CI 另外暴露了 Windows 默认控制台编码、未安装 ripgrep 和旧 macOS runner 退役问题。本次接续修正 CI 环境，不跳过原通用测试；静态分析改读 ripgrep JSON 事件，Windows 盘符不再破坏文件/行号解析，搜索失败记工具错误而非“零违规通过”。[GitHub 官方 runner 退役说明](https://github.com/actions/runner-images/issues/13518)。

**当前以macOS为验收范围。** Windows/Linux兼容保留但不列为发布必达项；需要时在Actions的Run workflow中手动开启cross_platform。不会自动更换其他线程/项目的已安装工具，不修改其工作区，也不取消已有任务。

### 如何启用与兼容旧项目

通过原 Plan 审批流程，在批准 UI 清单的 verification_states 对应行添加 target_observation，例如：

```json
{"bundle":"com.example.demo","page_path":"pages/Root","present":[{"id":"editorName"}],"absent":[{"id":"errorDialog"}]}
```

带批准谓词的 pair 自动要求严格回放。若要求所有视觉 pair 都必须严格验证，可在项目阶段断点将 `.migbot/config.json` 的 `native_visual_observation` 设置为 `native-page-state-v2`，缺谓词即阻断。采集器必须把同一批准谓词交给 capture_checkpoint，并将回调提供的截图前原树传给 write_visual_arrival；具体字段、调用示例见[原生模态视觉合同](migbot/skills/i2h-verify/references/native-modal-visual.md)。

安装升级不会自动开启严格模式、改写批准范围或给历史回执补造证据。旧非严格回执维持原读取规则；缺前后树、原图摘要或真实安装身份的严格证据保持未验证。CHECK-5 行为录制、uitest_scenario.py 与 layout_from_step 不在本次范围内。

### 保留的线上能力与验证结果

此前快照同步包涉及的 **48 个线上文件全部保留，SHA 不变**。Claude 任务路由、累计预算和 agent 安装，Execute 批准清单/source_only，Plan 需求索引/覆盖，以及 Spec Swift 声明、本地化、字体、主题和实际安装身份检查及原测试均保留。此前已完成的“旧 Android 二进制改为 Python iOS 门禁”也继续保留，不会重新装回旧 Android 二进制。

R3 工具产物与本次合并副本分别在 macOS 本机完成 **773 项回归、0 跳过**，包括干净安装、旧 G0 原样重汇总和 G1。13 项新增独立安装入口测试在原 R2 上为 **11 失败、2 通过**，补修后 **13 通过**。e057f48 上的正反向应用及全文件摘要校验通过。Windows/Linux 只配置了 CI，本次本地复审未实跑，提交后的远端 CI 结果需单独查看。以上不代表真实应用已通过设备 Verify。

远端 CI 环境修正后，合并副本再次通过 **777 项本机回归、0 跳过**，其中新增4项静态分析传输回归；原 R3 的773项记录作为历史保留，远端各平台结果单独记录。

必要的 **macOS 远端 CI 与插件清单检查已通过**，对应代码提交 `dc873de`：[实际 Actions 结果](https://github.com/liuxingwen1016-sys/hmigbot-ios-cc/actions/runs/45347008395)。该默认运行没有启动 Windows/Linux 兼容任务，也不将它们列为交付阻塞。

见[独立复审与验证摘要](docs/patches/20261124-modal-visual-review.md)、[逐文件原因](docs/patches/20261123-modal-visual-port.md)和[机器验证记录](docs/patches/20261124-modal-visual-validation.json)。已有转换项目在当前阶段结束后再用原安装器升级，避免在进行中的转换阶段更换工具。

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

需要 Python 3.8+、静态检查所需的 ripgrep（rg）、Claude Code、带 `.xcodeproj` 或 `Package.swift` 的 iOS 项目，以及可供 DevEco Studio 使用的 HarmonyOS 工程。设备验证还需要 Xcode 工具、`hdc` 和实际设备或模拟器。

安装后，`/i2h-init` 和 `/i2h-run` 是预期的工作流入口。`/i2h-build` 使用已安装的 `i2h-tool` 辅助工具；设备和 DevEco 检查仍为显式运行时前置条件。

首次功能验证使用 `/i2h-verify behavior`，修复后目标重测使用 `/i2h-verify recheck`。两者保留初始场景范围和所有当前验收标准。运行标准 Verify 阶段使用 `/i2h-verify full`。详见[原生 UITest 回执合同](migbot/skills/i2h-verify/references/check5-behavior-verify.md)。

## 流程交接入口（2026-11-26）

三个只读 CLI 入口为 Execute 和 Retrospect 阶段提供已校验输入：

| 命令 | 用途 | 合同 |
|------|------|------|
| `.migbot/bin/i2h execute-source` | 从 `.migbot/config.json` → `ios` 字段返回解析后的绝对 iOS 源码根路径。校验项目结构（`.xcodeproj` 或 `Package.swift`）及与 `resources-inventory.json` 和 `ui-delivery-approved.json` 的绑定一致性。任何校验错误以 exit 2 和诊断消息返回（无 traceback）。 | Execute Stage 0.1 使用 |
| `.migbot/bin/i2h execute-inputs` | 返回计划输入（默认 indexed-v1 三文件或显式 legacy）和静态资源事实（默认 static-v1）的 JSON 摘要。校验计划文件、`target-input.json` schema/hash、资源索引、批准范围绑定，并对选中范围内的未解决资源阻断。系统符号记录为目标映射义务。严格 argparse 拒绝未知选项和缩写。 | Execute Stage 0.4 使用 |
| `.migbot/bin/i2h retrospect-metrics` | 返回带双向行数统计的 JSON。iOS：源码根下的 Swift/ObjC（排除 Tests/Pods）。HarmonyOS：`entry/src/main/ets/` 下的 ArkTS/TS。状态：MEASURED（带计数）或 UNKNOWN（带原因，`total_lines: null`）。使用 `os.walk` 显式错误处理，不跟随符号链接。逐文件精确计数，保留无末尾换行的文件。从不输出硬编码的项目特定数字。 | Retrospect Stage 2 使用 |

**实现细节**:
- `execute-inputs`: 真实 `usage.json` schema 为 `{"resources": {"name": {"references": [...], "resolved": bool, "disposition": str}}}`（字典，非数组）。系统符号（kind=system_symbol）与缺失资产分离；仅选中范围内的常规缺失 image/color/localization 阻断执行。
- `retrospect-metrics`: 正确处理权限错误、符号链接、空目录与缺失目录。返回 `files` 计数及 `total_lines`。
- Execute 输入命令遇无效 JSON/UTF-8 返回 exit 2；Retrospect 将不可用的一侧或回执保留为 `UNKNOWN/null`，仍返回独立可用的数据。

**边界说明**：这些命令只读，不写入完成标记、批准范围或修改项目文件。校验结构与绑定，但不执行资源落地、Stage 1 执行或应用 Verify。实际设备验证、Windows/Linux 远端 CI 和冻结 `latest` 包更新不在本次范围内。

**验收状态**：macOS 本机 **825 项通过（新增 48 + 原有 777），0 失败/跳过**；另有 **32 项独立安装入口探针通过**。见[逐文件原因及发布边界](docs/patches/20261126-flow-handoff.md)。回归覆盖见 `tests/test_cc_flow_handoff.py`。文档已更新：Execute SKILL.md 加载 stage-0-resources.md，Retrospect SKILL.md 数据驱动无硬编码数字，迁移报告模板使用三计划格式，CI 包含流程交接回归步骤。

## 仓库布局

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

默认 GitHub Actions 在 macOS 运行离线 SwiftUI/UIKit fixture、i2h-execute、spec/plan/原生 Verify 契约与 Python 编译检查，并保留通用插件清单检查。Windows/Linux 通过手动 cross_platform 选项保留，失败不阻塞当前交付。fixture 将设备与 DevEco 检查记录为 `DEFERRED`，不会伪造运行时证据。
