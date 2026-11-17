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
        if not isinstance(source_obligations, dict):
            source_obligations = {}
        source_refs = [source_ref(source_root, source_file)]
        for symbol_fact in source_obligations.get("system_symbol_fidelity", []):
            definition = symbol_fact.get("component_definition")
            if definition:
                component_file = definition["file"]
                if not (source_root / component_file).resolve().is_relative_to(source_root):
                    raise ValueError(f"symbol component definition outside source root: {component_file}")
                ref = {**source_ref(source_root, component_file), "line": definition["line"]}
                if ref not in source_refs:
                    source_refs.append(ref)
        drawing_files = {row["definition"]["file"]
                         for row in source_obligations.get("drawing_component_calls", [])}
        for file in sorted(drawing_files - {ref["file"] for ref in source_refs}):
            if not (source_root / file).resolve().is_relative_to(source_root):
                raise ValueError(f"drawing component definition outside source root: {file}")
            source_refs.append(source_ref(source_root, file))
        source_presentations = source_obligations.get("presentations", [])
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
            "source_refs": source_refs,
            # Static source obligations are a deterministic checklist for the
            # converter. They never replace runtime evidence for viewport or
            # geometry decisions.
            "source_obligations": source_obligations,
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
        (unit.get("unit_id"), unit.get("page_id"), state.get("state_id")): state.get("arrival_mode", "preview")
        for unit in units if isinstance(unit, dict) and unit.get("required") is not False
        for state in (unit["required_states"] if isinstance(unit.get("required_states"), list) else [])
        if isinstance(state, dict)
        if all(isinstance(value, str) and value
               for value in (unit.get("unit_id"), unit.get("page_id"), state.get("state_id")))
    }
    seen_ids = set()
    covered = set()
    unbound = []
    arrival_mismatches = []
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
        declared = owners[(owner, page, state)]
        if row.get("arrival_mode", declared) != declared:
            arrival_mismatches.append({"verification_id": pair_id, "expected": declared,
                                       "actual": row.get("arrival_mode")})
            continue
        covered.add((page, state))
    return {
        "unbound_verification_rows": unbound,
        "missing_visual_states": [{"page_id": page, "state_id": state}
                                  for page, state in sorted({(p, s) for _, p, s in owners} - covered)],
        "visual_arrival_mode_mismatches": arrival_mismatches,
    }


_KNOWN_PRESENTATION_ROLES = frozenset({
    "routed_page", "hosted_destination", "embedded",
})

# Patterns that indicate placeholder values written by an executor bypass
_PLACEHOLDER_RE = re.compile(
    r"""(?xi)
    ^(?:UNRESOLVED|TODO|PLACEHOLDER|TBD|FIXME|UNKNOWN|
        None|null|undefined|"")\s*$
    """,
    re.IGNORECASE,
)
# Valid ArkTS target identifier: QualifiedName like "entry.SomeBuilder"
# or a bare CamelCase name.  Must not contain slashes or dots after last segment.
_ATS_IDENT_RE = re.compile(r'^[A-Za-z_$][A-Za-z0-9_$]*(?:\.[A-Za-z_$][A-Za-z0-9_$]*)*$')


def _is_placeholder(value: object) -> bool:
    return not isinstance(value, str) or not value.strip() or bool(_PLACEHOLDER_RE.match(value.strip()))


