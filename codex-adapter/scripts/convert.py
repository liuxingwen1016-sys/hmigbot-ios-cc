#!/usr/bin/env python3
"""arkts-skills / arkts-agents → Codex 适配转换脚本（机械层）。

产物布局（写入 <repo>/codex/）：
  codex/skills/<name>/SKILL.md        frontmatter 清洗（保留 name/description，taxonomy 收进 metadata）
  codex/skills/<name>/...             references/scripts/templates/assets 原样拷贝（排除 evals）
  codex/skills/<name>/agents/openai.yaml   domain 型 skill 追加 policy.allow_implicit_invocation: false
  codex/agents/<name>.toml            顶层 agents + skill 内嵌带 frontmatter 的 agent
  codex/manifest.yaml
  codex/MIGRATION-REPORT.md           人工改写清单（Claude 专有语法命中点）

语义层分两段处理：
  - 可确定性表达的部分（术语/路径/调用语法/派发写法/多行调用块）由 rewrite.py 自动改写，
    规则见 rewrite_rules.yaml，会误伤的语境登记在 exceptions.yaml。
  - 需要理解才能改的部分（机制不等价、上下文消歧、description 预算）不动手，
    由 rewrite.audit() 扫出来写进 MIGRATION-REPORT.md 的「待人工/LLM 处理」段。

改写只作用于**源内容**；本脚本自己生成的前言（前置 Skills / 工具边界 / 溯源注释）不过规则，
因此「原 Claude Code 配置 model: opus」这类溯源说明天然免疫。

可重复运行：每次清空 codex/skills 与 codex/agents 后重建；不触碰 codex/ 顶层手写文件
（README.md / AGENTS.md / config.toml.sample）。

用法：
    python3 convert.py                      # 自动定位仓库根，输出到 <repo>/codex/
    python3 convert.py --repo-root <path>   # 显式指定（skill 安装到别处时用）
    python3 convert.py --output <path>      # 输出到别处（试跑，不动现有 codex/）
    python3 convert.py --dry-run            # 只报告差异，不写文件
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import overlay as ovl  # noqa: E402
import rewrite as rw  # noqa: E402
import verify as vf  # noqa: E402

# 路径在 main() 里按 --repo-root / --output 落定；此处仅占位
REPO = SRC_SKILLS = SRC_AGENTS = SRC_COMMANDS = SRC_HOOKS = SRC_BIN = None
DST = DST_SKILLS = DST_AGENTS = DST_COMMANDS = None

# 转换器自身正常放在仓库根 codex-adapter/，本就不在扫描范围内；此处是防御性兜底
# —— 万一被挪进 arkts-skills/skills/，它正文里的 `Claude Code` / `.claude/` / `Skill({`
# 是待转换术语的**样本**，过一遍规则会把规则表改成「Codex → Codex」这种废话。
SKIP_SKILLS = {"codex-adapter"}


def source_dirs(repo: Path) -> tuple[Path, Path, Path | None]:
    """返回仓库的 skills、agents、commands 源目录。

    适配器原始输入是 `arkts-skills/` + `arkts-agents/`。hmigbot-ios 保留
    Claude 插件源在 `migbot/` 下，因此这里同时支持两种布局，产物规则不变。
    """
    layouts = (
        (repo / "arkts-skills" / "skills", repo / "arkts-agents" / "agents", None),
        (repo / "migbot" / "skills", repo / "migbot" / "agents", repo / "migbot" / "commands"),
    )
    for skills, agents, commands in layouts:
        if skills.is_dir() and agents.is_dir():
            return skills, agents, commands if commands and commands.is_dir() else None
    raise SystemExit(
        "定位不到源目录（需要 arkts-skills/skills + arkts-agents/agents，"
        "或 migbot/skills + migbot/agents）。请用 --repo-root 显式指定。")


def find_repo_root(start: Path) -> Path:
    for d in [start, *start.parents]:
        try:
            source_dirs(d)
            return d
        except SystemExit:
            continue
    raise SystemExit(
        "定位不到仓库根（需要 arkts-skills/skills + arkts-agents/agents，"
        "或 migbot/skills + migbot/agents）。请用 --repo-root 显式指定。")

# frontmatter 中的 taxonomy / 自定义字段 → 收进 metadata:
META_KEYS = ["type", "domain", "tags", "version", "title", "references", "depends_on"]
# Claude Code 专有字段 → 丢弃并登记人工处理
CLAUDE_ONLY_KEYS = ["allowed-tools", "argument-hint", "model", "context", "agent", "hooks"]

# 隐式路由分类：domain 型为内部 skill（仅供 pipeline/agent 显式调用）
IMPLICIT_OFF_TYPES = {"domain", "style"}

# 产物内 Claude 专有语法扫描（登记人工改写清单）
SCAN_PATTERNS = [
    ("skill-call", re.compile(r"Skill\s*\(\s*\{|Skill\s*\(\s*skill")),
    ("agent-dispatch", re.compile(r"subagent_type|Agent\s*\(|Task\s*\(\s*[\"'{]|Task 工具|Agent 工具")),
    ("claude-md", re.compile(r"CLAUDE\.md")),
    ("claude-brand", re.compile(r"[Cc]laude[- ][Cc]ode|\bClaude\b")),
    ("dot-claude-path", re.compile(r"\.claude/")),
    ("arguments-var", re.compile(r"\$ARGUMENTS")),
    ("frontmatter-claude", re.compile(r"allowed-tools|argument-hint")),
]
SCAN_EXTS = {".md", ".yaml", ".yml", ".json", ".txt", ".toml", ".py", ".sh", ".ets"}

report = {
    "skills": [],          # (name, type, implicit, notes[])
    "agents": [],          # (toml_name, source, notes[])
    "moved": [],           # (src, dst)
    "dropped_fields": [],  # (file, key, value-snippet)
    "hits": [],            # (relpath, lineno, tag, line-snippet)
    "audit": [],           # (relpath, kind, lineno, snippet, why)  改写后仍需人工/LLM 的
    "warnings": [],
    "overlay": None,       # overlay.Result —— 平台分歧结构性补丁（R10）
}

# 语义层改写引擎（main() 里先扫出 agent 名再实例化 —— 块变换要靠它回填派发目标）
REWRITER: rw.Rewriter | None = None
# 过改写规则的文本类型；其余（图片等）原样拷贝
REWRITE_EXTS = {".md", ".yaml", ".yml", ".toml", ".py", ".sh", ".ets", ".txt", ".json"}


def rewrite_text(text: str, relpath: str) -> str:
    """对源内容套用语义层改写。relpath 相对 codex/，供保护区匹配。"""
    return REWRITER.rewrite(text, relpath) if REWRITER else text


def copy_tree_rewritten(src: Path, dst: Path, rel_prefix: str):
    """拷贝目录，文本文件过改写规则，其余原样；文件名按 path_renames.yaml 转换。"""
    for item in sorted(src.rglob("*")):
        relative = item.relative_to(src)
        if item.is_dir():
            # The Claude plugin bundles large platform runtimes under
            # scripts/bin. Keep one copy in migbot and link the Codex view to
            # it, so regeneration does not double the repository's binary
            # payload while preserving the normal script entry points.
            if item.name == "bin" and item.parent.name == "scripts":
                target = dst / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.symlink_to(
                    Path(os.path.relpath(item, target.parent)), target_is_directory=True)
            continue
        # pathlib.rglob may enumerate the contents of the symlink created
        # above. Do not copy those files a second time.
        parts = relative.parts
        if (src.name == "scripts" and parts and parts[0] == "bin") or \
                any(parts[i:i + 2] == ("scripts", "bin") for i in range(len(parts) - 1)):
            continue
        new_name = REWRITER.rename(item.name) if REWRITER else item.name
        target = dst / relative.parent / new_name
        target.parent.mkdir(parents=True, exist_ok=True)
        rel = f"{rel_prefix}/{relative.parent / new_name}".replace("/./", "/")
        rewrite_file = item.suffix in REWRITE_EXTS or (
            src.name == "bin" and item.suffix == ""
        )
        if rewrite_file:
            try:
                target.write_text(rewrite_text(item.read_text(encoding="utf-8"), rel),
                                  encoding="utf-8")
                continue
            except UnicodeDecodeError:
                pass  # 当二进制处理
        shutil.copy2(item, target)


def parse_frontmatter(text: str):
    """返回 (fm_dict, body)。无 frontmatter 时 fm 为 None。"""
    if not text.startswith("---"):
        return None, text
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?", text, re.S)
    if not m:
        return None, text
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        fm = fallback_parse(m.group(1))
        if fm is None:
            report["warnings"].append("frontmatter 解析失败且降级解析无效")
            return None, text
    return fm, text[m.end():]


def fallback_parse(raw: str):
    """YAML 失败时的降级解析：按顶级 key 切段，值统一按纯文本处理（应对 description 内裸冒号）。"""
    fm, key, buf = {}, None, []
    for line in raw.splitlines():
        m = re.match(r"^([A-Za-z_-]+):\s*(.*)$", line)
        if m and not line.startswith((" ", "\t")):
            if key:
                fm[key] = "\n".join(buf).strip()
            key, first = m.group(1), m.group(2).strip()
            buf = [first] if first not in (">", ">-", "|", "|-") else []
        elif key is not None:
            buf.append(line.strip())
    if key:
        fm[key] = "\n".join(buf).strip()
    if not fm.get("name"):
        return None
    if "tags" in fm and isinstance(fm["tags"], str) and fm["tags"].startswith("["):
        fm["tags"] = [t.strip() for t in fm["tags"].strip("[]").split(",") if t.strip()]
    report["warnings"].append(f"frontmatter 经降级解析（值按纯文本处理）: name={fm.get('name')}")
    return fm


def dump_yaml(data) -> str:
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=10000)


def sanitize_agent_name(name: str) -> str:
    name = name.strip().lower()
    name = re.sub(r"\s*\(([^)]+)\)", r"-\1", name)  # "spec-fixer (ut)" → "spec-fixer-ut"
    name = re.sub(r"[^a-z0-9_-]+", "-", name).strip("-")
    return name


def toml_multiline(text: str) -> str:
    """优先 TOML 字面多行字符串（无转义），含 ''' 时退回 basic 字符串转义。"""
    text = text.strip("\n")
    if "'''" not in text:
        return "'''\n" + text + "\n'''"
    esc = text.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')
    return '"""\n' + esc + '\n"""'


