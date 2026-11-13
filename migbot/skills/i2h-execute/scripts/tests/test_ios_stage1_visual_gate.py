"""Visual archive regression checks against frozen scope and receipt identities."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.ios_stage1_acceptance import archive_g1
from lib.ios_stage1_scope import build_scope_from_inventory
from lib.ios_stage1_summary import summarize
from lib.ios_stage1_visual_gate import archive_visual
from lib.ios_ui_dispatch import INDEX, complete, json_bytes, prepare, sha256
from lib.ios_ui_relationships import compare_relationships
from lib.stage1_visual_report import assemble


class IOSVisualGateTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        page, state, unit = 'page_0001_Home', 'default', 'home'
        source = f'spec/baseline/ui-snapshots/{page}'
        self.png = b'\x89PNG\r\n\x1a\nfixture'
        self.tree = json_bytes({'viewport': [0, 0, 100, 200], 'nodes': [
            {'role': 'text', 'label': 'Home', 'frame': [10, 10, 50, 20]},
            {'role': 'Button', 'label': 'Next', 'frame': [10, 40, 50, 20]},
        ]})
        self.write(source+'/source.png', self.png)
        self.write(source+'/source.json', self.tree)
        self.write(source+'/meta.json', {'runtime_evidence_by_state': {state: {
            'status': 'audited', 'state_id': state, 'page_id': page, 'app_identity': 'test.source',
            'png_path': 'source.png', 'png_sha256': sha256(self.png),
            'ui_json_path': 'source.json', 'ui_json_sha256': sha256(self.tree),
        }}})
        self.write('spec/baseline/ui-delivery-approved.json', {
            'schema_version': 2, 'status': 'approved', 'units': [{
                'unit_id': unit, 'page_id': page, 'required_states': [{'state_id': state, 'arrival_mode': 'formal'}],
                'output': {'file': 'entry/src/main/ets/Home.ets'},
            }],
            'verification_states': [{'verification_id': 'pair', 'page_id': page, 'state_id': state, 'owner': unit}],
        })
        self.write('entry/src/main/ets/Home.ets', b'struct Home {}')
        self.scope = build_scope_from_inventory(self.root, None)
        self.scope_path = self.write('spec/scope.json', self.scope)
        self.scope_hash = sha256(self.scope_path.read_bytes())

    def write(self, filename, value):
        path = self.root / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value if isinstance(value, bytes) else json_bytes(value))
        return path

    def ref(self, path):
        return {'path': path.relative_to(self.root/'spec').as_posix(), 'sha256': sha256(path.read_bytes())}

    def observed_report(self, *, forged_relationship=False):
        self.write('entry/build/test.hap', b'fixture package')
        common = {'status': 'PASS', 'scope_sha256': self.scope_hash, 'source_sha256': self.scope['source_sha256'],
                  'hap_path': 'entry/build/test.hap', 'hap_sha256': sha256(b'fixture package')}
        build = self.write('spec/build.json', {**common, 'kind': 'build'})
        install = self.write('spec/install.json', {**common, 'kind': 'install', 'device_id': 'fixture-target'})
        arrive = self.write('spec/arrival.json', {'status': 'PASS', 'pair_id': 'pair', 'arrival_mode': 'formal',
                                                'device_id': 'fixture-target', 'build_receipt': self.ref(build),
                                                'install_receipt': self.ref(install)})
        self.write('spec/target.png', self.png)
        target = self.write('spec/target.json', {'attributes': {'bounds': '[0,0][200,400]'}, 'children': [
            {'attributes': {'type': 'Text', 'text': 'Home', 'bounds': '[20,20][120,60]'}},
            {'attributes': {'type': 'Button', 'text': 'Next', 'bounds': '[20,80][120,120]'}},
        ]})
        self.write('spec/appearance.json', {'comparison_id': 'pair:0', 'verdict': 'PASS',
                                            'ios_png_sha256': sha256(self.png), 'harmony_png_sha256': sha256(self.png)})
        pair = self.scope['pairs'][0]
        relationship = compare_relationships(self.root, pair, pair['comparisons'][0], target)
        self.assertEqual(relationship['verdict'], 'PASS')
        if forged_relationship:
            relationship['matched_anchors'] += 1
        self.write('spec/relationship.json', relationship)
        capture = self.write('spec/capture.json', {'pairs': [{
            'pair_id': 'pair', 'arrival_receipt': self.ref(arrive),
            'frames': [{'comparison_id': 'pair:0', 'harmony_png': 'target.png', 'harmony_xml': 'target.json'}],
        }]})
        judge = self.write('spec/judge.json', {'comparisons': [{
            'comparison_id': 'pair:0', 'verdict': 'PASS', 'appearance_report': 'appearance.json',
            'relationship_report': 'relationship.json',
        }]})
        return self.write('spec/report.json', assemble(self.root, self.scope_path, capture, [judge]))

    def test_verified_artifacts_are_archived_and_tampering_is_visible(self):
        report = self.observed_report()
        passed = archive_visual(self.root, self.scope_path, report)
        self.assertEqual(passed['status'], 'PASS')
        self.assertFalse(passed['stage1_complete'])
        self.assertEqual(passed['passed_pairs'], 1)
        self.assertEqual(archive_visual(self.root, self.scope_path, report), passed)
        self.write('spec/target.png', b'changed bytes')
        changed = archive_visual(self.root, self.scope_path, report)
        self.assertEqual(changed['status'], 'BLOCKED')
        self.assertEqual(changed['pairs'][0]['verdict'], 'NOT_RUN')
        self.assertTrue((self.root / passed['archive_path'] / 'receipt.json').exists())

    def test_visual_denominator_survives_missing_capture(self):
        capture = self.write('spec/capture.json', {'pairs': []})
        report = self.write('spec/report.json', assemble(self.root, self.scope_path, capture, []))
        result = archive_visual(self.root, self.scope_path, report)
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertEqual(result['required_pairs'], 1)
        self.assertFalse(result['assessment_complete'])

    def test_config_change_invalidates_visual_scope(self):
        report = self.observed_report()
        self.write('AppScope/app.json5', b'changed')
        with self.assertRaisesRegex(ValueError, 'scope is stale'):
            archive_visual(self.root, self.scope_path, report)

    def test_claimed_relationship_is_recomputed_from_both_trees(self):
        report = self.observed_report(forged_relationship=True)
        result = archive_visual(self.root, self.scope_path, report)
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertIn('native tree replay', result['pairs'][0]['reason'])

    def complete_converter(self):
        inventory_path = self.root / 'spec/baseline/ui-delivery-approved.json'
        inventory = json.loads(inventory_path.read_bytes())
        inventory['source_project_root'] = str(self.root / 'ios')
        source = self.write('ios/Home.swift', b'struct Home {}\n')
        unit = inventory['units'][0]
        unit['component'] = 'Home'
        unit['source_refs'] = [{'file': 'Home.swift', 'line': 1, 'sha256': sha256(source.read_bytes())}]
        unit['output'].update(symbol='Home', builder='build')
        self.write(unit['output']['file'], b'@ComponentV2\nexport struct Home { build() { Text("Home") } }')
        self.write(inventory_path.relative_to(self.root), inventory)
        baseline = self.scope['pairs'][0]['baseline']
        state = {**unit['required_states'][0], 'evidence': {
            **baseline, 'status': 'audited', 'page_id': unit['page_id'], 'state_id': 'default',
        }}
        self.write(INDEX, {'schema_version': 2, 'inventory_source': {
            'path': inventory_path.relative_to(self.root).as_posix(), 'sha256': sha256(inventory_path.read_bytes()),
        }, 'packets': [{**unit, 'required_states': [state]}]})
        dispatched = prepare(self.root, 'home', 1)
        self.assertEqual(dispatched['status'], 'READY', dispatched)
        packet = json.loads((self.root / dispatched['packet_path']).read_bytes())
        self.write('spec/execution/conversion-reports/home.json', {
            'unit_id': 'home', 'dispatch_id': dispatched['dispatch_id'], 'packet_sha256': dispatched['packet_sha256'],
            'state_implementations': [{'state_id': 'default', 'symbol': 'build'}],
            'image_observations': [{'state_id': 'default', 'comparison_id': 'default:screenshot_png'}],
            'input_applications': [{'input_id': row['input_id']} for row in packet['required_inputs']],
        })
        receipt = complete(self.root, dispatched['dispatch_id'])
        self.assertEqual(receipt['status'], 'PASS', receipt)
        self.scope = build_scope_from_inventory(self.root, None)
        self.write(self.scope_path.relative_to(self.root), self.scope)
        self.scope_hash = sha256(self.scope_path.read_bytes())

    def summary_cli(self, *args):
        result = self.acceptance_cli('summary', *args)
        return result.returncode, json.loads(result.stdout)

    def acceptance_cli(self, kind, *args):
        script = Path(__file__).resolve().parents[1] / 'stage1_acceptance.py'
        return subprocess.run(
            [sys.executable, '-E', '-B', '-X', 'utf8', str(script), '--kind', kind,
             '--project-root', str(self.root), '--scope', self.scope_path.relative_to(self.root).as_posix(), *args],
            cwd=self.root, capture_output=True, text=True, encoding='utf-8', timeout=20,
        )

    def result(self, kind, expected_exit, *args):
        process = self.acceptance_cli(kind, *args)
        self.assertEqual(process.returncode, expected_exit, process.stdout + process.stderr)
        return json.loads(process.stdout)

    def test_summary_requires_existing_g1_and_replays_all_proof(self):
        self.complete_converter()
        report = self.observed_report()
        visual = archive_visual(self.root, self.scope_path, report)
        status, incomplete = self.summary_cli('--out', 'spec/summary.json')
        self.assertEqual((status, incomplete['structural'], incomplete['visual']), (2, 'NOT_RUN', 'PASS'))
        self.assertEqual(incomplete['required_pairs'], 1)
        self.assertFalse((self.root/'spec/execution/dispatch/g1').exists())
        assembled = archive_g1(self.root)
        status, passed = self.summary_cli('--out', 'spec/summary.json')
        self.assertEqual((status, passed['phase']), (0, 'complete'))
        self.assertTrue(passed['stage1_complete'])
        self.assertEqual(passed['g1_archive_path'], assembled['archive_path'])
        self.assertEqual(passed['visual_archive_path'], visual['archive_path'])
        self.assertEqual(json.loads((self.root/'spec/summary.json').read_bytes()), passed)

        self.write('entry/build/test.hap', b'changed after visual approval')
        status, stale = self.summary_cli()
        self.assertEqual(status, 2)
        self.assertFalse(stale['stage1_complete'])
        self.assertIn('visual_evidence_invalid', {row['code'] for row in stale['failure_findings']})

    def test_summary_preserves_latest_visual_on_an_idempotent_historical_replay(self):
        self.complete_converter()
        archive_g1(self.root)
        report = self.observed_report()
        first = archive_visual(self.root, self.scope_path, report)
        empty = self.write('spec/empty.json', {'scope_sha256': self.scope_hash, 'pairs': []})
        latest = archive_visual(self.root, self.scope_path, empty)
        self.assertEqual(archive_visual(self.root, self.scope_path, report), first)
        status, summary = self.summary_cli('--build-receipt', 'spec/build.json')
        self.assertEqual((status, summary['build'], summary['visual']), (2, 'PASS', 'BLOCKED'))
        self.assertEqual(summary['visual_archive_path'], latest['archive_path'])
        self.assertEqual(summary['pairs'][0]['verdict'], 'NOT_RUN')
        self.assertFalse(summary['assessment_complete'])
        self.assertFalse(summary['stage1_complete'])
        self.assertIn('--report does not match the latest', str(self.summary_cli('--report', 'spec/report.json')[1]))

    def test_summary_reopens_archives_written_by_a_prior_runtime(self):
        self.complete_converter()
        archive_g1(self.root)
        report = self.observed_report()
        expected = archive_visual(self.root, self.scope_path, report)
        (self.root/'spec/execution/dispatch/visual/latest'/f'{self.scope_hash}.json').unlink()
        result = summarize(self.root, self.scope_path)
        self.assertTrue(result['stage1_complete'])
        self.assertEqual(result['visual_archive_path'], expected['archive_path'])

    def rebind_scope(self, revision):
        source = self.root/'entry/src/main/ets/Home.ets'
        source.write_bytes(source.read_bytes() + f'\n// source revision {revision}\n'.encode())
        self.assertEqual(archive_g1(self.root)['status'], 'PASS')
        self.scope = build_scope_from_inventory(self.root, None)
        self.scope_path = self.write(f'spec/scope-{revision}.json', self.scope)
        self.scope_hash = sha256(self.scope_path.read_bytes())

    def compile_problem(self, raw_status, number):
        log = self.write(f'spec/compiler-{number}.log', f'compiler {raw_status}: {number}'.encode())
        return self.write(f'spec/compile-{number}.json', {
            'scope_sha256': self.scope_hash, 'source_sha256': self.scope['source_sha256'],
            'status': raw_status, 'evidence': self.ref(log), 'reason': 'fixture diagnostic', 'exit_code': 1,
        })

    def test_native_next_preserves_compile_budget_across_changed_scope_paths(self):
        self.complete_converter()
        archive_g1(self.root)
        self.assertEqual(self.result('next', 2)['next_action'], 'build_current_hap')
        blocked = self.compile_problem('BLOCKED', 'sdk')
        self.assertEqual(self.result('compile', 2, '--report', str(blocked))['attempt'], 0)
        self.assertEqual(self.result('next', 2)['next_action'], 'resolve_build_blocker')
        for number in range(3):
            if number:
                self.rebind_scope(number)
            report = self.compile_problem('FAIL', number)
            recorded = self.result('compile', 2, '--report', str(report))
            self.assertEqual(recorded['attempt'], number)
            self.assertEqual(self.result('compile', 2, '--report', str(report)), recorded)
            action = 'repair_compile' if number < 2 else 'stop_with_compile_defects'
            self.assertEqual(self.result('next', 2)['next_action'], action)
        self.rebind_scope(3)
        report = self.compile_problem('FAIL', 3)
        rejected = self.acceptance_cli('compile', '--report', str(report))
        self.assertEqual(rejected.returncode, 2)
        self.assertIn('budget exhausted', rejected.stderr)

    def test_native_smoke_checks_cold_start_formal_coverage_and_same_installation(self):
        self.complete_converter()
        archive_g1(self.root)
        self.observed_report()
        compile_receipt = self.result('compile', 0, '--build-receipt', 'spec/build.json')
        self.assertEqual(compile_receipt['attempt'], 0)
        self.assertEqual(self.result('next', 2)['next_action'], 'capture_or_review_pending_pairs')
        arrival_path = self.root/'spec/arrival.json'
        arrival = json.loads(arrival_path.read_bytes())
        arrival.update(observed_page_id='page_0001_Home', observed_state_id='default', capture_run_id='run-one')
        self.write('spec/arrival.json', arrival)
        start_log = self.write('spec/start.log', b'fixture cold-start command output')
        cold = self.write('spec/cold-start.json', {
            'kind': 'cold_start', 'status': 'PASS', 'capture_run_id': 'run-one',
            'scope_sha256': self.scope_hash, 'source_sha256': self.scope['source_sha256'],
            'hap_sha256': compile_receipt['hap_sha256'], 'device_id': 'fixture-target', 'evidence': self.ref(start_log),
        })
        case = {'page_id': 'page_0001_Home', 'arrived': True, 'evidence': self.ref(arrival_path)}
        smoke = {'scope_sha256': self.scope_hash, 'cold_start': self.ref(cold),
                 'build_receipt': arrival['build_receipt'], 'install_receipt': arrival['install_receipt'], 'cases': []}
        path = self.write('spec/smoke.json', smoke)
        failed = self.acceptance_cli('smoke', '--report', str(path))
        self.assertEqual(failed.returncode, 2)
        self.assertIn('every formal page', failed.stderr)
        path = self.write('spec/smoke.json', {**smoke, 'cases': [case, case]})
        failed = self.acceptance_cli('smoke', '--report', str(path))
        self.assertIn('unique evidence', failed.stderr)
        path = self.write('spec/smoke.json', {**smoke, 'cases': [case]})
        recorded = self.result('smoke', 0, '--report', str(path))
        self.assertFalse(recorded['stage1_complete'])
        summary = self.result('summary', 2)
        self.assertEqual((summary['smoke'], summary['visual']), ('PASS', 'NOT_RUN'))
        self.write('spec/start.log', b'changed cold-start evidence')
        summary = self.result('summary', 2)
        self.assertIn('smoke_evidence_invalid', {row.get('code') for row in summary['failure_findings']})

    def failing_visual(self, severity):
        report_path = self.observed_report()
        report = json.loads(report_path.read_bytes())
        pair = report['pairs'][0]
        frame = pair['comparisons'][0]
        appearance_path = self.root/'spec/appearance.json'
        appearance = json.loads(appearance_path.read_bytes())
        self.write('spec/appearance.json', {**appearance, 'verdict': 'FAIL'})
        frame.update(verdict='FAIL', severity=severity, appearance_report=self.ref(appearance_path))
        pair.update(verdict='FAIL', severity=severity)
        self.write('spec/report.json', report)
        return archive_visual(self.root, self.scope_path, report_path)

    def test_visual_rounds_limit_critical_repairs_across_rebuilds(self):
        self.complete_converter()
        archive_g1(self.root)
        for number in range(3):
            if number:
                self.rebind_scope(number)
            self.assertEqual(self.failing_visual('critical')['status'], 'FAIL')
            status = self.result('next', 2)
            self.assertEqual(status['visual_round']['attempt'], number)
            self.assertEqual(status['repair_scope'], 'critical_only' if number else 'critical_and_normal')
            self.assertEqual(status['repair_units'], ['home'])
            self.assertEqual(status['next_action'], 'stop_with_visual_defects' if number == 2 else 'repair_visual')

    def test_normal_residual_keeps_raw_failure_after_one_verified_repair(self):
        self.complete_converter()
        archive_g1(self.root)
        self.failing_visual('normal')
        self.assertFalse(self.result('summary', 2)['stage1_complete'])
        self.rebind_scope(1)
        self.failing_visual('normal')
        final = self.result('summary', 0)
        self.assertTrue(final['stage1_complete'])
        self.assertEqual(final['raw_visual'], 'FAIL')
        self.assertEqual(final['accepted_differences'], ['pair'])
        self.assertEqual(final['pairs'][0]['verdict'], 'FAIL')


if __name__ == '__main__':
    unittest.main()
