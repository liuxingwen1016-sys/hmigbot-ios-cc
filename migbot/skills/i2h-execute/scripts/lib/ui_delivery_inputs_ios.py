"""Small source-mode freezer for iOS Stage-1 delivery inputs.

The execute bundle still contains the Android-only input freezer.  iOS
inventories use the same approved delivery contract, but their runtime
evidence is PNG plus an Accessibility JSON tree.  Keep this adapter
deterministic and fail closed when the inventory is malformed.  Missing
runtime evidence is recorded as a gap and never synthesized.

Source-backed alternatives: Require EXPLICIT typed input_alternatives declaration
in approved inventory with actual frozen-primary-covered fileSHA and real
declaration/branch proof (line+symbol) for that required state. source_refs alone
or arbitrary text reasons are INSUFFICIENT.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

# Import from ios_inventory_resolution which now uses SwiftSource
from .ios_inventory_resolution import validate_swift_declaration
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
        result.update({"status": "invalid", "reason": f"invalid meta.json: {exc}"})
        return result
    by_state = meta.get("runtime_evidence_by_state")
    if "runtime_evidence_by_state" in meta and not isinstance(by_state, dict):
        result.update({"status": "invalid", "reason": "runtime_evidence_by_state is not a dict"})
        return result
    evidence = by_state.get(state_id) if isinstance(by_state, dict) else None
    if not isinstance(by_state, dict):
        legacy_val = meta.get("runtime_evidence")
        if "runtime_evidence" in meta and not isinstance(legacy_val, dict):
            result.update({"status": "invalid", "reason": "runtime_evidence is not a dict"})
            return result
        if isinstance(legacy_val, dict):
            legacy = legacy_val
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


def _validate_typed_alternative(alt: dict, state_id: str, primary_refs: list[dict], source_root: Path) -> tuple[dict | None, str | None]:
    """
    Validate explicit typed input_alternative declaration with real declaration proof.

    Returns: (validated_alternative, error_message)
    """
    # Must have alternative_kind
    if alt.get('alternative_kind') != 'source_only':
        return None, f"invalid alternative_kind: {alt.get('alternative_kind')}"

    # Must have state_id matching
    if alt.get('state_id') != state_id:
        return None, f"alternative state_id mismatch: {alt.get('state_id')} != {state_id}"

    # Must have source file info
    source_file = alt.get('source_file')
    source_sha = alt.get('source_sha256')
    source_line = alt.get('source_line')
    declaration = alt.get('declaration')

    if not source_file or not isinstance(source_file, str):
        return None, "missing or invalid source_file"

    if not source_sha or not isinstance(source_sha, str):
        return None, "missing or invalid source_sha256"

    if not isinstance(source_line, int) or source_line < 1:
        return None, f"invalid source_line: must be positive integer, got {source_line}"

    if not declaration or not isinstance(declaration, str) or not declaration.strip():
        return None, "missing or invalid declaration/symbol"

    # Validate source_sha matches frozen primary index
    if not any(ref.get('file') == source_file and ref.get('sha256') == source_sha for ref in primary_refs):
        return None, f"source SHA not in frozen primary index: {source_file}@{source_sha}"

    # Validate file exists and SHA matches
    try:
        file_path = source_root / source_file
        if not file_path.is_file():
            return None, f"source file not found: {source_file}"

        actual_sha = _sha256(file_path)
        if actual_sha != source_sha:
            return None, f"source SHA mismatch: expected {source_sha}, got {actual_sha}"

        # OBLIGATION 1: Verify declaration at specified line using robust validator
        source_text = file_path.read_text(encoding='utf-8')
        lines = source_text.split('\n')

        valid, error = validate_swift_declaration(lines, source_line, declaration)
        if not valid:
            return None, f"declaration validation failed: {error}"

    except Exception as e:
        return None, f"error validating declaration: {e}"

    # Valid alternative
    return {
        'state_id': state_id,
        'alternative_kind': 'source_only',
        'source_file': source_file,
        'source_sha256': source_sha,
        'source_line': source_line,
        'declaration': declaration,
        'visual_status': 'BLOCKED'
    }, None


def freeze(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--inventory", required=True)
    parser.add_argument("--no-working-copies", action="store_true")
    args = parser.parse_args(argv)
    root = Path(args.project_root).expanduser().resolve()

    # DEFECT 3 FIX: Use shared load_inventory API instead of raw _read
    # This enforces strict validation BEFORE creating/changing index
    # Import at function level to have proper validation before any index creation
    from .ios_stage1_scope import load_inventory

    inventory_path, inventory = load_inventory(root, args.inventory)

    if inventory.get("schema_version") != 2 or not isinstance(inventory.get("units"), list) or not inventory["units"]:
        raise ValueError("approved schema-2 inventory with non-empty units is required")

    source_project_root = Path(inventory.get("source_project_root", "")).expanduser().resolve()
    if not source_project_root.is_dir():
        raise ValueError(f"source_project_root not found: {inventory.get('source_project_root')}")

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

        # Collect primary source refs for this unit - COPY and deduplicate to avoid mutation
        primary_refs_list = []
        seen_refs = set()

        for ref in unit.get("source_refs", []):
            key = (ref.get('file'), ref.get('sha256'), ref.get('line'))
            if key not in seen_refs:
                primary_refs_list.append(dict(ref))
                seen_refs.add(key)

        for state in states:
            if isinstance(state, dict) and state.get("source_refs"):
                for ref in state["source_refs"]:
                    key = (ref.get('file'), ref.get('sha256'), ref.get('line'))
                    if key not in seen_refs:
                        primary_refs_list.append(dict(ref))
                        seen_refs.add(key)

        state_inputs = []

        for state in states:
            if not isinstance(state, dict) or not isinstance(state.get("state_id"), str):
                raise ValueError(f"{unit_id} has an invalid required state")
            state_id = state["state_id"]
            evidence = _evidence(root, state.get("evidence_page_id") or page_id,
                                state.get("evidence_state_id") or state_id)

            state_inputs.append({
                "state_id": state_id,
                "responsibility": state.get("responsibility", "content"),
                "evidence": evidence,
            })

        # Build source alternatives ONLY from explicit input_alternatives
        # OBLIGATION 2: Only for genuinely missing runtime, not corrupt/incomplete existing bindings
        source_alternatives = []
        if unit.get('input_alternatives'):
            # Build map of state evidence status
            state_evidence_map = {}
            for state_input in state_inputs:
                state_evidence_map[state_input['state_id']] = state_input['evidence']

            for alt in unit['input_alternatives']:
                if not isinstance(alt, dict):
                    continue

                alt_state_id = alt.get('state_id', '')

                # Check if this state has genuinely missing runtime (not corrupt/incomplete)
                evidence = state_evidence_map.get(alt_state_id, {})
                evidence_status = evidence.get('status')

                # Only allow alternatives for truly missing runtime, not incomplete/invalid
                if evidence_status not in ('missing',):
                    # Has some recorded binding (even if corrupt) - cannot use source_only
                    continue

                validated, error = _validate_typed_alternative(
                    alt,
                    alt_state_id,
                    primary_refs_list,
                    source_project_root
                )

                if validated:
                    source_alternatives.append(validated)
                # Silently skip invalid alternatives (logged in validation receipts in Phase B)

        packet = {
            "unit_id": unit_id,
            "page_id": page_id,
            "component": unit.get("component"),
            "output": unit.get("output", {}),
            "required_states": state_inputs,
        }

        # Add source alternatives if any were validated
        if source_alternatives:
            packet["source_alternatives"] = source_alternatives

        packets.append(packet)

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
