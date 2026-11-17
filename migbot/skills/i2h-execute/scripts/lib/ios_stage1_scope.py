"""Build iOS Stage-1 scope and gate data without the Android bundle."""
from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any

from .stage1_visual_scope import baseline, read_snapshot_meta
from .ios_ui_delivery_gate import inspect_delivery
from .stage1_contract import source_digest


MAX_REPAIRS = 2


def acceptance_lane(scope):
    # Source changes and scope filenames cannot reset a budget for the same
    # approved pages and states.
    pairs = sorted((p['page_id'], p['state_id'], p['arrival_mode']) for p in scope['pairs'])
    return hashlib.sha256(json.dumps(pairs, ensure_ascii=False).encode('utf-8')).hexdigest()


def inventory_path(root: Path, value: str | None) -> Path:
    """Get inventory path with central authority priority.

    DEFECT 1 FIX: If standard index EXISTS, ALL wrong schema/not dict/missing
    inventory_source/missing or non-string path/missing or non-string SHA must ValueError.
    NO except-pass/fallback when index exists.
    """
    if value:
        # Explicit selector has priority
        path = Path(value)
        return path if path.is_absolute() else root / path

    # Check for standard native index
    index_path = root / "spec" / "execution" / "ui-inputs" / "index.json"
    if index_path.is_file():
        # Index exists - strict validation, no fallback
        try:
            index_text = index_path.read_text(encoding="utf-8")
            index = json.loads(index_text)
        except (OSError, UnicodeDecodeError) as e:
            raise ValueError(f"malformed index: cannot read index file: {e}")
        except json.JSONDecodeError as e:
            raise ValueError(f"malformed index: invalid JSON: {e}")

        # Index must be a dict
        if not isinstance(index, dict):
            raise ValueError(f"malformed index: index must be a dict, got {type(index).__name__}")

        # Must have schema_version == 2
        schema_version = index.get("schema_version")
        if schema_version != 2:
            raise ValueError(f"malformed index: schema_version must be 2, got {schema_version}")

        # Must have inventory_source
        if "inventory_source" not in index:
            raise ValueError("malformed index: missing inventory_source")

        inv_source = index.get("inventory_source")

        # inventory_source must be a dict
        if not isinstance(inv_source, dict):
            raise ValueError(f"malformed index: inventory_source must be a dict, got {type(inv_source).__name__}")

        # Must have path
        if "path" not in inv_source:
            raise ValueError("malformed index: inventory_source missing path")

        inv_path_rel = inv_source.get("path")

        # path must be a string
        if not isinstance(inv_path_rel, str):
            raise ValueError(f"malformed index: inventory_source.path must be a string, got {type(inv_path_rel).__name__}")

        # Must have sha256
        if "sha256" not in inv_source:
            raise ValueError("malformed index: inventory_source missing sha256")

        inv_sha = inv_source.get("sha256")

        # sha256 must be a string
        if not isinstance(inv_sha, str):
            raise ValueError(f"malformed index: inventory_source.sha256 must be a string, got {type(inv_sha).__name__}")

        # Valid index - return the path
        inv_path = root / inv_path_rel
        return inv_path

    # Fall back to canonical baseline (no index exists)
    return root / "spec" / "baseline" / "ui-delivery-approved.json"


