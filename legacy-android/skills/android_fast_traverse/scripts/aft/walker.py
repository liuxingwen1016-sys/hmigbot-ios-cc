"""Edge traversal with automatic discovery.

Cost invariant (happy path): every explored candidate costs one dump to
identify the landing and one dump after returning, which doubles as the
locate dump for the next candidate. No per-candidate restart.

Quality guard rails:
  1. no record without fresh identity  2. business readings are checked on every observation
  3. consecutive failures trip the breaker. Everything else stays local.
"""
from __future__ import annotations

import json
import re
import time
import traceback
from collections import Counter, deque

from . import VERSION
from . import capture as cap
from . import ui
from . import registry
from .baseline import ensure_baseline
from .popup import PopupStop, screen_fingerprint
from .device import DeviceError, DumpError, Obs
from .store import now_iso

DYNAMIC_TEXT = re.compile(r"^[\d\s:./°℃%+\-~]+$")
DIGITS = re.compile(r"\d+")
COMMIT_FAMILY_MIN = 6    # list families at least this large whose items pop back up are treated as "pick and commit"
PARAM_FAMILY_MIN = 13    # families larger than this select data (dates, keywords): their view states are parameters
RELATIVE_TIME = re.compile(r"\d+\s*(秒|分钟|分|小时|天|周)前|刚刚|更新于|发布于|\d+\s*(s|sec|secs|min|mins|minutes?|h|hrs?|hours?|days?)\s+ago|"
                           r"\bupdated\b", re.I)
NAV_RESULTS = ("new", "known", "up")
LOCATION_PERM = re.compile(r"LOCATION", re.I)
LOCATION_WORDS = re.compile(r"位置|定位|location", re.I)
POLICY_SKIPS = ("danger", "denied", "confirm_in_overlay", "confirm")      # listed for the model's one-shot review
SAMPLED_SKIPS = ("list_sample", "nav_back")                    # reported, can be re-queued by an allow rule


class RefuseError(RuntimeError):
    pass


class Halt(Exception):
    def __init__(self, status: str, reason: str):
        super().__init__(reason)
        self.status, self.reason = status, reason


def cand_obj(d: dict) -> ui.Candidate:
    x1, y1, x2, y2 = ui.parse_bounds(d["bounds"])
    return ui.Candidate(key=d["key"], label=d["label"], rid=d["resource-id"], text=d["text"],
                        desc=d["content-desc"], cls=d["class"], bounds=(x1, y1, x2, y2),
                        frame=d.get("last_frame", d["scroll_index"]), kind=d["kind"], group=d.get("group", ""),
                        danger=d.get("danger", ""), denied=d.get("denied", ""), first_frame=d["scroll_index"],
                        nav_back=d.get("nav_back", False), commit=d.get("commit", ""))


def cand_dict(c: ui.Candidate) -> dict:
    d = c.as_dict()
    d["group"] = c.group
    return d


