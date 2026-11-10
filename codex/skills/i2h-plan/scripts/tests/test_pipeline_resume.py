import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[2] / 'bin/scripts/pipeline'))

from marker_contract import write_marker
import pipeline_resume


class PipelineResumeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        target = self.root / 'spec/.i2h/target-input.json'
        target.parent.mkdir(parents=True)
        target.write_text(json.dumps({'target_input_sha256': 'a' * 64}), encoding='utf-8')
        self.target = 'a' * 64

    def tearDown(self):
        self.tmp.cleanup()

    def marker(self, rel, stage, artifacts=()):
        path = self.root / rel
        for artifact in artifacts:
            p = self.root / artifact
            if not p.exists():
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text('artifact', encoding='utf-8')
        return write_marker(path, stage, artifacts, self.target, root=self.root)

    def delivery(self, status='approved', target=None, duplicate=False):
        units = [
            {'unit_id': 'home', 'owned_ui_roles': ['content'],
             'required_states': [{'state_id': 'home', 'arrival_mode': 'preview', 'responsibility': 'content'}],
             'output': {'file': 'entry/src/main/ets/pages/Home.ets'}},
        ]
        if duplicate:
            units.append({'unit_id': 'detail', 'owned_ui_roles': ['content'],
                           'required_states': [{'state_id': 'home', 'arrival_mode': 'preview', 'responsibility': 'content'}],
                           'output': {'file': 'entry/src/main/ets/pages/Detail.ets'}})
        path = self.root / 'spec/baseline/ui-delivery-approved.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({'schema_version': 2, 'status': status,
                                    'target_input_sha256': self.target if target is None else target,
                                    'units': units}), encoding='utf-8')

    def test_canonical_markers_and_delivery_complete(self):
        self.marker('spec/baseline/spec-complete.txt', 'i2h-spec', ['spec/.i2h/resources-inventory.json'])
        self.delivery()
        self.marker('spec/baseline/plans/complete.txt', 'i2h-plan', ['spec/baseline/ui-delivery-approved.json'])
        (self.root / 'spec/migration-report.md').write_text('mode: static-only\nbuild: DEFERRED\n', encoding='utf-8')
        self.marker('spec/execution/stage5-complete.txt', 'i2h-execute', [
            'spec/migration-report.md', 'entry/src/main/ets/Home.ets',
        ])
        ownership = self.root / 'spec/execution/ui-state-ownership.json'
        ownership.parent.mkdir(parents=True, exist_ok=True)
        ownership.write_text(json.dumps({
            'schema_version': 1, 'status': 'PASS', 'errors': [],
            'warnings': [{'code': 'VERIFICATION_STATES_EMPTY', 'message': 'full_ui inventory has no composition verification states yet'}],
            'owners': {'__global__::home::content': 'home'},
        }), encoding='utf-8')
        (self.root / 'spec/verify-report.md').parent.mkdir(parents=True, exist_ok=True)
        (self.root / 'spec/verify-report.md').write_text('CHECK-1: PASS\nCHECK-3: DEFERRED\n', encoding='utf-8')
        report = self.root / 'docs/retrospect-report.md'
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text('retrospect: PASS\n', encoding='utf-8')
        self.marker('spec/retrospect-complete.txt', 'i2h-retrospect', ['docs/retrospect-report.md'])
        result = pipeline_resume.pipeline_status(self.root)
        self.assertEqual(result['resume_stage'], 'complete', result)
        self.assertTrue(all(row['complete'] for row in result['stages']))

    def test_hash_tampering_blocks_resume(self):
        self.marker('spec/baseline/spec-complete.txt', 'i2h-spec', ['spec/.i2h/resources-inventory.json'])
        path = self.root / 'spec/baseline/spec-complete.txt'
        payload = json.loads(path.read_text())
        payload['content_sha256'] = '0' * 64
        path.write_text(json.dumps(payload), encoding='utf-8')
        result = pipeline_resume.pipeline_status(self.root)
        self.assertEqual(result['resume_stage'], 'i2h-spec')
        self.assertIn('marker_content_hash_mismatch', result['stages'][0]['checks']['marker']['errors'])

    def test_plan_handoff_mutations_do_not_regress_to_spec(self):
        # i2h-plan appends decisions and may normalize feature-index after the
        # i2h-spec marker was written.  Once the plan marker and delivery
        # contract pass, resume must continue at execute while retaining an
        # auditable warning about the changed handoff artifacts.
        self.marker('spec/baseline/spec-complete.txt', 'i2h-spec', [
            'spec/.i2h/resources-inventory.json',
            'spec/baseline/feature-index.md',
            'spec/decision-ledger.md',
        ])
        self.delivery()
        self.marker('spec/baseline/plans/complete.txt', 'i2h-plan', ['spec/baseline/ui-delivery-approved.json'])
        (self.root / 'spec/baseline/feature-index.md').write_text('plan normalized\n', encoding='utf-8')
        (self.root / 'spec/decision-ledger.md').write_text('D-001 plan handoff\n', encoding='utf-8')

        result = pipeline_resume.pipeline_status(self.root)
        self.assertEqual(result['resume_stage'], 'i2h-execute', result)
        spec = result['stages'][0]
        self.assertTrue(spec['complete'])
        marker = spec['checks']['marker']
        self.assertTrue(marker['handoff_only'])
        self.assertIn('spec_handoff_artifact_changed_after_plan', marker['warnings'])
        self.assertEqual(set(marker['handoff_mismatches']), {
            'spec/baseline/feature-index.md',
            'spec/decision-ledger.md',
        })

    def test_legacy_path_is_reported_but_schema2_marker_is_accepted_in_compat_mode(self):
        # A legacy *path* can be consumed when its marker is still
        # content-addressed.  Plain-text/schema-1 markers remain diagnostic
        # only; file existence must never complete a stage.
        self.marker('spec/spec-complete.txt', 'i2h-spec', ['spec/.i2h/resources-inventory.json'])
        result = pipeline_resume.pipeline_status(self.root, allow_legacy=True)
        marker = result['stages'][0]['checks']['marker']
        self.assertTrue(marker['legacy'])
        self.assertEqual(result['resume_stage'], 'i2h-plan')
        strict = pipeline_resume.pipeline_status(self.root, allow_legacy=False)
        self.assertEqual(strict['resume_stage'], 'i2h-spec')

    def test_delivery_requires_approval_hash_and_unique_content(self):
        self.delivery(status='draft')
        result = pipeline_resume.validate_delivery(self.root, self.target)
        self.assertIn('schema2_delivery_not_approved', result['errors'])
        self.delivery(duplicate=True)
        result = pipeline_resume.validate_delivery(self.root, self.target)
        self.assertIn('schema2_delivery_duplicate_content', result['errors'])
        self.delivery(target='b' * 64)
        result = pipeline_resume.validate_delivery(self.root, self.target)
        self.assertIn('schema2_delivery_input_hash', result['errors'])
        self.delivery(target='')
        result = pipeline_resume.validate_delivery(self.root, self.target)
        self.assertIn('schema2_delivery_input_hash_missing', result['errors'])

    def test_delivery_requires_matching_ownership_contract(self):
        self.delivery()
        path = self.root / 'spec/baseline/ui-delivery-approved.json'
        payload = json.loads(path.read_text(encoding='utf-8'))
        payload['units'][0]['owned_ui_roles'] = ['behavior']
        path.write_text(json.dumps(payload), encoding='utf-8')
        result = pipeline_resume.validate_delivery(self.root, self.target)
        self.assertIn('schema2_delivery_ownership', result['errors'])
        self.assertEqual(result['ownership']['status'], 'FAIL')

    def test_execute_requires_fresh_immersive_safearea_receipt(self):
        self.delivery()
        path = self.root / 'spec/baseline/ui-delivery-approved.json'
        payload = json.loads(path.read_text(encoding='utf-8'))
        payload['units'][0]['needs_immersive_safearea'] = True
        path.write_text(json.dumps(payload), encoding='utf-8')
        result = pipeline_resume.validate_immersive_gate(self.root, payload)
        self.assertFalse(result['complete'])
        self.assertIn('immersive_safearea_gate_missing', result['errors'])

        receipt = self.root / 'spec/execution/immersive-safearea-gate.json'
        receipt.parent.mkdir(parents=True, exist_ok=True)
        import hashlib
        receipt.write_text(json.dumps({
            'status': 'PASS',
            'required_units': ['home'],
            'inventory_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'layers': {layer: {'ok': True} for layer in ('L1', 'L2', 'L3')},
        }), encoding='utf-8')
        result = pipeline_resume.validate_immersive_gate(self.root, payload)
        self.assertTrue(result['complete'], result)

    def test_delivery_allows_default_content_per_page(self):
        units = [
            {
                'unit_id': 'home',
                'page_id': 'page_home',
                'owned_ui_roles': ['content'],
                'required_states': [{'state_id': 'default', 'arrival_mode': 'preview', 'responsibility': 'content'}],
                'output': {'file': 'entry/src/main/ets/pages/Home.ets'},
            },
            {
                'unit_id': 'settings',
                'page_id': 'page_settings',
                'owned_ui_roles': ['content'],
                'required_states': [{'state_id': 'default', 'arrival_mode': 'preview', 'responsibility': 'content'}],
                'output': {'file': 'entry/src/main/ets/pages/Settings.ets'},
            },
        ]
        path = self.root / 'spec/baseline/ui-delivery-approved.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            'schema_version': 2,
            'status': 'approved',
            'target_input_sha256': self.target,
            'units': units,
        }), encoding='utf-8')
        result = pipeline_resume.validate_delivery(self.root, self.target)
        self.assertNotIn('schema2_delivery_duplicate_content', result['errors'])
        self.assertNotIn('schema2_delivery_ownership', result['errors'])

    def test_plain_legacy_marker_never_counts_as_completion(self):
        path = self.root / 'spec/spec-completed.txt'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('i2h-spec completed\n', encoding='utf-8')
        result = pipeline_resume.pipeline_status(self.root, allow_legacy=True)
        self.assertEqual(result['resume_stage'], 'i2h-spec')
        marker = result['stages'][0]['checks']['marker']
        self.assertTrue(marker['legacy'])
        self.assertIn('legacy_marker_unhashed', marker['warnings'])

    def test_installed_layout_imports_project_local_marker_contract(self):
        project = self.root / 'installed-project'
        script = project / '.agents/skills/i2h-plan/scripts/pipeline_resume.py'
        ownership = project / '.agents/skills/i2h-plan/scripts/ui_state_ownership.py'
        delivery = project / '.agents/skills/i2h-plan/scripts/ui_delivery.py'
        marker = project / '.migbot/bin/scripts/pipeline/marker_contract.py'
        script.parent.mkdir(parents=True, exist_ok=True)
        ownership.parent.mkdir(parents=True, exist_ok=True)
        marker.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(HERE / 'pipeline_resume.py', script)
        shutil.copy2(HERE / 'ui_state_ownership.py', ownership)
        shutil.copy2(HERE / 'ui_delivery.py', delivery)
        shutil.copy2(HERE.parents[2] / 'bin/scripts/pipeline/marker_contract.py', marker)
        result = subprocess.run(
            [sys.executable, str(script), '--project-root', str(project)],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 1)
        payload = json.loads(result.stdout)
        self.assertEqual(payload['resume_stage'], 'i2h-spec')

    def test_strict_mode_blocks_legacy_verify_report_path(self):
        self.marker('spec/baseline/spec-complete.txt', 'i2h-spec', ['spec/.i2h/resources-inventory.json'])
        report = self.root / 'spec/verify/verify-report.md'
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text('CHECK-1: PASS\n', encoding='utf-8')
        result = pipeline_resume.pipeline_status(self.root, allow_legacy=False)
        verify_marker = result['stages'][3]['checks']['marker']
        self.assertFalse(verify_marker['valid'])
        self.assertIn('legacy_marker_path_disallowed', verify_marker['errors'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
