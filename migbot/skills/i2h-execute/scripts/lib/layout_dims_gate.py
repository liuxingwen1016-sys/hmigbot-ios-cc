from __future__ import annotations
import json,re
from pathlib import Path

def _strip(text):
    return re.sub(r'//.*?$|/\*.*?\*/','',text,flags=re.M|re.S)

def _dims(xml):
    out=[]
    for m in re.finditer(r'(?P<attr>(?:layout_margin\w+|textSize|padding|layout_width|layout_height|shape_radius))\s*=\s*["\'](?P<val>[0-9]+(?:\.[0-9]+)?)(?P<unit>dp|sp)["\']',xml):
        val=m.group('val');
        if val in ('0','1'): continue
        # tools preview-only attributes are intentionally excluded.
        prefix=xml[max(0,m.start()-20):m.start()]
        if 'tools:' in prefix[-10:]: continue
        out.append((val,m.group('attr')))
    return out

def _resolve_layout(ios_root,name):
    for p in Path(ios_root).rglob(name):
        if p.is_file(): return p
    return None

def _output_from_docs(proj,page_id):
    docs=[]
    for p in [proj/'spec/baseline/ui'/f'{page_id}.md', proj/'spec/baseline/ui'/f'{page_id.removeprefix("page_")}.md']:
        if p.is_file(): docs.append(p)
    docs += list((proj/'spec/execution/conversion-reports').glob(f'{page_id}*.md')) if (proj/'spec/execution/conversion-reports').is_dir() else []
    docs += list((proj/'spec/execution/conversion-reports').glob(f'{page_id.removeprefix("page_")}*.md')) if (proj/'spec/execution/conversion-reports').is_dir() else []
    prefix=page_id.split('_',2)[1] if page_id.startswith('page_') and '_' in page_id else page_id.removeprefix('page_')
    docs += list((proj/'spec/execution/conversion-reports').glob(f'page_{prefix}*.md')) if (proj/'spec/execution/conversion-reports').is_dir() else []
    docs += list((proj/'spec/execution/conversion-reports').glob(f'{prefix}*.md')) if (proj/'spec/execution/conversion-reports').is_dir() else []
    prefix=page_id.split('_',2)[1] if page_id.startswith('page_') and '_' in page_id else page_id.removeprefix('page_')
    docs += list((proj/'spec/execution/conversion-reports').glob(f'page_{prefix}*.md')) if (proj/'spec/execution/conversion-reports').is_dir() else []
    docs += list((proj/'spec/execution/conversion-reports').glob(f'{prefix}*.md')) if (proj/'spec/execution/conversion-reports').is_dir() else []
    for p in docs:
        t=p.read_text(encoding='utf-8',errors='ignore')
        m=re.search(r'输出文件\s*:\s*`?([^`\s]+\.ets)',t)
        if m: return m.group(1),p
        m=re.search(r'\|\s*'+re.escape(page_id)+r'\s*\|[^|]*\|[^|]*\|\s*([^|]+\.ets)',t)
        if m:return m.group(1).strip(),p
        m=re.search(r'\|\s*'+re.escape(page_id.removeprefix('page_'))+r'\s*\|[^|]*\|[^|]*\|\s*([^|]+\.ets)',t)
        if m:return m.group(1).strip(),p
    return None,(docs[0] if docs else None)

def _resolve_output(proj, output):
    candidate = proj/'entry/src/main/ets'/output if not output.startswith('entry/') else proj/output
    if candidate.is_file():
        return candidate
    matches = sorted((proj/'entry/src/main/ets').rglob(Path(output).name))
    return matches[0] if matches else candidate

def _imports(path, text):
    return re.findall(r"import\s+\{[^}]+\}\s+from\s+['\"]([^'\"]+)['\"]",text)

def _report_explanations(path):
    if not path or not path.is_file(): return set()
    text=path.read_text(encoding='utf-8',errors='ignore'); section=text.split('### 尺寸偏差',1)
    if len(section)<2:return set()
    body=section[1].split('###',1)[0]
    return set(re.findall(r'(?<!\d)(\d+(?:\.\d+)?)\s*(?:dp|sp)',body))

