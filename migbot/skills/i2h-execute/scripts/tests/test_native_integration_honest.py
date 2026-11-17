"""Honest native integration test with actual Plan CLI validation and approval."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.ios_inventory_resolution import (
    sha256_file,
    validate_approved_execution_inventory,
)


def json_bytes(obj):
    """Canonical JSON bytes."""
    return (json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + '\n').encode('utf-8')


class HonestNativeIntegrationTest(unittest.TestCase):
    """Test real derive + actual Plan validate + actual Plan approve workflow."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.ios_root = self.root / 'ios'
        self.ios_root.mkdir(parents=True)
        self.script_dir = Path(__file__).resolve().parent.parent
        self.plan_cli = self.script_dir.parent.parent / 'i2h-plan' / 'scripts' / 'ui_delivery.py'
        self.evidence_dir = self.root / 'evidence'
        self.evidence_dir.mkdir(parents=True, exist_ok=True)

        self.create_swift_sources()
        self.baseline = self.create_baseline()
        self.baseline_path = self.root / 'spec' / 'baseline' / 'ui-delivery-approved.json'
        self.baseline_path.parent.mkdir(parents=True, exist_ok=True)
        self.baseline_path.write_bytes(json_bytes(self.baseline))
        self.baseline_sha = sha256_file(self.baseline_path)

    def create_swift_sources(self):
        legal_view = '''struct LegalConsentView: View {
    @Binding var isAgreed: Bool

    var body: some View {
        Toggle("I agree", isOn: $isAgreed)
    }
}
'''
        (self.ios_root / 'LegalConsentView.swift').write_text(legal_view, encoding='utf-8')

        walk_container = '''private struct WalkServiceContainer {
    func setup() {
        LegalConsentView(isAgreed: .constant(false))
    }
}
'''
        (self.ios_root / 'WalkServiceContainer.swift').write_text(walk_container, encoding='utf-8')

    def create_baseline(self):
        legal_sha = sha256_file(self.ios_root / 'LegalConsentView.swift')
        walk_sha = sha256_file(self.ios_root / 'WalkServiceContainer.swift')

        return {
            'schema_version': 2,
            'status': 'approved',
            'source_project_root': str(self.ios_root),
            'units': [
                {
                    'unit_id': 'ios.0001.LegalConsentView',
                    'page_id': 'page_legal',
                    'component': 'ios.LegalConsentView',
                    'presentation_role': 'embedded',
                    'owned_ui_roles': ['content'],
                    'required': True,
                    'output': {
                        'file': 'LegalConsentView.ets',
                        'symbol': 'LegalConsentView',
                        'builder': 'LegalConsentViewBuilder'
                    },
                    'generation_owner': 'i2h-harmony',
                    'source_refs': [
                        {'file': 'LegalConsentView.swift', 'line': 1, 'sha256': legal_sha}
                    ],
                    'required_states': [
                        {
                            'state_id': 'default',
                            'responsibility': 'content',
                            'arrival_mode': 'formal',
                            'source_refs': [
                                {'file': 'LegalConsentView.swift', 'line': 1, 'sha256': legal_sha}
                            ]
                        }
                    ],
                    'integration': [
                        {
                            'source_ref': {'file': 'LegalConsentView.swift', 'line': 1},
                            'host_file': None,
                            'host_symbol': None,
                            'child_symbol': 'LegalConsentView',
                        }
                    ]
                },
                {
                    'unit_id': 'ios.0002.WalkServiceContainer',
                    'page_id': 'page_walk',
                    'component': 'ios.WalkServiceContainer',
                    'presentation_role': 'routed_page',
                    'owned_ui_roles': ['content'],
                    'required': True,
                    'output': {
                        'file': 'WalkServiceContainer.ets',
                        'symbol': 'WalkServiceContainer',
                        'builder': 'WalkServiceContainerBuilder'
                    },
                    'generation_owner': 'i2h-harmony',
                    'source_refs': [
                        {'file': 'WalkServiceContainer.swift', 'line': 1, 'sha256': walk_sha}
                    ],
                    'required_states': [
                        {'state_id': 'default', 'responsibility': 'content', 'arrival_mode': 'formal'}
                    ]
                }
            ],
            'verification_states': []
        }

    def test_honest_native_integration_workflow(self):
        self.assertTrue(self.plan_cli.is_file(), f"Plan CLI not found at {self.plan_cli}")

        legal_sha = sha256_file(self.ios_root / 'LegalConsentView.swift')
        walk_sha = sha256_file(self.ios_root / 'WalkServiceContainer.swift')

        proof = {
            'baseline_sha256': self.baseline_sha,
            'requests': [
                {
                    'unit_id': 'ios.0001.LegalConsentView',
                    'original_slot': {
                        'source_ref': {'file': 'LegalConsentView.swift', 'line': 1},
                        'host_file': None,
                        'host_symbol': None,
                        'child_symbol': 'LegalConsentView',
                    },
                    'slot_index': 0,
                    'integration': {
                        'caller_file': 'WalkServiceContainer.swift',
                        'caller_line': 3,
                        'callee': 'LegalConsentView',
                        'expected_owner': 'WalkServiceContainer',
                        'targethost': 'ios.0002.WalkServiceContainer'
                    }
                },
                {
                    'unit_id': 'ios.0001.LegalConsentView',
                    'source_only': {
                        'alternative_kind': 'source_only',
                        'state_id': 'default',
                        'source_file': 'LegalConsentView.swift',
                        'source_sha256': legal_sha,
                        'source_line': 1,
                        'declaration': 'LegalConsentView'
                    }
                }
            ]
        }

        proof_path = self.root / 'proof.json'
        proof_path.write_bytes(json_bytes(proof))

        draft_path = (self.root / 'spec' / 'execution' / 'draft.json').resolve()
        draft_path.parent.mkdir(parents=True, exist_ok=True)

        derive_result = subprocess.run([
            sys.executable,
            str(self.script_dir / 'ui_inventory_resolution.py'),
            'derive',
            '--project-root', str(self.root),
            '--baseline', str(self.baseline_path.relative_to(self.root)),
            '--proof', str(proof_path.relative_to(self.root)),
            '--out', str(draft_path.relative_to(self.root))
        ], capture_output=True, text=True)

        derive_evidence = {
            'argv': derive_result.args,
            'stdout': derive_result.stdout,
            'stderr': derive_result.stderr,
            'returncode': derive_result.returncode,
        }

        self.assertEqual(derive_result.returncode, 0, f"derive failed: {derive_result.stderr}\n{derive_result.stdout}")

        derive_output = json.loads(derive_result.stdout)
        self.assertEqual(derive_output['status'], 'PASS')

        draft = json.loads(draft_path.read_text())
        legal_unit = [u for u in draft['units'] if u['unit_id'] == 'ios.0001.LegalConsentView'][0]
        integration = legal_unit['integration'][0]

        self.assertEqual(integration['source_ref']['sha256'], walk_sha)
        self.assertEqual(integration['host_file'], 'WalkServiceContainer.ets')
        self.assertIn('input_alternatives', legal_unit)
        self.assertEqual(legal_unit['source_refs'][0]['sha256'], legal_sha)

        receipt_path = (self.root / 'validation-receipt.json').resolve()

        validate_result = subprocess.run([
            sys.executable,
            str(self.plan_cli),
            'validate',
            '--project-root', str(self.root),
            '--inventory', str(draft_path),
            '--receipt-only',
            '--out', str(receipt_path)
        ], capture_output=True, text=True)

        validate_evidence = {
            'argv': validate_result.args,
            'stdout': validate_result.stdout,
            'stderr': validate_result.stderr,
            'returncode': validate_result.returncode,
        }

        self.assertEqual(validate_result.returncode, 0, f"Plan validate failed: {validate_result.stderr}\n{validate_result.stdout}")

        receipt = json.loads(receipt_path.read_text())
        self.assertEqual(receipt['status'], 'validated')

        approve_result = subprocess.run([
            sys.executable,
            str(self.plan_cli),
            'approve',
            '--project-root', str(self.root),
            '--inventory', str(draft_path),
            '--out', str(draft_path),
            '--validation-receipt', str(receipt_path),
            '--confirmation-ref', 'test-native'
        ], capture_output=True, text=True)

        approve_evidence = {
            'argv': approve_result.args,
            'stdout': approve_result.stdout,
            'stderr': approve_result.stderr,
            'returncode': approve_result.returncode,
        }

        self.assertEqual(approve_result.returncode, 0, f"Plan approve failed: {approve_result.stderr}\n{approve_result.stdout}")

        approved = json.loads(draft_path.read_text())
        self.assertEqual(approved['status'], 'approved')
        self.assertEqual(approved['approval']['confirmation_ref'], 'test-native')
        self.assertIn('candidate_sha256', approved['approval'])
        self.assertIn('validation_receipt_sha256', approved['approval'])

        valid, errors = validate_approved_execution_inventory(draft_path, self.baseline_path, proof_path)
        self.assertTrue(valid, f"replay validation failed: {errors}")

        replay_result = subprocess.run([
            sys.executable,
            str(self.script_dir / 'ui_inventory_resolution.py'),
            'derive',
            '--project-root', str(self.root),
            '--baseline', str(self.baseline_path.relative_to(self.root)),
            '--proof', str(proof_path.relative_to(self.root)),
            '--out', str(draft_path.relative_to(self.root)),
            '--validate-approved'
        ], capture_output=True, text=True)

        replay_evidence = {
            'argv': replay_result.args,
            'stdout': replay_result.stdout,
            'stderr': replay_result.stderr,
            'returncode': replay_result.returncode,
        }

        self.assertEqual(replay_result.returncode, 0, f"validate-approved failed: {replay_result.stderr}\n{replay_result.stdout}")

        evidence = {
            'derive': derive_evidence,
            'plan_validate': validate_evidence,
            'plan_approve': approve_evidence,
            'replay_cli': replay_evidence,
        }

        import copy

        evidence['replay_negatives'] = {}

        tamper_cases = [
            ('unit0_required_false', lambda a: a['units'][0].update({'required': False}) or a),
            ('unit0_owned_ui_roles_changed', lambda a: a['units'][0].update({'owned_ui_roles': ['nav']}) or a),
            ('unit0_presentation_role_changed', lambda a: a['units'][0].update({'presentation_role': 'modal'}) or a),
            ('unit0_responsibility_changed', lambda a: a['units'][0]['required_states'][0].update({'responsibility': 'nav'}) or a),
            ('unit0_arrival_mode_changed', lambda a: a['units'][0]['required_states'][0].update({'arrival_mode': 'informal'}) or a),
            ('unit0_output_file_changed', lambda a: a['units'][0]['output'].update({'file': 'Other.ets'}) or a),
            ('unit0_output_symbol_changed', lambda a: a['units'][0]['output'].update({'symbol': 'Other'}) or a),
            ('unit0_output_builder_changed', lambda a: a['units'][0]['output'].update({'builder': 'OtherBuilder'}) or a),
            ('unit0_generation_owner_changed', lambda a: a['units'][0].update({'generation_owner': 'other'}) or a),
            ('unit0_source_refs_sha_changed', lambda a: a['units'][0]['source_refs'][0].update({'sha256': 'deadbeef' * 8}) or a),
            ('unit0_required_states_source_refs_changed', lambda a: a['units'][0]['required_states'][0].update({'source_refs': []}) or a),
            ('verification_states_add_row', lambda a: (a['verification_states'].append({'state_id': 'x'}), a)[1]),
        ]

        for case_name, mutator in tamper_cases:
            tampered = copy.deepcopy(approved)
            mutator(tampered)
            tampered_path = self.root / f'tampered-{case_name}.json'
            tampered_path.write_bytes(json_bytes(tampered))

            tamper_result = subprocess.run([
                sys.executable,
                str(self.script_dir / 'ui_inventory_resolution.py'),
                'derive',
                '--project-root', str(self.root),
                '--baseline', str(self.baseline_path.relative_to(self.root)),
                '--proof', str(proof_path.relative_to(self.root)),
                '--out', str(tampered_path.relative_to(self.root)),
                '--validate-approved'
            ], capture_output=True, text=True)

            self.assertNotEqual(tamper_result.returncode, 0)
            out = tamper_result.stdout + tamper_result.stderr
            self.assertIn('replay mismatch', out.lower())

            evidence['replay_negatives'][case_name] = {
                'argv': tamper_result.args,
                'stdout': tamper_result.stdout,
                'stderr': tamper_result.stderr,
                'returncode': tamper_result.returncode,
            }

        evidence['derive_negatives'] = {}
        orig_bl = self.baseline_path.read_bytes()
        orig_pf = proof_path.read_bytes()
        walk_path = self.ios_root / 'WalkServiceContainer.swift'
        orig_wk = walk_path.read_bytes()
        try:
            def _neg(label, cli):
                out = self.root / f'ng-{label}.json'
                r = subprocess.run(
                    [sys.executable, str(self.script_dir / 'ui_inventory_resolution.py'),
                     'derive'] + cli + ['--out', str(out.relative_to(self.root))],
                    capture_output=True, text=True)
                self.assertNotEqual(r.returncode, 0, f'derive_neg[{label}] must fail')
                evidence['derive_negatives'][label] = {
                    'argv': r.args, 'stdout': r.stdout, 'stderr': r.stderr, 'returncode': r.returncode}
            bl_rel = str(self.baseline_path.relative_to(self.root))
            root_s = str(self.root)
            def _cli(bl, pf): return ['--project-root', root_s, '--baseline', bl, '--proof', pf]
            def _wp(d, fn):
                p = self.root / fn; p.write_bytes(json_bytes(d)); return p
            _neg('missing_proof', _cli(bl_rel, 'nonexistent.json'))
            bp = copy.deepcopy(proof); bp['baseline_sha256'] = 'deadbeef' * 8
            _neg('wrong_baseline_sha', _cli(bl_rel, str(_wp(bp, 'ng-bp.json').relative_to(self.root))))
            np2 = copy.deepcopy(proof); del np2['requests'][0]['integration']['caller_file']
            _neg('absent_caller_file', _cli(bl_rel, str(_wp(np2, 'ng-np.json').relative_to(self.root))))
            wp2 = copy.deepcopy(proof); wp2['requests'][0]['integration']['expected_owner'] = 'WrongOwner'
            _neg('wrong_expected_owner', _cli(bl_rel, str(_wp(wp2, 'ng-wp.json').relative_to(self.root))))
            ep2 = copy.deepcopy(proof); ep2['requests'][0]['integration']['caller_file'] = '../escape.swift'
            _neg('caller_path_escape', _cli(bl_rel, str(_wp(ep2, 'ng-ep.json').relative_to(self.root))))
            ns = copy.deepcopy(self.baseline)
            for u in ns['units']:
                for ref in u.get('source_refs', []):
                    if ref.get('file') == 'WalkServiceContainer.swift':
                        ref.pop('sha256', None)
                for s in u.get('required_states', []):
                    for ref in s.get('source_refs', []):
                        if ref.get('file') == 'WalkServiceContainer.swift':
                            ref.pop('sha256', None)
            ns_p = _wp(ns, 'ng-ns-bl.json')
            nsp = copy.deepcopy(proof); nsp['baseline_sha256'] = sha256_file(ns_p)
            _neg('primary_sha_absent', _cli(str(ns_p.relative_to(self.root)),
                                            str(_wp(nsp, 'ng-ns-pf.json').relative_to(self.root))))
            wk_ls = orig_wk.decode('utf-8').split('\n')
            wk_ls[2] = '        /* LegalConsentView(isAgreed: .constant(false)) */'
            walk_path.write_text('\n'.join(wk_ls), encoding='utf-8')
            cmt_sha = sha256_file(walk_path)
            cb = copy.deepcopy(self.baseline)
            for u in cb['units']:
                for ref in u.get('source_refs', []):
                    if ref.get('file') == 'WalkServiceContainer.swift': ref['sha256'] = cmt_sha
                for s in u.get('required_states', []):
                    for ref in s.get('source_refs', []):
                        if ref.get('file') == 'WalkServiceContainer.swift': ref['sha256'] = cmt_sha
            cb_p = _wp(cb, 'ng-cb-bl.json')
            cp = copy.deepcopy(proof); cp['baseline_sha256'] = sha256_file(cb_p)
            _neg('block_comment_invocation', _cli(str(cb_p.relative_to(self.root)),
                                                  str(_wp(cp, 'ng-cb-pf.json').relative_to(self.root))))
            cmt_ev = evidence['derive_negatives']['block_comment_invocation']
            cmt_out = cmt_ev['stdout'] + cmt_ev['stderr']
            self.assertIn('invocation', cmt_out.lower())
            self.assertIn('not found', cmt_out.lower())
            self.assertNotIn('sha mismatch', cmt_out.lower())
        finally:
            self.baseline_path.write_bytes(orig_bl)
            proof_path.write_bytes(orig_pf)
            walk_path.write_bytes(orig_wk)

        (self.evidence_dir / 'honest-native-integration-evidence.json').write_text(json.dumps(evidence, indent=2))


if __name__ == '__main__':
    unittest.main()
