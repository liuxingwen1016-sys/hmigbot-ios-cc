import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stage1_visual_acceptance import accept, report
from stage1_visual_scope import baseline
from stage1_contract import digest


class VisualAcceptanceTests(unittest.TestCase):
    def make_evidence(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        snap = root / 'spec/baseline/ui-snapshots/page_0001_Home'
        snap.mkdir(parents=True)
        png = snap / 'runtime.png'
        ui = snap / 'accessibility.json'
        png.write_bytes(b'PNG fixture')
        ui.write_text(json.dumps({'nodes': [
            {'id': 'title', 'role': 'staticText', 'label': 'Home', 'frame': [0, 20, 100, 40]},
            {'id': 'save', 'role': 'button', 'label': 'Save', 'frame': [0, 70, 100, 44]},
        ]}))
        meta = {
            'runtime_evidence': {
                'status': 'audited',
                'state': 'normal',
                'platform': 'ios',
                'png_path': 'runtime.png',
                'png_sha256': hashlib.sha256(png.read_bytes()).hexdigest(),
                'ui_json_path': 'accessibility.json',
                'ui_json_sha256': hashlib.sha256(ui.read_bytes()).hexdigest(),
                'app': {'bundle_id': 'com.example.app'},
            }
        }
        (snap / 'meta.json').write_text(json.dumps(meta))
        return root

    def test_ios_scope_accepts_png_and_accessibility_json(self):
        root = self.make_evidence()
        result = baseline(root, {'page_id': 'page_0001_Home', 'state_id': 'normal'})
        self.assertEqual(result['evidence_kind'], 'ios-accessibility-json')
        self.assertEqual(result['ui_json_sha256'], 'sha256:' + hashlib.sha256((root / result['ui_json_path']).read_bytes()).hexdigest())

    def test_ios_app_identity_mismatch_is_explicit(self):
        root = self.make_evidence()
        with self.assertRaisesRegex(ValueError, 'app identity mismatch'):
            baseline(root, {'page_id': 'page_0001_Home', 'state_id': 'normal', 'app_identity': 'com.example.other'})

    def test_missing_png_and_hash_are_blocked(self):
        root = self.make_evidence()
        (root / 'spec/baseline/ui-snapshots/page_0001_Home/runtime.png').unlink()
        with self.assertRaisesRegex(ValueError, 'baseline PNG is missing'):
            baseline(root, {'page_id': 'page_0001_Home', 'state_id': 'normal'})
        root = self.make_evidence()
        meta_path = root / 'spec/baseline/ui-snapshots/page_0001_Home/meta.json'
        meta = json.loads(meta_path.read_text())
        meta['runtime_evidence']['ui_json_sha256'] = 'bad'
        meta_path.write_text(json.dumps(meta))
        with self.assertRaisesRegex(ValueError, 'baseline accessibility JSON hash mismatch'):
            baseline(root, {'page_id': 'page_0001_Home', 'state_id': 'normal'})

    def test_legacy_android_view_xml_is_accepted(self):
        root = self.make_evidence()
        snap = root / 'spec/baseline/ui-snapshots/page_0001_Home'
        xml = snap / 'view.xml'
        xml.write_text('<hierarchy/>')
        meta = {'runtime_evidence': {
            'status': 'audited', 'state': 'normal', 'png_path': 'runtime.png',
            'png_sha256': hashlib.sha256((snap / 'runtime.png').read_bytes()).hexdigest(),
            'view_xml_path': 'view.xml', 'view_xml_sha256': hashlib.sha256(xml.read_bytes()).hexdigest(),
        }}
        (snap / 'meta.json').write_text(json.dumps(meta))
        self.assertEqual(baseline(root, {'page_id': 'page_0001_Home', 'state_id': 'normal'})['evidence_kind'], 'android-view-xml')

    def test_semantic_pass_and_geometry_tolerance(self):
        source = {
            'page_id': 'page_0001_Home', 'state_id': 'normal',
            'safe_area': {'top': 20, 'right': 0, 'bottom': 34, 'left': 0},
            'required_components': ['save'],
            'color_tokens': ['text.primary'],
            'font_tokens': ['body'],
            'actions': [{'id': 'save'}],
            'navigation_paths': [{'path': 'home->detail'}],
            'nodes': [
                {'id': 'title', 'role': 'staticText', 'label': 'Home', 'frame': [0, 20, 100, 40]},
                {'id': 'save', 'role': 'button', 'label': 'Save', 'frame': [0, 70, 100, 44]},
            ],
        }
        target = {
            'page_id': 'page_0001_Home', 'state_id': 'normal',
            'safe_area': {'top': 21, 'right': 0, 'bottom': 34, 'left': 0},
            'color_tokens': ['text.primary'],
            'font_tokens': ['body'],
            'actions': [{'id': 'save'}],
            'navigation_paths': [{'path': 'home->detail'}],
            'nodes': [
                {'id': 'title', 'role': 'staticText', 'label': 'Home', 'frame': [1, 20, 100, 40]},
                {'id': 'save', 'role': 'button', 'label': 'Save', 'frame': [0, 71, 100, 44]},
            ],
        }
        result = accept(source, target, geometry_tolerance=2)
        self.assertEqual(result['status'], 'PASS')
        self.assertLessEqual(result['geometry']['max_error'], 2)

    def test_missing_component_and_geometry_fail(self):
        source = {'page_id': 'p', 'state_id': 's', 'required_components': ['save'],
                  'nodes': [{'id': 'save', 'role': 'button', 'label': 'Save', 'frame': [0, 0, 10, 10]}]}
        target = {'page_id': 'p', 'state_id': 's',
                  'nodes': [{'id': 'save', 'role': 'button', 'label': 'Save', 'frame': [20, 0, 10, 10]}]}
        result = accept(source, target, geometry_tolerance=2)
        self.assertEqual(result['status'], 'FAIL')
        self.assertTrue(result['semantic']['missing_components'] == [])
        self.assertFalse(result['geometry']['within_tolerance'])

    def test_state_mismatch_is_blocked(self):
        source = {'page_id': 'p', 'state_id': 'normal', 'nodes': [{'id': 'x', 'role': 'text', 'label': 'x'}]}
        target = {'page_id': 'p', 'state_id': 'loading', 'nodes': [{'id': 'x', 'role': 'text', 'label': 'x'}]}
        result = accept(source, target)
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertEqual(result['failure_findings'][0]['code'], 'PAGE_STATE_MISMATCH')

    def test_report_contains_page_state_and_blocked_reason(self):
        result = report([{'source': {'page_id': 'p', 'state_id': 's', 'nodes': []}, 'target': {}}])
        self.assertEqual(result['page_count'], 1)
        self.assertEqual(result['state_count'], 1)
        self.assertTrue(result['visual_blocked_reasons'])

    def test_report_requires_target_page_state_binding(self):
        result = report([{
            'page_id': 'p', 'state_id': 's',
            'source': {'page_id': 'p', 'state_id': 's', 'nodes': []},
            'target': {'nodes': [{'id': 'home', 'role': 'text', 'label': 'Home'}]},
        }])
        self.assertEqual(result['status'], 'visual_blocked')
        self.assertEqual(result['results'][0]['failure_findings'][0]['code'], 'TARGET_PAGE_STATE_UNBOUND')

    def test_report_rejects_duplicate_target_evidence_for_different_pages(self):
        target = {
            'page_id': 'p1', 'state_id': 'normal',
            'nodes': [{'id': 'title', 'role': 'text', 'label': 'Same', 'frame': [0, 0, 10, 10]}],
        }
        result = report([
            {'source': {'page_id': 'p1', 'state_id': 'normal', 'nodes': target['nodes']}, 'target': target},
            {'source': {'page_id': 'p2', 'state_id': 'normal', 'nodes': target['nodes']},
             'target': {**target, 'page_id': 'p2'}},
        ])
        self.assertEqual(result['status'], 'visual_blocked')
        self.assertEqual(result['results'][1]['failure_findings'][-1]['code'], 'DUPLICATE_TARGET_EVIDENCE')


if __name__ == '__main__':
    unittest.main()
