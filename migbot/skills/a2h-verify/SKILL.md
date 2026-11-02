---
name: a2h-verify
description: 第四步：验证 Android→HarmonyOS 迁移产出，执行静态分析与 App 身份校验，并由用户选择视觉对齐、单元测试和行为验证，汇总所选范围内的真实结果。当用户说“验证迁移结果”“跑一下验证”或在迁移上下文中说“验证”“测试”时触发。不要用于生成迁移规格或执行迁移代码（分别用 a2h-spec、a2h-execute）。
tags: [pipeline, migration]
type: pipeline
domain: migration
---

# a2h-verify

Pipeline 第四步，负责基础检查与可选检查的编排和结果汇总。静态分析与 App 身份校验在主对话执行；用户选中的视觉、UT、行为验证委托对应 verifier。行为验证只报告，具体测试、源码修复、构建和设备执行按各 skill 契约完成。

## 开始前：选择可选检查项

开始任何 CHECK 前，先确定本次执行范围。CHECK-1/2 固定执行；CHECK-3/4/5 可任选、组合或全部不选。

若用户已明确指定（如“只跑 UT”“跑 3、4”“全部执行”），直接采用该可选检查选择。否则先用多选交互询问，选项仅显示检查编号和名称，不追加括号说明：

> 本次要执行哪些可选检查？可多选：CHECK-3 视觉对齐、CHECK-4 单元测试、CHECK-5 行为验证。也可以回复“全部”或“都不选，仅做 CHECK-1/2”。

无多选工具时用普通文本提问，接受编号或名称组合。收到有效选择后再开始执行；未回复不默认全选。选择只决定执行哪些 CHECK，各 verifier 的修复模式仍按当前任务意图确定。

未选项记为 SKIP（用户未选择），不检查其前置条件、不启动其 verifier、不复用其旧报告。未选 CHECK-5 也不创建 run、不调用 adapter、不读取历史 check12/check5 目录。选择在本次修复和复检中保持不变；用户明确调整时再更新。

“只跑 UT”选 4，“行为验证 / Behavior Verify / 跑效果检查”选 5，“全部执行”选 3/4/5，固定 1/2 始终执行。全选不授权 CHECK-5 第二轮。只验证、不改产品代码的任务选中 CHECK-5 时记 DEFERRED（当前能力与只读约束不兼容），不调用默认修复流程或虚构 verify_only。

## 输入与范围

- 确认鸿蒙工程根目录、待验证模块和用户指定范围；默认验证当前迁移产出。
- 仅为本次执行项从当前任务、工程记录或 `spec/baseline/` 定位所需的 Android 源码根目录、页面清单、UI Spec 与功能 Spec，不要求额外的执行报告作为启动凭证。
- **迁移阶段放行项**：存在 `spec/gate-release/verify-focus.json`（a2h-spec `scripts/gate_ledger.py check` 产出）时，读其中每条（工具缺口 / 未达标放行 / 阶段不可判定）。把条目涉及的页面与流程并入已选 verifier 的验证范围（视觉 / 行为验证优先覆盖），在报告「迁移放行项核实」段逐条写结论：`已核实正常`（工具判错，实际行为正确）/ `确认缺陷`（转入失败与建议项）/ `未覆盖`（附原因与恢复条件）。未选设备类检查时整段记 `未覆盖`，不得写成通过。
- 某项输入、设备或 verifier 缺失时，记录该项受影响范围和恢复条件，继续其他可执行项。CHECK-3/4 的输入和设备要求见 [设备验证](references/device-verification.md)；CHECK-5 见 [行为验证](references/check5-behavior-verify.md)，设备/签名缺失不阻止其可行的源码工作。

## 五项检查

执行 CHECK-1/2，再按 CHECK-3 → CHECK-4 → CHECK-5 的相对顺序执行已选项；每项结束后立即读取实际产物并记录结论。

| 编号 | 检查项 | 执行方式 | 通过条件 |
|---|---|---|---|
| CHECK-1 | 静态分析 | 扫描并复核迁移代码中的类型、导入、SQL、动态执行和生命周期用法 | ERROR 为 0；WARN 附报告 |
| CHECK-2 | App 身份校验 | 检查应用配置、名称和图标资源 | FAIL 为 0；WARN 附报告 |
| CHECK-3 | 视觉对齐 | `arkts-visual-verify` | 完成范围内实测且无未解决差异；纯 ALIGN 差异记建议项 |
| CHECK-4 | 单元测试 | `arkts-ut-verifier` | 全范围实际 GREEN，无未验证设计点 |
| CHECK-5 | 行为验证（可选） | `arkts-behavior-verify` 一次联合调用 | 只报告设置/点击稳定终态；不判全域 PASS，不参与整体判定 |

