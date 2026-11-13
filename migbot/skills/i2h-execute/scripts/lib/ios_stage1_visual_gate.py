"""Validate visual evidence for every frozen iOS verification pair."""
from __future__ import annotations

import json

from .ios_stage1_scope import MAX_REPAIRS, acceptance_lane, build_scope_from_inventory
from .ios_ui_delivery_gate import _project_file
from .ios_ui_dispatch import (
    append_event, atomic_write, checked_artifact, digest, dispatch_root, events, json_bytes, locked,
    project_relative, save_directory, sha256,
)
from .ios_ui_relationships import compare_relationships
from .stage1_contract import source_digest


def _checked_ref(root, ref):
    path = _project_file(root / 'spec', ref['path'])
    raw = checked_artifact(path, ref['sha256'])
    if not raw:
        raise ValueError(f'empty evidence: {path}')
    return path, raw


def _checked_json(root, ref):
    _, raw = _checked_ref(root, ref)
    return _json_object(raw)


def _json_object(raw):
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError('visual evidence must contain a JSON object')
    return value


def _index(rows, key):
    if not isinstance(rows, list):
        raise ValueError(f'{key} entries must be an array')
    result = {}
    for row in rows:
        name = row[key]
        if not isinstance(name, str) or not name or name in result:
            raise ValueError(f'duplicate or empty {key}')
        result[name] = row
    return result


def _receipt(root, ref, kind, scope_hash, source_hash):
    value = _checked_json(root, ref)
    if value.get('kind') != kind or value.get('status') != 'PASS':
        raise ValueError(f'{kind} receipt is not PASS')
    if digest(value.get('scope_sha256')) != scope_hash or digest(value.get('source_sha256')) != digest(source_hash):
        raise ValueError(f'{kind} receipt is bound to different scope or source')
    return value


def checked_build(root, ref, scope_hash, source_hash):
    build = _receipt(root, ref, 'build', scope_hash, source_hash)
    checked_artifact(_project_file(root, build['hap_path']), build['hap_sha256'])
    return build


def _arrival(root, expected, actual, scope_hash, source_hash):
    receipt = _checked_json(root, actual['arrival_receipt'])
    if (receipt.get('status'), receipt.get('pair_id'), receipt.get('arrival_mode')) != (
        'PASS', expected['pair_id'], expected['arrival_mode']
    ):
        raise ValueError('arrival receipt is bound to a different pair or mode')
    build = checked_build(root, receipt['build_receipt'], scope_hash, source_hash)
    install = _receipt(root, receipt['install_receipt'], 'install', scope_hash, source_hash)
    if digest(build['hap_sha256']) != digest(install.get('hap_sha256')) or not install.get('device_id'):
        raise ValueError('build and device installation do not bind the same HAP')
    if receipt.get('device_id') != install['device_id']:
        raise ValueError('arrival device does not match installation')
    return digest(build['hap_sha256']), install['device_id']


def _comparison(root, scope_pair, scope_frame, observed):
    source = scope_pair['baseline']
    checked_artifact(_project_file(root, source['png_path']), source['png_sha256'])
    checked_artifact(_project_file(root, source['ui_json_path']), source['ui_json_sha256'])
    if digest(observed['ios_png_sha256']) != digest(source['png_sha256']):
        raise ValueError('comparison does not bind current iOS image')
    if observed.get('ios_region_px') != scope_frame.get('ios_region_px'):
        raise ValueError('comparison does not bind the approved iOS region')
    _, image = _checked_ref(root, observed['harmony_png'])
    if not image.startswith((b'\x89PNG\r\n\x1a\n', b'\xff\xd8\xff')):
        raise ValueError('target screenshot is not PNG or JPEG')
    target_tree_path, tree_bytes = _checked_ref(root, observed['harmony_xml'])
    tree = _json_object(tree_bytes)
    if not tree.get('nodes') and not tree.get('children'):
        raise ValueError('target accessibility tree is empty')
    verdict = observed['verdict']
    appearance = _checked_json(root, observed['appearance_report'])
    relationship = _checked_json(root, observed['relationship_report'])
    common = {
        'comparison_id': scope_frame['comparison_id'], 'ios_png_sha256': source['png_sha256'],
        'harmony_png_sha256': observed['harmony_png']['sha256'],
    }
    for key, value in common.items():
        actual = appearance.get(key)
        if (digest(actual) if key.endswith('sha256') else actual) != (digest(value) if key.endswith('sha256') else value):
            raise ValueError(f'appearance report does not bind {key}')
    if relationship.get('comparison_id') != scope_frame['comparison_id']:
        raise ValueError('relationship report does not bind comparison')
    for field, expected in [('ios_ui_sha256', source['ui_json_sha256']),
                            ('harmony_ui_sha256', observed['harmony_xml']['sha256'])]:
        if digest(relationship.get(field)) != digest(expected):
            raise ValueError(f'relationship report does not bind {field}')
    calculated = compare_relationships(root, scope_pair, scope_frame, target_tree_path, observed['harmony_xml']['sha256'])
    if json_bytes(calculated) != json_bytes(relationship):
        raise ValueError('relationship report does not match native tree replay')
    evidence_verdicts = {appearance.get('verdict'), relationship.get('verdict')}
    if verdict == 'PASS' and evidence_verdicts == {'PASS'}:
        return verdict
    if verdict == 'FAIL' and 'FAIL' in evidence_verdicts and observed.get('severity') in {'critical', 'normal'}:
        return verdict
    raise ValueError('visual verdict lacks matching appearance and relationship evidence')


