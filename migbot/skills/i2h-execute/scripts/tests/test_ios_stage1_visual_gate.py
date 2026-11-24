"""Visual archive regression checks against frozen scope and receipt identities."""
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.ios_stage1_acceptance import archive_g1
from lib.ios_stage1_scope import build_scope_from_inventory
from lib.ios_stage1_summary import summarize
from lib.ios_stage1_visual_gate import archive_visual, conflicting_state_pairs, shared_capture_groups
from lib.ios_ui_dispatch import INDEX, complete, digest, json_bytes, prepare, sha256
from lib.ios_ui_relationships import compare_relationships
from lib.stage1_visual_report import assemble, capture_index, review_worklist


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

    def observed_report(self, *, forged_relationship=False, native_control_roles=False, audit_viewport=False,
                        foreground_diagnostic=False, audit_status_bar=False, audit_control_clipping=None):
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
            {'attributes': {
                'type': 'Text' if native_control_roles else 'Button', 'text': 'Next',
                'clickable': 'true', 'bounds': '[20,80][120,120]', 'origBounds': '[20,80][120,128]',
            }},
        ]})
        self.write('spec/appearance.json', {'comparison_id': 'pair:0', 'verdict': 'PASS',
                                            'ios_png_sha256': sha256(self.png), 'harmony_png_sha256': sha256(self.png)})
        pair = self.scope['pairs'][0]
        relationship = compare_relationships(self.root, pair, pair['comparisons'][0], target,
                                             native_control_roles=native_control_roles, audit_viewport=audit_viewport,
                                             audit_status_bar=audit_status_bar,
                                             audit_control_clipping=audit_control_clipping)
        self.assertEqual(relationship['verdict'], 'PASS')
        if forged_relationship:
            relationship['matched_anchors'] += 1
        if foreground_diagnostic:
            relationship['diagnostic_surface'] = {'ios_navigation_identifier': 'Tasting',
                                                 'harmony_surface_type': 'SheetPage'}
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

    def test_shared_capture_only_blocks_distinct_states_of_same_page(self):
        import copy
        first = self.scope['pairs'][0]
        second = copy.deepcopy(first)
        second.update(pair_id='second', state_id='second')
        second['baseline']['ui_json_sha256'] = 'a' * 64
        row = {'frames': [{'comparison_id': 'one', 'harmony_png': {'sha256': 'b' * 64},
                           'harmony_xml': {'sha256': 'c' * 64}}]}
        capture = {'pair': row, 'second': row}
        approved = {'pair': first, 'second': second}
        groups = shared_capture_groups(approved, capture)
        self.assertEqual(len(groups), 1)
        self.assertEqual(conflicting_state_pairs(groups), {'pair', 'second'})
        second['page_id'] = 'separate-page'
        self.assertEqual(conflicting_state_pairs(shared_capture_groups(approved, capture)), set())

    def test_capture_index_blocks_shared_target_for_two_distinct_source_states(self):
        from copy import deepcopy
        from unittest.mock import patch

        self.observed_report()
        first = self.scope['pairs'][0]
        second = deepcopy(first)
        second.update(pair_id='second', state_id='second')
        second['comparisons'][0]['comparison_id'] = 'second:0'
        other_tree = self.write('spec/other-source.json', self.tree + b'\n')
        second['baseline'].update(ui_json_path='spec/other-source.json',
                                  ui_json_sha256=sha256(other_tree.read_bytes()))
        self.scope['pairs'].append(second)
        self.scope_path.write_bytes(json_bytes(self.scope))
        current_hash = sha256(self.scope_path.read_bytes())
        for name in ('build', 'install'):
            path = self.root / f'spec/{name}.json'
            payload = json.loads(path.read_bytes())
            self.write(f'spec/{name}.json', {**payload, 'scope_sha256': current_hash})
        arrivals = []
        for pair in (first, second):
            name = pair['pair_id'] + '.json'
            arrivals.append(name)
            target = self.root / 'spec/target.json'
            self.write('spec/' + name, {
                'status': 'PASS', 'pair_id': pair['pair_id'], 'arrival_mode': 'formal',
                'observed_page_id': pair['page_id'], 'observed_state_id': pair['state_id'],
                'device_id': 'fixture-target', 'capture_run_id': 'fixture-run',
                'build_receipt': self.ref(self.root / 'spec/build.json'),
                'install_receipt': self.ref(self.root / 'spec/install.json'),
                'landing_evidence': self.ref(target),
                'frames': [{'comparison_id': pair['comparisons'][0]['comparison_id'],
                            'harmony_png': self.ref(self.root / 'spec/target.png'),
                            'harmony_xml': self.ref(target)}],
            })
        with patch('lib.stage1_visual_report.build_scope_from_inventory', return_value=self.scope):
            result = capture_index(self.root, self.scope_path, arrivals)
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertEqual(result['pairs'], [])
        self.assertEqual({row['pair_id'] for row in result['capture_gaps']}, {'pair', 'second'})
        self.assertTrue(all('share one target image and tree' in gap['reason']
                            for gap in result['capture_gaps']))

    def test_appearance_receipt_replays_group_and_image_identity(self):
        from lib.ios_stage1_visual_gate import _check_appearance_receipt

        name = 'pair:0'
        image_hash = sha256(self.png)
        item = {'comparison_id': name, 'verdict': 'PASS', 'severity': 'normal', 'notes': 'reviewed'}
        group = self.write('spec/group.json', {'comparisons': [item]})
        context = self.write('spec/panel.json', {'sides': ['iOS', 'HarmonyOS']})
        region = [0, 0, 40, 60]
        binding = {'ios_sha256': image_hash, 'harmony_sha256': image_hash, 'ios_region_px': region,
                   'source_context_sha256': [self.ref(context)['sha256']]}
        receipt = self.write('spec/group.receipt.json', {
            'verified': True, 'exit_code': 0, 'report_sha256': sha256(group.read_bytes()),
            'review_inputs': {name: binding},
        })
        appearance = {**item, 'review_receipt': self.ref(receipt), 'review_context': [self.ref(context)]}
        common = {'comparison_id': name, 'ios_png_sha256': image_hash, 'harmony_png_sha256': image_hash,
                  'ios_region_px': region}
        _check_appearance_receipt(self.root, appearance, common)
        with self.assertRaisesRegex(ValueError, 'differs from the verified'):
            _check_appearance_receipt(self.root, {**appearance, 'notes': 'changed'}, common)
        with self.assertRaisesRegex(ValueError, 'current harmony image'):
            _check_appearance_receipt(self.root, appearance, {**common, 'harmony_png_sha256': 'b' * 64})
        with self.assertRaisesRegex(ValueError, 'approved iOS region'):
            _check_appearance_receipt(self.root, appearance, {**common, 'ios_region_px': None})
        with self.assertRaisesRegex(ValueError, 'archived context'):
            _check_appearance_receipt(self.root, {**appearance, 'review_context': [self.ref(group)]}, common)
        with self.assertRaisesRegex(ValueError, 'archived context'):
            _check_appearance_receipt(self.root, item | {'review_receipt': self.ref(receipt)}, common)

    def test_platform_review_rejects_swapped_dimensions_even_with_correct_structured_fields(self):
        from lib.ios_stage1_visual_gate import _check_appearance_receipt

        def png_header(width, height):
            return b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR' + width.to_bytes(4, 'big') + height.to_bytes(4, 'big')

        name = 'pair:0'
        images = {'ios': png_header(1206, 2622), 'harmony': png_header(1256, 2760)}
        dims = {'ios': [1206, 2622], 'harmony': [1256, 2760]}
        common = {'comparison_id': name, **{f'{side}_png_sha256': sha256(raw) for side, raw in images.items()}}
        item = {'comparison_id': name, 'verdict': 'FAIL', 'severity': 'normal',
                'platform_dimensions': dims, 'notes': 'iOS 1206×2622，HarmonyOS 1256×2760'}

        def check(notes, expected=dims):
            item['notes'] = notes
            report = self.write('spec/group.json', {'comparisons': [item]})
            binding = {'platform_dimensions': expected,
                       **{f'{side}_sha256': sha256(raw) for side, raw in images.items()}}
            receipt = self.write('spec/group.receipt.json', {
                'verified': True, 'exit_code': 0, 'report_sha256': sha256(report.read_bytes()),
                'review_inputs': {name: binding},
            })
            _check_appearance_receipt(self.root, {**item, 'review_receipt': self.ref(receipt)}, common, images)

        check(item['notes'])
        with self.assertRaisesRegex(ValueError, 'explicitly assign'):
            check('左=iOS 1256x2760，右=HarmonyOS 1206x2622')
        with self.assertRaisesRegex(ValueError, 'differ from the bound images'):
            check('reviewed', {'ios': dims['harmony'], 'harmony': dims['ios']})

    def test_native_control_role_report_replays_with_the_declared_mode(self):
        report = self.observed_report(native_control_roles=True, audit_viewport=True)
        result = archive_visual(self.root, self.scope_path, report)
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['passed_pairs'], 1)
        relationship = self.root/'spec/relationship.json'
        value = json.loads(relationship.read_bytes())
        self.assertEqual([f['code'] for f in value['viewport_findings']], ['target_control_clipped'])
        value['viewport_findings'] = []
        self.write('spec/relationship.json', value)
        updated = json.loads(report.read_bytes())
        updated['pairs'][0]['comparisons'][0]['relationship_report'] = self.ref(relationship)
        self.write('spec/report.json', updated)
        rejected = archive_visual(self.root, self.scope_path, report)
        self.assertIn('does not match native tree replay', rejected['pairs'][0]['reason'])

    def test_legacy_viewport_report_replays_with_old_diagnostics(self):
        report = self.observed_report(audit_viewport=True, audit_control_clipping=False)
        result = archive_visual(self.root, self.scope_path, report)
        self.assertEqual(result['status'], 'PASS')

    def test_opt_in_status_bar_audit_is_replayed(self):
        report = self.observed_report(audit_status_bar=True)
        result = archive_visual(self.root, self.scope_path, report)
        self.assertEqual(result['status'], 'PASS')
        relationship = self.root/'spec/relationship.json'
        value = json.loads(relationship.read_bytes())
        self.assertEqual(value['navigation_status_bar']['status'], 'UNAVAILABLE')
        value['navigation_status_bar']['status'] = 'CLEAR'
        self.write('spec/relationship.json', value)
        amended = json.loads(report.read_bytes())
        amended['pairs'][0]['comparisons'][0]['relationship_report'] = self.ref(relationship)
        self.write('spec/report.json', amended)
        result = archive_visual(self.root, self.scope_path, report)
        self.assertIn('does not match native tree replay', result['pairs'][0]['reason'])

    def test_verify_replays_bound_visual_and_rejects_changed_artifacts(self):
        tool = Path(__file__).resolve().parents[3] / 'i2h-plan/scripts/pipeline_resume.py'
        command = [sys.executable, '-B', str(tool), '--project-root', str(self.root),
                   '--require-bound-visual', '--summary']

        def verify():
            result = subprocess.run(command, capture_output=True, encoding='utf-8', timeout=20)
            self.assertEqual(result.returncode, 1, result.stderr)
            return json.loads(result.stdout)['verification']

        rows = '| CHECK-1 | Build | PASS |\n| CHECK-3 | Visual | PASS |\n'
        self.write('spec/verify-report.md', rows.encode())
        self.assertIn('visual_receipt_invalid', verify()['errors'])
        report = self.observed_report()
        archive_visual(self.root, self.scope_path, report)
        bindings = f'visual-scope: spec/scope.json\nvisual-comparison-sha256: {sha256(report.read_bytes())}\n'
        self.write('spec/verify-report.md', (rows + bindings).encode())
        outcome = verify()
        self.assertTrue(outcome['complete'], outcome)
        self.assertEqual(outcome['visual_evidence']['pairs'], 1)
        self.assertEqual(outcome['visual_evidence']['device'], 'fixture-target')
        self.write('spec/target.png', b'changed bytes')
        outcome = verify()
        self.assertFalse(outcome['complete'])
        self.assertEqual(outcome['unpassed_checks']['CHECK-3'], 'UNVERIFIED')

    def test_visual_denominator_survives_missing_capture(self):
        capture = self.write('spec/capture.json', {'pairs': []})
        report = self.write('spec/report.json', assemble(self.root, self.scope_path, capture, []))
        result = archive_visual(self.root, self.scope_path, report)
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertEqual(result['required_pairs'], 1)
        self.assertFalse(result['assessment_complete'])

    def test_capture_index_requires_bound_frames_and_stops_before_judgement(self):
        self.observed_report()
        pair = self.scope['pairs'][0]
        arrival = self.root / 'spec/arrival.json'
        receipt = json.loads(arrival.read_bytes())
        self.assertEqual(capture_index(self.root, self.scope_path, ['arrival.json'])['status'], 'BLOCKED')
        receipt.update(observed_page_id=pair['page_id'], observed_state_id=pair['state_id'],
                       capture_run_id='native-run', landing_evidence=self.ref(self.root/'spec/target.json'),
                       frames=[{'comparison_id': 'pair:0',
                                'harmony_png': self.ref(self.root/'spec/target.png'),
                                'harmony_xml': self.ref(self.root/'spec/target.json')}])
        self.write('spec/arrival.json', receipt)
        hap_digest = sha256(b'fixture package')
        capture = capture_index(self.root, self.scope_path, ['arrival.json'], expected_hap=hap_digest)
        self.assertEqual(capture['status'], 'READY')
        self.assertEqual(capture['expected_hap_sha256'], hap_digest)
        wrong_hap = capture_index(self.root, self.scope_path, ['arrival.json'], expected_hap='f' * 64)
        self.assertIn('differs from the verified application package', wrong_hap['capture_gaps'][0]['reason'])
        wrong_index = self.write('spec/wrong-capture.json', {**capture, 'expected_hap_sha256': 'f' * 64})
        self.assertIn('differs from the verified application package',
                      assemble(self.root, self.scope_path, wrong_index, [])['assembly_gaps'][0]['reason'])
        path = self.write('spec/capture.json', capture)
        before = path.read_bytes()
        receipt['capture_run_id'] = 'resampled-run'
        self.write('spec/resampled.json', receipt)
        resampled = capture_index(self.root, self.scope_path, ['resampled.json'], base_index=path)
        self.assertEqual(resampled['status'], 'READY')
        self.assertEqual(resampled['expected_hap_sha256'], hap_digest)
        self.assertEqual(resampled['pairs'][0]['arrival_receipt']['path'], 'resampled.json')
        self.assertEqual(path.read_bytes(), before)
        install = json.loads((self.root / 'spec/install.json').read_bytes())
        replacement = self.write('spec/other-install.json', {**install, 'device_id': 'other-device'})
        self.write('spec/wrong-device.json', {**receipt, 'install_receipt': self.ref(replacement)})
        rejected = capture_index(self.root, self.scope_path, ['wrong-device.json'], base_index=path)
        self.assertEqual(rejected['status'], 'BLOCKED')
        self.assertIn('arrival device does not match installation', rejected['capture_gaps'][0]['reason'])
        self.write('spec/wrong-device.json', {**receipt, 'install_receipt': self.ref(replacement),
                                              'device_id': 'other-device'})
        with self.assertRaisesRegex(ValueError, 'must use the base capture HAP and device'):
            capture_index(self.root, self.scope_path, ['wrong-device.json'], base_index=path)
        self.assertEqual(path.read_bytes(), before)
        result = assemble(self.root, self.scope_path, path, [])
        self.assertIn('judgement missing', result['assembly_gaps'][0]['reason'])
        judge = self.root / 'spec/judge.json'
        report = self.write('spec/report.json', assemble(self.root, self.scope_path, path, [judge]))
        payload = json.loads(report.read_bytes())
        self.assertEqual(payload['status'], 'ASSEMBLED')
        alternate = self.write('spec/other.png', self.png)
        payload['pairs'][0]['comparisons'][0]['harmony_png'] = self.ref(alternate)
        self.write('spec/report.json', payload)
        archived = archive_visual(self.root, self.scope_path, report)
        self.assertIn('differ from the native arrival receipt', archived['pairs'][0]['reason'])
        self.write('spec/target.json', {})
        result = assemble(self.root, self.scope_path, path, [])
        self.assertIn('SHA-256 mismatch', result['assembly_gaps'][0]['reason'])
        receipt['observed_state_id'] = 'wrong-state'
        self.write('spec/arrival.json', receipt)
        result = capture_index(self.root, self.scope_path, ['arrival.json'])
        self.assertIn('approved page/state', result['capture_gaps'][0]['reason'])

    def test_missing_source_allows_review_of_bound_pairs_and_blocks_final_acceptance(self):
        inventory_path = self.root / 'spec/baseline/ui-delivery-approved.json'
        inventory = json.loads(inventory_path.read_bytes())
        unit = inventory['units'][0]
        missing = {'state_id': 'keyboard', 'arrival_mode': 'formal'}
        unit['required_states'].append(missing)
        inventory['verification_states'].append({
            'verification_id': 'missing-source', 'page_id': unit['page_id'],
            'state_id': missing['state_id'], 'owner': unit['unit_id'],
        })
        self.write('spec/baseline/ui-delivery-approved.json', inventory)
        self.scope = build_scope_from_inventory(self.root, None)
        self.scope_path = self.write('spec/scope.json', self.scope)
        self.scope_hash = sha256(self.scope_path.read_bytes())
        self.assertEqual(self.scope['status'], 'BLOCKED')
        self.observed_report()
        arrival = json.loads((self.root/'spec/arrival.json').read_bytes())
        pair = self.scope['pairs'][0]
        tree = self.ref(self.root/'spec/target.json')
        arrival.update(observed_page_id=pair['page_id'], observed_state_id=pair['state_id'],
                       capture_run_id='partial', landing_evidence=tree,
                       frames=[{'comparison_id': 'pair:0', 'harmony_xml': tree,
                                'harmony_png': self.ref(self.root/'spec/target.png')}])
        self.write('spec/arrival.json', arrival)
        capture = capture_index(self.root, self.scope_path, ['arrival.json'])
        self.assertEqual(capture['status'], 'BLOCKED')
        self.assertEqual(capture['required_pairs'], 2)
        self.assertEqual([row['pair_id'] for row in capture['pairs']], ['pair'])
        self.assertIn('source baseline blocked', capture['capture_gaps'][0]['reason'])
        index = self.write('spec/capture-partial.json', capture)
        updated = capture_index(self.root, self.scope_path, ['arrival.json'], base_index=index)
        self.assertEqual(updated, capture)
        work = review_worklist(self.root, self.scope_path, index)
        self.assertEqual(work['reviewable_comparisons'], 1)
        self.assertEqual(work['required_comparisons'], 2)

        assembled = assemble(self.root, self.scope_path, index, [self.root/'spec/judge.json'])
        self.assertEqual(assembled['status'], 'BLOCKED')
        self.assertEqual(assembled['pairs'][0]['verdict'], 'PASS')
        strict = archive_visual(self.root, self.scope_path, self.write('spec/partial-output.json', assembled))
        self.assertEqual(strict['status'], 'BLOCKED')
        self.assertEqual((strict['passed_pairs'], strict['required_pairs']), (1, 2))
        self.assertFalse(strict['assessment_complete'])

        # A structurally absent approved pair is different from a missing source image.
        inventory['verification_states'].pop()
        self.write('spec/baseline/ui-delivery-approved.json', inventory)
        structural = build_scope_from_inventory(self.root, None)
        structural_path = self.write('spec/structural-gap.json', structural)
        result = capture_index(self.root, structural_path, ['arrival.json'])
        self.assertEqual(result['pairs'], [])
        self.assertIn('pair mapping is incomplete', result['capture_gaps'][0]['reason'])

    def test_review_worklist_reuses_verified_current_inputs_and_preserves_conflicts(self):
        prior_path = self.observed_report()
        prior = json.loads(prior_path.read_bytes())
        frame = prior['pairs'][0]['comparisons'][0]
        pair = self.scope['pairs'][0]
        receipt = json.loads((self.root/'spec/arrival.json').read_bytes())
        receipt.update(observed_page_id=pair['page_id'], observed_state_id=pair['state_id'],
                       capture_run_id='worklist-test', landing_evidence=frame['harmony_xml'],
                       frames=[{key: frame[key] for key in ('comparison_id', 'harmony_png', 'harmony_xml')}])
        self.write('spec/arrival.json', receipt)
        capture = self.write('spec/bound-capture.json', capture_index(self.root, self.scope_path, ['arrival.json']))
        name = frame['comparison_id']
        binding = {'rule_version': 'current', 'ios_sha256': digest(frame['ios_png_sha256']),
                   'harmony_sha256': frame['harmony_png']['sha256'], 'ios_region_px': frame['ios_region_px'],
                   'source_context_sha256': [],
                   'control_tree_sha256': [digest(pair['baseline']['ui_json_sha256']), frame['harmony_xml']['sha256']]}
        bindings = self.write('spec/bindings.json', {name: binding})
        old_appearance = json.loads((self.root/'spec/appearance.json').read_bytes())

        def reviewed(verdict):
            item = {'comparison_id': name, 'verdict': verdict, 'severity': 'critical', 'notes': 'reviewed'}
            group = self.write(f'spec/{verdict}.json', {'comparisons': [item]})
            review_receipt = self.write(f'spec/{verdict}.receipt.json', {
                'verified': True, 'exit_code': 0, 'report_sha256': sha256(group.read_bytes()),
                'review_inputs': {name: binding},
            })
            appearance = self.write(f'spec/{verdict}-appearance.json',
                                    {**old_appearance, **item, 'review_receipt': self.ref(review_receipt)})
            comparison = {**frame, 'verdict': verdict, 'severity': 'critical',
                          'appearance_report': self.ref(appearance)}
            return self.write(f'spec/{verdict}-prior.json', {
                **prior, 'pairs': [{**prior['pairs'][0], 'comparisons': [comparison]}],
            })

        unverified = review_worklist(self.root, self.scope_path, capture, [prior_path], review_inputs={name: binding})
        self.assertEqual(unverified['pending'][0]['reason'], 'no_matching_verified_review')
        passed = reviewed('PASS')
        failed = reviewed('FAIL')
        cli = Path(__file__).resolve().parents[1] / 'stage1_visual_report.py'
        out = self.root/'spec/worklist.json'
        result = subprocess.run([sys.executable, '-B', str(cli), 'review-worklist', '--project-root', str(self.root),
                                 '--scope', str(self.scope_path), '--capture', str(capture),
                                 '--prior-report', str(passed), '--review-inputs', str(bindings), '--out', str(out)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        worklist = json.loads(out.read_bytes())
        self.assertEqual(worklist['required_comparisons'], 1)
        self.assertEqual(worklist['comparisons'][0]['verdict'], 'PASS')
        self.assertEqual(worklist['pending'], [])
        report = self.write('spec/final.json', assemble(self.root, self.scope_path, capture, [out]))
        self.assertEqual(archive_visual(self.root, self.scope_path, report)['status'], 'PASS')
        worklist = review_worklist(self.root, self.scope_path, capture, [failed], review_inputs={name: binding})
        self.assertEqual(worklist['comparisons'][0]['verdict'], 'FAIL')
        self.assertEqual(worklist['comparisons'][0]['severity'], 'critical')
        worklist = review_worklist(self.root, self.scope_path, capture, [passed, failed], review_inputs={name: binding})
        self.assertEqual(worklist['comparisons'], [])
        self.assertEqual(worklist['pending'][0]['reason'], 'conflicting_reviews')
        stale = {**binding, 'rule_version': 'updated', 'source_context_sha256': ['a' * 64]}
        worklist = review_worklist(self.root, self.scope_path, capture, [passed], review_inputs={name: stale})
        self.assertEqual(worklist['pending'][0]['reason'], 'no_matching_verified_review')
        changed = {**binding, 'harmony_sha256': 'b' * 64}
        worklist = review_worklist(self.root, self.scope_path, capture, [passed], review_inputs={name: changed})
        self.assertEqual(worklist['pending'][0]['reason'], 'current_review_inputs_differ_from_capture')
        self.write('spec/target.png', self.png + b'tampered')
        worklist = review_worklist(self.root, self.scope_path, capture, [passed], review_inputs={name: binding})
        self.assertEqual(worklist['status'], 'BLOCKED')
        self.assertEqual(worklist['pending'][0]['reason'], 'capture_blocked')

    def test_worklist_cli_tracks_one_labeled_followup_without_accepting_it(self):
        prior = self.observed_report()
        frame = json.loads(prior.read_bytes())['pairs'][0]['comparisons'][0]
        pair = self.scope['pairs'][0]
        arrival = json.loads((self.root/'spec/arrival.json').read_bytes())
        arrival.update(observed_page_id=pair['page_id'], observed_state_id=pair['state_id'],
                       capture_run_id='followup-test', landing_evidence=frame['harmony_xml'],
                       frames=[{key: frame[key] for key in ('comparison_id', 'harmony_png', 'harmony_xml')}])
        self.write('spec/arrival.json', arrival)
        capture = self.write('spec/bound-capture.json', capture_index(self.root, self.scope_path, ['arrival.json']))
        name = frame['comparison_id']
        original = {'rule_version': 2, 'ios_sha256': digest(frame['ios_png_sha256']),
                    'harmony_sha256': frame['harmony_png']['sha256'], 'ios_region_px': frame['ios_region_px'],
                    'source_context_sha256': [], 'control_tree_sha256': [],
                    'platform_dimensions': {'ios': [1206, 2622], 'harmony': [1256, 2760]}}
        labeled = {**original, 'source_context_sha256': ['a' * 64, 'b' * 64]}
        bindings = self.write('spec/bindings.json', {name: original})

        def timed_out(group, binding, **more):
            report = self.write(f'spec/appearance-group-{group}.json', {})
            return self.write(f'spec/appearance-group-{group}.receipt.json', {
                'group': group, 'exit_code': 124, 'verified': False,
                'report_sha256': sha256(report.read_bytes()), 'review_inputs': {name: binding}, **more,
            })

        initial = timed_out(2, original)
        attempted = timed_out(3, labeled, recovery_for=2)
        cli = Path(__file__).resolve().parents[1] / 'stage1_visual_report.py'
        command = [sys.executable, '-I', '-X', 'utf8', str(cli), 'review-worklist', '--project-root', str(self.root),
                   '--scope', str(self.scope_path), '--capture', str(capture), '--review-inputs', str(bindings),
                   '--review-receipt', str(initial)]

        def run(*args, code=0):
            result = subprocess.run([*command, *args], capture_output=True, text=True)
            self.assertEqual(result.returncode, code, result.stdout + result.stderr)
            return json.loads(result.stdout)

        work = run()
        self.assertEqual(work['comparisons'], [])
        self.assertEqual(work['pending'][0]['labeled_recheck'], {'status': 'READY', 'recovery_for': 2})
        self.write('spec/bindings.json', {name: labeled})
        self.assertEqual(run()['pending'][0]['labeled_recheck']['status'], 'READY')
        work = run('--review-receipt', str(attempted))
        self.assertEqual(work['comparisons'], [])
        self.assertEqual(work['pending'][0]['labeled_recheck'], {'status': 'ATTEMPTED', 'recovery_for': 2})
        self.write('spec/bindings.json', {name: {**labeled, 'harmony_sha256': 'c' * 64}})
        self.assertNotIn('labeled_recheck', run()['pending'][0])
        self.write('spec/bindings.json', {name: original})
        self.write('spec/appearance-group-2.json', {'modified': True})
        work = run()
        self.assertNotIn('labeled_recheck', work['pending'][0])
        self.assertIn('SHA-256 mismatch', work['rejected_review_receipts'][0]['reason'])
        self.assertEqual(run('--out', str(initial), code=2)['status'], 'BLOCKED')

    def test_partial_pair_keeps_verified_comparison_for_retry(self):
        prior = self.observed_report()
        frame = json.loads(prior.read_bytes())['pairs'][0]['comparisons'][0]
        pair = self.scope['pairs'][0]
        pair['comparisons'].insert(0, {'comparison_id': 'pair:1', 'ios_region_px': None})
        self.scope_path.write_bytes(json_bytes(self.scope))
        scope_hash = sha256(self.scope_path.read_bytes())
        for kind in ('build', 'install'):
            old = self.root / f'spec/{kind}.json'
            self.write(f'spec/{kind}.json', {**json.loads(old.read_bytes()), 'scope_sha256': scope_hash})
        arr = self.root / 'spec/arrival.json'
        receipt = json.loads(arr.read_bytes())
        frames = [{k: frame[k] for k in ('comparison_id', 'harmony_png', 'harmony_xml')}]
        frames.append({**frames[0], 'comparison_id': 'pair:1'})
        receipt.update(observed_page_id=pair['page_id'], observed_state_id=pair['state_id'],
                       capture_run_id='partial-retry', landing_evidence=frame['harmony_xml'],
                       frames=frames,
                       build_receipt=self.ref(self.root/'spec/build.json'),
                       install_receipt=self.ref(self.root/'spec/install.json'))
        self.write('spec/arrival.json', receipt)
        binding = {'rule_version': 'current', 'ios_sha256': digest(frame['ios_png_sha256']),
                   'harmony_sha256': frame['harmony_png']['sha256'], 'ios_region_px': None,
                   'source_context_sha256': [], 'control_tree_sha256': []}
        details = {'comparison_id': 'pair:0', 'verdict': 'PASS', 'severity': 'normal', 'notes': 'verified'}
        group = self.write('spec/group.json', {'comparisons': [details]})
        checked = self.write('spec/group.receipt.json', {
            'verified': True, 'exit_code': 0, 'report_sha256': sha256(group.read_bytes()),
            'review_inputs': {'pair:0': binding},
        })
        app = self.root/'spec/appearance.json'
        self.write('spec/appearance.json', {**json.loads(app.read_bytes()), **details, 'review_receipt': self.ref(checked)})
        with patch('lib.stage1_visual_report.build_scope_from_inventory', return_value=self.scope), \
                patch('lib.ios_stage1_visual_gate.build_scope_from_inventory', return_value=self.scope):
            capture = self.write('spec/retry-capture.json', capture_index(self.root, self.scope_path, ['arrival.json']))
            result = assemble(self.root, self.scope_path, capture, [self.root/'spec/judge.json'])
            self.assertEqual(result['status'], 'BLOCKED')
            self.assertEqual(result['pairs'], [])
            self.assertEqual([x['comparison_id'] for x in result['partial_comparisons']], ['pair:0'])
            self.assertEqual(result['assembly_gaps'][0]['comparison_id'], 'pair:1')
            report = self.write('spec/partial.json', result)
            self.assertEqual(archive_visual(self.root, self.scope_path, report)['status'], 'BLOCKED')
            worklist = review_worklist(self.root, self.scope_path, capture, [report],
                                       review_inputs={'pair:0': binding, 'pair:1': binding})
            self.assertEqual(worklist['required_comparisons'], 2)
            self.assertEqual([x['comparison_id'] for x in worklist['comparisons']], ['pair:0'])
            self.assertEqual([x['comparison_id'] for x in worklist['pending']], ['pair:1'])
            group.write_bytes(b'modified')
            invalid = review_worklist(self.root, self.scope_path, capture, [report], review_inputs={'pair:0': binding})
            self.assertEqual(invalid['comparisons'], [])

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

    def test_foreground_diagnostic_cannot_replace_full_relationship_report(self):
        report = self.observed_report(foreground_diagnostic=True)
        result = archive_visual(self.root, self.scope_path, report)
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertIn('foreground surface diagnostics cannot satisfy visual acceptance', result['pairs'][0]['reason'])

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
        self.rebind_scope(3)
        with self.assertRaisesRegex(ValueError, 'visual repair budget exhausted'):
            self.failing_visual('critical')
        dispatch = self.root / 'spec/execution/dispatch'
        def snapshot():
            return {path.relative_to(dispatch): path.read_bytes() for path in dispatch.rglob('*') if path.is_file()}

        before = snapshot()
        diagnostic = self.result('visual', 2, '--report', 'spec/report.json', '--report-only')
        self.assertTrue(diagnostic['report_only'])
        self.assertTrue(diagnostic['assessment_complete'])
        self.assertEqual(diagnostic['status'], 'FAIL')
        self.assertNotIn('archive_path', diagnostic)
        self.assertEqual(snapshot(), before)
        passing_report = self.observed_report()
        passing = archive_visual(self.root, self.scope_path, passing_report)
        self.assertEqual(passing['status'], 'PASS')
        self.assertEqual(passing['passed_pairs'], passing['required_pairs'])
        self.assertEqual(self.result('summary', 0)['visual_round']['attempt'], 2)
        self.rebind_scope(4)
        with self.assertRaisesRegex(ValueError, 'visual repair budget exhausted'):
            self.failing_visual('critical')

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
