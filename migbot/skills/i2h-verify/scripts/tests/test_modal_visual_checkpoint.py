"""Foreground/modal capture boundaries; no device, recorder or behavior bindings."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from uitest_action import ForegroundError, focused_page_matches, native, observed_window, require_focused_app
from uitest_checkpoint import capture_checkpoint, CheckpointTimeout, write_visual_arrival


def tree(focus=True):
    return {'attributes': {'pagePath': 'envelope-is-not-route'}, 'children': [
        {'attributes': {'focused': focus, 'bundleName': 'app', 'pagePath': 'pages/Root'}, 'children': [
            {'attributes': {'visible': True, 'type': 'Text', 'id': 'base'}, 'children': []},
            {'attributes': {'visible': True, 'type': 'SheetPage'}, 'children': [
                {'attributes': {'visible': True, 'type': 'Text', 'id': 'editor'}, 'children': []}]}]}]}


class ModalCheckpointTests(unittest.TestCase):
    def test_window_boolean_forms_are_equal_and_envelope_is_not_an_observed_page(self):
        for focus in [True, 'true']:
            value = tree(focus)
            require_focused_app(value, 'app')
            self.assertEqual(observed_window(value), {'bundle': 'app', 'page_path': 'pages/Root'})
            self.assertTrue(focused_page_matches(value, 'app', 'pages/Root'))
            self.assertFalse(focused_page_matches(value, 'app', 'envelope-is-not-route'))

    def test_duplicate_focus_and_malformed_flags_are_rejected_consistently(self):
        for other in [tree()['children'][0], {'attributes': {'focused': ''}},
                      {'attributes': {'focused': True, 'bundleName': 'system.permission', 'pagePath': 'dialog'}}]:
            value = tree();value['children'].append(other)
            with self.assertRaises(ValueError): native.focused_window(value, 'app')
            with self.assertRaises(ForegroundError): require_focused_app(value, 'app')
            with self.assertRaises(ForegroundError): observed_window(value)
            self.assertFalse(focused_page_matches(value, 'app', 'pages/Root'))

    def test_background_only_predicate_does_not_write_formal_arrival(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary);value=tree();layout=root/'layout.json';layout.write_text(json.dumps(value))
            for name, data in [('shot.jpeg', b'\xff\xd8\xffsynthetic'), ('build.json', b'{}'), ('install.json', b'{}')]:
                (root/name).write_bytes(data)
            pair={'pair_id':'sheet','page_id':'semantic-editor','state_id':'editing','arrival_mode':'formal',
                  'target_observation':{'bundle':'app','page_path':'pages/Root','present':[{'id':'base'}],'absent':[]},
                  'comparisons':[{'comparison_id':'sheet:0'}]}
            with self.assertRaisesRegex(ValueError, 'does not satisfy'):
                write_visual_arrival(root,root/'arrival.json',pair=pair,capture_run_id='r',device_id='d',
                    screenshot=root/'shot.jpeg',layout=layout,matched_tree=value,pre_capture_tree=value,
                    build_receipt=root/'build.json',install_receipt=root/'install.json')
            self.assertFalse((root/'arrival.json').exists())

    def test_modal_state_must_remain_after_screenshot_before_receipt_callback(self):
        before=tree();after=tree();after['children'][0]['children'][1]['children'][0]['attributes']['id']='other'
        predicate={'bundle':'app','page_path':'pages/Root','present':[{'id':'editor'}],'absent':[]}
        def ready(t):
            try:native.observe_state(t,predicate);return True
            except ValueError:return False
        callback=Mock();image=Mock()
        with self.assertRaises(CheckpointTimeout):
            capture_checkpoint('editor',bundle='app',read_layout=Mock(side_effect=[before,after]),
                is_ready=ready,capture_image=image,approved_images={'editor'},record_arrival=callback)
        image.assert_called_once();callback.assert_not_called()

    def test_strict_capture_rejects_modal_appearing_after_image_on_same_route(self):
        before=tree();before['children'][0]['children'].pop()
        after=tree()
        pred={'bundle':'app','page_path':'pages/Root','present':[{'id':'base'}],'absent':[]}
        image=Mock();callback=Mock()
        with self.assertRaises(CheckpointTimeout):
            capture_checkpoint('base',bundle='app',read_layout=Mock(side_effect=[before,after]),
                is_ready=lambda t:True,capture_image=image,approved_images={'base'},
                record_arrival=callback,target_observation=pred)
        image.assert_called_once();callback.assert_not_called()

    def test_strict_capture_rejects_modal_disappearing_even_if_id_survives_underneath(self):
        before=tree();after=tree();after['children'][0]['children'].pop()
        after['children'][0]['children'][0]['attributes']['id']='editor'
        pred={'bundle':'app','page_path':'pages/Root','present':[{'id':'editor'}],'absent':[]}
        image=Mock();callback=Mock()
        with self.assertRaises(CheckpointTimeout):
            capture_checkpoint('editor',bundle='app',read_layout=Mock(side_effect=[before,after]),
                is_ready=lambda t:True,capture_image=image,approved_images={'editor'},
                record_arrival=callback,target_observation=pred)
        image.assert_called_once();callback.assert_not_called()

    def test_strict_capture_checks_approved_predicate_before_taking_image(self):
        before=tree();before['children'][0]['children'].pop()
        pred={'bundle':'app','page_path':'pages/Root','present':[{'id':'editor'}],'absent':[]}
        image=Mock();callback=Mock()
        with self.assertRaises(CheckpointTimeout):
            capture_checkpoint('editor',bundle='app',read_layout=lambda n:before,
                is_ready=lambda t:True,capture_image=image,approved_images={'editor'},
                record_arrival=callback,target_observation=pred,timeout=.02,interval=.005)
        image.assert_not_called();callback.assert_not_called()

    def test_strict_capture_passes_pre_image_tree_to_writer(self):
        value=tree();pred={'bundle':'app','page_path':'pages/Root','present':[{'id':'editor'}],'absent':[]}
        image=Mock();callback=Mock()
        result=capture_checkpoint('editor',bundle='app',read_layout=lambda n:value,
            is_ready=lambda t:True,capture_image=image,approved_images={'editor'},
            record_arrival=callback,target_observation=pred)
        callback.assert_called_once_with('editor',value,pre_capture_tree=value)
        self.assertEqual(result,value)


if __name__ == '__main__': unittest.main()