def _assess_pair(root, expected, row, scope_hash, source_hash):
    if not row:
        return {'pair_id': expected['pair_id'], 'verdict': 'NOT_RUN', 'reason': 'comparison pair is absent'}
    if row.get('arrival_mode') != expected['arrival_mode']:
        raise ValueError('arrival mode does not match approved scope')
    verdict = row.get('verdict')
    if verdict == 'BLOCKED':
        _checked_ref(root, row['evidence'])
        if not row.get('reason'):
            raise ValueError('blocked pair has no observed reason')
        return {'pair_id': expected['pair_id'], 'verdict': 'BLOCKED', 'reason': row['reason']}
    if verdict == 'FAIL' and row.get('arrival_failure'):
        failure = row['arrival_failure']
        _checked_ref(root, failure['evidence'])
        install = _receipt(root, failure['install_receipt'], 'install', scope_hash, source_hash)
        if not install.get('device_id') or not failure.get('summary') or row.get('severity') != 'critical':
            raise ValueError('arrival failure has no device, summary or critical verdict')
        return {'pair_id': expected['pair_id'], 'verdict': 'FAIL', 'severity': 'critical', 'reason': failure['summary']}
    if expected['baseline'].get('evidence_kind') != 'ios-accessibility-json':
        raise ValueError('approved iOS runtime baseline is unavailable')
    hap, device = _arrival(root, expected, row, scope_hash, source_hash)
    frames = _index(row['comparisons'], 'comparison_id')
    wanted = _index(expected['comparisons'], 'comparison_id')
    if frames.keys() != wanted.keys():
        raise ValueError('comparison coverage differs from approved scope')
    checked = [_comparison(root, expected, frame, frames[name]) for name, frame in wanted.items()]
    if not checked or verdict != ('FAIL' if 'FAIL' in checked else 'PASS'):
        raise ValueError('pair verdict does not match its comparisons')
    result = {'pair_id': expected['pair_id'], 'verdict': verdict, 'device_id': device, 'hap_sha256': hap}
    if verdict == 'FAIL':
        severity = 'critical' if any(frame.get('severity') == 'critical' for frame in frames.values()) else 'normal'
        if row.get('severity') != severity:
            raise ValueError('pair severity does not match failed comparisons')
        result['severity'] = severity
    return result


