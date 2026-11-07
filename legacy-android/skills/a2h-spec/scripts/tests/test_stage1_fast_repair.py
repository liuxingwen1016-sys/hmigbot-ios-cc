"""Stage 1 fast repair: severity tiers, bounded repair scope, carried pairs and the final smoke."""
from pathlib import Path
import copy
import json
import tempfile
import unittest

import test_ui_delivery as base
from test_ui_delivery import evidence, stage1_acceptance, stage1_visual_scope
import stage1_incremental
import stage1_visual_report


class FastRepairFlowTest(unittest.TestCase):
    def setUp(self):
        self.helper = base.DeliveryTest(); self.helper.setUp()
        self.root, self.spec = self.helper.root, self.helper.spec
        for path in self.helper.run.glob('*/*.xml'):
            path.write_text(path.read_text().replace('</node></hierarchy>',
                '<node class="TextView" text="caption" bounds="[20,120][180,150]"/></node></hierarchy>'))
        inv = self.helper.inventory(); inv['schema_version'] = 2
        inv['units'][0]['owned_ui_roles'] = ['content']
        inv['units'][0]['required_states'] = inv['units'][0]['required_states'][:1]
        inv['units'][0]['required_states'][0]['responsibility'] = 'content'
        inv['units'][1]['owned_ui_roles'] = ['content']
        inv['units'][1]['required_states'][0]['responsibility'] = 'content'
        sdk = self.root / 'sdk'; sdk.mkdir(exist_ok=True)
        (sdk / 'enums.d.ts').write_text('declare enum Alignment { Center=0, Start=1, End=2 }')
        (self.root / 'build-profile.json5').write_text('{app:{products:[{name:"default",compatibleSdkVersion:"6.0.1(21)"}]}}')
        inv['toolchain'] = {'sdk_definitions': str(sdk)}
        self.helper.inventory = lambda: copy.deepcopy(inv)
        self.helper.code_and_reports()
        stage1_acceptance.archive_generation(self.root, 'g0')
        stage1_acceptance.archive_generation(self.root, 'g1')
        self.scope_path = self.spec / 'scope.json'
        self.scope = stage1_visual_scope.build_scope(self.root)
        evidence.save(self.scope_path, self.scope)
        self.runs = 0
        self.build()

    def tearDown(self):
        self.helper.tearDown()

    def build(self):
        """Record a PASS build for the current sources and return its receipt."""
        self.runs += 1
        hap = self.spec / f'execution/fixture-{self.runs}.hap'; hap.write_bytes(b'artifact %d' % self.runs)
        self.receipt = self.spec / f'execution/build-{self.runs}.json'
        evidence.save(self.receipt, {'kind': 'build', 'unit_id': 'stage1-test', 'status': 'PASS',
            'source_sha256': stage1_acceptance.source_digest(self.root), 'scope_sha256': evidence.digest(self.scope_path),
            'hap_sha256': evidence.digest(hap), 'hap_path': hap.relative_to(self.root).as_posix()})
        report = self.spec / f'compile-{self.runs}.json'
        evidence.save(report, {'status': 'PASS', 'scope_sha256': evidence.digest(self.scope_path),
                               'build_receipt': evidence.bound_file(self.spec, self.receipt)})
        return stage1_acceptance.record(self.root, self.scope_path, report, 'compile')

    def installed(self, pair_id):
        build = self.spec / f'execution/r{self.runs}/{pair_id}.build.json'
        install = self.spec / f'execution/r{self.runs}/{pair_id}.install.json'
        details = {**evidence.read(self.receipt), 'unit_id': next(p for p in self.scope['pairs'] if p['pair_id'] == pair_id)['unit_id']}
        evidence.save(build, details)
        evidence.save(install, {**details, 'kind': 'install', 'device_id': 'test-emulator'})
        return build, install

    def row(self, pair, verdict='PASS', severity=None):
        run = f'run-{self.runs}'
        build, install = self.installed(pair['pair_id'])
        arrival = self.spec / f'execution/r{self.runs}/{pair["pair_id"]}.arrival.json'
        evidence.save(arrival, {'pair_id': pair['pair_id'], 'status': 'PASS', 'arrival_mode': pair['arrival_mode'],
            'state_setup': pair['state_setup'], 'presentation': pair['presentation'],
            'build_receipt': evidence.bound_file(self.spec, build), 'install_receipt': evidence.bound_file(self.spec, install),
            'device_id': 'test-emulator', 'capture_run_id': run, 'observed_page_id': pair['page_id'],
            'observed_state_id': pair['state_id'], 'landing_evidence': 'fixture text and state'})
        comparisons = []
        for frame in pair['android_frames']:
            capture = self.spec / 'execution/stage1-visual' / run / pair['pair_id']
            capture.mkdir(parents=True, exist_ok=True)
            png = capture / (frame['comparison_id'] + '.png'); xml = capture / (frame['comparison_id'] + '.xml')
            png.write_bytes(evidence.check_file(self.spec, frame['working_png']).read_bytes())
            xml.write_bytes(evidence.check_file(self.spec, frame['xml']).read_bytes())
            appearance = self.spec / f'execution/r{self.runs}/{frame["comparison_id"]}.appearance.json'
            evidence.save(appearance, {'comparison_id': frame['comparison_id'], 'verdict': verdict})
            comparisons.append({'comparison_id': frame['comparison_id'], 'verdict': verdict,
                'android_png_sha256': frame['png']['sha256'], 'android_region_px': frame['region_px'],
                'harmony_png': evidence.bound_file(self.spec, png), 'harmony_xml': evidence.bound_file(self.spec, xml),
                'harmony_region_px': frame['region_px'], 'harmony_density': frame['density_factor'],
                'appearance_verdict': verdict, 'appearance_report': evidence.bound_file(self.spec, appearance)})
        result = {'pair_id': pair['pair_id'], 'verdict': verdict, 'arrival_mode': pair['arrival_mode'],
                  'arrival_receipt': evidence.bound_file(self.spec, arrival), 'comparisons': comparisons}
        if severity:
            result['severity'] = severity
        return result

    def visual(self, rows):
        path = self.spec / f'visual-{self.runs}-{len(rows)}.json'
        evidence.save(path, {'scope_sha256': evidence.digest(self.scope_path), 'pairs': rows})
        return stage1_acceptance.record(self.root, self.scope_path, path)

    def pairs(self):
        return self.scope['pairs']

    def edit(self, pair):
        path = self.root / pair['target']['file']
        path.write_text(path.read_text() + '\n// repaired\n')

    def test_fail_needs_severity_and_cosmetic_is_not_a_failure(self):
        first, *rest = self.pairs()
        with self.assertRaisesRegex(ValueError, 'severity'):
            self.visual([self.row(first, 'FAIL')] + [self.row(p) for p in rest])
        with self.assertRaisesRegex(ValueError, 'cosmetic'):
            self.visual([self.row(first, 'FAIL', 'cosmetic')] + [self.row(p) for p in rest])

    def test_normal_difference_is_repaired_once_then_accepted(self):
        first, *rest = self.pairs()
        entry = self.visual([self.row(first, 'FAIL', 'normal')] + [self.row(p) for p in rest])
        self.assertEqual((entry['status'], entry['repair_scope']), ('REPAIR_REQUIRED', 'critical_and_normal'))
        self.edit(first); self.build()
        entry = self.visual([self.row(first, 'FAIL', 'normal')] + [self.row(p) for p in rest])
        self.assertEqual(entry['status'], 'PASS')
        self.assertEqual(entry['accepted_differences'], [first['pair_id']])
        summary = stage1_acceptance.summary(self.root, self.scope_path)
        self.assertTrue(summary['stage1_complete'])
        self.assertEqual(summary['accepted_differences'], [first['pair_id']])

    def test_critical_failure_gets_two_repairs_then_blocks(self):
        first, *rest = self.pairs()
        scopes = []
        for _ in range(3):
            entry = self.visual([self.row(first, 'FAIL', 'critical')] + [self.row(p) for p in rest])
            scopes.append((entry['status'], entry['repair_scope']))
            if entry['status'] == 'REPAIR_REQUIRED':
                self.edit(first); self.build()
        self.assertEqual(scopes, [('REPAIR_REQUIRED', 'critical_and_normal'), ('REPAIR_REQUIRED', 'critical_only'),
                                  ('FAIL', 'critical_only')])

    def test_second_round_leaves_normal_differences_alone(self):
        first, second, *rest = self.pairs()
        self.visual([self.row(first, 'FAIL', 'critical'), self.row(second, 'FAIL', 'normal')] + [self.row(p) for p in rest])
        self.edit(first); self.edit(second); self.build()
        entry = self.visual([self.row(first, 'FAIL', 'critical'), self.row(second, 'FAIL', 'normal')] + [self.row(p) for p in rest])
        self.assertEqual((entry['status'], entry['repair_scope']), ('REPAIR_REQUIRED', 'critical_only'))
        self.edit(first); self.build()
        entry = self.visual([self.row(first), self.row(second, 'FAIL', 'normal')] + [self.row(p) for p in rest])
        self.assertEqual((entry['status'], entry['accepted_differences']), ('PASS', [second['pair_id']]))

    def test_app_caused_arrival_failure_is_critical_and_allows_rebuild(self):
        first, *rest = self.pairs()
        _, install = self.installed(first['pair_id'])
        shot = self.spec / 'execution/blank-page.png'; shot.write_bytes(b'blank')
        failed = {'pair_id': first['pair_id'], 'verdict': 'FAIL', 'severity': 'critical', 'arrival_mode': first['arrival_mode'],
                  'arrival_failure': {'evidence': evidence.bound_file(self.spec, shot),
                                      'install_receipt': evidence.bound_file(self.spec, install)}}
        entry = self.visual([failed] + [self.row(p) for p in rest])
        self.assertEqual(entry['status'], 'REPAIR_REQUIRED')
        self.edit(first)
        self.assertEqual(self.build()['status'], 'PASS')  # the fixed package can be registered again
        with self.assertRaisesRegex(ValueError, 'critical'):
            failed['severity'] = 'normal'
            path = self.spec / 'bad.json'
            evidence.save(path, {'scope_sha256': evidence.digest(self.scope_path), 'pairs': [failed] + [self.row(p) for p in rest]})
            stage1_acceptance.record(self.root, self.scope_path, path)

    def test_unaffected_pairs_are_carried_and_need_the_final_smoke(self):
        pairs = self.pairs()
        broken = next(p for p in pairs if p['unit_id'] != pairs[0]['unit_id'])
        others = [p for p in pairs if p['unit_id'] != broken['unit_id']]
        siblings = [p for p in pairs if p['unit_id'] == broken['unit_id']]
        self.visual([self.row(p, 'FAIL', 'normal') if p is broken else self.row(p) for p in pairs])
        self.edit(broken); self.build()
        carried = [{'pair_id': p['pair_id'], 'verdict': 'PASS', 'arrival_mode': p['arrival_mode'], 'carried_from_round': 0}
                   for p in others]
        with self.assertRaisesRegex(ValueError, 'recapture required'):
            touched = [{'pair_id': p['pair_id'], 'verdict': 'PASS', 'arrival_mode': p['arrival_mode'], 'carried_from_round': 0}
                       for p in siblings]
            self.visual(carried + touched)
        entry = self.visual(carried + [self.row(p) for p in siblings])
        self.assertEqual((entry['status'], entry['carried']), ('PASS', [p['pair_id'] for p in others]))
        summary = stage1_acceptance.summary(self.root, self.scope_path)
        self.assertEqual(summary['smoke'], 'NOT_RUN')
        self.assertFalse(summary['stage1_complete'])
        self.assertEqual(stage1_acceptance.next_step(self.root, self.scope_path)['next_action'], 'run_final_smoke_on_current_hap')
        build, install = self.installed(pairs[0]['pair_id'])
        shot = self.spec / 'execution/smoke.png'; shot.write_bytes(b'landing')
        formal = sorted({p['page_id'] for p in pairs if p['arrival_mode'] == 'formal'})
        smoke = self.spec / 'smoke.json'
        report = {'scope_sha256': evidence.digest(self.scope_path), 'build_receipt': evidence.bound_file(self.spec, build),
                  'install_receipt': evidence.bound_file(self.spec, install), 'cases': []}
        if formal:
            evidence.save(smoke, report)
            with self.assertRaisesRegex(ValueError, 'every formal page'):
                stage1_acceptance.record(self.root, self.scope_path, smoke, 'smoke')
        report['cases'] = [{'page_id': page, 'arrived': True, 'evidence': evidence.bound_file(self.spec, shot)} for page in formal]
        evidence.save(smoke, report)
        self.assertEqual(stage1_acceptance.record(self.root, self.scope_path, smoke, 'smoke')['status'], 'PASS')
        self.assertTrue(stage1_acceptance.summary(self.root, self.scope_path)['stage1_complete'])


    def capture_files(self, pairs, verdicts=None):
        """What capture and judge agents write: plain relative paths, no hashes."""
        verdicts = verdicts or {}
        captured, judged = [], []
        for pair in pairs:
            verdict, severity = verdicts.get(pair['pair_id'], ('PASS', None))
            row = self.row(pair, verdict, severity)
            frames = []
            for c in row['comparisons']:
                frames.append({'comparison_id': c['comparison_id'], 'harmony_png': c['harmony_png']['path'],
                               'harmony_xml': c['harmony_xml']['path'], 'harmony_region_px': c['harmony_region_px'],
                               'harmony_density': c['harmony_density']})
                item = {'comparison_id': c['comparison_id'], 'verdict': verdict, 'appearance_report': c['appearance_report']['path']}
                if severity:
                    item['severity'] = severity
                judged.append(item)
            captured.append({'pair_id': pair['pair_id'], 'arrival_receipt': row['arrival_receipt']['path'], 'frames': frames})
        capture = self.spec / f'capture-{self.runs}.json'; evidence.save(capture, {'pairs': captured})
        judgement = self.spec / f'judge-{self.runs}.json'; evidence.save(judgement, {'comparisons': judged})
        return capture, judgement

    def test_report_is_assembled_by_script_and_accepted(self):
        pairs = self.pairs()
        capture, judgement = self.capture_files(pairs, {pairs[0]['pair_id']: ('FAIL', 'normal')})
        report, errors = stage1_visual_report.assemble(self.root, self.scope_path, capture, [judgement])
        self.assertEqual(errors, [])
        path = self.spec / 'assembled.json'; evidence.save(path, report)
        entry = stage1_acceptance.record(self.root, self.scope_path, path)
        self.assertEqual((entry['status'], entry['normal']), ('REPAIR_REQUIRED', [pairs[0]['pair_id']]))
        # Repair one unit, recapture only what the plan asks for and carry the rest.
        self.edit(pairs[0]); self.build()
        planned = stage1_visual_report.plan(self.root, self.scope_path)
        self.assertEqual(planned['recapture'], [pairs[0]['pair_id']])
        capture, judgement = self.capture_files([p for p in pairs if p['pair_id'] in planned['recapture']])
        report, errors = stage1_visual_report.assemble(self.root, self.scope_path, capture, [judgement], carry_from=0)
        self.assertEqual(errors, [])
        evidence.save(path, report)
        entry = stage1_acceptance.record(self.root, self.scope_path, path)
        self.assertEqual((entry['status'], entry['carried']), ('PASS', planned['carry']))

    def test_empty_dump_and_unjudged_frames_are_listed_not_crashed(self):
        pairs = self.pairs()
        capture, judgement = self.capture_files(pairs)
        data = evidence.read(capture)
        (self.spec / data['pairs'][0]['frames'][0]['harmony_xml']).write_text('')
        evidence.save(capture, data)
        evidence.save(judgement, {'comparisons': evidence.read(judgement)['comparisons'][1:]})
        report, errors = stage1_visual_report.assemble(self.root, self.scope_path, capture, [judgement])
        self.assertTrue(any('no judgement' in e or 'empty or unreadable' in e for e in errors))
        self.assertTrue(errors)


class AffectedPairsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); root = Path(self.tmp.name)
        ets = root / 'entry/src/main/ets'
        files = {
            'pages/Index.ets': "import { APage } from './APage'\nimport { BPage } from './BPage'\n@Builder function pageMap() {}\n",
            'pages/APage.ets': "import { Card } from '../components/Card'\nimport { CContent } from '../components/CContent'\nstruct APage { build() { Text($r('app.color.accent')) } }\n",
            'components/CContent.ets': "export struct CContent { build() { Text('child') } }\n",
            'pages/BPage.ets': "struct BPage { build() { Image($r('app.media.logo')) } }\n",
            'components/Card.ets': "export struct Card { build() { Text('card') } }\n",
            'entryability/EntryAbility.ets': "export default class EntryAbility {}\n",
        }
        for rel, text in files.items():
            (ets / rel).parent.mkdir(parents=True, exist_ok=True); (ets / rel).write_text(text)
        res = root / 'entry/src/main/resources/base'
        (res / 'element').mkdir(parents=True); (res / 'media').mkdir()
        (res / 'element/color.json').write_text(json.dumps({'color': [{'name': 'accent', 'value': '#111111'},
                                                                      {'name': 'unused', 'value': '#222222'}]}))
        (res / 'media/logo.png').write_bytes(b'logo')
        (root / 'entry/src/main/module.json5').write_text('{module:{}}')
        self.root = root
        self.scope = {'pairs': [{'pair_id': 'a.default', 'unit_id': 'a', 'target': {'file': 'entry/src/main/ets/pages/APage.ets'}},
                                {'pair_id': 'b.default', 'unit_id': 'b', 'target': {'file': 'entry/src/main/ets/pages/BPage.ets'}},
                                {'pair_id': 'c.default', 'unit_id': 'c', 'target': {'file': 'entry/src/main/ets/components/CContent.ets'}}]}
        self.files = stage1_incremental.source_files(root)
        self.resources = stage1_incremental.resource_entries(root)

    def tearDown(self):
        self.tmp.cleanup()

    def affected(self):
        return stage1_incremental.affected(self.root, self.scope, self.files, self.resources)

    def change(self, rel, text):
        (self.root / rel).write_text(text)

    def test_shared_component_change_hits_only_its_users(self):
        self.change('entry/src/main/ets/components/Card.ets', "export struct Card { build() { Text('new') } }\n")
        self.assertEqual(sorted(self.affected()['pairs']), ['a.default'])

    def test_host_change_reaches_the_children_it_shows(self):
        self.change('entry/src/main/ets/pages/APage.ets', "import { CContent } from '../components/CContent'\nstruct APage {}\n")
        self.assertEqual(sorted(self.affected()['pairs']), ['a.default', 'c.default'])
        self.change('entry/src/main/ets/components/CContent.ets', "export struct CContent { build() { Text('new') } }\n")
        self.assertEqual(sorted(self.affected()['pairs']), ['a.default', 'c.default'])

    def test_router_change_reaches_every_routed_page(self):
        self.change('entry/src/main/ets/pages/Index.ets', "import { APage } from './APage'\nimport { BPage } from './BPage'\n// fixed\n")
        self.assertEqual(sorted(self.affected()['pairs']), ['a.default', 'b.default', 'c.default'])
        self.assertEqual(self.affected()['global'], [])

    def test_resource_entries_are_compared_one_by_one(self):
        path = 'entry/src/main/resources/base/element/color.json'
        self.change(path, json.dumps({'color': [{'name': 'accent', 'value': '#111111'}, {'name': 'unused', 'value': '#999999'},
                                                {'name': 'added', 'value': '#000000'}]}))
        self.assertEqual(self.affected()['pairs'], {})
        self.change(path, json.dumps({'color': [{'name': 'accent', 'value': '#ff0000'}]}))
        self.assertEqual(sorted(self.affected()['pairs']), ['a.default'])
        (self.root / 'entry/src/main/resources/base/media/logo.png').write_bytes(b'new logo')
        self.assertEqual(sorted(self.affected()['pairs']), ['a.default', 'b.default'])

    def test_unowned_code_and_configuration_are_global(self):
        self.change('entry/src/main/ets/entryability/EntryAbility.ets', 'export default class EntryAbility { x = 1 }\n')
        result = self.affected()
        self.assertTrue(result['global']); self.assertEqual(len(result['pairs']), 3)
        self.change('entry/src/main/ets/entryability/EntryAbility.ets', 'export default class EntryAbility {}\n')
        self.change('entry/src/main/module.json5', '{module:{name:"entry"}}')
        self.assertEqual(len(self.affected()['pairs']), 3)


if __name__ == '__main__':
    unittest.main()
