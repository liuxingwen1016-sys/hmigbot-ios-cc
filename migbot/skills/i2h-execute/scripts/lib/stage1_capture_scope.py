from __future__ import annotations
import json, hashlib
from pathlib import Path
from .stage1_contract import digest, source_digest

def _load(path): return json.loads(Path(path).read_text(encoding='utf-8'))

def _current_scope(root, scope):
    """The approved project, not a caller-editable schema tag, selects the contract."""
    from .ios_stage1_scope import build_scope_from_inventory, inventory_path
    config_path=root/'.migbot/config.json'
    config=_load(config_path) if config_path.is_file() else {}
    contract=config.get('native_visual_observation')
    if contract not in (None, 'native-page-state-v2'):
        raise ValueError('unsupported configured native visual observation contract')
    current_ios=(scope.get('schema_version') == 2 or 'pairs' in scope
                 or inventory_path(root,None).is_file() or contract is not None)
    if not current_ios:
        return scope,False,config
    canonical=build_scope_from_inventory(root,None)
    if scope != canonical:
        raise ValueError('capture scope differs from current approved inventory')
    return canonical,True,config

def prepare(root: Path | str, scope_path: Path | str) -> dict:
    root=Path(root).resolve(); scope_path=Path(scope_path)
    scope=_load(scope_path)
    scope, _, _ = _current_scope(root,scope)
    run_id='run-' + hashlib.sha256((str(scope_path)+scope.get('source_sha256','')).encode()).hexdigest()[:12]
    capture_dir=f'spec/execution/stage1-visual/{run_id}'
    cases=[]
    if scope.get('schema_version') == 2:
        cases = [{key: pair.get(key) for key in ('pair_id', 'unit_id', 'page_id', 'state_id')}
                 | {'status': 'PENDING', 'capture_dir': capture_dir} for pair in scope.get('pairs', [])]
    for unit in scope.get('units',[]) if scope.get('schema_version') != 2 else []:
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
            if not (root/value).resolve().is_relative_to((root/expected_dir).resolve()):
                continue
            return key, value
    return None, None

