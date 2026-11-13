"""Native dump comparison regressions with two distinct viewport coordinate spaces."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.ios_ui_dispatch import sha256
from lib.ios_ui_relationships import compare_relationships


class IOSRelationshipsTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name).resolve()
        self.source = self.root / 'ios.json'
        self.target = self.root / 'harmony.json'
        self.frame = {'comparison_id': 'example:0', 'ios_region_px': None}
        self.tree = """Attributes: Application, 0x123, label: 'Sample'
Element subtree:
    Window (Main), 0x123, {{0.0, 0.0}, {100.0, 200.0}}
      StaticText, 0x124, {{10.0, 10.0}, {50.0, 20.0}}, label: 'Sample'
      Button, 0x125, {{10.0, 40.0}, {50.0, 20.0}}, label: 'Next'
        StaticText, 0x126, {{12.0, 45.0}, {20.0, 10.0}}, label: 'Next'
      StatusBar, 0x127, {{0.0, 0.0}, {100.0, 8.0}}
        StaticText, 0x128, {{3.0, 0.0}, {40.0, 8.0}}, label: 'Clock'
Query chain:
    StaticText, 0x129, {{10.0, 50.0}, {30.0, 8.0}}, label: 'Ignore'
"""

    def compare(self, children):
        self.source.write_text(json.dumps({'debug_description': self.tree}))
        self.target.write_text(json.dumps({'attributes': {'bounds': '[0,0][300,600]'}, 'children': children}))
        pair = {'baseline': {'ui_json_path': self.source.name, 'ui_json_sha256': sha256(self.source.read_bytes())}}
        return compare_relationships(self.root, pair, self.frame, self.target)

    def node(self, role, bounds, label='', children=()):
        return {'attributes': {'type': role, 'bounds': bounds, 'text': label}, 'children': list(children)}

    def test_debug_description_and_button_label_inside_custom_control(self):
        report = self.compare([
            self.node('Text', '[30,30][180,90]', 'Sample'),
            self.node('Button', '[30,120][180,180]', children=[self.node('Text', '[36,135][96,165]', 'Next')]),
        ])
        self.assertEqual(report['verdict'], 'PASS')
        self.assertEqual(report['matched_anchors'], 2)

    def test_new_overlap_and_gap_are_retained(self):
        self.tree = self.tree.replace("StaticText, 0x124", "Button, 0x124")
        report = self.compare([
            self.node('Button', '[30,30][180,90]', 'Sample'),
            self.node('Button', '[30,66][180,126]', 'Next'),
        ])
        self.assertEqual(report['verdict'], 'FAIL')
        self.assertIn('new_overlap', {item['code'] for item in report['findings']})
        self.assertIn('gap_changed', {item['code'] for item in report['findings']})

    def test_stretched_text_preserves_its_leading_alignment(self):
        report = self.compare([
            self.node('Text', '[30,30][270,90]', 'Sample'),
            self.node('Button', '[30,120][180,180]', 'Next'),
        ])
        self.assertEqual(report['verdict'], 'PASS')

    def test_single_anchor_keeps_its_geometry_contract(self):
        self.tree = self.tree.replace("label: 'Sample'", "label: ''")
        report = self.compare([self.node('Button', '[30,120][180,180]', 'Next')])
        self.assertEqual(report['verdict'], 'PASS')
        self.assertEqual(report['matched_anchors'], 1)

    def test_duplicate_buttons_cannot_match_by_position_or_id(self):
        report = self.compare([
            self.node('Text', '[30,30][180,90]', 'Sample'),
            self.node('Button', '[30,120][180,180]', 'Next'),
            self.node('Button', '[30,250][180,310]', 'Next'),
        ])
        self.assertEqual(report['verdict'], 'UNRESOLVED')
        self.assertEqual(report['unresolved'][0]['candidate_count'], 2)


if __name__ == '__main__':
    unittest.main()
