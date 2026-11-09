"""Deterministic oracles for one frame pair (run before any judge).

1. Structure oracle: leaf text elements of both dumps; missing / extra / sibling order are hard findings,
   position offsets are only hints. Covered layers are skipped (same rules as the walk), and texts inside
   repeated list cells are *data* (data areas compare structure and style, not content or count), so they never
   become missing/extra -- unless HarmonyOS shows no list content at all (one "whole list missing" difference).
2. Measurement table: every size/position as raw px -> dp/vp with each side's own density, taken from
   view-tree bounds, never from screenshot pixels. Elements in the bottom 30% of the screen
   are compared from the bottom edge (a taller HarmonyOS screen moves bottom-anchored content down).
"""
from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from collections import Counter

from . import hui

BAND_TOL = 0.04
POS_HINT_THRESHOLD = 0.08
PAIR_MAX = 0.10
BOTTOM_ZONE = 0.88  # only bottom-docked bars/buttons are compared from the bottom edge
# The HarmonyOS dump covers the whole screen including the gesture navigation indicator, which apps must keep
# clear; the Android dump ends above its navigation bar. Bottom offsets compare usable bottoms.
HMOS_NAV_VP = 28.0
# Tops compare the same way, each side from below its own status bar -- but only when both heights are measured:
# HarmonyOS always (the system status-bar window in the dump); Android only when the baseline records it (apps
# draw edge to edge, the dump does not show it, and a guessed default creates offsets of its own).


def hmos_top_inset(raw: bytes, bundle: str) -> int:
    """Height (px) of the system status-bar window across the top of a HarmonyOS dump; 0 when there is none."""
    nodes, wins = hui.parse(raw)
    w, h = hui.screen_size(nodes)
    for win in wins:
        if win.bundle == bundle:
            continue
        x1, y1, x2, y2 = win.bounds
        if y1 == 0 and x2 - x1 >= 0.9 * w and 0 < y2 < 0.08 * h:
            return y2
    return 0
_DYN_RE = re.compile(r"^[\d:：年月日号\s,，.%/°℃~+-]+$")
TYPE_EQ = {"TextView": "Text", "AppCompatTextView": "Text", "MaterialTextView": "Text", "ImageView": "Image",
           "AppCompatImageView": "Image", "ImageButton": "Image", "EditText": "TextInput",
           "AppCompatEditText": "TextInput", "Button": "Button", "AppCompatButton": "Button", "MaterialButton": "Button",
           "CheckBox": "Checkbox", "Switch": "Toggle", "SwitchCompat": "Toggle", "RadioButton": "Radio",
           "ProgressBar": "Progress", "SeekBar": "Slider", "WebView": "Web"}


def is_dynamic(text: str) -> bool:
    return bool(_DYN_RE.match(text)) or "周" in text


def norm_type(t: str) -> str:
    return TYPE_EQ.get(t, t)


def _runs(cols: list, gap: int) -> list:
    runs, cur = [], [cols[0]]
    for c in cols[1:]:
        if c - cur[-1] > gap:
            runs.append(cur)
            cur = []
        cur.append(c)
    return runs + [cur]


def _drop_icons(inner: set, gap: int) -> set:
    """Text only, out of the ink inside an input field: split into column runs separated by >= gap empty columns
    (an icon sits drawablePadding away from the text, glyphs only ~1dp apart) and drop a square-ish run at either
    end (search / clear icon); then drop a thin tall bar at either end (the text cursor)."""
    def wh(run):
        rows = [j for i, j in inner if run[0] <= i <= run[-1]]
        return run[-1] - run[0] + 1, max(rows) - min(rows) + 1
    keep = _runs(sorted({i for i, _ in inner}), gap)
    if len(keep) > 1 and (lambda w, h: w <= 1.3 * h)(*wh(keep[0])):
        keep = keep[1:]
    if len(keep) > 1 and (lambda w, h: w <= 1.3 * h)(*wh(keep[-1])):
        keep = keep[:-1]
    cols = [c for r in keep for c in r]
    rows_of: dict = {}
    for i, j in inner:
        if cols[0] <= i <= cols[-1]:
            rows_of.setdefault(i, []).append(j)
    cols = sorted(rows_of)
    span = {i: max(v) - min(v) + 1 for i, v in rows_of.items()}
    ends = {i: (min(v), max(v)) for i, v in rows_of.items()}

    def solid(i):
        return len(rows_of[i]) >= 0.9 * span[i]
    for end in (0, -1):  # the cursor: solid columns of one height at one end, taller than every glyph column
        seq = cols if end == 0 else cols[::-1]
        k = 0
        while k < len(seq) and solid(seq[k]) and abs(ends[seq[k]][0] - ends[seq[0]][0]) <= 1 \
                and abs(ends[seq[k]][1] - ends[seq[0]][1]) <= 1:
            k += 1
        bar = cols[:k] if end == 0 else cols[len(cols) - k:]
        rest = cols[k:] if end == 0 else cols[:len(cols) - k]
        if bar and rest and min(span[i] for i in bar) > 1.1 * max(span[i] for i in rest):
            cols = rest
    lo, hi = cols[0], cols[-1]
    return {(i, j) for i, j in inner if lo <= i <= hi}