def toml_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").strip() + '"'


def normalize_list(v):
    """frontmatter 的 tools/skills 可能是逗号串或 yaml 列表。"""
    if v is None:
        return []
    if isinstance(v, str):
        return [x.strip() for x in v.split(",") if x.strip()]
    return [str(x).strip() for x in v]


def agent_md_to_toml(fm: dict, body: str, source: str) -> tuple[str, str]:
    """由 agent frontmatter + body 生成 Codex custom agent TOML。返回 (toml_name, toml_text)。"""
    raw_name = fm.get("name") or Path(source).stem
    name = sanitize_agent_name(raw_name)
    desc = (fm.get("description") or "").strip()
    skills = normalize_list(fm.get("skills"))
    tools = normalize_list(fm.get("tools"))
    notes = []

    preamble = []
    if skills:
        preamble.append(
            "## 前置 Skills（原 Claude Code spawn 时预加载，Codex 下改为执行前显式加载）\n"
            "开始任务前，先读取并遵循以下 skill（位于本仓库安装的 skills 目录，"
            "如 `<project>/.agents/skills/<name>/SKILL.md`）：\n"
            + "\n".join(f"- ${s}" for s in skills)
        )
    if tools:
        preamble.append(
            "## 工具边界（原 Claude Code 工具白名单，作为行为约束遵守，非硬性权限）\n"
            "允许的操作类型：" + ", ".join(tools) + "。\n"
            "对照 Codex：文件读取/搜索/shell 用 shell 工具，文件修改用 apply_patch；"
            "白名单之外的操作（如未列出 Edit/Write 则不得改动文件）必须遵守。"
        )

    # 改写只作用于源 body 与 description；preamble 是本脚本生成的溯源说明，过规则会变成假信息
    rel_toml = f"agents/{name}.toml"
    body = rewrite_text(body.strip(), rel_toml)
    desc = rewrite_text(desc, rel_toml)
    dev_instructions = ("\n\n".join(preamble) + "\n\n---\n\n" if preamble else "") + body

    lines = [f"name = {toml_str(name)}"]
    if raw_name != name:
        lines.append(f"# 原名: {raw_name}")
    lines.append(f"description = {toml_str(desc)}")
    if fm.get("model"):
        lines.append(f"# 原 Claude Code 配置 model: {fm['model']}（Codex 无 Claude 模型 pin，继承会话模型）")
        notes.append(f"model: {fm['model']} → 注释保留")
    if fm.get("color"):
        notes.append(f"color: {fm['color']} → 丢弃")
    lines.append("")
    lines.append("developer_instructions = " + toml_multiline(dev_instructions))
    lines.append("")
    if skills:
        notes.append(f"skills 预加载({len(skills)}) → developer_instructions 指引")
    if tools:
        notes.append(f"tools 白名单 → developer_instructions 行为约束")
    report["agents"].append((name, source, notes))
    return name, "\n".join(lines)


