"""Model fallback: one command runs several device steps (macro), each step returns a one-line status.

Grammar (steps separated by ';' or newlines):
  outline                     print the current screen outline
  tap <spec> | long <spec>    spec = rid:<id> | desc:<text> | @x,y | <text> (exact, else contains); prefix '!' to
                              tap a control that contains a danger word (only with the user's authorization)
  back | wait <s> | text <s>  key BACK / sleep / type into the focused input
  swipe up|down|left|right [target]
                              swipe a container: target = rid:<id> | @x1,y1,x2,y2 (its bounds); without a target,
                              up/down use the main vertical container, left/right the widest horizontal one
  capture [label]             dump + scroll capture into manual_NNNN_<Activity>/ (shares numbering and index.json);
                              scrolls the main container, profile extra_containers and read-only horizontal strips,
                              and writes the same meta.json fields as automatic units (dpi, readings, drift, click_path)
  start                       force-stop and launch the app's launcher activity
"""
from __future__ import annotations

import json
import re
import time

from . import capture as cap
from . import ui
from . import registry
from .baseline import ensure_baseline
from .store import now_iso


def parse_steps(script: str) -> list:
    steps = []
    for raw in re.split(r"[;\n]", script):
        raw = raw.strip()
        if raw:
            verb, _, arg = raw.partition(" ")
            steps.append((verb.lower(), arg.strip()))
    return steps


def find(nodes: list, package: str, spec: str):
    if spec.startswith("@"):
        x, y = (int(v) for v in spec[1:].split(","))
        return None, (x, y)
    if spec.startswith("rid:"):
        hits = ui.select(nodes, {"rid": spec[4:]}, package)
    elif spec.startswith("desc:"):
        hits = ui.select(nodes, {"desc": spec[5:]}, package)
    else:
        hits = ui.select(nodes, {"text": spec}, package) or ui.select(nodes, {"text_contains": spec}, package)
    if not hits:
        return None, None
    n = ui.tap_target(nodes, hits[0])
    return n, n.center


def swipe_box(nodes: list, package: str, direction: str, target: str = ""):
    """Bounds to swipe for `swipe <direction> [target]`; None when an explicit target is not on screen."""
    if target.startswith("@"):
        x1, y1, x2, y2 = (int(v) for v in target[1:].split(","))
        return (x1, y1, x2, y2)
    if target.startswith("rid:"):
        rid = target[4:]
        hits = [n for n in ui.scroll_containers(nodes, package) if rid in (n.rid, n.short_rid)] or \
            ui.select(nodes, {"rid": rid}, package)
        return hits[0].bounds if hits else None
    if target:
        raise ValueError(f"swipe target must be rid:<id> or @x1,y1,x2,y2, got {target!r}")
    screen = ui.screen_size(nodes)
    if direction in ("left", "right"):
        strips = [n for n in ui.scroll_containers(nodes, package) if ui.container_axis(n, screen) == "horizontal"]
        if strips:
            return max(strips, key=lambda n: n.area).bounds
    return (ui.primary_container(nodes, package) or nodes[0]).bounds


