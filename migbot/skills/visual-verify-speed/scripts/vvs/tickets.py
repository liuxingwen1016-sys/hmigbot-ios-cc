"""Judge results + walk gaps -> spec/fix/round-N (fixfiles.py renders the files).

Every judge result is re-checked mechanically before anything is written: a pair sent to a judge without a valid
result file blocks the round (exit 2); findings the dumps do not support are withdrawn or lowered.
"""
from __future__ import annotations

import os
import re

from . import fixfiles, hui, layout, source
from .android import Plan
from .store import Store, now_iso, read_json, write_json

TOL_POS = 8.0   # dp: position differences up to ~1% of the screen are device noise
TOL_SIZE = 4.0  # dp: size tolerance
SHAPE_WORDS = ("图标", "圆圈", "圆点", "箭头", "勾", "指示", "背景", "边框", "描边", "线", "阴影", "徽标", "icon", "indicator")
QUOTE_RE = re.compile(r"[「“\"]([^」”\"]{2,40})[」”\"]")

CATEGORIES = ("layout", "layout_bug", "color", "font", "spacing", "component", "icon", "text", "missing", "extra",
              "scroll", "flow", "image", "state", "render", "other")
PATTERNS = ("dialog_extra_on_android", "launch_flow_skipped", "nav_chain_broken_hmos", "page_missing_hmos",
            "render_invisible")
VERDICTS = ("pass", "fail", "pair_mismatch")
KEY_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,29}$")
TEXTSIZE_RE = re.compile(r"(?:textSize|bar_leftTextSize|TextSize)\s*=\s*(\d+(?:\.\d+)?)\s*(sp|dp)(?:[^（(\n]{0,12}[（(]([\w./-]+\.xml:\d+(?:/\d+)*)[)）])?")


def fix_root(hmos_project: str, rnd: int) -> str:
    return layout.fix_root(hmos_project, rnd)


def normalize_keys(res: dict) -> list:
    """Format slips a rule can fix are fixed here, not sent back to the judge: a key that is too long, has capitals
    or other characters becomes a 2-30 char a-z0-9- slug (cut at a word boundary), repeats get -2, -3...
    Returns [(old, new)]; a key with nothing usable left stays and fails validation."""
    changed, seen = [], set()
    for f in res.get("findings") or []:
        if not isinstance(f, dict):
            continue
        old = str(f.get("key", ""))
        new = re.sub(r"[^a-z0-9]+", "-", old.lower()).strip("-")
        if len(new) > 30:
            new = new[:31].rsplit("-", 1)[0] if "-" in new[:31] else new[:30]
        if len(new) < 2:
            seen.add(old)
            continue
        base, n = new, 2
        while new in seen:
            new = f"{base[:27]}-{n}"
            n += 1
        seen.add(new)
        if new != old:
            f["key"] = new
            changed.append((old, new))
    return changed


