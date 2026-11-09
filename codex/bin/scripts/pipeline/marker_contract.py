#!/usr/bin/env python3
"""Shared i2h completion-marker and legacy-path contract."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = 2

# Each stage has one canonical artifact group followed by explicit legacy
# groups. Canonical paths always win when both generations are present.
STAGE_PATH_ALIASES: dict[str, tuple[tuple[str, ...], ...]] = {
    "i2h-spec": (
        ("spec/baseline/spec-complete.txt",),
        ("spec/spec-complete.txt",),
        ("spec/spec-completed.txt",),
    ),
    "i2h-plan": (
        ("spec/baseline/plans/complete.txt",),
        ("spec/baseline/plan-complete.txt",),
        ("spec/baseline/plans/plan-complete.marker",),
    ),
    "i2h-execute": (
        ("spec/execution/stage5-complete.txt", "spec/migration-report.md"),
        ("spec/execute/stage5-complete.txt", "spec/execute/migration-report.md"),
    ),
    "i2h-verify": (
        ("spec/verify-report.md",),
        ("spec/verify/verify-report.md",),
        ("spec/verify/report.md",),
    ),
    "i2h-retrospect": (
        ("spec/retrospect-complete.txt",),
        ("spec/retrospect/complete.txt",),
        ("docs/retrospect-complete.txt",),
    ),
}

# Public projections used by launchers and diagnostics.  Keep the grouped
# representation above as the source of truth because execute has a marker
# plus a report that must be present together.
CANONICAL_STAGE_PATHS: dict[str, tuple[str, ...]] = {
    stage: groups[0] for stage, groups in STAGE_PATH_ALIASES.items()
}
LEGACY_STAGE_PATHS: dict[str, tuple[tuple[str, ...], ...]] = {
    stage: groups[1:] for stage, groups in STAGE_PATH_ALIASES.items()
}
# A short alias is convenient for callers that only need to enumerate legacy
# alternatives.  The grouped ``LEGACY_STAGE_PATHS`` remains available when a
# marker consists of more than one required file.
LEGACY_PATH_ALIASES = LEGACY_STAGE_PATHS


@dataclass(frozen=True)
class StageResolution:
    stage: str
    paths: tuple[Path, ...]
    legacy: bool
    missing: tuple[str, ...]

    @property
    def complete(self) -> bool:
        return bool(self.paths) and not self.missing

    def as_dict(self, root: Path) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "complete": self.complete,
            "legacy": self.legacy,
            "paths": [p.relative_to(root).as_posix() for p in self.paths],
            "missing": list(self.missing),
        }


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def file_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def content_hash(paths: Iterable[str | Path], root: str | Path | None = None) -> str:
    root_path = Path(root).resolve() if root else None
    rows: list[tuple[str, bytes]] = []
    for item in paths:
        path = Path(item)
        resolved = path.resolve()
        if root_path:
            try:
                name = resolved.relative_to(root_path).as_posix()
            except ValueError:
                # Callers should normally keep artifacts under ``root``.  Do
                # not silently hash two external files under the same name,
                # though; use a stable absolute path and let write_marker's
                # stricter relative_to check reject it when needed.
                name = resolved.as_posix()
        else:
            name = str(path)
        rows.append((name, path.read_bytes()))
    digest = hashlib.sha256()
    for name, data in sorted(rows):
        encoded = name.encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


def normalize_hash(value: str | None) -> str | None:
    if not value:
        return None
    return str(value).strip().lower().removeprefix("sha256:")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _resolve_group(root: Path, group: tuple[str, ...]) -> tuple[tuple[Path, ...], tuple[str, ...]]:
    paths = tuple(root / rel for rel in group)
    existing = tuple(path for path in paths if path.is_file())
    missing = tuple(rel for rel, path in zip(group, paths) if not path.is_file())
    return existing, missing


def resolve_stage(root: str | Path, stage: str) -> StageResolution:
    root = Path(root).expanduser().resolve()
    if stage not in STAGE_PATH_ALIASES:
        raise ValueError(f"unknown stage: {stage}")
    groups = STAGE_PATH_ALIASES[stage]
    # If any canonical artifact exists, it owns the stage even when the group
    # is incomplete.  Falling through to an old complete alias would allow a
    # stale marker to hide a newly started canonical run.
    canonical_paths, canonical_missing = _resolve_group(root, groups[0])
    if canonical_paths:
        return StageResolution(stage, canonical_paths, False, canonical_missing)
    for index, group in enumerate(groups[1:], 1):
        paths, missing = _resolve_group(root, group)
        if paths and not missing:
            return StageResolution(stage, paths, index > 0, ())
        if paths:
            return StageResolution(stage, paths, index > 0, missing)
    return StageResolution(stage, (), False, groups[0])


def write_marker(
    path: str | Path,
    stage: str,
    artifact_paths: Iterable[str | Path] = (),
    inputs_sha256: str | None = None,
    mode: str = "static-only",
    *,
    root: str | Path | None = None,
    producer: str = "i2h-run",
    fixture: bool = False,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write a content-addressed schema-2 marker atomically."""
    marker = Path(path)
    root_path = Path(root).expanduser().resolve() if root else marker.parent.resolve()
    artifacts: list[dict[str, str]] = []
    for item in artifact_paths:
        artifact = Path(item)
        if not artifact.is_absolute():
            artifact = root_path / artifact
        if not artifact.is_file():
            raise FileNotFoundError(artifact)
        rel = artifact.resolve().relative_to(root_path).as_posix()
        artifacts.append({"path": rel, "sha256": file_sha256(artifact)})
    artifacts.sort(key=lambda row: row["path"])
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "stage": stage,
        "status": "PASS",
        "mode": mode,
        "producer": producer,
        "inputs_sha256": normalize_hash(inputs_sha256),
        "artifacts": artifacts,
        "content_sha256": canonical_hash(artifacts),
        # Operational fields are part of the completion contract.  Callers
        # may replace them with measured values via ``metadata``.
        "started_at": utc_now(),
        "ended_at": utc_now(),
        "queue_time_ms": 0,
        "retry_count": 0,
        "cache_hit": False,
        "usage": {},
    }
    if metadata:
        payload.update({key: value for key, value in metadata.items() if key in {
            "started_at", "ended_at", "queue_time_ms", "retry_count", "cache_hit", "usage"
        }})
    if fixture:
        payload["fixture"] = True
    marker.parent.mkdir(parents=True, exist_ok=True)
    tmp = marker.with_name(marker.name + ".tmp")
    tmp.write_text(canonical_json(payload) + "\n", encoding="utf-8")
    tmp.replace(marker)
    return payload


