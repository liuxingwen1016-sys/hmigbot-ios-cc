# §1.1 执行铁律 — 决策来源与禁止交互

**S1-V 用户选择例外**：Stage 1 可选双端对比的执行 / 跳过必须由用户明确选择；复用本次运行已有选择，否则在 S1-V 收口点询问并等待，不按 default-policy 自动裁定。其他决策和门禁仍按本文执行。


> 本文件是 a2h-execute SKILL.md §1.1 + §2 启动必读 的**完整执行规范**。SKILL.md 仅保留摘要 + 指针；执行到该步时 **MUST Read 本文件全文**。
> 三道闸协同：闸 1（本 HARD-GATE）+ 闸 2（`spec/decision-ledger.md`）+ 闸 3（项目指令文件决策段，由 a2h-spec Step C4.8b 同步）。
> 宿主别名 **`PROJECT_INSTRUCTIONS_FILE`**：Claude Code → 项目根 `CLAUDE.md`；Codex → 项目根 `AGENTS.md`。下文统一用此别名；正确性不依赖宿主对该文件的自动注入，必须显式 Read。

## 启动必读

> 把 ledger 与项目指令文件强制拉进当前 skill 执行 context，

1. **`Read PROJECT_INSTRUCTIONS_FILE`**（按上述宿主别名解析，若存在）
   - 拉入闸 3 内容：决策段（C0–C17 类目 + "查表 / 未命中按默认裁定、不追问" 规则 + 门禁处置指针）+ 通用行为准则
   - 验证含 marker `<!-- a2h-decision-snippet:start -->` / `<!-- a2h-decision-snippet:end -->`
   - 文件缺失 / marker 缺失 → WARN 写入 `spec/migration-report.md`「启动检查」段（提示 a2h-spec Step C4.8b 未跑或被删），**不阻断**

2. **`Read spec/decision-ledger.md` 顶部「决策索引」段 + D0**（若存在；**按需读，不整份吞**）
   - 默认只读：文件头 → `## D 编号决策` 之前（含「决策索引」速查表 + 状态 + D0 产出定位，约 30–50 行）。索引表已含每条 D-编号的**一行结论 + 类目**，足以建立全局决策感知。
   - **正文按需 grep**：执行某 Slice/页触及某类目时，再 `grep -A 12 "### D-0NN" spec/decision-ledger.md` 取该条完整正文（背景/候选/依据/影响）。**禁止无差别 Read 整份 234 行 ledger** —— 实测旧流程 26 个 agent 整份吞全文 × cache_read 是控制面膨胀主因之一；索引 + 按需 grep 降 ~80% 注入量、零决策内容丢失。
   - 若 ledger **无「决策索引」段**（旧产物 / a2h-spec 未重跑 C4.8）→ 回退整份 Read（兼容），并 WARN 提示重跑 a2h-spec 生成索引。
   - 验证 status 字段：必须为 `approved`（spec Gate C 与 plan Gate 均已审批）—— status 在文件头部，按需读已覆盖。
   - 文件缺失 → **阻断**：写 migration-report 说明 grill #1/#2 未跑；无人值守时自动回到 a2h-spec Step C4.8 / a2h-plan §7.2 补跑 grill（按 default-policy 裁定）后再开工
   - status ≠ `approved` → **阻断**：用户要求逐个确认时提示用户先完成审批；默认无人值守按 [a2h-spec references/gate-handling.md](../../a2h-spec/references/gate-handling.md) §5 自动确认（审批人记 `default-policy`），status 置 `approved` 后开工

启动必读完成后，再自动读取 `spec/baseline/plans/` 下已审批的双计划文件（见 SKILL.md §2 表）。

## 执行铁律（HARD-GATE）

execute 阶段的歧义应在 a2h-spec / a2h-plan 的 grill 嵌入点已经清零。本阶段只负责**按决策推进**，不再交互式追问。

唯一事实源：**`spec/decision-ledger.md`**（D0 决策树根 + D-编号决策 + 运行期验证项 + 技术必做项 + Plan 待修订项 + spec 卫生检查结论）。

凡 execute 期遇到以下任一情形，**必先 grep `spec/decision-ledger.md` 对应类目**：
- 范围取舍 / 技术替代 / UX 行为差异 / 工程配置 / 数据策略 类判断
- 与 plan / spec 现有描述冲突
- 触发条件超出 plan 既定 task 范围
- 任何 SKILL.md 既有段落中写有「提示用户三选一」「除非用户指定 blocking」「要求人工补 plan」等交互动作

执行规则：
- ledger 命中 → 按之执行，**严禁询问用户**
- ledger 未命中 → 按 `a2h-spec/references/default-policy.md` 或决策卡「← 推荐」项裁定，**追加 D 编号**（`approval_source: default-policy`，依据写 Android 源码证据）后继续，**严禁交互式追问**；同时把缺口写入 `spec/migration-report.md` 的「决策缺口」段（schema 见下，「阻断范围」列改写为「裁定 D 编号」），供事后复核与下一轮 grill 回看。用户要求逐个确认时才阻断当前 Stage / Slice / Batch 等下一轮 grill
  （实测 1014：每页一个决策缺口、逐页停批等人，execute 估算拖到 4–9 周）
- ledger 与其他文档冲突 → **ledger 优先**
- Plan 待修订项段落 → 直接按本表覆盖 plan 原文，不再核对 plan 当前措辞

## 决策缺口段 schema（写入 spec/migration-report.md）

```markdown
## 决策缺口（execute 期未命中 ledger）

| 缺口 ID | 触发位置 | 类目候选(C0–C17 或 escape) | 现象 | 裁定 D 编号（阻断范围） | 上报时间 |
|---------|---------|---------------------------|------|---------|---------|
| G-001 | Stage 3 Slice 5 Step 3c | C8 SDK 策略 | F005 涉及 X SDK，ledger 未定占位/降级策略 | D-052（default-policy：留桩 + registry thirdparty-sdk） | YYYY-MM-DD HH:mm |
```

每条缺口由回流到 spec/plan grill 的下一轮拷问，或经评审升级为 checklist 新类目。
