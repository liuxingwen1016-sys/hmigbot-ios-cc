"""Bind converter attempts to approved iOS inputs and preserve their original G0."""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from contextlib import contextmanager
from pathlib import Path

from .ios_stage1_scope import load_inventory
from .ios_ui_delivery_gate import _check_unit, _project_file, _read_object, _states, host_slots
from .ios_inventory_resolution import sha256_file


INDEX = 'spec/execution/ui-inputs/index.json'
DISPATCH = 'spec/execution/dispatch'
NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]*')


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8')


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def digest(value):
    return value.removeprefix('sha256:').lower() if isinstance(value, str) else ''


def project_relative(root, path):
    return path.resolve().relative_to(root).as_posix()


def dispatch_root(root):
    return _project_file(root, DISPATCH)


@contextmanager
def locked(folder):
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / '.lock').open('a+b') as lock:
        if lock.tell() == 0:
            lock.write(b'\0')
            lock.flush()
        lock.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        yield


def atomic_write(path, data):
    with tempfile.TemporaryDirectory(dir=path.parent) as directory:
        candidate = Path(directory) / path.name
        candidate.write_bytes(data)
        candidate.replace(path)


def events(folder):
    path = folder / 'events.jsonl'
    records = []
    previous = None
    if path.is_file():
        for line in path.read_text(encoding='utf-8').splitlines():
            row = json.loads(line)
            body = dict(row)
            actual = body.pop('sha256', None)
            if body.get('previous_sha256') != previous or sha256(json_bytes(body)) != actual:
                raise ValueError('dispatch event hash chain is invalid')
            previous = actual
            records.append(row)
    return records


def append_event(folder, records, row):
    event = {**row, 'previous_sha256': records[-1]['sha256'] if records else None}
    event['sha256'] = sha256(json_bytes(event))
    lines = (json.dumps(item, ensure_ascii=False, sort_keys=True) for item in [*records, event])
    atomic_write(folder / 'events.jsonl', ('\n'.join(lines) + '\n').encode('utf-8'))


def save_directory(destination, files):
    with tempfile.TemporaryDirectory(dir=destination.parent) as directory:
        payload = Path(directory) / 'payload'
        payload.mkdir()
        for name, content in files.items():
            path = payload / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        if destination.exists():
            raise ValueError(f'original receipt already exists: {destination}')
        payload.rename(destination)


def checked_artifact(path, expected):
    data = path.read_bytes()
    if sha256(data) != digest(expected):
        raise ValueError(f'frozen input SHA-256 mismatch: {path}')
    return data


def store_artifact(folder, expected, data, suffix):
    path = _project_file(folder, f'objects/{digest(expected)}{suffix}')
    path.parent.mkdir(exist_ok=True)
    if path.exists():
        checked_artifact(path, expected)
    else:
        atomic_write(path, data)
    return path


def select_unit(inventory, name):
    matches = [unit for unit in inventory['units'] if unit['unit_id'] == name]
    if len(matches) != 1:
        raise ValueError(f'approved inventory must select exactly one unit: {name}')
    return matches[0]


def state_artifacts(root, unit_state, state):
    evidence = state['evidence']
    if evidence['status'] != 'audited':
        raise ValueError(evidence.get('reason', evidence['status']))
    selected = {}
    for kind, key in [('screenshot_png', 'png'), ('accessibility_json', 'ui_json')]:
        selected[kind] = (_project_file(root, evidence[f'{key}_path']), evidence[f'{key}_sha256'])
    if 'foreground_receipt' in unit_state.get('required_evidence', []):
        image_dir = selected['screenshot_png'][0].parent
        manifest_path = _project_file(root, str(image_dir / 'manifest.json'))
        manifest = _read_object(manifest_path)
        if (manifest.get('schema'), manifest.get('status'), manifest.get('page_id'), manifest.get('state_id')) != (
            'hmigbot-ios-ui-evidence/1', 'audited', evidence['page_id'], evidence['state_id']
        ):
            raise ValueError('audited iOS evidence manifest does not bind the required checkpoint')
        artifacts = manifest['artifacts']
        for manifest_key, kind in [('screenshot', 'screenshot_png'), ('ui_json', 'accessibility_json')]:
            original = artifacts[manifest_key]
            if (_project_file(root, str(image_dir / original['path'])), original['sha256']) != selected[kind]:
                raise ValueError('iOS evidence manifest does not match the frozen screenshot and tree')
        foreground = artifacts['foreground_receipt']
        selected['foreground_receipt'] = (_project_file(root, str(image_dir / foreground['path'])), foreground['sha256'])
        if 'foreground_ack' in artifacts:
            ack = artifacts['foreground_ack']
            selected['foreground_ack'] = (_project_file(root, str(image_dir / ack['path'])), ack['sha256'])
    return selected


