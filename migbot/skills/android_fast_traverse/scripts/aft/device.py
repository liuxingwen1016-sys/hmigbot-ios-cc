"""Device layer: one ADB owner, counted operations, robust focus parsing.

Every device command goes through Device._cmd so state.json device_counters can prove the
cost invariants (dumps per explored candidate, no per-candidate restarts).
"""
from __future__ import annotations

import re
import shlex
import struct
import subprocess
import time
from dataclasses import dataclass, field

from . import ui

MARK = "__AFT_FOCUS__"
FOCUS_GREP = "dumpsys window | grep -E 'WINDOW MANAGER|mCurrentFocus|mFocusedApp'"


class DeviceError(RuntimeError):
    pass


class DumpError(DeviceError):
    pass


def subprocess_backend(argv: list, timeout: float):
    try:
        r = subprocess.run(argv, capture_output=True, timeout=timeout, check=False)
        return r.returncode, r.stdout or b"", r.stderr or b""
    except subprocess.TimeoutExpired as exc:
        return 124, exc.stdout or b"", (exc.stderr or b"") + b"\ntimeout"


# ---------------------------------------------------------------- focus parsing

@dataclass
class Focus:
    kind: str            # activity | popup | dialog | anr | ime | none | other
    package: str
    activity: str        # full class name ('' when unknown)
    window: str          # raw window title
    focused_app: str = ""  # package/activity from mFocusedApp
    token: str = ""        # window token: changes when a new activity instance takes focus

    @property
    def short_activity(self) -> str:
        return self.activity.rsplit(".", 1)[-1] if self.activity else ""


WINDOW_RE = re.compile(r"mCurrentFocus=(?:Window\{(?P<tok>[0-9a-f]+) u\d+ (?P<title>[^}]*)\}|(?P<null>null))")
APP_RE = re.compile(r"mFocusedApp=(?:ActivityRecord|AppWindowToken)\{[^}]*? u\d+ (?P<comp>[\w.$]+/[\w.$]+)")


def live_focus_section(text: str) -> str:
    """Return the live section that holds mCurrentFocus.

    `dumpsys window` starts with a 'LAST ANR' snapshot that embeds its own
    DISPLAY CONTENTS section with a stale mCurrentFocus. Live sections always
    follow it, so scan sections from the end and take the first one that has
    focus lines (DISPLAY CONTENTS on new builds, WINDOWS on old builds).
    """
    lines = text.splitlines()
    starts = [i for i, l in enumerate(lines) if l.strip().startswith("WINDOW MANAGER ")]
    if not starts:
        return text
    bounds = list(zip(starts, starts[1:] + [len(lines)]))
    for a, b in reversed(bounds):
        if "LAST ANR" in lines[a]:
            continue
        chunk = lines[a:b]
        if any("mCurrentFocus" in l for l in chunk):
            return "\n".join(chunk)
    return ""


def _normalize_component(comp: str) -> tuple:
    pkg, cls = comp.split("/", 1)
    if cls.startswith("."):
        cls = pkg + cls
    return pkg, cls


def parse_focus(text: str, package: str) -> Focus:
    f, tokens = _parse_focus(live_focus_section(text), package)
    f.token = tokens.get(f.window, "")
    return f


def _parse_focus(text: str, package: str):
    windows, apps, tokens = [], [], {}
    for line in text.splitlines():
        m = WINDOW_RE.search(line)
        if m:
            windows.append(None if m.group("null") else m.group("title").strip())
            if not m.group("null"):
                tokens[m.group("title").strip()] = m.group("tok")
        a = APP_RE.search(line)
        if a:
            apps.append(a.group("comp"))
    app = next((c for c in apps if c.startswith(package + "/")), apps[0] if apps else "")
    titles = [w for w in windows if w]
    title = next((w for w in titles if package in w), titles[0] if titles else None)
    focused_app = app
    if title is None:
        if app:
            pkg, cls = _normalize_component(app)
            return Focus("none", pkg, cls, "", focused_app), tokens
        return Focus("none", "", "", "", focused_app), tokens
    if "Not Responding" in title:
        pkg = title.rsplit(":", 1)[-1].strip()
        return Focus("anr", pkg, "", title, focused_app), tokens
    m = re.fullmatch(r"([\w.$]+)/([\w.$]+)", title)
    if m:
        pkg, cls = _normalize_component(title)
        return Focus("activity", pkg, cls, title, focused_app), tokens
    app_pkg, app_cls = _normalize_component(app) if app else ("", "")
    if title.startswith("PopupWindow"):
        return Focus("popup", app_pkg, app_cls, title, focused_app), tokens
    if title == "InputMethod":
        return Focus("ime", app_pkg, app_cls, title, focused_app), tokens
    if re.fullmatch(r"[\w.$]+", title) and "." in title:
        # Dialog windows are titled by package name on many builds.
        return Focus("dialog", title, app_cls if app_pkg == title else "", title, focused_app), tokens
    return Focus("other", app_pkg, app_cls, title, focused_app), tokens


