<!-- when: 要改 rewrite_rules.yaml / divergence_rules.yaml / overlays.yaml / exceptions.yaml / path_renames.yaml，或分诊 MIGRATION-REPORT 的待人工项时加载 -->
<!-- topics: R1 术语与路径, R2 Skill 调用语法, R3 子代理派发, R4 工具名指涉, R5 内嵌 agent 路径, R6 frontmatter 遗留, R7 TOML 约束, R8 完成自检, R9 一致性约束, R10 平台能力分歧, 自动/人工分工 -->

# Codex 适配语义改写规则（SSOT）

适用对象：`codex/` 下由 convert.py 生成的产物（skills/*.md、agents/*.toml）。
总原则：**只改平台机制指涉，不改技术知识、流程逻辑、HARD-GATE 约束语义和中文措辞风格**。改动最小化，逐处替换，不重排段落。

## 执行方式：哪些自动、哪些留给人

本文件是语义 SSOT；其中**可确定性表达的部分已由 `rewrite.py` 自动执行**，`convert.py` 跑一次即完成，无需人工重来。

| 规则 | 状态 | 落在哪 |
|---|---|---|
| R1 术语与路径 | 自动 | `rewrite_rules.yaml`；例外见 `exceptions.yaml` |
| R2 Skill 调用语法 | 自动（含多行块） | `rewrite_rules.yaml` + `rewrite.py` 块变换 |
| R3 子代理派发 | 自动（含伪代码块） | 同上 |
| R4 工具名指涉 | 自动（R6 注入时） | `convert.py` 的 `_TOOL_PROSE` |
| R5 内嵌 agent 路径 | 自动（按路径消歧） | `rewrite_rules.yaml` 的 `when_path` |
| R6 frontmatter 遗留 | 自动 | `convert.py` 的 `inject_dropped_frontmatter()` |
| R7 TOML 结构约束 | 自动保证 | 改写只作用于源 body，不碰生成的前言 |
| R8 完成自检 | 自动 | `rewrite.audit()` → 迁移报告 |
| R10 平台能力分歧 | 自动 | `divergence_rules.yaml`（单行）+ `overlays.yaml`（结构性） |

**仍需人工/LLM 的**（`rewrite.audit()` 会逐项列进 `codex/MIGRATION-REPORT.md`）：

1. **机制不等价** —— Codex 没有对应能力，要用指令补偿而非换词（如 `@file.md` import 语法 → 写明「会话开始必须先读取」；Memory 系统 → 落盘项目文件）
2. **跨 skill 的上下文消歧** —— 同名实体在别处被提及，路径判不出指向（如 a2h-verify 里提 ut/ui 两侧的 spec-fixer）
3. **skill 与 agent 形态不符** —— 目标在 Codex 侧是子代理却写成 skill 调用
4. **description 预算压缩** —— 隐式路由 ON 的 description 总长受 8000 字符约束，压缩要保住触发力
5. **新的例外判定** —— 规则误伤了本该保留的语境时，把它登记进 `exceptions.yaml`（判一次，长期复用）

新增规则时：先改本文件，再改 `rewrite_rules.yaml`，两者必须一致。

## R1 术语与品牌

| 原文 | 改为 | 说明 |
|---|---|---|
| Claude Code（指运行环境/CLI） | Codex | 若语句描述 Claude Code 专有机制，须按 R2/R3 改写语义，不能只换词 |
| `CLAUDE.md`（指被迁移目标项目的说明文件） | `AGENTS.md` | Codex 读项目根 AGENTS.md |
| `.claude/skills/` 或 `~/.claude/skills/` | `<project>/.agents/skills/`（项目级）/ `~/.agents/skills/`（个人级） | |
| `.claude/agents/` | `.codex/agents/`（*.toml） | |
| `.claude/settings.json` | `.codex/config.toml` | |
| Claude 模型名（opus/sonnet/haiku）作为配置项 | 删除或注释保留（Codex 继承会话模型） | 提及模型行为的知识性内容不动 |

例外：描述「本仓库源产物来自 Claude Code 版本」这类溯源说明可保留字样；platform 枚举表（claude-code/opencode/…）新增 codex 条目而非替换。

## R2 Skill 调用语法

- `Skill({skill: "X", args: "..."})` → 「调用 `$X` skill（读取 `.agents/skills/X/SKILL.md` 并按其执行），参数：`...`」
- 「用 Skill 工具调用 X」「Skill 工具」 → 「显式调用 `$X` skill」
- 保留原有强约束语义（如「禁止 grep / 自跑 scripts 替代」照原样保留）。
- **`.sh` 里出裸名，不带 `$`**（`R2-paren-sh`，须排在 `R2-paren-*` 之前）：shell 的 `$` 是变量展开，`$android-fact-tree` 会被 bash 当成未定义的 `$android` 展开成空串、只剩 `-fact-tree`，脚本照跑不报错、只是 echo 的提示信息悄悄不对。不用 `\$` 转义——那只在双引号里成立，且会让 R9 那条可机械检查的不变式退化成依赖引号上下文的判断。`.py` / `.yaml` 不受此限（那里 `$` 是惰性字符，`$name` 正是 Codex 的调用形态，应当保留）。

## R3 子代理派发

- `Agent(subagent_type="X", prompt=...)` / `Task(subagent_type: "X", ...)` → 「派发 Codex 子代理 `X`（定义于 `.codex/agents/X.toml`），任务提示词：…」
- `subagent_type: general-purpose` / `Explore` → 「派发一个通用子代理」（无需专属定义文件）
- 「Task 工具」「Agent 工具」 → 「子代理派发」
- 伪代码块中的 Python/JS 风格 `Agent(...)` 调用：改为等价的结构化派发描述（保留参数名与值，写成「派发子代理 …，附加参数：ROUND=…, MODE=…」形式），不保留 Claude 工具函数签名。
  - 三种书写形态都要覆盖：`Agent(` 独占行、`x = Agent(` 赋值式（两者由 rewrite.py 的块变换处理），以及 `Agent(subagent_type="X",` 首行带参、后续参数续行（由行规则 `R3-pseudo-agent-headline` 处理，因闭合括号在多行之外，要求 `)` 的规则命中不了）。
- 并发派发语义保留；若原文一次并发数可能 >6，追加一句「受 Codex `agents.max_threads`（默认 6，可在 config.toml 调高）约束，超出按波次调度」。
- agent 内再派 agent（如 visual-fixer → visual-fixer-reviewer）：保留逻辑，追加一句「需 `agents.max_depth ≥ 2`（见 codex/config.toml.sample）」。

Legacy reference notes sometimes contain inline examples with plugin-qualified
agent names or single-quoted arguments that cannot be safely inferred as one
of the generated TOML agents. Those snippets still use Claude's
`subagent_type`/`Agent(` spelling, so the fallback rewrite normalizes them to
Codex's `agent_type`/`spawn_agent(` vocabulary without inventing an agent
definition.

## R4 工具名指涉

- body 中把 Read/Glob/Grep/Edit/Write/Bash 当作**工具名**指涉的段落 → 通用表述：读取文件 / 通配搜索 / 内容检索 / 编辑文件 / 写文件 / 执行 shell。
- 动词式用法（「Read 该文件」「grep 关键字」）可保留，不必逐词替换。
- 「主线程禁止直接调 X」这类约束照常保留，仅替换其中的工具名措辞。

## R5 内嵌 agent 路径（arkts-ut/ui/dt-verifier、a2h-verify）

- `agents/stepN-*.md` 引用路径 → `references/agent-prompts/stepN-*.md`
- `agents/spec-fixer.md` 的派发 → 「派发 Codex 子代理 `spec-fixer-ut`（ut-verifier 内）/ `spec-fixer-ui`（ui-verifier 内），定义于 `.codex/agents/`」；描述性提及可写「fixer 行为见子代理 `spec-fixer-ut` 定义（正文同 `references/agent-prompts/spec-fixer.md`）」
- step 类无 frontmatter 模板：派发写法 → 「派发通用子代理，提示词取 `references/agent-prompts/stepN-*.md` 全文 + 附加参数」

## R6 frontmatter 遗留（hmos_fix_build_errors）

原 `allowed-tools` / `argument-hint` 字段已在转换时移除。在 body 标题后新增一节：

```
## 调用参数与工具边界（原 Claude Code frontmatter 迁移）
- 参数格式：<原 argument-hint 内容>
- 允许的操作类型：<原 allowed-tools 列表>（作为行为约束遵守）
```

原值见 codex/MIGRATION-REPORT.md「丢弃的 frontmatter 字段」。

## R7 agents/*.toml 附加要求

- 只改 `developer_instructions` 内部文本，不动 TOML 结构与转换器生成的前言（前置 Skills / 工具边界两节）。
- body 中派发下游 agent、调用 skill、CLAUDE.md、.claude/ 路径等按 R1–R5 处理。
- 改完必须保证 TOML 仍可解析（值内不得出现裸 `'''`）。

## R8 完成自检（每个文件改完后）

文件内不得再出现（大小写均算）：`Skill({`、`subagent_type`、`CLAUDE.md`、`Claude Code`、`.claude/`、`allowed-tools`、`argument-hint`、`Task 工具`、`Agent 工具`、独立品牌词 `Claude`。
允许保留：`agents/openai.yaml`、一般语义的 task/agent 英文单词、R1 例外条款。

由 `rewrite.audit()` 自动执行，结果写进 `codex/MIGRATION-REPORT.md`。以下三类不计入残留（判定过、决定保留的）：
- `exceptions.yaml` 保护区内的文件与行
- convert.py 自己生成的溯源说明（`# 原 Claude Code 配置 model: …`、`## 前置 Skills（原 Claude Code …`）
- 平台枚举语境（`platform: claude-code` 等多平台注册表的合法值）

## R9 一致性约束（自动化引入的新要求）

- **文件名与正文引用成对改**：行规则改了某文件名的引用，`path_renames.yaml` 必须有对应条目，否则引用断链。
- **skill 目录名对齐 frontmatter `name`**：Codex 按 name 路由，目录与 name 不一致会让 `$name` 引用找不到目录（convert.py 已自动对齐）。
- **路径条件规则用 `when_path`**：只在拥有该文件的 skill 内改相对路径；跨 skill 的提及留给人工，否则会指向本 skill 下不存在的文件。
- **改写产物是 shell 时不加反引号/`$`**：md 的排版约定（工具名包反引号、skill 引用写 `$name`）搬进 `.sh` 就变成命令替换和变量展开，产物照跑不报错、只是输出悄悄不对。同一条语义规则若同时作用于 md 与脚本，按 `when_path: '*.md'` 拆两份（见 `divergence_rules.yaml` 的 D3-*）。verify.py 有一道警告级检查专盯这个。

## R10 平台能力分歧（不是措辞不同，是流程不同）

R1–R5 处理的是**同一件事的两种写法**。R10 处理的是**两边根本不是同一件事**：CC 与 Codex 在某个功能点上用的工具、命令、步骤数都不一样，翻译不出来，只能逐条登记正确的 Codex 侧写法。

判据很简单 —— **改完之后，两边的行为是否还等价？** 等价是 R1–R5（换个说法而已）；不等价是 R10（做的事真的变了）。

已登记的分歧：

| 分歧 | CC 侧 | Codex 侧 | 落在哪 |
|---|---|---|---|
| 阶段用量采集 | `a2h metrics report-stage`（采 usage.v2 + OTLP 上传） | `a2h-codex mark-stage`（只落水位标记；用量由生命周期 hook 传会话、服务端解析） | `divergence_rules.yaml` D1-* |
| 迁移完成信号 | `a2h metrics report-verify` | `a2h-codex count-lines` + `mark-stage`（后者才是完成判定，故顺序有语义） | `overlays.yaml` D-verify-section-10 |
| retrospect 收尾 | 三步（report-stage / upload-retrospect / upload-sessions） | 两步（count-lines / mark-stage） | `overlays.yaml` D-retrospect-section-10 |
| 授权前置门 | a2h-spec 开头与 §2 各一道 `verify-access` / `verify-consent` | 无（授权在 `$a2h-init` 一次性完成） | `overlays.yaml` D-spec-drop-* |
| 命令调用前缀 | `/a2h-run` slash command | `$a2h-run`（Codex 无自定义 slash command） | `divergence_rules.yaml` D2-* |
| 子代理派发 | `Task tool` / `subagent_type` | `spawn_agent` / `agent_type` | `divergence_rules.yaml` D3-* + banner overlay |

### 两层执行机制

**单行内能表达的** → `scripts/divergence_rules.yaml`。schema 与 `rewrite_rules.yaml` 完全相同（同一个 `Rewriter` 跑，本文件的规则排在后面）。分文件存放**不是**为了实现差异，是为了**失效语义**不同：rewrite 规则失配 = 源侧改了措辞，补个正则就行；divergence 规则失配 = 两边能力分叉了，得人重新推导映射。报告里也分族统计。

**单行内表达不了的**（删整行 / 换整节 / frontmatter 后插内容）→ `scripts/overlays.yaml` + `overlays/*.md` 正文，由 `overlay.py` 在行改写**之后**施加。跑在后面的好处：锚点只需匹配已归一化的那一种形态，不必兼容源侧原文。

三个 op：`delete_lines`（连同紧随的空行一起删，即段落删除）、`replace_section`（标题行到下一个节边界；**跟踪 ``` 围栏**，否则 bash 块里以 `# ` 开头的注释会被当成节边界）、`insert_after_frontmatter`。

### 两道防线，各管一种失效

| 机制 | 管什么 | 失败等级 |
|---|---|---|
| `anchor` + `expect: N` | 定位失败：源侧把这一节改名 / 删了 / 拆成两节 | **硬失败，退出码 1** |
| `source_digest` | 定位成功但被覆盖的原文变了（内容改了、标题没动） | 警告 |

**为什么定位失败必须硬失败**：上游一旦重构被补丁的那一节，锚点失配后若只是跳过，产物里就留着 CC 版的 `a2h metrics report-stage` —— 转换「悄悄少做一件事」，不报错、audit 也未必覆盖得到，要到下游 migbot-CodeX 交付时才拦得住。那边的守卫注释写得很清楚：这种静默漂移已经真的发生过一次。

**digest 管的是本方案的已知盲区**：overlay 不理解语义，只做定位 + 替换。源侧内容改了而标题没动时，它会**成功地**用旧的 Codex 版盖掉上游的新改进。digest 是这种情况下唯一的哨兵。

遇到锚点失配时的正确动作：去看源侧那一节现在长什么样，重新判断 Codex 侧该怎么写，然后更新 overlay 正文与 digest。**不要**把 `expect` 改成实际命中数了事 —— 那等于把告警关掉。这一步必须由人做（两边产品分叉了），机制不该也不能自动弥合。

失效行为由 `scripts/test_overlay.py` 锁住（锚点失配/重复 = 硬失败且不动文件；内容漂移 = 警告且照打）。

### 产物断言（verify.py）

这几条原本长在下游 migbot-CodeX 的 `validate.sh` 里，交付时才拦。前移到生成侧后坏产物出不了 `convert.py` 这道门；两边都留是有意的（那边还管着 26 个不经本转换器产出的自有 skill）。

- 全产物无 `a2h metrics` / `a2h stats` 残留、无 `/a2h-*` slash command 残留
- 五个 pipeline skill 各含 `a2h-codex mark-stage a2h-<stage>`（sentinel 是 `$a2h-run` 判定阶段完成的唯一依据）
- verify / retrospect 含 `count-lines`，且它排在 `mark-stage` **之前**（完成状态一落库看板就开始展示行数，行数得先就位）
- `$xxx` 引用不悬空：不指向产出的 skill/agent、也不在 `overlays.yaml` 的 `external_skills` 名单里 → 警告

`external_skills` 登记的是 migbot-CodeX 侧独立维护、不经本转换器产出的 skill（`a2h-run` / `a2h-init` / `a2h-build` / `a2h-privacy` 及其 `-zh` 变体，加条件可用的 `harmonyos-development`）。那边改名时这边会响一声，而不是等交付后才发现引用悬空。
