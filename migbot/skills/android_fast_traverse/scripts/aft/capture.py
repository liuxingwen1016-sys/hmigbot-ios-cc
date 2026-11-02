"""Page capture: first frame plus viewport-by-viewport scrolling of the main container.

Window and container continuity are checked before progress. Within that
boundary a majority vote of anchor displacements proves movement; node-set
change is only a degraded fallback, never evidence of page identity.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from . import ui
from .device import DeviceError, Obs

BUCKET = 8          # px tolerance when grouping displacements
MIN_MOVE = 8        # px below which content did not move
TRUNCATED_STOPS = frozenset(("png_failed", "dump_failed", "input_failed", "screen_changed", "identity_unconfirmed"))
UNSAFE_CURSOR_STOPS = TRUNCATED_STOPS - {"png_failed"}


class CaptureError(RuntimeError):
    """The first frame could not be captured: nothing is recorded for this state."""


@dataclass
class Frame:
    index: int
    xml: bytes
    png: bytes
    nodes: list
    container: str = ""     # container key ('' for the first frame)
    proof: dict = field(default_factory=dict)
    obs: Obs | None = None  # the actual observation, never combined with another frame's focus


@dataclass
class CaptureResult:
    frames: list
    container: dict | None
    stop: str               # normal stop or one of TRUNCATED_STOPS
    degraded: bool
    extra: list = field(default_factory=list)   # extra container runs
    auto_from: int | None = None                # index of the first frame of an auto-discovered strip (None: none)
    auto_keys: list = field(default_factory=list)  # container keys of the strips scrolled automatically
    last_obs: Obs | None = None  # final device observation, even when not saved as a page frame
    interruption: dict | None = None
    scope: dict = field(default_factory=dict)

    @property
    def page_frames(self) -> list:
        """Frames of the page's own viewports (first + main container + profile extras), without auto strips."""
        return self.frames if self.auto_from is None else self.frames[:self.auto_from]


def observation_identity(obs: Obs | None) -> dict | None:
    """Compact provenance for metadata; no synthetic identity and no copied node lists."""
    if obs is None:
        return None
    return {"seq": obs.seq, "package": obs.package, "activity": obs.activity,
            "focus_kind": obs.focus.kind, "focus_package": obs.focus.package,
            "focus_activity": obs.focus.activity, "window": obs.focus.window, "token": obs.focus.token,
            "overlay": obs.overlay, "layered": ui.layered(obs.nodes), "in_app": obs.in_app}


def frame_observations(frames: list) -> list:
    return [{"index": f.index, "observation": observation_identity(f.obs)} for f in frames]


def _window_boundary(before: Obs, after: Obs, package: str) -> tuple[str, str] | None:
    """Use already captured focus, not another ADB query. Unknown is not 'same'."""
    if not after.in_app or after.package != package:
        return "screen_changed", "left_target_package"
    if (not before.in_app or not before.activity or not after.activity
            or before.focus.kind in ("none", "other", "anr", "ime")
            or after.focus.kind in ("none", "other", "anr", "ime")
            or not before.focus.window or not after.focus.window):
        return "identity_unconfirmed", "focus_unavailable"
    if before.activity and after.activity and before.activity != after.activity:
        return "screen_changed", "activity_changed"
    for name in ("package", "activity", "kind", "window", "token"):
        old, new = getattr(before.focus, name), getattr(after.focus, name)
        if old and new and old != new:
            return "screen_changed", "focus_" + name + "_changed"
    if before.overlay != after.overlay or ui.layered(before.nodes) != ui.layered(after.nodes):
        return "screen_changed", "overlay_changed"
    return None


def _container_path(nodes: list, node) -> tuple:
    return tuple((n.cls, n.rid) for n in reversed(list(ui.ancestors(nodes, node))))