def finalize(root: Path | str, scope_path: Path | str, report: dict) -> dict:
    root=Path(root).resolve(); scope_path=Path(scope_path)
    scope=_load(scope_path)
    try:
        canonical,strict_scope,config=_current_scope(root,scope)
    except (OSError,ValueError,KeyError,TypeError) as error:
        report.update(status='visual_blocked',fix='none',failure_findings=[{
            'root_cause':'stale_capture_scope','detail':str(error)}])
        return report
    approved = {p['pair_id']: p for p in canonical.get('pairs', [])}
    seen_pairs = set()
    installations = set()
    if report.get('source_sha256') and report['source_sha256'] != source_digest(root):
        raise ValueError('source changed since capture scope was prepared')
    report['fix']='none'
    cases=report.get('cases') or []
    if not cases:
        report['status']='visual_blocked'; report.setdefault('failure_findings',[{'root_cause':'information_gap','detail':'scope has no capture cases'}]); return report
    failed=strict_scope and canonical.get('status') != 'READY'; any_diff=False
    for case in cases:
        if case.get('status') == 'DIFF': any_diff=True
        expected_dir=report.get('capture_dir','')
        png_key, png_value = _capture_file(root, case, expected_dir, ('harmony_png', 'target_png', 'harmony_screenshot'))
        ui_key, ui_value = _capture_file(root, case, expected_dir, ('harmony_ui_json', 'harmony_accessibility_json', 'harmony_xml', 'target_ui_json'))
        if png_key is None or ui_key is None:
            failed=True
        if case.get('capture_run_id') != report.get('run_id') or not case.get('device_id'):
            failed=True
        expected=approved.get(case.get('pair_id'), {})
        if strict_scope:
            if (not expected or case.get('pair_id') in seen_pairs
                    or (case.get('page_id'), case.get('state_id')) != (expected.get('page_id'), expected.get('state_id'))):
                failed=True
                case['arrival_issue']='capture case must bind one unique approved pair_id'
            seen_pairs.add(case.get('pair_id'))
        predicate=expected.get('target_observation')
        observation=case.get('page_state_observation')
        if predicate is not None or observation is not None or config.get('native_visual_observation'):
            try:
                import sys
                sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'i2h-plan/scripts'))
                from native_scenario_evidence import observe_state
                from .ios_stage1_visual_gate import checked_install_bundle
                if predicate is None or ui_value is None:
                    raise ValueError('approved target page/state predicate or captured tree missing')
                if (case.get('declared_page_id'),case.get('declared_state_id')) != (case.get('page_id'),case.get('state_id')):
                    raise ValueError('declared page/state differs from approved capture case')
                from .ios_ui_dispatch import digest as normalize_digest
                if case.get('status') not in ('READY','PASS','DIFF'):
                    raise ValueError('strict capture case has not successfully reached its state')
                if not (root/expected_dir).resolve().is_relative_to(root/'spec/execution/stage1-visual'):
                    raise ValueError('strict capture directory must belong to this project run')
                if png_value is None:
                    raise ValueError('strict capture screenshot missing')
                png_file=root/png_value
                image=png_file.read_bytes()
                if (not image.startswith((b'\x89PNG\r\n\x1a\n',b'\xff\xd8\xff'))
                        or normalize_digest(case.get('harmony_png_sha256')) != normalize_digest(digest(image))):
                    raise ValueError('strict capture screenshot is missing its captured SHA or has changed')
                build_receipt=_obj(root,case.get('build_receipt'))
                install_receipt=_obj(root,case.get('install_receipt'))
                scope_hash=normalize_digest(digest(scope_path))
                if any(not isinstance(receipt,dict) or normalize_digest(receipt.get('scope_sha256')) != scope_hash
                       for receipt in (build_receipt,install_receipt)):
                    raise ValueError('strict build/install receipts refer to another scope')
                tree_path=root/ui_value
                checked_install_bundle(root,build_receipt,install_receipt,predicate)
                installations.add((normalize_digest(build_receipt['hap_sha256']),install_receipt.get('device_id')))
                before_path=case.get('pre_capture_tree')
                if _capture_file(root,case,expected_dir,('pre_capture_tree',))[0] is None:
                    raise ValueError('strict capture lacks pre-capture tree in current run')
                before_file=root/before_path
                before={**observe_state(_load(before_file),predicate),'layout_sha256':digest(before_file).removeprefix('sha256:')}
                if case.get('pre_capture_observation') != before:
                    raise ValueError('pre-capture observation differs from approved predicate')
                actual={**observe_state(_load(tree_path),predicate),'layout_sha256':digest(tree_path).removeprefix('sha256:')}
                if before['active_layer'] != actual['active_layer']:
                    raise ValueError('active native layer changed during screenshot')
                if observation != actual:
                    raise ValueError('native observation differs from captured tree')
            except (OSError, ValueError, KeyError, TypeError) as error:
                failed=True
                case['arrival_issue']=str(error)
        elif case.get('observed_page_id') != case.get('page_id') or case.get('observed_state_id') != case.get('state_id'):
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
    if strict_scope and len(installations) != 1:
        failed=True
    if strict_scope and seen_pairs != set(approved):
        failed=True
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
    if ns.command=='prepare':
        try:
            result=prepare(root,ns.scope_manifest)
        except (OSError,ValueError,KeyError,TypeError) as exc:
            result={'status':'visual_blocked','fix':'none','failure_findings':[
                {'root_cause':'stale_capture_scope','detail':str(exc)}]}
    else:
        rp=Path(ns.report)
        report=_load(rp)
        try:
            result=finalize(root,ns.scope_manifest,report)
        except ValueError as exc:
            # A changed source invalidates the capture scope, but the CLI must
            # still persist a blocked report so callers retain the evidence
            # paths and can diagnose the stale run without parsing stderr.
            result=report
            result['status']='visual_blocked'
            result['fix']='none'
            findings=result.setdefault('failure_findings',[])
            findings.append({'root_cause':'stale_capture_scope','detail':str(exc)})
        rp.write_text(json.dumps(result,ensure_ascii=False,indent=2))
    if ns.command=='prepare': Path(ns.out).write_text(json.dumps(result,ensure_ascii=False,indent=2))
    else: print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result.get('status') in ('PASS','CAPTURE_PENDING','DIFF') else 2
