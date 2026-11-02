---
name: a2h-telemetry-instrument
description: Use when implementing a new feature, new pipeline stage, new command or new structured artifact and you need to decide how to add telemetry (打点) so it lands on the dashboards. Triggers - 新特性打点, 新增阶段打点, 打点上报, telemetry instrumentation, how to report usage, facts 契约.
---

# 新特性打点装配

给一个新增特性装上符合契约的打点：判断要不要打 → 按模板打 → 按三层递进自证。

**契约规范本体**（字段/插入位置的完整原文）：`docs/skills-telemetry-instrumentation.md`。本 skill 是它的可执行摘要；两者冲突时以规范本体为准。

## 铁律（违反 = 上报假数据）

1. **绝不**用 Write / Edit / NotebookEdit 创建或修改 `.migbot/metrics/` 下任何文件（含 `retrospect.done`）——一切产物只能由 `a2h metrics` 命令作为副产出生成；
2. App 名 / 版本号字段**只用真实值**：抓取失败就传空，禁止传目录名、build.gradle 源码片段、HTML、模板值；
3. 打点命令**尽力而为**：失败/未授权都不得阻断主流程，忽略退出码继续；
4. mark-stage / count-lines 必须由**主 agent 直接 Bash**，不得派发 subagent。

## 一、是否要打

**判定：三问（有没有发生 / 链路通不通 / 功能到底好不好）对功能特性都成立，区别在"本身可不可见"——文案/布局改完直接可见，不打；新增/修改逻辑运行在看不见的内部，必须打点。**

| 特性类型 | 结论 | 打什么 |
|---|---|---|
| 新增 pipeline 阶段 | ✅ 必须 | 阶段收尾调 `mark-stage <阶段id>`（落 stage-marks fact） |
| 新增 skill / 命令 | ✅ 必须 | 调用记入 `usage_entries` 集合（name/stage/kind 可归因） |
| 新增结构化产物 | ✅ 必须 | 契约登记新 fact_type，由 `a2h metrics` 子命令产出（落 `facts` 集合） |
| 修改既有阶段逻辑 | ✅ 保持 | 既有 `mark-stage` 调用不得丢失（CI 有断言） |
| 纯 UI / 文案 | ❌ 不打 | 本身可见，无需额外可视化 |

## 二、怎么打（模板）

### 2.1 阶段收尾（新增阶段必做）

在阶段 skill 的文件末「收尾」段插入，尽力而为：

```bash
.migbot/bin/a2h mark-stage <stage-id> || true
```

`<stage-id>` 用契约里的规范名（如 `a2h-plan`）；新阶段名先在 `docs/skills-telemetry-instrumentation.md` 登记。

### 2.2 迁移完成信号（verify 阶段）

```bash
.migbot/bin/a2h count-lines || true
.migbot/bin/a2h mark-stage a2h-verify || true
```

`count-lines` 产出两侧代码行数 + App 名称/版本号的 fact（HarmonyOS total 即服务端的完成信号），`mark-stage a2h-verify` 落阶段水位；**判"已完成"的时点在 verify，不在 retrospect**。

### 2.3 调用量（usage，新增 skill / 命令）

调用记录由运行时事件自动生成，阶段收尾的 `mark-stage` 落 stage-marks fact，服务端据此把 hook 上传的会话切片归属到阶段。你要做的是保证调用发生在正确 stage 上下文里，使 `name`（如 `migbot:<skill>`）/ `stage` / `kind`（skill/session/subagent）可归因——否则该次调用在 5002 上无法归因。

### 2.4 结构化产物（facts 集合）

先在 `docs/skills-telemetry-instrumentation.md` 登记契约，再由 `a2h metrics` 子命令产出，落 `facts` 集合。三种既有类型按需扩展或新增（新 fact_type 必须先登记契约）：

- `baseline`：`{project, timestamp, android_app_name, harmonyos_app_name, code_lines: {records: [{side, file_type, line_count}]}}`
- `code-lines`：`{project, timestamp, android_app_name, android_version?, records: [{side, file_type, line_count}]}`
- `stage-marks`：`{marks: [{stage, ts}]}`——run 级阶段水位，服务端据此归因会话阶段

### 2.5 会话原文

**不需要写任何代码**——7 类 hook 事件自动切送，无需手工操作。

## 三、怎么验证（两层验证；效果评估归评测环节）

打点自身的验证只有两层：①埋点触发了没有、②数据完整到达且可归因。**③功能效果由评测环节负责**——打点只保证数据能支撑它（字段足以回答三问），不负责评出结论。

| 层 | 验证什么 | 怎么做 |
|---|---|---|
| ① 是否触发 | 埋点代码真的执行了 | 跑 `a2h-telemetry-smoke`（全打点面冒烟）；确认 mark-stage 等调用真实发生 |
| ② 链路完整 | 事件无损到达且字段可归因 | 服务端 ingest_events 出现该 run、对应集合行数增长、看板会话可见；重点检查字段语义（真实 App 名/版本号） |

递进关系：①不过谈不上②，②不过数据不可信——两层都过，打点才算"打对且到达"；之后数据能不能回答"功能到底好不好"，交给评测环节消费（打点侧的责任是字段别缺）。