CHECK-1/2 的具体规则见 [静态分析与 App 身份](references/static-and-identity.md)。CHECK-3/4 的模式、产物和状态映射见 [设备验证](references/device-verification.md)。

## 执行与修复

1. 执行 CHECK-1/2，记录文件位置、复核依据与问题级别。
2. 将工程路径、验证范围和当前任务的修复约束传给已选 verifier。UT 默认 `verify_fix`，仅验证时使用 `verify_only`。
3. 按 visual → UT → behavior-verify 的相对顺序串行执行已选项；设备交接前确认前一 verifier 真实退出并释放设备，静默 5 秒。CHECK-5 按 [行为验证](references/check5-behavior-verify.md) 只联合调用一次，默认 single-round，结束后用 check5_result_adapter.py 汇总；未选项保持 SKIP，全部不选则汇总基础检查。
4. 每段结束后读取本次报告、当前轮摘要和必要证据，保留原始状态。verifier 的内部修复由其自身调度，a2h-verify 不另派同类 fixer，也不重置内部轮数。
5. 仍需由执行阶段处理的失败按 [失败处理](references/failure-loop.md) 回到 `a2h-execute`；CHECK-5 状态不触发该回环。包括 CHECK-5 在内的源码修复结束后，复检 CHECK-1、受影响的 CHECK-2 及已选 CHECK-3/4；未复测的受影响设备项记 PARTIAL，已确认失败保留。
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
| FAIL-functional | CHECK-3 存在崩溃、目的页不匹配或功能缺失等已确认问题 |
| WARN / ERROR | CHECK-5 的未验证修复 / 流程或结果错误；仅报告，其 SKIP/DEFERRED 同样不参与整体判定 |

基础及已选视觉/UT 范围结论仅根据 CHECK-1/2 和已选 CHECK-3/4 计算；排除 CHECK-5 的全部状态：

- 存在 FAIL 或 FAIL-functional → **FAIL**。
- 没有上述失败，但存在 PARTIAL 或 DEFERRED → **PARTIAL**，明确尚未验证的范围。
- 其余情况 → **PASS**；存在 WARN 或 FAIL-visual 时标注“通过，附建议项”。

已选项未生成报告、修复文件已写入或问题文件目录为空，都不能据此判 PASS。报告明确写出执行项与未选项；PASS 仅表示本次范围通过，存在未选项时不能描述为所有五项均已验证。CHECK-5 单列“行为验证结果（非门控）”；安装成功或局部点击通过仍为 WARN，设置正确性未验证。

## 收尾：上报本阶段用量与迁移完成信号

verify 成功产出 `spec/verify-report.md` 后，作为本 skill 的最后一步依次执行（均为纯本地 Bash，**忽略退出码、绝不阻断**）：

```bash
# 1. 统计 Android + HarmonyOS 两侧代码行，上传"迁移完成信号"
.migbot/bin/a2h count-lines

# 2. 上报本阶段 token 用量（usage.v2 快照）
.migbot/bin/a2h mark-stage a2h-verify
```

- **`count-lines`** 现在是迁移"已完成"的判定点（从 retrospect 前移到此）：它采集两侧行数并记为 fact（含 `android_app_name` / `android_version` / `harmonyos_app_name` + `code_lines`），服务端凭其中的 HarmonyOS total 判定完成。此刻两侧代码都已就位，是行数盘库的第一个有效时点——a2h-init 那次盘库跑在迁移之前，HarmonyOS 侧尚不存在。a2h-retrospect 结尾还会再盘一次（覆盖同一 run 的 fact），两次都跑不会重复计数。
- **`mark-stage a2h-verify`** 写出本阶段的 stage-marks fact；生命周期 hook 上传的会话切片在服务端据此归属到 verify 阶段，供性能看板（5002）的事件时间轴使用。

---

## 参考文件

| 文件 | 用途 |
|---|---|
| [静态分析与 App 身份](references/static-and-identity.md) | CHECK-1/2 执行规则 |
| [设备验证](references/device-verification.md) | CHECK-3/4 调用与结果读取 |
| [行为验证](references/check5-behavior-verify.md) | 可选 CHECK-5、两条 lane、结果校验和非门控边界 |
| [失败处理](references/failure-loop.md) | 外层修复范围、退出条件和复检 |
| [报告模板](references/verify-report-template.md) | 五项结果与证据汇总 |
