"""The Android baseline (android_fast_traverse output) as a walk plan for HarmonyOS.

Every unit of android_traverse_screenshots/index.json is one state to reproduce. Automatic units hang off
their parent (aft.parent) through the control in aft.via; manual units carry their own click_path from the
root page. The plan never reads _aft/: index.json and meta.json are the contract.
"""
from __future__ import annotations

import json
import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from . import hui

BOUNDS_RE = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")
OUT_NAME = "android_traverse_screenshots"


@dataclass
class Step:
    """One Android action, enough to find the same control on HarmonyOS."""
    action: str                # tap | back | swipe | text
    label: str = ""
    text: str = ""
    desc: str = ""
    rid: str = ""
    cls: str = ""
    center: tuple | None = None    # Android px
    bounds: tuple | None = None
    screen: tuple | None = None    # Android screen size, to compare positions as ratios
    scroll_index: int = 0
    family: str = ""
    direction: str = ""            # swipe
    chrome: bool = False
    src: str = ""                  # Android screen (activity) the step was taken on
    context: tuple = ()            # texts around the control on the Android screen (tells same-label controls apart)
    occurrence: int = 0            # index among same-key controls on the Android screen (aft key '#k')
    family_size: int = 0           # size of the repeated-control family it belongs to
    peers: frozenset = frozenset()  # every text on that Android screen (normalized): other controls, not this one
    near: str = ""                 # unlabelled control: the text beside it on the same row

    def as_dict(self) -> dict:
        return {k: (list(v) if isinstance(v, tuple) else v) for k, v in self.__dict__.items()
                if k != "peers" and v not in (None, "", 0, False)}

    @property
    def ratio(self) -> tuple | None:
        if not self.center or not self.screen:
            return None
        return self.center[0] / max(1, self.screen[0]), self.center[1] / max(1, self.screen[1])

    @property
    def size_ratio(self) -> tuple | None:
        if not self.bounds or not self.screen:
            return None
        x1, y1, x2, y2 = self.bounds
        return (x2 - x1) / max(1, self.screen[0]), (y2 - y1) / max(1, self.screen[1])


@dataclass
class Unit:
    page_id: str
    number: int
    kind: str                  # page | view_state | instance | danger_dialog | manual
    label: str
    activity: str
    layer: str
    parent: str | None
    step: Step | None          # from parent (automatic units)
    path: list                 # manual units: steps from the root page
    frames: list               # [(png, xml)] relative to the Android OUT
    density: float | None
    readings: dict
    replayable: bool = True
    drive_reason: str = ""     # why a manual unit needs a hand-written HarmonyOS drive
    vframes: int = 1           # frames of the main container (first frame included)
    hframes: int = 0           # most frames of one auto-discovered horizontal strip
    children: list = field(default_factory=list)

    @property
    def is_root(self) -> bool:
        return self.parent is None and self.kind == "page"


def parse_bounds(value) -> tuple | None:
    if isinstance(value, (list, tuple)) and len(value) == 4:
        return tuple(int(v) for v in value)
    m = BOUNDS_RE.search(value or "")
    return tuple(int(v) for v in m.groups()) if m else None


def xml_screen(path: str) -> tuple | None:
    try:
        root = ET.parse(path).getroot()
    except Exception:
        return None
    best = None
    for el in root.iter("node"):
        b = parse_bounds(el.attrib.get("bounds", ""))
        if b and (best is None or (b[2] * b[3]) > (best[0] * best[1])):
            best = (b[2], b[3])
    return best


def xml_texts(path: str, package: str = "") -> set:
    """Visible texts of an Android dump, normalised like HarmonyOS texts. A background layer covered by a
    same-window popup (two stacked near-full-screen children with content; the last one is on top) is skipped,
    as android_fast_traverse does."""
    out = set()
    try:
        root = ET.parse(path).getroot()
    except Exception:
        return out
    screen = xml_screen(path) or (1, 1)
    full = 0.7 * screen[0] * screen[1]

    def area(el):
        b = parse_bounds(el.attrib.get("bounds", "")) or (0, 0, 0, 0)
        return max(0, b[2] - b[0]) * max(0, b[3] - b[1])

    def has_content(el):
        return any((e.attrib.get("text") or e.attrib.get("content-desc") or e.attrib.get("clickable") == "true")
                   for e in el.iter("node"))
    covered = set()
    for p in root.iter("node"):
        kids = [c for c in p if c.tag == "node"]
        big = [c for c in kids if area(c) >= full and has_content(c)]
        for k in big[:-1]:
            covered.update(id(e) for e in k.iter("node"))
    for el in root.iter("node"):
        if id(el) in covered:
            continue
        a = el.attrib
        if package and a.get("package") and a.get("package") != package:
            continue
        for k in ("text", "content-desc"):
            t = (a.get(k) or "").strip()
            if t and not hui.DYNAMIC_TEXT.match(t) and not a.get("class", "").endswith("EditText"):
                out.add(hui.norm_label(t))
    return out