def load_inventory(root: Path, value: str | None) -> tuple[Path, dict[str, Any]]:
    """Load inventory with central authority validation.

    DEFECT 2 FIX: For NON-CANONICAL approved file, require canonical project
    baseline ancestor raw SHA, provenance baseline_path+SHA EXACT canonical file,
    proof_path+SHA mandatory/confined/read and hash valid, and invoke existing
    validate_approved_execution_inventory full replay.
    """
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from ios_inventory_resolution import sha256_file, validate_approved_execution_inventory

    path = inventory_path(root, value).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("approved inventory must be inside the project root")

    if not path.is_file():
        raise ValueError(f"inventory not found: {path}")

    # Verify index SHA if loaded from index
    if not value:  # Default path from index or baseline
        index_path = root / "spec" / "execution" / "ui-inputs" / "index.json"
        if index_path.is_file():
            try:
                index = json.loads(index_path.read_text(encoding="utf-8"))
                if index.get("schema_version") == 2:
                    inv_source = index.get("inventory_source", {})
                    expected_sha = inv_source.get("sha256")
                    # REPAIR 4: reject empty/malformed SHA, always compare bytes
                    if not expected_sha or not isinstance(expected_sha, str) or not expected_sha.strip():
                        raise ValueError(f"malformed index: inventory_source.sha256 is empty or invalid")
                    actual_sha = sha256_file(path)
                    if actual_sha != expected_sha:
                        raise ValueError(f"inventory SHA mismatch: expected {expected_sha}, got {actual_sha}")
            except (json.JSONDecodeError, KeyError) as e:
                raise ValueError(f"malformed index: {e}")

    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema_version") != 2 or data.get("status") != "approved":
        raise ValueError("approved schema-2 UI delivery inventory is required")

    # Validate approval for non-canonical-baseline
    canonical_baseline = root / "spec" / "baseline" / "ui-delivery-approved.json"
    if path.resolve() != canonical_baseline.resolve():
        # DEFECT 2 FIX: Execution-derived inventory must have proper approval with strict validation

        # Must have approval with confirmation_ref
        approval = data.get("approval")
        if not isinstance(approval, dict) or not approval.get("confirmation_ref"):
            raise ValueError("execution inventory missing approval confirmation_ref")

        # Must have validation dict with errors == [] (not None, not missing)
        validation = data.get("validation")
        if not isinstance(validation, dict):
            raise ValueError("execution inventory missing validation dict")

        err_list = validation.get("errors")
        # REPAIR 1: errors must exist as key and be exact empty list []
        if "errors" not in validation:
            raise ValueError("execution inventory validation missing errors field")
        if err_list is None:
            raise ValueError("execution inventory validation.errors is None, must be []")
        if err_list != []:
            raise ValueError(f"execution inventory has validation errors: {err_list}")

        # For receipt-bound approval route, require BOTH candidate_sha256 and validation_receipt_sha256
        # REPAIR 2: BOTH candidate_sha256 AND validation_receipt_sha256 always required
        if not approval.get("candidate_sha256") or not isinstance(approval.get("candidate_sha256"), str):
            raise ValueError("execution inventory approval missing candidate_sha256 hash string")
        if not approval.get("validation_receipt_sha256") or not isinstance(approval.get("validation_receipt_sha256"), str):
            raise ValueError("execution inventory approval missing validation_receipt_sha256 hash string")
        # DEFECT 2 FIX: Require canonical baseline ancestor and full proof validation
        ancestor_sha = data.get("baseline_ancestor_sha256")

        # Must have ancestor SHA
        if not ancestor_sha:
            raise ValueError("derived inventory requires canonical baseline ancestor SHA (baseline_ancestor_sha256)")

        # Canonical baseline must exist
        if not canonical_baseline.is_file():
            raise ValueError("derived inventory requires canonical baseline to exist")

        # Ancestor SHA must match canonical baseline
        baseline_sha = sha256_file(canonical_baseline)
        if baseline_sha != ancestor_sha:
            raise ValueError(f"ancestor SHA mismatch: expected {ancestor_sha}, baseline is {baseline_sha}")

        # DEFECT 2 FIX: Require provenance with proof_path and proof_sha256
        provenance = data.get("provenance", {})

        # REPAIR 3: provenance baseline_path AND baseline_sha256 mandatory
        prov_baseline_path = provenance.get("baseline_path")
        prov_baseline_sha = provenance.get("baseline_sha256")

        if not prov_baseline_path:
            raise ValueError("derived inventory missing provenance.baseline_path")
        if not prov_baseline_sha:
            raise ValueError("derived inventory missing provenance.baseline_sha256")

        # Resolve provenance baseline_path and require EXACT canonical baseline file
        prov_baseline_resolved = (root / prov_baseline_path).resolve()
        if prov_baseline_resolved != canonical_baseline.resolve():
            raise ValueError(f"provenance baseline_path must be canonical baseline: {prov_baseline_path}")

        # Provenance baseline_sha256 must equal actual canonical bytes AND baseline_ancestor_sha256
        if prov_baseline_sha != baseline_sha:
            raise ValueError(f"provenance baseline_sha256 mismatch: expected {baseline_sha}, got {prov_baseline_sha}")
        if prov_baseline_sha != ancestor_sha:
            raise ValueError(f"provenance baseline_sha256 must equal baseline_ancestor_sha256: {prov_baseline_sha} != {ancestor_sha}")
        proof_path_rel = provenance.get("proof_path")
        proof_sha_bound = provenance.get("proof_sha256")

        if not proof_path_rel:
            raise ValueError("derived inventory missing provenance.proof_path")

        if not proof_sha_bound:
            raise ValueError("derived inventory missing provenance.proof_sha256")

        # Proof file must exist
        proof_path = root / proof_path_rel
        if not proof_path.is_file():
            raise ValueError(f"bound proof not found: {proof_path}")

        # Proof path must be confined under project
        if not proof_path.resolve().is_relative_to(root.resolve()):
            raise ValueError(f"proof path must be inside project root: {proof_path}")

        # Proof SHA must match
        proof_sha_actual = sha256_file(proof_path)
        if proof_sha_actual != proof_sha_bound:
            raise ValueError(f"proof SHA mismatch: expected {proof_sha_bound}, got {proof_sha_actual}")

        # DEFECT 2 FIX: Invoke full replay validation
        valid, errors = validate_approved_execution_inventory(path, canonical_baseline, proof_path)
        if not valid:
            raise ValueError(f"replay validation failed: {errors}")

    return path, data


