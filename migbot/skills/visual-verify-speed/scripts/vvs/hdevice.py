"""HarmonyOS device layer: one hdc owner, counted operations, focus from the dump itself.

Every command goes through HDevice._cmd so the report can split device time by purpose, like the Android walk.
"""
from __future__ import annotations

import os
import re
import shlex
import struct
import subprocess
import tempfile
import time
from dataclasses import dataclass, field

from . import hui


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


def png_size(data: bytes) -> tuple:
    if not data.startswith(b"\x89PNG\r\n\x1a\n") or len(data) < 33 or data[12:16] != b"IHDR":
        raise DeviceError("invalid PNG")
    return struct.unpack(">II", data[16:24])


@dataclass
class Obs:
    seq: int
    raw: bytes
    nodes: list
    windows: list
    bundle: str           # owner of the focused window
    page_path: str
    ability: str
    in_app: bool
    overlay: str          # '' | 'layer' (same-window dialog) | 'win' (app sub-window) | 'permission'
    elapsed: float
    _structure: frozenset | None = field(default=None, repr=False)

    def structure(self, bundle: str) -> frozenset:
        if self._structure is None:
            self._structure = hui.structure(self.nodes, bundle)
        return self._structure

    def identity(self) -> dict:
        return {"seq": self.seq, "bundle": self.bundle, "page_path": self.page_path, "ability": self.ability,
                "in_app": self.in_app, "overlay": self.overlay}


def focus_of(nodes: list, windows: list, bundle: str) -> tuple:
    """(owner bundle, page_path, ability, in_app, overlay) from the windows of one dump."""
    w, h = hui.screen_size(nodes)
    full = 0.5 * w * h

    def area(win):
        x1, y1, x2, y2 = win.bounds
        return max(0, x2 - x1) * max(0, y2 - y1)
    focused = [x for x in windows if x.focused and x.bundle not in ("com.ohos.systemui",)]
    win = focused[-1] if focused else None
    if win is None:
        big = [x for x in windows if area(x) >= full]
        win = big[-1] if big else (windows[-1] if windows else None)
    if win is None:
        return "", "", "", False, ""
    if win.bundle in hui.PERMISSION_BUNDLES:
        return win.bundle, win.page_path, win.ability, False, "permission"
    if win.bundle != bundle:
        # A small foreign window (status bar, toast) does not take the app away; a full-screen one does.
        app = [x for x in windows if x.bundle == bundle and area(x) >= full]
        if app and area(win) < full:
            win = app[-1]
        else:
            return win.bundle, win.page_path, win.ability, False, ""
    main = max((x for x in windows if x.bundle == bundle), key=area)
    overlay = ""
    if win is not main and area(win) < 0.9 * area(main):
        overlay = "win"
    elif hui.layered(nodes):
        overlay = "layer"
    page = win.page_path or main.page_path
    return win.bundle, page, win.ability or main.ability, True, overlay