def read_marker(path: str | Path) -> dict[str, Any]:
    marker = Path(path)
    try:
        value = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {"schema_version": 0, "status": "legacy", "error": str(exc)}
    return value if isinstance(value, dict) else {"schema_version": 0, "status": "legacy"}


def validate_marker(
    path: str | Path,
    stage: str,
    expected_hash: str | None = None,
    *,
    allow_legacy: bool = True,
    root: str | Path | None = None,
) -> dict[str, Any]:
    marker = Path(path)
    result: dict[str, Any] = {
        "stage": stage,
        "path": str(marker),
        "valid": False,
        "legacy": False,
        "errors": [],
        "warnings": [],
    }
    if not marker.is_file():
        result["errors"].append("marker_missing")
        return result
    payload = read_marker(marker)
    schema = payload.get("schema_version", 0)
    if schema == 0:
        if allow_legacy and marker.read_text(encoding="utf-8", errors="ignore").strip():
            result["legacy"] = True
            result["warnings"].append("legacy_marker_unhashed")
            return result
        result["errors"].append("marker_not_json")
        return result
    if schema not in (1, SCHEMA_VERSION):
        result["errors"].append("marker_schema_unsupported")
    if payload.get("stage") != stage:
        result["errors"].append("marker_stage_mismatch")
    if payload.get("status") not in ("PASS", "complete", "COMPLETED"):
        result["errors"].append("marker_status_invalid")
    actual = normalize_hash(payload.get("inputs_sha256") or payload.get("input_sha256"))
    expected = normalize_hash(expected_hash)
    if not actual:
        result["errors"].append("marker_hash_missing")
    elif expected and actual != expected:
        result["errors"].append("marker_hash_mismatch")
    if schema == SCHEMA_VERSION:
        artifacts = payload.get("artifacts", [])
        if not isinstance(artifacts, list):
            result["errors"].append("artifacts_invalid")
        else:
            if payload.get("content_sha256") != canonical_hash(artifacts):
                result["errors"].append("marker_content_hash_mismatch")
            if root:
                root_path = Path(root).expanduser().resolve()
                for item in artifacts:
                    if not isinstance(item, dict) or not item.get("path") or not item.get("sha256"):
                        result["errors"].append("artifact_record_invalid")
                        continue
                    artifact = root_path / str(item["path"])
                    try:
                        artifact.resolve().relative_to(root_path)
                    except ValueError:
                        result["errors"].append("artifact_outside_root")
                        continue
                    if not artifact.is_file():
                        result["errors"].append("artifact_missing")
                    elif file_sha256(artifact) != normalize_hash(item["sha256"]):
                        result["errors"].append("artifact_hash_mismatch")
    else:
        result["legacy"] = True
        result["warnings"].append("legacy_marker_schema")
    # Schema-1 markers remain readable for migration diagnostics, but they do
    # not carry content-addressed evidence and therefore cannot satisfy a
    # stage completion gate.  Callers that want to permit them can inspect
    # ``legacy`` and rewrite with write_marker().
    result["valid"] = not result["errors"] and schema == SCHEMA_VERSION
    return result


def stage_status(
    root: str | Path,
    stage: str,
    expected_hash: str | None = None,
    *,
    allow_legacy: bool = True,
) -> dict[str, Any]:
    root_path = Path(root).expanduser().resolve()
    resolution = resolve_stage(root_path, stage)
    result = resolution.as_dict(root_path)
    if not resolution.complete:
        result.update({"valid": False, "errors": ["required_artifact_missing"]})
        return result
    checked = validate_marker(
        resolution.paths[0], stage, expected_hash,
        allow_legacy=allow_legacy, root=root_path,
    )
    # A schema-2 marker in an old path is still content-addressed, so it can
    # advance in compatibility mode while emitting a migration warning.  The
    # strict launcher mode rejects that path and asks the caller to rewrite it
    # under the canonical location.  Schema-1/text markers remain readable
    # for diagnostics but never advance because they carry no content hash.
    legacy_path_blocked = resolution.legacy and not allow_legacy
    warnings = list(dict.fromkeys([*checked.get("warnings", []), *(["legacy_marker_path"] if resolution.legacy else [])]))
    errors = list(checked.get("errors", []))
    if legacy_path_blocked:
        errors = list(dict.fromkeys([*errors, "legacy_marker_path_disallowed"]))
    result.update({
        "valid": checked["valid"] and not checked.get("legacy") and not legacy_path_blocked,
        "legacy": resolution.legacy or checked.get("legacy", False),
        "marker": checked,
        "warnings": warnings,
        "errors": errors,
    })
    return result
