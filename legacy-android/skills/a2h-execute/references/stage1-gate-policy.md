<!-- when: 任意 Stage 1 门禁 FAIL/BLOCKED 时，在重派、停止或放行之前加载 -->
# Stage 1 按根因处置失败

本协议在项目 ledger 已批准时覆盖 Stage 1 的通用分类放行与 strict_wiring 一律拦截规则。
保留现有 exact/inference/plumbing/env 的检测器类别；下表按本次失败根因选择后续动作。

| 根因 | 证据与例子 | 未耗尽预算 | 耗尽预算 |
|---|---|---|---|
| product_defect | 必交产物缺失/空槽/错接线、实际 UI 断言失败、真实 ArkTS 编译错误 | 回原 owner 修产物并重跑原闸 | BLOCK，返回失败，不能放行 |
| information_gap | 缺 Android 基线/源码事实/SDK 定义，且证据表明无法从当前可用输入补齐 | 补采/找替代来源，保留尝试日志 | RELEASE_WITH_GAPS，后续核实 |
| environment_gap | 无可用设备/SDK、捕获工具失败，有实际命令诊断 | 有界恢复环境 | RELEASE_WITH_GAPS，后续核实 |
| tool_gap | 有源文件/日志证明是检测器能力不足或误报 | 有界核证/可用工具重试，禁止改产物迎合检测器 | RELEASE_WITH_GAPS，反馈工具缺口 |
| unknown | 大类 inputs_invalid、无诊断的 BLOCKED、启动失败尚未查清 | 先诊断，不猜成信息缺失 | BLOCK，说明根因未查明 |

不能因重试次数多就把质量问题改成信息缺口。多个根因混合时，只要剩余真实产物缺陷就阻断。
已确认缺口放行仅表示流程可继续，原闸保持 FAIL/BLOCKED，gate_verified/stage1_complete/业务验收不得写 true。
依赖缺失资料的动作继续保留阻塞；其他有条件的工作可推进。不能补造 G0、HAP、安装回执或视觉 PASS。

## Stage 1 各门应用位置

| 门 | 质量缺陷 | 可诊断为外部缺口的情况 |
|---|---|---|
| S1-G / G0 | converter 漏交源码/报告、未实现必交状态 | 前置源码事实/状态观测缺失 |
| S1-W / G1 / 结构审计 | 空 builder、未挂载组件、漏绑定点击 | 已有合法写法但词法检测器不支持 |
| 编译 | 编译器实际报语法/类型/API 错误 | SDK/工具链不可用；原编译仍未通过 |
| S1-V / 设备冒烟 | 当前正确包实测白屏、Tab 不切换、目标内容缺失、遮挡导致点不到（critical）；普通外观差异只在第 1 轮修，之后记 accepted_differences，不是阻断缺陷 | 无设备、缺 Android 基线、捕获命令失败 |

误包/陈旧回执/错 source hash 不是「没截图」；先重建正确证据。单纯页面没变化也不能推断设备坏了。
full-ui-v2 的 G0/G1 原始归档、范围与哈希核对仍执行；阶段可带缺口继续，验收完成性仍按真实证据计算。

## 统一判定入口

Execute 主线程串行调用以下脚本（worker 只回原始诊断，避免并发改计数）：

```bash
python3 .claude/skills/a2h-execute/scripts/stage1_gate_policy.py \
  --project-root . --gate execute.stage1-wiring \
  --report spec/execution/wiring-experiment/preflight.json \
  --out spec/execution/wiring-experiment/disposition.json
```

其他门使用 execute.stage1-g0、execute.stage1-g1、execute.resources、execute.layout-dims、execute.entry-nav、closure.skeleton、execute.build 或 execute.stage1-visual。
如工具异常没有 JSON，先保存实际命令/诊断，再写引用该诊断的失败报告供归因；不能把异常当作成功。
ui_stage1_gate、ui_delivery_gate、缺基线的 visual scope 及 wiring smoke 已输出 failure_findings。
其他报告可含 errors/findings/cases/pairs；已知明确规则自动分类，大类错误保留 unknown。

每完成一轮真实修复、补资料或环境恢复，并重跑原闸后，再调用同一命令，追加：

```text
--remediation-evidence spec/execution/<本轮真实操作日志>
```

state 保存在 spec/execution/stage1-gate-policy/state.json，按冻结范围与门累计，默认两轮（严格接线模式复用契约的 max_repair_rounds）。
初检不计轮次；重复相同日志不增加次数；换任务/报告名、修改应用源码不重置预算；变更范围须显式决策，不能删除 state 重试。
日志必须是原闸报告以外的非空项目文件。现有编译/视觉修复预算也继续约束执行，不能把这层预算叠加成更多源码修复轮次。

## 需补充根因证据时

对 unknown 或工具误报，用 --review <review.json> 提交与当前原报告绑定的复核：

```json
{
  "report_sha256": "当前原报告的实际 SHA256",
  "findings": [{
    "finding_id": "原报告 failure_findings 的 ID",
    "root_cause": "information_gap",
    "reason": "具体缺什么、如何确认当前资料无法补齐",
    "evidence": ["spec/execution/实际诊断或查找日志"]
  }]
}
```

证据文件必须存在且非空。把已知 product_defect 复核为 tool_gap 还需 disproves_product_defect=true 和能否定原判断的实际源码/诊断；不能改为 information_gap 躲修复。
自动分类不是对任意 ArkTS 语义的证明，发现未支持写法应有证据复核。

## 放行记账

RELEASE_WITH_GAPS 时，按脚本 release_gates 分组写 D 编号，并运行现有 gate_ledger.py check：
information/environment 使用 execute.stage1-prerequisite（阶段不可判定）；tool 使用 execute.stage1-tool（工具缺口）。
记录原失败报告、处置报告、已恢复轮次、实际证据与 a2h-verify 的复核项，核对成立后才推进流程。
不在 execute.build 下放行真实编译错误；SDK 环境阻塞的流程放行另记前置缺口，编译标志仍为未通过。
用户选择「只重跑接线验收」时，部分执行结束即返回；全流程按既定范围推进可执行任务，缺口所依赖的验收仍保持未验证。
