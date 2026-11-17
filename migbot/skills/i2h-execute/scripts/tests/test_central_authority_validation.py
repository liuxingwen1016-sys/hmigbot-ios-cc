"""Central authority validation tests."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.ios_stage1_scope import load_inventory, inventory_path
from lib.ios_inventory_resolution import sha256_file


def json_bytes(obj):
    return (json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + '\n').encode('utf-8')


class CentralAuthorityValidationTest(unittest.TestCase):
    """Test central authority with production validation."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.ios_root = self.root / 'ios'
        self.ios_root.mkdir(parents=True)
        self.script_dir = Path(__file__).resolve().parent.parent
        self.plan_cli = self.script_dir.parent.parent / 'i2h-plan' / 'scripts' / 'ui_delivery.py'

        self.create_sources()
        self.create_canonical_baseline()

    def create_sources(self):
        (self.ios_root / 'TestView.swift').write_text('struct TestView: View { var body: some View { Text("Test") } }')

    def create_canonical_baseline(self):
        test_sha = sha256_file(self.ios_root / 'TestView.swift')
        baseline = {
            'schema_version': 2,
            'status': 'approved',
            'source_project_root': str(self.ios_root),
            'units': [{
                'unit_id': 'ios.0001.TestView',
                'page_id': 'page_test',
                'component': 'ios.TestView',
                'presentation_role': 'embedded',
                'owned_ui_roles': ['content'],
                'required': True,
                'output': {'file': 'TestView.ets', 'symbol': 'TestView', 'builder': 'TestViewBuilder'},
                'generation_owner': 'i2h-harmony',
                'source_refs': [{'file': 'TestView.swift', 'line': 1, 'sha256': test_sha}],
                'required_states': [{'state_id': 'default', 'responsibility': 'content', 'arrival_mode': 'formal'}]
            }],
            'verification_states': []
        }
        baseline_path = self.root / 'spec' / 'baseline' / 'ui-delivery-approved.json'
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_bytes(json_bytes(baseline))
        return baseline_path

    def test_no_index_uses_canonical_baseline(self):
        """Test that without index, canonical baseline is used."""
        path, data = load_inventory(self.root, None)
        self.assertEqual(path.name, 'ui-delivery-approved.json')
        self.assertEqual(data['status'], 'approved')

    def test_malformed_index_raises(self):
        """Test malformed index raises ValueError."""
        index_path = self.root / 'spec' / 'execution' / 'ui-inputs' / 'index.json'
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text('invalid json')

        with self.assertRaises(ValueError) as ctx:
            load_inventory(self.root, None)
        self.assertIn('malformed', str(ctx.exception))

    def test_stale_hash_raises(self):
        """Test stale hash in index raises ValueError."""
        baseline_path = self.root / 'spec' / 'baseline' / 'ui-delivery-approved.json'
        index = {
            'schema_version': 2,
            'inventory_source': {'path': 'spec/baseline/ui-delivery-approved.json', 'sha256': 'stale'},
            'packets': []
        }
        index_path = self.root / 'spec' / 'execution' / 'ui-inputs' / 'index.json'
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_bytes(json_bytes(index))

        with self.assertRaises(ValueError) as ctx:
            load_inventory(self.root, None)
        self.assertIn('SHA mismatch', str(ctx.exception))

    def test_explicit_priority_over_index(self):
        """Test explicit inventory has priority."""
        baseline_path = self.root / 'spec' / 'baseline' / 'ui-delivery-approved.json'

        # Bogus index
        index = {'schema_version': 2, 'inventory_source': {'path': 'nonexistent.json', 'sha256': 'fake'}}
        index_path = self.root / 'spec' / 'execution' / 'ui-inputs' / 'index.json'
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_bytes(json_bytes(index))

        # Explicit should work
        path, data = load_inventory(self.root, 'spec/baseline/ui-delivery-approved.json')
        self.assertEqual(data['status'], 'approved')

    def test_unapproved_execution_raises(self):
        """Test unapproved execution inventory raises."""
        exec_inv = self.root / 'spec' / 'execution' / 'draft.json'
        exec_inv.parent.mkdir(parents=True, exist_ok=True)

        draft = {
            'schema_version': 2,
            'status': 'draft',  # Not approved
            'source_project_root': str(self.ios_root),
            'units': []
        }
        exec_inv.write_bytes(json_bytes(draft))

        with self.assertRaises(ValueError) as ctx:
            load_inventory(self.root, str(exec_inv.relative_to(self.root)))
        self.assertIn('approved', str(ctx.exception))


if __name__ == '__main__':
    unittest.main()
