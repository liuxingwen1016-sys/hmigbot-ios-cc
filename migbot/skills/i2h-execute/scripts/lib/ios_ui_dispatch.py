"""Bind converter attempts to approved iOS inputs and preserve their original G0."""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from contextlib import contextmanager, nullcontext
from pathlib import Path

from .ios_stage1_scope import load_inventory
from .ios_ui_delivery_gate import _check_unit, _project_file, _read_object, _states, host_slots


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
    return _parse_events(path.read_bytes() if path.is_file() else None)


def _parse_events(content):
    records = []
    previous = None
    for line in (content or b'').decode('utf-8').splitlines():
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


def _dispatch_scope(root):
    index_path = _project_file(root, INDEX)
    index_bytes = index_path.read_bytes()
    index = json.loads(index_bytes)
    if not isinstance(index, dict):
        raise ValueError('UI input index must contain a JSON object')
    source = index['inventory_source']
    inventory_path, _ = load_inventory(root, source['path'])
    inventory_bytes = checked_artifact(inventory_path, source['sha256'])
    return index_path, index_bytes, index, inventory_path, inventory_bytes, json.loads(inventory_bytes)


def prepare(root, unit_id, attempt, *, no_working_copies=False, check_only=False, resume_pending=False,
            _scope=None, _records=None):
    if not NAME.fullmatch(unit_id) or attempt < 1:
        raise ValueError('unit_id must be a safe identifier and attempt must be positive')
    _, _, index, inventory_path, inventory_bytes, inventory = _scope if _scope is not None else _dispatch_scope(root)
    source = index['inventory_source']
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
    source_only_states = []
    inputs = []
    originals = {}
    working_copies = index.get('working_copies', True) and not no_working_copies

    def add(input_id, path, expected, kind, display_path, **identity):
        data = checked_artifact(path, expected)
        if check_only and not resume_pending:
            inputs.append({'input_id': input_id, 'kind': kind, 'path': display_path, 'sha256': digest(expected)})
            return
        if check_only:
            content_path = _project_file(folder, f'objects/{digest(expected)}{path.suffix}')
        else:
            content_path = store_artifact(folder, expected, data, path.suffix)
        if kind == 'screenshot_png':
            identity['comparison_id'] = input_id
        inputs.append({'input_id': input_id, 'kind': kind, 'path': display_path,
                       'sha256': digest(expected), 'object': project_relative(root, content_path), **identity})
        originals[input_id] = (content_path if working_copies else path)

    with nullcontext() if check_only else locked(folder):
        records = [] if check_only else events(folder)
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
                approved_state = approved_states[state_id]
                evidence = state.get('evidence', {})
                if (approved_state.get('arrival_mode') == 'behavior' and approved_state.get('source_refs')
                        and not approved_state.get('required_evidence')
                        and (evidence.get('status') == 'blocked'
                             or (evidence.get('status') == 'missing'
                                 and evidence.get('reason') == 'runtime evidence missing'))):
                    source_only_states.append(state_id)
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
        # This behavior hint is advisory; only approved typed alternatives can resolve gaps.
        advisory = {}
        if source_only_states and len(source_only_states) == len(gaps):
            # A fully verified runtime state must still be available as a visual reference for the unit.
            gaps_by_state = {gap['state_id'] for gap in gaps}
            if any(state['state_id'] not in gaps_by_state for state in frozen['required_states']):
                advisory = {'conversion_scope': 'SOURCE_ONLY_BEHAVIOR_GAPS', 'source_only_states': source_only_states}
        packet = {**frozen, 'schema_version': 2, 'dispatch_id': dispatch_id, 'attempt': attempt,
                  'required_inputs': inputs, 'input_gaps': gaps, 'inventory_source': source, **advisory}
        if slots:
            packet['integration'] = slots
        source_obligations = unit.get('source_obligations', {})
        for key in ('system_symbol_fidelity', 'date_format_calls', 'share_link_calls'):
            if rows := source_obligations.get(key):
                packet[key] = rows
        drawing_calls = unit.get('source_obligations', {}).get('drawing_component_calls', [])
        if drawing_calls:
            packet['drawing_component_calls'] = drawing_calls
            definitions = [row['definition'] for row in drawing_calls]
            drawing_bindings = [row for row in inventory.get('drawing_component_bindings', [])
                                if row['definition'] in definitions]
            if drawing_bindings:
                packet['drawing_component_bindings'] = drawing_bindings
        source_alt_state_ids = {alt['state_id'] for alt in validated_alternatives}
        status = ('SOURCE_ONLY' if gaps and all(gap['state_id'] in source_alt_state_ids for gap in gaps)
                  else 'BLOCKED' if gaps else 'READY')
        if check_only:
            if _scope is None:
                checked_artifact(inventory_path, source['sha256'])
            result = {'status': status, 'scope': 'INPUT_CHECK_ONLY',
                      'unit_id': unit_id, 'inventory_sha256': source['sha256'],
                      'checked_inputs': inputs, 'input_gaps': gaps, **advisory}
            if resume_pending and not gaps:
                pending = resumable_preparation(root, unit_id, packet, records=_records)
                if pending is not None:
                    result['pending_attempt'] = pending
            return result
        packet_bytes = json_bytes(packet)
        result = {
            'status': status, 'dispatch_id': dispatch_id, 'unit_id': unit_id, 'attempt': attempt,
            'packet_path': project_relative(root, destination / 'packet.json'), 'packet_sha256': sha256(packet_bytes),
            'prompt_path': project_relative(root, destination / 'prompt.md'), 'input_gaps': gaps, **advisory,
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
        if advisory and status == 'BLOCKED':
            prompt.extend([
                '',
                'Source-only behavior gaps: ' + ', '.join(source_only_states),
                'Implement the declared states from their approved Swift/ObjC anchors after the host authorizes',
                'work with gaps under Stage 1 policy. Use all supplied visual inputs for the other states.',
                'Do not report image observations for missing states. G0 remains BLOCKED until evidence is supplied.',
            ])
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


def check_required_inputs(root, *, resume_pending=False, unit_ids: set[str] | None = None):
    """Check approved dispatch inputs without creating per-unit attempts."""
    scope = _dispatch_scope(root)
    index_path, index_bytes, index, inventory_path, _, inventory = scope
    source = index['inventory_source']
    required = [unit['unit_id'] for unit in inventory['units'] if unit.get('required') is not False]
    if unit_ids is not None:
        if not unit_ids:
            raise ValueError('select at least one required dispatch unit')
        unexpected = unit_ids.difference(required)
        if unexpected:
            raise ValueError(f"selected dispatch units are not required: {', '.join(sorted(unexpected))}")
        required = [unit_id for unit_id in required if unit_id in unit_ids]
    folder = dispatch_root(root)
    event_path = folder / 'events.jsonl'
    event_bytes = event_path.read_bytes() if resume_pending and event_path.is_file() else None
    records = _parse_events(event_bytes) if resume_pending else None
    units = []
    for unit_id in required:
        result = prepare(root, unit_id, 1, check_only=True, resume_pending=resume_pending,
                         _scope=scope, _records=records)
        result['checked_inputs_count'] = len(result.pop('checked_inputs'))
        result.pop('inventory_sha256')
        result.pop('scope')
        units.append(result)
    checked_artifact(inventory_path, source['sha256'])
    checked_artifact(index_path, sha256(index_bytes))
    if resume_pending:
        current_events = event_path.read_bytes() if event_path.is_file() else None
        if current_events != event_bytes:
            raise ValueError('dispatch events changed while checking required inputs')
    ready = sum(unit['status'] == 'READY' for unit in units)
    source_only = sum(unit['status'] == 'SOURCE_ONLY' for unit in units)
    blocked = len(units) - ready - source_only
    status = ('BLOCKED' if not units or blocked else 'SOURCE_ONLY' if source_only else 'READY')
    result_scope = 'REQUIRED_INPUT_CHECK_ONLY' if unit_ids is None else 'SELECTED_REQUIRED_INPUT_CHECK_ONLY'
    result = {'status': status, 'scope': result_scope,
              'inventory_sha256': source['sha256'], 'required_units': len(units), 'ready_units': ready,
              'blocked_units': blocked, 'units': units}
    if source_only:
        result.update(source_only_units=source_only, visual_status='BLOCKED')
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
        if 'output.ets' in files and (packet.get('date_format_calls') or packet.get('share_link_calls') or any(
            row.get('role') == 'label' and row.get('target_symbol')
            for row in packet.get('system_symbol_fidelity', [])
        )):
            from ui_obligation_gate import check_date_formats, check_label_symbols, check_share_links
            try:
                arkts = files['output.ets'].decode('utf-8')
                findings = check_label_symbols(arkts, unit) + check_date_formats(arkts, unit) + check_share_links(arkts, unit)
            except UnicodeDecodeError:
                findings = []  # _check_unit already reports unreadable ArkTS.
            errors.extend({**finding, 'root_cause': 'product_defect'} for finding in findings)
        if 'conversion-report.json' in files:
            try:
                report = json.loads(files['conversion-report.json'])
                observations = {(item['state_id'], item['comparison_id']) for item in report.get('image_observations', [])}
            except (AttributeError, TypeError, KeyError, ValueError):
                observations = set()
            for item in packet['required_inputs']:
                if item['kind'] == 'screenshot_png' and (item['state_id'], item['input_id']) not in observations:
                    errors.append({'code': 'image_observation_missing', 'unit_id': unit['unit_id'],
                                   'state_id': item['state_id'], 'input_id': item['input_id'],
                                   'root_cause': 'product_defect'})
        for name, path in artifacts.items():
            current = path.read_bytes() if path.is_file() else None
            if current != files.get(name):
                raise ValueError(f'conversion output changed during G0 preflight: {path}')
        has_source_only = any(w.get('resolution') == 'source_only' for w in warnings)
        status = 'BLOCKED' if errors else ('SOURCE_ONLY' if has_source_only else 'PASS')
        preflight = {'schema_version': 2, 'policy_gate': 'execute.stage1-g0', 'dispatch_id': dispatch_id,
                     'unit_id': unit['unit_id'], 'status': status,
                     'result_scope': 'SOURCE_ONLY' if has_source_only else 'ORIGINAL_G0',
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


def attempts_for_inventory(root, records, inventory_hash):
    attempts = {}
    stale_units = set()
    for event in records:
        if event['event'] != 'prepare':
            continue
        row = event['result']
        raw = checked_artifact(_project_file(root, row['packet_path']), row['packet_sha256'])
        packet = json.loads(raw)
        unit = row['unit_id']
        if digest(packet['inventory_source']['sha256']) == inventory_hash:
            attempts.setdefault(unit, []).append(row)
        else:
            stale_units.add(unit)
    for rows in attempts.values():
        rows.sort(key=lambda row: row['attempt'])
    return attempts, stale_units


def first_archived_g0(root, records, attempts):
    """Return the earliest numbered attempt with an actual archive in this approved scope."""
    completed = {event['dispatch_id'] for event in records if event['event'] == 'complete'}
    for row in attempts:
        if row['dispatch_id'] in completed:
            return read_completed(root, records, row['dispatch_id'])
    return None


def packet_inputs(packet):
    return {key: value for key, value in packet.items() if key not in {'attempt', 'dispatch_id'}}


def resumable_preparation(root, unit_id, packet, *, records=None):
    """Find the earliest equivalent pending preparation after the latest completed attempt."""
    folder = dispatch_root(root)
    if records is None:
        records = events(folder)
    rows = [event['result'] for event in records if event['result']['unit_id'] == unit_id
            and event['event'] == 'prepare']
    checkpoint = packet['inventory_source']['sha256']
    # The event does not duplicate the inventory digest. Verify it from the frozen packet.
    completed_ids = {event['dispatch_id'] for event in records if event['event'] == 'complete'}
    prepared_for_scope = []
    for row in rows:
        if row['status'] != 'READY' and row['dispatch_id'] not in completed_ids:
            continue
        prepared, old_packet, _ = read_prepared(root, records, row['dispatch_id'])
        if old_packet['inventory_source']['sha256'] == checkpoint:
            prepared_for_scope.append((prepared, old_packet))
    latest_complete = max((row['attempt'] for row, _ in prepared_for_scope
                           if row['dispatch_id'] in completed_ids), default=0)
    report_path = _project_file(root, f'spec/execution/conversion-reports/{unit_id}.json')
    bound_dispatch = _read_object(report_path).get('dispatch_id') if report_path.is_file() else None
    for prepared, old_packet in sorted(prepared_for_scope, key=lambda item: item[0]['attempt']):
        if (prepared['attempt'] <= latest_complete or packet_inputs(old_packet) != packet_inputs(packet)
                or (bound_dispatch is not None and prepared['dispatch_id'] != bound_dispatch)):
            continue
        archive = folder / prepared['dispatch_id'] / 'g0'
        if archive.exists():
            raise ValueError(f'G0 archive without a complete event: {prepared["dispatch_id"]}')
        for item in old_packet['required_inputs']:
            checked_artifact(_project_file(root, item['object']), item['sha256'])
        return prepared
    return None


def current_g0(root, records, attempts):
    """Use an archived result across a pending retry with byte-equivalent inputs."""
    latest_id = attempts[-1]['dispatch_id']
    latest = read_completed(root, records, latest_id)
    if latest is not None or len(attempts) == 1:
        return latest
    for attempt in reversed(attempts[:-1]):
        candidate = read_completed(root, records, attempt['dispatch_id'])
        if candidate is not None:
            break
    else:
        return None
    if candidate['status'] not in {'PASS', 'SOURCE_ONLY'}:
        return None
    prepared, packet, _ = read_prepared(root, records, latest_id)
    if prepared['input_gaps']:
        return None
    archive = _project_file(root, candidate['archive_path'])
    old = _read_object(archive / 'packet.json')
    if packet_inputs(packet) != packet_inputs(old):
        return None
    output = _project_file(root, packet['output']['file'])
    report = _project_file(root, f'spec/execution/conversion-reports/{prepared["unit_id"]}.json')
    if (not output.is_file() or output.read_bytes() != (archive / 'output.ets').read_bytes()
            or not report.is_file() or report.read_bytes() != (archive / 'conversion-report.json').read_bytes()):
        return None
    return candidate


def recovery_review(root):
    """Compare current prepared units with their last passing historical G0."""
    folder = dispatch_root(root)
    inventory_path, inventory = load_inventory(root, None)
    inventory_hash = sha256(inventory_path.read_bytes())
    with locked(folder):
        records = events(folder)
        current, _ = attempts_for_inventory(root, records, inventory_hash)
        passing = {}
        for event in records:
            row = event['result']
            if event['event'] == 'complete' and row['status'] == 'PASS':
                passing.setdefault(row['unit_id'], []).append(row)
        units = []
        for unit in inventory['units']:
            if unit.get('required') is False:
                continue
            name = unit['unit_id']
            attempts = current.get(name, [])
            row = {'unit_id': name, 'status': 'NEEDS_CURRENT_DISPATCH'}
            if not attempts:
                units.append(row)
                continue
            prepared, packet, _ = read_prepared(root, records, attempts[-1]['dispatch_id'])
            row['dispatch_id'] = prepared['dispatch_id']
            if prepared['input_gaps']:
                row.update(status='INPUT_BLOCKED', input_gaps=prepared['input_gaps'])
            elif (completed := current_g0(root, records, attempts)) and completed['status'] == 'PASS':
                row['status'] = 'CURRENT_G0_PASS'
                row['g0_dispatch_id'] = completed['dispatch_id']
            elif old_attempts := passing.get(name):
                previous = max(old_attempts, key=lambda row: row['attempt'])
                old = read_completed(root, records, previous['dispatch_id'])
                archive = _project_file(root, old['archive_path'])
                old_packet = _read_object(archive / 'packet.json')
                old_unit = select_unit(_read_object(archive / 'inventory.json'), name)
                packet_fields = (packet.keys() | old_packet.keys()) - {'inventory_source', 'attempt', 'dispatch_id'}
                changed_fields = sorted(key for key in packet_fields if packet.get(key) != old_packet.get(key))
                changed_unit_fields = sorted(key for key in unit.keys() | old_unit.keys()
                                             if unit.get(key) != old_unit.get(key))
                output = _project_file(root, packet['output']['file'])
                output_changed = not output.is_file() or output.read_bytes() != (archive / 'output.ets').read_bytes()
                row.update(status='REVIEW_REQUIRED', previous_dispatch_id=old['dispatch_id'],
                           changed_packet_fields=changed_fields, changed_unit_fields=changed_unit_fields,
                           output_changed=output_changed)
            else:
                row['status'] = 'REVIEW_REQUIRED'
                row['reason'] = 'no_passing_historical_g0'
            units.append(row)
        checked_artifact(inventory_path, inventory_hash)
    return {'schema_version': 1, 'status': 'PASS' if units and all(
        row['status'] == 'CURRENT_G0_PASS' for row in units) else 'BLOCKED',
        'inventory_sha256': inventory_hash, 'units': units}


def aggregate_g0(root):
    folder = dispatch_root(root)
    inventory_path, inventory = load_inventory(root, None)
    inventory_hash = sha256(inventory_path.read_bytes())
    with locked(folder):
        records = events(folder)
        attempts, stale_units = attempts_for_inventory(root, records, inventory_hash)
        units = []
        for unit in inventory['units']:
            if unit.get('required') is False:
                continue
            name = unit['unit_id']
            rows = attempts.get(name, [])
            if not rows and name in stale_units:
                units.append({'unit_id': name, 'status': 'STALE', 'code': 'approved_inventory_changed'})
                continue
            archived = first_archived_g0(root, records, rows)
            units.append(archived or {'unit_id': name, 'status': 'NOT_RUN', 'code': 'first_g0_archive_missing'})
        for unit_result in units:
            name = unit_result['unit_id']
            history = []
            for event in records:
                if event['event'] != 'prepare' or event['result']['unit_id'] != name:
                    continue
                row = event['result']
                raw = checked_artifact(_project_file(root, row['packet_path']), row['packet_sha256'])
                old_hash = digest(json.loads(raw)['inventory_source']['sha256'])
                if old_hash != inventory_hash:
                    completed = read_completed(root, records, row['dispatch_id'])
                    history.append({'unit_id': name, 'dispatch_id': row['dispatch_id'],
                                    'inventory_sha256': old_hash,
                                    'status': completed['status'] if completed else 'NOT_RUN',
                                    'archive_path': completed['archive_path'] if completed else None})
            if history:
                unit_result['prior_authority_history'] = history
        structurally_ready = units and all(row['status'] in {'PASS', 'SOURCE_ONLY'} for row in units)
        result = {'schema_version': 2, 'policy_gate': 'execute.stage1-g0', 'result_scope': 'ORIGINAL_G0',
                  'status': 'PASS' if units and all(row['status'] == 'PASS' for row in units) else 'BLOCKED',
                  'structural_status': 'PASS' if structurally_ready else 'BLOCKED', 'visual_status': 'BLOCKED',
                  'stage1_complete': False, 'required_units': len(units), 'units': units,
                  'inventory_sha256': inventory_hash}
        if units and all(row['status'] in {'PASS', 'BLOCKED', 'SOURCE_ONLY'} for row in units):
            destination = folder / 'g0' / f'{inventory_hash}.json'
            destination.parent.mkdir(exist_ok=True)
            raw = json_bytes(result)
            if destination.exists() and destination.read_bytes() != raw:
                raise ValueError('original aggregate already exists for a different approved scope')
            if not destination.exists():
                atomic_write(destination, raw)
            # Preserve the first project aggregate as immutable history across authority changes.
            original = folder / 'g0.json'
            if not original.exists():
                atomic_write(original, raw)
        return result
