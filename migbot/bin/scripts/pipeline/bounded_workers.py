#!/usr/bin/env python3
"""Bounded, resumable worker execution shared by i2h-spec and i2h-plan.

Workers write only their own checkpoint and temporary output.  The caller owns
the deterministic join/merge step, so a failed model request cannot force all
other work back onto the main thread.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, TypeVar


T = TypeVar("T")
R = TypeVar("R")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def batch_items(items: Iterable[T], batch_size: int = 4) -> list[list[T]]:
    if batch_size < 1:
        raise ValueError("batch_size must be >= 1")
    batches: list[list[T]] = []
    current: list[T] = []
    for item in items:
        current.append(item)
        if len(current) >= batch_size:
            batches.append(current)
            current = []
    if current:
        batches.append(current)
    return batches


def _item_key(item: Any) -> str:
    # Include the complete worker input.  A page/feature with the same ID but
    # a changed source slice must invalidate its checkpoint on an incremental
    # run.  JSON is stable for the structured inputs used by the pipeline.
    if isinstance(item, dict):
        value = json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    else:
        value = str(item)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _read(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def run_bounded(
    items: Iterable[T],
    worker: Callable[[T, Path], R],
    *,
    max_workers: int = 4,
    retries: int = 2,
    checkpoint_dir: str | Path | None = None,
    cache_key: Callable[[T], str] | None = None,
    resume: bool = True,
) -> dict[str, Any]:
    """Run independent items with bounded concurrency and per-item resume.

    A worker receives a private temporary directory.  Return values are kept
    in memory for the deterministic joiner.  Checkpoints contain queue/start/
    end timestamps, retry count, cache hit, and a small usage payload when the
    worker returns one.
    """
    values = list(items)
    limit = max(1, min(int(max_workers), 32))
    checkpoint_root = Path(checkpoint_dir).expanduser().resolve() if checkpoint_dir else None
    if checkpoint_root:
        checkpoint_root.mkdir(parents=True, exist_ok=True)
    key_fn = cache_key or _item_key
    lock = threading.Lock()
    results: dict[str, Any] = {}
    failures: dict[str, str] = {}
    checkpoints: dict[str, dict[str, Any]] = {}

    def run_one(item: T) -> tuple[str, Any, dict[str, Any]]:
        key = key_fn(item)
        checkpoint_path = checkpoint_root / f"{key}.json" if checkpoint_root else None
        prior = _read(checkpoint_path) if checkpoint_path and resume else None
        if prior and prior.get("status") == "complete" and prior.get("cache_key") == key and "result" in prior:
            row = dict(prior)
            row["cache_hit"] = True
            return key, prior.get("result"), row
        row: dict[str, Any] = {
            "item_key": key,
            "status": "queued",
            "queued_at": utc_now(),
            "retry_count": 0,
            "cache_hit": False,
            "usage": {},
        }
        if checkpoint_path:
            _atomic_json(checkpoint_path, row)
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            row["status"] = "running"
            row["started_at"] = row.get("started_at") or utc_now()
            row["retry_count"] = attempt
            try:
                with tempfile.TemporaryDirectory(prefix=f"i2h-worker-{key}-") as temporary:
                    result = worker(item, Path(temporary))
                usage = result.get("usage") if isinstance(result, dict) else None
                row.update({"status": "complete", "ended_at": utc_now(), "result": result})
                if isinstance(usage, dict):
                    row["usage"] = usage
                if checkpoint_path:
                    _atomic_json(checkpoint_path, row)
                return key, result, row
            except Exception as exc:  # worker failures are isolated and retried
                last_error = exc
                row["error"] = f"{type(exc).__name__}: {exc}"
                if attempt < retries:
                    time.sleep(min(2 ** attempt, 4))
        row.update({"status": "failed", "ended_at": utc_now()})
        if checkpoint_path:
            _atomic_json(checkpoint_path, row)
        return key, None, row

    with ThreadPoolExecutor(max_workers=limit, thread_name_prefix="i2h") as pool:
        futures = {pool.submit(run_one, item): item for item in values}
        for future in as_completed(futures):
            item = futures[future]
            key = key_fn(item)
            try:
                item_key, result, checkpoint = future.result()
                with lock:
                    checkpoints[item_key] = checkpoint
                    if checkpoint.get("status") == "failed":
                        failures[item_key] = str(checkpoint.get("error", "worker failed"))
                    else:
                        results[item_key] = result
            except Exception as exc:
                failures[key] = str(exc)
                checkpoints[key] = {"item_key": key, "status": "failed", "ended_at": utc_now(), "error": str(exc)}
    return {
        "status": "complete" if not failures else "partial",
        "max_workers": limit,
        "total": len(values),
        "completed": len(results),
        "failed": len(failures),
        "results": results,
        "failures": failures,
        "checkpoints": checkpoints,
    }


__all__ = ["batch_items", "run_bounded", "utc_now"]
