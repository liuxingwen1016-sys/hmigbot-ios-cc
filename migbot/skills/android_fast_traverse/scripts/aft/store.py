"""Output layout. One task, one OUT, always named android_traverse_screenshots (any parent directory).

android_traverse_screenshots/          OUT, the delivered root; only these at its top level:
  index.json                           the current valid units (the only entry point for consumers)
  page_NNNN_<Activity>/                automatic units; NNNN = 4-digit global number shared with manual_
  manual_NNNN_<Activity>/              hand-driven units (drive capture)
    screenshot.png  view.xml           first viewport
    screenshot_scroll_<k>.png  view_scroll_<k>.xml   further viewports, k = 1.. (vertical, then horizontal strips)
    meta.json
  _aft/                                ledgers and model inputs, not deliverables:
    input/profile.json  input/review.json          written by the model
    profile.json                                   the profile in force (written by the executor)
    state.json sessions.jsonl edges.jsonl events.jsonl report.md report.json gallery.html
    drive_counters.json popup_rules.json
    inspect/inspect_<session>_<seq>.png|xml        anomalies/<gap code>_<n>.xml|png
    model_requests/<request_id>/request.json before.* response.json result.json after.* decision.json
    revisions/<PAGE_ID>/rev_NNNN/   attempts/<PAGE_ID>/rev_NNNN/   previous/NNN/ (run --fresh)
    bursts/<name>/burst.json screenshot_NNN.png view_NNN.xml

Paths inside meta.json/index.json are relative to OUT.
"""
from __future__ import annotations

import json
import shutil
import os
import re
import time
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path

from . import VERSION


_invocation = ContextVar("aft_invocation", default=None)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class InvocationSession:
    """Append-only invocation history, independent from cumulative traversal state.

    The CLI owns OutputLease around this context. Deferred burst history is only
    published if this invocation creates its manifest, never on a refused old OUT.
    """
    def __init__(self, out: str | Path, command: str, *, serial: str = "", deferred=False):
        self.out = Path(out).resolve()
        self.session_id = uuid.uuid4().hex
        self.command = command
        self.serial = serial
        self.deferred = deferred
        self.status = "running"
        self.exit_code = None
        self.error = None
        self.had_manifest = (self.out / "burst.json").exists()

    def _append(self, record: dict) -> None:
        aft = self.out / "_aft"
        aft.mkdir(parents=True, exist_ok=True)
        with (aft / "sessions.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")

    def __enter__(self):
        self.t0 = time.monotonic()
        self.started = {"session_id": self.session_id, "command": self.command, "version": VERSION,
                        "serial": self.serial, "output": str(self.out), "started_at": utc_now(),
                        "started_wall_time": time.time(), "status": "running", "event": "started"}
        if not self.deferred:
            self._append(self.started)
        self.token = _invocation.set(self)
        return self

    def __exit__(self, exc_type, exc, _tb):
        try:
            if exc_type is not None:
                self.status = "interrupted" if issubclass(exc_type, KeyboardInterrupt) else "error"
                if self.exit_code is None:
                    self.exit_code = 130 if self.status == "interrupted" else 1
            elif self.status == "running":
                self.status = "completed"
            end = {**self.started, "event": "finished", "status": self.status,
                   "ended_at": utc_now(), "ended_wall_time": time.time(),
                   "elapsed_s": round(time.monotonic() - self.t0, 6), "exit_code": self.exit_code}
            if exc is not None:
                end["error"] = f"{exc_type.__name__}: {exc}"
            elif self.error:
                end["error"] = self.error
            if not self.deferred or (not self.had_manifest and (self.out / "burst.json").is_file()):
                if self.deferred:
                    self._append(self.started)
                self._append(end)
        finally:
            _invocation.reset(self.token)


def current_session_id() -> str:
    session = _invocation.get()
    return session.session_id if session else uuid.uuid4().hex

