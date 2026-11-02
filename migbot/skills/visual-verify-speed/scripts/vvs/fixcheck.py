"""Mechanical review of one fix wave: what the fixers changed against what their fix files claim.

`fixplan` snapshots the HarmonyOS sources (hash of every source/resource file, text of .ets and element .json);
`fixcheck` compares the project with that snapshot and the attempts appended to section 6 of each fix file:

  empty_diff            the attempt names no real file, or none of the named files changed
  duplicate_hypothesis  the same root-cause hypothesis (or the same files + summary) as an earlier attempt
  wrong_edit            the diff of the named files has none of the properties this kind of difference needs
  missing_attempt       a scheduled fix file got no attempt this round and no status in its group result file
  fixer_blocked         (info) the fixer reported blocked / needs_file / refuted with a reason: not a missing or
                        empty attempt; the reason goes into fixcheck.md and the next round's fix file
  outside_write_set     a file changed that no group was allowed to edit (parallel groups must not overlap)
  risky_pattern         the change introduced a construct that blocks clicks of a whole subtree

Flags go to rounds/round-N/fix/fixcheck.json and docs/autofix-log/round-N/fixcheck.md; the next round's fix
files carry them in section 6 so the next fixer changes direction. The changed files also decide the next
round's re-walk scope.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import os
import re

from .store import now_iso, read_json, write_json

SKIP_DIRS = {"build", "oh_modules", "node_modules", ".hvigor", ".git", ".idea", "spec", "docs", ".preview"}
SOURCE_EXT = (".ets", ".ts", ".json", ".json5", ".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif")
TEXT_EXT = (".ets", ".ts", ".json", ".json5")
PLACEHOLDER = {"", "无", "-", "n/a", "na", "空", "none", "null"}
RESERVED = {"schedule.json", "snapshot.json", "fixcheck.json"}
ATTEMPT_RE = re.compile(r"^### round-(\d+) attempt by visual-fixer\s*$", re.M)
FIELD_RE = re.compile(r"^- (?:\*\*)?(改动文件|改动摘要|假设根因|预期效果|未做的事[^*:：]*)(?:\*\*)?[:：]\s*(.*)$", re.M)
PATH_RE = re.compile(r"`?([\w./-]+\.(?:ets|ts|json5?|png|svg|jpe?g|webp))(?::[\d,-]+)?`?")
KIND_WORDS = {
    "color_mismatch": r"color|Color|#[0-9A-Fa-f]{3,8}\b|backgroundColor|fontColor|opacity",
    "font_mismatch": r"fontSize|fontWeight|FontWeight|fontFamily|placeholderFont|lineHeight|letterSpacing|TEXT_|FontSize",
    "spacing_drift": r"padding|margin|space|lineHeight|offset|Padding|Margin",
    "layout_drift": r"width|height|padding|margin|offset|position|align|justify|layoutWeight|flexGrow|aspectRatio|translate|Row|Column|Stack",
    "layout_bug": r"width|height|layoutWeight|objectFit|ImageFit|aspectRatio|constraintSize|clip|flex",
    "icon_mismatch": r"\$r\(|width|height|objectFit|fillColor|Image|SymbolGlyph|src",
    "missing_element": r"^\+\s*(Text|Image|Button|Row|Column|Stack|List|Toggle|Checkbox|TextInput|Divider|[A-Z]\w+)\s*\(",
    "extra_element": r"^-\s*(Text|Image|Button|Row|Column|Stack|List|[A-Z]\w+)\s*\(|if\s*\(|visibility",
    "text_mismatch": r"\$r\('app\.string|['\"][^'\"]*[一-鿿]|maxLines|textOverflow",
    "component_mismatch": r"[A-Z]\w+\s*\(|\.\w+\(",
}
RISKY = [(re.compile(r"\?\s*HitTestMode\.Block\s*:\s*HitTestMode\.(None|Transparent|Default)"),
          "显示时 HitTestMode.Block（visible ? Block : None）：整棵子树的点击都会失效")]


def source_files(hp: str) -> list:
    out = []
    for d, dirs, files in os.walk(hp, followlinks=True):
        dirs[:] = [x for x in dirs if x not in SKIP_DIRS and not x.startswith(".")]
        for f in files:
            if f.endswith(SOURCE_EXT):
                out.append(os.path.relpath(os.path.join(d, f), hp))
    return sorted(out)


def _sha(path: str) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def snapshot(hp: str, path: str) -> dict:
    files = {}
    texts = {}
    for rel in source_files(hp):
        full = os.path.join(hp, rel)
        try:
            files[rel] = _sha(full)
            if rel.endswith(TEXT_EXT) and os.path.getsize(full) < 400_000 and \
                    (rel.endswith(".ets") or os.sep + "element" + os.sep in rel):
                texts[rel] = open(full, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
    snap = {"created": now_iso(), "files": files, "texts": texts}
    write_json(path, snap)
    return snap


def changed(hp: str, snap: dict) -> dict:
    now = {rel: _sha(os.path.join(hp, rel)) for rel in source_files(hp)}
    before = snap.get("files") or {}
    return {"modified": sorted(r for r in now if r in before and now[r] != before[r]),
            "added": sorted(r for r in now if r not in before),
            "deleted": sorted(r for r in before if r not in now)}


def attempts(text: str) -> list:
    """Section-6 attempts of one fix file: [{round, files, summary, hypothesis}]."""
    sec = text.split("## 6.", 1)[-1].split("\n## 7.", 1)[0] if "## 6." in text else ""
    marks = list(ATTEMPT_RE.finditer(sec))
    out = []
    for i, m in enumerate(marks):
        block = sec[m.end(): marks[i + 1].start() if i + 1 < len(marks) else len(sec)]
        fields = {k.split("/")[0].strip(): v.strip() for k, v in FIELD_RE.findall(block)}
        files_txt = fields.get("改动文件", "")
        out.append({"round": int(m.group(1)), "files": PATH_RE.findall(files_txt),
                    "files_raw": files_txt, "summary": fields.get("改动摘要", ""),
                    "hypothesis": fields.get("假设根因", "")})
    return out


def _norm(s: str) -> str:
    return re.sub(r"[\s`*，。,.；;：:（）()]+", "", s or "").lower()


def _similar(a: str, b: str) -> float:
    a, b = _norm(a), _norm(b)
    return difflib.SequenceMatcher(None, a, b).ratio() if a and b else 0.0


def _diff(old: str, new: str) -> str:
    return "\n".join(difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm="", n=0))


def _match(path: str, changed_set: set) -> str | None:
    """A file named in an attempt (possibly only its basename) -> the changed project path."""
    path = path.lstrip("./")
    if path in changed_set:
        return path
    hits = [c for c in changed_set if c.endswith("/" + path) or os.path.basename(c) == os.path.basename(path)]
    return hits[0] if len(hits) == 1 else None


def check(store, cfg: dict, rnd: int, log=print) -> int:
    hp = cfg["hmos_project"]
    fdir = os.path.join(store.round_dir(rnd), "fix")
    snap = read_json(os.path.join(fdir, "snapshot.json"))
    sched = read_json(os.path.join(fdir, "schedule.json"))
    if not snap or not sched:
        log(f"[vvs] no fix snapshot/schedule for round-{rnd}: run `vvs.py fixplan` before the fixers")
        return 2
    ch = changed(hp, snap)
    changed_set = set(ch["modified"] + ch["added"])
    allowed = {f for g in sched["groups"] for f in g["write_set"]}
    # result files: the scheduled groups', then follow-ups the parent dispatched after the wave (needs_file);
    # a follow-up may edit the files it was handed, so the files it reports count as allowed
    names = [f"{g['group']}.json" for g in sched["groups"]] + ["unlocated.json"]
    follow = sorted(n for n in (os.listdir(fdir) if os.path.isdir(fdir) else [])
                    if n.endswith(".json") and n not in names and n not in RESERVED)
    results = [(n, read_json(os.path.join(fdir, n), {}) or {}) for n in names + follow]
    for n, res in results:
        if n in follow:
            allowed |= {f for f in res.get("changed_files") or [] if isinstance(f, str)}
    unlocated = bool(sched.get("unlocated"))
    flags = []
    for f in sorted(changed_set):
        if f not in allowed and f not in ch["added"] and not unlocated:
            flags.append({"flag": "outside_write_set", "ticket": None, "evidence": f"{f} 不在任何一组的写集里"})
    texts = snap.get("texts") or {}
    for rel in sorted(ch["modified"]):
        if rel in texts and rel.endswith(".ets"):
            new = open(os.path.join(hp, rel), encoding="utf-8", errors="replace").read()
            for rx, why in RISKY:
                if len(rx.findall(new)) > len(rx.findall(texts[rel])):
                    flags.append({"flag": "risky_pattern", "ticket": None, "evidence": f"{rel}: {why}"})
    tickets = [t for g in sched["groups"] for t in g["tickets"]] + list(sched.get("unlocated") or [])
    reported = {}  # ticket id -> (status, reason); a later result file (a follow-up) overrides an earlier one
    for _, res in results:
        for t in res.get("tickets") or []:
            if isinstance(t, dict) and t.get("id"):
                reported[t["id"]] = (str(t.get("status") or ""), str(t.get("note") or t.get("why") or t.get("source") or ""))
        for t in res.get("needs_file") or []:
            if isinstance(t, dict):
                for tid in t.get("tickets") or []:
                    reported.setdefault(tid, ("needs_file", f"{t.get('file')}: {t.get('why')}"))
    for path in tickets:
        if not os.path.exists(path):
            continue
        text = open(path, encoding="utf-8").read()
        tid = os.path.basename(path)[:-3]
        kind = (re.search(r"^id:\s*\w+?_P\d+_([a-z_]+?)_", text, re.M) or [None, ""])[1]
        atts = attempts(text)
        mine = [a for a in atts if a["round"] == rnd]
        status, why = next((v for k, v in reported.items() if k == tid or (len(k) >= 40 and tid.startswith(k))),
                           ("", ""))
        if status in ("blocked", "refuted") or (status == "needs_file" and not mine):
            flags.append({"flag": "fixer_blocked", "ticket": tid, "evidence": f"修复方报 {status}：{why[:160]}"})
            continue  # no code change expected; the next round re-judges it
        if not mine:
            flags.append({"flag": "missing_attempt", "ticket": tid, "evidence": "本轮没有追加 §6 修复记录"})
            continue
        a = mine[-1]
        names = [p for p in a["files"]]
        if _norm(a["files_raw"]) in PLACEHOLDER or not names:
            flags.append({"flag": "empty_diff", "ticket": tid, "evidence": f"改动文件写的是「{a['files_raw'] or '空'}」"})
        else:
            hit = [m for m in (_match(p, changed_set) for p in names) if m]
            if not hit:
                flags.append({"flag": "empty_diff", "ticket": tid,
                              "evidence": f"声明改了 {', '.join(names[:3])}，快照对比这些文件没有变化"})
            elif kind in KIND_WORDS:
                rx = re.compile(KIND_WORDS[kind], re.M)
                diffs = "\n".join(_diff(texts.get(m, ""), open(os.path.join(hp, m), encoding="utf-8",
                                                                errors="replace").read())
                                  for m in hit if m in texts)
                if diffs and not rx.search(diffs):
                    flags.append({"flag": "wrong_edit", "ticket": tid,
                                  "evidence": f"{kind} 类问题，但 {', '.join(hit[:2])} 的改动里没有相应属性"})
        for old in atts:
            if old is a or old["round"] >= rnd:
                continue
            if _similar(old["hypothesis"], a["hypothesis"]) >= 0.85 or (
                    sorted(old["files"]) == sorted(a["files"]) and _similar(old["summary"], a["summary"]) >= 0.85):
                flags.append({"flag": "duplicate_hypothesis", "ticket": tid,
                              "evidence": f"与 round-{old['round']} 的假设/改法相同：{a['hypothesis'][:60]}"})
                break
    out = {"round": rnd, "checked": now_iso(), "changed": ch, "flags": flags}
    write_json(os.path.join(fdir, "fixcheck.json"), out)
    log_dir = os.path.join(hp, "docs", "autofix-log", f"round-{rnd}")
    os.makedirs(log_dir, exist_ok=True)
    lines = [f"# Round {rnd} 修复复核", "", f"> {out['checked']}", "",
             f"改动文件 {len(ch['modified'])} 个，新增 {len(ch['added'])} 个，删除 {len(ch['deleted'])} 个；"
             f"flag {sum(1 for x in flags if x['flag'] != 'fixer_blocked')} 条，修复方未改 "
             f"{sum(1 for x in flags if x['flag'] == 'fixer_blocked')} 张。", "",
             "## flag 列表", ""]
    lines += [f"- {x['flag']}" + (f" `{x['ticket']}`" if x["ticket"] else "") + f"：{x['evidence']}"
              for x in flags if x["flag"] != "fixer_blocked"] or ["（无）"]
    info = [x for x in flags if x["flag"] == "fixer_blocked"]
    if info:
        lines += ["", "## 修复方未改（blocked / needs_file / refuted，下一轮复验判定）", "",
                  *(f"- `{x['ticket']}`：{x['evidence']}" for x in info)]
    lines += ["", "## 改动文件", "", *(f"- {f}" for f in ch["modified"] + ch["added"])]
    with open(os.path.join(log_dir, "fixcheck.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    hard = [x for x in flags if x["flag"] in ("outside_write_set", "risky_pattern")]
    n_info = sum(1 for x in flags if x["flag"] == "fixer_blocked")
    log(f"[vvs] fixcheck round-{rnd}: {len(changed_set)} files changed, {len(flags) - n_info} flags, "
        f"{n_info} reported not fixed by the fixers"
        + (f" ({len(hard)} must be fixed before building)" if hard else "") + f" -> {log_dir}/fixcheck.md")
    return 1 if hard else 0


def flags_for(store, rnd: int) -> dict:
    """{ticket id: [flag lines]} of a round's fixcheck (for the next round's fix files)."""
    data = read_json(os.path.join(store.round_dir(rnd), "fix", "fixcheck.json"), {}) or {}
    out: dict = {}
    for x in data.get("flags") or []:
        if x.get("ticket"):
            out.setdefault(x["ticket"], []).append(f"{x['flag']}：{x['evidence']}")
    return out