# Claude Code 工具名 → Codex 下的通用操作表述（REWRITE-RULES.md R4）
_TOOL_PROSE = {
    "Agent": "子代理派发", "Task": "子代理派发", "Read": "读取文件", "Write": "写文件",
    "Edit": "编辑文件", "Glob": "通配搜索", "Grep": "内容检索", "Bash": "执行 shell",
    "WebFetch": "抓取网页", "WebSearch": "联网搜索",
}


def inject_dropped_frontmatter(body: str, fm: dict) -> str:
    """R6：argument-hint / allowed-tools 在 Codex 无对应 frontmatter，转成 body 指引。

    这两个字段的值转换器手上就有，节的措辞也是固定的 —— 不必留给人重写。
    插到第一个 H1 之后（紧跟标题，先于正文流程）。
    """
    hint, tools = fm.get("argument-hint"), fm.get("allowed-tools")
    if not hint and not tools:
        return body

    sec = ["## 调用参数与工具边界（原 Claude Code frontmatter 迁移）", "",
           "> 下列参数格式与操作边界由已移除的 frontmatter 字段迁移而来，"
           "在此以 body 指引形式保留、作为行为约束遵守。", ""]
    if hint:
        sec += [f"- **参数格式**：`{hint}`",
                "  - 参数按位置从调用方提示词中获取"
                "（Codex 无 slash-command 参数注入，调用时在提示词中依序给出）"]
    if tools:
        names = normalize_list(tools)
        sec.append("- **允许的操作类型**（作为行为约束遵守、非硬性权限）："
                   + "、".join(_TOOL_PROSE.get(t, t) for t in names) + "。")
    sec.append("")

    lines = body.split("\n")
    h1 = next((i for i, l in enumerate(lines) if l.startswith("# ")), None)
    at = h1 + 1 if h1 is not None else 0
    while at < len(lines) and not lines[at].strip():   # 跳过标题后的空行
        at += 1
    return "\n".join(lines[:at] + sec + lines[at:])


