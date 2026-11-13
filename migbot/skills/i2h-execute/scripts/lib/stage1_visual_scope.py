from __future__ import annotations

import json
import shutil
from pathlib import Path
import tempfile
from typing import Any

from .stage1_contract import digest, normalize, source_digest


_GOOD_STATUS = {'audited', 'captured', 'verified', 'pass', 'PASS'}
RUNTIME_META = 'runtime-meta.json'


def _load(path: Path | str) -> dict:
    return json.loads(Path(path).read_text(encoding='utf-8'))


def read_snapshot_meta(folder: Path) -> dict:
    static_path = folder / 'meta.json'
    meta = _load(static_path) if static_path.is_file() else {}
    if not isinstance(meta, dict):
        raise ValueError(f'invalid static metadata: {static_path}')
    runtime_path = folder / RUNTIME_META
    if not runtime_path.is_file():
        return meta
    runtime = _load(runtime_path)
    states = runtime.get('runtime_evidence_by_state') if isinstance(runtime, dict) else None
    if (not isinstance(states, dict) or runtime.get('page_id') != folder.name
            or any(not isinstance(row, dict) for row in states.values())):
        raise ValueError(f'invalid runtime metadata: {runtime_path}')
    legacy = meta.get('runtime_evidence_by_state')
    return {**meta, 'runtime_evidence_by_state': {**(legacy if isinstance(legacy, dict) else {}), **states}}


def write_runtime_snapshot_meta(folder: Path, states: dict) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', dir=folder, encoding='utf-8', delete=False) as stream:
            temporary = Path(stream.name)
            json.dump({'page_id': folder.name, 'runtime_evidence_by_state': states}, stream,
                      ensure_ascii=False, indent=2)
            stream.write('\n')
        temporary.replace(folder / RUNTIME_META)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


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
    meta = read_snapshot_meta(folder)
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


def _capture_manifest_candidates(root: Path) -> list[Path]:
    return [
        root / 'spec/execution/ios-runtime-capture/capture-plan-manifest.json',
        root / 'spec/execution/runtime-captures/capture-plan-manifest.json',
        root / 'spec/baseline/ios-runtime-capture/capture-plan-manifest.json',
    ]


def _safe_part(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or Path(value).name != value or value in {'.', '..'}:
        raise ValueError(f'{label} is invalid')
    return value


def _copy_file(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise ValueError(f'runtime capture file is missing: {source}')
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() != destination.resolve():
        shutil.copy2(source, destination)


def sync_runtime_capture(root: Path | str, manifest_path: Path | str) -> dict:
    """Materialize batch Simulator evidence into the canonical baseline tree.

    ``ios_runtime_capture_plan.py`` can write to a temporary output root to
    keep the capture run disposable.  The visual gate still needs the PNG,
    accessibility JSON, and per-state metadata below
    ``spec/baseline/ui-snapshots``. Store runtime rows beside the frozen
    Spec metadata so that an Execute sync leaves its exact bytes intact.
    """
    root = Path(root).resolve()
    manifest_file = Path(manifest_path).expanduser().resolve()
    manifest = _load(manifest_file)
    states = manifest.get('states')
    if not isinstance(states, list) or not states:
        raise ValueError('runtime capture manifest has no states')
    output_root_value = manifest.get('output_root')
    if not isinstance(output_root_value, str) or not output_root_value:
        raise ValueError('runtime capture manifest output_root is missing')
    output_root = Path(output_root_value).expanduser().resolve()
    if not output_root.is_dir():
        raise ValueError(f'runtime capture output root is missing: {output_root}')

    if any(not isinstance(row, dict) for row in states):
        raise ValueError('runtime capture state entry is invalid')
    blocked = [
        {
            'page_id': row.get('page_id'),
            'state_id': row.get('state_id', 'normal'),
            'reason': row.get('blocked_reason', 'capture did not complete'),
        }
        for row in states
        if row.get('status') != 'captured'
    ]
    if blocked:
        raise ValueError(f'runtime capture manifest is partial: {json.dumps(blocked, ensure_ascii=False)}')

    synced: list[dict[str, str]] = []
    baseline_root = root / 'spec/baseline/ui-snapshots'
    for row in states:
        page_id = _safe_part(row.get('page_id'), 'runtime capture page_id')
        state_id = _safe_part(row.get('state_id', 'normal'), 'runtime capture state_id')
        output_value = row.get('output_dir')
        if not isinstance(output_value, str) or not output_value:
            raise ValueError(f'runtime capture output_dir is missing for {page_id}/{state_id}')
        output_dir = Path(output_value).expanduser()
        if not output_dir.is_absolute():
            output_dir = output_root / output_dir
        output_dir = output_dir.resolve()
        try:
            output_dir.relative_to(output_root)
        except ValueError as exc:
            raise ValueError(f'runtime capture output_dir escapes output_root: {output_dir}') from exc
        expected_dir = output_root / page_id / 'states' / state_id
        if output_dir != expected_dir.resolve():
            raise ValueError(f'runtime capture output_dir does not match page/state: {output_dir}')
        source_page = output_root / page_id
        destination_page = baseline_root / page_id
        capture = _evidence_for_state(read_snapshot_meta(source_page), state_id)
        if not capture or (capture.get('state_id') or capture.get('state')) not in {None, state_id}:
            raise ValueError(f'runtime capture metadata does not bind {page_id}/{state_id}')
        files = sorted(path for path in output_dir.iterdir() if path.is_file()) if output_dir.is_dir() else []
        if not files:
            raise ValueError(f'runtime capture state directory is empty: {output_dir}')
        for source in files:
            _copy_file(source, destination_page / 'states' / state_id / source.name)
        meta = read_snapshot_meta(destination_page)
        states_by_id = meta.get('runtime_evidence_by_state')
        if not isinstance(states_by_id, dict):
            states_by_id = {}
        states_by_id[state_id] = capture
        write_runtime_snapshot_meta(destination_page, states_by_id)
        synced.append({'page_id': page_id, 'state_id': state_id, 'snapshot': str(destination_page.relative_to(root))})
    return {
        'manifest': str(manifest_file),
        'status': 'synced',
        'state_count': len(synced),
        'states': synced,
    }


def build_scope(
    wiring: Path | str,
    root: Path | str,
    runtime_capture_manifest: Path | str | None = None,
) -> dict:
    root = Path(root).resolve()
    wiring = Path(wiring)
    capture_sync = None
    manifest = Path(runtime_capture_manifest).expanduser().resolve() if runtime_capture_manifest else None
    if manifest is None:
        manifest = next((path for path in _capture_manifest_candidates(root) if path.is_file()), None)
    if manifest is not None:
        capture_sync = sync_runtime_capture(root, manifest)
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
        'runtime_capture': capture_sync,
        'units': units,
    }


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--project-root', required=True)
    parser.add_argument('--wiring-dir', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--runtime-capture-manifest')
    args = parser.parse_args(argv)
    try:
        result = build_scope(args.wiring_dir, args.project_root, args.runtime_capture_manifest)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        result = {
            'schema_version': 1,
            'status': 'BLOCKED',
            'failure_findings': [{'root_cause': 'information_gap', 'detail': str(exc)}],
        }
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if result.get('status') == 'READY' else 2
