"""Native window/modal visual observation contract; no scenario recorder or behavior binding."""
from hashlib import sha256
import json
import re

OBSERVATION_CONTRACT = 'native-page-state-v2'
BOOLEAN_SELECTOR_FIELDS = frozenset({'checked', 'selected', 'enabled', 'clickable'})
# Visible native modal layers.  ``SheetWrapper`` is a transparent container, not a
# modal by itself: it and its ``SheetPage`` child form one modal chain.
MODAL_TYPES = frozenset({'SheetPage', 'ModalPage', 'Dialog', 'AlertDialog', 'ActionSheet', 'Popup'})
# The sheet pattern keeps its own ``FocusHub`` in step with ``FocusSheetId``, so a
# ``SheetPage`` and the ``SheetWrapper`` that directly hosts it carry the same own
# ``focused`` flag.  A sibling ``ModalPage`` publishes its own flag too.  Those flags are
# evidence for *this one observed shape only*: they must never be generalised to "the
# focused modal is the top one".
_SHEET_PAGE_TYPE = 'SheetPage'
_SHEET_WRAPPER_TYPE = 'SheetWrapper'
_MODAL_PAGE_TYPE = 'ModalPage'
# ``SheetWrapper`` is a transparent container rather than a modal layer, but it is
# summarised in the rejection diagnostics so each sheet chain shows its own focus flag.
_LOCATOR_TYPES = MODAL_TYPES | {_SHEET_WRAPPER_TYPE}
_MULTIPLE_MODAL_ERROR = ('multiple active native modal layers are visible; their order '
                         'cannot be determined')
_MAX_LOCATOR_LAYERS = 8
_LOCATOR_TYPE = re.compile(r'[A-Za-z][A-Za-z0-9_]{0,31}')
_LOCATOR_GEOMETRY = re.compile(r'[0-9,\[\]\- ]{1,32}')
_LOCATOR_NUMBER = re.compile(r'-?[0-9]{1,8}')


def _strict_bool(value, field):
    """Accept only a real boolean or the explicit strings 'true'/'false'."""
    if type(value) is bool:
        return value
    if isinstance(value, str) and value in ('true', 'false'):
        return value == 'true'
    raise ValueError(f'native tree field {field} must be a boolean or "true"/"false"')


def _attribute_bool(attributes, field):
    return None if field not in attributes else _strict_bool(attributes[field], field)


def validate_bundle(bundle):
    """Reject a missing or blank bundle without imposing a vendor-specific shape."""
    if not isinstance(bundle, str) or not bundle.strip():
        raise ValueError('native scenario evidence requires a non-blank bundle identifier')
    return bundle


def focus_flag(attributes):
    """Strictly read one window focus flag; a missing flag simply means unfocused."""
    if 'focused' not in attributes:
        return False
    return _strict_bool(attributes['focused'], 'focused')


class FocusWindowDiagnosticsError(ValueError):
    """A malformed focus flag, carrying the diagnostics of the definitely focused windows."""

    def __init__(self, message, windows):
        self.windows = windows
        super().__init__(message)


def window_diagnostics(records):
    """Project focus records into the ``bundle``/``page`` pairs used for diagnostics."""
    return [{'bundle': record['bundle'] if isinstance(record['bundle'], str) else '',
             'page': record['page'] if isinstance(record['page'], str) else ''}
            for record in records]


def focused_window_records(tree):
    """Shared interpretation of the top-level native windows for every consumer.

    A malformed ``focused`` flag leaves that window's focus undetermined, so it is never
    reported as a definite focus.  The failure is still raised, carrying the diagnostics
    of the windows whose focus *is* known, so a consumer can keep its own error type.
    """
    children = tree.get('children', []) if isinstance(tree, dict) else []
    records = []
    malformed = None
    for window in children:
        if not isinstance(window, dict):
            continue
        attributes = window.get('attributes')
        if not isinstance(attributes, dict):
            attributes = {}
        try:
            focused = focus_flag(attributes)
        except ValueError as error:
            if malformed is None:
                malformed = error
            continue
        if not focused:
            continue
        records.append({'node': window, 'attributes': attributes,
                        'bundle': attributes.get('bundleName'),
                        'page': attributes.get('pagePath')})
    if malformed is not None:
        raise FocusWindowDiagnosticsError(str(malformed), window_diagnostics(records))
    return records