def near_text(xml_path: str, bounds: tuple | None) -> str:
    """The text on the same row nearest to an unlabelled control (the label beside a radio or check icon)."""
    if not bounds:
        return ""
    try:
        root = ET.parse(xml_path).getroot()
    except Exception:
        return ""
    x1, y1, x2, y2 = bounds
    cy, best, gap = (y1 + y2) / 2, "", None
    for el in root.iter("node"):
        t = hui.norm_label(el.attrib.get("text") or "")
        b = parse_bounds(el.attrib.get("bounds", ""))
        if not t or not b or hui.DYNAMIC_TEXT.match(t) or not (b[1] <= cy <= b[3]):
            continue
        d = max(0, b[0] - x2, x1 - b[2])  # horizontal gap; 0 = overlapping
        if d <= 3 * (x2 - x1) + 40 and (gap is None or d < gap):
            best, gap = t, d
    return best


def context_texts(xml_path: str, bounds: tuple | None, center: tuple | None = None) -> tuple:
    """Texts of the smallest container (>= 3 texts) around the control at bounds/center on an Android screen."""
    if not bounds and not center:
        return ()
    try:
        root = ET.parse(xml_path).getroot()
    except Exception:
        return ()
    parent = {c: p for p in root.iter() for c in p}
    target = None
    for el in root.iter("node"):
        b = parse_bounds(el.attrib.get("bounds", ""))
        if not b:
            continue
        if bounds and b == tuple(bounds):
            target = el
            break
        if center and b[0] <= center[0] < b[2] and b[1] <= center[1] < b[3]:
            target = el  # deepest last
    if target is None:
        return ()
    el = target
    while el in parent:
        el = parent[el]
        texts = [hui.norm_label(e.attrib.get("text") or e.attrib.get("content-desc") or "") for e in el.iter("node")]
        texts = [t for t in texts if t and not hui.DYNAMIC_TEXT.match(t)]
        if len(set(texts)) >= 3:
            return tuple(sorted(set(texts))[:40])
    return ()


def number_of(page_id: str) -> int:
    m = re.search(r"_(\d{4})_", page_id + "_")
    return int(m.group(1)) if m else 0


