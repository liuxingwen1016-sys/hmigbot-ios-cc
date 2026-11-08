"""Source-backed UI obligations shared by the iOS evidence indexers."""
from __future__ import annotations

import re
from typing import Any


def declaration_slice(text: str, start: int) -> str:
    """Return one Swift declaration body without neighboring declarations."""
    opening = text.find("{", start)
    if opening < 0:
        return text[start:]
    depth = 0
    quote: str | None = None
    escaped = False
    line_comment = False
    block_comment = 0
    index = opening
    while index < len(text):
        char = text[index]
        next_char = text[index + 1] if index + 1 < len(text) else ""
        if line_comment:
            if char == "\n":
                line_comment = False
            index += 1
            continue
        if block_comment:
            if char == "\n":
                index += 1
                continue
            if char == "/" and next_char == "*":
                block_comment += 1
                index += 2
                continue
            if char == "*" and next_char == "/":
                block_comment -= 1
                index += 2
                continue
            index += 1
            continue
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            index += 1
            continue
        if char == "/" and next_char == "/":
            line_comment = True
            index += 2
            continue
        if char == "/" and next_char == "*":
            block_comment = 1
            index += 2
            continue
        if char in {"\"", "'"}:
            quote = char
            index += 1
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start:index + 1]
        index += 1
    return text[start:]


def _line(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def parse_ui_obligations(text: str, *, line_offset: int = 0) -> dict[str, Any]:
    """Extract shallow interactive and layout facts from one declaration."""
    controls: list[dict[str, Any]] = []
    patterns = (
        ("button", r"\bButton\s*\(\s*(?:[\"']([^\"']+)[\"']|role\s*:\s*[^,]+,\s*label\s*:\s*\{?\s*Text\s*\(\s*[\"']([^\"']+)[\"'])"),
        ("picker", r"\bPicker\s*\(\s*(?:[\"']([^\"']+)[\"']|selection\s*:\s*[^,]+)"),
        ("toggle", r"\bToggle\s*\(\s*(?:[\"']([^\"']+)[\"']|isOn\s*:\s*[^,]+)"),
        ("text_field", r"\b(?:TextField|SecureField)\s*\(\s*[\"']([^\"']+)[\"']"),
        ("date_picker", r"\bDatePicker\s*\(\s*[\"']([^\"']+)[\"']"),
        ("navigation_link", r"\bNavigationLink\s*\("),
    )
    for kind, pattern in patterns:
        for match in re.finditer(pattern, text):
            label = next((group for group in match.groups() if group), None)
            row: dict[str, Any] = {
                "kind": kind,
                "line": _line(text, match.start()) + line_offset,
                "_offset": match.start(),
            }
            if label:
                row["label"] = label
            controls.append(row)
    controls.sort(key=lambda item: item["_offset"])
    for row in controls:
        row.pop("_offset", None)

    identifiers = [
        {"value": match.group(1), "line": _line(text, match.start()) + line_offset}
        for match in re.finditer(r"\.accessibilityIdentifier\s*\(\s*[\"']([^\"']+)[\"']\s*\)", text)
    ]
    containers = [
        name for name in (
            "Form", "ScrollView", "List", "LazyVStack", "LazyHStack", "LazyVGrid",
            "NavigationStack", "TabView", "ZStack", "VStack", "HStack", "overlay",
        ) if re.search(r"\b" + re.escape(name) + r"\b|\." + re.escape(name) + r"\s*\(", text)
    ]
    return {
        "interactive_controls": controls,
        "accessibility_identifiers": identifiers,
        "containers": containers,
        "has_form": "Form" in containers,
        "has_scroll": any(name in containers for name in ("ScrollView", "List", "LazyVStack", "LazyHStack", "LazyVGrid")),
        "has_overlay": "overlay" in containers,
    }