def focused_window(tree, bundle):
    validate_bundle(bundle)
    windows = focused_window_records(tree)
    if len(windows) != 1:
        raise ValueError('native scenario evidence requires the unique focused application window')
    attributes = windows[0]['attributes']
    page = attributes.get('pagePath')
    if (attributes.get('bundleName') != bundle
            or not isinstance(page, str) or not page.strip()):
        raise ValueError('native scenario evidence requires the unique focused application window')
    return windows[0]['node']


_SELECTOR_FIELDS = frozenset({'id', 'type', 'text', 'checked', 'selected', 'enabled', 'clickable'})
_PREDICATE_FIELDS = frozenset({'bundle', 'page_path', 'present', 'absent'})
_OPTIONAL_PREDICATE_FIELDS = frozenset({'within'})


def _validate_selector(selector):
    if (not isinstance(selector, dict) or not selector
            or set(selector) - _SELECTOR_FIELDS
            or not set(selector) & {'id', 'type', 'text'}):
        raise ValueError('invalid target page/state selector')
    for key, value in selector.items():
        if key in BOOLEAN_SELECTOR_FIELDS:
            _strict_bool(value, key)
        elif not isinstance(value, str):
            raise ValueError('invalid target page/state selector')


def validate_state_predicate(value):
    if (not isinstance(value, dict)
            or not _PREDICATE_FIELDS <= set(value)
            or set(value) - (_PREDICATE_FIELDS | _OPTIONAL_PREDICATE_FIELDS)
            or not isinstance(value['present'], list) or not 1 <= len(value['present']) <= 16
            or not isinstance(value['absent'], list) or len(value['absent']) > 16):
        raise ValueError('approved target observation requires bundle, page_path, present and absent')
    validate_bundle(value['bundle'])
    if not isinstance(value['page_path'], str) or not value['page_path'].strip():
        raise ValueError('approved target observation requires bundle, page_path, present and absent')
    for selector in value['present'] + value['absent']:
        _validate_selector(selector)
    if 'within' in value:
        within = value['within']
        if not isinstance(within, dict) or set(within) != {'ancestor'}:
            raise ValueError('within scope requires exactly one ancestor selector')
        _validate_selector(within['ancestor'])
    return value


def _selector_matches(attributes, selector):
    for key, expected in selector.items():
        if key in BOOLEAN_SELECTOR_FIELDS:
            if key not in attributes or _strict_bool(attributes[key], key) != _strict_bool(expected, key):
                return False
        elif attributes.get(key) != expected:
            return False
    return True


def _visible_window_records(window, window_bundle, window_host):
    """Collect one visible same-window tree, keeping foreign/hidden/extension exclusion.

    ``parent`` keeps its original meaning: the nearest *recorded* visible ancestor, which is
    what the subtree/ancestor/matching helpers rely on.  ``direct_parent`` is tracked
    separately: the record index of the node's actual parent in the original tree, or
    ``None`` when that parent carries no visible record (missing or ``visible`` false).
    A folded ancestor is therefore never reported as a real direct parent.
    """
    records = []

    def visit(node, parent, direct_parent, inherited_bundle, inherited_host):
        if not isinstance(node, dict):
            return
        attributes = node.get('attributes')
        if not isinstance(attributes, dict):
            attributes = {}
        node_bundle = attributes.get('bundleName', inherited_bundle)
        node_host = attributes.get('hostWindowId', inherited_host)
        if node_bundle != window_bundle or node_host != window_host:
            return
        if attributes.get('type') == 'UIExtensionComponent':
            return
        visible = _attribute_bool(attributes, 'visible')
        index = None
        if visible is True:
            index = len(records)
            records.append({'attributes': attributes, 'parent': parent,
                            'direct_parent': direct_parent, 'children': []})
            if parent is not None:
                records[parent]['children'].append(index)
        if visible is False:
            return
        next_parent = index if index is not None else parent
        for child in node.get('children', []):
            visit(child, next_parent, index, node_bundle, node_host)

    visit(window, None, None, window_bundle, window_host)
    return records