def _shell_structure(nodes: list, package: str, container) -> frozenset:
    """Structure outside the scrolled subtree, excluding shared Android chrome."""
    descendants = set(ui._subtree(nodes, container))
    common = set(ui.SYSTEM_RIDS) | {"content", "action_bar_root"}
    return frozenset((n.cls, n.rid) for n in nodes if n.idx not in descendants and n.package == package
                     and not n.covered and n.rid and n.short_rid not in common)


def _live_container(before: Obs, after: Obs, package: str, original):
    """Return the unique continuing container, or an explicit identity gap."""
    key = ui.container_key(original)
    path = _container_path(before.nodes, original)
    hits = [n for n in ui.scroll_containers(after.nodes, package)
            if ui.container_key(n) == key and _container_path(after.nodes, n) == path]
    if len(hits) > 1:
        hits = [n for n in hits if n.bounds == original.bounds]
    if len(hits) != 1:
        return None, "container_missing_or_ambiguous"
    live = hits[0]
    old, new = _shell_structure(before.nodes, package, original), _shell_structure(after.nodes, package, live)
    if (old or new) and ui.jaccard(old, new) < 0.5:
        return None, "page_shell_changed"
    return live, None


def scroll_continuity(before: Obs, after: Obs, package: str, container):
    """Shared boundary for capture, rewind and locating; uses only existing observations."""
    boundary = _window_boundary(before, after, package)
    live, reason = (None, None) if boundary else _live_container(before, after, package, container)
    if boundary or reason:
        stop, reason = boundary or ("identity_unconfirmed", reason)
        return None, {"stop": stop, "reason": reason, "container": ui.container_key(container),
                      "from": observation_identity(before), "to": observation_identity(after)}
    return live, None


def _anchor_map(nodes: list, package: str, box: tuple) -> dict:
    counts: Counter = Counter()
    found = {}
    for n in nodes:
        if n.package != package or not ui.inside(n, box):
            continue
        label = n.text.strip() or n.desc.strip()
        if not label:
            continue
        key = (n.short_rid, label, n.short_cls)
        counts[key] += 1
        found[key] = n.center
    return {k: v for k, v in found.items() if counts[k] == 1}


def _node_set(nodes: list, package: str, box: tuple) -> frozenset:
    return frozenset((n.short_cls, n.short_rid, n.text, n.desc, n.bounds) for n in nodes
                     if n.package == package and ui.inside(n, box))


def _ids(nodes: list, package: str, box: tuple) -> set:
    """Node identities inside a container, without positions: what content a viewport shows."""
    return {(n.short_cls, n.short_rid, n.text.strip(), n.desc.strip()) for n in nodes
            if n.package == package and not n.covered and ui.inside(n, box) and (n.text.strip() or n.desc.strip())}


def judge(prev: list, cur: list, package: str, box: tuple, axis: str = "vertical") -> dict:
    """Did the content move forward after a swipe toward the end of the container?"""
    a, b = _anchor_map(prev, package, box), _anchor_map(cur, package, box)
    common = [k for k in a if k in b]
    i = 1 if axis == "vertical" else 0
    deltas = [b[k][i] - a[k][i] for k in common]
    buckets = Counter(round(d / BUCKET) for d in deltas)
    changed = _node_set(prev, package, box) != _node_set(cur, package, box)
    result = {"anchors": len(deltas), "changed": changed}
    if deltas:
        top, votes = buckets.most_common(1)[0]
        members = [d for d in deltas if round(d / BUCKET) == top]
        delta = round(sum(members) / len(members))
        result.update(agree=votes, disagree=len(deltas) - votes, delta=delta)
        # Staying put proves the end only when most of the screen stayed. When most anchors were replaced and only
        # fixed elements over the list (a top bar, a floating icon) are on both frames, the content moved under
        # them (a fling past the whole viewport), so it is not the end.
        replaced = len(common) * 2 < len(a)
        if votes * 2 > len(deltas) and not (abs(delta) < MIN_MOVE and replaced):
            if abs(delta) < MIN_MOVE:
                result.update(progress=False, method="majority", reason="no_move")
            elif delta > 0:
                result.update(progress=False, method="majority", reason="wrong_direction")
            else:
                result.update(progress=True, method="majority")
            return result
    # No majority (or no anchors): fall back to node-set change, flag the weaker proof.
    result.update(progress=changed, method="node_set", degraded=True,
                  reason="changed" if changed else "unchanged")
    return result


