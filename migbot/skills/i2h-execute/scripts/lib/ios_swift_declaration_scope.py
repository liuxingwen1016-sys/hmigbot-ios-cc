"""Bounded, source-position preserving Swift declaration facts (not a compiler).

Only lexical ownership and conservative initializer types are claimed.  Unknown
syntax/types retain diagnostics instead of falling back to a whole Swift file.

Ported from dirty reference: /Users/liuxingwen/Codes/ios2harmony/hmigbot-ios
Dirty source hash: 3a74cf083298bcb08e882fbac8ae5663aec57fe8c36e37aa0dbd066a80a27b3c
Adaptations: Removed unrelated capture/localization logic, focused on declaration scoping
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Iterable

IDENT = r"(?:`[^`\n]+`|[^\W\d]\w*)"
WRAPPERS = "StateObject|ObservedObject|EnvironmentObject|Environment|Binding|State|AppStorage|SceneStorage|FocusState|Published|Bindable"
TYPE_DECL = re.compile(rf"\b(?P<kind>struct|class|enum|protocol|actor|extension)\s+(?P<name>{IDENT}(?:\s*\.\s*{IDENT})*)")
NON_NAMES = {"func", "var", "let", "subscript", "init", "deinit", "case"}
DEFAULT_TYPES = {"Date", "UUID", "NavigationPath", "CGFloat", "CGPoint", "CGSize", "CGRect", "CLLocationCoordinate2D", "MKCoordinateRegion", "Bool", "Int", "Double", "Float", "String", "Array", "Dictionary", "Set"}


def line_at(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _blank(value: str) -> str:
    return re.sub(r"[^\n]", " ", value)


@dataclass
class SwiftLex:
    text: str
    code: str
    uncommented: str
    pairs: dict[int, int]
    literals: dict[int, int]
    diagnostics: list[dict[str, Any]]


def lex_swift(text: str) -> SwiftLex:
    """Mask trivia/literals, including nested comments and string interpolation."""
    code = list(text)
    uncommented = list(text)
    diagnostics: list[dict[str, Any]] = []
    literals: dict[int, int] = {}

    def problem(code_name: str, at: int, message: str) -> None:
        diagnostics.append({"code": code_name, "line": line_at(text, at), "offset": at, "message": message})

    def block_end(start: int) -> int:
        depth, pos = 1, start + 2
        while pos < len(text):
            if text.startswith("/*", pos): depth, pos = depth + 1, pos + 2
            elif text.startswith("*/", pos):
                depth, pos = depth - 1, pos + 2
                if not depth: return pos
            else: pos += 1
        problem("unterminated-comment", start, "Swift block comment is not closed; remaining text is not code")
        return len(text)

    def string_open(pos: int) -> tuple[int, int] | None:
        cursor = pos
        while cursor < len(text) and text[cursor] == "#": cursor += 1
        if cursor < len(text) and text[cursor] == '"':
            return cursor - pos, 3 if text.startswith('"""', cursor) else 1
        return None

    def interpolation_end(pos: int) -> int:
        depth = 1
        while pos < len(text):
            if text.startswith("//", pos):
                end = text.find("\n", pos); pos = len(text) if end < 0 else end
            elif text.startswith("/*", pos): pos = block_end(pos)
            elif (opening := string_open(pos)) is not None: pos = string_end(pos, *opening)
            elif text[pos] == "(": depth, pos = depth + 1, pos + 1
            elif text[pos] == ")":
                depth, pos = depth - 1, pos + 1
                if not depth: return pos
            else: pos += 1
        return len(text)

    def string_end(start: int, hashes: int, width: int) -> int:
        closing = '"' * width + "#" * hashes
        escape = "\\" + "#" * hashes
        pos = start + hashes + width
        while pos < len(text):
            if text.startswith(escape + "(", pos):
                pos = interpolation_end(pos + len(escape) + 1)
            elif text.startswith(escape, pos): pos += len(escape) + 1
            elif text.startswith(closing, pos): return pos + len(closing)
            elif width == 1 and text[pos] == "\n":
                problem("unterminated-string", start, "Single-line Swift literal is not closed")
                return len(text)
            else: pos += 1
        problem("unterminated-string", start, "Swift string/interpolation is not closed; remaining text is not code")
        return len(text)

    pos = 0
    while pos < len(text):
        is_comment = False
        if text.startswith("//", pos):
            end = text.find("\n", pos); end = len(text) if end < 0 else end
            is_comment = True
        elif text.startswith("/*", pos): end, is_comment = block_end(pos), True
        elif (opening := string_open(pos)) is not None:
            end = string_end(pos, *opening); literals[pos] = end
        else:
            # Raw Swift regex literals can contain braces.  Do not interpret
            # their contents as Swift declarations; regex semantics are unknown.
            regex = re.match(r"#+/", text[pos:]) if text[pos] == "#" else None
            prefix = text[:pos].rstrip() if text[pos] == "/" else ""
            bare_regex = text[pos] == "/" and (not prefix or prefix[-1] in "=([{,:!&|?;" or re.search(r"\breturn$", prefix))
            if regex or bare_regex:
                hashes = regex.group(0).count("#") if regex else 0
                closing = "/" + "#" * hashes
                cursor, in_class, finish = pos + hashes + 1, False, -1
                while cursor < len(text):
                    if text[cursor] == "\\": cursor += 2; continue
                    if text[cursor] == "[": in_class = True
                    elif text[cursor] == "]": in_class = False
                    elif not in_class and text.startswith(closing, cursor): finish = cursor; break
                    elif not hashes and text[cursor] == "\n": break
                    cursor += 1
                end = len(text) if finish < 0 else finish + len(closing)
                problem("regex-literal-not-analyzed", pos, "Regex literal masked; regex semantics are outside static declaration facts")
                literals[pos] = end
            else:
                pos += 1; continue
        code[pos:end] = _blank(text[pos:end])
        if is_comment: uncommented[pos:end] = _blank(text[pos:end])
        pos = end
    masked = "".join(code)
    pairs: dict[int, int] = {}
    stack: list[tuple[str, int]] = []
    closing_map = {"}": "{", ")": "(", "]": "["}
    for offset, char in enumerate(masked):
        if char in "{([": stack.append((char, offset))
        elif char in "})]":
            if stack and stack[-1][0] == closing_map[char]:
                _, opening = stack.pop(); pairs[opening] = offset
            else: problem("unmatched-delimiter", offset, f"Unmatched Swift delimiter {char}")
    for char, offset in stack: problem("unclosed-delimiter", offset, f"Swift delimiter {char} is not closed")
    return SwiftLex(text, masked, "".join(uncommented), pairs, literals, diagnostics)


