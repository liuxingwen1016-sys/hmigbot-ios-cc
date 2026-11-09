# codex-adapter

把 Claude Code 形态的 `arkts-skills/` + `arkts-agents/` 或 hmigbot-ios 的
`migbot/skills` + `migbot/agents` 转换成 `codex/`（OpenAI Codex 形态）。

转换是确定性的：同一份源反复跑，产物逐字节一致。机械层与可确定表达的语义改写全自动完成，剩下需要人理解的少数几项列进迁移报告，不藏着。

规则怎么改、报告怎么读，见 [SKILL.md](./SKILL.md)。

---

## 环境要求

- Python 3.9+
- PyYAML：`pip install pyyaml`

---

## 方式一：直接跑脚本

最常用。不依赖任何 skill 加载机制，在仓库任意位置执行都行 —— 脚本会向上自动定位仓库根。

```bash
# 试跑：只看会改什么，产物落 <repo>/.codex-dry-run/，不动 codex/
python3 codex-adapter/scripts/convert.py --dry-run

# 正式执行：清空重建 codex/skills 与 codex/agents
python3 codex-adapter/scripts/convert.py
```

### 参数

| 参数 | 说明 |
|---|---|
| `--dry-run` | 产物写到 `<repo>/.codex-dry-run/`，不碰 `codex/`。用来先看差异 |
| `--repo-root <path>` | 显式指定源在哪（含 `arkts-skills/` 与 `arkts-agents/` 的目录）。脚本装到仓库外时用 |
| `--output <path>` | 产物写到别处，不写 `codex/`。用来做对比或 CI 校验 |

### 标准流程

```bash
# ① 改源侧（arkts-skills/ 或 arkts-agents/）—— 不要直接改 codex/，它是产物

# ② 试跑，看差异
python3 codex-adapter/scripts/convert.py --dry-run
diff -r .codex-dry-run/skills codex/skills | head -50

# ③ 确认无误，正式生成
python3 codex-adapter/scripts/convert.py

# ④ 处理报告里的待人工项，改动落回源侧，回到 ①
sed -n '/## 待人工/,/## 机械扫描全景/p' codex/MIGRATION-REPORT.md
```

跑完看四处输出：

- **语义层自动改写 N 处** —— 脚本自动完成的
- **待人工/LLM N 项** —— 需要人判断的，逐项列在 `codex/MIGRATION-REPORT.md`
- **产物校验** —— 结构自检；有失败则**退出码为 1**（可直接当 CI 门禁）
- **⚠ 警告** —— 规则失效、隐式路由预算超支

### 只校验不重新生成

```bash
python3 codex-adapter/scripts/verify.py                     # 校验 codex/
python3 codex-adapter/scripts/verify.py --codex-dir <path>  # 校验别处的产物
```

校验项：agent TOML 可解析、SKILL.md frontmatter 完整、目录名与 `name` 一致、openai.yaml 可解析、R8 禁用词残留、转换未引入断链、隐式路由预算（超支只警告）。

---

## 方式二：作为 skill 调用

本目录在仓库根，而 `.claude-plugin/plugin.json` 只从 `arkts-skills/skills/` 发现 skill，所以**默认不会被自动加载**。

> 为什么不放进 `arkts-skills/skills/`：它是构建工具不是迁移能力，且正文里的 `Claude Code`、`.claude/`、`Skill({` 是**待转换术语的样本**——放在源目录里会被自己转换，规则表会变成「Codex → Codex」这种废话。

要按 skill 用，建个软链即可：

```bash
mkdir -p ~/.claude/skills
ln -s "$(pwd)/codex-adapter" ~/.claude/skills/codex-adapter
```

之后这样触发：

```
/codex-adapter
```

或直接说需求，让模型自己路由：

- "重新生成 codex 版本"
- "源侧 skill 改了，同步一下 codex"
- "codex 转换规则要加一条"
- "某处转换改坏了，怎么加保护"

软链是双向的：改仓库里的文件即时生效，不用重新安装。

---

## 首次执行前先确认

`convert.py` 每次会清空重建 `codex/skills` 与 `codex/agents`。**只存在于 `codex/` 侧、源侧没有的人工增补会丢**：

| 内容 | 为什么要紧 | 处理 |
|---|---|---|
| 压缩过的 description（12 条） | 源侧总长 10868 字符 > Codex 隐式路由 8000 预算 | 压缩结果回填源侧 frontmatter |
| 部分 skill 的 `type` / `domain` | 决定隐式路由开关，源侧缺这两个字段 | 回填源侧 frontmatter |
| `skill-checker` 的平台适配说明 | 一段说明会丢 | 回填源侧，或写成转换规则 |

前两类回填后还有额外好处：taxonomy 信息进了输入，规则就能自己算，能消掉一整类人工依赖。

顶层手写文件（`codex/README.md`、`codex/AGENTS.md`、`codex/config.toml.sample`）不受影响，脚本不碰。

---

## 挂进 CI（可选）

两道门禁，都靠退出码，不用额外解析输出：

```bash
# ① 产物结构是否合法
python3 codex-adapter/scripts/verify.py || exit 1

# ② 产物是否与源同步（转换确定性，同源必同产物）
python3 codex-adapter/scripts/convert.py --output /tmp/codex-check >/dev/null
diff -r /tmp/codex-check/skills codex/skills || {
  echo "codex/ 与源不同步，请重新生成"; exit 1
}
```

现有 `.github/workflows/pr-check.yml` 的 5 个校验都不覆盖 `codex/`，这一道可以补上。

---

## 目录

```
codex-adapter/
├── README.md              本文件 —— 怎么跑
├── SKILL.md               怎么维护规则、怎么读报告
├── evals/evals.json       测试用例
├── overlays/              分歧补丁的正文（整节替换 / banner 的实际内容）
├── references/
│   └── REWRITE-RULES.md   规则 SSOT（R1–R10）
└── scripts/
    ├── convert.py         转换器入口
    ├── rewrite.py         改写引擎：块变换 + 行规则 + 保护区 + R8 自检
    ├── overlay.py         平台分歧的结构性补丁（删行/换节/插 banner，R10）
    ├── verify.py          产物结构校验（可独立跑，退出码可用作 CI 门禁）
    ├── test_overlay.py    overlay 失效行为测试（锚点失配必须硬失败）
    ├── rewrite_rules.yaml 行改写规则（when_path 路径限定 / expect 失效检测）
    ├── divergence_rules.yaml  平台能力分歧的单行规则（R10）
    ├── overlays.yaml      分歧补丁登记表 + 外部 skill 白名单（R10）
    ├── exceptions.yaml    保护区：规则会误伤的语境登记在此
    └── path_renames.yaml  文件名转换（与正文引用成对）
```

在 hmigbot-ios 中，转换器还把 `migbot/commands/*.md` 生成为 `$i2h-*` 入口 skill，并保留改写后的 `codex/commands/`、`codex/hooks/` 与 `codex/bin/` 运行时资产。
