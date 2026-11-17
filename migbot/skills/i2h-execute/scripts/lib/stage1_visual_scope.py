from __future__ import annotations

from hashlib import sha256
import json
import re
import shutil
import sys
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
    if evidence and evidence.get('status') == 'blocked':
        raise ValueError(evidence.get('reason', 'runtime capture blocked'))
    if not evidence:
        if isinstance(meta.get('runtime_evidence_by_state'), dict):
            raise ValueError('baseline state evidence is missing')
        # Existing Android/source-only handoffs retain their old contract.
        if meta.get('view_xml_synthesized') is not False:
            raise ValueError('runtime evidence is missing')
        return {'page_id': page_id, 'state_id': state, 'path': folder.relative_to(root).as_posix(), 'evidence_kind': 'legacy'}

    fixture = page.get('fixture_capture_sha256')
    if fixture != evidence.get('fixture_capture_sha256'):
        raise ValueError('baseline fixture does not match the approved state binding')
    if fixture:
        _check_fixture_capture(folder / 'states' / state, evidence, fixture, page_id=page_id, state_id=state)

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
        if fixture:
            result['fixture_capture_sha256'] = fixture
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


def capture_context(output_dir: Path) -> dict[str, str]:
    """Shared provenance for a primary capture and its source supplements."""
    evidence = _load(output_dir / 'runtime-evidence.json')
    context = {key: evidence.get(key) for key in ('source_sha256', 'device_udid', 'configuration_id')}
    context['bundle_id'] = _identity(evidence.get('app'))
    if not all(isinstance(value, str) and value for value in context.values()):
        raise ValueError(f'incomplete runtime capture provenance: {output_dir}')
    if not re.fullmatch(r'[a-f0-9]{64}', context['source_sha256']):
        raise ValueError(f'invalid runtime capture source digest: {output_dir}')
    return context


FIXTURE_BINDINGS = 'spec/baseline/plans/ui-fixture-captures.json'


def approved_fixture_bindings(root: Path, inventory_path: Path, inventory: dict) -> dict[tuple[str, str], str]:
    path = root / FIXTURE_BINDINGS
    if not path.is_file():
        return {}
    if not path.resolve().is_relative_to(root) or not inventory_path.is_relative_to(root):
        raise ValueError('fixture binding and inventory must stay inside the project')
    inventory_sha256 = digest(inventory_path).removeprefix('sha256:')
    raw = path.read_bytes()
    receipt = json.loads(raw)
    if (not isinstance(receipt, dict) or receipt.get('schema_version') != 1
            or receipt.get('inventory_sha256') != inventory_sha256
            or not isinstance(receipt.get('confirmation_ref'), str) or not receipt['confirmation_ref'].strip()
            or not isinstance(receipt.get('bindings'), list) or not receipt['bindings']):
        raise ValueError('invalid fixture bindings for the selected UI inventory')
    allowed = set()
    for unit in inventory.get('units', []):
        if not isinstance(unit, dict) or not isinstance(unit.get('required_states'), list):
            continue
        for state in unit['required_states']:
            if not isinstance(state, dict) or state.get('arrival_mode') != 'behavior':
                continue
            page, name = unit.get('page_id'), state.get('state_id')
            if (all(isinstance(part, str) and part for part in (page, name))
                    and state.get('evidence_state_id', name) == name and state.get('evidence_page_id', page) == page):
                allowed.add((page, name))
    bindings = {}
    for row in receipt['bindings']:
        if not isinstance(row, dict):
            raise ValueError('invalid approved fixture binding row')
        key = (_safe_part(row.get('page_id'), 'fixture page_id'), _safe_part(row.get('state_id'), 'fixture state_id'))
        expected = row.get('fixture_capture_sha256')
        if key not in allowed or key in bindings or not isinstance(expected, str) or not re.fullmatch(r'[a-f0-9]{64}', expected):
            raise ValueError(f'invalid approved fixture binding: {key}')
        bindings[key] = expected

    plan_scripts = str(Path(__file__).resolve().parents[3] / 'i2h-plan/scripts')
    if plan_scripts not in sys.path:
        sys.path.insert(0, plan_scripts)
    from acceptance_plan import approved_plan

    if (inventory.get('status') != 'approved' or not inventory.get('approval')
            or not approved_plan(root, inventory_path, inventory_sha256)
            or not approved_plan(root, path, digest(raw).removeprefix('sha256:'))):
        raise ValueError('isolated fixtures require both bindings and UI inventory in the approved Plan marker')
    return bindings


