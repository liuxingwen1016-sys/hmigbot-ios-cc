"""Stage 1 visual acceptance summary.

This module is intentionally deterministic and has no model or network dependency.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .stage1_visual_acceptance import accept, report as acceptance_report
from .ios_stage1_scope import build_scope_from_inventory
from .ios_stage1_visual_gate import (
    _arrival, _checked_json, _checked_ref, _comparison, _index, conflicting_state_pairs, shared_capture_groups,
)
from .ios_ui_delivery_gate import _project_file
from .ios_ui_dispatch import atomic_write, digest, sha256
from .stage1_contract import source_digest
from .visual_review_reuse import FLASH_RECHECK_MODELS, attempted_labeled_rechecks, labeled_recheck_ids


def reference(root, value):
    if isinstance(value, dict):
        _checked_ref(root, value)
        return value
    path = _project_file(root / 'spec', value)
    raw = path.read_bytes()
    if not raw:
        raise ValueError(f'empty evidence: {path}')
    return {'path': path.relative_to(root / 'spec').as_posix(), 'sha256': sha256(raw)}


def preflight_capture(root, scope_path, scope, capture, *, bound=False, expected_hap=None):
    """Prepare the approved comparisons before a model is asked to judge them."""
    scope_hash = sha256(scope_path.read_bytes())
    source_hash = scope['source_sha256']
    if scope.get('status') not in {'READY', 'BLOCKED'} or digest(source_hash) != digest(source_digest(root)):
        return {}, {pair['pair_id']: 'approved visual scope is invalid or target source has changed'
                    for pair in scope['pairs']}, []
    if any(finding.get('code') in {'visual_pair_unbound', 'visual_pair_missing'}
           for finding in scope.get('failure_findings', [])):
        return {}, {pair['pair_id']: 'approved visual pair mapping is incomplete'
                    for pair in scope['pairs']}, []
    rows, gaps, installations = {}, {}, set()
    for pair in scope['pairs']:
        name = pair['pair_id']
        try:
            baseline = pair['baseline']
            if baseline.get('evidence_kind') != 'ios-accessibility-json':
                reason = baseline.get('reason', 'approved iOS runtime baseline is unavailable')
                raise ValueError(f'source baseline blocked: {reason}')
            if name not in capture:
                raise ValueError('capture missing for approved pair')
            captured = capture[name]
            if captured.get('blocked') or captured.get('arrival_failure'):
                raise ValueError('pair did not arrive at the approved state')
            if 'frames' not in captured:
                raise ValueError('formal comparison frames missing; diagnostic captures require a native arrival receipt and bound frames')
            for field in ('png', 'ui_json'):
                source = _project_file(root, baseline[f'{field}_path'])
                if sha256(source.read_bytes()) != digest(baseline[f'{field}_sha256']):
                    raise ValueError(f'approved iOS {field} SHA-256 mismatch')
            observed = _index(captured['frames'], 'comparison_id')
            if observed.keys() != {frame['comparison_id'] for frame in pair['comparisons']}:
                raise ValueError('captured comparison IDs differ from the frozen pair')
            arrival = reference(root, captured['arrival_receipt'])
            identity = _arrival(root, pair, {'arrival_receipt': arrival}, scope_hash, source_hash)
            if expected_hap is not None and identity[0] != expected_hap:
                raise ValueError('capture HAP differs from the verified application package')
            receipt = _checked_json(root, arrival)
            if bound or 'frames' in receipt:
                if 'frames' not in receipt:
                    raise ValueError('native arrival receipt is missing bound frames')
                if _index(receipt['frames'], 'comparison_id') != observed:
                    raise ValueError('capture frames differ from the native arrival receipt')
            frames = []
            for frame in observed.values():
                if bound and any(not isinstance(frame.get(key), dict) for key in ('harmony_png', 'harmony_xml')):
                    raise ValueError('native arrival must bind image and control tree SHA-256')
                image = reference(root, frame['harmony_png'])
                tree = reference(root, frame['harmony_xml'])
                _, image_bytes = _checked_ref(root, image)
                if not image_bytes.startswith((b'\x89PNG\r\n\x1a\n', b'\xff\xd8\xff')):
                    raise ValueError('target screenshot is not PNG or JPEG')
                nodes = _checked_json(root, tree)
                if not nodes.get('nodes') and not nodes.get('children'):
                    raise ValueError('target accessibility tree is empty')
                frames.append({**frame, 'harmony_png': image, 'harmony_xml': tree})
            rows[name] = {'pair_id': name, 'arrival_receipt': arrival, 'frames': frames}
            installations.add(identity)
        except (OSError, TypeError, KeyError, ValueError) as exc:
            gaps[name] = str(exc)
    if len(installations) > 1:
        for name in rows:
            gaps[name] = 'captured pairs use different HAPs or devices'
        rows.clear()
    groups = shared_capture_groups({pair['pair_id']: pair for pair in scope['pairs']}, rows)
    for name in sorted(conflicting_state_pairs(groups)):
        gaps[name] = 'distinct states of the same page with different source evidence share one target image and tree'
        del rows[name]
    return rows, gaps, groups


def capture_index(root, scope_path, arrival_paths, *, base_index=None, expected_hap=None):
    scope = _read(scope_path)
    if scope != build_scope_from_inventory(root, None):
        raise ValueError('visual scope is stale or differs from the approved inventory')
    approved = _index(scope.get('pairs'), 'pair_id')
    rows = []
    for path in arrival_paths:
        arrival = reference(root, path)
        receipt = _checked_json(root, arrival)
        row = {'pair_id': receipt['pair_id'], 'arrival_receipt': arrival}
        if 'frames' in receipt:
            row['frames'] = receipt['frames']
        rows.append(row)
    capture = _index(rows, 'pair_id')
    if base_index is not None:
        prior = _read(base_index)
        if (prior.get('capture_contract') != 'native-arrival-v1'
                or prior.get('scope_sha256') != sha256(scope_path.read_bytes())
                or prior.get('status') not in {'READY', 'BLOCKED'}):
            raise ValueError('base capture index must match the current approved scope')
        original = _index(prior.get('pairs'), 'pair_id')
        prior_gaps = _index(prior.get('capture_gaps', []), 'pair_id')
        if (not original or original.keys() & prior_gaps.keys()
                or original.keys() | prior_gaps.keys() != approved.keys()
                or (prior.get('status') == 'READY') != (scope['status'] == 'READY' and not prior_gaps)):
            raise ValueError('base capture index must account for the complete approved scope')
        if prior.get('expected_hap_sha256') is not None:
            prior_hap = digest(prior['expected_hap_sha256'])
            if expected_hap is not None and digest(expected_hap) != prior_hap:
                raise ValueError('expected HAP differs from the base capture package')
            expected_hap = prior_hap
        # Revalidate the baseline installation even if every pair is replaced.
        scope_hash = sha256(scope_path.read_bytes())
        source_hash = scope['source_sha256']
        first = next(iter(original))
        baseline_identity = _arrival(root, approved[first], original[first], scope_hash, source_hash)
        for name, row in capture.items():
            if name not in approved:
                raise ValueError('replacement arrival is outside the approved visual scope')
            try:
                replacement_identity = _arrival(root, approved[name], row, scope_hash, source_hash)
            except (OSError, TypeError, KeyError, ValueError):
                continue  # Normal preflight emits the affected pair's evidence diagnostic.
            if replacement_identity != baseline_identity:
                raise ValueError('replacement arrival must use the base capture HAP and device')
        capture = {**original, **capture}
    if not approved or capture.keys() - approved.keys():
        raise ValueError('arrival IDs fall outside the approved visual scope')
    expected_hap = digest(expected_hap) if expected_hap is not None else None
    rows, gaps, groups = preflight_capture(root, scope_path, scope, capture, bound=True, expected_hap=expected_hap)
    return {'schema_version': 2, 'capture_contract': 'native-arrival-v1',
            'scope_sha256': sha256(scope_path.read_bytes()),
            **({'expected_hap_sha256': expected_hap} if expected_hap is not None else {}),
            'status': 'READY' if scope['status'] == 'READY' and not gaps else 'BLOCKED',
            'required_pairs': len(approved), 'pairs': list(rows.values()),
            'shared_capture_groups': groups,
            'capture_gaps': [{'pair_id': name, 'page_id': approved[name]['page_id'],
                              'state_id': approved[name]['state_id'], 'reason': reason}
                             for name, reason in gaps.items()]}


def _read(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    return json.loads(Path(value).read_text(encoding='utf-8'))


def _scope_rows(scope: dict) -> list[dict]:
    return [
        page
        for unit in scope.get('units', [])
        for page in unit.get('pages', [])
        if isinstance(page, dict)
    ]


def _device_rows(cases: list[dict] | None) -> list[dict]:
    rows = []
    for case in cases or []:
        target = case.get('target') or case.get('harmony') or case.get('execute') or {}
        if isinstance(target, dict):
            row = target.get('device_validation') or target.get('device') or {}
            if isinstance(row, dict):
                rows.append(row)
    return rows


def summarize(scope: dict | str | Path, cases: list[dict] | None = None, *, geometry_tolerance: float = 4.0) -> dict:
    scope_data = _read(scope)
    pages = _scope_rows(scope_data)
    expected = {(page.get('page_id'), page.get('state_id')) for page in pages}
    results = acceptance_report(cases or [], geometry_tolerance=geometry_tolerance) if cases is not None else {'results': []}
    observed = {(row.get('page_id'), row.get('state_id')) for row in results.get('results', [])}
    device_rows = _device_rows(cases)
    selected = next((row for row in device_rows if row.get('device_type')), {})
    return {
        'schema_version': 1,
        'status': results.get('status', 'CAPTURE_PENDING') if cases is not None else 'CAPTURE_PENDING',
        'page_count': len({page.get('page_id') for page in pages}),
        'state_count': len(expected),
        'expected_page_states': sorted(f'{page}/{state}' for page, state in expected),
        'observed_page_states': sorted(f'{page}/{state}' for page, state in observed),
        'coverage': round(len(expected & observed) / len(expected), 4) if expected else 0.0,
        'evidence_completeness': results.get('evidence_completeness', 0.0),
        'semantic_coverage': results.get('semantic_coverage', 0.0),
        'geometry_max_error': results.get('geometry_max_error', 0.0),
        'device_validation': {
            'ios_baseline': {
                'device': 'iPhone',
                'role': 'ios_runtime_baseline',
                'device_type': 'real_device',
                'serial': None,
                'system_version': None,
                'evidence_hashes': {},
                'status': 'PENDING_P0_RUNTIME_CAPTURE',
                'blocked_reasons': ['iOS PNG/accessibility JSON not yet captured']
                if cases is None else [],
            },
            'harmony_target': {
                'device': 'Huawei Mate 80 Pro',
                'role': 'harmony_install_screenshot_interaction',
                'preferred_device_type': 'real_device',
                'fallback_device_type': 'emulator',
                'selected_device_type': selected.get('device_type'),
                'serial': selected.get('serial') or selected.get('device_id'),
                'system_version': selected.get('system_version'),
                'evidence_hashes': selected.get('evidence_hashes', {}),
                'status': selected.get('status', 'PENDING_P0_RUNTIME_CAPTURE'),
                'blocked_reasons': ['awaiting iOS baseline and Harmony package evidence']
                if cases is None else [],
            },
        },
        'visual_blocked_reasons': results.get('visual_blocked_reasons', []),
        'results': results.get('results', []),
    }


def _review_rechecks(root, pending, review_inputs, receipts):
    """Annotate eligible work without treating raw attempts as accepted judgments."""
    sources = []
    rejected = []
    for receipt_path, report in receipts:
        try:
            receipt = _read(receipt_path)
            if not isinstance(receipt, dict):
                raise ValueError('expected an appearance review receipt object')
            if sha256(report.read_bytes()) != digest(receipt.get('report_sha256')):
                raise ValueError('review report SHA-256 mismatch')
            sources.append((receipt_path, receipt, report))
        except (OSError, TypeError, ValueError) as exc:
            rejected.append({'path': str(receipt_path.relative_to(root)), 'reason': str(exc)})

    current = {row['comparison_id']: review_inputs[row['comparison_id']] for row in pending
               if row['reason'] == 'no_matching_verified_review'}
    original = {name: {**binding, 'source_context_sha256': []} for name, binding in current.items()}
    parent_groups = labeled_recheck_ids(sources, original, FLASH_RECHECK_MODELS)
    attempts = attempted_labeled_rechecks(sources, current)
    for row in pending:
        name = row['comparison_id']
        if name in parent_groups:
            row['labeled_recheck'] = {'status': 'ATTEMPTED' if name in attempts else 'READY',
                                     'recovery_for': parent_groups[name]}
    return rejected


def review_worklist(root, scope_path, capture_path, prior_paths=(), *, review_inputs=None, receipts=()):
    """Plan reviews against the current captures and explicitly supplied prior reports."""
    if review_inputs is not None and not isinstance(review_inputs, dict):
        raise ValueError('current review inputs must be keyed by comparison ID')
    scope = _read(scope_path)
    if scope != build_scope_from_inventory(root, None):
        raise ValueError('visual scope is stale or differs from the approved inventory')
    scope_hash = sha256(scope_path.read_bytes())
    capture = _read(capture_path)
    if capture.get('capture_contract') != 'native-arrival-v1' or capture.get('scope_sha256') != scope_hash:
        raise ValueError('review worklist requires a native capture index for the current approved scope')
    approved = _index(scope.get('pairs'), 'pair_id')
    captured = _index(capture.get('pairs'), 'pair_id')
    if not approved or captured.keys() - approved.keys():
        raise ValueError('capture IDs fall outside the approved visual scope')
    expected_hap = capture.get('expected_hap_sha256')
    ready, gaps, _ = preflight_capture(root, scope_path, scope, captured, bound=True,
                                       expected_hap=digest(expected_hap) if expected_hap is not None else None)

    candidates = {}
    rejected_reports = []
    for path in prior_paths:
        try:
            report = _read(path)
            if report.get('schema_version') != 2 or report.get('status') not in ('ASSEMBLED', 'BLOCKED'):
                raise ValueError('expected a Stage 1 assembled visual report')
            completed = [frame for pair in _index(report.get('pairs'), 'pair_id').values()
                         for frame in pair.get('comparisons', [])]
            partial = report.get('partial_comparisons', [])
            if not isinstance(partial, list) or (partial and report['status'] != 'BLOCKED'):
                raise ValueError('partial comparisons require a blocked assembly')
            comparisons = _index([*completed, *partial], 'comparison_id')
            for name, frame in comparisons.items():
                candidates.setdefault(name, []).append(frame)
        except (AttributeError, OSError, TypeError, KeyError, ValueError) as exc:
            rejected_reports.append({'path': str(path), 'reason': str(exc)})

    reused, pending = [], []
    for pair_id, pair in approved.items():
        baseline = pair['baseline']
        observed = _index(ready[pair_id]['frames'], 'comparison_id') if pair_id in ready else {}
        for frame in pair['comparisons']:
            name = frame['comparison_id']
            item = {'pair_id': pair_id, 'comparison_id': name}
            if name not in observed:
                pending.append({**item, 'reason': 'capture_blocked', 'detail': gaps[pair_id]})
                continue
            current = observed[name]
            binding = (review_inputs or {}).get(name)
            if not isinstance(binding, dict) or not binding.get('rule_version'):
                pending.append({**item, 'reason': 'current_review_inputs_missing'})
                continue
            if (binding.get('ios_sha256') != digest(baseline['png_sha256'])
                    or binding.get('harmony_sha256') != digest(current['harmony_png']['sha256'])
                    or binding.get('control_tree_sha256') not in (
                        [], [digest(baseline['ui_json_sha256']), digest(current['harmony_xml']['sha256'])])
                    or binding.get('ios_region_px') != frame.get('ios_region_px')
                    or not isinstance(binding.get('source_context_sha256'), list)):
                pending.append({**item, 'reason': 'current_review_inputs_differ_from_capture'})
                continue
            accepted = {}
            for prior in candidates.get(name, []):
                try:
                    appearance = _checked_json(root, prior['appearance_report'])
                    receipt = _checked_json(root, appearance['review_receipt'])
                    if receipt['review_inputs'][name] != binding:
                        continue
                    # Reuse the strict verifier on the fresh frame and existing evidence.
                    result = {**prior, 'harmony_png': current['harmony_png'], 'harmony_xml': current['harmony_xml']}
                    verdict = _comparison(root, pair, frame, result)
                    severity = result['severity'] if verdict == 'FAIL' else None
                    judgement = {'comparison_id': name, 'verdict': verdict,
                                 'appearance_report': result['appearance_report'],
                                 'relationship_report': result['relationship_report']}
                    if severity:
                        judgement['severity'] = severity
                    accepted.setdefault((verdict, severity), judgement)
                except (AttributeError, OSError, TypeError, KeyError, ValueError):
                    continue
            if len(accepted) == 1:
                reused.append(next(iter(accepted.values())))
            else:
                pending.append({**item, 'reason': 'conflicting_reviews' if accepted else 'no_matching_verified_review'})
    rejected_receipts = _review_rechecks(root, pending, review_inputs, receipts) if receipts else []
    return {'schema_version': 1, 'status': 'READY' if scope['status'] == 'READY' and not gaps else 'BLOCKED',
            'scope_sha256': scope_hash,
            'required_comparisons': len(reused) + len(pending),
            'reviewable_comparisons': sum(len(row['frames']) for row in ready.values()), 'comparisons': reused,
            'pending': pending, 'rejected_prior_reports': rejected_reports,
            **({'rejected_review_receipts': rejected_receipts} if receipts else {})}


def assemble(root, scope_path, capture_path, judgement_paths):
    scope = _read(scope_path)
    approved = _index(scope.get('pairs'), 'pair_id')
    payload = _read(capture_path)
    scope_hash = sha256(scope_path.read_bytes())
    if 'scope_sha256' in payload and digest(payload['scope_sha256']) != scope_hash:
        raise ValueError('capture index belongs to a different approved scope')
    capture = _index(payload.get('pairs'), 'pair_id')
    judgements = _index([row for file in judgement_paths for row in _read(file).get('comparisons', [])],
                        'comparison_id')
    frames_in_scope = {frame['comparison_id'] for pair in approved.values() for frame in pair['comparisons']}
    if not approved or capture.keys() - approved.keys() or judgements.keys() - frames_in_scope:
        raise ValueError('capture or judgement IDs fall outside the approved visual scope')

    expected_hap = payload.get('expected_hap_sha256')
    ready, capture_gaps, groups = preflight_capture(
        root, scope_path, scope, capture, bound=payload.get('capture_contract') == 'native-arrival-v1',
        expected_hap=digest(expected_hap) if expected_hap is not None else None)

    rows = []
    gaps = []
    partial_comparisons = []
    for name, pair in approved.items():
        entry = {'pair_id': name, 'arrival_mode': pair['arrival_mode']}
        try:
            if name not in capture:
                raise ValueError(capture_gaps[name])
            captured = capture[name]
            if captured.get('blocked'):
                blocked = captured['blocked']
                entry.update(verdict='BLOCKED', reason=blocked['reason'], evidence=reference(root, blocked['evidence']))
            elif captured.get('arrival_failure'):
                failure = captured['arrival_failure']
                entry.update(verdict='FAIL', severity='critical', arrival_failure={
                    'evidence': reference(root, failure['evidence']),
                    'install_receipt': reference(root, failure['install_receipt']),
                    'summary': failure['summary'],
                })
            else:
                if name in capture_gaps:
                    raise ValueError(capture_gaps[name])
                observed = _index(ready[name]['frames'], 'comparison_id')
                comparisons = []
                pair_gaps = []
                for expected in pair['comparisons']:
                    key = expected['comparison_id']
                    try:
                        image = observed[key]
                        if key not in judgements:
                            raise ValueError(f'appearance and relationship judgement missing for {key}')
                        judgement = judgements[key]
                        if judgement['verdict'] not in {'PASS', 'FAIL'}:
                            raise ValueError(f'comparison {key} has no resolved visual verdict')
                        result = {
                            'comparison_id': key, 'ios_png_sha256': pair['baseline']['png_sha256'],
                            'ios_region_px': expected.get('ios_region_px'), 'verdict': judgement['verdict'],
                            'harmony_png': image['harmony_png'], 'harmony_xml': image['harmony_xml'],
                            'appearance_report': reference(root, judgement['appearance_report']),
                            'relationship_report': reference(root, judgement['relationship_report']),
                        }
                        if result['verdict'] == 'FAIL':
                            result['severity'] = judgement['severity']
                    except (OSError, TypeError, KeyError, ValueError) as exc:
                        pair_gaps.append({'pair_id': name, 'comparison_id': key, 'reason': str(exc)})
                        continue
                    comparisons.append(result)
                if pair_gaps:
                    gaps.extend(pair_gaps)
                    partial_comparisons.extend(comparisons)
                    continue
                failed = [row for row in comparisons if row['verdict'] == 'FAIL']
                entry.update(verdict='FAIL' if failed else 'PASS', comparisons=comparisons,
                             arrival_receipt=ready[name]['arrival_receipt'])
                if failed:
                    entry['severity'] = 'critical' if any(row['severity'] == 'critical' for row in failed) else 'normal'
        except (OSError, TypeError, KeyError, ValueError) as exc:
            gaps.append({'pair_id': name, 'reason': str(exc)})
            continue
        rows.append(entry)
    report = {
        'schema_version': 2, 'status': 'ASSEMBLED' if scope['status'] == 'READY' and not gaps else 'BLOCKED',
        'scope_sha256': scope_hash, 'pairs': rows, 'assembly_gaps': gaps,
        'shared_capture_groups': groups,
    }
    if partial_comparisons:
        report['partial_comparisons'] = partial_comparisons
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('command', nargs='?', default='summary',
                        choices=('summary', 'assemble', 'affected', 'capture-index', 'review-worklist'))
    parser.add_argument('--scope', required=True)
    parser.add_argument('--cases')
    parser.add_argument('--capture')
    parser.add_argument('--base-capture', help='current capture index to update with explicit arrivals on the same installation')
    parser.add_argument('--expected-hap-sha256', help='require capture to use the verified signed application package')
    parser.add_argument('--arrival', action='append', help='native arrival receipt path relative to spec/')
    parser.add_argument('--judgements', nargs='*')
    parser.add_argument('--prior-report', action='append', help='previous assembled visual report')
    parser.add_argument('--review-receipt', action='append', help='appearance-group .receipt.json for targeted follow-up')
    parser.add_argument('--review-inputs', help='current appearance review bindings keyed by comparison ID')
    parser.add_argument('--project-root')
    parser.add_argument('--carry-from')
    parser.add_argument('--out')
    parser.add_argument('--geometry-tolerance', type=float, default=4.0)
    args = parser.parse_args(argv)
    root = Path(args.project_root).resolve() if args.project_root else None
    scope_path = _project_file(root, args.scope) if root else Path(args.scope)
    if args.base_capture and args.command != 'capture-index':
        parser.error('--base-capture requires capture-index')
    if args.expected_hap_sha256 and args.command != 'capture-index':
        parser.error('--expected-hap-sha256 requires capture-index')
    if (args.prior_report or args.review_inputs or args.review_receipt) and args.command != 'review-worklist':
        parser.error('--prior-report, --review-receipt and --review-inputs require review-worklist')
    if args.command == 'review-worklist':
        if not root or not args.capture:
            parser.error('review-worklist requires --project-root and --capture')
        if (args.prior_report or args.review_receipt) and not args.review_inputs:
            parser.error('--prior-report and --review-receipt require current --review-inputs')
        try:
            capture_path = _project_file(root, args.capture)
            prior_paths = [_project_file(root, path) for path in args.prior_report or []]
            binding_path = _project_file(root, args.review_inputs) if args.review_inputs else None
            output = _project_file(root, args.out) if args.out else None
            receipts = []
            for path in args.review_receipt or []:
                receipt = _project_file(root, path)
                suffix = '.receipt.json'
                if not receipt.name.endswith(suffix):
                    raise ValueError('expected a .receipt.json file with its adjacent appearance report')
                report = _project_file(root, str(receipt.with_name(receipt.name.removesuffix(suffix) + '.json')))
                receipts.append((receipt, report))
            if output is not None and (output in {scope_path, capture_path, binding_path, *prior_paths}
                                       or any(output in pair for pair in receipts)):
                raise ValueError('write the worklist to a new file')
            result = review_worklist(root, scope_path, capture_path, prior_paths,
                                     review_inputs=_read(binding_path) if binding_path else None, receipts=receipts)
            encoded = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
            if output is not None:
                output.parent.mkdir(parents=True, exist_ok=True)
                atomic_write(output, encoded.encode('utf-8'))
            else:
                print(encoded, end='')
            return 0 if result['status'] == 'READY' else 2
        except (OSError, TypeError, KeyError, ValueError) as exc:
            print(json.dumps({'status': 'BLOCKED', 'error': str(exc)}, ensure_ascii=False))
            return 2
    if args.command == 'capture-index':
        if not root or not args.arrival:
            parser.error('capture-index requires --project-root and at least one --arrival')
        try:
            base = _project_file(root, args.base_capture) if args.base_capture else None
            output = _project_file(root, args.out) if args.out else None
            if base is not None and base == output:
                raise ValueError('write the updated capture index to a new file')
            result = capture_index(root, scope_path, args.arrival, base_index=base,
                                   expected_hap=args.expected_hap_sha256)
            encoded = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
            if output is not None:
                output.parent.mkdir(parents=True, exist_ok=True)
                atomic_write(output, encoded.encode('utf-8'))
            else:
                print(encoded, end='')
            return 0 if result['status'] == 'READY' else 2
        except (OSError, TypeError, KeyError, ValueError) as exc:
            print(json.dumps({'status': 'BLOCKED', 'error': str(exc)}, ensure_ascii=False))
            return 2
    if args.command == 'assemble' and root and _read(scope_path).get('schema_version') == 2:
        if args.carry_from:
            parser.error('iOS comparison reuse requires a separately validated repair round')
        if not args.capture:
            parser.error('assemble requires --capture')
        try:
            result = assemble(root, scope_path, _project_file(root, args.capture),
                              [_project_file(root, path) for path in args.judgements or []])
        except (OSError, TypeError, KeyError, ValueError) as exc:
            print(json.dumps({'status': 'BLOCKED', 'error': str(exc)}, ensure_ascii=False))
            return 2
        encoded = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
        if args.out:
            output = _project_file(root, args.out)
            output.parent.mkdir(parents=True, exist_ok=True)
            atomic_write(output, encoded.encode('utf-8'))
        else:
            print(encoded, end='')
        return 0 if result['status'] == 'ASSEMBLED' else 2
    cases = None
    if args.cases:
        payload = _read(args.cases)
        cases = payload.get('cases', []) if isinstance(payload, dict) else payload
    elif args.capture:
        # Capture/judgement assembly is owned by the bundled command. The
        # Python fallback still emits a truthful scope summary until those
        # artifacts are supplied in the compact `cases` schema.
        cases = []
    result = summarize(args.scope, cases, geometry_tolerance=args.geometry_tolerance)
    encoded = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(encoded, encoding='utf-8')
    else:
        print(encoded)
    return 0 if result['status'] in ('PASS', 'CAPTURE_PENDING') else 2