def swipe_forward(dev, node_bounds: tuple, axis: str, purpose: str = "capture_scroll") -> None:
    x1, y1, x2, y2 = node_bounds
    if axis == "vertical":
        cx = (x1 + x2) // 2
        h = y2 - y1
        dev.swipe(cx, y1 + int(h * 0.75), cx, y1 + int(h * 0.30), 300, purpose)
    else:
        cy = (y1 + y2) // 2
        w = x2 - x1
        dev.swipe(x1 + int(w * 0.80), cy, x1 + int(w * 0.20), cy, 300, purpose)


def swipe_backward(dev, node_bounds: tuple, axis: str, purpose: str = "locate_scroll") -> None:
    x1, y1, x2, y2 = node_bounds
    if axis == "vertical":
        cx = (x1 + x2) // 2
        h = y2 - y1
        dev.swipe(cx, y1 + int(h * 0.30), cx, y1 + int(h * 0.75), 300, purpose)
    else:
        cy = (y1 + y2) // 2
        w = x2 - x1
        dev.swipe(x1 + int(w * 0.20), cy, x1 + int(w * 0.80), cy, 300, purpose)


def scroll_run(dev, package: str, start_obs: Obs, container, axis: str, max_swipes: int,
               first_index: int, on_event=None) -> tuple:
    """Return (frames, stop, degraded, actual_last_obs, interruption)."""
    on_event = on_event or (lambda k, d: None)
    key = ui.container_key(container)
    box = container.bounds
    frames, prev, degraded, stop = [], start_obs, False, "max_scrolls"
    last_obs, interruption = start_obs, None
    seen_ids = _ids(start_obs.nodes, package, box)
    for step in range(max_swipes):
        try:
            swipe_forward(dev, box, axis)
        except DeviceError as exc:
            on_event("capture_input_failed", {"container": key, "step": step + 1, "error": str(exc)[:200]})
            stop, last_obs = "input_failed", None
            break
        try:
            obs = dev.dump("capture_scroll")
        except Exception as exc:  # local failure: keep what we have
            on_event("capture_dump_failed", {"container": key, "step": step + 1, "error": str(exc)[:200]})
            stop, last_obs = "dump_failed", None
            break
        last_obs = obs
        live, interruption = scroll_continuity(prev, obs, package, container)
        if interruption:
            stop = interruption["stop"]
            interruption["step"] = step + 1
            on_event("scroll_stop", interruption)
            break
        box = live.bounds
        verdict = judge(prev.nodes, obs.nodes, package, box, axis)
        degraded = degraded or bool(verdict.get("degraded"))
        if not verdict["progress"]:
            stop = "bottom" if verdict.get("reason") in ("no_move", "unchanged") else verdict.get("reason", "bottom")
            on_event("scroll_stop", {"container": key, "step": step + 1, "verdict": verdict})
            break
        size = (box[3] - box[1]) if axis == "vertical" else (box[2] - box[0])
        new_ids = _ids(obs.nodes, package, box) - seen_ids
        if (not new_ids and verdict.get("method") == "majority"
                and abs(verdict.get("delta", 0)) < 0.15 * max(size, 1)):
            # A small shift that reveals nothing new: not worth a frame, and it means we are at the end.
            on_event("scroll_stop", {"container": key, "step": step + 1, "verdict": verdict, "reason": "no_new_content"})
            stop = "no_new_content"
            break
        seen_ids |= new_ids
        try:
            png = dev.screencap("capture_scroll")
        except DeviceError as exc:  # keep the frames we have; the gap is reported by the caller
            on_event("capture_png_failed", {"container": key, "step": step + 1, "error": str(exc)[:200]})
            stop = "png_failed"
            break
        frames.append(Frame(first_index + len(frames), obs.xml, png, obs.nodes, key, verdict, obs))
        prev, container = obs, live
        size = (box[3] - box[1]) if axis == "vertical" else (box[2] - box[0])
        if verdict.get("method") == "majority" and abs(verdict.get("delta", 0)) < 0.05 * max(size, 1):
            stop = "small_move"
            break
    return frames, stop, degraded, last_obs, interruption


