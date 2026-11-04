"""Selected capture/facts policies must work together without weakening S1-V."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from validate_runtime_snapshots import check
from stage1_visual_scope import baseline


class InputPolicies(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.page = {'page_id': 'page_0001_MainActivity', 'state_id': 'normal'}
        self.snap = self.root / 'spec/baseline/ui-snapshots' / self.page['page_id']
        self.snap.mkdir(parents=True)
        (self.snap / 'view.xml').write_text('<hierarchy synthesized="true"/>')
        self.meta = {'view_xml_synthesized': True, 'confidence': 'medium', 'layout_sources': ['res/layout/main.xml']}
        self.save()

    def save(self):
        (self.snap / 'meta.json').write_text(json.dumps(self.meta))

    def test_source_only_without_device_frames_can_migrate_but_cannot_pass_s1v(self):
        result = check(self.root, [self.page], 'source_only')
        self.assertEqual(result['status'], 'pass')
        self.assertFalse(result['source_fallbacks'][0]['runtime_captured'])
        with self.assertRaises(ValueError):
            baseline(self.root, self.page)

    def test_runtime_required_cannot_use_source_only_baseline(self):
        self.assertEqual(check(self.root, [self.page])['status'], 'fail')

    def test_progressive_fallback_requires_failed_capture_evidence(self):
        self.assertEqual(check(self.root, [self.page], 'progressive')['status'], 'fail')
        self.meta['fallback_reason'] = 'device offline; evidence: spec/.i2h/run/events.jsonl#42'
        self.save()
        self.assertEqual(check(self.root, [self.page], 'progressive')['status'], 'pass')

    def test_legacy_and_shadow_do_not_require_static_v1_outputs(self):
        for facts in ('legacy', 'static-v1-shadow'):
            with self.subTest(facts=facts):
                self.assertEqual(check(self.root, [self.page], 'source_only', facts)['status'], 'pass')

    def test_static_v1_requires_canonical_inputs_and_never_uses_shadow(self):
        self.assertEqual(check(self.root, [self.page], 'source_only', 'static-v1')['status'], 'fail')
        for name in ('values', 'drawables', 'usage', 'design-tokens'):
            p = self.root / f'spec/baseline/res-index/{name}.json'
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text('{}')
        target = self.root / 'spec/.i2h/target-input.json'
        target.parent.mkdir(parents=True)
        target.write_text('{}')
        self.assertEqual(check(self.root, [self.page], 'source_only', 'static-v1')['status'], 'pass')

    def test_source_only_does_not_accept_real_xml_as_unverified_runtime_capture(self):
        (self.snap / 'view.xml').write_text('<hierarchy/>')
        self.meta['view_xml_synthesized'] = False
        self.save()
        self.assertEqual(check(self.root, [self.page], 'source_only')['status'], 'fail')
