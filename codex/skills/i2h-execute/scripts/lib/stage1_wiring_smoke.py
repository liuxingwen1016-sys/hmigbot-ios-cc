from __future__ import annotations
import json, subprocess, tempfile, time
from pathlib import Path
from .stage1_contract import digest, source_digest
from .stage1_wiring_checks import check_requirements, assert_case

def _load(root,v):
    if isinstance(v,(str,Path)): return json.loads(Path(v).read_text())
    return v

def run(root: Path | str, contract_path: Path | str, build=None, install=None, hdc='hdc'):
    root=Path(root).resolve(); static=check_requirements(root,contract_path)
    if static['status']!='PASS': return {'status':'FAIL','errors':static['errors'],'failure_findings':[{'root_cause':'product_defect'}]}, None
    b=_load(root,build) if build is not None else None; i=_load(root,install) if install is not None else None
    def valid(d,kind):
        if not isinstance(d,dict) or d.get('kind')!=kind or d.get('status')!='PASS' or d.get('source_sha256')!=source_digest(root): return False
        p=root/d.get('hap_path','')
        return p.is_file() and d.get('hap_sha256')==digest(p)
    if not valid(b,'build') or not valid(i,'install'):
        return {'status':'BLOCKED','failure_findings':[{'root_cause':'unknown','detail':'stale or missing build/install receipt'}]}, None
    device=i.get('device_id'); folder=root/'spec/execution/stage1-wiring-runs'/('run-'+str(int(time.time()*1000))); folder.mkdir(parents=True,exist_ok=True)
    subprocess.run([hdc,'-t',device,'install',str(root/b['hap_path'])],capture_output=True,text=True)
    dump=folder/'dump.json'; png=folder/'screen.png'
    subprocess.run([hdc,'-t',device,'file','recv','/data/local/tmp/view.json',str(dump)],capture_output=True,text=True)
    subprocess.run([hdc,'-t',device,'file','recv','/data/local/tmp/screen.png',str(png)],capture_output=True,text=True)
    if not dump.is_file() or not png.is_file():
        report={'status':'BLOCKED','device_id':device,'failure_findings':[{'root_cause':'environment_gap'}]}; (folder/'report.json').write_text(json.dumps(report)); return report,folder
    layout=json.loads(dump.read_text())
    contract=json.loads(Path(contract_path).read_text());
    try:
        for case in contract.get('runtime_cases',[]): assert_case(layout,case)
    except ValueError as exc:
        report={'status':'FAIL','device_id':device,'errors':[{'id':'runtime_case','reason':str(exc)}]}; (folder/'report.json').write_text(json.dumps(report)); return report,folder
    report={'status':'PASS','device_id':device,'source_sha256':source_digest(root),'dump_sha256':digest(dump),'screen_sha256':digest(png),
            'cases':[{'id':c.get('id'),'status':'PASS','dump_sha256':digest(dump),'screen_sha256':digest(png)} for c in contract.get('runtime_cases',[])]}
    (folder/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)); return report,folder
