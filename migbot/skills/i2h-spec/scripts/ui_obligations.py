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
        ("navigation_link", r"\bNavigationLink\s*(?:\(|\{)"),
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
    primary_ids = [
        item["value"] for item in identifiers
        if re.search(r"(?:prepare|start|save|finish|confirm|manual|taste|resume)", item["value"], re.IGNORECASE)
    ]
    form_pickers = [
        item.get("label") for item in controls
        if item.get("kind") == "picker" and item.get("label")
    ]
    has_scroll = any(name in containers for name in ("ScrollView", "List", "LazyVStack", "LazyHStack", "LazyVGrid"))
    grid = None
    grid_match = re.search(r"\b(LazyVGrid|LazyHGrid)\s*\(", text)
    if grid_match:
        grid_kind = "lazy_v_grid" if grid_match.group(1) == "LazyVGrid" else "lazy_h_grid"
        spacing_match = re.search(r"\bspacing\s*:\s*([0-9.]+)", text[grid_match.start():])
        adaptive_match = re.search(r"\.adaptive\s*\(\s*minimum\s*:\s*([0-9.]+)", text[grid_match.start():])
        fixed_count = len(re.findall(r"\bGridItem\s*\(", text[grid_match.start():]))
        grid = {
            "kind": grid_kind,
            "line": _line(text, grid_match.start()) + line_offset,
            "spacing": float(spacing_match.group(1)) if spacing_match else None,
            "adaptive_minimum": float(adaptive_match.group(1)) if adaptive_match else None,
            "fixed_item_count": fixed_count,
        }
    chart = None
    if re.search(r"\bChart\s*\(", text):
        y_domain = re.search(r"chartYScale\s*\(\s*domain\s*:\s*([^\)]+)", text)
        chart_height = re.search(r"chart[^\n]*?\.frame\s*\(\s*height\s*:\s*([0-9.]+)", text)
        chart = {
            "y_domain": y_domain.group(1).strip() if y_domain else None,
            "x_axis_hidden": bool(re.search(r"chartXAxis\s*\(\s*\.hidden", text)),
            "height": float(chart_height.group(1)) if chart_height else None,
        }
    searchable = bool(re.search(r"\.searchable\s*\(", text))
    presentation_patterns = (
        ("sheet", r"\.(sheet|fullScreenCover)\s*\("),
        ("alert", r"\.alert\s*\("),
        ("confirmation_dialog", r"\.confirmationDialog\s*\("),
        ("popover", r"\.popover\s*\("),
        ("context_menu", r"\.contextMenu\s*\("),
    )
    presentations = []
    for kind, pattern in presentation_patterns:
        for match in re.finditer(pattern, text):
            presentations.append({
                "kind": kind,
                "line": _line(text, match.start()) + line_offset,
                "source_pattern": match.group(0).split("(", 1)[0],
            })
    presentations.sort(key=lambda item: item["line"])

    conditional_patterns = (
        ("if", r"\bif\s+[^\n{]+\{"),
        ("else", r"\belse\s*(?:if\s+[^\n{]+)?\{"),
        ("switch", r"\bswitch\s+[^\n{]+\{"),
        ("case", r"\bcase\s+[^:\n]+:"),
    )
    conditional_states = []
    for kind, pattern in conditional_patterns:
        for match in re.finditer(pattern, text):
            conditional_states.append({
                "kind": kind,
                "line": _line(text, match.start()) + line_offset,
                "expression": re.sub(r"\s+", " ", match.group(0).strip()),
            })
    conditional_states.sort(key=lambda item: item["line"])

    state_markers = []
    state_patterns = (
        ("loading", r"\b(?:isLoading|loading|ProgressView)\b"),
        ("empty", r"\b(?:isEmpty|EmptyView|ContentUnavailableView|emptyState)\b"),
        ("error", r"\b(?:error|ErrorView|failure|failed)\b"),
    )
    for kind, pattern in state_patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            state_markers.append({"kind": kind, "line": _line(text, match.start()) + line_offset})
    state_markers.sort(key=lambda item: item["line"])

    # Custom view calls are candidates only.  They are deliberately not
    # treated as proven page ownership because SwiftUI builders can hide
    # content behind helpers and modifiers.
    builtin = {
        "VStack", "HStack", "ZStack", "List", "ScrollView", "LazyVStack", "LazyHStack",
        "LazyVGrid", "NavigationStack", "NavigationView", "NavigationLink", "TabView", "Form",
        "Group", "Button", "TextField", "SecureField", "Picker", "Toggle", "DatePicker", "Image",
        "Sheet", "Alert", "UICollectionView", "UITableView", "UIScrollView", "UIButton", "UILabel",
        "UIImageView", "UITextField", "UIStackView",
    } | {
        "Text", "Color", "Spacer", "Divider", "ForEach", "Group", "AnyView",
        "GeometryReader", "Section", "Label", "Link", "Menu", "ProgressView",
    }
    embedded_candidates = []
    for match in re.finditer(r"\b([A-Z][A-Za-z0-9_]*)\s*\(", text):
        name = match.group(1)
        if name in builtin:
            continue
        embedded_candidates.append({"name": name, "line": _line(text, match.start()) + line_offset})
    seen_embedded = set()
    embedded_views = []
    for item in embedded_candidates:
        key = (item["name"], item["line"])
        if key not in seen_embedded:
            seen_embedded.add(key)
            embedded_views.append(item)

    bottom_anchor_patterns = (
        r"\.safeAreaInset\s*\(\s*edge\s*:\s*\.bottom",
        r"\.overlay\s*\(\s*alignment\s*:\s*\.bottom",
        r"\.frame\s*\([^\n]*alignment\s*:\s*\.bottom",
    )
    fixed_bottom_action_required = bool(
        primary_ids
        and any(re.search(pattern, text) for pattern in bottom_anchor_patterns)
    )

    return {
        "interactive_controls": controls,
        "accessibility_identifiers": identifiers,
        "containers": containers,
        "has_form": "Form" in containers,
        "has_scroll": has_scroll,
        "has_overlay": "overlay" in containers,
        "primary_action_ids": primary_ids,
        "fixed_bottom_action_required": fixed_bottom_action_required,
        "form_picker_labels": form_pickers,
        "compact_picker_rows_required": bool("Form" in containers and form_pickers),
        "searchable": searchable,
        "searchable_placement": "toolbar" if searchable else None,
        "chart": chart,
        "grid": grid,
        "presentations": presentations,
        "conditional_states": conditional_states,
        "state_markers": state_markers,
        "embedded_view_candidates": embedded_views,
    }
