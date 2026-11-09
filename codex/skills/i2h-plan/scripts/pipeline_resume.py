#!/usr/bin/env python3
"""Deterministic completion and resume contract for $i2h-run.

The slash command remains the 模型 orchestration layer. This module supplies
one deterministic preflight: canonical indexed-v1 paths win, known legacy
paths are accepted explicitly, marker hashes are checked, and schema-2 UI
Delivery must be approved before execute can resume.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
# ``migbot-install.py`` copies shared helpers into the project-local
# ``.migbot/bin`` tree, while source-tree tests import them from ``migbot``.
# Keep both layouts importable so the command works after a real install as
# well as from a checkout.  The current working directory is included for a
# plugin-managed script invoked against a separate project via ``--project-root``.
_PIPELINE_DIRS = (
    Path.cwd() / ".migbot/bin/scripts/pipeline",
    _PROJECT_ROOT / ".migbot/bin/scripts/pipeline",
    _PROJECT_ROOT / "migbot/bin/scripts/pipeline",
)
for _pipeline_dir in _PIPELINE_DIRS:
    if _pipeline_dir.is_dir() and str(_pipeline_dir) not in sys.path:
        sys.path.insert(0, str(_pipeline_dir))

from marker_contract import (  # type: ignore[import-not-found]
    STAGE_PATH_ALIASES,
    normalize_hash,
    read_marker,
    resolve_stage,
    stage_status,
)
import ui_state_ownership  # type: ignore[import-not-found]
import ui_delivery  # type: ignore[import-not-found]

STAGES = ("i2h-spec", "i2h-plan", "i2h-execute", "i2h-verify", "i2h-retrospect")


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def target_input_hash(root: Path) -> str | None:
    for rel in ("spec/.i2h/target-input.json", "spec/.i2h/resources-inventory.json"):
        value = _read_json(root / rel)
        if value and isinstance(value.get("target_input_sha256"), str):
            return normalize_hash(value["target_input_sha256"])
    return None


def _delivery_candidates(root: Path) -> tuple[Path, ...]:
    return (
        root / "spec/baseline/ui-delivery-approved.json",
        root / "spec/baseline/plans/stage1-ui-delivery.json",
        root / "spec/baseline/plans/ui-delivery-approved.json",
    )


def _delivery_path(root: Path) -> Path | None:
    return next((candidate for candidate in _delivery_candidates(root) if candidate.is_file()), None)


def _ownership_receipt(root: Path, inventory: dict[str, Any] | None) -> dict[str, Any]:
    """Check the execute-time ownership receipt without hiding a pending step.

    The first $i2h-run preflight can legitimately arrive before execute has
    materialized the receipt.  That state is incomplete but has no hard error,
    so the command can write the receipt and rerun the checker.  Once a receipt
    exists, it must be a PASS and must still describe the current inventory.
    """
    path = root / "spec/execution/ui-state-ownership.json"
    result: dict[str, Any] = {
        "complete": False,
        "path": path.relative_to(root).as_posix(),
        "status": "PENDING",
        "errors": [],
        "warnings": [],
    }
    if not path.is_file():
        result["warnings"].append("ownership_receipt_missing")
        return result
    receipt = _read_json(path)
    if receipt is None:
        result["errors"].append("ownership_receipt_invalid_json")
        return result
    result["receipt"] = receipt
    result["status"] = receipt.get("status")
    if receipt.get("status") != "PASS":
        result["errors"].append("ownership_receipt_not_pass")
    if inventory is not None:
        try:
            expected = ui_state_ownership.review(root, inventory)
        except (TypeError, ValueError, KeyError) as exc:
            result["errors"].append("ownership_receipt_review_error")
            result["review_error"] = str(exc)
        else:
            # Compare the deterministic fields only; a caller may add
            # producer/timestamp metadata without making the receipt stale.
            for key in ("status", "errors", "owners"):
                if receipt.get(key) != expected.get(key):
                    result["errors"].append("ownership_receipt_stale")
                    break
    result["complete"] = not result["errors"] and result["status"] == "PASS"
    return result


def _validate_marker_artifacts(root: Path, stage: str, marker: dict[str, Any]) -> list[str]:
    """Require each resumable stage marker to bind its gate artifact."""
    payload = None
    paths = marker.get("paths", []) if isinstance(marker, dict) else []
    if paths:
        payload = read_marker(root / str(paths[0]))
    artifacts = payload.get("artifacts", []) if isinstance(payload, dict) else []
    names = {str(item.get("path")) for item in artifacts if isinstance(item, dict)}
    if stage == "i2h-spec":
        if not any(name.endswith(("spec/.i2h/resources-inventory.json", "spec/.i2h/target-input.json")) for name in names):
            return ["marker_required_spec_evidence_missing"]
    elif stage == "i2h-plan":
        delivery_names = {
            candidate.relative_to(root).as_posix()
            for candidate in _delivery_candidates(root)
        }
        if not any(name in delivery_names for name in names):
            return ["marker_required_delivery_missing"]
    elif stage == "i2h-execute":
        if not any(name.endswith("migration-report.md") for name in names):
            return ["marker_required_migration_report_missing"]
    elif stage == "i2h-retrospect":
        if not any("retrospect-report" in name and name.endswith(".md") for name in names):
            return ["marker_required_retrospect_report_missing"]
    return []


def validate_delivery(root: Path, input_hash: str | None) -> dict[str, Any]:
    """Validate the approved schema-2 inventory used by i2h-execute."""
    path = _delivery_path(root)
    result: dict[str, Any] = {
        "complete": False,
        "path": path.relative_to(root).as_posix() if path else None,
        "errors": [],
        "warnings": [],
    }
    if path is None:
        result["errors"].append("schema2_delivery_missing")
        return result
    data = _read_json(path)
    if data is None:
        result["errors"].append("schema2_delivery_invalid_json")
        return result
    result["inventory"] = data
    if data.get("schema_version") != 2:
        result["errors"].append("schema2_delivery_version")
    if data.get("status") != "approved":
        result["errors"].append("schema2_delivery_not_approved")
    delivery_hash = normalize_hash(data.get("target_input_sha256"))
    if not delivery_hash:
        result["errors"].append("schema2_delivery_input_hash_missing")
    elif input_hash and delivery_hash != input_hash:
        result["errors"].append("schema2_delivery_input_hash")
    units = data.get("units")
    if not isinstance(units, list) or not units:
        result["errors"].append("schema2_delivery_units")
    else:
        seen_ids: set[str] = set()
        # `state_id` is local to the page that owns it.  A full-ui inventory
        # legitimately uses `default/content` for every page.  Keep the
        # global fallback for hand-authored units that omit page_id so malformed
        # minimal inventories still fail closed.
        seen_content: dict[tuple[str, str], str] = {}
        for unit in units:
            if not isinstance(unit, dict):
                result["errors"].append("schema2_delivery_unit_invalid")
                continue
            unit_id = str(unit.get("unit_id", ""))
            if not unit_id or unit_id in seen_ids:
                result["errors"].append("schema2_delivery_unit_id")
            seen_ids.add(unit_id)
            output = unit.get("output")
            if not isinstance(output, dict) or not output.get("file"):
                result["errors"].append("schema2_delivery_output")
            states = unit.get("required_states")
            if not isinstance(states, list) or not states:
                result["errors"].append("schema2_delivery_states")
            for state in states if isinstance(states, list) else []:
                if not isinstance(state, dict) or not state.get("state_id"):
                    result["errors"].append("schema2_delivery_state_invalid")
                    continue
                if state.get("responsibility", "content") == "content":
                    key = (str(unit.get("page_id") or "__global__"), str(state["state_id"]))
                    previous = seen_content.get(key)
                    if previous and previous != unit_id:
                        result["errors"].append("schema2_delivery_duplicate_content")
                    seen_content[key] = unit_id
    # The inventory's duplicate checks are intentionally repeated by the
    # ownership checker used by i2h-execute.  Calling it here makes the
    # preflight and execute consume the same deterministic contract, while
    # retaining its structured diagnostics in the status JSON.
    try:
        ownership = ui_state_ownership.review(root, data)
    except (TypeError, ValueError, KeyError) as exc:
        result["errors"].append("schema2_delivery_ownership_error")
        result["ownership_error"] = str(exc)
    else:
        result["ownership"] = ownership
        if ownership.get("status") != "PASS":
            result["errors"].append("schema2_delivery_ownership")
    try:
        contract = ui_delivery.validate(root, data)
    except (TypeError, ValueError, KeyError) as exc:
        result["errors"].append("schema2_delivery_contract_error")
        result["contract_error"] = str(exc)
    else:
        result["contract"] = contract.get("validation", {})
        if contract.get("status") != "validated":
            result["errors"].append("schema2_delivery_contract")
    result["complete"] = not result["errors"]
    return result


def _verify_report(root: Path) -> dict[str, Any]:
    result = {"complete": False, "path": None, "errors": [], "warnings": []}
    candidates = (root / "spec/verify-report.md", root / "spec/verify/verify-report.md", root / "spec/verify/report.md")
    path = next((candidate for candidate in candidates if candidate.is_file()), None)
    if path is None:
        result["errors"].append("verify_report_missing")
        return result
    result["path"] = path.relative_to(root).as_posix()
    text = path.read_text(encoding="utf-8", errors="replace")
    if "CHECK-1" not in text:
        result["errors"].append("verify_check1_missing")
    if not re.search(r"(?:PASS|DEFERRED|SKIP|PARTIAL)", text, re.I):
        result["errors"].append("verify_status_missing")
    result["complete"] = not result["errors"]
    return result


def _report(root: Path, stage: str) -> dict[str, Any]:
    result = {"complete": False, "path": None, "errors": [], "warnings": []}
    if stage == "i2h-execute":
        candidates = (root / "spec/migration-report.md", root / "spec/execute/migration-report.md")
        identity = ("migration", "迁移", "execute", "执行", "mode")
        status = ("static-only", "DEFERRED", "PASS", "success", "成功", "failed", "失败", "error", "错误")
    else:
        candidates = tuple(sorted((root / "docs").glob("retrospect-report*.md"))) + (root / "docs/retrospect-report.md",)
        identity = ("retrospect", "回顾", "迁移度量", "指标")
        status = ("static-only", "DEFERRED", "PASS", "success", "成功", "failed", "失败", "error", "错误")
    path = next((candidate for candidate in candidates if candidate.is_file()), None)
    if path is None:
        result["errors"].append(f"{stage}_report_missing")
        return result
    result["path"] = path.relative_to(root).as_posix()
    text = path.read_text(encoding="utf-8", errors="replace")
    if not re.search("|".join(map(re.escape, identity)), text, re.I):
        result["errors"].append(f"{stage}_report_identity")
    if not re.search("|".join(map(re.escape, status)), text, re.I):
        result["errors"].append(f"{stage}_report_status")
    result["complete"] = not result["errors"]
    return result


def pipeline_status(root: str | Path, *, allow_legacy: bool = True) -> dict[str, Any]:
    root = Path(root).expanduser().resolve()
    input_hash = target_input_hash(root)
    stages: list[dict[str, Any]] = []
    for stage in STAGES:
        if stage == "i2h-verify":
            resolution = resolve_stage(root, stage)
            legacy_blocked = resolution.legacy and not allow_legacy
            marker = {
                "stage": stage,
                "valid": bool(resolution.paths) and not legacy_blocked,
                "legacy": resolution.legacy,
                "paths": [p.relative_to(root).as_posix() for p in resolution.paths],
                "missing": list(resolution.missing),
                "errors": ["legacy_marker_path_disallowed"] if legacy_blocked else [],
                "warnings": ["legacy_marker_path"] if resolution.legacy else [],
            }
        else:
            marker = stage_status(root, stage, input_hash, allow_legacy=allow_legacy)
            if input_hash is None and marker.get("valid"):
                marker["valid"] = False
                marker.setdefault("errors", []).append("target_input_hash_missing")
            if marker.get("valid"):
                required_errors = _validate_marker_artifacts(root, stage, marker)
                if required_errors:
                    marker["valid"] = False
                    marker.setdefault("errors", []).extend(required_errors)
        checks: dict[str, Any] = {"marker": marker}
        if stage == "i2h-plan":
            checks["delivery"] = validate_delivery(root, input_hash)
        elif stage == "i2h-execute":
            checks["report"] = _report(root, stage)
            delivery = _delivery_path(root)
            checks["ownership"] = _ownership_receipt(root, _read_json(delivery) if delivery else None)
        elif stage == "i2h-verify":
            # verify-report.md is the report itself, not a JSON marker.
            checks["report"] = _verify_report(root)
        elif stage == "i2h-retrospect":
            checks["report"] = _report(root, stage)
        complete = all(bool(item.get("valid", item.get("complete", False))) for item in checks.values())
        stages.append({"stage": stage, "complete": complete, "checks": checks})
    resume = next((item["stage"] for item in stages if not item["complete"]), "complete")
    return {
        "schema_version": 1,
        "status": "complete" if resume == "complete" else "incomplete",
        "project_root": str(root),
        "target_input_sha256": input_hash,
        "resume_stage": resume,
        "stages": stages,
        "legacy_paths": {
            stage: [path for group in groups[1:] for path in group]
            for stage, groups in STAGE_PATH_ALIASES.items()
            if len(groups) > 1
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--out")
    parser.add_argument("--strict", action="store_true", help="do not accept legacy marker schemas")
    args = parser.parse_args(argv)
    result = pipeline_status(args.project_root, allow_legacy=not args.strict)
    if args.out:
        path = Path(args.out)
        if not path.is_absolute():
            path = Path(args.project_root).expanduser().resolve() / path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