def convert_skill(src_dir: Path):
    skill_md = src_dir / "SKILL.md"
    text = skill_md.read_text(encoding="utf-8")
    fm, body = parse_frontmatter(text)
    if fm is None:
        report["warnings"].append(f"{src_dir.name}: SKILL.md 无有效 frontmatter，原样拷贝")
        fm, body = {}, text

    name = fm.get("name", src_dir.name)
    desc = fm.get("description", "")
    stype = fm.get("type")
    implicit = stype not in IMPLICIT_OFF_TYPES

    new_fm = {"name": name, "description": desc}
    metadata = {k: fm[k] for k in META_KEYS if k in fm}
    if metadata:
        new_fm["metadata"] = metadata
    notes = []
    for k in list(fm.keys()):
        if k in ("name", "description") or k in META_KEYS:
            continue
        snippet = str(fm[k])[:80]
        report["dropped_fields"].append((f"skills/{src_dir.name}/SKILL.md", k, snippet))
        notes.append(f"frontmatter 字段 `{k}` 已移除，需人工转为 body 指引")

    # 目录名对齐 frontmatter 的 name：Codex 按 name 路由，目录与 name 不一致会导致
    # 正文里的 `$name` 引用找不到对应目录（源侧 hmos_fix_build_errors/ 的 name 就是
    # hmos-fix-build-errors）。name 缺失时退回源目录名。
    dst_dir = DST_SKILLS / name
    if name != src_dir.name:
        report["moved"].append((f"skills/{src_dir.name}/", f"skills/{name}/（目录名对齐 frontmatter name）"))
    dst_dir.mkdir(parents=True, exist_ok=True)

    # 拷贝除 SKILL.md / evals / agents 外的内容（文本过语义层改写）
    rel_prefix = f"skills/{name}"
    for item in sorted(src_dir.iterdir()):
        if item.name in ("SKILL.md", "evals.json", "evals"):
            continue
        if item.name == "agents" and item.is_dir():
            continue  # 单独处理
        if item.is_dir():
            copy_tree_rewritten(item, dst_dir / item.name, f"{rel_prefix}/{item.name}")
            continue
        new_name = REWRITER.rename(item.name) if REWRITER else item.name
        if item.suffix in REWRITE_EXTS:
            (dst_dir / new_name).write_text(
                rewrite_text(item.read_text(encoding="utf-8"), f"{rel_prefix}/{new_name}"),
                encoding="utf-8")
        else:
            shutil.copy2(item, dst_dir / new_name)

    # 内嵌 agents/：openai.yaml 原位保留；*.md 迁到 references/agent-prompts/；带 frontmatter 的另出顶层 TOML
    src_agents = src_dir / "agents"
    if src_agents.is_dir():
        for f in sorted(src_agents.iterdir()):
            if f.name == "openai.yaml":
                (dst_dir / "agents").mkdir(exist_ok=True)
                shutil.copy2(f, dst_dir / "agents" / f.name)
                continue
            if f.suffix != ".md":
                report["warnings"].append(f"{src_dir.name}/agents/{f.name}: 未识别类型，跳过")
                continue
            rel_dst = dst_dir / "references" / "agent-prompts" / f.name
            rel_dst.parent.mkdir(parents=True, exist_ok=True)
            rel_name = f"{rel_prefix}/references/agent-prompts/{f.name}"
            content = f.read_text(encoding="utf-8")
            afm, abody = parse_frontmatter(content)
            if afm and afm.get("name"):
                tname, ttext = agent_md_to_toml(afm, abody, f"skills/{src_dir.name}/agents/{f.name}")
                (DST_AGENTS / f"{tname}.toml").write_text(ttext, encoding="utf-8")
                # prompt 模板位置保留 body（去 frontmatter），派发方仍可整文引用
                rel_dst.write_text(rewrite_text(abody.lstrip("\n"), rel_name), encoding="utf-8")
                notes.append(f"内嵌 agent {f.name} → codex/agents/{tname}.toml + references/agent-prompts/")
            else:
                rel_dst.write_text(rewrite_text(content, rel_name), encoding="utf-8")
                notes.append(f"内嵌 prompt 模板 {f.name} → references/agent-prompts/")
            report["moved"].append((f"skills/{src_dir.name}/agents/{f.name}", str(rel_dst.relative_to(DST))))

    # domain 型：openai.yaml 关闭隐式路由
    if not implicit:
        oy_path = dst_dir / "agents" / "openai.yaml"
        oy = {}
        if oy_path.exists():
            oy = yaml.safe_load(oy_path.read_text(encoding="utf-8")) or {}
        oy.setdefault("policy", {})["allow_implicit_invocation"] = False
        oy_path.parent.mkdir(exist_ok=True)
        oy_path.write_text(dump_yaml(oy), encoding="utf-8")

    body = rewrite_text(body, f"{rel_prefix}/SKILL.md")
    body = inject_dropped_frontmatter(body, fm)
    (dst_dir / "SKILL.md").write_text("---\n" + dump_yaml(new_fm) + "---\n" + body, encoding="utf-8")
    report["skills"].append((name, stype or "(无)", implicit, notes, len(str(desc))))