def validate_result(res: dict, pid: str, hmos_project: str, oracle_ids: list | None = None) -> tuple[list, list]:
    """(errors, warnings). oracle_ids: the O1.. differences the batch file asked the judge to confirm/refute."""
    errors, warnings = [], []
    if not isinstance(res, dict):
        return ["result is not a JSON object"], []
    checks = res.get("oracle_checks")
    if oracle_ids:
        if not isinstance(checks, list):
            errors.append("oracle_checks must list a decision for every structure-oracle difference")
            checks = []
        got = {c.get("id"): c for c in checks if isinstance(c, dict)}
        for oid in oracle_ids:
            c = got.get(oid)
            if c is None:
                errors.append(f"oracle_checks has no decision for {oid}")
            elif c.get("decision") not in ("confirmed", "refuted"):
                errors.append(f"oracle_checks {oid}: decision must be confirmed/refuted")
            elif c["decision"] == "refuted" and not str(c.get("evidence", "")).strip():
                errors.append(f"oracle_checks {oid}: refuted needs evidence")
    for k in ("icon_semantic_checks", "siblings_order_checks"):
        if not isinstance(res.get(k), list):
            errors.append(f"{k} must be a list (icon semantics and sibling order are mandatory checks)")
    known = {str(f.get("key")) for f in res.get("findings") or [] if isinstance(f, dict)} | \
        {str(c.get("id")) for c in checks or [] if isinstance(c, dict)}
    for k in ("oracle_checks", "icon_semantic_checks", "siblings_order_checks"):
        for c in res.get(k) or []:
            if isinstance(c, dict) and c.get("same_as") is not None and str(c["same_as"]) not in known:
                warnings.append(f"{k}: same_as {c['same_as']} points at nothing; the entry is ticketed on its own")
    for i, d in enumerate(res.get("data_only_differences") or []):
        if not isinstance(d, dict) or not str(d.get("android_source_proof", "")).strip():
            errors.append(f"data_only_differences[{i}] needs android_source_proof (Android source file:line)")
    if res.get("android") != pid:
        errors.append(f"android must be {pid}")
    if res.get("verdict") not in VERDICTS:
        errors.append(f"verdict must be one of {VERDICTS}")
    findings = res.get("findings")
    if not isinstance(findings, list):
        errors.append("findings must be a list")
        findings = []
    keys = set()
    for i, f in enumerate(findings):
        where = f"findings[{i}]"
        if not isinstance(f, dict):
            errors.append(f"{where} is not an object")
            continue
        if not KEY_RE.match(str(f.get("key", ""))):
            errors.append(f"{where}.key must be 2-30 chars of a-z 0-9 -")
        elif f["key"] in keys:
            errors.append(f"{where}.key {f['key']} repeats")
        keys.add(f.get("key"))
        if f.get("category") not in CATEGORIES:
            errors.append(f"{where}.category must be one of {CATEGORIES}")
        if f.get("severity") not in ("high", "medium", "low"):
            errors.append(f"{where}.severity must be high/medium/low")
        for k in ("description", "android", "harmony"):
            if not str(f.get(k, "")).strip():
                errors.append(f"{where}.{k} is empty")
        if not isinstance(f.get("is_migration_bug"), bool):
            errors.append(f"{where}.is_migration_bug must be true/false")
        if f.get("severity") in ("high", "medium") and not str(f.get("evidence", "")).strip():
            errors.append(f"{where}.evidence is required for high/medium (measurement row, dump node or source line)")
        if f.get("category_pattern") and f["category_pattern"] not in PATTERNS:
            errors.append(f"{where}.category_pattern must be one of {PATTERNS}")
        if f.get("category") == "flow" and not f.get("category_pattern"):
            errors.append(f"{where}: category flow needs category_pattern")
        reg = f.get("region")
        if reg is not None and not (isinstance(reg, list) and len(reg) == 4
                                    and all(isinstance(v, (int, float)) and 0 <= v <= 1 for v in reg)):
            errors.append(f"{where}.region must be [x1,y1,x2,y2] ratios in 0..1")
        files = f.get("suggested_files") or []
        kept = [p for p in files if os.path.exists(os.path.join(hmos_project, p))]
        if len(kept) != len(files):
            warnings.append(f"{where}: dropped missing suggested_files {sorted(set(files) - set(kept))}")
            f["suggested_files"] = kept
    # fail needs a difference behind it: a migration-bug finding, or a confirmed oracle item / failed icon or order
    # check (those become tickets by themselves; judge.md tells the judge not to write them again as findings)
    if res.get("verdict") == "fail" and not (
            any(f.get("is_migration_bug") for f in findings if isinstance(f, dict))
            or any(isinstance(c, dict) and c.get("decision") == "confirmed" for c in checks or [])
            or any(isinstance(c, dict) and c.get("match") is False
                   for k in ("icon_semantic_checks", "siblings_order_checks") for c in res.get(k) or [])):
        errors.append("verdict fail needs a difference: a finding with is_migration_bug true, a confirmed oracle "
                      "check or a failed icon / order check")
    sim = res.get("similarity")
    if sim is not None and not (isinstance(sim, (int, float)) and 0 <= sim <= 1):
        errors.append("similarity must be a number in 0..1")
    if res.get("verdict") == "pass" and any(f.get("is_migration_bug") and f.get("severity") in ("high", "medium")
                                            for f in findings if isinstance(f, dict)):
        errors.append("verdict pass cannot carry a high/medium migration bug")
    return errors, warnings


def frame_data(it: dict) -> list:
    return [read_json((fr.get("oracle") or {}).get("file", ""), {}) or {} for fr in it.get("frames") or []]


def _finding_text(f: dict) -> str:
    return hui.norm_label(" ".join(str(f.get(k, "")) for k in ("description", "android", "harmony", "key")))


def recheck(f: dict, it: dict, fdata: list) -> str:
    """Mechanical second check of one judge finding against the dumps ('done' needs a parent-side check, not
    only the sub-agent's claim). Returns '' to keep it, else why it is withdrawn."""
    if f.get("category") == "flow":
        return ""
    k = int(f.get("frame") or 0)
    d = fdata[k] if k < len(fdata) else (fdata[0] if fdata else {})
    if not d:
        return ""
    text = _finding_text(f)
    quoted = {hui.norm_label(q) for q in QUOTE_RE.findall(" ".join(str(f.get(x, "")) for x in ("description", "harmony")))}
    labels = set(d.get("android_ids") or {}) | {hui.norm_label(r["label"]) for r in d.get("measure") or []}
    mentioned = {t for t in labels if len(t) >= 2 and t in text} | {q for q in quoted if q}
    drawn = set(d.get("harmony_drawn") or [])
    desc = str(f.get("description", "")) + str(f.get("harmony", ""))
    says_missing = f.get("category") == "missing" or any(w in desc for w in ("消失", "缺失", "看不到", "不显示"))
    about_shape = any(w in desc for w in SHAPE_WORDS)
    if says_missing and not about_shape and mentioned and all(t in drawn for t in mentioned):
        return "鸿蒙截图里这些元素都画出来了：" + "、".join(sorted(mentioned))[:80]
    if f.get("category") == "layout":
        cited = text + hui.norm_label(str(f.get("evidence", "")))
        rows = [r for r in d.get("measure") or [] if _measured(r) and len(hui.norm_label(r["label"])) >= 3
                and hui.norm_label(r["label"]) in cited]
        if rows and all(_within(r, TOL_SIZE) for r in rows):
            return "度量表不支持：" + "；".join(f"{r['label'][:10]} Δx{r['dx']} Δy{r.get('dy_residual', r['dy'])}" for r in rows[:4])
    return ""


