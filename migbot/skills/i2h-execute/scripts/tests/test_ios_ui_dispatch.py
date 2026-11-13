"""Regression checks for original converter archives and attempt identity."""
import json
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.ios_ui_dispatch import (
    INDEX, aggregate_g0, complete, dispatch_root, events, json_bytes, prepare, reuse_metadata, sha256,
)
from lib.ios_stage1_acceptance import archive_g1

UNIT = 'ios.0001.Home'


class IOSDispatchTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.write('ios/Home.swift', b'struct Home {}\n')
        png = self.write('snap/home.png', b'fixture image bytes')
        tree = self.write('snap/home.json', b'{"nodes": []}')
        self.evidence = {'status': 'audited', 'page_id': 'page_0001_Home', 'state_id': 'default',
                         'png_path': 'snap/home.png', 'png_sha256': sha256(png.read_bytes()),
                         'ui_json_path': 'snap/home.json', 'ui_json_sha256': sha256(tree.read_bytes())}
        output = {'file': 'entry/src/main/ets/Home.ets', 'symbol': 'Home', 'builder': 'build'}
        unit = {'unit_id': UNIT, 'page_id': 'page_0001_Home', 'component': 'Home', 'output': output,
                'source_refs': [{'file': 'Home.swift', 'line': 1, 'sha256': sha256(b'struct Home {}\n')}],
                'required_states': [{'state_id': 'default'}]}
        approved = 'spec/baseline/ui-delivery-approved.json'
        raw = json_bytes({'schema_version': 2, 'status': 'approved',
                          'source_project_root': str(self.root / 'ios'), 'units': [unit]})
        self.write(approved, raw)
        self.index = {'schema_version': 2, 'inventory_source': {'path': approved, 'sha256': sha256(raw)},
                      'packets': [{**unit, 'required_states': [{'state_id': 'default', 'evidence': self.evidence}]}]}
        self.write(INDEX, json_bytes(self.index))
        self.output = self.write(output['file'], b'@ComponentV2\nexport struct Home { build() { Text("Ready") } }')

    def write(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def report(self, prepared, *, include_image=True):
        packet = json.loads((self.root / prepared['packet_path']).read_bytes())
        return self.write(f'spec/execution/conversion-reports/{UNIT}.json', json_bytes({
            'unit_id': UNIT, 'dispatch_id': prepared['dispatch_id'], 'packet_sha256': prepared['packet_sha256'],
            'state_implementations': [{'state_id': 'default', 'symbol': 'build'}],
            'image_observations': [{'state_id': 'default', 'comparison_id': 'default:screenshot_png'}] if include_image else [],
            'input_applications': [{'input_id': row['input_id']} for row in packet['required_inputs']],
        }))

    def test_original_success_is_immutable_and_aggregates(self):
        prepared = prepare(self.root, UNIT, 1)
        self.assertEqual(prepared['status'], 'READY')
        self.assertTrue(reuse_metadata(self.root, prepared['dispatch_id'], prepared['packet_path'])['reused'])
        self.assertIn('.png', (self.root / prepared['prompt_path']).read_text())
        self.report(prepared)
        passed = complete(self.root, prepared['dispatch_id'])
        self.assertEqual(passed['status'], 'PASS')
        original = self.root / passed['archive_path'] / 'output.ets'
        old_code = original.read_bytes()
        self.output.write_text('edited by closer')
        self.assertEqual(complete(self.root, prepared['dispatch_id']), passed)
        self.assertEqual(aggregate_g0(self.root)['status'], 'PASS')
        self.assertEqual(original.read_bytes(), old_code)
        original.write_text('archive was changed')
        with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
            aggregate_g0(self.root)

    def test_first_failure_stays_visible_after_a_new_attempt(self):
        first = prepare(self.root, UNIT, 1)
        self.report(first, include_image=False)
        rejected = complete(self.root, first['dispatch_id'])
        self.assertIn('image_observation_missing', {item['code'] for item in rejected['failure_findings']})
        second = prepare(self.root, UNIT, 2)
        self.report(second)
        self.assertEqual(complete(self.root, second['dispatch_id'])['status'], 'PASS')
        aggregate = aggregate_g0(self.root)
        self.assertEqual(aggregate['status'], 'BLOCKED')
        self.assertEqual(aggregate['units'][0]['dispatch_id'], first['dispatch_id'])
        self.assertEqual(len(events(dispatch_root(self.root))), 4)

    def test_missing_runtime_and_missing_report_are_distinct(self):
        self.evidence.update({'status': 'missing', 'reason': 'not captured'})
        self.write(INDEX, json_bytes(self.index))
        prepared = prepare(self.root, UNIT, 1)
        self.assertEqual(prepared['status'], 'BLOCKED')
        self.assertEqual(aggregate_g0(self.root)['units'][0]['status'], 'NOT_RUN')
        rejected = complete(self.root, prepared['dispatch_id'])
        self.assertEqual({row['code'] for row in rejected['failure_findings']},
                         {'runtime_input_unavailable', 'conversion_report_missing'})

    def test_g1_archives_only_current_structure_and_preserves_first_attempt(self):
        first = prepare(self.root, UNIT, 1)
        self.report(first, include_image=False)
        self.assertEqual(complete(self.root, first['dispatch_id'])['status'], 'BLOCKED')
        g0 = aggregate_g0(self.root)
        blocked = archive_g1(self.root)
        self.assertEqual(blocked['status'], 'BLOCKED')
        self.assertIn('g0_current_not_passed', {row['code'] for row in blocked['failure_findings']})

        second = prepare(self.root, UNIT, 2)
        report = self.report(second)
        self.assertEqual(complete(self.root, second['dispatch_id'])['status'], 'PASS')
        self.output.write_text('@ComponentV2\nexport struct Home { build() { Text("Assembled") } }')
        result = archive_g1(self.root)
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['result_scope'], 'STRUCTURAL_ONLY')
        self.assertFalse(result['stage1_complete'])
        self.assertEqual(result['g0_receipts'][0]['first_status'], 'BLOCKED')
        self.assertEqual(aggregate_g0(self.root), g0)
        self.assertTrue((self.root / blocked['archive_path'] / 'receipt.json').is_file())
        self.assertEqual(archive_g1(self.root), result)

        report.write_bytes(report.read_bytes() + b'\n')
        changed = archive_g1(self.root)
        self.assertIn('g0_live_report_changed', {row['code'] for row in changed['failure_findings']})
        self.assertEqual(changed['status'], 'BLOCKED')

    def test_g1_fingerprint_binds_build_inputs_but_excludes_evidence(self):
        prepared = prepare(self.root, UNIT, 1)
        self.report(prepared)
        complete(self.root, prepared['dispatch_id'])
        first = archive_g1(self.root)
        self.write('spec/evidence/record.json', b'{}')
        self.write('entry/build/generated.ets', b'generated output')
        self.assertEqual(archive_g1(self.root), first)
        for filename in ('AppScope/app.json5', 'entry/src/main/resources/base/element/string.json', 'hvigor/hvigor-config.json5'):
            self.write(filename, b'{ "changed": true }')
            second = archive_g1(self.root)
            self.assertNotEqual(first['source_sha256'], second['source_sha256'])
            self.assertNotEqual(first['archive_path'], second['archive_path'])
            first = second
        receipt = self.root / first['archive_path'] / 'receipt.json'
        receipt.write_bytes(receipt.read_bytes() + b'\n')
        with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
            archive_g1(self.root)

    def test_multiple_hosts_freeze_their_sources_and_require_the_declared_mount(self):
        inventory_path = self.root / self.index['inventory_source']['path']
        inventory = json.loads(inventory_path.read_bytes())
        unit = inventory['units'][0]
        unit['presentation_role'] = 'hosted_destination'
        unit['integration'] = []
        for name, mount in (('Library', 'bindSheet'), ('History', 'bindContentCover')):
            swift = self.write(f'ios/{name}.swift', f'struct {name} {{}}\n'.encode())
            host_file = f'entry/src/main/ets/{name}.ets'
            self.write(host_file, (
                f"import {{ Home }} from './Home'\n"
                f'export struct {name} {{\n'
                f'  build() {{ Column() {{}}.{mount}(this.visible, this.home()) }}\n'
                '  @Builder home() { Home() }\n'
                '}\n'
            ).encode())
            unit['integration'].append({
                'host_file': host_file, 'host_builder': f'{name}.home', 'child_symbol': 'Home',
                'mount': mount, 'source_ref': {'file': swift.name, 'line': 1, 'sha256': sha256(swift.read_bytes())},
            })
        raw = json_bytes(inventory)
        inventory_path.write_bytes(raw)
        self.index['inventory_source']['sha256'] = sha256(raw)
        self.write(INDEX, json_bytes(self.index))

        prepared = prepare(self.root, UNIT, 1)
        packet = json.loads((self.root / prepared['packet_path']).read_bytes())
        self.assertEqual(packet['integration'], unit['integration'])
        sources = {item['path'] for item in packet['required_inputs'] if item['kind'] == 'ios_source'}
        self.assertEqual(sources, {'Home.swift', 'Library.swift', 'History.swift'})
        self.report(prepared)
        self.assertEqual(complete(self.root, prepared['dispatch_id'])['status'], 'PASS')
        original = archive_g1(self.root)
        self.assertEqual(original['status'], 'PASS')

        history = self.root / unit['integration'][1]['host_file']
        history.write_text(history.read_text().replace('bindContentCover', 'bindSheet'))
        rejected = archive_g1(self.root)
        self.assertEqual(rejected['status'], 'BLOCKED')
        self.assertEqual(
            [(item['code'], item.get('host_builder')) for item in rejected['failure_findings']],
            [('required_host_slot_unbound', 'History.home')],
        )
        self.assertTrue((self.root / original['archive_path'] / 'receipt.json').is_file())

    def test_parallel_attempts_record_distinct_events(self):
        with ThreadPoolExecutor(4) as pool:
            rows = list(pool.map(lambda i: prepare(self.root, UNIT, i), range(1, 5)))
        self.assertEqual(len({row['dispatch_id'] for row in rows}), 4)
        self.assertEqual(len(events(dispatch_root(self.root))), 4)
        chain = dispatch_root(self.root) / 'events.jsonl'
        chain.write_text(chain.read_text().replace('"event": "prepare"', '"event": "complete"', 1))
        with self.assertRaisesRegex(ValueError, 'hash chain'):
            aggregate_g0(self.root)


if __name__ == '__main__':
    unittest.main()
