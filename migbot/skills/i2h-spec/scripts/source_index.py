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

try:
    from ui_obligations import declaration_slice, parse_ui_obligations
except ImportError:  # pragma: no cover - package/installed-tree fallback
    from .ui_obligations import declaration_slice, parse_ui_obligations  # type: ignore


TOOL_VERSION = "i2h-source-index/1.8"
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
            "start_offset": match.start(),
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


_SYMBOL_LITERAL = r'"([A-Za-z0-9][A-Za-z0-9._-]*)"'
_SYMBOL_CALL = re.compile(
    r'\b(?:Image|UIImage)\s*\(\s*systemName\s*:\s*'
    r'|\bLabel\s*\(\s*"(?P<label>(?:[^"\\]|\\.)*)"\s*,\s*systemImage\s*:\s*'
)
_SYMBOL_CONDITION = re.compile(
    r'\s*([A-Za-z_][\w.]*\s*(?:>=|<=|==|!=|>|<)\s*(?:[A-Za-z_][\w.]*|\d+))'
    r'\s*\?\s*' + _SYMBOL_LITERAL + r'\s*:\s*' + _SYMBOL_LITERAL + r'\s*\)'
)
_SYMBOL_DIRECT = re.compile(_SYMBOL_LITERAL + r'\s*(?=[,)])')
_INLINE_MODIFIER = re.compile(r'\s*\.([A-Za-z_]\w*)\s*\(')
_NUMBER = r'([0-9]+(?:\.[0-9]+)?)'
_MODIFIER_TOKEN = re.compile(r'"(?:[^"\\]|\\.)*"|[()]')


def _direct_modifiers(text: str, offset: int) -> Iterable[tuple[str, str]]:
    """Walk only modifiers attached to the same literal SwiftUI expression."""
    while match := _INLINE_MODIFIER.match(text, offset):
        depth = 1
        start = match.end()
        for token in _MODIFIER_TOKEN.finditer(text, start):
            if token[0] == '(':
                depth += 1
            elif token[0] == ')':
                depth -= 1
            if depth == 0:
                yield match[1], text[start:token.start()]
                offset = token.end()
                break
        else:
            return


def swift_system_symbol_facts(text: str) -> list[dict[str, Any]]:
    """Extract literal SF Symbols and scoped literal modifiers without guessing dynamic values."""
    hidden = re.compile(r'"(?:[^"\\]|\\.)*"|//[^\n]*|/\*.*?\*/', re.S)
    excluded = iter(hidden.finditer(text))
    current = next(excluded, None)
    result: list[dict[str, Any]] = []
    for call in _SYMBOL_CALL.finditer(text):
        while current is not None and current.end() <= call.start():
            current = next(excluded, None)
        if current is not None and current.start() <= call.start():
            continue
        literal = _SYMBOL_DIRECT.match(text, call.end())
        conditional = _SYMBOL_CONDITION.match(text, call.end()) if literal is None else None
        bound = literal or conditional
        if bound is None:
            continue
        facts: dict[str, Any] = {'kind': 'system_symbol', 'line': _line(text, call.start())}
        if (label := call["label"]) and "\\" not in label:
            is_tab = re.search(r"\.tabItem\s*\{\s*$", text[max(0, call.start() - 160):call.start()])
            facts.update(role="tab" if is_tab else "label", label=label)
        modifier_start = bound.end() + 1 if literal else bound.end()
        for name, args in _direct_modifiers(text, modifier_start):
            if name == 'font' and (size := re.match(r'\s*\.system\s*\(\s*size\s*:\s*' + _NUMBER + r'(?=\s*[,)]|\s*$)', args)):
                facts['symbol_font_pt'] = float(size[1])
            elif name == 'frame':
                frame: dict[str, float] = {}
                for field in ('width', 'height', 'minWidth', 'minHeight'):
                    if dimension := re.search(r'(?:^|,)\s*' + field + r'\s*:\s*' + _NUMBER + r'\s*(?=,|$)', args):
                        frame[field] = float(dimension[1])
                if frame:
                    facts['frame_pt'] = frame
            elif name in ('foregroundStyle', 'foregroundColor') and re.fullmatch(r'\s*\.?[A-Za-z_][\w.]*\s*', args):
                facts['foreground_expression'] = args.strip()
        if literal is not None:
            result.append({**facts, 'name': literal[1]})
        else:
            condition, enabled, other = conditional.groups()
            result.append({**facts, 'name': enabled, 'condition': condition, 'when': True})
            result.append({**facts, 'name': other, 'condition': condition, 'when': False})
    return result