class Plan:
    def __init__(self, out_dir: str):
        self.out = os.path.abspath(out_dir)
        if os.path.basename(self.out) != OUT_NAME and os.path.isdir(os.path.join(self.out, OUT_NAME)):
            self.out = os.path.join(self.out, OUT_NAME)
        idx_path = os.path.join(self.out, "index.json")
        if not os.path.exists(idx_path):
            raise FileNotFoundError(f"no index.json in {self.out}: run android_fast_traverse first")
        with open(idx_path, encoding="utf-8") as f:
            index = json.load(f)
        self.units: dict[str, Unit] = {}
        self.package = ""
        self._screens: dict = {}
        for meta in index:
            u = self._unit(meta)
            self.units[u.page_id] = u
        for u in self.units.values():
            if u.parent and u.parent in self.units:
                self.units[u.parent].children.append(u.page_id)
            elif u.parent:  # parent missing from index (replaced or dropped): hang the unit under the root
                u.parent = None
                u.kind = "orphan"
        for u in self.units.values():
            u.children.sort(key=lambda pid: (self.units[pid].kind == "view_state", self.units[pid].number))
        roots = [u for u in self.units.values() if u.is_root]
        self.root: Unit | None = min(roots, key=lambda u: u.number) if roots else None
        root_activity = self.root.activity if self.root else ""
        for u in self.units.values():
            if u.kind in ("manual", "orphan"):
                self._classify_manual(u, root_activity)

    # ---------------------------------------------------------------- building
    def _abs(self, rel: str) -> str:
        return rel if os.path.isabs(rel) else os.path.join(self.out, rel)

    def screen_of(self, rel_xml: str) -> tuple | None:
        if rel_xml not in self._screens:
            self._screens[rel_xml] = xml_screen(self._abs(rel_xml))
        return self._screens[rel_xml]

    def _unit(self, meta: dict) -> Unit:
        a = meta.get("aft") or {}
        pid = meta["page_id"]
        if not self.package:
            self.package = ((a.get("registry") or {}).get("context") or {}).get("package", "")
        shots = meta.get("screenshots") or [meta.get("screenshot")]
        xmls = meta.get("view_xmls") or [meta.get("view_xml")]
        frames = [(p, x) for p, x in zip(shots, xmls) if p and x]
        kind = a.get("kind") or ("manual" if pid.startswith("manual_") else "page")
        parent = a.get("parent")
        path = [self._step(s, frames) for s in (meta.get("click_path") or [])]
        step = None
        if kind != "manual" and parent:
            via = a.get("via") or {}
            last = (meta.get("click_path") or [{}])[-1]
            step = self._via_step(via, last)
        cap = a.get("capture") or {}
        extra = [e for e in cap.get("extra") or () if isinstance(e, dict)]
        hframes = max([int(e.get("frames") or 0) for e in extra if e.get("axis") == "horizontal"] or [0])
        vframes = max(1, len(frames) - sum(int(e.get("frames") or 0) for e in extra))
        return Unit(page_id=pid, number=number_of(pid), kind=kind, label=meta.get("label", ""),
                    vframes=vframes, hframes=hframes,
                    activity=a.get("activity", ""), layer=a.get("layer", ""), parent=parent if kind != "manual" else None,
                    step=step, path=path, frames=frames, density=meta.get("density_factor"),
                    readings=a.get("readings") or {})

    def _via_step(self, via: dict, last: dict) -> Step:
        scroll = last.get("scroll_info") or {}
        label = via.get("label") or last.get("element") or ""
        if label.startswith(("com.", "android:")) and ":id/" in label:
            label = ""  # aft prints the resource-id when a control has no label
        return Step(action="tap", label=label, text=via.get("text") or last.get("text", ""),
                    desc=via.get("content-desc") or last.get("content-desc", ""),
                    rid=(via.get("resource-id") or last.get("resource-id") or "").rsplit("/", 1)[-1],
                    cls=(via.get("class") or "").rsplit(".", 1)[-1],
                    center=tuple(via.get("center") or last.get("center") or ()) or None,
                    bounds=parse_bounds(via.get("bounds")),
                    scroll_index=int(scroll.get("scroll_index") or via.get("scroll_index") or 0),
                    family=via.get("family", "") or via.get("sib", ""), chrome=bool(via.get("chrome")),
                    occurrence=int((re.search(r"#(\d+)$", via.get("key") or "") or [0, 0])[1]),
                    family_size=int(via.get("family_size") or 0))

    def _step(self, s: dict, frames: list) -> Step:
        el = s.get("element") or ""
        scroll = s.get("scroll_info") or {}
        src = (s.get("from") or "").split("·")[0]
        if el == "BACK":
            return Step(action="back", src=src)
        m = re.fullmatch(r"swipe (up|down|left|right)", el)
        if m:
            return Step(action="swipe", direction=m.group(1), src=src,
                        bounds=parse_bounds(scroll.get("container_bounds")))
        m = re.fullmatch(r"text\((\d+)\)", el)
        if m:
            return Step(action="text", label=el, src=src)
        label = el
        if label.startswith(("com.", "android:")) and ":id/" in label:
            label = ""
        m = re.fullmatch(r"@(\d+),(\d+)", label)
        if m:  # a coordinate tap in the Android drive: position only
            label = ""
            s = {**s, "center": s.get("center") or [int(m.group(1)), int(m.group(2))]}
        return Step(action="tap", label=label, text=s.get("text", ""), desc=s.get("content-desc", ""),
                    rid=(s.get("resource-id") or "").rsplit("/", 1)[-1],
                    center=tuple(s.get("center") or ()) or None, src=src,
                    scroll_index=int(scroll.get("scroll_index") or 0))

    def _classify_manual(self, u: Unit, root_activity: str) -> None:
        if not u.path:
            if u.activity != root_activity:
                u.replayable, u.drive_reason = False, "first_launch"
            return
        if any(s.action == "text" for s in u.path):
            u.replayable, u.drive_reason = False, "text_input"
            return
        if u.path[0].src and root_activity and u.path[0].src != root_activity:
            u.replayable, u.drive_reason = False, "first_launch"  # starts before the root page exists
            return
        u.replayable, u.drive_reason = True, ""

    def attach_screens(self) -> None:
        """Fill Step.screen (Android screen size) and Step.context (texts around the control)."""
        for u in self.units.values():
            src = self.units.get(u.parent) if u.parent else self.root
            scr = self.screen_of(src.frames[0][1]) if src and src.frames else None
            if u.step:
                u.step.screen = scr
                if src and src.frames:
                    k = min(u.step.scroll_index, len(src.frames) - 1)
                    u.step.context = context_texts(self._abs(src.frames[k][1]), u.step.bounds, u.step.center)
                    u.step.peers = frozenset(hui.norm_label(t) for t in xml_texts(self._abs(src.frames[k][1]))) - \
                        {hui.norm_label(u.step.label or u.step.text or u.step.desc)}
                    if not (u.step.label or u.step.text or u.step.desc):
                        u.step.near = near_text(self._abs(src.frames[k][1]), u.step.bounds)
            for s in u.path:
                s.screen = scr or (self.screen_of(self.root.frames[0][1]) if self.root and self.root.frames else None)

    # ---------------------------------------------------------------- queries
    def order(self) -> list[str]:
        """Depth-first order of automatic units from the root, then the other top-level units by number."""
        out, seen = [], set()

        def dfs(pid: str) -> None:
            if pid in seen:
                return
            seen.add(pid)
            out.append(pid)
            for c in self.units[pid].children:
                dfs(c)
        if self.root:
            dfs(self.root.page_id)
        for u in sorted(self.units.values(), key=lambda x: x.number):
            if u.page_id not in seen and u.kind not in ("manual", "orphan"):
                dfs(u.page_id)
        for u in sorted(self.units.values(), key=lambda x: x.number):
            if u.page_id not in seen:
                dfs(u.page_id)
        return out

    def click_steps(self, pid: str) -> list:
        """The Android click path of a unit. A path step is a bare copy of a tap some unit's richer via step also
        describes (list membership, bounds, surroundings): each ancestor's final step, and any other tap of the
        same label on the same screen, is replaced by that via step -- one control, one description."""
        u = self.units[pid]
        steps = list(u.path)
        for a in self.ancestors(pid) + [pid]:
            au = self.units[a]
            i = len(au.path) - 1
            if au.step and 0 <= i < len(steps) and steps[i].action == "tap" and \
                    hui.norm_label(steps[i].label) == hui.norm_label(au.step.label):
                steps[i] = au.step
        if not hasattr(self, "_taps"):
            self._taps = {}
            for x in self.units.values():
                p = self.units.get(x.parent) if x.parent else None
                if x.step and p and hui.norm_label(x.step.label):
                    self._taps.setdefault((p.activity, hui.norm_label(x.step.label)), x.step)
        return [self._taps.get((s.src, hui.norm_label(s.label)), s) if s.action == "tap" and s.src and
                hui.norm_label(s.label) and not s.family_size and s not in self._taps.values() else s for s in steps]

    def ancestors(self, pid: str) -> list[str]:
        out, u = [], self.units[pid]
        while u.parent:
            out.append(u.parent)
            u = self.units[u.parent]
        return out[::-1]

    def descendants(self, pid: str) -> list[str]:
        out, stack = [], list(self.units[pid].children)
        while stack:
            c = stack.pop()
            out.append(c)
            stack.extend(self.units[c].children)
        return out

    def texts(self, pid: str) -> set:
        u = self.units[pid]
        out = set()
        for _, x in u.frames:
            out |= xml_texts(self._abs(x), self.package)
        return out

    def first_texts(self, pid: str) -> set:
        u = self.units[pid]
        return xml_texts(self._abs(u.frames[0][1]), self.package) if u.frames else set()

    def summary(self) -> dict:
        kinds: dict = {}
        for u in self.units.values():
            kinds[u.kind] = kinds.get(u.kind, 0) + 1
        drive = [u.page_id for u in self.units.values() if not u.replayable]
        return {"android_out": self.out, "package": self.package, "units": len(self.units), "kinds": kinds,
                "root": self.root.page_id if self.root else None,
                "frames": sum(len(u.frames) for u in self.units.values()),
                "needs_drive": drive}
