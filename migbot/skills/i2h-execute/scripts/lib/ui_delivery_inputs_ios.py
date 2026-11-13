"""Small source-mode freezer for iOS Stage-1 delivery inputs.

The execute bundle still contains the Android-only input freezer.  iOS
inventories use the same approved delivery contract, but their runtime
evidence is PNG plus an Accessibility JSON tree.  Keep this adapter
deterministic and fail closed when the inventory is malformed.  Missing
runtime evidence is recorded as a gap and never synthesized.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from .stage1_visual_scope import RUNTIME_META, _capture_manifest_candidates, read_snapshot_meta, sync_runtime_capture


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _relative(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _evidence(root: Path, page_id: str, state_id: str) -> dict[str, Any]:
    folder = root / "spec" / "baseline" / "ui-snapshots" / page_id
    result: dict[str, Any] = {"page_id": page_id, "state_id": state_id, "status": "missing"}
    if not ((folder / "meta.json").is_file() or (folder / RUNTIME_META).is_file()):
        result["reason"] = "meta.json missing"
        return result
    try:
        meta = read_snapshot_meta(folder)
    except (OSError, ValueError) as exc:
        result["reason"] = f"invalid meta.json: {exc}"
        return result
    by_state = meta.get("runtime_evidence_by_state")
    evidence = by_state.get(state_id) if isinstance(by_state, dict) else None
    if not isinstance(by_state, dict) and isinstance(meta.get("runtime_evidence"), dict):
        legacy = meta["runtime_evidence"]
        if (legacy.get("state_id") or legacy.get("state")) == state_id:
            evidence = legacy
    if not isinstance(evidence, dict):
        result["reason"] = "runtime evidence missing"
        return result
    if evidence.get("status") not in {"audited", "captured", "verified"} or evidence.get("source_platform") != "ios":
        result.update({"status": "invalid", "reason": "evidence is not an iOS capture"})
        return result
    if (evidence.get("state_id") or evidence.get("state")) not in {None, state_id} or evidence.get("page_id") not in {None, page_id}:
        result.update({"status": "invalid", "reason": "iOS capture identity does not match the requested state"})
        return result
    result.update({"status": "audited", "source_platform": "ios"})
    for key, digest_key in (("png_path", "png_sha256"), ("ui_json_path", "ui_json_sha256")):
        value = evidence.get(key)
        if not isinstance(value, str):
            result["status"] = "incomplete"
            result.setdefault("missing", []).append(key)
            continue
        candidate = root / "spec" / "baseline" / "ui-snapshots" / page_id / value
        if not candidate.is_file():
            result["status"] = "incomplete"
            result.setdefault("missing", []).append(key)
            continue
        actual = _sha256(candidate)
        if evidence.get(digest_key) != actual:
            result["status"] = "invalid"
            result.setdefault("errors", []).append(f"{key} sha256 mismatch")
            continue
        result[key] = _relative(root, candidate)
        result[digest_key] = actual
    return result


def freeze(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--inventory", required=True)
    parser.add_argument("--no-working-copies", action="store_true")
    args = parser.parse_args(argv)
    root = Path(args.project_root).expanduser().resolve()
    inventory_path = Path(args.inventory)
    if not inventory_path.is_absolute():
        inventory_path = root / inventory_path
    inventory = _read(inventory_path)
    if inventory.get("schema_version") != 2 or not isinstance(inventory.get("units"), list) or not inventory["units"]:
        raise ValueError("approved schema-2 inventory with non-empty units is required")
    capture_manifest = next((path for path in _capture_manifest_candidates(root) if path.is_file()), None)
    capture_sync = sync_runtime_capture(root, capture_manifest) if capture_manifest else None
    packets = []
    for unit in inventory["units"]:
        if not isinstance(unit, dict):
            raise ValueError("inventory unit must be an object")
        unit_id = unit.get("unit_id")
        page_id = unit.get("page_id")
        if not isinstance(unit_id, str) or not isinstance(page_id, str):
            raise ValueError("each unit requires unit_id and page_id")
        states = unit.get("required_states") or []
        if not isinstance(states, list) or not states:
            raise ValueError(f"{unit_id} has no required_states")
        state_inputs = []
        for state in states:
            if not isinstance(state, dict) or not isinstance(state.get("state_id"), str):
                raise ValueError(f"{unit_id} has an invalid required state")
            state_id = state["state_id"]
            state_inputs.append({
                "state_id": state_id,
                "responsibility": state.get("responsibility", "content"),
                "evidence": _evidence(root, state.get("evidence_page_id") or page_id,
                                      state.get("evidence_state_id") or state_id),
            })
        packets.append({
            "unit_id": unit_id,
            "page_id": page_id,
            "component": unit.get("component"),
            "output": unit.get("output", {}),
            "required_states": state_inputs,
        })
    output_path = root / "spec" / "execution" / "ui-inputs" / "index.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result = {
        "schema_version": 2,
        "scope": inventory.get("scope", "full_ui"),
        "producer": "i2h-execute/ui_delivery_inputs_ios",
        "inventory_source": {
            "path": _relative(root, inventory_path),
            "sha256": _sha256(inventory_path),
        },
        "packets": packets,
        "runtime_evidence_policy": "ios_png_accessibility_json",
        "working_copies": not args.no_working_copies,
        "runtime_capture": capture_sync,
    }
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": _relative(root, output_path), "packets": len(packets), "status": "PASS"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(freeze())