def assess_visual(root, scope_bytes, report_bytes):
    scope = _json_object(scope_bytes)
    report = _json_object(report_bytes)
    current = build_scope_from_inventory(root, None)
    if scope != current or scope.get('schema_version') != 2 or not scope.get('pairs'):
        raise ValueError('visual scope is stale or does not cover approved verification pairs')
    scope_hash = sha256(scope_bytes)
    if digest(report.get('scope_sha256')) != scope_hash:
        raise ValueError('comparison report belongs to a different scope')
    source_hash = current['source_sha256']
    approved = _index(current['pairs'], 'pair_id')
    actual = _index(report.get('pairs'), 'pair_id')
    if actual.keys() - approved.keys():
        raise ValueError('comparison report contains unexpected pair IDs')
    pairs = []
    for name, pair in approved.items():
        try:
            result = _assess_pair(root, pair, actual.get(name), scope_hash, source_hash)
        except (OSError, KeyError, TypeError, ValueError) as exc:
            result = {'pair_id': name, 'verdict': 'NOT_RUN', 'reason': str(exc)}
        pairs.append({**result, 'page_id': pair['page_id'], 'state_id': pair['state_id'],
                      'arrival_mode': pair['arrival_mode']})
    if source_hash != source_digest(root):
        raise ValueError('target source changed during visual acceptance')
    verdicts = {row['verdict'] for row in pairs}
    installations = {(row.get('hap_sha256'), row.get('device_id')) for row in pairs if row.get('hap_sha256')}
    consistent = len(installations) == 1
    ready = current['status'] == 'READY'
    return {
        'schema_version': 2, 'policy_gate': 'execute.stage1-visual', 'scope_sha256': scope_hash,
        'source_sha256': source_hash, 'report_sha256': sha256(report_bytes),
        'status': 'FAIL' if 'FAIL' in verdicts else 'PASS' if verdicts == {'PASS'} and consistent and ready else 'BLOCKED',
        'assessment_complete': 'NOT_RUN' not in verdicts and ready, 'stage1_complete': False,
        'required_pairs': len(approved), 'passed_pairs': sum(row['verdict'] == 'PASS' for row in pairs),
        'same_installation': consistent, 'pairs': pairs,
        'failure_findings': [*current['failure_findings'], *(row for row in pairs if row['verdict'] != 'PASS')],
    }


def archive_visual(root, scope_path, report_path):
    folder = dispatch_root(root)
    scope_bytes = scope_path.read_bytes()
    report_bytes = report_path.read_bytes()
    result = assess_visual(root, scope_bytes, report_bytes)
    raw = json_bytes(result)
    with locked(folder):
        parent = _project_file(folder, 'visual')
        parent.mkdir(exist_ok=True)
        archive = parent / sha256(raw)
        files = {'receipt.json': raw, 'scope.json': scope_bytes, 'comparison-report.json': report_bytes}
        if scope_path.read_bytes() != scope_bytes or report_path.read_bytes() != report_bytes:
            raise ValueError('visual inputs changed while archiving')
        existing = archive.exists()
        if existing:
            for name, content in files.items():
                checked_artifact(_project_file(archive, name), sha256(content))
        latest = _project_file(parent, f'latest/{result["scope_sha256"]}.json')
        publish_latest = not existing or not latest.exists()
        selected = publish_latest or _json_object(latest.read_bytes()).get('archive_id') == archive.name
        round_event = _visual_round(root, _json_object(scope_bytes), result, archive.name) if selected else None
        if publish_latest:
            latest.parent.mkdir(exist_ok=True)
            atomic_write(latest, json_bytes({'archive_id': archive.name, 'scope_sha256': result['scope_sha256']}))
        # Publish the selected identity first. A crash before the immutable directory
        # lands keeps summary blocked until the exact archive is retried.
        if not existing:
            save_directory(archive, files)
        if round_event:
            records, event = round_event
            append_event(folder, records, event)
    return {**result, 'archive_path': project_relative(root, archive)}


def _visual_round(root, scope, visual, archive_id):
    if visual['status'] == 'BLOCKED':
        return None
    folder = dispatch_root(root)
    records = events(folder)
    lane = acceptance_lane(scope)
    history = [row['result'] for row in records if row['event'] == 'stage1_visual' and row['lane'] == lane]
    if any(row['archive_id'] == archive_id for row in history):
        return None
    previous = history[-1] if history else None
    attempt = 0
    if previous:
        if previous['source_sha256'] == visual['source_sha256']:
            attempt = previous['attempt']
        elif previous['status'] == 'FAIL':
            attempt = previous['attempt'] + 1
            if attempt > MAX_REPAIRS:
                raise ValueError('visual repair budget exhausted for this approved scope')
    return records, {'event': 'stage1_visual', 'lane': lane, 'result': {
        'archive_id': archive_id, 'source_sha256': visual['source_sha256'], 'scope_sha256': visual['scope_sha256'],
        'status': visual['status'], 'attempt': attempt,
    }}
