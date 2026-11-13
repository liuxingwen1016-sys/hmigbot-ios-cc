"""Revalidate current iOS Stage-1 receipts without publishing new acceptance evidence."""
from __future__ import annotations

import json
import re

from .ios_stage1_acceptance import archive_g1
from .ios_stage1_progress import MAX_REPAIRS, latest_compile, latest_smoke, read_scope
from .ios_stage1_scope import acceptance_lane, build_scope_from_inventory
from .ios_stage1_visual_gate import assess_visual, checked_build
from .ios_ui_delivery_gate import _project_file
from .ios_ui_dispatch import checked_artifact, digest, dispatch_root, events, json_bytes, project_relative, sha256
from .stage1_contract import source_digest


DEFAULT_SCOPE = 'spec/execution/stage1-visual/scope.json'
ARCHIVE_ID = re.compile(r'[0-9a-f]{64}')
EVIDENCE_ERRORS = (OSError, ValueError, KeyError, TypeError, AttributeError)


def finding(code, detail, cause='information_gap'):
    return {'code': code, 'detail': detail, 'root_cause': cause}


def select_visual_archive(root, scope_bytes, report_path):
    folder = _project_file(dispatch_root(root), 'visual')
    selected_report = report_path.read_bytes() if report_path else None
    scope_hash = sha256(scope_bytes)
    latest_path = _project_file(folder, f'latest/{scope_hash}.json')
    if latest_path.is_file():
        pointer = latest_path.read_bytes()
        latest = json.loads(pointer)
        archive_id = latest['archive_id']
        if latest['scope_sha256'] != scope_hash or not ARCHIVE_ID.fullmatch(archive_id):
            raise ValueError('latest visual archive reference is invalid')
        archive = _project_file(folder, archive_id)
        checked_artifact(_project_file(archive, 'scope.json'), scope_hash)
        report = _project_file(archive, 'comparison-report.json').read_bytes()
        if selected_report is not None and report != selected_report:
            raise ValueError('--report does not match the latest visual archive for the current scope')
        return archive, report, (latest_path, sha256(pointer))
    candidates = []
    if folder.is_dir():
        for path in sorted(folder.iterdir()):
            if not path.is_dir() or not ARCHIVE_ID.fullmatch(path.name):
                continue
            archive = _project_file(folder, path.name)
            scope = _project_file(archive, 'scope.json')
            if not scope.is_file() or scope.read_bytes() != scope_bytes:
                continue
            report = _project_file(archive, 'comparison-report.json').read_bytes()
            if selected_report is None or report == selected_report:
                candidates.append((archive, report, None))
    if len(candidates) > 1:
        raise ValueError('multiple visual archives match this scope; select the intended comparison with --report')
    return candidates[0] if candidates else None


def read_visual(root, scope_bytes, report_path):
    selection = select_visual_archive(root, scope_bytes, report_path)
    if selection is None:
        return None, None, False
    archive, report_bytes, pointer = selection
    receipt = checked_artifact(_project_file(archive, 'receipt.json'), archive.name)
    current = assess_visual(root, scope_bytes, report_bytes)
    if json_bytes(current) != receipt:
        raise ValueError('archived visual receipt does not match replay of current evidence')
    if pointer is not None:
        checked_artifact(*pointer)
    report = json.loads(report_bytes)
    requires_smoke = any('carried_from_round' in pair for pair in report['pairs'])
    if report.get('carried') or report.get('accepted_differences'):
        requires_smoke = True
    return current, project_relative(root, archive), requires_smoke


def visual_round(root, scope, archive_path):
    if not archive_path:
        return None
    key = acceptance_lane(scope)
    name = archive_path.rsplit('/', 1)[-1]
    history = events(dispatch_root(root))
    return next((row['result'] for row in reversed(history) if row['event'] == 'stage1_visual'
                 and row['lane'] == key and row['result']['archive_id'] == name), None)


