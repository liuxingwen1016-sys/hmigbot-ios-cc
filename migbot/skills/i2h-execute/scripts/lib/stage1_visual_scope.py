from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .stage1_contract import digest, normalize, source_digest


_GOOD_STATUS = {'audited', 'captured', 'verified', 'pass', 'PASS'}


def _load(path: Path | str) -> dict:
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _evidence_for_state(meta: dict, state: str) -> dict:
    """Select one state without silently borrowing a different state."""
    by_state = meta.get('runtime_evidence_by_state')
    if isinstance(by_state, dict):
        value = by_state.get(state)
        return dict(value) if isinstance(value, dict) else {}
    value = meta.get('runtime_evidence')
    return dict(value) if isinstance(value, dict) else {}


def _identity(value: Any) -> Any:
    if isinstance(value, dict):
        for key in ('bundle_id', 'bundle_identifier', 'app_id', 'package', 'udid', 'device_id', 'name', 'id'):
            if value.get(key) is not None:
                return value[key]
    return value


def _expected(page: dict, meta: dict, *names: str) -> Any:
    for source in (page, meta):
        for name in names:
            if source.get(name) is not None:
                return source[name]
    return None


def _checked_file(
    folder: Path,
    evidence: dict,
    path_keys: tuple[str, ...],
    hash_keys: tuple[str, ...],
    label: str,
) -> tuple[Path, str]:
    raw_path = next((evidence.get(key) for key in path_keys if evidence.get(key)), None)
    if not isinstance(raw_path, str):
        raise ValueError(f'{label} is missing')
    path = Path(raw_path)
    if path.is_absolute() and not path.is_relative_to(folder.parents[1]):
        raise ValueError(f'{label} path escapes snapshot')
    if not path.is_absolute() and '..' in path.parts:
        raise ValueError(f'{label} path escapes snapshot')
    candidate = path if path.is_absolute() else folder / path
    if not candidate.is_file():
        raise ValueError(f'{label} is missing')
    actual = digest(candidate)
    recorded = next((evidence.get(key) for key in hash_keys if evidence.get(key)), None)
    if recorded is None or str(recorded).removeprefix('sha256:') != actual.removeprefix('sha256:'):
        raise ValueError(f'{label} hash mismatch')
    return candidate, actual


def _check_identity(
    page: dict,
    meta: dict,
    evidence: dict,
    label: str,
    page_names: tuple[str, ...],
    evidence_names: tuple[str, ...],
    *,
    required: bool = False,
) -> Any:
    expected = _expected(page, meta, *page_names)
    observed = next((evidence.get(name) for name in evidence_names if evidence.get(name) is not None), None)
    if observed is None and label == 'app identity' and isinstance(evidence.get('app'), dict):
        observed = evidence['app']
    if observed is None and label == 'device identity' and isinstance(evidence.get('device'), dict):
        observed = evidence['device']
    if observed is None and label == 'build identity' and isinstance(evidence.get('build'), dict):
        observed = evidence['build']
    if required and observed is None:
        raise ValueError(f'{label} is missing')
    if expected is not None and _identity(expected) != _identity(observed):
        raise ValueError(f'{label} mismatch')
    return observed


