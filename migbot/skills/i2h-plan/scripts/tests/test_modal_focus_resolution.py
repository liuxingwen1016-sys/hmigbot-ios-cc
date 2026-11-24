"""Contract tests for resolving one focused sibling sheet chain in a native tree.

Several independent leaf modals used to be a flat rejection: the tool has no way to
order them.  The one exception is the documented sheet shape, where a ``SheetPage``
and the ``SheetWrapper`` that directly hosts it publish the same own ``focused`` flag.
Only a uniform set of sibling chains with exactly one agreed focused pair may become
the active layer; every other multi-modal tree stays unverified.

A leaf ``SheetPage`` must also hang *directly* under its own ``SheetWrapper``, and those
wrappers must share one recorded direct parent.  A parent whose own ``visible`` flag is
missing carries no record, so the relation stays unknown: an unknown parent -- even the
same unknown twice -- is never a shared parent.

These tests are device-free and use generic identifiers only.  They describe the
observable contract -- which tree is accepted, which is rejected, and that the
rejection diagnostic stays bounded -- not the internal representation of the
resolution: no array position, ``zIndex`` or predicate value may influence the
outcome.
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


# --------------------------------------------------------------------------- #
# Fixtures: generic ids, one visible application window and no real project data.
# --------------------------------------------------------------------------- #

def _node(attributes, children=()):
    return {'attributes': dict(attributes), 'children': list(children)}


def _visible(attributes):
    attributes = dict(attributes)
    attributes['visible'] = True
    return attributes


_WINDOW_ATTRIBUTES = {'focused': True, 'bundleName': BUNDLE, 'pagePath': PAGE, 'hostWindowId': HOST}


def _window(children):
    """One focused application window.  A real device window publishes ``visible``."""
    return _node(_visible(_WINDOW_ATTRIBUTES), children)


def _window_without_visible(children):
    """The same window without a ``visible`` flag: it publishes no record of its own.

    Its children are therefore recorded without any known direct parent, which is the
    uncertain shape the resolution must never read as a shared parent.
    """
    return _node(_WINDOW_ATTRIBUTES, children)


def _tree(*windows):
    return {'children': list(windows)}


def _predicate(present, absent=(), **extra):
    value = {'bundle': BUNDLE, 'page_path': PAGE,
             'present': list(present), 'absent': list(absent)}
    value.update(extra)
    return value


def _record_list():
    return _node(_visible({'id': 'recordList', 'type': 'List'}))


def _editor(name):
    return _node(_visible({'id': name, 'type': 'TextInput'}))


def _row(row_id, *children):
    return _node(_visible({'id': row_id, 'type': 'Row'}), children)


def _item():
    return _node(_visible({'id': 'item', 'type': 'Text', 'text': 'Record'}))


def _sheet_chain(name, wrapper_focus, page_focus, *, content=None):
    """One ``SheetWrapper`` > ``SheetPage`` chain, with optional own focus flags."""
    page = {'id': f'sheet{name}', 'type': 'SheetPage',
            'bounds': '[0,164][1280,2832]', 'zIndex': '0'}
    if page_focus is not _MISSING:
        page['focused'] = page_focus
    wrapper = {'id': f'wrapper{name}', 'type': 'SheetWrapper',
               'bounds': '[0,137][1280,2832]', 'zIndex': '0'}
    if wrapper_focus is not _MISSING:
        wrapper['focused'] = wrapper_focus
    children = [_editor(f'editor{name}')] if content is None else list(content)
    return _node(_visible(wrapper), [_node(_visible(page), children)])


def _sibling_sheets(*specs):
    """Sibling sheet chains in document order; spec *i* is ``(wrapper_focus, page_focus)``.

    Sheets are named A, B, ... by position and each holds an ``editor<name>`` control.
    """
    chains = [_sheet_chain(chr(ord('A') + index), spec[0], spec[1])
              for index, spec in enumerate(specs)]
    return _tree(_window([_record_list(), *chains]))


def _scoped_sheets_tree(*, rows_in_active=1):
    """Active sheet B holds ``rowB`` rows; the covered sheet A holds an equally named row."""
    active = [_row('rowB', _item()) for _ in range(rows_in_active)]
    return _tree(_window([
        _record_list(),
        _sheet_chain('A', False, False, content=[_row('rowA', _item())]),
        _sheet_chain('B', True, True, content=active),
    ]))


def _wrapperless_sheets_tree():
    """Two sibling SheetPages straight under the window, the second one focused."""
    return _tree(_window([
        _record_list(),
        _node(_visible({'id': 'sheetA', 'type': 'SheetPage', 'focused': False}), [_editor('editorA')]),
        _node(_visible({'id': 'sheetB', 'type': 'SheetPage', 'focused': True}), [_editor('editorB')]),
    ]))


def _split_parent_sheets_tree():
    """The second wrapper is a sibling of a group column, not of the first wrapper."""
    return _tree(_window([
        _record_list(),
        _node(_visible({'id': 'group', 'type': 'Column'}),
              [_sheet_chain('A', False, False)]),
        _sheet_chain('B', True, True),
    ]))


def _mixed_modal_tree():
    """A focused sheet chain next to a focused dialog: two modal kinds stay ambiguous."""
    return _tree(_window([
        _record_list(),
        _sheet_chain('A', False, False),
        _node(_visible({'id': 'dialog', 'type': 'Dialog', 'focused': True}),
              [_editor('editorDialog')]),
    ]))


def _descendant_focus_tree():
    """Only a control inside sheet B is focused; the sheet nodes carry no flag."""
    focused_editor = _node(_visible({'id': 'editorB', 'type': 'TextInput', 'focused': True}))
    return _tree(_window([
        _record_list(),
        _sheet_chain('A', _MISSING, _MISSING),
        _sheet_chain('B', _MISSING, _MISSING, content=[focused_editor]),
    ]))


def _shared_wrapper_tree():
    """Two SheetPages under a single wrapper: one chain, not two independent ones."""
    wrapper = _node(_visible({'id': 'wrapper', 'type': 'SheetWrapper', 'focused': True}), [
        _node(_visible({'id': 'sheetA', 'type': 'SheetPage', 'focused': True}), [_editor('editorA')]),
        _node(_visible({'id': 'sheetB', 'type': 'SheetPage', 'focused': True}), [_editor('editorB')]),
    ])
    return _tree(_window([_record_list(), wrapper]))


def _sheets_under_unrecorded_window():
    """Sibling sheet chains whose real direct parent is a window without ``visible``.

    Both wrappers therefore have an unknown direct parent.  Two unknowns are not one
    shared parent, however identical they look.
    """
    return _tree(_window_without_visible([
        _record_list(),
        _sheet_chain('A', False, False),
        _sheet_chain('B', True, True),
    ]))


def _insert_intermediate_container(chain, *, container_visible):
    """Put one ``Container`` between a chain's wrapper and its ``SheetPage``."""
    page = chain['children'][0]
    attributes = _visible({'id': 'container', 'type': 'Container'}) if container_visible \
        else {'id': 'container', 'type': 'Container'}
    chain['children'] = [_node(attributes, [page])]
    return chain


