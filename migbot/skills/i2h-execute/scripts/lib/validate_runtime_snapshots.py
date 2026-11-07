from __future__ import annotations
import hashlib
import json
from pathlib import Path

def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _evidence_for_state(meta: dict, state: str) -> dict:
    by_state = meta.get('runtime_evidence_by_state')
    if isinstance(by_state, dict):
        value = by_state.get(state)
        if isinstance(value, dict):
            return value
    value = meta.get('runtime_evidence')
    return value if isinstance(value, dict) else {}


def _check_file(root: Path, folder: Path, evidence: dict, path_key: str, digest_key: str, label: str, errors: list[str]) -> str | None:
    value = evidence.get(path_key)
    if not value:
        errors.append(f'{label} path missing')
        return None
    path = Path(str(value)).expanduser()
    if not path.is_absolute():
        path = folder / path
    if not path.is_file():
        errors.append(f'{label} file missing: {value}')
        return None
    expected = evidence.get(digest_key)
    if not expected:
        errors.append(f'{label} sha256 missing')
    elif expected != _digest(path):
        errors.append(f'{label} sha256 mismatch: {value}')
    return path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path)


def check(root: Path | str, pages: list[dict], policy='runtime', facts=None) -> dict:
    root=Path(root).resolve(); fallbacks=[]; errors=[]
    canonical=(root/'spec/.i2h/target-input.json').is_file() and all((root/'spec/baseline/res-index'/f'{n}.json').is_file() for n in ('values','drawables','usage','design-tokens'))
    for page in pages:
        page_id = page['page_id']
        state = page.get('state_id') or page.get('state') or 'normal'
        snap=root/'spec/baseline/ui-snapshots'/page_id; mp=snap/'meta.json'
        if not mp.is_file():
            meta={}
            if policy != 'source_only':
                errors.append(f'{page_id}: meta.json missing')
        else:
            try:
                meta=json.loads(mp.read_text())
            except (OSError, json.JSONDecodeError):
                meta={}
                if policy != 'source_only':
                    errors.append(f'{page_id}: meta.json invalid')
        synthetic=meta.get('view_xml_synthesized') is True
        evidence = _evidence_for_state(meta, state)
        runtime_captured = False
        fallback={'page_id':page_id,'state_id':state,'runtime_captured':False}
        if synthetic: fallback['reason']=meta.get('fallback_reason')
        elif evidence:
            status = evidence.get('status')
            evidence_state = evidence.get('state_id') or evidence.get('state')
            if status not in ('audited', 'captured', 'verified'):
                errors.append(f'{page_id}/{state}: runtime evidence is not audited')
            if evidence_state and evidence_state != state:
                errors.append(f'{page_id}/{state}: runtime evidence state mismatch')
            _check_file(root, snap, evidence, 'png_path', 'png_sha256', f'{page_id}/{state} PNG', errors)
            ui_path_key = 'ui_json_path' if evidence.get('ui_json_path') else 'accessibility_json_path'
            ui_digest_key = 'ui_json_sha256' if evidence.get('ui_json_path') else 'accessibility_json_sha256'
            if evidence.get(ui_path_key):
                _check_file(root, snap, evidence, ui_path_key, ui_digest_key, f'{page_id}/{state} accessibility JSON', errors)
            elif evidence.get('view_xml_path'):
                _check_file(root, snap, evidence, 'view_xml_path', 'view_xml_sha256', f'{page_id}/{state} view.xml', errors)
            else:
                errors.append(f'{page_id}/{state}: UI tree evidence missing')
            runtime_captured = not any(item.startswith(f'{page_id}/{state}') for item in errors)
            fallback['runtime_captured'] = runtime_captured
            fallback['evidence_kind'] = 'ios-accessibility-json' if evidence.get('ui_json_path') else 'android-view-xml'
        elif not synthetic and policy == 'source_only':
            fallback['reason'] = 'source_only'
        elif not synthetic:
            errors.append(f'{page_id}/{state}: runtime evidence missing')
        fallbacks.append(fallback)
        if facts=='static-v1' and not canonical: errors.append('canonical static-v1 inputs missing')
        elif policy=='runtime' and synthetic: errors.append('runtime capture required')
        elif policy=='progressive' and synthetic and not (meta.get('fallback_reason') and 'evidence:' in meta.get('fallback_reason','')): errors.append('failed capture evidence required')
        elif policy=='source_only' and meta.get('view_xml_synthesized') is False:
            errors.append('source-only cannot use real runtime XML as evidence')
    if facts in ('legacy','static-v1-shadow'): errors=[]
    return {'status':'pass' if not errors else 'fail','errors':errors,'source_fallbacks':fallbacks,'policy':policy,'facts':facts}

def main(argv=None):
    import argparse
    ap=argparse.ArgumentParser()
    ap.add_argument('--project-root',required=True)
    ap.add_argument('--pages', '--pages-file', dest='pages', required=True)
    ap.add_argument('--policy', '--capture-policy', dest='policy', default='runtime')
    ap.add_argument('--facts')
    ns=ap.parse_args(argv)
    payload=json.loads(Path(ns.pages).read_text())
    pages=payload.get('pages', payload) if isinstance(payload, dict) else payload
    if not isinstance(pages, list):
        raise SystemExit('pages file must contain a list or a {"pages": [...]} object')
    result=check(ns.project_root,pages,ns.policy,ns.facts)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result['status']=='pass' else 1
