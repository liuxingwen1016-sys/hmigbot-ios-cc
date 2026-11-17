"""Tests for frozen source alternative binding validation."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.ui_delivery_inputs_ios import freeze
from lib.ios_ui_dispatch import prepare, json_bytes, sha256


class FrozenSourceAlternativeBindingTests(unittest.TestCase):

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.source_root = self.root / 'ios'
        self.source_root.mkdir()
        src = b'struct V { var body: some View { Text("X") } }\n'
        self.src_file = self.source_root / 'V.swift'
        self.src_file.write_bytes(src)
        self.src_sha = sha256(src)

    def _setup_unit(self, uid, alts=None):
        inv = {
            'schema_version': 2, 'status': 'approved',
            'source_project_root': str(self.source_root),
            'units': [{
                'unit_id': uid, 'page_id': f'page_{uid}', 'component': 'V',
                'output': {'file': 'out.ets', 'symbol': 'V', 'builder': 'build'},
                'source_refs': [{'file': 'V.swift', 'line': 1, 'sha256': self.src_sha}],
                'required_states': [{'state_id': 'default'}],
                'input_alternatives': alts or []
            }]
        }
        path = self.root / 'spec' / 'baseline' / 'ui-delivery-approved.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(json_bytes(inv))
        (self.root / 'out.ets').parent.mkdir(parents=True, exist_ok=True)
        (self.root / 'out.ets').write_bytes(b'export struct V {}')
        return uid

    def test_1_malformed_meta_before_freeze_invalid_no_fallback(self):
        uid = self._setup_unit('test001', [{
            'state_id': 'default', 'alternative_kind': 'source_only',
            'source_file': 'V.swift', 'source_sha256': self.src_sha,
            'source_line': 1, 'declaration': 'V'
        }])
        snap = self.root / 'spec' / 'baseline' / 'ui-snapshots' / f'page_{uid}'
        snap.mkdir(parents=True, exist_ok=True)
        (snap / 'meta.json').write_bytes(b'{broken')

        freeze(['--project-root', str(self.root), '--inventory', 'spec/baseline/ui-delivery-approved.json'])
        idx = json.loads((self.root / 'spec' / 'execution' / 'ui-inputs' / 'index.json').read_text())
        pkt = idx['packets'][0]

        evidence = pkt['required_states'][0]['evidence']
        self.assertEqual(evidence['status'], 'invalid', "Malformed meta must mark evidence invalid")
        self.assertNotIn('source_alternatives', pkt)

        result = prepare(self.root, uid, 1)
        self.assertEqual(result['status'], 'BLOCKED', "Invalid evidence must return BLOCKED")

    def test_2_no_approved_alternative_injection_blocked(self):
        uid = self._setup_unit('test002')
        freeze(['--project-root', str(self.root), '--inventory', 'spec/baseline/ui-delivery-approved.json'])

        idx_path = self.root / 'spec' / 'execution' / 'ui-inputs' / 'index.json'
        idx = json.loads(idx_path.read_text())
        idx['packets'][0]['source_alternatives'] = [{
            'state_id': 'default', 'alternative_kind': 'source_only',
            'source_file': 'V.swift', 'source_sha256': self.src_sha,
            'source_line': 1, 'declaration': 'V', 'visual_status': 'BLOCKED'
        }]
        idx_path.write_bytes(json_bytes(idx))

        try:
            result = prepare(self.root, uid, 1)
            self.assertNotIn(result['status'], ['SOURCE_ONLY', 'READY'],
                "Injected alternatives must be blocked")
        except ValueError:
            pass

    def test_3_incomplete_binding_added_post_freeze_blocked(self):
        uid = self._setup_unit('test003', [{
            'state_id': 'default', 'alternative_kind': 'source_only',
            'source_file': 'V.swift', 'source_sha256': self.src_sha,
            'source_line': 1, 'declaration': 'V'
        }])
        freeze(['--project-root', str(self.root), '--inventory', 'spec/baseline/ui-delivery-approved.json'])
        result1 = prepare(self.root, uid, 1)
        self.assertEqual(result1['status'], 'SOURCE_ONLY')

        snap = self.root / 'spec' / 'baseline' / 'ui-snapshots' / f'page_{uid}'
        snap.mkdir(parents=True, exist_ok=True)
        ax = b'{}'
        (snap / 'd.json').write_bytes(ax)
        (snap / 'meta.json').write_bytes(json_bytes({
            'runtime_evidence_by_state': {'default': {
                'status': 'audited', 'source_platform': 'ios', 'page_id': f'page_{uid}',
                'state_id': 'default', 'png_path': 'missing.png', 'png_sha256': 'x',
                'ui_json_path': 'd.json', 'ui_json_sha256': sha256(ax)
            }}
        }))

        try:
            result2 = prepare(self.root, uid, 2)
            self.assertEqual(result2['status'], 'BLOCKED', "Incomplete post-freeze must return BLOCKED")
        except ValueError:
            pass

    def test_4_malformed_meta_added_post_freeze_blocked(self):
        uid = self._setup_unit('test004', [{
            'state_id': 'default', 'alternative_kind': 'source_only',
            'source_file': 'V.swift', 'source_sha256': self.src_sha,
            'source_line': 1, 'declaration': 'V'
        }])
        freeze(['--project-root', str(self.root), '--inventory', 'spec/baseline/ui-delivery-approved.json'])
        snap = self.root / 'spec' / 'baseline' / 'ui-snapshots' / f'page_{uid}'
        snap.mkdir(parents=True, exist_ok=True)
        (snap / 'meta.json').write_bytes(b'{bad')

        try:
            result = prepare(self.root, uid, 1)
            self.assertEqual(result['status'], 'BLOCKED', "Malformed post-freeze must return BLOCKED")
        except ValueError:
            pass

    def test_5_approved_typed_alternative_source_only_ready(self):
        uid = self._setup_unit('test005', [{
            'state_id': 'default', 'alternative_kind': 'source_only',
            'source_file': 'V.swift', 'source_sha256': self.src_sha,
            'source_line': 1, 'declaration': 'V'
        }])

        freeze(['--project-root', str(self.root), '--inventory', 'spec/baseline/ui-delivery-approved.json'])

        idx = json.loads((self.root / 'spec' / 'execution' / 'ui-inputs' / 'index.json').read_text())
        pkt = idx['packets'][0]
        self.assertIn('source_alternatives', pkt)
        self.assertEqual(pkt['source_alternatives'][0]['state_id'], 'default')

        result = prepare(self.root, uid, 1)
        self.assertEqual(result['status'], 'SOURCE_ONLY')
        self.assertEqual(result['visual_status'], 'BLOCKED')

        dpkt = json.loads((self.root / result['packet_path']).read_bytes())
        proofs = [i for i in dpkt['required_inputs'] if i['kind'] == 'ios_source_proof']
        self.assertGreater(len(proofs), 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
