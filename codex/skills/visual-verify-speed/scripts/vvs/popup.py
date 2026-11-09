"""Unknown popups go to the model, the walker waits in the same process and applies the decision.

Protocol (files under WORK/cache/model_requests/<id>/):
  request.json  before.png  before.json     written by the walker; it prints `VVS_MODEL_REQUEST id=<id> dir=<dir>`
  decision.json                             written by the model
  response.json                             published by `vvs.py respond` after validation
  result.json                               what the walker did with it
Decision: {"action": "tap"|"back"|"continue"|"stop", "selector": {"text": ".."}|{"point": [x, y]},
           "remember": true|false, "reason": ".."}
  continue = the layer is a legitimate state of the screen being captured (capture it as it is).
  stop     = hand the run back (needs the user); the walker saves its state and exits.
"""
from __future__ import annotations

import os
import time

from . import hui
from .store import now_iso, read_json, write_json

ACTIONS = ("tap", "back", "continue", "stop")


class PopupStop(Exception):
    def __init__(self, status: str, reason: str):
        super().__init__(reason)
        self.status, self.reason = status, reason


def signature(obs, bundle: str) -> str:
    """Popup identity for remembered rules: owner, layer type and the labels inside the layer, digits as '#'."""
    nodes = obs.nodes
    top = hui.dialog_node(nodes)
    if top is not None:
        scope = [nodes[i] for i in hui.subtree(nodes, top)]
    else:
        scope = [n for n in nodes if not n.covered and (n.bundle == obs.bundle)]
    labels = sorted({hui.digit_pattern(n.text or n.desc) for n in scope if (n.text or n.desc).strip()})[:30]
    return f"{obs.bundle}|{obs.overlay}|{top.type if top else ''}|" + "|".join(labels)


def controls(obs) -> list:
    out = []
    for n in obs.nodes:
        if n.covered or not (n.clickable or n.checkable) or not hui.visible_on_screen(obs.nodes, n):
            continue
        out.append({"label": hui.label_of(obs.nodes, n), "type": n.type, "center": list(n.center),
                    "bundle": n.bundle})
    return out[:60]


def validate(decision: dict) -> str:
    if not isinstance(decision, dict) or decision.get("action") not in ACTIONS:
        return f"action must be one of {ACTIONS}"
    if decision["action"] == "tap":
        sel = decision.get("selector") or {}
        if not ("text" in sel or (isinstance(sel.get("point"), list) and len(sel["point"]) == 2)):
            return "tap needs selector {text} or {point:[x,y]}"
    return ""


