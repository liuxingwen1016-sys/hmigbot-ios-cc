"""Integration regressions: 1030 contracts and full UI evidence must both work."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest

import test_ui_delivery as base
import test_ui_fidelity_controls as fidelity
from test_ui_delivery import evidence, ui_delivery, ui_delivery_inputs, ui_dispatch, stage1_acceptance, ui_stage1_gate
import validate_runtime_snapshots
import stage1_visual_scope
import stage1_contract
import gate_ledger
import ui_layout_lint
import apply_writeback
import promote_android_fast_traverse as promotion


class ContractIntegration(unittest.TestCase):
    def setUp(self):
        self.control=fidelity.OwnershipAndFlowTest()
        self.control.setUp()
        self.addCleanup(self.control.tearDown)
        self.h=self.control.helper
        self.root=self.h.root

    def full_outputs(self):
        inv=self.control.inventory()
        self.h.inventory=lambda:copy.deepcopy(inv)
        return self.h.code_and_reports()

    def test_missing_frozen_index_does_not_fall_back_to_passing_smoke(self):
        self.full_outputs()
        evidence.save(self.h.spec/'execution/wiring/smoke.json',{'schema_version':1,'unit_id':'smoke',
            'status':'smoke_wired','pages':[{'page_id':self.h.pages[0],'state_id':'weather',
            'output_file':'entry/src/main/ets/pages/MainPage.ets'}]})
        self.assertEqual(ui_stage1_gate.check_wiring(self.root.resolve())['status'],'PASS')
        (self.h.spec/'execution/ui-inputs/index.json').unlink()
        self.assertEqual(ui_stage1_gate.check(self.root)['status'],'BLOCKED')
        intent=self.root/'false-complete.json'
        evidence.save(intent,{'mode':'batch','stage1':{'phase':'complete','scope':'scope.json'},
            'brief':{'path':'spec/false-pass.md','content':'PASS'}})
        self.assertEqual(apply_writeback.main([str(intent),'--project-root',str(self.root)]),1)
        self.assertFalse((self.h.spec/'false-pass.md').exists())
        with self.assertRaises(OSError):stage1_visual_scope.build_scope(self.root)

    def test_packet_cannot_downgrade_reviewed_schema(self):
        packets=self.full_outputs()
        path,packet=packets[0]
        packet['delivery_schema']=1
        evidence.save(path,packet)
        index_path=self.h.spec/'execution/ui-inputs/index.json'
        index=evidence.read(index_path)
        relative=path.relative_to(self.h.spec.resolve()).as_posix()
        index['packets']=[evidence.bound_file(self.h.spec,path) if r['path']==relative else r for r in index['packets']]
        evidence.save(index_path,index)
        with self.assertRaisesRegex(ValueError,'downgrade'):
            validate_runtime_snapshots.load_packets(self.root)

    def test_failed_preflight_is_still_kept_in_first_pass_archive(self):
        packets=self.full_outputs()
        # The first attempt was valid. A separately dispatched failed retry must
        # remain inspectable while the aggregate G0 keeps the first attempt.
        path,packet=packets[0];unit=packet['unit']
        dispatch=ui_dispatch.dispatch(self.root,unit['unit_id'],attempt=2)
        output=self.root/unit['output']['file']
        output.write_text(output.read_text()+'\nconst invalid = Alignment.CenterEnd;\n')
        report_path=self.h.spec/'execution/conversion-reports'/(unit['unit_id']+'.json')
        report=evidence.read(report_path);report.update(dispatch_id=dispatch['dispatch_id'],packet_sha256=evidence.digest(path))
        evidence.save(report_path,report)
        archived=ui_dispatch.complete(self.root,dispatch['dispatch_id'])
        self.assertEqual(archived['preflight_status'],'FAIL')
        stage1_acceptance.archive_generation(self.root,'g0')
        manifest=stage1_acceptance.require_g0(self.root)
        self.assertTrue(any(r['dispatch_id']==unit['unit_id']+'.attempt-1' for r in manifest['files']))
        self.assertEqual(ui_stage1_gate.check(self.root)['status'],'FAIL')

    def test_preflight_findings_are_visible_to_1030_release_rule_scan(self):
        result=ui_layout_lint.check('Text("x").align(Alignment.Missing)',enums={'Alignment':{'Center'}})
        path=self.h.spec/'execution/preflight.json';evidence.save(path,result)
        rules,found,read=gate_ledger.fail_rules_in_outputs('`spec/execution/preflight.json`',self.root)
        self.assertTrue(found)
        self.assertIn(str(path),read)
        self.assertIn('SDK_MEMBER_UNKNOWN',rules)
        self.assertEqual(gate_ledger.resolve(gate_ledger.load_registry(),'execute.ui-layout / SDK_MEMBER_UNKNOWN')['class'],'exact')

    def test_shared_source_identity_covers_appscope_modules_and_hvigor(self):
        for relative in ['AppScope/app.json5','feature/src/main/ets/Extra.ets','hvigorfile.ts']:
            path=self.root/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('before')
            previous=stage1_acceptance.source_digest(self.root)
            self.assertEqual(previous,stage1_contract.source_digest(self.root))
            path.write_text('after')
            self.assertNotEqual(previous,stage1_acceptance.source_digest(self.root))

    def test_refs_can_be_checked_before_packets_without_copying_runtime_view(self):
        self.h.promote()
        view=self.h.spec/'baseline/ui-snapshots'/self.h.pages[0]/'view.xml'
        original=view.read_bytes()
        checked=validate_runtime_snapshots.check(self.root,[{'page_id':self.h.pages[0],'state_id':'weather'}])
        self.assertEqual(checked['status'],'pass')
        paired=stage1_visual_scope.baseline(self.root.resolve(),{'page_id':self.h.pages[0],'state_id':'weather'})
        self.assertTrue((self.root/paired['android_png']).is_file())
        self.assertEqual(view.read_bytes(),original)


class RealCollectorRefs(unittest.TestCase):
    def test_collector_report_metadata_flows_into_schema3_refs(self):
        from test_runtime_promotion_handoff import write_traversal, OUT_NAME
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp).resolve();run=root/'spec/.a2h/android-fast-traverse/run'
            out=run/OUT_NAME
            state=write_traversal(out)
            first=state['index'][0]
            _,activity=evidence.activity_identity(first['activity_info']['resumed_activity'])
            page='page_0001_Main';snap=root/'spec/baseline/ui-snapshots'/page
            evidence.save(snap/'meta.json',{'activity':activity,'view_xml_origin':'static_synthetic'})
            (snap/'view.xml').write_text('<hierarchy synthesized="true"/>')
            mapping={'schema_version':3,'pages':[{'page_id':page,'states':[{'state_id':'weather',
                'source_page_ids':[first['page_id']],'review':'source-backed collector contract fixture'}]}]}
            result=promotion.promote(root,run,mapping)
            self.assertEqual(result['status'],'referenced')
            frame=evidence.validate_refs(root/'spec',page)[0]['frames'][0]
            self.assertEqual(frame['captured_at'],first['timestamp'])
            self.assertEqual(frame['package'],state['package'])
            context=evidence.read(snap/'runtime-refs.json')['runs'][0]
            self.assertEqual(context['run_id'],'run')
            self.assertEqual((root/'spec'/context['output_root']).resolve(),out)
            self.assertEqual(promotion.promote(root,out,mapping),result)
            self.assertFalse((snap/'android-runtime.png').exists())
            self.assertEqual(validate_runtime_snapshots.check(root,[{'page_id':page,'state_id':'weather'}])['status'],'pass')

    def test_index_revision_paths_are_followed_instead_of_original_frame_names(self):
        from test_runtime_promotion_handoff import write_traversal, OUT_NAME
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp).resolve();run=root/'spec/.a2h/android-fast-traverse/revised-run';out=run/OUT_NAME
            state=write_traversal(out);first=state['index'][0]
            _,activity=evidence.activity_identity(first['activity_info']['resumed_activity'])
            page='page_0001_Main';snap=root/'spec/baseline/ui-snapshots'/page
            evidence.save(snap/'meta.json',{'activity':activity});(snap/'view.xml').write_text('<hierarchy synthesized="true"/>')
            revision=out/'_aft/revisions'/first['page_id']/'rev_0001';revision.mkdir(parents=True)
            for field,plural,filename in [('screenshot','screenshots','screenshot.png'),('view_xml','view_xmls','view.xml')]:
                (revision/filename).write_bytes((out/first[field]).read_bytes())
                first[field]=(revision/filename).relative_to(out).as_posix();first[plural]=[first[field]]
            evidence.save(out/'index.json',state['index']);evidence.save(out/first['page_id']/'meta.json',first)
            mapped={'schema_version':3,'pages':[{'page_id':page,'states':[{'state_id':'weather','source_page_ids':[first['page_id']],'review':'reviewed revised frame'}]}]}
            promotion.promote(root,run,mapped)
            frame=evidence.validate_refs(root/'spec',page)[0]['frames'][0]
            self.assertEqual(evidence.check_file(root/'spec',frame['png']),revision/'screenshot.png')
            self.assertEqual(evidence.check_file(root/'spec',frame['xml']),revision/'view.xml')

    def test_flat_legacy_output_cannot_enter_new_refs(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);flat=root/'spec/.a2h/android-fast-traverse/flat';flat.mkdir(parents=True)
            evidence.save(flat/'index.json',[])
            with self.assertRaisesRegex(ValueError,'android_traverse_screenshots'):
                evidence.load_run(root/'spec',flat)


if __name__=='__main__':unittest.main()
