"""HarmonyOS walk along the Android tree.

For every Android unit in depth-first order: be on its parent (fast path: already there; then BACK; then cold
start + replay of the recorded Android steps), find the control the Android walk tapped, tap it, confirm the
screen changed, capture it under the Android unit's number. The model is asked only about popups that are not
the expected result of the tap. Failures stay local: a missing control or a dead tap becomes a gap (and a
ticket later), its subtree is marked blocked, the walk goes on. Three consecutive unrecovered failures stop it.
"""
from __future__ import annotations

import re
import time
import traceback
from collections import Counter

from . import VERSION, hcapture, hui, locate
from .android import Plan, Step, Unit
from .hdevice import DeviceError, DumpError, Obs
from .popup import PopupBridge, PopupStop
from .popup import signature as popup_signature
from .store import Store, now_iso

DONE = ("done",)
FINAL = ("done", "gap", "blocked", "needs_drive", "carried", "skipped")
GAP_CODES = ("control_not_found", "content_not_found", "control_covered", "no_response", "wrong_target", "left_app",
             "unreachable", "capture_failed", "danger_refused")
PERMISSION_ALLOW = ("仅使用期间允许", "允许本次使用", "本次使用", "允许", "始终允许", "allow", "while using the app")
PERMISSION_DENY = ("禁止", "不允许", "拒绝", "deny", "don't allow")
LOCATION_WORDS = ("位置", "定位", "location")
ANR_WORDS = ("无响应", "没有响应", "isn't responding", "not responding")
# View-state controls whose result depends on the current state (prev/next, +/-): entered from the base state.
OPPOSITES = (("前一", "后一"), ("上一", "下一"), ("昨天", "明天"), ("prev", "next"), ("pre", "next"), ("增加", "减少"),
             ("放大", "缩小"))
RELATIVE_RE = re.compile(r"前一|后一|上一|下一|昨|明|prev|next|pre\b|^iv_pre|^iv_next|increase|decrease|plus|minus|"
                         r"^[<>‹›＜＞+\-－]$|增加|减少|放大|缩小", re.I)


class Halt(Exception):
    def __init__(self, status: str, reason: str):
        super().__init__(reason)
        self.status, self.reason = status, reason


def selected(obs: Obs, bundle: str) -> set:
    return {hui.norm_label(hui.label_of(obs.nodes, n)) for n in obs.nodes
            if n.bundle == bundle and not n.covered and (n.selected or n.checked)} - {""}


def sig_of(frames_nodes: list, obs: Obs, bundle: str) -> dict:
    structure, texts = set(), set()
    for nodes in frames_nodes:
        structure |= hui.structure(nodes, bundle)
        texts |= hui.text_patterns(nodes, bundle)
    return {"page_path": obs.page_path, "overlay": obs.overlay, "structure": sorted(structure),
            "texts": sorted(texts), "selected": sorted(selected(obs, bundle))}


def screen_key(obs: Obs, bundle: str) -> tuple:
    """What a tap must change: page, layer, what is shown where, selection."""
    sel = frozenset(hui.label_of(obs.nodes, n) for n in obs.nodes
                    if n.bundle == bundle and not n.covered and (n.selected or n.checked))
    return (obs.bundle, obs.page_path, obs.overlay, hui.placed_texts(obs.nodes, bundle), obs.structure(bundle), sel)