def _check_fixture_capture(output_dir: Path, capture: dict, expected_sha256: str, *,
                           page_id: str, state_id: str, reference_context: dict[str, str] | None = None) -> None:
    """Validate a separately approved capture of one isolated behavior state."""
    manifest = output_dir / 'manifest.json'
    if manifest.resolve().parent != output_dir or not manifest.is_file():
        raise ValueError(f'approved fixture capture manifest missing: {page_id}/{state_id}')
    raw = manifest.read_bytes()
    if digest(raw).removeprefix('sha256:') != expected_sha256:
        raise ValueError(f'approved fixture capture digest mismatch: {page_id}/{state_id}')
    record = json.loads(raw)
    evidence_path = output_dir / 'runtime-evidence.json'
    if evidence_path.resolve().parent != output_dir:
        raise ValueError(f'approved fixture evidence escapes its state: {page_id}/{state_id}')
    evidence = _load(evidence_path)
    if (not isinstance(record, dict) or not isinstance(record.get('artifacts'), dict)
            or record.get('schema') != 'hmigbot-ios-ui-evidence/1' or record.get('status') != 'audited'
            or record.get('page_id') != page_id or record.get('state_id') != state_id
            or record.get('launch_mode') != 'standard' or record.get('runtime_evidence') != evidence):
        raise ValueError(f'approved fixture capture identity mismatch: {page_id}/{state_id}')
    actual_context = capture_context(output_dir)
    if reference_context and any(
        actual_context[key] != reference_context[key] for key in ('source_sha256', 'bundle_id')
    ):
        raise ValueError(f'approved fixture source or bundle mismatch: {page_id}/{state_id}')
    for kind, hash_key in (('screenshot', 'png_sha256'), ('ui_json', 'ui_json_sha256'),
                           ('foreground_receipt', None), ('foreground_ack', None)):
        artifact = record['artifacts'].get(kind)
        if not isinstance(artifact, dict):
            raise ValueError(f'approved fixture {kind} artifact missing: {page_id}/{state_id}')
        artifact_name = _safe_part(artifact.get('path'), f'fixture {kind} artifact path')
        path = output_dir / artifact_name
        expected = artifact.get('sha256')
        if (not expected or path.resolve().parent != output_dir or not path.is_file()
                or digest(path.read_bytes()).removeprefix('sha256:') != expected):
            raise ValueError(f'approved fixture {kind} digest mismatch: {page_id}/{state_id}')
        if kind in ('screenshot', 'ui_json'):
            path_key = hash_key.removesuffix('_sha256') + '_path'
            indexed = output_dir.parent.parent / capture.get(path_key, '')
            if capture.get(hash_key) != expected or indexed.resolve() != path:
                raise ValueError(f'approved fixture {kind} metadata mismatch: {page_id}/{state_id}')
        if kind == 'foreground_receipt' and _load(path).get('launch_mode') != 'standard':
            raise ValueError(f'approved fixture foreground launch mode mismatch: {page_id}/{state_id}')


def _check_supplement_pair(page_dir: Path, state_dir: Path, evidence: dict) -> None:
    for label, path_key, hash_key in (
        ('screenshot', 'png_path', 'png_sha256'), ('accessibility JSON', 'ui_json_path', 'ui_json_sha256')
    ):
        file, _ = _checked_file(page_dir, evidence, (path_key,), (hash_key,), label)
        if not file.resolve().is_relative_to(state_dir):
            raise ValueError(f'{label} is outside its state')


