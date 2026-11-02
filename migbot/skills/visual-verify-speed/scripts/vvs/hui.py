"""HarmonyOS UI hierarchy (uitest dumpLayout JSON): nodes, windows, layers, labels, candidates.

Pure functions, no device access. Field names follow android_fast_traverse's ui.Node where the meaning is the
same, so capture and matching logic reads alike on both platforms.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

BOUNDS_RE = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")
DIGITS = re.compile(r"\d+")
DYNAMIC_TEXT = re.compile(r"^[\d\s:./°℃%+\-~]+$")

# Same word lists as android_fast_traverse: the HarmonyOS walk never taps more than the Android walk did.
DANGER_WORDS = (
    "删除", "清空", "清除", "注销", "退出登录", "退出账号", "登出", "卸载", "支付", "付款", "购买",
    "充值", "开通", "订阅", "续费", "拨打", "呼叫", "举报", "投诉", "发送", "发布", "提交", "分享",
    "下载", "安装", "解绑", "移除", "重置", "恢复出厂", "取消订单", "取消关注", "取消收藏", "取消预约",
    "退订", "退款", "解约",
    "delete", "del", "trash", "erase", "wipe", "unbind", "remove", "clear", "logout", "log out", "sign out",
    "uninstall", "pay", "purchase", "buy", "subscribe", "unsubscribe", "call", "report", "send", "publish",
    "submit", "share", "download", "install", "reset", "refund", "cancel order",
)
CONFIRM_WORDS = ("确定", "确认", "保存", "提交", "完成", "同意并", "好的", "ok", "confirm", "save", "submit", "yes",
                 "done", "finish", "apply")
CANCEL_WORDS = ("取消", "关闭", "暂不", "暂不需要", "以后再说", "下次再说", "不了", "不用了", "否", "跳过", "我知道了",
                "知道了", "我再想想", "再想想", "算了", "cancel", "close", "not now", "later", "no", "no thanks",
                "skip", "dismiss")
# ArkUI component types that draw a layer above the page (same window).
DIALOG_TYPES = ("Dialog", "CustomDialog", "AlertDialog", "ActionSheet", "Popup", "Menu", "SheetPage", "Sheet",
                "BindSheet", "DatePickerDialog", "TextPickerDialog", "TimePickerDialog", "CalendarPickerDialog",
                "ModalPage", "SelectMenu")
SCROLL_TYPES = ("List", "Scroll", "Grid", "WaterFlow", "Swiper", "Tabs", "Refresh", "ListItemGroup")
INPUT_TYPES = ("TextInput", "TextArea", "Search", "RichEditor")
# components whose dump `text` is a name / group / value parameter, not something drawn on screen
NAME_TYPES = ("Checkbox", "CheckboxGroup", "Radio")
SYSTEM_BUNDLES = ("com.ohos.systemui", "com.ohos.sceneboard", "com.ohos.launcher")
PERMISSION_BUNDLES = ("com.ohos.permissionmanager", "com.huawei.hmos.permissionmanager")
LOADING_RE = re.compile(r"加载中|正在加载|请稍候|请稍等|loading", re.I)


@dataclass(eq=False)
class Node:
    idx: int
    parent: int
    depth: int
    type: str
    id: str
    key: str
    text: str
    desc: str
    bounds: tuple
    clickable: bool
    long_clickable: bool
    checkable: bool
    checked: bool
    selected: bool
    enabled: bool
    scrollable: bool
    focused: bool
    bundle: str = ""
    page_path: str = ""
    window: str = ""
    bg: str = ""
    hint: str = ""  # TextInput / TextArea placeholder (drawn while the field is empty; `text` is "" then)
    children: list = field(default_factory=list)
    covered: bool = False

    @property
    def center(self) -> tuple:
        x1, y1, x2, y2 = self.bounds
        return (x1 + x2) // 2, (y1 + y2) // 2

    @property
    def area(self) -> int:
        x1, y1, x2, y2 = self.bounds
        return max(0, x2 - x1) * max(0, y2 - y1)

    @property
    def ident(self) -> str:
        return self.key or self.id


@dataclass
class Window:
    root: int            # index of the window root node
    bundle: str
    ability: str
    page_path: str
    window_id: str
    focused: bool
    bounds: tuple


def parse_bounds(value: str) -> tuple:
    m = BOUNDS_RE.search(value or "")
    return tuple(int(v) for v in m.groups()) if m else (0, 0, 0, 0)


def _flag(a: dict, name: str) -> bool:
    return str(a.get(name, "")).lower() == "true"


def parse(raw: bytes | str | dict) -> tuple[list[Node], list[Window]]:
    """dumpLayout JSON -> (document-ordered node list, windows). Invisible subtrees are dropped."""
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", errors="replace")
    if isinstance(raw, str):
        starts = [i for i in (raw.find("{"), raw.find("[")) if i >= 0]
        if not starts:
            raise ValueError("no JSON in dump")
        start = min(starts)
        end = raw.rfind("]" if raw[start] == "[" else "}")
        raw = json.loads(raw[start:end + 1])
    if isinstance(raw, list):  # `dumpLayout -i`: one object per window, no virtual root
        tops = [parse_bounds((w.get("attributes") or {}).get("bounds", "")) for w in raw if isinstance(w, dict)]
        sw = max((b[2] for b in tops), default=0)
        sh = max((b[3] for b in tops), default=0)
        raw = {"attributes": {"type": "", "bounds": f"[0,0][{sw},{sh}]"}, "children": raw}
    nodes: list[Node] = []
    windows: list[Window] = []

    def walk(el: dict, parent: int, depth: int, bundle: str, page: str, window: str) -> None:
        a = el.get("attributes") or {}
        if str(a.get("visible", "true")).lower() == "false":
            return
        b = a.get("bundleName") or ""
        if b:
            bundle, page = b, a.get("pagePath") or page
            window = str(a.get("hostWindowId") or window)
        elif a.get("pagePath"):
            page = a.get("pagePath")
        n = Node(idx=len(nodes), parent=parent, depth=depth, type=a.get("type", ""), id=a.get("id", "") or "",
                 key=a.get("key", "") or "", text=a.get("text", "") or "", desc=a.get("description", "") or "",
                 bounds=parse_bounds(a.get("bounds", "")), clickable=_flag(a, "clickable"),
                 long_clickable=_flag(a, "longClickable"), checkable=_flag(a, "checkable"),
                 checked=_flag(a, "checked"), selected=_flag(a, "selected"),
                 enabled=str(a.get("enabled", "true")).lower() != "false", scrollable=_flag(a, "scrollable"),
                 focused=_flag(a, "focused"), bundle=bundle, page_path=page,
                 window=str(a.get("hostWindowId") or window), bg=str(a.get("backgroundColor") or ""),
                 hint=a.get("hint", "") or "")
        nodes.append(n)
        if parent >= 0:
            nodes[parent].children.append(n.idx)
        if b:
            windows.append(Window(n.idx, b, a.get("abilityName") or "", a.get("pagePath") or "",
                                  n.window, _flag(a, "focused"), n.bounds))
        for c in el.get("children") or ():
            walk(c, n.idx, depth + 1, bundle, page, n.window)

    walk(raw, -1, 0, "", "", "")  # the top object is a virtual root (screen bounds) holding one child per window
    if not nodes:
        raise ValueError("empty hierarchy")
    mark_layers(nodes)
    return nodes, windows


def subtree(nodes: list[Node], n: Node) -> list[int]:
    out, stack = [], [n.idx]
    while stack:
        i = stack.pop()
        out.append(i)
        stack.extend(nodes[i].children)
    return out


def ancestors(nodes: list[Node], n: Node):
    p = n.parent
    while p >= 0:
        yield nodes[p]
        p = nodes[p].parent


def screen_size(nodes: list[Node]) -> tuple:
    tops = [n.bounds for n in nodes if n.parent < 0] or [nodes[0].bounds]
    return max(b[2] for b in tops), max(b[3] for b in tops)


def _has_content(nodes: list[Node], n: Node) -> bool:
    return any(nodes[i].text.strip() or nodes[i].desc.strip() or nodes[i].clickable for i in subtree(nodes, n))


def _opaque(n: Node) -> bool:
    """backgroundColor #AARRGGBB (or #RRGGBB) with visible alpha."""
    c = n.bg.strip().lstrip("#")
    if len(c) == 8:
        return int(c[:2], 16) >= 0x40
    return len(c) == 6