def convert_command(src_file: Path):
    """把 Claude command 文档作为同名 Codex skill 入口生成。

    Codex 没有自定义 slash command。保留命令正文并套用同一套 frontmatter、
    语义改写和参数边界迁移，用户可通过 `$i2h-*` 显式调用这些入口。
    """
    text = src_file.read_text(encoding="utf-8")
    fm, body = parse_frontmatter(text)
    if fm is None:
        report["warnings"].append(f"commands/{src_file.name}: 无有效 frontmatter，跳过")
        return
    name = src_file.stem
    desc = str(fm.get("description") or f"由 {name} 命令迁移的 Codex 入口").strip()
    dst_dir = DST_SKILLS / name
    dst_dir.mkdir(parents=True, exist_ok=True)
    body = rewrite_text(body, f"skills/{name}/SKILL.md")
    body = inject_dropped_frontmatter(body, fm)
    new_fm = {"name": name, "description": desc}
    (dst_dir / "SKILL.md").write_text(
        "---\n" + dump_yaml(new_fm) + "---\n" + body, encoding="utf-8")
    if DST_COMMANDS is not None:
        DST_COMMANDS.mkdir(parents=True, exist_ok=True)
        (DST_COMMANDS / src_file.name).write_text(
            "---\n" + dump_yaml(new_fm) + "---\n" + body,
            encoding="utf-8")
    notes = ["Claude command → Codex skill 入口"]
    for key in fm:
        if key not in ("description", "name"):
            report["dropped_fields"].append((f"commands/{src_file.name}", key, str(fm[key])[:80]))
    report["skills"].append((name, "command", True, notes, len(desc)))


def _is_generated(f: Path) -> bool:
    """该文件是否由本脚本产出 —— 只有产出物才该被自检。

    codex/ 顶层的 README.md / AGENTS.md / config.toml.sample 是手写的，本脚本明确
    不碰；它们正文里的「Claude Code」是有意的平台对照说明（如「与 Claude Code 版本
    的差异」对照表），当成残留报出来是假阳性，会淹没真问题。
    """
    rel = f.relative_to(DST)
    if f.name == "MIGRATION-REPORT.md":
        return False
    return len(rel.parts) > 1 or f.name == "manifest.yaml"


def scan_outputs():
    for f in sorted(DST.rglob("*")):
        if not f.is_file() or f.suffix not in SCAN_EXTS:
            continue
        if not _is_generated(f):
            continue
        rel = f.relative_to(DST).as_posix()
        try:
            lines = f.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for i, line in enumerate(lines, 1):
            for tag, pat in SCAN_PATTERNS:
                if pat.search(line):
                    report["hits"].append((rel, i, tag, line.strip()[:160]))
                    break  # 每行只记一次


def audit_outputs():
    """改写跑完后的自检：R8 禁用词残留 + 已知需人理解的语境，填 report["audit"]。"""
    for f in sorted(DST.rglob("*")):
        if not f.is_file() or f.suffix not in SCAN_EXTS or not _is_generated(f):
            continue
        rel = f.relative_to(DST).as_posix()
        try:
            text = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        exc = REWRITER.exc if REWRITER else None
        known = REWRITER.known_agents if REWRITER else None
        for kind, lineno, snippet, why in rw.audit(text, rel, exc, known):
            report["audit"].append((rel, kind, lineno, snippet, why))