def prepare(root, unit_id, attempt, *, no_working_copies=False):
    if not NAME.fullmatch(unit_id) or attempt < 1:
        raise ValueError('unit_id must be a safe identifier and attempt must be positive')
    index = _read_object(_project_file(root, INDEX))
    source = index['inventory_source']
    inventory_path, _ = load_inventory(root, source['path'])
    inventory_bytes = checked_artifact(inventory_path, source['sha256'])
    inventory = json.loads(inventory_bytes)
    unit = select_unit(inventory, unit_id)
    matches = [packet for packet in index['packets'] if packet['unit_id'] == unit_id]
    if index.get('schema_version') != 2 or len(matches) != 1:
        raise ValueError(f'approved schema-2 frozen packet is required: {unit_id}')
    frozen = matches[0]
    if frozen['output'] != unit['output'] or _states(frozen['required_states']) != _states(unit['required_states']):
        raise ValueError(f'frozen unit output or states differ from approved inventory: {unit_id}')
    folder = dispatch_root(root)
    dispatch_id = f'{unit_id}.attempt-{attempt}'
    destination = folder / dispatch_id
    gaps = []
    inputs = []
    originals = {}
    working_copies = index.get('working_copies', True) and not no_working_copies

    def add(input_id, path, expected, kind, display_path, **identity):
        data = checked_artifact(path, expected)
        content_path = store_artifact(folder, expected, data, path.suffix)
        if kind == 'screenshot_png':
            identity['comparison_id'] = input_id
        inputs.append({'input_id': input_id, 'kind': kind, 'path': display_path,
                       'sha256': digest(expected), 'object': project_relative(root, content_path), **identity})
        originals[input_id] = (content_path if working_copies else path)

    with locked(folder):
        records = events(folder)
        approved_states = {state['state_id']: state for state in unit['required_states']}
        source_root = Path(inventory['source_project_root']).expanduser().resolve()
        refs = [*unit.get('source_refs', [])]
        for state in approved_states.values():
            refs.extend(state.get('source_refs', []))
        slots = host_slots(unit)
        for slot in slots:
            if isinstance(slot, dict) and slot.get('source_ref'):
                refs.append(slot['source_ref'])
        read_anchors = set()
        for ref in refs:
            name, line = ref['file'], ref['line']
            if (name, line) in read_anchors:
                continue
            read_anchors.add((name, line))
            add(f'source:{name}:{line}', _project_file(source_root, name), ref.get('sha256'), 'ios_source',
                name, line=line)
        if not read_anchors:
            raise ValueError(f'no approved iOS source anchors for {unit_id}')
        for state in frozen['required_states']:
            state_id = state['state_id']
            try:
                for kind, (path, expected) in state_artifacts(root, approved_states[state_id], state).items():
                    add(f'{state_id}:{kind}', path, expected, kind, project_relative(root, path), state_id=state_id)
            except (OSError, ValueError, KeyError) as exc:
                gaps.append({'state_id': state_id, 'code': 'runtime_input_unavailable', 'detail': str(exc)})
        from .ui_delivery_inputs_ios import _validate_typed_alternative, _evidence as _fresh_evidence
        raw_alternatives = frozen.get('source_alternatives', [])
        if not isinstance(raw_alternatives, list):
            raise ValueError(f'source_alternatives must be a list: {unit_id}')
        frozen_state_evidence = {s['state_id']: s['evidence'] for s in frozen['required_states']}
        validated_alternatives = []
        for alt in raw_alternatives:
            if not isinstance(alt, dict):
                raise ValueError(f'source alternative must be a dict: {unit_id}')
            kind = alt.get('alternative_kind')
            if kind != 'source_only':
                raise ValueError(f'unrecognized alternative_kind: {kind}')
            state_id = alt.get('state_id')
            if state_id not in approved_states:
                raise ValueError(f'source alternative for non-existent state: {state_id}')
            approved_alts = [a for a in unit.get('input_alternatives', [])
                             if isinstance(a, dict) and a.get('state_id') == state_id]
            if len(approved_alts) != 1:
                raise ValueError(f'source alternative requires exactly one approved typed alternative for state: {state_id}')
            primary_refs = [*unit.get('source_refs', [])]
            for st in approved_states.values():
                primary_refs.extend(st.get('source_refs', []))
            validated, error = _validate_typed_alternative(approved_alts[0], state_id, primary_refs, source_root)
            if not validated:
                raise ValueError(f'approved alternative validation failed for {state_id}: {error}')
            if alt != validated:
                raise ValueError(f'frozen alternative does not match approved validated proof: {state_id}')
            frozen_ev = frozen_state_evidence.get(state_id, {})
            if frozen_ev.get('status') != 'missing':
                raise ValueError(f'source alternative requires frozen evidence missing, found: {frozen_ev.get("status")}')
            approved_state = approved_states[state_id]
            current_ev = _fresh_evidence(
                root,
                approved_state.get('evidence_page_id') or unit['page_id'],
                approved_state.get('evidence_state_id') or state_id,
            )
            if current_ev['status'] != 'missing':
                raise ValueError(f'source alternative requires current evidence missing, found: {current_ev["status"]}')
            validated_alternatives.append(alt)
            source_path = _project_file(source_root, alt['source_file'])
            if source_path.is_file():
                add(f'{state_id}:source_proof', source_path, alt['source_sha256'], 'ios_source_proof',
                    alt['source_file'], state_id=state_id, alternative_kind='source_only')
        packet = {**frozen, 'schema_version': 2, 'dispatch_id': dispatch_id, 'attempt': attempt,
                  'required_inputs': inputs, 'input_gaps': gaps, 'inventory_source': source}
        if slots:
            packet['integration'] = slots
        packet_bytes = json_bytes(packet)
        source_alt_state_ids = {alt['state_id'] for alt in validated_alternatives}
        all_gaps_covered = gaps and all(gap['state_id'] in source_alt_state_ids for gap in gaps)
        if all_gaps_covered:
            status = 'SOURCE_ONLY'
        elif gaps:
            status = 'BLOCKED'
        else:
            status = 'READY'

        result = {
            'status': status, 'dispatch_id': dispatch_id, 'unit_id': unit_id, 'attempt': attempt,
            'packet_path': project_relative(root, destination / 'packet.json'), 'packet_sha256': sha256(packet_bytes),
            'prompt_path': project_relative(root, destination / 'prompt.md'), 'input_gaps': gaps,
            'visual_status': 'BLOCKED' if status == 'SOURCE_ONLY' else None,
        }
        prompt = [
            '# iOS UI converter input', '', f'Unit {unit_id} / {unit["page_id"]} / {unit["component"]}',
            f'Output {unit["output"]["file"]}', f'Dispatch {dispatch_id}',
            f'Packet {destination / "packet.json"}', f'Packet SHA-256 {result["packet_sha256"]}', '',
            'Read every required input. Cross-check each image against its state tree.',
            'For image_observations use the state_id and comparison_id from the packet.',
            'Record every required input by input_id in input_applications.',
            'Write the declared output and its conversion report, then call ui_dispatch.py complete.', '',
        ]
        for item in inputs:
            prompt.append(f'- {item["input_id"]} {originals[item["input_id"]]}')
        for gap in gaps:
            prompt.append(f'- BLOCKED {gap["state_id"]} {gap["detail"]}')
        prompt_bytes = ('\n'.join(prompt) + '\n').encode('utf-8')
        result['prompt_sha256'] = sha256(prompt_bytes)
        old = next((row for row in records if row['event'] == 'prepare' and row['dispatch_id'] == dispatch_id), None)
        if old:
            if old['result'] != result:
                raise ValueError(f'{dispatch_id} has different frozen inputs. Use a new attempt.')
            checked_artifact(destination / 'packet.json', result['packet_sha256'])
            checked_artifact(destination / 'prompt.md', result['prompt_sha256'])
            checked_artifact(destination / 'inventory.json', source['sha256'])
            return result
        save_directory(destination, {'packet.json': packet_bytes, 'prompt.md': prompt_bytes,
                                     'inventory.json': inventory_bytes})
        append_event(folder, records, {'event': 'prepare', 'dispatch_id': dispatch_id, 'result': result})
        return result


