#!/usr/bin/env python3
"""Deterministic completion and resume contract for /i2h-run.

The slash command remains the Claude orchestration layer. This module supplies
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
    file_sha256,
    normalize_hash,
    read_marker,
    resolve_stage,
    stage_status,
)
import ui_state_ownership  # type: ignore[import-not-found]
import ui_delivery  # type: ignore[import-not-found]
from acceptance_plan import BEHAVIOR_REPORT, replay_behavior

STAGES = ("i2h-spec", "i2h-plan", "i2h-execute", "i2h-verify", "i2h-retrospect")
VERIFY_CHECKS = tuple(f"CHECK-{index}" for index in range(1, 6))
_CHECK_ROW = re.compile(r"^(CHECK-[1-5])(?:\s|$)")
_CHECK_RESULT = re.compile(r"^(?:PASS|FAIL(?:-VISUAL|-FUNCTIONAL)?|PARTIAL|DEFERRED|SKIP|WARN|ERROR)$")

# Plan owns these two handoff documents and may append decisions or normalize
# the feature index after i2h-spec has written its marker.  Their mutation is
# safe to acknowledge only after the content-addressed i2h-plan marker and
# schema-2 delivery have both passed.  Any other spec artifact mutation keeps
# the fail-closed i2h-spec resume behavior.
_PLAN_HANDOFF_ARTIFACTS = frozenset({
    "spec/baseline/feature-index.md",
    "spec/decision-ledger.md",
})


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

    The first /i2h-run preflight can legitimately arrive before execute has
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


def _spec_handoff_mismatches(root: Path) -> list[str]:
    """Return spec marker artifacts changed by the completed plan handoff."""
    marker_path = root / "spec/baseline/spec-complete.txt"
    payload = _read_json(marker_path)
    if not payload:
        return []
    mismatches: list[str] = []
    for item in payload.get("artifacts", []):
        if not isinstance(item, dict):
            continue
        relative = item.get("path")
        expected = normalize_hash(item.get("sha256"))
        if not isinstance(relative, str) or not expected:
            continue
        path = root / relative
        if path.is_file() and normalize_hash(file_sha256(path)) != expected:
            mismatches.append(relative)
    return sorted(mismatches)


def validate_delivery(root: Path, input_hash: str | None, *, require_runtime_plan: bool = False) -> dict[str, Any]:
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
    verification_states = data.get("verification_states")
    verification_count = 0
    if isinstance(verification_states, list):
        verification_count = sum(isinstance(state, dict) and bool(state) for state in verification_states)
    preview_only_units = []
    missing_host_slots = []
    for unit in units if isinstance(units, list) else []:
        if not isinstance(unit, dict) or unit.get("required") is False:
            continue
        if unit.get("presentation_role") in {"embedded", "hosted_destination"}:
            integration = unit.get("integration")
            slots = integration if isinstance(integration, list) else [integration]
            output = unit.get("output")
            if (not isinstance(output, dict) or not output.get("symbol") or not slots
                    or any(not isinstance(slot, dict) or not slot.get("host_file") or not slot.get("host_builder")
                           or slot.get("child_symbol") != output.get("symbol") for slot in slots)):
                missing_host_slots.append(str(unit.get("unit_id", "")))
        states = unit.get("required_states")
        if not isinstance(states, list) or not any(
            isinstance(state, dict) and state.get("arrival_mode") in {"formal", "behavior"}
            for state in states
        ):
            preview_only_units.append(str(unit.get("unit_id", "")))
    result["runtime_scope"] = {
        "verification_state_count": verification_count,
        "preview_only_units": preview_only_units,
    }
    if require_runtime_plan and not verification_count:
        result["errors"].append("runtime_verification_states_missing")
    if require_runtime_plan and isinstance(verification_states, list) and verification_states and isinstance(units, list):
        gaps = ui_delivery.visual_binding_gaps(units, verification_states)
        for key, rows in gaps.items():
            if rows:
                result["runtime_scope"][key] = rows
                result["errors"].append(key)
    if require_runtime_plan and preview_only_units:
        result["errors"].append("required_units_without_runtime_arrival")
    if require_runtime_plan and missing_host_slots:
        result["errors"].append("required_host_slots_missing")
        result["runtime_scope"]["missing_host_slots"] = missing_host_slots
    result["complete"] = not result["errors"]
    return result


def validate_immersive_gate(root: Path, inventory: dict[str, Any] | None) -> dict[str, Any]:
    """Require a fresh L1/L2/L3 receipt when source evidence demands it."""
    units = inventory.get("units", []) if isinstance(inventory, dict) else []
    required = [
        str(unit.get("unit_id"))
        for unit in units
        if isinstance(unit, dict) and unit.get("needs_immersive_safearea") is True
    ]
    path = root / "spec/execution/immersive-safearea-gate.json"
    result: dict[str, Any] = {
        "complete": not required,
        "required_units": required,
        "path": path.relative_to(root).as_posix(),
        "errors": [],
        "warnings": [],
    }
    if not required:
        result["status"] = "NOT_REQUIRED"
        return result
    if not path.is_file():
        result["status"] = "MISSING"
        result["errors"].append("immersive_safearea_gate_missing")
        result["complete"] = False
        return result
    receipt = _read_json(path)
    if receipt is None:
        result["status"] = "INVALID"
        result["errors"].append("immersive_safearea_gate_invalid_json")
        return result
    result["receipt"] = receipt
    result["status"] = receipt.get("status")
    if receipt.get("status") != "PASS":
        result["errors"].append("immersive_safearea_gate_not_pass")
    receipt_units = sorted(str(item) for item in receipt.get("required_units", []))
    if receipt_units != sorted(required):
        result["errors"].append("immersive_safearea_gate_scope_stale")
    layers = receipt.get("layers")
    if not isinstance(layers, dict) or any(not isinstance(layers.get(layer), dict) or layers[layer].get("ok") is not True for layer in ("L1", "L2", "L3")):
        result["errors"].append("immersive_safearea_gate_layers_incomplete")
    inventory_path = _delivery_path(root)
    expected_hash = file_sha256(inventory_path) if inventory_path and inventory_path.is_file() else None
    if expected_hash and receipt.get("inventory_sha256") != expected_hash:
        result["errors"].append("immersive_safearea_gate_inventory_stale")
    result["complete"] = not result["errors"]
    return result


def _verify_summary(text: str) -> dict[str, str]:
    checks: dict[str, str] = {}
    for line in text.splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cells = [cell.strip().strip("*` ").upper() for cell in line.strip().strip("|").split("|")]
        label = _CHECK_ROW.match(cells[0])
        if not label or len(cells) < 3:
            continue
        status = cells[2]
        if _CHECK_RESULT.fullmatch(status):
            check = label[1]
            checks[check] = status if checks.get(check, status) == status else "CONFLICT"
    return checks


def _verify_report(root: Path, require_visual_and_ut: bool, require_behavior: bool = False) -> dict[str, Any]:
    required = VERIFY_CHECKS[:4] if require_visual_and_ut else ()
    if require_behavior:
        required += ("CHECK-5",)
    result = {
        "complete": False, "path": None, "errors": [], "warnings": [],
        "required_checks": list(required), "reported_checks": {},
        "unpassed_checks": dict.fromkeys(VERIFY_CHECKS, "NOT_REPORTED"),
    }
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
    checks = _verify_summary(text)
    result["reported_checks"] = checks
    result["unpassed_checks"] = {
        check: checks.get(check, "NOT_REPORTED") for check in VERIFY_CHECKS if checks.get(check) != "PASS"
    }
    if any(check in result["unpassed_checks"] for check in required):
        result["errors"].append("required_verify_checks_not_passed")
    if require_behavior and checks.get("CHECK-5") == "PASS":
        evidence = root / BEHAVIOR_REPORT
        evidence_error = None
        if not evidence.is_file():
            evidence_error = "behavior_receipt_missing"
        elif f"behavior-summary-sha256: {file_sha256(evidence)}" not in text.splitlines():
            evidence_error = "behavior_receipt_unbound"
        else:
            try:
                report = _read_json(evidence)
                if replay_behavior(root, report) != report:
                    evidence_error = "behavior_receipt_stale"
            except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
                evidence_error = "behavior_receipt_invalid"
                result["behavior_diagnostic"] = str(exc)
        if evidence_error:
            result["errors"].append(evidence_error)
            result["unpassed_checks"]["CHECK-5"] = "UNVERIFIED"
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


def pipeline_status(root: str | Path, *, allow_legacy: bool = True,
                    require_visual_and_ut: bool = False, require_runtime_plan: bool = False,
                    require_behavior: bool = False) -> dict[str, Any]:
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
            checks["delivery"] = validate_delivery(root, input_hash, require_runtime_plan=require_runtime_plan)
        elif stage == "i2h-execute":
            checks["report"] = _report(root, stage)
            delivery = _delivery_path(root)
            checks["ownership"] = _ownership_receipt(root, _read_json(delivery) if delivery else None)
            checks["immersive_safearea"] = validate_immersive_gate(root, _read_json(delivery) if delivery else None)
        elif stage == "i2h-verify":
            # verify-report.md is the report itself, not a JSON marker.
            checks["report"] = _verify_report(root, require_visual_and_ut, require_behavior)
        elif stage == "i2h-retrospect":
            checks["report"] = _report(root, stage)
        complete = all(bool(item.get("valid", item.get("complete", False))) for item in checks.values())
        stages.append({"stage": stage, "complete": complete, "checks": checks})

    # i2h-plan legitimately appends decision-ledger entries and can normalize
    # feature-index handoff text after the spec marker was written.  Once the
    # plan marker and delivery contract pass, do not send /i2h-run back to the
    # expensive LLM-driven spec stage for those two known handoff mutations.
    # Preserve the mismatch as an auditable warning.  Source/spec mutations
    # outside this allow-list remain fail-closed and still resume at i2h-spec.
    spec_row, plan_row = stages[0], stages[1]
    handoff_mismatches = _spec_handoff_mismatches(root)
    if (
        not spec_row["complete"]
        and plan_row["checks"]["marker"]["valid"]
        and handoff_mismatches
        and set(handoff_mismatches) <= _PLAN_HANDOFF_ARTIFACTS
        and set(spec_row["checks"]["marker"].get("errors", [])) <= {"artifact_hash_mismatch"}
    ):
        marker_check = spec_row["checks"]["marker"]
        marker_check.setdefault("warnings", []).append("spec_handoff_artifact_changed_after_plan")
        marker_check["handoff_mismatches"] = handoff_mismatches
        marker_check["handoff_only"] = True
        spec_row["complete"] = True
    resume = next((item["stage"] for item in stages if not item["complete"]), "complete")
    return {
        "schema_version": 1,
        "status": "complete" if resume == "complete" else "incomplete",
        "project_root": str(root),
        "target_input_sha256": input_hash,
        "resume_stage": resume,
        "verification": stages[3]["checks"]["report"],
        "stages": stages,
        "legacy_paths": {
            stage: [path for group in groups[1:] for path in group]
            for stage, groups in STAGE_PATH_ALIASES.items()
            if len(groups) > 1
        },
    }


def status_summary(result: dict[str, Any], report_path: Path | None = None) -> dict[str, Any]:
    check_fields = ("valid", "complete", "status", "path", "paths", "legacy", "missing", "errors", "warnings",
                    "required_checks", "reported_checks", "unpassed_checks", "handoff_only", "handoff_mismatches")
    stages = []
    for stage in result["stages"]:
        checks = {name: {field: check[field] for field in check_fields if field in check}
                  for name, check in stage["checks"].items()}
        stages.append({"stage": stage["stage"], "complete": stage["complete"], "checks": checks})
    summary = {field: result[field] for field in ("schema_version", "status", "project_root",
                                                  "target_input_sha256", "resume_stage", "legacy_paths")}
    summary.update({"view": "summary", "verification": stages[3]["checks"]["report"], "stages": stages})
    if report_path is not None:
        summary["report_path"] = str(report_path)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--out")
    parser.add_argument("--summary", action="store_true",
                        help="print a compact decision view; --out still receives the full report")
    parser.add_argument("--strict", action="store_true", help="do not accept legacy marker schemas")
    parser.add_argument("--require-visual-and-ut", action="store_true",
                        help="require report summary PASS for CHECK-1 through CHECK-4")
    parser.add_argument("--require-runtime-plan", action="store_true",
                        help="require runtime arrivals and planned verification states before execute")
    parser.add_argument("--require-behavior", action="store_true",
                        help="require CHECK-5 PASS with replayable native UITest evidence")
    parser.add_argument("--timing", choices=("start", "finish"))
    parser.add_argument("--timing-stage", choices=STAGES[:4])
    parser.add_argument("--timing-run")
    args = parser.parse_args(argv)
    if bool(args.timing) != bool(args.timing_stage) or (args.timing_run and not args.timing):
        parser.error("use --timing and --timing-stage together")
    result = pipeline_status(args.project_root, allow_legacy=not args.strict,
                             require_visual_and_ut=args.require_visual_and_ut,
                             require_runtime_plan=args.require_runtime_plan,
                             require_behavior=args.require_behavior)
    path = None
    if args.out:
        path = Path(args.out)
        if not path.is_absolute():
            path = Path(args.project_root).expanduser().resolve() / path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output = status_summary(result, path) if args.summary else result
    if args.timing:
        from pipeline_timing import record

        flags = {"runtime_plan": args.require_runtime_plan, "visual_and_ut": args.require_visual_and_ut,
                 "behavior": args.require_behavior}
        try:
            output["timing"] = record(Path(result["project_root"]), result, flags,
                                      args.timing, args.timing_stage, args.timing_run)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            parser.exit(2, f"pipeline timing: {exc}\n")
    print(json.dumps(output, ensure_ascii=False))
    return 0 if result["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