class Driver:
    def __init__(self, dev, store, package: str, log=print, profile: dict | None = None):
        self.t_started = time.monotonic()
        self._accounted_elapsed = 0.0
        self._accounted_counters = {}
        self.dev, self.store, self.pkg, self.log = dev, store, package, log
        self.state = store.load_state() or {"page_counter": 0, "index": [], "status": "manual_only",
                                            "package": package, "pages": {}, "order": []}
        if profile is None:  # the profile a run saved next to its ledger, else the one the model wrote
            for saved in (store.aft / "profile.json", store.aft / "input" / "profile.json"):
                try:
                    profile = json.loads(saved.read_text(encoding="utf-8")) if saved.exists() else None
                except (OSError, ValueError):
                    profile = None
                if profile:
                    break
        self.profile = profile or {}
        self.obs = None
        ensure_baseline(self.dev, self.state, self.pkg)
        if profile:
            self.store.save_json("profile.json", self.profile)

    @property
    def trail(self) -> list:
        """Manual steps since the last `start`: the click_path of the next manual capture."""
        return self.state.setdefault("manual_trail", [])

    def step(self, element: str, center=None, node=None, **extra) -> None:
        o = self.obs
        self.trail.append({"from": (o.activity if o is not None else "") or "?", "element": element,
                           "center": list(center) if center else None,
                           "resource-id": node.rid if node is not None else "", "text": node.text if node is not None else "",
                           "content-desc": node.desc if node is not None else "", "long-clickable": False,
                           "scroll_info": None, **extra})

    def density(self):
        if not self.state.get("density"):
            self.state["density"] = self.dev.density()
        return self.state.get("density")

    def readings_and_drift(self, frames: list, activity: str):
        """Same guard rail as the walker: readings of this capture against the run's baselines."""
        readings = ui.read_readings([f.nodes for f in frames], self.profile.get("business_readings", []),
                                    self.pkg, activity)
        base = self.state.setdefault("baseline", {})
        drift = dict(self.state.get("drift") or {})
        for name, value in readings.items():
            b = base.get(name)
            if b is None:
                base[name] = {"value": value, "activity": activity, "page": None, "fixed": False}
            elif (not b.get("activity") or b["activity"] == activity) and value != b["value"]:
                drift[name] = {"expected": b["value"], "actual": value, "seen_at": "manual"}
                self.store.event("drift", {"reading": name, **drift[name]})
            elif (not b.get("activity") or b["activity"] == activity) and name in drift:
                drift.pop(name)  # restored by hand (e.g. the city picked back): the next run sees it too
                self.store.event("drift_cleared", {"reading": name, "seen_at": "manual"})
        self.state["drift"] = drift or None
        return readings, drift or None

    def look(self, purpose: str = "drive"):
        self.obs = self.dev.dump(purpose)
        return self.obs

    def status(self) -> str:
        o = self.obs
        if o is None:
            return "(no observation)"
        where = o.activity or o.focus.window or "?"
        layer = " +layer" if ui.layered(o.nodes) else (f" +{o.overlay}" if o.overlay else "")
        return f"{'in-app' if o.in_app else 'OUTSIDE ' + o.focus.package} {where}{layer}"

    def capture(self, label: str, target_id: str | None = None) -> str:
        obs = self.look("drive")
        if not obs.in_app:
            raise ValueError("capture is outside the target application")
        limits = self.profile.get("limits") or {}
        extra = [c for c in self.profile.get("extra_containers", [])
                 if not c.get("activity") or obs.activity.endswith(c["activity"])]
        scope = {"max_scrolls": int(limits.get("max_scrolls", 8)),
                 "max_hscrolls": int(limits.get("max_hscrolls", 12)),
                 "extra_containers": extra, "skipped_auto": []}
        png = self.dev.screencap("capture_first")
        if target_id is None:
            existing = registry.lookup_reuse(self.store, self.state, obs, png, package=self.pkg,
                                              scope=scope, density=self.density())
            if existing:
                saved = registry.record_reuse(self.store, self.state, existing, source="manual",
                                              label=label, path=list(self.trail))
                self.store.save_state(self.state)
                self.store.edge({"kind": "manual_capture", "page_id": saved["page_id"],
                                 "label": label, "result": "reused"})
                return f"reused {saved['page_id']} frames={len(saved['screenshots'])} (existing coverage)"
        res = cap.capture_page(self.dev, self.pkg, obs, int(limits.get("max_scrolls", 8)), extra,
                               on_event=self.store.event, auto_horizontal=int(limits.get("max_hscrolls", 12)),
                               first_png=png)
        self.obs = None if res.stop in cap.UNSAFE_CURSOR_STOPS else res.last_obs
        cands = [c.as_dict() for c in ui.candidates(obs.nodes, self.pkg)]
        density = self.density()
        readings, drift = self.readings_and_drift(res.frames, obs.activity)
        path = list(self.trail)
        meta = {"label": label or obs.activity, "timestamp": now_iso(), "device": "adb",
                "dpi": density, "density_factor": (density / 160) if density else None,
                "activity_info": {"current_focus": f"mCurrentFocus=Window{{ {obs.focus.window} }}",
                                  "resumed_activity": obs.focus.focused_app or obs.focus.window},
                "clickable_count": len(cands), "clickable_elements": cands,
                "scroll_container_bounds": res.container["bounds"] if res.container else None,
                "click_path": path,
                "came_from": path[-1]["from"] if path else None,
                "trigger_element": path[-1]["element"] if path else None,
                "aft": {"kind": "manual", "parent": None, "activity": obs.activity,
                        "layer": ("win:" + obs.overlay) if obs.overlay else ("layer" if ui.layered(obs.nodes) else ""),
                        "capture": {"frames": len(res.frames), "stop": res.stop, "proof_degraded": res.degraded,
                                    "container": res.container, "extra": res.extra,
                                    "proofs": [f.proof for f in res.frames[1:]],
                                    "observations": cap.frame_observations(res.frames),
                                    "last_observation": cap.observation_identity(res.last_obs),
                                    "interruption": res.interruption, "scope": res.scope},
                        "readings": readings, "drift": drift, "via": None}}
        saved = registry.save_capture(self.store, self.state, res.frames, meta, package=self.pkg,
                                      manual=True, target_id=target_id)
        page_id = saved["page_id"]
        if res.stop in cap.TRUNCATED_STOPS:
            gap = {"code": "capture_truncated", "page": page_id, "stop": res.stop,
                   "interruption": res.interruption}
            if res.last_obs is not None:
                gap["evidence"] = self.store.anomaly("capture_truncated_" + page_id, xml=res.last_obs.xml)
            self.state.setdefault("gaps", []).append(gap)
            self.store.event("gap", gap)
        self.store.save_state(self.state)
        self.store.edge({"kind": "manual_capture", "page_id": page_id, "label": label})
        action = saved.get("aft", {}).get("registry", {}).get("last_action", "created")
        return f"captured {page_id} frames={len(res.frames)} stop={res.stop} result={action}"

    def start_recipe(self, tries: int = 20) -> int:
        """`start` goes through the profile's start_recipe the way a run's cold start does (the agreement, a
        first-launch choice), so hand-driven commands do not repeat those taps. Stops when the profile's root is
        visible and the screen holds still (without a root selector: when it holds still with no rule left), so a
        slow splash screen does not end it early."""
        rules = self.profile.get("start_recipe") or []
        root = self.profile.get("root")
        applied, prev, last = 0, None, None
        for _ in range(tries if (rules or root) else 0):
            try:
                obs = self.look()
            except Exception:  # splash screens and app start can fail a dump: wait and look again
                self.dev.pause(1.0, "drive_start")
                continue
            rule = next((r for r in rules if ui.select(obs.nodes, r["when"], self.pkg if obs.in_app else None)), None)
            sig = (obs.activity, obs.structure(self.pkg))
            if rule is not None and not (rule is last and sig == prev):
                if "tap" in rule:
                    hits = ui.select(obs.nodes, rule["tap"])
                    want = rule["tap"].get("text")
                    if not hits and want:
                        loose = [n for n in obs.nodes if not n.covered and want in n.text.strip()]
                        hits = loose if len({n.text.strip() for n in loose}) == 1 else []
                    if hits:
                        x, y = ui.tap_point(obs.nodes, hits[0])
                        self.dev.tap(x, y, "drive_start")
                if rule.get("back"):
                    self.dev.back("drive_start")
                if rule.get("wait"):
                    self.dev.pause(float(rule["wait"]), "drive_start")
                self.store.edge({"kind": "manual", "action": "start_recipe", "rule": rule.get("note") or rule["when"]})
                applied, last, prev = applied + 1, rule, sig
                continue
            at_root = bool(ui.select(obs.nodes, root, self.pkg)) if root else True
            if sig == prev and at_root:
                break
            prev, last = sig, None
            self.dev.pause(1.0, "drive_start")
        return applied

    def run(self, script: str) -> str:
        """Steps run in order; the first step that fails stops the command, so a later `capture` never records
        the wrong screen under the name the model gave it (one command may chain a whole batch of states)."""
        out = []
        steps = parse_steps(script)
        for i, (verb, arg) in enumerate(steps):
            try:
                if verb == "outline":
                    self.look()
                    out.append(ui.outline(self.obs.nodes, self.pkg, 60))
                    continue
                if verb in ("tap", "long"):
                    force = arg.startswith("!")
                    spec = arg[1:] if force else arg
                    obs = self.obs or self.look()
                    node, xy = find(obs.nodes, self.pkg, spec)
                    if xy is None:
                        out.append(f"{verb} {arg}: NOT FOUND")
                        break
                    if node is None:  # coordinates: check whatever control is under the point
                        hit = ui.node_at(obs.nodes, xy[0], xy[1])
                        node = ui.tap_target(obs.nodes, hit) if hit is not None else None
                        if hit is not None and not force:
                            word = ui.danger_word(ui.action_text(ui.label_of(obs.nodes, hit)), hit.desc, hit.short_rid,
                                                  ui.action_text(ui.label_of(obs.nodes, node)), node.desc, node.short_rid)
                            if word:
                                out.append(f"{verb} {arg}: REFUSED (danger word '{word}' under the point; "
                                           "prefix ! only with user authorization)")
                                break
                    if node is not None and not force:
                        word = ui.danger_word(ui.action_text(ui.label_of(obs.nodes, node)), node.desc, node.short_rid)
                        if word:
                            out.append(f"{verb} {arg}: REFUSED (danger word '{word}'; prefix ! only with user authorization)")
                            break
                    (self.dev.long_press if verb == "long" else self.dev.tap)(xy[0], xy[1], "drive")
                    self.store.edge({"kind": "manual", "action": verb, "spec": arg, "xy": list(xy)})
                    label = ui.label_of(obs.nodes, node) if node is not None else ""
                    self.step(label or (node.short_rid if node is not None else "") or spec, xy, node,
                              **({"long-clickable": True} if verb == "long" else {}))
                elif verb == "back":
                    self.dev.back("drive")
                    self.store.edge({"kind": "manual", "action": "back"})
                    self.step("BACK")
                elif verb == "wait":
                    self.dev.sleep(float(arg or 1))
                elif verb == "text":
                    self.dev.input_text(arg, "drive")
                    self.store.edge({"kind": "manual", "action": "text", "length": len(arg)})
                    self.step(f"text({len(arg)})")
                elif verb == "swipe":
                    obs = self.obs or self.look()
                    direction, _, target = arg.partition(" ")
                    if direction not in ("up", "down", "left", "right"):
                        out.append(f"swipe {arg}: ERROR direction must be up/down/left/right")
                        break
                    box = swipe_box(obs.nodes, self.pkg, direction, target.strip())
                    if box is None:
                        out.append(f"swipe {arg}: NOT FOUND")
                        break
                    axis = "horizontal" if direction in ("left", "right") else "vertical"
                    forward = direction in ("up", "left")
                    (cap.swipe_forward if forward else cap.swipe_backward)(self.dev, box, axis, "drive")
                    self.store.edge({"kind": "manual", "action": "swipe", "spec": arg, "bounds": list(box)})
                    self.step(f"swipe {direction}", ((box[0] + box[2]) // 2, (box[1] + box[3]) // 2),
                              scroll_info={"direction": direction, "container_bounds": list(box)})
                elif verb == "capture":
                    out.append(self.capture(arg))
                    continue
                elif verb == "recapture":
                    target_id, _, label = arg.partition(" ")
                    if not target_id or target_id not in {r["page_id"] for r in self.state.get("index", [])}:
                        raise ValueError("recapture needs an existing PAGE_ID, followed by an optional label")
                    out.append(self.capture(label, target_id=target_id))
                    continue
                elif verb == "start":
                    comp = self.state.get("launcher") or self.dev.resolve_launcher()
                    self.dev.force_stop("drive")
                    self.dev.start(comp, "drive")
                    self.state["manual_trail"] = []
                    applied = self.start_recipe()
                    if applied:
                        out.append(f"start: applied start_recipe x{applied}")
                else:
                    out.append(f"unknown step: {verb}")
                    break
                self.look()
                out.append(f"{verb} {arg}".strip() + " -> " + self.status())
            except Exception as exc:  # report and stop; the model decides what to do next
                out.append(f"{verb} {arg}: ERROR {exc}")
                self.obs = None
                break
        else:
            i = None  # every step ran
        if i is not None:
            rest = "; ".join(f"{v} {a}".strip() for v, a in steps[i + 1:])
            out.append(f"STOPPED at step {i + 1} ({steps[i][0]}): the steps after it were not run"
                       + (f": {rest}" if rest else ""))
        if self.obs is not None:
            out.append("--- outline ---")
            out.append(ui.outline(self.obs.nodes, self.pkg, 40))
        # Manual and automatic device costs stay disjoint: resuming Walker must not
        # feed manual commands back into its per-exploration cost model.
        totals = self.state.setdefault("manual_device_counters", {})
        for group in ("ops", "time", "purpose", "purpose_time"):
            target = totals.setdefault(group, {})
            previous = self._accounted_counters.setdefault(group, {})
            for key, value in self.dev.counters.get(group, {}).items():
                target[key] = target.get(key, 0) + max(0, value - previous.get(key, 0))
                previous[key] = value
        elapsed = time.monotonic() - self.t_started
        self.state["manual_elapsed_s"] = round(self.state.get("manual_elapsed_s", 0.0)
                                              + elapsed - self._accounted_elapsed, 3)
        self._accounted_elapsed = elapsed
        self.store.save_state(self.state)  # the manual trail continues in the next drive command
        self.store.save_json("drive_counters.json", self.dev.counters)
        return "\n".join(out)