def _is_ancestor(records, ancestor, node):
    parent = records[node]['parent']
    while parent is not None:
        if parent == ancestor:
            return True
        parent = records[parent]['parent']
    return False


def _focused_modal_leaf(records, leaves):
    """Return the unique focused leaf of the documented cover-sheet shape, else ``None``.

    This is the only multi-modal shape the tool can resolve without guessing, because it is
    the only one carrying independent own-focus evidence:

    * every leaf is a ``SheetPage`` or ``ModalPage`` and at least one leaf is a ``SheetPage``,
    * each ``SheetPage`` sits directly under its own *distinct* ``SheetWrapper``; the page
      and that wrapper both hold a strict bool/``'true'``/``'false'`` ``focused`` flag and
      the two agree,
    * each ``ModalPage`` holds its own strict flag -- a focused descendant is not evidence,
    * the branch containers (a sheet's wrapper, or the ``ModalPage`` itself) are distinct
      and share one recorded direct parent, and that parent is known -- an unrecorded parent
      is unknown, and two unknowns are not one shared parent,
    * exactly one branch is focused.

    Document order, ``zIndex``, the focus of ordinary descendants and the expected predicate
    itself are never consulted.
    """
    branches = []
    has_sheet_page = False
    for index in leaves:
        attributes = records[index]['attributes']
        kind = attributes.get('type')
        try:
            if kind == _SHEET_PAGE_TYPE:
                has_sheet_page = True
                # The page must hang directly under its wrapper: an unrecorded or folded
                # intermediate node leaves the direct parent unknown instead of a wrapper.
                container = records[index]['direct_parent']
                if (container is None
                        or records[container]['attributes'].get('type') != _SHEET_WRAPPER_TYPE):
                    return None
                leaf_flag = _attribute_bool(attributes, 'focused')
                container_flag = _attribute_bool(records[container]['attributes'], 'focused')
                if leaf_flag is None or container_flag is None or leaf_flag != container_flag:
                    return None
                branches.append((container, leaf_flag))
            elif kind == _MODAL_PAGE_TYPE:
                flag = _attribute_bool(attributes, 'focused')
                if flag is None:
                    return None
                branches.append((index, flag))
            else:
                return None
        except ValueError:
            return None
    if not has_sheet_page:
        return None
    containers = [container for container, _ in branches]
    if len(set(containers)) != len(containers):
        return None
    parents = {records[container]['direct_parent'] for container in containers}
    if len(parents) != 1 or None in parents:
        return None
    focused = [index for index, (_, flag) in zip(leaves, branches) if flag]
    return focused[0] if len(focused) == 1 else None


def _active_modal_index(records):
    """Return the innermost visible modal layer; ambiguous sibling layers are rejected.

    A single modal chain keeps its original behaviour: it is the active layer without any
    focus inspection.  Several independent leaf modals are resolved only through the
    documented cover-sheet own-focus relation (:func:`_focused_modal_leaf`); every other
    multi-modal tree stays rejected.
    """
    modal = [index for index, record in enumerate(records)
             if record['attributes'].get('type') in MODAL_TYPES]
    # A modal nested under another modal is the same stack chain, not a conflict.
    leaves = [index for index in modal
              if not any(_is_ancestor(records, index, other) for other in modal if other != index)]
    if len(leaves) > 1:
        focused = _focused_modal_leaf(records, leaves)
        if focused is None:
            raise ValueError(f'{_MULTIPLE_MODAL_ERROR}; {_modal_locator(records)}')
        return focused
    return leaves[0] if leaves else None


def _subtree(records, root):
    found, stack = [root], [root]
    while stack:
        for child in records[stack.pop()]['children']:
            found.append(child)
            stack.append(child)
    return found


def _locator_token(value, pattern):
    """Keep a diagnostic field only when it is a bounded type/geometry/number token."""
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        return 'unknown'
    text = str(value).strip()
    return text if pattern.fullmatch(text) else 'unknown'


def _locator_focus(attributes):
    try:
        flag = _attribute_bool(attributes, 'focused')
    except ValueError:
        return 'malformed'
    return 'absent' if flag is None else ('true' if flag else 'false')


