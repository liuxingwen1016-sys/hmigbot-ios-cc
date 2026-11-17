"""Test SOURCE_ONLY G1 archive with structural status."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.ui_delivery_inputs_ios import freeze
from lib.ios_ui_dispatch import prepare, complete, aggregate_g0, json_bytes, sha256
from lib.ios_stage1_acceptance import archive_g1


class SourceOnlyG1Tests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.source_root = self.root / 'ios'
        self.source_root.mkdir()

        self.source_content = b'struct TestView { var body: some View { Text("Test") } }\n'
        self.source_file = self.source_root / 'TestView.swift'
        self.source_file.write_bytes(self.source_content)
        self.source_sha = sha256(self.source_content)

    def test_source_only_g1_structural_archive(self):
        """Test that SOURCE_ONLY G0 can create structural G1 archive."""
        output = {'file': 'entry/src/main/ets/TestView.ets', 'symbol': 'TestView', 'builder': 'build'}
        unit = {
            'unit_id': 'ios.0001.G1Test',
            'page_id': 'page_0001_G1',
            'component': 'TestView',
            'output': output,
            'source_refs': [{'file': 'TestView.swift', 'line': 1, 'sha256': self.source_sha}],
            'required_states': [
                {'state_id': 'default'}
            ],
            'input_alternatives': [
                {
                    'state_id': 'default',
                    'alternative_kind': 'source_only',
                    'source_file': 'TestView.swift',
                    'source_sha256': self.source_sha,
                    'source_line': 1,
                    'declaration': 'TestView'
                }
            ]
        }

        inventory = {
            'schema_version': 2,
            'status': 'approved',
            'source_project_root': str(self.source_root),
            'units': [unit]
        }

        approved_path = self.root / 'spec' / 'baseline' / 'ui-delivery-approved.json'
        approved_path.parent.mkdir(parents=True, exist_ok=True)
        approved_path.write_bytes(json_bytes(inventory))

        output_file = self.root / output['file']
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_bytes(b'@ComponentV2\nexport struct TestView { build() { Text("Test") } }')

        # Freeze, prepare, complete SOURCE_ONLY
        freeze(['--project-root', str(self.root), '--inventory', 'spec/baseline/ui-delivery-approved.json'])
        prepared = prepare(self.root, 'ios.0001.G1Test', 1)

        packet_data = json.loads((self.root / prepared['packet_path']).read_bytes())
        report_path = self.root / 'spec/execution/conversion-reports/ios.0001.G1Test.json'
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report = {
            'unit_id': 'ios.0001.G1Test',
            'dispatch_id': prepared['dispatch_id'],
            'packet_sha256': prepared['packet_sha256'],
            'state_implementations': [{'state_id': 'default', 'symbol': 'build'}],
            'image_observations': [],
            'input_applications': [{'input_id': i['input_id']} for i in packet_data['required_inputs']],
        }
        report_path.write_bytes(json_bytes(report))

        completed = complete(self.root, prepared['dispatch_id'])
        self.assertEqual(completed['status'], 'SOURCE_ONLY')

        # Archive G1 - should succeed with SOURCE_ONLY G0
        g1_result = archive_g1(self.root)

        # G1 should accept SOURCE_ONLY and create archive
        self.assertIn('archive_path', g1_result)
        self.assertIsNotNone(g1_result['archive_path'])
        self.assertEqual(g1_result['status'], 'PASS')  # Structural PASS
        self.assertFalse(g1_result['stage1_complete'])  # But not visual complete
        self.assertFalse(g1_result['visual_verified'])

        # Verify G1 archive exists
        g1_archive = self.root / g1_result['archive_path']
        self.assertTrue(g1_archive.is_dir())
        self.assertTrue((g1_archive / 'receipt.json').is_file())


if __name__ == '__main__':
    unittest.main()
