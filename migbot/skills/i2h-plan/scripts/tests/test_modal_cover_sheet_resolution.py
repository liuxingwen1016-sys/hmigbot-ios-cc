"""Contract tests for a SheetPage leaf beside a ModalPage leaf in one native tree.

The documented cover-sheet shape is the only multi-modal tree the tool may resolve:
leaves are ``SheetPage``/``ModalPage`` with at least one ``SheetPage``; each sheet page
hangs directly under its own ``SheetWrapper`` and both carry the same strict own
``focused`` flag; each ``ModalPage`` carries its own strict flag; distinct branch
containers share one recorded non-None direct parent; exactly one branch is focused.

Unknown/folded parents, Dialog/Popup mixtures, borrowed descendant focus, missing or
illegal flags, two focused branches and zero focused branches all stay rejected.  Order,
``zIndex``, descendant focus and the expected predicate are never selection evidence.

Fixtures are device-free and generic: no project, control, package or file identifiers.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve()
_SCRIPTS = _HERE.parents[1]
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import native_scenario_evidence as native  # noqa: E402


BUNDLE = 'com.example.test'
PAGE = 'pages/Root'
HOST = '1'

# Marker for "this node must not carry a focused attribute at all".
_MISSING = object()


def _node(attributes, children=()):
    return {'attributes': dict(attributes), 'children': list(children)}


def _visible(attributes):
    attributes = dict(attributes)
    attributes['visible'] = True
    return attributes


_WINDOW_ATTRIBUTES = {'focused': True, 'bundleName': BUNDLE, 'pagePath': PAGE, 'hostWindowId': HOST}


def _window(children):
    return _node(_visible(_WINDOW_ATTRIBUTES), children)


def _window_without_visible(children):
    return _node(_WINDOW_ATTRIBUTES, children)


def _tree(*windows):
    return {'children': list(windows)}


def _predicate(present, absent=(), **extra):
    value = {'bundle': BUNDLE, 'page_path': PAGE,
             'present': list(present), 'absent': list(absent)}
    value.update(extra)
    return value


def _base_list():
    return _node(_visible({'id': 'recordList', 'type': 'List'}))


def _control(ident):
    return _node(_visible({'id': ident, 'type': 'TextInput'}))


def _row(ident, *children):
    return _node(_visible({'id': ident, 'type': 'Row'}), children)


def _text(ident, text):
    return _node(_visible({'id': ident, 'type': 'Text', 'text': text}))


def _sheet_chain(name, wrapper_focus, page_focus, *, content=()):
    page = {'id': f'sheet{name}', 'type': 'SheetPage'}
    if page_focus is not _MISSING:
        page['focused'] = page_focus
    wrapper = {'id': f'wrapper{name}', 'type': 'SheetWrapper'}
    if wrapper_focus is not _MISSING:
        wrapper['focused'] = wrapper_focus
    return _node(_visible(wrapper), [_node(_visible(page), list(content))])


def _modal_page(name, focus, *, content=()):
    attributes = {'id': f'modal{name}', 'type': 'ModalPage'}
    if focus is not _MISSING:
        attributes['focused'] = focus
    return _node(_visible(attributes), list(content))


def _cover_sheet_tree(*, sheet=(False, False), modal=False, modal_first=False,
                      sheet_content=(), modal_content=()):
    branches = [_sheet_chain('S', sheet[0], sheet[1], content=sheet_content),
                _modal_page('M', modal, content=modal_content)]
    if modal_first:
        branches.reverse()
    return _tree(_window([_base_list(), *branches]))


def _scoped_tree(*, rows_in_active=1):
    active = [_row('rowSheet', _text('item', 'SheetRecord')) for _ in range(rows_in_active)]
    return _cover_sheet_tree(
        sheet=(True, True), modal=False,
        sheet_content=[_control('sheetEditor'), *active],
        modal_content=[_control('modalEditor'),
                       _row('rowModal', _text('item', 'ModalRecord'))])


# --------------------------------------------------------------------------- #
# The narrow positive rule: one agreed focused branch becomes the active layer.
# --------------------------------------------------------------------------- #

class FocusedCoverSheetTests(unittest.TestCase):
    def test_focused_sheet_beside_unfocused_modal_is_the_active_layer(self):
        tree = _cover_sheet_tree(
            sheet=(True, True), modal=False,
            sheet_content=[_control('sheetEditor'), _text('item', 'SheetRecord')],
            modal_content=[_control('modalEditor'), _text('item', 'ModalRecord')])
        observation = native.observe_state(tree, _predicate([{'id': 'sheetEditor'}]))
        self.assertEqual([row['id'] for row in observation['matched']], ['sheetEditor'])
        observation = native.observe_state(
            tree, _predicate([{'id': 'item', 'text': 'SheetRecord'}]))
        self.assertEqual([row['text'] for row in observation['matched']], ['SheetRecord'])
        # ``present`` only scans the active sheet subtree, never the covered modal.
        for covered in ({'id': 'modalEditor'}, {'id': 'recordList'},
                        {'id': 'item', 'text': 'ModalRecord'}):
            with self.subTest(covered=covered):
                with self.assertRaises(ValueError):
                    native.observe_state(tree, _predicate([covered]))

    def test_focused_modal_beside_unfocused_sheets_is_the_active_layer(self):
        tree = _tree(_window([
            _base_list(),
            _sheet_chain('A', False, False, content=[_control('sheetAEditor')]),
            _sheet_chain('B', False, False, content=[_control('sheetBEditor')]),
            _modal_page('M', True, content=[_control('modalEditor')]),
        ]))
        observation = native.observe_state(tree, _predicate([{'id': 'modalEditor'}]))
        self.assertEqual([row['id'] for row in observation['matched']], ['modalEditor'])
        for covered in ({'id': 'sheetAEditor'}, {'id': 'sheetBEditor'}, {'id': 'recordList'}):
            with self.subTest(covered=covered):
                with self.assertRaises(ValueError):
                    native.observe_state(tree, _predicate([covered]))

    def test_reversing_sibling_order_does_not_change_resolution(self):
        for modal_first in (False, True):
            for sheet, modal, active, covered in (
                    ((True, True), False, 'sheetEditor', 'modalEditor'),
                    ((False, False), True, 'modalEditor', 'sheetEditor')):
                with self.subTest(modal_first=modal_first, modal=modal):
                    tree = _cover_sheet_tree(
                        sheet=sheet, modal=modal, modal_first=modal_first,
                        sheet_content=[_control('sheetEditor')],
                        modal_content=[_control('modalEditor')])
                    observation = native.observe_state(tree, _predicate([{'id': active}]))
                    self.assertEqual([row['id'] for row in observation['matched']], [active])
                    with self.assertRaises(ValueError):
                        native.observe_state(tree, _predicate([{'id': covered}]))

    def test_boolean_and_string_focus_forms_resolve_identically(self):
        for sheet, modal in (((True, True), False),
                             (('true', 'true'), 'false'),
                             ((True, 'true'), False),
                             ((False, False), 'true')):
            with self.subTest(sheet=sheet, modal=modal):
                expected = 'sheetEditor' if sheet[0] in (True, 'true') else 'modalEditor'
                tree = _cover_sheet_tree(
                    sheet=sheet, modal=modal,
                    sheet_content=[_control('sheetEditor')],
                    modal_content=[_control('modalEditor')])
                observation = native.observe_state(tree, _predicate([{'id': expected}]))
                self.assertEqual([row['id'] for row in observation['matched']], [expected])

    def test_single_modal_page_still_resolves_without_any_focus_flag(self):
        tree = _tree(_window([
            _base_list(),
            _modal_page('M', _MISSING, content=[_control('modalEditor')]),
        ]))
        observation = native.observe_state(tree, _predicate([{'id': 'modalEditor'}]))
        self.assertEqual([row['id'] for row in observation['matched']], ['modalEditor'])


# --------------------------------------------------------------------------- #
# Every other multi-modal tree keeps its original rejection.
# --------------------------------------------------------------------------- #

class RejectedCoverSheetTests(unittest.TestCase):
    def _assert_rejected(self, tree, identifiers=('sheetEditor', 'modalEditor')):
        # The ambiguity prefix distinguishes a real layer rejection from a tree that was
        # accepted and then merely failed to satisfy a selector.
        for ident in identifiers:
            with self.subTest(ident=ident):
                with self.assertRaises(ValueError) as caught:
                    native.observe_state(tree, _predicate([{'id': ident}]))
                self.assertTrue(str(caught.exception).startswith(
                    'multiple active native modal layers are visible'))

    def test_two_focused_branches_are_rejected(self):
        self._assert_rejected(_cover_sheet_tree(
            sheet=(True, True), modal=True,
            sheet_content=[_control('sheetEditor')],
            modal_content=[_control('modalEditor')]))

    def test_no_focused_branch_is_rejected(self):
        self._assert_rejected(_cover_sheet_tree(
            sheet=(False, False), modal=False,
            sheet_content=[_control('sheetEditor')],
            modal_content=[_control('modalEditor')]))

    def test_missing_focus_is_rejected(self):
        cases = {
            'modal without own focus': _cover_sheet_tree(sheet=(True, True), modal=_MISSING),
            'page without own focus': _cover_sheet_tree(sheet=(True, _MISSING), modal=False),
            'wrapper without own focus': _cover_sheet_tree(sheet=(_MISSING, True), modal=False),
            'sheet without any focus': _cover_sheet_tree(sheet=(_MISSING, _MISSING), modal=False),
        }
        for name, tree in cases.items():
            with self.subTest(case=name):
                self._assert_rejected(tree)

    def test_illegal_focus_forms_are_rejected(self):
        for modal in ('', 0, 1, 'True', 'yes'):
            with self.subTest(modal=modal):
                self._assert_rejected(_cover_sheet_tree(sheet=(False, False), modal=modal))
        for sheet in (('', ''), (0, 0), (1, 1), ('True', 'True')):
            with self.subTest(sheet=sheet):
                self._assert_rejected(_cover_sheet_tree(sheet=sheet, modal=False))

    def test_page_and_wrapper_focus_contradiction_is_rejected(self):
        for sheet in ((True, False), (False, True), ('true', 'false'), (False, 'true')):
            with self.subTest(sheet=sheet):
                self._assert_rejected(_cover_sheet_tree(sheet=sheet, modal=False))

    def test_modal_focus_cannot_be_borrowed_from_a_focused_child(self):
        sheet = _sheet_chain('S', False, False, content=[_control('sheetEditor')])
        modal = _modal_page('M', _MISSING, content=[
            _node(_visible({'id': 'modalEditor', 'type': 'TextInput', 'focused': True}))])
        self._assert_rejected(_tree(_window([_base_list(), sheet, modal])))

    def test_branches_with_different_direct_parents_are_rejected(self):
        sheet = _sheet_chain('S', True, True, content=[_control('sheetEditor')])
        modal = _modal_page('M', False, content=[_control('modalEditor')])
        group = _node(_visible({'id': 'group', 'type': 'Column'}), [sheet])
        self._assert_rejected(_tree(_window([_base_list(), group, modal])))

    def test_branches_with_unrecorded_direct_parent_are_rejected(self):
        sheet = _sheet_chain('S', True, True, content=[_control('sheetEditor')])
        modal = _modal_page('M', False, content=[_control('modalEditor')])
        tree = _tree(_window_without_visible([_base_list(), sheet, modal]))
        self._assert_rejected(tree)

    def test_one_unknown_direct_parent_is_not_a_shared_parent(self):
        sheet = _sheet_chain('S', True, True, content=[_control('sheetEditor')])
        modal = _modal_page('M', False, content=[_control('modalEditor')])
        # The container has no record of its own, so the modal's direct parent is unknown
        # while the wrapper's parent is the recorded window.  {None, window} is no match.
        hidden_group = _node({'id': 'group', 'type': 'Column'}, [modal])
        self._assert_rejected(_tree(_window([_base_list(), sheet, hidden_group])))

    def test_sheet_page_needs_its_wrapper_as_direct_parent(self):
        chain = _sheet_chain('S', True, True, content=[_control('sheetEditor')])
        page = chain['children'][0]
        chain['children'] = [_node(_visible({'id': 'container', 'type': 'Container'}), [page])]
        modal = _modal_page('M', False, content=[_control('modalEditor')])
        self._assert_rejected(_tree(_window([_base_list(), chain, modal])))

    def test_dialog_mixed_with_the_cover_sheet_shape_is_rejected(self):
        sheet = _sheet_chain('S', True, True, content=[_control('sheetEditor')])
        modal = _modal_page('M', False, content=[_control('modalEditor')])
        dialog = _node(_visible({'id': 'dialog', 'type': 'Dialog', 'focused': True}),
                       [_control('dialogEditor')])
        for branches in ([sheet, dialog], [modal, dialog], [sheet, modal, dialog]):
            with self.subTest(branch_types=[node['attributes']['type'] for node in branches]):
                self._assert_rejected(
                    _tree(_window([_base_list(), *branches])),
                    ('sheetEditor', 'modalEditor', 'dialogEditor'))

    def test_two_modal_pages_without_any_sheet_page_are_rejected(self):
        first = _modal_page('A', True, content=[_control('modalA')])
        second = _modal_page('B', False, content=[_control('modalB')])
        self._assert_rejected(_tree(_window([_base_list(), first, second])),
                              ('modalA', 'modalB'))


# --------------------------------------------------------------------------- #
# Scope semantics are unchanged: present in the active layer, absent in the window.
# --------------------------------------------------------------------------- #

class CoverSheetScopeTests(unittest.TestCase):
    def test_default_absent_covers_the_whole_window(self):
        tree = _scoped_tree()
        for absent in ({'id': 'recordList'}, {'id': 'modalEditor'},
                       {'id': 'sheetEditor'}, {'id': 'rowModal'}):
            with self.subTest(absent=absent):
                with self.assertRaises(ValueError):
                    native.observe_state(tree, _predicate([{'id': 'sheetEditor'}], [absent]))

    def test_absent_of_an_absent_selector_still_passes(self):
        observation = native.observe_state(
            _scoped_tree(), _predicate([{'id': 'sheetEditor'}], [{'id': 'neverVisible'}]))
        self.assertEqual([row['id'] for row in observation['matched']], ['sheetEditor'])

    def test_within_narrows_to_the_active_sheet(self):
        observation = native.observe_state(
            _scoped_tree(),
            _predicate([{'id': 'item', 'text': 'SheetRecord'}],
                       within={'ancestor': {'id': 'rowSheet'}}))
        self.assertEqual([row['text'] for row in observation['matched']], ['SheetRecord'])

    def test_within_ancestor_in_the_covered_modal_is_rejected(self):
        with self.assertRaises(ValueError):
            native.observe_state(
                _scoped_tree(),
                _predicate([{'id': 'item'}], within={'ancestor': {'id': 'rowModal'}}))

    def test_within_ancestor_is_not_part_of_the_matched_descendants(self):
        with self.assertRaises(ValueError):
            native.observe_state(
                _scoped_tree(),
                _predicate([{'id': 'rowSheet'}], within={'ancestor': {'id': 'rowSheet'}}))

    def test_within_ancestor_must_stay_unique_inside_the_active_layer(self):
        with self.assertRaises(ValueError):
            native.observe_state(
                _scoped_tree(rows_in_active=2),
                _predicate([{'id': 'item'}], within={'ancestor': {'id': 'rowSheet'}}))


if __name__ == '__main__':
    unittest.main()
