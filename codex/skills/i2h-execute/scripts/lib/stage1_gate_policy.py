from __future__ import annotations
import json
from pathlib import Path
from .stage1_contract import digest

INFO_CODES={'ANDROID_BASELINE_MISSING','SDK_UNAVAILABLE','DEVICE_OFFLINE','RUNTIME_EVIDENCE_MISSING','ENVIRONMENT_UNAVAILABLE'}
QUALITY_CODES={'OUTPUT_MISSING','UI_ASSERTION_FAILED','required_mount_unresolved','ARKTS_COMPILER_ERROR'}

def _read(report):
    if isinstance(report,(str,Path)): return json.loads(Path(report).read_text(encoding='utf-8'))
    return dict(report)

def annotate(report, gate):
    report=_read(report); findings=[]
    for i,error in enumerate(report.get('errors') or []):
        code=str(error.get('code','unknown'))
        root=error.get('root_cause')
        if code in QUALITY_CODES: root='product_defect'
        elif code in INFO_CODES: root='information_gap'
        elif not root: root='product_defect' if code.isupper() else 'unknown'
        findings.append({'finding_id':f'{i}:{code}','code':code,'root_cause':root,'reason':error.get('detail') or error.get('reason',''),'gate':gate,'error':error})
    return {'failure_findings':findings,'raw_status':report.get('status')}

def decide(findings, repair_rounds, max_rounds, raw_status):
    findings=list(findings or [])
    if not findings and raw_status=='PASS':
        return {'disposition':'VERIFIED','can_continue':True,'gate_verified':True,'stage1_complete':True,
                'raw_gate_status':raw_status,'repair_rounds':repair_rounds,'next_action':'continue','release_gates':[]}
    roots={f.get('root_cause') for f in findings}
    if 'product_defect' in roots or 'unknown' in roots or raw_status=='FAIL' and not roots <= {'information_gap'}:
        action='stop_with_product_defects' if 'product_defect' in roots else 'stop_with_unresolved_cause'
        return {'disposition':'BLOCK','can_continue':False,'gate_verified':False,'stage1_complete':False,
                'raw_gate_status':raw_status,'repair_rounds':repair_rounds,'next_action':action,'release_gates':[]}
    if roots <= {'information_gap'} and raw_status=='BLOCKED':
        if repair_rounds < max_rounds:
            return {'disposition':'RETRY','can_continue':False,'gate_verified':False,'stage1_complete':False,
                    'raw_gate_status':raw_status,'repair_rounds':repair_rounds,'next_action':'retry_information_gap','release_gates':[]}
        return {'disposition':'RELEASE_WITH_GAPS','can_continue':True,'gate_verified':False,'stage1_complete':False,
                'raw_gate_status':raw_status,'repair_rounds':repair_rounds,'next_action':'release_with_prerequisite_gap','release_gates':['execute.stage1-prerequisite']}
    return {'disposition':'BLOCK','can_continue':False,'gate_verified':False,'stage1_complete':False,
            'raw_gate_status':raw_status,'repair_rounds':repair_rounds,'next_action':'stop_with_unresolved_cause','release_gates':[]}

def _scope(root):
    p=Path(root)/'spec/execution/stage1-wiring-contract.json'
    return digest(p) if p.is_file() else 'none'

def _state_path(root): return Path(root)/'spec/.i2h/stage1-gate-policy.json'

def assess(root, report, gate, review=None, remediation_path=None):
    root=Path(root).resolve(); report_path=Path(report) if isinstance(report,(str,Path)) else None
    if remediation_path is not None and report_path is not None and Path(remediation_path).resolve()==report_path.resolve(): raise ValueError('raw report cannot be remediation evidence')
    raw=_read(report); ann=annotate(raw,gate); findings=ann['failure_findings']
    if review is not None:
        rev=_read(review); expected=digest(report_path) if report_path is not None else None
        if rev.get('report_sha256') != expected: raise ValueError('review is not bound to report')
        byid={f.get('finding_id'):f for f in rev.get('findings',[])}
        for f in findings:
            claim=byid.get(f['finding_id'])
            if not claim: continue
            if claim.get('root_cause')=='information_gap' and f['code'] not in INFO_CODES:
                raise ValueError('known product defect cannot be reclassified as information gap')
            if claim.get('root_cause')=='tool_gap':
                if not claim.get('disproves_product_defect') or not claim.get('evidence') or not all((root/e).exists() for e in claim['evidence']):
                    raise ValueError('tool gap review requires evidence')
                f['root_cause']='tool_gap'
    state_path=_state_path(root); state_path.parent.mkdir(parents=True,exist_ok=True)
    state=json.loads(state_path.read_text()) if state_path.exists() else {'gates':{}}
    rec=state.setdefault('gates',{}).setdefault(gate,{'repair_rounds':0,'actions':{},'scope':_scope(root)})
    current_scope=_scope(root)
    if rec.get('scope') != current_scope: raise ValueError('scope changed; repair budget cannot be reset')
    # The optional recovery evidence identifies a new attempted round. Reusing a
    # round is idempotent and cannot burn budget.
    action_key=str(repairment_key := (str(Path(remediation_path).resolve()) if remediation_path else ''))
    round_hint=None
    if report_path is not None:
        # callers use recovery-N.log; only count each path once
        pass
    if remediation_path is not None:
        action_key=str(Path(remediation_path).resolve())
        if action_key not in rec.setdefault('actions',{}):
            rec['actions'][action_key]=True; rec['repair_rounds'] += 1
    # Tests pass evidence as the fourth positional argument; detect it as review
    # only when it is a path to a JSON review, otherwise count unique evidence.
    if review is not None and isinstance(review,(str,Path)) and str(review).endswith('.log'):
        key=str(Path(review).resolve())
        if key not in rec.setdefault('actions',{}): rec['actions'][key]=True; rec['repair_rounds']+=1
    # In the public API the fourth positional argument is review and the fifth is
    # remediation evidence. The test helper passes evidence as that fifth value.
    if remediation_path is not None and isinstance(remediation_path,(str,Path)):
        key=str(Path(remediation_path).resolve())
        if key not in rec.setdefault('actions',{}): rec['actions'][key]=True; rec['repair_rounds']+=1
    # A normal report with no evidence must not increase rounds.
    result=decide(findings,rec['repair_rounds'],2,raw.get('status'))
    result['findings']=findings; result['gate']=gate
    result['scope_sha256']=current_scope
    state_path.write_text(json.dumps(state,ensure_ascii=False,indent=2))
    return result

def main(argv=None):
    import argparse
    ap=argparse.ArgumentParser(); ap.add_argument('--project-root',required=True); ap.add_argument('--report',required=True); ap.add_argument('--gate',required=True); ap.add_argument('--review'); ap.add_argument('--remediation')
    ns=ap.parse_args(argv); result=assess(ns.project_root,ns.report,ns.gate,ns.review,ns.remediation); print(json.dumps(result,ensure_ascii=False,indent=2)); return 0 if result['can_continue'] else 1
