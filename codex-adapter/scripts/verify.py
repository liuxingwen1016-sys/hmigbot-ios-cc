#!/usr/bin/env python3
"""Codex 产物结构校验 —— 转换跑完必查的那几项。

这些检查原本每次转换后靠手敲一段临时脚本完成，同样的代码写了六七遍；固化在这里，
convert.py 跑完自动执行，也可以单独跑：

    python3 verify.py                      # 校验 <repo>/codex
    python3 verify.py --codex-dir <path>   # 校验别处（比如 --output 的试跑产物）

退出码：0 全过；1 有硬失败。预算超支只警告不失败 —— 它是平台约束不是结构错误。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import overlay as ovl  # noqa: E402
import rewrite as rw  # noqa: E402

try:
    import tomllib
except ImportError:                                  # Python < 3.11
    try:
        import tomli as tomllib                      # type: ignore
    except ImportError:
        tomllib = None

# Codex 隐式路由清单的容量。来源是转换器初版记录的「上下文 2% 或 8000 字符」，
# 未经官方文档二次核实 —— 超支只作提示，判断留给人。
IMPLICIT_BUDGET = 8000
SCAN_EXTS = {".md", ".yaml", ".yml", ".json", ".txt", ".toml", ".py", ".sh", ".ets"}
# 相对引用的书写形式：`references/xxx.md` / `templates/xxx.md` / `scripts/xxx.py`
_REL_REF = re.compile(r"`((?:templates|references|scripts)/[\w./-]+\.\w+)`")


def _frontmatter(f: Path) -> dict | None:
    m = re.match(r"^---\s*\n(.*?)\n---", f.read_text(encoding="utf-8"), re.S)
    if not m:
        return None
    try:
        return yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return None


def _is_generated(f: Path, root: Path) -> bool:
    """顶层手写文件（README.md / AGENTS.md / config.toml.sample）不是产物，不该被检查。"""
    rel = f.relative_to(root)
    if f.name == "MIGRATION-REPORT.md":
        return False
    return len(rel.parts) > 1 or f.name == "manifest.yaml"


def _broken_refs(root: Path) -> set[tuple[str, str]]:
    """skill 内相对引用指向的文件是否存在。返回 {(引用所在文件, 引用路径)}。"""
    out = set()
    for f in root.rglob("*.md"):
        skill = f
        while skill.parent != root:
            skill = skill.parent
        for m in _REL_REF.finditer(f.read_text(encoding="utf-8", errors="replace")):
            if not (skill / m.group(1)).exists():
                out.add((str(f.relative_to(root)), m.group(1)))
    return out


# ── 平台能力分歧的产物断言（REWRITE-RULES.md R10）────────────────────────────
# 这几条原本长在下游 migbot-CodeX 的 validate.sh 里 —— 交付时才拦得住。前移到生成侧，
# 坏产物出不了 convert.py 这道门。两处都留是有意的：那边还管着 26 个不经本转换器
# 产出的自有 skill，职责不同，重复是纵深不是冗余。
_PIPELINE_STAGES = ["spec", "plan", "execute", "verify", "retrospect"]
_LOC_STAGES = ["verify", "retrospect"]
_LEGACY_CLI = re.compile(r"\ba2h(?:\.exe)? +(?:metrics|stats) ")
_SLASH_CMD = re.compile(
    r"(?<![A-Za-z0-9_./$-])/(a2h-(?:run|privacy|init|build|spec|plan|execute|verify"
    r"|retrospect|functional-merge|functional-registry)(?:-zh)?)(?![a-z0-9-]|/)")
# skill 引用的书写约定：反引号包裹的 `$name`（R2 规则的产出形态）。
# 限 kebab-case（至少一个连字符、无下划线）—— 产物里 `$value` / `$var` / `$string` /
# `$schema_version` 这类反引号占位符远多于真引用，不筛会淹掉真信号。代价是漏掉无
# 连字符命名的 skill；这只是警告级启发式，宁可漏报不要每轮八行噪音。
_SKILL_REF = re.compile(r"`\$([a-z][a-z0-9]*(?:-[a-z0-9]+)+)`")


def _shell_injection_warnings(skills_dir: Path, source_skills: Path | None) -> list[str]:
    """改写往 .sh 里新塞了反引号或 `$` —— 在 shell 里这两个都是活的。

    md 的排版约定（把工具名/skill 名包进反引号、skill 引用写 `$name`）搬进 shell
    脚本就变成了命令替换和变量展开：`spawn_agent` 会真去执行，`$android-fact-tree`
    会展开成空串（`$android` 未定义）。产物照跑不报错，只是输出悄悄不对。

    警告级：判断哪个 `$` 是有意的（脚本本来就有大量 `$TREE_PATH` 这类）需要人看，
    这里只负责把「改写新引入的」挑出来，不替人决定怎么改。
    """
    if not source_skills or not source_skills.is_dir():
        return []
    out = []
    for f in sorted(skills_dir.rglob("*.sh")):
        src = source_skills / f.relative_to(skills_dir)
        if not src.is_file():
            continue                      # 目录/文件被改名，配不上就不猜
        try:
            a, b = (src.read_text(encoding="utf-8").split("\n"),
                    f.read_text(encoding="utf-8").split("\n"))
        except UnicodeDecodeError:
            continue
        for n, (x, y) in enumerate(zip(a, b), 1):
            if x == y:
                continue
            hazard = [c for c in ("`", "$") if y.count(c) > x.count(c)]
            if hazard:
                out.append(
                    f"shell 活字符注入 {f.relative_to(skills_dir.parent).as_posix()}:{n} "
                    f"（新增 {' '.join(hazard)}）：`{y.strip()[:80]}` "
                    f"—— .sh 里反引号是命令替换、$ 是变量展开，md 的排版约定搬过来会改变行为")
    return out


def _divergence_checks(codex_dir: Path, texts: dict[str, str],
                       external_skills: list[str]) -> tuple[list[str], list[str]]:
    """texts: {相对路径: 内容}，只含本脚本产出的文件。"""
    errors, warnings = [], []
    skills_dir, agents_dir = codex_dir / "skills", codex_dir / "agents"

    # ① CC 专有 CLI / slash command 残留 —— 分歧规则失效的直接症状
    for rel, text in texts.items():
        for n, line in enumerate(text.split("\n"), 1):
            if _LEGACY_CLI.search(line):
                errors.append(f"CC 版 metrics CLI 残留 {rel}:{n} —— Codex 侧是 "
                              f"`a2h-codex`，动词也不同（见 divergence_rules.yaml D1-*）")
            m = _SLASH_CMD.search(line)
            if m:
                errors.append(f"slash command 残留 {rel}:{n} `/{m.group(1)}` —— "
                              f"Codex 无自定义 slash command，应为 `${m.group(1)}`（D2）")

    # ② 五个 pipeline skill 的收尾水位标记必须还在
    # sentinel 是 $a2h-run 判定阶段完成的唯一依据，丢了流水线会卡在该阶段。
    for s in _PIPELINE_STAGES:
        text = texts.get(f"skills/a2h-{s}/SKILL.md")
        if text is None:
            continue          # 该 skill 不在本次产物里（源侧改名/裁剪），不是分歧层的事
        if f"a2h-codex mark-stage a2h-{s}" not in text:
            errors.append(f"skills/a2h-{s}/SKILL.md 丢了收尾的 "
                          f"`a2h-codex mark-stage a2h-{s}` 调用 —— $a2h-run 靠它写的 "
                          f"sentinel 判定阶段完成，缺了整条流水线会卡在这一阶段")

    # ③ verify / retrospect 还要盘库，且 count-lines 必须排在 mark-stage 之前
    for s in _LOC_STAGES:
        text = texts.get(f"skills/a2h-{s}/SKILL.md")
        if text is None:
            continue
        cl = text.find("a2h-codex count-lines")
        ms = text.find(f"a2h-codex mark-stage a2h-{s}")
        if cl < 0:
            errors.append(f"skills/a2h-{s}/SKILL.md 丢了 `a2h-codex count-lines` 盘库调用")
        elif 0 <= ms < cl:
            errors.append(f"skills/a2h-{s}/SKILL.md 把 count-lines 排在了 mark-stage 之后"
                          f" —— 完成状态一落库看板就开始展示这个 app 的行数，行数得先就位")

    # ④ `$xxx` 引用悬空（警告级）
    # a2h-run / a2h-init / a2h-build / a2h-privacy 由 migbot-CodeX 侧独立维护，不经本
    # 转换器产出，本地无从校验 —— 登记在 overlays.yaml 的 external_skills 里放行。
    # 名单外的未知引用报警告：那边改名时这边至少响一声，而不是等交付后才发现悬空。
    known = {d.name for d in skills_dir.iterdir() if d.is_dir()} if skills_dir.is_dir() else set()
    known |= {f.stem for f in agents_dir.glob("*.toml")} if agents_dir.is_dir() else set()
    known |= set(external_skills)
    unknown: dict[str, set[str]] = {}
    for rel, text in texts.items():
        for m in _SKILL_REF.finditer(text):
            if m.group(1) not in known:
                unknown.setdefault(m.group(1), set()).add(rel)
    for name, wheres in sorted(unknown.items()):
        w = sorted(wheres)
        warnings.append(
            f"`${name}` 引用不指向任何产出的 skill/agent，也不在 external_skills 名单里"
            f"（{', '.join(w[:3])}{f' 等 {len(w)} 处' if len(w) > 3 else ''}）"
            f"——若它由 migbot-CodeX 侧维护，补进 overlays.yaml 的 external_skills")
    return errors, warnings


def verify(codex_dir: Path, source_skills: Path | None = None) -> tuple[list[str], list[str]]:
    """返回 (errors, warnings)。"""
    errors: list[str] = []
    warnings: list[str] = []
    skills_dir, agents_dir = codex_dir / "skills", codex_dir / "agents"
    if not skills_dir.is_dir():
        return [f"产物目录不存在或不完整：{codex_dir}"], []

    # ① agent TOML 可解析 —— 改写写进 developer_instructions，裸 ''' 会让 TOML 失效
    tomls = sorted(agents_dir.glob("*.toml"))
    if tomllib is None:
        warnings.append("未安装 tomllib/tomli，跳过 agent TOML 解析校验")
    else:
        for f in tomls:
            try:
                tomllib.loads(f.read_text(encoding="utf-8"))
            except Exception as e:
                errors.append(f"agent TOML 解析失败 {f.name}: {e}")

    # ② SKILL.md frontmatter + ③ 目录名与 name 一致（Codex 按 name 路由，不一致则引用找不到）
    skills = sorted(skills_dir.glob("*/SKILL.md"))
    for f in skills:
        fm = _frontmatter(f)
        if fm is None:
            errors.append(f"frontmatter 缺失或无法解析：{f.parent.name}/SKILL.md")
            continue
        if not fm.get("name") or not fm.get("description"):
            errors.append(f"frontmatter 缺 name/description：{f.parent.name}")
        elif fm["name"] != f.parent.name:
            errors.append(f"目录名与 name 不一致：{f.parent.name} vs name={fm['name']}")

    # ④ openai.yaml 可解析（隐式路由开关写在这里）
    for f in sorted(skills_dir.glob("*/agents/openai.yaml")):
        try:
            yaml.safe_load(f.read_text(encoding="utf-8"))
        except yaml.YAMLError as e:
            errors.append(f"openai.yaml 解析失败 {f.parent.parent.name}: {e}")

    # ⑤ R8 禁用词残留（保护区、生成前言、顶层手写文件都不算）
    # 相对路径一律走 as_posix()：exceptions.yaml 的 protected_paths 与 rewrite_rules.yaml
    # 的 when_path 都是 `skills/xxx/*` 这种正斜杠 glob，Windows 上用 str() 会得到反斜杠、
    # fnmatch 永远匹配不上，保护区与路径条件规则会静默失效。
    texts: dict[str, str] = {}
    exc = rw.load_exceptions()
    for f in sorted(codex_dir.rglob("*")):
        if not f.is_file() or f.suffix not in SCAN_EXTS or not _is_generated(f, codex_dir):
            continue
        rel = f.relative_to(codex_dir).as_posix()
        try:
            text = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        texts[rel] = text
        for kind, lineno, snippet, _ in rw.audit(text, rel, exc):
            if kind.startswith("forbidden:"):
                errors.append(f"R8 残留 {rel}:{lineno} [{kind.split(':')[1]}] {snippet[:70]}")

    # ⑤b 平台能力分歧的产物断言（R10）—— 见 _divergence_checks
    _, external = ovl.load()
    derr, dwarn = _divergence_checks(codex_dir, texts, external)
    errors += derr
    warnings += dwarn

    # ⑤c 改写把 md 排版约定带进了 shell 脚本（警告级）
    warnings += _shell_injection_warnings(skills_dir, source_skills)

    # ⑥ 相对引用不断链 —— 只报**转换新引入**的，源侧本就有的断链不算转换的锅
    baseline = _broken_refs(source_skills) if source_skills and source_skills.is_dir() else set()
    for where, ref in sorted(_broken_refs(skills_dir) - baseline):
        errors.append(f"转换引入断链 {where} → {ref}")

    # ⑦ 隐式路由预算（警告级：平台约束，压缩 description 是产品决策不是结构问题）
    on = []
    for f in skills:
        fm = _frontmatter(f) or {}
        if (fm.get("metadata") or {}).get("type") not in ("domain", "style"):
            on.append((f.parent.name, len(fm.get("description") or ""),
                       (fm.get("metadata") or {}).get("type")))
    total = sum(x[1] for x in on)
    if total > IMPLICIT_BUDGET:
        no_type = [x[0] for x in on if not x[2]]
        warnings.append(
            f"隐式路由 ON {len(on)} 个，description 总长 {total} > 预算 {IMPLICIT_BUDGET}"
            f"（超 {total - IMPLICIT_BUDGET}）。超出部分会被截断，排在后面的 skill 将静默失去"
            f"自动触发能力。" +
            (f"其中 {len(no_type)} 个源侧缺 type 字段而默认 ON："
             f"{', '.join(no_type[:5])}{'…' if len(no_type) > 5 else ''}" if no_type else ""))

    return errors, warnings


def main(argv=None):
    p = argparse.ArgumentParser(description="Codex 产物结构校验")
    p.add_argument("--codex-dir", type=Path, default=None, help="产物目录，缺省 <repo>/codex")
    p.add_argument("--source", type=Path, default=None,
                   help="源 skills 目录，用于断链基线对比，缺省自动识别 arkts-skills 或 migbot")
    args = p.parse_args(argv)

    here = Path(__file__).resolve().parent
    repo = None
    for d in [here, *here.parents]:
        if (d / "arkts-skills" / "skills").is_dir() or (d / "migbot" / "skills").is_dir():
            repo = d
            break
    codex_dir = args.codex_dir or (repo / "codex" if repo else Path("codex"))
    if args.source:
        source = args.source
    elif repo:
        source = (repo / "arkts-skills" / "skills" if (repo / "arkts-skills" / "skills").is_dir()
                  else repo / "migbot" / "skills")
    else:
        source = None

    errors, warnings = verify(codex_dir, source)
    print(format_result(errors, warnings, codex_dir))
    return 1 if errors else 0


def format_result(errors: list[str], warnings: list[str], codex_dir: Path) -> str:
    lines = [f"产物校验：{codex_dir}"]
    if not errors:
        lines.append("  ✓ 结构校验全部通过")
    else:
        lines.append(f"  ✗ {len(errors)} 项失败：")
        lines += [f"      {e}" for e in errors[:20]]
        if len(errors) > 20:
            lines.append(f"      …另有 {len(errors) - 20} 项")
    for w in warnings:
        lines.append(f"  ⚠ {w}")
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
