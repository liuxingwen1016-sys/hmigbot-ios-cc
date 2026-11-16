#!/usr/bin/env python3
"""Build deterministic iOS UI and resource evidence for the i2h pipeline.

The iOS pipeline cannot use Android's ``view.xml``/UIAutomator facts.  This
script is the static replacement: it records the source anchors, SwiftUI/UIKit
surface, asset variants, localization entries and code-to-resource references
that the LLM and downstream stages must consume.  It deliberately does not
invent runtime values.  A simulator capture, when available, is an additional
sidecar handled by :mod:`runtime_view`.

The script uses only the Python standard library so it remains executable from
Claude Code's copied ``.claude/skills`` tree on a clean machine.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Iterable

try:
    from ios_style_triggers import detect as detect_style_triggers
    from source_index import build_index, classify_view_surface
except ImportError:  # pragma: no cover - package/installed-tree fallback
    from .ios_style_triggers import detect as detect_style_triggers  # type: ignore
    from .source_index import build_index, classify_view_surface  # type: ignore

try:
    from ui_obligations import declaration_slice, parse_ui_obligations
except ImportError:  # pragma: no cover - package/installed-tree fallback
    from .ui_obligations import declaration_slice, parse_ui_obligations  # type: ignore

try:
    from ios_declaration_scope import SwiftSource, view_kind
except ImportError:  # pragma: no cover - package/installed-tree fallback
    from .ios_declaration_scope import SwiftSource, view_kind  # type: ignore


TOOL_VERSION = "i2h-ui-evidence/1.3"
SCHEMA_VERSION = 1


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def source_digest(root: Path, files: Iterable[Path]) -> str:
    """Hash path + content, making evidence invalid when an input changes."""
    digest = hashlib.sha256()
    for path in sorted({p.resolve() for p in files if p.is_file()}, key=lambda p: p.as_posix()):
        try:
            rel = relative(path, root)
        except ValueError:
            rel = path.as_posix()
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def parse_properties_scoped(source: "SwiftSource", declaration: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract properties using scoped declaration boundaries to prevent sibling contamination."""
    props = source.properties(declaration)
    result = []
    for prop in props:
        if prop["name"] is None:
            continue
        row: dict[str, Any] = {
            "name": prop["name"],
            "wrapper": prop["wrapper"],
            "type": prop["type"],
            "line": prop["line"],
        }
        if "default_value" in prop:
            row["default_value"] = prop["default_value"]
        result.append(row)
    return result


