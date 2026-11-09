import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audit_interaction_candidates import scan


class AdvisoryTests(unittest.TestCase):
    def scan_text(self, text):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / 'entry/src/main/ets'
            folder.mkdir(parents=True)
            (folder / 'Sample.ets').write_text(text)
            return scan(root)

    def test_empty_array_mutation_and_comment_only_click(self):
        text = '''@Local items: Item[] = [];
ForEach(this.items, item => Text(item.name))
Button('skip').onClick(() => { /* nothing */ })'''
        result = self.scan_text(text)
        self.assertEqual({f['code'] for f in result['findings']},
                         {'STATE_NEVER_ASSIGNED_CANDIDATE', 'CLICK_HANDLER_NOOP_CANDIDATE'})
        self.assertTrue(all(f['severity'] == 'WARN' for f in result['findings']))
        result = self.scan_text(text + '\nthis.items.push(value);')
        self.assertNotIn('STATE_NEVER_ASSIGNED_CANDIDATE', [f['code'] for f in result['findings']])

    def test_store_identity_and_delete_is_not_writer(self):
        text = '''PreferencesUtil.getString('city', '', Store.CACHE);
PreferencesUtil.putString('city', 'value', Store.USER);
PreferencesUtil.delete('city', Store.CACHE);'''
        result = self.scan_text(text)
        self.assertEqual(len(result['findings']), 1)
        self.assertEqual(result['findings'][0]['store'], 'Store.CACHE')
        self.assertEqual(self.scan_text(text + "\nPreferencesUtil.putString('city', 'value', Store.CACHE);")['findings'], [])

    def test_literal_constant_and_dynamic_unknown(self):
        text = '''static readonly CITY: string = 'city';
PreferencesUtil.getString(Keys.CITY, '', Store.CACHE);
PreferencesUtil.getString(`weather_${id}`, '', Store.CACHE);
PreferencesUtil.putString('city', 'value', Store.CACHE);'''
        self.assertEqual(self.scan_text(text)['findings'], [])

    def test_missing_source_is_not_a_clean_scan(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = scan(Path(tmp))
            self.assertEqual(result['status'], 'NOT_SCANNED')
            self.assertEqual(result['files_scanned'], 0)
