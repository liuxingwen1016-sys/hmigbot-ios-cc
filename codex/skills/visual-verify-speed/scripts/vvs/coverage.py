"""Coverage ledger in three layers, plus 'Android missing / HarmonyOS present' sorted by the Android source.

1. Android source inventory (baseline coverage is measured against the page list derived from the Android
   source, not against what was reached): Activities from every AndroidManifest.xml, dialog classes.
2. What android_fast_traverse did not capture: controls it did not tap (danger words, confirm buttons, deny rules),
   list items it sampled, controls it could not find (from its report, read for accounting only).
3. What the HarmonyOS side has that the Android baseline lacks:
   - extra frames of a paired unit: Android page scrollable -> the Android capture is short (baseline debt);
     Android page fits one screen -> HarmonyOS content overflows (a candidate difference);
   - tappable controls on a HarmonyOS screen the Android screen does not show: label found in the Android source
     -> the Android baseline did not reach that state (debt); not found -> HarmonyOS-only (to confirm);
   - hand-driven captures without an Android counterpart.
"""
from __future__ import annotations

import os
import re
import subprocess
import xml.etree.ElementTree as ET

from . import hui
from .android import Plan, xml_texts
from .store import Store, read_json, write_json

DIALOG_RE = re.compile(r"class\s+(\w+)[^{]*?(?:extends|:)\s*[\w.<>, ]*?(Dialog|DialogFragment|BottomSheetDialogFragment|"
                       r"PopupWindow|BasePopupView|CenterPopupView|BottomPopupView)\b")


def _walk(root: str, exts: tuple):
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if x not in ("build", ".gradle", ".git", ".idea", "intermediates", "node_modules")]
        for f in files:
            if f.endswith(exts):
                yield os.path.join(d, f)


