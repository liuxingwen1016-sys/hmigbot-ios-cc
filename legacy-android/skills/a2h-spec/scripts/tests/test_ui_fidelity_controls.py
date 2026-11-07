"""Behavioral regressions for layout generation, ownership and honest acceptance."""
from pathlib import Path
import copy
import json
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

import test_ui_delivery as base
from test_ui_delivery import evidence, ui_delivery, ui_delivery_inputs, ui_dispatch, stage1_acceptance, stage1_visual_scope
import ui_layout_lint
import ui_relationships
import ui_state_ownership
import ui_isolation_audit
import source_layout
import apply_writeback

class SourceLayoutTest(unittest.TestCase):
    def test_constraints_and_dimen_are_source_bound_not_measured(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); android=root/'android';res=android/'app/src/main/res'
            (res/'layout').mkdir(parents=True);(res/'values').mkdir()
            (res/'values/dimens.xml').write_text('<resources><dimen name="edge">16dp</dimen></resources>')
            layout=res/'layout/top.xml'
            layout.write_text('<FrameLayout xmlns:android="http://schemas.android.com/apk/res/android" android:layout_height="wrap_content"><ImageView android:layout_width="75dp" android:layout_gravity="end" android:layout_marginEnd="@dimen/edge"/></FrameLayout>')
            evidence.save(root/'spec/.a2h/target-input.json',{'android_root':str(android),'source_sets':[{'name':'app:main','priority':0,'res_dirs':['app/src/main/res']}]})
            evidence.save(root/'spec/baseline/ui-snapshots/p/meta.json',{'layout_sources':['app/src/main/res/layout/top.xml']})
            data=source_layout.extract(root,{'unit_id':'unit','page_id':'p'})
            self.assertEqual(data['authority'],'source_constraints_v1')
            self.assertEqual(data['nodes'][0]['constraints']['android:layout_height'],'wrap_content')
            self.assertEqual(data['nodes'][1]['constraints']['android:layout_gravity'],'end')
            self.assertEqual(data['nodes'][1]['dimensions']['android:layout_marginEnd']['value'],16)
            self.assertTrue(all(x['sha256']==evidence.digest(x['file']) for x in data['sources']))
            self.assertNotIn('bounds',str(data))

