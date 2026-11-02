"""An in-process, filesystem mailbox for model-reviewed popup decisions.

The Walker owns the device and OUT lease throughout ``handle``. Only
``submit_response`` may write a response without that lease; it never accesses
the device. Request/evidence/result files are immutable. A request-local flock
serializes response publication with termination, and a hard link publishes a
fully written O_EXCL temporary file without overwriting another responder.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
import time
import uuid
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path

from . import ui
from .device import Obs
from .store import utc_now


class PopupStop(Exception):
    def __init__(self, status: str, reason: str):
        super().__init__(reason)
        self.status, self.reason = status, reason


def _json(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False,
                      separators=(",", ":")).encode("utf-8")


def _copy(value):
    return json.loads(_json(value))


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _read(path: Path, *, limit=4 * 1024 * 1024):
    if limit is not None and path.stat().st_size > limit:
        raise ValueError(f"mailbox file too large: {path.name}")
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_pairs)


def _write_new(path: Path, data: bytes):
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def _publish(path: Path, value):
    """Atomic exclusive publication: readers never see a partial JSON file."""
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        _write_new(temporary, _json(value))
        os.link(temporary, path)  # exclusive even when two responders race
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def _mailbox_lock(directory: Path):
    # Created by the request owner before publishing request.json. The response
    # helper is deliberately not allowed to invent mailbox directories/locks.
    flags = os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(directory / "mailbox.lock", flags)
    try:
        if os.name == "nt":
            import msvcrt
            os.lseek(descriptor, 0, os.SEEK_SET)
            msvcrt.locking(descriptor, msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        try:
            if os.name == "nt":
                import msvcrt
                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _request_dir(out, request_id: str) -> tuple[Path, Path]:
    if not isinstance(request_id, str) or not re.fullmatch(r"[0-9a-f]{32}", request_id):
        raise ValueError("request_id must be a lowercase UUID hex string")
    if uuid.UUID(hex=request_id).hex != request_id:
        raise ValueError("invalid request_id")
    root = Path(out).resolve()
    directory = root / "_aft" / "model_requests" / request_id
    # Do not follow a symlink anywhere beneath OUT, including individual files.
    for candidate in (root / "_aft", directory.parent, directory):
        if candidate.is_symlink():
            raise ValueError("mailbox path must not contain symlinks")
    if not directory.resolve().is_relative_to(root):
        raise ValueError("mailbox escapes output directory")
    for name in ("mailbox.lock", "request.json", "response.json", "result.json"):
        if (directory / name).is_symlink():
            raise ValueError("mailbox files must not be symlinks")
    return root, directory


def _selector(value):
    if (not isinstance(value, dict) or not value or set(value) - {"rid", "text", "desc", "class"}
            or any(not isinstance(v, str) or not v for v in value.values())):
        raise ValueError("selector must contain nonempty exact rid/text/desc/class strings")


def _validate(decision, request):
    keys = {"request_id", "fingerprint", "action", "expect", "reason", "remember"}
    if not isinstance(decision, dict) or set(decision) != keys:
        raise ValueError("decision requires exactly request_id, fingerprint, action, expect, reason, remember")
    for key in ("request_id", "fingerprint"):
        if decision[key] != request[key]:
            raise ValueError(f"decision {key} does not match request")
    if not isinstance(decision["reason"], str) or not decision["reason"].strip():
        raise ValueError("decision reason must be nonempty")
    if type(decision["remember"]) is not bool:
        raise ValueError("remember must be boolean")
    action = decision["action"]
    if not isinstance(action, dict):
        raise ValueError("action must be an object")
    kind = action.get("type")
    if kind == "tap":
        if set(action) != {"type", "selector"}:
            raise ValueError("tap requires only type and selector")
        _selector(action["selector"])
        if request.get("controls") is not None:
            # Checked when the response is submitted, so a wrong selector is answered again right away
            # instead of failing on the device and ending the run.
            hits = [c for c in request["controls"]
                    if all(c["selector"].get(k) == v for k, v in action["selector"].items())]
            if len(hits) != 1:
                raise ValueError(f"tap selector matches {len(hits)} of the request's controls; pick exactly one "
                                 f"selector from request.json controls")
    elif kind == "wait":
        seconds = action.get("seconds")
        if (set(action) != {"type", "seconds"} or type(seconds) not in (int, float)
                or not math.isfinite(seconds) or not 0 <= seconds <= 3):
            raise ValueError("wait seconds must be a number in [0, 3]")
    elif kind in ("back", "continue", "handoff"):
        if set(action) != {"type"}:
            raise ValueError(f"{kind} accepts only type")
    else:
        raise ValueError("action type must be tap, back, wait, continue, or handoff")
    expect = decision["expect"]
    if kind in ("continue", "handoff"):
        if expect is not None:
            raise ValueError(f"{kind} requires expect: null")
    elif isinstance(expect, dict) and len(expect) == 1:
        if "changed" in expect:
            if expect["changed"] is not True:
                raise ValueError("changed must be true")
        elif "present" in expect or "absent" in expect:
            target = expect.get("present", expect.get("absent"))
            if not isinstance(target, dict) or set(target) != {"selector"}:
                raise ValueError("present/absent requires a selector object")
            _selector(target["selector"])
        else:
            raise ValueError("expect must contain changed, present, or absent")
    else:
        raise ValueError("device actions require one postcondition")
    if kind in ("wait", "handoff") and decision["remember"]:
        raise ValueError(f"{kind} decisions cannot be remembered")


def _pending(root: Path, directory: Path, request_id: str):
    if (directory / "result.json").exists():
        raise ValueError("request is already terminal")
    request = _read(directory / "request.json")
    if request.get("request_id") != request_id or request.get("status") != "pending":
        raise ValueError("request identity/status is invalid")
    if time.time() >= request["deadline_wall_time"]:
        raise ValueError("request deadline has expired")
    state_path = root / "_aft" / "state.json"
    if state_path.is_symlink():
        raise ValueError("state.json must not be a symlink")
    state = _read(state_path, limit=None)  # the traversal ledger may legitimately be large
    pending = state.get("model_request", {})
    if (state.get("status") != "waiting_model" or pending.get("status") != "waiting_model"
            or pending.get("request_id") != request_id
            or pending.get("session_id") != request.get("session_id")):
        raise ValueError("request is not the current waiting model request")
    return request


def submit_response(out, request_id: str, decision: dict) -> Path:
    """Validate and exclusively publish one pending response; no device/OUT lease.

    The only mutation is response publication in an existing request directory.
    A deadline, terminal result or changed current request makes a response stale.
    """
    root, directory = _request_dir(out, request_id)
    with _mailbox_lock(directory):
        request = _pending(root, directory, request_id)
        _validate(decision, request)
        destination = directory / "response.json"
        _publish(destination, decision)
        return destination


def _xml_root(obs):
    raw = obs.xml.decode("utf-8", errors="replace") if isinstance(obs.xml, bytes) else obs.xml
    start = raw.find("<hierarchy")
    end = raw.rfind("</hierarchy>")
    if start < 0 or end < 0:
        raise ValueError("popup observation has no complete hierarchy")
    return ET.fromstring(raw[start:end + len("</hierarchy>")])


def _identity(obs):
    def canonical(element):
        attrs = dict(element.attrib)
        if (attrs.get("package") == "com.android.systemui"
                and attrs.get("resource-id", "").rsplit("/", 1)[-1] == "clock"):
            # Only the known system clock's volatile strings are ignored.
            for key in ("text", "content-desc"):
                if key in attrs:
                    attrs[key] = "<system-clock>"
        return [element.tag, sorted(attrs.items()), [canonical(child) for child in element]]
    hierarchy = hashlib.sha256(_json(canonical(_xml_root(obs)))).hexdigest()
    return {"hierarchy_sha256": hierarchy, "focus": asdict(obs.focus), "package": obs.package,
            "activity": obs.activity, "overlay": obs.overlay, "in_app": obs.in_app}


DIGITS = re.compile(r"\d+")


def popup_signature(obs: Obs) -> str:
    """What the popup is, not where it appeared: window kind and the visible nodes as (class, id, text) with digits
    masked. The same date panel on another day, or the same ad on another page, gets the same signature; a dialog
    with different wording does not."""
    items = sorted({(n.cls, n.rid, DIGITS.sub("#", (n.text or n.desc or "").strip()))
                    for n in obs.nodes if not n.covered})
    return hashlib.sha256(_json([obs.package, obs.activity, obs.focus.kind, bool(obs.overlay), items])).hexdigest()


def screen_fingerprint(obs: Obs) -> str:
    """Exact hierarchy + focus/window instance identity, excluding system clock text."""
    return hashlib.sha256(_json(_identity(obs))).hexdigest()


def _visibility(obs):
    elements = [el for el in _xml_root(obs).iter("node")]
    width, height = ui.screen_size(obs.nodes)
    result = {}
    for node in obs.nodes:
        bounds = node.bounds
        visible = not node.covered and elements[node.idx].get("visible-to-user") != "false"
        enabled = node.enabled
        x1, y1, x2, y2 = max(0, bounds[0]), max(0, bounds[1]), min(width, bounds[2]), min(height, bounds[3])
        for ancestor in ui.ancestors(obs.nodes, node):
            visible = visible and not ancestor.covered and elements[ancestor.idx].get("visible-to-user") != "false"
            enabled = enabled and ancestor.enabled
            ax1, ay1, ax2, ay2 = ancestor.bounds
            x1, y1, x2, y2 = max(x1, ax1), max(y1, ay1), min(x2, ax2), min(y2, ay2)
        result[node.idx] = (visible and x2 > x1 and y2 > y1, enabled, (x1, y1, x2, y2))
    return result


def _matches(node, selector):
    return all(getattr(node, "cls" if key == "class" else key) == value for key, value in selector.items())


def _target(obs, selector):
    visibility = _visibility(obs)
    matches = [n for n in obs.nodes if _matches(n, selector) and visibility[n.idx][0]]
    if len(matches) != 1:
        raise ValueError(f"selector has {len(matches)} visible matches; exactly one required")
    node = matches[0]
    if not visibility[node.idx][1]:
        raise ValueError("selector target is disabled")
    target = next((n for n in [node, *ui.ancestors(obs.nodes, node)]
                   if n.clickable and n.package == node.package), None)
    if target is None or not all(visibility[target.idx][:2]):
        raise ValueError("selector has no enabled visible clickable target/ancestor")
    if target is node:
        x, y = ui.tap_point(obs.nodes, node)
    else:
        x1, y1, x2, y2 = visibility[node.idx][2]
        x, y = (x1 + x2) // 2, (y1 + y2) // 2
    x1, y1, x2, y2 = visibility[target.idx][2]
    if not x1 <= x < x2 or not y1 <= y < y2:
        raise ValueError("tap point is outside the visible clickable target")
    allowed = {node.idx, target.idx, *(n.idx for n in ui.ancestors(obs.nodes, node))}
    for other in obs.nodes:
        if (other.idx not in allowed and other.clickable and visibility[other.idx][0]
                and target.idx in {n.idx for n in ui.ancestors(obs.nodes, other)}):
            ox1, oy1, ox2, oy2 = visibility[other.idx][2]
            if ox1 <= x < ox2 and oy1 <= y < oy2:
                raise ValueError("tap point is intercepted by a different clickable descendant")
    return x, y


def _controls(obs):
    visibility = _visibility(obs)
    controls, outline = [], []
    for node in obs.nodes:
        visible, enabled, bounds = visibility[node.idx]
        if not visible:
            continue
        selector = {key: value for key, value in (("rid", node.rid), ("text", node.text),
                    ("desc", node.desc), ("class", node.cls)) if value}
        actionable = bool(node.clickable or any(a.clickable for a in ui.ancestors(obs.nodes, node)))
        if node.text or node.desc or node.clickable:
            outline.append(f"{node.cls} rid={node.rid!r} text={node.text!r} desc={node.desc!r} enabled={enabled}")
        if selector and (node.text or node.desc or actionable):
            controls.append({"selector": selector, "enabled": enabled, "clickable": node.clickable,
                             "clickable_ancestor": actionable and not node.clickable, "bounds": list(bounds)})
    return controls, "\n".join(outline)


class PopupBridge:
    def __init__(self, dev, store, package, *, timeout_s=180, log=print, responder=None):
        if not math.isfinite(timeout_s) or timeout_s < 0:
            raise ValueError("model timeout must be finite and nonnegative")
        self.dev, self.store, self.package = dev, store, package
        self.timeout_s, self.log, self.responder = timeout_s, log, responder
        self.rules_path = self.store.aft / "popup_rules.json"

    def _context(self, state, phase, context):
        return _copy({"package": self.package, "phase": phase, "app": state.get("app"),
                      "dpi": state.get("density"), "baseline": state.get("baseline"),
                      "drift": state.get("drift"), "context": context})

    def _rules(self):
        if not self.rules_path.exists():
            return {}
        data = _read(self.rules_path)
        if not isinstance(data, dict) or data.get("schema_version") != 1 or not isinstance(data.get("rules"), dict):
            raise ValueError("invalid popup_rules.json")
        return data["rules"]

    def _save_rules(self, rules):
        descriptor, name = tempfile.mkstemp(prefix=".popup_rules.", dir=self.store.aft)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(_json({"schema_version": 1, "rules": rules}))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.rules_path)
        finally:
            Path(name).unlink(missing_ok=True)

    def _event(self, kind, data):
        self.store.event(kind, data)

    def _finish(self, state, save, directory, request, status, reason, *, after=None, decision=None, **extra):
        result = {"request_id": request["request_id"], "session_id": request["session_id"],
                  "fingerprint": request["fingerprint"], "status": status, "reason": reason,
                  "completed_at": utc_now(), **extra}
        if decision is not None:
            result["action"] = decision["action"]
            result["expect"] = decision["expect"]
        if after is not None:
            result["after_fingerprint"] = screen_fingerprint(after)
            _write_new(directory / "after.xml", after.xml)
            try:
                _write_new(directory / "after.png", self.dev.screencap("model_after"))
            except Exception as exc:
                result["after_screenshot_error"] = str(exc)
        with _mailbox_lock(directory):
            _publish(directory / "result.json", result)
        state["model_request"].update(status=status, result_path=str(directory / "result.json"))
        state["popup_last_result"] = result
        state["status"] = "blocked_user" if status == "handoff" else (
            "paused_model" if status in ("timeout", "failed") else "running")
        self._event("model_result", result)
        save()

    def _failure(self, state, key):
        record = state.setdefault("popup_attempts", {}).setdefault(key, {"failures": 0})
        record["failures"] += 1
        state["popup_stats"]["failures"] += 1

    def _perform(self, obs, state, request, decision, observe, cached=False):
        action = decision["action"]
        kind = action["type"]
        if kind == "handoff":
            return obs, "handoff"
        # Cached continue already matched this observation and adds no dumps.
        fresh = obs if cached and kind == "continue" else observe("model_validate")
        if fresh is None:
            raise ValueError("fresh observation unavailable before model action")
        if (screen_fingerprint(fresh) != request["fingerprint"]
                or self._context(state, request["phase"], request["context"]) != request["cache_context"]):
            return fresh, "stale"
        if kind == "continue":
            return fresh, "continued"
        if kind == "tap":
            x, y = _target(fresh, action["selector"])
            self.dev.tap(x, y, "model_popup")
        elif kind == "back":
            self.dev.back("model_popup")
        else:
            self.dev.pause(action["seconds"], "model_popup")
        state["popup_stats"]["actions"] += 1
        after = observe("model_verify")
        if after is None:
            raise ValueError("fresh observation unavailable after model action")
        changed = screen_fingerprint(after) != request["fingerprint"]
        expect = decision["expect"]
        verified = changed
        if "changed" not in expect:
            key = "present" if "present" in expect else "absent"
            visible = _visibility(after)
            found = any(_matches(n, expect[key]["selector"]) and visible[n.idx][0] for n in after.nodes)
            verified = changed and (found if key == "present" else not found)
        if not verified:
            return after, "failed"
        return after, "verified"

    def handle(self, obs, state, *, phase, observe, save, context=None, previous_failure=None):
        stats = state.setdefault("popup_stats", {})
        for name in ("requests", "cache_hits", "actions", "wait_s", "timeouts", "failures", "stale", "continues", "handoffs"):
            stats.setdefault(name, 0)
        fingerprint = screen_fingerprint(obs)
        cache_context = self._context(state, phase, context)
        key = hashlib.sha256(_json([fingerprint, cache_context])).hexdigest()
        # Remembered decisions are found by what the popup is (same app build and density), not by the page stack,
        # trigger or exact texts: those would make every date panel a new question.
        signature = popup_signature(obs)
        app = state.get("app") or {}
        build = {k: app.get(k) for k in ("versionName", "versionCode")}  # not lastUpdateTime: a reinstall keeps rules
        rule_key = hashlib.sha256(_json([signature, build, state.get("density"), self.package])).hexdigest()
        attempts = state.setdefault("popup_attempts", {}).get(key, {})
        if attempts.get("handoff") or attempts.get("failures", 0) >= 3:
            status = "blocked_user" if attempts.get("handoff") else "paused_model"
            state["status"] = status
            save()
            raise PopupStop(status, "unchanged_handoff" if attempts.get("handoff") else "retry_limit")
        request = {"fingerprint": fingerprint, "phase": phase, "context": _copy(context),
                   "cache_context": cache_context}
        try:
            rules = self._rules()
        except Exception as exc:
            self._failure(state, key)
            state["status"] = "paused_model"
            save()
            raise PopupStop("paused_model", f"invalid_popup_cache: {exc}") from exc
        if rule_key in rules:
            rule = rules[rule_key]
            cached_request = {**request, "request_id": "cache"}
            decision = None
            try:
                if rule.get("signature") != signature:
                    raise ValueError("cached rule signature does not match its key")
                decision = {**rule["decision"], "request_id": "cache", "fingerprint": fingerprint}
                _validate(decision, cached_request)
                if decision["action"]["type"] not in ("tap", "back", "continue") or not decision["remember"]:
                    raise ValueError("cached rule is not a remembered tap/back/continue decision")
                after, status = self._perform(obs, state, cached_request, decision, observe, cached=True)
            except Exception as exc:
                after, status = obs, "failed"
                reason = str(exc)
            else:
                reason = decision["reason"] if status != "failed" else "postcondition_not_met_or_unchanged"
            stats["cache_hits"] += 1
            cached_result = {"fingerprint": fingerprint, "phase": phase, "cached": True,
                             "status": status, "reason": reason,
                             "action": decision.get("action") if decision else None}
            state["popup_last_result"] = cached_result
            self._event("model_cache_result", cached_result)
            if status == "failed":
                # The remembered decision no longer fits (a countdown "跳过 5" became "跳过 4"): forget it and ask
                # the model now, in this call, instead of ending the run.
                del rules[rule_key]
                self._save_rules(rules)
                self._failure(state, key)
                self._event("model_cache_dropped", {"reason": reason})
                state["status"] = "running"
                save()
                fresh = after if after is not None else obs
                return self.handle(fresh, state, phase=phase, observe=observe, save=save, context=context,
                                   previous_failure=f"remembered rule failed: {reason}")
            if status == "stale":
                stats["stale"] += 1
            if status == "continued":
                stats["continues"] += 1
            state["status"] = "running"
            save()
            return after

        request_id = uuid.uuid4().hex
        _, directory = _request_dir(self.store.out, request_id)
        directory.mkdir(parents=True, exist_ok=False)
        _write_new(directory / "mailbox.lock", b" ")
        controls, outline = _controls(obs)
        request.update(schema_version=1, status="pending", request_id=request_id, session_id=self.store.session_id,
                       created_at=utc_now(), deadline_wall_time=time.time() + self.timeout_s,
                       package=self.package, activity=obs.activity, focus=asdict(obs.focus),
                       token=obs.focus.token, hierarchy_identity=_identity(obs), app=state.get("app"),
                       dpi=state.get("density"), baseline=state.get("baseline"), drift=state.get("drift"),
                       visible_outline=outline, controls=controls, previous_failure=previous_failure,
                       before_xml=str(directory / "before.xml"), before_png=str(directory / "before.png"))
        _write_new(directory / "before.xml", obs.xml)
        _publish(directory / "request.json", request)
        state["model_request"] = {"request_id": request_id, "request_path": str(directory / "request.json"),
                                  "session_id": self.store.session_id, "fingerprint": fingerprint,
                                  "phase": phase, "status": "waiting_model"}
        stats["requests"] += 1
        try:
            _write_new(directory / "before.png", self.dev.screencap("model_request"))
        except Exception as exc:
            self._failure(state, key)
            reason = f"request_screenshot_failed: {exc}"
            self._finish(state, save, directory, request, "failed", reason)
            raise PopupStop("paused_model", reason) from exc
        state["status"] = "waiting_model"
        save()
        self._event("model_request", {"request_id": request_id, "request_path": str(directory / "request.json"),
                                     "fingerprint": fingerprint, "phase": phase})
        # The handshake must be flushed even when stdout is piped to a supervisor.
        message = f"AFT_MODEL_REQUEST {directory / 'request.json'}"
        if self.log is print:
            print(message, flush=True)
        else:
            self.log(message)
            import sys
            sys.stdout.flush()
        t0 = time.monotonic()
        decision = None
        try:
            if self.responder is not None:
                supplied = self.responder(_copy(request))
                if supplied is not None:
                    submit_response(self.store.out, request_id, supplied)
            response_path = directory / "response.json"
            while not response_path.exists():
                remaining = request["deadline_wall_time"] - time.time()
                if remaining <= 0:
                    stats["timeouts"] += 1
                    self._finish(state, save, directory, request, "timeout", "model_response_timeout")
                    raise PopupStop("paused_model", "model_response_timeout")
                time.sleep(min(0.1, remaining))
            with _mailbox_lock(directory):
                _pending(self.store.out, directory, request_id)
                if response_path.is_symlink():
                    raise ValueError("response.json must not be a symlink")
                decision = _read(response_path)
                _validate(decision, request)
        except KeyboardInterrupt:
            stats["interrupted"] = stats.get("interrupted", 0) + 1
            self._finish(state, save, directory, request, "failed", "model_wait_interrupted")
            raise
        except PopupStop:
            raise
        except Exception as exc:
            self._failure(state, key)
            reason = f"invalid_model_response: {exc}"
            self._finish(state, save, directory, request, "failed", reason)
            raise PopupStop("paused_model", reason) from exc
        finally:
            stats["wait_s"] = round(stats["wait_s"] + time.monotonic() - t0, 6)
            save()

        try:
            after, status = self._perform(obs, state, request, decision, observe)
        except KeyboardInterrupt:
            stats["interrupted"] = stats.get("interrupted", 0) + 1
            self._finish(state, save, directory, request, "failed", "model_action_interrupted", decision=decision)
            raise
        except Exception as exc:
            after, status = None, "failed"
            reason = f"model_action_failed: {exc}"
        else:
            reason = decision["reason"] if status != "failed" else "postcondition_not_met_or_unchanged"
        if status == "failed":
            self._failure(state, key)
        elif status == "handoff":
            stats["handoffs"] += 1
            state.setdefault("popup_attempts", {}).setdefault(key, {"failures": 0})["handoff"] = True
        elif status == "stale":
            stats["stale"] += 1
        elif status == "continued":
            stats["continues"] += 1
        # Only proved actions or explicit continue can become exact-screen rules.
        if status in ("verified", "continued") and decision["remember"]:
            rules[rule_key] = {"signature": signature, "fingerprint": fingerprint, "context": cache_context,
                               "decision": decision, "verified_at": utc_now(), "source_request": request_id}
            self._save_rules(rules)
        self._finish(state, save, directory, request, status, reason, after=after, decision=decision)
        if status in ("failed", "handoff"):
            raise PopupStop(state["status"], reason)
        return after