def baseline(root: Path | str, page: dict) -> dict:
    root = Path(root).resolve()
    page_id = page.get('page_id')
    state = page.get('state_id', 'normal')
    if not isinstance(page_id, str) or not page_id or not isinstance(state, str) or not state:
        raise ValueError('page_id and state_id are required')
    folder = root / 'spec/baseline/ui-snapshots' / page_id
    meta_path = folder / 'meta.json'
    meta = _load(meta_path) if meta_path.is_file() else {}
    evidence = _evidence_for_state(meta, state)
    if meta.get('view_xml_synthesized') is True:
        raise ValueError('runtime baseline is synthesized')
    if not evidence:
        if isinstance(meta.get('runtime_evidence_by_state'), dict):
            raise ValueError('baseline state evidence is missing')
        # Existing Android/source-only handoffs retain their old contract.
        if meta.get('view_xml_synthesized') is not False:
            raise ValueError('runtime evidence is missing')
        return {'page_id': page_id, 'state_id': state, 'path': folder.relative_to(root).as_posix(), 'evidence_kind': 'legacy'}

    if evidence.get('page_id') is not None and evidence.get('page_id') != page_id:
        raise ValueError('baseline page_id mismatch')
    evidence_state = evidence.get('state_id') or evidence.get('state')
    evidence_status = evidence.get('status') or meta.get('runtime_status') or meta.get('status')
    if evidence_status not in _GOOD_STATUS or evidence_state != state:
        raise ValueError('baseline state is not audited')

    png, png_sha = _checked_file(
        folder,
        evidence,
        ('png_path', 'screenshot_path', 'image_path'),
        ('png_sha256', 'screenshot_sha256'),
        'baseline PNG',
    )
    ui_json_value = next((evidence.get(key) for key in ('ui_json_path', 'accessibility_json_path', 'accessibility_path') if evidence.get(key)), None)
    is_ios = bool(ui_json_value) or evidence.get('platform') == 'ios' or evidence.get('source_platform') == 'ios'
    if is_ios:
        ui_json, ui_sha = _checked_file(
            folder,
            evidence,
            ('ui_json_path', 'accessibility_json_path', 'accessibility_path'),
            ('ui_json_sha256', 'accessibility_json_sha256', 'accessibility_sha256'),
            'baseline accessibility JSON',
        )
        device = _check_identity(
            page,
            meta,
            evidence,
            'device identity',
            ('device', 'device_id', 'device_serial'),
            ('device', 'device_id', 'device_serial'),
            required=False,
        )
        build = _check_identity(
            page,
            meta,
            evidence,
            'build identity',
            ('build_identity', 'build_id', 'build_sha256'),
            ('build_identity', 'build_id', 'build_sha256'),
            required=False,
        )
        app = _check_identity(
            page,
            meta,
            evidence,
            'app identity',
            ('app_identity', 'app_id', 'bundle_id', 'bundle_identifier'),
            ('app_identity', 'app_id', 'bundle_id', 'bundle_identifier', 'package'),
            required=True,
        )
        result = {
            'page_id': page_id,
            'state_id': state,
            'path': folder.relative_to(root).as_posix(),
            'evidence_kind': 'ios-accessibility-json',
            'png_path': png.relative_to(root).as_posix(),
            'png_sha256': png_sha,
            'ui_json_path': ui_json.relative_to(root).as_posix(),
            'ui_json_sha256': ui_sha,
            'device': device,
            'build_identity': build,
            'app_identity': app,
        }
        if evidence.get('captured_at') is not None:
            result['captured_at'] = evidence['captured_at']
        return result

    # Android/legacy view.xml remains supported and is checked just as before.
    xml, xml_sha = _checked_file(
        folder,
        evidence,
        ('view_xml_path', 'xml_path'),
        ('view_xml_sha256', 'xml_sha256'),
        'baseline view XML',
    )
    return {
        'page_id': page_id,
        'state_id': state,
        'path': folder.relative_to(root).as_posix(),
        'evidence_kind': 'android-view-xml',
        'png_path': png.relative_to(root).as_posix(),
        'view_xml_path': xml.relative_to(root).as_posix(),
        'png_sha256': png_sha,
        'view_xml_sha256': xml_sha,
    }


def _manifest_files(wiring: Path):
    return sorted(wiring.glob('*.json')) if wiring.is_dir() else [wiring]


def build_scope(wiring: Path | str, root: Path | str) -> dict:
    root = Path(root).resolve()
    wiring = Path(wiring)
    units = []
    for path in _manifest_files(wiring):
        data = normalize(_load(path))
        pages = []
        for page in data.get('pages', []):
            pages.append({**page, 'baseline': baseline(root, page)})
        units.append(
            {
                'unit_id': data.get('unit_id', path.stem),
                'status': data.get('status'),
                'entry_file': data.get('entry_file'),
                'preview_host_file': data.get('preview_host_file'),
                'pages': pages,
                'contract_path': path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path),
            }
        )
    if not units:
        raise ValueError('empty wiring scope')
    return {
        'schema_version': 1,
        'status': 'READY',
        'source_sha256': source_digest(root),
        'wiring_dir': str(wiring.relative_to(root) if wiring.is_relative_to(root) else wiring),
        'units': units,
    }


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--project-root', required=True)
    parser.add_argument('--wiring-dir', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args(argv)
    try:
        result = build_scope(args.wiring_dir, args.project_root)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        result = {
            'schema_version': 1,
            'status': 'BLOCKED',
            'failure_findings': [{'root_cause': 'information_gap', 'detail': str(exc)}],
        }
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if result.get('status') == 'READY' else 2
