"""Reconcile UT generation records with an independently extracted registration list."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re


def project_file(root: Path, name: str) -> Path:
    if not isinstance(name, str) or not name.strip():
        raise ValueError("expected a project file path")
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f"path outside project: {name}")
    return path


def _cases(root: Path, feature: dict) -> list[dict]:
    feature_id = feature['feature_id']
    path = project_file(root, feature['generation_file'])
    record = json.loads(path.read_text(encoding='utf-8-sig'))
    if record.get('feature_id') != feature_id:
        raise ValueError(f"{path}: Feature ID differs from dispatch")
    for field in ('feature_file', 'design_file', 'test_file'):
        value = record.get(field)
        if field == 'test_file' and value is None:
            continue
        if project_file(root, value) != project_file(root, feature[field]):
            raise ValueError(f"{path}: {field} differs from dispatch")
    allowed = None
    if 'ac_inputs' in feature:
        allowed = {row['source_ac_id'] for row in feature['ac_inputs']}
    cases = record.get('cases')
    if not isinstance(cases, list):
        raise ValueError(f"{path}: cases must be an array")
    for case in cases:
        case_id = case.get('case_id')
        if not isinstance(case_id, str) or not case_id.startswith(feature_id + '_'):
            raise ValueError(f"{path}: invalid case ID {case_id!r}")
        outcome = case.get('outcome')
        testability = case.get('testability')
        if (outcome, testability) not in (('generated', 'ut'), ('deferred', 'no_entry'), ('deferred', 'needs_review')):
            raise ValueError(f"{path}: invalid classification for {case_id}")
        if outcome == 'generated' and not record.get('test_file'):
            raise ValueError(f"{path}: generated cases require test_file")
        ac_ids = case.get('source_ac_ids')
        if (not isinstance(ac_ids, list) or not ac_ids
                or not all(isinstance(ac, str) and re.fullmatch(feature_id + r'-AC[0-9]{2}', ac) for ac in ac_ids)
                or len(set(ac_ids)) != len(ac_ids)):
            raise ValueError(f"{path}: invalid source_ac_ids for {case_id}")
        if allowed is not None and set(ac_ids) - allowed:
            raise ValueError(f"{path}: {case_id} cites IDs absent from AC inputs")
    return cases


def inventory(manifest: dict, registered_ids: list[str] | None = None) -> dict:
    root = Path(manifest['project_root']).resolve()
    index = {}
    seen_features = set()
    for feature in manifest['features']:
        feature_id = feature['feature_id']
        if not re.fullmatch(r'F[0-9]{3}', feature_id) or feature_id in seen_features:
            raise ValueError(f"invalid or duplicate Feature ID {feature_id!r}")
        seen_features.add(feature_id)
        for case in _cases(root, feature):
            case_id = case['case_id']
            if case_id in index:
                raise ValueError(f"duplicate case ID {case_id}")
            index[case_id] = case['testability']
    generated = sorted(key for key, value in index.items() if value == 'ut')
    totals = Counter(index.values())
    check = {'status': 'not_checked'}
    if registered_ids is not None:
        if not isinstance(registered_ids, list) or not all(isinstance(key, str) and key for key in registered_ids):
            raise ValueError('registered IDs must be a JSON array of strings')
        actual = Counter(registered_ids)
        mismatches = {'missing': sorted(set(generated) - actual.keys()),
                      'unexpected': sorted(actual.keys() - set(generated)),
                      'duplicates': sorted(key for key, count in actual.items() if count > 1)}
        check = {'status': 'mismatch' if any(mismatches.values()) else 'matched', **mismatches}
    return {'totals': {'recorded_logic_count': len(index), 'generated': len(generated),
                       'no_entry': totals['no_entry'], 'needs_review': totals['needs_review']},
            'generated_ids': generated, 'deferred_ids': sorted(index.keys() - set(generated)),
            'registered_id_check': check}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--feature-inputs', required=True, type=Path)
    parser.add_argument('--registered-ids', type=Path)
    args = parser.parse_args()
    try:
        manifest = json.loads(args.feature_inputs.read_text(encoding='utf-8-sig'))
        registered = json.loads(args.registered_ids.read_text(encoding='utf-8-sig')) if args.registered_ids else None
        if args.registered_ids and registered is None:
            raise ValueError('registered IDs must be a JSON array of strings')
        result = inventory(manifest, registered)
    except (OSError, AttributeError, KeyError, TypeError, ValueError) as exc:
        parser.exit(2, f'generation_inventory: {exc}\n')
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return int(result['registered_id_check']['status'] == 'mismatch')


if __name__ == '__main__':
    raise SystemExit(main())
