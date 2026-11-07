from __future__ import annotations
import json, hashlib
from pathlib import Path
from .stage1_contract import digest, source_digest

def _load(path): return json.loads(Path(path).read_text(encoding='utf-8'))

def prepare(root: Path | str, scope_path: Path | str) -> dict:
    root=Path(root).resolve(); scope_path=Path(scope_path)
    scope=_load(scope_path)
    run_id='run-' + hashlib.sha256((str(scope_path)+scope.get('source_sha256','')).encode()).hexdigest()[:12]
    capture_dir=f'spec/execution/stage1-visual/{run_id}'
    cases=[]
    for unit in scope.get('units',[]):
        for page in unit.get('pages',[]):
            cases.append({'unit_id':unit.get('unit_id'),'page_id':page.get('page_id'),'state_id':page.get('state_id'),
                          'status':'PENDING','capture_dir':capture_dir})
    return {'schema_version':1,'status':'CAPTURE_PENDING','run_id':run_id,'capture_dir':capture_dir,
            'scope_manifest':str(scope_path.relative_to(root) if scope_path.is_relative_to(root) else scope_path),
            'source_sha256':scope.get('source_sha256'),'cases':cases}

def _obj(root, value):
    if isinstance(value, (str,Path)): return _load(root/ value if not Path(value).is_absolute() else Path(value))
    return value

def _receipt_ok(root, value, kind):
    if value is None: return False
    try: d=_obj(root,value)
    except Exception: return False
    if not isinstance(d,dict) or d.get('kind') != kind or d.get('status') != 'PASS': return False
    if d.get('source_sha256') != source_digest(root): return False
    hp=d.get('hap_path'); p=root/hp if isinstance(hp,str) else None
    return p is not None and p.is_file() and d.get('hap_sha256') == digest(p) and (kind!='install' or bool(d.get('device_id')))

def _capture_file(root, case, expected_dir, names):
    """Accept Harmony accessibility JSON while preserving harmony_xml callers."""
    for key in names:
        value = case.get(key)
        if isinstance(value, str) and value.startswith(expected_dir + '/') and (root / value).is_file():
            return key, value
    return None, None

def finalize(root: Path | str, scope_path: Path | str, report: dict) -> dict:
    root=Path(root).resolve(); scope_path=Path(scope_path)
    if report.get('source_sha256') and report['source_sha256'] != source_digest(root):
        raise ValueError('source changed since capture scope was prepared')
    report['fix']='none'
    cases=report.get('cases') or []
    if not cases:
        report['status']='visual_blocked'; report.setdefault('failure_findings',[{'root_cause':'information_gap','detail':'scope has no capture cases'}]); return report
    failed=False; any_diff=False
    for case in cases:
        if case.get('status') == 'DIFF': any_diff=True
        expected_dir=report.get('capture_dir','')
        png_key, png_value = _capture_file(root, case, expected_dir, ('harmony_png', 'target_png', 'harmony_screenshot'))
        ui_key, ui_value = _capture_file(root, case, expected_dir, ('harmony_ui_json', 'harmony_accessibility_json', 'harmony_xml', 'target_ui_json'))
        if png_key is None or ui_key is None:
            failed=True
        if case.get('capture_run_id') != report.get('run_id') or not case.get('device_id'):
            failed=True
        if case.get('observed_page_id') != case.get('page_id') or case.get('observed_state_id') != case.get('state_id'):
            failed=True
        if not case.get('landing_evidence') or not _receipt_ok(root,case.get('build_receipt'),'build') or not _receipt_ok(root,case.get('install_receipt'),'install'):
            failed=True
        try:
            inst = _obj(root, case.get('install_receipt'))
            if case.get('device_id') != inst.get('device_id'): failed=True
        except Exception:
            failed=True
        if not any_diff and not failed:
            png=root/png_value; ui=root/ui_value
            case['harmony_png_sha256']=digest(png)
            case[f'{ui_key}_sha256']=digest(ui)
            case['visibility']='preview_ready'
    if any_diff and not failed: report['status']='DIFF'
    elif failed: report['status']='visual_blocked'; report.setdefault('failure_findings',[{'root_cause':'information_gap','detail':'capture evidence does not match current run'}])
    else: report['status']='PASS'
    return report

def main(argv=None):
    import argparse
    ap=argparse.ArgumentParser(); sub=ap.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare'); p.add_argument('--project-root',required=True); p.add_argument('--scope-manifest',required=True); p.add_argument('--out',required=True)
    f=sub.add_parser('finalize'); f.add_argument('--project-root',required=True); f.add_argument('--scope-manifest',required=True); f.add_argument('--report',required=True)
    ns=ap.parse_args(argv); root=Path(ns.project_root)
    if ns.command=='prepare': result=prepare(root,ns.scope_manifest)
    else:
        rp=Path(ns.report); result=finalize(root,ns.scope_manifest,_load(rp)); rp.write_text(json.dumps(result,ensure_ascii=False,indent=2))
    if ns.command=='prepare': Path(ns.out).write_text(json.dumps(result,ensure_ascii=False,indent=2))
    else: print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result.get('status') in ('PASS','CAPTURE_PENDING','DIFF') else 2
