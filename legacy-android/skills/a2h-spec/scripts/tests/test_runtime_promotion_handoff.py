"""Exercise android_fast_traverse output through promotion and the S1-V consumer.

The run follows the traversal naming rule: spec/.a2h/android-fast-traverse/<run_id>/android_traverse_screenshots/
holds index.json, the unit directories and the _aft/ ledger; _aft/report.json is written by the traversal's own
report generator.
"""
import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import struct
import zlib
from types import SimpleNamespace
import unittest

SKILLS = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(SKILLS / 'android_fast_traverse/scripts'))
sys.path.insert(0, str(SKILLS / 'a2h-execute/scripts'))
from aft.report import report
from aft.store import OUT_NAME
from stage1_visual_scope import baseline
from validate_runtime_snapshots import check

path = Path(__file__).resolve().parents[1] / 'promote_android_fast_traverse.py'
spec = importlib.util.spec_from_file_location('runtime_promotion', path)
promotion = importlib.util.module_from_spec(spec)
spec.loader.exec_module(promotion)

PACKAGE = 'com.example.app'
def png():
    def chunk(kind, payload):
        return struct.pack('>I',len(payload))+kind+payload+struct.pack('>I',zlib.crc32(kind+payload))
    return (b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',1440,720,8,2,0,0,0))+
            chunk(b'IDAT',zlib.compress((b'\0'+b'\0'*4320)*720))+chunk(b'IEND',b''))
PNG = png()


def view_xml(texts):
    nodes = ''.join(f'<node index="{i}" text="{t}" resource-id="{PACKAGE}:id/t{i}" class="android.widget.TextView" '
                    f'package="{PACKAGE}" content-desc="" clickable="false" bounds="[0,{i * 100}][1440,{i * 100 + 90}]" />'
                    for i, t in enumerate(texts))
    return f'<?xml version="1.0" encoding="UTF-8"?><hierarchy rotation="0">{nodes}</hierarchy>'


def write_traversal(out: Path) -> dict:
    """A finished traversal: a home page and its 15-day view state, as android_fast_traverse lays them out."""
    units = [('page_0001_MainActivity', 'page', '首页', ['首页', '今天']),
             ('page_0002_MainActivity', 'view_state', '首页·15日', ['首页', '15日', '周一'])]
    rows = []
    for page_id, kind, label, texts in units:
        unit = out / page_id
        unit.mkdir(parents=True)
        (unit / 'screenshot.png').write_bytes(PNG + page_id.encode())
        (unit / 'view.xml').write_text(view_xml(texts), encoding='utf-8')
        rec = {'page_id': page_id, 'label': label, 'timestamp': '2026-01-01T00:00:00+00:00',
               'activity_info': {'resumed_activity': f'{PACKAGE}/{PACKAGE}.MainActivity'}, 'density_factor': 3.5,
               'screenshot': f'{page_id}/screenshot.png', 'view_xml': f'{page_id}/view.xml',
               'screenshots': [f'{page_id}/screenshot.png'], 'view_xmls': [f'{page_id}/view.xml'],
               'aft': {'kind': kind, 'activity': 'MainActivity'}}
        (unit / 'meta.json').write_text(json.dumps(rec, ensure_ascii=False), encoding='utf-8')
        rows.append(rec)
    (out / 'index.json').write_text(json.dumps(rows, ensure_ascii=False), encoding='utf-8')
    state = {'status': 'completed', 'package': PACKAGE, 'serial': 'sim', 'app': {'versionName': '1.0'},
             'counters': {}, 'gaps': [], 'pages': {}, 'index': rows}
    (out / '_aft').mkdir()
    (out / '_aft' / 'state.json').write_text(json.dumps(state, ensure_ascii=False), encoding='utf-8')
    report(out)
    return state