def _validate_integration_host(unit: dict[str, Any], errors: list[dict[str, Any]]) -> None:
    """Fail-closed validation of integration host fields.

    Catches executor bypass patterns:
    - Unknown/None presentation_role for required units (not in known enum)
    - host_file: must be safe relative POSIX .ets path — rejects absolute,
      path-traversal, Windows backslash paths, .swift and any non-.ets extension
    - host_builder / child_symbol: reject placeholders and invalid identifiers
    - Required hosted_destination/embedded slots must have all 3 host fields
    - hosted_destination/embedded MUST have at least one integration slot
    """
    unit_id = unit.get("unit_id")
    role = unit.get("presentation_role")
    required = unit.get("required") is not False

    # presentation_role must be a supported enum value for required units
    # None is rejected outright for any required unit (not just those with integration)
    if required and (role is None or role not in _KNOWN_PRESENTATION_ROLES):
        errors.append({"code": "PRESENTATION_ROLE_UNKNOWN", "unit_id": unit_id, "role": role})

    integration = unit.get("integration")
    slots = integration if isinstance(integration, list) else ([integration] if integration else [])

    # hosted_destination/embedded MUST have at least one non-empty integration slot
    if role in ("hosted_destination", "embedded"):
        valid_slots = [s for s in slots if isinstance(s, dict) and s]
        if not valid_slots:
            errors.append({"code": "INTEGRATION_REQUIRED", "unit_id": unit_id, "role": role})
            return  # No slots to validate further

    for slot in slots:
        if not isinstance(slot, dict):
            continue
        host_file = slot.get("host_file")
        host_builder = slot.get("host_builder")
        child_symbol = slot.get("child_symbol")

        # Required hosted/embedded slots must have all 3 fields present
        if role in ("hosted_destination", "embedded"):
            for field_name, field_val in (
                ("host_file", host_file),
                ("host_builder", host_builder),
                ("child_symbol", child_symbol),
            ):
                if field_val is None:
                    errors.append({"code": "HOST_FIELD_REQUIRED", "unit_id": unit_id,
                                   "field": field_name, "role": role})

        if host_file is not None:
            if _is_placeholder(host_file):
                errors.append({"code": "HOST_FILE_PLACEHOLDER", "unit_id": unit_id, "host_file": host_file})
            elif isinstance(host_file, str):
                hf = host_file.strip()
                # Reject absolute paths (Unix and Windows)
                if hf.startswith("/") or (len(hf) >= 2 and hf[1] == ":"):
                    errors.append({"code": "HOST_FILE_ABSOLUTE_PATH", "unit_id": unit_id, "host_file": hf})
                # Reject Windows-style backslash paths
                elif "\\" in hf:
                    errors.append({"code": "HOST_FILE_BACKSLASH_PATH", "unit_id": unit_id, "host_file": hf})
                # Reject path traversal
                elif ".." in hf.split("/"):
                    errors.append({"code": "HOST_FILE_PATH_TRAVERSAL", "unit_id": unit_id, "host_file": hf})
                # Must end with .ets — reject .swift, .ts, .txt, etc.
                elif not hf.endswith(".ets"):
                    errors.append({"code": "HOST_FILE_NOT_ETS", "unit_id": unit_id, "host_file": hf,
                                   "detail": "target host file must be a .ets ArkTS path"})
                # Planned .ets hosts need not exist yet; no existence check

        if host_builder is not None:
            if _is_placeholder(host_builder):
                errors.append({"code": "HOST_BUILDER_PLACEHOLDER", "unit_id": unit_id, "host_builder": host_builder})
            elif isinstance(host_builder, str) and not _ATS_IDENT_RE.match(host_builder.strip()):
                errors.append({"code": "HOST_BUILDER_INVALID_IDENTIFIER", "unit_id": unit_id, "host_builder": host_builder})

        if child_symbol is not None:
            if _is_placeholder(child_symbol):
                errors.append({"code": "CHILD_SYMBOL_PLACEHOLDER", "unit_id": unit_id, "child_symbol": child_symbol})
            elif isinstance(child_symbol, str) and not _ATS_IDENT_RE.match(child_symbol.strip()):
                errors.append({"code": "CHILD_SYMBOL_INVALID_IDENTIFIER", "unit_id": unit_id, "child_symbol": child_symbol})
            else:
                # child_symbol must match unit's output.symbol exactly
                expected_symbol = (unit.get("output") or {}).get("symbol") if isinstance(unit.get("output"), dict) else None
                if expected_symbol is not None and isinstance(child_symbol, str) and child_symbol.strip() != expected_symbol:
                    errors.append({"code": "CHILD_SYMBOL_MISMATCH", "unit_id": unit_id,
                                   "child_symbol": child_symbol, "output_symbol": expected_symbol})


