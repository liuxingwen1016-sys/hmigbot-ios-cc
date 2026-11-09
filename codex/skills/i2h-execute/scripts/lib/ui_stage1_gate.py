from __future__ import annotations
import json
from pathlib import Path
from .stage1_contract import normalize

def check(root: Path | str, wiring: Path | str) -> dict:
    root=Path(root).resolve(); wiring=Path(wiring)
    errors=[]
    paths=sorted(wiring.glob('*.json')) if wiring.is_dir() else ([wiring] if wiring.exists() else [])
    if not paths: errors.append({'code':'scope_empty','detail':'no wiring manifests'})
    for path in paths:
        try: data=normalize(json.loads(path.read_text(encoding='utf-8')))
        except Exception as exc: errors.append({'code':'contract_invalid','detail':str(exc)}); continue
        for row in data.get('pages',[]):
            p=root/row['output_file']
            if not p.is_file(): errors.append({'code':'output_missing','detail':row['output_file']})
            try: p.resolve().relative_to(root)
            except ValueError: errors.append({'code':'path_escape','detail':row['output_file']})
        if data.get('entry_file') and not (root/data['entry_file']).is_file(): errors.append({'code':'entry_missing','detail':data['entry_file']})
        if data.get('preview_host_file') and not (root/data['preview_host_file']).is_file(): errors.append({'code':'preview_host_missing','detail':data['preview_host_file']})
    return {'status':'PASS' if not errors else 'FAIL','errors':errors,'manifests':[str(p) for p in paths]}

def main(argv=None):
    import argparse
    ap=argparse.ArgumentParser(); ap.add_argument('--project-root',required=True); ap.add_argument('--wiring-dir',required=True); ap.add_argument('--output')
    ns=ap.parse_args(argv); result=check(Path(ns.project_root),ns.wiring_dir)
    text=json.dumps(result,ensure_ascii=False,indent=2)
    if ns.output: Path(ns.output).write_text(text)
    else: print(text)
    return 0 if result['status']=='PASS' else 1
