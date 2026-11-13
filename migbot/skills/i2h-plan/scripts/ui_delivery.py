#!/usr/bin/env python3
"""Create and validate the schema-2 iOS Stage-1 UI delivery inventory.

This is intentionally a small, source-driven implementation.  It supplies
the contract consumed by i2h-execute and leaves semantic choices (states,
ownership and formal routes) visible for Claude Code review instead of
silently fabricating runtime evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

_SPEC_SCRIPTS = Path(__file__).resolve().parents[2] / "i2h-spec/scripts"

TOOL_VERSION = "i2h-ui-delivery/1.1"


_IMMERSIVE_SOURCE_PATTERNS: tuple[tuple[str, str], ...] = (
    ("ignoresSafeArea", r"\.ignoresSafeArea\s*\("),
    ("safeAreaInset", r"\.safeAreaInset\s*\("),
    ("statusBar", r"\.statusBar\s*\("),
    ("fullScreenCover", r"\.fullScreenCover\s*\("),
)
_SWIFT_TRIVIA = re.compile(r'/\*[\s\S]*?\*/|//[^\n]*|"""[\s\S]*?"""|"(?:\\.|[^"\\])*"')
_TAB_VIEW = re.compile(r"(?<![\w.])TabView\s*(?:\([^(){}]*\)\s*)?\{")
_LABELED_TAB = re.compile(
    r"(?<![\w.])(?:Navigation(?:Stack|View)\s*\{\s*)?"
    r"(?P<child>[A-Z]\w*)\s*\([^(){}]*\)\s*(?:\}\s*)?\.tabItem\s*\{"
)
_MODERN_TAB = re.compile(
    r"(?<![\w.])Tab\s*\([^(){}]*\)\s*\{\s*"
    r"(?:(?P<wrapper>Navigation(?:Stack|View))\s*\{\s*)?"
    r"(?P<child>[A-Z]\w*)\s*\([^(){}]*\)\s*\}(?(wrapper)\s*\})"
)


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def read(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object: {path}")
    return data


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def evidence_path(root: Path) -> Path:
    return root / "spec/.i2h/resources-inventory.json"


def source_ref(root: Path, rel: str) -> dict[str, Any]:
    path = (root / rel).resolve()
    ref: dict[str, Any] = {"file": rel, "line": 1}
    if path.is_file():
        ref["sha256"] = digest(path.read_bytes())
    return ref


def _is_shared_component(view: dict[str, Any]) -> bool:
    """Keep reusable SwiftUI declarations out of the route graph.

    Older ``resources-inventory.json`` files predate the ``surface`` field.
    The fallback deliberately uses the same conservative naming/path rules as
    the source index so cached evidence remains usable.
    """
    if view.get("surface") == "shared_component":
        return True
    name = str(view.get("view_name", ""))
    bases = " ".join(str(item) for item in view.get("bases", []))
    if any(token in bases for token in ("UIViewRepresentable", "UIViewControllerRepresentable", "UIViewController")):
        return True
    path = Path(str(view.get("file_path", "")))
    if name.endswith(("Row", "Cell", "Card", "Button", "Pill", "Badge", "Header", "Footer")):
        return True
    if any(part.lower() in {"components", "design", "widgets"} for part in path.parts):
        return True
    return name in {"Coordinator", "ScannerHost"}


def _presentation_hints(source_root: Path, views: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Infer only source-backed presentation ownership for delivery units.

    The hint is intentionally small and reviewable.  It does not guess visual
    details.  Modal targets are detected from the source modifier that owns
    them, while all other screen declarations remain routed pages.  This
    prevents the converter from turning SwiftUI sheets into ordinary pushes.
    """
    files = sorted(source_root.rglob("*.swift")) if source_root.is_dir() else []
    texts: list[tuple[Path, str]] = []
    for path in files:
        try:
            texts.append((path, path.read_text(encoding="utf-8")))
        except (OSError, UnicodeDecodeError):
            continue
    hints: dict[str, dict[str, Any]] = {}
    for view in views:
        name = str(view.get("view_name", ""))
        if not name:
            continue
        if _is_shared_component(view):
            hints[name] = {
                "presentation_role": "embedded",
                "source": "shared_component",
                "harmony_mapping": "embedded_builder",
            }
            continue
        candidates: list[tuple[int, dict[str, Any]]] = []
        for path, text in texts:
            # A bounded window avoids crossing unrelated declarations while
            # still covering the common ``sheet { NavigationStack { ... } }``
            # form used by SwiftUI.
            for match in re.finditer(r"\.(sheet|fullScreenCover)\s*\(", text):
                window = text[match.start(): match.start() + 900]
                target = re.search(rf"\b{re.escape(name)}\s*\(", window)
                if not target:
                    continue
                kind = match.group(1)
                candidate = {
                    "presentation_role": "hosted_destination",
                    "source": f".{kind}",
                    "harmony_mapping": "bindSheet" if kind == "sheet" else "bindContentCover",
                    "host_source": path.relative_to(source_root).as_posix(),
                    "source_line": text.count("\n", 0, match.start()) + 1,
                }
                candidates.append((target.start(), candidate))
        selected = min(candidates, key=lambda item: item[0])[1] if candidates else None
        if selected is None:
            selected = {
                "presentation_role": "routed_page",
                "source": "navigation_or_tab",
                "harmony_mapping": "NavDestination",
            }
        hints[name] = selected
    return hints


