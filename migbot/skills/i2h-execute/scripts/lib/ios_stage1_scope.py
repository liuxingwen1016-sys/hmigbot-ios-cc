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
    if value:
        path = Path(value)
        return path if path.is_absolute() else root / path
    return root / "spec" / "baseline" / "ui-delivery-approved.json"


def load_inventory(root: Path, value: str | None) -> tuple[Path, dict[str, Any]]:
    path = inventory_path(root, value).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("approved inventory must be inside the project root")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema_version") != 2 or data.get("status") != "approved":
        raise ValueError("approved schema-2 UI delivery inventory is required")
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