def _measured(r: dict) -> bool:
    """A row can speak for or against a claim only when both axes were measured (text box vs ink: x is not)."""
    return not r.get("data") and r.get("x_anchor") != "n/a"


def _dy(r: dict) -> float:
    """Vertical offset for the mechanical check: the larger of the raw offset and the residual after the common
    shift. A common shift may be a scroll difference or a taller header; only the judge can tell which."""
    res = r.get("dy_residual")
    return max(abs(r["dy"]), abs(res if res is not None else r["dy"]))


def _within(r: dict, pos: float = TOL_POS, sizes: bool = True) -> bool:
    ok = max(abs(r["dx"]), _dy(r)) <= pos
    if sizes and r.get("size_comparable"):
        ok = ok and max(abs(r["dw"]), abs(r["dh"])) <= TOL_SIZE
    return ok


def downgrade(f: dict, fdata: list) -> str:
    """A layout claim that names no measured element, on a frame whose measured elements all sit within
    tolerance (bottom-docked bars left out: system navigation areas differ), is kept but lowered to low."""
    if f.get("category") != "layout" or f.get("severity") == "low":
        return ""
    k = int(f.get("frame") or 0)
    d = fdata[k] if k < len(fdata) else (fdata[0] if fdata else {})
    text = _finding_text(f) + hui.norm_label(str(f.get("evidence", "")))
    named = [r for r in d.get("measure") or [] if _measured(r) and len(hui.norm_label(r["label"])) >= 3
             and hui.norm_label(r["label"]) in text]  # two-character labels (我的、设置) collide with ordinary words
    if named and all(_within(r, sizes=False) for r in named):
        return "引用元素的位移只有 " + "、".join(f"{r['label'][:8]} {max(abs(r['dx']), _dy(r))}dp"
                                         for r in named[:3]) + f"（≤{TOL_POS}dp），按低级处理"
    rows = [r for r in d.get("measure") or [] if _measured(r) and r.get("anchor") == "top"]
    spread = max((r["dy"] for r in rows), default=0) - min((r["dy"] for r in rows), default=0)
    if not named and len(rows) >= 3 and all(_within(r, sizes=False) for r in rows) and spread <= TOL_POS:
        return f"整页 {len(rows)} 个元素的度量位移都在 {TOL_POS}dp 内，按低级处理"
    return ""


def source_lines(idx: dict, it: dict, fdata: list, f: dict | None, limit: int = 6) -> list:
    ids = {}
    for d in fdata:
        ids.update(d.get("android_ids") or {})
    page = list(ids.values())
    want = page
    if f is not None:
        text = _finding_text(f)
        want = [rid for t, rid in ids.items() if len(t) >= 2 and t in text] or page[:3]
    return source.refs(idx, want, limit=limit, page_rids=page) if idx else []


ETS_RE = re.compile(r"[\w./-]*?(\w+\.ets)")
_ETS_INDEX: dict = {}


def ets_files(hp: str, text: str) -> list:
    """HarmonyOS source files named in a judge's evidence (`SearchPage.ets:101`), resolved inside the project."""
    if hp not in _ETS_INDEX:
        idx: dict = {}
        for d, dirs, files in os.walk(hp, followlinks=True):
            dirs[:] = [x for x in dirs if x not in ("build", "oh_modules", "node_modules", ".hvigor", ".git", "spec")]
            for f in files:
                if f.endswith(".ets"):
                    idx.setdefault(f, []).append(os.path.relpath(os.path.join(d, f), hp))
        _ETS_INDEX[hp] = idx
    out = []
    for m in ETS_RE.finditer(text or ""):
        full, base = m.group(0).lstrip("./"), m.group(1)
        hits = [full] if os.path.isfile(os.path.join(hp, full)) else _ETS_INDEX[hp].get(base, [])
        if len(hits) == 1 and hits[0] not in out:
            out.append(hits[0])
    return out


def merge_font_items(group: list, checks: dict) -> tuple:
    """Several texts of one frame changed by the same ratio and point to the same code: one ticket."""
    if len(group) == 1:
        return group[0], checks.get(group[0]["id"])
    first = group[0]
    texts = "、".join(f"「{o['text']}」" for o in group)
    o = {**first, "id": "/".join(o["id"] for o in group), "text": " ".join(o["text"] for o in group), "text_label": texts,
         "description": f"{texts}字号疑似不同：墨迹宽高同比例{'变大' if (first.get('ratio') or 1) > 1 else '变小'}"
                        f" ×{first.get('ratio')}（逐条见证据）",
         "android": "；".join(f"{x['text']} {x['android']}" for x in group),
         "harmony": "；".join(f"{x['text']} {x['harmony']}" for x in group)}
    said = " / ".join(f"{x['id']}：{checks.get(x['id'], {}).get('evidence', '')}" for x in group)
    return o, {"evidence": said}