def balanced_slice(text: str, start: int) -> str:
    """One balanced block for declarations *or* builder calls; no tail fallback."""
    lex = lex_swift(text)
    opening = lex.code.find("{", start)
    end = lex.pairs.get(opening)
    return text[start:end + 1] if end is not None else ""


def _split_top(value: str, separator: str = ",") -> list[str]:
    code = lex_swift(value).code
    depth, start, rows = 0, 0, []
    for pos, char in enumerate(code):
        if char in "([<{": depth += 1
        elif char in ")]>}": depth -= 1
        elif char == separator and not depth:
            rows.append(value[start:pos].strip()); start = pos + 1
    rows.append(value[start:].strip())
    return rows


def _bases(header: str, name_end: int) -> list[str]:
    tail = header[name_end:].strip()
    if tail.startswith("<"):
        depth = 0
        for pos, char in enumerate(tail):
            if char == "<": depth += 1
            elif char == ">":
                depth -= 1
                if not depth: tail = tail[pos + 1:].strip(); break
    if not tail.startswith(":"): return []
    return _split_top(re.split(r"\bwhere\b", tail[1:], maxsplit=1)[0])


def view_kind(bases: Iterable[str]) -> str | None:
    leaves = [re.split(r"[<\s]", base.strip())[0].rsplit(".", 1)[-1] for base in bases]
    if any(base in {"View", "ViewModifier", "UIViewRepresentable", "UIViewControllerRepresentable", "NSViewRepresentable", "NSViewControllerRepresentable"} for base in leaves): return "SwiftUI View"
    if any(base.endswith("ViewController") for base in leaves): return "UIKit ViewController"
    if any(base in {"UIView", "UIStackView", "UICollectionView", "UITableView"} for base in leaves): return "UIKit View"
    return None


