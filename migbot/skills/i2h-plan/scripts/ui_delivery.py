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


TOOL_VERSION = "i2h-ui-delivery/1.0"


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


def views_from_evidence(root: Path) -> list[dict[str, Any]]:
    path = evidence_path(root)
    if path.is_file():
        payload = read(path)
        views = payload.get("views", [])
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


def draft(project_root: str | Path, out: str | Path) -> dict[str, Any]:
    root = Path(project_root).expanduser().resolve()
    views = views_from_evidence(root)
    source_root = evidence_source_root(root)
    presentation_hints = _presentation_hints(source_root, views)
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
        units.append({
            "unit_id": f"ios.{index:04d}.{slug}",
            "page_id": page_id,
            "component": component,
            "presentation_role": hint["presentation_role"],
            "presentation": {
                "source": hint["source"],
                "harmony_mapping": hint["harmony_mapping"],
                **({"host_source": hint["host_source"], "source_line": hint["source_line"]} if hint.get("host_source") else {}),
            },
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
    evidence = evidence_path(root)
    target_hash = None
    if evidence.is_file():
        target_hash = read(evidence).get("target_input_sha256")
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
        "component_exclusions": [],
        "presentation": {"source": "pending-review", "runtime_required": True},
        "toolchain": {"sdk_definitions": None, "product": None},
        "warnings": [] if units else ["no static iOS views found; run i2h-spec Phase A"],
    }
    write(Path(out), result)
    return result


def validate(project_root: str | Path, inventory: dict[str, Any]) -> dict[str, Any]:
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


def approve(project_root: str | Path, inventory: dict[str, Any], confirmation_ref: str) -> dict[str, Any]:
    result = validate(project_root, inventory)
    if result["validation"]["errors"]:
        raise ValueError("cannot approve invalid UI delivery inventory")
    if not confirmation_ref or not confirmation_ref.strip():
        raise ValueError("confirmation_ref is required for approval")
    result["status"] = "approved"
    result["approval"] = {"confirmation_ref": confirmation_ref, "scope": result.get("scope", "full_ui")}
    return result


def diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    left = {u.get("unit_id"): u for u in before.get("units", []) if isinstance(u, dict)}
    right = {u.get("unit_id"): u for u in after.get("units", []) if isinstance(u, dict)}
    return {"schema_version": 1, "added": sorted(set(right) - set(left)), "removed": sorted(set(left) - set(right)), "changed": sorted(k for k in set(left) & set(right) if left[k] != right[k])}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("draft", "validate", "approve", "diff"))
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--inventory")
    parser.add_argument("--confirmation-ref")
    parser.add_argument("--before")
    parser.add_argument("--after")
    args = parser.parse_args(argv)
    try:
        if args.command == "draft":
            result = draft(args.project_root, args.out)
        elif args.command == "validate":
            if not args.inventory:
                raise ValueError("--inventory is required")
            result = validate(args.project_root, read(Path(args.inventory)))
            write(Path(args.out), result)
        elif args.command == "approve":
            if not args.inventory:
                raise ValueError("--inventory is required")
            result = approve(args.project_root, read(Path(args.inventory)), args.confirmation_ref or "")
            write(Path(args.out), result)
        else:
            if not args.before or not args.after:
                raise ValueError("--before and --after are required")
            result = diff(read(Path(args.before)), read(Path(args.after)))
            write(Path(args.out), result)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if args.command == "draft":
        print(json.dumps({"output": args.out, "units": len(result.get("units", [])), "status": result.get("status")}, ensure_ascii=False))
    else:
        print(json.dumps({"output": args.out, "status": result.get("status")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