def overlaps(name: str, texts: list, share: float = 0.5) -> bool:
    """Most character pairs of `name` appear in one of `texts` (same thing described in other words)."""
    n = hui.norm_label(name)
    grams = {n[i:i + 2] for i in range(len(n) - 1)}
    if not grams:
        return False
    return any(sum(1 for g in grams if g in t) >= share * len(grams) for t in texts if t)


class Slugs:
    """context_slug per (page, diff_kind): the judge key when it is a valid slug, else idx01, idx02, ..."""

    def __init__(self):
        self.n: dict = {}

    def get(self, page: str, kind: str, preferred: str = "") -> str:
        if preferred:
            return preferred
        k = (page, kind)
        self.n[k] = self.n.get(k, 0) + 1
        return f"idx{self.n[k]:02d}"


def oracle_finding(o: dict, check: dict | None, hp: str) -> tuple[dict, str, str]:
    """A structure-oracle difference the judge confirmed, shaped like a judge finding. Returns (finding,
    diff_kind, preferred slug). The judge's confirmation evidence (source values, code lines) is carried along."""
    dk = {"missing": "missing_element", "extra": "extra_element", "order": "layout_drift",
          "render": "missing_element", "font": "font_mismatch"}[o["category"]]
    said = str((check or {}).get("evidence") or "").strip()
    files = ets_files(hp, said)
    f = {"category": {"missing_element": "missing", "extra_element": "extra", "layout_drift": "layout",
                      "font_mismatch": "font"}[dk],
         "severity": "medium" if o["category"] == "font" else "high", "description": o["description"],
         "android": o.get("android") or ("安卓有此元素" if o["category"] != "extra" else "安卓无此元素"),
         "harmony": o.get("harmony") or o["description"], "is_migration_bug": True, "frame": o["frame"],
         "evidence": f"结构 oracle {o['id']}" + (f"；判图确认：{said}" if said else ""),
         "element": o.get("text") if o["category"] in ("missing", "extra", "render") else None,
         "category_pattern": "render_invisible" if o["category"] == "render" else None,
         "suggested_files": files}
    if o["category"] == "render":
        f["description"] = f"「{o.get('text')}」节点在但画不出来：{o['description']}"
    if o.get("whole_list"):  # one finding for a whole empty list, named as such (not after its first item)
        f["title_text"] = f"整块列表内容为空（安卓 {o.get('count')} 项，如「{o.get('text')}」）"
    if o["category"] == "font":
        r = o.get("ratio") or 1
        f["title_text"] = f"{o.get('text_label') or '「' + str(o.get('text')) + '」'}字号{'偏大' if r > 1 else '偏小'}（墨迹 ×{r}）"
        m = TEXTSIZE_RE.search(said)
        if m:
            f["android"] = f"字号 {m.group(1)}{m.group(2)}" + (f"（{m.group(3)}）" if m.group(3) else "") + f"；{f['android']}"
    pref = ""
    if o["category"] == "font" and files:
        pref = fixfiles.ascii_slug(os.path.splitext(os.path.basename(files[0]))[0] + " font")
    elif o["category"] in ("missing", "extra", "render"):
        pref = fixfiles.ascii_slug(o.get("text") or "")
    return f, dk, pref