class Walker:
    def __init__(self, dev, store, profile: dict, serial: str = "", log=print, clock=time.monotonic,
                 popup_bridge=None):
        self.dev, self.store, self.profile, self.log, self.clock = dev, store, profile, log, clock
        self.pkg = profile["package"]
        self.lim = profile["limits"]
        self.dev.settle_s = self.lim["settle_s"]
        self.serial = serial
        self.cur: Obs | None = None
        self.state: dict = {}
        self.pending_drift_restore = False
        self.last_action = None   # (page key, candidate) of the tap being classified: side-effect attribution
        self.anr_waits = 0        # consecutive "Wait" taps on an ANR dialog that did not help
        self.anr_closed = False   # the last observation ended in closing a hung app
        self._deny_cache: dict = {}  # (activity, control key) -> deny reason under the current profile
        self._blocked_reason = ""    # set when a recorded path or route hit a control denied now
        self.t_start = clock()
        self.popup_bridge = popup_bridge
        self._popup_passthrough = set()

    # ------------------------------------------------------------------ state
    def new_state(self) -> dict:
        return {"version": VERSION, "package": self.pkg, "serial": self.serial, "status": "running",
                "started": now_iso(), "launcher": None, "app": {}, "density": None,
                "pages": {}, "order": [], "stack": [], "page_counter": 0, "root": None,
                "explored": {}, "skipped": [], "sampled": [], "gaps": [], "baseline": {}, "drift": None,
                "failures": 0, "elapsed_s": 0.0,
                "counters": {"explored": 0, "edges": {}, "restarts": 0, "replays": 0, "replay_steps": 0,
                             "captures": 0, "frames": 0, "views": 0, "pages": 0, "dialogs": 0,
                             "transients": 0, "instances": 0, "skipped": {}},
                "families": {}, "auto_deny": []}

    @property
    def pages(self) -> dict:
        return self.state["pages"]

    @property
    def counters(self) -> dict:
        return self.state["counters"]

    def save(self) -> None:
        self.state["elapsed_s"] = round(self.state.get("_elapsed_base", 0.0) + (self.clock() - self.t_start), 2)
        self.state["device_counters"] = self.dev.counters
        self.store.save_state(self.state)

    def bump(self, group: str, key: str, n: int = 1) -> None:
        d = self.counters.setdefault(group, {})
        d[key] = d.get(key, 0) + n

    def gap(self, code: str, page: str | None, obs: Obs | None = None, **detail) -> None:
        rec = {"code": code, "page": page, **detail}
        if obs is not None:  # keep the screen that explains the gap
            rec["evidence"] = self.store.anomaly(f"{code}_{len(self.state['gaps']) + 1}", xml=obs.xml)
        self.state["gaps"].append(rec)
        self.store.event("gap", rec)

    def edge(self, kind: str, src: str | None, cand: dict | None, dst: str | None, **extra) -> None:
        self.bump("edges", kind)
        rec = {"kind": kind, "from": src, "to": dst}
        if cand is not None:
            rec["control"] = {k: cand.get(k) for k in ("key", "label", "resource-id", "text", "content-desc",
                                                       "scroll_index")}
        rec.update(extra)
        self.store.edge(rec)

    # ------------------------------------------------------------------ observation
    def observe(self, purpose: str) -> Obs | None:
        try:
            self.cur = self.dev.dump(purpose)
        except (DumpError, DeviceError) as exc:
            self.cur = None
            self.store.event("observe_failed", {"purpose": purpose, "error": str(exc)[:200]})
            return None
        if self.cur.in_app and self.profile["business_readings"]:
            self.watch_readings(self.cur, purpose)
        return self.cur

    def watch_readings(self, obs: Obs, purpose: str) -> None:
        """Guard rail 2: business readings are checked on every observation that shows them.

        A reading is bound to the activity where its baseline was first seen (unless the profile names one), and
        once its page is known, to that page and position: another tab of the same activity, or a list that uses the
        same resource-id for its rows (a city picker), is not the reading; reading those would report drift that
        did not happen and deny an innocent tab.
        A reading that sat outside any scroll container on a known page and is now gone from that page
        counts as drift too (e.g. the logged-in user name after a logout).
        """
        base = self.state["baseline"]
        for r in self.profile["business_readings"]:
            name = r["name"]
            b = base.get(name)
            act = r.get("activity") or (b or {}).get("activity")
            if act and not obs.activity.endswith(act):
                continue
            if b is not None and b.get("page") in self.pages and not self.on_baseline_page(obs, b["page"], strict=True):
                continue
            hits = ui.select(obs.nodes, r["selector"], self.pkg)
            if b is not None and b.get("at") and hits:
                x, y = b["at"]
                hits = [n for n in hits if n.bounds[0] <= x <= n.bounds[2] and n.bounds[1] <= y <= n.bounds[3]]
            value = (hits[0].text.strip() or hits[0].desc.strip()) if hits else ""
            if b is None:
                if value:
                    fixed = not any(a.scrollable for a in ui.ancestors(obs.nodes, hits[0]))
                    base[name] = {"value": value, "activity": obs.activity, "page": self.match(obs), "fixed": fixed,
                                  "at": list(hits[0].center) if fixed else None}
                continue
            if b.get("page") is None and value:
                b["page"] = self.match(obs)
            if value:
                actual = value
            elif b.get("fixed") and b.get("page") in self.pages and self.on_baseline_page(obs, b["page"]):
                actual = "(missing)"
            else:
                continue
            drift = dict(self.state.get("drift") or {})
            if actual != b["value"]:
                if drift.get(name, {}).get("actual") != actual:
                    drift[name] = {"expected": b["value"], "actual": actual, "seen_at": purpose}
                    self.state["drift"] = drift
                    self.gap("drift", None, obs=obs, drift={name: drift[name]}, suspects=self.ranked_suspects())
                    self.pending_drift_restore = True
                    self.learn_side_effect(name, drift[name], obs)
            else:
                # Seen unchanged: no tap before this point can have changed it.
                self.state["read_clean_at"] = self.counters["explored"]
                self.state["read_suspects"] = []
                if name in drift:
                    drift.pop(name)
                    self.state["drift"] = drift or None
                    self.store.event("drift_cleared", {"reading": name})

    def note_suspect(self, page: dict, cand: dict) -> None:
        """Every tap since the readings were last seen unchanged could be the one that changed them."""
        if not self.profile["business_readings"]:
            return
        sus = self.state.setdefault("read_suspects", [])
        sus.append({"page_id": page["page_id"], "activity": page["activity"], "label": cand.get("label") or "",
                    "resource-id": (cand.get("resource-id") or "").rsplit("/", 1)[-1], "key": cand.get("key", "")})
        del sus[:-40]

    def ranked_suspects(self) -> list:
        """Taps whose page closed itself right after (picked something and went back: the commit pattern) first,
        then the rest, latest first. All are kept: the real one is often not among the latest few."""
        sus = list(reversed(self.state.get("read_suspects") or []))
        return [s for s in sus if s.get("closed_own_page")] + [s for s in sus if not s.get("closed_own_page")]

    def learn_side_effect(self, reading: str, change: dict, obs: Obs) -> None:
        """Deny the tap that changed a business reading, but only when it is certainly that tap: the reading was
        seen unchanged right before it, or the tap closed its own screen and came back to the reading changed
        (picking a city). Otherwise the change may come from any tap since the reading was last visible (a city
        picked on another screen, noticed only after a tab switch): nothing is denied, the suspects are reported."""
        if not self.last_action:
            return
        pk, c = self.last_action
        p = self.pages.get(pk)
        if p is None:
            return
        just_before = self.state.get("read_clean_at") == self.counters["explored"] - 1
        closed_own = p["activity"] != obs.activity and self.back_on_instance(self.match(obs), obs)
        if not (just_before or closed_own):
            return
        rule = {"activity": p["activity"], "reason": f"side effect: {reading} {change['expected']} -> {change['actual']}"}
        rid = (c.get("resource-id") or "").rsplit("/", 1)[-1]
        if rid:
            rule["rid"] = rid
        else:
            rule["text"] = c.get("label") or ""
        auto = self.state.setdefault("auto_deny", [])
        if not any(r.get("rid") == rule.get("rid") and r.get("text") == rule.get("text") and r["activity"] == rule["activity"]
                   for r in auto):
            auto.append(rule)
            self.gap("side_effect", p["page_id"], control=c.get("label") or rid, reading=reading, rule=rule)

    def bind_readings(self, key: str, frames: list, activity: str) -> None:
        """Baselines first seen before any page existed (cold start) are bound to the page that shows them."""
        for r in self.profile["business_readings"]:
            b = self.state["baseline"].get(r["name"])
            if not b or b.get("page") or b.get("activity") != activity:
                continue
            if any(ui.select(f.nodes, r["selector"], self.pkg) for f in frames):
                b["page"] = key

    def reading_drift(self) -> dict:
        names = {r["name"] for r in self.profile["business_readings"]}
        return {k: v for k, v in (self.state.get("drift") or {}).items() if k in names}

    def restore_drift(self) -> None:
        """One cold start per drift event clears in-memory state (a selected date). If a reading is still changed,
        the app saved it (an added city): stop here instead of capturing the rest of the app on changed data, which
        would not be usable as ground truth. The model restores the data and resumes the same OUT; the suspects are
        in the report."""
        if not self.pending_drift_restore:
            return
        self.pending_drift_restore = False
        obs = self.cold_start()
        for name in list(self.reading_drift()):
            page = (self.state["baseline"].get(name) or {}).get("page")
            if obs is not None and page in self.pages and not self.on_baseline_page(obs, page, strict=True):
                obs = self.ensure_at(page, obs)  # look where the reading is shown
        self.cur = None
        drift = self.reading_drift()
        if not drift:
            self.store.event("drift_restored", {})
            return
        what = "；".join(f"{k}: {v['expected']} → {v['actual']}" for k, v in drift.items())
        who = "；".join(f"{s['page_id']}「{s['label'] or s['resource-id']}」" + ("（点完页面自己关闭）" if s.get("closed_own_page") else "")
                       for s in self.ranked_suspects()) or "未知"
        raise Halt("halted_drift", f"业务读数冷启动后仍未恢复（{what}），App 保存了改动；嫌疑点击：{who}。"
                                   f"先恢复数据（测试机上 pm clear，或用 drive 改回），把改数据的控件写进 deny，再对同一 OUT 续跑")

    def on_baseline_page(self, obs: Obs, key: str, strict: bool = False) -> bool:
        """The screen is the baseline page, possibly in a changed state (most of its first frame still there).

        strict: by layout only. A tab drawn as a view state of the page matches the page key, but it is not the
        screen that shows the reading."""
        if not strict and self.match(obs) == key:
            return True
        p = self.pages[key]
        if p["activity"] != obs.activity or not p["frame_structs"]:
            return False
        f0 = frozenset(p["frame_structs"][0])
        return bool(f0) and len(f0 & obs.structure(self.pkg)) / len(f0) >= 0.6

    def settle(self, obs: Obs | None, *, popups: bool = True) -> Obs | None:
        """Handle transient system states: ANR dialog, soft keyboard.

        An ANR that two "Wait" taps did not clear is a hung app: close it and return None, so the caller recovers
        with a cold start instead of tapping "Wait" for minutes."""
        for _ in range(3):
            if obs is None:
                return None
            if obs.focus.kind == "anr":
                self.counters["transients"] += 1
                close = ui.select(obs.nodes, {"rid": "aerr_close"}) or ui.find_text(obs.nodes, None, ("关闭应用", "Close app"))
                if self.anr_waits >= 2 and close:
                    self.anr_waits = 0
                    self.anr_closed = True
                    self.store.event("transient", {"type": "anr", "window": obs.focus.window, "action": "close"})
                    self.gap("anr_closed", None, obs=obs)
                    x, y = close[0].center
                    self.dev.tap(x, y, "transient")
                    self.cur = None
                    return None
                hits = ui.select(obs.nodes, {"rid": "aerr_wait"}) or ui.find_text(obs.nodes, None, ("等待", "Wait"))
                self.store.event("transient", {"type": "anr", "window": obs.focus.window, "action": "wait" if hits else "back"})
                if hits:
                    self.anr_waits += 1
                    x, y = hits[0].center
                    self.dev.tap(x, y, "transient")
                else:
                    self.dev.back("transient")
                obs = self.observe("transient")
                continue
            self.anr_waits = 0
            if obs.focus.kind == "ime":
                self.counters["transients"] += 1
                self.store.event("transient", {"type": "ime"})
                self.dev.back("transient")
                obs = self.observe("transient")
                continue
            break
        if popups and obs is not None and self.popup_bridge is not None:
            # Reuse the observation already needed by navigation. Normal pages
            # do not incur a screenshot, dump or model request here.
            return self.resolve_popups(obs, phase="navigation")
        return obs

    @staticmethod
    def is_permission_prompt(obs: Obs) -> bool:
        owner = obs.focus.package
        return (owner.endswith(".permissioncontroller") or owner == "com.android.packageinstaller") and any(
            n.short_rid.startswith("permission_") for n in obs.nodes if not n.covered)

    @staticmethod
    def is_location_prompt(obs: Obs) -> bool:
        return any(LOCATION_WORDS.search(n.text) for n in obs.nodes if not n.covered and n.text)

    def allow_permission(self, obs: Obs) -> Obs | None:
        """Test devices: a system permission prompt is answered by the executor, not the model. Location is denied
        unless the profile grants it (grant_location), because granting it can make an app relocate and change
        business data (the current city). grant_permissions: false leaves every prompt to the model."""
        if not self.profile.get("grant_permissions", True):
            return None
        if self.is_location_prompt(obs) and not self.profile.get("grant_location", False):
            buttons = ("permission_deny_and_dont_ask_again_button", "permission_deny_button")
        else:
            buttons = ("permission_allow_foreground_only_button", "permission_allow_button",
                       "permission_allow_one_time_button")
        for rid in buttons:
            hits = [n for n in obs.nodes if not n.covered and n.short_rid == rid and n.enabled]
            if hits:
                x, y = hits[0].center
                self.dev.tap(x, y, "permission")
                what = "permissions_denied" if "deny" in rid else "permissions_allowed"
                self.counters[what] = self.counters.get(what, 0) + 1
                self.store.event(what[:-1], {"button": rid, "window": obs.focus.window})
                return self.observe("permission")
        return None

    def popup_visible(self, obs: Obs) -> bool:
        if not obs.in_app and not self.is_permission_prompt(obs):
            return False  # another app or the launcher: the recovery ladder relaunches, no model round trip
        if obs.in_app and ui.loading(obs.nodes, self.pkg):
            return False  # existing bounded loading wait is cheaper than model handoff
        if obs.focus.kind in ("popup", "dialog") or obs.overlay or ui.layered(obs.nodes):
            return True
        # Android permissions use a separate Activity, rather than a dialog
        # window owned by the app. Do not treat arbitrary external pages as UI prompts.
        owner = obs.focus.package
        return (owner.endswith(".permissioncontroller") or owner == "com.android.packageinstaller") and any(
            n.short_rid.startswith("permission_") for n in obs.nodes if not n.covered)

    def own_tap(self) -> bool:
        """The screen is the direct result of a tap this executor made (not the model's, not a permission answer)."""
        op, purpose = getattr(self.dev, "last_input", ("", "")) or ("", "")
        return op == "tap" and purpose not in ("model_popup", "permission")

    def resolve_popups(self, obs: Obs, *, phase: str, force: bool = False) -> Obs:
        """Popups by cause. A layer opened by the executor's own tap (date panel, filter panel, confirm box, wheel)
        is a state of the app under test: captured, explored and closed by the normal rules, which never tap a
        confirm button; so is a layer already registered as a page. Only unknown layers that appear on their own
        (ads, ratings, update prompts, startup blockers) go to the model; system permission prompts are the
        executor's. One failed model action is asked again with the
        failure, in the same process."""
        if self.popup_bridge is None:
            return obs
        retried, failure = False, None
        for _ in range(4):
            if self.is_permission_prompt(obs):
                allowed = self.allow_permission(obs)
                if allowed is not None:
                    obs = allowed
                    continue
            elif not obs.in_app:
                return obs  # left the app (launcher, file picker): handled by recovery, never by the model
            before = screen_fingerprint(obs)
            if before in self._popup_passthrough:
                return obs
            if not force and not self.popup_visible(obs):
                return obs
            # Explicit startup recipes are already model-approved; leave those
            # to cold_start, which validates their when selector before acting.
            if phase == "startup" and self.recipe_rule(obs) is not None:
                return obs
            if (phase == "navigation" and not force and not self.is_permission_prompt(obs)
                    and (self.own_tap() or self.match(obs) is not None)):
                return obs  # opened by our own tap, or a layer already registered as a page: not the model's
            context = {"root_selector": self.profile.get("root"),
                       "stack": list(self.state.get("stack", [])),
                       "trigger": self.last_action[1] if self.last_action else None}
            if failure:
                context["previous_failure"] = failure
            try:
                self.cur = self.popup_bridge.handle(obs, self.state, phase=phase,
                                                    observe=self.observe, save=self.save, context=context)
            except PopupStop as stop:
                if retried or not stop.reason.startswith(("model_action_failed", "postcondition")):
                    raise
                retried, failure = True, stop.reason
                self.store.event("model_retry", {"reason": stop.reason})
                self.state["status"] = "running"
                obs = self.observe("model_retry")
                if obs is None:
                    raise
                continue
            if self.cur is None:
                raise PopupStop("paused_model", "popup handling produced no fresh observation")
            obs = self.cur
            if screen_fingerprint(obs) == before:
                # A successful continue decision explicitly delegates this
                # business dialog to normal capture/exploration. Never infer
                # that it has disappeared or that a candidate was explored.
                if self.state.get("popup_last_result", {}).get("status") == "continued":
                    self._popup_passthrough.add(before)
                    return obs
                # Business baseline/context can change even when the pixels
                # and hierarchy did not. A stale decision is not permission to
                # traverse that dialog, including a forced startup blocker.
                continue
            force = False
        if not force and not self.popup_visible(obs):
            return obs
        raise PopupStop("paused_model", "popup chain exceeded four transitions; checkpoint preserved")

    # ------------------------------------------------------------------ identity
    def layer_key(self, obs: Obs) -> str:
        if obs.overlay:
            return "win:" + obs.overlay
        return "layer" if ui.layered(obs.nodes) else ""

    def texts(self, nodes: list) -> set:
        """Visible text items, ignoring numeric/time values and relative times that refresh on their own."""
        return {t for t in ui.text_fingerprint(nodes, self.pkg)
                if not DYNAMIC_TEXT.match(t[1]) and not RELATIVE_TIME.search(t[1])}

    def text_pool(self, page: dict) -> set:
        pool = set(map(tuple, page["base_texts"]))
        for v in page["views"]:
            pool |= set(map(tuple, v["texts"]))
        return pool

    def match(self, obs: Obs | None) -> str | None:
        """Page whose structure contains the screen and resembles one captured viewport.

        Pages that share one layout (sibling sub-pages, same-activity instances) are told apart by
        how much of the visible text each page has shown before.
        """
        if obs is None or not obs.in_app:
            return None
        lk = self.layer_key(obs)
        s = obs.structure(self.pkg)
        obs_texts = None
        best, score = None, -1.0
        for key in self.state["order"]:
            p = self.pages[key]
            if p["activity"] != obs.activity or p["layer"] != lk:
                continue
            if ui.containment(s, frozenset(p["structure"])) < self.lim["match_threshold"]:
                continue
            sim = max((ui.jaccard(s, frozenset(f)) for f in p["frame_structs"]), default=0.0)
            if sim < 0.5:
                continue
            if obs_texts is None:
                obs_texts = self.texts(obs.nodes)
            overlap = (len(obs_texts & self.text_pool(p)) / len(obs_texts)) if obs_texts else 0.0
            sc = sim + 0.5 * overlap
            if sc > score:
                best, score = key, sc
        return best

    @staticmethod
    def norm(t) -> tuple:
        """Digits become '#': AQI 71 -> 70 or another date is a parameter change, not new content."""
        return (t[0], DIGITS.sub("#", t[1]))

    def novel(self, page: dict, obs: Obs, cand: dict | None) -> set:
        """Texts on screen that no captured frame of this page has shown: the mark of a new view state.

        Scrolling only reveals texts some frame already captured; texts of rids known to refresh on their
        own (banners, tickers) are ignored.
        """
        known = {self.norm(t) for t in map(tuple, page["base_texts"])}
        volatile = set(page.get("volatile", []))
        label = DIGITS.sub("#", ((cand or {}).get("label") or "").strip())
        return {n for n in (self.norm(t) for t in self.texts(obs.nodes))
                if n not in known and n[1] != label and not (n[0] and n[0] in volatile)}

    def failure(self, why: str) -> None:
        self.state["failures"] += 1
        self.store.event("failure", {"why": why, "consecutive": self.state["failures"]})
        if self.state["failures"] >= self.lim["breaker"]:
            raise Halt("halted_breaker", f"{self.state['failures']} consecutive unrecovered failures; last: {why}")

    def success(self) -> None:
        self.state["failures"] = 0

    # ------------------------------------------------------------------ start / navigation
    def recipe_rule(self, obs: Obs) -> dict | None:
        for rule in self.profile["start_recipe"]:
            if ui.select(obs.nodes, rule["when"], self.pkg if obs.in_app else None):
                return rule
        return None

    def apply_rule(self, obs: Obs, rule: dict) -> None:
        self.store.event("start_recipe", {"rule": rule})
        if "tap" in rule:
            hits = ui.select(obs.nodes, rule["tap"])
            want = rule["tap"].get("text")
            if not hits and want:
                # The profile said 北京, the screen says 北京市: accept one unambiguous containing text.
                loose = [n for n in obs.nodes if not n.covered and want in n.text.strip()]
                if len({n.text.strip() for n in loose}) == 1:  # one text, maybe shown twice (定位 + 热门)
                    hits = loose
                    self.store.event("start_recipe_loose", {"want": want, "got": loose[0].text})
            if hits:
                x, y = ui.tap_point(obs.nodes, hits[0])
                self.dev.tap(x, y, "start")
        if rule.get("back"):
            self.dev.back("start")
        if rule.get("wait"):
            self.dev.pause(float(rule["wait"]), "start")

    def root_visible(self, obs: Obs) -> bool:
        sel = self.profile.get("root")
        return bool(ui.select(obs.nodes, sel, self.pkg)) if sel else True

    def cold_start(self, first: bool = False) -> Obs | None:
        self.counters["restarts"] += 0 if first else 1
        self.store.event("cold_start", {"first": first})
        self.dev.force_stop("restart")
        self.dev.pause(0.3, "restart")
        self.dev.start(self.state["launcher"], "restart")
        prev, noop, escaped = None, 0, False
        stuck, last_rule, last_sig = {}, None, None
        blocked_sig = None
        relaunches = 0
        for _ in range(16):
            # Startup rules have priority over generic popup handling.
            raw = self.observe("start")
            if raw is not None and not raw.in_app and not self.is_permission_prompt(raw) and relaunches < 2:
                # The start intent did not bring the app up (launcher, another app in front): start it again.
                relaunches += 1
                self.store.event("relaunch", {"focus": raw.focus.window})
                self.dev.start(self.state["launcher"], "restart")
                continue
            if raw is not None and self.popup_bridge is not None and self.recipe_rule(raw) is None:
                raw = self.resolve_popups(raw, phase="startup")
            obs = self.settle(raw, popups=False)
            if obs is None:
                self.dev.pause(1.0, "restart")
                continue
            known = None if first else self.match(obs)
            if known is not None and (known == self.state["root"] or noop >= 2):
                # Root, or another known page (apps that reopen the last tab): the ladder navigates from it.
                self.edge("restart", None, None, self.state["root"], landed=known)
                return obs
            rule = self.recipe_rule(obs)
            sig_now = (obs.activity, obs.structure(self.pkg), frozenset(self.texts(obs.nodes)))
            if rule and stuck.get(id(rule), 0) < 2:
                if last_rule is rule and last_sig == sig_now:
                    stuck[id(rule)] = stuck.get(id(rule), 0) + 1  # the tap changed nothing
                last_rule, last_sig = rule, sig_now
                self.apply_rule(obs, rule)
                prev, noop = None, 0
                continue
            if rule:
                self.store.event("start_recipe_stuck", {"rule": rule})
            if (self.popup_bridge is not None and not self.root_visible(obs) and known is None
                    and not ui.loading(obs.nodes, self.pkg)):
                fingerprint = screen_fingerprint(obs)
                # A stable full-screen interstitial may not expose a Dialog
                # window (e.g. onboarding). Ask once after two observations,
                # rather than spending all 16 root-recovery attempts on it.
                if fingerprint == blocked_sig:
                    obs = self.resolve_popups(obs, phase="startup_blocked", force=True)
                    if not self.root_visible(obs) and screen_fingerprint(obs) == fingerprint:
                        raise PopupStop("paused_model", "startup blocker remains; root not confirmed")
                    prev, noop, blocked_sig = None, 0, None
                    continue
                blocked_sig = fingerprint
            else:
                blocked_sig = None
            if first and obs.in_app and self.root_visible(obs):
                sig = (obs.activity, obs.structure(self.pkg))
                if sig == prev:
                    return obs
                prev = sig
            elif not first and obs.in_app and known is None and not escaped and noop >= 1:
                escaped = True
                home = self.go_home(obs)  # a sibling tab the app reopened: its tab bar leads home
                if home is not None:
                    self.edge("restart", None, None, self.state["root"], landed=self.state["root"])
                    return home
                self.dev.back("restart")  # an unknown interstitial (what's new, promo): one BACK, then look again
                continue
            noop += 1
            if not first and noop >= 4:
                break
            self.dev.pause(1.0, "restart")
        self.edge("restart", None, None, self.state["root"], landed=None, result="fail")
        return None

    def path_of(self, key: str) -> list:
        return self.pages[key]["path"]

    def is_on_path(self, anc: str, target: str) -> bool:
        if anc == target:
            return True
        return anc == self.state["root"] or any(step["src"] == anc for step in self.path_of(target))

    def tap_step(self, src: str, cand: dict, obs: Obs, purpose: str) -> Obs | None:
        why = self.blocked(src, cand)
        if why:  # a recorded path or route through a control that is denied now is not walked again
            self._blocked_reason = why
            self.store.event("path_blocked", {"page": self.pages[src]["page_id"], "control": cand.get("label")
                                              or cand.get("key"), "reason": why, "purpose": purpose})
            return None
        node, obs = self.locate(self.pages[src], cand, obs, purpose=purpose + "_locate", loose=True)
        if node is None:
            return None
        x, y = ui.tap_point(obs.nodes, node)
        self.note_suspect(self.pages[src], cand)  # a replayed tap can change data as well as a new one
        self.dev.tap(x, y, purpose)
        return self.settle(self.observe(purpose))

    def replay(self, src: str, target: str, obs: Obs) -> Obs | None:
        steps = self.path_of(target)
        start = next((i for i, s in enumerate(steps) if s["src"] == src), None)
        if start is None:
            return None
        self.counters["replays"] += 1
        for step in steps[start:]:
            why = self.blocked(step["src"], step["cand"])
            if why:
                # The recorded path goes through a control denied now: try another recorded route.
                self._blocked_reason = why
                self.store.event("path_blocked", {"page": self.pages[step["src"]]["page_id"], "reason": why,
                                                  "control": step["cand"].get("label") or step["cand"].get("key"),
                                                  "purpose": "replay", "target": self.pages[target]["page_id"]})
                return self.navigate(step["src"], {target}, obs)
            got_obs = self.tap_step(step["src"], step["cand"], obs, "replay")
            self.counters["replay_steps"] += 1
            got = self.match(got_obs)
            ok = got == step["dst"]
            self.edge("replay", step["src"], step["cand"], step["dst"], result="ok" if ok else "mismatch", landed=got)
            if not ok:
                return None
            obs = got_obs
        return obs

    def graph(self) -> dict:
        """Navigation edges observed so far: src page -> [(control, dst page)]."""
        g: dict = {}
        for dk, rec in self.state["explored"].items():
            c = rec["cand"]
            bad = set(self.state.get("bad_edges", []))
            # Navigate only through structural controls: data items (list rows, repeated keywords) and
            # controls with side effects make poor, sometimes harmful, routes.
            if (c.get("group") or c.get("family_size", 0) >= COMMIT_FAMILY_MIN
                    or self.auto_denied(dk.split("|", 1)[0], c)
                    or any(src in self.pages and self.blocked(src, c) for src in rec["pages"])):
                continue  # list rows / large data families / side effects; tab bars and menus stay usable
            for src, r in rec["pages"].items():
                if f"{src}|{c['key']}" in bad:
                    continue
                if r["result"] in NAV_RESULTS and r.get("to") and r["to"] != src:
                    g.setdefault(src, []).append((rec["cand"], r["to"]))
        return g

    def go_home(self, obs: Obs) -> Obs | None:
        """From another screen of the root activity (a sibling tab), tap a control that keeps the root on
        the root (its own tab): such 'self' controls usually lead back to the root from its siblings."""
        root = self.state.get("root")
        if not root or obs is None or not obs.in_app or obs.activity != self.pages[root]["activity"]:
            return None
        rp = self.pages[root]
        for cand in rp["cands"]:
            rec = self.state["explored"].get(self.dkey(rp, cand))
            if not rec or rec["pages"].get(root, {}).get("result") != "self":
                continue
            node = ui.locate_loose(obs.nodes, self.pkg, cand_obj(cand))
            if node is None:
                continue
            x, y = ui.tap_point(obs.nodes, node)
            self.dev.tap(x, y, "go_home")
            got = self.settle(self.observe("go_home"))
            ok = self.match(got) == root
            self.edge("go_home", None, cand, root, result="ok" if ok else "mismatch", landed=self.match(got))
            if ok:
                return got
            obs = got
            if obs is None or not obs.in_app:
                return None
        return None

    def navigate(self, src: str, goals: set, obs: Obs) -> Obs | None:
        """Walk recorded edges from a known page to any goal page (used when not on the target's path)."""
        g = self.graph()
        prev = {src: None}
        queue = deque([src])
        hit = None
        while queue:
            k = queue.popleft()
            if k in goals:
                hit = k
                break
            for cand, dst in g.get(k, []):
                if dst not in prev:
                    prev[dst] = (k, cand)
                    queue.append(dst)
        if hit is None or hit == src:
            return None
        steps = []
        k = hit
        while prev[k] is not None:
            p, cand = prev[k]
            steps.append((p, cand, k))
            k = p
        for p, cand, dst in reversed(steps):
            obs = self.tap_step(p, cand, obs, "navigate")
            got = self.match(obs)
            self.edge("navigate", p, cand, dst, result="ok" if got == dst else "mismatch", landed=got)
            if got != dst:
                # Do not walk this edge again in this run: it already led somewhere else once.
                self.state.setdefault("bad_edges", []).append(f"{p}|{cand['key']}")
                return None
        return obs

    def ensure_at(self, key: str, obs: Obs | None = None) -> Obs | None:
        """Make sure the device shows page `key`, using the recovery ladder; None when unreachable."""
        self._blocked_reason = ""
        tried_back, restarted, navigated, pending_back = False, False, False, False
        last, back_from = None, None
        for _ in range(10):
            if obs is None:
                obs = self.settle(self.observe("verify"))
            last = obs or last
            m = self.match(obs) if obs is not None else None
            if pending_back:
                self.edge("return", back_from, None, key, method="recover_back", landed=m)
                pending_back = False
            if obs is None:
                if restarted:
                    break
                restarted = True
                obs = self.cold_start()
                continue
            if m == key:
                self.success()
                return obs
            if m is not None and self.is_on_path(m, key):
                got = self.replay(m, key, obs)
                if got is not None:
                    self.success()
                    return got
                obs = None
                if not restarted:
                    restarted = True
                    obs = self.cold_start()
                    continue
                break
            if m is not None and not navigated:
                navigated = True
                goals = {s["src"] for s in self.path_of(key)} | {key, self.state["root"]}
                got = self.navigate(m, goals, obs)
                obs = got  # None -> fresh observation next round
                continue
            if not navigated or m is None:
                navigated = True
                home = self.go_home(obs)
                if home is not None:
                    obs = home
                    continue
            if not tried_back:
                tried_back = True
                back_from = m  # page (or None: unknown/outside) the BACK is pressed on
                self.dev.back("recover")
                pending_back = True
                obs = None
                continue
            if not restarted:
                restarted = True
                obs = self.cold_start()
                continue
            break
        page = self.pages[key]
        if page["status"] != "unreachable":
            page["status"] = "unreachable"
            if self._blocked_reason:
                # Every known way there goes through a control denied now: retrying cannot help.
                page["blocked_by"] = self._blocked_reason
                self.gap("path_denied", key, page_id=page["page_id"], reason=self._blocked_reason)
            else:
                self.gap("unreachable", key, obs=last, page_id=page["page_id"])
        self.cur = None
        self.failure(f"cannot reach {key}")
        return None

    # ------------------------------------------------------------------ locating
    def locate(self, page: dict, cand: dict, obs: Obs | None, purpose: str = "locate_scroll", loose: bool = False):
        """Return (node, obs) where node is visible in obs; (None, obs) when not found.

        loose=True (replay / navigation) also accepts the single node with the same rid and class, since
        controls whose label carries data (a date) change between visits.
        """
        if obs is None:
            return None, None
        c = cand_obj(cand)
        find = (lambda nodes: ui.locate_loose(nodes, self.pkg, c)) if loose else (lambda nodes: ui.locate(nodes, self.pkg, c))
        node = find(obs.nodes)
        if node is not None:
            return node, obs
        cont = page.get("container")
        if not cont:
            return None, obs
        live = ui.find_container(obs.nodes, self.pkg, cont["key"])
        if live is None:
            return None, obs
        here = self.viewport_of(page, obs)
        if here is not None:
            page["viewport"] = here
        target = c.first_frame if c.first_frame >= 0 else c.frame
        jump = target - page.get("viewport", 0)

        def continuing(before, nxt, container):
            if nxt is None:
                self.gap("scroll_interrupted", page["page_id"], purpose=purpose, stop="dump_failed")
                return None
            current, issue = cap.scroll_continuity(before, nxt, self.pkg, container)
            if issue:
                self.cur = None
                self.gap("scroll_interrupted", page["page_id"], obs=nxt, purpose=purpose,
                         stop=issue["stop"], interruption=issue)
            return current

        if here is not None and jump > 1:
            # Swipe straight to the recorded viewport, one dump.
            for _ in range(jump):
                cap.swipe_forward(self.dev, live.bounds, "vertical", purpose)
            nxt = self.observe(purpose)
            live = continuing(obs, nxt, live)
            if live is None:
                return None, None
            obs = nxt
            node = find(obs.nodes)
            if node is not None:
                page["viewport"] = target
                return node, obs
            here = self.viewport_of(page, obs)
            page["viewport"] = here if here is not None else target
        forward = c.frame > page.get("viewport", 0)
        flipped = False
        for _ in range(4):  # bounded: a control that is gone costs a few swipes, not a full sweep both ways
            before = cap._node_set(obs.nodes, self.pkg, live.bounds)
            (cap.swipe_forward if forward else cap.swipe_backward)(self.dev, live.bounds, "vertical", purpose)
            nxt = self.observe(purpose)
            live = continuing(obs, nxt, live)
            if live is None:
                return None, None
            obs = nxt
            node = find(obs.nodes)
            if node is not None:
                page["viewport"] = c.frame
                return node, obs
            if cap._node_set(obs.nodes, self.pkg, live.bounds) == before:  # hit an end
                if flipped:
                    return None, obs
                forward, flipped = not forward, True
        return None, obs

    def viewport_of(self, page: dict, obs: Obs) -> int | None:
        """Which captured viewport of the page the screen shows (best text overlap), if clear."""
        frames = page.get("frame_texts") or []
        if len(frames) < 2:
            return None
        cur = {t for t in self.texts(obs.nodes)}
        if not cur:
            return None
        scores = [len(cur & set(map(tuple, f))) / max(1, len(cur)) for f in frames]
        best = max(range(len(scores)), key=lambda i: scores[i])
        return best if scores[best] >= 0.6 else None

    # ------------------------------------------------------------------ registration / capture
    def collect_cands(self, frames: list, activity: str) -> list:
        merged: dict = {}
        for f in frames:
            for c in ui.candidates(f.nodes, self.pkg, f.index, activity=activity, deny=self.profile["deny"],
                                   allow=self.profile["allow"], extra_danger=self.profile["extra_danger_words"]):
                if c.key in merged:
                    c.first_frame = merged[c.key].first_frame
                merged[c.key] = c  # later frames win: their viewport is closer to where we stand
        width, height = ui.screen_size(frames[0].nodes)
        last = len(frames) - 1

        def chrome(c) -> bool:
            # Fixed bars (toolbar, bottom tabs): seen in every viewport, or hugging the top/bottom edge.
            # Explored last, so a tab that jumps to another page does not force a replay back.
            seen_everywhere = last > 0 and c.first_frame == 0 and c.frame == last
            return seen_everywhere or c.bounds[1] >= height * 0.88 or c.bounds[3] <= height * 0.10

        ordered = sorted(merged.values(), key=lambda c: (chrome(c), -c.frame))
        out = []
        for c in ordered:
            d = cand_dict(c)
            d["chrome"] = chrome(c)
            out.append(d)
        # Families: list rows (adapter children) or a resource-id repeated 3+ times (keyword chips, day cells).
        reps = Counter((d["resource-id"], d["class"]) for d in out if d["resource-id"])
        sibs = Counter(d["sib"] for d in out if d.get("sib"))
        for d in out:
            d["rid_count"] = reps[(d["resource-id"], d["class"])] if d["resource-id"] else 0
            d["family"] = d.get("group") or (f"rid:{d['class'].rsplit('.', 1)[-1]}|{d['resource-id'].rsplit('/', 1)[-1]}"
                                             if d["resource-id"] and reps[(d["resource-id"], d["class"])] >= 3 else "")
            if not d["family"] and d.get("sib") and sibs[d["sib"]] >= 3:
                d["family"] = "sib:" + d["sib"]  # repeated cells without ids (hourly forecast items)
        sizes = Counter(d["family"] for d in out if d["family"])
        for d in out:
            d["family_size"] = sizes.get(d["family"], 0)
        return out

    def label_for(self, activity: str, via: dict | None, parent: dict | None, view: bool = False) -> str:
        if via is None:
            return activity
        via_label = via.get("label") or via.get("content-desc") or via.get("resource-id", "").rsplit("/", 1)[-1]
        if view and parent is not None:
            return f"{parent['label']}·{via_label}"
        return f"{activity}·{via_label}" if via_label else activity

    def mark_progress(self) -> None:
        self._progress = (self.clock(), self.state.get("popup_stats", {}).get("wait_s", 0.0))

    def stalled(self) -> bool:
        """No new unit for stall_minutes of executor time (time spent waiting for the model does not count)."""
        limit = self.lim.get("stall_minutes", 0)
        if not limit:
            return False
        if getattr(self, "_progress", None) is None:
            self.mark_progress()
        t0, wait0 = self._progress
        waited = self.state.get("popup_stats", {}).get("wait_s", 0.0) - wait0
        return (self.clock() - t0 - waited) / 60 >= limit

    def write_page(self, frames: list, res, obs: Obs, *, kind: str, label: str, parent_key: str | None,
                   via: dict | None, path: list, cands: list) -> str:
        self.mark_progress()
        drift = dict(self.state["drift"]) if self.state.get("drift") else None
        click_path = []
        for step in path:
            c = step["cand"]
            b = ui.parse_bounds(c["bounds"])
            src = self.pages.get(step["src"], {})
            click_path.append({"from": src.get("label", step["src"]), "element": c["label"] or c["resource-id"],
                               "center": [(b[0] + b[2]) // 2, (b[1] + b[3]) // 2], "resource-id": c["resource-id"],
                               "text": c["text"], "content-desc": c["content-desc"], "long-clickable": False,
                               "scroll_info": ({"scroll_index": c["scroll_index"],
                                                "container_bounds": (src.get("container") or {}).get("bounds")}
                                               if c["scroll_index"] else None)})
        via_meta = {k: v for k, v in via.items() if k != "view_via"} if via else None
        meta = {
            "label": label, "timestamp": now_iso(),
            "device": "adb", "dpi": self.state.get("density"),
            "density_factor": (self.state["density"] / 160) if self.state.get("density") else None,
            "activity_info": {"current_focus": f"mCurrentFocus=Window{{ {obs.focus.window} }}",
                              "resumed_activity": obs.focus.focused_app or obs.focus.window},
            "clickable_count": len(cands),
            "clickable_elements": [{k: v for k, v in c.items() if k != "view_via"} for c in cands],
            "scroll_container_bounds": res.container["bounds"] if res and res.container else None,
            "click_path": click_path,
            "came_from": click_path[-1]["from"] if click_path else None,
            "trigger_element": click_path[-1]["element"] if click_path else None,
            "aft": {"kind": kind, "parent": self.pages[parent_key]["page_id"] if parent_key else None,
                    "activity": obs.activity, "layer": self.layer_key(obs),
                    "capture": {"frames": len(frames), "stop": res.stop if res else "single",
                                "proof_degraded": bool(res and res.degraded),
                                "container": res.container if res else None,
                                "extra": res.extra if res else [],
                                "proofs": [f.proof for f in frames[1:]],
                                "observations": cap.frame_observations(frames),
                                "last_observation": cap.observation_identity(res.last_obs) if res else None,
                                "interruption": res.interruption if res else None},
                    "readings": ui.read_readings([f.nodes for f in frames], self.profile["business_readings"],
                                                 self.pkg, obs.activity),
                    "drift": drift, "via": via_meta},
        }
        meta["aft"]["capture"]["scope"] = res.scope if res else {}
        saved = registry.save_capture(self.store, self.state, frames, meta, package=self.pkg)
        page_id = saved["page_id"]
        if page_id in self.profile["names"]:
            saved["label"] = self.profile["names"][page_id]
            self.store.write_meta(page_id, saved)
            self.state["index"] = [{k: v for k, v in saved.items() if k != "clickable_elements"}
                                   if r["page_id"] == page_id else r for r in self.state["index"]]
            self.store.write_index(self.state["index"])
        self.counters["captures"] += 1
        self.counters["frames"] += len(frames)
        if res and res.degraded:
            self.gap("proof_degraded", page_id, stop=res.stop)
        if res and res.stop in cap.TRUNCATED_STOPS:
            self.gap("capture_truncated", page_id, obs=res.last_obs, stop=res.stop,
                     interruption=res.interruption)
        return page_id

    def capture(self, obs: Obs, scroll: bool = True):
        extra = [c for c in self.profile["extra_containers"]
                 if not c.get("activity") or obs.activity.endswith(c["activity"])] if scroll else []
        # Read-only horizontal strips are scrolled once per activity and run, on the first page that shows them.
        done = self.state.setdefault("auto_strips", [])
        skip = {k.split("|", 1)[1] for k in done if k.split("|", 1)[0] == obs.activity}
        res = cap.capture_page(self.dev, self.pkg, obs, self.lim["max_scrolls"] if scroll else 0, extra,
                               on_event=self.store.event, auto_horizontal=self.lim["max_hscrolls"] if scroll else 0,
                               skip_auto=skip)
        done.extend(f"{obs.activity}|{k}" for k in res.auto_keys)
        if res.stop in cap.UNSAFE_CURSOR_STOPS:
            self.cur = None  # the app left the page during the capture: look again before doing anything
            return res
        # Includes the final bottom/no-new-content dump, which need not have a saved PNG.
        self.cur = res.last_obs
        return res

    def register_page(self, obs: Obs, parent_key: str | None, via: dict | None, kind: str = "page") -> str:
        res = self.capture(obs)
        frames = res.frames
        own = res.page_frames  # viewports of the page itself: auto-scrolled strips hold no controls to tap
        parent = self.pages.get(parent_key) if parent_key else None
        cands = [] if kind == "danger_dialog" else self.collect_cands(own, obs.activity)
        path = []
        if parent:
            path = list(parent["path"])
            if via and via.get("view_via"):  # the control only exists in a view state: switch to it first
                path.append({"src": parent_key, "cand": via["view_via"], "dst": parent_key})
            path.append({"src": parent_key, "cand": via, "dst": None})
        key = f"P{len(self.state['order']) + 1}"
        if path:
            path[-1]["dst"] = key
        label = self.label_for(obs.activity, via, parent)
        page_id = self.write_page(frames, res, obs, kind=kind, label=label, parent_key=parent_key, via=via,
                                  path=path, cands=cands)
        frame_structs = [sorted(obs.structure(self.pkg))] + [sorted(ui.structure(f.nodes, self.pkg)) for f in frames[1:]]
        structure = set().union(*map(set, frame_structs))
        same_layout = bool(parent and parent["activity"] == obs.activity and parent["layer"] == self.layer_key(obs)
                           and ui.containment(frozenset(structure), frozenset(parent["structure"])) >= self.lim["match_threshold"])
        self.pages[key] = {
            "key": key, "page_id": page_id, "label": label, "activity": obs.activity, "layer": self.layer_key(obs),
            "structure": sorted(structure), "frame_structs": frame_structs,
            "base_texts": sorted(set().union(*(self.texts(f.nodes) for f in frames))),
            "frame_texts": [sorted(self.texts(f.nodes)) for f in own],
            "parent": parent_key, "depth": (parent["depth"] + 1) if parent else 0, "path": path,
            "status": "leaf" if kind == "danger_dialog" else "open", "kind": kind,
            "cands": cands, "next": 0, "container": res.container, "viewport": len(own) - 1,
            "views": [], "list_results": {}, "explored": 0, "volatile": [], "active_view": None, "instances": [],
            "base_selection": sorted([list(x) for x in ui.selection(obs.nodes, self.pkg)]),
            "same_layout_depth": ((parent.get("same_layout_depth", 0) + 1) if same_layout else 0),
            "token": obs.focus.token if obs.focus.kind == "activity" else "",
        }
        self.state["order"].append(key)
        self.bind_readings(key, frames, obs.activity)
        self.counters["dialogs" if kind == "danger_dialog" else "pages"] += 1
        self.log(f"  + {page_id}  {label}  frames={len(frames)} cands={len(cands)}")
        return key

    # ------------------------------------------------------------------ policy
    def dkey(self, page: dict, cand: dict) -> str:
        return f"{page['activity']}|{page['layer']}|{cand['key']}"

    def allowed(self, page: dict, cand: dict) -> bool:
        return any(ui.rule_hits(r, page["activity"], cand_obj(cand)) for r in self.profile["allow"])

    def skip_reason(self, page: dict, cand: dict) -> str:
        allowed = self.allowed(page, cand)
        if cand.get("nav_back") and not allowed:
            return "nav_back"
        if not allowed and self.auto_denied(page["activity"], cand):
            return "denied:side_effect"
        if cand.get("danger") and not allowed:
            return "danger:" + cand["danger"]
        if cand.get("denied") and not allowed:
            return "denied:" + cand["denied"]
        if not allowed and self.denied_now(page["activity"], cand):
            return "denied:" + self.denied_now(page["activity"], cand)
        if (self.profile.get("skip_confirm_in_overlay", True) and not allowed and
                (cand.get("commit") or ui.is_confirm_label(cand["label"] or ""))):
            # Commit-style buttons (确定 / 完成 / 保存, a dialog's answers, a form's 登录) are never tapped
            # automatically, on any page.
            reason = "confirm_in_overlay" if page["layer"] else "confirm"
            return f"{reason}:{cand['commit']}" if cand.get("commit") else reason
        rec = self.state["explored"].get(self.dkey(page, cand))
        if rec:
            if page["key"] in rec["pages"]:
                return "dedup"
            results = list(rec["pages"].values())
            if any(r["result"] == "external" for r in results):
                return "dedup"
            # A control counts as global (bottom tab, toolbar entry) only after two pages saw it go to the
            # same place; a same-labelled control that went somewhere else keeps being explored per page.
            nav = [r for r in results if r["result"] in NAV_RESULTS]
            if len(nav) >= 2 and len({r["to"] for r in nav}) == 1 and len(nav) == len(results):
                return "dedup"
        fam = cand.get("family") or cand.get("group")
        if not fam and cand.get("rid_count") == 1:
            done = page.get("rid_done", {}).get(f"{cand['resource-id']}|{cand['class']}")
            if done in NAV_RESULTS + ("self",):
                return "dedup"  # same one-off control, its label only shows other data (another day's 宜忌)
        if fam and allowed:
            pass  # the reviewer asked for this item: never sampled away again
        elif fam:
            sigs = page["list_results"].get(fam, [])
            known = self.state.setdefault("families", {}).get(fam)
            # A family already shown homogeneous elsewhere needs only one sentinel item here.
            if known and sigs and all(x == known["sig"] for x in sigs):
                return "list_sample"
            # Otherwise sample once N items in a row landed on the same kind of place.
            if self.settled_family(sigs):
                return "list_sample"
        if page["explored"] >= self.lim["max_candidates_per_page"]:
            return "page_cap"
        return ""

    def back_on_instance(self, key: str | None, obs: Obs | None) -> bool:
        """The screen is page `key` in the very window it was registered in. A tap that opens a new instance of an
        ancestor's Activity is not a return to it (it would be read as a pick-and-return when it matches an ancestor
        page). Unknown tokens (older checkpoints) count as a match."""
        if key not in self.pages or obs is None:
            return False
        want = self.pages[key].get("token", "")
        return not want or not obs.focus.token or obs.focus.token == want

    def note_explored(self, page: dict, cand: dict, result: str, to: str | None = None) -> None:
        rec = self.state["explored"].setdefault(self.dkey(page, cand), {"pages": {}, "cand": cand})
        rec["pages"][page["key"]] = {"result": result, "to": to}
        dest = self.pages.get(to) if to else None
        if (result == "up" and dest is not None and (page["layer"] or dest["activity"] != page["activity"])
                and self.back_on_instance(to, self.cur)):
            # The tap closed the screen it was on (its Activity finished, or its layer went away) and the app went
            # back: the pick-and-commit pattern. A tab switch back to an ancestor page does not count.
            for s in reversed(self.state.get("read_suspects") or []):
                if s.get("key") == cand.get("key") and s["page_id"] == page["page_id"]:
                    s["closed_own_page"] = True
                    break
        page["explored"] = page.get("explored", 0) + 1
        fam = cand.get("family") or cand.get("group")
        if not fam and cand.get("resource-id"):
            page.setdefault("rid_done", {})[f"{cand['resource-id']}|{cand['class']}"] = result
        if not fam:
            return
        if result == "capture_failed":
            # An attempted action is not evidence of a homogeneous destination.
            # Break the local consecutive sample without erasing proof from other pages.
            page["list_results"].pop(fam, None)
            return
        size = cand.get("family_size", 0)
        if result in NAV_RESULTS:
            sig = to
        elif result == "view":
            # Small families (tabs, categories) are modes: every view counts. Large ones select data.
            sig = "view" if size >= PARAM_FAMILY_MIN else f"view:{to}"
        else:
            sig = result
        commit_like = result == "up" and size >= COMMIT_FAMILY_MIN
        if commit_like:
            sig = f"up:{to}"
        sigs = page["list_results"].setdefault(fam, [])
        sigs.append(sig)
        fams = self.state.setdefault("families", {})
        gkey = fam
        if gkey not in fams and (commit_like or self.settled_family(sigs)):
            fams[gkey] = {"sig": sig, "page": page["page_id"], "label": cand.get("label"), "commit_like": commit_like}
            if commit_like:
                # Picking a row returned to the caller (choose a city, an option): likely a commit. One is enough.
                self.gap("commit_like", page["page_id"], control=cand.get("label"), family=fam)

    def settled_family(self, sigs: list) -> bool:
        """The latest N results of a family agree. Only the latest: one odd result early on (a detail page caught
        before its data arrived, a tap that bounced to the parent) must not keep a long family from ever being
        sampled, since the first N would never agree again."""
        n = self.lim["max_list_items"]
        return len(sigs) >= n and len(set(sigs[-n:])) == 1

    def auto_denied(self, activity: str, cand: dict) -> bool:
        return any(ui.rule_hits(r, activity, cand_obj(cand)) for r in self.state.get("auto_deny", []))

    def denied_now(self, activity: str, cand: dict) -> str:
        """Deny decided when the control is about to be tapped, under the current profile (and review), not only
        when its page was first registered. A deny written after a drift stop or in the review applies to pages
        registered earlier and to recorded paths too, so a resumed run never replays a tap that was denied after it
        was recorded. Cached: deny lists can run to thousands."""
        key = (activity, cand.get("key", ""))
        if key not in self._deny_cache:
            rules = self.profile["deny"]
            c = cand_obj(cand) if rules else None
            hit = next((r for r in rules if ui.rule_hits(r, activity, c)), None)
            self._deny_cache[key] = (hit.get("reason") or "deny") if hit else ""
        if self._deny_cache[key]:
            return self._deny_cache[key]
        return "side_effect" if self.auto_denied(activity, cand) else ""

    def blocked(self, src: str, cand: dict) -> str:
        page = self.pages[src]
        return "" if self.allowed(page, cand) else self.denied_now(page["activity"], cand)

    def wait_loaded(self, obs: Obs | None) -> Obs | None:
        """Do not identify or capture a screen that is still loading (spinner, '正在加载', a blank WebView)."""
        for _ in range(3):
            if obs is None or not obs.in_app:
                return obs
            what = ui.loading(obs.nodes, self.pkg) or ui.blank_webview(obs.nodes, self.pkg)
            if not what:
                return obs
            self.store.event("loading_wait", {"what": what})
            self.dev.pause(0.8, "loading")
            obs = self.settle(self.observe("loading"))
        return obs

    def settle_new(self, obs: Obs) -> Obs:
        """A list item opened a screen no page matches: it will become the template of the whole family, so make
        sure its data has arrived: a detail page caught before its list loaded (with no spinner) would not match
        its loaded siblings, which would then be registered as a second page. Look again until the screen stops
        growing (at most twice); the latest observation wins."""
        for _ in range(2):
            self.dev.pause(0.6, "settle_new")
            again = self.settle(self.observe("settle_new"))
            if again is None:
                return obs
            same = (again.activity == obs.activity and again.structure(self.pkg) == obs.structure(self.pkg)
                    and self.texts(again.nodes) == self.texts(obs.nodes))
            if not same:
                self.store.event("new_page_grew", {"activity": again.activity,
                                                   "added": sorted(again.structure(self.pkg) - obs.structure(self.pkg))[:8]})
            obs = again
            if same:
                break
        return obs

    def confirm_stable(self, obs: Obs | None) -> Obs | None:
        """A dump that needed a retry was taken on a busy screen, and its hierarchy and focus may come from
        different moments (a closing WebView's XML under the next Activity's name, a screenshot of yet another
        screen), producing a 'page' nobody can reach again. Look again until two observations agree; the latest
        one wins."""
        if obs is None or not obs.retried:
            return obs
        for _ in range(2):
            self.dev.pause(0.5, "stable")
            again = self.settle(self.observe("stable"))
            if again is None:
                continue
            same = (again.in_app == obs.in_app and again.activity == obs.activity
                    and ui.jaccard(again.structure(self.pkg), obs.structure(self.pkg)) >= 0.8)
            if not same:
                self.store.event("unstable_screen", {"was": obs.activity, "now": again.activity,
                                                     "in_app": again.in_app})
            obs = again
            if same and not again.retried:
                break
        return obs

    def back_to(self, key: str, landed: Obs | None, cand: dict | None = None) -> None:
        """Return from a page we just tapped into.

        A new activity (or an overlay / another app) is left with BACK, the cheap path. Inside the same
        activity (tabs, fragments) BACK may leave the app, so replay / recorded edges are used instead.
        """
        if landed is None:
            self.ensure_at(key)  # capture lost the observation: recover from a fresh one, not an old fallback
            return
        same_activity = (landed.in_app and not landed.overlay and not ui.layered(landed.nodes)
                         and landed.activity == self.pages[key]["activity"])
        # Tab bars / toolbars switch sibling screens (BACK may leave the app); a content control inside the same
        # activity usually pushes a fragment, which BACK pops.
        if same_activity and (cand is None or cand.get("chrome")):
            self.ensure_at(key, landed)
            return
        self.dev.back("return")
        self.cur = None
        obs = self.settle(self.observe("verify"))
        got = self.match(obs)
        self.edge("return", self.match(landed) if landed is not None and landed.in_app else None, None, key,
                  method="back", landed=got, result="ok" if got == key else "redirected")
        self.ensure_at(key, obs)

    def is_danger_dialog(self, obs: Obs) -> bool:
        if not (obs.overlay or ui.layered(obs.nodes)):
            return False
        texts = " ".join(n.text + " " + n.desc for n in obs.nodes if n.package == self.pkg and not n.covered)
        has_danger = bool(ui.danger_word(texts, words=tuple(ui.DANGER_WORDS) + tuple(self.profile["extra_danger_words"])))
        has_confirm = any(ui.is_confirm_label(n.text or n.desc) or ui.danger_word(n.text, n.desc)
                          for n in obs.nodes if n.package == self.pkg and not n.covered
                          and (n.clickable or ui.tap_target(obs.nodes, n).clickable) and (n.text or n.desc))
        return has_danger and has_confirm

    def dismiss(self, obs: Obs, purpose: str = "dismiss") -> str:
        """Close an overlay without committing anything: an exact cancel-like button, else BACK."""
        for n in obs.nodes:
            if n.package != self.pkg or n.covered:
                continue
            label = (n.text or n.desc).strip()
            if label and ui.is_cancel_label(label):
                target = ui.tap_target(obs.nodes, n)
                if target.clickable or n.clickable:
                    x, y = target.center
                    self.dev.tap(x, y, purpose)
                    return "cancel_button"
        self.dev.back(purpose)
        return "back"

    # ------------------------------------------------------------------ view states
    def rewind(self, page: dict, obs: Obs) -> Obs | None:
        """Scroll the page's main container back to the top so a view state is captured from its start."""
        cont = page.get("container")
        if not cont or page.get("viewport", 0) <= 0:
            return obs
        for _ in range(self.lim["max_scrolls"] + 2):
            live = ui.find_container(obs.nodes, self.pkg, cont["key"])
            if live is None:
                break
            before = cap._node_set(obs.nodes, self.pkg, live.bounds)
            cap.swipe_backward(self.dev, live.bounds, "vertical", "rewind")
            nxt = self.observe("rewind")
            if nxt is None:
                self.gap("scroll_interrupted", page["page_id"], purpose="rewind", stop="dump_failed")
                return None
            _, issue = cap.scroll_continuity(obs, nxt, self.pkg, live)
            if issue:
                self.cur = None
                self.gap("scroll_interrupted", page["page_id"], obs=nxt, purpose="rewind",
                         stop=issue["stop"], interruption=issue)
                return None
            obs = nxt
            if cap._node_set(obs.nodes, self.pkg, live.bounds) == before:
                break
        page["viewport"] = 0
        return obs

    def view_state(self, page: dict, cand: dict, after: Obs, novel: set) -> bool:
        for v in page["views"]:
            vt = set(map(tuple, v["texts"]))
            if novel <= vt or ui.jaccard(frozenset(novel), frozenset(map(tuple, v["novel"]))) >= 0.5:
                self.edge("view_known", page["key"], cand, page["key"], view=v["page_id"])
                self.note_explored(page, cand, "view", v["page_id"])
                page["active_view"] = v["page_id"]
                self.cur = after
                return True
        if len(page["views"]) >= self.lim["max_views_per_page"] or self.counters["captures"] >= self.lim["max_pages"]:
            self.gap("view_cap", page["page_id"], control=cand["label"])
            self.note_explored(page, cand, "view")
            self.cur = after
            return True
        after = self.rewind(page, after)
        if after is None:
            self.note_explored(page, cand, "capture_failed")
            return False
        res = self.capture(after)
        own = res.page_frames
        if len(own) > 1:
            # Keep scroll frames of a view only where they show something the base page has not shown.
            known = {self.norm(t) for t in map(tuple, page["base_texts"])}
            kept = [own[0]] + [f for f in own[1:] if {self.norm(t) for t in self.texts(f.nodes)} - known]
            if len(kept) < len(own):
                self.store.event("view_frames_dropped", {"page": page["page_id"], "dropped": len(own) - len(kept)})
                strips = res.frames[len(own):]
                res.frames = kept + strips
                for i, f in enumerate(res.frames):
                    f.index = i
                if res.auto_from is not None:
                    res.auto_from = len(kept)
        toggle = {k: v for k, v in cand.items() if k != "view_via"}
        new_cands = []
        for c in self.collect_cands(res.page_frames, after.activity):
            if c["key"] not in {x["key"] for x in page["cands"]}:
                c["view_via"] = toggle  # reachable only while this view is active
                new_cands.append(c)
        label = self.label_for(after.activity, cand, page, view=True)
        page_id = self.write_page(res.frames, res, after, kind="view_state", label=label, parent_key=page["key"],
                                  via=cand, path=page["path"] + [{"src": page["key"], "cand": toggle, "dst": page["key"]}],
                                  cands=new_cands)
        view_texts = {self.norm(t) for f in res.frames for t in self.texts(f.nodes)}
        page["views"].append({"page_id": page_id, "via": cand["key"], "novel": sorted(novel), "texts": sorted(view_texts)})
        added = [sorted(after.structure(self.pkg))] + [sorted(ui.structure(f.nodes, self.pkg)) for f in res.frames[1:]]
        page["frame_structs"].extend(added)
        page["structure"] = sorted(set(page["structure"]).union(*map(set, added)))
        # New controls exist only in this view: explore them next, while the view is active.
        page["cands"][page["next"]:page["next"]] = new_cands
        page["viewport"] = len(res.page_frames) - 1
        page["active_view"] = page_id
        self.counters["views"] += 1
        self.edge("view_state", page["key"], cand, page["key"], view=page_id)
        self.note_explored(page, cand, "view", page_id)
        self.log(f"  ~ {page_id}  {label}  frames={len(res.frames)} new_cands={len(new_cands)}")
        return True

    def checkable_snapshot(self, obs: Obs) -> dict:
        return {c.key: n.checked for c in ui.candidates(obs.nodes, self.pkg) if c.kind == "check"
                for n in [ui.locate(obs.nodes, self.pkg, c)] if n is not None}

    def restore_check(self, page: dict, cand: dict, snapshot: dict) -> None:
        """Toggle back what the exploration toggled, then verify every checkable control is as before.

        Radio groups are restored by tapping the item that was checked before (tapping the same radio
        again does not uncheck it). A mismatch is recorded as a gap and as business drift.
        """
        obs = self.cur or self.observe("verify")
        if obs is None:
            return
        now = self.checkable_snapshot(obs)
        changed = [k for k, v in snapshot.items() if k in now and now[k] != v]
        if not changed:
            return
        target_key = next((k for k in changed if snapshot[k]), cand["key"])
        node = ui.locate(obs.nodes, self.pkg, cand_obj({**cand, "key": target_key}))
        if node is not None:
            x, y = ui.tap_point(obs.nodes, node)
            self.dev.tap(x, y, "restore_toggle")
            self.cur = None
            self.edge("restore_toggle", page["key"], cand, page["key"], target=target_key)
            obs = self.observe("verify")
        if obs is not None:
            now = self.checkable_snapshot(obs)
            still = [k for k, v in snapshot.items() if k in now and now[k] != v]
            if still:
                self.gap("toggle_not_restored", page["page_id"], obs=obs, control=cand["label"], keys=still)
                drift = dict(self.state.get("drift") or {})
                drift["toggle:" + (cand["label"] or cand["key"])] = {"expected": "restored", "actual": "changed"}
                self.state["drift"] = drift

    # ------------------------------------------------------------------ explore
    def explore(self, page: dict, cand: dict) -> None:
        key = page["key"]
        obs = self.cur
        if obs is None or self.match(obs) != key:
            obs = self.ensure_at(key, obs)
            if obs is None:
                return
        # Passive volatility check: with no view active, base content should not have changed by itself.
        if page.get("active_view") is None:
            drifted = self.novel(page, obs, None)
            rids = sorted({t[0] for t in drifted if t[0]})
            if rids:
                page["volatile"] = sorted(set(page.get("volatile", [])) | set(rids))
                self.store.event("volatile_text", {"page": page["page_id"], "rids": rids})
        node, before = self.locate(page, cand, obs, loose=cand.get("rid_count") == 1)
        if node is None and cand.get("view_via"):
            # The control only exists in a view state: switch the view on, then look again.
            got = self.tap_step(key, cand["view_via"], before, "view_switch")
            if got is not None and self.match(got) == key:
                node, before = self.locate(page, cand, got)
        if node is None:
            self.gap("not_found", page["page_id"], control=cand["label"] or cand["key"])
            self.note_explored(page, cand, "not_found")
            return
        snapshot = self.checkable_snapshot(before) if cand["kind"] == "check" else None
        x, y = ui.tap_point(before.nodes, node)
        self.last_action = (key, cand)
        self.note_suspect(page, cand)
        self.dev.tap(x, y, "explore")
        self.counters["explored"] += 1
        self.cur = None
        after = self.wait_loaded(self.confirm_stable(self.settle(self.observe("identify"))))
        if after is None:
            # A hung app after this tap says something about the control; a failed dump says nothing.
            self.note_explored(page, cand, "anr" if self.anr_closed else "observe_failed")
            self.anr_closed = False
            self.failure("identify dump failed")
            self.ensure_at(key)
            return
        blank = ui.blank_webview(after.nodes, self.pkg) if after.in_app else ""
        if blank:
            # Still blank after the wait: an about:blank screen is not the page the control opens. Report it.
            self.gap("webview_blank", page["page_id"], obs=after, control=cand["label"] or cand["key"], what=blank)
            self.note_explored(page, cand, "blank")
            self.back_to(key, after, cand)
            return
        if not after.in_app:
            self.edge("external", key, cand, None, package=after.focus.package)
            self.note_explored(page, cand, "external")
            self.store.event("external", {"page": page["page_id"], "control": cand["label"], "package": after.focus.package})
            self.back_to(key, after)
            return
        m = self.match(after)
        if m is None and (cand.get("family") or cand.get("group")):
            after = self.settle_new(after)
            m = self.match(after)
        if m == key and not self.navigated_in_place(page, cand, before, after):
            novel = self.novel(page, after, cand)
            if novel and len(novel) <= 2 and not page.get("stable_checked"):
                after, novel = self.confirm_view(page, cand, after, novel)
            if not novel and cand["kind"] != "check":
                # Same texts, different selection (a mode switch drawn by selected state: 农历, 列表).
                sel_a, sel_b = ui.selection(after.nodes, self.pkg), ui.selection(before.nodes, self.pkg)
                if sel_a != sel_b and sorted([list(x) for x in sel_a]) != page.get("base_selection"):
                    novel = {("sel:" + r, l) for r, l in sel_a - sel_b} or {("sel:", "-")}
            if novel:
                if not self.view_state(page, cand, after, novel):
                    return
            elif self.novel(page, before, cand) and page.get("active_view"):
                self.edge("view_base", key, cand, key)  # left a view state, back to the base content
                self.note_explored(page, cand, "view")
                page["active_view"] = None
                self.cur = after
            else:
                self.edge("self", key, cand, key)
                self.note_explored(page, cand, "self")
                self.cur = after
            if snapshot is not None:
                self.restore_check(page, cand, snapshot)
            self.success()
            return
        if m is not None and m != key and m in self.state["stack"]:
            self.edge("up", key, cand, m)
            self.note_explored(page, cand, "up", m)
            if any(not self.skip_reason(page, c) for c in page["cands"][page["next"]:]):
                self.ensure_at(key, after)
            else:
                self.cur = after  # nothing left here: stay on the ancestor instead of replaying back
            return
        if m is not None and m != key and not (self.pages[m]["layer"] and self.novel(self.pages[m], after, cand)):
            mp = self.pages[m]
            inst = None
            opened = self.allowed(page, cand)  # reviewer-requested items always keep their own shot
            mp.setdefault("instances", [])
            content = self.novel(mp, after, None)  # what this detail shows beyond the template, label included
            same = next((i["page_id"] for i in mp.setdefault("instance_sigs", [])
                         if ui.jaccard(frozenset(content), frozenset(map(tuple, i["sig"]))) >= 0.8), None)
            if same and self.novel(mp, after, cand):
                # This content already has its shot (the same item reached through another control): one each.
                self.store.event("instance_duplicate", {"page": mp["page_id"], "same_as": same, "control": cand["label"]})
            elif (not mp["layer"] and self.novel(mp, after, cand)
                    and (opened or len(mp.setdefault("instances", [])) < self.lim["max_instances_per_page"])
                    and self.counters["captures"] < self.lim["max_pages"]):
                # Same template, different content (another detail item): keep one screenshot of this instance.
                res = self.capture(after, scroll=False)  # the template page already holds the full scroll
                item = cand["label"] or cand.get("content-desc") or (cand.get("resource-id") or "").rsplit("/", 1)[-1]
                inst = self.write_page(res.frames, res, after, kind="instance",
                                       label=f"{mp['label']}·{item}" if item else mp["label"],
                                       parent_key=key, via=cand,
                                       path=page["path"] + [{"src": key, "cand": cand, "dst": m}], cands=[])
                mp["instances"].append(inst)
                mp["instance_sigs"].append({"page_id": inst, "sig": sorted(content)})
                self.counters["instances"] = self.counters.get("instances", 0) + 1
            self.edge("known", key, cand, m, instance=inst, **({"same_as": same} if same and not inst else {}))
            self.note_explored(page, cand, "known", m)
            self.back_to(key, self.cur, cand)
            return
        # A page never seen before, a dialog sharing a known layout with a new message,
        # or a same-layout page reached by real navigation.
        if self.counters["captures"] >= self.lim["max_pages"]:
            self.gap("page_cap", page["page_id"], control=cand["label"])
            self.note_explored(page, cand, "page_cap")
            self.ensure_at(key, after)
            return
        if self.is_danger_dialog(after):
            new = self.register_page(after, key, cand, kind="danger_dialog")
            self.edge("forward", key, cand, new, dialog="danger")
            self.note_explored(page, cand, "new", new)
            self.close_overlay(new, self.cur, key)
            return
        new = self.register_page(after, key, cand)
        self.edge("forward", key, cand, new)
        self.note_explored(page, cand, "new", new)
        self.success()
        np_ = self.pages[new]
        if np_["depth"] >= self.lim["max_depth"] or np_["same_layout_depth"] >= 2:
            np_["status"] = "leaf"
            self.gap("depth_cap" if np_["depth"] >= self.lim["max_depth"] else "same_layout_chain",
                     np_["page_id"], unexplored=len(np_["cands"]))
            self.return_to(new, key)
        else:
            self.state["stack"].append(new)

    def confirm_view(self, page: dict, cand: dict, after: Obs, novel: set):
        """A one- or two-item text change may be a rotating banner: read the screen again after a short wait.

        If those texts changed again by themselves, their rids are volatile (ignored from now on); otherwise
        the change came from the tap and this page needs no further checks.
        """
        self.dev.pause(self.lim["volatility_check_s"], "volatility")
        again = self.observe("volatility")
        if again is None or self.match(again) != page["key"]:
            return after, novel
        def by_rid(obs: Obs) -> dict:
            d: dict = {}
            for rid, text in self.texts(obs.nodes):
                d.setdefault(rid, set()).add(text)
            return d
        first, second = by_rid(after), by_rid(again)
        moved = sorted({rid for rid, _ in novel if rid and first.get(rid) != second.get(rid)})
        if moved:
            page["volatile"] = sorted(set(page.get("volatile", [])) | set(moved))
            self.store.event("volatile_text", {"page": page["page_id"], "rids": moved, "via": "recheck"})
            return again, self.novel(page, again, cand)
        page["stable_checked"] = True
        return again, novel

    def navigated_in_place(self, page: dict, cand: dict, before: Obs, after: Obs) -> bool:
        """Same layout as the current page, but a real navigation happened.

        Signals: a new window token (a new activity instance), or every control of the old page vanished
        (an in-place fragment replacement). Tabs and segmented controls keep their siblings visible.
        """
        if (after.focus.kind == "activity" and before.focus.token and after.focus.token
                and before.focus.token != after.focus.token):
            # A new instance of this activity. Showing exactly this page's content it is this page again (the app
            # recreated it when the child it opened closed itself).
            return bool(self.novel(page, after, None)) or after.structure(self.pkg) != before.structure(self.pkg)
        if ui.locate(after.nodes, self.pkg, cand_obj(cand)) is not None:
            return False  # the tapped control is still there: a tab / segmented control / toggle
        visible_before = [c for c in page["cands"] if c["key"] != cand["key"] and not c.get("nav_back")
                          and ui.locate(before.nodes, self.pkg, cand_obj(c)) is not None]
        if not visible_before:
            return False
        remaining = sum(1 for c in visible_before if ui.locate(after.nodes, self.pkg, cand_obj(c)) is not None)
        return remaining * 3 <= len(visible_before)  # chrome (toolbar, bottom bar) may stay; content is gone

    def close_overlay(self, child: str, obs: Obs | None, parent: str) -> None:
        for attempt in range(2):
            if obs is None:
                obs = self.settle(self.observe("verify"))
            if obs is None:
                continue  # no stale cancel coordinates when verification failed
            if not self.is_danger_dialog(obs):
                self.ensure_at(parent, obs)
                return
            method = self.dismiss(obs)
            self.cur = None
            after = self.settle(self.observe("verify"))
            landed = self.match(after) if after is not None else None
            if after is not None and landed != child and not self.is_danger_dialog(after):
                self.edge("return", child, None, parent, method=method, result="ok", landed=landed)
                self.ensure_at(parent, after)
                return
            self.edge("return", child, None, parent, method=method, result="still_open", landed=landed)
            obs = after
        raise Halt("halted_unsafe", f"danger dialog {self.pages[child]['page_id']} could not be dismissed")

    def return_control(self, cp: dict, parent: str, obs: Obs):
        """A control on the child that is known to lead to the parent (e.g. the parent's tab)."""
        for cand in cp["cands"]:
            rec = self.state["explored"].get(self.dkey(cp, cand))
            if not rec:
                continue
            if any(r.get("to") == parent and r["result"] in NAV_RESULTS for r in rec["pages"].values()):
                node = ui.locate(obs.nodes, self.pkg, cand_obj(cand))
                if node is not None:
                    return node
        return None

    def return_to(self, child: str, parent: str) -> None:
        cp = self.pages[child]
        pp = self.pages[parent]
        obs = self.cur
        if obs is None:
            self.ensure_at(parent)
            return
        here = self.match(obs) if obs is not None else None
        if here == parent:  # the last control already led back up
            self.edge("return", child, None, parent, method="already_there", landed=here, result="ok")
            self.success()
            return
        if here is not None and here != child and self.is_on_path(here, parent):
            self.ensure_at(parent, obs)  # an ancestor of the parent: replay forward, no blind BACK
            self.edge("return", child, None, parent, method="replay_from_ancestor", landed=here)
            return
        at_child = here == child
        node = self.return_control(cp, parent, obs) if (at_child and cp["activity"] == pp["activity"]
                                                         and not cp["layer"]) else None
        if node is not None:
            x, y = ui.tap_point(obs.nodes, node)
            self.dev.tap(x, y, "return")
            method = "known_control"
        elif cp["layer"] and at_child:
            method = self.dismiss(obs, "return")
        else:
            self.dev.back("return")
            method = "back"
        self.cur = None
        landed_obs = self.settle(self.observe("verify"))
        landed = self.match(landed_obs)
        self.edge("return", child, None, parent, method=method, landed=landed,
                  result="ok" if landed == parent else "redirected")
        self.ensure_at(parent, landed_obs)

    # ------------------------------------------------------------------ review / resume
    def reopen(self) -> str | None:
        """Cleanup pass: pages that still have unexplored candidates (e.g. allowed after review)."""
        for key in self.state["order"]:
            p = self.pages[key]
            if p["status"] in ("open", "done", "reopened") and p["next"] < len(p["cands"]):
                return key
        return None

    def apply_review(self, review: dict) -> None:
        """Re-queue skipped/sampled candidates the profile now allows; retry pages; apply labels."""
        requeued = 0
        for bucket in ("skipped", "sampled"):
            for rec in list(self.state.get(bucket, [])):
                page = self.pages.get(rec["page_key"])
                if page is None:
                    continue
                cand = rec["cand"]
                if self.allowed(page, cand):
                    page["cands"].append(cand)
                    self.state[bucket].remove(rec)
                    requeued += 1
        by_page_id = {p["page_id"]: k for k, p in self.pages.items()}
        for ref in review.get("retry", []):
            key = by_page_id.get(ref, ref)
            if key not in self.pages:
                continue
            requeued += self.retry_failed(key, {"observe_failed", "capture_failed", "not_found", "blank"})
        labels = review.get("labels") or {}
        if labels:
            for rec in self.state.get("index", []):
                if rec["page_id"] in labels:
                    rec["label"] = labels[rec["page_id"]]
                    meta_path = self.store.out / rec["page_id"] / "meta.json"
                    if meta_path.exists():
                        meta = json.loads(meta_path.read_text(encoding="utf-8"))
                        meta["label"] = rec["label"]
                        self.store.write_meta(rec["page_id"], meta)
            self.store.write_index(self.state["index"])
        self.store.event("review_applied", {"requeued": requeued, "labels": len(labels)})
        self.log(f"review applied: {requeued} items re-queued, {len(labels)} labels")

    def retry_failed(self, key: str, retryable: set) -> int:
        """Re-queue the candidates of one page whose last result is in `retryable`; successes are not retried."""
        requeued = 0
        page = self.pages[key]
        if page.get("blocked_by"):
            return 0  # unreachable only because of a deny: a retry would replay into the same block
        if page["status"] in ("unreachable", "leaf"):
            page["status"] = "open"
            requeued += 1
        retries = []
        for cand in list(page["cands"]):
            dkey = self.dkey(page, cand)
            record = self.state["explored"].get(dkey)
            result = record.get("pages", {}).get(key) if record else None
            if not result or result.get("result") not in retryable:
                continue
            # A failed identification is not a completed edge. Explicit
            # review retries only that page's result, preserving successes
            # under the same control key on other pages and all old gaps.
            del record["pages"][key]
            if not record["pages"]:
                del self.state["explored"][dkey]
            retries.append(cand)
            page["status"] = "open"
            page["explored"] = max(0, page.get("explored", 0) - 1)
            rid_key = f"{cand['resource-id']}|{cand['class']}"
            if page.get("rid_done", {}).get(rid_key) in retryable:
                page["rid_done"].pop(rid_key)
            family = cand.get("family") or cand.get("group")
            if family:
                # Do not join successful samples across a failed attempt:
                # that could immediately sample away the explicit retry.
                page.setdefault("list_results", {}).pop(family, None)
                learned = self.state.get("families", {}).get(family, {})
                if learned.get("page") == page["page_id"] and learned.get("sig") in retryable:
                    self.state["families"].pop(family)
            requeued += 1
        if retries:
            retry_keys = {cand["key"] for cand in retries}
            remaining = [cand for cand in page["cands"][page["next"]:] if cand["key"] not in retry_keys]
            # Retry before untouched pending controls consume the restored
            # candidate allowance; never rewind through successful edges.
            page["cands"][page["next"]:] = retries + remaining
        return requeued

    def retry_transient(self) -> int:
        """Once per run, before finishing: candidates that failed because the screen could not be read at that
        moment (a blank WebView, a failed dump, a failed capture) are tried again, so they do not wait for review."""
        if self.state.get("transient_retry_done"):
            return 0
        self.state["transient_retry_done"] = True
        transient = {"observe_failed", "capture_failed", "blank"}
        keys = {pk for rec in self.state["explored"].values() for pk, r in rec["pages"].items()
                if r.get("result") in transient and pk in self.pages}
        n = sum(self.retry_failed(k, transient) for k in sorted(keys))
        self.store.event("transient_retry", {"pages": len(keys), "requeued": n})
        return n

    def setup(self, resume: bool) -> None:
        loaded = self.store.load_state()
        manual_only = bool(loaded) and "counters" not in loaded
        if loaded and not manual_only:
            if not resume:
                raise RefuseError("output directory already holds a traversal; use --resume, or --fresh to start over in this OUT")
            if loaded.get("device_counters"):
                self.dev.counters = loaded["device_counters"]  # cumulative across resumes
                for k in ("ops", "time", "purpose", "purpose_time"):
                    self.dev.counters.setdefault(k, {})
            ensure_baseline(self.dev, loaded, self.pkg)
            self.state = loaded
            self.state["_elapsed_base"] = loaded.get("elapsed_s", 0.0)
            self.state["status"] = "running"
            self.state.pop("halt_reason", None)  # a resumed run must not report the previous halt
            self.state["version"] = VERSION
            self.state["failures"] = 0
            self.state.setdefault("sampled", [])
            pending = self.state.get("inflight_candidate")
            if pending and pending.get("page_key") in self.pages:
                page = self.pages[pending["page_key"]]
                index = pending.get("index")
                if isinstance(index, int) and 0 <= index < len(page["cands"]):
                    cand = page["cands"][index]
                    if cand["key"] == pending.get("key") and self.dkey(page, cand) not in self.state["explored"]:
                        page["next"] = min(page["next"], index)
                self.state.pop("inflight_candidate", None)
            self.carry_rules()
            self.rebase_changed_readings()
            self.store.save_json("profile.json", self.profile)
            return
        if not loaded:
            leftovers = [p.name for p in self.store.out.iterdir()
                         if p.name == "index.json" or p.name.startswith(("page_", "manual_"))]
            if leftovers:
                raise RefuseError(f"output directory is not empty ({leftovers[:3]}...); use --fresh to archive it and start over")
        self.state = self.new_state()
        if manual_only:
            # Manual captures made with `drive` before the first run keep their numbering and index entries.
            self.state["page_counter"] = loaded.get("page_counter", 0)
            self.state["index"] = loaded.get("index", [])
            for name in ("app", "density", "baseline", "drift", "artifact_stats",
                         "manual_device_counters", "manual_elapsed_s"):
                if name in loaded:
                    self.state[name] = loaded[name]
            if loaded.get("package") and loaded["package"] != self.pkg:
                raise ValueError("output belongs to another package; use a separate baseline directory")
        ensure_baseline(self.dev, self.state, self.pkg)
        self.state["launcher"] = self.profile.get("launch_component") or self.dev.resolve_launcher()
        self.store.save_json("profile.json", self.profile)

    def carry_rules(self) -> None:
        """Allow and deny rules saved by an earlier invocation (a review, a deny added after a drift stop) stay in
        force when a later resume passes the original profile; rules are only ever added. Without this a plain
        resume overwrote _aft/profile.json and tapped the city picker again. To lift a deny, allow the control."""
        try:
            old = json.loads((self.store.aft / "profile.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        for field in ("deny", "allow"):
            have = {json.dumps(r, sort_keys=True, ensure_ascii=False) for r in self.profile[field]}
            extra = [r for r in old.get(field) or [] if json.dumps(r, sort_keys=True, ensure_ascii=False) not in have]
            if extra:
                self.profile[field] = list(self.profile[field]) + extra
                self.store.event("rules_carried", {"field": field, "count": len(extra)})
        self._deny_cache.clear()

    def rebase_changed_readings(self) -> None:
        """A reading whose definition changed in the profile (a selector that read the wrong text) takes a new
        baseline on resume; its old drift record goes with the old definition."""
        try:
            old = json.loads((self.store.aft / "profile.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        before = {r["name"]: r for r in old.get("business_readings", [])}
        now = {r["name"]: r for r in self.profile["business_readings"]}
        drift = dict(self.state.get("drift") or {})
        for name in set(before) | set(now):
            if before.get(name) != now.get(name):
                self.state.get("baseline", {}).pop(name, None)
                drift.pop(name, None)
                self.store.event("reading_rebased", {"reading": name})
                if name not in now:  # switching the check off is not a way past drift: keep it visible
                    self.gap("reading_removed", None, reading=name)
        self.state["drift"] = drift or None

    def run(self, resume: bool = False, review: dict | None = None) -> dict:
        self.setup(resume)
        try:
            if not self.state["order"]:
                if self.profile.get("grant_permissions", True) and not self.state.get("permissions"):
                    # Test devices: grant runtime permissions up front, except location unless the profile says so
                    # (it can make the app relocate and change the city).
                    grant_location = bool(self.profile.get("grant_location", False))
                    try:
                        self.state["permissions"] = self.dev.grant_permissions(
                            skip=lambda p: not grant_location and bool(LOCATION_PERM.search(p)))
                        self.store.event("permissions_granted", self.state["permissions"])
                    except DeviceError as exc:
                        self.store.event("permissions_grant_failed", {"error": str(exc)[:200]})
                obs = self.cold_start(first=True)
                if obs is None:
                    raise Halt("halted_breaker", "could not reach a stable root page after cold start")
                root = self.register_page(obs, None, None)
                self.state["root"] = root
                self.state["stack"] = [root]
                self.mark_progress()
            else:
                if review:
                    self.apply_review(review)
                if self.reading_drift():
                    # Stopped on changed data: confirm it was restored before capturing anything more.
                    self.pending_drift_restore = True
                    self.guarded(self.restore_drift, None, "restore_drift")
                if self.state["stack"]:
                    self.guarded(lambda: self.ensure_at(self.state["stack"][-1]), None, "resume")
            self.loop()
            open_items = self.state["gaps"] or self.state["skipped"] or self.state["sampled"]
            self.state["status"] = "completed_with_gaps" if open_items else "completed"
        except (Halt, PopupStop) as h:
            self.state["status"] = h.status
            self.state["halt_reason"] = h.reason
            self.log(f"HALT {h.status}: {h.reason}")
        except Exception as exc:  # never leave the ledger in 'running'
            self.state["status"] = "error"
            self.state["halt_reason"] = f"{type(exc).__name__}: {exc}"
            self.store.event("crash", {"error": repr(exc), "trace": traceback.format_exc()[-2000:]})
            self.log(f"ERROR {exc!r}")
        finally:
            self.save()
        return self.state

    def guarded(self, fn, page: dict | None, what: str):
        """Device/capture errors stay local: record a gap, count a failure, continue."""
        try:
            return fn()
        except (DeviceError, cap.CaptureError) as exc:
            self.cur = None
            self.gap("device_error", page["page_id"] if page else None, step=what, error=str(exc)[:200])
            self.failure(f"device error during {what}: {exc}")
            return None

    def loop(self) -> None:
        stack = self.state["stack"]
        max_minutes = self.lim["max_minutes"]
        while True:
            if max_minutes and (self.clock() - self.t_start) / 60 >= max_minutes:
                raise Halt("paused", f"time budget {max_minutes} min reached; resume with --resume")
            if self.pending_drift_restore:
                # Changed data may also be noticed while returning between pages, not only inside explore.
                self.guarded(self.restore_drift, self.pages.get(stack[-1]) if stack else None, "restore_drift")
            if self.stalled():
                self.gap("stalled", None, minutes=self.lim["stall_minutes"],
                         remaining=sum(max(0, len(p["cands"]) - p["next"]) for p in self.pages.values()))
                self.store.event("stalled", {"minutes": self.lim["stall_minutes"]})
                return
            if not stack:
                nxt = self.reopen()
                if nxt is None and self.retry_transient():
                    nxt = self.reopen()
                if nxt is None:
                    return
                self.pages[nxt]["status"] = "reopened"
                stack.append(nxt)  # only the page itself: the recovery ladder navigates, no ancestor unwinding
                if self.guarded(lambda: self.ensure_at(nxt), self.pages[nxt], "reopen") is None:
                    stack.clear()
                continue
            page = self.pages[stack[-1]]
            if page["status"] == "unreachable" or page["next"] >= len(page["cands"]):
                if page["status"] != "unreachable":
                    page["status"] = "done"
                stack.pop()
                if stack and page["status"] != "unreachable":
                    self.guarded(lambda: self.return_to(page["key"], stack[-1]), page, "return")
                self.save()
                continue
            cand = page["cands"][page["next"]]
            page["next"] += 1
            reason = self.skip_reason(page, cand)
            if reason:
                kind = reason.split(":")[0]
                self.bump("skipped", kind)
                rec = {"page_key": page["key"], "page_id": page["page_id"], "label": cand["label"],
                       "reason": reason, "cand": cand, "family": cand.get("family", "")}
                if kind in POLICY_SKIPS:
                    self.state["skipped"].append(rec)
                elif kind in SAMPLED_SKIPS:
                    self.state["sampled"].append(rec)
                continue
            self.state["inflight_candidate"] = {"page_key": page["key"], "key": cand["key"],
                                                "index": page["next"] - 1}
            try:
                self.guarded(lambda: self.explore(page, cand), page, "explore:" + (cand["label"] or cand["key"]))
            except PopupStop:
                # The long-lived process normally continues at the same call
                # site. If the model times out/hands off instead, this candidate
                # still needs classification on the next invocation.
                if self.dkey(page, cand) not in self.state["explored"]:
                    page["next"] -= 1
                raise
            self.state.pop("inflight_candidate", None)
            self.last_action = None
            self.save()