def ink(im, box: tuple, scale: tuple, tol: int = 40, max_samples: int = 4000, edge_clear: bool = False,
        gap_px: int = 0) -> dict | None:
    """Visible ink inside a node: background = most frequent colour, ink = pixels
    farther than tol from it. Returns box in dump px, fg/bg, ink pixel count, unreliable (busy background).
    edge_clear (input fields): ink connected to the node's edge is its border or the outside of rounded corners,
    not the text; the box is taken from the rest, without an icon drawn inside the field (gap_px apart)."""
    if im is None:
        return None
    sx, sy = scale
    x1, y1, x2, y2 = int(box[0] * sx), int(box[1] * sy), int(box[2] * sx), int(box[3] * sy)
    x1, y1, x2, y2 = max(0, x1), max(0, y1), min(im.width, x2), min(im.height, y2)
    w, h = x2 - x1, y2 - y1
    if w <= 1 or h <= 1:
        return None
    step = 1
    while (w // step) * (h // step) > (max_samples * 40 if edge_clear else max_samples):
        step += 1  # edge_clear needs a fine grid: a 1dp border must stay connected to the edge
    px = im.load()
    hist = Counter(px[x, y] for y in range(y1, y2, step) for x in range(x1, x2, step))
    bg = hist.most_common(1)[0][0]

    def far(c):
        return abs(c[0] - bg[0]) + abs(c[1] - bg[1]) + abs(c[2] - bg[2]) > tol
    ring = [px[x, yy] for x in range(x1, x2, step) for yy in (y1, y2 - 1)] + \
           [px[xx, y] for y in range(y1, y2, step) for xx in (x1, x2 - 1)]
    spread = sum(1 for c in ring if far(c)) / max(1, len(ring))
    ix1, iy1, ix2, iy2, n, fg, fd = x2, y2, x1, y1, 0, bg, -1
    for y in range(y1, y2, step):
        for x in range(x1, x2, step):
            c = px[x, y]
            dist = abs(c[0] - bg[0]) + abs(c[1] - bg[1]) + abs(c[2] - bg[2])
            if dist > tol:
                n += 1
                ix1, iy1, ix2, iy2 = min(ix1, x), min(iy1, y), max(ix2, x + step), max(iy2, y + step)
                if dist > fd:
                    fd, fg = dist, c
    out = {"bg": "#%02X%02X%02X" % bg, "fg": "#%02X%02X%02X" % fg, "ink_px": n, "unreliable": spread > 0.35}
    if n and edge_clear:
        xs, ys = list(range(x1, x2, step)), list(range(y1, y2, step))
        far_at = {(i, j) for j, y in enumerate(ys) for i, x in enumerate(xs) if far(px[x, y])}
        seen = {(i, j) for (i, j) in far_at if i in (0, len(xs) - 1) or j in (0, len(ys) - 1)}
        todo = list(seen)
        while todo:
            i, j = todo.pop()
            for q in ((i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1), (i + 1, j + 1), (i - 1, j - 1), (i + 1, j - 1), (i - 1, j + 1)):
                if q in far_at and q not in seen:
                    seen.add(q)
                    todo.append(q)
        inner = far_at - seen
        if not inner:
            return out  # nothing drawn inside the frame: no text box
        inner = _drop_icons(inner, max(1, gap_px // step)) if gap_px else inner
        ix1, ix2 = xs[min(i for i, _ in inner)], xs[max(i for i, _ in inner)] + step
        iy1, iy2 = ys[min(j for _, j in inner)], ys[max(j for _, j in inner)] + step
        out["unreliable"] = False
    if n:
        out["box"] = [round(ix1 / sx), round(iy1 / sy), round(ix2 / sx), round(iy2 / sy)]
    return out


def _load(png: str | None):
    if not png:
        return None
    try:
        from PIL import Image
        return Image.open(png).convert("RGB")
    except Exception:
        return None


def _elem(text, typ, ident, desc, b, clickable, data, density, screen):
    x1, y1, x2, y2 = b
    d = density or 0
    e = {"text": text, "type": typ, "id": ident, "desc": desc, "bounds": list(b), "clickable": clickable,
         "data": data, "cx": (x1 + x2) / 2 / max(1, screen[0]), "cy": (y1 + y2) / 2 / max(1, screen[1])}
    if d:
        e["dp"] = {"x": round(x1 / d, 1), "y": round(y1 / d, 1), "w": round((x2 - x1) / d, 1),
                   "h": round((y2 - y1) / d, 1), "bottom": round((screen[1] - y2) / d, 1)}
    return e


def _cells(children_of, size_of, cls_of, nodes) -> set:
    """Ids of nodes inside repeated cells: >= 3 siblings of one class sharing their height (chips, rows of a
    vertical list) or their width (columns, grid tiles)."""
    out = set()
    for parent, kids in children_of.items():
        groups: dict = {}
        for k in kids:
            w, h = size_of[k]
            groups.setdefault(("h", cls_of[k], h), []).append(k)
            groups.setdefault(("w", cls_of[k], w), []).append(k)
        for g in groups.values():
            if len(g) >= 3:
                for k in g:
                    out.update(nodes[k])
    return out


# ---------------------------------------------------------------- Android

def android_elements(xml_path: str, density: float | None, package: str = "") -> tuple[list, tuple]:
    root = ET.parse(xml_path).getroot()
    all_nodes = [el for el in root.iter("node")]
    parent = {c: p for p in root.iter() for c in p}

    def bounds(el):
        m = re.findall(r"-?\d+", el.attrib.get("bounds", ""))
        return tuple(int(v) for v in m[:4]) if len(m) >= 4 else None
    screen = [1, 1]
    for el in all_nodes:
        b = bounds(el)
        if b:
            screen[0], screen[1] = max(screen[0], b[2]), max(screen[1], b[3])
    for el in all_nodes:  # an edge-to-edge app draws under the navigation bar: its usable bottom is the bar's top
        b = bounds(el)
        if el.attrib.get("resource-id") == "android:id/navigationBarBackground" and b and b[3] >= screen[1] > b[1] > 0:
            screen[1] = b[1]
    full = 0.7 * screen[0] * screen[1]

    def area(el):
        b = bounds(el) or (0, 0, 0, 0)
        return max(0, b[2] - b[0]) * max(0, b[3] - b[1])

    def content(el):
        return any((e.attrib.get("text") or e.attrib.get("content-desc") or e.attrib.get("clickable") == "true")
                   for e in el.iter("node"))
    covered = set()
    for p in root.iter("node"):
        kids = [c for c in p if c.tag == "node"]
        big = [c for c in kids if area(c) >= full and content(c)]
        for k in big[:-1]:
            covered.update(id(e) for e in k.iter("node"))
    # repeated cells
    children_of, size_of, cls_of, sub = {}, {}, {}, {}
    for p in root.iter("node"):
        kids = [c for c in p if c.tag == "node"]
        if len(kids) >= 3:
            children_of[id(p)] = [id(k) for k in kids]
            for k in kids:
                b = bounds(k) or (0, 0, 0, 0)
                size_of[id(k)] = (b[2] - b[0], b[3] - b[1])
                cls_of[id(k)] = k.attrib.get("class", "")
                sub[id(k)] = {id(e) for e in k.iter("node")}
    cells = _cells(children_of, size_of, cls_of, sub)
    web = {id(e) for w in all_nodes if "WebView" in w.attrib.get("class", "") for e in w.iter("node")}
    out = []
    for el in all_nodes:
        if id(el) in covered:
            continue
        a = el.attrib
        if package and a.get("package") and a.get("package") != package:
            continue
        b = bounds(el)
        if not b or b[2] <= b[0] or b[3] <= b[1]:
            continue
        txt = (a.get("text") or "").strip()
        desc_texts = [(c.attrib.get("text") or "").strip() for c in el.iter("node") if c is not el]
        cls = a.get("class", "").rsplit(".", 1)[-1]
        leaf_text = txt and not any(desc_texts)
        leaf_icon = not txt and not list(el) and ("Image" in cls) and (b[2] - b[0]) >= 8
        if leaf_text or leaf_icon:
            e = _elem(txt, cls, (a.get("resource-id") or "").rsplit("/", 1)[-1],
                      (a.get("content-desc") or "").strip(), b, a.get("clickable") == "true",
                      id(el) in cells, density, screen)
            e["input"] = cls.endswith("EditText") or "EditText" in a.get("class", "")
            e["web"] = id(el) in web
            out.append(e)
    return out, tuple(screen)


# ---------------------------------------------------------------- HarmonyOS

def harmony_elements(raw: bytes, density: float | None, bundle: str) -> tuple[list, tuple]:
    nodes, _ = hui.parse(raw)
    screen = hui.screen_size(nodes)
    app = [n for n in nodes if n.bundle == bundle and not n.covered and n.area > 0]
    children_of, size_of, cls_of, sub = {}, {}, {}, {}
    for p in app:
        kids = [k for k in p.children if not nodes[k].covered]
        if len(kids) >= 3:
            children_of[p.idx] = kids
            for k in kids:
                x1, y1, x2, y2 = nodes[k].bounds
                size_of[k] = (x2 - x1, y2 - y1)
                cls_of[k] = nodes[k].type
                sub[k] = set(hui.subtree(nodes, nodes[k]))
    cells = _cells(children_of, size_of, cls_of, sub)
    web = {i for w in app if w.type == "Web" for i in hui.subtree(nodes, w)}
    out = []
    for n in app:
        txt = "" if n.type in hui.NAME_TYPES else n.text.strip()
        if not txt and n.type in hui.INPUT_TYPES:
            txt = n.hint.strip()  # the placeholder is what is drawn; Android dumps an empty EditText's hint as text
        desc_texts = [nodes[i].text.strip() for i in hui.subtree(nodes, n)[1:] if not nodes[i].covered]
        leaf_text = txt and not any(desc_texts)
        leaf_icon = not txt and not n.children and n.type in ("Image", "SymbolGlyph") and (n.bounds[2] - n.bounds[0]) >= 8
        if not (leaf_text or leaf_icon):
            continue
        if n.type in hui.INPUT_TYPES and txt:
            pass  # placeholder/typed text still counts as an element
        e = _elem(txt, n.type, n.ident, n.desc.strip(), n.bounds, n.clickable, n.idx in cells, density, screen)
        e["input"] = n.type in hui.INPUT_TYPES
        e["web"] = n.idx in web
        out.append(e)
    return out, screen


# ---------------------------------------------------------------- structure oracle

def _region(cx, cy):
    col = "left" if cx < 0.34 else ("right" if cx > 0.66 else "center")
    row = "top" if cy < 0.34 else ("bottom" if cy > 0.66 else "middle")
    return f"{row}-{col}"


def mark_data(a_txt: list, h_txt: list) -> None:
    """Repeated cells on both sides whose texts mostly differ are list content (data); cells whose texts mostly
    match (menus, tab bars, setting rows) stay structural. A cell text the other side does not show at all is
    data as well when the other side has cells (a random or user-data list)."""
    for e in a_txt + h_txt:
        e["text_n"] = hui.norm_label(e["text"])
    a_cells = {e["text_n"] for e in a_txt if e["data"]}
    h_cells = {e["text_n"] for e in h_txt if e["data"]}
    a_set, h_set = {e["text_n"] for e in a_txt}, {e["text_n"] for e in h_txt}
    lists = bool(a_cells and h_cells) and len(a_cells & h_cells) / max(1, min(len(a_cells), len(h_cells))) < 0.6
    for e in a_txt:
        e["data"] = bool(e["data"] and h_cells and (lists or e["text_n"] not in h_set))
    for e in h_txt:
        e["data"] = bool(e["data"] and a_cells and (lists or e["text_n"] not in a_set))


def structure(android: list, harmony: list) -> dict:
    a_txt = [e for e in android if e["text"]]
    h_txt = [e for e in harmony if e["text"]]
    mark_data(a_txt, h_txt)
    ac = Counter(e["text_n"] for e in a_txt if not e["data"] and not e.get("input"))
    hc = Counter(e["text_n"] for e in h_txt if not e["data"] and not e.get("input"))
    h_all = Counter(e["text_n"] for e in h_txt)
    a_all = Counter(e["text_n"] for e in a_txt)
    shown = {e["text_n"]: e["text"] for e in a_txt + h_txt}
    diffs = []
    for t in ac:
        gap = ac[t] - h_all.get(t, 0)  # a structural text present anywhere on HarmonyOS (even in a cell) counts
        if gap > 0:
            diffs.append({"category": "missing", "severity": "high", "text": shown[t], "count": gap,
                          "description": f"Android 有文本元素「{shown[t]}」(x{ac[t]})，HarmonyOS 缺 {gap} 个",
                          "source": "structural_oracle", "dynamic_suspect": is_dynamic(t)})
    for t in hc:
        gap = hc[t] - a_all.get(t, 0)
        if gap > 0:
            diffs.append({"category": "extra", "severity": "high", "text": shown[t], "count": gap,
                          "description": f"HarmonyOS 多出文本元素「{shown[t]}」(x{gap})，Android 无对应",
                          "source": "structural_oracle", "dynamic_suspect": is_dynamic(t)})
    gone = [e for e in a_txt if e["data"] and e["text_n"] not in h_all]
    if len(gone) >= 3 and not any(e["data"] for e in h_txt):
        # Android shows list content (cells whose texts HarmonyOS does not have) and HarmonyOS shows no list
        # content at all: the list is empty or never loaded there. Data differences need data on both sides.
        names = list(dict.fromkeys(e["text"] for e in gone))
        diffs.append({"category": "missing", "severity": "high", "text": names[0], "count": len(names),
                      "whole_list": True, "source": "structural_oracle", "dynamic_suspect": False,
                      "description": f"Android 有一整块列表内容（{len(names)} 项，如「{'」「'.join(names[:4])}」），"
                                     "HarmonyOS 同一画面一项列表内容都没有（列表为空或没加载出来）"})
    common = Counter(e["text_n"] for e in a_txt) & Counter(e["text_n"] for e in h_txt)

    def banded(elems):
        # numbers and texts that repeat on a side are skipped: they pair across unrelated containers
        dup = Counter(e["text_n"] for e in elems)
        rows = []
        for e in sorted([e for e in elems if common.get(e["text_n"], 0) > 0 and not is_dynamic(e["text"])
                         and dup[e["text_n"]] == 1 and not e["data"]], key=lambda e: e["cy"]):
            for row in rows:
                if abs(row[0]["cy"] - e["cy"]) <= BAND_TOL:
                    row.append(e)
                    break
            else:
                rows.append([e])
        return [[x["text_n"] for x in sorted(r, key=lambda e: e["cx"])] for r in rows if len(r) >= 2]
    for ab in banded(a_txt):
        for hb in banded(h_txt):
            if frozenset(hb) == frozenset(ab) and ab != hb:
                diffs.append({"category": "order", "severity": "high",
                              "description": f"同一横向带兄弟顺序不一致：Android {ab} vs HarmonyOS {hb}",
                              "source": "structural_oracle", "dynamic_suspect": False})
                break
    data_a = {e["text"] for e in a_txt if e["data"]}
    data_h = {e["text"] for e in h_txt if e["data"]}
    checklist = []
    remaining = Counter(e["text_n"] for e in h_txt)
    for e in a_txt:
        present = remaining.get(e["text_n"], 0) > 0
        if present:
            remaining[e["text_n"]] -= 1
        checklist.append({"text": e["text"], "type": e["type"], "region": _region(e["cx"], e["cy"]),
                          "present_in_hmos": present, "data": e["data"]})
    return {"differences": diffs, "checklist": checklist,
            "data_texts": {"android": len(data_a), "harmony": len(data_h), "shared": len(data_a & data_h)}}


# ---------------------------------------------------------------- measurement table

def pair(android: list, harmony: list) -> list:
    """Text unique on both sides -> id -> nearest element of the equivalent type (ratio distance <= PAIR_MAX)."""
    pairs, used = [], set()
    ac = Counter(e["text"] for e in android if e["text"])
    hc = Counter(e["text"] for e in harmony if e["text"])
    for a in android:
        if a["text"] and ac[a["text"]] == 1 and hc.get(a["text"]) == 1:
            h = next(x for x in harmony if x["text"] == a["text"])
            pairs.append((a, h, "text"))
            used.add(id(h))
            a["_p"] = True
    for a in android:
        if a.get("_p"):
            continue
        best, bd = None, PAIR_MAX
        for h in harmony:
            if id(h) in used or norm_type(h["type"]) != norm_type(a["type"]):
                continue
            if a["text"] and h["text"] and a["text"] != h["text"] and not (a["data"] or h["data"]):
                continue
            d = math.hypot(a["cx"] - h["cx"], a["cy"] - h["cy"])
            if d < bd:
                best, bd = h, d
        if best is not None:
            pairs.append((a, best, "nearest"))
            used.add(id(best))
            a["_p"] = True
    for a in android:
        a.pop("_p", None)
    return pairs


def _visible_dp(e: dict, density: float, screen: tuple, inset: float = 0.0, top: int = 0) -> dict:
    """Text: the ink box (what is drawn); icons and unreliable backgrounds: the node bounds. `y` is measured from
    the usable top (below `top` px of status bar), `bottom` from the usable bottom (`inset` dp of navigation area)."""
    b = e["bounds"]
    k = e.get("ink") or {}
    if e["text"] and k.get("box") and not k.get("unreliable"):
        b = k["box"]
    x1, y1, x2, y2 = b
    return {"x": round(x1 / density, 1), "y": round((y1 - top) / density, 1), "w": round((x2 - x1) / density, 1),
            "h": round((y2 - y1) / density, 1), "bottom": round((screen[1] - y2) / density - inset, 1),
            "basis": "ink" if b is not e["bounds"] else "bounds"}


EDGE = 24.0  # dp: an element this close to one screen edge on Android is pinned to it


def measure_table(android: list, harmony: list, da: float, dh: float, ascreen: tuple, hscreen: tuple,
                  h_inset: float = HMOS_NAV_VP, a_top: int = 0, h_top: int = 0) -> list:
    """Paired elements in dp/vp. The two screens differ in width and height, so:
    - x offset = the smallest of left-edge / centre / right-edge offsets (an element follows one of them);
    - full-width elements compare their margins, not their widths;
    - every side is measured inside its usable area: tops from below its own status bar (a_top / h_top px),
      bottom-docked elements (bottom 12% on both sides) from the usable bottom edge (HarmonyOS: above the gesture
      indicator; content inside it shows as a downward offset);
    - a text whose ink holds an icon on one side (compound drawable) compares its bottom edge;
    - an element within EDGE dp of one screen edge on Android is pinned to that edge and compared there;
    - web page content (WebView / Web) scales with the screen width, not with dp: HarmonyOS values are scaled by
      the width ratio before comparing (the autosize density does not apply inside a WebView either)."""
    wa, wh = ascreen[0] / da, hscreen[0] / dh
    rows = []
    for a, h, how in pair(android, harmony):
        ad, hd = _visible_dp(a, da, ascreen, top=a_top), _visible_dp(h, dh, hscreen, h_inset, h_top)
        web = bool(a.get("web") or h.get("web"))
        sw = wh
        if web:  # each page is laid out at its own screen width: HarmonyOS values -> Android dp of the same fraction
            hd = {**hd, **{k: round(hd[k] * wa / wh, 1) for k in ("x", "w", "h")}}
            sw = wa
        both_text = bool(a["text"] and h["text"])
        basis_ok = ad["basis"] == hd["basis"] and (not both_text or ad["basis"] == "ink")
        compound = both_text and basis_ok and max(ad["h"], hd["h"]) > 0 and \
            abs(ad["h"] - hd["h"]) > 0.35 * max(ad["h"], hd["h"])
        size_ok = basis_ok and not compound
        pos_ok = ad["basis"] == hd["basis"] and not compound  # two text boxes: positions compare, widths may not
        if compound:   # icon above the text on one side: the text sits at the bottom of both boxes
            dy_top = round((hd["y"] + hd["h"]) - (ad["y"] + ad["h"]), 1)
            dy_bottom = round(ad["bottom"] - hd["bottom"], 1)
        elif not basis_ok:  # text box vs drawn ink: compare vertical centres
            dy_top = round((hd["y"] + hd["h"] / 2) - (ad["y"] + ad["h"] / 2), 1)
            dy_bottom = round((ad["bottom"] + ad["h"] / 2) - (hd["bottom"] + hd["h"] / 2), 1)
        else:
            dy_top = round(hd["y"] - ad["y"], 1)
            dy_bottom = round(ad["bottom"] - hd["bottom"], 1)
        bottom = a["cy"] >= BOTTOM_ZONE and h["cy"] >= BOTTOM_ZONE
        if pos_ok:
            cand = {"left": hd["x"] - ad["x"],
                    "center": (hd["x"] + hd["w"] / 2 - sw / 2) - (ad["x"] + ad["w"] / 2 - wa / 2),
                    "right": (wa - ad["x"] - ad["w"]) - (sw - hd["x"] - hd["w"])}
            lg, rg = ad["x"], wa - ad["x"] - ad["w"]
            if lg <= EDGE < rg:
                h_anchor = "left"
            elif rg <= EDGE < lg:
                h_anchor = "right"
            else:
                h_anchor = min(cand, key=lambda k: abs(cand[k]))
            dx = round(cand[h_anchor], 1)
        else:
            h_anchor, dx = "n/a", 0.0  # not measured: the left edge of a text box and of its ink differ by the gravity
        full = ad["w"] >= 0.9 * wa and hd["w"] >= 0.9 * sw
        dw = round((hd["w"] - sw) - (ad["w"] - wa), 1) if full else round(hd["w"] - ad["w"], 1)
        rows.append({"label": a["text"] or a["desc"] or a["id"] or a["type"], "pair_by": how,
                     "android_dp": ad, "harmony_vp": hd, "anchor": "bottom" if bottom else "top", "x_anchor": h_anchor,
                     "dx": dx, "dy": dy_bottom if bottom else dy_top, "dy_top": dy_top, "dy_bottom": dy_bottom,
                     "dw": dw if size_ok else 0.0, "dh": round(hd["h"] - ad["h"], 1) if size_ok else 0.0,
                     "size_comparable": size_ok, "full_width": full, "data": a["data"] or h["data"], "web": web,
                     "fg": [(a.get("ink") or {}).get("fg"), (h.get("ink") or {}).get("fg")]})
    rows.sort(key=lambda r: -max(abs(r["dx"]), abs(r["dy"]), abs(r["dw"]), abs(r["dh"])))
    return rows


ICON_GAP_DP = 3.5  # dp: an icon inside an input field sits >= ~4dp from its text; CJK glyph gaps stay under ~3dp
FONT_RATIO = 1.08  # the same text drawn >= 8% wider AND taller (or narrower AND shorter): a different font size


def font_suspects(rows: list) -> list:
    """Same text on both sides whose ink width and height changed by the same ratio (>= 8%): the font size differs.
    Rows whose ink holds an icon, a border or a second line are left out (not size-comparable, or the two ratios
    disagree: a wrapped line is narrower but taller)."""
    out = []
    for r in rows:
        ad, hd = r["android_dp"], r["harmony_vp"]
        if r["pair_by"] != "text" or not r["size_comparable"] or r["data"] or ad["w"] < 10 or ad["h"] < 6:
            continue
        rw, rh = hd["w"] / ad["w"], hd["h"] / ad["h"]
        if not ((rw >= FONT_RATIO and rh >= FONT_RATIO) or (rw <= 1 / FONT_RATIO and rh <= 1 / FONT_RATIO)):
            continue
        if abs(rw / rh - 1) > 0.06:
            continue
        ratio = round((rw + rh) / 2, 2)
        out.append({"text": r["label"], "ratio": ratio, "android_ink": [ad["w"], ad["h"]], "harmony_ink": [hd["w"], hd["h"]],
                    "description": f"「{r['label'][:24]}」字号疑似不同：墨迹 宽 {ad['w']}dp→{hd['w']}vp（×{rw:.2f}）、"
                                   f"高 {ad['h']}→{hd['h']}（×{rh:.2f}），宽高同比例{'变大' if ratio > 1 else '变小'}"
                                   f"（14→16 约 ×1.14，10→12 约 ×1.20）"})
    return out


def common_offset(rows: list, tol: float = 4.0) -> dict | None:
    """Most top-anchored rows moved by the same amount: the whole content is shifted (a different scroll position,
    a taller header). Reported once; per-row residuals are what is left after removing it."""
    ys = sorted(r["dy"] for r in rows if r["anchor"] == "top" and not r["data"])
    if len(ys) < 4:
        return None
    med = ys[len(ys) // 2]
    share = sum(1 for y in ys if abs(y - med) <= tol) / len(ys)
    if abs(med) <= 8 or share < 0.6:
        return None
    for r in rows:
        if r["anchor"] == "top":
            r["dy_residual"] = round(r["dy"] - med, 1)
    return {"dy": med, "share": round(share, 2),
            "note": "多数元素整体同向偏移：多半是截图时滚动位置或顶部栏高度不同，不是逐个元素的布局差异"}


def frame_oracle(android_xml: str, harmony_raw: bytes, density_a: float | None, density_h: float | None,
                 bundle: str, package: str = "", android_png: str | None = None, harmony_png: str | None = None,
                 a_top_px: int | None = None) -> dict:
    a, ascreen = android_elements(android_xml, density_a, package)
    h, hscreen = harmony_elements(harmony_raw, density_h, bundle)
    for elems, png, screen, dens in ((a, android_png, ascreen, density_a), (h, harmony_png, hscreen, density_h)):
        im = _load(png)
        if im is None:
            continue
        k = im.width / max(1, screen[0])  # dump coordinates are screen pixels; the PNG may add system bars below
        scale = (k, k)
        gap = round(ICON_GAP_DP * (dens or 3.0) * k)
        for e in elems:
            e["ink"] = ink(im, tuple(e["bounds"]), scale, edge_clear=bool(e.get("input")), gap_px=gap)
    st = structure(a, h)
    h_top = hmos_top_inset(harmony_raw, bundle)
    both = a_top_px is not None
    table = measure_table(a, h, density_a or 1.0, density_h or 1.0, ascreen, hscreen, a_top=a_top_px if both else 0,
                          h_top=h_top if both else 0) if density_a and density_h else []
    shift = common_offset(table)
    fonts = font_suspects(table)
    invisible = [{"label": e["text"] or e["desc"] or e["id"], "type": e["type"], "bounds": e["bounds"],
                  "fg_bg": [(e.get("ink") or {}).get("fg"), (e.get("ink") or {}).get("bg")]}
                 for e in h if e.get("ink") is not None and not e["ink"].get("ink_px") and (e["text"] or e["type"] == "Image")]
    hard = [d for d in st["differences"] if not d.get("dynamic_suspect")]
    return {"android_screen": list(ascreen), "harmony_screen": list(hscreen),
            "android_screen_dp": [round(ascreen[0] / density_a, 1), round(ascreen[1] / density_a, 1)] if density_a else None,
            "harmony_screen_vp": [round(hscreen[0] / density_h, 1), round(hscreen[1] / density_h, 1)] if density_h else None,
            "status_bar_px": {"android": a_top_px, "harmony": h_top, "tops_from": "status_bar" if both else "screen"},
            "structure": st, "measure": table, "common_offset": shift, "harmony_invisible": invisible,
            "font_suspects": fonts,
            # texts actually drawn on HarmonyOS (ink found, or no screenshot to check) and Android text -> resource-id
            "harmony_drawn": sorted({hui.norm_label(e["text"]) for e in h if e["text"]
                                     and (e.get("ink") is None or e["ink"].get("ink_px"))}),
            "android_ids": {hui.norm_label(e["text"] or e["desc"]): e["id"] for e in a if e["id"] and (e["text"] or e["desc"])},
            "summary": {"missing": sum(1 for d in hard if d["category"] == "missing"),
                        "invisible": len(invisible),
                        "font": len(fonts),
                        "extra": sum(1 for d in hard if d["category"] == "extra"),
                        "order": sum(1 for d in hard if d["category"] == "order"),
                        "max_offset": max((max(abs(r["dx"]), abs(r["dy"]), abs(r.get("dy_residual") or 0)) for r in table
                                           if not r["data"]), default=0),
                        "max_size": max((max(abs(r["dw"]), abs(r["dh"])) for r in table
                                         if not r["data"] and r["size_comparable"]), default=0)}}