def summarize(root, scope_path, report_path=None, wiring_contract=None, build_path=None):
    before = source_digest(root)
    findings = []
    try:
        g1 = archive_g1(root, wiring_contract, read_only=True)
        findings.extend(g1['failure_findings'])
    except EVIDENCE_ERRORS as exc:
        g1 = {'status': 'BLOCKED', 'archive_path': None}
        findings.append(finding('g1_evidence_invalid', str(exc)))

    scope_hash = None
    visual, visual_archive, requires_smoke = None, None, False
    visual_status = 'NOT_RUN'
    round_receipt = None
    accepted = []
    required_pairs = []
    try:
        scope = build_scope_from_inventory(root, None)
        required_pairs = scope['pairs']
        if not scope_path.is_file():
            findings.append(finding('visual_scope_missing', 'freeze the approved iOS visual scope first'))
        else:
            scope_bytes = scope_path.read_bytes()
            if json.loads(scope_bytes) != scope or scope.get('schema_version') != 2 or not required_pairs:
                raise ValueError('STALE or incomplete iOS visual scope; freeze it again against the current project')
            scope_hash = sha256(scope_bytes)
            visual, visual_archive, requires_smoke = read_visual(root, scope_bytes, report_path)
            if visual is None:
                findings.append(finding('visual_archive_missing', 'archive the selected comparison report first'))
            else:
                visual_status = visual['status']
                findings.extend(visual['failure_findings'])
                round_receipt = visual_round(root, scope, visual_archive)
                if requires_smoke:
                    visual_status = 'BLOCKED'
                    findings.append(finding('visual_carry_unverified', 'iOS summary requires fresh evidence for each pair '
                                            'until carried visual rounds and their final smoke can be validated'))
                elif (round_receipt and round_receipt['attempt'] > 0 and visual['assessment_complete']
                      and visual['same_installation'] and visual_status == 'FAIL'
                      and all(row['verdict'] == 'PASS' or
                              (row['verdict'] == 'FAIL' and row.get('severity') == 'normal')
                              for row in visual['pairs'])):
                    accepted = [row['pair_id'] for row in visual['pairs'] if row['verdict'] == 'FAIL']
                    visual_status = 'PASS'
    except EVIDENCE_ERRORS as exc:
        visual_status = 'BLOCKED'
        findings.append(finding('visual_evidence_invalid', str(exc)))

    observed_haps = {row['hap_sha256'] for row in visual['pairs'] if row.get('hap_sha256')} if visual else set()
    hap_hash = next(iter(observed_haps)) if len(observed_haps) == 1 else None
    build_status = 'PASS' if hap_hash else 'NOT_RUN'
    build_reference = None
    if build_path is not None:
        try:
            if not scope_hash or not build_path.is_relative_to(root / 'spec'):
                raise ValueError('build receipt requires the current scope and a path inside spec')
            build_reference = {'path': build_path.relative_to(root / 'spec').as_posix(),
                               'sha256': sha256(build_path.read_bytes())}
            build = checked_build(root, build_reference, scope_hash, before)
            hap_hash = digest(build['hap_sha256'])
            if observed_haps - {hap_hash}:
                raise ValueError('explicit build and archived visual checks use different HAPs')
            build_status = 'PASS'
        except EVIDENCE_ERRORS as exc:
            build_status = 'BLOCKED'
            hap_hash, build_reference = None, None
            findings.append(finding('build_evidence_invalid', str(exc)))
    compile_receipt = None
    smoke = None
    if scope_hash is not None:
        try:
            compile_receipt = latest_compile(root, scope, scope_hash)
            if compile_receipt:
                if not compile_receipt['current'] or compile_receipt['status'] != 'PASS':
                    build_status = compile_receipt['status'] if compile_receipt['current'] else 'STALE'
                    hap_hash, build_reference = None, None
                    findings.append(finding('recorded_compile_not_passed', 'register a current passing compile'))
                elif observed_haps - {compile_receipt['hap_sha256']} or hap_hash not in {None, compile_receipt['hap_sha256']}:
                    raise ValueError('archived visual, explicit build and recorded compile must use one HAP')
                elif build_status != 'BLOCKED':
                    build_status = 'PASS'
                    hap_hash = compile_receipt['hap_sha256']
                    build_reference = compile_receipt['build_receipt']
        except EVIDENCE_ERRORS as exc:
            build_status = 'BLOCKED'
            hap_hash, build_reference = None, None
            findings.append(finding('compile_evidence_invalid', str(exc)))
        if build_status == 'PASS':
            try:
                smoke = latest_smoke(root, scope, scope_hash, hap_hash)
                devices = {row['device_id'] for row in visual['pairs'] if row.get('device_id')} if visual else set()
                if smoke and devices - {smoke['device_id']}:
                    raise ValueError('visual and final smoke used different devices')
            except EVIDENCE_ERRORS as exc:
                smoke = None
                findings.append(finding('smoke_evidence_invalid', str(exc)))
    if not compile_receipt and build_path is None and not hap_hash:
        code = 'build_identity_mismatch' if observed_haps else 'build_evidence_missing'
        findings.append(finding(code, 'one current build and its HAP must bind the selected visual evidence'))
        if observed_haps:
            build_status = 'BLOCKED'

    if before != source_digest(root) or (scope_hash is not None and scope_hash != sha256(scope_path.read_bytes())):
        raise ValueError('target source or scope changed during Stage-1 summary')
    assessed = bool(visual and visual['assessment_complete']) and not requires_smoke
    complete = (g1['status'] == build_status == visual_status == 'PASS') and assessed
    phase = 'pending'
    if g1['status'] == 'PASS':
        phase = 'complete' if complete else 'assessed' if assessed else 'assembled'
    pairs = visual['pairs'] if visual else [
        {key: pair[key] for key in ('pair_id', 'page_id', 'state_id', 'arrival_mode')} | {'verdict': 'NOT_RUN'}
        for pair in required_pairs
    ]
    return {
        'schema_version': 2, 'policy_gate': 'execute.stage1-summary',
        'status': 'PASS' if complete else 'FAIL' if 'FAIL' in (visual_status, build_status) else 'BLOCKED',
        'phase': phase, 'stage1_complete': complete, 'assessment_complete': assessed,
        'structural': g1['status'], 'build': build_status, 'visual': visual_status,
        'raw_visual': visual['status'] if visual else visual_status, 'visual_round': round_receipt,
        'accepted_differences': accepted,
        'smoke': 'PASS' if smoke else 'NOT_RUN' if requires_smoke or visual is None else 'NOT_REQUIRED',
        'smoke_required': requires_smoke, 'smoke_receipt': smoke, 'compile_receipt': compile_receipt,
        'source_sha256': before, 'scope_sha256': scope_hash, 'hap_sha256': hap_hash,
        'g1_archive_path': g1['archive_path'], 'visual_archive_path': visual_archive, 'build_receipt': build_reference,
        'required_units': g1.get('required_units'), 'required_pairs': len(required_pairs),
        'passed_pairs': sum(row['verdict'] == 'PASS' for row in pairs), 'pairs': pairs,
        'failure_findings': findings,
    }


