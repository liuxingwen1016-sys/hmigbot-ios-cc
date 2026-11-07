import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stage1_contract import digest
from stage1_gate_policy import annotate, assess, decide


class Stage1GatePolicyTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.write('entry/src/main/ets/pages/Main.ets', 'struct Main { build() { Text("body") } }')
        self.report = self.write('spec/execution/report.json', {'status': 'BLOCKED', 'errors': [
            {'code': 'ANDROID_BASELINE_MISSING', 'detail': 'audited frame unavailable'}]})
        self.gate = 'execute.stage1-visual'

    def write(self, relative, value):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value) if isinstance(value, dict) else value)
        return path

    def assess(self, round=None, review=None):
        evidence = self.write(f'spec/execution/recovery-{round}.log', f'collect original input, attempt {round}: still absent') if round else None
        return assess(self.root, self.report, self.gate, review, evidence)

    def exhausted(self):
        self.assess()
        self.assess(1)
        return self.assess(2)

    def test_information_gap_retries_then_releases_without_passing(self):
        original = self.report.read_bytes()
        self.assertEqual(self.assess()['disposition'], 'RETRY')
        self.assertEqual(self.assess(1)['disposition'], 'RETRY')
        result = self.assess(2)
        self.assertEqual(result['disposition'], 'RELEASE_WITH_GAPS')
        self.assertTrue(result['can_continue'])
        self.assertFalse(result['gate_verified'])
        self.assertFalse(result['stage1_complete'])
        self.assertEqual(result['raw_gate_status'], 'BLOCKED')
        self.assertEqual(self.report.read_bytes(), original)

    def test_product_defect_blocks_even_when_budget_exhausted(self):
        self.write('spec/execution/report.json', {'status': 'FAIL', 'errors': [{'code': 'required_mount_unresolved'}]})
        result = self.exhausted()
        self.assertEqual(result['disposition'], 'BLOCK')
        self.assertEqual(result['next_action'], 'stop_with_product_defects')

    def test_compile_error_cannot_be_waived_as_missing_information(self):
        self.gate = 'execute.build'
        self.write('spec/execution/report.json', {'status': 'FAIL', 'errors': [
            {'code': 'ARKTS_COMPILER_ERROR', 'root_cause': 'information_gap'}]})
        self.assertEqual(self.exhausted()['disposition'], 'BLOCK')

    def test_environment_gap_has_separate_release_gate_from_compile(self):
        self.gate = 'execute.build'
        self.write('spec/execution/report.json', {'status': 'BLOCKED', 'errors': [{'code': 'SDK_UNAVAILABLE'}]})
        result = self.exhausted()
        self.assertEqual(result['release_gates'], ['execute.stage1-prerequisite'])
        self.assertNotIn('execute.build', result['release_gates'])

    def test_unknown_failure_needs_diagnosis_even_after_retries(self):
        self.write('spec/execution/report.json', {'status': 'FAIL', 'errors': [{'code': 'inputs_invalid'}]})
        self.assertEqual(self.exhausted()['next_action'], 'stop_with_unresolved_cause')

    def test_mixed_quality_and_missing_information_still_blocks(self):
        self.write('spec/execution/report.json', {'status': 'FAIL', 'errors': [
            {'code': 'ANDROID_BASELINE_MISSING'}, {'code': 'UI_ASSERTION_FAILED'}]})
        self.assertFalse(self.exhausted()['can_continue'])

    def test_pass_does_not_hide_contradictory_quality_findings(self):
        findings = annotate({'status': 'PASS', 'errors': [{'code': 'OUTPUT_MISSING'}]}, self.gate)['failure_findings']
        self.assertEqual(decide(findings, 2, 2, 'PASS')['disposition'], 'BLOCK')

    def test_clean_pass_is_verified(self):
        self.write('spec/execution/report.json', {'status': 'PASS', 'errors': []})
        self.assertTrue(self.assess()['gate_verified'])

    def test_repeated_action_log_cannot_burn_budget(self):
        self.assess(1)
        self.assertEqual(self.assess(1)['repair_rounds'], 1)
        self.assertEqual(self.assess()['repair_rounds'], 1)

    def test_new_report_or_source_does_not_reset_budget(self):
        self.assess(1)
        self.write('entry/src/main/ets/pages/Main.ets', 'struct Main { build() { Text("changed") } }')
        moved = self.write('spec/execution/new-task-report.json', json.loads(self.report.read_text()))
        result = assess(self.root, moved, self.gate)
        self.assertEqual(result['repair_rounds'], 1)

    def test_scope_change_cannot_silently_reset_budget(self):
        self.assess(1)
        self.write('spec/execution/stage1-wiring-contract.json', {'max_repair_rounds': 2})
        with self.assertRaisesRegex(ValueError, 'scope changed'):
            self.assess()

    def test_raw_report_cannot_be_remediation_evidence(self):
        with self.assertRaises(ValueError):
            assess(self.root, self.report, self.gate, remediation_path=self.report)

    def test_known_quality_cannot_be_reclassified_as_information_gap(self):
        self.write('spec/execution/report.json', {'status': 'FAIL', 'errors': [{'code': 'OUTPUT_MISSING'}]})
        review = self.write('spec/execution/review.json', {'report_sha256': digest(self.report), 'findings': [{
            'finding_id': '0:OUTPUT_MISSING', 'root_cause': 'information_gap', 'reason': 'tried many times',
            'evidence': ['entry/src/main/ets/pages/Main.ets']}]})
        with self.assertRaisesRegex(ValueError, 'known product defect'):
            self.assess(review=review)

    def test_proven_detector_gap_requires_bound_review_and_evidence(self):
        self.write('spec/execution/report.json', {'status': 'FAIL', 'errors': [{'code': 'required_mount_unresolved'}]})
        review = self.write('spec/execution/review.json', {'report_sha256': digest(self.report), 'findings': [{
            'finding_id': '0:required_mount_unresolved', 'root_cause': 'tool_gap',
            'reason': 'source uses a valid alias outside detector support', 'disproves_product_defect': True,
            'evidence': ['entry/src/main/ets/pages/Main.ets']}]})
        self.assertEqual(self.assess(review=review)['findings'][0]['root_cause'], 'tool_gap')
        self.write('spec/execution/report.json', {'status': 'FAIL', 'errors': [{'code': 'required_mount_unresolved', 'id': 'changed'}]})
        with self.assertRaisesRegex(ValueError, 'not bound'):
            self.assess(review=review)

    def test_gap_claim_without_evidence_does_not_unlock_release(self):
        self.write('spec/execution/report.json', {'status': 'FAIL', 'errors': [
            {'code': 'UNRECOGNIZED', 'root_cause': 'tool_gap'}]})
        self.assertEqual(self.exhausted()['next_action'], 'stop_with_unresolved_cause')


if __name__ == '__main__':
    unittest.main()
