"""Resolve a label to its visible HarmonyOS UITest action."""
from __future__ import annotations

import importlib
from pathlib import Path
import re
import sys

_NATIVE_MODULE = 'native_scenario_evidence'

# The self-contained install contract: a source checkout and the installed
# ``.claude`` tree have the same shape, so this file always lives in
# ``skills/i2h-verify/scripts`` next to the shared contract in
# ``skills/i2h-plan/scripts``.  That one directory is the whole search space.
_PLAN_SCRIPTS = Path(__file__).resolve().parents[2] / 'i2h-plan' / 'scripts'


def _native_module_directory():
    """Return the single sibling Plan ``scripts`` directory this install ships.

    Nothing else is searched: a same-named module in some other ancestor directory
    or elsewhere on ``sys.path`` belongs to a different project and must never be
    mixed with this installation.
    """
    if not (_PLAN_SCRIPTS / f'{_NATIVE_MODULE}.py').is_file():
        return None
    return _PLAN_SCRIPTS


def _is_installed_copy(module, expected: Path) -> bool:
    """Accept only the module file this installation actually ships."""
    origin = getattr(module, '__file__', None)
    return isinstance(origin, str) and Path(origin).resolve() == expected


def _import_native_module():
    """Import the shared native evidence contract, refusing every other copy.

    The caller's ``sys.path`` is never trusted to locate the module, and a module of
    the same name that was already imported from anywhere else is a version mix:
    it is rejected instead of silently reused from the import cache.
    """
    directory = _native_module_directory()
    if directory is None:
        raise ImportError(
            f'cannot import {_NATIVE_MODULE!r}: the shared contract is not installed next to '
            f'this module at {_PLAN_SCRIPTS}')
    expected = (directory / f'{_NATIVE_MODULE}.py').resolve()
    loaded = sys.modules.get(_NATIVE_MODULE)
    if loaded is not None:
        if not _is_installed_copy(loaded, expected):
            raise ImportError(
                f'{_NATIVE_MODULE!r} is already imported from '
                f'{getattr(loaded, "__file__", None)!r}, not from this installation at {expected}')
        return loaded
    path = str(directory)
    if path not in sys.path:
        # Insert first so a foreign copy elsewhere on ``sys.path`` cannot win.
        sys.path.insert(0, path)
    module = importlib.import_module(_NATIVE_MODULE)
    if not _is_installed_copy(module, expected):
        raise ImportError(
            f'{_NATIVE_MODULE!r} resolved to {getattr(module, "__file__", None)!r}, not to this '
            f'installation at {expected}')
    return module


native = _import_native_module()


class ForegroundError(ValueError):
    def __init__(self, bundle: str, windows: list[dict], detail: str = ''):
        self.windows = windows
        focused = sorted({window['bundle'] for window in windows if window['bundle']})
        message = f"expected foreground {bundle!r}, observed {focused!r}"
        super().__init__(f"{message}: {detail}" if detail else message)


def _is_focused(attrs: dict) -> bool:
    """Read the focus flag through the shared native window contract."""
    return native.focus_flag(attrs)


def _focused_windows(tree: dict, expected: str = '') -> list[dict]:
    """Project the focused windows, keeping this module's own error type and diagnostics.

    ``native`` refuses a malformed focus flag; that refusal is translated here so callers
    never see a bare ``native.ValueError`` that has dropped the observed windows.
    """
    try:
        records = native.focused_window_records(tree)
    except native.FocusWindowDiagnosticsError as error:
        raise ForegroundError(expected, error.windows, str(error)) from error
    return native.window_diagnostics(records)


def require_focused_app(tree: dict, bundle: str) -> None:
    """Require one focused app root before treating a dump as product evidence."""
    native.validate_bundle(bundle)
    windows = _focused_windows(tree, bundle)
    # The app may expose an unfocused root below a system-owned modal.
    # Require a single focused root that also identifies an actual ability surface,
    # so that a duplicated or ghost window cannot satisfy the foreground check.  A blank
    # route is not an ability surface, so it can never be accepted as product evidence.
    surface = any(window['bundle'] == bundle and window['page'].strip() for window in windows)
    if len(windows) != 1 or windows[0]['bundle'] != bundle or not surface:
        raise ForegroundError(bundle, windows)


def observed_window(tree: dict) -> dict:
    """Read the foreground app window so a receipt records what was actually observed."""
    windows = _focused_windows(tree)
    if len(windows) != 1:
        raise ForegroundError('', windows)
    bundle, page = windows[0]['bundle'], windows[0]['page']
    # Same actual-ability-page requirement as require_focused_app: an unfocused envelope,
    # a missing page or a page that is not a real path is not a product window.
    if not isinstance(bundle, str) or not bundle.strip() or not isinstance(page, str) or not page.strip():
        raise ForegroundError('', windows)
    return {'bundle': bundle, 'page_path': page}


def focused_page_matches(tree: dict, bundle: str, page: str) -> bool:
    """Match the one focused app window, rejecting envelope attributes and conflicts."""
    try:
        windows = _focused_windows(tree)
    except ValueError:
        return False
    return (len(windows) == 1 and isinstance(bundle, str) and bool(bundle.strip())
            and isinstance(page, str) and bool(page.strip())
            and windows[0]['bundle'] == bundle and windows[0]['page'] == page)


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

    records = [record for record in native.focused_window_records(tree)
               if record['bundle'] == bundle
               and isinstance(record['page'], str) and record['page'].strip()]
    if len(records) != 1 or not (window_id := records[0]['attributes'].get("hostWindowId")):
        raise ValueError("expected one focused app window with a native window ID")
    window = records[0]['node']
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
