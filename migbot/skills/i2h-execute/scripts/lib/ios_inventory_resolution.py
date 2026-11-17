"""Production iOS inventory resolution with strict caller proof and deep invariant validation.

Phase B: Source-proven derive CLI + enforced deep invariant/provenance/caller proof.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

# Add lib to path for SwiftSource import
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ios_swift_declaration_scope import SwiftSource


def sha256_bytes(data: bytes) -> str:
    """Compute SHA-256 of bytes."""
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    """Compute SHA-256 of actual file bytes."""
    return sha256_bytes(path.read_bytes())


def validate_swift_declaration(source_lines: list[str], line_1indexed: int, declared_symbol: str) -> tuple[bool, str | None]:
    """Validate that declared_symbol appears in a declaration at specified line."""
    if line_1indexed < 1 or line_1indexed > len(source_lines):
        return False, f"line {line_1indexed} out of range (1-{len(source_lines)})"

    source_text = '\n'.join(source_lines)
    swift = SwiftSource(source_text)

    for decl in swift.declarations:
        if decl['line'] == line_1indexed:
            if decl['name'] == declared_symbol or decl['qualified_name'] == declared_symbol:
                return True, None

    return False, f"declaration '{declared_symbol}' not found at line {line_1indexed}"


def validate_caller_invocation(source_lines: list[str], line_1indexed: int, callee_symbol: str) -> tuple[bool, str | None, str | None]:
    """Validate that callee_symbol is invoked (not declared or commented) at specified line."""
    if line_1indexed < 1 or line_1indexed > len(source_lines):
        return False, None, f"line {line_1indexed} out of range"

    source_text = '\n'.join(source_lines)
    swift = SwiftSource(source_text)

    target_line = swift.lex.code.split('\n')[line_1indexed - 1]

    invocation_pattern = rf'\b{re.escape(callee_symbol)}\s*\('
    if not re.search(invocation_pattern, target_line):
        return False, None, f"invocation '{callee_symbol}(' not found at line {line_1indexed}"

    declaration_pattern = rf'\b(?:struct|class|enum|protocol|extension|actor)\s+{re.escape(callee_symbol)}\b'
    if re.search(declaration_pattern, target_line):
        return False, None, f"line {line_1indexed} is a declaration, not an invocation"

    target_offset = sum(len(line) + 1 for line in source_lines[:line_1indexed - 1])

    enclosing_type = None
    for decl in swift.declarations:
        if decl['kind'] == 'extension':
            continue
        start = decl['start_offset']
        end = decl.get('end_offset')
        if end is not None and start <= target_offset < end:
            if enclosing_type is None or start > enclosing_type[1]:
                enclosing_type = (decl['name'], start)

    owner = enclosing_type[0] if enclosing_type else None
    return True, owner, None


def deep_compare_inventory_structure(baseline: dict, candidate: dict) -> list[str]:
    """Deep validate inventory structure - all fields must match except Plan metadata."""
    errors = []

    baseline_units = baseline.get('units', [])
    candidate_units = candidate.get('units', [])

    if len(baseline_units) != len(candidate_units):
        errors.append(f"unit_count_changed: baseline={len(baseline_units)} candidate={len(candidate_units)}")
        return errors

    for i, (b_unit, c_unit) in enumerate(zip(baseline_units, candidate_units)):
        unit_id = b_unit.get('unit_id', f'unit[{i}]')

        for field in ['unit_id', 'page_id', 'component', 'required']:
            if b_unit.get(field) != c_unit.get(field):
                errors.append(f"{unit_id}.{field}_changed")

        if b_unit.get('output') != c_unit.get('output'):
            errors.append(f"{unit_id}.output_changed")

        if b_unit.get('generation_owner') != c_unit.get('generation_owner'):
            errors.append(f"{unit_id}.generation_owner_changed")

        b_states = b_unit.get('required_states', [])
        c_states = c_unit.get('required_states', [])

        if len(b_states) != len(c_states):
            errors.append(f"{unit_id}.states_count_changed")
            continue

        for j, (b_state, c_state) in enumerate(zip(b_states, c_states)):
            state_id = b_state.get('state_id', f'state[{j}]')

            for field in ['state_id', 'responsibility', 'arrival_mode']:
                if b_state.get(field) != c_state.get(field):
                    errors.append(f"{unit_id}.{state_id}.{field}_changed")

            if b_state.get('source_refs') != c_state.get('source_refs'):
                errors.append(f"{unit_id}.{state_id}.source_refs_changed")

        if b_unit.get('source_refs') != c_unit.get('source_refs'):
            errors.append(f"{unit_id}.unit_source_refs_changed")

    b_verif = baseline.get('verification_states', [])
    c_verif = candidate.get('verification_states', [])

    if len(b_verif) != len(c_verif):
        errors.append(f"verification_states_count_changed")
    else:
        for b_v, c_v in zip(b_verif, c_verif):
            for field in ['verification_id', 'page_id', 'state_id', 'owner']:
                if b_v.get(field) != c_v.get(field):
                    errors.append(f"verification.{b_v.get('verification_id')}.{field}_changed")

    return errors


def validate_inventory_provenance(candidate: dict, baseline_sha256: str) -> tuple[bool, list[str]]:
    """Validate that execution inventory has proper ancestry and approval."""
    errors = []

    ancestor = candidate.get('baseline_ancestor_sha256')
    if not ancestor:
        errors.append("missing baseline_ancestor_sha256")
        return False, errors

    if ancestor != baseline_sha256:
        errors.append(f"baseline_ancestor_sha256 mismatch: expected {baseline_sha256}, got {ancestor}")

    approval = candidate.get('approval')
    if not approval or not isinstance(approval, dict):
        errors.append("missing or invalid approval")
        return False, errors

    if not approval.get('confirmation_ref'):
        errors.append("approval missing confirmation_ref")

    validation = candidate.get('validation')
    if not isinstance(validation, dict):
        errors.append("missing or invalid validation")
    # REPAIR 1: validation.errors must exist as key and be exact empty list []
    if "errors" not in validation:
        errors.append("validation missing errors field")
    elif validation.get('errors') is None:
        errors.append("validation.errors is None, must be []")
    elif validation.get('errors') != []:
        errors.append(f"validation must have errors=[], got {validation.get('errors')}")

    if candidate.get('status') != 'approved':
        errors.append(f"status must be 'approved', got {candidate.get('status')}")

    return len(errors) == 0, errors


def load_proof(proof_path: Path) -> tuple[dict | None, str | None]:
    """Load and validate proof file structure."""
    if not proof_path.is_file():
        return None, f"proof file not found: {proof_path}"

    try:
        proof = json.loads(proof_path.read_text(encoding='utf-8'))
    except Exception as e:
        return None, f"proof file is not valid JSON: {e}"

    if not isinstance(proof, dict):
        return None, "proof must be a JSON object"

    known_fields = {'baseline_sha256', 'requests'}
    unknown = set(proof.keys()) - known_fields
    if unknown:
        return None, f"proof contains unknown fields: {sorted(unknown)}"

    if 'baseline_sha256' not in proof:
        return None, "proof missing baseline_sha256"

    if not isinstance(proof.get('baseline_sha256'), str):
        return None, "proof baseline_sha256 must be a string"

    if 'requests' not in proof:
        return None, "proof missing requests array"

    if not isinstance(proof.get('requests'), list):
        return None, "proof requests must be an array"

    return proof, None


def collect_primary_source_refs(baseline: dict) -> dict[str, set[str]]:
    """Collect all PRIMARY source_refs from baseline. Returns file -> set of SHAs."""
    primary_refs = {}

    for unit in baseline.get('units', []):
        for ref in unit.get('source_refs', []):
            if isinstance(ref, dict) and 'file' in ref and 'sha256' in ref:
                file = ref['file']
                sha = ref['sha256']
                if file not in primary_refs:
                    primary_refs[file] = set()
                primary_refs[file].add(sha)

        for state in unit.get('required_states', []):
            if isinstance(state, dict):
                for ref in state.get('source_refs', []):
                    if isinstance(ref, dict) and 'file' in ref and 'sha256' in ref:
                        file = ref['file']
                        sha = ref['sha256']
                        if file not in primary_refs:
                            primary_refs[file] = set()
                        primary_refs[file].add(sha)

    return primary_refs


def confine_path(path: Path, root: Path) -> tuple[bool, str | None]:
    """Validate path is confined under root using is_relative_to."""
    try:
        resolved_path = path.resolve()
        resolved_root = root.resolve()

        if not resolved_path.is_relative_to(resolved_root):
            return False, f"path escapes root: {path}"

        return True, None
    except Exception as e:
        return False, f"cannot resolve path: {e}"


def apply_proof_to_inventory(baseline: dict, proof: dict, baseline_file_sha: str, source_root: Path, proof_file_sha: str | None = None) -> tuple[dict | None, list[str]]:
    """Apply proof requests to baseline inventory."""
    errors = []

    if proof['baseline_sha256'] != baseline_file_sha:
        errors.append(f"baseline SHA mismatch: proof expects {proof['baseline_sha256']}, got {baseline_file_sha}")
        return None, errors

    candidate = copy.deepcopy(baseline)

    unit_map = {unit['unit_id']: unit for unit in candidate.get('units', [])}
    unit_ids = set(unit_map.keys())
    primary_refs = collect_primary_source_refs(baseline)

    applied_requests = []

    for idx, request in enumerate(proof.get('requests', [])):
        request_id = f"request[{idx}]"

        if not isinstance(request, dict):
            errors.append(f"{request_id}: must be an object")
            continue

        unit_id = request.get('unit_id')
        if not isinstance(unit_id, str) or unit_id not in unit_ids:
            errors.append(f"{request_id}: invalid unit_id")
            continue

        unit = unit_map[unit_id]

        # Handle source_only independent alternative
        if 'source_only' in request and 'integration' not in request:
            source_only = request['source_only']

            if not isinstance(source_only, dict):
                errors.append(f"{request_id}: source_only must be an object")
                continue

            if source_only.get('alternative_kind') != 'source_only':
                errors.append(f"{request_id}: invalid alternative_kind")
                continue

            state_id = source_only.get('state_id')
            so_file = source_only.get('source_file')
            so_sha = source_only.get('source_sha256')
            so_line = source_only.get('source_line')
            so_decl = source_only.get('declaration')

            if not all([state_id, so_file, so_sha, isinstance(so_line, int), so_decl]):
                errors.append(f"{request_id}: source_only missing required fields")
                continue

            state_exists = any(s.get('state_id') == state_id for s in unit.get('required_states', []))
            if not state_exists:
                errors.append(f"{request_id}: state_id {state_id} not found in unit")
                continue

            if so_file not in primary_refs or so_sha not in primary_refs[so_file]:
                errors.append(f"{request_id}: source_only file/SHA not in primary refs")
                continue

            so_path = source_root / so_file
            confined, conf_err = confine_path(so_path, source_root)
            if not confined:
                errors.append(f"{request_id}: {conf_err}")
                continue

            if not so_path.is_file():
                errors.append(f"{request_id}: source_only file not found")
                continue

            actual_sha = sha256_file(so_path)
            if actual_sha != so_sha:
                errors.append(f"{request_id}: source_only SHA mismatch")
                continue

            source_text = so_path.read_text(encoding='utf-8')
            lines = source_text.split('\n')
            valid, err = validate_swift_declaration(lines, so_line, so_decl)
            if not valid:
                errors.append(f"{request_id}: {err}")
                continue

            if 'input_alternatives' not in unit:
                unit['input_alternatives'] = []

            unit['input_alternatives'].append(dict(source_only))

            applied_requests.append({
                'unit_id': unit_id,
                'type': 'source_only',
                'state_id': state_id,
            })
            continue

        # Handle integration request
        if 'integration' not in request:
            errors.append(f"{request_id}: must have integration or source_only")
            continue

        integration = request['integration']
        original_slot = request.get('original_slot')
        slot_index = request.get('slot_index', 0)

        if not isinstance(integration, dict):
            errors.append(f"{request_id}: integration must be an object")
            continue

        if not isinstance(original_slot, dict):
            errors.append(f"{request_id}: missing original_slot")
            continue

        caller_file = integration.get('caller_file')
        caller_line = integration.get('caller_line')
        callee = integration.get('callee')
        expected_owner = integration.get('expected_owner')
        targethost = integration.get('targethost')

        if not all([caller_file, isinstance(caller_line, int), callee, expected_owner]):
            errors.append(f"{request_id}: integration missing required fields")
            continue

        component = unit.get('component')
        # Normalize ios. prefix for component matching
        component_normalized = component.removeprefix("ios.") if isinstance(component, str) else component
        callee_normalized = callee
        if callee_normalized != component_normalized and callee != component:
            errors.append(f"{request_id}: callee '{callee}' doesn't match component '{component}'")
            continue

        current_integration = unit.get('integration')
        if isinstance(current_integration, dict):
            current_slot = current_integration
        elif isinstance(current_integration, list):
            if slot_index >= len(current_integration):
                errors.append(f"{request_id}: slot_index out of range")
                continue
            current_slot = current_integration[slot_index]
        else:
            errors.append(f"{request_id}: unit has no integration")
            continue

        if current_slot != original_slot:
            errors.append(f"{request_id}: original_slot mismatch")
            continue

        if caller_file not in primary_refs:
            errors.append(f"{request_id}: caller_file not in primary refs")
            continue

        caller_path = source_root / caller_file
        confined, conf_err = confine_path(caller_path, source_root)
        if not confined:
            errors.append(f"{request_id}: {conf_err}")
            continue

        if not caller_path.is_file():
            errors.append(f"{request_id}: caller_file not found")
            continue

        actual_sha = sha256_file(caller_path)
        if actual_sha not in primary_refs[caller_file]:
            errors.append(f"{request_id}: caller SHA not in primary refs")
            continue

        if len(primary_refs[caller_file]) > 1:
            errors.append(f"{request_id}: conflicting primary SHAs for {caller_file}")
            continue

        source_text = caller_path.read_text(encoding='utf-8')
        lines = source_text.split('\n')
        valid, owner, err = validate_caller_invocation(lines, caller_line, callee)
        if not valid:
            errors.append(f"{request_id}: {err}")
            continue

        if owner != expected_owner:
            errors.append(f"{request_id}: owner mismatch: expected {expected_owner}, got {owner}")
            continue

        new_slot = dict(original_slot)

        new_slot['source_ref'] = {
            'file': caller_file,
            'line': caller_line,
            'sha256': actual_sha,
        }

        if targethost:
            if targethost not in unit_ids:
                errors.append(f"{request_id}: targethost not in baseline")
                continue

            target_unit = unit_map[targethost]
            target_output = target_unit.get('output', {})

            new_slot['host_file'] = target_output.get('file')
            new_slot['host_symbol'] = target_output.get('symbol')
            new_slot['host_builder'] = target_output.get('builder')

        if isinstance(current_integration, dict):
            unit['integration'] = new_slot
        else:
            unit['integration'][slot_index] = new_slot

        applied_requests.append({
            'unit_id': unit_id,
            'type': 'integration',
            'caller': f"{caller_file}:{caller_line}",
            'targethost': targethost,
        })

    if errors:
        return None, errors

    candidate['provenance'] = {
        'applied_requests': applied_requests,
    }

    if proof_file_sha:
        candidate['provenance']['proof_sha256'] = proof_file_sha

    return candidate, []


def validate_approved_execution_inventory(inventory_path: Path, baseline_path: Path, proof_path: Path | None) -> tuple[bool, list[str]]:
    """Validate approved execution inventory by deterministic replay."""
    errors = []

    try:
        approved = json.loads(inventory_path.read_text(encoding='utf-8'))
    except Exception as e:
        errors.append(f"cannot load approved inventory: {e}")
        return False, errors

    try:
        baseline = json.loads(baseline_path.read_text(encoding='utf-8'))
    except Exception as e:
        errors.append(f"cannot load baseline: {e}")
        return False, errors

    baseline_sha = sha256_file(baseline_path)
    approved_ancestor = approved.get('baseline_ancestor_sha256')
    if not approved_ancestor:
        errors.append("approved inventory missing baseline_ancestor_sha256")
        return False, errors

    if baseline_sha != approved_ancestor:
        errors.append(f"baseline SHA mismatch: approved expects {approved_ancestor}, got {baseline_sha}")
        return False, errors

    if approved.get('status') != 'approved':
        errors.append(f"inventory status must be 'approved', got {approved.get('status')}")

    approval = approved.get('approval')
    if not isinstance(approval, dict) or not approval.get('confirmation_ref'):
        errors.append("approval missing confirmation_ref")

    validation = approved.get('validation')
    if not isinstance(validation, dict):
        errors.append("validation must be a dict")
    # REPAIR 1: validation.errors must exist as key and be exact empty list []
    if "errors" not in validation:
        errors.append("validation missing errors field")
    elif validation.get('errors') is None:
        errors.append("validation.errors is None, must be []")
    elif validation.get('errors') != []:
        errors.append(f"validation must have errors=[], got {validation.get('errors')}")

    if proof_path:
        proof, error = load_proof(proof_path)
        if error:
            errors.append(f"proof validation failed: {error}")
            return False, errors

        proof_sha_bound = approved.get('provenance', {}).get('proof_sha256')
        if proof_sha_bound:
            proof_sha_actual = sha256_file(proof_path)
            if proof_sha_actual != proof_sha_bound:
                errors.append(f"proof SHA mismatch: provenance expects {proof_sha_bound}, got {proof_sha_actual}")
                return False, errors
    else:
        if approved.get('provenance', {}).get('proof_sha256'):
            errors.append("approved inventory references proof but none provided")
            return False, errors

        proof = {'baseline_sha256': baseline_sha, 'requests': []}

    source_root = Path(baseline.get('source_project_root', '.')).resolve()
    proof_sha = sha256_file(proof_path) if proof_path else None
    replayed, replay_errors = apply_proof_to_inventory(baseline, proof, baseline_sha, source_root, proof_sha)

    if replay_errors:
        errors.extend([f"replay: {e}" for e in replay_errors])
        return False, errors

    approved_normalized = copy.deepcopy(approved)
    replayed_normalized = copy.deepcopy(replayed)

    for inv in [approved_normalized, replayed_normalized]:
        inv.pop('status', None)
        inv.pop('approval', None)
        inv.pop('validation', None)
        inv.pop('provenance', None)
        inv.pop('baseline_ancestor_sha256', None)

    if approved_normalized != replayed_normalized:
        errors.append("replay mismatch: approved inventory differs from replayed derive")
        return False, errors

    return len(errors) == 0, errors
