"""Strict visual observation replay, preserving the online legacy/G0 acceptance contracts."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from zipfile import ZipFile
from unittest.mock import patch

HERE = Path(__file__).resolve()
SCRIPTS = HERE.parents[1]
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(HERE.parents[3] / 'i2h-verify/scripts'))
import test_ios_stage1_visual_gate as fixtures
from lib.ios_stage1_scope import build_scope_from_inventory
from lib.ios_stage1_visual_gate import archive_visual, _arrival
from lib.ios_ui_dispatch import json_bytes, sha256
from lib.ios_ui_relationships import compare_relationships
from lib.stage1_visual_report import capture_index, assemble
from uitest_checkpoint import write_visual_arrival
from uitest_action import native


def node(**attrs):
    return {'attributes': {'visible': True, **attrs}, 'children': []}


class ModalVisualChainTests(unittest.TestCase):
    def setUp(self):
        self.fx = fixtures.IOSVisualGateTests('test_verified_artifacts_are_archived_and_tampering_is_visible')
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        self.root = self.fx.root
        self.pred = {'bundle': 'test.target', 'page_path': 'pages/Root',
                     'present': [{'id': 'continue'}], 'absent': [{'id': 'error'}]}
        inv = json.loads((self.root / 'spec/baseline/ui-delivery-approved.json').read_bytes())
        inv['verification_states'][0]['target_observation'] = self.pred
        self.fx.write('spec/baseline/ui-delivery-approved.json', inv)
        self.fx.write('.migbot/config.json', {'native_visual_observation': 'native-page-state-v2'})
        self.fx.scope = build_scope_from_inventory(self.root, None)
        self.fx.scope_path = self.fx.write('spec/scope.json', self.fx.scope)
        self.fx.scope_hash = sha256(self.fx.scope_path.read_bytes())
        # Generate existing appearance/build/install fixture, then replace its legacy raw layout
        # with a real window + modal and a native observation arrival. No verdict is hand-sealed.
        pair = self.fx.scope['pairs'][0]
        approved_predicate = pair.pop('target_observation')
        self.fx.observed_report()
        pair['target_observation'] = approved_predicate
        with ZipFile(self.root/'entry/build/test.hap','w') as package:
            package.writestr('module.json', json.dumps({'app': {'bundleName':'test.target','versionCode':1}}))
        self.fx.write('spec/installed.log', b'msg:install bundle successfully.\n')
        self.fx.write('spec/identity.log', b'test.target: {"bundleName":"test.target","versionCode":1}')
        for kind in ['build','install']:
            receipt=json.loads((self.root/f'spec/{kind}.json').read_bytes())
            receipt['hap_sha256']=sha256((self.root/'entry/build/test.hap').read_bytes())
            if kind=='install':
                receipt.update(bundle='test.target',version_code=1,
                    install_log={'path':'spec/installed.log','sha256':sha256((self.root/'spec/installed.log').read_bytes())},
                    identity_log={'path':'spec/identity.log','sha256':sha256((self.root/'spec/identity.log').read_bytes())})
            self.fx.write(f'spec/{kind}.json', receipt)
        target = json.loads((self.root / 'spec/target.json').read_bytes())
        children = target['children']
        for child in children:
            child['attributes']['visible'] = True
        children[0]['attributes']['id'] = 'heading'
        children[1]['attributes']['id'] = 'continue'
        sheet = node(type='SheetPage', focused=True)
        sheet['children'] = children
        wrapper = node(type='SheetWrapper', focused=True)
        wrapper['children'] = [sheet]
        window = node(type='Window', bundleName='test.target', focused=True,
                      pagePath='pages/Root', hostWindowId='1', bounds='[0,0][200,400]')
        window['children'] = [node(id='base-only', type='Text', text='Covered'), wrapper]
        foreign = node(type='Window', bundleName='other.app', focused=False,
                       pagePath='pages/Other', hostWindowId='2')
        foreign['children'] = [node(id='foreign-only', type='Text', text='Secret')]
        self.tree = {'attributes': target['attributes'], 'children': [window, foreign]}
        self.save_arrival(self.tree)

    def save_arrival(self, tree):
        target = self.fx.write('spec/target.json', tree)
        return write_visual_arrival(self.root / 'spec', self.root / 'spec/arrival.json',
            pair=self.fx.scope['pairs'][0], capture_run_id='native-run', device_id='fixture-target',
            screenshot=self.root / 'spec/target.png', layout=target, matched_tree=tree, pre_capture_tree=tree,
            build_receipt=self.root / 'spec/build.json', install_receipt=self.root / 'spec/install.json')

    def index(self):
        return capture_index(self.root, self.fx.scope_path, ['arrival.json'])

    def rehash_arrival(self, mutate):
        value = json.loads((self.root / 'spec/arrival.json').read_bytes())
        mutate(value)
        self.fx.write('spec/arrival.json', value)

    def test_scope_retains_approved_predicate_and_actual_window_identity(self):
        self.assertEqual(self.fx.scope['pairs'][0]['target_observation'], self.pred)
        value = json.loads((self.root / 'spec/arrival.json').read_bytes())
        self.assertEqual(value['observed_window'], {'bundle': 'test.target', 'page_path': 'pages/Root'})
        self.assertNotIn('observed_page_id', value)
        self.assertEqual(value['page_state_observation']['matched'][0]['id'], 'continue')
        self.assertEqual(self.index()['status'], 'READY')

    def test_background_base_page_and_foreign_window_cannot_satisfy_approved_predicate(self):
        for ident in ['base-only', 'foreign-only']:
            with self.subTest(ident=ident):
                pred = {**self.pred, 'present': [{'id': ident}]}
                with self.assertRaisesRegex(ValueError, 'does not satisfy'):
                    native.observe_state(self.tree, pred)
                pair = copy.deepcopy(self.fx.scope['pairs'][0])
                pair['target_observation'] = pred
                with self.assertRaisesRegex(ValueError, 'does not satisfy'):
                    write_visual_arrival(self.root/'spec', self.root/'spec/rejected.json', pair=pair,
                        capture_run_id='native-run', device_id='fixture-target', screenshot=self.root/'spec/target.png',
                        layout=self.root/'spec/target.json', matched_tree=self.tree, pre_capture_tree=self.tree,
                        build_receipt=self.root/'spec/build.json', install_receipt=self.root/'spec/install.json')
                self.assertFalse((self.root/'spec/rejected.json').exists())

    def test_observation_and_window_metadata_tampering_cannot_pass(self):
        saved = (self.root/'spec/arrival.json').read_bytes()
        for mutate in [lambda x: x['page_state_observation'].update(predicate_sha256='0'*64),
                       lambda x: x['page_state_observation']['matched'][0].update(text='forged'),
                       lambda x: x['observed_window'].update(bundle='other.app'),
                       lambda x: x.update(declared_state_id='other-state')]:
            (self.root/'spec/arrival.json').write_bytes(saved)
            self.rehash_arrival(mutate)
            self.assertEqual(self.index()['status'], 'BLOCKED')

    def test_raw_layout_change_and_rehashed_wrong_state_both_block(self):
        wrong = copy.deepcopy(self.tree)
        wrong['children'][0]['children'][1]['children'][0]['children'][1]['attributes']['id'] = 'wrong-control'
        self.fx.write('spec/target.json', wrong)
        self.assertEqual(self.index()['status'], 'BLOCKED')
        self.rehash_arrival(lambda x: x['frames'][0].update(harmony_xml=self.fx.ref(self.root/'spec/target.json')))
        # Hash-valid but wrong active-layer evidence must still fail semantic replay.
        self.assertEqual(self.index()['status'], 'BLOCKED')

    def test_image_and_tree_rebinding_in_comparison_cannot_pass(self):
        index = self.index()
        self.assertEqual(index['status'], 'READY')
        arrival = json.loads((self.root/'spec/arrival.json').read_bytes())
        pair = self.fx.scope['pairs'][0]
        actual = {'arrival_receipt': self.fx.ref(self.root/'spec/arrival.json'),
                  'comparisons': copy.deepcopy(arrival['frames'])}
        alternate = self.fx.write('spec/other.jpeg', self.fx.png)
        actual['comparisons'][0]['harmony_png'] = self.fx.ref(alternate)
        with self.assertRaisesRegex(ValueError, 'frames differ'):
            _arrival(self.root, pair, actual, self.fx.scope_hash, self.fx.scope['source_sha256'])
        self.fx.write('spec/target.png', b'corrupted screenshot')
        self.assertEqual(self.index()['status'], 'BLOCKED')

    def test_capture_and_final_archive_replay_real_same_pair(self):
        index = self.index()
        capture = self.fx.write('spec/capture.json', index)
        pair = self.fx.scope['pairs'][0]
        rel = compare_relationships(self.root, pair, pair['comparisons'][0], self.root/'spec/target.json')
        self.assertEqual(rel['verdict'], 'PASS')
        self.fx.write('spec/relationship.json', rel)
        report = self.fx.write('spec/report.json', assemble(self.root, self.fx.scope_path, capture,
                                                          [self.root/'spec/judge.json']))
        self.assertEqual(archive_visual(self.root, self.fx.scope_path, report)['status'], 'PASS')
        # A forged valid-hash receipt cannot turn background-only controls into active evidence.
        tree = copy.deepcopy(self.tree)
        tree['children'][0]['children'][0]['attributes'].update(id='continue')
        tree['children'][0]['children'][1]['children'][0]['children'][1]['attributes']['id'] = 'different'
        self.fx.write('spec/target.json', tree)
        self.assertEqual(archive_visual(self.root, self.fx.scope_path, report)['status'], 'BLOCKED')

    def test_formal_smoke_replays_native_modal_observation(self):
        from lib.ios_stage1_progress import validate_smoke
        log = self.fx.write('spec/start.log', b'synthetic successful cold-start output')
        arrival = json.loads((self.root/'spec/arrival.json').read_bytes())
        cold = self.fx.write('spec/cold.json', {
            'kind':'cold_start','status':'PASS','device_id':'fixture-target',
            'capture_run_id':'native-run','hap_sha256':sha256((self.root/'entry/build/test.hap').read_bytes()),
            'scope_sha256':self.fx.scope_hash,'source_sha256':self.fx.scope['source_sha256'],
            'evidence':self.fx.ref(log)})
        smoke = {'scope_sha256':self.fx.scope_hash,'build_receipt':arrival['build_receipt'],
                 'install_receipt':arrival['install_receipt'],'cold_start':self.fx.ref(cold),
                 'cases':[{'page_id':self.fx.scope['pairs'][0]['page_id'],'arrived':True,
                           'evidence':self.fx.ref(self.root/'spec/arrival.json')}]}
        self.assertEqual(validate_smoke(self.root,self.fx.scope,self.fx.scope_hash,smoke)['device_id'],
                         'fixture-target')
        self.rehash_arrival(lambda x:x['page_state_observation'].update(predicate_sha256='0'*64))
        smoke['cases'][0]['evidence']=self.fx.ref(self.root/'spec/arrival.json')
        with self.assertRaisesRegex(ValueError, 'observation differs'):
            validate_smoke(self.root,self.fx.scope,self.fx.scope_hash,smoke)

    def test_capture_summary_cannot_downgrade_a_native_claim(self):
        from lib.stage1_capture_scope import finalize
        from lib.stage1_contract import digest
        directory='spec/execution/stage1-visual/synthetic'
        tree=self.fx.write(directory+'/tree.json',self.tree)
        image=self.fx.write(directory+'/shot.jpeg',self.fx.png)
        observation={**native.observe_state(self.tree,self.pred),'layout_sha256':sha256(tree.read_bytes())}
        for kind in ['build','install']:
            receipt=json.loads((self.root/f'spec/{kind}.json').read_bytes())
            receipt['hap_sha256']=digest(self.root/'entry/build/test.hap')
            self.fx.write(f'spec/capture-{kind}.json',receipt)
        before_tree=self.fx.write(directory+'/before.json',self.tree)
        before_observation={**native.observe_state(self.tree,self.pred),'layout_sha256':sha256(before_tree.read_bytes())}
        base={'pair_id':self.fx.scope['pairs'][0]['pair_id'], 'pre_capture_tree':str(before_tree.relative_to(self.root)),
              'pre_capture_observation':before_observation, 'status':'READY','capture_run_id':'run-one','device_id':'fixture-target',
              'page_id':self.fx.scope['pairs'][0]['page_id'],'state_id':'default',
              'declared_page_id':self.fx.scope['pairs'][0]['page_id'],'declared_state_id':'default',
              'harmony_ui_json':str(tree.relative_to(self.root)),
              'harmony_png':str(image.relative_to(self.root)), 'harmony_png_sha256':sha256(image.read_bytes()), 'page_state_observation':observation,
              'landing_evidence':str(tree.relative_to(self.root)),
              'build_receipt':'spec/capture-build.json','install_receipt':'spec/capture-install.json'}
        report={'run_id':'run-one','capture_dir':directory,'source_sha256':self.fx.scope['source_sha256'],
                'cases':[base]}
        value=finalize(self.root,self.fx.scope_path,copy.deepcopy(report))
        self.assertEqual(value['status'],'PASS',value)
        del report['cases'][0]['page_state_observation']
        report['cases'][0].update(observed_page_id=base['page_id'],observed_state_id='default')
        self.assertEqual(finalize(self.root,self.fx.scope_path,report)['status'],'visual_blocked')

    def test_strict_configuration_has_no_legacy_label_only_fallback(self):
        saved = (self.root/'spec/arrival.json').read_bytes()
        self.rehash_arrival(lambda x: x.pop('page_state_observation'))
        self.assertEqual(self.index()['status'], 'BLOCKED')
        (self.root/'spec/arrival.json').write_bytes(saved)
        scope = copy.deepcopy(self.fx.scope)
        scope['pairs'][0].pop('target_observation')
        with self.assertRaisesRegex(ValueError, 'predicate required'):
            _arrival(self.root, scope['pairs'][0], {'arrival_receipt': self.fx.ref(self.root/'spec/arrival.json')},
                     self.fx.scope_hash, self.fx.scope['source_sha256'])

    def smoke(self):
        log=self.fx.write('spec/start.log',b'cold start')
        receipt=json.loads((self.root/'spec/arrival.json').read_bytes())
        cold=self.fx.write('spec/cold.json',{'kind':'cold_start','status':'PASS','device_id':'fixture-target',
            'capture_run_id':'native-run','hap_sha256':sha256((self.root/'entry/build/test.hap').read_bytes()),
            'scope_sha256':self.fx.scope_hash,'source_sha256':self.fx.scope['source_sha256'],
            'evidence':self.fx.ref(log)})
        return {'scope_sha256':self.fx.scope_hash,'build_receipt':receipt['build_receipt'],
                'install_receipt':receipt['install_receipt'],'cold_start':self.fx.ref(cold),
                'cases':[{'page_id':self.fx.scope['pairs'][0]['page_id'],'arrived':True,
                          'evidence':self.fx.ref(self.root/'spec/arrival.json')}]}

    def test_writer_and_formal_replay_both_reject_modal_appearing_or_disappearing(self):
        # Both states deliberately satisfy the SAME ID predicate and native route.
        # Active-layer continuity, rather than an incidental absent ID, must reject them.
        base=copy.deepcopy(self.tree)
        base['children'][0]['children']=copy.deepcopy(self.tree['children'][0]['children'][1]['children'][0]['children'])
        modal=copy.deepcopy(self.tree)
        for before,after in [(base,modal),(modal,base)]:
            with self.subTest(before_modal=before is modal):
                self.save_arrival(after)
                with self.assertRaisesRegex(ValueError,'active native layer changed'):
                    write_visual_arrival(self.root/'spec',self.root/'spec/rejected-transition.json',
                        pair=self.fx.scope['pairs'][0],capture_run_id='native-run',device_id='fixture-target',
                        screenshot=self.root/'spec/target.png',layout=self.root/'spec/target.json',
                        matched_tree=after,pre_capture_tree=before,
                        build_receipt=self.root/'spec/build.json',install_receipt=self.root/'spec/install.json')
                self.assertFalse((self.root/'spec/rejected-transition.json').exists())
                path=self.fx.write('spec/arrival.before.json',before)
                observation={**native.observe_state(before,self.pred),'layout_sha256':sha256(path.read_bytes())}
                self.rehash_arrival(lambda r:r.update(pre_capture_tree=self.fx.ref(path),
                                                     pre_capture_observation=observation))
                self.assertEqual(self.index()['status'],'BLOCKED')

    def test_smoke_blocks_missing_screenshot(self):
        from lib.ios_stage1_progress import validate_smoke
        report=self.smoke();(self.root/'spec/target.png').unlink()
        with self.assertRaises((OSError,ValueError)):
            validate_smoke(self.root,self.fx.scope,self.fx.scope_hash,report)

    def test_smoke_blocks_replaced_screenshot_with_valid_format(self):
        from lib.ios_stage1_progress import validate_smoke
        report=self.smoke();self.fx.write('spec/target.png',self.fx.png+b'changed')
        with self.assertRaises(ValueError):
            validate_smoke(self.root,self.fx.scope,self.fx.scope_hash,report)

    def test_strict_replay_rejects_missing_or_wrong_installed_identity(self):
        install=json.loads((self.root/'spec/install.json').read_bytes())
        for mutate in [lambda r:r.pop('bundle'), lambda r:r.update(bundle='wrong.app'),
                       lambda r:r.pop('identity_log')]:
            with self.subTest(mutate=mutate):
                value=copy.deepcopy(install);mutate(value);self.fx.write('spec/install.json',value)
                self.save_arrival(self.tree)
                self.assertEqual(self.index()['status'],'BLOCKED')
        self.fx.write('spec/install.json',install)
        self.save_arrival(self.tree)
        self.assertEqual(self.index()['status'],'READY')

    def test_wrong_predicate_and_tree_bundle_cannot_override_real_installed_hap(self):
        inv=json.loads((self.root/'spec/baseline/ui-delivery-approved.json').read_bytes())
        inv['verification_states'][0]['target_observation']['bundle']='wrong.app'
        self.fx.write('spec/baseline/ui-delivery-approved.json',inv)
        self.fx.scope=build_scope_from_inventory(self.root,None)
        self.fx.scope_path=self.fx.write('spec/scope.json',self.fx.scope)
        self.fx.scope_hash=sha256(self.fx.scope_path.read_bytes())
        for kind in ['build','install']:
            value=json.loads((self.root/f'spec/{kind}.json').read_bytes());value['scope_sha256']=self.fx.scope_hash
            self.fx.write(f'spec/{kind}.json',value)
        wrong=copy.deepcopy(self.tree);wrong['children'][0]['attributes']['bundleName']='wrong.app'
        self.save_arrival(wrong)
        self.assertEqual(self.index()['status'],'BLOCKED')

    def test_replay_rejects_missing_or_rebound_pre_image_tree(self):
        raw=(self.root/'spec/arrival.json').read_bytes()
        self.rehash_arrival(lambda r:r.pop('pre_capture_tree'))
        self.assertEqual(self.index()['status'],'BLOCKED')
        (self.root/'spec/arrival.json').write_bytes(raw)
        before=copy.deepcopy(self.tree);before['children'][0]['children'].pop()
        self.fx.write('spec/arrival.before.json',before)
        self.rehash_arrival(lambda r:r.update(pre_capture_tree=self.fx.ref(self.root/'spec/arrival.before.json')))
        self.assertEqual(self.index()['status'],'BLOCKED')

    def test_relationship_target_anchors_only_in_covered_base_do_not_pass(self):
        value=copy.deepcopy(self.tree)
        window=value['children'][0];sheet=window['children'][1]['children'][0]
        heading=sheet['children'].pop(0)
        window['children'].insert(0,heading)
        path=self.fx.write('spec/covered-heading.json',value)
        pair=self.fx.scope['pairs'][0]
        report=compare_relationships(self.root,pair,pair['comparisons'][0],path)
        self.assertNotEqual(report['verdict'],'PASS')
        self.assertEqual(report['matched_anchors'],1)

    def capture_report(self):
        from lib.stage1_contract import digest
        directory='spec/execution/stage1-visual/synthetic'
        tree=self.fx.write(directory+'/tree.json',self.tree)
        before=self.fx.write(directory+'/before.json',self.tree)
        image=self.fx.write(directory+'/shot.jpeg',self.fx.png)
        for kind in ['build','install']:
            receipt=json.loads((self.root/f'spec/{kind}.json').read_bytes())
            receipt['hap_sha256']=digest(self.root/'entry/build/test.hap')
            self.fx.write(f'spec/capture-{kind}.json',receipt)
        pair=self.fx.scope['pairs'][0]
        case={'pair_id':pair['pair_id'],'page_id':pair['page_id'],'state_id':pair['state_id'],
              'declared_page_id':pair['page_id'],'declared_state_id':pair['state_id'],
              'status':'READY','capture_run_id':'r','device_id':'fixture-target',
              'harmony_ui_json':str(tree.relative_to(self.root)),'harmony_png':str(image.relative_to(self.root)),
              'harmony_png_sha256':sha256(image.read_bytes()),
              'pre_capture_tree':str(before.relative_to(self.root)),
              'pre_capture_observation':{**native.observe_state(self.tree,self.pred),'layout_sha256':sha256(before.read_bytes())},
              'page_state_observation':{**native.observe_state(self.tree,self.pred),'layout_sha256':sha256(tree.read_bytes())},
              'landing_evidence':str(tree.relative_to(self.root)),
              'build_receipt':'spec/capture-build.json','install_receipt':'spec/capture-install.json'}
        return {'run_id':'r','capture_dir':directory,'source_sha256':self.fx.scope['source_sha256'],'cases':[case]}

    def test_capture_summary_rejects_predicate_removed_from_supplied_scope_without_config(self):
        from lib.stage1_capture_scope import finalize
        self.fx.write('.migbot/config.json',{})
        report=self.capture_report()
        self.assertEqual(finalize(self.root,self.fx.scope_path,copy.deepcopy(report))['status'],'PASS')
        supplied=copy.deepcopy(self.fx.scope);supplied['pairs'][0].pop('target_observation')
        bad=self.fx.write('spec/stripped-scope.json',supplied)
        report['cases'][0].pop('page_state_observation')
        report['cases'][0].update(observed_page_id=report['cases'][0]['page_id'],
                                 observed_state_id=report['cases'][0]['state_id'])
        self.assertEqual(finalize(self.root,bad,report)['status'],'visual_blocked')

    def test_capture_summary_uses_pair_id_for_same_page_state_and_requires_every_pair(self):
        from lib.stage1_capture_scope import finalize,prepare
        inv=json.loads((self.root/'spec/baseline/ui-delivery-approved.json').read_bytes())
        other=copy.deepcopy(inv['verification_states'][0]);other['verification_id']='pair-second'
        other['target_observation']['present']=[{'id':'heading'}]
        inv['verification_states'].append(other)
        self.fx.write('spec/baseline/ui-delivery-approved.json',inv)
        self.fx.scope=build_scope_from_inventory(self.root,None)
        self.fx.scope_path=self.fx.write('spec/scope.json',self.fx.scope)
        self.fx.scope_hash=sha256(self.fx.scope_path.read_bytes())
        for kind in ['build','install']:
            v=json.loads((self.root/f'spec/{kind}.json').read_bytes());v['scope_sha256']=self.fx.scope_hash
            self.fx.write(f'spec/{kind}.json',v)
        self.assertEqual(len(prepare(self.root,self.fx.scope_path)['cases']),2)
        report=self.capture_report()
        self.assertEqual(finalize(self.root,self.fx.scope_path,copy.deepcopy(report))['status'],'visual_blocked')
        extra=copy.deepcopy(report['cases'][0]);extra['pair_id']='pair-second'
        report['cases'].append(extra)
        self.assertEqual(finalize(self.root,self.fx.scope_path,copy.deepcopy(report))['status'],'visual_blocked')
        pred=other['target_observation'];obs=native.observe_state(self.tree,pred)
        for field in ['pre_capture_observation','page_state_observation']:
            extra[field]={**obs,'layout_sha256':extra[field]['layout_sha256']}
        self.assertEqual(finalize(self.root,self.fx.scope_path,copy.deepcopy(report))['status'],'PASS')
        report['cases'][1]['pair_id']=report['cases'][0]['pair_id']
        self.assertEqual(finalize(self.root,self.fx.scope_path,report)['status'],'visual_blocked')


if __name__ == '__main__':
    unittest.main()
