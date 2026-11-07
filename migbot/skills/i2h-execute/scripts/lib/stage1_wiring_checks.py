from __future__ import annotations
import json,re
from pathlib import Path
from .stage1_contract import digest, source_digest

def _strip(text):
    text=re.sub(r'//.*?$|/\*.*?\*/','',text,flags=re.M|re.S)
    return re.sub(r"(['\"])(?:\\.|(?!\1).)*\1", "''", text, flags=re.S)

def _method(text, symbol):
    name=symbol.split('.')[-1]
    # Match a declaration, never a `this.foo()` call in an earlier method.
    m=re.search(r'(?<![\w.])'+re.escape(name)+r'\s*\([^)]*\)\s*\{',text)
    if not m:return ''
    i=m.end(); depth=1
    while i<len(text) and depth:
        if text[i]=='{':depth+=1
        elif text[i]=='}':depth-=1
        i+=1
    return text[m.end():i-1]

def check_requirements(root: Path | str, contract_path: Path | str) -> dict:
    root=Path(root).resolve(); cp=Path(contract_path); contract=json.loads(cp.read_text(encoding='utf-8'))
    errors=[]
    ledger=root/'spec/decision-ledger.md'
    if ledger.exists():
        m=re.search(r'contract_sha256.{0,100}?([0-9a-f]{64})',ledger.read_text(encoding='utf-8'),re.I)
        if m and m.group(1) != digest(cp).split(':', 1)[-1]:
            errors.append({'id':'frozen','reason':'frozen contract digest does not match current contract'})
    files={}
    for p in root.rglob('*.ets'):
        files[p.relative_to(root).as_posix()]=_strip(p.read_text(encoding='utf-8',errors='ignore'))
    for req in contract.get('required_mounts',[]):
        rid=req.get('id','mount'); owner=req.get('owner_file'); comp=req.get('component_file')
        text=files.get(owner,''); ctext=files.get(comp,'')
        ok=True; reason=''
        if not text or not ctext: ok=False; reason='source file missing'
        # Component must be imported under the binding used by its call.
        symbol=req.get('component_symbol','').split('.')[-1]; bound=symbol
        im=re.search(r'import\s*\{([^}]*)\}\s*from\s*[\'\"](?:\./)?[^\'\"]*[\'\"]',text)
        imports=[]
        if im:
            for item in im.group(1).split(','):
                parts=item.strip().split()
                if parts: imports.append((parts[0],parts[-1] if len(parts)>=3 and parts[-2]=='as' else parts[0]))
            for original,alias in imports:
                if original==symbol: bound=alias
        owner_method=_method(text,req.get('owner_symbol',''))
        if not imports or not any(original==symbol for original,alias in imports): ok=False; reason='required component import is not bound'
        if not re.search(r'\b'+re.escape(bound)+r'\s*\(',owner_method): ok=False; reason='required component is not mounted from reachable builder'
        # Invocation of a builder itself must be present in the parent render body.
        builder=req.get('owner_symbol','').split('.')[-1]
        if builder and not re.search(r'\bthis\s*\.\s*'+re.escape(builder)+r'\s*\(',text): ok=False; reason='required builder is not called'
        if not ok: errors.append({'id':rid,'reason':reason or 'required mount unresolved'})
    for req in contract.get('required_actions',[]):
        rid=req.get('id','action'); text=files.get(req.get('owner_file'),''); method=_method(text,req.get('owner_symbol',''))
        effect=req.get('effect_call','')
        effect_ok=bool(method and effect in method)
        if not effect_ok and method:
            for called in re.findall(r'\bthis\.([A-Za-z_]\w*)\s*\(',method):
                if effect in _method(text,called): effect_ok=True; break
        ok=bool(text and method and effect_ok and not re.search(r"console\.info\([^)]*"+re.escape(effect),method))
        # A handler is only proven when owner method is referenced by a click/action binding.
        handler=req.get('owner_symbol','').split('.')[-1]
        if not re.search(r'\bthis\s*\.\s*'+re.escape(handler)+r'\s*\(',text): ok=False
        if not ok: errors.append({'id':rid,'reason':'required action effect is not bound or resolved'})
    return {'status':'PASS' if not errors else 'FAIL','errors':errors,'source_sha256':source_digest(root)}

def assert_case(layout: dict, case: dict):
    def walk(node, visible=True):
        attrs=node.get('attributes',{}); now=visible and str(attrs.get('visible','true')).lower()!='false'
        yield node,now
        for child in node.get('children',[]): yield from walk(child,now)
    nodes=list(walk(layout)); visible=[n for n,v in nodes if v]
    # A tab label is navigation chrome, not proof that the selected page
    # content rendered. Exclude text beneath TabBar for content assertions.
    def content_nodes(node, visible=True, inside_tab=False):
        attrs=node.get('attributes', {})
        visible = visible and str(attrs.get('visible', 'true')).lower() != 'false'
        in_tab = inside_tab or attrs.get('type') == 'TabBar'
        if visible and not in_tab:
            yield node
        for child in node.get('children', []):
            yield from content_nodes(child, visible, in_tab)
    texts={str(n.get('attributes',{}).get('text','')) for n in content_nodes(layout)}
    for wanted in case.get('content_text',[]):
        if wanted not in texts: raise ValueError(f'content not visible: {wanted}')
    selected=case.get('selected_tab')
    if selected:
        def subtree_text(node):
            vals=[str(node.get('attributes',{}).get('text',''))]
            for ch in node.get('children',[]): vals += subtree_text(ch)
            return vals
        if not any(n.get('attributes',{}).get('selected') in (True,'true','1') and selected in subtree_text(n) for n,v in nodes if v): raise ValueError('wrong selected tab')
    has_tab=any(n.get('attributes',{}).get('type')=='TabBar' for n in visible)
    if case.get('no_tab_bar') and has_tab: raise ValueError('tab bar unexpectedly present')

def main(argv=None):
    import argparse
    ap=argparse.ArgumentParser(); ap.add_argument('--project-root',required=True); ap.add_argument('--contract',required=True); ap.add_argument('--output')
    ns=ap.parse_args(argv); result=check_requirements(ns.project_root,ns.contract); print(json.dumps(result,ensure_ascii=False,indent=2)); return 0 if result['status']=='PASS' else 1
