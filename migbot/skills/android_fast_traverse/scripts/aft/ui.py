"""UI hierarchy parsing: nodes, page structure, candidates, outline.

Pure functions over uiautomator XML. No device access here.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

BOUNDS_RE = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")

# Words whose controls are never tapped automatically (listed for review instead).
DANGER_WORDS = (
    "删除", "清空", "清除", "注销", "退出登录", "退出账号", "登出", "卸载", "支付", "付款", "购买",
    "充值", "开通", "订阅", "续费", "拨打", "呼叫", "举报", "投诉", "发送", "发布", "提交", "分享",
    "下载", "安装", "解绑", "移除", "重置", "恢复出厂", "取消订单", "取消关注", "取消收藏", "取消预约",
    "退订", "退款", "解约", "验证码", "一键登录", "加入购物车", "加购",
    "delete", "del", "trash", "erase", "wipe", "unbind",  # icon-only buttons are known by their rid: iv_del_city
    "remove", "clear", "logout", "log out", "sign out", "uninstall", "pay", "purchase",
    "buy", "subscribe", "unsubscribe", "call", "report", "send", "resend", "get code", "publish", "submit", "share",
    "download", "install", "reset", "refund", "cancel order", "add to cart", "add to bag",
)
# Promotion / ad entries: skipped by default (reason "ad"), can be allowed in the profile.
AD_WORDS = ("广告", "抽奖", "抽手机", "领红包", "红包", "立即领取", "领取", "看视频", "观看视频", "激励视频",
            "赚钱", "提现", "福利", "推广")
# Buttons that commit something: never used to dismiss dialogs or restore state. Includes answers that make a
# choice stick ("Always", "不再提示") or act right away ("Once"). English ones count only as the label's first words:
# "Save changes" is a button, "How to Save Money" is a title.
CONFIRM_WORDS = ("确定", "确认", "保存", "提交", "完成", "同意并", "好的", "总是", "始终", "仅此一次", "不再提示", "不再询问",
                 "ok", "confirm", "save", "submit", "yes", "done", "finish", "apply", "always", "once", "just once",
                 "don't ask again")
# Whole labels of a log-in / sign-up button. On a page with an input field it submits the form; elsewhere it only
# opens the form. A label that only contains the word ("会员登录", "微信登录") is another control.
LOGIN_LABELS = ("登录", "注册", "立即登录", "立即注册", "登录注册", "注册登录", "login", "log in", "sign in", "sign up",
                "register")
# Word lists judge button labels. Longer text is content (a title, a description), whatever words it contains.
ACTION_MAX_WORDS = 5
ACTION_MAX_CJK = 12
# Button bar of a system-style alert dialog: every answer except the cancel-like one commits the dialog's question.
DIALOG_BUTTON_RE = re.compile(r"^android:id/button[123]$")
# Buttons that dismiss without committing. Matched only as the WHOLE label: "取消订阅" is not a cancel button.
CANCEL_WORDS = ("取消", "关闭", "暂不", "暂不需要", "以后再说", "下次再说", "不了", "不用了", "否", "跳过", "我知道了",
                "知道了", "我再想想", "再想想", "算了", "cancel", "close", "not now", "later", "no", "no thanks",
                "skip", "dismiss")
SYSTEM_RIDS = ("statusBarBackground", "navigationBarBackground", "action_bar_container",
               "status_bar", "navigation_bar")
INPUT_CLASSES = ("EditText", "AutoCompleteTextView", "SearchView$SearchAutoComplete")
ADAPTER_CLASSES = ("ListView", "GridView", "RecyclerView", "ExpandableListView")
# Old-style AdapterViews handle item clicks at list level, so their children may not be marked clickable.
ADAPTERVIEW_CLASSES = ("ListView", "GridView", "ExpandableListView")
# Back-arrow controls: tapping them equals the BACK key. Matched strictly (exact rid/desc/label) and,
# for rid matches, only in the top-left corner, so "btn_back_up_data" or "tv_return_policy" are explored.
NAV_BACK_RID_RE = re.compile(r"^(iv|ib|img|image|btn|button|tv|toolbar|title|nav|top|action|head|header|left)?_?"
                             r"(back|go_back|goback|nav_back|navigate_up|arrow_back|back_arrow|back_btn|back_icon|"
                             r"left_back|return|fanhui)$", re.I)
NAV_BACK_LABELS = ("返回", "back", "navigate up", "向上导航", "转到上一层级")
HORIZONTAL_CLASSES = ("HorizontalScrollView",)


@dataclass(eq=False)
class Node:
    idx: int
    parent: int
    depth: int
    cls: str
    rid: str
    text: str
    desc: str
    package: str
    bounds: tuple
    clickable: bool
    long_clickable: bool
    checkable: bool
    checked: bool
    selected: bool
    enabled: bool
    scrollable: bool
    focused: bool
    children: list = field(default_factory=list)
    covered: bool = False   # inside a background layer hidden by a same-window overlay

    @property
    def short_rid(self) -> str:
        return self.rid.rsplit("/", 1)[-1] if self.rid else ""

    @property
    def short_cls(self) -> str:
        return self.cls.rsplit(".", 1)[-1]

    @property
    def center(self) -> tuple:
        x1, y1, x2, y2 = self.bounds
        return (x1 + x2) // 2, (y1 + y2) // 2

    @property
    def area(self) -> int:
        x1, y1, x2, y2 = self.bounds
        return max(0, x2 - x1) * max(0, y2 - y1)


def parse_bounds(value: str) -> tuple:
    m = BOUNDS_RE.search(value or "")
    return tuple(int(v) for v in m.groups()) if m else (0, 0, 0, 0)


def parse(xml: bytes | str) -> list[Node]:
    """Parse uiautomator XML into a flat, document-ordered node list."""
    if isinstance(xml, bytes):
        xml = xml.decode("utf-8", errors="replace")
    start = xml.find("<?xml")
    if start < 0:
        start = xml.find("<hierarchy")
    if start < 0:
        raise ValueError("no hierarchy in XML")
    end = xml.rfind("</hierarchy>")
    if end < 0:
        raise ValueError("truncated hierarchy XML")
    root = ET.fromstring(xml[start:end + len("</hierarchy>")])
    nodes: list[Node] = []

    def walk(el, parent: int, depth: int) -> None:
        for child in el:
            if child.tag != "node":
                continue
            a = child.attrib
            n = Node(idx=len(nodes), parent=parent, depth=depth, cls=a.get("class", ""),
                     rid=a.get("resource-id", ""), text=a.get("text", ""), desc=a.get("content-desc", ""),
                     package=a.get("package", ""), bounds=parse_bounds(a.get("bounds", "")),
                     clickable=a.get("clickable") == "true", long_clickable=a.get("long-clickable") == "true",
                     checkable=a.get("checkable") == "true", checked=a.get("checked") == "true",
                     selected=a.get("selected") == "true", enabled=a.get("enabled") == "true",
                     scrollable=a.get("scrollable") == "true", focused=a.get("focused") == "true")
            nodes.append(n)
            if parent >= 0:
                nodes[parent].children.append(n.idx)
            walk(child, n.idx, depth + 1)

    walk(root, -1, 0)
    if not nodes:
        raise ValueError("empty hierarchy")
    mark_layers(nodes)
    return nodes


def _subtree(nodes: list[Node], n: Node) -> list[int]:
    out, stack = [], [n.idx]
    while stack:
        i = stack.pop()
        out.append(i)
        stack.extend(nodes[i].children)
    return out


def _has_content(nodes: list[Node], n: Node) -> bool:
    return any(nodes[i].text.strip() or nodes[i].desc.strip() or nodes[i].clickable for i in _subtree(nodes, n))


def mark_layers(nodes: list[Node]) -> None:
    """Mark nodes hidden behind a same-window overlay as covered.

    Popups attached to the activity's content view (common in popup libraries)
    leave the background hierarchy in the dump. When a parent stacks two or more
    near-full-screen children that both carry content, only the last one is the
    foreground layer.
    """
    width, height = screen_size(nodes)
    full = 0.7 * width * height
    # Web page content is a DOM, not a window stack: full-size <div>s inside a WebView are not layers.
    web = {i for n in nodes if n.short_cls == "WebView" for i in _subtree(nodes, n)}
    for p in nodes:
        if len(p.children) < 2 or p.covered or p.idx in web:
            continue
        big = [nodes[c] for c in p.children if nodes[c].area >= full and _has_content(nodes, nodes[c])]
        for k in big[:-1]:
            for i in _subtree(nodes, k):
                nodes[i].covered = True


def layered(nodes: list[Node]) -> bool:
    return any(n.covered for n in nodes)


def app_nodes(nodes: list[Node], package: str) -> list[Node]:
    return [n for n in nodes if n.package == package]


def screen_size(nodes: list[Node]) -> tuple:
    tops = [n.bounds for n in nodes if n.parent < 0] or [nodes[0].bounds]
    return max(b[2] for b in tops), max(b[3] for b in tops)


def label_of(nodes: list[Node], n: Node) -> str:
    """Own text/desc, else the first descendant text."""
    if n.text.strip():
        return n.text.strip()
    if n.desc.strip():
        return n.desc.strip()
    stack = list(n.children)
    while stack:
        c = nodes[stack.pop(0)]
        if c.text.strip():
            return c.text.strip()
        if c.desc.strip():
            return c.desc.strip()
        stack[0:0] = c.children
    return ""


def ancestors(nodes: list[Node], n: Node):
    p = n.parent
    while p >= 0:
        yield nodes[p]
        p = nodes[p].parent


# ---------------------------------------------------------------- page identity

SPARSE_MIN_NODES = 20  # a real screen with at least this many visible target-package nodes ...
SPARSE_MAX_IDS = 5     # ... but fewer resource-ids than this (Jetpack Compose without testTag) has no id structure


def sparse_ids(nodes: list[Node], package: str) -> bool:
    """Too few resource-ids to identify the screen by them (a Compose screen; not a small dialog)."""
    app = [n for n in nodes if n.package == package and not n.covered]
    return len(app) >= SPARSE_MIN_NODES and sum(1 for n in app if n.rid) < SPARSE_MAX_IDS


def label_structure(nodes: list[Node], package: str) -> frozenset:
    """Fallback identity for screens without resource-ids: the labels outside repeated list cells.

    Repeated cells (3+ siblings of one class and size: cards, rows, bottom-bar items) carry data or appear
    on every tab, so they are left out; digits are normalised; selection state is not part of it.
    """
    app = [n for n in nodes if n.package == package and not n.covered]
    siblings: dict = {}
    for n in app:
        if n.parent >= 0:
            x1, y1, x2, y2 = n.bounds
            siblings.setdefault((n.parent, n.short_cls, x2 - x1, y2 - y1), []).append(n)
    cells = set()
    for group in siblings.values():
        if len(group) >= 3:
            for c in group:
                cells.update(_subtree(nodes, c))
    out = set()
    for n in app:
        if n.idx in cells:
            continue
        label = n.text.strip() or n.desc.strip()
        if label and len(label) <= 40:
            out.add("label:" + re.sub(r"\d+", "#", label))
    return frozenset(out)


def structure(nodes: list[Node], package: str) -> frozenset:
    """Page structure: set of class|rid for target-package nodes that carry a resource-id.

    Text, bounds and counts are excluded so data refresh and scrolling do not change it.
    A screen with almost no resource-ids (Compose) is identified by its labels instead (label_structure).
    """
    if sparse_ids(nodes, package):
        return label_structure(nodes, package)
    out = set()
    for n in nodes:
        if n.package != package or n.covered:
            continue
        if n.rid:
            out.add(f"{n.short_cls}|{n.short_rid}")
        elif (n.clickable or n.scrollable) and n.desc:
            out.add(f"{n.short_cls}|desc:{n.desc[:40]}")
    return frozenset(out)


def containment(observed: frozenset, known: frozenset) -> float:
    if not observed:
        return 1.0 if not known else 0.0
    return len(observed & known) / len(observed)


def jaccard(a: frozenset, b: frozenset) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def text_fingerprint(nodes: list[Node], package: str) -> frozenset:
    """Visible text content of the page (used to detect in-place view-state changes)."""
    return frozenset((n.short_rid, n.text.strip()) for n in nodes
                     if n.package == package and not n.covered and n.text.strip()
                     and not n.short_cls.endswith(INPUT_CLASSES))


def selection(nodes: list[Node], package: str) -> frozenset:
    return frozenset((n.short_rid, label_of(nodes, n)) for n in nodes
                     if n.package == package and (n.selected or n.checked))


def find_text(nodes: list[Node], package: str | None, words) -> list[Node]:
    """Nodes whose text/desc equals or contains one of the words (case-insensitive)."""
    out = []
    for n in nodes:
        if (package and n.package != package) or n.covered:
            continue
        hay = (n.text + " " + n.desc).strip().lower()
        if hay and any(w.lower() in hay for w in words):
            out.append(n)
    return out


# ---------------------------------------------------------------- selectors

def matches(n: Node, sel: dict, nodes: list[Node] | None = None) -> bool:
    if "rid" in sel and sel["rid"] not in (n.rid, n.short_rid):
        return False
    if "text" in sel and sel["text"] != n.text.strip() and not (
            nodes is not None and not n.text.strip() and sel["text"] == label_of(nodes, n)):
        return False
    if "text_contains" in sel and sel["text_contains"] not in (n.text + n.desc):
        return False
    if "desc" in sel and sel["desc"] != n.desc:
        return False
    if "class" in sel and sel["class"] not in (n.cls, n.short_cls):
        return False
    return True


def select(nodes: list[Node], sel: dict, package: str | None = None) -> list[Node]:
    hits = [n for n in nodes if (package is None or n.package == package) and not n.covered
            and matches(n, sel, nodes)]
    if "text" in sel:
        # A node that carries the text itself beats a container whose first child happens to carry it.
        # The label may be the node's text or its content-description (icon buttons, Compose).
        own = [n for n in hits if n.text.strip() == sel["text"] or n.desc.strip() == sel["text"]]
        if own:
            return own
    return hits


def read_readings(frames_nodes: list, readings: list, package: str, activity: str = "") -> dict:
    """Business readings visible in a capture (first frame that shows each), for meta.json of every unit."""
    out = {}
    for r in readings or ():
        if r.get("activity") and not activity.endswith(r["activity"]):
            continue
        for nodes in frames_nodes:
            hits = select(nodes, r["selector"], package)
            value = (hits[0].text.strip() or hits[0].desc.strip()) if hits else ""
            if value:
                out[r["name"]] = value
                break
    return out


def tap_point(nodes: list[Node], n: Node) -> tuple[int, int]:
    """Where to tap a control so that the control itself receives the tap.

    The centre of a clickable container can sit on a child list or button that swallows the tap
    (the 时辰宜忌 card: its centre is on the hour list). Then tap the first text of the container
    that is not inside such a child.
    """
    t = tap_target(nodes, n)
    sub = _subtree(nodes, t)
    # A RecyclerView takes touches even when the dump marks it neither clickable nor scrollable.
    inner = [nodes[i] for i in sub[1:] if nodes[i].clickable or nodes[i].scrollable
             or nodes[i].short_cls in ADAPTER_CLASSES or nodes[i].short_cls.endswith("ScrollView")]

    def intercepted(x: int, y: int) -> bool:
        return any(c.bounds[0] <= x < c.bounds[2] and c.bounds[1] <= y < c.bounds[3] for c in inner)
    cx, cy = t.center
    if not inner or not intercepted(cx, cy):
        return cx, cy
    for i in sub[1:]:
        m = nodes[i]
        if (m.text.strip() or m.desc.strip()) and not m.covered:
            x, y = m.center
            if t.bounds[0] <= x < t.bounds[2] and t.bounds[1] <= y < t.bounds[3] and not intercepted(x, y):
                return x, y
    return cx, cy


def tap_target(nodes: list[Node], n: Node) -> Node:
    """A text node inside a clickable container should be tapped through the container."""
    if n.clickable or n.checkable:
        return n
    for a in ancestors(nodes, n):
        if a.clickable:
            return a
    return n


# ---------------------------------------------------------------- candidates

@dataclass
class Candidate:
    key: str              # stable identity: rid|label|desc|class#occurrence
    label: str
    rid: str
    text: str
    desc: str
    cls: str
    bounds: tuple
    frame: int            # last viewport index where it was seen (processing order / locate direction)
    kind: str             # tap | check | item
    group: str            # list container key for item sampling ('' when not a list item)
    danger: str = ""      # matched danger word, if any
    denied: str = ""      # matched deny rule, if any
    first_frame: int = -1  # first viewport index where it was seen (= swipes from the top, scroll_index)
    nav_back: bool = False
    sib: str = ""         # parent + class of a control without resource-id (repeated siblings form a family)
    commit: str = ""      # commits without a commit word: 'dialog_answer' or 'form_submit'
    idx: int = -1         # node index in this screen's hierarchy (not persisted; locate() uses it)

    def as_dict(self) -> dict:
        x1, y1, x2, y2 = self.bounds
        return {"key": self.key, "label": self.label, "resource-id": self.rid, "text": self.text,
                "content-desc": self.desc, "class": self.cls,
                "bounds": "[%d,%d][%d,%d]" % self.bounds, "center": [(x1 + x2) // 2, (y1 + y2) // 2],
                "long-clickable": False,
                "scroll_index": self.first_frame if self.first_frame >= 0 else self.frame, "last_frame": self.frame,
                "kind": self.kind, "danger": self.danger, "denied": self.denied, "nav_back": self.nav_back,
                "sib": self.sib, "commit": self.commit}


def _norm(text: str) -> str:
    return re.sub(r"[\s\u3000.,，。!！?？:：、·…]+", "", (text or "").strip().lower())


def word_hit(words, *parts: str) -> str:
    """CJK words match as substrings; ASCII words must match whole tokens (rid 'display' is not 'pay').

    camelCase is split first, so a rid 'btnDelCity' has the token 'del' like 'iv_del_city' does."""
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


def danger_word(*parts: str, words=DANGER_WORDS) -> str:
    return word_hit(words, *parts)


def action_text(text: str) -> str:
    """The text if it is short enough to be a button label, else '' (a title or description is content)."""
    t = (text or "").strip()
    if len(re.findall(r"[一-鿿]", t)) > ACTION_MAX_CJK or len(re.findall(r"[A-Za-z]+", t)) > ACTION_MAX_WORDS:
        return ""
    return t


def is_cancel_label(label: str) -> bool:
    """Whole-label match only; a label that also carries a danger word is never a cancel button."""
    n = _norm(label)
    return bool(n) and n in {_norm(w) for w in CANCEL_WORDS} and not danger_word(label)


def _lead_hit(words, text: str) -> str:
    """CJK words anywhere in the text; ASCII words only at its start."""
    head = " " + " ".join(t for t in re.split(r"[^a-z0-9]+", text.lower()) if t) + " "
    for w in words:
        lw = w.lower()
        if re.search(r"[a-z]", lw):
            if head.startswith(" " + " ".join(t for t in re.split(r"[^a-z0-9]+", lw) if t) + " "):
                return w
        elif lw in text.lower():
            return w
    return ""


def is_confirm_label(label: str) -> bool:
    return bool(_lead_hit(CONFIRM_WORDS, action_text(label)))


def is_login_label(label: str) -> bool:
    return _norm(label).replace("/", "") in {_norm(w) for w in LOGIN_LABELS}


def is_dialog_answer(rid: str, label: str) -> bool:
    return bool(DIALOG_BUTTON_RE.match(rid or "")) and not is_cancel_label(label)


def is_nav_back(label: str, desc: str, rid: str, bounds: tuple, screen: tuple) -> bool:
    if _norm(desc) in {_norm(w) for w in NAV_BACK_LABELS} or _norm(label) in ("返回", "back"):
        return True
    short = rid.rsplit("/", 1)[-1]
    if short and NAV_BACK_RID_RE.match(short):
        x1, y1, x2, y2 = bounds
        return x2 <= screen[0] * 0.3 and y2 <= screen[1] * 0.15
    return False


def node_at(nodes: list[Node], x: int, y: int) -> Node | None:
    """Topmost visible node under a point (last in document order: later siblings and children draw on top)."""
    hit = None
    for n in nodes:
        if n.covered:
            continue
        x1, y1, x2, y2 = n.bounds
        if x1 <= x < x2 and y1 <= y < y2:
            hit = n
    return hit


def rule_hits(rule: dict, activity: str, c: Candidate) -> bool:
    if "activity" in rule and not activity.endswith(rule["activity"]):
        return False
    for f in ("rid", "text", "desc", "text_contains", "class"):
        if f not in rule:
            continue
        v = rule[f]
        if f == "rid" and v not in (c.rid, c.rid.rsplit("/", 1)[-1]):
            return False
        if f == "text" and v != c.label:
            return False
        if f == "desc" and v != c.desc:
            return False
        if f == "text_contains" and v not in (c.label + " " + c.desc):
            return False
        if f == "class" and v not in (c.cls, c.cls.rsplit(".", 1)[-1]):
            return False
    return any(f in rule for f in ("rid", "text", "desc", "text_contains", "class"))


def clipped_item(nodes: list[Node], n: Node) -> bool:
    """A list cell cut off by its list's edge: much shorter (or narrower) than its siblings and flush with that edge.

    A grid whose second row shows as short stubs at the bottom of one viewport would otherwise add a second set of
    unlabelled controls beside the labelled ones of the next viewport.
    """
    if n.parent < 0:
        return False
    p = nodes[n.parent]
    sibs = [nodes[c] for c in p.children if nodes[c].short_cls == n.short_cls and nodes[c].short_rid == n.short_rid]
    x1, y1, x2, y2 = n.bounds
    px1, py1, px2, py2 = p.bounds
    tall = max(s.bounds[3] - s.bounds[1] for s in sibs)
    wide = max(s.bounds[2] - s.bounds[0] for s in sibs)
    cut_v = (y2 - y1) < 0.6 * tall and (y2 >= py2 - 2 or y1 <= py1 + 2)
    cut_h = (x2 - x1) < 0.6 * wide and (x2 >= px2 - 2 or x1 <= px1 + 2)
    return cut_v or cut_h


def candidates(nodes: list[Node], package: str, frame: int = 0, *, activity: str = "",
               deny: list | None = None, allow: list | None = None, extra_danger=()) -> list[Candidate]:
    """Tappable controls of the target package visible in this frame, in document order."""
    width, height = screen_size(nodes)
    adapter_children, adapterview_children = set(), set()
    for n in nodes:
        if n.package == package and not n.covered and n.short_cls in ADAPTER_CLASSES:
            adapter_children.update(n.children)
            if n.short_cls in ADAPTERVIEW_CLASSES:
                adapterview_children.update(n.children)
    out: list[Candidate] = []
    seen: dict = {}
    words = tuple(DANGER_WORDS) + tuple(extra_danger)
    form = any(n.package == package and not n.covered and n.enabled and n.short_cls.endswith(INPUT_CLASSES)
               for n in nodes)
    for n in nodes:
        if n.package != package or not n.enabled or n.covered:
            continue
        is_item = n.idx in adapter_children
        if not (n.clickable or n.checkable or n.idx in adapterview_children):
            continue
        if any(s in n.rid for s in SYSTEM_RIDS) or n.short_cls.endswith(INPUT_CLASSES):
            continue
        x1, y1, x2, y2 = n.bounds
        if x2 - x1 < 8 or y2 - y1 < 8:
            continue
        cx, cy = n.center
        if not (0 <= cx < width and 0 <= cy < height):
            continue
        label = label_of(nodes, n)
        if not label and not n.rid and not n.desc:
            continue  # anonymous decoration
        if is_item and not label and clipped_item(nodes, n):
            continue  # a list cell cut off at the viewport edge: its text is outside, the next viewport shows it whole
        if not (n.text.strip() or n.desc.strip()) and n.clickable and any(
                nodes[i].clickable for i in _subtree(nodes, n)[1:]):
            continue  # container whose clickable children are the real targets
        group = ""
        if is_item:
            parent = nodes[n.parent]
            group = f"{parent.short_cls}|{parent.short_rid}|{parent.bounds[0]},{parent.bounds[2]}"
        base = f"{n.short_rid}|{label[:40]}|{n.desc[:40]}|{n.short_cls}"
        occurrence = seen.get(base, 0)
        seen[base] = occurrence + 1
        kind = "check" if n.checkable else ("item" if is_item else "tap")
        c = Candidate(key=f"{base}#{occurrence}", label=label, rid=n.rid, text=n.text, desc=n.desc,
                      cls=n.cls, bounds=n.bounds, frame=frame, kind=kind, group=group, first_frame=frame,
                      nav_back=is_nav_back(label, n.desc, n.rid, n.bounds, (width, height)))
        c.idx = n.idx
        if not n.rid and n.parent is not None and n.parent >= 0:
            p = nodes[n.parent]
            c.sib = f"{p.short_cls}|{p.short_rid}|{p.bounds[0]},{p.bounds[2]}|{n.short_cls}"
        c.danger = danger_word(action_text(label), n.desc, n.short_rid, words=words)
        ad = danger_word(action_text(label), n.desc, words=AD_WORDS)
        if is_dialog_answer(n.rid, label):
            c.commit = "dialog_answer"
        elif form and is_login_label(label):
            c.commit = "form_submit"
        if ad:
            c.denied = "ad:" + ad
        for rule in deny or ():
            if rule_hits(rule, activity, c):
                c.denied = rule.get("reason", "deny")
                break
        for rule in allow or ():
            if rule_hits(rule, activity, c):
                c.danger = ""
                c.denied = ""
                break
        out.append(c)
    return out


LOADING_RE = re.compile(r"加载中|正在加载|请稍候|请稍等|loading", re.I)


def loading(nodes: list[Node], package: str) -> str:
    """A visible loading indicator: a loading text, or a small square spinner (ProgressBar)."""
    width, height = screen_size(nodes)
    for n in nodes:
        if n.package != package or n.covered or n.area <= 0:
            continue
        if n.text and LOADING_RE.search(n.text):
            return n.text.strip()[:30]
        if n.short_cls == "ProgressBar":
            x1, y1, x2, y2 = n.bounds
            w, h = x2 - x1, y2 - y1
            if abs(w - h) <= 0.2 * max(w, h) and w < width * 0.3:
                return "spinner"
    return ""


def blank_webview(nodes: list[Node], package: str) -> str:
    """A page-sized WebView that has not rendered its document yet.

    A loaded WebView exposes the page text as descendant nodes; an empty one, one that shows only the document
    title on the WebView node itself, or an 'about:blank' title bar is a page still loading.
    """
    width, height = screen_size(nodes)
    if any(n.package == package and not n.covered and n.text.strip().lower() == "about:blank" for n in nodes):
        return "about:blank"
    webs = [n for n in nodes if n.package == package and not n.covered and n.short_cls == "WebView"
            and n.area >= 0.25 * width * height]
    if not webs:
        return ""
    outer = [n for n in webs if not any(a.short_cls == "WebView" for a in ancestors(nodes, n))]
    for w in outer:
        if any((nodes[i].text.strip() or nodes[i].desc.strip()) and nodes[i].short_cls != "WebView"
               for i in _subtree(nodes, w)):
            return ""
    return "empty_webview"


def locate_loose(nodes: list[Node], package: str, cand: "Candidate") -> Node | None:
    """Exact key first; else the single visible node with the same rid and class (labels that carry data,
    such as a date, change between visits)."""
    n = locate(nodes, package, cand)
    # Only labels that carry data (digits: dates, counts) or no label at all may fall back to the rid:
    # a fixed label that is gone means a different control, and tapping a namesake rid goes elsewhere.
    # A container labelled by its children's text (宜忌 of the selected day) shows data, not identity.
    derived = not (cand.text.strip() or cand.desc.strip())
    if n is not None or not cand.rid or (cand.label and not re.search(r"\d", cand.label) and not derived):
        return n
    rid = cand.rid.rsplit("/", 1)[-1]
    cls = cand.cls.rsplit(".", 1)[-1]
    hits = [x for x in nodes if x.package == package and not x.covered and x.enabled and x.area > 0
            and x.short_rid == rid and x.short_cls == cls]
    return hits[0] if len(hits) == 1 else None


def locate(nodes: list[Node], package: str, cand: Candidate) -> Node | None:
    """Find the on-screen node for a candidate key; None when absent or ambiguous.

    The key's occurrence is counted among the same tappable controls candidates() lists, never among containers:
    in Compose every container is a View labelled by its first labelled descendant, so the outermost full-screen
    View would take occurrence #0 of a button and the tap would land in the middle of the screen.
    """
    hit = next((c for c in candidates(nodes, package) if c.key == cand.key), None)
    if hit is None or hit.idx < 0:
        return None
    width, height = screen_size(nodes)
    n = nodes[hit.idx]
    cx, cy = n.center
    if not (0 <= cx < width and 0 <= cy < height) or n.area <= 0:
        return None
    return n


# ---------------------------------------------------------------- containers

def scroll_containers(nodes: list[Node], package: str) -> list[Node]:
    width, height = screen_size(nodes)
    out = []
    for n in nodes:
        if n.package != package or not n.scrollable or n.covered:
            continue
        x1, y1, x2, y2 = n.bounds
        if x2 - x1 <= 0 or y2 - y1 <= 0:
            continue
        out.append(n)
    return out


def container_axis(n: Node, screen: tuple) -> str:
    if n.short_cls in HORIZONTAL_CLASSES:
        return "horizontal"
    x1, y1, x2, y2 = n.bounds
    w, h = x2 - x1, y2 - y1
    if n.short_cls in ("ScrollView", "NestedScrollView", "ListView", "GridView", "ExpandableListView"):
        return "vertical"
    if h < screen[1] * 0.25 and w > 2 * h:
        return "horizontal"
    return "vertical"


def primary_container(nodes: list[Node], package: str) -> Node | None:
    """Largest vertical scrollable container covering at least a quarter of the screen height."""
    screen = screen_size(nodes)
    best = None
    for n in scroll_containers(nodes, package):
        if container_axis(n, screen) != "vertical":
            continue
        if n.bounds[3] - n.bounds[1] < screen[1] * 0.25:
            continue
        if best is None or n.area > best.area:
            best = n
    return best


def horizontal_strips(nodes: list[Node], package: str) -> list[Node]:
    """Horizontal content strips worth scrolling without a profile entry (an hourly forecast, a 48-hour AQI row).

    Only wide, fully visible, read-only strips with several texts: a strip with tappable items (date pickers,
    category tabs) is left alone, since scrolling it would hide the items the walker still has to tap.
    """
    width, height = screen_size(nodes)
    out = []
    for n in scroll_containers(nodes, package):
        if container_axis(n, (width, height)) != "horizontal":
            continue
        x1, y1, x2, y2 = n.bounds
        if x2 - x1 < 0.6 * width or x1 < 0 or y1 < 0 or x2 > width or y2 > height:
            continue
        sub = [nodes[i] for i in _subtree(nodes, n)[1:]]
        if any(s.clickable or s.checkable or s.long_clickable for s in sub):
            continue
        if sum(1 for s in sub if s.text.strip()) >= 3:
            out.append(n)
    return out


def container_key(n: Node) -> str:
    return f"{n.short_cls}|{n.short_rid}|{n.bounds[0]},{n.bounds[2]}"


def find_container(nodes: list[Node], package: str, key: str) -> Node | None:
    for n in scroll_containers(nodes, package):
        if container_key(n) == key:
            return n
    return None


def inside(n: Node, box: tuple) -> bool:
    x1, y1, x2, y2 = n.bounds
    return x1 >= box[0] - 2 and y1 >= box[1] - 2 and x2 <= box[2] + 2 and y2 <= box[3] + 2 and (x2 > x1) and (y2 > y1)


# ---------------------------------------------------------------- outline

def outline(nodes: list[Node], package: str, limit: int = 60) -> str:
    """Compact text outline for the model: clickable markers, text, rid, center."""
    lines = []
    for n in nodes:
        if n.package != package or n.covered:
            continue
        label = n.text.strip() or n.desc.strip()
        clickable = n.clickable or n.checkable
        if not label and not (clickable and n.rid):
            continue
        mark = "[c]" if clickable else ("[s]" if n.scrollable else "   ")
        flags = "".join(f for f, on in ((" sel", n.selected), (" chk", n.checked)) if on)
        cx, cy = n.center
        lines.append(f"{mark} {label[:30] or '-'} ({n.short_rid or n.short_cls}) @{cx},{cy}{flags}")
        if len(lines) >= limit:
            lines.append("…")
            break
    return "\n".join(lines)
