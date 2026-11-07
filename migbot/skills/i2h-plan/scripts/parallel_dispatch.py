#!/usr/bin/env python3
"""Dependency-grouped P1 dispatch helper for Claude orchestration.

This module does not write plan files.  It returns worker results in stable
input order so the main thread can perform one merge, lint, and gate pass.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable, Iterable

_shared = Path(__file__).resolve().parents[3] / "bin/scripts/pipeline"
if str(_shared) not in sys.path:
    sys.path.insert(0, str(_shared))

from bounded_workers import batch_items, run_bounded  # type: ignore


def dependency_groups(items: Iterable[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Topologically batch features by ``depends_on`` with stable ordering."""
    pending = {str(item.get("feature_id") or item.get("id")): dict(item) for item in items}
    completed: set[str] = set()
    groups: list[list[dict[str, Any]]] = []
    while pending:
        ready = [
            item for key, item in pending.items()
            if all(str(dep) in completed or str(dep) in {"base", ""} for dep in item.get("depends_on", []))
        ]
        if not ready:
            # Preserve all remaining work and let the linter surface the cycle.
            ready = [pending[key] for key in sorted(pending)]
        ready.sort(key=lambda row: str(row.get("feature_id") or row.get("id")))
        groups.append(ready)
        for item in ready:
            key = str(item.get("feature_id") or item.get("id"))
            pending.pop(key, None)
            completed.add(key)
    return groups


def dispatch_p1(
    items: Iterable[dict[str, Any]],
    worker: Callable[[dict[str, Any], Path], Any],
    *,
    checkpoint_dir: str | Path,
    max_workers: int = 4,
    retries: int = 2,
) -> dict[str, Any]:
    """Dispatch each dependency group in parallel and join deterministically."""
    all_results: dict[str, Any] = {}
    all_failures: dict[str, str] = {}
    all_checkpoints: dict[str, Any] = {}
    groups = dependency_groups(items)
    for index, group in enumerate(groups, 1):
        outcome = run_bounded(
            group,
            worker,
            max_workers=max_workers,
            retries=retries,
            checkpoint_dir=Path(checkpoint_dir) / f"group-{index}",
        )
        all_results.update(outcome["results"])
        all_failures.update(outcome["failures"])
        all_checkpoints.update(outcome["checkpoints"])
    return {
        "status": "complete" if not all_failures else "partial",
        "groups": len(groups),
        "completed": len(all_results),
        "failed": len(all_failures),
        "results": all_results,
        "failures": all_failures,
        "checkpoints": all_checkpoints,
    }


__all__ = ["batch_items", "dependency_groups", "dispatch_p1"]
