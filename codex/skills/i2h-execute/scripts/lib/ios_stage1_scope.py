"""Build iOS Stage-1 scope and gate data without the Android bundle."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .stage1_visual_scope import baseline


def inventory_path(root: Path, value: str | None) -> Path:
    if value:
        path = Path(value)
        return path if path.is_absolute() else root / path
    return root / "spec" / "baseline" / "ui-delivery-approved.json"


def load_inventory(root: Path, value: str | None) -> tuple[Path, dict[str, Any]]:
    path = inventory_path(root, value).resolve()
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 2 or data.get("status") != "approved":
        raise ValueError("approved schema-2 UI delivery inventory is required")
    return path, data


def build_scope_from_inventory(root: Path | str, value: str | None) -> dict[str, Any]:
    root = Path(root).resolve()
    path, inventory = load_inventory(root, value)
    units = []
    failures = []
    for unit in inventory.get("units", []):
        pages = []
        for state in unit.get("required_states", []):
            state_id = state.get("state_id")
            page = {
                "page_id": unit.get("page_id"),
                "state_id": state_id,
                "output_file": (unit.get("output") or {}).get("file"),
            }
            evidence_state_id = state.get("evidence_state_id") or state_id
            if evidence_state_id == state_id and state_id == "default":
                meta_path = root / "spec" / "baseline" / "ui-snapshots" / str(page["page_id"]) / "meta.json"
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                    by_state = meta.get("runtime_evidence_by_state")
                    if isinstance(by_state, dict) and "normal" in by_state and "default" not in by_state:
                        evidence_state_id = "normal"
                except (OSError, json.JSONDecodeError):
                    pass
            page["evidence_state_id"] = evidence_state_id
            try:
                evidence_page = dict(page)
                evidence_page["state_id"] = evidence_state_id
                page["baseline"] = baseline(root, evidence_page)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                page["baseline"] = {"status": "BLOCKED", "reason": str(exc)}
                failures.append({"unit_id": unit.get("unit_id"), "page_id": page.get("page_id"), "state_id": page.get("state_id"), "reason": str(exc)})
            pages.append(page)
        units.append({
            "unit_id": unit.get("unit_id"),
            "component": unit.get("component"),
            "status": "BLOCKED" if any(p.get("baseline", {}).get("status") == "BLOCKED" for p in pages) else "READY",
            "output": unit.get("output", {}),
            "pages": pages,
        })
    return {
        "schema_version": 1,
        "status": "READY" if not failures else "BLOCKED",
        "scope": "stage1_delivery",
        "inventory_path": path.relative_to(root).as_posix(),
        "units": units,
        "failure_findings": failures,
    }


def gate_from_inventory(root: Path | str, value: str | None, inputs_index: str | None = None) -> dict[str, Any]:
    root = Path(root).resolve()
    try:
        path, inventory = load_inventory(root, value)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {"schema_version": 2, "gate": "stage1_ui", "status": "BLOCKED", "errors": [{"code": "inputs_invalid", "detail": str(exc)}], "wired_units": []}
    errors = []
    units = inventory.get("units") or []
    if not units:
        errors.append({"code": "no_selected_page_bindings"})
    for unit in units:
        output_file = (unit.get("output") or {}).get("file")
        if not isinstance(output_file, str) or not (root / output_file).is_file():
            errors.append({"code": "output_missing", "unit_id": unit.get("unit_id"), "file": output_file})
    if inputs_index:
        index_path = Path(inputs_index)
        if not index_path.is_absolute():
            index_path = root / index_path
        if not index_path.is_file():
            errors.append({"code": "inputs_index_missing", "path": str(index_path.relative_to(root))})
    return {
        "schema_version": 2,
        "gate": "stage1_ui",
        "status": "PASS" if not errors else "BLOCKED",
        "errors": errors,
        "warnings": [],
        "wired_units": [u.get("unit_id") for u in units if isinstance(u, dict)],
        "failure_findings": errors,
        "policy_gate": "execute.stage1-g1",
        "inventory": path.relative_to(root).as_posix(),
    }
