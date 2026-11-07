from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from .stage1_contract import digest, source_digest, normalize

def _load(path): return json.loads(Path(path).read_text(encoding='utf-8'))

def baseline(root: Path | str, page: dict) -> dict:
    root=Path(root).resolve(); page_id=page.get('page_id'); state=page.get('state_id','normal')
    folder=root/'spec/baseline/ui-snapshots'/str(page_id)
    meta_path=folder/'meta.json'; meta=_load(meta_path) if meta_path.is_file() else {}
    ev=meta.get('runtime_evidence') or {}
    if meta.get('view_xml_synthesized') is True: raise ValueError('runtime baseline is synthesized')
    if not ev:
        # Legacy runtime captures still need an audited state and checksums.
        if meta.get('view_xml_synthesized') is not False: raise ValueError('runtime evidence is missing')
        return {'page_id':page_id,'state_id':state,'path':folder.relative_to(root).as_posix()}
    if ev.get('status') not in ('audited','captured','verified') or ev.get('state') != state:
        raise ValueError('baseline state is not audited')
    png=folder/str(ev.get('png_path','runtime.png')); xml=folder/str(ev.get('view_xml_path','view.xml'))
    if not png.is_file() or not xml.is_file(): raise ValueError('baseline capture is incomplete')
    if ev.get('png_sha256') != digest(png) or ev.get('view_xml_sha256') != digest(xml): raise ValueError('baseline capture changed')
    return {'page_id':page_id,'state_id':state,'path':folder.relative_to(root).as_posix(),
            'png_path':png.relative_to(root).as_posix(),'view_xml_path':xml.relative_to(root).as_posix(),
            'png_sha256':digest(png),'view_xml_sha256':digest(xml)}

def _manifest_files(wiring: Path):
    return sorted(wiring.glob('*.json')) if wiring.is_dir() else [wiring]

def build_scope(wiring: Path | str, root: Path | str) -> dict:
    root=Path(root).resolve(); wiring=Path(wiring)
    units=[]
    for path in _manifest_files(wiring):
        data=normalize(_load(path)); pages=[]
        for page in data.get('pages',[]):
            b=baseline(root,page)
            pages.append({**page,'baseline':b})
        units.append({'unit_id':data.get('unit_id',path.stem),'status':data.get('status'),
                      'entry_file':data.get('entry_file'),'preview_host_file':data.get('preview_host_file'),'pages':pages,
                      'contract_path':path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path)})
    if not units: raise ValueError('empty wiring scope')
    return {'schema_version':1,'status':'READY','source_sha256':source_digest(root),'wiring_dir':str(wiring.relative_to(root) if wiring.is_relative_to(root) else wiring), 'units':units}
