from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ui_evidence import build_skeleton, run
from runtime_view import normalize


class UiEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()

    def write(self, relative: str, value: str | bytes):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value if isinstance(value, bytes) else value.encode())
        return path

    def test_skeleton_indexes_swift_files_without_view_declarations(self):
        self.write('App/Views/Home.swift', 'struct HomeView: View { var body: some View { Text("Home") } }')
        self.write('Core/BrewDomain.swift', 'struct BrewSession { let id: String }')
        evidence_path = self.root / 'spec/.i2h/resources-inventory.json'
        payload = run(str(self.root), str(evidence_path))
        skeleton = build_skeleton(payload)
        self.assertEqual(skeleton['source_file_count'], 2)
        self.assertEqual(skeleton['swift_files'], ['App/Views/Home.swift', 'Core/BrewDomain.swift'])

    def test_runtime_normalize_preserves_ios_state_and_artifact_hashes(self):
        output = self.root / 'capture'
        output.mkdir()
        self.write('capture/ios-runtime.png', b'png')
        self.write('capture/ios-accessibility.json', json.dumps({'nodes': [{'id': 'title', 'role': 'staticText'}]}))
        self.write('capture/capture.json', json.dumps({
            'page_id': 'page_0001_HomeView',
            'state_id': 'normal',
            'screenshot': 'ios-runtime.png',
            'ui_json': 'ios-accessibility.json',
            'nodes': [{'id': 'title', 'role': 'staticText'}],
        }))
        normalized = normalize(self.root / 'capture/capture.json')
        self.assertEqual(normalized['schema_version'], 2)
        self.assertEqual(normalized['state_id'], 'normal')
        self.assertIsNotNone(normalized['screenshot_sha256'])
        self.assertIsNotNone(normalized['ui_json_sha256'])
        self.assertFalse(normalized['warnings'])


if __name__ == '__main__':
    unittest.main()
