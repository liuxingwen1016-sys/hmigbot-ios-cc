#!/usr/bin/env python3
"""Check schema-2 UI state and implementation ownership."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def review(project_root: str | Path, inventory: dict[str, Any]) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    # A state id is scoped to the page/component that owns it.  ``default`` is
    # intentionally common across every page produced by the source-driven
    # draft, so treating ``(state_id, responsibility)`` as a global key makes
    # a valid full-ui inventory impossible to approve.  Hand-authored units
    # without a page id retain the old global scope so malformed/minimal
    # inventories still fail closed.
    owners: dict[tuple[str, str, str], str] = {}
    for unit in inventory.get("units", []):
        if not isinstance(unit, dict):
            errors.append({"code": "UNIT_INVALID"})
            continue
        unit_id = unit.get("unit_id")
        page_scope = str(unit.get("page_id") or "__global__")
        roles = set(unit.get("owned_ui_roles", []))
        for state in unit.get("required_states", []):
            if not isinstance(state, dict):
                errors.append({"code": "STATE_INVALID", "unit_id": unit_id}); continue
            state_id = state.get("state_id")
            responsibility = state.get("responsibility", "content")
            if responsibility not in roles:
                errors.append({"code": "UNASSIGNED_STATE", "unit_id": unit_id, "state_id": state_id, "responsibility": responsibility})
            key = (page_scope, str(state_id), str(responsibility))
            if responsibility == "content" and key in owners and owners[key] != unit_id:
                errors.append({"code": "DUPLICATE_CONTENT_OWNERSHIP", "state_id": state_id, "owners": [owners[key], unit_id]})
            else:
                owners[key] = str(unit_id)
            if state.get("arrival_mode") not in {"formal", "preview", "behavior"}:
                errors.append({"code": "ARRIVAL_MODE_INVALID", "unit_id": unit_id, "state_id": state_id})
    if inventory.get("scope", "full_ui") == "full_ui" and not inventory.get("verification_states"):
        warnings.append({"code": "VERIFICATION_STATES_EMPTY", "message": "full_ui inventory has no composition verification states yet"})
    # JSON object keys must be strings.  The in-memory lookup keeps tuple keys
    # so duplicate detection remains unambiguous, while the persisted report
    # uses a stable delimiter that can be read by shell/Claude consumers.
    serializable_owners = {
        f"{page_id}::{state_id}::{responsibility}": owner
        for (page_id, state_id, responsibility), owner in sorted(owners.items())
    }
    return {"schema_version": 1, "status": "PASS" if not errors else "FAIL", "errors": errors, "warnings": warnings, "owners": serializable_owners}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--inventory", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    try:
        inventory = json.loads(Path(args.inventory).read_text(encoding="utf-8"))
        result = review(args.project_root, inventory)
        path = Path(args.out); path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"output": args.out, "status": result["status"], "errors": len(result["errors"])}, ensure_ascii=False))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
