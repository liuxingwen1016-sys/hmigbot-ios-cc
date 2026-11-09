from __future__ import annotations
import re
from pathlib import Path
from .stage1_contract import normalize

_IMPORT_RE = re.compile(r"(?:import|export)\s+(?:[^;]*?\s+from\s+)?['\"]([^'\"]+)['\"]")
_LOAD_RE = re.compile(r"loadContent\(\s*['\"]([^'\"]+)['\"]")

def _resolve(root: Path, owner: Path, spec: str) -> Path | None:
    if spec.startswith("."):
        base = (owner.parent / spec)
    elif spec.startswith("/"):
        return None
    else:
        # ArkTS package imports are outside the product graph.
        return None
    if base.suffix:
        candidates = [base]
    else:
        candidates = [base.with_suffix(".ets"), base / "index.ets"]
    for p in candidates:
        try:
            p.relative_to(root)
        except ValueError:
            continue
        if p.is_file(): return p.resolve()
    return None

def _entry_from_ability(root: Path) -> str | None:
    for p in root.rglob("EntryAbility.ets"):
        text = p.read_text(encoding="utf-8", errors="ignore")
        m = _LOAD_RE.search(text)
        if m:
            page = m.group(1)
            rel = Path("entry/src/main/ets") / (page + (".ets" if not page.endswith(".ets") else ""))
            if (root / rel).is_file(): return rel.as_posix()
    return None

def check(root: Path | str, contract: dict) -> dict:
    root = Path(root).resolve()
    try: data = normalize(contract)
    except ValueError as exc: return {"gate":"FAIL", "errors":[str(exc)], "missing":[], "unreachable":[], "reachable":[], "analysis":[]}
    errors=[]; missing=[]; unreachable=[]; reachable=[]
    entry = data.get("entry_file") or _entry_from_ability(root)
    if not entry:
        errors.append("entry_file is required; no EntryAbility loadContent entry was found")
    entry_path = root / entry if entry else None
    if entry_path is not None and not entry_path.is_file(): missing.append(entry)
    graph: set[Path] = set(); queue = [entry_path] if entry_path and entry_path.is_file() else []
    while queue:
        p = queue.pop()
        p = p.resolve()
        if p in graph: continue
        graph.add(p); reachable.append(p.relative_to(root).as_posix())
        text = p.read_text(encoding="utf-8", errors="ignore")
        # Remove comments before identifying imports. Keep a marker that this is source-only analysis.
        clean = re.sub(r"//.*?$|/\*.*?\*/", "", text, flags=re.M|re.S)
        for spec in _IMPORT_RE.findall(clean):
            q = _resolve(root, p, spec)
            if q is not None: queue.append(q)
    targets = list(data.get("target_files") or []) + [p.get("output_file") for p in data.get("pages", [])]
    targets = [x for i,x in enumerate(targets) if x and x not in targets[:i]]
    for target in targets:
        p = root / target
        if not p.is_file(): missing.append(target)
        elif p.resolve() not in graph: unreachable.append(target)
    if missing or unreachable or errors: gate = "FAIL"
    else: gate = "PASS"
    return {"gate": gate, "entry_file": entry, "missing": missing, "unreachable": unreachable,
            "reachable": sorted(set(reachable)), "analysis": ["not_runtime"],
            "errors": errors}

def main(argv=None):
    import argparse, json
    ap=argparse.ArgumentParser(); ap.add_argument("--project-root", required=True); ap.add_argument("--contract", required=True)
    ns=ap.parse_args(argv); result=check(Path(ns.project_root), json.loads(Path(ns.contract).read_text()))
    print(json.dumps(result, ensure_ascii=False, indent=2)); return 0 if result["gate"] == "PASS" else 1
