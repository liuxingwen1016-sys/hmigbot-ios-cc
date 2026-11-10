"""Deterministic semantic and geometry acceptance for iOS-to-Harmony evidence.

The checker deliberately treats screenshot comparison as a secondary signal. A page
can only pass after page/state binding, accessibility semantics, component coverage,
and geometry checks pass.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def _read(value: Any) -> Any:
    if isinstance(value, dict):
        return value
    return json.loads(Path(value).read_text(encoding='utf-8'))


def _evidence_payload(value: Any) -> dict:
    data = _read(value)
    if not isinstance(data, dict):
        return {}
    nested = data.get('runtime_evidence') or data.get('accessibility')
    if isinstance(nested, dict):
        merged = dict(nested)
        for key in ('page_id', 'state_id', 'state', 'png_path', 'screenshot_path', 'device', 'app'):
            if merged.get(key) is None and data.get(key) is not None:
                merged[key] = data[key]
        return merged
    return data


def _page_state(data: dict) -> tuple[str | None, str | None]:
    return data.get('page_id'), data.get('state_id', data.get('state'))


def _nodes(data: dict) -> list[dict]:
    result: list[dict] = []

    def visit(value: Any) -> None:
        if isinstance(value, list):
            for item in value:
                visit(item)
            return
        if not isinstance(value, dict):
            return
        candidate = value.get('node') if isinstance(value.get('node'), dict) else value
        if any(candidate.get(key) is not None for key in ('role', 'type', 'label', 'identifier', 'id', 'frame', 'bounds', 'children')):
            result.append(candidate)
        for key in ('nodes', 'elements', 'children', 'accessibility_elements', 'items'):
            child = value.get(key)
            if isinstance(child, (list, dict)):
                visit(child)

    for key in ('nodes', 'elements', 'accessibility_elements', 'tree', 'root'):
        if key in data:
            visit(data[key])
    if not result:
        visit(data.get('accessibility'))
    return result


def _text(node: dict, *keys: str) -> str | None:
    for key in keys:
        value = node.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _frame(value: Any) -> tuple[float, float, float, float] | None:
    if isinstance(value, dict):
        if all(value.get(k) is not None for k in ('x', 'y', 'width', 'height')):
            return tuple(float(value[k]) for k in ('x', 'y', 'width', 'height'))
        if all(value.get(k) is not None for k in ('left', 'top', 'right', 'bottom')):
            return (float(value['left']), float(value['top']), float(value['right']) - float(value['left']), float(value['bottom']) - float(value['top']))
    if isinstance(value, (list, tuple)) and len(value) == 4:
        return tuple(float(x) for x in value)
    if isinstance(value, str):
        try:
            values = [float(x.strip()) for x in value.replace('(', '').replace(')', '').split(',')]
            return tuple(values) if len(values) == 4 else None
        except ValueError:
            return None
    return None


def _normalized(node: dict) -> dict:
    role = _text(node, 'role', 'accessibility_role', 'type', 'component', 'class')
    label = _text(node, 'label', 'accessibility_label', 'accessibilityLabel', 'text', 'value')
    identifier = _text(node, 'identifier', 'accessibility_identifier', 'accessibilityIdentifier', 'test_id', 'id')
    frame = _frame(node.get('frame', node.get('bounds', node.get('rect'))))
    return {
        'role': role,
        'label': label,
        'identifier': identifier,
        'frame': frame,
        'truncated': bool(node.get('truncated', node.get('text_truncated', node.get('textTruncated', False)))),
        'raw': node,
    }


def _index(data: dict) -> list[dict]:
    return [_normalized(node) for node in _nodes(data)]


def _matching(source: dict, target: list[dict]) -> dict | None:
    identity = source.get('identifier')
    if identity:
        for candidate in target:
            if candidate.get('identifier') == identity:
                return candidate
    role, label = source.get('role'), source.get('label')
    for candidate in target:
        if role and label and candidate.get('role') == role and candidate.get('label') == label:
            return candidate
    if label:
        for candidate in target:
            if candidate.get('label') == label:
                return candidate
    return None


def _role_equal(first: str | None, second: str | None) -> bool:
    if not first or not second:
        return first == second
    aliases = {
        'statictext': 'text', 'label': 'text', 'text': 'text',
        'textfield': 'text_field', 'text_field': 'text_field', 'input': 'text_field',
        'imageview': 'image', 'image': 'image',
        'button': 'button', 'tab': 'tab',
    }
    return aliases.get(first.lower().replace(' ', ''), first.lower()) == aliases.get(second.lower().replace(' ', ''), second.lower())


def _names(values: Any) -> set[str]:
    if not isinstance(values, list):
        return set()
    result = set()
    for value in values:
        if isinstance(value, str) and value:
            result.add(value)
        elif isinstance(value, dict):
            name = _text(value, 'identifier', 'id', 'name', 'component', 'role', 'label')
            if name:
                result.add(name)
    return result


def _path_names(data: dict, key: str) -> set[str]:
    values = data.get(key, data.get('navigation_paths' if key == 'actions' else key, []))
    names = set()
    if isinstance(values, list):
        for value in values:
            if isinstance(value, str):
                names.add(value)
            elif isinstance(value, dict):
                name = _text(value, 'id', 'identifier', 'name', 'action', 'path', 'trigger', 'destination')
                if name:
                    names.add(name)
    return names


def _safe_area(data: dict) -> tuple[float, float, float, float] | None:
    value = data.get('safe_area', data.get('safeArea', data.get('insets')))
    if isinstance(value, dict) and all(value.get(key) is not None for key in ('top', 'right', 'bottom', 'left')):
        return (float(value['left']), float(value['top']), float(value['right']), float(value['bottom']))
    return _frame(value)


def _geometry_error(expected: tuple[float, float, float, float] | None, actual: tuple[float, float, float, float] | None) -> float | None:
    if expected is None or actual is None:
        return None
    return max(abs(a - b) for a, b in zip(expected, actual))


def _screenshot_score(source: dict, target: dict) -> dict | None:
    source_path = source.get('png_path') or source.get('screenshot_path')
    target_path = target.get('png_path') or target.get('screenshot_path')
    if not source_path or not target_path:
        return None
    try:
        from PIL import Image, ImageChops, ImageStat
        first = Image.open(source_path).convert('L').resize((128, 128))
        second = Image.open(target_path).convert('L').resize((128, 128))
        mean = ImageStat.Stat(ImageChops.difference(first, second)).mean[0] / 255.0
        return {'mean_absolute_difference': round(mean, 6), 'auxiliary': True}
    except (ImportError, OSError, ValueError):
        return {'available': False, 'auxiliary': True}


def _target_binding(data: dict) -> tuple[str | None, str | None]:
    """Return only target-supplied page/state metadata.

    A case filename or the caller's expected page must not be allowed to
    masquerade as runtime evidence.  The Harmony capture wrapper therefore
    has to bind its own page/state fields before this gate can accept it.
    """
    page, state = _page_state(data)
    return page, state


def _target_fingerprint(data: dict) -> str:
    """Hash stable UI semantics while ignoring volatile device identifiers."""
    rows = []
    for node in _index(data):
        rows.append({
            'role': node.get('role'),
            'label': node.get('label'),
            'identifier': node.get('identifier'),
            'frame': node.get('frame'),
        })
    payload = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def accept(source: dict | str | Path, target: dict | str | Path, *, geometry_tolerance: float = 4.0) -> dict:
    source_data, target_data = _evidence_payload(source), _evidence_payload(target)
    source_page, source_state = _page_state(source_data)
    target_page, target_state = _page_state(target_data)
    result = {
        'page_id': source_page,
        'state_id': source_state,
        'status': 'PASS',
        'failure_findings': [],
        'coverage': {},
        'semantic': {},
        'geometry': {},
        'tokens': {},
        'interaction': {},
    }

    if source_page != target_page or source_state != target_state:
        result['status'] = 'BLOCKED'
        result['failure_findings'].append({'code': 'PAGE_STATE_MISMATCH', 'root_cause': 'information_gap', 'detail': f'expected {source_page}/{source_state}, observed {target_page}/{target_state}'})
        return result

    source_nodes, target_nodes = _index(source_data), _index(target_data)
    result['coverage'] = {'source_nodes': len(source_nodes), 'target_nodes': len(target_nodes)}
    if not source_nodes:
        result['status'] = 'BLOCKED'
        result['failure_findings'].append({'code': 'SOURCE_ACCESSIBILITY_EMPTY', 'root_cause': 'information_gap', 'detail': 'source accessibility JSON has no nodes'})
        return result

    missing, bad_roles, bad_labels, missing_identifiers, truncation = [], [], [], [], []
    geometry_errors = []
    for expected in source_nodes:
        actual = _matching(expected, target_nodes)
        key = expected.get('identifier') or expected.get('label') or expected.get('role') or '<unnamed>'
        if actual is None:
            missing.append(key)
            continue
        if expected.get('role') and not actual.get('role'):
            bad_roles.append(key)
        elif expected.get('role') and not _role_equal(actual.get('role'), expected['role']):
            bad_roles.append(key)
        if expected.get('label') and not actual.get('label'):
            bad_labels.append(key)
        if expected.get('identifier') and not actual.get('identifier'):
            missing_identifiers.append(key)
        if expected.get('truncated') != actual.get('truncated'):
            truncation.append(key)
        error = _geometry_error(expected.get('frame'), actual.get('frame'))
        if error is not None:
            geometry_errors.append({'node': key, 'max_delta': round(error, 3)})
    result['semantic'] = {
        'missing_components': missing,
        'role_mismatches': bad_roles,
        'missing_labels': bad_labels,
        'missing_identifiers': missing_identifiers,
        'truncation_mismatches': truncation,
        'coverage_rate': round((len(source_nodes) - len(missing)) / len(source_nodes), 4),
    }
    result['geometry'] = {
        'max_error': max((entry['max_delta'] for entry in geometry_errors), default=0.0),
        'tolerance': geometry_tolerance,
        'within_tolerance': all(entry['max_delta'] <= geometry_tolerance for entry in geometry_errors),
        'errors': geometry_errors,
    }

    required_components = _names(source_data.get('required_components', source_data.get('components')))
    target_component_names = set()
    for node in target_nodes:
        target_component_names.update(value for value in (node.get('identifier'), node.get('role'), node.get('label')) if value)
    missing_components = sorted(required_components - target_component_names)
    if missing_components:
        result['semantic']['missing_components'].extend(value for value in missing_components if value not in result['semantic']['missing_components'])

    source_colors = _names(source_data.get('color_tokens', source_data.get('colors')))
    target_colors = _names(target_data.get('color_tokens', target_data.get('colors')))
    source_fonts = _names(source_data.get('font_tokens', source_data.get('fonts')))
    target_fonts = _names(target_data.get('font_tokens', target_data.get('fonts')))
    result['tokens'] = {
        'color_tokens': {'expected': sorted(source_colors), 'missing': sorted(source_colors - target_colors)},
        'font_tokens': {'expected': sorted(source_fonts), 'missing': sorted(source_fonts - target_fonts)},
    }

    source_actions = _path_names(source_data, 'actions')
    target_actions = _path_names(target_data, 'actions')
    source_paths = _path_names(source_data, 'navigation_paths')
    target_paths = _path_names(target_data, 'navigation_paths')
    result['interaction'] = {
        'actions': {'expected': sorted(source_actions), 'missing': sorted(source_actions - target_actions)},
        'navigation_paths': {'expected': sorted(source_paths), 'missing': sorted(source_paths - target_paths)},
    }

    safe_source, safe_target = _safe_area(source_data), _safe_area(target_data)
    result['geometry']['safe_area'] = {
        'expected': safe_source,
        'observed': safe_target,
        'max_error': _geometry_error(safe_source, safe_target),
        'within_tolerance': _geometry_error(safe_source, safe_target) is None or _geometry_error(safe_source, safe_target) <= geometry_tolerance,
    }
    result['screenshot_diff'] = _screenshot_score(source_data, target_data)

    blocking = [
        ('missing_components', result['semantic']['missing_components']),
        ('role_mismatches', result['semantic']['role_mismatches']),
        ('missing_labels', result['semantic']['missing_labels']),
        ('missing_identifiers', result['semantic']['missing_identifiers']),
        ('truncation_mismatches', result['semantic']['truncation_mismatches']),
        ('geometry', not result['geometry']['within_tolerance']),
        ('safe_area', not result['geometry']['safe_area']['within_tolerance']),
        ('color_tokens', result['tokens']['color_tokens']['missing']),
        ('font_tokens', result['tokens']['font_tokens']['missing']),
        ('actions', result['interaction']['actions']['missing']),
        ('navigation_paths', result['interaction']['navigation_paths']['missing']),
    ]
    for code, value in blocking:
        if value:
            result['status'] = 'FAIL'
            result['failure_findings'].append({'code': code.upper(), 'root_cause': 'product_defect', 'detail': value})
    return result


def report(cases: list[dict], *, geometry_tolerance: float = 4.0) -> dict:
    results = []
    seen_targets: dict[str, tuple[str | None, str | None]] = {}
    for case in cases:
        source = next((case.get(key) for key in ('source', 'ios', 'baseline') if case.get(key) is not None), None)
        target = next((case.get(key) for key in ('target', 'harmony', 'execute') if case.get(key) is not None), None)
        if source is None or target is None:
            results.append({'status': 'BLOCKED', 'failure_findings': [{'code': 'EVIDENCE_MISSING', 'root_cause': 'information_gap'}]})
        else:
            source_data = _evidence_payload(source)
            target_data = _evidence_payload(target)
            if source_data.get('page_id') is None and case.get('page_id') is not None:
                source_data['page_id'] = case['page_id']
            if source_data.get('state_id') is None and case.get('state_id') is not None:
                source_data['state_id'] = case['state_id']
            target_page, target_state = _target_binding(target_data)
            if target_page is None or target_state is None:
                row = {
                    'page_id': source_data.get('page_id'),
                    'state_id': source_data.get('state_id', source_data.get('state')),
                    'status': 'BLOCKED',
                    'failure_findings': [{
                        'code': 'TARGET_PAGE_STATE_UNBOUND',
                        'root_cause': 'information_gap',
                        'detail': 'Harmony UI evidence must carry its own page_id and state_id',
                    }],
                }
            else:
                row = accept(source_data, target_data, geometry_tolerance=geometry_tolerance)
                fingerprint = _target_fingerprint(target_data)
                previous = seen_targets.get(fingerprint)
                current = (target_page, target_state)
                if previous is not None and previous != current:
                    row['status'] = 'BLOCKED'
                    row.setdefault('failure_findings', []).append({
                        'code': 'DUPLICATE_TARGET_EVIDENCE',
                        'root_cause': 'information_gap',
                        'detail': f'target evidence fingerprint already bound to {previous[0]}/{previous[1]}',
                    })
                else:
                    seen_targets[fingerprint] = current
            row.setdefault('page_id', source_data.get('page_id'))
            row.setdefault('state_id', source_data.get('state_id', source_data.get('state')))
            results.append(row)
    total = len(results)
    passed = sum(row.get('status') == 'PASS' for row in results)
    blocked = sum(row.get('status') == 'BLOCKED' for row in results)
    return {
        'schema_version': 1,
        'status': 'PASS' if total and passed == total else ('visual_blocked' if blocked else 'FAIL'),
        'page_count': len({row.get('page_id') for row in results if row.get('page_id')}),
        'state_count': len({(row.get('page_id'), row.get('state_id')) for row in results if row.get('page_id')}),
        'evidence_completeness': round(passed / total, 4) if total else 0.0,
        'semantic_coverage': round(sum(row.get('semantic', {}).get('coverage_rate', 0.0) for row in results) / total, 4) if total else 0.0,
        'geometry_max_error': max((row.get('geometry', {}).get('max_error', 0.0) for row in results), default=0.0),
        'visual_blocked_reasons': [finding for row in results for finding in row.get('failure_findings', []) if row.get('status') == 'BLOCKED'],
        'results': results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-json')
    parser.add_argument('--target-json')
    parser.add_argument('--cases')
    parser.add_argument('--out')
    parser.add_argument('--geometry-tolerance', type=float, default=4.0)
    args = parser.parse_args(argv)
    if args.cases:
        payload = _read(args.cases)
        cases = payload.get('cases', []) if isinstance(payload, dict) else payload
        result = report(cases, geometry_tolerance=args.geometry_tolerance)
    elif args.source_json and args.target_json:
        result = accept(args.source_json, args.target_json, geometry_tolerance=args.geometry_tolerance)
    else:
        parser.error('provide --source-json and --target-json, or --cases')
    encoded = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(encoded, encoding='utf-8')
    else:
        print(encoded)
    return 0 if result.get('status') == 'PASS' else 2
