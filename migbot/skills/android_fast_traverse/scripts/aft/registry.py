"""Conservative artifact identity, immutable revisions and visit provenance.

Artifact reuse never declares a control explored. Ambiguous identities remain
separate; traversal state and artifact storage deliberately have different jobs.
"""
from __future__ import annotations

import copy
import hashlib
import json

from . import ui
from .capture import TRUNCATED_STOPS
from .store import _atomic_write, dump_json, now_iso


def _hash(value) -> str:
    data = value if isinstance(value, bytes) else json.dumps(value, sort_keys=True, ensure_ascii=False,
                                                            separators=(",", ":"), default=list).encode()
    return hashlib.sha256(data).hexdigest()


def _semantic(nodes, package: str) -> str:
    """Exact application hierarchy; Android clock/chrome are not app identity."""
    kept = [n for n in nodes if n.package == package and n.short_rid not in ui.SYSTEM_RIDS]
    indices = {n.idx: i for i, n in enumerate(kept)}
    result = []
    for n in kept:
        parent = n.parent
        while parent >= 0 and parent not in indices:
            parent = nodes[parent].parent
        result.append((indices.get(parent, -1), n.cls, n.rid, n.text, n.desc, n.bounds,
                       n.selected, n.checked, n.checkable, n.clickable, n.long_clickable,
                       n.enabled, n.scrollable, n.focused, n.covered))
    return _hash(result) if result else ""


def _frame_key(frame, package: str) -> dict:
    xml, png = _hash(frame.xml), _hash(frame.png)
    return {"semantic": _semantic(frame.nodes, package), "xml": xml, "png": png,
            "pair": _hash([xml, png]), "container": frame.container, "opaque": _opaque(frame.nodes, package)}


def _context(meta, state, package):
    aft = meta.get("aft", {})
    return {"package": package, "activity": aft.get("activity"), "layer": aft.get("layer", ""),
            "dpi": meta.get("dpi"), "app": state.get("app") or {},
            "readings": aft.get("readings") or {}, "drift": aft.get("drift") or {}}