def _sheets_with_intermediate_containers(*, container_visible):
    """Sibling chains whose pages hang under an intermediate ``Container``.

    ``container_visible`` decides whether that container is itself recorded; either way it
    is not the ``SheetWrapper``, even though it is the page's nearest *visible* ancestor.
    """
    return _tree(_window([
        _record_list(),
        _insert_intermediate_container(_sheet_chain('A', False, False), container_visible=container_visible),
        _insert_intermediate_container(_sheet_chain('B', True, True), container_visible=container_visible),
    ]))


# --------------------------------------------------------------------------- #
# The narrow positive rule: one agreed focused sheet chain becomes the active layer.
# --------------------------------------------------------------------------- #

class FocusedSheetResolutionTests(unittest.TestCase):
    def test_only_the_focused_sheet_is_the_active_layer(self):
        tree = _sibling_sheets((False, False), (True, True))
        observation = native.observe_state(tree, _predicate([{'id': 'editorB'}]))
        self.assertEqual([row['id'] for row in observation['matched']], ['editorB'])

    def test_control_of_the_covered_sheet_is_rejected(self):
        tree = _sibling_sheets((False, False), (True, True))
        with self.assertRaises(ValueError):
            native.observe_state(tree, _predicate([{'id': 'editorA'}]))

    def test_control_of_the_covered_base_page_is_rejected(self):
        tree = _sibling_sheets((False, False), (True, True))
        with self.assertRaises(ValueError):
            native.observe_state(tree, _predicate([{'id': 'recordList'}]))

    def test_document_order_does_not_change_the_resolution(self):
        # Both trees hold one focused chain among two siblings; only its position differs.
        for tree, active, covered in ((_sibling_sheets((False, False), (True, True)), 'editorB', 'editorA'),
                                      (_sibling_sheets((True, True), (False, False)), 'editorA', 'editorB')):
            with self.subTest(active=active):
                observation = native.observe_state(tree, _predicate([{'id': active}]))
                self.assertEqual([row['id'] for row in observation['matched']], [active])
                with self.assertRaises(ValueError):
                    native.observe_state(tree, _predicate([{'id': covered}]))

    def test_boolean_and_string_focus_forms_resolve_identically(self):
        accepted = (
            ((False, False), (True, 'true')),
            (('false', 'false'), ('true', True)),
            ((False, 'false'), ('true', 'true')),
        )
        for first, second in accepted:
            with self.subTest(first=first, second=second):
                tree = _sibling_sheets(first, second)
                observation = native.observe_state(tree, _predicate([{'id': 'editorB'}]))
                self.assertEqual([row['id'] for row in observation['matched']], ['editorB'])
                with self.assertRaises(ValueError):
                    native.observe_state(tree, _predicate([{'id': 'editorA'}]))

    def test_focus_flags_are_not_order_or_zindex_evidence(self):
        # The unfocused chain is written first and carries the *lower* zIndex, yet the
        # focused sheet stays the active layer.
        tree = _sibling_sheets((False, False), (True, True))
        self.assertEqual(tree['children'][0]['children'][1]['attributes']['zIndex'], '0')
        observation = native.observe_state(tree, _predicate([{'id': 'editorB'}]))
        self.assertEqual([row['id'] for row in observation['matched']], ['editorB'])