def _immersive_hint(source_root: Path, view: dict[str, Any], presentation: dict[str, Any]) -> dict[str, Any]:
    """Derive a reviewable safe-area requirement from SwiftUI source.

    i2h has no Android ``meta.json`` to reuse for iOS projects.  Keep the
    decision conservative and source-backed so full-screen backgrounds,
    safe-area modifiers and full-screen destinations cannot silently lose
    their foreground inset contract during conversion.  A page with no
    matching source evidence is explicitly marked ``false`` and remains
    eligible for the normal routed-page shell.
    """
    source_file = str(view.get("file_path", ""))
    path = (source_root / source_file).resolve()
    try:
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
    except (OSError, UnicodeDecodeError):
        text = ""
    evidence: list[dict[str, Any]] = []
    for kind, pattern in _IMMERSIVE_SOURCE_PATTERNS:
        match = re.search(pattern, text)
        if match:
            evidence.append({
                "kind": kind,
                "file": source_file,
                "line": text.count("\n", 0, match.start()) + 1,
            })
    if presentation.get("source") == ".fullScreenCover":
        evidence.append({"kind": "hosted_fullScreenCover", "file": presentation.get("host_source"), "line": presentation.get("source_line")})
    required = bool(evidence)
    return {
        "required": required,
        "evidence": evidence,
        "policy": "source-backed-ios-safearea-v1",
    }


def views_from_evidence(root: Path) -> list[dict[str, Any]]:
    path = evidence_path(root)
    if path.is_file():
        payload = read(path)
        # Delivery units represent navigable screens. Shared SwiftUI
        # declarations are inputs to those screens and must not become page
        # owners or duplicate content states.
        views = payload.get("pages")
        if not isinstance(views, list) or not views:
            views = [item for item in payload.get("views", []) if isinstance(item, dict) and not _is_shared_component(item)]
        if isinstance(views, list):
            return [item for item in views if isinstance(item, dict) and item.get("view_name") and item.get("file_path")]
    # Fallback for a hand-created baseline: retain Claude Code compatibility
    # without pretending that a missing static scan is complete.
    result = []
    for meta in sorted((root / "spec/baseline/ui-snapshots").glob("*/meta.json")):
        try:
            item = read(meta)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        name = item.get("view_name") or item.get("class_name") or meta.parent.name.rsplit("_", 1)[-1]
        file_path = item.get("file_path") or item.get("source_file")
        if name and file_path:
            result.append({"view_name": name, "file_path": file_path, "type": item.get("type", "SwiftUI View"), "line_count": item.get("line_count", 0)})
    return result