def _read_meta(store, record):
    try:
        return json.loads((store.out / record["page_id"] / "meta.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, KeyError):
        return None


def _evidence(store, meta, state, package):
    """Lazily understand older artifacts without rewriting their files."""
    reg = meta.get("aft", {}).get("registry", {})
    if reg.get("schema") == 1:
        return reg
    keys = []
    try:
        from .capture import Frame
        shots, xmls = meta["screenshots"], meta["view_xmls"]
        if not shots or len(shots) != len(xmls):
            return {}
        for i, (png_path, xml_path) in enumerate(zip(shots, xmls)):
            xml = (store.out / xml_path).read_bytes()
            keys.append(_frame_key(Frame(i, xml, (store.out / png_path).read_bytes(), ui.parse(xml)), package))
    except (OSError, ValueError, KeyError):
        return {}
    return {"schema": 1, "context": _context(meta, state, package), "frame_keys": keys,
            "sources": ["manual" if meta.get("aft", {}).get("kind") == "manual" else "auto"]}


def _eligible(old, new, manual):
    """Automatic semantic distinctions keep their own artifact IDs."""
    a, b = old.get("aft", {}), new.get("aft", {})
    sources = a.get("registry", {}).get("sources", [])
    if manual or a.get("kind") == "manual" or sources == ["manual"]:
        return True
    return (a.get("kind"), a.get("parent"), a.get("via"), old.get("click_path")) == (
        b.get("kind"), b.get("parent"), b.get("via"), new.get("click_path"))


def _quality(meta):
    cap = meta.get("aft", {}).get("capture", {})
    if cap.get("stop") in TRUNCATED_STOPS or cap.get("interruption"):
        return 0
    if (cap.get("proof_degraded") or cap.get("scope", {}).get("skipped_auto")
            or cap.get("stop") not in ("bottom", "no_container", "no_new_content", "small_move", "max_scrolls", "single")):
        return 1
    if any(e.get("status") == "not_visible" or e.get("stop") in TRUNCATED_STOPS for e in cap.get("extra", [])):
        return 1
    return 2


def _scope_covers(meta, request):
    cap = meta.get("aft", {}).get("capture", {})
    old = cap.get("scope", {})
    if not old or old.get("skipped_auto") or _quality(meta) < 2:
        return False
    if old.get("extra_containers", []) != request.get("extra_containers", []):
        return False
    for key in ("max_scrolls", "max_hscrolls"):
        if int(old.get(key, 0)) < int(request.get(key, 0)):
            return False
    return True


def _coverage_not_less(new, old):
    a = new.get("aft", {}).get("capture", {}).get("scope", {})
    b = old.get("aft", {}).get("capture", {}).get("scope", {})
    if not b:
        return bool(a)
    return (all(int(a.get(k, 0)) >= int(b.get(k, 0)) for k in ("max_scrolls", "max_hscrolls"))
            and all(item in a.get("extra_containers", []) for item in b.get("extra_containers", []))
            and set(a.get("skipped_auto", [])).issubset(b.get("skipped_auto", [])))


def _tick(state, action, ambiguous=False):
    stats = state.setdefault("artifact_stats", {})
    for key in ("captures_attempted", "created", "reused", "revised", "retained", "ambiguous"):
        stats.setdefault(key, 0)
    stats["captures_attempted"] += 1
    stats[action] += 1
    stats["ambiguous"] += int(ambiguous)


def _visit(store, reg, source, label="", path=None):
    visit = {"timestamp": now_iso(), "source": source, "label": label, "path": path or []}
    session = getattr(store, "session_id", None)
    if session:
        visit["session"] = session
    reg.setdefault("visits", []).append(visit)
    reg["sources"] = sorted(set(reg.get("sources", [])) | {source})


def _persist(store, state, meta):
    store.write_meta(meta["page_id"], meta)
    record = {k: v for k, v in meta.items() if k != "clickable_elements"}
    records = state.setdefault("index", [])
    for i, existing in enumerate(records):
        if existing["page_id"] == meta["page_id"]:
            records[i] = record
            break
    else:
        records.append(record)
    store.write_index(records)
    return meta


def record_reuse(store, state, meta, *, source="manual", label="", path=None):
    saved = copy.deepcopy(meta)
    reg = saved.setdefault("aft", {}).setdefault("registry", {})
    _visit(store, reg, source, label, path)
    reg["last_action"] = "reused"
    _tick(state, "reused")
    store.event("artifact_reused", {"page_id": saved["page_id"], "source": source})
    return _persist(store, state, saved)


def _new_evidence_dir(store, category, page_id):
    parent = store.aft / category / page_id
    number = 1
    while (parent / f"rev_{number:04d}").exists():
        number += 1
    return (parent / f"rev_{number:04d}").relative_to(store.out).as_posix()


def _with_paths(meta, page_id, shots, xmls):
    meta.update(page_id=page_id, screenshots=shots, view_xmls=xmls,
                screenshot=shots[0], view_xml=xmls[0])
    return meta


def _files_available(store, meta):
    shots, xmls = meta.get("screenshots", []), meta.get("view_xmls", [])
    return bool(shots) and len(shots) == len(xmls) and all((store.out / p).is_file() for p in shots + xmls)


def save_capture(store, state, frames, meta, *, package, manual=False, target_id=None):
    """Register one complete attempted group; return the effective indexed unit."""
    if not frames:
        raise ValueError("cannot register an empty capture")
    meta = copy.deepcopy(meta)
    keys = [_frame_key(f, package) for f in frames]
    context = _context(meta, state, package)
    source = "manual" if manual else "auto"
    matches = []
    for record in state.get("index", []):
        if target_id and record.get("page_id") != target_id:
            continue
        old = _read_meta(store, record)
        if not old:
            continue
        reg = _evidence(store, old, state, package)
        overlap = {k["semantic"] for k in reg.get("frame_keys", [])} & {k["semantic"] for k in keys}
        if reg.get("context") == context and overlap - {""} and (target_id or _eligible(old, meta, manual)):
            old.setdefault("aft", {})["registry"] = reg
            matches.append(old)
    if target_id and len(matches) != 1:
        raise ValueError("recapture target identity does not match uniquely; capture separately instead")
    if len(matches) != 1:
        page_id = store.allocate_page_id(state, meta["aft"].get("activity", ""), manual=manual)
        shots, xmls = store.write_frames(page_id, frames)
        reg = {"schema": 1, "context": context, "frame_keys": keys, "last_action": "created"}
        if len(matches) > 1:
            reg["suspected_duplicate"] = [m["page_id"] for m in matches]
        _visit(store, reg, source, meta.get("label", ""), meta.get("click_path"))
        meta["aft"]["registry"] = reg
        _tick(state, "created", ambiguous=len(matches) > 1)
        return _persist(store, state, _with_paths(meta, page_id, shots, xmls))

    old = matches[0]
    oldreg = old["aft"]["registry"]
    oldkeys = oldreg["frame_keys"]
    oldpairs, newpairs = [k["pair"] for k in oldkeys], [k["pair"] for k in keys]
    available = _files_available(store, old)
    if available and oldpairs == newpairs and 0 < _quality(meta) <= _quality(old):
        return record_reuse(store, state, old, source=source, label=meta.get("label", ""),
                            path=meta.get("click_path"))

    # Fewer frames or weaker evidence must never replace a known complete group.
    append = available and set(oldpairs).issubset(newpairs)
    poorer = (_quality(meta) < _quality(old) or len(keys) < len(oldkeys)
              or (_quality(meta) == 0 and _quality(old) == 0)
              or not _coverage_not_less(meta, old)
              or (not append and keys[0]["semantic"] != oldkeys[0]["semantic"]))
    if poorer:
        folder = _new_evidence_dir(store, "attempts", old["page_id"])
        shots, xmls = store.write_frames(folder, frames)
        attempt = _with_paths(meta, old["page_id"], shots, xmls)
        store.write_meta(folder, attempt)
        oldreg.setdefault("retained_attempts", []).append(folder + "/meta.json")
        oldreg["last_action"] = "retained"
        _visit(store, oldreg, source, meta.get("label", ""), meta.get("click_path"))
        _tick(state, "retained")
        return _persist(store, state, old)

    folder = _new_evidence_dir(store, "revisions", old["page_id"])
    lookup = {key["pair"]: (p, x) for key, p, x in zip(oldkeys, old["screenshots"], old["view_xmls"])}
    novel = [f for f, key in zip(frames, keys) if not append or key["pair"] not in lookup]
    if novel:
        newshots, newxmls = store.write_frames(folder, novel)
    else:
        (store.out / folder).mkdir(parents=True, exist_ok=False)
        newshots, newxmls = [], []
    _atomic_write(store.out / folder / "previous_meta.json", dump_json(old))
    if append:
        it = iter(zip(newshots, newxmls))
        pairs = [lookup[k["pair"]] if k["pair"] in lookup else next(it) for k in keys]
        shots, xmls = map(list, zip(*pairs))
    else:
        shots, xmls = newshots, newxmls
    reg = copy.deepcopy(oldreg)
    reg.update(schema=1, context=context, frame_keys=keys, last_action="revised",
               revision_mode="append_exact_superset" if append else "replace_group")
    reg.setdefault("revisions", []).append(folder)
    _visit(store, reg, source, meta.get("label", ""), meta.get("click_path"))
    # The artifact ID and its original semantic/traversal classification stay stable.
    for field in ("kind", "parent", "via"):
        meta["aft"][field] = old["aft"].get(field)
    for field in ("label", "click_path", "came_from", "trigger_element"):
        if field in old:
            meta[field] = old[field]
    meta["aft"]["registry"] = reg
    meta = _with_paths(meta, old["page_id"], shots, xmls)
    store.write_meta(folder, meta)
    _tick(state, "revised")
    return _persist(store, state, meta)


def _opaque(nodes, package):
    app = [n for n in nodes if n.package == package and n.short_rid not in ui.SYSTEM_RIDS]
    for n in app:
        if any(name in n.cls for name in ("WebView", "SurfaceView", "TextureView")):
            return True
        if not n.children and n.area > 0:
            if ((n.short_cls == "View" and not (n.text or n.desc))
                    or not n.cls.startswith(("android.", "androidx.", "com.google.android.material."))):
                return True
    return not app


def lookup_reuse(store, state, obs, png, *, package, scope, density):
    """Cheap manual preflight: never infer hidden custom/WebView content from XML."""
    if not obs.in_app or obs.package != package or _opaque(obs.nodes, package):
        return None
    try:
        profile = json.loads((store.aft / "profile.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        profile = {}
    readings = ui.read_readings([obs.nodes], profile.get("business_readings", []), package, obs.activity)
    layer = "win:" + obs.overlay if obs.overlay else ("layer" if ui.layered(obs.nodes) else "")
    current = {"dpi": density, "aft": {"activity": obs.activity, "layer": layer,
                                       "readings": readings, "drift": state.get("drift")}}
    context, semantic, image = _context(current, state, package), _semantic(obs.nodes, package), _hash(png)
    matches = []
    for record in state.get("index", []):
        old = _read_meta(store, record)
        if not old:
            continue
        reg = _evidence(store, old, state, package)
        first = (reg.get("frame_keys") or [{}])[0]
        if reg.get("context") != context or first.get("semantic") != semantic or first.get("png") != image:
            continue
        old.setdefault("aft", {})["registry"] = reg
        matches.append(old)
    if len(matches) != 1:
        return None
    old = matches[0]
    if (not _scope_covers(old, scope) or not _files_available(store, old)
            or any(k.get("opaque", True) for k in old["aft"]["registry"].get("frame_keys", []))):
        return None
    return old