def write(store: Store, plan: Plan, rnd: int, cfg: dict, log=print) -> int:
    hp = cfg["hmos_project"]
    rdir = store.round_dir(rnd)
    pairs = read_json(os.path.join(rdir, "pairs.json"))
    if not pairs:
        log(f"[vvs] no pairs.json for round-{rnd}: run `vvs.py pairs` first")
        return 2
    fix_dir = fix_root(hp, rnd)
    marker = os.path.join(fix_dir, "_source.json")
    if os.path.isdir(fix_dir) and os.listdir(fix_dir) and not os.path.exists(marker):
        log(f"[vvs] {fix_dir} exists and was written by another run; refusing to overwrite (start a new round)")
        return 2
    missing, invalid, warnings = [], [], []
    results = {}
    from .pairs import oracle_items
    for it in pairs["items"]:
        path = None
        if it["verdict"] == "judge":
            path = os.path.join(rdir, "judge", "results", it["android"] + ".json")
        elif it["verdict"] in ("judged", "carried") and it.get("result"):
            path = it["result"]  # judged: a re-run of tickets in the same round; carried: an earlier round's result
        if not path:
            continue
        res = read_json(path)
        if res is None:
            missing.append(it["android"])
            continue
        oids = [o["id"] for o in oracle_items(it)] if it["verdict"] == "judge" else None
        fixed = normalize_keys(res)
        if fixed:
            write_json(path, res)
            warnings.append(f"{it['android']}: keys normalized " + ", ".join(f"{a}->{b}" for a, b in fixed[:3]))
        errs, warns = validate_result(res, it["android"], hp, oids)
        warnings += [f"{it['android']}: {w}" for w in warns]
        if errs:
            invalid.append((it["android"], errs))
            continue
        results[it["android"]] = (res, path)
        if it["verdict"] == "judge":
            it["verdict"], it["result"] = "judged", path
    if missing or invalid:
        for pid in missing:
            log(f"[vvs] MISSING judge result: {pid}")
        for pid, errs in invalid:
            log(f"[vvs] INVALID judge result {pid}: " + "; ".join(errs[:6]))
        log(f"[vvs] round-{rnd}: {len(missing)} missing, {len(invalid)} invalid results; fix them and run tickets again")
        return 2
    write_json(os.path.join(rdir, "pairs.json"), pairs)
    # a fresh round directory: only this skill's files (marker checked above). What fixers or people already
    # wrote into this round's files (section 6, disposition) is read first and carried into the new files.
    same_round = read_round(fix_dir)
    for d, _, files in os.walk(fix_dir):
        for name in files:
            if name.endswith(".md"):
                os.remove(os.path.join(d, name))
    idx = source.index(store, cfg)
    ctx = fixfiles.Ctx(store, plan, cfg, rnd, idx)
    by_pid = {it["android"]: it for it in pairs["items"]}
    slugs = Slugs()
    tickets, withdrawn = [], []
    stats = {"oracle_confirmed": 0, "oracle_refuted": 0, "icon_total": 0, "icon_failed": 0, "sib_total": 0,
             "sib_failed": 0, "data_only": 0}
    crash_of: dict = {}
    for pid, (res, path) in results.items():
        it = by_pid[pid]
        page = layout.page_id(pid)
        fdata = frame_data(it)
        rpath = layout.rel(hp, path)
        stats["data_only"] += len(res.get("data_only_differences") or [])
        if res["verdict"] == "pair_mismatch":
            t = fixfiles.nav_failed(ctx, it, "wrong_target", by_pid, res)
            tickets.append(t)
            crash_of[pid] = t
            continue
        kept = []
        for f in res.get("findings") or []:
            if not f.get("is_migration_bug"):
                continue
            why = recheck(f, it, fdata)
            if why:
                withdrawn.append({"android": pid, "key": f.get("key"), "description": f.get("description"), "why": why})
                continue
            low = downgrade(f, fdata)
            if low:
                f = {**f, "severity": "low", "evidence": (str(f.get("evidence") or "") + "；机械复核：" + low).strip("；")}
                withdrawn.append({"android": pid, "key": f.get("key"), "description": f.get("description"),
                                  "why": "降为低级：" + low})
            kept.append(f)
            dk = fixfiles.DIFF_KIND.get(f.get("category"), "component_mismatch")
            slug = slugs.get(page, dk, fixfiles.key_slug(f.get("key")))
            tickets.append(fixfiles.align(ctx, it, f, res, source_lines(idx, it, fdata, f), slug, result_path=rpath))
        flow = any(f.get("category") == "flow" for f in kept)
        checks = {c.get("id"): c for c in res.get("oracle_checks") or [] if isinstance(c, dict)}
        decisions = {k: c.get("decision") for k, c in checks.items()}
        stats["oracle_confirmed"] += sum(1 for v in decisions.values() if v == "confirmed")
        stats["oracle_refuted"] += sum(1 for v in decisions.values() if v == "refuted")
        # the judge names duplicates itself: an entry with same_as points at the one entry that carries the difference
        targets = {f.get("key") for f in kept} | {k for k, v in decisions.items() if v == "confirmed"}
        dup = lambda c: bool(isinstance(c, dict) and c.get("same_as") in targets and c.get("same_as") != c.get("id"))
        covered = " ".join(_finding_text(f) for f in kept)
        covered_font = " ".join(_finding_text(f) for f in kept if f.get("category") == "font")
        fonts: dict = {}
        for o in oracle_items(it):
            if decisions.get(o["id"]) != "confirmed" or dup(checks.get(o["id"])):
                continue
            if flow and o["category"] in ("missing", "extra"):
                continue  # explained by the flow finding (a dialog only one side has)
            if o.get("text") and hui.norm_label(o["text"]) in (covered_font if o["category"] == "font" else covered):
                continue  # the judge already wrote it up with more detail
            if o["category"] == "font":  # one file per frame / ratio / code: the same style on several rows
                g = (o["frame"], o.get("ratio"), tuple(ets_files(hp, str(checks.get(o["id"], {}).get("evidence") or ""))))
                fonts.setdefault(g, []).append(o)
                continue
            f, dk, pref = oracle_finding(o, checks.get(o["id"]), hp)
            refs = source_lines(idx, it, fdata, {"description": o.get("text") or o["description"]})
            tickets.append(fixfiles.align(ctx, it, f, res, refs, slugs.get(page, dk, pref), dk, bool(f["suggested_files"]),
                                          result_path=f"结构 oracle {o['id']}"))
        for group in fonts.values():
            o, check = merge_font_items(group, checks)
            f, dk, pref = oracle_finding(o, check, hp)
            refs = source_lines(idx, it, fdata, {"description": o["text"]})
            tickets.append(fixfiles.align(ctx, it, f, res, refs, slugs.get(page, dk, pref), dk, bool(f["suggested_files"]),
                                          result_path=f"结构 oracle {o['id']}"))
        texts = [_finding_text(f) for f in kept]
        data_texts = [hui.norm_label(str(d.get("what", ""))) for d in res.get("data_only_differences") or []
                      if isinstance(d, dict)]
        for kind, key, field in (("icon", "icon_semantic_checks", "context"), ("sib", "siblings_order_checks", "container")):
            for c in res.get(key) or []:
                if not isinstance(c, dict):
                    continue
                stats[f"{kind}_total"] += 1
                if c.get("match") is not False:
                    continue
                stats[f"{kind}_failed"] += 1
                name = str(c.get(field) or "")
                if dup(c):
                    continue  # the judge says another entry carries this difference
                if flow:
                    continue  # the two screens differ by a flow (a dialog only one side has): checked by that finding
                if overlaps(name, texts):
                    continue  # the judge also wrote it as a finding
                if kind == "sib" and overlaps(name, data_texts):
                    continue  # order of list / random content, proven by the Android source
                if kind == "sib" and not (c.get("android_order") and c.get("hmos_order")):
                    continue  # nothing to order on one side: an absence, which the missing finding covers
                dk = "icon_mismatch" if kind == "icon" else "layout_drift"
                refs = source_lines(idx, it, fdata, {"description": name})
                tickets.append(fixfiles.check_ticket(ctx, it, c, "icon" if kind == "icon" else "siblings", res, refs,
                                                     slugs.get(page, dk, fixfiles.ascii_slug(name))))
        it["withdrawn"] = [w for w in withdrawn if w["android"] == pid]
    # walk gaps: edges Android walked and HarmonyOS did not, then placeholders for everything not captured
    rank = {p: i for i, p in enumerate(plan.order())}
    for it in sorted(pairs["items"], key=lambda x: rank.get(x["android"], len(rank))):  # parents first
        if it["verdict"] != "not_paired":
            continue
        code = (it.get("gap") or {}).get("code") if it.get("status") == "gap" else None
        if any(a in crash_of for a in plan.ancestors(it["android"])):
            continue  # the parent already failed (a nav ticket, or HarmonyOS showed another page): placeholder below
        if code in fixfiles.NAV:
            t = fixfiles.nav_failed(ctx, it, code, by_pid)
        elif code == "left_app":
            t = fixfiles.app_crash(ctx, it)
        else:
            continue
        tickets.append(t)
        crash_of[it["android"]] = t
    for it in pairs["items"]:
        if it["verdict"] != "not_paired" or it["android"] in crash_of:
            continue
        pid, st = it["android"], it.get("status")
        up = next((a for a in plan.ancestors(pid) if a in crash_of), None)
        if up:
            ref = f"spec/fix/round-{rnd}/ui/{crash_of[up]['id']}.md"
            tickets.append(fixfiles.blocked(ctx, it, f"上游「{plan.units[up].label}」这一步鸿蒙没走通，本轮未采到",
                                            ref, f"{plan.units[up].label} → {plan.units[pid].label}", "pending_upstream_fix"))
        elif st == "needs_drive":
            why = f"自动走查到不了（{it.get('reason') or '需要手驱'}），按报告用 drive 补采"
            tickets.append(fixfiles.blocked(ctx, it, why, None, str(it.get("reason") or "needs_drive"), "pending_recapture"))
        elif (it.get("gap") or {}).get("code") == "content_not_found":
            step = plan.units[pid].step
            why = (f"安卓点的是列表内容「{step.label if step else ''}」，鸿蒙同一列表里没有这一项也没有同类项"
                   "（列表为空或两端数据不同），本轮未采到；列表本身缺失由上级页的对比单负责")
            tickets.append(fixfiles.blocked(ctx, it, why, None, "content_not_found", "pending_recapture"))
        else:
            code = (it.get("gap") or {}).get("code") or st or "missing"
            tickets.append(fixfiles.blocked(ctx, it, f"本轮未采到（{code}），下一轮重采", None, str(code), "pending_recapture"))
    seen = set()
    for t in tickets:
        base, n = t["id"], 2
        while t["id"] in seen:
            t["id"] = f"{base}-{n}"
            n += 1
        seen.add(t["id"])
        t["front"]["id"] = t["id"]
    tickets += fixfiles.systemic(ctx, tickets)
    unified = unify_severity(tickets)
    stubborn = carry_forward(store, hp, rnd, tickets, same_round)
    when = now_iso()
    fixfiles.write_files(fix_dir, tickets)
    write_json(marker, {"tool": "visual-verify-speed", "round": rnd, "created": when, "withdrawn": withdrawn})
    write_json(os.path.join(rdir, "pairs.json"), pairs)
    pages, n_compared, n_blocked = summary_pages(ctx, pairs, tickets, results)
    checks_rows = [f"| pages screenshot-compared | {n_compared}/{len(pairs['items'])} |",
                   f"| auto_pass（度量预筛一致，未判图） | {sum(1 for it in pairs['items'] if it['verdict'] == 'auto_pass')} |",
                   f"| 结构 oracle 条目 | confirmed {stats['oracle_confirmed']} / refuted {stats['oracle_refuted']} |",
                   f"| siblings_order_checks | {stats['sib_total']} 项，失败 {stats['sib_failed']} |",
                   f"| icon_semantic_checks | {stats['icon_total']} 项，失败 {stats['icon_failed']} |",
                   f"| 出单前机械复核 | 撤回 {sum(1 for w in withdrawn if not w['why'].startswith('降为'))} / "
                   f"降级 {sum(1 for w in withdrawn if w['why'].startswith('降为'))} |",
                   f"| 只比结构的数据差异（附安卓源码依据） | {stats['data_only']} |",
                   f"| 同一问题跨页统一级别 | {unified} 张 |"]
    prev = fix_root(hp, rnd - 1)
    unchanged = fixfiles.write_delta(fix_dir, prev, rnd, tickets) if rnd > 0 and os.path.isdir(prev) else None
    fixfiles.write_index(fix_dir, rnd, tickets, when)
    fixfiles.write_summary(fix_dir, rnd, tickets, pages, checks_rows, when, unchanged, stubborn)
    open_t = [t for t in tickets if t["front"]["kind"] not in ("BLOCKED",)]
    layout.write_state(hp, rnd, {"pages_compared": n_compared, "pages_blocked": n_blocked, "failed_total": len(open_t),
                                 "ui_findings": sum(1 for t in open_t if t["layer"].startswith("ui")),
                                 "feat_findings": sum(1 for t in open_t if t["layer"].startswith("feat")),
                                 "siblings_order_checks": stats["sib_total"], "icon_semantic_checks": stats["icon_total"]},
                       when)
    store.event("tickets", {"round": rnd, "count": len(tickets)})
    for w in warnings[:20]:
        log(f"[vvs] warning: {w}")
    log(f"[vvs] round-{rnd}: {len(tickets)} fix files -> {fix_dir}" +
        (f"; {len(withdrawn)} judge findings withdrawn/lowered by the mechanical check" if withdrawn else ""))
    from .selfcheck import check
    fails = check(hp, fix_dir)
    for f in fails[:30]:
        log(f"[vvs] SELF-CHECK ❌ {f}")
    log(f"[vvs] fix self-check: {'PASS' if not fails else f'FAIL {len(fails)}'} (round-{rnd})")
    return 1 if fails else 0


