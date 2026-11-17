"""Tests for the 3 remaining Phase A obligations - demonstrate failures first."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.ui_delivery_inputs_ios import freeze
from lib.ios_ui_dispatch import prepare, complete, json_bytes, sha256


class PhaseAFinalObligationsTests(unittest.TestCase):
    """Tests that SHOULD FAIL with current implementation."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.source_root = self.root / 'ios'
        self.source_root.mkdir()

        # Create realistic Swift file with actual declarations
        self.source_content = b'''struct LoginView {
    var body: some View {
        VStack {
            Text("Login")
        }
    }
}
'''
        self.source_file = self.source_root / 'LoginView.swift'
        self.source_file.write_bytes(self.source_content)
        self.source_sha = sha256(self.source_content)

    def test_obligation1_negative_line_must_reject(self):
        """OBLIGATION 1: Negative source_line must be rejected."""
        output = {'file': 'entry/src/main/ets/LoginView.ets', 'symbol': 'LoginView', 'builder': 'build'}
        unit = {
            'unit_id': 'ios.0001.Test',
            'page_id': 'page_0001',
            'component': 'LoginView',
            'output': output,
            'source_refs': [{'file': 'LoginView.swift', 'line': 1, 'sha256': self.source_sha}],
            'required_states': [{'state_id': 'default'}],
            'input_alternatives': [{
                'state_id': 'default',
                'alternative_kind': 'source_only',
                'source_file': 'LoginView.swift',
                'source_sha256': self.source_sha,
                'source_line': -1,  # NEGATIVE LINE
                'declaration': 'LoginView'
            }]
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
        output_file.write_bytes(b'export struct LoginView { build() {} }')

        freeze(['--project-root', str(self.root), '--inventory', 'spec/baseline/ui-delivery-approved.json'])

        index = json.loads((self.root / 'spec' / 'execution' / 'ui-inputs' / 'index.json').read_text())
        packet = index['packets'][0]

        # EXPECTED: Should NOT create source_alternatives for negative line
        self.assertNotIn('source_alternatives', packet,
            "OBLIGATION 1: Negative source_line should be rejected")

    def test_obligation1_bogus_declaration_must_reject(self):
        """OBLIGATION 1: Declaration not matching actual source must be rejected."""
        output = {'file': 'entry/src/main/ets/LoginView.ets', 'symbol': 'LoginView', 'builder': 'build'}
        unit = {
            'unit_id': 'ios.0002.Test',
            'page_id': 'page_0002',
            'component': 'LoginView',
            'output': output,
            'source_refs': [{'file': 'LoginView.swift', 'line': 1, 'sha256': self.source_sha}],
            'required_states': [{'state_id': 'default'}],
            'input_alternatives': [{
                'state_id': 'default',
                'alternative_kind': 'source_only',
                'source_file': 'LoginView.swift',
                'source_sha256': self.source_sha,
                'source_line': 1,
                'declaration': 'NonExistentView'  # BOGUS DECLARATION
            }]
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
        output_file.write_bytes(b'export struct LoginView { build() {} }')

        freeze(['--project-root', str(self.root), '--inventory', 'spec/baseline/ui-delivery-approved.json'])

        index = json.loads((self.root / 'spec' / 'execution' / 'ui-inputs' / 'index.json').read_text())
        packet = index['packets'][0]

        # EXPECTED: Should NOT create source_alternatives for bogus declaration
        self.assertNotIn('source_alternatives', packet,
            "OBLIGATION 1: Bogus declaration not in source should be rejected")

    def test_obligation2_corrupt_runtime_cannot_downgrade_to_source_only(self):
        """OBLIGATION 2: Existing binding with corrupt/missing files cannot use source_only."""
        # Create meta.json with evidence pointing to non-existent PNG
        snap_dir = self.root / 'spec' / 'baseline' / 'ui-snapshots' / 'page_0003'
        snap_dir.mkdir(parents=True, exist_ok=True)

        # Create AX file but NOT PNG file (corrupt binding)
        ax_content = b'{"nodes": []}'
        ax_file = snap_dir / 'default.json'
        ax_file.write_bytes(ax_content)

        meta = {
            'runtime_evidence_by_state': {
                'default': {
                    'status': 'audited',
                    'source_platform': 'ios',
                    'page_id': 'page_0003',
                    'state_id': 'default',
                    'png_path': 'default.png',  # Points to non-existent file
                    'png_sha256': 'abc123',
                    'ui_json_path': 'default.json',
                    'ui_json_sha256': sha256(ax_content)
                }
            }
        }
        (snap_dir / 'meta.json').write_bytes(json_bytes(meta))

        output = {'file': 'entry/src/main/ets/LoginView.ets', 'symbol': 'LoginView', 'builder': 'build'}
        unit = {
            'unit_id': 'ios.0003.Test',
            'page_id': 'page_0003',
            'component': 'LoginView',
            'output': output,
            'source_refs': [{'file': 'LoginView.swift', 'line': 1, 'sha256': self.source_sha}],
            'required_states': [{'state_id': 'default'}],
            'input_alternatives': [{
                'state_id': 'default',
                'alternative_kind': 'source_only',
                'source_file': 'LoginView.swift',
                'source_sha256': self.source_sha,
                'source_line': 1,
                'declaration': 'LoginView'
            }]
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
        output_file.write_bytes(b'export struct LoginView { build() {} }')

        freeze(['--project-root', str(self.root), '--inventory', 'spec/baseline/ui-delivery-approved.json'])

        index = json.loads((self.root / 'spec' / 'execution' / 'ui-inputs' / 'index.json').read_text())
        packet = index['packets'][0]

        # EXPECTED: Should NOT create source_alternatives when binding is corrupt
        self.assertNotIn('source_alternatives', packet,
            "OBLIGATION 2: Corrupt existing binding cannot downgrade to source_only")

    def test_obligation3_prepare_returns_source_only_cli0_not_blocked(self):
        """OBLIGATION 3: prepare should return SOURCE_ONLY/CLI0 when all gaps have valid proof."""
        output = {'file': 'entry/src/main/ets/LoginView.ets', 'symbol': 'LoginView', 'builder': 'build'}
        unit = {
            'unit_id': 'ios.0004.Test',
            'page_id': 'page_0004',
            'component': 'LoginView',
            'output': output,
            'source_refs': [{'file': 'LoginView.swift', 'line': 1, 'sha256': self.source_sha}],
            'required_states': [{'state_id': 'default'}],
            'input_alternatives': [{
                'state_id': 'default',
                'alternative_kind': 'source_only',
                'source_file': 'LoginView.swift',
                'source_sha256': self.source_sha,
                'source_line': 1,
                'declaration': 'LoginView'
            }]
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
        output_file.write_bytes(b'export struct LoginView { build() {} }')

        freeze(['--project-root', str(self.root), '--inventory', 'spec/baseline/ui-delivery-approved.json'])

        prepared = prepare(self.root, 'ios.0004.Test', 1)

        # EXPECTED: Should return SOURCE_ONLY (CLI 0), not BLOCKED (CLI 2)
        self.assertEqual(prepared['status'], 'SOURCE_ONLY',
            "OBLIGATION 3: prepare should return SOURCE_ONLY when all gaps have valid proof")


if __name__ == '__main__':
    unittest.main(verbosity=2)
