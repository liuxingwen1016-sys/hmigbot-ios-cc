"""Persist and replay actual Stage-1 compile and final smoke receipts."""
from __future__ import annotations

from .ios_stage1_acceptance import archive_g1
from .ios_stage1_scope import MAX_REPAIRS, acceptance_lane, build_scope_from_inventory
from .ios_stage1_visual_gate import _arrival, _checked_json, _checked_ref, _json_object, _receipt, checked_build
from .ios_ui_dispatch import append_event, digest, dispatch_root, events, json_bytes, locked, sha256
from .stage1_contract import source_digest


def read_scope(root, path):
    raw = path.read_bytes()
    scope = _json_object(raw)
    if scope != build_scope_from_inventory(root, None) or scope.get('schema_version') != 2 or not scope['pairs']:
        raise ValueError('STALE or incomplete iOS visual scope; freeze it again against the current project')
    return scope, sha256(raw)


def reference(root, path):
    if not path.is_relative_to(root / 'spec'):
        raise ValueError('acceptance evidence must be inside spec')
    return {'path': path.relative_to(root / 'spec').as_posix(), 'sha256': sha256(path.read_bytes())}


def matching(records, kind, scope):
    key = acceptance_lane(scope)
    return [row['result'] for row in records if row['event'] == kind and row['lane'] == key]


def validate_compile(root, scope, scope_hash, report):
    raw_status = report.get('status')
    source_hash = scope['source_sha256']
    if digest(report.get('scope_sha256')) != scope_hash or digest(report.get('source_sha256', source_hash)) != digest(source_hash):
        raise ValueError('compile report does not bind the current scope and source')
    if raw_status == 'PASS':
        build = checked_build(root, report['build_receipt'], scope_hash, source_hash)
        return {'build_receipt': report['build_receipt'], 'hap_sha256': digest(build['hap_sha256'])}
    if raw_status not in {'FAIL', 'BLOCKED'}:
        raise ValueError('compile status must be PASS, FAIL or BLOCKED')
    if digest(report.get('source_sha256')) != digest(source_hash) or not str(report.get('reason') or '').strip():
        raise ValueError('failed or blocked compile requires the actual source digest and a reason')
    _, log = _checked_ref(root, report['evidence'])
    if not log.strip():
        raise ValueError('compile diagnostic is empty')
    if raw_status == 'FAIL' and (type(report.get('exit_code')) is not int or report['exit_code'] == 0):
        raise ValueError('compile failure requires the actual nonzero compiler exit code')
    return {'evidence': report['evidence'], 'reason': report['reason'], 'exit_code': report.get('exit_code')}


def record_compile(root, scope_path, report_path, build_path, wiring_contract):
    scope, scope_hash = read_scope(root, scope_path)
    if (report_path is None) == (build_path is None):
        raise ValueError('compile requires one --report or --build-receipt')
    if archive_g1(root, wiring_contract, read_only=True)['status'] != 'PASS':
        raise ValueError('archive the current passing G1 before registering a compile')
    report = (_json_object(report_path.read_bytes()) if report_path else {
        'status': 'PASS', 'scope_sha256': scope_hash, 'build_receipt': reference(root, build_path),
    })
    proof = validate_compile(root, scope, scope_hash, report)
    raw_status = report['status']
    source_hash = scope['source_sha256']
    key = sha256(json_bytes([raw_status, source_hash, proof.get('hap_sha256') or proof['evidence']['sha256'],
                            proof.get('exit_code')]))
    folder = dispatch_root(root)
    with locked(folder):
        if read_scope(root, scope_path) != (scope, scope_hash):
            raise ValueError('scope changed while registering the compile')
        records = events(folder)
        previous = matching(records, 'stage1_compile', scope)
        if previous and previous[-1]['scope_sha256'] == scope_hash and previous[-1]['evidence_id'] == key:
            return previous[-1]
        productive = [row for row in previous if row['raw_status'] != 'BLOCKED']
        last = productive[-1] if productive else None
        attempt, cycle = (last['attempt'], last['cycle']) if last else (0, 0)
        if last and last['raw_status'] == 'FAIL':
            if last['attempt'] >= MAX_REPAIRS:
                raise ValueError('compile repair budget exhausted for this approved scope')
            if raw_status != 'BLOCKED':
                if last['source_sha256'] == source_hash:
                    raise ValueError('a compiler repair must use changed source; preserve the original failure')
                attempt += 1
        elif last and last['source_sha256'] != source_hash:
            attempt, cycle = 0, cycle + 1
        if raw_status == 'BLOCKED':
            recovery = len(previous) - previous.index(last) - 1 if last else len(previous)
            if recovery > MAX_REPAIRS:
                raise ValueError('compile environment recovery budget exhausted for this cycle')
        status = 'REPAIR_REQUIRED' if raw_status == 'FAIL' and attempt < MAX_REPAIRS else raw_status
        result = {
            'schema_version': 2, 'policy_gate': 'execute.stage1-compile',
            'status': status, 'raw_status': raw_status, 'attempt': attempt, 'cycle': cycle,
            'stage1_complete': False, 'source_sha256': source_hash, 'scope_sha256': scope_hash,
            'evidence_id': key, **proof,
        }
        append_event(folder, records, {'event': 'stage1_compile', 'lane': acceptance_lane(scope), 'result': result})
        return result


