#!/usr/bin/env python3
"""Codex 适配 —— 语义层改写引擎（L2：可确定性表达的那部分）。

三件事：
  1. 块变换  多行 `Agent(...)` / `Skill({...})` 调用块 → Codex 派发/调用写法（正则做不了，需状态机）
  2. 行改写  rewrite_rules.yaml 的有序正则，逐行套用
  3. 保护区  exceptions.yaml 命中的文件/行整体跳过 —— 规则会误伤的语境在那里登记

剩下的（例外新判、机制不等价、上下文消歧、description 预算压缩）不在这里做，
由 audit() 扫出来写进迁移报告，交人工或 LLM 定夺。

单独运行可做干跑对比：
    python3 rewrite.py --diff <文件或目录>
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent


# ─── 规则与保护区加载 ─────────────────────────────────────────────────────────
@dataclass
class Rule:
    id: str
    pat: re.Pattern
    repl: str
    when_path: str | None = None   # 仅在相对 codex/ 的路径匹配该 glob 时生效
    required: bool = False         # 本该命中：0 命中说明源侧措辞变了，规则已静默失效
    family: str = "rewrite"        # rewrite=形态翻译 / divergence=平台能力分歧（R10）

    def applies_to(self, relpath: str) -> bool:
        return self.when_path is None or fnmatch(relpath, self.when_path)


@dataclass
class Exceptions:
    paths: list[str] = field(default_factory=list)
    lines: list[re.Pattern] = field(default_factory=list)
    marker: str = "codex-keep"

    def file_protected(self, relpath: str) -> bool:
        return any(fnmatch(relpath, p) for p in self.paths)

    def line_protected(self, line: str) -> bool:
        if self.marker and self.marker in line:
            return True
        return any(p.search(line) for p in self.lines)


def load_rules(path: Path | None = None, family: str = "rewrite") -> list[Rule]:
    data = yaml.safe_load((path or HERE / "rewrite_rules.yaml").read_text(encoding="utf-8"))
    return [Rule(r["id"], re.compile(r["pattern"]), r["repl"], r.get("when_path"),
                 r.get("expect") == "required", family) for r in data]


def load_all_rules() -> list[Rule]:
    """形态翻译规则 + 平台分歧规则，按此顺序拼接（分歧规则后跑）。

    两者 schema 相同、执行机制相同，分文件存放是因为**失效语义不同**：
    rewrite 规则失配 = 源侧改了措辞，补个正则即可；divergence 规则失配 =
    CC 与 Codex 两边的能力真的分叉了，得人重新推导映射（见 REWRITE-RULES.md R10）。
    """
    rules = load_rules()
    div = HERE / "divergence_rules.yaml"
    if div.exists():
        rules += load_rules(div, family="divergence")
    return rules


def load_renames(path: Path | None = None) -> list[tuple[re.Pattern, str]]:
    """文件名转换规则。正文引用被行规则改了名，文件本身也得改，否则引用断链。"""
    p = path or HERE / "path_renames.yaml"
    if not p.exists():
        return []
    return [(re.compile(r["pattern"]), r["repl"]) for r in (yaml.safe_load(p.read_text(encoding="utf-8")) or [])]


def rename_file(name: str, renames=None) -> str:
    for pat, repl in (renames if renames is not None else load_renames()):
        new = pat.sub(repl, name)
        if new != name:
            return new
    return name


def load_exceptions(path: Path | None = None) -> Exceptions:
    p = path or HERE / "exceptions.yaml"
    if not p.exists():
        return Exceptions()
    d = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return Exceptions(
        paths=d.get("protected_paths") or [],
        lines=[re.compile(x) for x in (d.get("protected_lines") or [])],
        marker=d.get("inline_marker") or "codex-keep",
    )


# ─── 块变换 ───────────────────────────────────────────────────────────────────
# 源里的多行调用块有三种形态，各自的目标写法在 REWRITE-RULES.md R2/R3。
# 共同点：都跨行且要重排结构，单行正则做不到，所以先于行改写处理。

_H_TITLE_AGENT = re.compile(r"^#{1,3} .*?（([a-z0-9-]+)）")  # 「# §5. …（a2h-migration-worker）」
_FENCE = re.compile(r"^\s*```")


def _nearest_agent_name(lines: list[str], idx: int, known: set[str]) -> str | None:
    """向上找最近的标题，取括号里的 agent 名。

    a2h-execute/references/agent-prompts/*.md 的 `Agent(` 块不写 subagent_type，
    派发目标只出现在节标题里（人工改写时也是这么认的），据此回填。
    """
    for i in range(idx, -1, -1):
        m = _H_TITLE_AGENT.match(lines[i])
        if m and m.group(1) in known:
            return m.group(1)
    return None


# 末尾的 `\)?` 容忍「闭合括号贴在本行尾」的写法：`subagent_type="general-purpose")`
# ——源里有把 Agent( 的收尾 `)` 直接接在最后一个参数行的（plan-dispatch.md）。
# 不容忍的话该行失配，整块不转换，subagent_type 原样漏进产物（R8 残留）。
_SUBAGENT_KV = re.compile(r'^\s*subagent_type\s*=\s*"?([a-z0-9-]+)"?\)?,?\s*$')


def _transform_fenced_agent(lines: list[str], i: int, known: set[str], stats: dict):
    """形态 A：``` 围栏内独占的 `Agent(\n  prompt="…"\n)` → 派发说明 + 纯提示词围栏。

    派发目标两个来源，优先级从高到低：
      1. 块内的 `subagent_type="X"`（可能出现在 prompt 之后，故整块扫）
      2. 最近的节标题括号（a2h-execute 的 prompt 文件都不写 subagent_type）
    """
    if lines[i].strip() != "Agent(" or sum(1 for line in lines[:i] if _FENCE.match(line)) % 2 == 0:
        return None
    j = i + 1
    if j >= len(lines):
        return None
    m = re.match(r'^(\s*)prompt\s*=\s*"(.*)$', lines[j])
    if not m:
        return None
    # 找块尾：闭合围栏
    end = next((k for k in range(j + 1, len(lines)) if _FENCE.match(lines[k])), None)
    if end is None:
        return None

    body = [m.group(2)] + lines[j + 1:end]
    # 块内显式声明的派发目标优先；同时把该行从提示词正文里摘掉
    name = None
    for k, l in enumerate(body):
        km = _SUBAGENT_KV.match(l)
        if km:
            name = km.group(1)
            body.pop(k)
            break
    if not name:
        name = _nearest_agent_name(lines, i, known)
    if not name:
        return None

    # 去掉 prompt 字符串的收尾 `")` / `",` / `"` / `)` 与尾部空行
    # （末参与 subagent_type 之间的 `,` 分隔符，摘掉 subagent_type 行后会留在末尾）
    while body and re.fullmatch(r'\s*["\)]*\s*', body[-1]):
        body.pop()
    if body:
        body[-1] = re.sub(r'"\s*\)?\s*,?\s*$', "", body[-1])

    # general-purpose 是内置子代理，没有专属 TOML —— 不能给它编一个 .codex/agents/ 路径
    if name == "general-purpose":
        head = "派发一个通用子代理，任务提示词："
    else:
        head = f"派发 Codex 子代理 `{name}`（定义于 `.codex/agents/{name}.toml`），任务提示词："
    out = [head, "", "```", *body, "```"]
    stats["block-agent-fenced"] = stats.get("block-agent-fenced", 0) + 1
    drop_from = i - 1 if i and _FENCE.match(lines[i - 1]) else i
    return out, end + 1, drop_from


def _transform_pseudo_agent(lines: list[str], i: int, stats: dict):
    """形态 B/C：伪代码里的 `Agent(subagent_type=…, …)` 多行调用。

    general-purpose → dispatch_general_subagent(...)（去掉 subagent_type 行）
    具名 agent      → 注释标出定义位置 + dispatch_codex_subagent("name", ...)
    """
    # 允许赋值前缀：`result = Agent(` / `b_result_raw = Agent(`
    m = re.match(r"^(\s*)((?:\w+\s*=\s*)?)Agent\($", lines[i])
    if not m:
        return None
    indent, assign = m.group(1), m.group(2)
    # 闭合括号按**同缩进**找，不能限行数 —— prompt 常是几十行的 f-string
    end = next((k for k in range(i + 1, len(lines))
                if lines[k].rstrip() in (f"{indent})", f"{indent}),")), None)
    if end is None:
        return None
    inner = lines[i + 1:end]
    st = next((k for k, l in enumerate(inner)
               if re.match(r"^\s*subagent_type\s*=\s*['\"]", l)), None)
    if st is None:
        return None
    name_match = re.search(r"['\"]([a-z0-9-]+)['\"]", inner[st])
    if name_match is None:
        return None
    name = name_match.group(1)
    rest = inner[:st] + inner[st + 1:]

    if name == "general-purpose":
        head = [f"{indent}{assign}dispatch_general_subagent("]
        stats["block-agent-pseudo-general"] = stats.get("block-agent-pseudo-general", 0) + 1
    else:
        head = [
            f"{indent}# 派发 Codex 子代理 {name}（定义于 .codex/agents/{name}.toml）",
            f"{indent}{assign}dispatch_codex_subagent(",
            f'{indent}    "{name}",',
        ]
        stats["block-agent-pseudo-named"] = stats.get("block-agent-pseudo-named", 0) + 1
    return head + rest + [lines[end]], end + 1, i


def _transform_fenced_skill(lines: list[str], i: int, stats: dict):
    """形态 D：围栏内多行 `Skill({ skill: "x", args: "…" })` → 一句散文调用。"""
    if lines[i].strip() != "Skill({":
        return None
    # Skill({ ... }) 常嵌在 bash/伪代码围栏中，不一定紧跟开围栏。
    if sum(1 for line in lines[:i] if _FENCE.match(line)) % 2 == 0:
        return None
    end = next((k for k in range(i + 1, len(lines))
                if lines[k].strip() in ("})", "});")), None)
    if end is None:
        return None
    blob = " ".join(lines[i + 1:end])
    ms = re.search(r'skill:\s*"([a-z0-9_-]+)"', blob)
    if not ms:
        return None
    name = ms.group(1)
    ma = re.search(r'args:\s*"([^"]*)"', blob)
    call = (f"# Codex skill call: `${name}`（读取 `.agents/skills/{name}/SKILL.md` 并按其执行）"
            + (f"，参数：`{ma.group(1)}`" if ma else ""))
    stats["block-skill-fenced"] = stats.get("block-skill-fenced", 0) + 1
    drop_from = i - 1 if i and _FENCE.match(lines[i - 1]) else i
    return [call], end + 1, drop_from


def transform_blocks(text: str, known_agents: set[str], stats: dict) -> str:
    lines = text.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        hit = (_transform_fenced_agent(lines, i, known_agents, stats)
               or _transform_fenced_skill(lines, i, stats)
               or _transform_pseudo_agent(lines, i, stats))
        if hit:
            repl, nxt, drop_from = hit
            while len(out) > drop_from:      # 回退掉被块吞掉的行（如开围栏）
                out.pop()
            out.extend(repl)
            i = nxt
            continue
        out.append(lines[i])
        i += 1
    return "\n".join(out)


# ─── 行改写 ───────────────────────────────────────────────────────────────────
# 英文词换成中文词后，原本分隔英文的空格要吃掉，否则留下「模型 下次跑时」这种瑕疵。
# 只作用于被规则替换出来的中文词；`Codex` 仍是英文，中英之间保留空格（且「派发 Codex 子代理」
# 是规则生成的固定短语，吃掉空格会变成「Codex子代理」）。
_CJK_GAP = re.compile(r"(模型|子代理)\s+(?=[一-鿿])")


class Rewriter:
    def __init__(self, rules=None, exceptions=None, known_agents=None, renames=None):
        self.rules = rules if rules is not None else load_all_rules()
        self.exc = exceptions if exceptions is not None else load_exceptions()
        self.renames = renames if renames is not None else load_renames()
        self.known_agents = known_agents or set()
        self.stats: dict[str, int] = {}
        self.protected_hits: list[tuple[str, int, str]] = []
        self._family = {r.id: r.family for r in self.rules}

    def family_of(self, rule_id: str) -> str:
        return self._family.get(rule_id, "rewrite")

    def rename(self, filename: str) -> str:
        new = rename_file(filename, self.renames)
        if new != filename:
            self.stats["file-renamed"] = self.stats.get("file-renamed", 0) + 1
        return new

    def stale_rules(self) -> list[str]:
        """标了 expect: required 却一次没命中的规则 —— 源侧措辞已变，规则静默失效了。

        只报 required 的：整句精确匹配（如 R0 机制映射）源侧改个标点就失配，且失配后
        转换悄悄少做一件事、不报错。防御性规则（源侧当前没有该写法）0 命中是正常的，
        全报会淹没真问题。
        """
        return [r.id for r in self.rules if r.required and r.id not in self.stats]

    def rewrite(self, text: str, relpath: str) -> str:
        """改写单个文件内容。relpath 用于保护区匹配，须是相对 codex/ 的路径。"""
        if self.exc.file_protected(relpath):
            self.stats["file-protected"] = self.stats.get("file-protected", 0) + 1
            return text

        text = transform_blocks(text, self.known_agents, self.stats)
        rules = [r for r in self.rules if r.applies_to(relpath)]

        out = []
        for n, line in enumerate(text.split("\n"), 1):
            if self.exc.line_protected(line):
                self.protected_hits.append((relpath, n, line.strip()[:120]))
                out.append(line)
                continue
            new = line
            for r in rules:
                after = r.pat.sub(r.repl, new)
                if after != new:
                    self.stats[r.id] = self.stats.get(r.id, 0) + 1
                    new = after
            if new != line:
                new = _CJK_GAP.sub(r"\1", new)
            out.append(new)
        return "\n".join(out)


# ─── 审计：机械层处理不了的，列出来交人工/LLM ────────────────────────────────
# R8 完成自检禁用词（REWRITE-RULES.md L66）
FORBIDDEN = [
    ("Skill({", re.compile(r"Skill\s*\(\s*\{")),
    ("subagent_type", re.compile(r"subagent_type")),
    ("CLAUDE.md", re.compile(r"CLAUDE\.md")),
    ("Claude Code", re.compile(r"[Cc]laude[- ][Cc]ode")),
    (".claude/", re.compile(r"\.claude/")),
    ("allowed-tools", re.compile(r"allowed-tools")),
    ("argument-hint", re.compile(r"argument-hint")),
    ("Task 工具", re.compile(r"Task 工具")),
    # 英文写法：源侧 arkts-visual-verify 用的是 `Task tool`，中文规则和禁用词都逮不着，
    # 曾整整 4 处静默漏过转换（由 divergence_rules.yaml 的 D3-* 负责改写）
    ("Task tool", re.compile(r"Task tool")),
    ("Agent 工具", re.compile(r"Agent 工具")),
    ("裸 Claude", re.compile(r"\bClaude\b")),
    # CC 专有的 metrics CLI —— Codex 侧是 a2h-codex，命令动词都不同（R10 / D1-*）
    ("a2h metrics CLI", re.compile(r"\ba2h(?:\.exe)? +(?:metrics|stats) ")),
]

# 已知的「必须人理解才能改」的语境 —— 命中只报告不动手
SEMANTIC_FLAGS = [
    ("mechanism-gap", re.compile(r"@[\w/.-]+\.md.*import|import 语法|Memory 系统"),
     "机制不等价：Codex 无对应能力，需改成显式指令补偿"),
    ("agent-disambiguation", re.compile(r"spec-fixer(?!-u[ti])(?!\.md)"),
     "跨 skill 提及，路径定不了指向哪个，需人工判断 spec-fixer-ut / -ui"),
]
# 「当 skill 调用」但目标在 Codex 侧其实是 agent —— 需要 agent 名单才能判定，故单列
_SKILL_CALL = re.compile(r"(?:使用|调用) `\$([a-z0-9_-]+)` skill")


# 转换器自己生成的内容：内含「Claude Code」「subagent_type」是刻意的（讲的是迁移前的
# 状态、或在教模型两边的对应关系），不算残留。
#   - 溯源说明：convert.py 的 agent_md_to_toml / inject_dropped_frontmatter 前言
#   - 派发约定 banner：overlay.py 注入，整句就是在说「CC 写 subagent_type，Codex 写
#     agent_type」，把它当残留报出来等于要求它别提 CC 的字段名，那这句话就没用了
_GENERATED_PREAMBLE = re.compile(
    r"^\s*#?#?\s*(原名:|原 Claude Code 配置|## 前置 Skills（原 Claude Code"
    r"|## 工具边界（原 Claude Code|## 调用参数与工具边界（原 Claude Code)"
    r"|^> \*\*Codex subagent dispatch convention\.\*\*")


def audit(text: str, relpath: str, exc: Exceptions | None = None,
          known_agents: set[str] | None = None) -> list[tuple[str, int, str, str]]:
    """返回 [(kind, lineno, 摘要, 说明)]。kind=forbidden:* 是硬残留，其余是待判语境。

    保护区内的行不算残留 —— 它们是「判定过、决定保留」的，不该每轮再报一次。
    """
    if exc and exc.file_protected(relpath):
        return []
    found = []
    for n, line in enumerate(text.split("\n"), 1):
        if _GENERATED_PREAMBLE.match(line) or (exc and exc.line_protected(line)):
            continue
        for name, pat in FORBIDDEN:
            if pat.search(line):
                found.append((f"forbidden:{name}", n, line.strip()[:120], "R8 自检禁用词残留"))
                break
        for kind, pat, why in SEMANTIC_FLAGS:
            if pat.search(line):
                found.append((kind, n, line.strip()[:120], why))
        # 只有目标确实是 agent 才报 —— 否则「调用 `$arkts-i18n` skill」这类正常调用会刷屏
        m = _SKILL_CALL.search(line)
        if m and known_agents and m.group(1) in known_agents:
            found.append(("skill-to-agent", n, line.strip()[:120],
                          f"`{m.group(1)}` 在 Codex 侧是子代理不是 skill，"
                          f"需改为「参照子代理定义执行」或改成派发"))
    return found


# ─── 干跑入口 ────────────────────────────────────────────────────────────────
def _diff_preview(target: Path):
    rw = Rewriter()
    files = [target] if target.is_file() else [
        f for f in sorted(target.rglob("*"))
        if f.is_file() and f.suffix in {".md", ".yaml", ".yml", ".toml", ".py", ".sh", ".ets", ".txt", ".json"}
    ]
    changed = 0
    for f in files:
        try:
            t = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, IsADirectoryError):
            continue
        rel = str(f.relative_to(target)) if target.is_dir() else f.name
        new = rw.rewrite(t, rel)
        if new != t:
            changed += 1
            for a, b in zip(t.split("\n"), new.split("\n")):
                if a != b:
                    print(f"  {rel}\n    - {a.strip()[:150]}\n    + {b.strip()[:150]}")
    print(f"\n{changed}/{len(files)} 文件有改动")
    print("规则命中：", dict(sorted(rw.stats.items(), key=lambda kv: -kv[1])))
    print(f"保护区跳过 {len(rw.protected_hits)} 行")


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--diff":
        _diff_preview(Path(sys.argv[2]))
    else:
        print(__doc__)