def capture_page(dev, package: str, obs0, max_swipes: int = 8, extra_containers=(), on_event=None,
                 auto_horizontal: int = 0, skip_auto=(), first_png: bytes | None = None) -> CaptureResult:
    """Capture first frame (reusing obs0 XML) and scroll the primary vertical container.

    auto_horizontal > 0 also scrolls read-only horizontal strips visible where the capture ends (at most that
    many swipes each), unless the profile declares them or their key is in skip_auto (already captured).
    """
    try:
        png0 = first_png if first_png is not None else dev.screencap("capture_first")
    except DeviceError as exc:
        raise CaptureError(str(exc)) from exc
    frames = [Frame(0, obs0.xml, png0, obs0.nodes, obs=obs0)]
    primary = ui.primary_container(obs0.nodes, package) if max_swipes > 0 else None
    if primary is None:
        result = CaptureResult(frames, None, "no_container", False, last_obs=obs0)
    else:
        more, stop, degraded, last_obs, issue = scroll_run(dev, package, obs0, primary, "vertical",
                                                         max_swipes, 1, on_event)
        frames.extend(more)
        result = CaptureResult(frames, {"key": ui.container_key(primary), "bounds": list(primary.bounds),
                                        "axis": "vertical", "class": primary.cls, "resource-id": primary.rid},
                               stop, degraded, last_obs=last_obs, interruption=issue)
    result.scope = {"max_scrolls": max_swipes, "max_hscrolls": auto_horizontal,
                    "extra_containers": list(extra_containers), "skipped_auto": sorted(skip_auto)}
    if result.stop in TRUNCATED_STOPS:
        return result  # no following containers on another or unconfirmed screen

    def append_run(node, axis, limit, detail, auto=False):
        first = len(result.frames)
        more, stop, degraded, last_obs, issue = scroll_run(dev, package, result.last_obs, node, axis,
                                                         limit, first, on_event)
        if auto and more and result.auto_from is None:
            result.auto_from = first
        result.frames.extend(more)
        result.degraded = result.degraded or degraded
        result.last_obs = last_obs
        result.extra.append({**detail, "axis": axis, "frames": len(more), "stop": stop})
        if stop in TRUNCATED_STOPS:
            result.stop, result.interruption = stop, issue
            return False
        if auto:
            result.auto_keys.append(ui.container_key(node))
        return True
    # Profile-declared extra containers (e.g. a horizontal forecast strip), when visible now.
    declared = set()
    for spec in extra_containers:
        hits = [n for n in ui.scroll_containers(result.last_obs.nodes, package)
                if ui.matches(n, spec.get("selector", {}))]
        if not hits:
            result.extra.append({"selector": spec.get("selector"), "status": "not_visible"})
            continue
        node = hits[0]
        declared.add(ui.container_key(node))
        axis = spec.get("axis") or ui.container_axis(node, ui.screen_size(result.last_obs.nodes))
        if not append_run(node, axis, int(spec.get("max_swipes", 6)), {"selector": spec.get("selector")}):
            return result
    if auto_horizontal > 0:
        # Read-only horizontal strips the profile did not declare (an hourly forecast, a 48-hour AQI row).
        keys = [ui.container_key(n) for n in ui.horizontal_strips(result.last_obs.nodes, package)]
        for key in keys:
            if key in declared or key in skip_auto:
                continue
            # Resolve against the actual latest observation, not a node from an earlier strip.
            node = ui.find_container(result.last_obs.nodes, package, key)
            if node is None:
                continue
            if not append_run(node, "horizontal", auto_horizontal,
                              {"auto": key, "bounds": list(node.bounds)}, auto=True):
                return result
    return result
