from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

from acceptance_plan import DEFAULT_PLAN, PLAN_MARKER, approved_plan


class AcceptancePlanTest(unittest.TestCase):
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
            [sys.executable, '-B', str(SCRIPTS / 'acceptance_plan.py'),
             '--project-root', str(self.root), mode, *map(str, args)],
            cwd=self.root, capture_output=True, encoding='utf-8', timeout=20,
        )

    def check(self, mode, *args, device='test-device'):
        return self.invoke(mode, '--signed-hap', self.hap, '--device', device, *args)

    def report(self, result, exit_code):
        self.assertEqual(result.returncode, exit_code, result.stderr)
        return json.loads((self.root / 'spec/verify/check5/behavior-summary.json').read_bytes())

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
        self.assertFalse((self.root / 'spec/verify-report.md').exists())

    def test_same_build_recheck_uses_latest_failure_or_unrun_result(self):
        self.approve()
        first = self.receipt('first', ['save', 'read'], {'save': 'PASS', 'read': 'PASS'})
        failed = self.receipt('failed', ['save'], {'save': 'FAIL'})
        report = self.report(self.check('behavior', '--run', first, '--run', failed, '--case', 'save'), 1)
        self.assertEqual(report['status'], 'FAIL')
        self.assertEqual(report['counts'], {
            'criteria': {'UNVERIFIED': 1, 'DIRECT_EVIDENCE': 1}, 'scenarios': {'FAIL': 1, 'PASS': 1},
        })
        legacy = self.check('evaluate', '--run', first, '--run', failed)
        self.assertEqual(legacy.returncode, 0, legacy.stderr)
        self.assertEqual(json.loads(legacy.stdout), report['counts']['criteria'])
        unrun = self.receipt('unrun', ['read'], {})
        report = self.report(self.check('behavior', '--run', first, '--run', unrun, '--case', 'read'), 1)
        self.assertEqual(report['counts']['scenarios'], {'PASS': 1, 'NOT_RUN': 1})

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
        self.save_json('full/read.json', {'attributes': {'visible': 'true', 'text': 'Changed'}, 'children': []})
        check = pipeline_status(self.root, require_behavior=True)['verification']
        self.assertFalse(check['complete'])
        self.assertEqual(check['unpassed_checks']['CHECK-5'], 'UNVERIFIED')
        self.assertIn('behavior_receipt_stale', check['errors'])


if __name__ == '__main__':
    unittest.main()
