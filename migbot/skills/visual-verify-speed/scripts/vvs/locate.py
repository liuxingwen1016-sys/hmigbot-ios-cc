"""Find on HarmonyOS the control an Android step tapped: identify the same control, never "something like it".

Evidence from strong to weak; the first kind that yields a *unique* candidate wins, an ambiguous one taps nothing:
  identity    the Android resource-id kept as the ArkUI id; the same label (whitespace and digits ignored, one
              containing the other, or relabelled: similarity >= 0.6, a clear best, near the Android position,
              and not a text the Android screen shows on another control)
  beside      an unlabelled icon: the label beside it on the Android row
  position    an unlabelled or relabelled control at the same screen ratio, similar size, no other label
  context     last resort for an unlabelled control: the k-th of a repeated family, or the clickable whose
              container shares the most texts with the Android control's container (a clear winner)
List members (family_size >= 2) are data: their labels are not evidence, only "the same place in the same kind
of list" is (family_fallback, used by the walker after the search). A control the Android walk would not have
tapped -- a danger / confirm word the Android control's own description lacks -- is never tapped.
"""
from __future__ import annotations

import difflib
import math
from dataclasses import dataclass

from . import hui
from .android import Step

POS_MAX = 0.07        # screen-ratio distance accepted for position matches
POS_TIEBREAK = 0.25   # for text ties: give up when the nearest is farther than this
SIMILAR = 0.6         # label similarity accepted for relabelled controls


@dataclass
class Hit:
    node: hui.Node
    method: str
    distance: float | None
    label: str


def _ratio(nodes: list, n: hui.Node) -> tuple:
    w, h = hui.screen_size(nodes)
    cx, cy = n.center
    return cx / max(1, w), cy / max(1, h)


def _dist(a: tuple | None, b: tuple) -> float:
    if a is None:
        return 0.0
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _nearest(nodes: list, step: Step, cands: list) -> tuple:
    ranked = sorted(cands, key=lambda c: _dist(step.ratio, _ratio(nodes, c.node)))
    best = ranked[0]
    return best, _dist(step.ratio, _ratio(nodes, best.node))


def _guard(step: Step, label: str) -> str:
    """Refuse a HarmonyOS control the Android walk would not have tapped: it carries a danger / confirm word that
    the Android control's own description (label, id, the label beside an icon) does not."""
    a_label = " ".join(x for x in (step.label, step.text, step.desc, step.rid, step.near) if x)
    d = hui.danger_word(label)
    if d and not hui.danger_word(a_label):
        return "danger:" + d
    if hui.is_confirm_label(label) and not hui.is_confirm_label(a_label):
        return "confirm:" + label
    return ""


def _context(nodes: list, n: hui.Node) -> set:
    """Texts of the smallest container (>= 3 texts) around a HarmonyOS node, the node itself included."""
    for a in [n, *hui.ancestors(nodes, n)]:
        texts = {hui.norm_label(nodes[i].text or nodes[i].desc) for i in hui.subtree(nodes, a)}
        texts = {t for t in texts if t and not hui.DYNAMIC_TEXT.match(t)}
        if len(texts) >= 3:
            return texts
    return set()


def _pick(nodes: list, step: Step, cands: list) -> tuple:
    """Several controls carry the same label: the one whose surroundings match the Android control's, then the
    nearest to the Android position."""
    if len(cands) > 1 and step.context:
        ctx = set(step.context)
        scored = sorted(((len(_context(nodes, c.node) & ctx), c) for c in cands), key=lambda t: -t[0])
        if scored[0][0] > 0 and (len(scored) == 1 or scored[0][0] > scored[1][0]):
            best = scored[0][1]
            return best, _dist(step.ratio, _ratio(nodes, best.node)), True
    best, d = _nearest(nodes, step, cands)
    return best, d, False