_PRIMARY_BUTTON_TARGETS = {
    "arrow.right": "arrow_right",
    "play.fill": "play_fill",
    "timer": "timer",
    "pencil.line": "pencil_line",
    "checkmark": "checkmark",
}
_LABEL_SYMBOL_TARGETS = {"photo": "picture"}
_SWIFT_TRIVIA = re.compile(
    r'(?P<comment>//[^\r\n]*|/\*.*?\*/)|""".*?"""|"(?:[^"\\]|\\.)*"',
    re.DOTALL,
)
_PRIMARY_BUTTON = re.compile(r"\bstruct\s+PrimaryButton\s*:\s*View\s*\{")
_SYMBOL_DEFAULT = re.compile(r'\bvar\s+symbol\s*:\s*String\s*=\s*' + _SYMBOL_LITERAL + r"(?=[ \t]*(?:[;\r\n}]|$))")
_PRIMARY_BUTTON_CALL = re.compile(r"(?<![\w.])PrimaryButton\s*\(\s*title\s*:")
_PRIMARY_BUTTON_ARGUMENTS = re.compile(
    r'\s*"(?P<label>[^"\\\r\n]+)"\s*(?:,\s*symbol\s*:\s*'
    + _SYMBOL_LITERAL + r'\s*)?\)'
)


def _mask_swift(text: str, keep_literals: bool) -> str:
    return _SWIFT_TRIVIA.sub(
        lambda match: match[0] if keep_literals and match.lastgroup != "comment"
        else re.sub(r"[^\r\n]", " ", match[0]), text,
    )


def _share_link_facts(text: str, line_offset: int) -> list[dict[str, Any]]:
    code = _mask_swift(text, keep_literals=False)
    literals = _mask_swift(text, keep_literals=True)
    facts = []
    for call in re.finditer(r"(?<![\w.])(?:SwiftUI\.)?ShareLink\s*\(\s*(items?)\s*:", code):
        row = {"line": _line(text, call.start()) + line_offset, "payload_argument": call[1]}
        depth = 1
        for token in _MODIFIER_TOKEN.finditer(code, call.end()):
            depth += (token[0] == "(") - (token[0] == ")")
            if depth == 0:
                label = re.match(r'\s*\{\s*(?:Label|Text)\s*\(\s*"([^"\\\r\n]+)"\s*(?=[,)])',
                                 literals[token.end():])
                if label:
                    row["label"] = label[1]
                facts.append(row)
                break
    return facts


def _drawing_components(texts: dict[Path, str], root: Path) -> dict[str, dict[str, Any]]:
    """Index unambiguous top-level views with a direct Canvas or local Shape call."""
    definitions = {}
    for path, text in texts.items():
        code = _mask_swift(text, keep_literals=False)
        depth, previous = 0, 0
        for row in _declarations(code):
            start = row["start_offset"]
            prefix = code[previous:start]
            depth += prefix.count("{") - prefix.count("}")
            previous = start
            if depth == 0 and row["kind"] != "extension":
                definitions.setdefault(row["name"], []).append((path, code, row))
    unique = {name: group[0] for name, group in definitions.items() if len(group) == 1}
    shapes = {name: (path, row) for name, (path, _, row) in unique.items() if "Shape" in row["bases"]}
    if shapes:
        shape_call = re.compile(r"(?<![\w.])(" + "|".join(map(re.escape, shapes)) + r")\s*\(")
    components = {}
    for name, (path, code, row) in unique.items():
        if "View" not in row["bases"]:
            continue
        body = declaration_slice(code, row["start_offset"])
        used = sorted({match[1] for match in shape_call.finditer(body)}) if shapes else []
        # Same-file Shape resolution is deterministic for common fileprivate
        # drawing helpers. Cross-file or qualified type lookup needs review.
        used = [shape for shape in used if shapes[shape][0] == path]
        if not used and not re.search(r"\bCanvas\s*(?:\(|\{)", body):
            continue
        file = _relative(path, root)
        components[name] = {
            "component": name, "definition": {"file": file, "line": row["line"]},
            "shape_definitions": [{"name": shape, "file": file, "line": shapes[shape][1]["line"]}
                                  for shape in used],
        }
    return components


