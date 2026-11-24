import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock
import importlib.util
import io
from contextlib import redirect_stdout


SCRIPT = Path(__file__).resolve().parents[1] / 'ios_static_analyzer.py'


class IOSStaticAnalyzerTest(unittest.TestCase):
    def analyze(self, source):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'Example.ets').write_text(source, encoding='utf-8')
            result = subprocess.run(
                [sys.executable, '-B', str(SCRIPT), str(root), '--json'],
                capture_output=True, text=True, check=False,
            )
        self.assertTrue(result.stdout.strip(), result.stderr)
        return result.returncode, json.loads(result.stdout)

    def test_multiline_source_notes_and_quoted_delimiters_do_not_report_violations(self):
        code, report = self.analyze(
            '/* Swift references\n'
            ' * UserDefaults\n'
            ' * import UIKit\n'
            ' */\n'
            'const url = "https://example.test/*";\n'
            'const message = "UserDefaults"; // DispatchQueue\n'
            'const note = `source documentation\n'
            'DispatchQueue\n'
            '`;\n'
        )
        self.assertEqual(code, 0)
        self.assertEqual(report['findings'], [])

    def test_code_after_comments_or_literals_keeps_its_rule_and_line(self):
        code, report = self.analyze(
            '/* UserDefaults\n'
            ' */ UserDefaults.standard;\n'
            'const url = "https://example.test"; DispatchQueue.main;\n'
            'const docs = "UserDefaults"; UserDefaults.standard;\n'
            'import value from "@ohos.example";\n'
        )
        self.assertEqual(code, 1)
        findings = {(row['rule_id'], row['line']) for row in report['findings']}
        self.assertEqual(findings, {('IOS.USER_DEFAULTS', 2), ('IOS.DISPATCH_QUEUE', 3),
                                    ('IOS.USER_DEFAULTS', 4), ('COMMON.OLD_OHOS_IMPORT', 5)})

    def test_string_boundary_warning_keeps_arrays_and_grapheme_helpers_untouched(self):
        code, report = self.analyze(
            'function lengthOf(value: string): number {\n'
            '  return Array.from(value).length;\n'
            '}\n'
            'function prefix(value: string, max: number): string {\n'
            '  return Array.from(value)\n'
            '    .slice(0, max).join("");\n'
            '}\n'
            'function items(value: number[]): number { return Array.from(value).length; }\n'
            'function characters(value: string): number { return characterCount(value); }\n'
            '// function ignored(value: string): number { return Array.from(value).length; }\n'
        )
        self.assertEqual(code, 0)
        self.assertEqual([(row['rule_id'], row['line'], row['symbol'], row['level'])
                          for row in report['findings']], [
            ('IOS.SWIFT_STRING_BOUNDARY', 2, 'lengthOf', 'WARN'),
            ('IOS.SWIFT_STRING_BOUNDARY', 5, 'prefix', 'WARN'),
        ])


class StaticAnalyzerTransportTests(unittest.TestCase):
    def setUp(self):
        spec=importlib.util.spec_from_file_location('portable_static_analyzer',SCRIPT)
        self.module=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.module)

    def test_rg_json_keeps_windows_drive_path_and_colons_in_code(self):
        path=r'C:\workspace\Example.ets'
        event={'type':'match','data':{'path':{'text':path},'line_number':7,
               'lines':{'text':'  UserDefaults.standard; // note: text\n'}}}
        result=Mock(returncode=0,stdout=json.dumps(event)+'\n',stderr='')
        with patch.object(self.module.subprocess,'run',return_value=result) as run:
            rows=self.module.IOSStaticAnalyzer('.').search_pattern('UserDefaults')
        self.assertEqual(rows,[(path,7,'  UserDefaults.standard; // note: text')])
        self.assertIn('--json',run.call_args.args[0])

    def test_no_matches_remains_an_empty_result(self):
        result=Mock(returncode=1,stdout='',stderr='')
        with patch.object(self.module.subprocess,'run',return_value=result):
            self.assertEqual(self.module.IOSStaticAnalyzer('.').search_pattern('UserDefaults'),[])

    def test_rg_failure_is_a_tool_error_not_zero_violations(self):
        result=Mock(returncode=2,stdout='',stderr='permission denied')
        with patch.object(self.module.subprocess,'run',return_value=result):
            with self.assertRaisesRegex(RuntimeError,'ripgrep failed'):
                self.module.IOSStaticAnalyzer('.').search_pattern('UserDefaults')

    def test_missing_rg_returns_structured_json_and_error_exit(self):
        output=io.StringIO()
        with patch.object(sys,'argv',[str(SCRIPT),'.','--json']), patch.object(self.module.shutil,'which',return_value=None), redirect_stdout(output):
            with self.assertRaises(SystemExit) as caught:self.module.main()
        self.assertEqual(caught.exception.code,2)
        self.assertEqual(json.loads(output.getvalue())['status'],'ERROR')