def unify_severity(tickets: list) -> int:
    """The same problem on several pages gets one level: same judge key, or members of one SYSTEMIC file, take
    the most common level among them (a tie takes the higher one). Returns how many files changed level."""
    from collections import Counter
    aligns = {t["id"]: t for t in tickets if t["front"]["kind"] == "ALIGNMENT_DIFF"}
    groups: list = []
    by_key: dict = {}
    for t in aligns.values():
        k = t["meta"].get("key")
        if k and not str(k).startswith("idx"):
            by_key.setdefault(k, []).append(t)
    groups += [g for g in by_key.values() if len({t["meta"]["page"] for t in g}) > 1]
    groups += [[aligns[i] for i in t["meta"]["members"] if i in aligns] for t in tickets
               if t["front"]["kind"] == "SYSTEMIC"]
    order = {"P0": 0, "P1": 1, "P2": 2}
    mm_of = {"P0": "high", "P1": "medium", "P2": "low"}
    changed = set()
    for g in groups:
        if len(g) < 2:
            continue
        votes = Counter(t["front"]["severity"] for t in g)
        best = max(votes.values())
        level = min((s for s, n in votes.items() if n == best), key=lambda s: order.get(s, 9))
        for t in g:
            if t["front"]["severity"] != level:
                t["front"]["severity"] = level
                t["front"]["multimodal_severity"] = mm_of[level]
                t["meta"]["sev"], t["meta"]["mm"] = level, mm_of[level]
                changed.add(t["id"])
    for t in tickets:  # a SYSTEMIC file takes the level its members ended with
        if t["front"]["kind"] == "SYSTEMIC":
            levels = [aligns[i]["front"]["severity"] for i in t["meta"]["members"] if i in aligns]
            if levels:
                t["front"]["severity"] = min(levels, key=lambda s: order.get(s, 9))
                t["front"]["multimodal_severity"] = mm_of[t["front"]["severity"]]
    return len(changed)