def _drawing_calls(text: str, offset: int, components: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    if not components:
        return []
    names = "|".join(map(re.escape, components))
    calls = re.compile(r"(?<![\w.])(" + names + r")\s*\(")
    code = _mask_swift(text, keep_literals=False)
    literals = _mask_swift(text, keep_literals=True)
    facts = []
    for call in calls.finditer(code):
        depth = 1
        for token in re.finditer(r"[()]", code[call.end():]):
            depth += 1 if token[0] == "(" else -1
            if depth == 0:
                end = call.end() + token.start()
                break
        else:
            continue
        info = {**components[call[1]], "line": offset + _line(text, call.start())}
        arguments = literals[call.end():end].strip()
        if len(arguments) <= 240:
            info["arguments"] = arguments
        for modifier, value in _direct_modifiers(literals, end + 1):
            if modifier != "frame":
                continue
            size = re.fullmatch(r"\s*width:\s*" + _NUMBER + r"\s*,\s*height:\s*" + _NUMBER + r"\s*", value)
            if size:
                info["frame_pt"] = {"width": float(size[1]), "height": float(size[2])}
            break
        facts.append(info)
    return facts


def _primary_button_definition(texts: dict[Path, str], root: Path) -> dict[str, Any] | None:
    definitions = []
    for path, text in texts.items():
        if "PrimaryButton" not in text:
            continue
        code = _mask_swift(text, keep_literals=False)
        for declaration in _PRIMARY_BUTTON.finditer(code):
            body = declaration_slice(code, declaration.start())
            if not re.search(r"\bImage\s*\(\s*systemName\s*:\s*symbol\s*\)", body):
                continue
            literal_body = _mask_swift(text[declaration.start():declaration.start() + len(body)], keep_literals=True)
            if default := _SYMBOL_DEFAULT.search(literal_body):
                definitions.append({
                    "file": _relative(path, root),
                    "line": _line(text, declaration.start() + default.start()),
                    "default_symbol": default[1],
                })
    return definitions[0] if len(definitions) == 1 else None


def _primary_button_facts(text: str, line_offset: int, definition: dict[str, Any]) -> list[dict[str, Any]]:
    code = _mask_swift(text, keep_literals=False)
    literals = _mask_swift(text, keep_literals=True)
    result = []
    for call in _PRIMARY_BUTTON_CALL.finditer(code):
        if args := _PRIMARY_BUTTON_ARGUMENTS.match(literals, call.end()):
            source_symbol = args[2] or definition["default_symbol"]
            target = _PRIMARY_BUTTON_TARGETS.get(source_symbol)
            result.append({
                "role": "primary_button", "line": line_offset + _line(text, call.start()),
                "label": args["label"], "source_symbol": source_symbol,
                "origin": "explicit" if args[2] else "component_default",
                "component_definition": definition,
                **({"target_symbol": target} if target else {}),
            })
    return result


def view_ui_obligations(
    text: str, line_offset: int, primary_button: dict[str, Any] | None = None,
) -> dict[str, Any]:
    obligations = parse_ui_obligations(text, line_offset=line_offset)
    facts = swift_system_symbol_facts(text)
    fidelity = []
    for fact in facts:
        source_line = fact["line"] + line_offset
        if fact.get("role") == "tab" and fact["name"] == "square.stack.3d.up":
            fidelity.append({
                "role": "tab", "line": source_line, "label": fact["label"],
                "source_symbol": fact["name"], "target_symbol": "square_stack_3d_fill",
            })
        if fact.get("role") == "label" and "condition" not in fact:
            label = {"role": "label", "line": source_line, "label": fact["label"], "source_symbol": fact["name"]}
            if target := _LABEL_SYMBOL_TARGETS.get(fact["name"]):
                label["target_symbol"] = target
            fidelity.append(label)
        if fact["name"] != "star.fill" or fact.get("when") is not True:
            continue
        alternate = any(
            row["name"] == "star" and row["line"] == fact["line"]
            and row.get("condition") == fact["condition"] and row.get("when") is False
            for row in facts
        )
        frame = fact.get("frame_pt", {})
        size = fact.get("symbol_font_pt")
        button_label = re.search(r"\bButton\s*\{[^{}]*\}\s*label:\s*\{\s*$",
                                 "\n".join(text.splitlines()[:fact["line"] - 1]))
        if (alternate and ">=" in fact["condition"] and button_label and size
                and frame.get("minWidth") and frame.get("minHeight")):
            fidelity.append({
                "role": "rating", "line": source_line, "condition": fact["condition"],
                "source_symbols": ["star.fill", "star"], "target_symbols": ["star_fill", "star"],
                "symbol_font_pt": size, "minimum_button_pt": [frame["minWidth"], frame["minHeight"]],
            })
    if primary_button and "PrimaryButton" in text:
        fidelity.extend(_primary_button_facts(text, line_offset, primary_button))
    if fidelity:
        obligations["system_symbol_fidelity"] = fidelity
    date_formats = [
        {"line": _line(text, match.start()) + line_offset,
         "value_path": re.sub(r"\s+", "", match["value"]),
         "slot": "text" if match["text"] else "subtitle",
         "date_style": match["date"], "time_style": match["time"]}
        for match in re.finditer(
            r"(?<![\w.])(?:(?P<text>Text)\s*\(\s*|SectionHeading\s*\(\s*title\s*:\s*,\s*subtitle\s*:\s*)"
            r"(?P<value>[A-Za-z_]\w*(?:\s*\.\s*\w+)*)\s*\.\s*formatted\s*\(\s*"
            r"date\s*:\s*\.(?P<date>omitted|numeric|abbreviated|long|complete)\s*,\s*"
            r"time\s*:\s*\.(?P<time>omitted|shortened|standard|complete)\s*\)\s*(?=[,)])",
            _mask_swift(text, keep_literals=False),
        )
    ]
    if date_formats:
        obligations["date_format_calls"] = date_formats
    if share_links := _share_link_facts(text, line_offset):
        obligations["share_link_calls"] = share_links
    return obligations

def _resources(text: str) -> list[dict[str, Any]]:
    patterns = {
        "image": r"\bImage\s*\(\s*\"([^\"]+)\"|\bUIImage\s*\(named:\s*\"([^\"]+)\"",
        "color": r"\bColor\s*\(\s*\"([^\"]+)\"",
        "localization": r"\bNSLocalizedString\s*\(\s*\"([^\"]+)\"",
    }
    result: list[dict[str, Any]] = []
    for kind, pattern in patterns.items():
        for match in re.finditer(pattern, text):
            name = next((group for group in match.groups() if group), None)
            if name:
                result.append({"kind": kind, "name": name, "line": _line(text, match.start())})
    result.extend(swift_system_symbol_facts(text))
    return result


def classify_view_surface(name: str, bases: Iterable[str], relative_path: str, text: str) -> str:
    """Separate navigable screens from reusable SwiftUI view components."""
    base_text = " ".join(bases)
    if any(token in base_text for token in ("UIViewRepresentable", "NSViewRepresentable", "ViewModifier")):
        return "shared_component"
    if name.endswith(("Row", "Cell", "Card", "Button", "Pill", "Badge", "Header", "Footer")):
        return "shared_component"
    path_parts = {part.lower() for part in Path(relative_path).parts}
    screen_path = bool(path_parts & {"views", "screens", "pages", "viewcontrollers"})
    component_path = bool(path_parts & {"components", "design", "services", "widgets"})
    if name == "RootView":
        return "screen"
    if name.endswith("ViewController"):
        return "screen"
    if "UIViewController" in base_text:
        return "shared_component"
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

    primary_button = _primary_button_definition(texts, root)
    drawing_components = _drawing_components(texts, root)

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
                declaration_text = declaration_slice(text, int(declaration["start_offset"]))
                view = {
                    "page_id": f"page_{len(pages) + 1:04d}_{declaration['name']}",
                    "view_name": declaration["name"],
                    "file_path": rel,
                    "declaration_line": declaration["line"],
                    "dependencies": dependencies,
                    "surface": surface,
                    "ui_obligations": view_ui_obligations(
                        declaration_text,
                        line_offset=int(declaration["line"]) - 1,
                        primary_button=primary_button,
                    ),
                }
                calls = _drawing_calls(declaration_text, int(declaration["line"]) - 1, drawing_components)
                if calls:
                    view["ui_obligations"]["drawing_component_calls"] = calls
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
