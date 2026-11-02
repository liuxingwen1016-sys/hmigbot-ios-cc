"""Android source as ground truth: resource-id -> layout XML file:line and the attributes that decide its look.

Judges and fixers get the exact lines instead of re-deriving values from screenshots: every value is traced to
the Android source, and every fix file carries its Android source lines.
"""
from __future__ import annotations

import os
import re

from .store import read_json, write_json

ATTRS = ("layout_width", "layout_height", "layout_margin", "layout_marginTop", "layout_marginBottom",
         "layout_marginStart", "layout_marginEnd", "layout_marginLeft", "layout_marginRight", "padding",
         "paddingTop", "paddingBottom", "paddingStart", "paddingEnd", "paddingLeft", "paddingRight", "textSize",
         "textColor", "textStyle", "fontFamily", "hint", "textColorHint", "gravity", "layout_gravity", "background",
         "src", "srcCompat", "drawableTop", "drawableStart", "drawableLeft", "lineSpacingExtra", "maxLines",
         "visibility", "text")
ID_RE = re.compile(r'android:id="@\+id/(\w+)"')
ATTR_RE = re.compile(r'(?:android|app):(\w+)="([^"]*)"')


def build_index(android_project: str | None) -> dict:
    """{rid: [{"file", "line", "tag", "attrs"}]} over res/layout*/ of every module (build/ skipped)."""
    out: dict = {}
    if not android_project or not os.path.isdir(android_project):
        return out
    for root, dirs, files in os.walk(android_project):
        dirs[:] = [d for d in dirs if d not in ("build", ".gradle", ".git", ".idea", "intermediates")]
        if not os.path.basename(root).startswith("layout"):
            continue
        for name in files:
            if not name.endswith(".xml"):
                continue
            path = os.path.join(root, name)
            try:
                text = open(path, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            for m in ID_RE.finditer(text):
                start = text.rfind("<", 0, m.start())
                end = text.find(">", m.end())
                if start < 0 or end < 0:
                    continue
                elem = text[start:end + 1]
                tag = re.match(r"<\s*([\w.]+)", elem)
                attrs = {k: v for k, v in ATTR_RE.findall(elem) if k in ATTRS}
                out.setdefault(m.group(1), []).append({
                    "file": os.path.relpath(path, android_project), "line": text.count("\n", 0, m.start()) + 1,
                    "tag": tag.group(1).rsplit(".", 1)[-1] if tag else "", "attrs": attrs})
    return out


def index(store, cfg: dict) -> dict:
    path = os.path.join(store.vvs, "android_layout_index.json")
    cached = read_json(path)
    if cached is not None and cached.get("project") == cfg.get("android_project"):
        return cached["ids"]
    ids = build_index(cfg.get("android_project"))
    write_json(path, {"project": cfg.get("android_project"), "ids": ids})
    return ids


def refs(idx: dict, rids, limit: int = 14, page_rids=None) -> list:
    """Source lines for the given resource-ids. An id defined in several layouts resolves to the layout that
    defines the most ids of this page (the screen's own layout), not to the first match."""
    page = set(page_rids or rids)
    score: dict = {}
    for rid in page:
        for d in idx.get(rid, ()):
            score[d["file"]] = score.get(d["file"], 0) + 1
    out, seen = [], set()
    for rid in rids:
        if not rid or rid in seen or rid not in idx:
            continue
        seen.add(rid)
        d = max(idx[rid], key=lambda d: score.get(d["file"], 0))
        out.append({"rid": rid, "file": d["file"], "line": d["line"], "tag": d["tag"], "attrs": d["attrs"],
                    "also_in": len(idx[rid]) - 1})
        if len(out) >= limit:
            break
    return out


def format_ref(r: dict) -> str:
    attrs = ", ".join(f"{k}={v}" for k, v in r["attrs"].items() if k != "text")[:220]
    more = f"（另有 {r['also_in']} 处同名 id）" if r["also_in"] else ""
    return f"`{r['rid']}` {r['tag']} — {r['file']}:{r['line']}{more}  {attrs}"
