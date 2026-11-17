"""Resolve a label to its visible HarmonyOS UITest action."""
from __future__ import annotations

import re


class ForegroundError(ValueError):
    def __init__(self, bundle: str, windows: list[dict]):
        self.windows = windows
        focused = sorted({window['bundle'] for window in windows if window['bundle']})
        super().__init__(f"expected foreground {bundle!r}, observed {focused!r}")


def require_focused_app(tree: dict, bundle: str) -> None:
    """Require a focused app root before treating a dump as product evidence."""
    windows = [
        {'bundle': attrs.get('bundleName', ''), 'page': attrs.get('pagePath', '')}
        for node in tree.get("children", [])
        if (attrs := node.get("attributes", {})).get("focused") == "true"
        and isinstance(attrs.get("bundleName", ''), str)
    ]
    focused = {window['bundle'] for window in windows if window['bundle']}
    # The app may expose an unfocused root below a system-owned modal.
    # Require a focused root that also identifies an actual ability surface.
    surface = any(window['bundle'] == bundle and window['page'] for window in windows)
    if focused != {bundle} or not surface:
        raise ForegroundError(bundle, windows)


def _bounds(node, key="bounds"):
    match = re.fullmatch(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]", node.get(key) or "")
    if match:
        x, y, right, bottom = map(int, match.groups())
        if right > x and bottom > y:
            return x, y, right, bottom
    return None


def visible_tab_bar_bounds(tree: dict) -> list[tuple[int, int, int, int]]:
    """Read the native bar viewport even when individual tabs omit their IDs."""
    attrs = tree.get('attributes', {})
    if attrs.get('visible') == 'false':
        return []
    bounds = _bounds(attrs) if attrs.get('type') == 'TabBar' and attrs.get('visible') == 'true' else None
    if bounds is not None:
        return [bounds]
    return [bounds for child in tree.get('children', []) for bounds in visible_tab_bar_bounds(child)]


def overlaps_obstruction(node: dict, obstructions: list[tuple[int, int, int, int]]) -> bool:
    """Require the entire reported control frame to clear a native overlay."""
    frame = _bounds(node)
    if frame is None:
        return False
    left, top, right, bottom = frame
    return any(left < r and l < right and top < b and t < bottom for l, t, r, b in obstructions)


def fully_visible_control(node: dict, obstructions: list[tuple[int, int, int, int]]) -> bool:
    """Reject clipped controls when UITest provides the original frame."""
    frame = _bounds(node)
    if node.get('visible') != 'true' or node.get('enabled') == 'false' or frame is None:
        return False
    original = _bounds(node, 'origBounds')
    return (original is None or original == frame) and not overlaps_obstruction(node, obstructions)


def control_fits_viewport(node: dict, viewport: dict, obstructions: list[dict]) -> bool:
    """Prove that the original frame fits the captured viewport and clears known overlays."""
    screen = _bounds(viewport)
    frame = _bounds(node, 'origBounds')
    overlays = [_bounds(overlay) for overlay in obstructions]
    if screen is None or frame is None or any(box is None for box in overlays):
        return False
    left, top, right, bottom = frame
    return (screen[0] <= left and screen[1] <= top and right <= screen[2] and bottom <= screen[3]
            and fully_visible_control(node, overlays))


def _visible_containers(node: dict, container_id: str):
    attrs = node.get("attributes", {})
    if attrs.get("visible") == "false" or attrs.get("enabled") == "false":
        return
    if attrs.get("id") == container_id and attrs.get("visible") == "true":
        yield node
    for child in node.get("children", []):
        yield from _visible_containers(child, container_id)


def label_action_center(tree: dict, label: str, *, container_id: str | None = None) -> tuple[int, int]:
    """Use a labeled action or its enclosing clickable control in the same window."""
    candidates = {}
    parent_types = ('Button', 'Row') if container_id is not None else ('Button',)

    def visit(node, ancestors):
        attrs = node.get("attributes", {})
        if container_id is not None and (attrs.get("visible") == "false" or attrs.get("enabled") == "false"):
            return
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
                if action is not attrs and action.get("type") not in parent_types:
                    continue
                if container_id is not None and not fully_visible_control(action, []):
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

    if container_id is not None:
        matches = list(_visible_containers(tree, container_id))
        if len(matches) != 1:
            raise ValueError(f"expected one visible action container {container_id!r}, found {len(matches)}")
        tree = matches[0]
    visit(tree, ())
    if len(candidates) != 1:
        raise ValueError(f"expected one visible action for {label!r}, found {len(candidates)}")
    return next(iter(candidates.values()))