def read_prepared(root, records, dispatch_id):
    if not NAME.fullmatch(dispatch_id):
        raise ValueError('invalid dispatch_id')
    prepared = next((row['result'] for row in records if row['event'] == 'prepare' and row['dispatch_id'] == dispatch_id), None)
    if prepared is None:
        raise ValueError(f'dispatch not prepared: {dispatch_id}')
    directory = dispatch_root(root) / dispatch_id
    packet_bytes = checked_artifact(directory / 'packet.json', prepared['packet_sha256'])
    packet = json.loads(packet_bytes)
    prompt = checked_artifact(directory / 'prompt.md', prepared['prompt_sha256'])
    inventory = checked_artifact(directory / 'inventory.json', packet['inventory_source']['sha256'])
    return prepared, packet, {'packet.json': packet_bytes, 'prompt.md': prompt, 'inventory.json': inventory}


def read_completed(root, records, dispatch_id):
    completed = next((row['result'] for row in records if row['event'] == 'complete' and row['dispatch_id'] == dispatch_id), None)
    if completed:
        directory = _project_file(root, completed['archive_path'])
        preflight = checked_artifact(directory / 'preflight.json', completed['preflight_sha256'])
        for name, expected in json.loads(preflight)['archive_sha256'].items():
            checked_artifact(_project_file(root, str(directory / name)), expected)
        packet = _read_object(directory / 'packet.json')
        for item in packet['required_inputs']:
            checked_artifact(_project_file(root, item['object']), item['sha256'])
    return completed