def _covers(nodes: list[Node], n: Node) -> bool:
    """A stacked full-size child hides its earlier siblings only when it paints a background or its content
    spreads over at least half of it (a transparent Stack holding a progress bar hides nothing)."""
    if _opaque(n):
        return True
    boxes = [nodes[i].bounds for i in subtree(nodes, n)[1:]
             if (nodes[i].text.strip() or nodes[i].desc.strip() or nodes[i].clickable or _opaque(nodes[i]))
             and nodes[i].area > 0]
    if not boxes:
        return False
    x1, y1 = min(b[0] for b in boxes), min(b[1] for b in boxes)
    x2, y2 = max(b[2] for b in boxes), max(b[3] for b in boxes)
    return (x2 - x1) * (y2 - y1) >= 0.5 * max(1, n.area)


def mark_layers(nodes: list[Node]) -> None:
    """Hide what a same-window layer covers: an ArkUI dialog/sheet node, or the last of several stacked
    near-full-screen children that carry content and actually cover (popup libraries)."""
    width, height = screen_size(nodes)
    full = 0.7 * width * height
    web = {i for n in nodes if n.type == "Web" for i in subtree(nodes, n)}
    for p in nodes:
        if len(p.children) < 2 or p.covered or p.idx in web or not p.bundle:
            continue  # window stacking (children of the virtual root) is decided by focus, not by order
        big = [nodes[c] for c in p.children if nodes[c].area >= full and _has_content(nodes, nodes[c])]
        covering = [b for b in big[1:] if _covers(nodes, b)]
        if not covering:
            continue
        top = covering[-1]
        for k in big:
            if k is top:
                break
            for i in subtree(nodes, k):
                nodes[i].covered = True
    dialogs = [n for n in nodes if n.type in DIALOG_TYPES and n.area > 0 and _has_content(nodes, n)]
    if dialogs:
        top = dialogs[-1]
        keep = set(subtree(nodes, top)) | {a.idx for a in ancestors(nodes, top)}
        for n in nodes:
            if n.window == top.window and n.idx not in keep:
                n.covered = True


