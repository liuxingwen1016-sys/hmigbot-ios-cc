"""Fixer schedule: serialize only on the real conflict surface (shared files), run the rest in parallel.

Fix files that share a suggested file end up in one group (union-find); groups have disjoint write sets and can
be fixed by parallel fixers. A host page several units share (a Navigation root) joins a write set only when a
ticket names nothing else; a fix that needs it after all comes back as needs_file. A file without a located source goes to one 'unlocated' group that runs alone after
the others (it may touch anything). BLOCKED placeholders are not fixed. The schedule is written to
rounds/round-N/fix/schedule.json and summarised in docs/autofix-log/round-N/batch.md.
"""
from __future__ import annotations

import os
import re

from .store import Store, now_iso, write_json

FRONT_RE = re.compile(r"^---\n(.*?)\n---", re.S)


def read_front(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        text = f.read()
    m = FRONT_RE.match(text)
    out, key = {}, None
    if not m:
        return out
    for line in m.group(1).splitlines():
        if line.startswith("  - ") and key:
            out.setdefault(key, []).append(line[4:].strip())
            continue
        k, _, v = line.partition(":")
        key = k.strip()
        v = v.strip()
        if v == "[]":
            out[key] = []
        elif v:
            out[key] = v.strip("'\"")
        else:
            out[key] = []
    return out


def tickets_of(hmos_project: str, rnd: int) -> list:
    from .tickets import fix_root
    d = fix_root(hmos_project, rnd)
    out = []
    for layer in ("feat", "feat/_systemic", "ui", "ui/_systemic"):
        ld = os.path.join(d, layer)
        if not os.path.isdir(ld):
            continue
        for name in sorted(os.listdir(ld)):
            if name.endswith(".md") and not name.startswith("_"):
                fm = read_front(os.path.join(ld, name))
                disp = str(fm.get("disposition") or "")
                if fm.get("kind") == "BLOCKED" or disp in ("skipped", "manual_review", "fixed") or disp.startswith("pending_"):
                    continue
                fm["path"] = os.path.join(ld, name)
                out.append(fm)
    return out


def host_files(store: Store, cfg: dict, rnd: int) -> set:
    """Page files that host several Android units (a Navigation root, a tab container). Nearly every ticket can
    name one; in every write set it would glue unrelated groups into one."""
    from collections import Counter
    from .fixfiles import _page_file
    from .store import read_json
    pairs = read_json(os.path.join(store.round_dir(rnd), "pairs.json"), {}) or {}
    count = Counter(f for f in (_page_file(cfg["hmos_project"], it.get("harmony_page"))
                                for it in pairs.get("items") or []) if f)
    return {f for f, n in count.items() if n > 1}


def schedule(store: Store, cfg: dict, rnd: int, max_parallel: int = 4, log=print) -> dict:
    tickets = tickets_of(cfg["hmos_project"], rnd)
    hosts = host_files(store, cfg, rnd)
    parent = {}

    def find(x):
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        parent[find(a)] = find(b)
    unlocated = []
    for t in tickets:
        files = [f for f in t.get("suggested_files") or [] if f and f != "unknown"]
        files = [f for f in files if f not in hosts] or files  # a host page only when nothing else is named
        t["files"] = files
        if not files:
            unlocated.append(t)
            continue
        for f in files[1:]:
            union(files[0], f)
        find(files[0])
    groups: dict = {}
    for t in tickets:
        if t["files"]:
            groups.setdefault(find(t["files"][0]), []).append(t)
    out_groups = []
    for i, (root, ts) in enumerate(sorted(groups.items(), key=lambda kv: -len(kv[1])), 1):
        files = sorted({f for t in ts for f in t["files"]})
        out_groups.append({"group": f"g{i:02d}", "write_set": files, "tickets": [t["path"] for t in ts],
                           "pages": sorted({t.get("page_id", "") for t in ts})})
    waves = []
    for i in range(0, len(out_groups), max_parallel):
        waves.append([g["group"] for g in out_groups[i:i + max_parallel]])
    plan = {"round": rnd, "created": now_iso(), "groups": out_groups, "waves": waves,
            "unlocated": [t["path"] for t in unlocated],
            "rules": ["one fixer per group; groups in one wave run in parallel",
                      "a fixer edits only its write_set (+ new files it creates); needing another file -> report it, do not edit",
                      "the 'unlocated' tickets run in one fixer after all waves, alone",
                      "fixers do not build, install or capture; the parent builds once after all fixers"]}
    path = os.path.join(store.round_dir(rnd), "fix", "schedule.json")
    write_json(path, plan)
    from .fixcheck import snapshot
    snapshot(cfg["hmos_project"], os.path.join(store.round_dir(rnd), "fix", "snapshot.json"))
    hp = cfg["hmos_project"]
    log_dir = os.path.join(hp, "docs", "autofix-log", f"round-{rnd}")
    os.makedirs(log_dir, exist_ok=True)
    lines = [f"# Round {rnd} 修复批次", "", f"> 生成时间：{plan['created']}", "",
             f"共 {len(tickets)} 张，{len(out_groups)} 组，{len(waves)} 波；每组一个修复子代理，同一波并行。", ""]
    for w, names in enumerate(waves, 1):
        lines.append(f"## 第 {w} 波")
        for g in (x for x in out_groups if x["group"] in names):
            lines.append(f"- {g['group']}（{len(g['tickets'])} 张）写集：" + "、".join(f"`{f}`" for f in g["write_set"]))
            lines += [f"  - {os.path.relpath(t, hp)}" for t in g["tickets"]]
        lines.append("")
    if unlocated:
        lines += ["## 最后单独跑（未定位文件）", *(f"- {os.path.relpath(t['path'], hp)}" for t in unlocated), ""]
    with open(os.path.join(log_dir, "batch.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    log(f"[vvs] fix plan round-{rnd}: {len(tickets)} tickets, {len(out_groups)} groups in {len(waves)} waves, "
        f"{len(unlocated)} unlocated -> {path}")
    return plan
