from __future__ import annotations
import json
from pathlib import Path

def _load(root,p): return json.loads((root/p).read_text())

def build(intent: dict, root: Path | str):
    root=Path(root).resolve(); cov=_load(root,'spec/.i2h/plan-coverage.json'); warns=[]
    mode=intent.get('mode','group'); unconverged=intent.get('fv1_unconverged')
    if unconverged is not None:
        if mode!='final' or not unconverged.get('decision'): raise SystemExit(2)
    orphans=set()
    if unconverged:
        loop=unconverged.get('loop_result'); lp=root/loop if loop else None
        if lp and lp.exists():
            doc=json.loads(lp.read_text()); op=doc.get('detector_json_paths',{}).get('orphans');
            if op and (root/op).exists(): orphans={x.get('file') for x in json.loads((root/op).read_text()).get('orphans',[])}
    claims=[]; implemented=[]; dropped={}
    packets=intent.get('packets') or {}
    for packet in cov.get('packets') or []:
        pid=packet.get('packet_id'); feature=pid.rsplit('-',1)[-1] if '-' in pid else pid
        files=((packets.get(pid) or {}).get('files') or [])
        if orphans and any(f in orphans for f in files):
            dropped[pid]=[f for f in files if f in orphans]; warns.append(f'{pid} has unresolved orphan files; claims withheld')
            continue
        implemented.append(feature)
        for req in packet.get('requirement_ids') or []:
            claims.append({'requirement_id':req,'packet_id':pid,'files':files,
                           'requirement_digest':(packet.get('requirement_digests') or {}).get(req),'attempt':1})
    # Preserve intent ordering and unique feature ids.
    implemented=[x for i,x in enumerate(implemented) if x and x not in implemented[:i]]
    manifest={'impl_claims':{'claims':claims,'executed_packets':sorted({c['packet_id'] for c in claims})},
              'feature_index':{'implemented':implemented},
              'notes':{'fv1_unconverged':{'dropped':dropped}} if unconverged else {}}
    return manifest,warns

def main(argv=None):
    import argparse
    ap=argparse.ArgumentParser(); ap.add_argument('intent'); ap.add_argument('--project-root',required=True); ap.add_argument('--output')
    ns=ap.parse_args(argv); intent=json.loads(Path(ns.intent).read_text()); manifest,warns=build(intent,ns.project_root)
    text=json.dumps(manifest,ensure_ascii=False,indent=2)
    if ns.output: Path(ns.output).write_text(text)
    else: print(text)
    for warning in warns: print('warning:',warning)
    return 0