def next_step(root, scope_path, report_path=None, wiring_contract=None, build_path=None):
    summary = summarize(root, scope_path, report_path, wiring_contract, build_path)
    pending = [pair['pair_id'] for pair in summary['pairs'] if pair['verdict'] == 'NOT_RUN']
    blocked = [pair['pair_id'] for pair in summary['pairs'] if pair['verdict'] == 'BLOCKED']
    attempt = summary['visual_round']['attempt'] if summary['visual_round'] else 0
    failed = [pair for pair in summary['pairs'] if pair['verdict'] == 'FAIL']
    repairable = [pair for pair in failed if not attempt or pair.get('severity') == 'critical']
    compile_receipt = summary['compile_receipt']
    repairs = []
    repair_scope = None
    if summary['stage1_complete']:
        action = 'complete'
    elif summary['structural'] != 'PASS':
        action = 'archive_g1' if summary['structural'] == 'NOT_RUN' else 'repair_g1'
    elif summary['scope_sha256'] is None:
        action = 'freeze_visual_scope'
    elif compile_receipt and compile_receipt['raw_status'] == 'FAIL' and compile_receipt['attempt'] >= MAX_REPAIRS:
        action = 'stop_with_compile_defects'
    elif summary['build'] == 'REPAIR_REQUIRED':
        action = 'repair_compile'
    elif summary['build'] == 'BLOCKED':
        action = 'resolve_build_blocker'
    elif summary['build'] != 'PASS':
        action = 'build_current_hap'
    elif summary['smoke_required']:
        action = 'run_final_smoke_on_current_hap' if summary['smoke'] != 'PASS' else 'resolve_visual_provenance'
    elif repairable:
        action = 'stop_with_visual_defects' if attempt >= MAX_REPAIRS else 'repair_visual'
        repair_scope = 'critical_only' if attempt else 'critical_and_normal'
        scope, _ = read_scope(root, scope_path)
        failed_ids = {pair['pair_id'] for pair in repairable}
        repairs = sorted({unit for pair in scope['pairs'] if pair['pair_id'] in failed_ids
                          for unit in pair['implementation_units']})
    elif pending:
        action = 'capture_or_review_pending_pairs'
    else:
        action = 'resolve_visual_blockers'
    return {**summary, 'policy_gate': 'execute.stage1-next', 'next_action': action,
            'repair_scope': repair_scope, 'repair_units': repairs, 'failed_pairs': failed,
            'pending_pairs': pending, 'blocked_pairs': blocked}
