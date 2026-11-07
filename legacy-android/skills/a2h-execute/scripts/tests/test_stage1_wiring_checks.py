import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
from stage1_contract import digest, source_digest
from stage1_wiring_checks import assert_case, check_requirements
from stage1_wiring_smoke import run


class WiringChecksTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.host = 'entry/src/main/ets/pages/Parent.ets'
        self.child = 'entry/src/main/ets/pages/View.ets'
        self.source = """import { View } from './View';
@ComponentV2 export struct Parent {
  build() { Column() { this.slot() }.onClick(() => this.click()) }
  @Builder slot() { View() }
  private click() { this.switchTab(); }
  private switchTab() { this.controller.changeIndex(1); }
}
"""
        self.write(self.host, self.source)
        self.write(self.child, """@ComponentV2 export struct View {
  @Monitor('a') changedA() { console.info('a'); }
  @Monitor('b') changedB() { console.info('b'); }
  build() { Text('Body') }
}""")
        self.contract = {'schema_version': 1, 'unit_id': 'test-wiring', 'policy': 'strict_wiring',
                         'bundle_name': 'com.example.test', 'ability_name': 'EntryAbility',
                         'required_mounts': [{'id': 'body', 'owner_file': self.host, 'owner_symbol': 'Parent.slot',
                                              'component_file': self.child, 'component_symbol': 'View'}],
                         'required_actions': [{'id': 'switch', 'owner_file': self.host,
                                               'owner_symbol': 'Parent.click', 'effect_call': 'this.controller.changeIndex'}],
                         'runtime_cases': [{'id': 'body', 'actions': [{'tap_text': 'First', 'tab_bar': True}],
                                            'content_text': ['Body'], 'selected_tab': 'First'}]}
        self.path = self.write('spec/execution/stage1-wiring-contract.json', json.dumps(self.contract))
        self.write('spec/execution/wiring/test.json', json.dumps({
            'schema_version': 1, 'unit_id': 'test-wiring', 'status': 'smoke_wired',
            'pages': [{'page_id': 'parent', 'state_id': 'body', 'output_file': self.host}],
            'target_files': [self.host, self.child]}))

    def write(self, path, text):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(text if isinstance(text, bytes) else text.encode())
        return target

    def check(self, source):
        self.write(self.host, source)
        return check_requirements(self.root, self.path)

    def layout(self):
        def node(type, text='', **extra):
            return {'attributes': {'type': type, 'text': text, 'visible': 'true',
                                   'bounds': '[0,0][200,200]', **extra}, 'children': []}
        root = node('Column')
        root['children'] = [node('Text', 'Body'), node('TabBar')]
        selected = node('Column', selected='true')
        selected['children'] = [node('Text', 'First')]
        root['children'][1]['children'] = [selected]
        return root

    def receipts(self):
        hap = self.write('entry/build/test.hap', b'test package')
        build = {'kind': 'build', 'status': 'PASS', 'unit_id': 'test-wiring',
                 'source_sha256': source_digest(self.root), 'hap_path': 'entry/build/test.hap', 'hap_sha256': digest(hap)}
        install = {**build, 'kind': 'install', 'device_id': 'test-device'}
        return self.write('spec/execution/build.json', json.dumps(build)), self.write('spec/execution/install.json', json.dumps(install))

    def test_mount_and_transitive_effect_pass_with_decorated_component(self):
        self.assertEqual(self.check(self.source)['status'], 'PASS')

    def test_import_without_mount_fails(self):
        result = self.check(self.source.replace('slot() { View() }', 'slot() { }'))
        self.assertEqual([e['id'] for e in result['errors']], ['body'])

    def test_comment_or_string_is_not_a_mount(self):
        for fake in ["/* View() */", "Text('View()')"]:
            self.assertEqual(self.check(self.source.replace('slot() { View() }', 'slot() { ' + fake + ' }'))['status'], 'FAIL')

    def test_unused_builder_does_not_prove_render_reachability(self):
        self.assertEqual(self.check(self.source.replace('Column() { this.slot() }', 'Column() { Text("empty") }'))['status'], 'FAIL')

    def test_empty_handler_and_string_effect_fail(self):
        for body in ['', "console.info('this.controller.changeIndex(1)');"]:
            result = self.check(self.source.replace('this.switchTab();', body))
            self.assertEqual([e['id'] for e in result['errors']], ['switch'])

    def test_unbound_handler_fails(self):
        self.assertEqual(self.check(self.source.replace('.onClick(() => this.click())', ''))['status'], 'FAIL')

    def test_named_import_alias_passes(self):
        source = self.source.replace('{ View }', '{ View as Content }').replace('slot() { View() }', 'slot() { Content() }')
        self.assertEqual(self.check(source)['status'], 'PASS')

    def test_commented_import_does_not_bind_component(self):
        self.assertEqual(self.check('// ' + self.source)['status'], 'FAIL')

    def test_contract_change_is_rejected_against_frozen_ledger(self):
        self.write('spec/decision-ledger.md', '### D-test\n- **契约**：`spec/execution/stage1-wiring-contract.json`\n'
                   '- **contract_sha256**：`' + digest(self.path) + '`\n')
        self.assertEqual(self.check(self.source)['status'], 'PASS')
        self.path.write_text(json.dumps({**self.contract, 'runtime_cases': self.contract['runtime_cases'] * 2}))
        result = self.check(self.source)
        self.assertEqual(result['status'], 'FAIL')
        self.assertIn('frozen', result['errors'][0]['reason'])

    def test_tab_label_cannot_substitute_for_content(self):
        layout = self.layout()
        case = self.contract['runtime_cases'][0]
        assert_case(layout, case)
        layout['children'].pop(0)
        with self.assertRaises(ValueError):
            assert_case(layout, {**case, 'content_text': ['First']})

    def test_hidden_ancestor_and_wrong_selected_tab_fail(self):
        case = self.contract['runtime_cases'][0]
        layout = self.layout()
        layout['attributes']['visible'] = 'false'
        with self.assertRaises(ValueError):
            assert_case(layout, case)
        with self.assertRaises(ValueError):
            assert_case(self.layout(), {**case, 'selected_tab': 'Second'})

    def test_secondary_page_must_cover_tab_bar(self):
        with self.assertRaises(ValueError):
            assert_case(self.layout(), {'content_text': ['Body'], 'no_tab_bar': True})

    def test_static_failure_prevents_device_access(self):
        self.check(self.source.replace('slot() { View() }', 'slot() {}'))
        with patch('stage1_wiring_smoke.subprocess.run') as device:
            report, _ = run(self.root, self.path, None, None, hdc='hdc')
        device.assert_not_called()
        self.assertEqual(report['status'], 'FAIL')

    def test_stale_receipt_prevents_device_access(self):
        build, install = self.receipts()
        self.write(self.host, self.source + '\n// source changed\n')
        with patch('stage1_wiring_smoke.subprocess.run') as device:
            report, _ = run(self.root, self.path, build, install, hdc='hdc')
        device.assert_not_called()
        self.assertEqual(report['status'], 'BLOCKED')
        self.assertEqual(report['failure_findings'][0]['root_cause'], 'unknown')

    def test_mock_device_run_records_current_case_evidence(self):
        build, install = self.receipts()
        layout = self.layout()
        def device(args, **kwargs):
            if args[3:5] == ['file', 'recv']:
                target = Path(args[-1])
                target.write_bytes(json.dumps(layout).encode() if str(target).endswith('.json') else b'\x89PNG\r\n\x1a\nmock')
            return subprocess.CompletedProcess(args, 0, stdout='', stderr='')
        with patch('stage1_wiring_smoke.subprocess.run', side_effect=device), patch('stage1_wiring_smoke.time.sleep'):
            report, folder = run(self.root, self.path, build, install, hdc='hdc')
        self.assertEqual(report['status'], 'PASS')
        self.assertEqual(report['device_id'], 'test-device')
        self.assertIn('dump_sha256', report['cases'][0])
        self.assertTrue((folder / 'report.json').is_file())


if __name__ == '__main__':
    unittest.main()
