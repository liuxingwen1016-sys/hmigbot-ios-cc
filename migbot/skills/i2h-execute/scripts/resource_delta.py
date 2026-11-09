#!/usr/bin/env python3
"""Task-owned OpenHarmony resource delta protocol.

This is an opt-in merge primitive.  It does not replace ``sweep_resources``
or decide which resource a task should create.  Each delta records a preimage
hash, and the merge refuses conflicting writers before touching the project.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import uuid
from typing import Any


ROOT = "spec/execution/resource-deltas"
SCHEMA_VERSION = 1
MAX_BYTES = 16 * 1024 * 1024


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _project(value: str | Path) -> Path:
    root = Path(value).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"project does not exist: {root}")
    return root


def _safe_relative(value: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        raise ValueError("resource path must be a project-relative POSIX path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != value:
        raise ValueError(f"unsafe resource path: {value}")
    return path


def _path(project: Path, relative: str) -> Path:
    path = project.joinpath(*_safe_relative(relative).parts)
    current = project
    for part in _safe_relative(relative).parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"resource path traverses symlink: {relative}")
    if path.resolve() != path.absolute().resolve():
        raise ValueError(f"resource path escapes project: {relative}")
    return path


def _read(path: Path) -> bytes | None:
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"resource destination must be an ordinary file: {path}")
    if path.stat().st_size > MAX_BYTES:
        raise ValueError(f"resource exceeds {MAX_BYTES} bytes: {path}")
    return path.read_bytes()


def _scope(project: Path, scope_id: str) -> Path:
    if not scope_id or not scope_id.replace("_", "").replace("-", "").isalnum():
        raise ValueError("scope_id must be portable")
    return _path(project, f"{ROOT}/{scope_id}")


def _atomic_write(path: Path, raw: bytes) -> None:
    if len(raw) > MAX_BYTES:
        raise ValueError(f"output exceeds {MAX_BYTES} bytes")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".resource-delta-{uuid.uuid4().hex}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(temporary, flags, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def _lock(project: Path):
    try:
        import fcntl
    except ImportError as exc:
        raise RuntimeError("fcntl locking is required on this host") from exc
    lock_path = _path(project, ROOT + "/.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected object: {path}")
    return value


def init_scope(project: str | Path, scope_id: str, tasks: list[dict[str, Any]], resources: list[dict[str, Any]]) -> Path:
    root = _project(project)
    scope = _scope(root, scope_id)
    if scope.exists() and any(scope.iterdir()):
        raise ValueError(f"resource scope already initialized: {scope_id}")
    normalized_tasks = []
    seen_tasks = set()
    for task in tasks:
        task_id = task.get("task_id") if isinstance(task, dict) else None
        if not isinstance(task_id, str) or not task_id or task_id in seen_tasks:
            raise ValueError("tasks need unique task_id")
        seen_tasks.add(task_id)
        normalized_tasks.append({"task_id": task_id, "attempt": int(task.get("attempt", 1))})
    normalized_resources = []
    seen_resources = set()
    for resource in resources:
        relative = resource.get("path") if isinstance(resource, dict) else None
        if not isinstance(relative, str):
            raise ValueError("resources need path")
        _safe_relative(relative)
        if relative.casefold() in seen_resources:
            raise ValueError("duplicate or case-colliding resource path")
        seen_resources.add(relative.casefold())
        raw = _read(_path(root, relative))
        normalized_resources.append({"path": relative, "type": resource.get("type", "json"), "preimage_sha256": _digest(raw) if raw is not None else None})
    manifest = {"schema_version": SCHEMA_VERSION, "scope_id": scope_id, "tasks": normalized_tasks, "resources": normalized_resources}
    _atomic_write(scope / "manifest.json", (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode())
    return scope / "manifest.json"


def submit_delta(project: str | Path, scope_id: str, task_id: str, delta: dict[str, Any]) -> Path:
    root = _project(project)
    scope = _scope(root, scope_id)
    manifest = _json(scope / "manifest.json")
    task_ids = {item.get("task_id") for item in manifest.get("tasks", []) if isinstance(item, dict)}
    if task_id not in task_ids:
        raise ValueError(f"task is not declared in scope: {task_id}")
    if delta.get("task_id") != task_id or not isinstance(delta.get("resources"), list):
        raise ValueError("delta needs matching task_id and resources")
    attempt = int(delta.get("attempt", 1))
    clean = {"schema_version": SCHEMA_VERSION, "scope_id": scope_id, "task_id": task_id, "attempt": attempt, "resources": []}
    for item in delta["resources"]:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise ValueError("delta resource needs path")
        _safe_relative(item["path"])
        if "value" not in item:
            raise ValueError("delta resource needs value")
        clean["resources"].append({"path": item["path"], "type": item.get("type", "json"), "expected_sha256": item.get("expected_sha256"), "value": item["value"]})
    destination = scope / f"delta-{task_id}-{attempt}.json"
    _atomic_write(destination, (json.dumps(clean, ensure_ascii=False, indent=2) + "\n").encode())
    return destination


def merge(project: str | Path, scope_id: str) -> dict[str, Any]:
    root = _project(project)
    scope = _scope(root, scope_id)
    with _lock(root):
        manifest = _json(scope / "manifest.json")
        declared = {item["path"]: item for item in manifest.get("resources", [])}
        deltas = sorted(scope.glob("delta-*.json"))
        selected: dict[str, tuple[dict[str, Any], Path]] = {}
        for delta_path in deltas:
            delta = _json(delta_path)
            for item in delta.get("resources", []):
                relative = item.get("path")
                if relative not in declared:
                    raise ValueError(f"resource is outside manifest: {relative}")
                if relative.casefold() in {path.casefold() for path in selected}:
                    raise ValueError(f"multiple task writers for resource: {relative}")
                selected[relative] = (item, delta_path)
        writes = []
        for relative, (item, _delta_path) in selected.items():
            destination = _path(root, relative)
            current = _read(destination)
            expected = item.get("expected_sha256") or declared[relative].get("preimage_sha256")
            if expected is not None and _digest(current or b"") != expected:
                raise ValueError(f"resource preimage changed: {relative}")
            raw = (json.dumps(item["value"], ensure_ascii=False, indent=2) + "\n").encode()
            writes.append((destination, raw))
        for destination, raw in writes:
            _atomic_write(destination, raw)
        result = {"schema_version": SCHEMA_VERSION, "scope_id": scope_id, "status": "merged", "merged": sorted(relative for relative in selected)}
        _atomic_write(scope / "merge.json", (json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode())
        return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("--project", required=True)
    init.add_argument("--scope", required=True)
    init.add_argument("--manifest", required=True, help="JSON with tasks/resources")
    submit = sub.add_parser("submit")
    submit.add_argument("--project", required=True)
    submit.add_argument("--scope", required=True)
    submit.add_argument("--task", required=True)
    submit.add_argument("--delta", required=True)
    merge_cmd = sub.add_parser("merge")
    merge_cmd.add_argument("--project", required=True)
    merge_cmd.add_argument("--scope", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            manifest = _json(Path(args.manifest))
            result = init_scope(args.project, args.scope, manifest.get("tasks", []), manifest.get("resources", []))
            print(json.dumps({"manifest": str(result), "status": "initialized"}, ensure_ascii=False))
        elif args.command == "submit":
            result = submit_delta(args.project, args.scope, args.task, _json(Path(args.delta)))
            print(json.dumps({"delta": str(result), "status": "submitted"}, ensure_ascii=False))
        else:
            print(json.dumps(merge(args.project, args.scope), ensure_ascii=False))
        return 0
    except (OSError, ValueError, json.JSONDecodeError, RuntimeError) as exc:
        print(f"ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