# --------------------------------------------------------------------------- #
# Every other multi-modal tree keeps its original rejection.
# --------------------------------------------------------------------------- #

class RejectedMultiModalEvidenceTests(unittest.TestCase):
    _REJECTED_FOCUS_FORMS = {
        'two focused sheets': ((True, True), (True, True)),
        'no focused sheet': ((False, False), (False, False)),
        'page focused but wrapper not': ((False, True), (False, False)),
        'wrapper focused but page not': ((True, False), (False, False)),
        'no focus on either node of a sheet': ((_MISSING, _MISSING), (True, True)),
        'no focus on the matched wrapper': ((False, False), (True, _MISSING)),
        'no focus on the matched page': ((False, False), (_MISSING, True)),
        'no focus on the unmatched page': ((False, False), (_MISSING, False)),
        'empty string focus': (('', ''), (True, True)),
        'integer focus': ((0, 0), (1, 1)),
        'boolean conflict across one chain': ((True, 'false'), (True, True)),
    }

    def test_conflicting_or_missing_focus_is_rejected(self):
        for name, (first, second) in self._REJECTED_FOCUS_FORMS.items():
            with self.subTest(case=name):
                tree = _sibling_sheets(first, second)
                with self.assertRaises(ValueError):
                    native.observe_state(tree, _predicate([{'id': 'editorB'}]))
                with self.assertRaises(ValueError):
                    native.observe_state(tree, _predicate([{'id': 'editorA'}]))

    def test_sheets_without_wrappers_are_rejected(self):
        with self.assertRaises(ValueError):
            native.observe_state(_wrapperless_sheets_tree(), _predicate([{'id': 'editorB'}]))

    def test_sheets_whose_wrappers_are_not_siblings_are_rejected(self):
        with self.assertRaises(ValueError):
            native.observe_state(_split_parent_sheets_tree(), _predicate([{'id': 'editorB'}]))

    def test_mixed_modal_kinds_are_rejected(self):
        with self.assertRaises(ValueError):
            native.observe_state(_mixed_modal_tree(), _predicate([{'id': 'editorDialog'}]))

    def test_focus_on_a_descendant_is_not_evidence(self):
        with self.assertRaises(ValueError):
            native.observe_state(_descendant_focus_tree(), _predicate([{'id': 'editorB'}]))

    def test_two_pages_under_one_wrapper_are_rejected(self):
        with self.assertRaises(ValueError):
            native.observe_state(_shared_wrapper_tree(), _predicate([{'id': 'editorB'}]))

    def test_sheets_whose_shared_parent_is_unrecorded_are_rejected(self):
        # The window publishes no `visible`, so neither wrapper has a recorded direct
        # parent.  The two unknowns must not collapse into a shared parent.
        tree = _sheets_under_unrecorded_window()
        with self.assertRaises(ValueError):
            native.observe_state(tree, _predicate([{'id': 'editorB'}]))
        with self.assertRaises(ValueError):
            native.observe_state(tree, _predicate([{'id': 'editorA'}]))

    def test_page_whose_direct_parent_is_not_its_wrapper_is_rejected(self):
        # An intermediate Container between wrapper and page is not the wrapper, whether or
        # not that container is itself recorded; folding it away would invent a direct parent.
        for container_visible in (False, True):
            with self.subTest(container_visible=container_visible):
                tree = _sheets_with_intermediate_containers(container_visible=container_visible)
                with self.assertRaises(ValueError):
                    native.observe_state(tree, _predicate([{'id': 'editorB'}]))
                with self.assertRaises(ValueError):
                    native.observe_state(tree, _predicate([{'id': 'editorA'}]))

    def test_a_single_nested_chain_is_still_accepted_without_any_focus_flag(self):
        # Original behaviour for one chain: no focus inspection is introduced here.
        tree = _tree(_window([
            _record_list(),
            _sheet_chain('A', _MISSING, _MISSING),
        ]))
        observation = native.observe_state(tree, _predicate([{'id': 'editorA'}]))
        self.assertEqual([row['id'] for row in observation['matched']], ['editorA'])

    def test_one_chain_needs_no_window_record(self):
        # The narrow sheet rule is the only consumer of the direct-parent relation, so a
        # single modal chain keeps resolving even when the window publishes no visible flag.
        tree = _tree(_window_without_visible([
            _record_list(),
            _sheet_chain('A', _MISSING, _MISSING),
        ]))
        observation = native.observe_state(tree, _predicate([{'id': 'editorA'}]))
        self.assertEqual([row['id'] for row in observation['matched']], ['editorA'])


