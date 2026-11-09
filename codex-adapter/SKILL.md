---
name: codex-adapter
description: 把 arkts-skills / arkts-agents 转换成 OpenAI Codex 可用的形态（codex/ 目录），并维护转换规则集。当用户说"重新生成 codex 版本"、"同步 codex 适配"、"源侧 skill 改了要更新 codex"、"codex 转换规则要加一条"、"某处转换改坏了"时使用。也负责转换后的自检报告与待人工项分诊。不用于 Android→HarmonyOS 迁移本身（那是 a2h-* 系列）；不用于直接编辑 codex/ 产物内容（产物每次重建，改动要落在源侧或规则里）；不处理 skill 内容质量（那是 skill-checker）。
tags: [tool, codex, migration, build]
type: tool
domain: engineering
---

# codex-adapter

## 1. 定位

`arkts-skills/` + `arkts-agents/` 或 hmigbot-ios 的 `migbot/skills` + `migbot/agents`
（Claude Code 形态）→ `codex/`（OpenAI Codex 形态）的**转换器与规则维护入口**。

一条命令重新生成整个 `codex/`，转换是确定性的：同一份源反复跑，产物逐字节一致。改写不了的少数几项由脚本列进报告，不藏着。

**边界**：
- 本 skill 服务于**本仓库的构建**，不参与 Android→HarmonyOS 迁移流程（那是 `a2h-*` 系列）
- 不评价 skill 内容质量（那是 `$skill-checker`），只管形态转换
- 不直接改 `codex/` 里的内容 —— 产物每次重建，改动要落在源侧或规则里（见 §5）

**位置**：本 skill 放在仓库根 `codex-adapter/`，**不在** `arkts-skills/skills/` 下 —— 它是构建工具而非迁移能力，且放在源目录里会被自己转换（正文里的 `Claude Code`、`.claude/`、`Skill({` 是待转换术语的**样本**，过一遍规则会把规则表改成「Codex → Codex」这种废话）。

代价是 `.claude-plugin/plugin.json` 的 `skills: arkts-skills/skills/` 扫不到它，因此**不会随插件自动加载**。用法是直接跑脚本（见 §2）；若要按 skill 方式调用，把本目录 symlink 进 `.claude/skills/` 即可。

---

## 2. 快速开始

```bash
# 在仓库任意位置执行均可 —— 脚本会向上自动定位仓库根
python3 codex-adapter/scripts/convert.py --dry-run   # 先看会改什么，产物落 .codex-dry-run/，不动 codex/
python3 codex-adapter/scripts/convert.py             # 确认后重新生成 codex/
```

其他参数：`--repo-root <path>`（装到仓库外时指定源在哪）、`--output <path>`（产物写到别处）。

跑完看四处输出：

- **语义层自动改写 N 处** —— 脚本干掉的
- **待人工/LLM N 项** —— 逐项列在 `codex/MIGRATION-REPORT.md` 的「待人工 / LLM 处理」段
- **产物校验** —— 结构自检，有失败则退出码为 1（详见 §6）
- **⚠ 规则失效警告** —— 标了 `expect: required` 的规则 0 命中，说明源侧措辞变了（见 §4a）

单独跑校验（不重新生成）：

```bash
python3 codex-adapter/scripts/verify.py                    # 校验 codex/
python3 codex-adapter/scripts/verify.py --codex-dir <path> # 校验试跑产物
```

---

## 3. 分工：什么自动、什么留给人

规则 SSOT 在 [`references/REWRITE-RULES.md`](./references/REWRITE-RULES.md)，R1–R10 逐条说明。执行方式：

| 层 | 内容 | 谁做 |
|---|---|---|
| 机械层 | frontmatter 清洗、目录搬运、TOML 生成、隐式路由开关、manifest | `convert.py` |
| 语义层（可确定表达） | 术语/路径、Skill 调用语法、子代理派发、多行调用块、内嵌 agent 路径、frontmatter 遗留 | `rewrite.py` + 三个 yaml |
| **平台能力分歧（R10）** | 两边工具/命令/步骤真的不同：metrics CLI、slash 前缀、派发工具名（单行）；授权前置门、收尾数据采集节、派发约定 banner（结构性） | `divergence_rules.yaml` + `overlay.py` + `overlays.yaml` |
| 语义层（需理解） | 机制不等价、跨 skill 消歧、skill/agent 形态不符、description 预算 | 人 / LLM |

配置文件都在 `scripts/` 下，改哪个取决于问题类型（见 §4）。

**R10 和 R1–R5 的分界**：改完之后两边行为还等价吗？等价 = 只是换个说法，归 R1–R5；不等价 = 做的事真的变了，归 R10。`a2h metrics report-stage` → `a2h-codex mark-stage` 是后者 —— 不只是换了个二进制名，采集用量这件事在 Codex 侧压根不由这条命令做。