def latest_compile(root, scope, scope_hash):
    previous = matching(events(dispatch_root(root)), 'stage1_compile', scope)
    if not previous:
        return None
    latest = previous[-1]
    if latest['scope_sha256'] != scope_hash or latest['source_sha256'] != scope['source_sha256']:
        return {**latest, 'current': False}
    if latest['status'] == 'PASS':
        build = checked_build(root, latest['build_receipt'], scope_hash, scope['source_sha256'])
        if latest['hap_sha256'] != digest(build['hap_sha256']):
            raise ValueError('archived compile and current HAP do not match')
    else:
        _checked_ref(root, latest['evidence'])
    return {**latest, 'current': True}


def validate_smoke(root, scope, scope_hash, report):
    source_hash = scope['source_sha256']
    if digest(report.get('scope_sha256')) != scope_hash:
        raise ValueError('smoke report does not bind the current scope')
    build = checked_build(root, report['build_receipt'], scope_hash, source_hash)
    install = _receipt(root, report['install_receipt'], 'install', scope_hash, source_hash)
    hap_hash, device = digest(build['hap_sha256']), install.get('device_id')
    if not isinstance(device, str) or not device or hap_hash != digest(install.get('hap_sha256')):
        raise ValueError('smoke must use the actual device and current built HAP')
    cold = _checked_json(root, report['cold_start'])
    if (cold.get('kind'), cold.get('status'), cold.get('device_id'), digest(cold.get('hap_sha256')),
            digest(cold.get('scope_sha256')), digest(cold.get('source_sha256'))) != (
            'cold_start', 'PASS', device, hap_hash, scope_hash, digest(source_hash)):
        raise ValueError('missing successful cold start for this installation')
    if not isinstance(cold.get('capture_run_id'), str) or not cold['capture_run_id']:
        raise ValueError('cold start requires an actual capture run')
    _checked_ref(root, cold['evidence'])
    formal = {pair['pair_id']: pair for pair in scope['pairs'] if pair['arrival_mode'] == 'formal'}
    pages = {pair['page_id'] for pair in formal.values()}
    tabs = {key for key, pair in formal.items() if pair['state_id'].endswith('-tab')}
    seen_pairs, seen_pages, seen_evidence, runs = set(), set(), set(), set()
    cases = report['cases']
    if not isinstance(cases, list):
        raise ValueError('smoke cases must be an array')
    for case in cases:
        receipt = _checked_json(root, case['evidence'])
        pair_id = receipt.get('pair_id')
        pair = formal.get(pair_id)
        evidence_id = digest(case['evidence']['sha256'])
        if (not pair or pair_id in seen_pairs or evidence_id in seen_evidence or case.get('arrived') is not True
                or case.get('page_id') != pair['page_id'] or receipt.get('observed_page_id') != pair['page_id']
                or receipt.get('observed_state_id') != pair['state_id'] or not receipt.get('capture_run_id')):
            raise ValueError('smoke case requires unique evidence for the actual formal page and state')
        if receipt['build_receipt'] != report['build_receipt'] or receipt['install_receipt'] != report['install_receipt']:
            raise ValueError('smoke cases must use the same build and install receipts')
        if _arrival(root, pair, {'arrival_receipt': case['evidence']}, scope_hash, source_hash) != (hap_hash, device):
            raise ValueError('smoke case belongs to another HAP or device')
        seen_pairs.add(pair_id)
        seen_pages.add(pair['page_id'])
        seen_evidence.add(evidence_id)
        runs.add(receipt['capture_run_id'])
    if seen_pages != pages or not tabs <= seen_pairs:
        raise ValueError('smoke must cover every formal page and approved tab state')
    if runs and runs != {cold['capture_run_id']}:
        raise ValueError('smoke cases and cold start must be from one capture run')
    return {'hap_sha256': hap_hash, 'device_id': device, 'covered_pages': sorted(seen_pages),
            'covered_pairs': sorted(seen_pairs), 'capture_run_id': cold['capture_run_id']}


def record_smoke(root, scope_path, report_path):
    scope, scope_hash = read_scope(root, scope_path)
    report_ref = reference(root, report_path)
    proof = validate_smoke(root, scope, scope_hash, _checked_json(root, report_ref))
    folder = dispatch_root(root)
    with locked(folder):
        if read_scope(root, scope_path) != (scope, scope_hash):
            raise ValueError('scope changed while registering smoke')
        records = events(folder)
        previous = matching(records, 'stage1_smoke', scope)
        current = latest_compile(root, scope, scope_hash)
        if current and (not current['current'] or current['status'] != 'PASS' or current['hap_sha256'] != proof['hap_sha256']):
            raise ValueError('smoke does not bind the latest recorded compile')
        result = {'schema_version': 2, 'policy_gate': 'execute.stage1-smoke', 'status': 'PASS',
                  'stage1_complete': False, 'source_sha256': scope['source_sha256'], 'scope_sha256': scope_hash,
                  'report': report_ref, **proof}
        if not previous or previous[-1] != result:
            append_event(folder, records, {'event': 'stage1_smoke', 'lane': acceptance_lane(scope), 'result': result})
        return result


def latest_smoke(root, scope, scope_hash, hap_hash):
    previous = matching(events(dispatch_root(root)), 'stage1_smoke', scope)
    if not previous:
        return None
    latest = previous[-1]
    if (latest['scope_sha256'], latest['source_sha256'], latest['hap_sha256']) != (
        scope_hash, scope['source_sha256'], hap_hash,
    ):
        return None
    proof = validate_smoke(root, scope, scope_hash, _checked_json(root, latest['report']))
    if any(latest[key] != value for key, value in proof.items()):
        raise ValueError('archived smoke does not match current evidence')
    return latest
