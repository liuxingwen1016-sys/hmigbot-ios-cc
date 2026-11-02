"""Format self-check of one spec/fix/round-N directory, run after every `tickets`.

1 file name = id  2 common fields  3 fixer_layer  4 body sections 1-5  5 SYSTEMIC affects  6 per-page fields
7 similarity 0..1 on ALIGN  8 unique ids  9 evidence points at existing canonical files (not at a workspace)
10 nav_failed: android_verified true + blocks_subtree; BLOCKED: blocked_by exists.
"""
from __future__ import annotations

import os
import re

COMMON = ("id", "title", "source", "layer", "kind", "severity", "fixer_layer", "suggested_files", "evidence")
PER_PAGE = ("page_id", "multimodal_severity", "is_migration_bug")
SECTIONS = ("## 1. Spec 引用", "## 2. 期望", "## 3. 实际", "## 4. 源码缺口", "## 5. 修复建议")
WORKSPACES = ("spec/visual-verify/walk/", "spec/visual-verify/rounds/", "spec/visual-verify/cache/")


def front_of(text: str) -> tuple[dict, list]:
    """Top-level scalars and lists of the front matter, plus its raw lines."""
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    if not m:
        return {}, []
    lines = m.group(1).splitlines()
    out, key = {}, None
    for ln in lines:
        if re.match(r"^[a-z_]+:", ln):
            key, _, v = ln.partition(":")
            v = v.strip()
            out[key] = [] if v in ("", "[]") else v.strip('"')
        elif ln.startswith("  - ") and key and isinstance(out.get(key), list):
            out[key].append(ln[4:].strip().strip('"'))
    return out, lines


def check(project: str, fix_dir: str) -> list:
    fails, seen = [], {}
    for d, _, files in os.walk(fix_dir):
        for name in sorted(files):
            if not name.endswith(".md") or name.startswith("_"):
                continue
            path = os.path.join(d, name)
            rel = os.path.relpath(path, project)
            text = open(path, encoding="utf-8").read()
            fm, raw = front_of(text)
            tid = name[:-3]
            if fm.get("id") != tid:
                fails.append(f"{rel}: id 与文件名不一致")
            seen.setdefault(fm.get("id"), []).append(rel)
            for k in COMMON:
                if k not in fm:
                    fails.append(f"{rel}: 缺字段 {k}")
            if fm.get("fixer_layer") not in ("ui", "feat"):
                fails.append(f"{rel}: 非法 fixer_layer {fm.get('fixer_layer')}")
            for sec in SECTIONS:
                if sec not in text:
                    fails.append(f"{rel}: 缺 section [{sec}]")
            kind = fm.get("kind")
            if kind == "SYSTEMIC" and not fm.get("affects"):
                fails.append(f"{rel}: SYSTEMIC 缺 affects")
            if fm.get("source") == "visual-verify":
                for k in PER_PAGE:
                    if fm.get(k) in (None, "", []):
                        fails.append(f"{rel}: 必填字段 {k} 为空")
            if kind == "ALIGNMENT_DIFF":
                try:
                    v = float(fm.get("similarity"))
                    if not 0 <= v <= 1:
                        fails.append(f"{rel}: similarity 越界 ({v})")
                except (TypeError, ValueError):
                    fails.append(f"{rel}: ALIGN 缺 similarity")
            for ev in fm.get("evidence") or []:
                p = re.sub(r":\d+(-\d+)?$", "", ev)
                if any(w in p for w in WORKSPACES):
                    fails.append(f"{rel}: evidence 指向工作区: {ev}")
                if p != "unknown" and not os.path.exists(p if os.path.isabs(p) else os.path.join(project, p)):
                    fails.append(f"{rel}: evidence 路径不存在: {ev}")
            if fm.get("reason_slug") == "nav_failed":
                if not any(ln.strip() == "android_verified: true" for ln in raw):
                    fails.append(f"{rel}: nav_failed 必须 android_verified=true")
                if "blocks_subtree" not in fm:
                    fails.append(f"{rel}: nav_failed 必须列 blocks_subtree")
            if kind == "BLOCKED":
                ref = fm.get("blocked_by") or ""
                if not ref or not os.path.exists(ref if os.path.isabs(ref) else os.path.join(project, ref)):
                    fails.append(f"{rel}: blocked_by 指向不存在: {ref}")
    for tid, paths in seen.items():
        if len(paths) > 1:
            fails.append(f"ID 冲突: {tid} -> {', '.join(paths)}")
    return fails