class LayoutLintTest(unittest.TestCase):
    def test_sdk_bare_enum_members_are_not_skipped_after_commas(self):
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp)/'alignment.d.ts').write_text('declare enum Alignment { TopStart, Top, TopEnd, Start, Center, End, BottomStart, Bottom, BottomEnd }')
            enums,_=ui_layout_lint.sdk_enums(temp)
            self.assertEqual(enums['Alignment'],{'TopStart','Top','TopEnd','Start','Center','End','BottomStart','Bottom','BottomEnd'})
            self.assertEqual(ui_layout_lint.check('Text("x").align(Alignment.Center)',enums=enums)['status'],'PASS')

    def test_wrong_members_caught_using_actual_sdk_definition(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'enums.d.ts';p.write_text('declare enum Alignment { Start=0, Center=1, End=2 }\ndeclare enum ImageSize { FILL=0, Cover=1 }')
            enums,seals=ui_layout_lint.sdk_enums(temp)
            result=ui_layout_lint.check('Text("a").align(Alignment.CenterEnd)\nImage("x").backgroundImageSize(ImageSize.Fill)',enums=enums)
            self.assertEqual(result['status'],'FAIL')
            self.assertEqual({f['symbol'] for f in result['findings'] if f['code']=='SDK_MEMBER_UNKNOWN'},{'Alignment.CenterEnd','ImageSize.Fill'})
            self.assertEqual(seals[0]['sha256'],evidence.digest(p))

    def test_parent_placement_misuse_and_legitimate_internal_alignment(self):
        result=ui_layout_lint.check('Stack() { Row() { Text("right") }.align(Alignment.End) }')
        self.assertIn('INEFFECTIVE_STACK_CHILD_ALIGN',{f['code'] for f in result['findings']})
        self.assertEqual(ui_layout_lint.check('Row() { Text("a") }.align(Alignment.End)')['status'],'PASS')
        valid=ui_layout_lint.check('Stack() { Stack() { Text("a") }.width(100).height(80).align(Alignment.BottomEnd) }')
        self.assertEqual(valid['status'],'PASS')
        self.assertTrue(valid['findings'])

    def test_comments_and_constant_names_cannot_hide_measured_geometry(self):
        obligations={'nodes':[{'dimensions':{'height':{'resolution':'source_literal','unit':'dp','value':80}}}]}
        a='// 不可见测量条\nconst HEADER: number = 42;\nRow().height(HEADER)'
        b='// hardcoded temporary placeholder\nconst OTHER: number = 42;\nRow().height(OTHER)'
        for text in (a,b):
            self.assertIn('LAYOUT_LITERAL_WITHOUT_SOURCE',{f['code'] for f in ui_layout_lint.check(text,obligations)['findings']})
        self.assertEqual(ui_layout_lint.check('Row().height(80)',obligations)['status'],'PASS')
        resource=ui_layout_lint.check("Row().height($r('app.float.renamed'))",obligations,resource_values={'app.float.renamed':42})
        self.assertEqual(resource['status'],'FAIL')
        for expression in ('42','84/2'):
            text='struct Page { @Local h: number = '+expression+'; build() { Row().height(this.h) } }'
            self.assertEqual(ui_layout_lint.check(text,obligations)['status'],'FAIL')

    def test_layout_gravity_reads_compatibility_floor(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);path=root/'build-profile.json5'
            for api in (19,21):
                path.write_text('{ app: { products: [{ compatibleSdkVersion: "6.0.1('+str(api)+')" }] } }')
                result=ui_layout_lint.check('Image("x").layoutGravity(LocalizedAlignment.TOP_END)',compatible=ui_layout_lint.sdk_level(root))
                self.assertEqual(result['status'],'FAIL' if api==19 else 'PASS')

    def test_sdk_floor_uses_selected_product(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/'build-profile.json5').write_text('{app:{products:[{name:"legacy",compatibleSdkVersion:19},{name:"default",compatibleSdkVersion:"6.0.1(21)"}]}}')
            self.assertEqual(ui_layout_lint.sdk_level(root),21)
            self.assertEqual(ui_layout_lint.sdk_level(root,'legacy'),19)
            self.assertIsNone(ui_layout_lint.sdk_level(root,'missing'))

class OwnershipAndFlowTest(unittest.TestCase):
    def setUp(self):
        self.helper=base.DeliveryTest();self.helper.setUp();self.root=self.helper.root

    def tearDown(self):self.helper.tearDown()

    def inventory(self):
        inv=self.helper.inventory();inv['schema_version']=2
        inv['units'][0]['owned_ui_roles']=['shell','content']
        inv['units'][0]['required_states'][0]['responsibility']='content'
        inv['units'][0]['required_states'][1]['responsibility']='shell'
        inv['units'][1]['owned_ui_roles']=['content']
        inv['units'][1]['required_states'][0]['responsibility']='content'
        sdk=self.root/'sdk';sdk.mkdir(exist_ok=True)
        (sdk/'enums.d.ts').write_text('declare enum Alignment { Center=0, Start=1, End=2 }')
        (self.root/'build-profile.json5').write_text('{app:{products:[{name:"default",compatibleSdkVersion:"6.0.1(21)"}]}}')
        inv['toolchain']={'sdk_definitions':str(sdk)}
        return inv

    def test_full_delivery_cannot_opt_out_of_visual_verification(self):
        self.helper.promote();inv=self.inventory()
        inv['visual_policy']='skip'
        with self.assertRaisesRegex(ValueError,'requires S1-V'):
            ui_delivery.approve(self.root,inv,'test:not-authorized-to-skip')

    def test_shell_cannot_account_for_unassigned_body(self):
        self.helper.promote();inv=self.inventory()
        self.assertEqual(ui_state_ownership.review(self.root,inv)['status'],'PASS')
        inv['units'][0]['required_states'][0]['responsibility']='shell'
        result=ui_state_ownership.review(self.root,inv)
        self.assertEqual(result['errors'][0]['code'],'UNASSIGNED_STATE')

    def test_same_layer_body_cannot_be_owned_twice(self):
        self.helper.promote();inv=self.inventory()
        child=inv['units'][1]
        child['required_states'].append({'state_id':'weather','evidence_page_id':self.helper.pages[0],'evidence_state_id':'weather','arrival_mode':'preview','responsibility':'content','region_px':[10,10,300,500]})
        self.assertIn('DUPLICATE_CONTENT_OWNERSHIP',{x['code'] for x in ui_state_ownership.review(self.root,inv)['errors']})

    def test_small_region_gets_context_but_large_body_does_not_duplicate_it(self):
        self.helper.promote();inv=self.inventory()
        inv['units'][1]['required_states'][0]['region_px']=[20,20,200,100]
        path=self.helper.spec/'baseline/plans/stage1-ui-delivery.json'
        evidence.save(path,ui_delivery.approve(self.root,inv,'test:explicit-pilot-review'))
        ui_delivery_inputs.freeze(self.root,path)
        from validate_runtime_snapshots import load_packets
        packets=load_packets(self.root)
        child=next(p for _,p in packets if p['unit_id']=='main.forecast')
        self.assertEqual(len(child['states'][0]['context_frames']),1)
        self.assertEqual(child['states'][0]['context_frames'][0]['png'],child['states'][0]['frames'][0]['png'])
        self.assertTrue(child['states'][0]['frames'][0]['parsed'])
        main=next(p for _,p in packets if p['unit_id']=='main.shell')
        self.assertFalse(main['states'][0]['context_frames'])

    def test_complete_writeback_rejected_before_brief_mutation(self):
        original=self.helper.inventory
        inv=self.inventory();self.helper.inventory=lambda:copy.deepcopy(inv)
        self.helper.code_and_reports();stage1_acceptance.archive_generation(self.root,'g0')
        self.assertEqual(stage1_acceptance.next_step(self.root)['next_action'],'assemble_and_archive_g1')
        stage1_acceptance.archive_generation(self.root,'g1')
        scope=self.helper.spec/'scope.json';evidence.save(scope,stage1_visual_scope.build_scope(self.root))
        manifest={'mode':'batch','stage1':{'phase':'complete','scope':'scope.json'},'brief':{'path':'spec/no-false-pass.md','content':'PASS'}}
        path=self.root/'writeback.json';evidence.save(path,manifest)
        self.assertEqual(apply_writeback.main([str(path),'--project-root',str(self.root)]),1)
        self.assertFalse((self.root/'spec/no-false-pass.md').exists())
        result=stage1_acceptance.summary(self.root,scope)
        self.assertEqual(result['visual'],'NOT_RUN')
        self.assertFalse(result['assessment_complete'])
        self.assertEqual(stage1_acceptance.next_step(self.root,scope)['next_action'],'build_with_hmos_builder')

    def test_composition_verification_does_not_claim_child_implementation(self):
        self.helper.promote();inv=self.inventory()
        inv['verification_states']=[{'verification_id':'home','owner_unit_id':'main.shell',
            'implementation_units':['main.shell','main.forecast'], 'arrival_mode':'preview',
            'evidence_page_id':self.helper.pages[0],'evidence_state_id':'weather'}]
        path=self.helper.spec/'baseline/plans/stage1-ui-delivery.json'
        evidence.save(path,ui_delivery.approve(self.root,inv,'test:composition-review'))
        ui_delivery_inputs.freeze(self.root,path)
        scope=stage1_visual_scope.build_scope(self.root)
        pair=next(p for p in scope['pairs'] if p['pair_id']=='composition.home')
        self.assertEqual(pair['owner_unit_id'],'main.shell')
        self.assertEqual(pair['responsibility'],'composition')
        self.assertEqual(pair['android_frames'][0]['region_px'],[0,0,320,640])
        self.assertEqual(scope['pairs'][0]['responsibility'],'content')

    def test_parser_upgrade_creates_revision_without_overwriting_old_windows(self):
        inv=self.inventory();self.helper.inventory=lambda:copy.deepcopy(inv)
        packets=self.helper.frozen()
        first_path,first=packets[0]
        before={item['path']:evidence.check_file(self.helper.spec,item).read_bytes() for item in first['windows']}
        original=ui_delivery_inputs.digest
        def upgraded(path):
            return 'f'*64 if Path(path).resolve()==Path(ui_delivery_inputs.__file__).resolve() else original(path)
        with patch.object(ui_delivery_inputs,'digest',side_effect=upgraded):
            ui_delivery_inputs.freeze(self.root,self.helper.spec/'baseline/plans/stage1-ui-delivery.json')
        from validate_runtime_snapshots import load_packets
        revised=next(p for _,p in load_packets(self.root) if p['unit_id']==first['unit_id'])
        self.assertNotEqual(revised['producer_sha256'],first['producer_sha256'])
        self.assertNotEqual(revised['windows'],first['windows'])
        for rel,content in before.items():self.assertEqual((self.helper.spec/rel).read_bytes(),content)

    def test_g0_keeps_consumed_inputs_and_detects_blob_tampering(self):
        inv=self.inventory();self.helper.inventory=lambda:copy.deepcopy(inv)
        packets=self.helper.code_and_reports()
        archive=next(e for e in ui_dispatch.events(self.root) if e['kind']=='g0')
        files=evidence.read(evidence.check_file(self.helper.spec,archive['input_files_manifest']))
        png=next(f for f in files if f['original']['path'].endswith('.png'))
        original=evidence.check_file(self.helper.spec,png['original'])
        content=original.read_bytes()
        original.write_bytes(b'new ROI cache')
        self.assertEqual(evidence.check_file(self.helper.spec,png['archived']).read_bytes(),content)
        original.write_bytes(content)
        stage1_acceptance.archive_generation(self.root,'g0')
        blob=evidence.check_file(self.helper.spec,png['archived'])
        blob.write_bytes(b'tampered')
        packet_path,packet=next((p,v) for p,v in packets if v['unit_id']==archive['unit_id'])
        report=evidence.read(self.helper.spec/'execution/conversion-reports'/f"{packet['unit_id']}.json")
        with self.assertRaisesRegex(ValueError,'hash changed'):
            ui_dispatch.validate_handoff(self.root,packet_path,report)

    def test_new_contract_requires_g1_build_matching_setup_and_visual_before_complete(self):
        # Contract fixtures only: actual SDK rendering has a separate pilot.
        for path in self.helper.run.glob('*/*.xml'):
            path.write_text(path.read_text().replace('</node></hierarchy>',
                '<node class="TextView" text="caption" bounds="[20,120][180,150]"/></node></hierarchy>'))
        inv=self.inventory();inv['units'][0]['required_states']=inv['units'][0]['required_states'][:1]
        inv['units'][0]['owned_ui_roles']=['content']
        self.helper.inventory=lambda:copy.deepcopy(inv)
        self.helper.code_and_reports();stage1_acceptance.archive_generation(self.root,'g0')
        scope_path=self.helper.spec/'scope.json';scope=stage1_visual_scope.build_scope(self.root)
        evidence.save(scope_path,scope)
        hap=self.helper.spec/'execution/fixture.hap';hap.write_bytes(b'unit-test artifact')
        receipt=self.helper.spec/'execution/build.json'
        evidence.save(receipt,{'kind':'build','unit_id':'stage1-test','status':'PASS','source_sha256':stage1_acceptance.source_digest(self.root),
            'scope_sha256':evidence.digest(scope_path),'hap_sha256':evidence.digest(hap),'hap_path':hap.relative_to(self.root).as_posix()})
        compile_path=self.helper.spec/'compile.json'
        evidence.save(compile_path,{'status':'PASS','scope_sha256':evidence.digest(scope_path),'build_receipt':evidence.bound_file(self.helper.spec,receipt)})
        with self.assertRaises(FileNotFoundError):stage1_acceptance.record(self.root,scope_path,compile_path,'compile')
        stage1_acceptance.archive_generation(self.root,'g1')
        rows=[]
        for pair in scope['pairs']:
            build=self.helper.spec/'execution'/(pair['pair_id']+'.build.json')
            install=self.helper.spec/'execution'/(pair['pair_id']+'.install.json')
            details={**evidence.read(receipt),'unit_id':pair['unit_id']}
            evidence.save(build,details)
            evidence.save(install,{**details,'kind':'install','device_id':'test-emulator'})
            arrival=self.helper.spec/'execution'/(pair['pair_id']+'.arrival.json')
            evidence.save(arrival,{'pair_id':pair['pair_id'],'status':'PASS','arrival_mode':pair['arrival_mode'],
                'state_setup':pair['state_setup'],'presentation':pair['presentation'],
                'build_receipt':evidence.bound_file(self.helper.spec,build),'install_receipt':evidence.bound_file(self.helper.spec,install),
                'device_id':'test-emulator','capture_run_id':'test-run','observed_page_id':pair['page_id'],
                'observed_state_id':pair['state_id'],'landing_evidence':'fixture text and state'})
            comparisons=[]
            for frame in pair['android_frames']:
                capture=self.helper.spec/'execution/stage1-visual/test-run'/pair['pair_id']
                capture.mkdir(parents=True,exist_ok=True)
                png=capture/(frame['comparison_id']+'.png');xml=capture/(frame['comparison_id']+'.xml')
                png.write_bytes(evidence.check_file(self.helper.spec,frame['working_png']).read_bytes())
                xml.write_bytes(evidence.check_file(self.helper.spec,frame['xml']).read_bytes())
                appearance=self.helper.spec/'execution'/(frame['comparison_id']+'.appearance.json')
                evidence.save(appearance,{'comparison_id':frame['comparison_id'],'verdict':'PASS'})
                comparisons.append({'comparison_id':frame['comparison_id'],'verdict':'PASS',
                    'android_png_sha256':frame['png']['sha256'],'android_region_px':frame['region_px'],
                    'harmony_png':evidence.bound_file(self.helper.spec,png),'harmony_xml':evidence.bound_file(self.helper.spec,xml),
                    'harmony_region_px':frame['region_px'],'harmony_density':frame['density_factor'],
                    'appearance_verdict':'PASS','appearance_report':evidence.bound_file(self.helper.spec,appearance)})
            rows.append({'pair_id':pair['pair_id'],'verdict':'PASS','arrival_mode':pair['arrival_mode'],
                'arrival_receipt':evidence.bound_file(self.helper.spec,arrival),'comparisons':comparisons})
        visual=self.helper.spec/'visual.json';evidence.save(visual,{'scope_sha256':evidence.digest(scope_path),'pairs':rows})
        with self.assertRaisesRegex(ValueError,'recorded PASS build'):stage1_acceptance.record(self.root,scope_path,visual)
        stage1_acceptance.record(self.root,scope_path,compile_path,'compile')
        first=evidence.check_file(self.helper.spec,rows[0]['arrival_receipt']);original=evidence.read(first)
        evidence.save(first,{**original,'presentation':{'density':'uncontrolled'}})
        rows[0]['arrival_receipt']=evidence.bound_file(self.helper.spec,first)
        evidence.save(visual,{'scope_sha256':evidence.digest(scope_path),'pairs':rows})
        with self.assertRaisesRegex(ValueError,'fixed device'):stage1_acceptance.record(self.root,scope_path,visual)
        for changed,message in [({'device_id':'wrong-device'},'installed device'),
                                ({'observed_state_id':'another-state'},'actual page/state arrival'),
                                ({'capture_run_id':'old-run'},'outside this run'),
                                ({'install_receipt':original['build_receipt']},'invalid install receipt')]:
            evidence.save(first,{**original,**changed})
            rows[0]['arrival_receipt']=evidence.bound_file(self.helper.spec,first)
            evidence.save(visual,{'scope_sha256':evidence.digest(scope_path),'pairs':rows})
            with self.assertRaisesRegex(ValueError,message):stage1_acceptance.record(self.root,scope_path,visual)
        evidence.save(first,original);rows[0]['arrival_receipt']=evidence.bound_file(self.helper.spec,first)
        evidence.save(visual,{'scope_sha256':evidence.digest(scope_path),'pairs':rows})
        stage1_acceptance.record(self.root,scope_path,visual)
        result=stage1_acceptance.validate_writeback(self.root,{'mode':'batch','stage1':{'phase':'complete','scope':'scope.json'}})
        self.assertTrue(result['stage1_complete'])
        self.assertFalse(result['business_integration_verified'])

class RelationshipsTest(unittest.TestCase):
    def test_unrelated_target_system_labels_do_not_block_unique_matches(self):
        with tempfile.TemporaryDirectory() as temp:
            a=Path(temp)/'a.xml';b=Path(temp)/'b.xml'
            body='<node text="City" class="TextView" bounds="[0,0][30,30]"/><node text="Value" class="TextView" bounds="[0,40][30,70]"/>'
            a.write_text('<hierarchy>'+body+'</hierarchy>')
            b.write_text('<hierarchy>'+body+'<node text="system" class="TextView" bounds="[100,0][150,30]"/><node text="system" class="TextView" bounds="[100,40][150,70]"/></hierarchy>')
            result=ui_relationships.compare(a,b,1,1,[0,0,320,640],[0,0,320,640])
            self.assertEqual(result['status'],'PASS')

    def test_duplicate_labels_match_by_semantic_parent_context(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'view.xml'
            p.write_text('<hierarchy><group><node text="Today" class="TextView" bounds="[0,0][80,20]"/><node text="16" class="TextView" bounds="[0,25][30,50]"/></group><group><node text="Tomorrow" class="TextView" bounds="[0,80][80,100]"/><node text="16" class="TextView" bounds="[0,105][30,130]"/></group></hierarchy>')
            result=ui_relationships.compare(p,p,1,1,[0,0,320,640],[0,0,320,640])
            self.assertEqual(result['status'],'PASS')
            self.assertEqual(len(result['matched']),4)
    def test_overlap_and_anchor_side_are_detected_across_different_viewports(self):
        with tempfile.TemporaryDirectory() as temp:
            a=Path(temp)/'a.xml';b=Path(temp)/'b.json'
            a.write_text('<hierarchy><node class="TextView" text="City" bounds="[10,10][80,30]"/><node class="TextView" text="Value" bounds="[300,10][400,30]"/></hierarchy>')
            def dump(rect):return {'children':[{'attributes':{'type':'Text','text':'City','bounds':'[10,10][80,30]'}},{'attributes':{'type':'Text','text':'Value','bounds':rect}}]}
            evidence.save(b,dump('[267,10][367,30]'))
            result=ui_relationships.compare(a,b,1,1,[0,0,411,800],[0,0,377,800])
            self.assertEqual(result['status'],'PASS')
            evidence.save(b,dump('[20,10][120,30]'))
            result=ui_relationships.compare(a,b,1,1,[0,0,411,800],[0,0,377,800])
            self.assertIn('NEW_OVERLAP',{v['code'] for v in result['violations']})

    def test_ambiguous_matching_is_not_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            a=Path(temp)/'a.xml';a.write_text('<hierarchy><node text="x" class="TextView" bounds="[0,0][30,30]"/><node text="x" class="TextView" bounds="[0,40][30,70]"/></hierarchy>')
            self.assertEqual(ui_relationships.compare(a,a,1,1,[0,0,320,640],[0,0,320,640])['status'],'UNRESOLVED')

class IsolationTest(unittest.TestCase):
    def test_parent_cd_then_relative_android_read_stays_inside_allowlist(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);android=root/'android';android.mkdir();project=root/'project';project.mkdir()
            db=root/'test.db';con=sqlite3.connect(db)
            con.executescript('CREATE TABLE session(id,parent_id,directory); CREATE TABLE message(id,data); CREATE TABLE part(id,session_id,message_id,time_created,data);')
            con.execute('INSERT INTO session VALUES (?,?,?)',('main',None,str(project)))
            con.execute('INSERT INTO message VALUES (?,?)',('msg','{}'))
            data={'type':'tool','tool':'bash','state':{'status':'completed','input':{'command':f'cd {root}; cat android/allowed.xml'}}}
            con.execute('INSERT INTO part VALUES (?,?,?,?,?)',('p','main','msg',1,json.dumps(data)));con.commit();con.close()
            result=ui_isolation_audit.audit(db,['main'],[str(project),str(android)])
            self.assertEqual(result['status'],'PASS')
            self.assertEqual(result['observed'][0]['path'],str((android/'allowed.xml').resolve()))

    def test_nested_session_shell_read_of_sibling_invalidates_run(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);db=root/'test.db';con=sqlite3.connect(db)
            con.executescript('CREATE TABLE session(id,parent_id,directory); CREATE TABLE message(id,data); CREATE TABLE part(id,session_id,message_id,time_created,data);')
            project=root/'project';project.mkdir()
            con.execute('INSERT INTO session VALUES (?,?,?)',('main',None,str(project)))
            con.execute('INSERT INTO session VALUES (?,?,?)',('child','main',str(project)))
            con.execute('INSERT INTO message VALUES (?,?)',('msg','{}'))
            data={'type':'tool','tool':'bash','state':{'status':'completed','input':{'command':'cat /Users/test/MyWeather_version_1017/entry/Old.ets'}}}
            con.execute('INSERT INTO part VALUES (?,?,?,?,?)',('part','child','msg',1,json.dumps(data)));con.commit();con.close()
            result=ui_isolation_audit.audit(db,['main'],[str(project)])
            self.assertEqual(result['status'],'INVALID')
            self.assertFalse(result['confinement_proven'])
            self.assertEqual(result['violations'][0]['session_id'],'child')

if __name__=='__main__':unittest.main()