def _modal_locator(records):
    """Bounded locator summary of the visible modal layers; never the whole tree.

    Each layer reports its record index, type, parent index, subtree node count, bounds,
    ``zIndex`` and own ``focused`` flag.  Free-form node text is deliberately left out and
    the listing stops at :data:`_MAX_LOCATOR_LAYERS` entries.
    """
    layers = []
    for index, record in enumerate(records):
        if len(layers) == _MAX_LOCATOR_LAYERS:
            break
        attributes = record['attributes']
        if attributes.get('type') not in _LOCATOR_TYPES:
            continue
        layers.append(
            f"#{index} type={_locator_token(attributes.get('type'), _LOCATOR_TYPE)}"
            f" parent={record['parent']} nodes={len(_subtree(records, index))}"
            f" bounds={_locator_token(attributes.get('bounds'), _LOCATOR_GEOMETRY)}"
            f" zIndex={_locator_token(attributes.get('zIndex'), _LOCATOR_NUMBER)}"
            f" focused={_locator_focus(attributes)}")
    return 'visible modal layers: ' + (' | '.join(layers) if layers else 'none')


def observe_state(tree, predicate):
    predicate = validate_state_predicate(predicate)
    window = focused_window(tree, predicate['bundle'])
    attrs = window['attributes']
    if attrs.get('pagePath') != predicate['page_path']:
        raise ValueError('observed native route differs from approved target predicate')
    records = _visible_window_records(window, attrs['bundleName'], attrs.get('hostWindowId'))
    # The active modal (if any) is the innermost visible layer.  Background nodes are
    # still visible but cannot prove that the approved state was reached.
    active = _active_modal_index(records)
    present_scope = _subtree(records, active) if active is not None else list(range(len(records)))
    # Top-level absent keeps its full-window exclusion semantics.
    absent_scope = list(range(len(records)))
    if 'within' in predicate:
        layer_scope = _subtree(records, active) if active is not None else list(range(len(records)))
        ancestors = [index for index in layer_scope
                     if _selector_matches(records[index]['attributes'], predicate['within']['ancestor'])]
        if len(ancestors) != 1:
            raise ValueError('within ancestor must match exactly one visible node in the active layer')
        anchor = ancestors[0]
        # The ancestor itself is not a descendant, so it cannot satisfy present/absent.
        scoped = [index for index in _subtree(records, anchor) if index != anchor]
        present_scope = scoped
        absent_scope = scoped
    selected = []
    for selector in predicate['present']:
        rows = [records[index]['attributes'] for index in present_scope
                if _selector_matches(records[index]['attributes'], selector)]
        if len(rows) != 1:
            raise ValueError('actual native tree does not satisfy approved target page/state predicate')
        # ``selected`` holds the actual attributes dict of each unique match.
        selected.append(rows[0])
    if any(_selector_matches(records[index]['attributes'], selector)
           for selector in predicate['absent'] for index in absent_scope):
        raise ValueError('actual native tree does not satisfy approved target page/state predicate')
    return {'contract': OBSERVATION_CONTRACT, 'bundle': attrs['bundleName'], 'page_path': attrs['pagePath'],
            'active_layer': None if active is None else {
                'type': records[active]['attributes']['type'], 'record': active},
            'predicate_sha256': sha256(json.dumps(predicate, sort_keys=True, ensure_ascii=False,
                                                 separators=(',', ':')).encode()).hexdigest(),
            'matched': [dict(attributes) for attributes in selected]}


def active_layer_tree(tree, predicate):
    """Project only visible same-window active-layer nodes; raw bytes remain the evidence."""
    observe_state(tree, predicate)
    window = focused_window(tree, predicate['bundle'])
    attrs = window['attributes']
    records = _visible_window_records(window, attrs['bundleName'], attrs.get('hostWindowId'))
    active = _active_modal_index(records)
    indices = _subtree(records, active) if active is not None else list(range(len(records)))
    selected = set(indices)
    def project(index):
        return {'attributes': dict(records[index]['attributes']),
                'children': [project(i) for i in records[index]['children'] if i in selected]}
    return {'attributes': {'bounds': tree.get('attributes', {}).get('bounds') or attrs.get('bounds')},
            'children': [project(i) for i in indices if records[i]['parent'] not in selected]}
