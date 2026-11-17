from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from zipfile import ZipFile

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

from acceptance_plan import DEFAULT_PLAN, PLAN_MARKER, approved_plan, replay_behavior


class AcceptancePlanTest(unittest.TestCase):
    def test_compare_draft_identifies_reused_ids_without_touching_frozen_plan(self):
        historical = self.root / 'historical'
        for name in ('spec/baseline/features/feat_001_demo.md', 'spec/baseline/plans/slices/slice-01.md'):
            path = historical / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((self.root / name).read_bytes())
        frozen = self.root / DEFAULT_PLAN
        before = frozen.read_bytes()
        self.save('spec/baseline/features/feat_001_demo.md',
                  '# F001 Demo\n## Acceptance Criteria\n'
                  '- [ ] F001-AC01 Reject empty names\n- [ ] F001-AC02 Read saved name\n'
                  '- [ ] F001-AC03 Save a name\n')
        current_draft = self.save_json('current-bindings.json', {'schema_version': 1, 'bindings': []})
        result = self.invoke('compare-draft', '--previous-project-root', historical,
                             '--previous-draft', self.draft, '--draft', current_draft)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data['criterion_counts'], {'historical': 2, 'current': 3,
                                                    'current_bound': 0, 'current_unbound': 3})
        self.assertEqual(data['binding_counts'], {'TEXT_CHANGED': 1, 'AC_UNCHANGED': 1})
        row = data['bindings'][0]
        self.assertEqual(row['historical_ac']['statement'], 'Save a name')
        self.assertEqual(row['current_ac']['statement'], 'Reject empty names')
        self.assertEqual(row['same_text_other_ids'], ['F001-AC03'])
        self.assertEqual(frozen.read_bytes(), before)

    def test_compare_draft_checks_criterion_continuations_and_full_text_matches(self):
        relative = 'spec/baseline/features/feat_001_demo.md'
        historical = self.root / 'historical'
        slice_path = historical / 'spec/baseline/plans/slices/slice-01.md'
        slice_path.parent.mkdir(parents=True)
        slice_path.write_bytes((self.root / 'spec/baseline/plans/slices/slice-01.md').read_bytes())
        previous = self.save('historical/' + relative,
                             '# F001 Demo\n## Acceptance Criteria\n'
                             '- [ ] F001-AC01 Save a name\n'
                             '      `判: stores the first 40 characters`\n\n'
                             '- [ ] F001-AC02 Read saved name\n')
        current = self.save(relative, '# F001 Demo\n## Acceptance Criteria\n'
                            '- [x] F001-AC01 Save a name\n'
                            '      `判: stores the first 41 characters`\n'
                            '- [ ] F001-AC02 Read saved name\n'
                            '- [ ] F001-AC03 Save a name\n'
                            '   `判: stores the first 40 characters`\n'
                            '- [ ] F001-AC04 Save a name\n'
                            '   `判: stores the first 42 characters`\n'
                            '## Notes\n   A separate section.\n')
        inputs = [previous, current, self.root / DEFAULT_PLAN, self.draft]
        before = [item.read_bytes() for item in inputs]
        result = self.invoke('compare-draft', '--previous-project-root', historical,
                             '--previous-draft', self.draft)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data['binding_counts'], {'TEXT_CHANGED': 1, 'AC_UNCHANGED': 1})
        row = data['bindings'][0]
        self.assertEqual(row['historical_ac']['digest'], row['current_ac']['digest'])
        self.assertEqual(row['historical_ac']['continuation'], ['`判: stores the first 40 characters`'])
        self.assertEqual(row['current_ac']['continuation'], ['`判: stores the first 41 characters`'])
        self.assertEqual(row['same_text_other_ids'], ['F001-AC03'])
        self.assertEqual([item.read_bytes() for item in inputs], before)

    def test_resume_requires_matching_checkpoint_and_never_credits_suffix_alone(self):
        self.approve()
        first = self.receipt('checkpoint', ['save', 'read'], {'save': 'PASS'},
                             status='PAUSED_AT_SCENARIO_BOUNDARY', next_scenario='read',
                             requested_case='full', visual_scope_sha256='a' * 64,
                             fixture_setup={'status': 'PASS'})
        link = {'path': str(first), 'sha256': sha256(first.read_bytes()).hexdigest(), 'prior_passes': ['save']}
        second = self.receipt('suffix', ['read'], {'read': 'PASS'}, resume_from=link,
                              requested_case='full', visual_scope_sha256='a' * 64,
                              fixture_setup={'status': 'PASS'})
        self.assertEqual(self.check('behavior', '--run', second).returncode, 2)
        report = self.report(self.check('behavior', '--run', first, '--run', second), 0)
        self.assertEqual(report['counts']['scenarios'], {'PASS': 2})
        data = json.loads(second.read_bytes())
        no_setup = {key: value for key, value in data.items() if key != 'fixture_setup'}
        self.save_json('suffix/results.json', no_setup)
        refused = self.check('behavior', '--run', first, '--run', second)
        self.assertEqual(refused.returncode, 2)
        self.assertIn('successful fixture recheck', refused.stderr)
        self.save_json('suffix/results.json', {**data, 'cases': {},
                                              'fixture_setup': {'status': 'FAIL', 'reason': 'fixture drift'}})
        blocked = self.report(self.check('behavior', '--run', first, '--run', second), 1)
        self.assertEqual(blocked['counts']['scenarios'], {'PASS': 1, 'NOT_RUN': 1})
        self.save_json('suffix/results.json', data)
        for key, value in [('runner_sha256', 'd' * 64), ('fixture_sha256', 'e' * 64),
                           ('visual_scope_sha256', 'f' * 64)]:
            data = json.loads(second.read_bytes())
            self.save_json('suffix/results.json', {**data, key: value})
            self.assertEqual(self.check('behavior', '--run', first, '--run', second).returncode, 2)
            self.save_json('suffix/results.json', data)
        data = json.loads(first.read_bytes())
        self.save_json('checkpoint/results.json', {**data, 'status': 'INTERRUPTED_DEVICE_TIMEOUT'})
        self.assertEqual(self.check('behavior', '--run', first, '--run', second).returncode, 2)

    def test_sealed_plan_rejects_changed_conditions_with_the_same_title(self):
        spec_file = self.root / 'spec/baseline/features/feat_001_demo.md'
        source = spec_file.read_text(encoding='utf-8').replace(
            'F001-AC01 Save a name\n', 'F001-AC01 Save a name\n      `判: stores 40 characters`\n')
        spec_file.write_text(source, encoding='utf-8')
        self.assertEqual(self.invoke('seal', '--draft', self.draft).returncode, 0)
        path = self.root / DEFAULT_PLAN
        original = json.loads(path.read_bytes())
        self.assertEqual(original['schema_version'], 2)
        self.assertRegex(original['criteria'][0]['criterion_sha256'], r'^[a-f0-9]{64}$')
        self.approve()
        receipt = self.receipt('full-criterion', ['save', 'read'], {'save': 'PASS', 'read': 'PASS'})
        report = self.report(self.check('behavior', '--run', receipt), 0)
        spec_file.write_text(source.replace('stores 40 characters', 'stores 41 characters'), encoding='utf-8')
        stale = self.check('behavior', '--run', receipt)
        self.assertEqual(stale.returncode, 2)
        self.assertIn('acceptance plan is stale', stale.stderr)
        with self.assertRaisesRegex(ValueError, 'acceptance plan is stale'):
            replay_behavior(self.root, report)
        self.assertEqual(json.loads(path.read_bytes()), original)

    def test_legacy_title_only_plan_remains_readable(self):
        path = self.root / DEFAULT_PLAN
        legacy = json.loads(path.read_bytes())
        legacy['schema_version'] = 1
        for row in legacy['criteria']:
            del row['criterion_sha256']
        self.save_json(DEFAULT_PLAN, legacy)
        self.approve()
        receipt = self.receipt('legacy-criterion', ['save', 'read'], {'save': 'PASS', 'read': 'PASS'})
        report = self.report(self.check('behavior', '--run', receipt), 0)
        self.assertEqual(replay_behavior(self.root, report), report)
        self.assertEqual(json.loads(path.read_bytes()), legacy)

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.hap = self.root / 'signed.hap'
        self.hap.write_bytes(b'first package')
        self.save('spec/baseline/features/feat_001_demo.md',
                  '# F001 Demo\n## Acceptance Criteria\n'
                  '- [ ] F001-AC01 Save a name\n- [ ] F001-AC02 Read saved name\n')
        self.save('spec/baseline/plans/slices/slice-01.md', 'feature_id: F001\n')
        self.draft = self.save_json('bindings.json', {'schema_version': 1, 'bindings': [
            {'requirement_id': f'F001-AC0{index}', 'scenario': case, 'assertions': [{
                'step': 'visible', 'layout': f'{case}.json', 'present': [{'text': 'Saved name'}],
            }]} for index, case in enumerate(('save', 'read'), start=1)
        ]})
        result = self.invoke('seal', '--draft', self.draft)
        self.assertEqual(result.returncode, 0, result.stderr)

    def save(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
        return path

    def save_json(self, name, data):
        return self.save(name, json.dumps(data))

    def approve(self):
        path = self.root / DEFAULT_PLAN
        digest = sha256(path.read_bytes()).hexdigest()
        self.assertFalse(approved_plan(self.root, path, digest))
        from marker_contract import write_marker

        write_marker(self.root / PLAN_MARKER, 'i2h-plan', [path], 'a' * 64, root=self.root)

    def receipt(self, name, planned, statuses, **metadata):
        for case, status in statuses.items():
            if status == 'PASS':
                self.save_json(f'{name}/{case}.json', {
                    'attributes': {'visible': 'true', 'text': 'Saved name'}, 'children': [],
                })
        return self.save_json(f'{name}/results.json', {
            'hap_sha256': sha256(self.hap.read_bytes()).hexdigest(), 'device': 'test-device',
            'runner_sha256': 'b' * 64, 'fixture_sha256': 'c' * 64, 'planned_cases': planned,
            'cases': {case: {'status': status, 'passed_steps': ['visible']} for case, status in statuses.items()},
            **metadata,
        })

    def invoke(self, mode, *args):
        return subprocess.run(
            [sys.executable, '-I', '-B', str(SCRIPTS / 'acceptance_plan.py'),
             '--project-root', str(self.root), mode, *map(str, args)],
            cwd=self.root, capture_output=True, encoding='utf-8', timeout=20,
        )

    def check(self, mode, *args, device='test-device'):
        return self.invoke(mode, '--signed-hap', self.hap, '--device', device, *args)

    def report(self, result, exit_code):
        self.assertEqual(result.returncode, exit_code, result.stderr)
        return json.loads((self.root / 'spec/verify/check5/behavior-summary.json').read_bytes())

    def test_hypium_preview_requires_matching_packages_and_per_case_outcome(self):
        test_hap = self.root / 'test.hap'
        test_hap.write_bytes(b'signed test package')
        draft = self.save_json('hypium-bindings.json', {'schema_version': 1, 'bindings': [
            {'requirement_id': f'F001-AC0{i}', 'suite': 'Contract', 'test': name}
            for i, name in enumerate(('save', 'read'), 1)
        ]})
        log = ''
        for name, result in (('save', 0), ('read', -2)):
            for code in (1, result):
                log += (f'OHOS_REPORT_STATUS: class=Contract\nOHOS_REPORT_STATUS: test={name}\n'
                        f'OHOS_REPORT_STATUS_CODE: {code}\n')
        summary = 'OHOS_REPORT_RESULT: stream=Tests run: 2, Failure: 1, Error: 0, Pass: 1, Ignore: 0\n'
        log += summary + 'TestFinished-ResultCode: 0\n'
        path = self.save('hypium/hypium.log', log)
        metadata = {'app_hap_sha256': sha256(self.hap.read_bytes()).hexdigest(),
                    'test_hap_sha256': sha256(test_hap.read_bytes()).hexdigest(),
                    'device': 'test-device', 'exit_code': 0, 'log_sha256': sha256(path.read_bytes()).hexdigest()}
        receipt = self.save_json('hypium/results.json', metadata)
        args = ['--run', receipt, '--draft', draft, '--signed-test-hap', test_hap]
        result = self.check('evaluate-hypium', *args)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['counts'], {'DIRECT_EVIDENCE': 1, 'UNVERIFIED': 1})
        mixed = json.loads(self.draft.read_bytes())
        mixed['bindings'][1] = {'requirement_id': 'F001-AC02', 'hypium': {'suite': 'Contract', 'test': 'save'}}
        self.draft.write_text(json.dumps(mixed), encoding='utf-8')
        self.assertEqual(self.invoke('seal', '--draft', self.draft).returncode, 0)
        ui = self.receipt('ui', ['save'], {'save': 'PASS'})
        behavior = ['--run', ui, '--hypium-run', receipt, '--signed-test-hap', test_hap]
        preview = self.check('evaluate', '--draft', self.draft, *behavior)
        self.assertEqual(preview.returncode, 0, preview.stderr)
        self.assertEqual(json.loads(preview.stdout)['counts'], {'DIRECT_EVIDENCE': 2})
        self.assertFalse((self.root / 'spec/verify/check5').exists())
        hybrid = json.loads(self.draft.read_bytes())
        hybrid['bindings'][0]['hypium'] = {'suite': 'Contract', 'test': 'save'}
        self.draft.write_text(json.dumps(hybrid), encoding='utf-8')
        hybrid_report = self.check('evaluate', '--draft', self.draft, *behavior)
        self.assertEqual(hybrid_report.returncode, 0, hybrid_report.stderr)
        self.assertEqual(json.loads(hybrid_report.stdout)['counts'], {'DIRECT_EVIDENCE': 2})
        without_hypium = self.check('evaluate', '--draft', self.draft, '--run', ui)
        self.assertEqual(json.loads(without_hypium.stdout)['counts'], {'UNVERIFIED': 2})
        (ui.parent / 'save.json').unlink()
        without_ui = self.check('evaluate', '--draft', self.draft, *behavior)
        self.assertEqual(json.loads(without_ui.stdout)['counts'], {'UNVERIFIED': 1, 'DIRECT_EVIDENCE': 1})
        self.save_json('ui/save.json', {'attributes': {'visible': 'true', 'text': 'Saved name'}, 'children': []})
        self.draft.write_text(json.dumps(mixed), encoding='utf-8')
        partial = self.check('evaluate', '--draft', self.draft, '--run', ui, '--hypium-run', receipt)
        self.assertIn('requires both', partial.stderr)
        self.assertEqual(self.report(self.check('behavior', *behavior), 1)['counts']['criteria'], {'NO_BINDING': 2})
        self.approve()
        self.assertEqual(self.report(self.check('behavior', '--run', ui), 1)['status'], 'INCOMPLETE')
        mixed_report = self.report(self.check('behavior', *behavior), 0)
        self.assertEqual(mixed_report['counts']['criteria'], {'DIRECT_EVIDENCE': 2})
        self.assertEqual(replay_behavior(self.root, mixed_report), mixed_report)
        mixed['bindings'][1]['hypium']['test'] = 'read'
        self.draft.write_text(json.dumps(mixed), encoding='utf-8')
        self.assertEqual(self.invoke('seal', '--draft', self.draft).returncode, 0)
        self.approve()
        failed = self.report(self.check('behavior', *behavior), 1)
        self.assertEqual(failed['status'], 'FAIL')
        self.assertEqual(failed['criteria'][1]['test_status'], 'FAIL')
        path.write_text(log.replace('Failure: 1', 'Failure: 0'), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'log digest mismatch'):
            replay_behavior(self.root, mixed_report)
        self.assertIn('log digest mismatch', self.check('evaluate-hypium', *args).stderr)
        metadata['log_sha256'] = sha256(path.read_bytes()).hexdigest()
        self.save_json('hypium/results.json', metadata)
        self.assertIn('cases disagree', self.check('evaluate-hypium', *args).stderr)
        test_hap.write_bytes(b'new test package')
        self.assertIn('does not match the packages', self.check('evaluate-hypium', *args).stderr)

    def test_full_pass_requires_an_approved_plan_and_visible_assertions(self):
        receipt = self.receipt('full', ['save', 'read'], {'save': 'PASS', 'read': 'PASS'})
        self.assertEqual(self.report(self.check('behavior', '--run', receipt), 1)['counts']['criteria'],
                         {'NO_BINDING': 2})
        self.approve()
        report = self.report(self.check('behavior', '--run', receipt), 0)
        self.assertEqual(report['counts'], {'criteria': {'DIRECT_EVIDENCE': 2}, 'scenarios': {'PASS': 2}})
        (receipt.parent / 'read.json').unlink()
        report = self.report(self.check('behavior', '--run', receipt), 1)
        self.assertEqual(report['counts']['criteria'], {'DIRECT_EVIDENCE': 1, 'UNVERIFIED': 1})
        self.assertEqual(report['criteria'][1]['issues'], [
            {'code': 'LAYOUT_MISSING', 'step': 'visible', 'layout': 'read.json'},
        ])
        self.assertFalse((self.root / 'spec/verify-report.md').exists())

    def test_unverified_criterion_explains_failed_step_and_layout(self):
        self.approve()
        receipt = self.receipt('diagnostic', ['save', 'read'], {'save': 'PASS', 'read': 'PASS'})
        data = json.loads(receipt.read_bytes())
        data['cases']['read']['passed_steps'] = []
        receipt.write_text(json.dumps(data), encoding='utf-8')
        self.save('diagnostic/save.json', 'invalid JSON')
        report = self.report(self.check('behavior', '--run', receipt), 1)
        self.assertEqual([row['issues'][0]['code'] for row in report['criteria']],
                         ['LAYOUT_INVALID', 'STEP_MISSING'])
        self.save_json('diagnostic/save.json', {'attributes': {'visible': 'true', 'text': 'wrong'}, 'children': []})
        report = self.report(self.check('behavior', '--run', receipt), 1)
        self.assertEqual(report['criteria'][0]['issues'][0]['code'], 'LAYOUT_ASSERTION_FAILED')

    def test_draft_preview_evaluates_without_writing_plan_or_verify_reports(self):
        original = (self.root / DEFAULT_PLAN).read_bytes()
        receipt = self.receipt('preview', ['save', 'read'], {'save': 'PASS'})
        result = self.check('evaluate', '--draft', self.draft, '--run', receipt)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report['plan_status'], 'DRAFT')
        self.assertEqual(report['counts'], {'DIRECT_EVIDENCE': 1, 'UNVERIFIED': 1})
        self.assertEqual((self.root / DEFAULT_PLAN).read_bytes(), original)
        self.assertFalse((self.root / 'spec/verify').exists())
        self.assertFalse((self.root / PLAN_MARKER).exists())

    def test_same_build_recheck_uses_latest_failure_or_unrun_result(self):
        self.approve()
        first = self.receipt('first', ['save', 'read'], {'save': 'PASS', 'read': 'PASS'})
        failed = self.receipt('failed', ['save'], {'save': 'FAIL'})
        report = self.report(self.check('behavior', '--run', first, '--run', failed, '--case', 'save'), 1)
        self.assertEqual(report['status'], 'FAIL')
        self.assertEqual(report['counts'], {
            'criteria': {'UNVERIFIED': 1, 'DIRECT_EVIDENCE': 1}, 'scenarios': {'FAIL': 1, 'PASS': 1},
        })
        self.assertEqual(report['criteria'][0]['issues'], [{'code': 'SCENARIO_NOT_PASSED', 'status': 'FAIL'}])
        legacy = self.check('evaluate', '--run', first, '--run', failed)
        self.assertEqual(legacy.returncode, 0, legacy.stderr)
        self.assertEqual(json.loads(legacy.stdout), report['counts']['criteria'])
        unrun = self.receipt('unrun', ['read'], {})
        report = self.report(self.check('behavior', '--run', first, '--run', unrun, '--case', 'read'), 1)
        self.assertEqual(report['counts']['scenarios'], {'PASS': 1, 'NOT_RUN': 1})

    def test_behavior_keeps_system_window_context_in_interrupted_run(self):
        receipt = self.receipt('interrupted', ['save', 'read'], {'save': 'ERROR'})
        data = json.loads(receipt.read_bytes())
        windows = [{'bundle': 'ime', 'page': 'pages/permission/StartupPage'}]
        data['cases']['save']['focused_windows'] = windows
        receipt.write_text(json.dumps(data), encoding='utf-8')
        report = self.report(self.check('behavior', '--run', receipt), 1)
        self.assertEqual(report['status'], 'INCOMPLETE')
        self.assertEqual(report['counts']['scenarios'], {'ERROR': 1, 'NOT_RUN': 1})
        self.assertEqual(report['scenarios'][0]['focused_windows'], windows)

    def test_fixture_recovery_preserves_failure_and_next_scenario_outcome(self):
        receipt = self.receipt('recovered', ['save', 'read'], {'save': 'FAIL', 'read': 'PASS'})
        data = json.loads(receipt.read_bytes())
        data['cases']['save']['fixture_recovery'] = {'status': 'PASS'}
        receipt.write_text(json.dumps(data), encoding='utf-8')
        report = self.report(self.check('behavior', '--run', receipt), 1)
        self.assertEqual(report['counts']['scenarios'], {'FAIL': 1, 'PASS': 1})
        self.assertEqual(report['scenarios'][0]['fixture_recovery'], {'status': 'PASS'})

    def test_cross_scenario_assertions_require_both_steps_in_matching_receipts(self):
        draft = json.loads(self.draft.read_bytes())
        draft['bindings'] = draft['bindings'][:1]
        first_assertion = draft['bindings'][0]['assertions'][0]
        first_assertion['step'] = 'saved_4.5'
        draft['bindings'][0]['assertions'].append({
            **first_assertion, 'scenario': 'read', 'step': 'reloaded', 'layout': 'read.json',
        })
        self.draft.write_text(json.dumps(draft), encoding='utf-8')
        self.assertEqual(self.invoke('seal', '--draft', self.draft).returncode, 0)
        self.approve()
        first = self.receipt('first', ['save'], {'save': 'PASS'})
        second = self.receipt('second', ['read'], {'read': 'PASS'})
        for path, name, step in ((first, 'save', 'saved_4.5'), (second, 'read', 'reloaded')):
            run = json.loads(path.read_bytes())
            run['cases'][name]['passed_steps'] = [step]
            path.write_text(json.dumps(run), encoding='utf-8')
        missing = self.report(self.check('behavior', '--run', first), 1)
        self.assertTrue(any(row['scenario'] == 'read' and row['status'] == 'NOT_RUN'
                            for row in missing['scenarios']))
        report = self.report(self.check('behavior', '--run', first, '--run', second), 1)
        self.assertEqual(report['counts']['criteria'], {'DIRECT_EVIDENCE': 1, 'NO_BINDING': 1})
        self.assertEqual(report['criteria'][0]['evidence'][1]['run'], report['runs'][1])
        (second.parent / 'read.json').unlink()
        report = self.report(self.check('behavior', '--run', first, '--run', second), 1)
        self.assertEqual(report['criteria'][0]['issues'][0]['code'], 'LAYOUT_MISSING')
        run = json.loads(second.read_bytes())
        run['fixture_sha256'] = 'd' * 64
        second.write_text(json.dumps(run), encoding='utf-8')
        evaluated = self.check('evaluate', '--run', first, '--run', second, '--draft', self.draft)
        self.assertEqual(evaluated.returncode, 2)
        self.assertIn('runner or fixture context mismatch', evaluated.stderr)

    def test_fixture_setup_failure_remains_visible_without_crediting_any_cases(self):
        receipt = self.receipt('fixture-failed', ['save', 'read'], {})
        data = json.loads(receipt.read_bytes())
        data['fixture_setup'] = {'status': 'FAIL', 'reason': 'expected seeded recipe'}
        receipt.write_text(json.dumps(data), encoding='utf-8')
        report = self.report(self.check('behavior', '--run', receipt), 1)
        self.assertEqual(report['counts']['scenarios'], {'NOT_RUN': 2})
        self.assertEqual(report['fixture_setup'], [
            {'run': report['runs'][0], 'status': 'FAIL', 'reason': 'expected seeded recipe'}])
        data['cases']['save'] = {'status': 'PASS'}
        receipt.write_text(json.dumps(data), encoding='utf-8')
        result = self.check('behavior', '--run', receipt)
        self.assertEqual(result.returncode, 2)
        self.assertIn('invalid fixture setup receipt', result.stderr)

    def test_device_capability_block_preserves_scope_and_does_not_credit_ac(self):
        self.approve()
        receipt = self.receipt('blocked', ['save', 'read'], {'save': 'BLOCKED', 'read': 'PASS'})
        data = json.loads(receipt.read_bytes())
        data['cases']['save'].update(device_capability='rear_camera_yuv_preview', reason='no YUV preview')
        receipt.write_text(json.dumps(data), encoding='utf-8')
        report = self.report(self.check('behavior', '--run', receipt), 1)
        self.assertEqual(report['status'], 'INCOMPLETE')
        self.assertEqual(report['counts']['scenarios'], {'BLOCKED': 1, 'PASS': 1})
        self.assertEqual(report['counts']['criteria'], {'UNVERIFIED': 1, 'DIRECT_EVIDENCE': 1})
        self.assertEqual(report['scenarios'][0]['device_capability'], 'rear_camera_yuv_preview')
        self.assertEqual(report['scenarios'][0]['reason'], 'no YUV preview')

    def test_failure_diagnostics_distinguish_failed_service_and_blocked_hardware(self):
        self.approve()
        receipt = self.receipt('ocr', ['save', 'read'], {'save': 'FAIL', 'read': 'BLOCKED'})
        data = json.loads(receipt.read_bytes())
        recognition = {'stage': 'recognition', 'code': '1001400001'}
        camera_setup = {'stage': 'camera_setup'}
        data['cases']['save']['failure_diagnostic'] = recognition
        data['cases']['read'].update(device_capability='rear_camera_yuv_preview', failure_diagnostic=camera_setup)
        receipt.write_text(json.dumps(data), encoding='utf-8')
        report = self.report(self.check('behavior', '--run', receipt), 1)
        self.assertEqual(report['counts']['scenarios'], {'FAIL': 1, 'BLOCKED': 1})
        self.assertEqual(report['counts']['criteria'], {'UNVERIFIED': 2})
        self.assertEqual([row['failure_diagnostic'] for row in report['scenarios']], [recognition, camera_setup])
        self.assertEqual(report['scenarios'][1]['device_capability'], 'rear_camera_yuv_preview')
        data['cases']['save']['status'] = 'PASS'
        receipt.write_text(json.dumps(data), encoding='utf-8')
        self.assertEqual(self.check('behavior', '--run', receipt).returncode, 2)

    def test_device_preflight_preserves_model_and_reference_in_behavior_report(self):
        self.approve()
        receipt = self.receipt('device-preflight', ['save', 'read'], {'save': 'BLOCKED', 'read': 'PASS'})
        data = json.loads(receipt.read_bytes())
        diagnostic = {'stage': 'device_preflight', 'device_model': 'emulator',
                      'reference': 'https://developer.huawei.com/consumer/en/doc/doccenter-capabilities/core-vision-introduction/'}
        case = data['cases']['save']
        case.update(device_capability='core_vision_ocr', failure_diagnostic=diagnostic)
        receipt.write_text(json.dumps(data), encoding='utf-8')
        report = self.report(self.check('behavior', '--run', receipt), 1)
        self.assertEqual(report['status'], 'INCOMPLETE')
        self.assertEqual(report['counts']['scenarios'], {'BLOCKED': 1, 'PASS': 1})
        self.assertEqual(report['scenarios'][0]['failure_diagnostic'], diagnostic)
        self.assertEqual(report['counts']['criteria'], {'UNVERIFIED': 1, 'DIRECT_EVIDENCE': 1})
        for invalid in ({**diagnostic, 'stage': 'recognition'}, {**diagnostic, 'reference': 'file:///tmp/doc'},
                        {**diagnostic, 'device_model': ''}):
            case['failure_diagnostic'] = invalid
            receipt.write_text(json.dumps(data), encoding='utf-8')
            self.assertEqual(self.check('behavior', '--run', receipt).returncode, 2)

    def test_package_input_is_rehashed_from_the_signed_hap(self):
        self.approve()
        member = 'resources/rawfile/example.png'
        image = b'known OCR input'
        with ZipFile(self.hap, 'w') as package:
            package.writestr(member, image)
        receipt = self.receipt('ocr-input', ['save', 'read'], {'save': 'FAIL', 'read': 'BLOCKED'})
        data = json.loads(receipt.read_bytes())
        case = data['cases']['save']
        evidence = {'member': member, 'sha256': sha256(image).hexdigest()}
        case.update(package_input=evidence, failure_diagnostic={'stage': 'recognition', 'code': '1001400001'})
        receipt.write_text(json.dumps(data), encoding='utf-8')
        report = self.report(self.check('behavior', '--run', receipt), 1)
        self.assertEqual(report['scenarios'][0]['package_input'], evidence)
        self.assertEqual(report['counts']['scenarios'], {'FAIL': 1, 'BLOCKED': 1})
        for changed, diagnostic in [
            ({'sha256': '0' * 64}, 'signed package input digest mismatch'),
            ({'member': 'resources/rawfile/absent.png'}, 'invalid signed package input'),
            ({'member': '../example.png'}, 'invalid package input receipt'),
        ]:
            with self.subTest(changed=changed):
                case['package_input'] = {**evidence, **changed}
                receipt.write_text(json.dumps(data), encoding='utf-8')
                result = self.check('behavior', '--run', receipt)
                self.assertEqual(result.returncode, 2)
                self.assertIn(diagnostic, result.stderr)

    def test_scenario_fixture_failure_preserves_independent_pass_and_blocks_credit(self):
        self.approve()
        receipt = self.receipt('case-fixture', ['save', 'read'], {'read': 'PASS'})
        data = json.loads(receipt.read_bytes())
        setup = {'status': 'FAIL', 'reason': 'previous step did not create the required record'}
        data['case_fixture_setup'] = {'save': setup}
        receipt.write_text(json.dumps(data), encoding='utf-8')
        report = self.report(self.check('behavior', '--run', receipt), 1)
        self.assertEqual(report['status'], 'INCOMPLETE')
        self.assertEqual(report['counts']['scenarios'], {'NOT_RUN': 1, 'PASS': 1})
        self.assertEqual(report['counts']['criteria'], {'UNVERIFIED': 1, 'DIRECT_EVIDENCE': 1})
        self.assertEqual(report['scenarios'][0]['fixture_setup'], setup)

        data['cases']['save'] = {'status': 'PASS'}
        receipt.write_text(json.dumps(data), encoding='utf-8')
        self.assertEqual(self.check('behavior', '--run', receipt).returncode, 2)
        del data['cases']['save']
        data['case_fixture_setup'] = {'out_of_scope': setup}
        receipt.write_text(json.dumps(data), encoding='utf-8')
        self.assertEqual(self.check('behavior', '--run', receipt).returncode, 2)

    def test_viewport_assertion_rejects_clipping_overlap_and_missing_overlay_evidence(self):
        draft = json.loads(self.draft.read_bytes())
        assertion = draft['bindings'][0]['assertions'][0]
        assertion.update(fully_visible=assertion['present'], obstructions=[{'id': 'keyboard'}])
        self.draft.write_text(json.dumps(draft), encoding='utf-8')
        self.assertEqual(self.invoke('seal', '--draft', self.draft).returncode, 0)
        self.approve()
        receipt = self.receipt('viewport', ['save', 'read'], {'save': 'PASS', 'read': 'PASS'})

        def node(**attributes):
            return {'attributes': {'visible': 'true', **attributes}, 'children': []}

        target = node(text='Saved name', bounds='[0,20][40,40]', origBounds='[0,20][40,40]')
        keyboard = node(id='keyboard', bounds='[0,60][100,100]')
        bar = node(type='TabBar', bounds='[0,80][100,100]')
        tree = node(bounds='[0,0][100,100]')
        tree['children'] = [target, keyboard, bar]

        def replay(expected):
            self.save_json('viewport/save.json', tree)
            report = self.report(self.check('behavior', '--run', receipt), 0 if expected is None else 1)
            criterion = report['criteria'][0]
            if expected is None:
                self.assertEqual(criterion['status'], 'DIRECT_EVIDENCE')
            else:
                self.assertEqual(criterion['issues'][0]['code'], expected)

        replay(None)
        target['attributes']['origBounds'] = '[0,20][40,70]'
        replay('CONTROL_NOT_FULLY_VISIBLE')
        target['attributes']['bounds'] = '[0,20][40,70]'
        replay('CONTROL_NOT_FULLY_VISIBLE')
        keyboard['attributes']['bounds'] = '[50,60][100,100]'
        bar['attributes']['bounds'] = '[0,65][100,100]'
        replay('CONTROL_NOT_FULLY_VISIBLE')
        keyboard['attributes']['visible'] = 'false'
        replay('OBSTRUCTION_NOT_OBSERVED')

    def test_transport_timeout_keeps_completed_and_unrun_scenarios(self):
        receipt = self.receipt('timeout', ['save', 'read', 'next'], {'save': 'PASS', 'read': 'ERROR'})
        data = json.loads(receipt.read_bytes())
        data['cases']['read']['device_timeout'] = {'seconds': 35}
        receipt.write_text(json.dumps(data), encoding='utf-8')
        report = self.report(self.check('behavior', '--run', receipt), 1)
        self.assertEqual(report['counts']['scenarios'], {'PASS': 1, 'ERROR': 1, 'NOT_RUN': 1})
        self.assertEqual(report['scenarios'][1]['device_timeout'], {'seconds': 35})

    def test_selected_parent_must_contain_the_target_label(self):
        draft = json.loads(self.draft.read_bytes())
        assertion = draft['bindings'][0]['assertions'][0]
        assertion['present'] = []
        assertion['descendants'] = [{'ancestor': {'type': 'Column', 'selected': 'true'},
                                     'descendant': {'text': 'Saved name'}}]
        self.draft.write_text(json.dumps(draft), encoding='utf-8')
        sealed = self.invoke('seal', '--draft', self.draft)
        self.assertEqual(sealed.returncode, 0, sealed.stderr)
        self.approve()
        receipt = self.receipt('tabs', ['save', 'read'], {'save': 'PASS', 'read': 'PASS'})

        def node(attributes, *children):
            return {'attributes': {'visible': 'true', **attributes}, 'children': children}

        title = node({'text': 'Saved name'})
        selected = {'type': 'Column', 'selected': 'true'}
        self.save_json('tabs/save.json', node({}, node(selected), title))
        self.assertEqual(self.report(self.check('behavior', '--run', receipt), 1)['counts']['criteria'],
                         {'UNVERIFIED': 1, 'DIRECT_EVIDENCE': 1})
        self.save_json('tabs/save.json', node({}, node(selected, title)))
        self.assertEqual(self.report(self.check('behavior', '--run', receipt), 0)['counts']['criteria'],
                         {'DIRECT_EVIDENCE': 2})

    def test_grouped_fields_require_one_visible_row(self):
        draft = json.loads(self.draft.read_bytes())
        assertion = draft['bindings'][0]['assertions'][0]
        assertion['present'] = []
        assertion['within'] = [{'ancestor': {'type': 'Row', 'clickable': 'true'},
                                'present': [{'text': 'Saved name'}, {'text': '5'}]}]
        self.draft.write_text(json.dumps(draft), encoding='utf-8')
        sealed = self.invoke('seal', '--draft', self.draft)
        self.assertEqual(sealed.returncode, 0, sealed.stderr)
        self.approve()
        receipt = self.receipt('rows', ['save', 'read'], {'save': 'PASS', 'read': 'PASS'})

        def node(attributes, *children):
            return {'attributes': {'visible': 'true', **attributes}, 'children': children}

        row = {'type': 'Row', 'clickable': 'true'}
        name, rating = node({'text': 'Saved name'}), node({'text': '5'})
        for tree in (node({}, node(row, name), node(row, rating)),
                     node({}, node(row, name, node({'visible': 'false'}, rating)))):
            self.save_json('rows/save.json', tree)
            self.assertEqual(self.report(self.check('behavior', '--run', receipt), 1)['counts']['criteria'],
                             {'UNVERIFIED': 1, 'DIRECT_EVIDENCE': 1})
        self.save_json('rows/save.json', node({}, node(row, name, rating)))
        self.assertEqual(self.report(self.check('behavior', '--run', receipt), 0)['counts']['criteria'],
                         {'DIRECT_EVIDENCE': 2})

    def test_theme_choice_and_rendered_background_are_both_required(self):
        draft = json.loads(self.draft.read_bytes())
        draft['bindings'][0]['assertions'][0]['present'] = [
            {'type': 'Select', 'text': '深色'}, {'type': 'Column', 'backgroundColor': '#FF211B18'}]
        self.draft.write_text(json.dumps(draft), encoding='utf-8')
        sealed = self.invoke('seal', '--draft', self.draft)
        self.assertEqual(sealed.returncode, 0, sealed.stderr)
        self.approve()
        receipt = self.receipt('theme', ['save', 'read'], {'save': 'PASS', 'read': 'PASS'})
        select = {'attributes': {'type': 'Select', 'text': '深色', 'visible': 'true'}, 'children': []}
        for color, exit_code in (('#FFF6F2EB', 1), ('#FF211B18', 0)):
            self.save_json('theme/save.json', {'attributes': {
                'type': 'Column', 'backgroundColor': color, 'visible': 'true'}, 'children': [select]})
            self.report(self.check('behavior', '--run', receipt), exit_code)

    def test_rebuild_preserves_scope_and_rejects_previous_package_or_wrong_device(self):
        self.approve()
        first = self.receipt('first', ['save', 'read'], {'save': 'PASS', 'read': 'PASS'})
        self.hap.write_bytes(b'rebuilt package')
        latest = self.receipt('latest', ['save'], {'save': 'PASS'})
        args = ['--baseline', first, '--case', 'save', '--run', latest]
        report = self.report(self.check('behavior', *args), 1)
        self.assertEqual(report['counts'], {
            'criteria': {'DIRECT_EVIDENCE': 1, 'UNVERIFIED': 1}, 'scenarios': {'PASS': 1, 'NOT_RUN': 1},
        })
        self.assertEqual(report['scenario_total'], 2)
        wrong_device = self.check('behavior', *args, device='wrong-device')
        wrong_hap = self.check('behavior', '--run', first, '--run', latest)
        for result in (wrong_device, wrong_hap):
            self.assertEqual(result.returncode, 2)
            self.assertIn('device or signed package mismatch', result.stderr)

    def test_cannot_combine_changed_fixtures_or_shrink_the_recheck_scope(self):
        first = self.receipt('first', ['save', 'read'], {'save': 'PASS'})
        changed = self.receipt('changed', ['save'], {'save': 'PASS'}, fixture_sha256='d' * 64)
        result = self.check('behavior', '--run', first, '--run', changed)
        self.assertEqual(result.returncode, 2)
        self.assertIn('runner or fixture context mismatch', result.stderr)
        result = self.check('behavior', '--run', changed, '--case', 'save')
        self.assertEqual(result.returncode, 2)
        self.assertIn('requires the first full runner receipt', result.stderr)

    def test_strict_resume_replays_machine_evidence_and_rejects_changed_layout(self):
        from pipeline_resume import pipeline_status

        self.approve()
        receipt = self.receipt('full', ['save', 'read'], {'save': 'PASS', 'read': 'PASS'})
        result = self.check('behavior', '--run', receipt)
        self.assertEqual(result.returncode, 0, result.stderr)
        digest = json.loads(result.stdout)['report_sha256']
        rows = '\n'.join(f'| CHECK-{n} | Check | PASS |' for n in range(1, 6))
        self.save('spec/verify-report.md', rows + '\n')
        check = pipeline_status(self.root, require_behavior=True)['verification']
        self.assertIn('behavior_receipt_unbound', check['errors'])
        self.save('spec/verify-report.md', f'{rows}\n\nbehavior-summary-sha256: {digest}\n')
        self.assertTrue(pipeline_status(self.root, require_behavior=True)['verification']['complete'])
        from unittest.mock import patch

        with patch('pipeline_resume._bound_visual', return_value={
            'hap_sha256': sha256(self.hap.read_bytes()).hexdigest(), 'device': 'another-device',
        }):
            outcome = pipeline_status(self.root, require_behavior=True, require_bound_visual=True)['verification']
        self.assertIn('behavior_visual_installation_mismatch', outcome['errors'])
        self.assertEqual(outcome['unpassed_checks']['CHECK-5'], 'UNVERIFIED')

        self.save_json('full/read.json', {'attributes': {'visible': 'true', 'text': 'Changed'}, 'children': []})
        check = pipeline_status(self.root, require_behavior=True)['verification']
        self.assertFalse(check['complete'])
        self.assertEqual(check['unpassed_checks']['CHECK-5'], 'UNVERIFIED')
        self.assertIn('behavior_receipt_stale', check['errors'])


if __name__ == '__main__':
    unittest.main()
