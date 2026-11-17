"""Regression checks for original converter archives and attempt identity."""
import json
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.ios_ui_dispatch import (
    INDEX, aggregate_g0, check_required_inputs, complete, dispatch_root, events, json_bytes, prepare,
    recovery_review, reuse_metadata, sha256,
)
from lib import ios_ui_dispatch
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

    def test_dispatch_projects_mappings_from_digest_bound_inventory(self):
        inventory = self.root / self.index["inventory_source"]["path"]
        data = json.loads(inventory.read_bytes())
        rows = [{"role": "tab", "line": 1, "label": "Archive", "source_symbol": "square.stack.3d.up",
                 "target_symbol": "square_stack_3d_fill"}]
        drawing = [{"component": "Card", "definition": {"file": "Card.swift", "line": 1},
                    "line": 3, "frame_pt": {"width": 80, "height": 100}}]
        source = self.write("ios/Card.swift", b"struct Card: View {}\n")
        source_digest = sha256(source.read_bytes())
        data["units"][0]["source_obligations"] = {"system_symbol_fidelity": rows, "drawing_component_calls": drawing}
        data["units"][0]["source_refs"].append({"file": "Card.swift", "line": 1, "sha256": source_digest})
        binding = {"definition": drawing[0]["definition"],
                   "output": {"file": "entry/src/main/ets/components/CardArt.ets", "symbol": "CardArt"}}
        data["drawing_component_bindings"] = [binding,
            {"definition": {"file": "Other.swift", "line": 1},
             "output": {"file": "entry/src/main/ets/components/Other.ets", "symbol": "Other"}}]
        payload = json_bytes(data)
        inventory.write_bytes(payload)
        self.index["inventory_source"]["sha256"] = sha256(payload)
        self.write(INDEX, json_bytes(self.index))
        prepared = prepare(self.root, UNIT, 1)
        packet = json.loads((self.root / prepared["packet_path"]).read_bytes())
        self.assertEqual(packet["system_symbol_fidelity"], rows)
        self.assertEqual(packet["drawing_component_calls"], drawing)
        self.assertEqual(packet["drawing_component_bindings"], [binding])
        dependency = next(item for item in packet["required_inputs"] if item["input_id"] == "source:Card.swift:1")
        self.assertEqual(dependency["sha256"], source_digest)

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

    def test_literal_label_symbol_is_frozen_and_blocks_text_only_g0(self):
        inventory = self.root / self.index['inventory_source']['path']
        approved = json.loads(inventory.read_bytes())
        obligation = {'role': 'label', 'line': 1, 'label': 'Open album',
                      'source_symbol': 'photo', 'target_symbol': 'picture'}
        approved['units'][0]['source_obligations'] = {'system_symbol_fidelity': [obligation]}
        inventory.write_bytes(json_bytes(approved))
        self.index['inventory_source']['sha256'] = sha256(inventory.read_bytes())
        self.write(INDEX, json_bytes(self.index))
        first = prepare(self.root, UNIT, 1)
        packet = json.loads((self.root / first['packet_path']).read_bytes())
        self.assertEqual(packet['system_symbol_fidelity'], [obligation])
        self.output.write_text("@ComponentV2\nexport struct Home { build() { Row() { Text('Open album') } } }")
        self.report(first)
        failure = complete(self.root, first['dispatch_id'])
        self.assertEqual(failure['status'], 'BLOCKED')
        self.assertEqual([row['code'] for row in failure['failure_findings']], ['mapped_system_symbol_mismatch'])

        retry = prepare(self.root, UNIT, 2)
        self.output.write_text("@ComponentV2\nexport struct Home { build() { Row() { SymbolGlyph($r('sys.symbol.picture')) Text('Open album') } } }")
        self.report(retry)
        self.assertEqual(complete(self.root, retry['dispatch_id'])['status'], 'PASS')
        self.assertEqual(complete(self.root, first['dispatch_id']), failure)

    def test_share_link_obligation_blocks_a_local_copy_only_handler(self):
        inventory = self.root / self.index['inventory_source']['path']
        approved = json.loads(inventory.read_bytes())
        rows = [{'line': 8, 'payload_argument': 'item', 'label': 'Share this'}]
        approved['units'][0]['source_obligations'] = {'share_link_calls': rows}
        inventory.write_bytes(json_bytes(approved))
        self.index['inventory_source']['sha256'] = sha256(inventory.read_bytes())
        self.write(INDEX, json_bytes(self.index))
        first = prepare(self.root, UNIT, 1)
        packet = json.loads((self.root / first['packet_path']).read_bytes())
        self.assertEqual(packet['share_link_calls'], rows)
        clipboard = '''@ComponentV2
export struct Home {
    build() {
        Button({ type: ButtonType.Normal }) { Row() { Text('Share this') } }
            .id('share').onClick(() => this.share())
    }
    private async share(): Promise<void> {
        // systemShare.ShareController.show()
        await pasteboard.getSystemPasteboard().setData(data);
    }
}
'''
        self.output.write_text(clipboard)
        self.report(first)
        result = complete(self.root, first['dispatch_id'])
        self.assertEqual([r['code'] for r in result['failure_findings']], ['share_link_clipboard_only'])
        self.assertEqual(result['status'], 'BLOCKED')
        retry = prepare(self.root, UNIT, 2)
        self.output.write_text(clipboard.replace(
            '// systemShare.ShareController.show()',
            'if (await this.presenter.openNativeShare(data)) { return; }'))
        self.report(retry)
        self.assertEqual(complete(self.root, retry['dispatch_id'])['status'], 'PASS')

    def test_date_format_obligation_blocks_unqualified_locale_defaults(self):
        inventory = self.root / self.index['inventory_source']['path']
        approved = json.loads(inventory.read_bytes())
        rows = [{'line': 7, 'value_path': 'item.startedAt', 'slot': 'text',
                 'date_style': 'long', 'time_style': 'shortened'}]
        approved['units'][0]['source_obligations'] = {'date_format_calls': rows}
        inventory.write_bytes(json_bytes(approved))
        self.index['inventory_source']['sha256'] = sha256(inventory.read_bytes())
        self.write(INDEX, json_bytes(self.index))
        first = prepare(self.root, UNIT, 1)
        packet = json.loads((self.root / first['packet_path']).read_bytes())
        self.assertEqual(packet['date_format_calls'], rows)
        self.output.write_text(
            '@ComponentV2\nexport struct Home { build() { Text(new Date(item.startedAt).toLocaleString()) } }')
        self.report(first)
        failure = complete(self.root, first['dispatch_id'])
        self.assertEqual(failure['status'], 'BLOCKED')
        self.assertEqual([r['code'] for r in failure['failure_findings']], ['date_format_unqualified_locale'])

        retry = prepare(self.root, UNIT, 2)
        self.output.write_text('''@ComponentV2
export struct Home {
    build() { Column() {
        Text(DisplayFormat.historyDate(item.startedAt))
        Text(new Date(other.startedAt).toLocaleString())
        // Text(new Date(item.startedAt).toLocaleString())
    } }
    @Builder unused() { Text(new Date(item.startedAt).toLocaleString()) }
}
''')
        self.report(retry)
        self.assertEqual(complete(self.root, retry['dispatch_id'])['status'], 'PASS')
        self.assertEqual(complete(self.root, first['dispatch_id']), failure)

    def test_prepared_only_attempt_cannot_hide_the_first_real_archive(self):
        unopened = prepare(self.root, UNIT, 1)
        first_conversion = prepare(self.root, UNIT, 2)
        self.assertEqual(aggregate_g0(self.root)['units'][0]['status'], 'NOT_RUN')
        self.report(first_conversion)
        self.assertEqual(complete(self.root, first_conversion['dispatch_id'])['status'], 'PASS')
        self.assertEqual(aggregate_g0(self.root)['units'][0]['dispatch_id'], first_conversion['dispatch_id'])
        closed = archive_g1(self.root)
        self.assertEqual(closed['status'], 'PASS')
        self.assertEqual(closed['g0_receipts'][0]['first_dispatch_id'], first_conversion['dispatch_id'])
        self.assertEqual(closed['g0_receipts'][0]['earliest_prepared_dispatch_id'], unopened['dispatch_id'])
        self.assertFalse((dispatch_root(self.root) / unopened['dispatch_id'] / 'g0').exists())

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

    def test_equivalent_pending_attempt_can_use_unchanged_g0_archive(self):
        first = prepare(self.root, UNIT, 1)
        report = self.report(first)
        completed = complete(self.root, first['dispatch_id'])
        self.assertEqual(completed['status'], 'PASS')
        pending = prepare(self.root, UNIT, 20)
        chain = dispatch_root(self.root) / 'events.jsonl'
        before = chain.read_bytes()
        g1 = archive_g1(self.root, read_only=True)
        self.assertEqual(g1['status'], 'NOT_RUN')
        self.assertEqual(g1['current_g0_units'], 1)
        self.assertEqual(g1['g0_receipts'][0]['current_dispatch_id'], first['dispatch_id'])
        self.assertEqual(g1['g0_receipts'][0]['latest_prepared_dispatch_id'], pending['dispatch_id'])
        self.assertEqual(recovery_review(self.root)['units'][0]['g0_dispatch_id'], first['dispatch_id'])
        self.assertEqual(chain.read_bytes(), before)
        self.assertEqual(archive_g1(self.root)['status'], 'PASS')

        original_output = self.output.read_bytes()
        self.output.write_bytes(original_output + b'\n// changed')
        self.assertEqual(archive_g1(self.root, read_only=True)['current_g0_units'], 0)
        self.output.write_bytes(original_output)
        report.write_bytes(report.read_bytes() + b'\n')
        self.assertEqual(archive_g1(self.root, read_only=True)['current_g0_units'], 0)
        self.report(pending, include_image=False)
        self.assertEqual(complete(self.root, pending['dispatch_id'])['status'], 'BLOCKED')
        self.report(first)
        self.assertEqual(archive_g1(self.root, read_only=True)['current_g0_units'], 0)

    def test_newer_attempt_with_changed_inputs_still_requires_a_pass(self):
        first = prepare(self.root, UNIT, 1)
        self.report(first)
        complete(self.root, first['dispatch_id'])
        face = self.write('snap/home.png', b'a different screenshot')
        self.evidence['png_sha256'] = sha256(face.read_bytes())
        self.write(INDEX, json_bytes(self.index))
        prepare(self.root, UNIT, 2)
        self.assertEqual(archive_g1(self.root, read_only=True)['current_g0_units'], 0)

    def test_first_attempt_is_preserved_per_approved_inventory(self):
        first = prepare(self.root, UNIT, 1)
        original = aggregate_g0(self.root)
        self.assertEqual(original['units'][0]['status'], 'NOT_RUN')
        approved = self.index['inventory_source']['path']
        prior = json.loads((self.root / approved).read_bytes())
        raw = json_bytes({**prior, 'approval': {'confirmation_ref': 'reapproved'}})
        self.write(approved, raw)
        self.index['inventory_source']['sha256'] = sha256(raw)
        self.write(INDEX, json_bytes(self.index))
        self.assertEqual(aggregate_g0(self.root)['units'][0]['status'], 'STALE')
        current = prepare(self.root, UNIT, 2)
        self.report(current)
        self.assertEqual(complete(self.root, current['dispatch_id'])['status'], 'PASS')
        self.assertEqual(aggregate_g0(self.root)['units'][0]['dispatch_id'], current['dispatch_id'])
        self.assertEqual(archive_g1(self.root)['g0_receipts'][0]['first_dispatch_id'], current['dispatch_id'])
        self.assertFalse((self.root / first['packet_path']).with_name('g0').exists())

    def test_recovery_review_preserves_archived_evidence(self):
        first = prepare(self.root, UNIT, 1)
        self.report(first)
        complete(self.root, first['dispatch_id'])
        approved = self.index['inventory_source']['path']
        inventory = json.loads((self.root / approved).read_bytes())
        inventory['units'][0]['integration'] = [{'child_symbol': 'Home'}]
        raw = json_bytes(inventory)
        self.write(approved, raw)
        self.index['inventory_source']['sha256'] = sha256(raw)
        self.write(INDEX, json_bytes(self.index))
        prepare(self.root, UNIT, 2)
        self.output.write_text('changed output', encoding='utf-8')
        chain = dispatch_root(self.root) / 'events.jsonl'
        before = chain.read_bytes()
        report = recovery_review(self.root)
        self.assertEqual(report['status'], 'BLOCKED')
        row = report['units'][0]
        self.assertEqual(row['previous_dispatch_id'], first['dispatch_id'])
        self.assertEqual(row['changed_unit_fields'], ['integration'])
        self.assertTrue(row['output_changed'])
        self.assertEqual(chain.read_bytes(), before)

    def test_missing_runtime_and_missing_report_are_distinct(self):
        self.evidence.update({'status': 'missing', 'reason': 'not captured'})
        self.write(INDEX, json_bytes(self.index))
        prepared = prepare(self.root, UNIT, 1)
        self.assertEqual(prepared['status'], 'BLOCKED')
        self.assertEqual(aggregate_g0(self.root)['units'][0]['status'], 'NOT_RUN')
        rejected = complete(self.root, prepared['dispatch_id'])
        self.assertEqual({row['code'] for row in rejected['failure_findings']},
                         {'runtime_input_unavailable', 'conversion_report_missing'})

    def add_missing_state(self, mode='behavior', *, status='missing', source_ref=True, required_evidence=None):
        approved = self.index['inventory_source']['path']
        inventory = json.loads((self.root / approved).read_bytes())
        unit = inventory['units'][0]
        state = {'state_id': 'exception', 'arrival_mode': mode}
        if source_ref:
            state['source_refs'] = unit['source_refs']
        if required_evidence:
            state['required_evidence'] = required_evidence
        unit['required_states'].append(state)
        raw = json_bytes(inventory)
        self.write(approved, raw)
        self.index['inventory_source']['sha256'] = sha256(raw)
        self.index['packets'][0]['required_states'].append(
            {'state_id': 'exception', 'evidence': {'status': status, 'reason': 'runtime evidence missing'}}
        )
        self.write(INDEX, json_bytes(self.index))

    def test_missing_anchored_behavior_allows_source_work_but_still_blocks_delivery(self):
        self.add_missing_state()
        readiness = prepare(self.root, UNIT, 1, check_only=True)
        self.assertEqual(readiness['status'], 'BLOCKED')
        self.assertEqual(readiness['source_only_states'], ['exception'])
        self.assertFalse(dispatch_root(self.root).exists())
        prepared = prepare(self.root, UNIT, 1)
        self.assertEqual(prepared['status'], 'BLOCKED')
        self.assertEqual(prepared['conversion_scope'], 'SOURCE_ONLY_BEHAVIOR_GAPS')
        self.assertIn('Do not report image observations for missing states',
                      (self.root / prepared['prompt_path']).read_text())
        report = self.report(prepared)
        data = json.loads(report.read_bytes())
        data['state_implementations'].append({'state_id': 'exception', 'symbol': 'build'})
        report.write_bytes(json_bytes(data))
        completed = complete(self.root, prepared['dispatch_id'])
        self.assertEqual(completed['status'], 'BLOCKED')
        self.assertEqual({item['code'] for item in completed['failure_findings']}, {'runtime_input_unavailable'})
        self.assertEqual(archive_g1(self.root)['status'], 'BLOCKED')

    def test_only_missing_anchored_behavior_without_explicit_evidence_can_use_source(self):
        for case in ({'mode': 'formal'}, {'mode': 'preview'}, {'status': 'invalid'},
                     {'source_ref': False}, {'required_evidence': ['foreground_receipt']}):
            with self.subTest(case=case):
                self.add_missing_state(**case)
                readiness = prepare(self.root, UNIT, 1, check_only=True)
                self.assertEqual(readiness['status'], 'BLOCKED')
                self.assertNotIn('conversion_scope', readiness)
                self.index['packets'][0]['required_states'].pop()
                approved = self.index['inventory_source']['path']
                raw = json.loads((self.root / approved).read_bytes())
                raw['units'][0]['required_states'].pop()
                self.write(approved, json_bytes(raw))

    def test_readiness_checks_preserve_attempts_and_input_objects(self):
        report = prepare(self.root, UNIT, 1, check_only=True)
        self.assertEqual(report['status'], 'READY')
        self.assertEqual(report['scope'], 'INPUT_CHECK_ONLY')
        self.assertTrue(report['checked_inputs'])
        self.assertNotIn('dispatch_id', report)
        folder = dispatch_root(self.root)
        self.assertFalse(folder.exists())
        first = prepare(self.root, UNIT, 1)
        self.report(first)
        self.assertEqual(complete(self.root, first['dispatch_id'])['status'], 'PASS')
        before = {item.relative_to(folder): item.read_bytes()
                  for item in folder.rglob('*') if item.is_file()}
        self.evidence.update({'status': 'missing', 'reason': 'not captured'})
        self.write(INDEX, json_bytes(self.index))
        blocked = prepare(self.root, UNIT, 20, check_only=True)
        self.assertEqual(blocked['status'], 'BLOCKED')
        self.assertEqual(blocked['input_gaps'][0]['code'], 'runtime_input_unavailable')
        after = {item.relative_to(folder): item.read_bytes()
                 for item in folder.rglob('*') if item.is_file()}
        self.assertEqual(before, after)

    def test_batch_cli_checks_only_required_units_without_creating_attempts(self):
        self.add_missing_state()
        p = self.root / self.index['inventory_source']['path']
        inventory = json.loads(p.read_bytes())
        inventory['units'].append({**inventory['units'][0], 'unit_id': 'ios.optional', 'required': False})
        raw = json_bytes(inventory)
        p.write_bytes(raw)
        self.index['inventory_source']['sha256'] = sha256(raw)
        self.write(INDEX, json_bytes(self.index))
        script = Path(__file__).resolve().parents[1] / 'ui_dispatch.py'
        result = subprocess.run([sys.executable, '-B', str(script), 'check-inputs', '--all-required',
                                 '--project-root', str(self.root), '--resume-pending'],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 2, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual((report['required_units'], report['ready_units'], report['blocked_units']), (1, 0, 1))
        self.assertEqual(report['units'][0]['source_only_states'], ['exception'])
        self.assertFalse(dispatch_root(self.root).exists())

    def test_resume_check_uses_original_pending_packet_without_writing(self):
        single = prepare(self.root, UNIT, 1)
        later = prepare(self.root, UNIT, 2)
        folder = dispatch_root(self.root)
        chain = folder / 'events.jsonl'
        before = chain.read_bytes()
        ready = prepare(self.root, UNIT, 3, check_only=True, resume_pending=True)
        self.assertEqual(ready['pending_attempt'], single)
        self.assertEqual(chain.read_bytes(), before)
        self.assertFalse((folder / f'{UNIT}.attempt-3').exists())

        self.report(later)
        ready = prepare(self.root, UNIT, 3, check_only=True, resume_pending=True)
        self.assertEqual(ready['pending_attempt'], later)
        self.report(later, include_image=False)
        self.assertEqual(complete(self.root, later['dispatch_id'])['status'], 'BLOCKED')
        self.assertNotIn('pending_attempt', prepare(self.root, UNIT, 4, check_only=True, resume_pending=True))

    def test_batch_uses_one_snapshot_and_preserves_pending_results(self):
        path = self.root / self.index['inventory_source']['path']
        inventory = json.loads(path.read_bytes())
        second = 'ios.0002.SameSource'
        inventory['units'].append({**inventory['units'][0], 'unit_id': second})
        self.write(str(path.relative_to(self.root)), json_bytes(inventory))
        self.index['inventory_source']['sha256'] = sha256(path.read_bytes())
        self.index['packets'].append({**self.index['packets'][0], 'unit_id': second})
        self.write(INDEX, json_bytes(self.index))
        pending = [prepare(self.root, unit, 1) for unit in (UNIT, second)]
        with patch.object(ios_ui_dispatch, 'load_inventory', wraps=ios_ui_dispatch.load_inventory) as load, \
                patch.object(ios_ui_dispatch, '_parse_events', wraps=ios_ui_dispatch._parse_events) as parse:
            result = check_required_inputs(self.root, resume_pending=True)
        self.assertEqual([unit['pending_attempt'] for unit in result['units']], pending)
        self.assertEqual(load.call_count, 1)
        self.assertEqual(parse.call_count, 1)

    def test_batch_rejects_event_changes_during_the_check(self):
        prepare(self.root, UNIT, 1)
        original = ios_ui_dispatch.state_artifacts
        chain = dispatch_root(self.root) / 'events.jsonl'

        def change_after_read(*args):
            result = original(*args)
            chain.write_bytes(chain.read_bytes() + b'\n')
            return result

        with patch.object(ios_ui_dispatch, 'state_artifacts', side_effect=change_after_read):
            with self.assertRaisesRegex(ValueError, 'dispatch events changed'):
                check_required_inputs(self.root, resume_pending=True)

    def test_scoped_input_check_only_reads_requested_required_units(self):
        path = self.root / self.index['inventory_source']['path']
        inventory = json.loads(path.read_bytes())
        unrelated = 'ios.0002.Unrelated'
        optional = 'ios.0003.Optional'
        inventory['units'].extend([
            {**inventory['units'][0], 'unit_id': unrelated,
             'source_refs': [{'file': 'Unrelated.swift', 'line': 1}]},
            {**inventory['units'][0], 'unit_id': optional, 'required': False},
        ])
        path.write_bytes(json_bytes(inventory))
        self.index['inventory_source']['sha256'] = sha256(path.read_bytes())
        self.index['packets'].append({**self.index['packets'][0], 'unit_id': unrelated})
        self.write(INDEX, json_bytes(self.index))

        result = check_required_inputs(self.root, unit_ids={UNIT})
        self.assertEqual(result['scope'], 'SELECTED_REQUIRED_INPUT_CHECK_ONLY')
        self.assertEqual(result['status'], 'READY')
        self.assertEqual(result['required_units'], 1)
        self.assertEqual([unit['unit_id'] for unit in result['units']], [UNIT])
        with self.assertRaisesRegex(ValueError, 'not required.*ios.0003.Optional'):
            check_required_inputs(self.root, unit_ids={UNIT, optional})
        with self.assertRaisesRegex(ValueError, 'at least one'):
            check_required_inputs(self.root, unit_ids=set())
        with self.assertRaises(FileNotFoundError):
            check_required_inputs(self.root)

    def test_resume_check_does_not_reuse_changed_or_corrupt_inputs(self):
        original = prepare(self.root, UNIT, 1)
        png = self.write('snap/home-v2.png', b'new runtime capture')
        self.evidence.update(png_path='snap/home-v2.png', png_sha256=sha256(png.read_bytes()))
        self.write(INDEX, json_bytes(self.index))
        self.assertNotIn('pending_attempt', prepare(self.root, UNIT, 2, check_only=True, resume_pending=True))
        fresh = prepare(self.root, UNIT, 2)
        packet = json.loads((self.root / fresh['packet_path']).read_bytes())
        item = next(item for item in packet['required_inputs'] if item['kind'] == 'screenshot_png')
        self.write(item['object'], b'corrupt stored screenshot')
        with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
            prepare(self.root, UNIT, 3, check_only=True, resume_pending=True)
        self.assertNotEqual(original['packet_sha256'], fresh['packet_sha256'])

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