class SwiftSource:
    """Declaration ranges and owned member code within one Swift source file."""
    def __init__(self, text: str):
        self.text, self.lex = text, lex_swift(text)
        self._constructor_candidates: dict[str, list[bool]] | None = None
        self.diagnostics = list(self.lex.diagnostics)
        self.declarations: list[dict[str, Any]] = []
        for match in TYPE_DECL.finditer(self.lex.code):
            if match.group("name") in NON_NAMES: continue
            cursor = match.end()
            while cursor < len(text) and self.lex.code[cursor] not in "{};":
                if self.lex.code[cursor] in "([" and cursor in self.lex.pairs: cursor = self.lex.pairs[cursor] + 1
                else: cursor += 1
            opening = cursor if cursor < len(text) and self.lex.code[cursor] == "{" else None
            closing = self.lex.pairs.get(opening) if opening is not None else None
            header = self.lex.code[match.start():opening if opening is not None else cursor]
            name = re.sub(r"\s+|`", "", match.group("name"))
            row = {"kind": match.group("kind"), "name": name.rsplit(".", 1)[-1], "qualified_name": name,
                   "bases": _bases(header, match.end() - match.start()), "line": line_at(text, match.start()),
                   "start_offset": match.start(), "opening_offset": opening, "end_offset": closing + 1 if closing is not None else None,
                   "end_line": line_at(text, closing) if closing is not None else None, "diagnostics": []}
            if closing is None:
                row["diagnostics"].append({"code": "incomplete-declaration", "line": row["line"], "message": "No balanced declaration body; no member facts inferred"})
            self.declarations.append(row)
        for row in self.declarations:
            parents = [p for p in self.declarations if p["end_offset"] is not None and p["start_offset"] < row["start_offset"] < p["end_offset"]]
            if parents:
                parent = max(parents, key=lambda p: p["start_offset"])
                row["qualified_name"] = parent["qualified_name"] + "." + row["qualified_name"]
            row["identity"] = f"{row['qualified_name']}@{row['start_offset']}"
        self.extensions: dict[int, list[dict[str, Any]]] = {}
        for ext in [d for d in self.declarations if d["kind"] == "extension"]:
            owners = [d for d in self.declarations if d["kind"] != "extension" and d["qualified_name"] == ext["qualified_name"]]
            if len(owners) == 1 and ext["end_offset"] is not None:
                self.extensions.setdefault(owners[0]["start_offset"], []).append(ext)
            else:
                diag = {"code": "unbound-extension", "line": ext["line"], "qualified_name": ext["qualified_name"], "message": "Extension owner is external or ambiguous; facts are not merged by leaf name"}
                ext["diagnostics"].append(diag); self.diagnostics.append(diag)
        leaf_counts: dict[str, int] = {}
        for row in self.declarations:
            if row["kind"] != "extension": leaf_counts[row["name"]] = leaf_counts.get(row["name"], 0) + 1
        for row in self.declarations:
            if row["kind"] != "extension" and leaf_counts[row["name"]] > 1:
                diag = {"code": "ambiguous-leaf-name", "line": row["line"], "qualified_name": row["qualified_name"], "message": "Use qualified_name and declaration offset; legacy leaf-name page identity is ambiguous"}
                row["diagnostics"].append(diag); self.diagnostics.append(diag)
        if re.search(r"^\s*#(?:if|elseif|else|endif)\b", self.lex.code, re.MULTILINE):
            self.diagnostics.append({"code": "conditional-compilation-unresolved", "line": 1, "message": "All lexical branches indexed; active build conditions are not evaluated"})

    def regions(self, declaration: dict[str, Any]) -> list[dict[str, Any]]:
        return [d for d in [declaration, *self.extensions.get(declaration["start_offset"], [])] if d["end_offset"] is not None]

    def bases_for(self, declaration: dict[str, Any]) -> list[str]:
        return list(dict.fromkeys(base for region in [declaration, *self.extensions.get(declaration["start_offset"], [])] for base in region["bases"]))

    def scope_diagnostics(self, declaration: dict[str, Any]) -> list[dict[str, Any]]:
        regions = self.regions(declaration)
        return [*declaration["diagnostics"], *[
            diagnostic for diagnostic in self.lex.diagnostics
            if any(region["start_offset"] <= diagnostic.get("offset", -1) < region["end_offset"] for region in regions)
        ], *[d for d in self.diagnostics if d["code"] == "conditional-compilation-unresolved"]]

    def owned_text(self, declaration: dict[str, Any], *, code: bool = False) -> str:
        original = self.lex.code if code else self.lex.uncommented
        output = list(_blank(original))
        for region in self.regions(declaration):
            start, end = region["start_offset"], region["end_offset"]
            output[start:end] = original[start:end]
            for child in self.declarations:
                if start < child["start_offset"] < end:
                    stop = child["end_offset"] or end
                    output[child["start_offset"]:stop] = _blank(original[child["start_offset"]:stop])
        return "".join(output)

    def body_line(self, declaration: dict[str, Any]) -> int | None:
        code = self.owned_text(declaration, code=True)
        for match in re.finditer(r"\bvar\s+body\s*:\s*(?:some\s+)?(?:SwiftUI\.)?View\s*\{", code):
            if self.is_direct_member(match.start(), declaration): return line_at(self.text, match.start())
        return None

    def is_direct_member(self, offset: int, declaration: dict[str, Any]) -> bool:
        for region in self.regions(declaration):
            opening, end = region["opening_offset"], region["end_offset"]
            if opening < offset < end:
                prefix = self.lex.code[opening:offset]
                return prefix.count("{") - prefix.count("}") == 1
        return False

    def properties(self, declaration: dict[str, Any] | None = None, *, known_types: Iterable[str] | None = None) -> list[dict[str, Any]]:
        if declaration is None:
            return [row for d in self.declarations if d["kind"] != "extension" for row in self.properties(d, known_types=known_types)]
        code = self.owned_text(declaration, code=True)
        rows = []
        known = set(known_types) if known_types is not None else known_constructor_types([self])
        for match in re.finditer(rf"@(?P<wrapper>{WRAPPERS})\b", code):
            if not self.is_direct_member(match.start(), declaration): continue
            cursor = match.end()
            while cursor < len(code) and code[cursor].isspace(): cursor += 1
            if cursor < len(code) and code[cursor] == "<":
                level = 0
                while cursor < len(code):
                    if code[cursor] == "<": level += 1
                    elif code[cursor] == ">": level -= 1
                    cursor += 1
                    if not level: break
                while cursor < len(code) and code[cursor].isspace(): cursor += 1
            if cursor < len(code) and code[cursor] == "(": cursor = self.lex.pairs.get(cursor, len(code)) + 1
            tail = re.match(rf"\s*(?:(?:@[A-Za-z_]\w*|private|fileprivate|internal|public|open|final|static|class|lazy|weak|unowned|nonisolated|isolated)\s*(?:\([^\n)]*\))?\s*)*var\s+(?P<name>{IDENT})", code[cursor:])
            if not tail:
                rows.append({"name": None, "wrapper": "@" + match.group("wrapper"), "type": "unknown", "line": line_at(self.text, match.start()), "owner": declaration["qualified_name"], "type_source": "unknown", "diagnostic": "unsupported-wrapper-property-syntax"})
                continue
            name = tail.group("name").strip("`"); start = cursor + tail.end()
            end = self._property_end(start)
            raw = self.lex.uncommented[start:end].strip()
            masked = self.lex.code[start:end]
            equals = self._top_equals(masked)
            annotation = self.lex.uncommented[start:start + equals].strip() if equals is not None else raw
            explicit = annotation[1:].strip() if annotation.startswith(":") else None
            value = self.lex.uncommented[start + equals + 1:end].strip() if equals is not None else None
            inferred = infer_type(value, known) if not explicit else None
            row = {"name": name, "wrapper": "@" + match.group("wrapper"), "type": explicit or inferred or "unknown", "line": line_at(self.text, match.start()), "owner": declaration["qualified_name"], "type_source": "annotation" if explicit else "initializer" if inferred else "unknown"}
            if value: row["default_value"] = value
            if not explicit and not inferred: row["diagnostic"] = "initializer-type-not-statically-known" if value else "no-explicit-type-or-initializer"
            rows.append(row)
        return rows

    def _property_end(self, start: int) -> int:
        pos, nesting = start, []
        while pos < len(self.text):
            if pos in self.lex.literals: pos = self.lex.literals[pos]; continue
            char = self.lex.code[pos]
            if char in "([": nesting.append(char)
            elif char in ")]" and nesting: nesting.pop()
            elif char == "{" and not nesting:
                if "=" not in self.lex.code[start:pos] or re.match(r"\s*(?:didSet|willSet)\b", self.lex.code[pos + 1:]): return pos
                finish = self.lex.pairs.get(pos)
                if finish is None: return pos
                pos = finish + 1; continue
            elif char == "}" and not nesting: return pos
            elif char == ";" and not nesting: return pos
            elif char == "\n" and not nesting:
                before = self.lex.uncommented[start:pos].rstrip()
                after = self.lex.code[pos + 1:].lstrip()
                if not before.endswith(("=", ":", ",")) and not after.startswith("."): return pos
            pos += 1
        return pos

    @staticmethod
    def _top_equals(value: str) -> int | None:
        depth = 0
        for pos, char in enumerate(value):
            if char in "([<": depth += 1
            elif char in ")]>": depth -= 1
            elif char == "=" and not depth: return pos
        return None