def _partial_job_context(root: Path, manifest_file: Path, output_root: Path,
                         manifest: dict, raw_manifest: bytes) -> dict[str, str]:
    if manifest_file != _capture_manifest_candidates(root)[0]:
        raise ValueError('runtime capture manifest is partial and requires the canonical job handoff')
    job = output_root.parent
    jobs = root / 'spec/execution/ios-runtime-jobs'
    if output_root.name != 'states' or job.parent != jobs:
        raise ValueError('partial runtime capture requires a project-local job')
    raw_inputs = (job / 'inputs.json').read_bytes()
    inputs = json.loads(raw_inputs)
    result = _load(job / 'result.json')
    plan = job / 'capture-plan.json'
    if (manifest.get('status') != 'partial'
            or result.get('status') != 'partial' or result.get('exit_code') != 2
            or result.get('inputs_sha256') != sha256(raw_inputs).hexdigest()
            or result.get('manifest_sha256') != sha256(raw_manifest).hexdigest()
            or (output_root / 'capture-plan-manifest.json').read_bytes() != raw_manifest
            or manifest.get('plan_path') != str(plan)
            or inputs.get('plan_sha256') != sha256(plan.read_bytes()).hexdigest()):
        raise ValueError('partial runtime capture does not match the frozen job receipt')
    plan_states = _load(plan)['states']
    keys = [(row['page_id'], row.get('state_id', 'normal')) for row in plan_states]
    rows = manifest['states']
    observed = [(row['page_id'], row.get('state_id', 'normal')) for row in rows]
    captured = sum(row.get('status') == 'captured' for row in rows)
    if (len(set(keys)) != len(keys) or sorted(keys) != sorted(observed)
            or (len(rows), captured, len(rows) - captured)
            != tuple(manifest.get(key) for key in ('state_count', 'captured_count', 'blocked_count'))
            or not any(row.get('status') == 'blocked' for row in rows)
            or any(row.get('status') not in {'captured', 'blocked'} for row in rows)):
        raise ValueError('partial runtime capture changed the frozen state coverage')
    context = {
        'source_sha256': inputs.get('source_sha256'),
        'device_udid': inputs.get('device_id'),
        'configuration_id': inputs.get('configuration_id'),
        'bundle_id': inputs.get('bundle_id'),
    }
    if not all(isinstance(value, str) and value for value in context.values()):
        raise ValueError('partial runtime capture job provenance is incomplete')
    return context