class PopupBridge:
    def __init__(self, store, bundle: str, timeout: float = 180.0, sleep=time.sleep, clock=time.monotonic,
                 printer=print):
        self.store, self.bundle, self.timeout = store, bundle, timeout
        self.sleep, self.clock, self.printer = sleep, clock, printer
        self.dir = os.path.join(store.vvs, "model_requests")
        self.rules_path = os.path.join(store.vvs, "popup_rules.json")
        self.stats = {"requests": 0, "rule_hits": 0, "wait_s": 0.0, "continues": 0, "failures": 0}

    def rules(self) -> dict:
        return read_json(self.rules_path, {})

    def _apply(self, dev, obs, decision: dict) -> None:
        act = decision["action"]
        if act == "back":
            dev.back("model_popup")
        elif act == "tap":
            sel = decision.get("selector") or {}
            if "point" in sel:
                x, y = sel["point"]
            else:
                hits = hui.select(obs.nodes, {"text": sel["text"]})
                if len(hits) != 1:
                    raise PopupStop("paused_model", f"selector {sel} matches {len(hits)} controls on the popup")
                x, y = hui.tap_target(obs.nodes, hits[0]).center
            dev.tap(x, y, "model_popup")

    def handle(self, dev, obs, observe, context: dict) -> tuple:
        """Return (obs, continued). Raise PopupStop when the run must pause."""
        sig = signature(obs, self.bundle)
        rule = self.rules().get(sig)
        if rule:
            self.stats["rule_hits"] += 1
            try:
                self._apply(dev, obs, rule)
                after = observe("model_popup")
                if after is not None and signature(after, self.bundle) != sig:
                    self.store.event("popup_rule", {"signature": sig[:200], "action": rule["action"]})
                    return after, False
            except PopupStop:
                pass
            rules = self.rules()
            rules.pop(sig, None)
            write_json(self.rules_path, rules)
            self.store.event("popup_rule_failed", {"signature": sig[:200]})
            obs = observe("model_popup") or obs
            sig = signature(obs, self.bundle)
        return self.ask(dev, obs, observe, context, sig)

    def ask(self, dev, obs, observe, context: dict, sig: str, failure: str = "") -> tuple:
        self.stats["requests"] += 1
        rid = f"r{len(os.listdir(self.dir)) + 1 if os.path.isdir(self.dir) else 1:04d}"
        d = os.path.join(self.dir, rid)
        os.makedirs(d, exist_ok=True)
        try:
            png = dev.screencap("model_popup")
            with open(os.path.join(d, "before.png"), "wb") as f:
                f.write(png)
        except Exception:
            pass
        with open(os.path.join(d, "before.json"), "wb") as f:
            f.write(obs.raw)
        req = {"id": rid, "created": now_iso(), "signature": sig, "screen": obs.identity(),
               "outline": hui.outline(obs.nodes, obs.bundle or self.bundle),
               "controls": controls(obs), "context": context, "previous_failure": failure or None,
               "decision_file": os.path.join(d, "decision.json"),
               "respond": f"vvs.py respond --request-id {rid} --decision {os.path.join(d, 'decision.json')}"}
        write_json(os.path.join(d, "request.json"), req)
        self.store.event("model_request", {"id": rid, "signature": sig[:200]})
        self.printer(f"VVS_MODEL_REQUEST id={rid} dir={d}", flush=True)
        t0 = self.clock()
        resp_path = os.path.join(d, "response.json")
        while not os.path.exists(resp_path):
            if self.clock() - t0 > self.timeout:
                self.stats["wait_s"] += self.clock() - t0
                write_json(os.path.join(d, "result.json"), {"status": "timeout", "at": now_iso()})
                raise PopupStop("paused_model", f"no decision for {rid} within {self.timeout:.0f}s")
            self.sleep(0.5)
        self.stats["wait_s"] += self.clock() - t0
        decision = read_json(resp_path, {})
        if decision.get("action") == "stop":
            write_json(os.path.join(d, "result.json"), {"status": "stopped", "at": now_iso()})
            raise PopupStop("blocked_user", decision.get("reason") or "model handed the run back")
        if decision.get("action") == "continue":
            self.stats["continues"] += 1
            write_json(os.path.join(d, "result.json"), {"status": "continued", "at": now_iso()})
            return obs, True
        try:
            self._apply(dev, obs, decision)
        except PopupStop as exc:
            self.stats["failures"] += 1
            write_json(os.path.join(d, "result.json"), {"status": "failed", "reason": exc.reason, "at": now_iso()})
            if failure:
                raise
            return self.ask(dev, obs, observe, context, sig, failure=exc.reason)
        after = observe("model_popup")
        changed = after is not None and signature(after, self.bundle) != sig
        write_json(os.path.join(d, "result.json"), {"status": "applied" if changed else "no_effect",
                                                    "at": now_iso(), "after": after.identity() if after else None})
        if not changed:
            self.stats["failures"] += 1
            if failure:
                raise PopupStop("paused_model", f"decision for {rid} did not change the screen")
            return self.ask(dev, after or obs, observe, context, sig, failure="previous decision had no effect")
        if decision.get("remember") and decision["action"] in ("tap", "back"):
            rules = self.rules()
            rules[sig] = {"action": decision["action"], "selector": decision.get("selector"),
                          "reason": decision.get("reason", ""), "created": now_iso(), "request": rid}
            write_json(self.rules_path, rules)
        return after, False


def respond(store, request_id: str, decision_path: str) -> str:
    d = os.path.join(store.vvs, "model_requests", request_id)
    if not os.path.isdir(d):
        return f"unknown request {request_id}"
    decision = read_json(decision_path)
    why = validate(decision)
    if why:
        return why
    if os.path.exists(os.path.join(d, "response.json")):
        return f"request {request_id} already answered"
    write_json(os.path.join(d, "response.json"), decision)
    return ""
