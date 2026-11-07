import importlib.util
import tempfile
import unittest
from pathlib import Path


spec = importlib.util.spec_from_file_location("join_gate", Path(__file__).with_name("join_gate.py"))
join_gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(join_gate)


class ResultFormatTests(unittest.TestCase):
    def check(self, relative, content):
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
            return join_gate.check_artifacts(root, {"artifacts": [{"path": relative, "json": True}]})

    def test_raw_json_stays_supported(self):
        self.assertEqual(self.check("spec/reports/report.json", '{"ok": true}'), [])

    def test_fenced_json_is_rejected(self):
        self.assertTrue(self.check("spec/reports/report.json", '```json\n{}\n```'))


if __name__ == "__main__":
    unittest.main()
