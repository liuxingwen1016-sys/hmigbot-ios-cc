"""Resolve a label to its visible HarmonyOS UITest action."""
from __future__ import annotations

import re


def require_focused_app(tree: dict, bundle: str) -> None:
    """Require a focused app root before treating a dump as product evidence."""
    focused = {
        attrs["bundleName"]
        for node in tree.get("children", [])
        if (attrs := node.get("attributes", {})).get("focused") == "true"
        and isinstance(attrs.get("bundleName"), str) and attrs["bundleName"]
    }
    # The app may expose an unfocused root below a system-owned modal.
    # Require a focused root that also identifies an actual ability surface.
    surface = any(
        (attrs := node.get("attributes", {})).get("bundleName") == bundle
        and attrs.get("focused") == "true" and attrs.get("pagePath")
        for node in tree.get("children", [])
    )
    if focused != {bundle} or not surface:
        raise ValueError(f"expected foreground {bundle!r}, observed {sorted(focused)!r}")


def _bounds(node):
    match = re.fullmatch(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]", node.get("bounds", ""))
    if match:
        x, y, right, bottom = map(int, match.groups())
        if right > x and bottom > y:
            return x, y, right, bottom
    return None


def label_action_center(tree: dict, label: str) -> tuple[int, int]:
    """Use a labeled action or its enclosing clickable control in the same window."""
    candidates = {}

    def visit(node, ancestors):
        attrs = node.get("attributes", {})
        visible = attrs.get("visible") == "true" and attrs.get("enabled") == "true"
        label_bounds = _bounds(attrs) if visible and attrs.get("text") == label else None
        if label_bounds is not None:
            x, y, right, bottom = label_bounds
            for action in (attrs, *reversed(ancestors)):
                if action.get("hostWindowId") != attrs.get("hostWindowId"):
                    break
                if action.get("enabled") == "false":
                    break
                if action.get("visible") != "true" or action.get("clickable") != "true":
                    continue
                if action is not attrs and action.get("type") != "Button":
                    continue
                bounds = _bounds(action)
                if bounds is None:
                    continue
                left, top, edge, end = bounds
                if left <= x and top <= y and edge >= right and end >= bottom:
                    candidates[id(action)] = ((left + edge) // 2, (top + end) // 2)
                    break
        for child in node.get("children", []):
            visit(child, (*ancestors, attrs))

    visit(tree, ())
    if len(candidates) != 1:
        raise ValueError(f"expected one visible action for {label!r}, found {len(candidates)}")
    return next(iter(candidates.values()))


def selected_tab_label(tree: dict, labels: set[str]) -> str:
    """Read a selected native TabBar item with a visible, uniquely identified label."""
    selected = []

    def visit(node, in_tab_bar=False, in_selected=False):
        attrs = node.get("attributes", {})
        in_tab_bar = in_tab_bar or attrs.get("type") == "TabBar"
        in_selected = in_selected or (in_tab_bar and attrs.get("type") != "TabBar"
                                      and attrs.get("visible") == "true" and attrs.get("selected") == "true")
        label = attrs.get("text")
        if in_selected and attrs.get("visible") == "true" and label in labels:
            selected.append(label)
        for child in node.get("children", []):
            visit(child, in_tab_bar, in_selected)

    visit(tree)
    if len(selected) != 1:
        raise ValueError(f"expected one selected TabBar label, found {selected!r}")
    return selected[0]
