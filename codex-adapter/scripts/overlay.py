#!/usr/bin/env python3
"""Codex 适配 —— 平台能力分歧的结构性补丁层（L2，REWRITE-RULES.md R10）。

行规则（rewrite_rules.yaml / divergence_rules.yaml）改不了三件事：删整行、
换整节、往 frontmatter 后插内容。这三件都源于「CC 与 Codex 的能力真的不一样」
——不是措辞差异是流程差异，逐条登记在 overlays.yaml。

跑在**行改写之后**：锚点只需匹配已归一化的那一种形态，不必兼容源侧原文
（比如 §10 里的 `.claude/` 到这一步已经是 `.agents/` 了）。

两道防线，各管一种失效：
  anchor + expect  定位失败 → 硬失败，convert.py 退出码 1
  source_digest    定位成功但被覆盖的原文变了 → 警告

必须硬失败的理由：上游一旦重构被补丁的那一节，锚点失配后若只是跳过，产物里
就留着 CC 版的 `a2h metrics report-stage`，转换「悄悄少做一件事」，而下游
migbot-CodeX 的 validate.sh 要到交付时才拦得住。那边的守卫注释写得很清楚：
这种静默漂移已经真的发生过一次。

新增条目时怎么拿 source_digest：留空跑一次 `convert.py --dry-run`，值在
`MIGRATION-REPORT.md`「平台能力分歧补丁」表的最后一列，抄回 overlays.yaml 即可。
**不要**拿本模块对着已打过补丁的产物再算一遍 —— 那量到的是替换**之后**的内容，
填回去等于把漂移告警永久关掉。
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
ADAPTER = HERE.parent                      # codex-adapter/

_FENCE = re.compile(r"^\s*```")
# 节边界：同级或更高级标题，或水平线。`### 10a.` 是子节不算边界（故限 1~2 个 #）。
_SECTION_END = re.compile(r"^(?:---[ \t]*$|#{1,2} )")
_FRONTMATTER = re.compile(r"^---\s*\n.*?\n---[ \t]*\n", re.S)


@dataclass
class Overlay:
    id: str
    paths: list[str]
    op: str
    why: str = ""
    anchor: re.Pattern | None = None
    heading: re.Pattern | None = None
    body: str = ""
    expect: int = 1
    source_digest: str | None = None
    render: str | None = None


@dataclass
class Result:
    applied: list[tuple[str, str, int]] = field(default_factory=list)   # (id, path, hits)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    digests: list[tuple[str, str, str]] = field(default_factory=list)   # (id, path, digest)


def load(path: Path | None = None) -> tuple[list[Overlay], list[str]]:
    """读 overlays.yaml。返回 (overlays, external_skills)。"""
    p = path or HERE / "overlays.yaml"
    if not p.exists():
        return [], []
    doc = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    out = []
    for e in doc.get("overlays") or []:
        paths = e["path"] if isinstance(e["path"], list) else [e["path"]]
        body = ""
        if e.get("body"):
            body = (ADAPTER / e["body"]).read_text(encoding="utf-8")
        out.append(Overlay(
            id=e["id"], paths=paths, op=e["op"], why=e.get("why", ""),
            anchor=re.compile(e["anchor"]) if e.get("anchor") else None,
            heading=re.compile(e["heading"]) if e.get("heading") else None,
            body=body, expect=int(e.get("expect", 1)),
            source_digest=e.get("source_digest") or None, render=e.get("render"),
        ))
    return out, list(doc.get("external_skills") or [])


def _digest(blob: str) -> str:
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]


def _outside_fence(lines: list[str]):
    """产出围栏外的 (行号, 行)。

    必须跟踪围栏：被替换的两节里都有 ```bash 块，块内注释以 `# ` 开头，
    不跟踪的话 _SECTION_END 会把节边界截在那行，只换掉半节。
    """
    fence = False
    for i, l in enumerate(lines):
        if _FENCE.match(l):
            fence = not fence
            continue
        if not fence:
            yield i, l


def _delete_lines(lines: list[str], anchor: re.Pattern) -> tuple[list[str], int, str]:
    """删命中行；其后紧跟的空行一并删（段落删除，否则留下双空行）。"""
    targets = {i for i, l in _outside_fence(lines) if anchor.search(l)}
    if not targets:
        return lines, 0, ""
    out, removed, i = [], [], 0
    while i < len(lines):
        if i in targets:
            removed.append(lines[i])
            i += 1
            if i < len(lines) and not lines[i].strip():
                i += 1
            continue
        out.append(lines[i])
        i += 1
    return out, len(targets), "\n".join(removed)


def _replace_section(lines: list[str], heading: re.Pattern,
                     body: str) -> tuple[list[str], int, str]:
    """整节替换：从标题行到下一个节边界（不含）。"""
    starts = [i for i, l in _outside_fence(lines) if heading.search(l)]
    if len(starts) != 1:
        return lines, len(starts), ""
    h = starts[0]
    end = next((k for k, _ in _outside_fence(lines) if k > h and _SECTION_END.match(lines[k])),
               len(lines))
    removed = lines[h:end]
    # body 后补一个空行，复原「正文 → 空行 → 下一节边界」的间距
    block = body.rstrip("\n").split("\n") + [""]
    return lines[:h] + block + lines[end:], 1, "\n".join(removed)


def _insert_after_frontmatter(text: str, body: str) -> tuple[str, int]:
    m = _FRONTMATTER.match(text)
    if not m:
        return text, 0
    return text[:m.end()] + "\n" + body.rstrip("\n") + "\n\n" + text[m.end():], 1


def _render(body: str, ov: Overlay, ctx: dict) -> str:
    """占位符替换。agent 名单从实际产出的 TOML 生成 —— 硬编码的名单加个 agent 就烂了。"""
    if ov.render == "agents_list":
        names = sorted(ctx.get("agent_names") or [])
        if not names:
            return body
        body = body.replace("{{agent_names}}", ", ".join(f"`{n}`" for n in names))
    return body


def apply_all(codex_dir: Path, ctx: dict | None = None,
              overlays: list[Overlay] | None = None) -> Result:
    """把所有 overlay 打到产物上。就地改写文件，返回逐条结果。"""
    res = Result()
    ctx = ctx or {}
    if overlays is None:
        overlays, _ = load()

    for ov in overlays:
        for rel in ov.paths:
            f = codex_dir / rel
            if not f.is_file():
                res.errors.append(f"overlay `{ov.id}`: 目标文件不存在 {rel}"
                                  f"（源侧 skill 改名或被删？）")
                continue
            text = f.read_text(encoding="utf-8")
            body = _render(ov.body, ov, ctx)

            if ov.op == "insert_after_frontmatter":
                new, hits = _insert_after_frontmatter(text, body)
                blob = None
            elif ov.op in ("delete_lines", "replace_section"):
                lines = text.split("\n")
                if ov.op == "delete_lines":
                    lines, hits, blob = _delete_lines(lines, ov.anchor)
                else:
                    lines, hits, blob = _replace_section(lines, ov.heading, body)
                new = "\n".join(lines)
            else:
                res.errors.append(f"overlay `{ov.id}`: 未知 op `{ov.op}`")
                continue

            if hits != ov.expect:
                res.errors.append(
                    f"overlay `{ov.id}` 在 {rel} 命中 {hits} 次，应为 {ov.expect} 次"
                    f" —— 锚点失配，源侧多半重构了这一节。**不要把 expect 改成 {hits} 了事**，"
                    f"去看源侧现在长什么样，再决定 Codex 侧该怎么写（{ov.why}）")
                continue

            if blob is not None:
                d = _digest(blob)
                res.digests.append((ov.id, rel, d))
                if ov.source_digest and ov.source_digest != d:
                    res.warnings.append(
                        f"overlay `{ov.id}`（{rel}）：被覆盖的源侧内容已变"
                        f"（digest {ov.source_digest} → {d}）。补丁照打了，但上游这一节的"
                        f"改动可能需要同步进 Codex 版；确认后把新 digest 填回 overlays.yaml")

            f.write_text(new, encoding="utf-8")
            res.applied.append((ov.id, rel, hits))
    return res


def main(argv=None):
    """本模块没有独立入口 —— overlay 必须在 convert.py 的产物刚生成、还没被打过补丁时
    施加一次，对着成品重跑既无意义又会算出错的 digest。列一下登记了什么就够了。"""
    argparse.ArgumentParser(description="Codex 产物的平台分歧补丁层（由 convert.py 调用）"
                            ).parse_args(argv)
    print(__doc__)
    overlays, external = load()
    print(f"已登记 {len(overlays)} 条 overlay：")
    for o in overlays:
        for rel in o.paths:
            pin = o.source_digest or "（未固定）"
            print(f"  {o.id:28} {o.op:26} {rel:34} {pin}")
    print(f"\n外部 skill 白名单（{len(external)}）：{', '.join(external)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