# --------------------------------------------------------------------------- #
# Scope semantics are unchanged: present in the active layer, absent in the window.
# --------------------------------------------------------------------------- #

class ActiveLayerScopeTests(unittest.TestCase):
    def test_present_defaults_to_the_active_layer_only(self):
        # Both sheets hold an identical item; only the active one may satisfy `present`.
        observation = native.observe_state(_scoped_sheets_tree(), _predicate([{'id': 'item'}]))
        self.assertEqual([row['text'] for row in observation['matched']], ['Record'])

    def test_absent_still_covers_the_whole_window(self):
        tree = _sibling_sheets((False, False), (True, True))
        for absent in ({'id': 'recordList'}, {'id': 'editorA'}):
            with self.subTest(absent=absent):
                with self.assertRaises(ValueError):
                    native.observe_state(tree, _predicate([{'id': 'editorB'}], [absent]))

    def test_absent_of_an_absent_selector_still_passes(self):
        tree = _sibling_sheets((False, False), (True, True))
        observation = native.observe_state(
            tree, _predicate([{'id': 'editorB'}], [{'id': 'neverVisible'}]))
        self.assertEqual([row['id'] for row in observation['matched']], ['editorB'])

    def test_within_scope_narrows_to_the_active_layer(self):
        observation = native.observe_state(
            _scoped_sheets_tree(),
            _predicate([{'id': 'item', 'text': 'Record'}], within={'ancestor': {'id': 'rowB'}}))
        self.assertEqual([row['id'] for row in observation['matched']], ['item'])

    def test_within_ancestor_outside_the_active_layer_is_rejected(self):
        # rowA lives only in the covered sheet, so it cannot anchor the active layer.
        with self.assertRaises(ValueError):
            native.observe_state(
                _scoped_sheets_tree(),
                _predicate([{'id': 'item'}], within={'ancestor': {'id': 'rowA'}}))

    def test_within_ancestor_must_stay_unique_inside_the_active_layer(self):
        tree = _scoped_sheets_tree(rows_in_active=2)
        with self.assertRaises(ValueError):
            native.observe_state(tree, _predicate([{'id': 'item'}],
                                                 within={'ancestor': {'id': 'rowB'}}))

    def test_within_descendant_absent_from_the_active_layer_is_rejected(self):
        with self.assertRaises(ValueError):
            native.observe_state(
                _scoped_sheets_tree(),
                _predicate([{'id': 'recordList'}], within={'ancestor': {'id': 'rowB'}}))


# --------------------------------------------------------------------------- #
# The rejection diagnostic stays bounded and free of arbitrary node text.
# --------------------------------------------------------------------------- #

# Four sibling chains already exceed any bounded summary; sixteen must not read longer.
_SHEET_COUNT_CAP = 4
_MARKER = 'private-note-value'


def _many_sheets(count):
    chains = []
    for index in range(count):
        chain = _sheet_chain(chr(ord('A') + index), _MISSING, _MISSING)
        chain['children'][0]['attributes']['text'] = _MARKER
        chains.append(chain)
    return _tree(_window([_record_list(), *chains]))


class RejectionDiagnosticTests(unittest.TestCase):
    def _message(self, tree):
        with self.assertRaises(ValueError) as caught:
            native.observe_state(tree, _predicate([{'id': 'editorA'}]))
        return str(caught.exception)

    def test_rejection_keeps_the_original_prefix(self):
        message = self._message(_sibling_sheets((True, True), (True, True)))
        self.assertTrue(message.startswith(
            'multiple active native modal layers are visible; their order cannot be determined'))

    def test_rejection_summary_stops_at_the_layer_cap(self):
        small = self._message(_many_sheets(_SHEET_COUNT_CAP))
        large = self._message(_many_sheets(_SHEET_COUNT_CAP * 4))
        self.assertEqual(small, large)
        self.assertLess(len(large), 1500)

    def test_rejection_summary_omits_free_form_node_text(self):
        message = self._message(_many_sheets(_SHEET_COUNT_CAP * 4))
        self.assertNotIn(_MARKER, message)
        self.assertNotIn('editorA', message)


if __name__ == '__main__':
    unittest.main()