---

## 4. 四类维护动作

### 4a. 新的写法没被转换 → 加规则

`scripts/rewrite_rules.yaml`，有序列表，**先具体后泛化**（列表顺序即执行顺序）。

```yaml
- id: R3-dispatch-named
  pattern: '派发 Agent `([a-z0-9-]+)`'
  repl: '派发 Codex 子代理 `\1`（定义于 `.codex/agents/\1.toml`）'
```

只在特定 skill 内生效时加 `when_path`（glob，相对 `codex/`）：

```yaml
- id: R5-spec-fixer-ui
  when_path: 'skills/arkts-ui-verifier/*'
  pattern: '\bspec-fixer\b(?!-u[ti])(?!\.md)(?!/)'
  repl: 'spec-fixer-ui'
```

> 判断能不能用 `when_path`：**目标是否由文件路径唯一决定**。是 → 规则能做，别留给人。ut/ui 的 spec-fixer 分裂就是这么从「需人工消歧」降级成规则的。同理，若线索在**同一句话里**（如句中已点名 `arkts-ut-verifier`），用捕获组把线索带进 pattern 即可，也不必留给人。

**整句精确匹配的规则要标 `expect: required`**：

```yaml
- id: R0-memory-intro
  expect: required          # 0 命中 → 报警
  pattern: '将本次迁移中值得跨会话复用的经验写入 Claude Code memory 系统：'
  repl: '...'
```

这类规则（R0 段的机制映射）匹配的是一整句话，源侧改个措辞就失配 —— 而失配后转换只是**悄悄少做一件事**，不报错、audit 也未必覆盖得到。标了 `required` 后 0 命中会明确警告。防御性规则（源侧当前没有该写法）不要标，否则每轮都是噪音。

### 4b. 规则改坏了不该改的 → 加保护

`scripts/exceptions.yaml`，三级粒度：

- `protected_paths` 整文件跳过（如多平台注册表 `skill-hub-guide.md`，其中 `platform: claude-code` 是合法枚举值）
- `protected_lines` 命中该正则的行跳过（全局）
- 行内标记：在源文件那一行尾部写 `codex-keep`（md 用 `<!-- codex-keep -->`），就地声明

**判断一次，长期复用** —— 保护区是把人工判断固化成数据的地方，不要每轮重新判断。

### 4c. 文件名要跟着改 → 成对登记

行规则改了正文里的文件名引用，`scripts/path_renames.yaml` 必须有对应条目，否则引用断链（R9）。

```yaml
- pattern: '^claude-md-(.*)$'
  repl: 'agents-md-\1'
```

### 4d. 报告里的待人工项 → 逐项分诊

`codex/MIGRATION-REPORT.md`「待人工 / LLM 处理」段按类型分组：

| 类型 | 含义 | 处理 |
|---|---|---|
| `mechanism-gap` | Codex 无对应机制 | 用指令补偿，不是换词。如 `@file.md` import → 写明「会话开始必须先读取」 |
| `agent-disambiguation` | 跨 skill 提及，路径判不出指向 | 人工改写该句 |
| `skill-to-agent` | 目标在 Codex 侧是子代理却写成 skill 调用 | 改为「参照子代理定义执行」或改成派发 |
| `forbidden:*` | R8 禁用词残留 | 通常意味着 §4a 缺规则 |

改完**要回到源侧改**（`arkts-skills/`），不要直接改 `codex/` —— 下次重新生成会覆盖。若源侧不该改（是 Codex 特有表述），就补一条规则或例外，让转换器下次自己做对。

### 4e. 两边功能点真的不一样 → 登记分歧（R10）

先用 §3 的分界判一下：改完两边行为还等价吗？不等价才走这里。

**单行内能表达** → `scripts/divergence_rules.yaml`，schema 与 `rewrite_rules.yaml` 相同。

**单行内表达不了**（删整行 / 换整节 / frontmatter 后插内容）→ `scripts/overlays.yaml` 登记 + `overlays/` 放正文：

```yaml
- id: D-retrospect-section-10
  path: skills/a2h-retrospect/SKILL.md
  op: replace_section          # 另有 delete_lines / insert_after_frontmatter
  heading: '^## 10\. '         # 锚点选结构位（标题、整行命令），别选散文
  expect: 1                    # 命中 ≠1 → 硬失败，退出码 1
  body: overlays/a2h-retrospect-section-10.md
  source_digest: 88c4a806b18c  # 被覆盖内容的哈希；变了 → 警告
  why: 三步塌成两步（upload-* 由生命周期 hook 取代）
```