def android_inventory(project: str | None, package: str) -> dict:
    out = {"activities": [], "third_party_activities": [], "dialogs": [], "fact_tree_pages": None}
    if not project or not os.path.isdir(project):
        return out
    acts, third = set(), set()
    for path in _walk(project, ("AndroidManifest.xml",)):
        try:
            text = open(path, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        mpkg = (re.search(r'package="([\w.]+)"', text) or [None, ""])[1]
        for name in re.findall(r'<activity[^>]*?android:name="([\w.$]+)"', text, re.S):
            full = (mpkg + name) if name.startswith(".") else name
            short = full.rsplit(".", 1)[-1]
            prefix = ".".join(package.split(".")[:2]) if package else ""
            if name.startswith(".") or (prefix and full.startswith(prefix)) or "." not in name:
                acts.add(short)
            elif not any(full.startswith(p) for p in (prefix,)):
                (third if re.match(r"(com\.(tencent|alipay|sina|umeng|baidu|bytedance|huawei|xiaomi|vivo|oppo)|cn\.jpush)", full)
                 else acts).add(short)
    out["activities"], out["third_party_activities"] = sorted(acts), sorted(third)
    dialogs = set()
    for path in _walk(project, (".kt", ".java")):
        try:
            text = open(path, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        for m in DIALOG_RE.finditer(text):
            dialogs.add(m.group(1))
    out["dialogs"] = sorted(dialogs)
    ft = read_json(os.path.join(project, "spec", "toolkit-fact-tree.json"))
    if isinstance(ft, dict):
        out["fact_tree_pages"] = len(ft.get("pages") or ft.get("nodes") or [])
    return out


def aft_uncaptured(android_out: str) -> dict:
    r = read_json(os.path.join(android_out, "_aft", "report.json"), {}) or {}
    return {"not_tapped": r.get("skipped_for_review") or {}, "sampled": r.get("sampled_not_tapped") or {},
            "not_found": [f"{g.get('page')}: {g.get('control')}" for g in r.get("not_found") or []],
            "unreachable": r.get("unreachable") or [], "path_denied": r.get("path_denied") or []}


def android_scrollable(xml_path: str) -> bool:
    """The Android screen has a scrolling container taller than a quarter of the screen."""
    try:
        root = ET.parse(xml_path).getroot()
    except Exception:
        return False
    h = 1
    nodes = list(root.iter("node"))
    for el in nodes:
        m = re.findall(r"-?\d+", el.attrib.get("bounds", ""))
        if len(m) >= 4:
            h = max(h, int(m[3]))
    for el in nodes:
        if el.attrib.get("scrollable") == "true":
            m = [int(v) for v in re.findall(r"-?\d+", el.attrib.get("bounds", ""))[:4]]
            if len(m) == 4 and m[3] - m[1] >= 0.25 * h:
                return True
    return False


VALUE_RE = re.compile(r"^[\d.,:/\s]+[a-zA-Z%°]{0,3}$")
SEP_RE = re.compile(r"[^\s\-—_:：/·|｜]+")


def shape(label: str) -> str:
    """'经典-红色-短袖' -> '*-*-*': labels of one list share a shape even when their words differ."""
    return SEP_RE.sub("*", label.strip())


def in_list(nodes: list, n, label_counts: dict) -> bool:
    """List/grid content: inside repeated container cells (>= 3 siblings of one type sharing height or width,
    each with children; inline text spans do not count) and the label differs from cell to cell. A label repeated
    in several cells (a button inside every card) is part of the cell's structure, not data."""
    if label_counts.get(hui.norm_label(hui.label_of(nodes, n)), 0) >= 2:
        return False
    a, depth = n, 0
    while a.parent >= 0 and depth < 4:
        p = nodes[a.parent]
        sib = [nodes[k] for k in p.children if nodes[k].children]
        h = a.bounds[3] - a.bounds[1]
        w = a.bounds[2] - a.bounds[0]
        if a.children and (sum(1 for x in sib if x.type == a.type and x.bounds[3] - x.bounds[1] == h) >= 3 or
                           sum(1 for x in sib if x.type == a.type and x.bounds[2] - x.bounds[0] == w) >= 3):
            return True
        a, depth = p, depth + 1
    return False


def in_android_source(project: str | None, label: str) -> str:
    """First Android source file that contains the label (strings.xml, layouts, code)."""
    if not project or len(label) < 2:
        return ""
    try:
        out = subprocess.run(["grep", "-rlF", "--include=*.xml", "--include=*.kt", "--include=*.java", "--", label, project],
                             capture_output=True, text=True, timeout=30).stdout.split("\n")
    except Exception:
        return ""
    hits = [p for p in out if p and "/build/" not in p]
    return os.path.relpath(hits[0], project) if hits else ""


def harmony_extras(store: Store, plan: Plan, pairs: dict, cfg: dict, bundle: str) -> dict:
    frames, entries = [], []
    for it in pairs.get("items") or []:
        if it.get("status") != "paired":
            continue
        a_frames, h_frames = it.get("android_frames") or [], it.get("harmony_frames") or []
        if len(h_frames) > len(a_frames) and it.get("android_xmls"):
            scroll = android_scrollable(it["android_xmls"][0])
            frames.append({"android": it["android"], "extra": len(h_frames) - len(a_frames),
                           "kind": "android_short" if scroll else "harmony_overflow",
                           "note": ("安卓页面可滚动，安卓少截了这几屏：安卓基线欠账，用 aft 补采后再比" if scroll else
                                    "安卓页面一屏放得下，鸿蒙要滚动：鸿蒙内容超出一屏，按差异处理")})
        a_texts, a_shapes, a_norms = set(), {}, []
        for x in it.get("android_xmls") or []:
            for t in xml_texts(x):
                a_texts.add(hui.digit_pattern(t))
                a_norms.append(hui.norm_label(t))
                if SEP_RE.sub("", t):
                    a_shapes[shape(t)] = a_shapes.get(shape(t), 0) + 1
        seen = set()
        judged_data = set()
        res = read_json(it.get("result") or "", {}) if it.get("result") else {}
        if res:
            from .pairs import oracle_items
            texts = {o["id"]: o.get("text") for o in oracle_items(it) if o["category"] in ("missing", "extra")}
            for c in res.get("oracle_checks") or []:
                if isinstance(c, dict) and c.get("decision") == "refuted" and texts.get(c.get("id")):
                    judged_data.add(hui.norm_label(texts[c["id"]]))
        for v in it.get("harmony_views") or []:
            try:
                nodes, _ = hui.parse(open(v, "rb").read())
            except Exception:
                continue
            cands = hui.labelled(nodes, bundle)
            counts: dict = {}
            for c in cands:
                counts[c.norm] = counts.get(c.norm, 0) + 1
            for c in cands:
                if not (c.node.clickable or c.node.checkable) or c.pattern in a_texts or c.norm in seen:
                    continue
                if c.node.type in hui.INPUT_TYPES or (c.node.type in hui.NAME_TYPES and c.label == c.node.text.strip()):
                    continue  # what was typed into a field / a checkbox's name parameter: nothing drawn
                if len(c.norm) < 2 or len(c.norm) > 20 or hui.DYNAMIC_TEXT.match(c.label) or VALUE_RE.match(c.label):
                    continue
                seen.add(c.norm)
                if len(c.norm) >= 3 and any(c.norm in t for t in a_norms):
                    continue  # one segment of an Android text that HarmonyOS splits into several Text nodes
                a11y = not c.node.text.strip() and bool(c.node.desc.strip())
                if c.norm in judged_data:
                    entries.append({"android": it["android"], "label": c.label, "kind": "data_judged", "source": "判图以安卓源码驳回"})
                    continue
                if in_list(nodes, c.node, counts) or a_shapes.get(shape(c.label), 0) >= 2:
                    entries.append({"android": it["android"], "label": c.label, "kind": "list_content", "source": ""})
                    continue
                src = in_android_source(cfg.get("android_project"), c.label)
                entries.append({"android": it["android"], "label": c.label, "a11y": a11y,
                                "kind": "android_has" if src else "harmony_only", "source": src})
    extra_units = [{"unit": m.get("unit_dir"), "label": m.get("label")} for m in store.index()
                   if not (m.get("pair") or {}).get("android")]
    return {"frames": frames, "entries": entries, "extra_captures": extra_units}


def build(store: Store, plan: Plan, rnd: int, cfg: dict, bundle: str) -> dict:
    pairs = read_json(os.path.join(store.round_dir(rnd), "pairs.json"), {}) or {}
    inv = android_inventory(cfg.get("android_project"), plan.package)
    captured = sorted({u.activity for u in plan.units.values() if u.activity})
    paired_units = {it["android"] for it in pairs.get("items") or [] if it.get("status") == "paired"}
    paired_acts = sorted({plan.units[p].activity for p in paired_units if p in plan.units and plan.units[p].activity})
    out = {"round": rnd,
           "android_source": {**inv, "activities_captured_by_aft": [a for a in inv["activities"] if a in captured],
                              "activities_not_captured": [a for a in inv["activities"] if a not in captured]},
           "aft_uncaptured": aft_uncaptured(plan.out),
           "harmony": {"android_units": len(plan.units), "paired": len(paired_units),
                       "activities_paired": paired_acts},
           "android_missing_harmony_present": harmony_extras(store, plan, pairs, cfg, bundle)}
    write_json(os.path.join(store.round_dir(rnd), "coverage.json"), out)
    return out
