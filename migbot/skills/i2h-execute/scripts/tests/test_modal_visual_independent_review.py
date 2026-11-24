"""Independent R2 package review: exercise installed CLIs and preserved raw-tree audits."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parent))
import test_modal_visual_chain as fixtures
from lib.ios_ui_dispatch import sha256
from lib.ios_stage1_scope import build_scope_from_inventory
from lib.ios_ui_relationships import compare_relationships,audit_navigation_status_bar

class IndependentModalReviewTests(unittest.TestCase):
    def setUp(self):
        self.case=fixtures.ModalVisualChainTests('test_scope_retains_approved_predicate_and_actual_window_identity')
        self.case.setUp();self.addCleanup(self.case.doCleanups)
        self.root=self.case.root;self.fx=self.case.fx
        repo=Path(__file__).resolve().parents[5]
        r=subprocess.run([sys.executable,'-B',str(repo/'migbot/scripts/migbot-install.py'),
                          '--project',str(self.root)],capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        self.script=self.root/'.claude/skills/i2h-execute/scripts/stage1_capture_scope.py'

    def finalize(self,report,scope=None):
        path=self.fx.write('spec/review-capture.json',report)
        r=subprocess.run([sys.executable,'-B',str(self.script),'finalize','--project-root',str(self.root),
                          '--scope-manifest',str(scope or self.fx.scope_path),'--report',str(path)],
                         capture_output=True,text=True)
        self.assertIn(r.returncode,[0,2],r.stdout+r.stderr)
        return r,json.loads(path.read_bytes())

    def test_installed_finalize_cannot_downgrade_schema_to_remove_current_predicates(self):
        self.fx.write('.migbot/config.json',{})
        report=self.case.capture_report()
        scope=copy.deepcopy(self.fx.scope);scope['schema_version']=1;scope.pop('pairs')
        for c in report['cases']:
            c.pop('page_state_observation');c.pop('pre_capture_observation')
            c.update(observed_page_id=c['page_id'],observed_state_id=c['state_id'])
        path=self.fx.write('spec/downgraded-scope.json',scope)
        r,out=self.finalize(report,path)
        self.assertEqual((r.returncode,out['status']),(2,'visual_blocked'))

    def test_installed_prepare_rejects_scope_downgrade_with_structured_report(self):
        self.fx.write('.migbot/config.json',{})
        scope=copy.deepcopy(self.fx.scope);scope['schema_version']=1;scope.pop('pairs')
        path=self.fx.write('spec/downgraded-prepare.json',scope);out=self.root/'spec/prepare-review.json'
        r=subprocess.run([sys.executable,'-B',str(self.script),'prepare','--project-root',str(self.root),
                          '--scope-manifest',str(path),'--out',str(out)],capture_output=True,text=True)
        self.assertEqual(r.returncode,2,r.stdout+r.stderr)
        value=json.loads(out.read_bytes());self.assertEqual(value['status'],'visual_blocked')
        self.assertIn('failure_findings',value)

    def test_installed_finalize_keeps_multiple_pairs_on_one_installation(self):
        inv=json.loads((self.root/'spec/baseline/ui-delivery-approved.json').read_bytes())
        other=copy.deepcopy(inv['verification_states'][0]);other['verification_id']='pair-other'
        inv['verification_states'].append(other);self.fx.write('spec/baseline/ui-delivery-approved.json',inv)
        self.fx.scope=build_scope_from_inventory(self.root,None)
        self.fx.scope_path=self.fx.write('spec/scope.json',self.fx.scope)
        self.fx.scope_hash=sha256(self.fx.scope_path.read_bytes())
        for kind in ['build','install']:
            path=self.root/f'spec/{kind}.json';v=json.loads(path.read_bytes());v['scope_sha256']=self.fx.scope_hash
            self.fx.write(str(path.relative_to(self.root)),v)
        report=self.case.capture_report();second=copy.deepcopy(report['cases'][0]);second['pair_id']='pair-other'
        report['cases'].append(second)
        r,out=self.finalize(copy.deepcopy(report));self.assertEqual((r.returncode,out['status']),(0,'PASS'))
        receipt=json.loads((self.root/'spec/capture-install.json').read_bytes());receipt['device_id']='device-other'
        self.fx.write('spec/capture-other-install.json',receipt)
        second.update(device_id='device-other',install_receipt='spec/capture-other-install.json')
        r,out=self.finalize(report);self.assertEqual((r.returncode,out['status']),(2,'visual_blocked'))

    def test_installed_finalize_rejects_image_replacement_after_first_summary(self):
        r,report=self.finalize(self.case.capture_report());self.assertEqual(r.returncode,0,report)
        self.fx.write(report['cases'][0]['harmony_png'],self.fx.png+b'replaced')
        r,out=self.finalize(report)
        self.assertEqual((r.returncode,out['status']),(2,'visual_blocked'))

    def test_installed_finalize_rejects_install_receipts_from_other_scope(self):
        report=self.case.capture_report()
        for kind in ['build','install']:
            path=self.root/f'spec/capture-{kind}.json';receipt=json.loads(path.read_bytes())
            receipt['scope_sha256']='a'*64;self.fx.write(str(path.relative_to(self.root)),receipt)
        r,out=self.finalize(report)
        self.assertEqual((r.returncode,out['status']),(2,'visual_blocked'))

    def test_installed_finalize_does_not_promote_blocked_case_with_old_artifacts(self):
        report=self.case.capture_report();report['cases'][0].update(status='BLOCKED',reason='not reached')
        r,out=self.finalize(report)
        self.assertEqual((r.returncode,out['status']),(2,'visual_blocked'))

    def test_installed_finalize_requires_images_bound_at_capture(self):
        report=self.case.capture_report();report['cases'][0].pop('harmony_png_sha256',None)
        r,out=self.finalize(report)
        self.assertEqual((r.returncode,out['status']),(2,'visual_blocked'))

    def test_installed_finalize_cannot_escape_current_capture_directory(self):
        report=self.case.capture_report();outside=self.fx.write('spec/execution/stage1-visual/outside.jpeg',self.fx.png)
        report['cases'][0]['harmony_png']=report['capture_dir']+'/../outside.jpeg'
        r,out=self.finalize(report)
        self.assertEqual((r.returncode,out['status']),(2,'visual_blocked'))

    def test_installed_formal_capture_assemble_archive_and_smoke_bind_the_image(self):
        scripts=self.script.parent
        def run(name,args):
            r=subprocess.run([sys.executable,'-B',str(scripts/name),*args],capture_output=True,text=True)
            self.assertIn(r.returncode,[0,2],r.stdout+r.stderr)
            return r
        pair=self.fx.scope['pairs'][0]
        relationship=compare_relationships(self.root,pair,pair['comparisons'][0],self.root/'spec/target.json')
        self.fx.write('spec/relationship.json',relationship)
        index_args=['capture-index','--project-root',str(self.root),'--scope','spec/scope.json',
                    '--arrival','arrival.json','--out','spec/installed-index.json']
        r=run('stage1_visual_report.py',index_args);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        r=run('stage1_visual_report.py',['assemble','--project-root',str(self.root),'--scope','spec/scope.json',
              '--capture','spec/installed-index.json','--judgements','spec/judge.json','--out','spec/installed-final.json'])
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        visual_args=['--project-root',str(self.root),'--kind','visual','--scope','spec/scope.json',
                     '--report','spec/installed-final.json']
        r=run('stage1_acceptance.py',visual_args);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        self.fx.write('spec/installed-smoke.json',self.case.smoke())
        smoke_args=['--project-root',str(self.root),'--kind','smoke','--scope','spec/scope.json',
                    '--report','spec/installed-smoke.json']
        r=run('stage1_acceptance.py',smoke_args);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        for replacement in [None,self.fx.png+b'changed-after-receipt']:
            with self.subTest(replacement=replacement is not None):
                image=self.root/'spec/target.png'
                if replacement is None:image.unlink()
                else:image.write_bytes(replacement)
                for entry,args in [('stage1_visual_report.py',index_args),
                                   ('stage1_acceptance.py',visual_args),('stage1_acceptance.py',smoke_args)]:
                    r=run(entry,args);self.assertEqual(r.returncode,2,(entry,r.stdout,r.stderr))

    def test_installed_plan_null_validation_returns_structured_errors(self):
        script=self.root/'.claude/skills/i2h-plan/scripts/ui_delivery.py'
        for fields in [{},{'verification_states':None},{'verification_states':23}]:
            candidate=self.fx.write('spec/review-plan-input.json',{'schema_version':2,'units':[],**fields})
            out=self.root/'spec/review-plan-output.json'
            r=subprocess.run([sys.executable,'-B',str(script),'validate','--project-root',str(self.root),
                              '--inventory',str(candidate),'--out',str(out),'--require-runtime-plan'],
                             capture_output=True,text=True)
            self.assertEqual(r.returncode,2,r.stdout+r.stderr)
            value=json.loads(out.read_bytes())
            self.assertIn('runtime_verification_states_missing',
                          {item['code'] for item in value['validation']['errors']})

    def test_strict_relationship_keeps_raw_status_bar_audit(self):
        t=copy.deepcopy(self.case.tree);w=t['children'][0];w['attributes']['displayId']='0'
        back={'attributes':{'type':'BackButton','id':'nativeBack','visible':True,
              'bounds':'[12,20][50,28]','origBounds':'[12,4][50,28]'},'children':[]}
        w['children'][1]['children'][0]['children'].append(back)
        bar={'attributes':{'id':'StatusBarBox','visible':True,'displayId':'0','bounds':'[0,0][200,19]'},'children':[]}
        t['children'].append({'attributes':{'bundleName':'com.ohos.sceneboard','type':'WindowScene','focused':False},'children':[bar]})
        expected=audit_navigation_status_bar(t,['nativeBack']);self.assertEqual(expected['status'],'CLIPPED')
        path=self.fx.write('spec/status-bar-tree.json',t);pair=self.fx.scope['pairs'][0]
        report=compare_relationships(self.root,pair,pair['comparisons'][0],path,
                                     audit_status_bar=True,navigation_control_ids=['nativeBack'])
        self.assertEqual(report['navigation_status_bar'],expected)

    def test_strict_layer_filter_preserves_original_coordinate_viewport(self):
        t=copy.deepcopy(self.case.tree);t['children'][0]['attributes']['bounds']='[0,10][200,400]'
        path=self.fx.write('spec/offset-window-tree.json',t);pair=self.fx.scope['pairs'][0]
        report=compare_relationships(self.root,pair,pair['comparisons'][0],path)
        self.assertEqual(tuple(report['harmony_viewport']),(0,0,200,400))

    def test_malformed_install_identity_is_blocked_not_an_uncaught_exception(self):
        self.fx.write('spec/identity.log',b'test.target: []')
        install=json.loads((self.root/'spec/install.json').read_bytes())
        install['identity_log']['sha256']=sha256((self.root/'spec/identity.log').read_bytes())
        self.fx.write('spec/install.json',install);self.case.save_arrival(self.case.tree)
        result=self.case.index();self.assertEqual(result['status'],'BLOCKED')

if __name__=='__main__':unittest.main()
