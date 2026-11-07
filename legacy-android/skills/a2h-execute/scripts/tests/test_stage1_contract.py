import copy
import importlib.util
import json
import sys
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
from stage1_contract import digest, normalize, source_digest
from stage1_preview import check as preview
from stage1_reachability import check as reach
from stage1_visual_scope import build_scope
from stage1_capture_scope import prepare, finalize
from ui_stage1_gate import check as gate


class Stage1Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.entry = 'entry/src/main/ets/pages/Start.ets'
        self.page = 'entry/src/main/ets/pages/Detail.ets'
        self.vm = 'entry/src/main/ets/viewmodels/DetailVM.ets'
        self.write(self.entry, "import { Detail } from './Detail';\nimport { PreviewHost } from './PreviewHost';\nexport struct Start {}")
        self.write('entry/src/main/ets/pages/PreviewHost.ets', 'export struct PreviewHost {}')
        self.write(self.page, "import { DetailVM } from '../viewmodels/DetailVM';\nexport struct Detail {}")
        self.write(self.vm, 'export class DetailVM {}')
        self.wiring = self.root / 'spec/execution/wiring'
        self.wiring.mkdir(parents=True)
        self.data = {'schema_version': 1, 'unit_id': 'detail', 'status': 'preview_prepared',
                     'delivery_mode': 'preview_host', 'entry_file': self.entry,
                     'preview_host_file': 'entry/src/main/ets/pages/PreviewHost.ets',
                     'pages': [{'page_id': 'page_0001_Detail', 'state_id': 'normal', 'output_file': self.page}],
                     'target_files': [self.entry, self.page, self.vm]}
        self.put_manifest()
        self.baseline()

    def write(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value if isinstance(value, bytes) else value.encode())
        return path

    def put_manifest(self):
        return self.write('spec/execution/wiring/detail.json', json.dumps(self.data))

    def baseline(self, state='normal'):
        base = 'spec/baseline/ui-snapshots/page_0001_Detail/'
        png = self.write(base + 'runtime.png', b'\x89PNG\r\n\x1a\nframe')
        xml = self.write(base + 'view.xml', '<hierarchy/>')
        self.write(base + 'meta.json', json.dumps({'runtime_evidence': {
            'status': 'audited', 'state': state, 'png_path': 'runtime.png', 'view_xml_path': 'view.xml',
            'png_sha256': digest(png), 'view_xml_sha256': digest(xml)}}))

    def receipts(self):
        hap = self.write('entry/build/current.hap', b'current package')
        build = {'kind': 'build', 'status': 'PASS', 'unit_id': 'detail',
                 'source_sha256': source_digest(self.root), 'hap_path': 'entry/build/current.hap', 'hap_sha256': digest(hap)}
        install = {**build, 'kind': 'install', 'device_id': 'device-1'}
        return (self.write('spec/execution/build.json', json.dumps(build)),
                self.write('spec/execution/install.json', json.dumps(install)))

    def scope_report(self):
        path = self.write('spec/execution/scope.json', json.dumps(build_scope(self.wiring, self.root)))
        return path, prepare(self.root, path)

    def captured(self):
        path, report = self.scope_report()
        build, install = self.receipts()
        png = self.write(report['capture_dir'] + '/current.png', b'current frame')
        xml = self.write(report['capture_dir'] + '/current.json', '{"visible":"Detail"}')
        report['cases'][0].update(status='PASS', build_receipt=build.relative_to(self.root).as_posix(),
                                 install_receipt=install.relative_to(self.root).as_posix(), device_id='device-1',
                                 capture_run_id=report['run_id'], observed_page_id='page_0001_Detail',
                                 observed_state_id='normal', landing_evidence='visible Detail title in current dump',
                                 harmony_png=png.relative_to(self.root).as_posix(), harmony_xml=xml.relative_to(self.root).as_posix())
        return path, report

    def test_page_binding_cannot_reuse_another_page_to_cover_missing_file(self):
        self.data['pages'].append({'page_id': 'page_0002_Missing', 'state_id': 'normal',
                                   'output_file': 'entry/src/main/ets/pages/Missing.ets'})
        self.put_manifest()
        self.assertEqual(gate(self.root, self.wiring)['status'], 'FAIL')

    def test_missing_selected_vm_is_failure(self):
        (self.root / self.vm).unlink()
        result = reach(self.root, self.data)
        self.assertEqual(result['gate'], 'FAIL')
        self.assertIn(self.vm, result['missing'])

    def test_custom_entry_and_relative_imports(self):
        self.assertFalse((self.root / 'entry/src/main/ets/pages/Index.ets').exists())
        result = reach(self.root, self.data)
        self.assertEqual(result['gate'], 'PASS')
        self.assertIn(self.vm, result['reachable'])
        self.assertIn('not_runtime', result['analysis'])

    def test_unreachable_existing_target_fails(self):
        self.write(self.entry, 'export struct Start {}')
        self.assertEqual(reach(self.root, self.data)['gate'], 'FAIL')

    def test_missing_or_ambiguous_entry_does_not_default_to_index(self):
        data = copy.deepcopy(self.data)
        del data['entry_file']
        self.assertEqual(reach(self.root, data)['gate'], 'FAIL')
        self.write('entry/src/main/ets/entryability/EntryAbility.ets', "stage.loadContent('pages/Start');")
        self.assertEqual(reach(self.root, data)['gate'], 'PASS')

    def test_legacy_singular_requires_explicit_binding(self):
        data = {**self.data, **self.data['pages'][0]}
        del data['pages']
        self.assertEqual(normalize(data)['pages'][0]['output_file'], self.page)
        del data['output_file']
        with self.assertRaises(ValueError):
            normalize(data)

    def test_legacy_arrays_are_zipped_only_with_output_map(self):
        data = {**self.data, 'page_ids': ['p1', 'p2'], 'state_ids': ['normal'], 'page_outputs': {}}
        del data['pages']
        with self.assertRaises(ValueError):
            normalize(data)
        data.update(page_ids=['p1'], page_outputs={'p1': self.page})
        self.assertEqual(normalize(data)['pages'][0]['state_id'], 'normal')

    def test_path_escape_and_duplicate_bindings_fail(self):
        self.data['pages'][0]['output_file'] = '../outside.ets'
        self.put_manifest()
        self.assertEqual(gate(self.root, self.wiring)['status'], 'FAIL')
        self.data['pages'][0]['output_file'] = self.page
        self.data['pages'].append(copy.deepcopy(self.data['pages'][0]))
        with self.assertRaises(ValueError):
            normalize(self.data)

    def test_prepared_without_optional_sidecars_can_enter_scope(self):
        self.assertEqual(preview(self.root, self.data)['status'], 'preview_prepared')
        value = build_scope(self.wiring, self.root)
        self.assertEqual(value['units'][0]['pages'][0]['state_id'], 'normal')

    def test_build_receipt_cannot_be_install_receipt(self):
        build, _ = self.receipts()
        self.assertEqual(preview(self.root, self.data, build, build)['status'], 'blocked')
        self.assertEqual(preview(self.root, self.data, None, build)['status'], 'blocked')

    def test_installed_does_not_mean_page_visible(self):
        build, install = self.receipts()
        result = preview(self.root, self.data, build, install)
        self.assertEqual(result['status'], 'preview_installed')
        self.assertFalse(result['runtime_visibility_verified'])

    def test_stale_source_or_wrong_hap_receipt_fails(self):
        build, install = self.receipts()
        self.write(self.vm, 'export class ChangedVM {}')
        self.assertEqual(preview(self.root, self.data, build, install)['status'], 'blocked')
        build, install = self.receipts()
        self.write('entry/build/current.hap', b'another package')
        self.assertEqual(preview(self.root, self.data, build, install)['status'], 'blocked')

    def test_baseline_wrong_state_or_changed_bytes_fail(self):
        self.baseline(state='another-state')
        with self.assertRaises(ValueError):
            build_scope(self.wiring, self.root)
        self.baseline()
        self.write('spec/baseline/ui-snapshots/page_0001_Detail/runtime.png', b'changed')
        with self.assertRaises(ValueError):
            build_scope(self.wiring, self.root)

    def test_missing_baseline_cli_reports_information_gap(self):
        self.baseline(state='unobserved')
        output = self.root / 'spec/execution/scope-missing.json'
        result = subprocess.run([sys.executable, str(SCRIPTS / 'stage1_visual_scope.py'),
                                 '--project-root', str(self.root), '--wiring-dir', str(self.wiring),
                                 '--out', str(output)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        report = json.loads(output.read_text())
        self.assertEqual(report['status'], 'BLOCKED')
        self.assertEqual(report['failure_findings'][0]['root_cause'], 'information_gap')

    def test_missing_case_does_not_finalize_pass(self):
        path, report = self.scope_report()
        report['cases'] = []
        self.assertEqual(finalize(self.root, path, report)['status'], 'visual_blocked')

    def test_matched_capture_and_receipts_can_finalize(self):
        path, report = self.captured()
        result = finalize(self.root, path, report)
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['cases'][0]['visibility'], 'preview_ready')
        self.assertIn('harmony_png_sha256', result['cases'][0])

    def test_wrong_run_device_or_landing_blocks(self):
        for field, wrong in [('capture_run_id', 'old'), ('device_id', 'device-other'), ('observed_state_id', 'wrong')]:
            path, report = self.captured()
            report['cases'][0][field] = wrong
            self.assertEqual(finalize(self.root, path, report)['status'], 'visual_blocked', field)

    def test_diff_is_not_pass_or_automatic_repair(self):
        path, report = self.captured()
        report['cases'][0].update(status='DIFF', reason='spacing differs')
        self.assertEqual(finalize(self.root, path, report)['status'], 'DIFF')
        self.assertEqual(report['fix'], 'none')

    def test_empty_scope_fails_ui_gate(self):
        self.put_manifest().unlink()
        self.assertEqual(gate(self.root, self.wiring)['status'], 'FAIL')

    def test_old_capture_path_cannot_pass_as_current_run(self):
        path, report = self.captured()
        old = self.write('spec/execution/stage1-visual/old/frame.png', b'old frame')
        report['cases'][0]['harmony_png'] = old.relative_to(self.root).as_posix()
        self.assertEqual(finalize(self.root, path, report)['status'], 'visual_blocked')

    def test_source_change_invalidates_existing_capture(self):
        path, report = self.captured()
        self.write(self.page, 'export struct ChangedPage {}')
        with self.assertRaises(ValueError):
            finalize(self.root, path, report)

    def test_preview_requires_product_host_not_skill_template(self):
        del self.data['preview_host_file']
        self.assertEqual(preview(self.root, self.data)['status'], 'blocked')

    def test_cli_stale_report_is_blocked_and_keeps_capture_evidence(self):
        path, report = self.captured()
        report_file = self.write('spec/execution/stage1-visual/manifest.json', json.dumps(report))
        self.write(self.page, 'export struct ChangedPage {}')
        result = subprocess.run([sys.executable, str(SCRIPTS / 'stage1_capture_scope.py'),
                                 'finalize', '--project-root', str(self.root),
                                 '--scope-manifest', str(path), '--report', str(report_file)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        blocked = json.loads(report_file.read_text())
        self.assertEqual(blocked['status'], 'visual_blocked')
        self.assertEqual(len(blocked['cases']), 1)
        self.assertIn('harmony_png', blocked['cases'][0])
