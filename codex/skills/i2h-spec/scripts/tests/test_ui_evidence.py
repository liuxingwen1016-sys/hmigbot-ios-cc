from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ui_evidence import build_skeleton, parse_ui_obligations, run
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

    def test_ui_obligations_capture_controls_and_layout_containers(self):
        source = '''
        struct SettingsView: View {
            var body: some View {
                Form {
                    Picker("外观", selection: $appearance) { Text("跟随系统") }
                    Toggle("通知", isOn: $notifications)
                    Button("完成") { save() }
                }
                .accessibilityIdentifier("settingsDone")
            }
        }
        '''
        obligations = parse_ui_obligations(source)
        self.assertEqual([row['kind'] for row in obligations['interactive_controls']], ['picker', 'toggle', 'button'])
        self.assertEqual(obligations['interactive_controls'][0]['label'], '外观')
        self.assertEqual(obligations['interactive_controls'][2]['label'], '完成')
        self.assertEqual(obligations['accessibility_identifiers'][0]['value'], 'settingsDone')
        self.assertTrue(obligations['has_form'])
        self.assertFalse(obligations['has_scroll'])

    def test_view_evidence_carries_ui_obligations(self):
        self.write('Views/RecipeView.swift', '''
        import SwiftUI
        struct RecipeView: View {
            var body: some View {
                ScrollView { Text("Recipe") }
                Button("开始冲煮") { startBrew() }
            }
        }
        ''')
        evidence_path = self.root / 'spec/.i2h/resources-inventory.json'
        payload = run(str(self.root), str(evidence_path))
        recipe = next(row for row in payload['views'] if row['view_name'] == 'RecipeView')
        self.assertTrue(recipe['ui_obligations']['has_scroll'])
        self.assertEqual(recipe['ui_obligations']['interactive_controls'][-1]['label'], '开始冲煮')

    def test_ui_obligations_capture_embedded_states_and_presentations(self):
        source = '''
        struct HomeView: View {
            var body: some View {
                if isLoading { ProgressView() }
                else if beans.isEmpty { EmptyStateView() }
                .sheet(isPresented: $showRecipe) { RecipeView() }
                .confirmationDialog("确认", isPresented: $confirm) { Button("确定") {} }
            }
        }
        '''
        obligations = parse_ui_obligations(source)
        self.assertEqual([item['kind'] for item in obligations['presentations']], ['sheet', 'confirmation_dialog'])
        self.assertGreaterEqual(len(obligations['conditional_states']), 2)
        self.assertEqual({item['kind'] for item in obligations['state_markers']}, {'loading', 'empty'})
        self.assertEqual([item['name'] for item in obligations['embedded_view_candidates']], ['EmptyStateView', 'RecipeView'])

    def test_same_file_views_keep_obligations_scoped_to_declaration(self):
        self.write('Views/BeanViews.swift', '''
        import SwiftUI
        struct BeanLibraryView: View {
            var body: some View { ScrollView { Button("添加档案") {} } }
        }
        struct BeanDetailView: View {
            var body: some View { Button("编辑") {} }
        }
        struct BeanEditorView: View {
            var body: some View {
                Form {
                    Picker("处理法", selection: .constant(0)) { Text("水洗") }
                    Button("保存档案") {}
                }
            }
        }
        ''')
        payload = run(str(self.root), str(self.root / 'spec/.i2h/resources-inventory.json'))
        views = {row['view_name']: row for row in payload['views'] if row['file_path'] == 'Views/BeanViews.swift'}
        self.assertTrue(views['BeanLibraryView']['ui_obligations']['has_scroll'])
        self.assertFalse(views['BeanLibraryView']['ui_obligations']['has_form'])
        self.assertEqual([row['kind'] for row in views['BeanLibraryView']['ui_obligations']['interactive_controls']], ['button'])
        self.assertEqual([row['kind'] for row in views['BeanDetailView']['ui_obligations']['interactive_controls']], ['button'])
        self.assertFalse(views['BeanDetailView']['ui_obligations']['has_form'])
        self.assertTrue(views['BeanEditorView']['ui_obligations']['has_form'])
        self.assertEqual([row['kind'] for row in views['BeanEditorView']['ui_obligations']['interactive_controls']], ['picker', 'button'])


if __name__ == '__main__':
    unittest.main()
