"""Tests demonstrating the 4 defects in Phase A implementation before fixes."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.ui_delivery_inputs_ios import freeze
from lib.ios_ui_dispatch import prepare, complete, aggregate_g0, json_bytes, sha256


class SourceOnlyDefectTests(unittest.TestCase):
    """These tests SHOULD FAIL with current implementation, demonstrating the defects."""

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

    def test_defect1_source_refs_alone_must_stay_blocked(self):
        """DEFECT 1: Having source_refs without explicit typed input_alternatives MUST NOT create SOURCE_ONLY."""
        output = {'file': 'entry/src/main/ets/TestView.ets', 'symbol': 'TestView', 'builder': 'build'}
        unit = {
            'unit_id': 'ios.0001.Test',
            'page_id': 'page_0001_Test',
            'component': 'TestView',
            'output': output,
            'source_refs': [{'file': 'TestView.swift', 'line': 1, 'sha256': self.source_sha}],
            'required_states': [
                # Has source_refs but NO explicit input_alternatives or state_gaps
                {'state_id': 'default', 'source_refs': [{'file': 'TestView.swift', 'line': 1, 'sha256': self.source_sha}]}
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

        # Freeze should NOT create source_alternatives without explicit input_alternatives
        freeze(['--project-root', str(self.root), '--inventory', 'spec/baseline/ui-delivery-approved.json'])

        index = json.loads((self.root / 'spec' / 'execution' / 'ui-inputs' / 'index.json').read_text())
        packet = index['packets'][0]

        # EXPECTED: No source_alternatives created
        self.assertNotIn('source_alternatives', packet,
            "DEFECT 1: source_refs alone should NOT create source_alternatives")

        # Prepare and complete should remain BLOCKED
        prepared = prepare(self.root, 'ios.0001.Test', 1)
        self.assertEqual(prepared['status'], 'BLOCKED')

        # Create report
        report_path = self.root / 'spec/execution/conversion-reports/ios.0001.Test.json'
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report = {
            'unit_id': 'ios.0001.Test',
            'dispatch_id': prepared['dispatch_id'],
            'packet_sha256': prepared['packet_sha256'],
            'state_implementations': [{'state_id': 'default', 'symbol': 'build'}],
            'image_observations': [],
            'input_applications': [],
        }
        report_path.write_bytes(json_bytes(report))

        completed = complete(self.root, prepared['dispatch_id'])

        # EXPECTED: Should be BLOCKED, not SOURCE_ONLY
        self.assertEqual(completed['status'], 'BLOCKED',
            "DEFECT 1: Without explicit typed gap, should remain BLOCKED not SOURCE_ONLY")

    def test_defect2_runtime_png_always_requires_observation(self):
        """DEFECT 2: Real runtime PNG inputs must always require image observations, never waived."""
        output = {'file': 'entry/src/main/ets/TestView.ets', 'symbol': 'TestView', 'builder': 'build'}
        unit = {
            'unit_id': 'ios.0002.Test',
            'page_id': 'page_0002_Test',
            'component': 'TestView',
            'output': output,
            'source_refs': [{'file': 'TestView.swift', 'line': 1, 'sha256': self.source_sha}],
            'required_states': [
                {'state_id': 'default'}
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

        # Create REAL runtime evidence (PNG + AX)
        snap_dir = self.root / 'spec' / 'baseline' / 'ui-snapshots' / 'page_0002_Test'
        snap_dir.mkdir(parents=True, exist_ok=True)

        png_content = b'fake PNG data'
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
                    'page_id': 'page_0002_Test',
                    'state_id': 'default',
                    'png_path': 'default.png',
                    'png_sha256': sha256(png_content),
                    'ui_json_path': 'default.json',
                    'ui_json_sha256': sha256(ax_content)
                }
            }
        }
        (snap_dir / 'meta.json').write_bytes(json_bytes(meta))

        freeze(['--project-root', str(self.root), '--inventory', 'spec/baseline/ui-delivery-approved.json'])
        prepared = prepare(self.root, 'ios.0002.Test', 1)

        # Create report WITHOUT image_observations
        report_path = self.root / 'spec/execution/conversion-reports/ios.0002.Test.json'
        report_path.parent.mkdir(parents=True, exist_ok=True)

        packet = json.loads((self.root / prepared['packet_path']).read_bytes())
        report = {
            'unit_id': 'ios.0002.Test',
            'dispatch_id': prepared['dispatch_id'],
            'packet_sha256': prepared['packet_sha256'],
            'state_implementations': [{'state_id': 'default', 'symbol': 'build'}],
            'image_observations': [],  # MISSING despite having screenshot_png
            'input_applications': [{'input_id': inp['input_id']} for inp in packet['required_inputs']],
        }
        report_path.write_bytes(json_bytes(report))

        completed = complete(self.root, prepared['dispatch_id'])

        # EXPECTED: Should be BLOCKED for missing image_observation
        self.assertEqual(completed['status'], 'BLOCKED',
            "DEFECT 2: Missing image_observation for real PNG should cause BLOCKED")
        self.assertTrue(
            any('image_observation_missing' in str(e) for e in completed.get('failure_findings', [])),
            "DEFECT 2: Should have image_observation_missing error"
        )


if __name__ == '__main__':
    # Run only defect tests to demonstrate failures
    unittest.main(verbosity=2)