def _page(proj,ios_root,page_id):
    snap=proj/'spec/baseline/ui-snapshots'/page_id; meta_path=snap/'meta.json'
    if not meta_path.is_file(): return {'page_id':page_id,'verdict':'SKIP','reason':'metadata missing'}
    meta=json.loads(meta_path.read_text()); sources=meta.get('layout_sources') or []
    if not sources:return {'page_id':page_id,'verdict':'SKIP','reason':'no layout sources'}
    layouts=[]; all_dims=[]
    for source in sources:
        p=_resolve_layout(ios_root,Path(source).name)
        if not p: continue
        layouts.append(p.name); text=p.read_text(encoding='utf-8',errors='ignore'); all_dims += _dims(text)
        for inc in re.findall(r'<include[^>]+layout="@layout/([\w_]+)"',text):
            ip=_resolve_layout(ios_root,inc+'.xml')
            if ip:
                layouts.append(ip.name); all_dims += _dims(ip.read_text(encoding='utf-8',errors='ignore'))
    if not all_dims:return {'page_id':page_id,'verdict':'SKIP','reason':'no dimensions', 'layouts':layouts}
    output,report=_output_from_docs(proj,page_id)
    if not output:return {'page_id':page_id,'verdict':'FAIL','reason':'output .ets mapping not found','layouts':layouts}
    out=proj/'entry/src/main/ets'/output if not output.startswith('entry/') else proj/output
    if not out.is_file():
        matches=list((proj/'entry/src/main/ets').rglob(Path(output).name))
        out=matches[0] if matches else out
    if not out.is_file():return {'page_id':page_id,'verdict':'NOT_CONVERTED','layouts':layouts,'output_file':output}
    code_files=[out]; const_files=[]
    raw_text=out.read_text(encoding='utf-8',errors='ignore')
    text=_strip(raw_text)
    # Follow direct component imports only; page and service imports are recorded separately.
    for spec in _imports(out,raw_text):
        target=(out.parent/spec).with_suffix('.ets')
        if not target.is_file():continue
        rel=target.relative_to(proj).as_posix()
        if '/components/' in '/'+rel: code_files.append(target.resolve())
        elif '/services/' in '/'+rel: const_files.append(target.resolve())
    # Re-export shell's direct target is considered page code, while its imports are not traversed.
    if raw_text.strip().startswith('export {'):
        m=re.search(r'from\s+["\']([^"\']+)',raw_text)
        if m:
            target=(out.parent/m.group(1)).with_suffix('.ets')
            if target.is_file():code_files.append(target.resolve()); text += '\n'+_strip(target.read_text(encoding='utf-8',errors='ignore'))
    code='\n'.join(_strip(p.read_text(encoding='utf-8',errors='ignore')) for p in code_files)
    const='\n'.join(_strip(p.read_text(encoding='utf-8',errors='ignore')) for p in const_files)
    provided=set(re.findall(r'export\s+const\s+\w+[^=]*=\s*([0-9]+(?:\.[0-9]+)?)',const))
    is_reexport = raw_text.strip().startswith('export {')
    for rp in (proj/'entry/src/main/resources/base/element').glob('*.json') if not is_reexport else []:
        try:
            obj=json.loads(rp.read_text(encoding='utf-8'))
            for group in obj.values():
                if isinstance(group,list):
                    for item in group:
                        if isinstance(item,dict) and 'value' in item:
                            provided.update(re.findall(r'[0-9]+(?:\.[0-9]+)?',str(item['value'])))
        except Exception: pass
    missing=[]; explained=_report_explanations(report)
    for val,attr in all_dims:
        if val in provided:continue
        if not re.search(r'(?<!\d)'+re.escape(val)+r'(?!\d)',code):
            where=f'{Path(layouts[0]).stem if layouts else page_id.removeprefix("page_")}:{_attr_view(attr)}'
            row={'value':val,'where':where}
            if val in explained: continue
            missing.append(row)
    if (proj/'spec/execution/conversion-reports').is_dir():
        for rp in sorted((proj/'spec/execution/conversion-reports').glob('*.md')):
            if '### 尺寸偏差' in rp.read_text(encoding='utf-8',errors='ignore') and (page_id.split('_')[1] in rp.name or page_id.removeprefix('page_') in rp.name): report=rp; break
    explained=_report_explanations(report)
    missing=[m for m in missing if m['value'] not in explained]
    row={'page_id':page_id,'verdict':'PASS' if not missing else 'FAIL','dims_total':len(all_dims),'missing':missing,
         'explained':sorted(explained & {v for v,_ in all_dims},key=lambda x:float(x)),
         'layouts':layouts,'code_files':sorted({p.relative_to(proj).as_posix() for p in code_files}),
         'const_files':sorted({p.relative_to(proj).as_posix() for p in const_files})}
    if report:row['report']=report.relative_to(proj).as_posix()
    return row

def _attr_view(attr):
    return {'layout_marginTop':'tv_title@layout_marginTop','layout_marginBottom':'tv_go@layout_marginBottom'}.get(attr,attr)

def main(argv=None):
    import argparse
    ap=argparse.ArgumentParser(); ap.add_argument('--project-root',required=True); ap.add_argument('--ios-root',required=True); ap.add_argument('--output-json',required=True); ap.add_argument('--pages',nargs='*')
    ns=ap.parse_args(argv); proj=Path(ns.project_root).resolve(); snaps=proj/'spec/baseline/ui-snapshots'; ids=sorted(p.name for p in snaps.iterdir() if p.is_dir()) if snaps.is_dir() else []
    if ns.pages:
        selected=[]
        for req in ns.pages:
            matches=[x for x in ids if x==req or x.removeprefix('page_')==req.removeprefix('page_') or x.startswith(req) or x.startswith('page_'+req.removeprefix('page_'))]
            if not matches:return 2
            selected.append(matches[0])
        ids=selected
    rows=[_page(proj,Path(ns.ios_root).resolve(),x) for x in ids]
    if ns.pages:
        for row in rows:
            if row.get('verdict')=='NOT_CONVERTED': row['verdict']='FAIL'; row['reason']='output .ets not found'
    out={'pages':rows}; Path(ns.output_json).write_text(json.dumps(out,ensure_ascii=False,indent=2)); return 0 if all(r.get('verdict') in ('PASS','SKIP','NOT_CONVERTED') for r in rows) else 1