# ---------------------------------------------------------------- PNG check

def png_size(data: bytes) -> tuple:
    if not data.startswith(b"\x89PNG\r\n\x1a\n") or len(data) < 33 or data[12:16] != b"IHDR":
        raise DeviceError("invalid PNG")
    return struct.unpack(">II", data[16:24])


# ---------------------------------------------------------------- observation

@dataclass
class Obs:
    seq: int
    xml: bytes
    nodes: list
    focus: Focus
    package: str          # target package when the target app owns the foreground
    activity: str         # short activity name for the page key ('' if unknown)
    overlay: str          # '' | popup | dialog
    in_app: bool
    elapsed: float
    _structure: frozenset | None = field(default=None, repr=False)
    retried: bool = False  # the dump needed another attempt: the screen was busy (loading, mid-transition)

    def structure(self, package: str) -> frozenset:
        if self._structure is None:
            self._structure = ui.structure(self.nodes, package)
        return self._structure


class Device:
    def __init__(self, serial: str, package: str, backend=None, adb: str = "adb",
                 sleep=time.sleep, clock=time.monotonic, on_event=None, timeout: float = 30.0):
        self.serial, self.package, self.adb = serial, package, adb
        self.backend = backend or subprocess_backend
        self.sleep, self.clock = sleep, clock
        self.on_event = on_event or (lambda kind, data: None)
        self.timeout = timeout
        self.seq = 0
        self.counters: dict = {"ops": {}, "time": {}, "purpose": {}, "purpose_time": {}}
        self.last_activity = ""
        self.settle_s = 0.35
        self.last_input = ("", "")  # (op, purpose) of the last input sent: was the screen changed by our own tap?

    # ---- plumbing
    def _count(self, op: str, purpose: str, elapsed: float) -> None:
        c = self.counters
        c["ops"][op] = c["ops"].get(op, 0) + 1
        c["time"][op] = round(c["time"].get(op, 0.0) + elapsed, 4)
        key = f"{op}:{purpose}"
        c["purpose"][key] = c["purpose"].get(key, 0) + 1
        c["purpose_time"][key] = round(c["purpose_time"].get(key, 0.0) + elapsed, 4)

    def _cmd(self, args: list, op: str, purpose: str = "", timeout: float | None = None) -> bytes:
        argv = [self.adb, "-s", self.serial, *args]
        t0 = self.clock()
        rc, out, err = self.backend(argv, timeout or self.timeout)
        elapsed = self.clock() - t0
        self._count(op, purpose or op, elapsed)
        if rc != 0:
            self.on_event("command_failed", {"op": op, "purpose": purpose, "rc": rc,
                                             "stderr": (err or b"")[-300:].decode(errors="replace")})
            raise DeviceError(f"{op} failed rc={rc}: {(err or b'')[-200:].decode(errors='replace')}")
        return out

    def shell(self, cmd: str, op: str = "shell", purpose: str = "") -> bytes:
        return self._cmd(["shell", cmd], op, purpose)

    # ---- observation
    def focus(self, purpose: str = "ready") -> Focus:
        out = self._cmd(["shell", FOCUS_GREP], "focus", purpose)
        return parse_focus(out.decode(errors="replace"), self.package)

    def dump(self, purpose: str) -> Obs:
        """uiautomator dump + focus. A failed dump (no idle state) is retried once; a third time, after a longer
        pause, when an activity of the app holds the focus (a WebView still loading), instead of a cold start."""
        last_error, tries = None, 0
        for attempt in range(3):
            if attempt == 2 and not (focus.kind == "activity" and focus.package == self.package):
                break
            tries += 1
            self.seq += 1
            remote = f"/data/local/tmp/aft_{self.seq}.xml"
            script = (f"uiautomator dump {remote} >/dev/null 2>&1; cat {remote} 2>/dev/null; rm -f {remote}; "
                      f"echo; echo {MARK}; {FOCUS_GREP}")
            t0 = self.clock()
            raw = self._cmd(["exec-out", "sh -c " + shlex.quote(script)], "dump", purpose)
            elapsed = self.clock() - t0
            text = raw.decode("utf-8", errors="replace")
            xml_part, _, focus_part = text.partition("\n" + MARK + "\n")
            focus = parse_focus(focus_part, self.package)
            try:
                nodes = ui.parse(xml_part)
            except Exception as exc:  # idle-state failures, empty window, truncated output
                last_error = exc
                self.on_event("dump_retry", {"purpose": purpose, "attempt": attempt + 1, "error": str(exc)[:200],
                                             "focus": focus.window})
                busy_app = attempt == 1 and focus.kind == "activity" and focus.package == self.package
                self.pause(1.5 if busy_app else 0.6, "retry")
                continue
            obs = self._obs(xml_part.encode("utf-8"), nodes, focus, elapsed)
            obs.retried = attempt > 0
            return obs
        raise DumpError(f"dump failed {tries} times: {last_error}")

    def _obs(self, xml: bytes, nodes: list, focus: Focus, elapsed: float) -> Obs:
        pkg_nodes = sum(1 for n in nodes if n.package == self.package)
        majority = pkg_nodes * 2 >= len(nodes)
        overlay = ""
        if focus.kind == "activity":
            in_app = focus.package == self.package
            activity = focus.short_activity
        elif focus.kind in ("popup", "dialog"):
            in_app = (focus.package == self.package) or majority
            activity = focus.short_activity or self.last_activity
            overlay = focus.kind
        elif focus.kind == "ime":
            in_app = majority
            activity = focus.short_activity or self.last_activity
        else:  # none / other / anr: trust the hierarchy owner
            in_app = majority and focus.kind != "anr"
            activity = focus.short_activity if focus.package == self.package else self.last_activity
        if in_app and activity:
            self.last_activity = activity
        return Obs(self.seq, xml, nodes, focus, self.package if in_app else focus.package,
                   activity if in_app else "", overlay, in_app, elapsed)

    def screencap(self, purpose: str = "capture") -> bytes:
        last = None
        for attempt in range(2):
            try:
                data = self._cmd(["exec-out", "screencap -p"], "png", purpose)
                at = data.find(b"\x89PNG")
                if at > 0:
                    data = data[at:]
                png_size(data)
                return data
            except DeviceError as exc:
                last = exc
                self.on_event("screencap_retry", {"purpose": purpose, "attempt": attempt + 1, "error": str(exc)[:200]})
                self.pause(0.3, "retry")
        raise DeviceError(f"screencap failed twice: {last}")

    def pause(self, seconds: float, purpose: str) -> None:
        """A counted device-side wait (settle, splash, retry) so cost reports include it."""
        t0 = self.clock()
        self.sleep(seconds)
        self._count("pause", purpose, self.clock() - t0)

    # ---- input
    def wait_ready(self, min_wait: float = 0.25, max_wait: float = 3.0, purpose: str = "ready") -> float:
        """Poll the focused window until it is stable twice (bounded)."""
        t0 = self.clock()
        prev = None
        interval = 0.15
        while True:
            self.sleep(interval)
            elapsed = self.clock() - t0
            try:
                f = self.focus("ready")
                cur = (f.kind, f.window)
            except DeviceError:
                cur = None
            if cur is not None and cur == prev and elapsed >= min_wait:
                break
            if elapsed >= max_wait:
                break
            prev = cur
        waited = self.clock() - t0
        self._count("ready_wait", purpose, waited)
        return waited

    def tap(self, x: int, y: int, purpose: str = "tap") -> None:
        self._cmd(["shell", f"input tap {int(x)} {int(y)}"], "tap", purpose)
        self.last_input = ("tap", purpose)
        self.wait_ready(purpose=purpose)

    def long_press(self, x: int, y: int, purpose: str = "tap") -> None:
        self._cmd(["shell", f"input swipe {int(x)} {int(y)} {int(x)} {int(y)} 900"], "tap", purpose)
        self.last_input = ("tap", purpose)
        self.wait_ready(purpose=purpose)

    def swipe(self, x1, y1, x2, y2, ms: int = 300, purpose: str = "scroll") -> None:
        self._cmd(["shell", f"input swipe {int(x1)} {int(y1)} {int(x2)} {int(y2)} {int(ms)}"], "swipe", purpose)
        self.last_input = ("swipe", purpose)
        self.pause(self.settle_s, purpose)

    def back(self, purpose: str = "return") -> None:
        self._cmd(["shell", "input keyevent 4"], "back", purpose)
        self.last_input = ("back", purpose)
        self.wait_ready(purpose=purpose)

    def input_text(self, text: str, purpose: str = "drive") -> None:
        escaped = text.replace(" ", "%s")
        self._cmd(["shell", "input text " + shlex.quote(escaped)], "text", purpose)
        self.last_input = ("text", purpose)
        self.wait_ready(purpose=purpose)

    # ---- app lifecycle
    def resolve_launcher(self) -> str:
        out = self._cmd(["shell", f"cmd package resolve-activity --brief -c android.intent.category.LAUNCHER {self.package}"],
                        "resolve", "launch").decode(errors="replace")
        lines = [l.strip() for l in out.splitlines() if "/" in l]
        if not lines:
            raise DeviceError(f"cannot resolve launcher activity of {self.package}")
        return lines[-1]

    def runtime_permissions(self) -> list:
        """Runtime (dangerous) permissions the package requests, from the 'runtime permissions:' section."""
        out = self._cmd(["shell", f"dumpsys package {shlex.quote(self.package)}"], "grant", "setup").decode(errors="replace")
        perms, inside = set(), False
        for line in out.splitlines():
            s = line.strip()
            if s.startswith("runtime permissions:"):
                inside = True
                continue
            if inside:
                m = re.match(r"([\w.]+\.permission\.[\w.]+):", s)
                if m:
                    perms.add(m.group(1))
                    continue
                inside = False
        return sorted(perms)

    def grant_permissions(self, skip=lambda perm: False) -> dict:
        """Grant every runtime permission up front (test devices), so system permission prompts do not interrupt."""
        granted, failed, skipped = [], [], []
        for perm in self.runtime_permissions():
            if skip(perm):
                skipped.append(perm)
                continue
            try:
                self._cmd(["shell", f"pm grant {shlex.quote(self.package)} {perm}"], "grant", "setup")
                granted.append(perm)
            except DeviceError:
                failed.append(perm)
        return {"granted": granted, "failed": failed, "skipped": skipped}

    def force_stop(self, purpose: str = "restart") -> None:
        self._cmd(["shell", f"am force-stop {self.package}"], "force_stop", purpose)
        self.last_input = ("force_stop", purpose)

    def start(self, component: str, purpose: str = "restart") -> None:
        if not component.startswith(self.package + "/"):
            raise DeviceError("launch component must belong to the target package")
        self._cmd(["shell", f"am start -W -n {shlex.quote(component)}"], "start", purpose)
        self.last_input = ("start", purpose)
        self.wait_ready(min_wait=0.5, max_wait=5.0, purpose=purpose)

    def density(self) -> int | None:
        try:
            out = self._cmd(["shell", "wm density"], "density", "setup").decode(errors="replace")
            m = re.search(r"Override density:\s*(\d+)", out) or re.search(r"Physical density:\s*(\d+)", out)
            return int(m.group(1)) if m else None
        except DeviceError:
            return None

    def app_version(self) -> dict:
        try:
            out = self._cmd(["shell", f"dumpsys package {self.package} | grep -E 'versionName|versionCode|lastUpdateTime'"],
                            "version", "setup").decode(errors="replace")
        except DeviceError:
            return {}
        info = {}
        for key in ("versionName", "versionCode", "lastUpdateTime"):
            m = re.search(key + r"=(\S+(?: \S+)?)", out)
            if m:
                info[key] = m.group(1)
        return info