def find(nodes: list, bundle: str, step: Step, position: bool = True) -> tuple[Hit | None, str]:
    """(hit, reason). reason explains a miss ('' on a hit). position=False: label rules only."""
    labelled = hui.labelled(nodes, bundle)
    want = hui.norm_label(step.label or step.text or step.desc)
    refused = ""
    if step.rid:  # the migrated control kept the Android resource-id as its ArkUI id: the same control
        rid = step.rid.lower()
        same = [n for n in nodes if n.bundle == bundle and not n.covered and n.ident.lower() == rid
                and hui.visible_on_screen(nodes, n)]
        if len(same) == 1:
            n = hui.tap_target(nodes, same[0])
            return Hit(n, "id", _dist(step.ratio, _ratio(nodes, n)) if step.ratio else None, hui.label_of(nodes, n)), ""
    if want:
        exact = [c for c in labelled if c.norm == want]
        if exact:
            best, d, by_ctx = _pick(nodes, step, exact)
            if len(exact) == 1 or by_ctx or d <= POS_TIEBREAK:
                why = _guard(step, best.label)
                if not why:
                    return Hit(best.node, "text", d if step.ratio else None, best.label), ""
                refused = why
        pat = hui.digit_pattern(want)
        if pat != want:
            same = [c for c in labelled if c.pattern == pat]
            if same:
                best, d, by_ctx = _pick(nodes, step, same)
                if len(same) == 1 or by_ctx or d <= POS_TIEBREAK:
                    why = _guard(step, best.label)
                    if not why:
                        return Hit(best.node, "pattern", d if step.ratio else None, best.label), ""
                    refused = refused or why
        if len(want) >= 2 and step.family_size < 2:  # a list member's label is data: 「经典-短袖」 is not 「短袖」
            part = [c for c in labelled if len(c.norm) >= 2 and (want in c.norm or c.norm in want)
                    and c.node.clickable]
            if len(part) == 1:
                why = _guard(step, part[0].label)
                if not why:
                    return Hit(part[0].node, "partial", None, part[0].label), ""
                refused = refused or why
        if len(want) >= 3 and step.family_size < 2:  # list contents are data: no guessing by similar wording
            sim = sorted(((difflib.SequenceMatcher(None, want, c.norm).ratio(), c) for c in labelled
                          if len(c.norm) >= 3 and c.node.clickable and c.norm not in step.peers),
                         key=lambda t: -t[0])
            if sim and sim[0][0] >= SIMILAR and (len(sim) == 1 or sim[0][0] - sim[1][0] >= 0.1):
                best = sim[0][1]
                d = _dist(step.ratio, _ratio(nodes, best.node))
                why = _guard(step, best.label)
                if d <= POS_TIEBREAK and not why:
                    return Hit(best.node, "similar", d if step.ratio else None, best.label), ""
                refused = refused or why
    if step.ratio is None or not position or (want and step.family_size >= 2):
        # a labelled list member is not found by position (an icon sits where a chip scrolled away):
        # the walker tries the same place of the same kind of list instead
        return None, refused or ("label_not_found" if want else "no_label_no_position")
    if not want:
        hit = _beside(nodes, bundle, step)
        if hit is not None:
            return hit, ""
    # Position: icon buttons (iv_pre), tab items whose label moved into an image, relabelled controls.
    best, bd = None, POS_MAX
    sr = step.size_ratio
    w, h = hui.screen_size(nodes)
    for n in hui.clickables(nodes, bundle):
        d = _dist(step.ratio, _ratio(nodes, n))
        if d > bd:
            continue
        if sr:
            x1, y1, x2, y2 = n.bounds
            hr = ((x2 - x1) / max(1, w), (y2 - y1) / max(1, h))
            a_area, h_area = max(1e-6, sr[0] * sr[1]), max(1e-6, hr[0] * hr[1])
            if not (0.2 <= h_area / a_area <= 5.0):
                continue
        label = hui.label_of(nodes, n)
        if want and label and hui.norm_label(label) != want and hui.digit_pattern(label) != hui.digit_pattern(want):
            continue  # a different labelled control sits there
        if _guard(step, label):
            continue
        best, bd = n, d
    if best is not None:
        return Hit(best, "position", bd, hui.label_of(nodes, best)), ""
    if not want:
        hit = _family(nodes, bundle, step) or _by_context(nodes, bundle, step)
        if hit is not None:
            return hit, ""
    return None, refused or ("label_not_found" if want else "position_not_found")