def _validate_drawing_bindings(root: Path, units: list, bindings: Any) -> tuple[list[dict], list[dict]]:
    def identity(row):
        definition = row.get("definition") if isinstance(row, dict) else None
        if not isinstance(definition, dict):
            return None
        file, line = definition.get("file"), definition.get("line")
        if not isinstance(file, str) or not file or type(line) is not int or line < 1:
            return None
        return file, line

    consumers = {}
    for unit in units:
        if not isinstance(unit, dict) or not unit.get("required", True):
            continue
        obligations = unit.get("source_obligations")
        if not isinstance(obligations, dict) or not isinstance(obligations.get("drawing_component_calls"), list):
            continue
        for row in obligations["drawing_component_calls"]:
            if key := identity(row):
                consumers.setdefault(key, set()).add(str(unit.get("unit_id", "")))
    if not isinstance(bindings, list):
        return [{"code": "DRAWING_BINDINGS_INVALID", "message": "drawing_component_bindings must be an array"}], []
    errors, bound = [], set()
    for index, row in enumerate(bindings):
        key = identity(row)
        output = row.get("output") if isinstance(row, dict) else None
        file = output.get("file") if isinstance(output, dict) else None
        symbol = output.get("symbol") if isinstance(output, dict) else None
        if (key not in consumers or key in bound or not isinstance(file, str) or not file.endswith(".ets")
                or Path(file).is_absolute() or not (root / file).resolve().is_relative_to(root)
                or not isinstance(symbol, str) or not re.fullmatch(r"[A-Za-z_$][\w$]*", symbol)):
            errors.append({"code": "DRAWING_BINDING_INVALID", "index": index,
                           "message": "expected a unique used definition and a project-relative ArkUI output"})
            continue
        bound.add(key)
    warnings = [{"code": "SHARED_DRAWING_BINDING_UNSPECIFIED",
                 "definition": {"file": file, "line": line}, "unit_ids": sorted(ids)}
                for (file, line), ids in sorted(consumers.items()) if len(ids) > 1 and (file, line) not in bound]
    return errors, warnings


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
    drawing_errors, drawing_warnings = _validate_drawing_bindings(root, units, inventory.get("drawing_component_bindings", []))
    errors.extend(drawing_errors)
    warnings.extend(drawing_warnings)
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
    native_hashes: dict[Path, str | None] = {}
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
        refs = unit.get("source_refs", [])
        if not isinstance(refs, list):
            errors.append({"code": "SOURCE_REF_INVALID", "unit_id": unit_id})
            refs = []
        for ref in refs:
            if not isinstance(ref, dict) or not isinstance(ref.get("file"), str) or not ref["file"]:
                errors.append({"code": "SOURCE_REF_INVALID", "unit_id": unit_id})
                continue
            if not (source_root / ref["file"]).is_file() and not (root / ref["file"]).is_file() and not (root / "spec" / ref["file"]).is_file():
                warnings.append({"code": "SOURCE_REF_MISSING", "unit_id": unit_id, "file": ref["file"]})
        if require_runtime_plan:
            errors.extend(_validate_native_refs(source_root, refs, unit_id, native_hashes))
        _validate_integration_host(unit, errors)
        states = unit.get("required_states")
        if not isinstance(states, list) or not states:
            errors.append({"code": "STATES_EMPTY", "unit_id": unit_id})
            continue
        roles = set(unit.get("owned_ui_roles", []))
        for state in states:
            if not isinstance(state, dict) or not state.get("state_id"):
                errors.append({"code": "STATE_INVALID", "unit_id": unit_id})
                continue
            if require_runtime_plan:
                errors.extend(_validate_native_refs(source_root, state.get("source_refs", []), unit_id,
                                                    native_hashes, state_id=state["state_id"]))
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
    validation = {"errors": errors, "warnings": warnings}
    try:
        retained = _configured_formal_scope(root, inventory)
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        errors.append({"code": "PRIOR_UI_APPROVAL_INVALID", "message": str(exc)})
    else:
        if retained is not None:
            validation["retained_formal_scope"] = retained
            if retained["status"] != "PASS":
                errors.append({"code": "APPROVED_FORMAL_SCOPE_REDUCED", "rows": retained["missing"]})
    result["status"] = "validated" if not errors else "invalid"
    result["validation"] = validation
    return result


def _validate_native_refs(source_root: Path, refs: Any, unit_id: Any, cache: dict[Path, str | None],
                          *, state_id: Any = None) -> list[dict[str, Any]]:
    location = {"unit_id": unit_id}
    if state_id is not None:
        location["state_id"] = state_id
    if not isinstance(refs, list):
        return [{"code": "SOURCE_REF_INVALID", **location}]
    errors = []
    for ref in refs:
        if not isinstance(ref, dict) or not isinstance(ref.get("file"), str):
            continue
        file = Path(ref["file"])
        if file.suffix.lower() not in {".swift", ".m", ".mm", ".h", ".hpp"}:
            continue
        path = (source_root / file).resolve()
        expected = str(ref.get("sha256", "")).removeprefix("sha256:")
        if file.is_absolute() or not path.is_relative_to(source_root):
            code = "NATIVE_SOURCE_REF_OUTSIDE_ROOT"
        elif not re.fullmatch(r"[a-f0-9]{64}", expected):
            code = "NATIVE_SOURCE_REF_DIGEST_MISSING"
        else:
            if path not in cache:
                try:
                    cache[path] = digest(path.read_bytes())
                except OSError:
                    cache[path] = None
            if cache[path] is None:
                code = "NATIVE_SOURCE_REF_UNREADABLE"
            elif cache[path] != expected:
                code = "NATIVE_SOURCE_REF_DIGEST_MISMATCH"
            else:
                continue
        errors.append({"code": code, "file": file.as_posix(), **location})
    return errors


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


