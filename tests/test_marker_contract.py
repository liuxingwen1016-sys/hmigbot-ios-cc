from __future__ import annotations
import json
import tempfile
import unittest
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'migbot/bin/scripts/pipeline'))
import marker_contract as mc

class MarkerContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.input_file = self.root / 'spec/input.json'
        self.input_file.parent.mkdir(parents=True)
        self.input_file.write_text('{"target":1}\n', encoding='utf-8')
        self.input_hash = mc.file_sha256(self.input_file)
    def tearDown(self):
        self.tmp.cleanup()
    def test_write_and_validate_schema_two_marker(self):
        marker = self.root / 'spec/baseline/spec-complete.txt'
        payload = mc.write_marker(marker, 'i2h-spec', [self.input_file], self.input_hash, root=self.root)
        self.assertEqual(payload['schema_version'], 2)
        self.assertTrue(mc.validate_marker(marker, 'i2h-spec', self.input_hash, root=self.root)['valid'])
        self.assertFalse(mc.validate_marker(marker, 'i2h-plan', self.input_hash)['valid'])
    def test_content_mutation_blocks(self):
        marker = self.root / 'spec/baseline/spec-complete.txt'
        mc.write_marker(marker, 'i2h-spec', [self.input_file], self.input_hash, root=self.root)
        self.input_file.write_text('{"target":2}\n', encoding='utf-8')
        result = mc.validate_marker(marker, 'i2h-spec', self.input_hash, root=self.root)
        self.assertIn('artifact_hash_mismatch', result['errors'])
    def test_canonical_path_wins_over_legacy_alias(self):
        canonical = self.root / 'spec/baseline/spec-complete.txt'
        canonical.parent.mkdir(parents=True)
        canonical.write_text('canonical', encoding='utf-8')
        legacy = self.root / 'spec/spec-complete.txt'
        legacy.parent.mkdir(parents=True, exist_ok=True)
        legacy.write_text('legacy', encoding='utf-8')
        result = mc.resolve_stage(self.root, 'i2h-spec')
        self.assertFalse(result.legacy)
        self.assertEqual(result.paths, (canonical.resolve(),))

    def test_incomplete_canonical_group_blocks_complete_legacy_group(self):
        canonical = self.root / 'spec/execution/stage5-complete.txt'
        canonical.parent.mkdir(parents=True)
        canonical.write_text('canonical marker', encoding='utf-8')
        legacy_marker = self.root / 'spec/execute/stage5-complete.txt'
        legacy_report = self.root / 'spec/execute/migration-report.md'
        legacy_marker.parent.mkdir(parents=True, exist_ok=True)
        legacy_marker.write_text('legacy marker', encoding='utf-8')
        legacy_report.write_text('legacy report', encoding='utf-8')
        result = mc.resolve_stage(self.root, 'i2h-execute')
        self.assertFalse(result.legacy)
        self.assertEqual(result.paths, (canonical.resolve(),))
        self.assertEqual(result.missing, ('spec/migration-report.md',))
    def test_legacy_text_marker_is_warning(self):
        marker = self.root / 'spec/spec-complete.txt'
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text('i2h-spec completed', encoding='utf-8')
        result = mc.stage_status(self.root, 'i2h-spec')
        self.assertFalse(result['valid'])
        self.assertTrue(result['legacy'])
        self.assertIn('legacy_marker_unhashed', result['warnings'])

    def test_schema_two_legacy_path_is_compatible_unless_strict(self):
        marker = self.root / 'spec/spec-complete.txt'
        marker.parent.mkdir(parents=True, exist_ok=True)
        mc.write_marker(marker, 'i2h-spec', [self.input_file], self.input_hash, root=self.root)
        compatible = mc.stage_status(self.root, 'i2h-spec', self.input_hash, allow_legacy=True)
        self.assertTrue(compatible['valid'])
        self.assertTrue(compatible['legacy'])
        self.assertIn('legacy_marker_path', compatible['warnings'])
        strict = mc.stage_status(self.root, 'i2h-spec', self.input_hash, allow_legacy=False)
        self.assertFalse(strict['valid'])
        self.assertIn('legacy_marker_path_disallowed', strict['errors'])

    def test_schema_one_marker_is_readable_but_not_valid(self):
        marker = self.root / 'spec/baseline/spec-complete.txt'
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(json.dumps({
            'schema_version': 1,
            'stage': 'i2h-spec',
            'status': 'PASS',
            'inputs_sha256': self.input_hash,
        }), encoding='utf-8')
        result = mc.validate_marker(marker, 'i2h-spec', self.input_hash, root=self.root)
        self.assertFalse(result['valid'])
        self.assertTrue(result['legacy'])
        self.assertIn('legacy_marker_schema', result['warnings'])
    def test_bad_input_hash_blocks(self):
        marker = self.root / 'spec/baseline/spec-complete.txt'
        mc.write_marker(marker, 'i2h-spec', [self.input_file], 'deadbeef', root=self.root)
        result = mc.validate_marker(marker, 'i2h-spec', self.input_hash, root=self.root)
        self.assertIn('marker_hash_mismatch', result['errors'])

    def test_artifact_outside_root_is_rejected(self):
        marker = self.root / 'spec/baseline/spec-complete.txt'
        payload = mc.write_marker(marker, 'i2h-spec', [self.input_file], self.input_hash, root=self.root)
        payload['artifacts'][0]['path'] = '../outside.json'
        payload['content_sha256'] = mc.canonical_hash(payload['artifacts'])
        marker.write_text(json.dumps(payload), encoding='utf-8')
        result = mc.validate_marker(marker, 'i2h-spec', self.input_hash, root=self.root)
        self.assertIn('artifact_outside_root', result['errors'])

if __name__ == '__main__':
    unittest.main()
