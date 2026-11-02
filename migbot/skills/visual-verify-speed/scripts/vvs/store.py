"""Work directory (default <HarmonyOS project>/spec/visual-verify), laid out like the downstream fixer expects:

  config.json                                   project binding (Android baseline, HarmonyOS project, bundle)
  progress.json                                 current round and per-round scope (resume state)
  report.md                                     human-readable report of the latest round
  screenshots/android/<page_id>.png             canonical deliverables referenced by the fix files
  screenshots/harmony/round-N/<page_id>.jpeg    .hmos.json  _evidence/
  screenshots/sbs/round-N/<page_id>.jpeg        blocks/
  walk/index.json                               current HarmonyOS unit of every Android unit (walk workspace)
  walk/round-N/<unit>/                          screenshot.png view.json screenshot_scroll_k.png view_scroll_k.json meta.json
  rounds/round-N/                               pairs, metric/oracle, judge batches and results, coverage, fix schedule
  cache/                                        walker state, events, model requests, popup rules, locks
"""
from __future__ import annotations

import datetime as _dt
import fcntl
import json
import os
import re
import shutil

H_OUT = "walk"


def now_iso() -> str:
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")


def read_json(path: str, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(path: str, data) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def append_jsonl(path: str, rec: dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def safe_name(text: str, limit: int = 40) -> str:
    s = re.sub(r"[^0-9A-Za-z_]+", "", text or "")
    return s[:limit] or "Page"


def page_short(page_path: str) -> str:
    return safe_name((page_path or "").rsplit("/", 1)[-1]) or "Page"


class Lock:
    def __init__(self, path: str, what: str):
        self.path, self.what, self.fd = path, what, None

    def __enter__(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self.fd = open(self.path, "a+")
        try:
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.fd.seek(0)
            holder = self.fd.read().strip()
            self.fd.close()
            raise RuntimeError(f"{self.what} is in use by another vvs command ({holder or 'unknown'}); "
                               f"one walk/drive per device at a time")
        self.fd.seek(0)
        self.fd.truncate()
        self.fd.write(f"pid={os.getpid()} at={now_iso()}")
        self.fd.flush()
        return self

    def __exit__(self, *exc):
        try:
            fcntl.flock(self.fd, fcntl.LOCK_UN)
        finally:
            self.fd.close()


class Store:
    def __init__(self, work: str):
        self.work = os.path.abspath(work)
        self.vvs = os.path.join(self.work, "cache")
        self.hout = os.path.join(self.work, H_OUT)

    # ---- paths
    def p(self, *parts: str) -> str:
        return os.path.join(self.work, *parts)

    def round_dir(self, n: int) -> str:
        return self.p("rounds", f"round-{n}")

    def config(self) -> dict:
        cfg = read_json(self.p("config.json"))
        if not cfg:
            raise FileNotFoundError(f"{self.p('config.json')} missing: run `vvs.py init` first")
        return cfg

    def save_config(self, cfg: dict) -> None:
        write_json(self.p("config.json"), cfg)

    def rounds(self) -> dict:
        return read_json(self.p("progress.json"), {"current": 0, "history": {}})

    def save_rounds(self, r: dict) -> None:
        write_json(self.p("progress.json"), r)

    # ---- ledgers
    def event(self, kind: str, data: dict | None = None) -> None:
        append_jsonl(os.path.join(self.vvs, "events.jsonl"), {"t": now_iso(), "kind": kind, **(data or {})})

    def edge(self, rec: dict) -> None:
        append_jsonl(os.path.join(self.vvs, "edges.jsonl"), {"t": now_iso(), **rec})

    def session(self, rec: dict) -> None:
        append_jsonl(os.path.join(self.vvs, "sessions.jsonl"), {"t": now_iso(), **rec})

    def anomaly(self, name: str, raw: bytes | None = None, png: bytes | None = None) -> dict:
        d = os.path.join(self.vvs, "anomalies")
        os.makedirs(d, exist_ok=True)
        out = {}
        if raw:
            path = os.path.join(d, safe_name(name, 60) + ".json")
            with open(path, "wb") as f:
                f.write(raw)
            out["dump"] = os.path.relpath(path, self.work)
        if png:
            path = os.path.join(d, safe_name(name, 60) + ".png")
            with open(path, "wb") as f:
                f.write(png)
            out["png"] = os.path.relpath(path, self.work)
        return out

    def state(self, rnd: int) -> dict | None:
        return read_json(os.path.join(self.vvs, f"state_round-{rnd}.json"))

    def save_state(self, rnd: int, state: dict) -> None:
        write_json(os.path.join(self.vvs, f"state_round-{rnd}.json"), state)

    def device_lock(self) -> Lock:
        return Lock(os.path.join(self.vvs, "device.lock"), "the HarmonyOS device")

    # ---- HarmonyOS units
    def index(self) -> list:
        return read_json(os.path.join(self.hout, "index.json"), [])

    def index_by_pair(self) -> dict:
        out = {}
        for m in self.index():
            if m.get("pair", {}).get("android"):
                out[m["pair"]["android"]] = m
        return out

    def unit_dir(self, rnd: int, android_id: str | None, page_path: str, extra_no: int = 0) -> tuple[str, str]:
        if android_id:
            prefix = android_id.split("_")[0] + "_" + android_id.split("_")[1]
        else:
            prefix = f"extra_{extra_no:04d}"
        name = f"{prefix}_{page_short(page_path)}"
        rel = os.path.join(f"round-{rnd}", name)
        full = os.path.join(self.hout, rel)
        if os.path.exists(full):
            shutil.rmtree(full)  # a re-capture in the same round replaces the earlier attempt of that unit
        os.makedirs(full, exist_ok=True)
        return full, rel

    def write_unit(self, rnd: int, frames: list, meta: dict, android_id: str | None, page_path: str,
                   extra_no: int = 0) -> dict:
        full, rel = self.unit_dir(rnd, android_id, page_path, extra_no)
        shots, views = [], []
        for i, f in enumerate(frames):
            png = "screenshot.png" if i == 0 else f"screenshot_scroll_{i}.png"
            js = "view.json" if i == 0 else f"view_scroll_{i}.json"
            with open(os.path.join(full, png), "wb") as fh:
                fh.write(f.png)
            with open(os.path.join(full, js), "wb") as fh:
                fh.write(f.raw)
            shots.append(os.path.join(rel, png))
            views.append(os.path.join(rel, js))
        meta = {**meta, "unit_dir": rel, "screenshots": shots, "view_jsons": views,
                "screenshot": shots[0] if shots else None, "view_json": views[0] if views else None,
                "round": rnd, "timestamp": now_iso()}
        write_json(os.path.join(full, "meta.json"), meta)
        self.upsert_index(meta)
        return meta

    def upsert_index(self, meta: dict) -> None:
        idx = self.index()
        key = meta.get("pair", {}).get("android") or meta["unit_dir"]
        idx = [m for m in idx if (m.get("pair", {}).get("android") or m.get("unit_dir")) != key]
        idx.append(meta)
        idx.sort(key=lambda m: m.get("unit_dir", ""))
        write_json(os.path.join(self.hout, "index.json"), idx)

    def drop_index(self, android_id: str) -> None:
        idx = [m for m in self.index() if m.get("pair", {}).get("android") != android_id]
        write_json(os.path.join(self.hout, "index.json"), idx)

    def abs_h(self, rel: str) -> str:
        return rel if os.path.isabs(rel) else os.path.join(self.hout, rel)