def dialog_node(nodes: list[Node]) -> Node | None:
    hits = [n for n in nodes if n.type in DIALOG_TYPES and n.area > 0 and not n.covered]
    return hits[-1] if hits else None


def layered(nodes: list[Node]) -> bool:
    return any(n.covered for n in nodes)


def norm_label(text: str) -> str:
    return re.sub(r"[\s　]+", "", (text or "").strip()).lower()


def digit_pattern(text: str) -> str:
    return DIGITS.sub("#", norm_label(text))


def label_of(nodes: list[Node], n: Node) -> str:
    """Own text/description, else the first descendant text."""
    if n.text.strip():
        return n.text.strip()
    if n.desc.strip():
        return n.desc.strip()
    stack = list(n.children)
    while stack:
        c = nodes[stack.pop(0)]
        if c.covered:
            continue
        if c.text.strip():
            return c.text.strip()
        if c.desc.strip():
            return c.desc.strip()
        stack[0:0] = c.children
    return ""


def app_nodes(nodes: list[Node], bundle: str) -> list[Node]:
    return [n for n in nodes if n.bundle == bundle and not n.covered]


def texts(nodes: list[Node], bundle: str) -> set:
    """Visible texts of the app, ignoring pure numbers/times (they refresh on their own)."""
    return {norm_label(n.text) for n in nodes if n.bundle == bundle and not n.covered and n.text.strip()
            and n.type not in INPUT_TYPES and not DYNAMIC_TEXT.match(n.text.strip())}


def text_patterns(nodes: list[Node], bundle: str) -> set:
    return {DIGITS.sub("#", t) for t in texts(nodes, bundle)}


