"""Archive the assembled iOS delivery gate and its original converter inputs."""
from __future__ import annotations

import json

from .ios_stage1_scope import load_inventory
from .ios_ui_delivery_gate import _project_file, _read_object, host_slots, inspect_delivery
from .ios_ui_dispatch import (
    checked_artifact, digest, dispatch_root, events, json_bytes, locked, project_relative,
    read_completed, save_directory, sha256,
)
from .stage1_contract import source_digest


WIRING = 'spec/execution/stage1-wiring-contract.json'


def _finding(code, unit_id, detail):
    return {'code': code, 'unit_id': unit_id, 'detail': detail, 'root_cause': 'product_defect'}


def _conversion_receipts(root, inventory, inventory_hash, records):
    attempts = {}
    for event in records:
        if event['event'] == 'prepare':
            row = event['result']
            attempts.setdefault(row['unit_id'], []).append(row)
    receipts = []
    errors = []
    for unit in inventory['units']:
        if unit.get('required') is False:
            continue
        name = unit['unit_id']
        rows = sorted(attempts.get(name, []), key=lambda row: row['attempt'])
        if not rows:
            errors.append(_finding('g0_dispatch_missing', name, 'required unit was not dispatched'))
            continue
        original = read_completed(root, records, rows[0]['dispatch_id'])
        latest = read_completed(root, records, rows[-1]['dispatch_id']) if len(rows) > 1 else original
        if original is None:
            errors.append(_finding('g0_original_archive_missing', name, 'first attempt has no original archive'))
        if latest is None or latest['status'] != 'PASS':
            errors.append(_finding('g0_current_not_passed', name, 'latest attempt has no passing G0 archive'))
            continue
        path = _project_file(root, latest['archive_path'])
        packet = _read_object(path / 'packet.json')
        if digest(packet['inventory_source']['sha256']) != inventory_hash:
            errors.append(_finding('g0_inventory_stale', name, 'G0 belongs to a different approved inventory'))
            continue
        archived_report = path / 'conversion-report.json'
        report = _project_file(root, f'spec/execution/conversion-reports/{name}.json')
        if not report.is_file() or report.read_bytes() != archived_report.read_bytes():
            errors.append(_finding('g0_live_report_changed', name, 'current conversion report differs from the archived report'))
            continue
        if original is not None:
            receipts.append({
                'unit_id': name, 'first_dispatch_id': original['dispatch_id'], 'first_status': original['status'],
                'current_dispatch_id': latest['dispatch_id'], 'archive_path': latest['archive_path'],
                'preflight_sha256': latest['preflight_sha256'], 'report_sha256': sha256(archived_report.read_bytes()),
            })
    return receipts, errors


def _product_snapshot(root, inventory):
    paths = set()
    for unit in inventory['units']:
        if unit.get('required') is False:
            continue
        name = unit['unit_id']
        paths.add(f'spec/execution/conversion-reports/{name}.json')
        output = unit.get('output')
        if isinstance(output, dict) and isinstance(output.get('file'), str):
            paths.add(output['file'])
        for integration in host_slots(unit):
            if isinstance(integration, dict) and isinstance(integration.get('host_file'), str):
                paths.add(integration['host_file'])
    snapshot = {}
    for name in sorted(paths):
        path = _project_file(root, name)
        if path.is_file():
            snapshot[project_relative(root, path)] = path.read_bytes()
    return snapshot


def archive_g1(root, wiring_contract=None, *, read_only=False):
    folder = dispatch_root(root)
    with locked(folder):
        inventory_path, _ = load_inventory(root, None)
        inventory_bytes = inventory_path.read_bytes()
        inventory = json.loads(inventory_bytes)
        inventory_hash = sha256(inventory_bytes)
        selected_contract = wiring_contract
        if selected_contract is None and _project_file(root, WIRING).is_file():
            selected_contract = WIRING
        contract = _project_file(root, selected_contract) if selected_contract else None
        contract_bytes = contract.read_bytes() if contract and contract.is_file() else None
        before = source_digest(root)
        snapshot = _product_snapshot(root, inventory)
        receipts, findings = _conversion_receipts(root, inventory, inventory_hash, events(folder))
        structural = inspect_delivery(root, inventory_path, inventory, None, selected_contract)
        checked_artifact(inventory_path, inventory_hash)
        if before != source_digest(root) or snapshot != _product_snapshot(root, inventory):
            raise ValueError('target source or converter report changed while running G1')
        if contract is not None:
            current = contract.read_bytes() if contract.is_file() else None
            if current != contract_bytes:
                raise ValueError('wiring contract changed while running G1')
        findings.extend(structural['failure_findings'])
        result = {
            'schema_version': 2, 'policy_gate': 'execute.stage1-g1', 'result_scope': 'STRUCTURAL_ONLY',
            'status': 'BLOCKED' if findings else 'PASS',
            'stage1_complete': False, 'visual_verified': False, 'arrival_verified': False,
            'source_sha256': before, 'inventory_sha256': inventory_hash,
            'wiring_contract_sha256': sha256(contract_bytes) if contract_bytes is not None else None,
            'required_units': structural['required_units'], 'delivered_units': structural['delivered_units'],
            'wired_units': structural['wired_units'], 'current_g0_units': len(receipts), 'g0_receipts': receipts,
            'product_files': {name: sha256(data) for name, data in snapshot.items()},
            'failure_findings': findings, 'warnings': structural['warnings'],
        }
        raw = json_bytes(result)
        archive_root = _project_file(folder, 'g1')
        archive = archive_root / sha256(raw)
        files = {'receipt.json': raw, 'inventory.json': inventory_bytes}
        files.update({f'product/{name}': data for name, data in snapshot.items()})
        if contract_bytes is not None:
            files['wiring-contract.json'] = contract_bytes
        if archive.exists():
            for name, content in files.items():
                checked_artifact(_project_file(archive, name), sha256(content))
        elif not read_only:
            archive_root.mkdir(exist_ok=True)
            save_directory(archive, files)
        elif findings:
            return {**result, 'archive_path': None}
        else:
            return {**result, 'archive_path': None, 'status': 'NOT_RUN',
                    'failure_findings': [{
                        'code': 'current_g1_archive_missing', 'root_cause': 'information_gap',
                        'detail': 'the current assembled source has no archived G1 receipt',
                    }]}
        return {**result, 'archive_path': project_relative(root, archive)}
