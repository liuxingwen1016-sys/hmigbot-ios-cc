from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from .stage1_contract import normalize, source_digest, digest

def _obj(value):
    if value is None: return None
    if isinstance(value, (str, Path)): return json.loads(Path(value).read_text(encoding='utf-8'))
    return value

def _valid_receipt(root, rec, kind):
    rec = _obj(rec)
    if not isinstance(rec, dict) or rec.get('kind') != kind or rec.get('status') != 'PASS': return False
    if rec.get('source_sha256') != source_digest(root): return False
    hp = rec.get('hap_path')
    if not isinstance(hp, str): return False
    p = root / hp
    return p.is_file() and rec.get('hap_sha256') == digest(p)

def check(root: Path | str, contract: dict, build=None, install=None) -> dict:
    root = Path(root).resolve()
    try: data = normalize(contract)
    except ValueError as exc: return {'status':'blocked','errors':[str(exc)],'runtime_visibility_verified':False}
    errors=[]
    host = data.get('preview_host_file')
    if not host: errors.append('preview host is required')
    elif not (root / host).is_file(): errors.append(f'preview host missing: {host}')
    if data.get('entry_file') and not (root / data['entry_file']).is_file(): errors.append('entry file missing')
    for row in data.get('pages', []):
        if not (root / row['output_file']).is_file(): errors.append(f"page missing: {row['output_file']}")
    if errors: return {'status':'blocked','errors':errors,'runtime_visibility_verified':False}
    b = _obj(build); i = _obj(install)
    if build is None and install is None:
        return {'status':'preview_prepared','errors':[],'runtime_visibility_verified':False}
    if not _valid_receipt(root, b, 'build') or not _valid_receipt(root, i, 'install'):
        return {'status':'blocked','errors':['valid build and install receipts are required'],'runtime_visibility_verified':False}
    if not i.get('device_id'): return {'status':'blocked','errors':['install receipt has no device_id'],'runtime_visibility_verified':False}
    return {'status':'preview_installed','errors':[],'runtime_visibility_verified':False,
            'device_id':i.get('device_id'),'source_sha256':b.get('source_sha256'),'hap_sha256':b.get('hap_sha256')}

def main(argv=None):
    import argparse, json
    ap=argparse.ArgumentParser(); ap.add_argument('--project-root',required=True); ap.add_argument('--contract',required=True); ap.add_argument('--build'); ap.add_argument('--install'); ap.add_argument('--output')
    ns=ap.parse_args(argv)
    result=check(Path(ns.project_root), json.loads(Path(ns.contract).read_text()), ns.build, ns.install)
    if ns.output: Path(ns.output).write_text(json.dumps(result,ensure_ascii=False,indent=2))
    else: print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result['status'] != 'blocked' else 2