def placed_texts(nodes: list[Node], bundle: str) -> frozenset:
    """What is shown where: visible texts (digits normalised) with a coarse place (1/20 width, 1/40 height). A
    selection mark that moves from one row to another (◉ / ○ swapping places) changes this, not the text set."""
    w, h = screen_size(nodes)
    return frozenset((DIGITS.sub("#", norm_label(n.text)), n.center[0] * 20 // max(1, w), n.center[1] * 40 // max(1, h))
                     for n in nodes if n.bundle == bundle and not n.covered and n.text.strip()
                     and n.type not in INPUT_TYPES and not DYNAMIC_TEXT.match(n.text.strip()))


def structure(nodes: list[Node], bundle: str) -> frozenset:
    """Page identity without text data: developer ids plus labels outside repeated cells (digits normalised)."""
    app = [n for n in nodes if n.bundle == bundle and not n.covered]
    siblings: dict = {}
    for n in app:
        if n.parent >= 0:
            x1, y1, x2, y2 = n.bounds
            siblings.setdefault((n.parent, n.type, x2 - x1, y2 - y1), []).append(n)
    cells = set()
    for group in siblings.values():
        if len(group) >= 3:
            for c in group:
                cells.update(subtree(nodes, c))
    out = set()
    for n in app:
        if n.ident:
            out.add(f"{n.type}|{n.ident}")
        if n.idx in cells:
            continue
        label = n.text.strip() or n.desc.strip()
        if label and len(label) <= 40 and not DYNAMIC_TEXT.match(label):
            out.add("label:" + digit_pattern(label))
    return frozenset(out)


def containment(observed: frozenset, known: frozenset) -> float:
    if not observed:
        return 1.0 if not known else 0.0
    return len(observed & known) / len(observed)


def jaccard(a: frozenset | set, b: frozenset | set) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def word_hit(words, *parts: str) -> str:
    hay = " ".join(re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", p) for p in parts if p).lower()
    tokens = " " + " ".join(t for t in re.split(r"[^a-z0-9]+", hay) if t) + " "
    for w in words:
        lw = w.lower()
        if re.search(r"[a-z]", lw):
            if " " + " ".join(re.split(r"[^a-z0-9]+", lw)).strip() + " " in tokens:
                return w
        elif lw in hay:
            return w
    return ""


def danger_word(*parts: str) -> str:
    return word_hit(DANGER_WORDS, *parts)


def is_confirm_label(label: str) -> bool:
    return bool(word_hit(CONFIRM_WORDS, label))


def is_cancel_label(label: str) -> bool:
    n = norm_label(label)
    return bool(n) and n in {norm_label(w) for w in CANCEL_WORDS} and not danger_word(label)


def _inside(b: tuple, x: int, y: int) -> bool:
    return b[0] <= x < b[2] and b[1] <= y < b[3]


def tap_point(nodes: list[Node], n: Node, bundle: str = "") -> tuple | None:
    """Where to tap a control so that the control itself gets the tap, or None when every candidate point is
    covered. Two things can take the tap instead: a clickable / scrollable child inside the control (its centre
    sits on an inner list or button), and a layer drawn after it that overlaps it (a bottom tab bar over the last
    row of a list, a floating button). The layouts differ between the platforms, so a point that worked on Android
    can be covered on HarmonyOS."""
    t = tap_target(nodes, n)
    sub = subtree(nodes, t)
    own, last = set(sub), max(sub)
    anc = {a.idx for a in ancestors(nodes, t)}
    inner = [nodes[i] for i in sub[1:] if nodes[i].clickable or nodes[i].scrollable]
    over = [m for m in nodes if m.idx > last and m.idx not in anc and m.area > 0 and not m.covered
            and (not bundle or m.bundle == bundle) and (m.clickable or m.scrollable or _opaque(m))]
    w, h = screen_size(nodes)

    def free(x: int, y: int) -> bool:
        return (0 <= x < w and 0 <= y < h and _inside(t.bounds, x, y)
                and not any(_inside(c.bounds, x, y) for c in inner)
                and not any(_inside(o.bounds, x, y) for o in over))
    x1, y1, x2, y2 = t.bounds
    cands = [t.center]
    cands += [nodes[i].center for i in sub[1:] if (nodes[i].text.strip() or nodes[i].desc.strip())]
    cands += [(x1 + (x2 - x1) * fx // 8, y1 + (y2 - y1) * fy // 8) for fy in (4, 2, 6, 1, 7) for fx in (4, 2, 6)]
    for x, y in cands:
        if free(int(x), int(y)):
            return int(x), int(y)
    return None


def tap_target(nodes: list[Node], n: Node) -> Node:
    """A label inside a clickable container is tapped through the container (unless the container is huge)."""
    if n.clickable or n.checkable:
        return n
    w, h = screen_size(nodes)
    for a in ancestors(nodes, n):
        if a.covered:
            break
        if a.clickable or a.checkable:
            return a if a.area < 0.6 * w * h else n
    return n


def visible_on_screen(nodes: list[Node], n: Node) -> bool:
    w, h = screen_size(nodes)
    cx, cy = n.center
    x1, y1, x2, y2 = n.bounds
    return n.area > 0 and 0 <= cx < w and 0 <= cy < h and (x2 - x1) >= 8 and (y2 - y1) >= 8


@dataclass
class Cand:
    node: Node
    label: str
    norm: str
    pattern: str


def labelled(nodes: list[Node], bundle: str) -> list[Cand]:
    """Every visible app node with a label, mapped to the node that receives the tap; deduplicated by target."""
    out, seen = [], set()
    for n in nodes:
        if n.bundle != bundle or n.covered or not n.enabled or not visible_on_screen(nodes, n):
            continue
        label = n.text.strip() or n.desc.strip()
        if not label and (n.clickable or n.checkable):
            label = label_of(nodes, n)
        if not label:
            continue
        t = tap_target(nodes, n)
        k = (t.idx, norm_label(label))
        if k in seen:
            continue
        seen.add(k)
        out.append(Cand(t, label, norm_label(label), digit_pattern(label)))
    # Nested clickables with one label (an outer and an inner Column of a tab item) are one control: keep the inner.
    inner = []
    for c in out:
        sub = set(subtree(nodes, c.node))
        if any(o is not c and o.norm == c.norm and o.node.idx in sub and o.node.idx != c.node.idx for o in out):
            continue
        inner.append(c)
    return inner


def clickables(nodes: list[Node], bundle: str) -> list[Node]:
    out = []
    for n in nodes:
        if n.bundle != bundle or n.covered or not n.enabled or not (n.clickable or n.checkable):
            continue
        if n.type in INPUT_TYPES or not visible_on_screen(nodes, n):
            continue
        if not (n.text.strip() or n.desc.strip()) and any(nodes[i].clickable for i in subtree(nodes, n)[1:]):
            continue  # container whose clickable children are the real targets
        out.append(n)
    return out


def node_at(nodes: list[Node], x: int, y: int, bundle: str = "") -> Node | None:
    hit = None
    for n in nodes:
        if n.covered or (bundle and n.bundle != bundle):
            continue
        x1, y1, x2, y2 = n.bounds
        if x1 <= x < x2 and y1 <= y < y2:
            hit = n
    return hit


# ---------------------------------------------------------------- selectors (profile, drive, popup rules)

def matches(nodes: list[Node], n: Node, sel: dict) -> bool:
    if "text" in sel:
        want = norm_label(sel["text"])
        own = norm_label(n.text) or norm_label(n.desc)
        if want != own and not (not own and (n.clickable or n.checkable) and want == norm_label(label_of(nodes, n))):
            return False
    if "text_contains" in sel and norm_label(sel["text_contains"]) not in norm_label(n.text + n.desc):
        return False
    if "desc" in sel and norm_label(sel["desc"]) != norm_label(n.desc):
        return False
    if "id" in sel and sel["id"] not in (n.id, n.key):
        return False
    if "type" in sel and sel["type"] != n.type:
        return False
    if "page" in sel and not n.page_path.endswith(sel["page"]):
        return False
    return any(k in sel for k in ("text", "text_contains", "desc", "id", "type"))


def select(nodes: list[Node], sel: dict, bundle: str | None = None) -> list[Node]:
    hits = [n for n in nodes if (not bundle or n.bundle == bundle) and not n.covered and matches(nodes, n, sel)]
    if "text" in sel:
        own = [n for n in hits if norm_label(n.text) == norm_label(sel["text"])
               or norm_label(n.desc) == norm_label(sel["text"])]
        if own:
            return own
    return hits


# ---------------------------------------------------------------- containers

def scroll_containers(nodes: list[Node], bundle: str) -> list[Node]:
    out = []
    for n in nodes:
        if n.bundle != bundle or n.covered or n.area <= 0:
            continue
        if n.scrollable or n.type in ("List", "Scroll", "Grid", "WaterFlow"):
            out.append(n)
    return out


def container_axis(n: Node, screen: tuple) -> str:
    x1, y1, x2, y2 = n.bounds
    w, h = x2 - x1, y2 - y1
    if n.type in ("Swiper",) or (h < screen[1] * 0.25 and w > 2 * h):
        return "horizontal"
    return "vertical"


def primary_container(nodes: list[Node], bundle: str) -> Node | None:
    screen = screen_size(nodes)
    best = None
    for n in scroll_containers(nodes, bundle):
        if n.type in ("Swiper", "Tabs") or container_axis(n, screen) != "vertical":
            continue
        if n.bounds[3] - n.bounds[1] < screen[1] * 0.25:
            continue
        if best is None or n.area > best.area:
            best = n
    return best


def horizontal_strips(nodes: list[Node], bundle: str) -> list[Node]:
    """Wide read-only horizontal strips with several texts (an hourly forecast)."""
    w, h = screen_size(nodes)
    out = []
    for n in scroll_containers(nodes, bundle):
        if container_axis(n, (w, h)) != "horizontal" or n.type == "Swiper":
            continue
        x1, y1, x2, y2 = n.bounds
        if x2 - x1 < 0.6 * w or x1 < 0 or y1 < 0 or x2 > w or y2 > h:
            continue
        sub = [nodes[i] for i in subtree(nodes, n)[1:]]
        if any(s.clickable or s.checkable for s in sub):
            continue
        if sum(1 for s in sub if s.text.strip()) >= 3:
            out.append(n)
    return out


def container_key(n: Node) -> str:
    return f"{n.type}|{n.ident}|{n.bounds[0]},{n.bounds[2]}"


def find_container(nodes: list[Node], bundle: str, key: str) -> Node | None:
    for n in scroll_containers(nodes, bundle):
        if container_key(n) == key:
            return n
    return None


def inside(n: Node, box: tuple) -> bool:
    x1, y1, x2, y2 = n.bounds
    return x1 >= box[0] - 2 and y1 >= box[1] - 2 and x2 <= box[2] + 2 and y2 <= box[3] + 2 and x2 > x1 and y2 > y1


def loading(nodes: list[Node], bundle: str) -> str:
    w, h = screen_size(nodes)
    for n in nodes:
        if n.bundle != bundle or n.covered or n.area <= 0:
            continue
        if n.text and LOADING_RE.search(n.text):
            return n.text.strip()[:30]
        if n.type in ("LoadingProgress", "Progress") and n.area < 0.1 * w * h:
            return "spinner"
    return ""


def blank_web(nodes: list[Node], bundle: str) -> bool:
    w, h = screen_size(nodes)
    webs = [n for n in nodes if n.bundle == bundle and not n.covered and n.type == "Web" and n.area >= 0.25 * w * h]
    if not webs:
        return False
    return not any((nodes[i].text.strip() or nodes[i].desc.strip()) for web in webs for i in subtree(nodes, web)[1:])


def outline(nodes: list[Node], bundle: str, limit: int = 70) -> str:
    lines = []
    for n in nodes:
        if n.bundle != bundle or n.covered:
            continue
        label = n.text.strip() or n.desc.strip()
        click = n.clickable or n.checkable
        if not label and not click:
            continue
        if not label:
            label = label_of(nodes, n)
        mark = "[c]" if click else ("[s]" if n.scrollable else "   ")
        flags = "".join(f for f, on in ((" sel", n.selected), (" chk", n.checked)) if on)
        cx, cy = n.center
        lines.append(f"{mark} {label[:30] or '-'} ({n.type}{'#' + n.ident if n.ident else ''}) @{cx},{cy}{flags}")
        if len(lines) >= limit:
            lines.append("…")
            break
    return "\n".join(lines)