HUMAN_DISPOSITIONS = ("skipped", "manual_review", "wont_fix", "problematic")
STUBBORN_ROUNDS = 3     # the same fix file open in this many rounds ...
STUBBORN_ATTEMPTS = 3   # ... or this many fix attempts: focused mode, change the hypothesis
MANUAL_ATTEMPTS = 5     # still open after this many attempts: hand it to a person


def read_round(fix_dir: str) -> dict:
    """{id: {"history": section-6 attempts, "front": scalar front matter}} of one round directory."""
    from .selfcheck import front_of
    out = {}
    for d, _, files in os.walk(fix_dir):
        for name in files:
            if name.endswith(".md") and not name.startswith("_"):
                text = open(os.path.join(d, name), encoding="utf-8").read()
                fm, _ = front_of(text)
                out[name[:-3]] = {"history": fixfiles.section6(text), "front": fm}
    return out


def carry_forward(store, hp: str, rnd: int, tickets: list, same_round: dict) -> list:
    """Section-6 history, human dispositions and last round's fixcheck flags follow a fix file across rounds
    (same id); files open for many rounds / attempts are marked stubborn or handed to a person."""
    from . import fixcheck
    prev = read_round(fix_root(hp, rnd - 1)) if rnd > 0 else {}
    seen: dict = {}
    for k in range(rnd):
        for tid in fixfiles.ids_of(fix_root(hp, k)):
            seen[tid] = seen.get(tid, 0) + 1
    flags = fixcheck.flags_for(store, rnd - 1) if rnd > 0 else {}
    stubborn = []
    for t in tickets:
        if t["front"]["kind"] == "BLOCKED":
            continue
        tid = t["id"]
        old = same_round.get(tid) or prev.get(tid) or {}
        history = old.get("history", "")
        n_att = len(fixcheck.ATTEMPT_RE.findall(history))
        rounds = seen.get(tid, 0) + 1
        disp = (same_round.get(tid) or {}).get("front", {}).get("disposition") or \
            (prev.get(tid) or {}).get("front", {}).get("disposition")
        notes = []
        if disp in HUMAN_DISPOSITIONS:
            src = (same_round.get(tid) or prev.get(tid))["front"]
            t["front"].update(disposition=disp, disposition_reason=src.get("disposition_reason"),
                              disposition_set_at_round=int(src.get("disposition_set_at_round") or rnd))
        elif n_att >= MANUAL_ATTEMPTS:
            t["front"].update(disposition="manual_review", disposition_reason=f"修复 {n_att} 次仍未通过，转人工（见 §6）",
                              disposition_set_at_round=rnd)
            stubborn.append((tid, rounds, n_att, "转人工"))
        elif rounds >= STUBBORN_ROUNDS or n_att >= STUBBORN_ATTEMPTS:
            notes.append(f"顽固问题：已出现 {rounds} 轮 / 修复 {n_att} 次仍未通过——读完下面全部历史，"
                         f"换一个假设根因（不同文件 / 不同属性 / 不同层级），并在「未做的事」里写明排除了哪些方向")
            stubborn.append((tid, rounds, n_att, "顽固"))
        for line in flags.get(tid, []):
            notes.append(f"上轮修复复核：{line} —— 本轮必须换方向")
        t["body"] = fixfiles.with_history(t["body"], notes, history)
    return stubborn