class PromotionHandoff(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.run = self.root / 'spec/.a2h/android-fast-traverse/run_0001'
        self.out = self.run / OUT_NAME
        self.state = write_traversal(self.out)
        self.page = 'page_0027_MainActivity'
        self.mapping = [{'page_id': self.page, 'state_id': 'main_weather',
                         'source_page_id': self.state['index'][0]['page_id']}]

    def promote(self, run=None):
        mapping = self.root / 'mapping.json'
        mapping.write_text(json.dumps({'pages': self.mapping}))
        with contextlib.redirect_stdout(io.StringIO()):
            promotion.promote(SimpleNamespace(project_root=str(self.root), run=str(run or self.run),
                                             mapping=str(mapping), output=None))

    def test_actual_traversal_frame_reaches_s1v_with_semantic_state_and_provenance(self):
        self.promote()
        pair = baseline(self.root, {'page_id': self.page, 'state_id': 'main_weather'})
        self.assertTrue((self.root / pair['android_png']).is_file())
        meta = json.loads((self.root / f'spec/baseline/ui-snapshots/{self.page}/meta.json').read_text())
        ev = meta['runtime_evidence_by_state']['main_weather']
        self.assertEqual(ev['package'], self.state['package'])
        self.assertEqual(ev['device_serial'], 'sim')
        self.assertTrue(ev['activity'])
        self.assertTrue(ev['captured_at'])
        self.assertNotEqual(ev['state'], ev['capture_kind'])
        self.assertEqual(check(self.root, [{'page_id': self.page, 'state_id': 'main_weather'}])['status'], 'pass')

    def test_run_id_is_the_run_directory_and_paths_resolve_from_it(self):
        self.promote()
        result = json.loads((self.run / 'snapshot-promotion.json').read_text())
        self.assertEqual(result['run_id'], 'run_0001')
        ev = result['pages'][0]
        self.assertEqual(ev['run_id'], 'run_0001')
        for key in ('frame_id', 'source_unit', 'report_path'):
            self.assertTrue((self.run / ev[key]).is_file(), ev[key])
        self.assertFalse((self.out / 'snapshot-promotion.json').exists())  # the traversal output stays untouched

    def test_the_output_directory_itself_is_accepted_as_run(self):
        self.promote(run=self.out)
        result = json.loads((self.run / 'snapshot-promotion.json').read_text())
        self.assertEqual(result['run_id'], 'run_0001')

    def test_output_at_the_run_root_is_refused_with_the_naming_rule(self):
        flat = self.root / 'spec/.a2h/android-fast-traverse/run_flat'
        write_traversal(flat)
        with self.assertRaisesRegex(ValueError, OUT_NAME):
            self.promote(run=flat)

    def test_multiple_states_survive_promotion_and_repeated_import(self):
        other = next(row for row in self.state['index'] if '15日' in row['label'])
        self.mapping.append({'page_id': self.page, 'state_id': 'main_15day', 'source_page_id': other['page_id']})
        self.promote()
        weather = baseline(self.root, {'page_id': self.page, 'state_id': 'main_weather'})
        future = baseline(self.root, {'page_id': self.page, 'state_id': 'main_15day'})
        self.assertNotEqual(weather['android_xml'], future['android_xml'])
        self.assertNotEqual(weather['android_xml_sha256'], future['android_xml_sha256'])
        self.mapping = self.mapping[:1]
        self.promote()
        self.assertEqual(future, baseline(self.root, {'page_id': self.page, 'state_id': 'main_15day'}))

    def test_missing_business_state_is_not_inferred_from_capture_kind(self):
        del self.mapping[0]['state_id']
        with self.assertRaises(ValueError):
            self.promote()

    def test_drift_frame_is_not_marked_audited(self):
        rows = copy.deepcopy(self.state['index'])
        rows[0]['aft']['drift'] = {'city': 'unexpected'}
        (self.out / 'index.json').write_text(json.dumps(rows))
        with self.assertRaisesRegex(ValueError, 'drift'):
            self.promote()

    def test_stale_report_or_missing_device_identity_blocks_import(self):
        state = json.loads((self.out / '_aft/state.json').read_text())
        state['status'] = 'running'
        (self.out / '_aft/state.json').write_text(json.dumps(state))
        with self.assertRaises(ValueError):
            self.promote()
        state['status'] = self.state['status']
        state.pop('serial')
        (self.out / '_aft/state.json').write_text(json.dumps(state))
        with self.assertRaises(ValueError):
            self.promote()

    def test_invalid_later_mapping_does_not_partially_write_baseline(self):
        self.mapping.append({'page_id': self.page, 'state_id': '../outside',
                             'source_page_id': self.mapping[0]['source_page_id']})
        with self.assertRaises(ValueError):
            self.promote()
        self.assertFalse((self.root / 'spec/baseline/ui-snapshots').exists())


if __name__ == '__main__':
    unittest.main()