新增条目时 `source_digest` 先留空，跑一次 `--dry-run`，值在报告「平台能力分歧补丁」表的最后一列，抄回来即可。**别**拿 `overlay.py` 对着已打过补丁的产物再算一遍 —— 那量到的是替换之后的内容，填回去等于把漂移告警永久关掉。

**锚点失配（硬失败）时的正确动作**：去看源侧那一节现在长什么样，重新判断 Codex 侧该怎么写，更新正文与 digest。**不要**把 `expect` 改成实际命中数了事 —— 那是把告警关掉，产物里会留着 CC 版的命令。这一步必须人做：两边产品分叉了，机制不该替你弥合。

---

## 5. 硬约束

**转换只作用于源内容。** `convert.py` 生成的前言（前置 Skills / 工具边界 / 溯源注释「原 Claude Code 配置 model: opus」）与 `overlay.py` 注入的派发约定 banner 都不过规则 —— 过了会变成「原 Codex 配置」这种假信息，banner 里那句「CC 写 `subagent_type`，Codex 写 `agent_type`」也会被自己的规则吃掉。新增生成内容时保持这条，并把它登记进 `rewrite.py` 的 `_GENERATED_PREAMBLE`，否则 R8 自检会把它当残留报出来。

**`codex/` 是产物，不是源。** `convert.py` 每次清空 `codex/skills` 与 `codex/agents` 重建。直接改 `codex/` 的内容下次就没了。顶层手写文件（`README.md` / `AGENTS.md` / `config.toml.sample`）不受影响。

**重新生成前先确认这两类人工增补已回填源侧**，否则会丢：

1. `type` / `domain`（决定隐式路由开关，源侧有些 skill 没这两个字段）
2. 压缩过的 description（Codex 隐式路由预算 8000 字符）

**本 skill 自己不参与转换。** 主要靠位置保证（在仓库根，不在 `arkts-skills/skills/` 扫描范围内）；`convert.py` 的 `SKIP_SKILLS` 与 `exceptions.yaml` 里各留了一条同名防御，万一将来被挪回源目录也不会自噬。

---

## 6. 自检

`convert.py` 跑完自动做三层自检，都不需要手动触发。

**① R8 禁用词残留**（`rewrite.audit`）——结果进报告。三类不计残留（判定过、决定保留的）：保护区内的文件与行、转换器自己生成的溯源说明、平台枚举语境。

**② 产物结构校验**（`verify.py`）——有失败则**退出码为 1**，可直接用作 CI 门禁：

| 检查 | 失败意味着 |
|---|---|
| agent TOML 可解析 | 改写把裸 `'''` 写进了 `developer_instructions` |
| SKILL.md frontmatter 有 name/description | Codex 加载不了该 skill |
| 目录名与 `name` 一致 | Codex 按 name 路由，不一致则 `$name` 引用找不到目录 |
| openai.yaml 可解析 | 隐式路由开关失效 |
| R8 禁用词残留 0 | 缺规则（见 §4a） |
| 未引入断链 | 路径规则改坏了引用（与源侧基线对比，源侧本有的断链不算） |
| overlay 锚点全部命中 | 源侧重构了被补丁的那一节（见 §4e） |
| 无 `a2h metrics` / `/a2h-*` 残留 | 分歧规则失效（见 §4e） |
| 五个 pipeline skill 各有 `mark-stage` | 收尾水位标记丢了——`$a2h-run` 靠它判定阶段完成，缺了流水线会卡住 |
| verify/retrospect 的 `count-lines` 在 `mark-stage` 之前 | 顺序错了：完成状态一落库看板就展示行数，行数得先就位 |

预算超支只警告不失败——它是平台约束，不是结构错误。另有三类警告级检查：overlay 的 `source_digest` 漂移（上游改了被覆盖的内容）、`$xxx` 引用悬空（不在产物里也不在 `external_skills` 名单里）、shell 活字符注入（改写把 md 的反引号/`$` 排版约定带进了 `.sh`，那里它们是命令替换和变量展开）。

overlay 自身的失效行为由 `scripts/test_overlay.py` 锁住（锚点失配/重复 = 硬失败且不动文件；内容漂移 = 警告且照打）：

```bash
python3 codex-adapter/scripts/test_overlay.py
```

**③ 规则失效检测**——标了 `expect: required` 的规则 0 命中就警告。这一层专防**静默失效**：整句匹配的规则在源侧措辞微调后会失配，而失配只是少做一件事，不报错、audit 也未必覆盖得到。

> 官方 `migrate-to-codex --validate-target` 未纳入本脚本，切换到自动重生成前建议补上这一关。