def family_fallback(nodes: list, bundle: str, step: Step, avoid: set) -> Hit | None:
    """A labelled list member whose label is not on the HarmonyOS list (random or different data): the member at
    the same place in the same kind of list, never one that another Android unit tapped (labels in avoid)."""
    if step.family_size < 2:
        return None
    hit = _family(nodes, bundle, step, avoid, strict=True)
    return Hit(hit.node, "family", None, hit.label) if hit else None


def _family(nodes: list, bundle: str, step: Step, avoid: set = frozenset(), strict: bool = False) -> Hit | None:
    """An unlabelled member of a repeated family (product cards, grid tiles): the k-th member of the HarmonyOS
    group of similar clickable siblings that is closest in size to the Android family."""
    if step.family_size < 2:
        return None
    groups: dict = {}
    w, h = hui.screen_size(nodes)
    sr = step.size_ratio
    for n in hui.clickables(nodes, bundle):
        if strict:
            lab = hui.norm_label(hui.label_of(nodes, n))
            if lab in avoid or lab in step.peers:
                continue  # a control another Android unit tapped, or one the Android screen also shows elsewhere
            x1, y1, x2, y2 = n.bounds
            if sr and not 1 / 3 <= ((x2 - x1) * (y2 - y1) / max(1, w * h)) / max(1e-6, sr[0] * sr[1]) <= 3:
                continue  # another kind of list (a bottom tab bar instead of category chips)
        x1, y1, x2, y2 = n.bounds  # same type and size; ForEach often wraps each item in its own parent
        groups.setdefault((n.type, round((x2 - x1) / 20), round((y2 - y1) / 20)), []).append(n)
    cands = [g for g in groups.values() if len(g) >= max(2, step.occurrence + 1)]
    if not cands:
        return None
    g = min(cands, key=lambda g: (abs(len(g) - step.family_size), _dist(step.ratio, _ratio(nodes, g[0]))))
    g = sorted(g, key=lambda n: (n.bounds[1] // 20, n.bounds[0]))
    n = g[min(step.occurrence, len(g) - 1)]
    if _guard(step, hui.label_of(nodes, n)):
        return None
    return Hit(n, "family", None, hui.label_of(nodes, n))


def _beside(nodes: list, bundle: str, step: Step) -> Hit | None:
    """An unlabelled icon whose Android row shows a label beside it (a radio or check icon next to 「支付宝」):
    the one HarmonyOS clickable carrying that label."""
    if not step.near:
        return None
    own = [n for n in hui.clickables(nodes, bundle) if hui.norm_label(hui.label_of(nodes, n)) == step.near]
    if len(own) == 1 and not _guard(step, hui.label_of(nodes, own[0])):
        return Hit(own[0], "beside", None, hui.label_of(nodes, own[0]))
    return None


def _by_context(nodes: list, bundle: str, step: Step) -> Hit | None:
    """An unlabelled single control (an avatar, an icon button): the clickable whose surrounding texts share the
    most with the Android control's surroundings (at least two shared texts, a clear winner). Controls without
    any label are tried first, label-carrying containers (a card whose texts are its children) second."""
    if not step.context:
        return None
    ctx = set(step.context)
    bare, boxes = [], []
    for n in hui.clickables(nodes, bundle):
        if n.text.strip() or n.desc.strip():
            continue  # the Android control has no label: a labelled HarmonyOS control is another control
        (boxes if hui.label_of(nodes, n) else bare).append(n)
    for tier in (bare, boxes):
        scored = []
        for n in tier:
            c = _context(nodes, n)
            common = len(c & ctx)
            if common >= 2:  # specificity: shared texts relative to the container's own texts
                scored.append((common / max(1, len(c)), common, n))
        scored.sort(key=lambda t: (-t[0], -t[1]))
        if not scored:
            continue
        if len(scored) > 1 and scored[1][0] >= 0.8 * scored[0][0]:
            return None
        n = scored[0][2]
        if _guard(step, hui.label_of(nodes, n)):
            return None
        return Hit(n, "context", None, hui.label_of(nodes, n))
    return None