def write_report(verify_errors=None, verify_warnings=None):
    L = ["# Codex 迁移报告（机械层转换产物）", "",
         "由 `codex-adapter/scripts/convert.py`（`$codex-adapter` skill）生成。"
         "机械层 + 可确定性语义改写已自动完成；仍需理解才能改的列在「待人工 / LLM 处理」段。", ""]

    L.append("## Skills（{} 个）".format(len(report["skills"])))
    L.append("")
    L.append("| skill | type | 隐式路由 | desc 长度 | 备注 |")
    L.append("|---|---|---|---|---|")
    for name, stype, implicit, notes, dlen in sorted(report["skills"]):
        L.append(f"| {name} | {stype} | {'ON' if implicit else 'off'} | {dlen} | {'; '.join(notes)} |")
    on = [x for x in report["skills"] if x[2]]
    budget = sum(x[4] for x in on)
    L += ["", f"隐式路由 ON 共 {len(on)} 个，description 总长约 {budget} 字符（Codex 预算：上下文 2% 或 8000 字符）。", ""]

    L.append(f"## Agents（{len(report['agents'])} 个 TOML）")
    L.append("")
    L.append("| agent | 来源 | 处理 |")
    L.append("|---|---|---|")
    for name, source, notes in sorted(report["agents"]):
        L.append(f"| {name} | {source} | {'; '.join(notes)} |")
    L.append("")

    if report["dropped_fields"]:
        L.append("## 丢弃的 frontmatter 字段（需人工转 body 指引）")
        L.append("")
        for f, k, v in report["dropped_fields"]:
            L.append(f"- `{f}` → `{k}`: {v}")
        L.append("")

    if report["moved"]:
        L.append("## 位置迁移（skill 内嵌 agents）")
        L.append("")
        for s, d in report["moved"]:
            L.append(f"- `{s}` → `{d}`")
        L.append("")

    # ── 语义层改写统计（rewrite.py 自动完成的部分）──────────────────────────
    if REWRITER:
        L.append("## 语义层自动改写（rewrite.py）")
        L.append("")
        L.append("族：`rewrite` = 形态翻译（措辞/路径/调用语法）；"
                 "`divergence` = 平台能力分歧（两边工具或流程真的不同，见 R10）。")
        L.append("")
        L.append("| 规则 | 族 | 命中次数 |")
        L.append("|---|---|---|")
        for rid, n in sorted(REWRITER.stats.items(), key=lambda kv: -kv[1]):
            L.append(f"| {rid} | {REWRITER.family_of(rid)} | {n} |")
        L.append("")
        L.append(f"保护区跳过 {len(REWRITER.protected_hits)} 行"
                 f"（规则会误伤的语境，登记在 `exceptions.yaml`）。")
        if REWRITER.protected_hits:
            L.append("")
            for rel, n, snippet in REWRITER.protected_hits[:40]:
                L.append(f"- `{rel}` L{n}: `{snippet}`")
            if len(REWRITER.protected_hits) > 40:
                L.append(f"- …另有 {len(REWRITER.protected_hits) - 40} 行")
        L.append("")

    # ── 平台分歧的结构性补丁（overlay.py）────────────────────────────────────
    ores = report["overlay"]
    if ores is not None:
        L.append("## 平台能力分歧补丁（overlay.py）")
        L.append("")
        L.append("行规则做不了的那部分分歧：删整行 / 换整节 / 插 banner。"
                 "登记在 `codex-adapter/scripts/overlays.yaml`，正文在 `codex-adapter/overlays/`。")
        L.append("")
        L.append("| overlay | 目标 | 命中 | 被覆盖内容 digest |")
        L.append("|---|---|---|---|")
        dmap = {(i, p): d for i, p, d in ores.digests}
        for oid, rel, hits in ores.applied:
            L.append(f"| {oid} | `{rel}` | {hits} | {dmap.get((oid, rel), '—')} |")
        L.append("")
        if ores.errors:
            L.append(f"✗ {len(ores.errors)} 条锚点失配（**硬失败**）：")
            L += [f"- {e}" for e in ores.errors]
            L.append("")
        for w in ores.warnings:
            L.append(f"> ⚠ {w}")
            L.append("")

    # ── 改写后仍需人工/LLM 的 ────────────────────────────────────────────────
    # ── 产物结构校验（verify.py）────────────────────────────────────────────
    L.append("## 产物结构校验")
    L.append("")
    if verify_errors is None:
        L.append("未执行。")
    elif not verify_errors:
        L.append("✓ 全部通过：agent TOML 可解析、SKILL.md frontmatter 完整、"
                 "目录名与 name 一致、openai.yaml 可解析、R8 禁用词残留 0、转换未引入断链。")
    else:
        L.append(f"✗ {len(verify_errors)} 项失败：")
        L += [f"- {e}" for e in verify_errors[:30]]
        if len(verify_errors) > 30:
            L.append(f"- …另有 {len(verify_errors) - 30} 项")
    for w in (verify_warnings or []):
        L.append("")
        L.append(f"> ⚠ {w}")
    L.append("")

    L.append("## 待人工 / LLM 处理（机械层处理不了）")
    L.append("")
    if not report["audit"]:
        L.append("无。")
        L.append("")
    else:
        by_kind = {}
        for rel, kind, i, snippet, why in report["audit"]:
            by_kind.setdefault(kind, []).append((rel, i, snippet, why))
        L.append(f"共 {len(report['audit'])} 项，分 {len(by_kind)} 类。")
        L.append("")
        for kind in sorted(by_kind):
            items = by_kind[kind]
            L.append(f"### {kind}（{len(items)}）")
            L.append(f"> {items[0][3]}")
            L.append("")
            for rel, i, snippet, _ in items[:25]:
                L.append(f"- `{rel}` L{i}: `{snippet}`")
            if len(items) > 25:
                L.append(f"- …另有 {len(items) - 25} 项")
            L.append("")

    L.append("## 机械扫描全景（宽口径，含已自动改写的）")
    L.append("")
    by_file = {}
    for rel, i, tag, snippet in report["hits"]:
        by_file.setdefault(rel, []).append((i, tag, snippet))
    L.append(f"共 {len(report['hits'])} 处命中，涉及 {len(by_file)} 个文件。")
    L.append("")
    for rel in sorted(by_file):
        L.append(f"### {rel}")
        for i, tag, snippet in by_file[rel]:
            L.append(f"- L{i} [{tag}] `{snippet}`")
        L.append("")

    if report["warnings"]:
        L.append("## Warnings")
        L.append("")
        for w in report["warnings"]:
            L.append(f"- {w}")
        L.append("")

    (DST / "MIGRATION-REPORT.md").write_text("\n".join(L), encoding="utf-8")