def summary_pages(ctx, pairs: dict, tickets: list, results: dict) -> tuple[list, int, int]:
    """One row per unit. A unit's status comes from every ticket about it, wherever the ticket is filed (a nav
    ticket lives under the page with the entry, but it is about the unit it failed to reach)."""
    by_unit: dict = {}
    for t in tickets:
        by_unit.setdefault(t["meta"].get("pid"), []).append(t)
    rows, compared, blocked_n = [], 0, 0
    for it in pairs["items"]:
        page = layout.page_id(it["android"])
        ts = by_unit.get(it["android"], [])
        aligns = [t for t in ts if t["front"]["kind"] == "ALIGNMENT_DIFF"]
        mm = {k: sum(1 for t in aligns if t["meta"].get("mm") == k) for k in ("high", "medium", "low")}
        if it["verdict"] == "not_paired":
            blocked_n += 1
            status = "🚫 blocked" if any(t["front"]["kind"] in ("CRASH", "BLOCKED") for t in ts) else "⚠️ not_arrived"
            cap, sim = "-", "-"
        else:
            compared += 1
            cap = ctx.capture_mode(it)
            res = (results.get(it["android"]) or (None,))[0]
            sim = f"{fixfiles.similarity(res, it):.2f}"
            if any(t["front"]["severity"] == "P0" for t in ts):
                status = "❌ fail"
            elif ts:
                status = "🔄 partial"
            else:
                status = "✅ pass"
        rows.append(f"| {page} | {it.get('label', '')} | {cap} | {sim} | {mm['high']} | "
                    f"{mm['medium']} | {mm['low']} | 1 | {status} |")
    return rows, compared, blocked_n