def complete(root, dispatch_id):
    folder = dispatch_root(root)
    with locked(folder):
        records = events(folder)
        prepared, packet, files = read_prepared(root, records, dispatch_id)
        existing = read_completed(root, records, dispatch_id)
        if existing:
            return existing
        unit = select_unit(json.loads(files['inventory.json']), prepared['unit_id'])
        for item in packet['required_inputs']:
            checked_artifact(_project_file(root, item['object']), item['sha256'])
        errors, warnings = [], []
        # Check if gaps have valid source alternatives
        source_alternatives = packet.get('source_alternatives', [])
        source_alt_states = {alt['state_id'] for alt in source_alternatives if alt.get('alternative_kind') == 'source_only'}

        for gap in prepared['input_gaps']:
            state_id = gap['state_id']
            # If this gap has a valid source alternative, mark as SOURCE_ONLY instead of error
            if state_id in source_alt_states:
                # Verify source proof input was provided
                source_proof_provided = any(
                    item['kind'] == 'ios_source_proof' and item.get('state_id') == state_id
                    for item in packet['required_inputs']
                )
                if source_proof_provided:
                    warnings.append({**gap, 'unit_id': unit['unit_id'], 'resolution': 'source_only'})
                else:
                    errors.append({**gap, 'unit_id': unit['unit_id'], 'root_cause': 'information_gap'})
            else:
                errors.append({**gap, 'unit_id': unit['unit_id'], 'root_cause': 'information_gap'})
        inventory_source = packet['inventory_source']
        try:
            checked_artifact(_project_file(root, inventory_source['path']), inventory_source['sha256'])
        except (OSError, ValueError) as exc:
            errors.append({'code': 'approved_inventory_changed', 'detail': str(exc), 'unit_id': unit['unit_id'],
                           'root_cause': 'information_gap'})
        artifacts = {
            'output.ets': _project_file(root, unit['output']['file']),
            'conversion-report.json': _project_file(root, f'spec/execution/conversion-reports/{unit["unit_id"]}.json'),
        }
        for name, path in artifacts.items():
            if path.is_file():
                files[name] = path.read_bytes()
        _check_unit(root, unit, {**packet, 'packet_sha256': prepared['packet_sha256']},
                    errors, warnings, check_host=False)
        if 'conversion-report.json' in files:
            try:
                report = json.loads(files['conversion-report.json'])
                observations = {(item['state_id'], item['comparison_id']) for item in report.get('image_observations', [])}
            except (AttributeError, TypeError, KeyError, ValueError):
                observations = set()
            for item in packet['required_inputs']:
                # ALWAYS require image observations for screenshot_png inputs, never waived
                if item['kind'] == 'screenshot_png' and (item['state_id'], item['input_id']) not in observations:
                    errors.append({'code': 'image_observation_missing', 'unit_id': unit['unit_id'],
                                   'state_id': item.get('state_id'), 'input_id': item['input_id'],
                                   'root_cause': 'product_defect'})
        for name, path in artifacts.items():
            current = path.read_bytes() if path.is_file() else None
            if current != files.get(name):
                raise ValueError(f'conversion output changed during G0 preflight: {path}')
        # Determine status: PASS if no errors, SOURCE_ONLY if only source alternatives used, BLOCKED otherwise
        has_source_only = any(w.get('resolution') == 'source_only' for w in warnings)
        status = 'BLOCKED' if errors else ('SOURCE_ONLY' if has_source_only else 'PASS')

        preflight = {'schema_version': 2, 'policy_gate': 'execute.stage1-g0', 'dispatch_id': dispatch_id,
                     'unit_id': unit['unit_id'], 'status': status, 'result_scope': 'SOURCE_ONLY' if has_source_only else 'ORIGINAL_G0',
                     'failure_findings': errors, 'warnings': warnings,
                     'archive_sha256': {name: sha256(data) for name, data in files.items()}}
        files['preflight.json'] = json_bytes(preflight)
        archive = folder / dispatch_id / 'g0'
        save_directory(archive, files)
        result = {**prepared, 'status': preflight['status'], 'archive_path': project_relative(root, archive),
                  'preflight_sha256': sha256(files['preflight.json']), 'failure_findings': errors}
        append_event(folder, records, {'event': 'complete', 'dispatch_id': dispatch_id, 'result': result})
        return result


