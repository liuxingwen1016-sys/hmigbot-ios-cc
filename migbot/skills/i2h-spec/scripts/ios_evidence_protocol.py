#!/usr/bin/env python3
"""Bounded, source-backed evidence protocol for i2h UI captures.

The protocol keeps source/runtime evidence useful without making a simulator or
Harmony device a mandatory dependency of i2h-spec.  A capture is current only
when its source, build, device, scenario, configuration and checkpoint identity
still match the request that consumes it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


CAPTURE_SCHEMA = "hmigbot-ios-ui-evidence/1"
PAIR_SCHEMA = "hmigbot-ui-pair/1"
PLATFORMS = {"ios", "harmonyos"}
EXCEPTION_CATEGORIES = {"design_difference", "config_difference", "dynamic_content"}
SEVERITY_WEIGHTS = {"high": 0.05, "medium": 0.02, "low": 0.01}
EXCLUDED_PARTS = {".git", ".build", "DerivedData", "build", "dist", "node_modules"}


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid evidence JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"evidence must be a JSON object: {path}")
    return value


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _iter_files(root: Path) -> Iterable[Path]:
    root = root.expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"evidence root is not a directory: {root}")
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        if any(part in EXCLUDED_PARTS for part in path.relative_to(root).parts):
            continue
        yield path


def source_identity(root: Path | str) -> str:
    """Hash source paths and bytes without including generated build output."""
    root = Path(root).expanduser().resolve()
    digest = hashlib.sha256()
    for path in _iter_files(root):
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def bundle_identity(app: Path | str) -> str:
    """Fingerprint an app bundle while ignoring volatile code-signing metadata."""
    return source_identity(Path(app))


def _identity(value: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("evidence identity must be an object")
    required = ("platform", "page_id", "state_id", "scenario_id", "configuration_id", "checkpoint_id")
    missing = [key for key in required if not isinstance(value.get(key), str) or not value[key]]
    if missing:
        raise ValueError("evidence identity missing: " + ", ".join(missing))
    if value["platform"] not in PLATFORMS:
        raise ValueError("unsupported evidence platform: " + str(value["platform"]))
    for key in ("source_sha256", "build_sha256", "screenshot_sha256", "ui_json_sha256", "foreground_receipt_sha256", "foreground_ack_sha256"):
        if value.get(key) is not None and (not isinstance(value[key], str) or len(value[key]) != 64):
            raise ValueError(f"invalid identity hash: {key}")
    if value["platform"] == "ios" and not isinstance(value.get("device_udid"), str):
        raise ValueError("iOS evidence requires exact device_udid")
    return value


def validate_manifest(path: Path | str, current: dict[str, Any] | None = None) -> dict[str, Any]:
    """Validate a capture manifest and optionally bind it to current inputs."""
    path = Path(path).expanduser().resolve()
    try:
        manifest = _json(path)
        if manifest.get("schema") != CAPTURE_SCHEMA:
            raise ValueError("unsupported capture schema")
        identity = _identity(manifest.get("identity"))
        artifacts = manifest.get("artifacts")
        if not isinstance(artifacts, dict):
            raise ValueError("capture artifacts must be an object")
        issues: list[dict[str, Any]] = []
        for name in ("screenshot", "ui_json", "foreground_receipt", "foreground_ack"):
            item = artifacts.get(name)
            if item is None and name in {"foreground_receipt", "foreground_ack"}:
                continue
            if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                issues.append({"rule": "artifact_missing", "artifact": name})
                continue
            artifact = (path.parent / item["path"]).resolve()
            if not artifact.is_file():
                issues.append({"rule": "artifact_not_found", "artifact": name, "path": item["path"]})
                continue
            actual = sha256_file(artifact)
            if actual != item.get("sha256"):
                issues.append({"rule": "artifact_hash_mismatch", "artifact": name, "expected": item.get("sha256"), "actual": actual})
        if current is not None:
            for key, expected in current.items():
                if expected is None:
                    continue
                if identity.get(key) != expected:
                    issues.append({"rule": "identity_mismatch", "field": key, "expected": expected, "actual": identity.get(key)})
        status = "current" if not issues else "stale"
        return {"status": status, "manifest": manifest, "issues": issues, "manifest_path": str(path)}
    except ValueError as exc:
        return {"status": "invalid", "manifest_path": str(path), "issues": [{"rule": "invalid_manifest", "detail": str(exc)}]}


def _exception_valid(exception: dict[str, Any], difference: dict[str, Any]) -> bool:
    if set(exception) != {"difference_id", "observation_sha256", "category", "reason", "evidence"}:
        return False
    return (
        exception.get("difference_id") == difference.get("id")
        and exception.get("observation_sha256") == difference.get("observation_sha256")
        and exception.get("category") in EXCEPTION_CATEGORIES
        and bool(str(exception.get("reason", "")).strip())
        and isinstance(exception.get("evidence"), dict)
        and bool(exception["evidence"].get("source_manifest_sha256"))
        and bool(exception["evidence"].get("target_manifest_sha256"))
    )


def pair_manifests(source_path: Path | str, target_path: Path | str, *, current: dict[str, Any] | None = None,
                   differences: list[dict[str, Any]] | None = None,
                   exceptions: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Pair current iOS/Harmony manifests without inventing missing evidence."""
    source = validate_manifest(source_path, current)
    target = validate_manifest(target_path, current)
    report: dict[str, Any] = {
        "schema": PAIR_SCHEMA,
        "status": "not_run",
        "source": source,
        "target": target,
        "differences": [],
        "exceptions": [],
        "visual_score": None,
    }
    if not Path(source_path).expanduser().is_file() or not Path(target_path).expanduser().is_file():
        report["status"] = "not_run"
        report["reason"] = "source_or_target_evidence_missing"
        return report
    if source["status"] != "current" or target["status"] != "current":
        report["status"] = "blocked" if source["status"] == "invalid" or target["status"] == "invalid" else "not_run"
        report["reason"] = "source_or_target_evidence_not_current"
        return report
    source_identity_value = source["manifest"]["identity"]
    target_identity_value = target["manifest"]["identity"]
    if source_identity_value["page_id"] != target_identity_value["page_id"] or source_identity_value["checkpoint_id"] != target_identity_value["checkpoint_id"]:
        report["status"] = "blocked"
        report["reason"] = "page_or_checkpoint_mismatch"
        return report
    observed = differences or []
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(observed, 1):
        row = dict(item)
        row.setdefault("id", f"UI-D{index:04d}")
        row.setdefault("severity", "medium")
        row["observation_sha256"] = sha256_bytes(json.dumps(row, ensure_ascii=False, sort_keys=True).encode("utf-8"))
        normalized.append(row)
    report["differences"] = normalized
    accepted: list[dict[str, Any]] = []
    for exception in exceptions or []:
        found = next((item for item in normalized if item["id"] == exception.get("difference_id")), None)
        if found is not None and _exception_valid(exception, found):
            accepted.append(exception)
    report["exceptions"] = accepted
    unresolved = [item for item in normalized if item not in [next((d for d in normalized if d["id"] == e["difference_id"]), None) for e in accepted]]
    if any(item.get("category") in {"control_missing", "state_mismatch", "route_mismatch", "application_error_dialog"} for item in unresolved):
        report["status"] = "fail_functional"
        return report
    penalty = sum(SEVERITY_WEIGHTS.get(str(item.get("severity")), 0.02) for item in unresolved)
    report["visual_score"] = max(0.0, round(1.0 - penalty, 4))
    report["status"] = "pass_visual" if report["visual_score"] >= 0.95 else "fail_visual"
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("--manifest", required=True)
    pair = sub.add_parser("pair")
    pair.add_argument("--source", required=True)
    pair.add_argument("--target", required=True)
    pair.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    if args.command == "validate":
        result = validate_manifest(args.manifest)
    else:
        result = pair_manifests(args.source, args.target)
        Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") in {"current", "pass_visual", "fail_visual", "not_run"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