def grouped_row_action_center(
    tree: dict, labels: tuple[str, ...], *, bundle: str, container_id: str | None = None,
    obstruction_ids: tuple[str, ...] = (),
) -> tuple[int, int]:
    """Locate one fully visible row by exact child labels from the focused window."""
    if (not isinstance(labels, (tuple, list)) or any(not isinstance(label, str) or not label.strip() for label in labels)
            or len(set(labels)) < 2):
        raise ValueError("a grouped row needs at least two distinct labels")
    require_focused_app(tree, bundle)
    wanted = set(labels)
    viewport = tree.get("attributes", {})
    def visible_nodes(node, window_id):
        attrs = node.get("attributes", {})
        if (attrs.get("visible") == "false" or attrs.get("enabled") == "false"
                or attrs.get("hostWindowId", window_id) != window_id):
            return
        if attrs.get("visible") == "true":
            yield node
        for child in node.get("children", []):
            yield from visible_nodes(child, window_id)

    windows = [node for node in tree.get("children", [])
               if node.get("attributes", {}).get("focused") == "true"
               and node["attributes"].get("bundleName") == bundle and node["attributes"].get("pagePath")]
    if len(windows) != 1 or not (window_id := windows[0]["attributes"].get("hostWindowId")):
        raise ValueError("expected one focused app window with a native window ID")
    window = windows[0]
    nodes = list(visible_nodes(window, window_id))
    overlays = [node["attributes"] for node in nodes if node["attributes"].get("id") in obstruction_ids]
    obstructions = visible_tab_bar_bounds(window)
    if container_id is not None:
        matching = [node for node in nodes if node["attributes"].get("id") == container_id]
        if len(matching) != 1:
            raise ValueError(f"expected one visible row container {container_id!r}, found {len(matching)}")
        nodes = visible_nodes(matching[0], window_id)
    candidates = []
    for node in nodes:
        attrs = node["attributes"]
        if (attrs.get("type") not in ("Row", "ListItem") or attrs.get("clickable") != "true"
                or attrs.get("hostWindowId") != window_id
                or not control_fits_viewport(attrs, viewport, overlays)
                or not control_fits_viewport(attrs, window["attributes"], [])
                or overlaps_obstruction(attrs, obstructions)):
            continue
        left, top, right, bottom = _bounds(attrs)
        children = [child["attributes"] for branch in node.get("children", [])
                    for child in visible_nodes(branch, window_id)]
        names = {child.get("text") for child in children if child.get("type") == "Text"
                 and child.get("hostWindowId") == window_id
                 and (box := _bounds(child)) and left <= box[0] < box[2] <= right
                 and top <= box[1] < box[3] <= bottom}
        if wanted <= names and not any(child.get("clickable") == "true" for child in children):
            candidates.append(((left + right) // 2, (top + bottom) // 2))
    if len(candidates) != 1:
        raise ValueError(f"expected one actionable grouped row, found {len(candidates)}")
    return candidates[0]


def selected_tab_label(tree: dict, labels: set[str], *, container_id: str | None = None) -> str:
    """Read the visible label of a selected item in a native or specified custom tab bar."""
    selected = []
    scope_window = None

    def visit(node, in_tab_bar=False, in_selected=False):
        attrs = node.get("attributes", {})
        if container_id is not None and (
            attrs.get("visible") == "false" or attrs.get("enabled") == "false"
            or (scope_window is not None and attrs.get("hostWindowId", scope_window) != scope_window)
        ):
            return
        in_tab_bar = in_tab_bar or attrs.get("type") == "TabBar"
        in_selected = in_selected or (in_tab_bar and attrs.get("type") != "TabBar"
                                      and attrs.get("visible") == "true" and attrs.get("selected") == "true")
        label = attrs.get("text")
        if in_selected and attrs.get("visible") == "true" and label in labels:
            selected.append(label)
        for child in node.get("children", []):
            visit(child, in_tab_bar, in_selected)

    if container_id is None:
        visit(tree)
    else:
        matches = list(_visible_containers(tree, container_id))
        if len(matches) != 1:
            raise ValueError(f"expected one visible tab container {container_id!r}, found {len(matches)}")
        scope = matches[0]
        scope_window = scope["attributes"].get("hostWindowId")
        for child in scope.get("children", []):
            visit(child, in_tab_bar=True)
    if len(selected) != 1:
        raise ValueError(f"expected one selected TabBar label, found {selected!r}")
    return selected[0]


if __name__ == "__main__":
    import sys
    sys.stderr.write(
        "uitest_action.py is a library module and cannot be invoked as a CLI.\n"
        "Import and use the following functions in your code:\n"
        "  - require_focused_app(tree, bundle)\n"
        "  - label_action_center(tree, label)\n"
        "  - grouped_row_action_center(tree, labels, bundle=...)\n"
        "  - selected_tab_label(tree, labels)\n"
    )
    sys.exit(1)
