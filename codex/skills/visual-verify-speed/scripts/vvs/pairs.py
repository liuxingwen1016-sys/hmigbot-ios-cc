"""Pairs of one round: Android unit <-> HarmonyOS capture, measured, pre-filtered, grouped for the judges.

Pre-filter (no model): a pair goes to a judge unless all of these hold
  - the pairing is confirmed (texts overlap) and both sides have the same number of frames
  - metric_diff (bundled measurement diff) finds no medium/high difference on any frame
  - no Android text is missing on HarmonyOS
  - the two first frames look alike (average-hash distance <= prefilter.ahash_max)
A pair whose HarmonyOS evidence did not change since a judged round carries that verdict over.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess

from . import layout, hui, imgutil, oracle
from .android import Plan, xml_texts
from .metric import metric_diff, metric_pack
from .store import Store, now_iso, read_json, write_json

TOLERANCE = os.path.join(os.path.dirname(__file__), "metric", "tolerance.json")
DEFAULT_PREFILTER = {"ahash_max": 10, "max_pairs_per_batch": 4, "max_frames_per_batch": 10,
                     "offset_max": 4.0, "size_max": 4.0}
IMMERSIVE_RE = re.compile(r"enableEdgeToEdge|setDecorFitsSystemWindows\s*\(\s*\w+\s*,\s*false|"
                          r"SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN|FLAG_TRANSLUCENT_STATUS|fitsSystemWindows=\"false\"|"
                          r"statusBarColor\s*=\s*Color\.TRANSPARENT|transparentStatusBar|ImmersionBar")


def filter_bundle(raw: bytes, bundle: str) -> dict:
    """Only the windows of the app (dumpLayout -i lists every window: status bar, desktop, dialogs)."""
    starts = [i for i in (raw.find(b"{"), raw.find(b"[")) if i >= 0]
    data = json.loads(raw[min(starts):].decode("utf-8", errors="replace"))
    wins = data if isinstance(data, list) else data.get("children") or []
    kids = [c for c in wins if (c.get("attributes") or {}).get("bundleName") == bundle]

    def hidden(el):
        return str((el.get("attributes") or {}).get("visible", "true")).lower() == "false"

    def prune(el):  # metric_pack does not know about invisible subtrees
        return {**el, "children": [prune(c) for c in el.get("children") or () if not hidden(c)]}
    kids = [prune(k) for k in kids] or wins
    return {"attributes": {"type": "", "bounds": (kids[0].get("attributes") or {}).get("bounds", "") if kids else ""},
            "children": kids}


def tolerance() -> dict:
    return {k: v for k, v in read_json(TOLERANCE, {}).items() if not k.startswith("_")}


def pack(dump: str, png: str | None, density: float | None, platform: str) -> dict:
    ns = argparse.Namespace(platform=platform, dump=dump, png=png, density=density or 0, tol=40, out=None)
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        metric_pack.build_pack(ns)
    return json.loads(buf.getvalue())


DESIGN_RE = re.compile(r'android:name="design_width_in_dp"\s*android:value="(\d+)"', re.S)


def autosize_density(src: str | None, screen_w: int | None) -> tuple:
    """AndroidAutoSize-style apps render at screen_width_px / design_width_in_dp, not at the system density."""
    if not src or not screen_w or not os.path.isdir(src):
        return None, None
    try:
        out = subprocess.run(["grep", "-rl", "--include=AndroidManifest.xml", "design_width_in_dp", src],
                             capture_output=True, text=True, timeout=60).stdout.split()
    except Exception:
        return None, None
    for path in out:
        if "/build/" in path:
            continue
        try:
            text = open(path, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        m = DESIGN_RE.search(text) or re.search(r'design_width_in_dp"[^>]*?android:value="(\d+)"', text, re.S)
        if m and int(m.group(1)) > 0:
            return round(screen_w / int(m.group(1)), 3), f"{path}: design_width_in_dp={m.group(1)}"
    return None, None


def shared_facts(cfg: dict, density_a, density_h, screen_w=None) -> dict:
    """Project-level facts computed once and handed to every judge."""
    facts = {"android_density": density_a, "harmony_density": density_h, "immersive_android": None}
    eff, why = autosize_density(cfg.get("android_project"), screen_w)
    if eff and density_a and abs(eff - density_a) > 0.05:
        facts["android_density_effective"] = eff
        facts["android_density_note"] = f"屏幕适配库按设计宽度换算，实际 {eff} px/dp（系统 {density_a}）；来源 {why}"
    src = cfg.get("android_project")
    if src and os.path.isdir(src):
        try:
            out = subprocess.run(["grep", "-rnE", IMMERSIVE_RE.pattern, "--include=*.kt", "--include=*.java",
                                  "--include=*.xml", src], capture_output=True, text=True, timeout=60).stdout
            hits = [l[:200] for l in out.splitlines() if "/build/" not in l][:8]
            facts["immersive_android"] = hits or "zero hits (Android draws below the system bars)"
        except Exception as exc:
            facts["immersive_android"] = f"not checked: {exc}"
    return facts


def evidence_hash(h_meta: dict, store: Store) -> str:
    shots = h_meta.get("screenshots") or []
    hashes = [imgutil.ahash(store.abs_h(p)) or "" for p in shots]
    texts = "|".join((h_meta.get("sig") or {}).get("texts") or [])
    import hashlib
    return hashlib.sha1(("/".join(hashes) + "#" + texts).encode()).hexdigest()[:16]


def measure_item(job: dict) -> dict:
    """One pair: side-by-side images + metric packs/diffs per frame (runs in a worker process)."""
    frames, worst = [], {"high": 0, "medium": 0, "low": 0}
    a_frames, h_frames = job["android_frames"], job["harmony_frames"]
    for k in range(max(len(a_frames), len(h_frames))):
        a_png = a_frames[k] if k < len(a_frames) else None
        h_png = h_frames[k] if k < len(h_frames) else None
        fr = {"k": k, "android": a_png, "harmony": h_png}
        sbs = job["sbs_paths"][k]
        try:
            fr["sbs"] = imgutil.side_by_side(a_png, h_png, sbs, job["label"][:40], job["density_a"], job["density_h"])
        except Exception as exc:
            fr["sbs"], fr["sbs_error"] = None, str(exc)[:200]
        if a_png and h_png:
            try:
                with open(job["harmony_views"][k], "rb") as f:
                    raw = f.read()
                o = oracle.frame_oracle(job["android_xmls"][k], raw, job["density_a"], job["density_h"],
                                        job["bundle"], job.get("package", ""), a_png, h_png,
                                        a_top_px=job.get("a_top_px"))
                opath = os.path.join(job["rdir"], "metric", f"{job['pid']}__f{k}.oracle.json")
                write_json(opath, o)
                fr["oracle"] = {"file": opath, **o["summary"], "common_offset": o["common_offset"]}
            except Exception as exc:
                fr["oracle"] = {"error": str(exc)[:200]}
            try:
                hdump = os.path.join(job["rdir"], "metric", f"{job['pid']}__h{k}.json")
                with open(job["harmony_views"][k], "rb") as f:
                    write_json(hdump, filter_bundle(f.read(), job["bundle"]))
                A = pack(job["android_xmls"][k], a_png, job["density_a"], "android")
                H = pack(hdump, h_png, job["density_h"], "hmos")
                md = metric_diff.compare(A, H, job["tol"], job["pid"])
                sev = {"high": 0, "medium": 0, "low": 0}
                for d in md["differences"]:
                    sev[d.get("severity", "low")] = sev.get(d.get("severity", "low"), 0) + 1
                for kk in worst:
                    worst[kk] += sev.get(kk, 0)
                mpath = os.path.join(job["rdir"], "metric", f"{job['pid']}__f{k}.mdiff.json")
                write_json(mpath, md)
                fr["metric"] = {"file": mpath, **sev, "top": [d["description"] for d in md["differences"][:12]]}
            except Exception as exc:
                fr["metric"] = {"error": str(exc)[:200]}
        frames.append(fr)
    dist = imgutil.hamming(imgutil.ahash(a_frames[0]) if a_frames else None,
                           imgutil.ahash(h_frames[0]) if h_frames else None)
    return {"pid": job["pid"], "frames": frames, "worst": worst, "ahash_distance": dist}


def build(store: Store, plan: Plan, rnd: int, cfg: dict, profile: dict, log=print, workers: int = 0) -> dict:
    pre = {**DEFAULT_PREFILTER, **(profile.get("prefilter") or {})}
    rdir = store.round_dir(rnd)
    for sub in ("metric", "judge/results"):
        os.makedirs(os.path.join(rdir, sub), exist_ok=True)
    state = store.state(rnd) or {}
    units_state = state.get("units", {})
    hidx = store.index_by_pair()
    from . import PIPELINE_VERSION
    same_round = {it["android"]: it for it in (read_json(os.path.join(rdir, "pairs.json"), {}) or {}).get("items", [])}
    prev_items = {}
    for r in range(rnd - 1, -1, -1):
        old = read_json(os.path.join(store.round_dir(r), "pairs.json"))
        if old:
            for it in old["items"]:
                prev_items.setdefault(it["android"], {**it, "_round": r})
    bundle = profile["bundle"]
    tol = tolerance()
    density_h = state.get("density") or cfg.get("harmony_density")
    density_a0 = next((u.density for u in plan.units.values() if u.density), None)
    scr = plan.screen_of(plan.root.frames[0][1]) if plan.root and plan.root.frames else None
    facts = shared_facts(cfg, density_a0, density_h, scr[0] if scr else None)
    density_eff = facts.get("android_density_effective")
    a_status = (read_json(os.path.join(plan.out, "_aft", "state.json"), {}) or {}).get("status_bar_px")  # when recorded
    items, counts, jobs = [], {}, []
    for pid in plan.order():
        u = plan.units[pid]
        st = units_state.get(pid, {})
        h = hidx.get(pid)
        it = {"android": pid, "kind": u.kind, "label": u.label, "activity": u.activity,
              "android_frames": [plan._abs(p) for p, _ in u.frames],
              "android_xmls": [plan._abs(x) for _, x in u.frames]}
        status = st.get("status") or ("carried" if h else "pending")
        if status in ("gap", "blocked", "needs_drive", "pending") and not (status == "pending" and h):
            gap = next((g for g in reversed(state.get("gaps", [])) if g.get("android") == pid), None)
            it.update(verdict="not_paired", status=status, gap=gap, blocked_by=st.get("blocked_by"),
                      reason=st.get("reason"))
            if status == "blocked" and u.parent and units_state.get(u.parent, {}).get("status") in ("done", "carried"):
                it["blocked_by"] = st.get("blocked_by")
            items.append(it)
            counts[it["verdict"]] = counts.get(it["verdict"], 0) + 1
            continue
        if not h:
            it.update(verdict="not_paired", status="missing")
            items.append(it)
            counts["not_paired"] = counts.get("not_paired", 0) + 1
            continue
        pair = h.get("pair") or {}
        it.update(status="paired", harmony_unit=h["unit_dir"], harmony_round=h.get("round"),
                  harmony_frames=[store.abs_h(p) for p in h.get("screenshots") or []],
                  harmony_views=[store.abs_h(p) for p in h.get("view_jsons") or []],
                  harmony_page=(h.get("harmony") or {}).get("page_path"),
                  confidence=pair.get("confidence"), method=pair.get("method"),
                  text_overlap=pair.get("text_overlap"), path_methods=pair.get("path_methods"))
        it["evidence_hash"] = evidence_hash(h, store)
        it["_h_texts"] = list((h.get("sig") or {}).get("texts") or [])
        it["pipeline"] = PIPELINE_VERSION
        same = same_round.get(pid)
        if same and same.get("evidence_hash") == it["evidence_hash"] and same.get("pipeline") == PIPELINE_VERSION:
            res = os.path.join(rdir, "judge", "results", pid + ".json")
            done = same.get("verdict") == "auto_pass" or (same.get("verdict") in ("judge", "judged") and os.path.exists(res))
            if done:  # this round already measured and judged the same evidence (pairs re-run, or run during the walk)
                it.pop("_h_texts", None)
                keep = {k: same.get(k) for k in ("frames", "prefilter", "missing_texts", "extra_texts", "ahash_distance",
                                                 "metric_worst", "canonical", "sentinel")}
                it.update(keep, verdict="auto_pass" if same["verdict"] == "auto_pass" else "judged",
                          result=None if same["verdict"] == "auto_pass" else res)
                items.append(it)
                counts[it["verdict"]] = counts.get(it["verdict"], 0) + 1
                continue
        prev = prev_items.get(pid)
        if prev and prev.get("verdict") in ("auto_pass", "judged", "carried") and prev.get("pipeline") == PIPELINE_VERSION \
                and (prev.get("harmony_unit") == it["harmony_unit"] or prev.get("evidence_hash") == it["evidence_hash"]):
            if not sentinel(pid, rnd):
                it.pop("_h_texts", None)
                it.update(verdict="carried", carried_from=prev.get("carried_from", prev["_round"]),
                          result=prev.get("result"), prefilter=prev.get("prefilter"), frames=prev.get("frames"),
                          canonical=prev.get("canonical"))  # the evidence of the round that judged it
                items.append(it)
                counts["carried"] = counts.get("carried", 0) + 1
                continue
            it["sentinel"] = True  # spot check: an unchanged pair judged again under the same rules
        it["canonical"] = layout.place(store, cfg, rnd, it)
        jobs.append({"pid": pid, "label": u.label, "rdir": rdir, "bundle": bundle, "tol": tol, "package": plan.package,
                     "sbs_paths": it["canonical"]["sbs"],
                     "android_frames": it["android_frames"], "android_xmls": it["android_xmls"],
                     "harmony_frames": it["harmony_frames"], "harmony_views": it["harmony_views"],
                     "density_a": density_eff or u.density, "density_h": density_h,
                     "a_top_px": a_status})
        items.append(it)
    results = {}
    if jobs:
        n = workers or max(1, min(8, (os.cpu_count() or 2) - 1))
        if n > 1 and len(jobs) > 1:
            from concurrent.futures import ProcessPoolExecutor
            with ProcessPoolExecutor(max_workers=n) as ex:
                for r in ex.map(measure_item, jobs):
                    results[r["pid"]] = r
        else:
            for j in jobs:
                r = measure_item(j)
                results[r["pid"]] = r
    for it in items:
        r = results.get(it["android"])
        if r is None:
            continue
        a_n, h_n = len(it["android_frames"]), len(it["harmony_frames"])
        worst, frames, dist = r["worst"], r["frames"], r["ahash_distance"]
        a_texts = {hui.DIGITS.sub("#", t) for t in plan.texts(it["android"])}
        h_texts = set(it.pop("_h_texts"))
        missing = sorted(a_texts - h_texts)
        extra = sorted(h_texts - a_texts)
        orc = [f.get("oracle") or {} for f in frames if f.get("oracle")]
        oracle_clean = bool(orc) and all("error" not in o and not (o.get("missing") or o.get("extra") or o.get("order")
                                                                   or o.get("invisible") or o.get("font"))
                                          and o.get("max_offset", 0) <= pre["offset_max"]
                                          and o.get("max_size", 0) <= pre["size_max"] for o in orc)
        clean = (it["confidence"] == "confirmed" and a_n == h_n and worst["high"] == 0 and worst["medium"] == 0
                 and not missing and dist is not None and dist <= pre["ahash_max"] and oracle_clean
                 and not any("error" in (f.get("metric") or {}) for f in frames) and not it.get("sentinel"))
        canon = it.get("canonical") or {}
        lacking = [side for side in ("sbs", "harmony", "android")
                   if not (canon.get(side) or [None])[0] or not os.path.exists(canon[side][0])]
        if lacking:  # nothing to judge from: a capture debt, not a pass and not a finding
            it.pop("_h_texts", None)
            it.update(frames=frames, verdict="not_paired", status="missing_artifacts",
                      reason="缺少交付截图：" + "、".join(lacking))
            counts["not_paired"] = counts.get("not_paired", 0) + 1
            continue
        it.update(frames=frames, missing_texts=missing[:40], extra_texts=extra[:40], ahash_distance=dist,
                  metric_worst=worst, verdict="auto_pass" if clean else "judge",
                  prefilter={"confirmed": it["confidence"] == "confirmed", "frames_equal": a_n == h_n,
                             "oracle_clean": oracle_clean,
                             "metric_medium_high": worst["high"] + worst["medium"], "missing_texts": len(missing),
                             "ahash_distance": dist})
        counts[it["verdict"]] = counts.get(it["verdict"], 0) + 1
    for it in items:
        it.pop("_h_texts", None)
    out = {"round": rnd, "created": now_iso(), "android_out": plan.out, "bundle": bundle,
           "counts": counts, "facts": facts, "items": items}
    write_json(os.path.join(rdir, "pairs.json"), out)
    log(f"[vvs] pairs round-{rnd}: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    return out


SENTINEL_SHARE = 10  # 1 in N unchanged pairs is judged again each round


def sentinel(pid: str, rnd: int) -> bool:
    import hashlib
    return int(hashlib.sha1(f"{pid}:{rnd}".encode()).hexdigest(), 16) % SENTINEL_SHARE == 0


# ---------------------------------------------------------------- judge batches

def oracle_items(it: dict) -> list:
    """Hard structure-oracle differences of a pair (dynamic texts left out), numbered O1.. across frames."""
    out = []
    for fr in it.get("frames") or []:
        o = fr.get("oracle") or {}
        data = read_json(o.get("file", ""), {}) if o.get("file") else {}
        for d in (data.get("structure") or {}).get("differences", []):
            if d.get("dynamic_suspect"):
                continue
            out.append({"id": f"O{len(out) + 1}", "frame": fr["k"], "category": d["category"],
                        "text": d.get("text"), "description": d["description"],
                        **({"whole_list": True, "count": d.get("count")} if d.get("whole_list") else {})})
        for v in data.get("harmony_invisible") or []:
            out.append({"id": f"O{len(out) + 1}", "frame": fr["k"], "category": "render",
                        "text": v.get("label"), "description": f"鸿蒙「{v.get('label')}」({v.get('type')}) 节点存在但画不出来："
                                                               f"前景 {v['fg_bg'][0]} / 背景 {v['fg_bg'][1]}，bounds {v.get('bounds')}"})
        for v in data.get("font_suspects") or []:
            out.append({"id": f"O{len(out) + 1}", "frame": fr["k"], "category": "font", "text": v["text"], "ratio": v["ratio"],
                        "description": v["description"], "android": f"墨迹 {v['android_ink'][0]}×{v['android_ink'][1]}dp",
                        "harmony": f"墨迹 {v['harmony_ink'][0]}×{v['harmony_ink'][1]}vp（×{v['ratio']}）"})
    return out


def state_group(plan: Plan, pid: str) -> str:
    """Same Activity + same resource-id set = structurally isomorphic states."""
    u = plan.units[pid]
    rids = set()
    if u.frames:
        try:
            import xml.etree.ElementTree as ET
            for el in ET.parse(plan._abs(u.frames[0][1])).getroot().iter("node"):
                rid = (el.attrib.get("resource-id") or "").rsplit("/", 1)[-1]
                if rid:
                    rids.add(rid)
        except Exception:
            pass
    return f"{u.activity}|{hash(frozenset(rids)) & 0xffffff:06x}"


def batches(store: Store, plan: Plan, rnd: int, profile: dict, log=print, cfg: dict | None = None) -> list:
    pre = {**DEFAULT_PREFILTER, **(profile.get("prefilter") or {})}
    rdir = store.round_dir(rnd)
    pairs = read_json(os.path.join(rdir, "pairs.json"))
    todo = [it for it in pairs["items"] if it["verdict"] == "judge"]
    groups: dict = {}
    for it in todo:
        groups.setdefault(state_group(plan, it["android"]), []).append(it)
    out, cur, frames = [], [], 0
    for key in sorted(groups, key=lambda k: min(plan.units[i["android"]].number for i in groups[k])):
        for it in groups[key]:
            n = max(1, len(it.get("frames") or []))
            if cur and (len(cur) >= pre["max_pairs_per_batch"] or frames + n > pre["max_frames_per_batch"]):
                out.append(cur)
                cur, frames = [], 0
            cur.append(it)
            frames += n
    if cur:
        out.append(cur)
    prev_findings = previous_findings(store, rnd)
    from . import source
    idx = source.index(store, cfg or {}) if cfg else {}
    manifest = []
    for i, items in enumerate(out, 1):
        bid = f"batch_{i:02d}"
        path = os.path.join(rdir, "judge", f"{bid}.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(task_text(bid, items, pairs["facts"], rdir, prev_findings, plan, idx))
        manifest.append({"batch": bid, "task": path, "pairs": [it["android"] for it in items],
                         "results": [os.path.join(rdir, "judge", "results", it["android"] + ".json") for it in items]})
    write_json(os.path.join(rdir, "judge", "batches.json"), {"round": rnd, "created": now_iso(), "batches": manifest})
    log(f"[vvs] judge round-{rnd}: {len(todo)} pairs in {len(manifest)} batches -> {os.path.join(rdir, 'judge')}")
    return manifest


def previous_findings(store: Store, rnd: int) -> dict:
    out = {}
    for r in range(rnd - 1, -1, -1):
        d = os.path.join(store.round_dir(r), "judge", "results")
        if not os.path.isdir(d):
            continue
        for name in os.listdir(d):
            if name.endswith(".json") and name[:-5] not in out:
                res = read_json(os.path.join(d, name), {})
                out[name[:-5]] = [{"key": x.get("key"), "category": x.get("category"),
                                   "description": x.get("description")} for x in res.get("findings") or []]
    return out


def _page_rids(xml_path: str) -> list:
    try:
        text = open(xml_path, encoding="utf-8", errors="replace").read()
    except OSError:
        return []
    return [r.rsplit("/", 1)[-1] for r in re.findall(r'resource-id="([^"]+)"', text)
            if "/" in r and not r.startswith("android:")]


def task_text(bid: str, items: list, facts: dict, rdir: str, prev: dict, plan: Plan, idx: dict | None = None) -> str:
    from . import source
    lines = [f"# 判图任务 {bid}", "",
             "按 references/judge.md 的口径逐对判定。每对写一个结果文件（写完一对立刻落盘，不要攒到最后）。",
             "对比图两边是同一 dp 比例（红线每 50dp），只用来看颜色/图标/样式/有无，尺寸位置只认下面的度量表和源码。",
             "", "## 共享事实（父会话已算好；你的源码证据与之矛盾时以证据为准，并在 notes 里写出处）", "",
             "```json", json.dumps(facts, ensure_ascii=False, indent=1), "```", ""]
    for it in items:
        u = plan.units[it["android"]]
        lines += [f"## {it['android']} — {it['label']}",
                  f"- 类型: {it['kind']}；Android Activity: {it['activity']}；鸿蒙页面: {it.get('harmony_page')}",
                  f"- 配对: {it.get('confidence')}（找控件方式 {it.get('method')}，文字重合 {it.get('text_overlap')}）",
                  f"- 帧数: Android {len(it['android_frames'])} / 鸿蒙 {len(it.get('harmony_frames') or [])}",
                  f"- 结果文件: `{os.path.join(rdir, 'judge', 'results', it['android'] + '.json')}`"]
        if it.get("sentinel"):
            lines.append("- 抽样复核：这一对鸿蒙证据和上一轮一样，上一轮的结论本可沿用；按同样口径从头判一遍，"
                         "和上一轮结论不同（多出或少了问题）时在 notes 里写明")
        if u.parent:
            lines.append(f"- 来路: 从 {u.parent} 点「{u.step.label if u.step else ''}」")
        for fr in it.get("frames") or []:
            lines.append(f"- 第 {fr['k']} 帧 对比图 `{fr.get('sbs')}`（安卓原图 `{fr.get('android')}`，鸿蒙原图 `{fr.get('harmony')}`）")
            if not fr.get("android") and fr.get("harmony"):
                from .coverage import android_scrollable
                if it.get("android_xmls") and not android_scrollable(it["android_xmls"][0]):
                    lines.append("  - 这一帧只有鸿蒙，且安卓页面一屏放得下：鸿蒙内容超出一屏，按 scroll 类判断")
                else:
                    lines.append("  - 这一帧只有鸿蒙，安卓页面可滚动（安卓少截了）：不判、不出单，覆盖账里记为安卓基线欠账")
        oi = oracle_items(it)
        if oi:
            lines.append("- 结构 oracle 硬差异（每条都要在 oracle_checks 里表态；几条说的是同一处差异时只留一条，其余写 same_as）：")
            lines += [f"  - {o['id']}（第 {o['frame']} 帧）{o['description']}" for o in oi]
        else:
            lines.append("- 结构 oracle 硬差异：无")
        for fr in it.get("frames") or []:
            o = fr.get("oracle") or {}
            data = read_json(o.get("file", ""), {}) if o.get("file") else {}
            rows = [r for r in data.get("measure") or [] if not r.get("data")]
            if not rows:
                continue
            sh = data.get("common_offset")
            sb = data.get("status_bar_px") or {}
            hs, hv = data.get("harmony_screen") or [0], data.get("harmony_screen_vp") or [0]
            h_sb = round(sb.get("harmony", 0) / (hs[0] / hv[0]), 1) if hv[0] and sb.get("harmony") else None
            tops = ("；贴顶元素从各自状态栏下沿量" if sb.get("tops_from") == "status_bar" else
                    f"；贴顶元素 Δy 从屏幕顶量（鸿蒙状态栏 {h_sb}vp，安卓状态栏基线未记录，看截图）：两端状态栏高度差"
                    "造成的整体偏移不算差异，只比各自状态栏下沿到内容的距离" if h_sb else "")
            lines.append(f"- 第 {fr['k']} 帧度量表（安卓 dp / 鸿蒙 vp；屏幕 {data.get('android_screen_dp')} / {data.get('harmony_screen_vp')}）"
                         + tops + (f"；整体偏移 Δy={sh['dy']}（{sh['note']}），下面 Δy 先写残差、括号里是原始值" if sh else "") + "：")
            for r in rows[:14]:
                ad, hd = r["android_dp"], r["harmony_vp"]
                res = r.get("dy_residual")
                dy = f"{res}（原始 {r['dy']}）" if res is not None else f"{r['dy']}"
                cmp_ = "" if r.get("size_comparable") else "（宽高不可比）"
                xa = {"left": "按左边", "right": "按右边", "center": "按中线"}.get(r.get("x_anchor"))
                dx = f"{r['dx']}（{xa}）" if xa else "不可比"
                web = "（网页内容，鸿蒙已按屏宽比例换算）" if r.get("web") else ""
                lines.append(f"  - 「{r['label'][:18]}」安卓 x{ad['x']} y{ad['y']} {ad['w']}×{ad['h']} | 鸿蒙 x{hd['x']} y{hd['y']} "
                             f"{hd['w']}×{hd['h']} | Δx{dx} Δy{dy}（{'底边' if r['anchor'] == 'bottom' else '顶边'}） Δw{r['dw']} Δh{r['dh']}{cmp_}{web}")
        if idx:
            rids = _page_rids(it["android_xmls"][0]) if it.get("android_xmls") else []
            refs = source.refs(idx, rids, limit=14, page_rids=rids)
            if refs:
                lines.append("- 安卓布局出处（源码真值）：")
                lines += [f"  - {source.format_ref(r)}" for r in refs]
        if it.get("missing_texts"):
            lines.append(f"- 鸿蒙缺少的安卓文字（全页，数字已归一为#，含列表内容）: {', '.join(it['missing_texts'][:20])}")
        if prev.get(it["android"]):
            lines.append("- 上一轮的问题（同一问题沿用原 key；已修好的不要再写）: "
                         + "; ".join(f"{x['key']}={x['description'][:40]}" for x in prev[it["android"]]))
        lines.append("")
    return "\n".join(lines)
