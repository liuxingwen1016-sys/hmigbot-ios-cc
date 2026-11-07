from __future__ import annotations
import json
from pathlib import Path

def check(root: Path | str, pages: list[dict], policy='runtime', facts=None) -> dict:
    root=Path(root).resolve(); fallbacks=[]; errors=[]
    canonical=(root/'spec/.i2h/target-input.json').is_file() and all((root/'spec/baseline/res-index'/f'{n}.json').is_file() for n in ('values','drawables','usage','design-tokens'))
    for page in pages:
        snap=root/'spec/baseline/ui-snapshots'/page['page_id']; vp=snap/'view.xml'; mp=snap/'meta.json'
        meta=json.loads(mp.read_text()) if mp.exists() else {}
        synthetic=meta.get('view_xml_synthesized') is True
        runtime_captured=not synthetic
        fallback={'page_id':page['page_id'],'runtime_captured':runtime_captured}
        if synthetic: fallback['reason']=meta.get('fallback_reason')
        fallbacks.append(fallback)
        if facts=='static-v1' and not canonical: errors.append('canonical static-v1 inputs missing')
        elif policy=='runtime' and synthetic: errors.append('runtime capture required')
        elif policy=='progressive' and synthetic and not (meta.get('fallback_reason') and 'evidence:' in meta.get('fallback_reason','')): errors.append('failed capture evidence required')
        elif policy=='source_only' and not synthetic: errors.append('source-only cannot use real runtime XML as evidence')
    if facts in ('legacy','static-v1-shadow'): errors=[]
    return {'status':'pass' if not errors else 'fail','errors':errors,'source_fallbacks':fallbacks,'policy':policy,'facts':facts}

def main(argv=None):
    import argparse
    ap=argparse.ArgumentParser(); ap.add_argument('--project-root',required=True); ap.add_argument('--pages',required=True); ap.add_argument('--policy',default='runtime'); ap.add_argument('--facts')
    ns=ap.parse_args(argv); result=check(ns.project_root,json.loads(Path(ns.pages).read_text()),ns.policy,ns.facts); print(json.dumps(result,ensure_ascii=False,indent=2)); return 0 if result['status']=='pass' else 1