def detect_views(path: Path, root: Path) -> list[dict[str, Any]]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []

    # Use SwiftSource for proper declaration scoping
    source = SwiftSource(text)
    result = []
    known_components = (
        "VStack", "HStack", "ZStack", "List", "ScrollView", "LazyVStack", "LazyHStack",
        "NavigationStack", "NavigationView", "NavigationLink", "TabView", "Form", "Group",
        "Button", "TextField", "SecureField", "Picker", "Toggle", "DatePicker", "Image",
        "Sheet", "Alert", "UICollectionView", "UITableView", "UIScrollView", "UIButton",
        "UILabel", "UIImageView", "UITextField", "UIStackView",
    )

    for declaration in source.declarations:
        if declaration["kind"] not in {"struct", "class"}:
            continue
        bases = source.bases_for(declaration)
        kind = view_kind(bases)
        if kind is None:
            continue

        # Extract scoped text for this declaration only
        scoped_text = source.owned_text(declaration, code=False)

        # Components: search only in scoped text
        components = [name for name in known_components if re.search(r"\b" + re.escape(name) + r"\b", scoped_text)]

        # Interactions: search only in scoped text
        interactions = []
        interaction_patterns = {
            "navigation": r"\bNavigation(Link|Stack|View)\b",
            "button": r"\bButton\b|\.onTapGesture\s*\(",
            "input": r"\b(TextField|SecureField|Picker|Toggle|DatePicker)\b",
            "sheet": r"\.(sheet|fullScreenCover)\s*\(",
            "alert": r"\.alert\s*\(",
            "list": r"\b(List|ForEach|UICollectionView|UITableView)\b",
        }
        for interaction, pattern in interaction_patterns.items():
            for match in re.finditer(pattern, scoped_text):
                interactions.append({
                    "type": interaction,
                    "evidence": "source pattern",
                    "line": line_number(text, match.start())
                })

        # Body line using scoped detection
        body_line = source.body_line(declaration)

        # Properties using scoped extraction
        properties = parse_properties_scoped(source, declaration)

        # Declaration text for ui_obligations
        declaration_text = declaration_slice(text, declaration["start_offset"])
        ui_obligations = parse_ui_obligations(
            declaration_text,
            line_offset=declaration["line"] - 1,
        )

        # Calculate line_count for this declaration only
        if declaration["end_offset"] is not None:
            decl_text = text[declaration["start_offset"]:declaration["end_offset"]]
            line_count = len(decl_text.splitlines())
            end_line = declaration["end_line"]
        else:
            line_count = 0
            end_line = None

        result.append({
            "view_name": declaration["name"],
            "type": kind,
            "bases": bases,
            "file_path": relative(path, root),
            "line_count": line_count,
            "declaration_line": declaration["line"],
            "declaration_end_line": end_line,
            "body_line": body_line,
            "properties": properties,
            "has_state": bool(properties),
            "state_count": len(properties),
            "ui_structure": {
                "key_components": components,
                "container": components[0] if components else None,
                "depth_estimate": max(0, scoped_text.count("{") - scoped_text.count("}") // 2),
            },
            "interactions": interactions,
            "ui_obligations": ui_obligations,
            "surface": classify_view_surface(declaration["name"], bases, relative(path, root), scoped_text),
            "confidence": "high",
            "source_sha256": sha256_bytes(text.encode("utf-8")),
            "scoped_diagnostics": source.scope_diagnostics(declaration),
        })
    return result


def decode_string(value: str) -> str:
    try:
        return json.loads('"' + value + '"')
    except json.JSONDecodeError:
        return value.replace(r'\"', '"').replace(r"\\", "\\")


def parse_strings(path: Path) -> dict[str, str]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {}
    # Supports escaped quotes and escaped newlines, while ignoring comments.
    pattern = re.compile(r'"((?:\\.|[^"\\])*)"\s*=\s*"((?:\\.|[^"\\])*)"\s*;')
    return {decode_string(key): decode_string(value) for key, value in pattern.findall(text)}


def file_entry(path: Path, root: Path, **extra: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {"path": relative(path, root), "exists": path.is_file()}
    if path.is_file():
        entry["size_bytes"] = path.stat().st_size
        entry["sha256"] = sha256_file(path)
    entry.update(extra)
    return entry


def parse_catalog(catalog: Path, root: Path) -> dict[str, Any]:
    result: dict[str, Any] = {"name": catalog.stem, "path": relative(catalog, root), "images": [], "colors": [], "app_icons": [], "data": [], "symbols": [], "warnings": []}
    for suffix, key in (("*.imageset", "images"), ("*.colorset", "colors"), ("*.appiconset", "app_icons"), ("*.dataset", "data"), ("*.symbolset", "symbols")):
        for asset in sorted(catalog.rglob(suffix)):
            contents = asset / "Contents.json"
            payload = read_json(contents)
            item: dict[str, Any] = {"name": asset.stem, "path": relative(asset, root), "contents_sha256": sha256_file(contents) if contents.is_file() else None}
            if not contents.is_file():
                result["warnings"].append({"type": "missing-contents", "path": item["path"]})
            if key in ("images", "app_icons"):
                item["variants"] = []
                for variant in payload.get("images", []):
                    if not isinstance(variant, dict):
                        continue
                    filename = variant.get("filename")
                    variant_row = {k: variant.get(k) for k in ("idiom", "scale", "size", "role", "subtype", "appearances") if k in variant}
                    if filename:
                        variant_path = asset / filename
                        variant_row.update(file_entry(variant_path, root, filename=filename))
                    item["variants"].append(variant_row)
                item["missing_variants"] = [v.get("filename") for v in item["variants"] if v.get("filename") and not v.get("exists")]
            elif key == "colors":
                item["variants"] = []
                for variant in payload.get("colors", []):
                    if not isinstance(variant, dict):
                        continue
                    color = variant.get("color", {}) if isinstance(variant.get("color", {}), dict) else {}
                    item["variants"].append({"idiom": variant.get("idiom", "universal"), "appearances": variant.get("appearances", []), "color_space": color.get("color-space", "srgb"), "components": color.get("components", {})})
            else:
                item["payload"] = payload
            result[key].append(item)
    return result


def scan_resources(root: Path) -> tuple[dict[str, Any], list[Path]]:
    excluded_parts = {".git", ".i2h", ".migbot", "spec", "build", "DerivedData"}
    def eligible(path: Path) -> bool:
        return not any(part in excluded_parts for part in path.parts)

    catalogs = [parse_catalog(path, root) for path in sorted(root.rglob("*.xcassets")) if eligible(path)]
    source_files = [
        path for path in sorted(root.rglob("*.swift"))
        if eligible(path) and "Tests" not in path.parts and "Test" not in path.name
    ]
    input_files: list[Path] = list(source_files)
    input_files += [p for p in root.rglob("*.json") if eligible(p)]
    input_files += [p for p in root.rglob("*.strings") if eligible(p)]
    input_files += [p for p in root.rglob("*.xcstrings") if eligible(p)]
    input_files += [p for p in root.rglob("*.stringsdict") if eligible(p)]
    references: list[dict[str, Any]] = []

    # Use ios_localizations for complete xcstrings/strings/stringsdict support
    loc_entries: list[dict[str, Any]] = []
    loc_sources: list[dict[str, Any]] = []
    loc_diagnostics: list[dict[str, Any]] = []
    try:
        from ios_localizations import scan_localizations
        loc_facts = scan_localizations(root, eligible)
        localizations = loc_facts.get("localizations", {})
        loc_entries = loc_facts.get("entries", [])
        loc_sources = loc_facts.get("sources", [])
        loc_diagnostics = loc_facts.get("diagnostics", [])
        # Add localization source files to input tracking
        for source in loc_sources:
            source_path = root / source["file"]
            if source_path.is_file():
                input_files.append(source_path)
    except (ImportError, Exception) as exc:
        # Fallback to legacy .strings-only parsing
        localizations: dict[str, dict[str, Any]] = {}
        loc_diagnostics.append({"code": "localization-import-failed", "error": str(exc)})
        for strings in sorted(root.rglob("*.strings")):
            if not eligible(strings):
                continue
            language = next((part[:-5] for part in strings.parts if part.endswith(".lproj")), "und")
            localizations.setdefault(language, {})[relative(strings, root)] = parse_strings(strings)
    # Scan fonts (TTF/OTF) and registrations
    font_facts: dict[str, Any] = {"fonts": [], "registrations": []}
    try:
        from ios_fonts import scan_fonts
        font_facts = scan_fonts(root, eligible)
        # Add font files to input tracking
        for font in font_facts.get("fonts", []):
            font_path = root / font["path"]
            if font_path.is_file():
                input_files.append(font_path)
        # Add Info.plist source files to input tracking — UIAppFonts registration
        # affects font_registrations output so plist bytes must hash the input.
        for info_plist in sorted(root.rglob("Info.plist")):
            if eligible(info_plist) and info_plist.is_file():
                input_files.append(info_plist)
    except (ImportError, Exception) as exc:
        loc_diagnostics.append({"code": "font-scan-failed", "error": str(exc)})

    # Scan theme source files for Color/spacing/Font expressions
    theme_facts: dict[str, Any] = {"themes": [], "colors": [], "spacing": [], "fonts": []}
    try:
        from ios_theme import scan_themes
        theme_facts = scan_themes(root, eligible)
        # Theme source files are already in source_files
    except (ImportError, Exception) as exc:
        loc_diagnostics.append({"code": "theme-scan-failed", "error": str(exc)})
    for path in root.rglob("*.swift"):
        if not eligible(path) or "Tests" in path.parts or "Test" in path.name:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        # Keep all references with source anchors; unknown references are a
        # finding for the LLM, never silently dropped.
        patterns = {
            "image": r"\bImage\s*\(\s*\"([^\"]+)\"|UIImage\s*\(named:\s*\"([^\"]+)\"",
            "color": r"\bColor\s*\(\s*\"([^\"]+)\"",
            "system_symbol": r"\bImage\s*\(\s*systemName:\s*\"([^\"]+)\"|\bUIImage\s*\(\s*systemName:\s*\"([^\"]+)\"",
            "localization": r"\bNSLocalizedString\s*\(\s*\"([^\"]+)\"",
        }
        for kind, pattern in patterns.items():
            for match in re.finditer(pattern, text):
                name = next((group for group in match.groups() if group), None)
                if not name:
                    continue
                input_files.append(path)
                references.append({"kind": kind, "name": name, "file": relative(path, root), "line": line_number(text, match.start())})
    all_assets = [p for p in root.rglob("*") if eligible(p) and p.is_file() and (p.suffix.lower() in {".png", ".jpg", ".jpeg", ".pdf", ".svg", ".gif", ".webp"})]
    input_files += all_assets
    inventory = {
        "schema_version": SCHEMA_VERSION,
        "tool_version": TOOL_VERSION,
        "project_root": str(root),
        "catalogs": catalogs,
        "source_files": [file_entry(path, root) for path in source_files],
        "localizations": localizations,
        "localization_entries": loc_entries,
        "localization_sources": loc_sources,
        "fonts": font_facts.get("fonts", []),
        "font_registrations": font_facts.get("registrations", []),
        "themes": theme_facts.get("themes", []),
        "code_references": references,
        "standalone_assets": [file_entry(path, root) for path in sorted(all_assets)],
        "diagnostics": loc_diagnostics,
        "summary": {
            "catalog_count": len(catalogs),
            "images": sum(len(c["images"]) for c in catalogs),
            "colors": sum(len(c["colors"]) for c in catalogs),
            "app_icons": sum(len(c["app_icons"]) for c in catalogs),
            "localization_languages": len(localizations),
            "localization_entry_count": len(loc_entries),
            "localization_source_count": len(loc_sources),
            "font_count": font_facts.get("total_count", 0),
            "font_resolved_count": font_facts.get("resolved_count", 0),
            "theme_file_count": theme_facts.get("summary", {}).get("theme_file_count", 0),
            "theme_color_count": theme_facts.get("summary", {}).get("color_count", 0),
            "theme_spacing_count": theme_facts.get("summary", {}).get("spacing_count", 0),
            "theme_font_count": theme_facts.get("summary", {}).get("font_count", 0),
            "code_reference_count": len(references),
            "source_file_count": len(source_files),
        },
    }
    return inventory, input_files


def build_res_index(inventory: dict[str, Any], views: list[dict[str, Any]], target_hash: str, runtime_required: bool = False) -> dict[str, dict[str, Any]]:
    metadata = {"schema_version": 1, "tool_version": TOOL_VERSION, "target_input_sha256": target_hash}
    values: list[dict[str, Any]] = []
    drawables: dict[str, Any] = {}
    usage: dict[str, Any] = {}
    tokens: list[dict[str, Any]] = []
    refs = inventory.get("code_references", [])
    page_by_file = {view["file_path"]: "page_%04d_%s" % (index, view["view_name"]) for index, view in enumerate(views, 1) if view.get("surface") == "screen"}
    refs_by_name: dict[str, list[dict[str, Any]]] = {}
    for ref in refs:
        refs_by_name.setdefault(ref["name"], []).append(ref)
    for catalog in inventory.get("catalogs", []):
        for color in catalog.get("colors", []):
            resource_id = "color/" + color["name"]
            values.append({"key": color["name"], "resource_id": resource_id, "type": "color", "name": color["name"], "config": {"variants": color.get("variants", [])}, "source": {"file": color["path"], "sha256": color.get("contents_sha256")}, "tier": "T1"})
            token_refs = refs_by_name.get(color["name"], [])
            tokens.append({"token_id": "ios-color-" + color["name"], "resource_id": resource_id, "role": "color", "value": {"variants": color.get("variants", [])}, "status": "resolved", "pages": sorted({page_by_file.get(ref["file"]) for ref in token_refs if page_by_file.get(ref["file"])}), "source": {"file": color["path"]}})
        for image in catalog.get("images", []) + catalog.get("app_icons", []):
            resource_id = "drawable/" + image["name"]
            drawables[resource_id] = {"kind": "image", "name": image["name"], "variants": image.get("variants", []), "source": {"file": image["path"], "sha256": image.get("contents_sha256")}}
    for language, files in inventory.get("localizations", {}).items():
        for file_path, entries in files.items():
            for key, value in entries.items():
                values.append({"key": key, "resource_id": "string/" + key, "type": "string", "name": key, "config": {"locale": language, "value": value}, "source": {"file": file_path}, "tier": "T1"})
    for name, rows in refs_by_name.items():
        usage[name] = {"references": rows, "resolved": any(name == d.get("name") for d in drawables.values()) or any(name == v.get("name") for v in values), "disposition": "resolved" if name in {d.get("name") for d in drawables.values()} or name in {v.get("name") for v in values} else "unresolved"}
    usage_payload = {**metadata, "resources": usage}
    return {"values": {**metadata, "resources": values}, "drawables": {**metadata, "resources": drawables}, "usage": usage_payload, "design-tokens": {**metadata, "tokens": tokens}, "handoff": {**metadata, "source": "ios-static-evidence", "runtime_required": runtime_required, "unresolved": [name for name, row in usage.items() if row["disposition"] == "unresolved"]}}


def run(
    project_root: str,
    output: str,
    res_index: str | None = None,
    runtime_required: bool = False,
    source_index_output: str | None = None,
    source_index_force: bool = False,
) -> dict[str, Any]:
    root = Path(project_root).expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"iOS project directory not found: {project_root}")
    inventory, inputs = scan_resources(root)
    views = []
    for swift in sorted(root.rglob("*.swift")):
        if "Tests" not in swift.parts and "Test" not in swift.name:
            views.extend(detect_views(swift, root))
    pages = [view for view in views if view.get("surface") == "screen"]
    components = [view for view in views if view.get("surface") != "screen"]
    target_hash = source_digest(root, inputs)
    output_path = Path(output).expanduser().resolve()
    index_path = Path(source_index_output).expanduser().resolve() if source_index_output else output_path.parent / "cache/source-index.json"
    source_index = build_index(
        root,
        index_path,
        source_tree_hash=target_hash,
        skill_root=Path(__file__).resolve().parents[1],
        force=source_index_force,
    )
    inventory["target_input_sha256"] = target_hash
    inventory["source_index"] = {
        "path": str(index_path),
        "cache_key": source_index.get("cache_key"),
        "cache_hit": source_index.get("cache_hit", False),
        "source_tree_sha256": source_index.get("source_tree_sha256"),
    }
    inventory["views"] = views
    inventory["pages"] = pages
    inventory["components"] = components
    inventory["summary"]["view_count"] = len(views)
    inventory["summary"]["page_count"] = len(pages)
    inventory["summary"]["component_count"] = len(components)
    payload = {"schema_version": SCHEMA_VERSION, "tool_version": TOOL_VERSION, "target_input_sha256": target_hash, "project_root": str(root), "runtime_required": runtime_required, "views": views, "pages": pages, "components": components, "resources": inventory}
    atomic_json(output_path, payload)
    # Stable handoff consumed by execute/resource-facts.  Keep it separate
    # from the human-facing inventory so downstream scripts can verify the
    # exact source snapshot without parsing the large evidence document.
    receipt = {
        "schema_version": 1,
        "target_input_sha256": target_hash,
        "source": "ios-static-evidence",
        "runtime_required": runtime_required,
        "inventory": str(output_path),
    }
    spec_dir = output_path.parent.parent
    if output_path.parent.name == ".i2h" and spec_dir.name == "spec":
        style_path = spec_dir / "ref/ios-style-triggers.json"
        style = detect_style_triggers(root)
        style["target_input_sha256"] = target_hash
        atomic_json(style_path, style)
        receipt["style_triggers_sha256"] = sha256_file(style_path)
    atomic_json(output_path.parent / "target-input.json", receipt)
    if res_index:
        index = build_res_index(inventory, pages, target_hash, runtime_required)
        destination = Path(res_index)
        for name, value in index.items():
            atomic_json(destination / (name + ".json"), value)
    return payload


def build_skeleton(payload: dict[str, Any]) -> dict[str, Any]:
    """Project skeleton consumed by the semantic Phase-A steps."""
    views = payload.get("pages") or [view for view in payload.get("views", []) if view.get("surface") == "screen"]
    components = payload.get("components") or [view for view in payload.get("views", []) if view.get("surface") != "screen"]
    resources = payload.get("resources", {})
    source_files = resources.get("source_files", [])
    swift_files = sorted(
        {
            row.get("path")
            for row in source_files
            if isinstance(row, dict) and row.get("path")
        }
    )
    if not swift_files:
        # Keep compatibility with evidence files produced by older installers.
        swift_files = sorted({view.get("file_path") for view in views if view.get("file_path")})
    swiftui_views = [
        {
            "class_name": view["view_name"],
            "file_path": view["file_path"],
            "line_count": view.get("line_count", 0),
            "has_state": view.get("has_state", False),
            "state_count": view.get("state_count", 0),
        }
        for view in views if view.get("type") == "SwiftUI View"
    ]
    uikit_viewcontrollers = [
        {
            "class_name": view["view_name"],
            "file_path": view["file_path"],
            "line_count": view.get("line_count", 0),
        }
        for view in views if view.get("type") != "SwiftUI View"
    ]
    catalogs = resources.get("catalogs", [])
    assets = [catalog.get("path") for catalog in catalogs if catalog.get("path")]
    root = Path(payload.get("project_root", ""))
    info_plists = sorted(
        path.relative_to(root).as_posix() for path in root.rglob("Info.plist") if path.is_file()
    ) if root.is_dir() else []
    return {
        "schema_version": 1,
        "project_name": Path(payload.get("project_root", "")).name,
        "target_input_sha256": payload.get("target_input_sha256"),
        "swift_files": swift_files,
        "swiftui_views": swiftui_views,
        "shared_components": [
            {
                "class_name": view["view_name"],
                "file_path": view["file_path"],
                "line_count": view.get("line_count", 0),
            }
            for view in components
        ],
        "uikit_viewcontrollers": uikit_viewcontrollers,
        "info_plist": info_plists[0] if info_plists else None,
        "assets": assets,
        "source_file_count": len(swift_files),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_root", help="iOS project root")
    parser.add_argument("--output", default="spec/.i2h/ui-evidence.json", help="evidence JSON output")
    parser.add_argument("--resources-output", help="alias for --output, retained for pipeline compatibility")
    parser.add_argument("--res-index", help="optional spec/baseline/res-index directory")
    parser.add_argument("--skeleton-output", help="optional Phase-A project skeleton JSON")
    parser.add_argument("--runtime-required", action="store_true", help="require audited iOS runtime evidence downstream")
    parser.add_argument("--source-index-output", help="content-addressed Swift source index output")
    parser.add_argument("--source-index-force", action="store_true", help="rebuild source index even when cache key matches")
    args = parser.parse_args(argv)
    try:
        payload = run(
            args.project_root,
            args.resources_output or args.output,
            args.res_index,
            args.runtime_required,
            args.source_index_output,
            args.source_index_force,
        )
        if args.skeleton_output:
            atomic_json(Path(args.skeleton_output), build_skeleton(payload))
    except (FileNotFoundError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    summary = payload["resources"]["summary"]
    print(json.dumps({"output": args.resources_output or args.output, "target_input_sha256": payload["target_input_sha256"], "summary": summary}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