def build_scope_from_inventory(root: Path | str, value: str | None) -> dict[str, Any]:
    root = Path(root).resolve()
    path, inventory = load_inventory(root, value)
    units = []
    failures = []
    approved_pages = {}
    for unit in inventory.get("units", []):
        pages = []
        for state in unit.get("required_states", []):
            state_id = state.get("state_id")
            page = {
                "page_id": unit.get("page_id"),
                "state_id": state_id,
                "output_file": (unit.get("output") or {}).get("file"),
                "arrival_mode": state.get("arrival_mode", "preview"),
            }
            evidence_state_id = state.get("evidence_state_id") or state_id
            if evidence_state_id == state_id and state_id == "default":
                folder = root / "spec" / "baseline" / "ui-snapshots" / str(page["page_id"])
                try:
                    meta = read_snapshot_meta(folder)
                    by_state = meta.get("runtime_evidence_by_state")
                    if isinstance(by_state, dict) and "normal" in by_state and "default" not in by_state:
                        evidence_state_id = "normal"
                except (OSError, ValueError):
                    pass
            page["evidence_state_id"] = evidence_state_id
            try:
                evidence_page = dict(page)
                evidence_page["page_id"] = state.get("evidence_page_id") or page["page_id"]
                evidence_page["state_id"] = evidence_state_id
                page["baseline"] = baseline(root, evidence_page)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                page["baseline"] = {"status": "BLOCKED", "reason": str(exc)}
                failures.append({"unit_id": unit.get("unit_id"), "page_id": page.get("page_id"), "state_id": page.get("state_id"), "reason": str(exc)})
            pages.append(page)
            if unit.get("required") is not False:
                approved_pages[(unit["unit_id"], state_id)] = (page, state)
        units.append({
            "unit_id": unit.get("unit_id"),
            "component": unit.get("component"),
            "status": "BLOCKED" if any(p.get("baseline", {}).get("status") == "BLOCKED" for p in pages) else "READY",
            "output": unit.get("output", {}),
            "pages": pages,
        })
    pairs = []
    pair_ids = set()
    covered = set()
    verification = inventory.get("verification_states") or []
    for row in verification:
        pair_id = row.get("verification_id")
        page_id = row.get("page_id")
        state_id = row.get("state_id")
        owner = row.get("owner")
        selected = approved_pages.get((owner, state_id))
        if not isinstance(pair_id, str) or not pair_id or pair_id in pair_ids or not selected or selected[0]["page_id"] != page_id:
            failures.append({"code": "visual_pair_unbound", "pair_id": pair_id, "page_id": page_id, "state_id": state_id,
                             "reason": "verification pair does not bind an approved owner and state"})
            continue
        page, state = selected
        pair_ids.add(pair_id)
        covered.add((page_id, state_id))
        pairs.append({
            "pair_id": pair_id, "page_id": page_id, "state_id": state_id,
            "arrival_mode": row.get("arrival_mode", page["arrival_mode"]),
            "unit_id": owner, "implementation_units": row.get("implementation_units") or [owner],
            "baseline": page["baseline"], "comparisons": [{"comparison_id": f"{pair_id}:0",
                                                              "ios_region_px": state.get("region_px")}],
        })
    if verification:
        for page_id, state_id in sorted({(page["page_id"], page["state_id"]) for page, _ in approved_pages.values()} - covered):
            failures.append({"code": "visual_pair_missing", "page_id": page_id, "state_id": state_id,
                             "reason": "required page state is absent from the verification inventory"})
    return {
        "schema_version": 2 if verification else 1,
        "status": "READY" if not failures else "BLOCKED",
        "scope": "stage1_delivery",
        "inventory_path": path.relative_to(root).as_posix(),
        "inventory_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "source_sha256": source_digest(root),
        "units": units,
        "pairs": pairs,
        "failure_findings": failures,
    }


def gate_from_inventory(root: Path | str, value: str | None, inputs_index: str | None = None,
                        wiring_contract: str | None = None) -> dict[str, Any]:
    root = Path(root).resolve()
    try:
        path, inventory = load_inventory(root, value)
    except (OSError, ValueError, UnicodeError) as exc:
        error = {"code": "inputs_invalid", "detail": str(exc), "root_cause": "information_gap"}
        return {
            "schema_version": 2, "gate": "stage1_ui", "status": "BLOCKED",
            "result_scope": "STRUCTURAL_ONLY", "stage1_complete": False,
            "arrival_verified": False, "visual_verified": False,
            "errors": [error], "failure_findings": [error], "warnings": [],
            "required_units": 0, "delivered_units": 0, "wired_units": [], "policy_gate": "execute.stage1-g1",
        }
    return inspect_delivery(root, path, inventory, inputs_index, wiring_contract)