def reuse_metadata(root, dispatch_id, packet_path):
    folder = dispatch_root(root)
    with locked(folder):
        prepared, _, _ = read_prepared(root, events(folder), dispatch_id)
        checked_artifact(_project_file(root, packet_path), prepared['packet_sha256'])
        return {**prepared, 'reused': True}


def aggregate_g0(root):
    folder = dispatch_root(root)
    inventory_path, inventory = load_inventory(root, None)
    inventory_hash = sha256(inventory_path.read_bytes())
    with locked(folder):
        records = events(folder)
        attempts = {}
        for event in records:
            if event['event'] == 'prepare':
                row = event['result']
                name = row['unit_id']
                attempts.setdefault(name, []).append(row)
        units = []
        for unit in inventory['units']:
            if unit.get('required') is False:
                continue
            name = unit['unit_id']
            all_rows = attempts.get(name, [])
            current_rows = []
            prior_rows = []
            for row in all_rows:
                packet_path = _project_file(root, row['packet_path'])
                checked_artifact(packet_path, row['packet_sha256'])
                packet = _read_object(packet_path)
                row_inv_hash = digest(packet['inventory_source']['sha256'])
                if row_inv_hash == inventory_hash:
                    current_rows.append(row)
                else:
                    prior_rows.append((row, row_inv_hash))
            if not current_rows:
                units.append({'unit_id': name, 'status': 'NOT_RUN', 'code': 'first_g0_archive_missing'})
                continue
            current_rows.sort(key=lambda r: r['attempt'])
            row = current_rows[0]
            archived = read_completed(root, records, row['dispatch_id'])
            unit_result = archived or {'unit_id': name, 'status': 'NOT_RUN', 'code': 'first_g0_archive_missing'}
            prior_history = []
            for prior_row, prior_inv_hash in prior_rows:
                prior_completed = read_completed(root, records, prior_row['dispatch_id'])
                prior_history.append({
                    'unit_id': name, 'dispatch_id': prior_row['dispatch_id'],
                    'inventory_sha256': prior_inv_hash,
                    'status': prior_completed['status'] if prior_completed else 'NOT_RUN',
                    'archive_path': prior_completed['archive_path'] if prior_completed else None,
                })
            if prior_history:
                unit_result['prior_authority_history'] = prior_history
            units.append(unit_result)
        # Determine aggregate status: PASS if all PASS, structural if some SOURCE_ONLY, BLOCKED otherwise
        pass_count = sum(1 for u in units if u['status'] == 'PASS')
        source_only_count = sum(1 for u in units if u['status'] == 'SOURCE_ONLY')
        blocked_count = sum(1 for u in units if u['status'] == 'BLOCKED')

        if units and pass_count == len(units):
            overall_status = 'PASS'
            structural_status = 'PASS'
        elif units and (pass_count + source_only_count) == len(units) and source_only_count > 0:
            overall_status = 'BLOCKED'  # Visual still blocked
            structural_status = 'PASS'  # But structural code is complete
        else:
            overall_status = 'BLOCKED'
            structural_status = 'BLOCKED'

        result = {'schema_version': 2, 'policy_gate': 'execute.stage1-g0', 'result_scope': 'ORIGINAL_G0',
                  'status': overall_status, 'structural_status': structural_status,
                  'stage1_complete': False, 'visual_status': 'BLOCKED',
                  'required_units': len(units), 'units': units, 'inventory_sha256': inventory_hash}
        if units and all(row['status'] in {'PASS', 'BLOCKED', 'SOURCE_ONLY'} for row in units):
            raw = json_bytes(result)
            content_hash = sha256(raw)
            archive_root = folder / 'g0'
            archive_root.mkdir(exist_ok=True)
            archive_path = archive_root / content_hash
            if archive_path.exists():
                checked_artifact(archive_path / 'aggregate.json', content_hash)
            else:
                save_directory(archive_path, {'aggregate.json': raw})
            destination = folder / 'g0.json'
            if not destination.exists():
                atomic_write(destination, raw)
        return result
