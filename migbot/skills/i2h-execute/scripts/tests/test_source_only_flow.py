"""Comprehensive tests for SOURCE_ONLY flow with explicit typed input_alternatives."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.ui_delivery_inputs_ios import freeze
from lib.ios_ui_dispatch import prepare, complete, aggregate_g0, check_required_inputs, json_bytes, sha256
from lib.ios_stage1_acceptance import archive_g1


class SourceOnlyFlowTests(unittest.TestCase):
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

    def test_explicit_typed_alternative_creates_source_only(self):
        """Test that explicit typed input_alternatives creates SOURCE_ONLY flow."""
        output = {'file': 'entry/src/main/ets/TestView.ets', 'symbol': 'TestView', 'builder': 'build'}
        unit = {
            'unit_id': 'ios.0001.Test',
            'page_id': 'page_0001_Test',
            'component': 'TestView',
            'output': output,
            'source_refs': [{'file': 'TestView.swift', 'line': 1, 'sha256': self.source_sha, 'symbol': 'TestView'}],
            'required_states': [
                {'state_id': 'default', 'source_refs': [{'file': 'TestView.swift', 'line': 1, 'sha256': self.source_sha}]}
            ],
            # EXPLICIT typed input_alternatives required
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

        # Freeze should create source_alternatives from explicit input_alternatives
        freeze(['--project-root', str(self.root), '--inventory', 'spec/baseline/ui-delivery-approved.json'])

        index = json.loads((self.root / 'spec' / 'execution' / 'ui-inputs' / 'index.json').read_text())
        packet = index['packets'][0]

        self.assertIn('source_alternatives', packet)
        self.assertEqual(len(packet['source_alternatives']), 1)
        self.assertEqual(packet['source_alternatives'][0]['state_id'], 'default')
        self.assertEqual(packet['source_alternatives'][0]['declaration'], 'TestView')

        # New read-only checks retain typed source-only approval without creating dispatch state.
        checked = prepare(self.root, unit['unit_id'], 1, check_only=True)
        self.assertEqual(checked['status'], 'SOURCE_ONLY')
        self.assertTrue(any(row['kind'] == 'ios_source_proof' for row in checked['checked_inputs']))
        batch = check_required_inputs(self.root)
        self.assertEqual(batch['status'], 'SOURCE_ONLY')
        self.assertEqual(batch['source_only_units'], 1)
        self.assertEqual(batch['blocked_units'], 0)
        self.assertEqual(batch['visual_status'], 'BLOCKED')
        self.assertFalse((self.root / 'spec/execution/dispatch').exists())

        # Prepare adds source proof
        prepared = prepare(self.root, 'ios.0001.Test', 1)
        packet_data = json.loads((self.root / prepared['packet_path']).read_bytes())
        source_proof = [i for i in packet_data['required_inputs'] if i['kind'] == 'ios_source_proof']
        self.assertGreater(len(source_proof), 0)

        # Complete creates SOURCE_ONLY archive
        report_path = self.root / 'spec/execution/conversion-reports/ios.0001.Test.json'
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report = {
            'unit_id': 'ios.0001.Test',
            'dispatch_id': prepared['dispatch_id'],
            'packet_sha256': prepared['packet_sha256'],
            'state_implementations': [{'state_id': 'default', 'symbol': 'build'}],
            'image_observations': [],
            'input_applications': [{'input_id': i['input_id']} for i in packet_data['required_inputs']],
        }
        report_path.write_bytes(json_bytes(report))

        completed = complete(self.root, prepared['dispatch_id'])
        self.assertEqual(completed['status'], 'SOURCE_ONLY')

        # Aggregate recognizes SOURCE_ONLY with structural_status PASS
        aggregate = aggregate_g0(self.root)
        self.assertEqual(aggregate['status'], 'BLOCKED')  # Visual blocked
        self.assertEqual(aggregate['structural_status'], 'PASS')  # But structural complete
        self.assertFalse(aggregate['stage1_complete'])

    def test_missing_declaration_rejects_alternative(self):
        """Test that missing declaration in typed alternative rejects it."""
        output = {'file': 'entry/src/main/ets/TestView.ets', 'symbol': 'TestView', 'builder': 'build'}
        unit = {
            'unit_id': 'ios.0002.Test',
            'page_id': 'page_0002_Test',
            'component': 'TestView',
            'output': output,
            'source_refs': [{'file': 'TestView.swift', 'line': 1, 'sha256': self.source_sha}],
            'required_states': [{'state_id': 'default'}],
            'input_alternatives': [
                {
                    'state_id': 'default',
                    'alternative_kind': 'source_only',
                    'source_file': 'TestView.swift',
                    'source_sha256': self.source_sha,
                    'source_line': 1,
                    # Missing 'declaration'
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

        freeze(['--project-root', str(self.root), '--inventory', 'spec/baseline/ui-delivery-approved.json'])

        index = json.loads((self.root / 'spec' / 'execution' / 'ui-inputs' / 'index.json').read_text())
        packet = index['packets'][0]

        # Should NOT create source_alternatives
        self.assertNotIn('source_alternatives', packet)

    def test_wrong_sha_rejects_alternative(self):
        """Test that wrong SHA in typed alternative rejects it."""
        output = {'file': 'entry/src/main/ets/TestView.ets', 'symbol': 'TestView', 'builder': 'build'}
        unit = {
            'unit_id': 'ios.0003.Test',
            'page_id': 'page_0003_Test',
            'component': 'TestView',
            'output': output,
            'source_refs': [{'file': 'TestView.swift', 'line': 1, 'sha256': self.source_sha}],
            'required_states': [{'state_id': 'default'}],
            'input_alternatives': [
                {
                    'state_id': 'default',
                    'alternative_kind': 'source_only',
                    'source_file': 'TestView.swift',
                    'source_sha256': 'wrong_hash_123',  # Wrong SHA
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

        freeze(['--project-root', str(self.root), '--inventory', 'spec/baseline/ui-delivery-approved.json'])

        index = json.loads((self.root / 'spec' / 'execution' / 'ui-inputs' / 'index.json').read_text())
        packet = index['packets'][0]

        # Should NOT create source_alternatives
        self.assertNotIn('source_alternatives', packet)

    def test_mixed_runtime_and_source_only_states(self):
        """Test that some states can use runtime while others use source_only."""
        # Create runtime evidence for one state
        snap_dir = self.root / 'spec' / 'baseline' / 'ui-snapshots' / 'page_0004_Test'
        snap_dir.mkdir(parents=True, exist_ok=True)

        png_content = b'fake PNG'
        png_file = snap_dir / 'default.png'
        png_file.write_bytes(png_content)

        ax_content = b'{"nodes": []}'
        ax_file = snap_dir / 'default.json'
        ax_file.write_bytes(ax_content)

        meta = {
            'runtime_evidence_by_state': {
                'default': {
                    'status': 'audited',
                    'source_platform': 'ios',
                    'page_id': 'page_0004_Test',
                    'state_id': 'default',
                    'png_path': 'default.png',
                    'png_sha256': sha256(png_content),
                    'ui_json_path': 'default.json',
                    'ui_json_sha256': sha256(ax_content)
                }
            }
        }
        (snap_dir / 'meta.json').write_bytes(json_bytes(meta))

        output = {'file': 'entry/src/main/ets/TestView.ets', 'symbol': 'TestView', 'builder': 'build'}
        unit = {
            'unit_id': 'ios.0004.Test',
            'page_id': 'page_0004_Test',
            'component': 'TestView',
            'output': output,
            'source_refs': [{'file': 'TestView.swift', 'line': 1, 'sha256': self.source_sha}],
            'required_states': [
                {'state_id': 'default'},  # Has runtime
                {'state_id': 'loading'}   # Will use source_only
            ],
            'input_alternatives': [
                {
                    'state_id': 'loading',
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

        freeze(['--project-root', str(self.root), '--inventory', 'spec/baseline/ui-delivery-approved.json'])
        prepared = prepare(self.root, 'ios.0004.Test', 1)

        packet_data = json.loads((self.root / prepared['packet_path']).read_bytes())

        # Should have both screenshot_png (for default) and ios_source_proof (for loading)
        screenshot = [i for i in packet_data['required_inputs'] if i['kind'] == 'screenshot_png']
        source_proof = [i for i in packet_data['required_inputs'] if i['kind'] == 'ios_source_proof']

        self.assertGreater(len(screenshot), 0)
        self.assertGreater(len(source_proof), 0)

        # Create report with image observation for default state
        report_path = self.root / 'spec/execution/conversion-reports/ios.0004.Test.json'
        report_path.parent.mkdir(parents=True, exist_ok=True)

        report = {
            'unit_id': 'ios.0004.Test',
            'dispatch_id': prepared['dispatch_id'],
            'packet_sha256': prepared['packet_sha256'],
            'state_implementations': [
                {'state_id': 'default', 'symbol': 'build'},
                {'state_id': 'loading', 'symbol': 'build'}
            ],
            'image_observations': [
                {'state_id': 'default', 'comparison_id': screenshot[0]['comparison_id']}
            ],
            'input_applications': [{'input_id': i['input_id']} for i in packet_data['required_inputs']],
        }
        report_path.write_bytes(json_bytes(report))

        completed = complete(self.root, prepared['dispatch_id'])

        # Should be SOURCE_ONLY (because loading state uses source_only)
        self.assertEqual(completed['status'], 'SOURCE_ONLY')

    def test_duplicate_source_refs_across_states(self):
        """Test that duplicate source_refs across states are deduplicated without mutation."""
        output = {'file': 'entry/src/main/ets/TestView.ets', 'symbol': 'TestView', 'builder': 'build'}

        same_ref = {'file': 'TestView.swift', 'line': 1, 'sha256': self.source_sha}

        unit = {
            'unit_id': 'ios.0005.Test',
            'page_id': 'page_0005_Test',
            'component': 'TestView',
            'output': output,
            'source_refs': [same_ref],  # Same ref in unit
            'required_states': [
                {'state_id': 'default', 'source_refs': [same_ref]},  # And in state
                {'state_id': 'loading', 'source_refs': [same_ref]}   # And in another state
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
        original_inventory_bytes = json_bytes(inventory)
        approved_path.write_bytes(original_inventory_bytes)

        output_file = self.root / output['file']
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_bytes(b'@ComponentV2\nexport struct TestView { build() { Text("Test") } }')

        freeze(['--project-root', str(self.root), '--inventory', 'spec/baseline/ui-delivery-approved.json'])

        # Verify original inventory bytes unchanged
        current_inventory_bytes = approved_path.read_bytes()
        self.assertEqual(original_inventory_bytes, current_inventory_bytes,
            "Inventory bytes should not be mutated by freeze")

        index = json.loads((self.root / 'spec' / 'execution' / 'ui-inputs' / 'index.json').read_text())
        packet = index['packets'][0]

        # Should still create source_alternatives (dedup works correctly)
        self.assertIn('source_alternatives', packet)


if __name__ == '__main__':
    unittest.main()
