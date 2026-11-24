import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import native_scenario_evidence as evidence


BUNDLE = 'com.example.test'
ROUTE = 'pages/Root'
WINDOW = 'window-main'


def _tree(*nodes, focused=True):
    return {'children': [{
        'attributes': {
            'focused': focused, 'bundleName': BUNDLE, 'pagePath': ROUTE,
            'hostWindowId': WINDOW,
        },
        'children': list(nodes),
    }]}


def _node(node_type, *, ident=None, visible='true', children=(), **attributes):
    value = {'type': node_type, 'visible': visible}
    if ident is not None:
        value['id'] = ident
    value.update(attributes)
    return {'attributes': value, 'children': list(children)}


def _predicate(present, absent=()):
    return {'bundle': BUNDLE, 'page_path': ROUTE,
            'present': list(present), 'absent': list(absent)}


class NativeScenarioEvidenceTests(unittest.TestCase):
    def test_bool_and_string_attributes_observe_the_same_control(self):
        for checked in (True, 'true'):
            for visible in (True, 'true'):
                tree = _tree(_node('ListItem', ident='recordList', visible=visible, checked=checked))
                observed = evidence.observe_state(
                    tree, _predicate([{'id': 'recordList', 'checked': 'true'}]))
                self.assertEqual([row['id'] for row in observed['matched']], ['recordList'])

    def test_integer_one_and_zero_are_not_booleans(self):
        tree = _tree(_node('List', ident='recordList'), focused=1)
        with self.assertRaises(ValueError):
            evidence.observe_state(tree, _predicate([{'id': 'recordList'}]))
        tree = _tree(_node('List', ident='recordList', visible=0))
        with self.assertRaises(ValueError):
            evidence.observe_state(tree, _predicate([{'id': 'recordList'}]))
        tree = _tree(_node('List', ident='recordList', checked=1))
        with self.assertRaises(ValueError):
            evidence.observe_state(tree, _predicate([{'id': 'recordList', 'checked': 'true'}]))
        with self.assertRaises(ValueError):
            evidence.observe_state(tree, _predicate([{'id': 'recordList', 'checked': '1'}]))

    def test_controls_under_other_bundle_window_or_extension_do_not_match(self):
        control = _node('ListItem', ident='recordList')
        subtrees = (
            _node('Container', bundleName='com.other.app', children=[control]),
            _node('Container', hostWindowId='window-other', children=[control]),
            _node('UIExtensionComponent', children=[control]),
        )
        for subtree in subtrees:
            with self.assertRaises(ValueError):
                evidence.observe_state(_tree(subtree), _predicate([{'id': 'recordList'}]))

    def test_same_root_route_with_wrong_state_is_rejected(self):
        tree = _tree(_node('ListItem', ident='recordList', checked='false'))
        with self.assertRaises(ValueError):
            evidence.observe_state(tree, _predicate([{'id': 'recordList', 'checked': 'true'}]))
        with self.assertRaises(ValueError):
            evidence.observe_state(tree, _predicate([{'id': 'emptyState'}]))


if __name__ == '__main__':
    unittest.main(verbosity=2)