def write_manifest():
    manifest = {
        "collection": "hmigbot-ios-codex",
        "description": "iOS → HarmonyOS migration skills, agents, commands and runtime assets for Codex",
        "platform": "codex",
        "maintainer": "liuxingwen1016-sys",
        "version": "1.0.0",
        "skills_dir": "skills/",
        "agents_dir": "agents/",
        "commands_dir": "commands/",
        "hooks_dir": "hooks/",
        "generated_by": "codex-adapter/scripts/convert.py",
    }
    (DST / "manifest.yaml").write_text(dump_yaml(manifest), encoding="utf-8")


def collect_agent_names() -> set[str]:
    """先扫一遍所有 agent 名。

    块变换要靠它回填派发目标：agent-prompts/*.md 里的 `Agent(` 块不写 subagent_type，
    目标只出现在节标题的括号里（`# §5. …（a2h-migration-worker）`），得先知道有哪些合法名。
    """
    names = set()
    for f in list(SRC_AGENTS.glob("*.md")) + list(SRC_SKILLS.glob("*/agents/*.md")):
        try:
            fm, _ = parse_frontmatter(f.read_text(encoding="utf-8"))
        except UnicodeDecodeError:
            continue
        if fm and fm.get("name"):
            names.add(sanitize_agent_name(fm["name"]))
    return names


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="arkts-skills / arkts-agents → Codex 适配转换（机械层 + 可确定性语义改写）")
    p.add_argument("--repo-root", type=Path, default=None,
                   help="仓库根（含 arkts-skills/ 与 arkts-agents/）。缺省向上自动定位")
    p.add_argument("--output", type=Path, default=None,
                   help="产物目录，缺省 <repo-root>/codex。试跑时指向别处即可不动现有产物")
    p.add_argument("--dry-run", action="store_true",
                   help="不写文件，只报告将产生的改写与待人工项")
    return p.parse_args(argv)