def _formal_scope(inventory: dict[str, Any]) -> dict[tuple[str, str], str]:
    """Read formal bindings using the source component identity across plans."""
    if inventory.get("schema_version") != 2:
        raise ValueError("formal scope comparison requires schema-2 inventories")
    owners = {}
    for unit in inventory["units"]:
        if not unit.get("required", True):
            continue
        for state in unit["required_states"]:
            if state.get("arrival_mode") != "formal":
                continue
            owners[(unit["unit_id"], unit["page_id"], state["state_id"])] = unit.get("component")
    scope = {}
    seen_ids = set()
    for row in inventory["verification_states"]:
        binding = (row.get("owner"), row.get("page_id"), row.get("state_id"))
        if binding not in owners or row.get("arrival_mode", "formal") != "formal":
            continue
        component = owners[binding]
        pair_id = row.get("verification_id")
        if not isinstance(pair_id, str) or not pair_id or pair_id in seen_ids:
            raise ValueError(f"missing or ambiguous formal verification ID: {pair_id}")
        seen_ids.add(pair_id)
        if not isinstance(component, str) or not component:
            raise ValueError(f"formal state lacks a source component: {binding[1:]}")
        state = (component, binding[2])
        if state in scope:
            raise ValueError(f"ambiguous formal scope binding: {component}/{state[1]}")
        scope[state] = binding[1]
    return scope


def compare_formal_scope(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    if before.get("status") != "approved" or not before.get("approval"):
        raise ValueError("formal scope comparison requires the previous approved inventory")
    previous = _formal_scope(before)
    if not previous:
        raise ValueError("previous approval does not contain formal verification states")
    current = _formal_scope(after)
    missing = sorted(previous.keys() - current.keys())
    return {
        "schema_version": 1, "status": "INCOMPLETE" if missing else "PASS",
        "approved_count": len(previous), "retained_count": len(previous.keys() & current.keys()),
        "missing": [{"component": component, "state_id": state, "previous_page_id": previous[(component, state)]}
                    for component, state in missing],
        "additional": [{"component": component, "state_id": state, "page_id": current[(component, state)]}
                       for component, state in sorted(current.keys() - previous.keys())],
    }


def _configured_formal_scope(root: Path, inventory: dict[str, Any]) -> dict[str, Any] | None:
    config = root / ".migbot/config.json"
    if not config.is_file():
        return None
    approval = read(config).get("prior_ui_approval")
    if approval is None:
        return None
    if not isinstance(approval, dict) or not isinstance(approval.get("path"), str):
        raise ValueError("prior_ui_approval requires a project-relative path and SHA-256")
    relative = Path(approval["path"])
    source = (root / relative).resolve()
    if relative.is_absolute() or not source.is_relative_to(root):
        raise ValueError("prior_ui_approval must stay inside the project")
    raw = source.read_bytes()
    fingerprint = digest(raw)
    if fingerprint != approval.get("sha256"):
        raise ValueError("prior_ui_approval SHA-256 changed")
    return {**compare_formal_scope(json.loads(raw), inventory),
            "before_path": relative.as_posix(), "before_sha256": fingerprint}


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
    parser.add_argument("command", choices=("draft", "pair-states", "validate", "approve", "diff",
                                            "compare-formal-scope"))
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
            before, after = (Path(value) for value in (args.before, args.after))
            if args.command == "compare-formal-scope":
                if Path(args.out).resolve() in {before.resolve(), after.resolve()}:
                    raise ValueError("formal scope comparison output must be separate from the inventories")
                before_raw, after_raw = before.read_bytes(), after.read_bytes()
                result = compare_formal_scope(json.loads(before_raw), json.loads(after_raw))
                result.update(before_sha256=digest(before_raw), after_sha256=digest(after_raw))
            else:
                result = diff(read(before), read(after))
            write(Path(args.out), result)
    except (OSError, ValueError, ImportError, KeyError, TypeError, AttributeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if args.command == "draft":
        print(json.dumps({"output": args.out, "units": len(result.get("units", [])), "status": result.get("status")}, ensure_ascii=False))
    else:
        print(json.dumps({"output": args.out, "status": result.get("status")}, ensure_ascii=False))
    if args.command == "validate" and (args.receipt_only or args.require_runtime_plan) and result["status"] != "validated":
        return 2
    if args.command == "compare-formal-scope" and result["status"] != "PASS":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