def evidence_source_root(root: Path) -> Path:
    evidence = evidence_path(root)
    if evidence.is_file():
        try:
            value = read(evidence).get("project_root")
            if value:
                source_root = Path(str(value)).expanduser().resolve()
                if source_root.is_dir():
                    return source_root
        except (OSError, ValueError, json.JSONDecodeError):
            pass
    return root


def swiftui_tab_roots(source_root: Path, views: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Find explicit tab children with known source declarations."""
    if not views:
        return {}
    if str(_SPEC_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(_SPEC_SCRIPTS))
    from ui_obligations import declaration_slice

    known = {str(view["view_name"]) for view in views}
    tabs: dict[str, list[dict[str, Any]]] = {}
    for view in views:
        host = str(view["view_name"])
        file = str(view["file_path"])
        path = (source_root / file).resolve()
        if source_root not in path.parents or path.suffix != ".swift" or not path.is_file():
            continue
        raw = path.read_bytes()
        if b"TabView" not in raw:
            continue
        text = _SWIFT_TRIVIA.sub(lambda match: re.sub(r"[^\n]", " ", match[0]), raw.decode("utf-8-sig"))
        declaration = re.search(rf"\bstruct\s+{re.escape(host)}\b[^{{]*\{{", text)
        if not declaration:
            continue
        start = declaration.start()
        body = declaration_slice(text, start)
        for tab_view in _TAB_VIEW.finditer(body):
            content = declaration_slice(body, tab_view.start())
            matches = [match for pattern in (_LABELED_TAB, _MODERN_TAB) for match in pattern.finditer(content)]
            for match in sorted(matches, key=lambda item: item.start("child")):
                prefix = content[:match.start()]
                if prefix.count("{") - prefix.count("}") != 1 or prefix.count("(") != prefix.count(")"):
                    continue
                child = match["child"]
                if child not in known or child == host:
                    continue
                offset = start + tab_view.start() + match.start("child")
                ref = {"file": file, "line": text.count("\n", 0, offset) + 1, "sha256": digest(raw)}
                tabs.setdefault(child, []).append({"host": host, "source_ref": ref})
    return tabs


def draft(project_root: str | Path, out: str | Path) -> dict[str, Any]:
    root = Path(project_root).expanduser().resolve()
    views = views_from_evidence(root)
    evidence = read(evidence_path(root)) if evidence_path(root).is_file() else {}
    shared_components = evidence.get("components", []) if isinstance(evidence, dict) else []
    source_root = evidence_source_root(root)
    presentation_hints = _presentation_hints(source_root, views)
    tab_roots = swiftui_tab_roots(source_root, views)
    units = []
    for index, view in enumerate(views, 1):
        name = str(view["view_name"])
        slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", name).strip("-") or f"view-{index:04d}"
        page_id = f"page_{index:04d}_{name}"
        source_file = str(view["file_path"])
        symbol = name
        component = f"ios.{name}"
        hint = presentation_hints.get(name, {
            "presentation_role": "routed_page",
            "source": "navigation_or_tab",
            "harmony_mapping": "NavDestination",
        })
        source_obligations = view.get("ui_obligations", {})
        source_presentations = (
            source_obligations.get("presentations", [])
            if isinstance(source_obligations, dict)
            else []
        )
        presentation_contract = {
            "source": hint["source"],
            "harmony_mapping": hint["harmony_mapping"],
            **({"host_source": hint["host_source"], "source_line": hint["source_line"]} if hint.get("host_source") else {}),
        }
        if source_presentations:
            # Keep the modifier facts next to the presentation mapping.  The
            # same rows remain in source_obligations for compatibility, while
            # this field lets execute gates validate the host file without
            # reconstructing SwiftUI syntax from a prompt.
            presentation_contract["source_obligations"] = source_presentations
        if name in tab_roots:
            presentation_contract["swiftui_tab_roots"] = tab_roots[name]
        immersive = _immersive_hint(source_root, view, hint)
        units.append({
            "unit_id": f"ios.{index:04d}.{slug}",
            "page_id": page_id,
            "component": component,
            "presentation_role": hint["presentation_role"],
            "presentation": presentation_contract,
            "needs_immersive_safearea": immersive["required"],
            "immersive_safearea": immersive,
            "required": True,
            "required_states": [{"state_id": "default", "arrival_mode": "preview", "responsibility": "content", "source_refs": [source_ref(source_root, source_file)]}],
            "source_refs": [source_ref(source_root, source_file)],
            # Static source obligations are a deterministic checklist for the
            # converter. They never replace runtime evidence for viewport or
            # geometry decisions.
            "source_obligations": view.get("ui_obligations", {}),
            "generation_owner": "i2h-view-converter",
            "integration_owner": "closer",
            "owned_ui_roles": ["content", "behavior"],
            "output": {"file": f"entry/src/main/ets/pages/{name}.ets", "symbol": symbol, "builder": "build"},
            "integration": None,
            "input_alternatives": {},
        })
    target_hash = None
    evidence_file = evidence_path(root)
    if evidence_file.is_file():
        target_hash = evidence.get("target_input_sha256")
    result = {
        "schema_version": 2,
        "tool_version": TOOL_VERSION,
        "project_root": str(root),
        "source_project_root": str(source_root),
        "scope": "full_ui",
        "status": "draft",
        "target_input_sha256": target_hash,
        "units": units,
        "verification_states": [],
        "component_exclusions": [
            {
                "view_name": item.get("view_name"),
                "file_path": item.get("file_path"),
                "reason": "shared_component_embedded_in_screen",
            }
            for item in shared_components
            if isinstance(item, dict) and item.get("view_name")
        ],
        "presentation": {"source": "pending-review", "runtime_required": True},
        "toolchain": {"sdk_definitions": None, "product": None},
        "warnings": [] if units else ["no static iOS views found; run i2h-spec Phase A"],
    }
    write(Path(out), result)
    return result


def visual_binding_gaps(units: list, verification: list) -> dict[str, list]:
    owners = {
        (unit.get("unit_id"), unit.get("page_id"), state.get("state_id"))
        for unit in units if isinstance(unit, dict) and unit.get("required") is not False
        for state in (unit["required_states"] if isinstance(unit.get("required_states"), list) else [])
        if isinstance(state, dict)
        if all(isinstance(value, str) and value
               for value in (unit.get("unit_id"), unit.get("page_id"), state.get("state_id")))
    }
    seen_ids = set()
    covered = set()
    unbound = []
    for index, row in enumerate(verification):
        values = [row.get(key) for key in ("verification_id", "owner", "page_id", "state_id")] if isinstance(row, dict) else []
        if not values or not all(isinstance(value, str) and value for value in values):
            unbound.append(index)
            continue
        pair_id, owner, page, state = values
        if pair_id in seen_ids or (owner, page, state) not in owners:
            unbound.append(index)
            continue
        seen_ids.add(pair_id)
        covered.add((page, state))
    return {
        "unbound_verification_rows": unbound,
        "missing_visual_states": [{"page_id": page, "state_id": state}
                                  for page, state in sorted({(p, s) for _, p, s in owners} - covered)],
    }


def validate(project_root: str | Path, inventory: dict[str, Any], *, require_runtime_plan: bool = False) -> dict[str, Any]:
    root = Path(project_root).expanduser().resolve()
    source_root = Path(str(inventory.get("source_project_root", root))).expanduser().resolve()
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    if inventory.get("schema_version") != 2:
        errors.append({"code": "SCHEMA_VERSION", "message": "schema_version must be 2"})
    units = inventory.get("units")
    if not isinstance(units, list) or not units:
        errors.append({"code": "UNITS_EMPTY", "message": "units must contain at least one UI unit"})
        units = []
    if require_runtime_plan:
        verification = inventory.get("verification_states")
        if not isinstance(verification, list) or not verification:
            errors.append({"code": "runtime_verification_states_missing"})
        else:
            for code, rows in visual_binding_gaps(units, verification).items():
                if rows:
                    errors.append({"code": code, "rows": rows})
    seen_ids: set[str] = set()
    seen_outputs: set[str] = set()
    # State ids are scoped to the page/component that owns them.  A source
    # inventory legitimately contains ``default/content`` for every page and
    # shared component.  Keep the fallback scope for hand-authored units that
    # omit page_id so duplicate ownership still fails closed there.
    seen_roles: dict[tuple[str, str, str], str] = {}
    for unit in units:
        if not isinstance(unit, dict):
            errors.append({"code": "UNIT_INVALID", "message": "unit must be an object"})
            continue
        unit_id = unit.get("unit_id")
        page_scope = str(unit.get("page_id") or "__global__")
        if not unit_id or unit_id in seen_ids:
            errors.append({"code": "UNIT_ID_DUPLICATE", "unit_id": unit_id})
        seen_ids.add(str(unit_id))
        output = unit.get("output", {})
        output_file = output.get("file") if isinstance(output, dict) else None
        if not output_file or output_file in seen_outputs:
            errors.append({"code": "OUTPUT_DUPLICATE", "unit_id": unit_id, "file": output_file})
        seen_outputs.add(str(output_file))
        presentation = unit.get("presentation")
        role = unit.get("presentation_role")
        if presentation is not None:
            if not isinstance(presentation, dict):
                errors.append({"code": "PRESENTATION_INVALID", "unit_id": unit_id})
            else:
                source = str(presentation.get("source", ""))
                mapping = presentation.get("harmony_mapping")
                expected = {
                    "hosted_destination": {"bindSheet", "bindContentCover"},
                    "embedded": {"embedded_builder"},
                    "routed_page": {"NavDestination"},
                }.get(str(role))
                if expected is not None and mapping not in expected:
                    errors.append({
                        "code": "PRESENTATION_MAPPING_MISMATCH",
                        "unit_id": unit_id,
                        "presentation_role": role,
                        "harmony_mapping": mapping,
                    })
                if source == ".sheet" and mapping != "bindSheet":
                    errors.append({"code": "SHEET_MAPPING_MISMATCH", "unit_id": unit_id})
                if source == ".fullScreenCover" and mapping != "bindContentCover":
                    errors.append({"code": "FULLSCREEN_MAPPING_MISMATCH", "unit_id": unit_id})
                if source == "shared_component" and mapping != "embedded_builder":
                    errors.append({"code": "EMBEDDED_MAPPING_MISMATCH", "unit_id": unit_id})
                modifier_rows = presentation.get("source_obligations", [])
                if modifier_rows is not None and not isinstance(modifier_rows, list):
                    errors.append({"code": "PRESENTATION_OBLIGATIONS_INVALID", "unit_id": unit_id})
                for row in modifier_rows if isinstance(modifier_rows, list) else []:
                    if not isinstance(row, dict):
                        errors.append({"code": "PRESENTATION_OBLIGATION_INVALID", "unit_id": unit_id})
                        continue
                    kind = str(row.get("kind", ""))
                    if kind not in {"sheet", "full_screen_cover", "alert", "confirmation_dialog", "popover", "context_menu"}:
                        errors.append({"code": "PRESENTATION_KIND_INVALID", "unit_id": unit_id, "kind": kind})
        for ref in unit.get("source_refs", []):
            if not isinstance(ref, dict) or not ref.get("file"):
                errors.append({"code": "SOURCE_REF_INVALID", "unit_id": unit_id})
                continue
            if not (source_root / ref["file"]).is_file() and not (root / ref["file"]).is_file() and not (root / "spec" / ref["file"]).is_file():
                warnings.append({"code": "SOURCE_REF_MISSING", "unit_id": unit_id, "file": ref["file"]})
        states = unit.get("required_states")
        if not isinstance(states, list) or not states:
            errors.append({"code": "STATES_EMPTY", "unit_id": unit_id})
            continue
        roles = set(unit.get("owned_ui_roles", []))
        for state in states:
            if not isinstance(state, dict) or not state.get("state_id"):
                errors.append({"code": "STATE_INVALID", "unit_id": unit_id})
                continue
            responsibility = state.get("responsibility", "content")
            if responsibility not in {"shell", "content", "overlay", "behavior"}:
                errors.append({"code": "RESPONSIBILITY_INVALID", "unit_id": unit_id, "state_id": state.get("state_id")})
            if responsibility not in roles:
                errors.append({"code": "ROLE_UNDECLARED", "unit_id": unit_id, "role": responsibility})
            key = (page_scope, str(state.get("state_id")), responsibility)
            previous = seen_roles.get(key)
            if previous and responsibility == "content":
                errors.append({"code": "DUPLICATE_CONTENT_OWNERSHIP", "state_id": key[0], "owners": [previous, unit_id]})
            else:
                seen_roles[key] = str(unit_id)
    result = dict(inventory)
    result["status"] = "validated" if not errors else "invalid"
    result["validation"] = {"errors": errors, "warnings": warnings}
    return result


def validate_tab_integrations(root: Path, inventory: dict[str, Any]) -> list[dict[str, Any]]:
    source_root = evidence_source_root(root)
    tabs = swiftui_tab_roots(source_root, views_from_evidence(root))
    by_component: dict[str, list[dict[str, Any]]] = {}
    for unit in inventory["units"]:
        component = unit.get("component")
        if unit.get("required", True) and isinstance(component, str):
            by_component.setdefault(component, []).append(unit)
    errors = []
    for child, anchors in tabs.items():
        matching = by_component.get(f"ios.{child}", [])
        if not matching and inventory.get("scope") != "full_ui":
            continue
        for anchor in anchors:
            hosts = by_component.get(f'ios.{anchor["host"]}', [])
            host_outputs = {unit["output"]["file"]: unit["output"].get("symbol") for unit in hosts}
            if not any(tab_slot_matches(unit, anchor["source_ref"], host_outputs) for unit in matching):
                errors.append({"code": "SWIFTUI_TAB_HOST_SLOT_MISSING", "child": child, **anchor})
    return errors


def tab_slot_matches(unit: dict, source: dict, host_outputs: dict) -> bool:
    integration = unit.get("integration")
    slots = integration if isinstance(integration, list) else [integration]
    for slot in slots:
        if (not isinstance(slot, dict) or slot.get("source_ref") != source or slot.get("mount")
                or slot.get("child_symbol") != unit["output"].get("symbol")):
            continue
        host_file, builder = slot.get("host_file"), slot.get("host_builder")
        if not isinstance(host_file, str) or not isinstance(builder, str):
            continue
        owner, _, name = builder.rpartition(".")
        if name and host_outputs.get(host_file) and (owner or slot.get("host_symbol")) == host_outputs[host_file]:
            return True
    return False


def approve(project_root: str | Path, inventory: dict[str, Any], confirmation_ref: str, *,
            require_runtime_plan: bool = False) -> dict[str, Any]:
    result = validate(project_root, inventory, require_runtime_plan=require_runtime_plan)
    if result["validation"]["errors"]:
        raise ValueError("cannot approve invalid UI delivery inventory: " +
                         json.dumps(result["validation"]["errors"], ensure_ascii=False))
    tab_errors = validate_tab_integrations(Path(project_root).resolve(), inventory)
    if tab_errors:
        raise ValueError(json.dumps(tab_errors, ensure_ascii=False))
    if not confirmation_ref or not confirmation_ref.strip():
        raise ValueError("confirmation_ref is required for approval")
    result["status"] = "approved"
    result["approval"] = {"confirmation_ref": confirmation_ref, "scope": result.get("scope", "full_ui")}
    return result


def diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    left = {u.get("unit_id"): u for u in before.get("units", []) if isinstance(u, dict)}
    right = {u.get("unit_id"): u for u in after.get("units", []) if isinstance(u, dict)}
    return {"schema_version": 1, "added": sorted(set(right) - set(left)), "removed": sorted(set(left) - set(right)), "changed": sorted(k for k in set(left) & set(right) if left[k] != right[k])}


def add_visual_pairs(inventory: dict) -> dict:
    """Fill missing page/state pairs in a draft without changing declared journeys."""
    if inventory.get("schema_version") != 2 or inventory.get("status") != "draft":
        raise ValueError("visual pair generation requires a schema-2 draft")
    rows = inventory.get("verification_states", [])
    units = inventory.get("units")
    if not isinstance(rows, list) or not isinstance(units, list):
        raise ValueError("expected units and verification_states arrays")
    journeys = inventory.get("behavior_journeys", [])
    if not isinstance(journeys, list):
        raise ValueError("expected behavior_journeys array")
    journeys = list(journeys)
    pairs = []
    ids, covered = set(), set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("invalid verification state")
        keys = [row.get(k) for k in ("verification_id", "owner", "page_id", "state_id")]
        if not any(keys[:2]) and all(isinstance(value, str) and value for value in keys[2:]) and (
                row.get("source_test") or row.get("description")):
            if row not in journeys:
                journeys.append(row)
            continue
        if not all(isinstance(value, str) and value for value in keys) or keys[0] in ids:
            raise ValueError("invalid or duplicate visual pair")
        ids.add(keys[0])
        covered.add((keys[2], keys[3]))
        pairs.append(row)
    candidates = {}
    for unit in units:
        if not isinstance(unit, dict):
            raise ValueError("invalid delivery unit")
        if unit.get("required") is False:
            continue
        page, owner = unit.get("page_id"), unit.get("unit_id")
        states = unit.get("required_states")
        if not isinstance(states, list) or not states:
            raise ValueError("required unit must declare states")
        for state in states:
            if not isinstance(state, dict):
                raise ValueError("invalid required state")
            state_id = state.get("state_id")
            if not all(isinstance(value, str) and value for value in (owner, page, state_id)):
                raise ValueError("visual pair requires stable unit, page and state IDs")
            candidates.setdefault((page, state_id), []).append((owner, state))
    for row in pairs:
        key = (row["page_id"], row["state_id"])
        if not any(owner == row["owner"] for owner, _ in candidates.get(key, [])):
            raise ValueError(f"visual pair does not bind a required owner: {row['verification_id']}")
    for page, state_id in sorted(candidates.keys() - covered):
        choices = candidates[(page, state_id)]
        if len(choices) != 1:
            raise ValueError(f"explicit visual owner required for {page}/{state_id}")
        owner, state = choices[0]
        pair_id = "visual-" + digest(json.dumps([page, state_id]).encode())[:16]
        if pair_id in ids:
            raise ValueError(f"visual pair ID already exists: {pair_id}")
        ids.add(pair_id)
        pairs.append({"verification_id": pair_id, "owner": owner, "page_id": page, "state_id": state_id,
                      "arrival_mode": state.get("arrival_mode", "preview")})
    result = {**inventory, "verification_states": pairs}
    if journeys:
        result["behavior_journeys"] = journeys
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("draft", "pair-states", "validate", "approve", "diff"))
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--inventory")
    parser.add_argument("--confirmation-ref")
    parser.add_argument("--require-runtime-plan", action="store_true")
    parser.add_argument("--receipt-only", action="store_true", help="validate writes a digest-bound receipt without inventory units")
    parser.add_argument("--validation-receipt", help="approve checks the receipt for this exact candidate before revalidation")
    parser.add_argument("--before")
    parser.add_argument("--after")
    args = parser.parse_args(argv)
    if args.receipt_only and args.command != "validate":
        parser.error("--receipt-only requires validate")
    if args.validation_receipt and args.command != "approve":
        parser.error("--validation-receipt requires approve")
    try:
        if args.command == "draft":
            result = draft(args.project_root, args.out)
        elif args.command == "pair-states":
            if not args.inventory:
                raise ValueError("--inventory is required")
            root = Path(args.project_root).resolve()
            candidate, output = (Path(value).resolve() for value in (args.inventory, args.out))
            if any(root not in path.parents for path in (candidate, output)):
                raise ValueError("draft and paired output must stay inside the project")
            if output.is_file() and read(output).get("status") == "approved":
                raise ValueError("pair-states cannot overwrite an approved inventory")
            result = add_visual_pairs(read(candidate))
            write(output, result)
        elif args.command in {"validate", "approve"}:
            if not args.inventory:
                raise ValueError("--inventory is required")
            candidate = Path(args.inventory)
            output = Path(args.out)
            in_place = output.resolve() == candidate.resolve()
            if args.receipt_only and in_place:
                raise ValueError("validation receipt must use a separate output file")
            raw = candidate.read_bytes()
            inventory = json.loads(raw)
            if not isinstance(inventory, dict):
                raise ValueError(f"expected JSON object: {args.inventory}")
            if args.command == "validate":
                result = validate(args.project_root, inventory, require_runtime_plan=args.require_runtime_plan)
                if args.receipt_only:
                    if not result["validation"]["errors"]:
                        result["validation"]["errors"].extend(validate_tab_integrations(
                            Path(args.project_root).resolve(), inventory))
                        if result["validation"]["errors"]:
                            result["status"] = "invalid"
                    result = {"schema_version": 1, "kind": "ui-delivery-validation", "status": result["status"],
                              "inventory_sha256": digest(raw), "validation": result["validation"]}
            else:
                raw_receipt = None
                if args.validation_receipt:
                    receipt_path = Path(args.validation_receipt)
                    if receipt_path.resolve() == output.resolve():
                        raise ValueError("approval output cannot overwrite its validation receipt")
                    raw_receipt = receipt_path.read_bytes()
                    receipt = json.loads(raw_receipt)
                    if not isinstance(receipt, dict) or (receipt.get("schema_version"), receipt.get("kind"), receipt.get("status"),
                            receipt.get("inventory_sha256")) != (1, "ui-delivery-validation", "validated", digest(raw)):
                        raise ValueError("validation receipt does not cover the current UI delivery inventory")
                result = approve(args.project_root, inventory, args.confirmation_ref or "",
                                 require_runtime_plan=args.require_runtime_plan)
                if in_place and raw_receipt is not None:
                    result["approval"]["candidate_sha256"] = digest(raw)
                    result["approval"]["validation_receipt_sha256"] = digest(raw_receipt)
            write(output, result)
        else:
            if not args.before or not args.after:
                raise ValueError("--before and --after are required")
            result = diff(read(Path(args.before)), read(Path(args.after)))
            write(Path(args.out), result)
    except (OSError, ValueError, ImportError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if args.command == "draft":
        print(json.dumps({"output": args.out, "units": len(result.get("units", [])), "status": result.get("status")}, ensure_ascii=False))
    else:
        print(json.dumps({"output": args.out, "status": result.get("status")}, ensure_ascii=False))
    if args.command == "validate" and (args.receipt_only or args.require_runtime_plan) and result["status"] != "validated":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