def main(argv=None):
    global REWRITER, REPO, SRC_SKILLS, SRC_AGENTS, SRC_COMMANDS, SRC_HOOKS, SRC_BIN
    global DST, DST_SKILLS, DST_AGENTS, DST_COMMANDS
    args = parse_args(argv)

    REPO = (args.repo_root or find_repo_root(Path(__file__).resolve().parent)).resolve()
    SRC_SKILLS, SRC_AGENTS, SRC_COMMANDS = source_dirs(REPO)
    SRC_HOOKS = REPO / "migbot" / "hooks"
    SRC_BIN = REPO / "migbot" / "bin"

    # dry-run 产物放仓库根的隐藏目录，不放 skill 内 —— 放在 skill 里会被 skill-checker
    # 等扫描工具当成本 skill 的脚本，把 72 个 skill 的内容全算进本 skill 的质量报告。
    if args.dry_run:
        DST = REPO / ".codex-dry-run"
    else:
        DST = (args.output or REPO / "codex").resolve()
    DST_SKILLS, DST_AGENTS = DST / "skills", DST / "agents"
    DST_COMMANDS = DST / "commands"

    print(f"源: {SRC_SKILLS.parent}\n产物: {DST}" + ("（dry-run，不动 codex/）" if args.dry_run else ""))
    for d in (DST_SKILLS, DST_AGENTS, DST_COMMANDS, DST / "hooks", DST / "bin"):
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)

    REWRITER = rw.Rewriter(known_agents=collect_agent_names())

    for src_dir in sorted(SRC_SKILLS.iterdir()):
        if src_dir.name in SKIP_SKILLS:
            report["warnings"].append(f"{src_dir.name}: 构建工具自身，按 SKIP_SKILLS 跳过")
            continue
        if src_dir.is_dir() and (src_dir / "SKILL.md").exists():
            convert_skill(src_dir)

    if SRC_COMMANDS:
        for src_file in sorted(SRC_COMMANDS.glob("*.md")):
            convert_command(src_file)

    # Lifecycle hooks and the portable i2h runtime are kept as Codex-side assets.
    # Hook commands use CODEX_PLUGIN_ROOT after the normal rewrite pass.
    if SRC_HOOKS.is_dir():
        copy_tree_rewritten(SRC_HOOKS, DST / "hooks", "hooks")
    if SRC_BIN.is_dir():
        copy_tree_rewritten(SRC_BIN, DST / "bin", "bin")

    for f in sorted(SRC_AGENTS.glob("*.md")):
        fm, body = parse_frontmatter(f.read_text(encoding="utf-8"))
        if fm is None:
            report["warnings"].append(f"agents/{f.name}: 无 frontmatter，跳过")
            continue
        tname, ttext = agent_md_to_toml(
            fm, body, f"{SRC_AGENTS.parent.name}/agents/{f.name}")
        (DST_AGENTS / f"{tname}.toml").write_text(ttext, encoding="utf-8")

    # 平台能力分歧的结构性补丁（R10）：删整行 / 换整节 / 插 banner，行规则做不了的那部分。
    # 排在这里 —— skills 与 agents 都已落盘（banner 要用实际产出的 agent 名单），
    # 且早于 scan/audit/verify（自检必须看到最终产物）。
    report["overlay"] = ovl.apply_all(
        DST, ctx={"agent_names": {name for name, _, _ in report["agents"]}})

    write_manifest()
    scan_outputs()
    audit_outputs()

    # 规则静默失效检测：标了 expect: required 却 0 命中 = 源侧措辞已变，转换悄悄少做一件事
    stale = REWRITER.stale_rules() if REWRITER else []
    for rid in stale:
        fam = REWRITER.family_of(rid)
        where = "divergence_rules.yaml" if fam == "divergence" else "rewrite_rules.yaml"
        report["warnings"].append(
            f"[{fam}] 规则 `{rid}` 标记为 expect: required 但本次 0 命中 —— "
            f"源侧对应写法可能已改，规则已失效，请核对 {where}")

    # 产物结构校验（原先每次都靠手敲临时脚本，现在固化在 verify.py）
    errors, warns = vf.verify(DST, SRC_SKILLS)
    # overlay 的锚点失配是硬失败：定位不到该打补丁的地方，产物里就留着 CC 版的命令
    ores = report["overlay"]
    if ores:
        errors = ores.errors + errors
        warns = warns + ores.warnings
    write_report(verify_errors=errors, verify_warnings=warns)

    rewritten = sum(REWRITER.stats.values()) if REWRITER else 0
    div = (sum(n for rid, n in REWRITER.stats.items()
               if REWRITER.family_of(rid) == "divergence") if REWRITER else 0)
    print(f"skills: {len(report['skills'])}, agents(toml): {len(report['agents'])}\n"
          f"语义层自动改写: {rewritten} 处（其中平台分歧 {div} 处），保护区跳过: "
          f"{len(REWRITER.protected_hits) if REWRITER else 0} 行\n"
          f"分歧补丁(overlay): {len(ores.applied) if ores else 0} 处应用\n"
          f"待人工/LLM: {len(report['audit'])} 项，warnings: {len(report['warnings'])}")
    print(vf.format_result(errors, warns, DST))
    for rid in stale:
        print(f"  ⚠ 规则 `{rid}` 标了 required 却 0 命中 —— 源侧写法可能已变，规则失效了")
    if report["audit"]:
        print(f"→ 待人工项逐条见 {DST / 'MIGRATION-REPORT.md'}")
    if args.dry_run:
        print("（dry-run：产物留在上述目录供比对，未触碰 codex/；下次 dry-run 会清空重建）")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
