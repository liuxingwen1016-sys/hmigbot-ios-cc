#!/usr/bin/env python3
"""Content-addressed static index for an iOS source tree.

The index is deliberately deterministic.  Claude workers can consume a page
or feature slice from this file instead of reopening every Swift file.  The
index is also safe to keep in ``spec/.i2h/cache`` because its key includes the
source tree, tool implementation, and prompt/template inputs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable


TOOL_VERSION = "i2h-source-index/1.1"
SCHEMA_VERSION = 1
DEFAULT_TEMPLATE_GLOBS = ("templates/**/*.md", "references/**/*.md")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tree_hash(root: Path, files: Iterable[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted({item.resolve() for item in files if item.is_file()}, key=lambda item: item.as_posix()):
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            rel = path.as_posix()
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def template_hash(skill_root: Path | None = None, template_paths: Iterable[Path] = ()) -> str:
    """Hash reference/template files without depending on their absolute path."""
    files = [Path(path) for path in template_paths]
    if skill_root and skill_root.is_dir():
        for pattern in DEFAULT_TEMPLATE_GLOBS:
            files.extend(skill_root.glob(pattern))
    digest = hashlib.sha256()
    for path in sorted({item.resolve() for item in files if item.is_file()}, key=lambda item: item.as_posix()):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _line(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _properties(text: str) -> list[dict[str, Any]]:
    pattern = re.compile(
        r"@(?P<wrapper>StateObject|ObservedObject|EnvironmentObject|Environment|Binding|"
        r"State|AppStorage|SceneStorage|FocusState|Published)"
        r"(?:\([^\n)]*\))?\s+(?:(?:private|internal|public|fileprivate)\s+)?"
        r"var\s+(?P<name>[A-Za-z_]\w*)\s*:\s*(?P<type>[^=\n{]+?)"
        r"(?:\s*=\s*(?P<default>[^\n]+))?(?=\n|$)"
    )
    rows = []
    for match in pattern.finditer(text):
        row: dict[str, Any] = {
            "name": match.group("name"),
            "wrapper": "@" + match.group("wrapper"),
            "type": match.group("type").strip(),
            "line": _line(text, match.start()),
        }
        if match.group("default"):
            row["default_value"] = match.group("default").strip()
        rows.append(row)
    return rows


def _declarations(text: str) -> list[dict[str, Any]]:
    pattern = re.compile(
        r"\b(?P<kind>struct|class|enum|protocol|actor|extension)\s+"
        r"(?P<name>[A-Za-z_]\w*)\s*(?::\s*(?P<bases>[^\{\n]+))?"
    )
    return [
        {
            "kind": match.group("kind"),
            "name": match.group("name"),
            "bases": [part.strip() for part in (match.group("bases") or "").split(",") if part.strip()],
            "line": _line(text, match.start()),
        }
        for match in pattern.finditer(text)
    ]


def _methods(text: str) -> list[dict[str, Any]]:
    pattern = re.compile(r"\b(?:static\s+|class\s+|private\s+|internal\s+|public\s+|mutating\s+|override\s+)*func\s+([A-Za-z_]\w*)\s*\(([^)]*)\)")
    result = []
    for match in pattern.finditer(text):
        result.append({"name": match.group(1), "signature": match.group(0).strip(), "line": _line(text, match.start())})
    return result


def _imports(text: str) -> list[str]:
    return sorted(set(re.findall(r"^\s*import\s+([A-Za-z_][\w.]*)", text, re.MULTILINE)))


def _routes(text: str) -> list[dict[str, Any]]:
    patterns = (
        ("NavigationLink", r"\bNavigationLink\b(?:\s*\([^\n]*?destination:\s*([A-Za-z_]\w*))?"),
        ("navigationDestination", r"\.navigationDestination\s*\([^\n]*?for:\s*([^,\)]+)"),
        ("sheet", r"\.(?:sheet|fullScreenCover)\s*\([^\n]*?"),
        ("route", r"\b(?:case|enum)\s+([A-Za-z_]\w*)")
    )
    result: list[dict[str, Any]] = []
    for kind, pattern in patterns:
        for match in re.finditer(pattern, text):
            destination = next((group.strip() for group in match.groups() if group and group.strip()), None)
            result.append({"kind": kind, "destination": destination, "line": _line(text, match.start())})
    return result


def _resources(text: str) -> list[dict[str, Any]]:
    patterns = {
        "image": r"\bImage\s*\(\s*\"([^\"]+)\"|\bUIImage\s*\(named:\s*\"([^\"]+)\"",
        "system_symbol": r"\bImage\s*\(\s*systemName:\s*\"([^\"]+)\"|\bUIImage\s*\(\s*systemName:\s*\"([^\"]+)\"",
        "color": r"\bColor\s*\(\s*\"([^\"]+)\"",
        "localization": r"\bNSLocalizedString\s*\(\s*\"([^\"]+)\"",
    }
    result: list[dict[str, Any]] = []
    for kind, pattern in patterns.items():
        for match in re.finditer(pattern, text):
            name = next((group for group in match.groups() if group), None)
            if name:
                result.append({"kind": kind, "name": name, "line": _line(text, match.start())})
    return result


def classify_view_surface(name: str, bases: Iterable[str], relative_path: str, text: str) -> str:
    """Separate navigable screens from reusable SwiftUI view components."""
    base_text = " ".join(bases)
    if any(token in base_text for token in ("UIViewRepresentable", "NSViewRepresentable", "ViewModifier")):
        return "shared_component"
    path_parts = {part.lower() for part in Path(relative_path).parts}
    screen_path = bool(path_parts & {"views", "screens", "pages", "viewcontrollers"})
    component_path = bool(path_parts & {"components", "design", "services", "widgets"})
    if name == "RootView":
        return "screen"
    if "UIViewController" in base_text or name.endswith("ViewController"):
        return "screen"
    if screen_path and not component_path and "View" in base_text:
        return "screen"
    if name.endswith("View") and any(token in text for token in ("NavigationStack", "TabView", "navigationDestination")):
        return "screen"
    return "shared_component"


def _read_swift_files(root: Path) -> list[Path]:
    return [
        path for path in sorted(root.rglob("*.swift"))
        if "Tests" not in path.parts and not path.name.endswith("Tests.swift") and ".git" not in path.parts
    ]


def build_index(
    project_root: str | Path,
    output: str | Path | None = None,
    *,
    source_tree_hash: str | None = None,
    skill_root: str | Path | None = None,
    template_paths: Iterable[str | Path] = (),
    force: bool = False,
) -> dict[str, Any]:
    root = Path(project_root).expanduser().resolve()
    files = _read_swift_files(root)
    source_hash = source_tree_hash or _tree_hash(root, files)
    templates_hash = template_hash(Path(skill_root).resolve() if skill_root else None, [Path(path) for path in template_paths])
    key = _sha256_bytes(f"{source_hash}\0{TOOL_VERSION}\0{templates_hash}".encode("utf-8"))
    output_path = Path(output).expanduser().resolve() if output else root / "spec/.i2h/cache/source-index.json"
    if not force and output_path.is_file():
        try:
            cached = json.loads(output_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            cached = None
        if isinstance(cached, dict) and cached.get("cache_key") == key:
            cached["cache_hit"] = True
            # Keep the on-disk receipt aligned with the value returned to the
            # caller so downstream reports can inspect the cache hit without
            # depending on in-process state.
            output_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = output_path.with_name(output_path.name + ".tmp")
            temporary.write_text(json.dumps(cached, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            temporary.replace(output_path)
            return cached

    declarations_by_name: dict[str, str] = {}
    texts: dict[Path, str] = {}
    for path in files:
        try:
            texts[path] = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for declaration in _declarations(texts[path]):
            declarations_by_name.setdefault(declaration["name"], _relative(path, root))

    entries: list[dict[str, Any]] = []
    pages: list[dict[str, Any]] = []
    components: list[dict[str, Any]] = []
    for path in files:
        text = texts.get(path)
        if text is None:
            continue
        rel = _relative(path, root)
        declarations = _declarations(text)
        declared_names = {row["name"] for row in declarations}
        identifiers = set(re.findall(r"\b[A-Z][A-Za-z0-9_]*\b", text))
        dependencies = sorted(
            name for name in identifiers
            if name in declarations_by_name and name not in declared_names
        )
        entry = {
            "path": rel,
            "sha256": _sha256_file(path),
            "line_count": len(text.splitlines()),
            "imports": _imports(text),
            "declarations": declarations,
            "properties": _properties(text),
            "methods": _methods(text),
            "dependencies": [{"name": name, "file": declarations_by_name[name]} for name in dependencies],
            "routes": _routes(text),
            "resources": _resources(text),
        }
        entries.append(entry)
        for declaration in declarations:
            if "View" in declaration["bases"] or any("View" in base for base in declaration["bases"]):
                surface = classify_view_surface(declaration["name"], declaration["bases"], rel, text)
                view = {
                    "page_id": f"page_{len(pages) + 1:04d}_{declaration['name']}",
                    "view_name": declaration["name"],
                    "file_path": rel,
                    "declaration_line": declaration["line"],
                    "dependencies": dependencies,
                    "surface": surface,
                }
                if surface == "screen":
                    pages.append(view)
                else:
                    view["component_id"] = f"component_{len(components) + 1:04d}_{declaration['name']}"
                    view.pop("page_id", None)
                    components.append(view)

    index: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "tool_version": TOOL_VERSION,
        "project_root": str(root),
        "source_tree_sha256": source_hash,
        "template_sha256": templates_hash,
        "cache_key": key,
        "cache_hit": False,
        "swift_files": entries,
        "pages": pages,
        "components": components,
        "summary": {
            "swift_file_count": len(entries),
            "page_count": len(pages),
            "component_count": len(components),
            "declaration_count": sum(len(row["declarations"]) for row in entries),
            "method_count": sum(len(row["methods"]) for row in entries),
        },
    }
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = output_path.with_name(output_path.name + ".tmp")
        temporary.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(output_path)
    return index


def slice_index(index: dict[str, Any], *, page_ids: Iterable[str] = (), paths: Iterable[str] = ()) -> dict[str, Any]:
    """Return a small immutable worker context from the full index."""
    wanted_pages = set(page_ids)
    wanted_paths = set(paths)
    pages = [page for page in index.get("pages", []) if page.get("page_id") in wanted_pages or page.get("file_path") in wanted_paths]
    wanted_paths.update(page.get("file_path") for page in pages if page.get("file_path"))
    files = [row for row in index.get("swift_files", []) if row.get("path") in wanted_paths]
    return {
        "schema_version": index.get("schema_version"),
        "cache_key": index.get("cache_key"),
        "source_tree_sha256": index.get("source_tree_sha256"),
        "pages": pages,
        "swift_files": files,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_root")
    parser.add_argument("--output", default=None)
    parser.add_argument("--skill-root")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    result = build_index(args.project_root, args.output, skill_root=args.skill_root, force=args.force)
    print(json.dumps({"output": args.output or "spec/.i2h/cache/source-index.json", "cache_key": result["cache_key"], "cache_hit": result["cache_hit"], "summary": result["summary"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