def sync_runtime_capture(root: Path | str, manifest_path: Path | str, *,
                         supplement_context: dict[str, str] | None = None,
                         fixture_bindings: dict[tuple[str, str], str] | None = None) -> dict:
    """Materialize batch Simulator evidence into the canonical baseline tree.

    ``ios_runtime_capture_plan.py`` can write to a temporary output root to
    keep the capture run disposable.  The visual gate still needs the PNG,
    accessibility JSON, and per-state metadata below
    ``spec/baseline/ui-snapshots``. Store runtime rows beside the frozen
    Spec metadata so that an Execute sync leaves its exact bytes intact.
    """
    root = Path(root).resolve()
    manifest_file = Path(manifest_path).expanduser().resolve()
    raw_manifest = manifest_file.read_bytes()
    manifest = json.loads(raw_manifest)
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
    partial_context = None
    job_result = output_root.parent / 'result.json'
    job_is_partial = (
        output_root.name == 'states'
        and output_root.parent.parent == root / 'spec/execution/ios-runtime-jobs'
        and job_result.is_file()
        and _load(job_result).get('status') == 'partial'
    )
    if supplement_context is None and (manifest.get('status') == 'partial' or job_is_partial):
        partial_context = _partial_job_context(root, manifest_file, output_root, manifest, raw_manifest)
    elif blocked and supplement_context is None:
        raise ValueError(f'runtime capture manifest is partial: {json.dumps(blocked, ensure_ascii=False)}')

    if partial_context:
        for row in blocked:
            _safe_part(row['page_id'], 'runtime capture page_id')
            _safe_part(row['state_id'], 'runtime capture state_id')

    baseline_root = root / 'spec/baseline/ui-snapshots'
    prepared = []
    seen = {}
    reused = []
    synced = []
    for row in states:
        if row.get('status') != 'captured':
            continue
        page_id = _safe_part(row.get('page_id'), 'runtime capture page_id')
        state_id = _safe_part(row.get('state_id', 'normal'), 'runtime capture state_id')
        if (page_id, state_id) in seen:
            raise ValueError(f'duplicate runtime capture: {page_id}/{state_id}')
        seen[(page_id, state_id)] = None
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
        if partial_context:
            if capture_context(output_dir) != partial_context:
                raise ValueError(f'partial runtime capture provenance mismatch: {page_id}/{state_id}')
            if capture.get('source_platform') != 'ios' or capture.get('page_id') != page_id:
                raise ValueError(f'not a bound iOS capture: {page_id}/{state_id}')
            _check_supplement_pair(source_page, output_dir, capture)
        if supplement_context is not None:
            bound = (fixture_bindings or {}).get((page_id, state_id))
            if bound:
                _check_fixture_capture(output_dir, capture, bound, page_id=page_id, state_id=state_id,
                                       reference_context=supplement_context)
            elif capture_context(output_dir) != supplement_context:
                raise ValueError(f'supplemental capture provenance mismatch: {page_id}/{state_id}')
            if capture.get('source_platform') != 'ios' or capture.get('page_id') != page_id:
                raise ValueError(f'not a bound iOS capture: {page_id}/{state_id}')
            _check_supplement_pair(source_page, output_dir, capture)
            if bound:
                capture = {**capture, 'fixture_capture_sha256': bound}
            existing = _evidence_for_state(read_snapshot_meta(destination_page), state_id)
            if existing and existing.get('status') == 'blocked':
                capture = {**capture, 'resolved_partial_manifest_sha256': existing.get('partial_manifest_sha256')}
            elif existing:
                for key in ('png_sha256', 'ui_json_sha256', 'fixture_capture_sha256'):
                    if existing.get(key) != capture.get(key):
                        raise ValueError(f'supplement would replace captured state: {page_id}/{state_id}')
                destination = destination_page / 'states' / state_id
                try:
                    if destination.resolve() != destination:
                        raise ValueError('snapshot path is redirected')
                    if bound:
                        _check_fixture_capture(destination, existing, bound, page_id=page_id, state_id=state_id,
                                               reference_context=supplement_context)
                    else:
                        if capture_context(destination) != supplement_context:
                            raise ValueError('provenance mismatch')
                        _check_supplement_pair(destination_page, destination, existing)
                except (OSError, ValueError) as exc:
                    raise ValueError(f'existing supplemental capture {page_id}/{state_id}: {exc}') from exc
                reused.append((page_id, state_id))
                continue
        files = sorted(path for path in output_dir.iterdir() if path.is_file()) if output_dir.is_dir() else []
        if not files:
            raise ValueError(f'runtime capture state directory is empty: {output_dir}')
        prepared.append((page_id, state_id, destination_page, capture, files))

    for page_id, state_id, destination_page, capture, files in prepared:
        for source in files:
            _copy_file(source, destination_page / 'states' / state_id / source.name)
        meta = read_snapshot_meta(destination_page)
        states_by_id = meta.get('runtime_evidence_by_state')
        if not isinstance(states_by_id, dict):
            states_by_id = {}
        states_by_id[state_id] = capture
        write_runtime_snapshot_meta(destination_page, states_by_id)
        synced.append((page_id, state_id))

    if partial_context:
        manifest_sha256 = sha256(raw_manifest).hexdigest()
        for row in blocked:
            page = baseline_root / row['page_id']
            meta = read_snapshot_meta(page)
            states_by_id = meta.get('runtime_evidence_by_state')
            if not isinstance(states_by_id, dict):
                states_by_id = {}
            existing = states_by_id.get(row['state_id'], {})
            if existing.get('resolved_partial_manifest_sha256') == manifest_sha256:
                continue
            states_by_id[row['state_id']] = {**row, 'status': 'blocked', 'source_platform': 'ios',
                                             'partial_manifest_sha256': manifest_sha256}
            write_runtime_snapshot_meta(page, states_by_id)

    def describe(keys):
        return [{'page_id': page, 'state_id': state, 'snapshot': str((baseline_root / page).relative_to(root))}
                for page, state in keys]

    result = {
        'manifest': str(manifest_file),
        'status': 'synced',
        'state_count': len(seen),
        'states': describe(seen),
    }
    if partial_context:
        result.update(status='partial', blocked_states=blocked, capture_context=partial_context)
    if supplement_context is not None:
        result['blocked_states'] = blocked
        result['imported_state_count'] = len(synced)
        result['reused_states'] = describe(reused)
    return result


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