class HDevice:
    def __init__(self, target: str, bundle: str, ability: str = "", backend=None, hdc: str = "hdc",
                 sleep=time.sleep, clock=time.monotonic, on_event=None, timeout: float = 30.0):
        self.target, self.bundle, self.ability, self.hdc = target, bundle, ability, hdc
        self.backend = backend or subprocess_backend
        self.sleep, self.clock = sleep, clock
        self.on_event = on_event or (lambda kind, data: None)
        self.timeout = timeout
        self.seq = 0
        self.counters: dict = {"ops": {}, "time": {}, "purpose": {}, "purpose_time": {}}
        self.settle_s = 0.8
        self.swipe_velocity = 1500
        self.last_input = ("", "")
        self.last_tap = None
        self._screencap_png = True

    # ---- plumbing
    def _count(self, op: str, purpose: str, elapsed: float) -> None:
        c = self.counters
        c["ops"][op] = c["ops"].get(op, 0) + 1
        c["time"][op] = round(c["time"].get(op, 0.0) + elapsed, 4)
        key = f"{op}:{purpose}"
        c["purpose"][key] = c["purpose"].get(key, 0) + 1
        c["purpose_time"][key] = round(c["purpose_time"].get(key, 0.0) + elapsed, 4)

    def _argv(self, args: list) -> list:
        return [self.hdc, *(["-t", self.target] if self.target else []), *args]

    def _cmd(self, args: list, op: str, purpose: str = "", timeout: float | None = None, check_text=True) -> bytes:
        t0 = self.clock()
        rc, out, err = self.backend(self._argv(args), timeout or self.timeout)
        elapsed = self.clock() - t0
        self._count(op, purpose or op, elapsed)
        text = (out or b"")[-400:].decode(errors="replace")
        # hdc returns 0 even for many failures; known failure texts count as errors.
        failed = rc != 0 or (check_text and re.search(r"\[Fail\]|error:|Error:|not found|No such file|failed", text)
                             and op not in ("dump",))
        if failed:
            self.on_event("command_failed", {"op": op, "purpose": purpose, "rc": rc,
                                             "out": text[-300:], "err": (err or b"")[-200:].decode(errors="replace")})
            raise DeviceError(f"{op} failed rc={rc}: {text[-200:]} {(err or b'')[-200:].decode(errors='replace')}")
        return out or b""

    def shell(self, cmd: str, op: str = "shell", purpose: str = "", timeout: float | None = None,
              check_text: bool = True) -> bytes:
        return self._cmd(["shell", cmd], op, purpose, timeout, check_text)

    def crash_logs(self, purpose: str = "crash_log") -> list:
        """Newest-first device fault-log files of this app (JS / native crashes); [] when none or unreadable."""
        try:
            out = self.shell("ls -t /data/log/faultlog/faultlogger/", "shell", purpose).decode("utf-8", "replace")
        except Exception:
            return []
        return ["/data/log/faultlog/faultlogger/" + x.strip() for x in out.split() if self.bundle in x][:3]

    def pause(self, seconds: float, purpose: str) -> None:
        t0 = self.clock()
        self.sleep(seconds)
        self._count("pause", purpose, self.clock() - t0)

    # ---- observation
    def dump(self, purpose: str) -> Obs:
        last = None
        for attempt in range(3):
            self.seq += 1
            remote = f"/data/local/tmp/vvs_{self.seq}.json"
            t0 = self.clock()
            try:
                raw = self.shell(f"uitest dumpLayout -i -p {remote} >/dev/null 2>&1; cat {remote}; rm -f {remote}",
                                 op="dump", purpose=purpose, check_text=False)
            except DeviceError as exc:
                last = exc
                self.pause(0.6, "retry")
                continue
            elapsed = self.clock() - t0
            try:
                nodes, windows = hui.parse(raw)
            except Exception as exc:  # empty window, truncated JSON, uitest busy
                last = exc
                self.on_event("dump_retry", {"purpose": purpose, "attempt": attempt + 1, "error": str(exc)[:200]})
                self.pause(0.8 if attempt == 0 else 1.5, "retry")
                continue
            owner, page, ability, in_app, overlay = focus_of(nodes, windows, self.bundle)
            starts = [i for i in (raw.find(b"{"), raw.find(b"[")) if i >= 0]
            start = min(starts) if starts else 0
            return Obs(self.seq, raw[start:], nodes, windows, owner, page, ability, in_app, overlay, elapsed)
        raise DumpError(f"dump failed 3 times: {last}")

    def screencap(self, purpose: str = "capture") -> bytes:
        """PNG of the screen (uitest screenCap); JPEG snapshot_display converted to PNG as the fallback."""
        last = None
        for attempt in range(2):
            self.seq += 1
            try:
                if self._screencap_png:
                    remote = f"/data/local/tmp/vvs_shot_{self.seq}.png"
                    self.shell(f"uitest screenCap -p {remote}", op="png", purpose=purpose, check_text=False)
                else:
                    remote = f"/data/local/tmp/vvs_shot_{self.seq}.jpeg"
                    self.shell(f"snapshot_display -f {remote}", op="png", purpose=purpose, check_text=False)
                data = self._recv(remote, purpose)
                self.shell(f"rm -f {remote}", op="rm", purpose=purpose, check_text=False)
                if not data.startswith(b"\x89PNG"):
                    data = to_png(data)
                png_size(data)
                return data
            except DeviceError as exc:
                last = exc
                self.on_event("screencap_retry", {"purpose": purpose, "attempt": attempt + 1, "error": str(exc)[:200]})
                self._screencap_png = not self._screencap_png
                self.pause(0.3, "retry")
        raise DeviceError(f"screencap failed twice: {last}")

    def _recv(self, remote: str, purpose: str) -> bytes:
        fd, local = tempfile.mkstemp(prefix="vvs_", suffix=os.path.splitext(remote)[1])
        os.close(fd)
        try:
            self._cmd(["file", "recv", remote, local], "recv", purpose, check_text=False)
            with open(local, "rb") as f:
                data = f.read()
            if not data:
                raise DeviceError(f"empty file from {remote}")
            return data
        finally:
            try:
                os.unlink(local)
            except OSError:
                pass

    # ---- input
    def tap(self, x: int, y: int, purpose: str = "tap") -> None:
        self.shell(f"uitest uiInput click {int(x)} {int(y)}", op="tap", purpose=purpose)
        self.last_input, self.last_tap = ("tap", purpose), (int(x), int(y))
        self.pause(self.settle_s, purpose)

    def long_press(self, x: int, y: int, purpose: str = "tap") -> None:
        self.shell(f"uitest uiInput longClick {int(x)} {int(y)}", op="tap", purpose=purpose)
        self.last_input, self.last_tap = ("tap", purpose), (int(x), int(y))
        self.pause(self.settle_s, purpose)

    def swipe(self, x1, y1, x2, y2, purpose: str = "scroll", velocity: int | None = None) -> None:
        v = int(velocity or self.swipe_velocity)
        self.shell(f"uitest uiInput swipe {int(x1)} {int(y1)} {int(x2)} {int(y2)} {v}", op="swipe", purpose=purpose)
        self.last_input = ("swipe", purpose)
        self.pause(0.45, purpose)

    def back(self, purpose: str = "return") -> None:
        self.shell("uitest uiInput keyEvent Back", op="back", purpose=purpose)
        self.last_input = ("back", purpose)
        self.pause(self.settle_s, purpose)

    def input_text(self, text: str, purpose: str = "drive", xy: tuple | None = None) -> None:
        """Type into the field at xy (default: the last tap). `uiInput text` reports success without typing on
        some builds, so inputText at the field's coordinates is the primary way; it also takes Chinese."""
        q = shlex.quote(text)
        xy = xy or self.last_tap
        if xy:
            self.shell(f"uitest uiInput inputText {int(xy[0])} {int(xy[1])} {q}", op="text", purpose=purpose)
        else:
            self.shell(f"uitest uiInput text {q}", op="text", purpose=purpose)
        self.last_input = ("text", purpose)
        self.pause(self.settle_s, purpose)

    # ---- app lifecycle
    def force_stop(self, purpose: str = "restart") -> None:
        self.shell(f"aa force-stop {shlex.quote(self.bundle)}", op="force_stop", purpose=purpose, check_text=False)
        self.last_input = ("force_stop", purpose)

    def start(self, purpose: str = "restart") -> None:
        if not self.ability:
            raise DeviceError("launch ability unknown: pass --ability or set it in the HarmonyOS profile")
        self.shell(f"aa start -a {shlex.quote(self.ability)} -b {shlex.quote(self.bundle)}", op="start",
                   purpose=purpose)
        self.last_input = ("start", purpose)
        self.pause(1.2, purpose)

    def clear_data(self, purpose: str = "setup") -> None:
        self.shell(f"bm clean -n {shlex.quote(self.bundle)} -d", op="clear", purpose=purpose)

    def install(self, hap: str, purpose: str = "install") -> str:
        out = self._cmd(["install", "-r", hap], "install", purpose, timeout=180, check_text=False)
        text = out.decode(errors="replace")
        if "success" not in text.lower():
            raise DeviceError(f"install failed: {text[-300:]}")
        return text

    def density(self) -> float | None:
        probes = (("hidumper -s DisplayManagerService -a -a",
                   r"(?i)(?:virtualPixelRatio|densityInCurResolution|density)\s*[:=]\s*([0-9.]+)"),
                  ("param get const.product.densitydpi", r"^\s*(\d{3})\s*$"))
        for cmd, pat in probes:
            try:
                out = self.shell(cmd, op="density", purpose="setup", check_text=False).decode(errors="replace")
            except DeviceError:
                continue
            for m in re.finditer(pat, out, re.M):
                v = float(m.group(1))
                if v >= 100:
                    v = v / 160.0
                if 1.0 <= v <= 6.0:
                    return round(v, 3)
        return None

    def app_version(self) -> dict:
        try:
            out = self.shell(f"bm dump -n {shlex.quote(self.bundle)}", op="version", purpose="setup",
                             check_text=False).decode(errors="replace")
        except DeviceError:
            return {}
        info = {}
        for key in ("versionName", "versionCode", "installTime", "updateTime"):
            m = re.search(r'"' + key + r'"\s*:\s*"?([^",\n]+)', out)
            if m:
                info[key] = m.group(1).strip()
        return info

    def main_ability(self) -> str:
        """The launcher ability from bm dump (mainAbility / first ability with entities 'entity.system.home')."""
        try:
            out = self.shell(f"bm dump -n {shlex.quote(self.bundle)}", op="version", purpose="setup",
                             check_text=False).decode(errors="replace")
        except DeviceError:
            return ""
        m = re.search(r'"mainAbility"\s*:\s*"([^"]+)"', out) or re.search(r'"mainElementName"\s*:\s*"([^"]+)"', out)
        if m:
            return m.group(1)
        m = re.search(r'"name"\s*:\s*"(\w*Ability)"', out)
        return m.group(1) if m else ""


def to_png(data: bytes) -> bytes:
    try:
        from PIL import Image
        import io
        im = Image.open(io.BytesIO(data))
        buf = io.BytesIO()
        im.convert("RGB").save(buf, format="PNG")
        return buf.getvalue()
    except Exception as exc:
        raise DeviceError(f"cannot convert screenshot to PNG: {exc}") from exc
