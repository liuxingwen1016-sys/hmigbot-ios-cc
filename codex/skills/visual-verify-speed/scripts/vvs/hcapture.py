"""HarmonyOS page capture: first frame, then viewport-by-viewport scrolling of the main container.

Same rules as the Android walk: the window must stay the same page (page path, overlay), the container must
continue, a majority of anchor displacements proves movement, node-set change is only a degraded fallback.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from . import hui
from .hdevice import DeviceError, Obs

BUCKET = 8
MIN_MOVE = 8
TRUNCATED_STOPS = frozenset(("png_failed", "dump_failed", "input_failed", "screen_changed", "identity_unconfirmed"))


class CaptureError(RuntimeError):
    pass


@dataclass
class Frame:
    index: int
    raw: bytes
    png: bytes
    nodes: list
    container: str = ""
    proof: dict = field(default_factory=dict)
    obs: Obs | None = None
    axis: str = ""


@dataclass
class CaptureResult:
    frames: list
    container: dict | None
    stop: str
    degraded: bool
    extra: list = field(default_factory=list)
    last_obs: Obs | None = None
    interruption: dict | None = None


def _boundary(before: Obs, after: Obs, bundle: str) -> tuple | None:
    if not after.in_app or after.bundle != bundle:
        return "screen_changed", "left_app"
    if before.page_path and after.page_path and before.page_path != after.page_path:
        return "screen_changed", "page_changed"
    if before.overlay != after.overlay:
        return "screen_changed", "overlay_changed"
    return None


def _path(nodes: list, node) -> tuple:
    return tuple(n.type for n in reversed(list(hui.ancestors(nodes, node))))


def _live_container(before: Obs, after: Obs, bundle: str, original):
    key = hui.container_key(original)
    path = _path(before.nodes, original)
    hits = [n for n in hui.scroll_containers(after.nodes, bundle)
            if hui.container_key(n) == key and _path(after.nodes, n) == path]
    if len(hits) > 1:
        hits = [n for n in hits if n.bounds == original.bounds]
    if len(hits) != 1:
        return None, "container_missing_or_ambiguous"
    return hits[0], None


def continuity(before: Obs, after: Obs, bundle: str, container):
    b = _boundary(before, after, bundle)
    live, reason = (None, None) if b else _live_container(before, after, bundle, container)
    if b or reason:
        stop, reason = b or ("identity_unconfirmed", reason)
        return None, {"stop": stop, "reason": reason, "container": hui.container_key(container),
                      "from": before.identity(), "to": after.identity()}
    return live, None


def _anchor_map(nodes: list, bundle: str, box: tuple) -> dict:
    counts: Counter = Counter()
    found = {}
    for n in nodes:
        if n.bundle != bundle or n.covered or not hui.inside(n, box):
            continue
        label = n.text.strip() or n.desc.strip()
        if not label:
            continue
        key = (n.ident, label, n.type)
        counts[key] += 1
        found[key] = n.center
    return {k: v for k, v in found.items() if counts[k] == 1}


def _node_set(nodes: list, bundle: str, box: tuple) -> frozenset:
    return frozenset((n.type, n.ident, n.text, n.desc, n.bounds) for n in nodes
                     if n.bundle == bundle and not n.covered and hui.inside(n, box))


def _ids(nodes: list, bundle: str, box: tuple) -> set:
    return {(n.type, n.ident, n.text.strip(), n.desc.strip()) for n in nodes
            if n.bundle == bundle and not n.covered and hui.inside(n, box) and (n.text.strip() or n.desc.strip())}


def judge(prev: list, cur: list, bundle: str, box: tuple, axis: str = "vertical") -> dict:
    """Did the content move forward after a swipe toward the end of the container?"""
    a, b = _anchor_map(prev, bundle, box), _anchor_map(cur, bundle, box)
    common = [k for k in a if k in b]
    i = 1 if axis == "vertical" else 0
    deltas = [b[k][i] - a[k][i] for k in common]
    buckets = Counter(round(d / BUCKET) for d in deltas)
    changed = _node_set(prev, bundle, box) != _node_set(cur, bundle, box)
    result = {"anchors": len(deltas), "changed": changed}
    if deltas:
        top, votes = buckets.most_common(1)[0]
        members = [d for d in deltas if round(d / BUCKET) == top]
        delta = round(sum(members) / len(members))
        result.update(agree=votes, disagree=len(deltas) - votes, delta=delta)
        replaced = len(common) * 2 < len(a)
        if votes * 2 > len(deltas) and not (abs(delta) < MIN_MOVE and replaced):
            if abs(delta) < MIN_MOVE:
                result.update(progress=False, method="majority", reason="no_move")
            elif delta > 0:
                result.update(progress=False, method="majority", reason="wrong_direction")
            else:
                result.update(progress=True, method="majority")
            return result
    result.update(progress=changed, method="node_set", degraded=True, reason="changed" if changed else "unchanged")
    return result


def swipe_forward(dev, box: tuple, axis: str, purpose: str = "capture_scroll") -> None:
    x1, y1, x2, y2 = box
    if axis == "vertical":
        cx, hgt = (x1 + x2) // 2, y2 - y1
        dev.swipe(cx, y1 + int(hgt * 0.75), cx, y1 + int(hgt * 0.30), purpose)
    else:
        cy, wid = (y1 + y2) // 2, x2 - x1
        dev.swipe(x1 + int(wid * 0.80), cy, x1 + int(wid * 0.20), cy, purpose)


def swipe_backward(dev, box: tuple, axis: str, purpose: str = "rewind") -> None:
    x1, y1, x2, y2 = box
    if axis == "vertical":
        cx, hgt = (x1 + x2) // 2, y2 - y1
        dev.swipe(cx, y1 + int(hgt * 0.25), cx, y1 + int(hgt * 0.85), purpose, velocity=4000)
    else:
        cy, wid = (y1 + y2) // 2, x2 - x1
        dev.swipe(x1 + int(wid * 0.20), cy, x1 + int(wid * 0.80), cy, purpose, velocity=4000)


def scroll_run(dev, bundle: str, start: Obs, container, axis: str, max_swipes: int, first_index: int,
               on_event=None) -> tuple:
    on_event = on_event or (lambda k, d: None)
    key = hui.container_key(container)
    box = container.bounds
    frames, prev, degraded, stop = [], start, False, "max_scrolls"
    last, interruption = start, None
    seen = _ids(start.nodes, bundle, box)
    for step in range(max_swipes):
        try:
            swipe_forward(dev, box, axis)
        except DeviceError as exc:
            on_event("capture_input_failed", {"container": key, "step": step + 1, "error": str(exc)[:200]})
            stop, last = "input_failed", None
            break
        try:
            obs = dev.dump("capture_scroll")
        except Exception as exc:
            on_event("capture_dump_failed", {"container": key, "step": step + 1, "error": str(exc)[:200]})
            stop, last = "dump_failed", None
            break
        last = obs
        live, interruption = continuity(prev, obs, bundle, container)
        if interruption:
            stop = interruption["stop"]
            interruption["step"] = step + 1
            on_event("scroll_stop", interruption)
            break
        box = live.bounds
        verdict = judge(prev.nodes, obs.nodes, bundle, box, axis)
        degraded = degraded or bool(verdict.get("degraded"))
        if not verdict["progress"]:
            stop = "bottom" if verdict.get("reason") in ("no_move", "unchanged") else verdict.get("reason", "bottom")
            break
        size = (box[3] - box[1]) if axis == "vertical" else (box[2] - box[0])
        new = _ids(obs.nodes, bundle, box) - seen
        if not new and verdict.get("method") == "majority" and abs(verdict.get("delta", 0)) < 0.15 * max(size, 1):
            stop = "no_new_content"
            break
        seen |= new
        try:
            png = dev.screencap("capture_scroll")
        except DeviceError as exc:
            on_event("capture_png_failed", {"container": key, "step": step + 1, "error": str(exc)[:200]})
            stop = "png_failed"
            break
        frames.append(Frame(first_index + len(frames), obs.raw, png, obs.nodes, key, verdict, obs, axis))
        prev, container = obs, live
        if verdict.get("method") == "majority" and abs(verdict.get("delta", 0)) < 0.05 * max(size, 1):
            stop = "small_move"
            break
    return frames, stop, degraded, last, interruption


def rewind(dev, bundle: str, obs: Obs, max_swipes: int = 6) -> Obs:
    """Scroll the main container back to its top (view states are captured from the top, as on Android)."""
    c = hui.primary_container(obs.nodes, bundle)
    if c is None:
        return obs
    prev = obs
    for _ in range(max_swipes):
        swipe_backward(dev, c.bounds, "vertical")
        try:
            cur = dev.dump("rewind")
        except Exception:
            return prev
        live, issue = continuity(prev, cur, bundle, c)
        if issue:
            return cur
        v = judge(prev.nodes, cur.nodes, bundle, live.bounds, "vertical")
        if v.get("method") == "majority" and v.get("reason") in ("no_move", "wrong_direction") or (
                v.get("method") == "node_set" and not v.get("changed")):
            return cur
        prev, c = cur, live
    return prev


def capture(dev, bundle: str, obs0: Obs, max_swipes: int, hstrips: int = 0, on_event=None,
            first_png: bytes | None = None) -> CaptureResult:
    """First frame (reusing obs0) + main container frames (+ read-only horizontal strips when hstrips > 0)."""
    try:
        png0 = first_png if first_png is not None else dev.screencap("capture_first")
    except DeviceError as exc:
        raise CaptureError(str(exc)) from exc
    frames = [Frame(0, obs0.raw, png0, obs0.nodes, obs=obs0)]
    primary = hui.primary_container(obs0.nodes, bundle) if max_swipes > 0 else None
    if primary is None:
        result = CaptureResult(frames, None, "no_container", False, last_obs=obs0)
    else:
        more, stop, degraded, last, issue = scroll_run(dev, bundle, obs0, primary, "vertical", max_swipes, 1,
                                                       on_event)
        frames.extend(more)
        result = CaptureResult(frames, {"key": hui.container_key(primary), "bounds": list(primary.bounds),
                                        "axis": "vertical", "type": primary.type}, stop, degraded,
                               last_obs=last, interruption=issue)
    if result.stop in TRUNCATED_STOPS or hstrips <= 0 or result.last_obs is None:
        return result
    for key in [hui.container_key(n) for n in hui.horizontal_strips(result.last_obs.nodes, bundle)]:
        node = hui.find_container(result.last_obs.nodes, bundle, key)
        if node is None:
            continue
        first = len(result.frames)
        more, stop, degraded, last, issue = scroll_run(dev, bundle, result.last_obs, node, "horizontal", hstrips,
                                                       first, on_event)
        result.frames.extend(more)
        result.degraded = result.degraded or degraded
        result.last_obs = last
        result.extra.append({"auto": key, "axis": "horizontal", "frames": len(more), "stop": stop})
        if stop in TRUNCATED_STOPS or last is None:
            result.stop, result.interruption = stop, issue
            break
    return result
