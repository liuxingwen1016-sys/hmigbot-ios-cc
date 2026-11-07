"""Serial, timed raw observations; never navigate or register traversal pages.

Each frame is a fresh dump, then a PNG, then a focus check. These observations
are not atomic: unchanged focus cannot prove that XML and PNG show the same UI.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import struct
import tempfile
import time
import zlib
from datetime import datetime, timezone
from pathlib import Path

from . import ui
from .device import png_size


PAIRING_NOTE = (
    "XML, dump focus, PNG and post-PNG focus are captured sequentially, not atomically. "
    "A focus mismatch makes the pair unreliable; unchanged focus does not prove the "
    "same UI, especially within one Activity. Raw frames require review and are not "
    "formal page or scroll captures."
)


def _validate_png(data: bytes) -> tuple[int, int]:
    """Validate the complete PNG container and bounded IDAT stream, without decoding pixels.

    The largest transient decompression buffer is 64 KiB. Reject images declaring
    more than 256 MiB of scanline data, and abort immediately if the stream expands
    beyond its IHDR dimensions. This is deliberately local to raw burst evidence.
    """
    width, height = png_size(data)
    if width <= 0 or height <= 0 or width > 0x7fffffff or height > 0x7fffffff:
        raise ValueError("invalid PNG dimensions")
    view = memoryview(data)
    offset, expected, decoded = 8, 0, 0
    saw_header = saw_palette = saw_data = data_closed = False
    decoder = zlib.decompressobj()
    while offset < len(data):
        if len(data) - offset < 12:
            raise ValueError("truncated PNG chunk header or CRC")
        size = struct.unpack_from(">I", data, offset)[0]
        kind = data[offset + 4:offset + 8]
        end = offset + 12 + size
        if size > 0x7fffffff or end > len(data):
            raise ValueError("truncated or oversized PNG chunk")
        if not all(65 <= ch <= 90 or 97 <= ch <= 122 for ch in kind) or kind[2] & 32:
            raise ValueError("invalid PNG chunk type")
        payload = view[offset + 8:offset + 8 + size]
        stored_crc = struct.unpack_from(">I", data, offset + 8 + size)[0]
        if zlib.crc32(payload, zlib.crc32(kind)) != stored_crc:
            raise ValueError("PNG chunk CRC mismatch: " + kind.decode("ascii"))
        if not saw_header and kind != b"IHDR":
            raise ValueError("PNG must begin with IHDR")
        if kind == b"IHDR":
            if saw_header or size != 13:
                raise ValueError("invalid or repeated PNG IHDR")
            _, _, depth, color, compression, filtering, interlace = struct.unpack(">IIBBBBB", payload)
            depths = {0: (1, 2, 4, 8, 16), 2: (8, 16), 3: (1, 2, 4, 8), 4: (8, 16), 6: (8, 16)}
            if (color not in depths or depth not in depths[color] or compression != 0
                    or filtering != 0 or interlace not in (0, 1)):
                raise ValueError("invalid PNG IHDR format")
            bits = depth * {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color]
            passes = ((0, 0, 1, 1),) if interlace == 0 else (
                (0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8), (2, 0, 4, 4),
                (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2))
            for x, y, dx, dy in passes:
                columns = max(0, (width - x + dx - 1) // dx)
                rows = max(0, (height - y + dy - 1) // dy)
                if columns and rows:
                    expected += rows * (1 + (columns * bits + 7) // 8)
            if expected > 256 * 1024 * 1024:
                raise ValueError("PNG scanline data exceeds the 256 MiB validation limit")
            saw_header = True
        elif kind == b"PLTE":
            if saw_palette or saw_data or color in (0, 4) or size == 0 or size > 768 or size % 3:
                raise ValueError("invalid PNG palette or palette order")
            if color == 3 and size // 3 > 1 << depth:
                raise ValueError("PNG palette exceeds its bit depth")
            saw_palette = True
        elif kind == b"IDAT":
            if data_closed or color == 3 and not saw_palette:
                raise ValueError("invalid PNG IDAT order")
            saw_data = True
            # Bound both compressed slices and decompressed output; never join IDATs.
            for start in range(0, size, 65536):
                pending = payload[start:start + 65536]
                while pending:
                    block = decoder.decompress(pending, min(65536, expected - decoded + 1))
                    decoded += len(block)
                    if decoded > expected:
                        raise ValueError("PNG data expands beyond its IHDR dimensions")
                    if decoder.unused_data:
                        raise ValueError("PNG IDAT has data after its zlib stream")
                    pending = decoder.unconsumed_tail
        elif kind == b"IEND":
            if size != 0 or not saw_data or end != len(data):
                raise ValueError("invalid PNG IEND, missing IDAT, or trailing bytes")
            if not decoder.eof or decoded != expected:
                raise ValueError("incomplete PNG IDAT stream or wrong scanline length")
            return width, height
        elif not kind[0] & 32:
            raise ValueError("unsupported critical PNG chunk: " + kind.decode("ascii"))
        if saw_data and kind != b"IDAT":
            data_closed = True
        offset = end
    raise ValueError("PNG is missing IEND")


def _positive_seconds(value, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a finite positive number") from exc
    if isinstance(value, bool) or not math.isfinite(number) or number <= 0:
        raise ValueError(f"{name} must be a finite positive number")
    return number


def _atomic_manifest(path: Path, manifest: dict, *, exclusive: bool = False) -> None:
    data = json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".burst-", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if exclusive:
            # A hard link publishes the complete initial file atomically and fails
            # if another capture already owns this output, unlike os.replace.
            os.link(temporary, path)
        else:
            os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _focus_dict(focus) -> dict:
    return {key: getattr(focus, key, "") for key in
            ("kind", "package", "activity", "window", "focused_app", "token")}


def _counter_delta(before: dict, after: dict) -> dict:
    result = {}
    for group, values in after.items():
        if not isinstance(values, dict):
            continue
        old = before.get(group, {})
        result[group] = {key: round(value - old.get(key, 0), 6)
                         for key, value in values.items()
                         if isinstance(value, (int, float)) and value != old.get(key, 0)}
    return result


def _change_summary(previous: dict | None, current: dict) -> dict:
    """Describe evidence differences, without inferring navigation or scrolling."""
    if previous is None:
        return {"kind": "initial", "compared_to_frame": None,
                "page_identity": "not_inferred", "scroll": "not_inferred"}
    changes = {}
    for name in ("xml_sha256", "png_sha256", "focus"):
        left, right = previous.get(name), current.get(name)
        changes[name.replace("_sha256", "") + "_changed"] = (
            left != right if left is not None and right is not None else None)
    kind = ("observed_changed" if any(value is True for value in changes.values()) else
            "incomplete_evidence" if any(value is None for value in changes.values()) else
            "no_observed_change")
    return {"kind": kind, "compared_to_frame": previous["index"], **changes,
            "page_identity": "not_inferred", "scroll": "not_inferred"}


def capture_burst(dev, out, duration=5, interval=1, label="", trigger=None, *,
                  clock=None, sleep=None, wall_clock=None) -> dict:
    """Capture raw frames in a new or empty directory and return ``burst.json``.

    ``trigger`` is an optional zero-argument callable returning JSON-safe action
    details. It runs once, after a complete first frame, before the deadline.
    A successful trigger always gets at least one subsequent frame, even if it
    overran the deadline. The caller owns device exclusion and action safety.

    Start intervals are best effort: slow observations run serially without
    queued catch-up frames. An already started frame may exceed ``duration``.
    Parameters/directory errors raise; observation failures are recorded, and
    KeyboardInterrupt returns an ``interrupted`` manifest with saved evidence.
    Final status is completed, partial, failed (no saved evidence), or interrupted.
    """
    duration = _positive_seconds(duration, "duration")
    interval = _positive_seconds(interval, "interval")
    if trigger is not None and not callable(trigger):
        raise ValueError("trigger must be callable")
    if not isinstance(label, str):
        raise ValueError("label must be a string")
    clock = clock or getattr(dev, "clock", time.monotonic)
    sleep = sleep or getattr(dev, "sleep", time.sleep)
    wall_clock = wall_clock or time.time
    directory = Path(out).absolute()
    if directory.is_symlink() or (directory.exists() and (
            not directory.is_dir() or any(directory.iterdir()))):
        raise FileExistsError(f"burst output must be a new or empty directory: {directory}")
    directory.mkdir(parents=True, exist_ok=True)
    manifest_path = directory / "burst.json"
    t0 = clock()
    deadline = t0 + duration
    counters_before = copy.deepcopy(getattr(dev, "counters", {}))
    manifest = {
        "schema_version": 1, "kind": "raw_burst", "status": "running",
        "label": label, "output": str(directory),
        "device": getattr(dev, "serial", ""), "target_package": getattr(dev, "package", ""),
        "requested_duration_s": duration, "requested_interval_s": interval,
        "pairing_note": PAIRING_NOTE, "review_required": True, "formal_page_index": False,
        "timing_policy": "serial best-effort start intervals; no queued catch-up; finish in-flight frame",
        "frames": [], "failures": [], "actual_intervals_s": [], "overrun_reasons": [],
        "trigger": {"requested": trigger is not None,
                    "status": "pending" if trigger is not None else "not_requested", "calls": 0},
    }

    def stamp() -> dict:
        return {"at": datetime.fromtimestamp(wall_clock(), timezone.utc).isoformat(timespec="milliseconds"),
                "offset_s": round(clock() - t0, 6)}

    manifest["started_at"] = stamp()["at"]

    def failure(phase: str, exc: BaseException, frame=None) -> None:
        record = {"phase": phase, "error_type": type(exc).__name__, "error": str(exc), **stamp()}
        if frame is not None:
            record["frame"] = frame["index"]
            frame["failures"].append(record)
        manifest["failures"].append(record)

    def save(*, exclusive=False) -> None:
        frames = manifest["frames"]
        manifest["actual_duration_s"] = round(clock() - t0, 6)
        manifest["overrun_s"] = round(max(0.0, clock() - deadline), 6)
        manifest["counters"] = {
            "frames_attempted": len(frames),
            **{name: sum(f["status"] == name for f in frames)
               for name in ("normal", "partial", "failed", "interrupted")},
            "xml_saved": sum(f.get("view_xml") is not None for f in frames),
            "png_saved": sum(f.get("screenshot") is not None for f in frames),
            "failures": len(manifest["failures"]),
        }
        manifest["device_counters"] = _counter_delta(counters_before, getattr(dev, "counters", {}))
        _atomic_manifest(manifest_path, manifest, exclusive=exclusive)

    def timed(record: dict, phase: str, action, frame=None):
        start = stamp()
        record.update(status="running", started_at=start["at"], started_offset_s=start["offset_s"])
        save()
        try:
            value = action()
            record["status"] = "completed"
            return True, value
        except KeyboardInterrupt as exc:
            record["status"] = "interrupted"
            failure(phase, exc, frame)
            raise
        except Exception as exc:
            record["status"] = "failed"
            failure(phase, exc, frame)
            return False, None
        finally:
            end = stamp()
            record.update(finished_at=end["at"], finished_offset_s=end["offset_s"],
                          duration_s=round(end["offset_s"] - start["offset_s"], 6))
            save()

    current = None
    stop_reason = "duration_elapsed"
    force_post_trigger = False
    next_start = t0
    previous_start = None
    # Publish a complete initial manifest exclusively before any device work.
    save(exclusive=True)
    try:
        while force_post_trigger or clock() < deadline:
            # A promised post-trigger frame must still respect the requested
            # minimum start interval, even when that places it past the deadline.
            wait = (next_start if force_post_trigger else min(next_start, deadline)) - clock()
            if wait > 0:
                sleep(wait)
            if not force_post_trigger and clock() >= deadline:
                break
            start = stamp()
            if previous_start is not None:
                manifest["actual_intervals_s"].append(round(start["offset_s"] - previous_start, 6))
            previous_start = start["offset_s"]
            if force_post_trigger and clock() >= deadline and "post_trigger_evidence" not in manifest["overrun_reasons"]:
                manifest["overrun_reasons"].append("post_trigger_evidence")
            current = {"index": len(manifest["frames"]) + 1, "status": "running",
                       "started_at": start["at"], "started_offset_s": start["offset_s"],
                       "after_trigger": manifest["trigger"]["status"] == "completed",
                       "forced_post_trigger": force_post_trigger and clock() >= deadline,
                       "view_xml": None, "screenshot": None, "focus": None,
                       "focus_after_png": None, "activity": None, "package": None, "window": None,
                       "captures": {}, "failures": [],
                       "change": {"kind": "incomplete_evidence", "page_identity": "not_inferred",
                                  "scroll": "not_inferred"},
                       "pairing": {"status": "incomplete", "atomic": False, "same_ui_proven": False}}
            force_post_trigger = False
            manifest["frames"].append(current)
            suffix = f"{current['index']:03d}"

            def dump():
                obs = dev.dump("burst")
                raw = obs.xml.encode("utf-8") if isinstance(obs.xml, str) else obs.xml
                nodes = ui.parse(raw)
                name = f"view_{suffix}.xml"
                with (directory / name).open("xb") as stream:
                    stream.write(raw)
                focus = _focus_dict(obs.focus)
                current.update(view_xml=name, xml_sha256=hashlib.sha256(raw).hexdigest(),
                               focus=focus, activity=focus["activity"], package=focus["package"],
                               window=focus["window"], node_count=len(nodes),
                               dump_seq=getattr(obs, "seq", None), retried=getattr(obs, "retried", False))

            def screenshot():
                raw = dev.screencap("burst")
                width, height = _validate_png(raw)
                name = f"screenshot_{suffix}.png"
                with (directory / name).open("xb") as stream:
                    stream.write(raw)
                current.update(screenshot=name, png_sha256=hashlib.sha256(raw).hexdigest(),
                               screenshot_size=[width, height])

            current["captures"]["xml"] = {}
            xml_ok, _ = timed(current["captures"]["xml"], "dump", dump, current)
            current["captures"]["png"] = {}
            png_ok, _ = timed(current["captures"]["png"], "screencap", screenshot, current)
            if png_ok:
                current["captures"]["post_png_focus"] = {}
                focus_ok, focus = timed(current["captures"]["post_png_focus"], "post_png_focus",
                                        lambda: _focus_dict(dev.focus("burst")), current)
                if focus_ok:
                    current["focus_after_png"] = focus
            before, after = current["focus"], current["focus_after_png"]
            if xml_ok and png_ok:
                if not before or not after or not before["window"] or not after["window"]:
                    current["pairing"]["status"] = "unverified"
                    if not current["failures"]:
                        failure("pairing", RuntimeError("focused window unavailable; pairing unverified"), current)
                else:
                    fields = [key for key in ("kind", "package", "activity", "window", "token")
                              if before[key] != after[key] and (key != "token" or before[key] and after[key])]
                    current["pairing"].update(status="mismatch" if fields else "sequential_same_focus",
                                              changed_focus_fields=fields)
                    if fields:
                        failure("pairing", RuntimeError("focus changed between dump and post-PNG check: "
                                                        + ", ".join(fields)), current)
            current["status"] = ("normal" if xml_ok and png_ok and not current["failures"] else
                                 "partial" if current["view_xml"] or current["screenshot"] else "failed")
            current["change"] = _change_summary(manifest["frames"][-2] if len(manifest["frames"]) > 1 else None,
                                                current)
            end = stamp()
            current.update(finished_at=end["at"], finished_offset_s=end["offset_s"],
                           duration_s=round(end["offset_s"] - start["offset_s"], 6))
            if clock() > deadline and "in_flight_frame" not in manifest["overrun_reasons"]:
                manifest["overrun_reasons"].append("in_flight_frame")
            save()
            if current["index"] == 1 and trigger is not None:
                if current["status"] != "normal" or clock() >= deadline:
                    stop_reason = "baseline_failed" if current["status"] != "normal" else "deadline_before_trigger"
                    manifest["trigger"].update(status="skipped", reason=stop_reason)
                    failure("trigger", RuntimeError("trigger skipped: " + stop_reason))
                    break
                manifest["trigger"]["calls"] = 1

                def invoke_trigger():
                    result = trigger()
                    # Check before insertion so a malformed callback result cannot break manifest saving.
                    json.dumps(result, allow_nan=False)
                    manifest["trigger"]["result"] = result

                ok, _ = timed(manifest["trigger"], "trigger", invoke_trigger)
                if not ok:
                    stop_reason = "trigger_failed"
                    break
                force_post_trigger = True
                if clock() >= deadline:
                    manifest["overrun_reasons"].append("post_trigger_evidence")
            next_start = t0 + start["offset_s"] + interval
            current = None
    except KeyboardInterrupt:
        stop_reason = "keyboard_interrupt"
        manifest["status"] = "interrupted"
        if current is not None and current["status"] == "running":
            current["status"] = "interrupted"
            end = stamp()
            current.update(finished_at=end["at"], finished_offset_s=end["offset_s"],
                           duration_s=round(end["offset_s"] - current["started_offset_s"], 6))
        if not manifest["failures"] or manifest["failures"][-1]["error_type"] != "KeyboardInterrupt":
            failure("wait", KeyboardInterrupt())
        if manifest["trigger"]["status"] == "pending":
            manifest["trigger"].update(status="skipped", reason="interrupted_before_trigger")
    except Exception as exc:
        stop_reason = "capture_error"
        failure("capture", exc, current)
        if current is not None and current["status"] == "running":
            current["status"] = "partial" if current["view_xml"] or current["screenshot"] else "failed"
        if manifest["trigger"]["status"] == "pending":
            manifest["trigger"].update(status="skipped", reason="capture_error")
    finally:
        manifest["stop_reason"] = stop_reason
        manifest["finished_at"] = stamp()["at"]
        if manifest["status"] != "interrupted":
            has_evidence = any(f["view_xml"] or f["screenshot"] for f in manifest["frames"])
            manifest["status"] = ("failed" if not has_evidence else "partial" if manifest["failures"]
                                  else "completed")
        save()
    return manifest
