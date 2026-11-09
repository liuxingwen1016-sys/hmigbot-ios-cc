from __future__ import annotations
import json
from pathlib import Path
SECTION='execute'

def main(argv=None):
    import argparse
    ap=argparse.ArgumentParser(); ap.add_argument('--project-root',required=True); ap.add_argument('--final',action='store_true')
    ns=ap.parse_args(argv); root=Path(ns.project_root); idir=root/'spec/.i2h'
    cov=json.loads((idir/'plan-coverage.json').read_text()); idx=json.loads((idir/'requirements-index.json').read_text())
    claims_path=idir/'impl-claims.json'; claims=json.loads(claims_path.read_text()) if claims_path.exists() else {}
    executed=set(claims.get('executed_packets') or [])
    packets=cov.get('packets') or []
    scope={p.get('packet_id') for p in packets} if ns.final else executed
    claimed={(c.get('packet_id'),c.get('requirement_id')) for c in claims.get('claims') or []}
    findings=[]
    for packet in packets:
        if packet.get('packet_id') not in scope: continue
        for req in packet.get('requirement_ids') or []:
            if (packet.get('packet_id'),req) not in claimed:
                findings.append({'rule':'EXECUTE.REQUIREMENT_UNCLAIMED','subject':req,'packet_id':packet.get('packet_id')})
    out={'sections':{SECTION:{'findings':findings}}}; (idir/'open-findings.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
    return 2 if findings else 0