class HWalker:
    def __init__(self, dev, store: Store, plan: Plan, profile: dict, rnd: int, scope: list | None = None,
                 log=print, clock=time.monotonic, bridge: PopupBridge | None = None, max_minutes: float = 0,
                 reset: list | None = None):
        self.dev, self.store, self.plan, self.profile, self.rnd = dev, store, plan, profile, rnd
        self.bundle = profile["bundle"]
        self.log, self.clock = log, clock
        self.bridge = bridge
        lim = profile.get("limits") or {}
        self.lim = {"max_swipes": int(lim.get("max_swipes", 8)), "extra_swipes": int(lim.get("extra_swipes", 2)),
                    "breaker": int(lim.get("breaker", 3)), "search_swipes": int(lim.get("search_swipes", 4)),
                    "max_minutes": float(max_minutes or lim.get("max_minutes", 0) or 0)}
        self.scope = set(scope) if scope else None
        self.reset = list(reset or ())
        self.t0 = clock()
        self.cur: Obs | None = None
        self.here: str | None = None       # Android id of the unit the device is believed to show
        self.state: dict = {}
        self.prev_index = store.index_by_pair()

    # ------------------------------------------------------------------ state
    def new_state(self) -> dict:
        return {"version": VERSION, "round": self.rnd, "bundle": self.bundle, "status": "running",
                "started": now_iso(), "units": {}, "gaps": [], "failures": 0, "elapsed_s": 0.0,
                "baseline": {}, "counters": {"taps": 0, "restarts": 0, "replays": 0, "backs": 0, "captures": 0,
                                             "frames": 0, "searches": 0, "permissions": 0},
                "app": {}, "density": None, "scope": sorted(self.scope) if self.scope else None}

    def save(self) -> None:
        self.state["elapsed_s"] = round(self.state.get("_base_elapsed", 0.0) + self.clock() - self.t0, 2)
        self.state["device_counters"] = self.dev.counters
        if self.bridge is not None:
            self.state["popup_stats"] = self.bridge.stats
        self.store.save_state(self.rnd, self.state)

    def us(self, pid: str) -> dict:
        return self.state["units"].setdefault(pid, {"status": "pending"})

    def gap(self, pid: str | None, code: str, obs: Obs | None = None, png: bytes | None = None, **detail) -> None:
        rec = {"code": code, "android": pid, "t": now_iso(), **detail}
        if obs is not None or png is not None:
            rec["evidence"] = self.store.anomaly(f"r{self.rnd}_{code}_{pid or 'x'}_{len(self.state['gaps']) + 1}",
                                                 raw=obs.raw if obs else None, png=png)
        self.state["gaps"].append(rec)
        self.store.event("gap", rec)
        if pid:
            u = self.us(pid)
            u.update(status="gap", gap=code, detail=detail)
            for d in self.plan.descendants(pid):
                du = self.us(d)
                if du.get("status") not in ("done", "needs_drive"):
                    du.update(status="blocked", blocked_by=pid)

    def failure(self, why: str) -> None:
        self.state["failures"] += 1
        self.store.event("failure", {"why": why, "consecutive": self.state["failures"]})
        if self.state["failures"] >= self.lim["breaker"]:
            raise Halt("halted_breaker", f"{self.state['failures']} consecutive unrecovered failures; last: {why}")

    def success(self) -> None:
        self.state["failures"] = 0

    def check_time(self) -> None:
        if self.lim["max_minutes"] and (self.clock() - self.t0) / 60 >= self.lim["max_minutes"]:
            raise Halt("max_minutes", f"walk reached {self.lim['max_minutes']} minutes; run again to resume")

    # ------------------------------------------------------------------ observation
    def observe(self, purpose: str) -> Obs | None:
        try:
            self.cur = self.dev.dump(purpose)
        except (DumpError, DeviceError) as exc:
            self.cur = None
            self.store.event("observe_failed", {"purpose": purpose, "error": str(exc)[:200]})
            return None
        return self.cur

    def settle(self, obs: Obs | None, purpose: str) -> Obs | None:
        """System states the executor answers itself: permission prompts, ANR, soft keyboard."""
        for _ in range(4):
            if obs is None:
                return None
            if obs.overlay == "permission":
                if not self.answer_permission(obs):
                    return obs
                obs = self.observe("permission")
                continue
            anr = [n for n in obs.nodes if not n.covered and any(w in (n.text or "") for w in ANR_WORDS)]
            if anr:
                close = hui.select(obs.nodes, {"text": "关闭应用"}) or hui.select(obs.nodes, {"text": "关闭"})
                wait = hui.select(obs.nodes, {"text": "等待"})
                self.store.event("transient", {"type": "anr"})
                target = (wait or close)[0] if (wait or close) else None
                if target is None:
                    self.dev.back("transient")
                else:
                    self.dev.tap(*hui.tap_target(obs.nodes, target).center, "transient")
                obs = self.observe("transient")
                continue
            if any(n.type in hui.INPUT_TYPES and n.focused for n in obs.nodes if not n.covered) \
                    and any(w.bundle.endswith("inputmethod") or "keyboard" in w.bundle for w in obs.windows):
                self.dev.back("transient")
                obs = self.observe("transient")
                continue
            break
        return obs

    def answer_permission(self, obs: Obs) -> bool:
        if not self.profile.get("grant_permissions", True):
            return False
        loc = any(any(w in (n.text or "") for w in LOCATION_WORDS) for n in obs.nodes if not n.covered)
        words = PERMISSION_DENY if (loc and not self.profile.get("grant_location", False)) else PERMISSION_ALLOW
        for w in words:
            hits = [n for n in obs.nodes if not n.covered and hui.norm_label(hui.label_of(obs.nodes, n)) == hui.norm_label(w)
                    and (n.clickable or n.type == "Button" or n.text)]
            if hits:
                self.dev.tap(*hui.tap_target(obs.nodes, hits[0]).center, "permission")
                self.state["counters"]["permissions"] += 1
                self.store.event("permission", {"answer": w, "location": loc})
                return True
        return False

    def wait_loaded(self, obs: Obs | None) -> Obs | None:
        for _ in range(3):
            if obs is None or not obs.in_app:
                return obs
            if not (hui.loading(obs.nodes, self.bundle) or hui.blank_web(obs.nodes, self.bundle)):
                return obs
            self.dev.pause(1.2, "loading")
            obs = self.observe("loading")
        return obs

    def popup(self, obs: Obs, phase: str, context: dict) -> tuple:
        if self.bridge is None:
            raise PopupStop("paused_model", "popup needs the model but no bridge is attached")
        context = {"phase": phase, **context}
        self.save()
        out, cont = self.bridge.handle(self.dev, obs, lambda p: self.settle(self.observe(p), p), context)
        self.cur = out
        return out, cont

    # ------------------------------------------------------------------ identity
    def sig(self, pid: str) -> dict | None:
        u = self.state["units"].get(pid, {})
        if u.get("sig"):
            return u["sig"]
        prev = self.prev_index.get(pid)
        return prev.get("sig") if prev else None

    def identify(self, obs: Obs | None, pid: str, base: bool) -> bool:
        return not self.mismatch(obs, pid, base)

    def mismatch(self, obs: Obs | None, pid: str, base: bool) -> str:
        """'' when the screen is unit pid (in its base state when base), else the first failing check."""
        s = self.sig(pid)
        if obs is None or not obs.in_app:
            return "not_in_app"
        if not s:
            return "no_signature"
        if s.get("page_path") and obs.page_path != s["page_path"]:
            return "page_path"
        if base and (s.get("overlay") or "") != obs.overlay:
            return "overlay"
        known = set(s.get("structure") or ())
        if not base:  # any state of the page: its view states captured so far count as the page too
            for v in self.view_states(pid):
                known |= set((self.sig(v) or {}).get("structure") or ())
        if known and hui.containment(obs.structure(self.bundle), frozenset(known)) < 0.5:
            return "structure"
        if base:
            vis = hui.text_patterns(obs.nodes, self.bundle)
            own = set(s.get("texts") or ())
            if vis and len(vis & own) / len(vis) < 0.75:
                return "texts"
            # a state is known by its own content: texts only a captured sibling state showed (the monthly plan's
            # auto-renewal note) mean another state, even when nothing on screen is marked selected
            others = set()
            for v in self.view_states(pid):
                others |= set((self.sig(v) or {}).get("texts") or ())
            if (others - own) & vis:
                return "another_state"
            shown = {c.norm for c in hui.labelled(obs.nodes, self.bundle)}
            if (set(s.get("selected") or ()) & shown) - selected(obs, self.bundle):
                return "selection"  # a visible tab/day/segment other than the base one is selected
        if pid == (self.plan.root.page_id if self.plan.root else None) and not self.root_visible(obs):
            return "root_selector"
        return ""

    def view_states(self, pid: str) -> list:
        out, stack = [], [c for c in self.plan.units[pid].children if self.plan.units[c].kind == "view_state"]
        while stack:
            c = stack.pop()
            out.append(c)
            stack.extend(x for x in self.plan.units[c].children if self.plan.units[x].kind == "view_state")
        return out

    def backs_to(self, pid: str) -> int:
        """BACK presses from the believed unit up to pid: one per page/layer on the way; view states need none
        (BACK on a view state leaves the page)."""
        if not self.here or self.here not in self.plan.units or pid not in self.plan.ancestors(self.here):
            return 0
        n, u = 0, self.plan.units[self.here]
        while u.page_id != pid and u.parent:
            if u.kind != "view_state":
                n += 1
            u = self.plan.units[u.parent]
        return min(n, 4)

    def root_visible(self, obs: Obs) -> bool:
        sel = self.profile.get("root")
        return bool(hui.select(obs.nodes, sel, self.bundle)) if sel else True

    # ------------------------------------------------------------------ start / navigation
    def recipe_rule(self, obs: Obs) -> dict | None:
        for rule in self.profile.get("start_recipe") or ():
            if hui.select(obs.nodes, rule["when"]):
                return rule
        return None

    def apply_rule(self, obs: Obs, rule: dict) -> None:
        self.store.event("start_recipe", {"rule": rule.get("note") or rule.get("when")})
        if "tap" in rule:
            hits = hui.select(obs.nodes, rule["tap"])
            if hits:
                self.dev.tap(*hui.tap_target(obs.nodes, hits[0]).center, "start")
        if rule.get("back"):
            self.dev.back("start")
        if rule.get("wait"):
            self.dev.pause(float(rule["wait"]), "start")

    def cold_start(self, first: bool = False) -> Obs | None:
        self.state["counters"]["restarts"] += 0 if first else 1
        self.store.event("cold_start", {"first": first})
        self.dev.force_stop("restart")
        self.dev.pause(0.3, "restart")
        self.dev.start("restart")
        prev, stuck, asked, blocked = None, 0, 0, None
        self.start_issue = None
        for _ in range(20):
            obs = self.settle(self.observe("start"), "start")
            if obs is None:
                self.dev.pause(1.0, "restart")
                continue
            if not obs.in_app:
                if stuck >= 2:
                    self.start_issue = ("left_app", obs)  # the app does not stay in front: a crash at start-up
                    break
                stuck += 1
                self.dev.start("restart")
                continue
            rule = self.recipe_rule(obs)
            if rule:
                self.apply_rule(obs, rule)
                prev = None
                continue
            if self.root_visible(obs) and not obs.overlay:
                key = (obs.page_path, obs.structure(self.bundle))
                if key == prev or not first:
                    self.here = self.plan.root.page_id if self.plan.root else None
                    self.check_readings(obs)
                    return obs
                prev = key
                self.dev.pause(0.6, "restart")
                continue
            if hui.loading(obs.nodes, self.bundle) or not hui.labelled(obs.nodes, self.bundle):
                self.dev.pause(1.0, "restart")  # loading or a blank transition screen
                continue
            fp = popup_signature(obs, self.bundle)
            if fp != blocked:  # ask only about a screen that stays put
                blocked = fp
                self.dev.pause(1.0, "restart")
                continue
            if asked >= 3:
                self.start_issue = ("root_not_visible", obs)
                break
            asked += 1
            blocked = None
            obs, _ = self.popup(obs, "startup", {"why": "root page not visible after launch",
                                                 "root_selector": self.profile.get("root")})
        self.store.event("cold_start_failed", {})
        return None

    def check_readings(self, obs: Obs) -> None:
        readings = self.profile.get("business_readings") or ()
        if not readings:
            return
        base = self.state.setdefault("baseline", {})
        drift = {}
        for r in readings:
            hits = hui.select(obs.nodes, r["selector"], self.bundle)
            value = (hits[0].text or hits[0].desc).strip() if hits else ""
            if not value:
                continue
            if r["name"] not in base:
                base[r["name"]] = value
            elif base[r["name"]] != value:
                drift[r["name"]] = {"expected": base[r["name"]], "actual": value}
        if drift:
            self.store.event("drift", drift)
            if self.state.get("drift_seen"):
                raise Halt("halted_drift", f"business readings changed: {drift}")
            self.state["drift_seen"] = True
        else:
            self.state.pop("drift_seen", None)

    def hop_path(self, pid: str) -> list:
        """Android units whose steps lead from the root to pid."""
        return [p for p in self.plan.ancestors(pid) if not self.plan.units[p].is_root] + [pid]

    def tap_step(self, step: Step, obs: Obs, purpose: str, label: str) -> tuple:
        """Locate (with bounded scroll search) and tap. Returns (after_obs, hit, reason, before_obs)."""
        hit, why, obs = self.search(step, obs, purpose)
        if hit is None:
            return None, None, why, obs
        pt = hui.tap_point(obs.nodes, hit.node, self.bundle)
        for _ in range(2):  # covered (a bottom bar over the last row, a floating layer): bring it out, find it again
            if pt is not None:
                break
            c = hui.primary_container(obs.nodes, self.bundle)
            if c is None:
                break
            x1, y1, x2, y2 = c.bounds
            up = hit.node.center[1] > (y1 + y2) // 2
            a, b = (y1 + (y2 - y1) * 6 // 10, y1 + (y2 - y1) * 3 // 10) if up else \
                (y1 + (y2 - y1) * 3 // 10, y1 + (y2 - y1) * 6 // 10)
            self.dev.swipe((x1 + x2) // 2, a, (x1 + x2) // 2, b, purpose + "_uncover")
            nxt = self.observe(purpose + "_uncover")
            if nxt is None:
                break
            again = self.track(nxt.nodes, obs.nodes, hit.node, b - a)  # the same control, whatever rule found it
            if again is None:
                break
            obs, hit = nxt, locate.Hit(again, hit.method, hit.distance, hit.label)
            pt = hui.tap_point(obs.nodes, hit.node, self.bundle)
        if pt is None:
            return None, None, "control_covered", obs
        x, y = pt
        self.dev.tap(x, y, purpose)
        self.state["counters"]["taps"] += 1
        after = self.settle(self.observe(purpose), purpose)
        return after, hit, "", obs

    def track(self, nodes: list, old_nodes: list, node, dy: int):
        """The control found before a scroll, after it: same type, size, id and label, nearest to where the scroll
        (content moved by about dy) should have put it."""
        x1, y1, x2, y2 = node.bounds
        w, h, lab = x2 - x1, y2 - y1, hui.norm_label(hui.label_of(old_nodes, node))
        cands = [n for n in nodes if n.bundle == self.bundle and not n.covered and n.type == node.type
                 and n.ident == node.ident and abs((n.bounds[2] - n.bounds[0]) - w) <= 0.1 * w + 2
                 and abs((n.bounds[3] - n.bounds[1]) - h) <= 0.1 * h + 2
                 and hui.norm_label(hui.label_of(nodes, n)) == lab]
        ex, ey = node.center[0], node.center[1] + dy
        return min(cands, key=lambda n: (n.center[0] - ex) ** 2 + (n.center[1] - ey) ** 2) if cands else None

    def search(self, step: Step, obs: Obs, purpose: str) -> tuple:
        """Label rules on the current viewport, then while scrolling forward, then from the top; the position rule
        only at the viewport the Android step was taken on (scroll_index swipes from the top)."""
        hit, why = locate.find(obs.nodes, self.bundle, step, position=False)
        if hit is not None:
            return hit, "", obs
        hit, obs = self.search_row(step, obs, purpose)
        if hit is not None:
            return hit, "", obs
        c = hui.primary_container(obs.nodes, self.bundle)
        if c is None:
            hit, why = locate.find(obs.nodes, self.bundle, step, position=True)
            return (hit, "", obs) if hit else self.list_fallback(step, obs, why)
        self.state["counters"]["searches"] += 1
        cur = obs
        for _ in range(max(self.lim["search_swipes"], step.scroll_index + 2)):
            hcapture.swipe_forward(self.dev, c.bounds, "vertical", purpose + "_search")
            nxt = self.observe(purpose + "_search")
            if nxt is None:
                return None, "dump_failed", cur
            live, issue = hcapture.continuity(cur, nxt, self.bundle, c)
            hit, why2 = locate.find(nxt.nodes, self.bundle, step, position=False)
            if hit is not None:
                return hit, "", nxt
            if issue:
                return None, why, nxt
            v = hcapture.judge(cur.nodes, nxt.nodes, self.bundle, live.bounds, "vertical")
            cur, c = nxt, live
            if not v.get("progress"):
                break
        cur = hcapture.rewind(self.dev, self.bundle, cur, max_swipes=8)
        hit, why2 = locate.find(cur.nodes, self.bundle, step, position=False)
        if hit is not None:
            return hit, "", cur
        c = hui.primary_container(cur.nodes, self.bundle) or c
        for _ in range(step.scroll_index):
            hcapture.swipe_forward(self.dev, c.bounds, "vertical", purpose + "_search")
            nxt = self.observe(purpose + "_search")
            if nxt is None:
                return None, "dump_failed", cur
            cur = nxt
            c = hui.primary_container(cur.nodes, self.bundle) or c
        hit, why2 = locate.find(cur.nodes, self.bundle, step, position=True)
        if hit is not None:
            return hit, "", cur
        return self.list_fallback(step, cur, why2 or why)

    def search_row(self, step: Step, obs: Obs, purpose: str, any_row: bool = False) -> tuple:
        """A labelled control in a horizontally scrolling row (category tabs, chips) at the height the Android step
        was taken (any_row: every such row, top first -- a hand-driven tap has no Android position): swipe the row
        forward, then back, looking for the label. Returns (hit, obs)."""
        r = step.ratio
        if (r is None and not any_row) or not hui.norm_label(step.label or step.text or step.desc):
            return None, obs
        w, h = hui.screen_size(obs.nodes)
        rows = [c for c in hui.scroll_containers(obs.nodes, self.bundle)
                if c.type != "Swiper" and hui.container_axis(c, (w, h)) == "horizontal"
                and (r is None or c.bounds[1] - 0.08 * h <= r[1] * h <= c.bounds[3] + 0.08 * h)]
        rows.sort(key=lambda c: abs((c.bounds[1] + c.bounds[3]) / 2 - r[1] * h) if r else c.bounds[1])
        cur = obs
        for c in rows:
            hit, cur = self._swipe_row(step, cur, c, purpose)
            if hit is not None:
                return hit, cur
        return None, cur

    def _swipe_row(self, step: Step, obs: Obs, c, purpose: str) -> tuple:
        key, cur = hui.container_key(c), obs
        self.state["counters"]["searches"] += 1
        for fwd in (True, False):
            for _ in range(self.lim["search_swipes"] + 2):
                (hcapture.swipe_forward if fwd else hcapture.swipe_backward)(self.dev, c.bounds, "horizontal",
                                                                             purpose + "_row")
                nxt = self.observe(purpose + "_row")
                if nxt is None:
                    return None, cur
                hit, _ = locate.find(nxt.nodes, self.bundle, step, position=False)
                if hit is not None:
                    return hit, nxt
                moved = hcapture.judge(cur.nodes, nxt.nodes, self.bundle, c.bounds, "horizontal").get("changed")
                cur = nxt
                c = hui.find_container(cur.nodes, self.bundle, key) or c
                if not moved:
                    break
        return None, cur

    def list_fallback(self, step: Step, obs: Obs, why: str) -> tuple:
        """The Android step tapped a list member whose label HarmonyOS does not show (random or different data, an
        empty list): the member at the same place of the same kind of list; none -> content_not_found."""
        if step.family_size < 2 or not hui.norm_label(step.label or step.text or step.desc) or \
                why.startswith(("danger", "confirm")):
            return None, why, obs
        fam = step.family
        avoid = {hui.norm_label(x.step.label) for x in self.plan.units.values()
                 if x.step and fam and x.step.family == fam and x.step.label and x.step.label != step.label}
        hit = locate.family_fallback(obs.nodes, self.bundle, step, avoid)
        return (hit, "", obs) if hit else (None, "content_not_found", obs)

    def do_step(self, s: Step, obs: Obs, purpose: str) -> tuple:
        """Replay one Android click-path step. Returns (obs, hit_or_None, reason)."""
        if s.action == "back":
            self.dev.back(purpose)
            return self.settle(self.observe(purpose), purpose), None, ""
        if s.action == "swipe":
            c = hui.primary_container(obs.nodes, self.bundle) if obs else None
            box = c.bounds if c else (0, 0, *hui.screen_size(obs.nodes))
            axis = "vertical" if s.direction in ("up", "down") else "horizontal"
            fwd = s.direction in ("up", "left")
            (hcapture.swipe_forward if fwd else hcapture.swipe_backward)(self.dev, box, axis, purpose)
            return self.observe(purpose), None, ""
        if s.action == "text":
            return obs, None, "text_input"
        after, hit, why, before = self.tap_step(s, obs, purpose, s.label)
        if hit is None:
            return before, None, why or "not_found"
        if after is None or not after.in_app:
            return after, None, "left_app"
        if screen_key(after, self.bundle) == screen_key(before, self.bundle):
            self.dev.pause(1.0, "slow_tap")
            after = self.settle(self.observe(purpose), purpose)
            if after is None or screen_key(after, self.bundle) == screen_key(before, self.bundle):
                return after, None, "no_change"
        return self.wait_loaded(after), hit, ""

    def restore_base(self, pid: str, obs: Obs) -> Obs | None:
        """On the page but in another view state: tap back the control that was selected in the base state
        (a tab, a day, a segment), as the Android walk does, instead of a cold start."""
        s = self.sig(pid) or {}
        shown = {c.norm for c in hui.labelled(obs.nodes, self.bundle)}
        want = (set(s.get("selected") or ()) & shown) - selected(obs, self.bundle)
        if not want:
            return self.undo_relative(pid, obs)
        for label in sorted(want):
            hits = [c for c in hui.labelled(obs.nodes, self.bundle) if c.norm == label]
            if not hits:
                return None
            self.dev.tap(*hits[0].node.center, "view_base")
            obs = self.settle(self.observe("view_base"), "view_base")
            if obs is None:
                return None
        self.store.edge({"kind": "view_base", "to": pid, "labels": sorted(want)})
        return obs if self.identify(obs, pid, True) else None

    def undo_relative(self, pid: str, obs: Obs) -> Obs | None:
        """The page sits in a state reached by a relative control (prev day): tap its opposite once (next day)."""
        last = self.here if self.here in self.plan.units else None
        u = self.plan.units.get(last) if last else None
        if not u or u.kind != "view_state" or u.parent != pid or not u.step:
            return None
        label = (u.step.label or u.step.rid or "")
        for a, b in OPPOSITES:
            if a in label or b in label:
                other = label.replace(a, "\0").replace(b, a).replace("\0", b)
                step = Step(action="tap", label=other if u.step.label else "", rid=other if not u.step.label else "",
                            center=None)
                hits = [c for c in hui.labelled(obs.nodes, self.bundle) if c.norm == hui.norm_label(other)]
                if len(hits) != 1:
                    return None
                self.dev.tap(*hits[0].node.center, "view_base")
                got = self.settle(self.observe("view_base"), "view_base")
                self.store.edge({"kind": "view_base", "to": pid, "opposite": other})
                return got if got is not None and self.identify(got, pid, True) else None
        return None

    def replay_steps(self, steps: list, obs: Obs) -> Obs | None:
        for s in steps:
            obs, hit, why = self.do_step(s, obs, "replay")
            if why or obs is None:
                return None
        return obs

    def replay_to(self, pid: str, obs: Obs) -> Obs | None:
        """From the root, replay the Android click path of pid (ancestor final steps use their richer via)."""
        self.state["counters"]["replays"] += 1
        for i, s in enumerate(self.plan.click_steps(pid)):
            obs, hit, why = self.do_step(s, obs, "replay")
            self.store.edge({"kind": "replay", "to": pid, "step": i, "label": s.label, "result": why or "ok",
                             "method": hit.method if hit else None})
            if why or obs is None:
                return None
        self.here = pid
        return obs

    def ensure_at(self, pid: str, base: bool) -> Obs | None:
        """Make the device show unit pid (in its base state when base): current -> BACK -> cold start + replay."""
        obs = self.cur or self.settle(self.observe("verify"), "verify")
        if self.identify(obs, pid, base):
            self.here = pid
            return obs
        if base and self.identify(obs, pid, False):
            got = self.restore_base(pid, obs)
            if got is not None:
                self.here = pid
                self.success()
                return got
        backs = self.backs_to(pid)
        if backs:
            for _ in range(backs):
                self.dev.back("return")
                self.state["counters"]["backs"] += 1
                obs = self.settle(self.observe("return"), "return")
                if self.identify(obs, pid, base):
                    self.here = pid
                    self.success()
                    return obs
                if obs is None or not obs.in_app:
                    break
            if base and self.identify(obs, pid, False):
                got = self.restore_base(pid, obs)
                if got is not None:
                    self.here = pid
                    self.success()
                    return got
        self.store.event("ensure_cold", {"target": pid, "here": self.here, "base": base,
                                         "why": self.mismatch(obs, pid, base),
                                         "page": obs.page_path if obs else None})
        obs = self.cold_start()
        if obs is None:
            self.failure("cold start failed")
            return None
        if self.plan.root and pid == self.plan.root.page_id:
            self.success()
            return obs
        got = self.replay_to(pid, obs)
        if got is None:
            self.failure(f"cannot reach {pid}")
            return None
        if not self.identify(got, pid, base):
            self.store.event("identity_unverified", {"unit": pid})
        self.success()
        return got

    # ------------------------------------------------------------------ capture
    def capture_unit(self, pid: str, obs: Obs, method: str, hit_label: str, path_methods: list) -> bool:
        u = self.plan.units[pid]
        obs = self.wait_loaded(obs)
        if u.kind == "view_state":
            obs = hcapture.rewind(self.dev, self.bundle, obs)
        max_swipes = min(self.lim["max_swipes"], max(0, u.vframes - 1) + self.lim["extra_swipes"])
        hstrips = (u.hframes + 1) if u.hframes else 0
        try:
            res = hcapture.capture(self.dev, self.bundle, obs, max_swipes, hstrips,
                                   on_event=lambda k, d: self.store.event(k, d))
        except hcapture.CaptureError as exc:
            self.gap(pid, "capture_failed", obs=obs, error=str(exc)[:200])
            return False
        frames_nodes = [f.nodes for f in res.frames]
        sig = sig_of(frames_nodes, obs, self.bundle)
        a_texts = {hui.DIGITS.sub("#", t) for t in self.plan.texts(pid)}
        h_texts = set(sig["texts"])
        overlap = (len(a_texts & h_texts) / min(len(a_texts), 40)) if a_texts else None
        conf = ("unknown" if overlap is None else "confirmed" if overlap >= 0.4
                else "weak" if overlap >= 0.15 else "unconfirmed")
        if u.is_root and conf in ("weak", "unconfirmed"):  # every unit hangs off this screen: say it loudly
            self.state["root_warning"] = (
                f"the HarmonyOS root screen shares only {round(overlap or 0.0, 2)} of the Android root unit {pid}'s "
                "texts: profile root / start_recipe may land on another screen (another tab) than the Android "
                "baseline; check against the Android root screenshot, fix the profile and walk --fresh")
            self.log("[vvs] warning: " + self.state["root_warning"], flush=True)
        if conf in ("weak", "unconfirmed") and not u.is_root and u.kind != "manual":
            other, best = self.better_match(pid, h_texts, overlap or 0.0)
            if other:  # the tap led to another page of the Android tree: not the target, do not walk its children
                self.gap(pid, "wrong_target", obs=obs, landed=other, landed_label=self.plan.units[other].label,
                         overlap=round(overlap or 0.0, 3), landed_overlap=best,
                         reason=f"点击后落到了安卓「{self.plan.units[other].label}」那一页（重合 {best}，目标只有 {round(overlap or 0.0, 2)}）")
                return False
        meta = {"page_id": None, "label": u.label, "kind": u.kind,
                "pair": {"android": pid, "method": method, "matched_label": hit_label, "confidence": conf,
                         "text_overlap": round(overlap, 3) if overlap is not None else None,
                         "path_methods": path_methods},
                "harmony": {"bundle": obs.bundle, "ability": obs.ability, "page_path": obs.page_path,
                            "overlay": obs.overlay},
                "density_factor": self.state.get("density"), "sig": sig,
                "capture": {"frames": len(res.frames), "stop": res.stop, "degraded": res.degraded,
                            "container": res.container, "extra": res.extra, "interruption": res.interruption,
                            "max_swipes": max_swipes},
                "app": self.state.get("app")}
        saved = self.store.write_unit(self.rnd, res.frames, meta, pid, obs.page_path)
        self.state["counters"]["captures"] += 1
        self.state["counters"]["frames"] += len(res.frames)
        self.us(pid).update(status="done", unit_dir=saved["unit_dir"], method=method, confidence=conf, sig=sig)
        self.here = pid
        self.cur = res.last_obs if res.stop not in hcapture.TRUNCATED_STOPS else None
        if self.cur is not None and len(res.frames) > 1 and u.children:
            self.cur = hcapture.rewind(self.dev, self.bundle, self.cur)  # children are located from the top
        self.log(f"[vvs] {pid} -> {saved['unit_dir']} ({len(res.frames)} frames, {method}, {conf})", flush=True)
        return True

    def better_match(self, pid: str, h_texts: set, overlap: float) -> tuple:
        """Another Android unit whose own texts the landed screen shows clearly better than the target's. Texts
        that many units show (a bottom tab bar, a shared title) prove nothing: an empty list page and another
        sparse page share little else. At least two distinctive texts of the other unit must be on screen."""
        if not hasattr(self, "_texts"):
            self._texts = {q: {hui.DIGITS.sub("#", t) for t in self.plan.texts(q)} for q in self.plan.units}
            seen = Counter(t for a in self._texts.values() for t in a)
            n = len(self._texts)
            self._common = {t for t, c in seen.items() if c >= max(3, 0.3 * n)}
        h = h_texts - self._common
        own = self._texts.get(pid, set()) - self._common
        mine = len(own & h) / min(len(own), 40) if own else 0.0
        def base(q):  # a view state belongs to its page: another state of the same page is not another page
            u = self.plan.units[q]
            return u.parent if u.kind == "view_state" else q
        best, who = 0.0, None
        for q, a in self._texts.items():
            a = a - self._common
            if q == pid or base(q) == base(pid) or len(a) < 2 or len(a & h) < 2:
                continue
            ov = len(a & h) / min(len(a), 40)
            if ov > best:
                best, who = ov, q
        return (who, round(best, 3)) if best >= 0.4 and best >= mine + 0.2 else (None, round(best, 3))

    def in_scope(self, pid: str) -> bool:
        return self.scope is None or pid in self.scope

    def visit_child(self, pid: str) -> None:
        u = self.plan.units[pid]
        # Pages, and view states whose control is relative (prev/next, +/-), start from the parent's base state.
        # An absolute selection (a tab, a chip, a day) gives the same state from any sibling state.
        st = u.step
        relative = bool(st and (RELATIVE_RE.search(st.label or "") or RELATIVE_RE.search(st.rid or "")))
        base = u.kind != "view_state" or relative
        pre = self.plan.click_steps(pid)[:-1]
        ppath = self.plan.click_steps(u.parent)
        same = [hui.norm_label(x.label) for x in pre[:len(ppath)]] == [hui.norm_label(x.label) for x in ppath]
        extra = pre[len(ppath):] if same else None
        if extra is None:  # aft reached it along another route than its parent: replay its own path
            obs = self.cold_start()
            obs = self.replay_steps(pre, obs) if obs is not None else None
        else:
            obs = self.ensure_at(u.parent, base or bool(extra))
            for i, s in enumerate(extra):  # Android selected a state first (a date, a tab) before this control
                if obs is None:
                    break
                obs, hit, why = self.do_step(s, obs, "precondition")
                if why:
                    self.gap(pid, why if why == "content_not_found" else "control_not_found"
                             if why in ("not_found", "label_not_found", "position_not_found")
                             else "unreachable", obs=obs, reason=f"precondition step {i} '{s.label}': {why}",
                             android_step=s.as_dict())
                    self.here, self.cur = None, None
                    return
        if obs is None:
            self.gap(pid, "unreachable", reason=f"parent {u.parent} not reachable")
            return
        before_key = screen_key(obs, self.bundle)
        after, hit, why, before = self.tap_step(u.step, obs, "explore", u.label)
        if hit is None and not (base or extra) and extra is not None and not why.startswith(("danger", "confirm")) \
                and before is not None and not self.identify(before, u.parent, True):
            # an absolute selection was assumed reachable from any sibling state, but a sibling state can hide the
            # control (another plan selected hides the payment options): once more from the parent's base state --
            # only when the screen is not in that state already (otherwise the same search would just run again)
            obs = self.ensure_at(u.parent, True)
            if obs is not None:
                before_key = screen_key(obs, self.bundle)
                after, hit, why, before = self.tap_step(u.step, obs, "explore", u.label)
        if hit is None:
            png = self._png()
            code = "danger_refused" if why.startswith(("danger", "confirm")) else \
                why if why in ("content_not_found", "control_covered") else "control_not_found"
            self.gap(pid, code, obs=before, png=png, reason=why, android_step=u.step.as_dict(), parent=u.parent)
            self.here = u.parent
            self.cur = before
            return
        if after is None:
            self.gap(pid, "no_response", reason="no observation after tap", android_step=u.step.as_dict())
            return
        if not after.in_app:  # a crash or another app: the device fault log tells which, keep its path
            self.gap(pid, "left_app", obs=after, png=self._png(), owner=after.bundle, matched=hit.label,
                     method=hit.method, crash_logs=self.dev.crash_logs())
            self.here, self.cur = None, None
            return
        if screen_key(after, self.bundle) in (before_key, screen_key(before, self.bundle)):
            self.dev.pause(1.0, "slow_tap")
            after = self.settle(self.observe("explore"), "explore")
            if after is None or screen_key(after, self.bundle) in (before_key, screen_key(before, self.bundle)):
                self.gap(pid, "no_response", obs=after, png=self._png(), matched=hit.label, method=hit.method,
                         android_step=u.step.as_dict())
                self.here, self.cur = u.parent, after
                return
        continued = False
        if after.overlay and not u.layer and not self._overlay_expected(pid, after):
            after, continued = self.popup(after, "navigation", {
                "why": "a layer appeared that the Android screen does not have",
                "android_unit": pid, "android_label": u.label,
                "android_screenshot": self.plan._abs(u.frames[0][0]) if u.frames else None,
                "tapped": hit.label})
            if after is None or not after.in_app:
                self.gap(pid, "left_app", obs=after)
                self.here, self.cur = None, None
                return
        methods = [self.us(h).get("method") for h in self.hop_path(u.parent)] if u.parent else []
        self.capture_unit(pid, after, hit.method, hit.label, methods)
        if u.kind == "danger_dialog":
            self.dismiss(after)

    def _overlay_expected(self, pid: str, obs: Obs) -> bool:
        a = {hui.DIGITS.sub("#", t) for t in self.plan.first_texts(pid)}
        top = hui.dialog_node(obs.nodes)
        scope = [obs.nodes[i] for i in hui.subtree(obs.nodes, top)] if top else [n for n in obs.nodes if not n.covered]
        h = {hui.digit_pattern(n.text) for n in scope if n.text.strip()}
        return bool(a and h and len(a & h) / max(1, min(len(a), len(h))) >= 0.2)

    def dismiss(self, obs: Obs) -> None:
        cancel = [n for n in obs.nodes if not n.covered and hui.is_cancel_label(hui.label_of(obs.nodes, n))
                  and (n.clickable or n.type == "Button")]
        if cancel:
            self.dev.tap(*hui.tap_target(obs.nodes, cancel[0]).center, "dismiss")
        else:
            self.dev.back("dismiss")
        self.cur = None

    def _png(self) -> bytes | None:
        try:
            return self.dev.screencap("evidence")
        except DeviceError:
            return None

    def visit_manual(self, pid: str) -> None:
        u = self.plan.units[pid]
        if not u.replayable:
            self.us(pid).update(status="needs_drive", reason=u.drive_reason)
            return
        obs = self.cold_start()
        if obs is None:
            self.failure("cold start failed")
            self.gap(pid, "unreachable", reason="cold start failed")
            return
        methods = []
        for i, s in enumerate(u.path):
            if s.action == "back":
                self.dev.back("manual")
                obs = self.settle(self.observe("manual"), "manual")
            elif s.action == "swipe":
                c = hui.primary_container(obs.nodes, self.bundle) if obs else None
                box = c.bounds if c else (0, 0, *hui.screen_size(obs.nodes))
                if s.direction in ("up", "down"):
                    (hcapture.swipe_forward if s.direction == "up" else hcapture.swipe_backward)(
                        self.dev, box, "vertical", "manual")
                else:
                    (hcapture.swipe_forward if s.direction == "left" else hcapture.swipe_backward)(
                        self.dev, box, "horizontal", "manual")
                obs = self.observe("manual")
            else:
                before = obs
                obs, hit, why, before = self.tap_step(s, obs, "manual", s.label)
                if hit is None:
                    # The Android side of a manual unit was hand-driven (often through content items such as a
                    # template name): a failed replay asks for a HarmonyOS drive, it is not a missing entry.
                    ev = self.store.anomaly(f"r{self.rnd}_manual_replay_{pid}", raw=before.raw if before else None,
                                            png=self._png())
                    self.us(pid).update(status="needs_drive", reason=f"replay step {i} '{s.label}': {why}",
                                        evidence=ev)
                    self.store.event("manual_replay_failed", {"android": pid, "step": i, "label": s.label, "why": why})
                    self.here, self.cur = None, before
                    return
                methods.append(hit.method)
            if obs is None or not obs.in_app:
                self.gap(pid, "left_app", obs=obs, step_index=i)
                self.here, self.cur = None, None
                return
        self.capture_unit(pid, obs, methods[-1] if methods else "path", u.label, methods)

    # ------------------------------------------------------------------ run
    def setup(self, resume: bool) -> None:
        prev = self.store.state(self.rnd)
        if resume and prev and prev.get("bundle") == self.bundle:
            self.state = prev
            self.state["_base_elapsed"] = prev.get("elapsed_s", 0.0)
            old = prev.get("device_counters") or {}
            for k in ("ops", "time", "purpose", "purpose_time"):  # device time accumulates over resumed runs
                for op, v in (old.get(k) or {}).items():
                    self.dev.counters[k][op] = round(self.dev.counters[k].get(op, 0) + v, 4)
            self.state["status"] = "running"
            for pid, u in self.state["units"].items():
                if u.get("status") == "blocked" or (u.get("status") == "gap" and u.get("gap") == "unreachable"):
                    u["status"] = "pending"  # unreachable is retried on resume; real gaps stay
        else:
            self.state = self.new_state()
        self.state["app"] = self.dev.app_version() or self.state.get("app") or {}
        if self.state.get("density") is None:
            self.state["density"] = self.dev.density()
        if not self.dev.ability:
            self.dev.ability = self.profile.get("ability") or self.dev.main_ability()
        for pid in self.reset:  # walk --only: re-capture these even when an earlier attempt ended in a gap
            if pid in self.plan.units:
                self.state["units"][pid] = {"status": "pending"}
                self.state["gaps"] = [g for g in self.state["gaps"] if g.get("android") != pid]
                for d in self.plan.descendants(pid):
                    if self.state["units"].get(d, {}).get("blocked_by") == pid:
                        self.state["units"][d] = {"status": "pending"}
        if self.scope is not None:
            for pid in self.plan.units:
                if pid not in self.scope and pid in self.prev_index and self.us(pid).get("status") == "pending":
                    self.us(pid).update(status="carried", unit_dir=self.prev_index[pid].get("unit_dir"))
        self.save()

    def run(self, resume: bool = True) -> dict:
        self.setup(resume)
        self.store.session({"cmd": "walk", "round": self.rnd, "event": "start"})
        try:
            root = self.plan.root
            if root is None:
                raise Halt("no_root", "the Android baseline has no root page")
            if self.us(root.page_id).get("status") != "done" and (self.in_scope(root.page_id) or
                                                                  root.page_id not in self.prev_index):
                obs = self.cold_start(first=True)
                if obs is None:
                    kind, seen = getattr(self, "start_issue", None) or ("root_not_visible", None)
                    if kind == "left_app":  # the launch is the step to the root: the same gap as leaving the app
                        logs = self.dev.crash_logs()
                        self.gap(root.page_id, "left_app", obs=seen, png=self._png(), owner=seen.bundle if seen else "",
                                 phase="launch", crash_logs=logs, reason="冷启动后应用立刻离开前台（疑似启动崩溃）")
                        raise Halt("halted_start", "the app leaves the foreground right after launch (a start-up crash?"
                                   + (f" newest fault log: {logs[0]}" if logs else "") + "): `tickets` writes the launch"
                                   " crash ticket; fix and rebuild before walking again, the profile is not the cause")
                    raise Halt("halted_start", "the app stays in front but the root page did not appear: check profile "
                                               "root / start_recipe against the Android root screenshot")
                self.capture_unit(root.page_id, obs, "root", "", [])
            for pid in self.plan.order():
                self.check_time()
                st = self.us(pid)
                if st.get("status") in FINAL or pid == root.page_id:
                    continue
                if not self.in_scope(pid):
                    if pid in self.prev_index:
                        st.update(status="carried", unit_dir=self.prev_index[pid].get("unit_dir"))
                        continue
                u = self.plan.units[pid]
                if u.kind in ("manual", "orphan") or not u.parent:
                    self.guard(self.visit_manual, pid)
                else:
                    parent = self.us(u.parent).get("status")
                    if parent not in ("done", "carried"):
                        st.update(status="blocked", blocked_by=u.parent)
                        continue
                    self.guard(self.visit_child, pid)
                self.save()
            self.state["status"] = "done"
        except Halt as h:
            self.state["status"], self.state["halt_reason"] = h.status, h.reason
        except PopupStop as p:
            self.state["status"], self.state["halt_reason"] = p.status, p.reason
        finally:
            self.state["finished"] = now_iso()
            self.save()
            self.store.session({"cmd": "walk", "round": self.rnd, "event": "end", "status": self.state["status"]})
        return self.state

    def guard(self, fn, pid: str) -> None:
        try:
            fn(pid)
        except (Halt, PopupStop):
            raise
        except DeviceError as exc:
            self.store.event("device_error", {"unit": pid, "error": str(exc)[:300]})
            self.gap(pid, "unreachable", reason="device error: " + str(exc)[:200])
            self.here, self.cur = None, None
            self.failure(f"device error at {pid}")
        except Exception as exc:  # a bug must not lose the run: record it and continue
            self.store.event("walker_error", {"unit": pid, "error": str(exc)[:300],
                                              "trace": traceback.format_exc()[-1500:]})
            self.gap(pid, "unreachable", reason="walker error: " + str(exc)[:200])
            self.here, self.cur = None, None
            self.failure(f"walker error at {pid}")
