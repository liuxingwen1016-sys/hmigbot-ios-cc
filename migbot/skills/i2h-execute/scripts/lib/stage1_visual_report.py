"""Stage 1 visual acceptance summary.

This module is intentionally deterministic and has no model or network dependency.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .stage1_visual_acceptance import accept, report as acceptance_report
from .ios_stage1_visual_gate import _checked_ref, _index
from .ios_ui_delivery_gate import _project_file
from .ios_ui_dispatch import atomic_write, sha256


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


def assemble(root, scope_path, capture_path, judgement_paths):
    scope = _read(scope_path)
    approved = _index(scope.get('pairs'), 'pair_id')
    capture = _index(_read(capture_path).get('pairs'), 'pair_id')
    judgements = _index([row for file in judgement_paths for row in _read(file).get('comparisons', [])],
                        'comparison_id')
    frames_in_scope = {frame['comparison_id'] for pair in approved.values() for frame in pair['comparisons']}
    if not approved or capture.keys() - approved.keys() or judgements.keys() - frames_in_scope:
        raise ValueError('capture or judgement IDs fall outside the approved visual scope')

    def reference(value):
        if isinstance(value, dict):
            _checked_ref(root, value)
            return value
        path = _project_file(root / 'spec', value)
        raw = path.read_bytes()
        if not raw:
            raise ValueError(f'empty evidence: {path}')
        return {'path': path.relative_to(root / 'spec').as_posix(), 'sha256': sha256(raw)}

    rows = []
    gaps = []
    for name, pair in approved.items():
        entry = {'pair_id': name, 'arrival_mode': pair['arrival_mode']}
        try:
            captured = capture[name]
            if captured.get('blocked'):
                blocked = captured['blocked']
                entry.update(verdict='BLOCKED', reason=blocked['reason'], evidence=reference(blocked['evidence']))
            elif captured.get('arrival_failure'):
                failure = captured['arrival_failure']
                entry.update(verdict='FAIL', severity='critical', arrival_failure={
                    'evidence': reference(failure['evidence']), 'install_receipt': reference(failure['install_receipt']),
                    'summary': failure['summary'],
                })
            else:
                observed = _index(captured['frames'], 'comparison_id')
                if observed.keys() != {frame['comparison_id'] for frame in pair['comparisons']}:
                    raise ValueError('captured comparison IDs differ from the frozen pair')
                comparisons = []
                for expected in pair['comparisons']:
                    key = expected['comparison_id']
                    image, judgement = observed[key], judgements[key]
                    if judgement['verdict'] not in {'PASS', 'FAIL'}:
                        raise ValueError(f'comparison {key} has no resolved visual verdict')
                    result = {
                        'comparison_id': key, 'ios_png_sha256': pair['baseline']['png_sha256'],
                        'ios_region_px': expected.get('ios_region_px'), 'verdict': judgement['verdict'],
                        'harmony_png': reference(image['harmony_png']), 'harmony_xml': reference(image['harmony_xml']),
                        'appearance_report': reference(judgement['appearance_report']),
                        'relationship_report': reference(judgement['relationship_report']),
                    }
                    if result['verdict'] == 'FAIL':
                        result['severity'] = judgement['severity']
                    comparisons.append(result)
                failed = [row for row in comparisons if row['verdict'] == 'FAIL']
                entry.update(verdict='FAIL' if failed else 'PASS', comparisons=comparisons,
                             arrival_receipt=reference(captured['arrival_receipt']))
                if failed:
                    entry['severity'] = 'critical' if any(row['severity'] == 'critical' for row in failed) else 'normal'
        except (OSError, TypeError, KeyError, ValueError) as exc:
            gaps.append({'pair_id': name, 'reason': str(exc)})
            continue
        rows.append(entry)
    return {
        'schema_version': 2, 'status': 'BLOCKED' if gaps else 'ASSEMBLED',
        'scope_sha256': sha256(scope_path.read_bytes()), 'pairs': rows, 'assembly_gaps': gaps,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('command', nargs='?', default='summary', choices=('summary', 'assemble', 'affected'))
    parser.add_argument('--scope', required=True)
    parser.add_argument('--cases')
    parser.add_argument('--capture')
    parser.add_argument('--judgements', nargs='*')
    parser.add_argument('--project-root')
    parser.add_argument('--carry-from')
    parser.add_argument('--out')
    parser.add_argument('--geometry-tolerance', type=float, default=4.0)
    args = parser.parse_args(argv)
    root = Path(args.project_root).resolve() if args.project_root else None
    scope_path = _project_file(root, args.scope) if root else Path(args.scope)
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