def known_constructor_types(sources: Iterable[SwiftSource]) -> set[str]:
    """Only unambiguous project nominal types without failable initializers."""
    candidates: dict[str, list[bool]] = {}
    for source in sources:
        if source._constructor_candidates is None:
            source._constructor_candidates = {}
            for declaration in source.declarations:
                if declaration["kind"] in {"struct", "class", "enum", "actor"}:
                    safe = declaration["end_offset"] is not None and not re.search(r"\binit\s*[?!]", source.owned_text(declaration, code=True))
                    source._constructor_candidates.setdefault(declaration["qualified_name"], []).append(safe)
        for name, definitions in source._constructor_candidates.items():
            candidates.setdefault(name, []).extend(definitions)
    return {name for name, definitions in candidates.items() if definitions == [True]}


def infer_type(value: str | None, known_types: Iterable[str] = ()) -> str | None:
    """Infer only basic literal/known-constructor types, never arbitrary factories."""
    if not value: return None
    value = value.strip()
    if value in {"true", "false"}: return "Bool"
    if re.fullmatch(r"[+-]?(?:0[xX][0-9a-fA-F_]+|0[bB][01_]+|0[oO][0-7_]+|\d[\d_]*)", value): return "Int"
    if re.fullmatch(r"[+-]?(?:\d[\d_]*\.\d[\d_]*(?:[eE][+-]?\d+)?|\d[\d_]*[eE][+-]?\d+)", value): return "Double"
    lex = lex_swift(value)
    if lex.literals.get(0) == len(value) and re.match(r'\#*"', value) and not lex.diagnostics: return "String"
    if value.startswith("[") and lex.pairs.get(0) == len(value) - 1:
        entries = _split_top(value[1:-1])
        if not entries or not all(entries): return None
        pairs = [_split_top(entry, ":") for entry in entries]
        if all(len(pair) == 2 for pair in pairs):
            keys = {infer_type(pair[0], known_types) for pair in pairs}; vals = {infer_type(pair[1], known_types) for pair in pairs}
            if len(keys) == len(vals) == 1 and None not in keys | vals: return f"[{next(iter(keys))}: {next(iter(vals))}]"
        elif all(len(pair) == 1 for pair in pairs):
            types = {infer_type(entry, known_types) for entry in entries}
            if len(types) == 1 and None not in types: return f"[{next(iter(types))}]"
        return None
    constructor = re.match(r"(?P<type>[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*(?:<[^{}\n]+>)?)\s*\(", lex.code)
    if constructor:
        opening = lex.code.find("(", constructor.start())
        if lex.pairs.get(opening) != len(value) - 1: return None
        name = constructor.group("type").strip(); base = name.split("<", 1)[0]
        empty = not lex.uncommented[opening + 1:-1].strip()
        if base in set(known_types) or (empty and base in DEFAULT_TYPES):
            if base in {"Array", "Set", "Dictionary"} and "<" not in name: return None
            return name
    return None