def _atomic_write(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def dump_json(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False, indent=1, default=list).encode("utf-8")


OUT_NAME = "android_traverse_screenshots"   # the one name of the output root, agreed with downstream consumers
INPUT_DIR = "input"                          # _aft/input/: files the model writes (profile.json, review.json)


def check_out(path: str | Path) -> Path:
    """OUT must be named android_traverse_screenshots; it may sit in any parent directory."""
    p = Path(path)
    if p.name != OUT_NAME:
        raise ValueError(f"the output directory must be named {OUT_NAME} (got {p.name!r}); "
                         f"put it wherever the task needs, e.g. ./{OUT_NAME}")
    return p


def check_burst_dir(path: str | Path) -> Path:
    p = Path(path)
    if not (p.parent.name == "bursts" and p.parent.parent.name == "_aft" and p.parent.parent.parent.name == OUT_NAME):
        raise ValueError(f"burst output goes to {OUT_NAME}/_aft/bursts/<name> (got {p})")
    return p


# Kept in place by run --fresh: history, prep evidence, verified popup rules and the model's own inputs.
KEEP_ON_FRESH = {"sessions.jsonl", "inspect", "bursts", "previous", "popup_rules.json", INPUT_DIR}


def archive_traversal(out: str | Path) -> Path | None:
    """`run --fresh`: move the current traversal (units, index, checkpoint, ledgers, reports, model requests) into
    OUT/_aft/previous/NNN/ and leave OUT ready for a new traversal. Nothing is deleted, and the top level then holds
    only the new attempt's units, so one task keeps one OUT even when it starts over (a reinstall, a wrong root).
    Session history, inspect captures, bursts and verified popup rules (keyed by app build and density) stay;
    manual units captured before the restart go with the old traversal."""
    out = Path(out).resolve()
    aft = out / "_aft"
    top = [p for p in out.iterdir() if p.name == "index.json" or p.name.startswith(("page_", "manual_"))] \
        if out.is_dir() else []
    inner = [p for p in aft.iterdir() if p.name not in KEEP_ON_FRESH] if aft.is_dir() else []
    if not top and not inner:
        return None
    previous = aft / "previous"
    used = [int(p.name) for p in previous.iterdir() if p.name.isdigit()] if previous.is_dir() else []
    dest = previous / f"{max(used, default=0) + 1:03d}"
    (dest / "_aft").mkdir(parents=True)
    for p in top:
        shutil.move(str(p), str(dest / p.name))
    for p in inner:
        shutil.move(str(p), str(dest / "_aft" / p.name))
    return dest


class Store:
    def __init__(self, out: str | Path):
        self.out = Path(out).resolve()
        self.aft = self.out / "_aft"
        (self.aft / "anomalies").mkdir(parents=True, exist_ok=True)
        self._edge_fh = open(self.aft / "edges.jsonl", "a", encoding="utf-8")
        self._event_fh = open(self.aft / "events.jsonl", "a", encoding="utf-8")
        self.t0 = time.monotonic()
        self.session_id = current_session_id()

    def close(self) -> None:
        for fh in (self._edge_fh, self._event_fh):
            try:
                fh.close()
            except Exception:
                pass

    # ---- ledgers
    def event(self, kind: str, data: dict | None = None) -> None:
        rec = {"t": round(time.monotonic() - self.t0, 3), "kind": kind}
        rec.update(data or {})
        rec.update(session_id=self.session_id, at=utc_now())
        self._event_fh.write(json.dumps(rec, ensure_ascii=False, default=list) + "\n")
        self._event_fh.flush()

    def edge(self, rec: dict) -> None:
        rec = {"t": round(time.monotonic() - self.t0, 3), **rec,
               "session_id": self.session_id, "at": utc_now()}
        self._edge_fh.write(json.dumps(rec, ensure_ascii=False, default=list) + "\n")
        self._edge_fh.flush()

    def save_state(self, state: dict) -> None:
        _atomic_write(self.aft / "state.json", dump_json(state))

    def load_state(self) -> dict | None:
        p = self.aft / "state.json"
        if not p.exists():
            return None
        state = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(state, dict):
            raise ValueError("state.json must be an object")
        # Artifact registration commits index.json before the later traversal
        # checkpoint. A crash between those writes must not drop committed units
        # on resume. Recover only artifact records; never infer explored edges,
        # page graph, DFS stack or completion from having a screenshot.
        index = self._read_index()
        if index is not None:
            state["index"] = index
        return state

    def _read_index(self) -> list | None:
        path = self._path("index.json")
        if not path.exists():
            return None
        records = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(records, list):
            raise ValueError("index.json must be a list")
        seen = set()
        for record in records:
            page_id = record.get("page_id") if isinstance(record, dict) else None
            if (not isinstance(page_id, str) or not re.fullmatch(r"(?:page|manual)_\d{4,}(?:_\w+)?", page_id)
                    or page_id in seen):
                raise ValueError("index.json contains an invalid or duplicate page_id")
            seen.add(page_id)
            self._path(page_id)
            paths = [record[key] for key in ("screenshot", "view_xml") if key in record]
            for key in ("screenshots", "view_xmls"):
                values = record.get(key, [])
                if not isinstance(values, list):
                    raise ValueError(f"index.json {key} must be a list")
                paths.extend(values)
            for relative in paths:
                if not isinstance(relative, str):
                    raise ValueError("index.json evidence paths must be output-relative strings")
                self._path(relative)
        return records

    def save_json(self, name: str, obj) -> Path:
        p = self._path("_aft/" + name)
        _atomic_write(p, dump_json(obj))
        return p

    def anomaly(self, name: str, xml: bytes | None = None, png: bytes | None = None) -> str:
        safe = re.sub(r"[^\w.-]+", "_", name)[:80]
        rel = f"_aft/anomalies/{safe}"
        if any((self.out / (rel + ext)).exists() for ext in (".xml", ".png")):
            rel += "_" + uuid.uuid4().hex
        if xml is not None:
            (self.out / (rel + ".xml")).write_bytes(xml)
        if png is not None:
            (self.out / (rel + ".png")).write_bytes(png)
        return rel

    # ---- pages
    def page_id(self, number: int, activity: str) -> str:
        suffix = re.sub(r"[^\w]+", "", activity or "")
        return f"page_{number:04d}" + (f"_{suffix}" if suffix else "")

    def allocate_page_id(self, state: dict, activity: str, manual: bool = False) -> str:
        """Reserve the next global number without trusting a possibly stale state.

        Index records and orphaned capture directories both count. In particular,
        a failed previous write or hand capture cannot make numbering go backwards.
        Caller must hold the output lease when using this API concurrently.
        """
        pattern = re.compile(r"^(?:page|manual)_(\d+)(?:_|$)")
        largest = max(0, int(state.get("page_counter", 0)))
        ids = [r.get("page_id", "") for r in state.get("index", [])]
        records = self._read_index()
        if records is not None:
            ids.extend(r.get("page_id", "") for r in records)
        ids.extend(p.name for p in self.out.iterdir())
        for page_id in ids:
            match = pattern.match(str(page_id))
            if match:
                largest = max(largest, int(match.group(1)))
        state["page_counter"] = largest + 1
        page_id = self.page_id(largest + 1, activity)
        if manual:
            page_id = "manual_" + page_id.removeprefix("page_")
        if (self.out / page_id).exists():
            raise FileExistsError(f"capture already exists: {page_id}")
        return page_id

    def _path(self, relative: str) -> Path:
        path = Path(relative)
        if path.is_absolute() or not path.parts or any(p in (".", "..") for p in path.parts):
            raise ValueError(f"unsafe output-relative path: {relative!r}")
        resolved = (self.out / path).resolve()
        if resolved == self.out or not resolved.is_relative_to(self.out):
            raise ValueError(f"path escapes output directory: {relative!r}")
        return resolved

    def write_frames(self, page_id: str, frames: list) -> tuple:
        d = self._path(page_id)
        # Exclusive creation also protects revision paths and partially written
        # captures. Never replace evidence left by an interrupted invocation.
        d.mkdir(parents=True, exist_ok=False)
        shots, xmls = [], []
        for i, f in enumerate(frames):
            png_name = "screenshot.png" if i == 0 else f"screenshot_scroll_{i}.png"
            xml_name = "view.xml" if i == 0 else f"view_scroll_{i}.xml"
            (d / png_name).write_bytes(f.png)
            (d / xml_name).write_bytes(f.xml)
            shots.append(f"{page_id}/{png_name}")
            xmls.append(f"{page_id}/{xml_name}")
        return shots, xmls

    def write_meta(self, page_id: str, meta: dict) -> None:
        _atomic_write(self._path(page_id) / "meta.json", dump_json(meta))

    def write_index(self, records: list) -> None:
        _atomic_write(self.out / "index.json", dump_json(records))


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")
