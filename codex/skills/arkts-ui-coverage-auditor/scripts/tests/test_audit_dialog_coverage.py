"""The auditor renders the lint's closure report and adds no logic of its own:
its verdict must equal the lint's, and a missing or stale report is a FAIL."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
SKILLS = SCRIPTS.parents[1]
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SKILLS / "a2h-spec/scripts"))
import audit_dialog_coverage as adc  # noqa: E402
import dialog_closure  # noqa: E402

INVENTORY = {
    "schema_version": 1,
    "candidates": [{"dialog_id": "dlg_x", "source_fqn": "X", "required": True,
                    "host_fqns": ["H"]}],
    "anonymous_instantiations": [], "inline_call_sites": [],
    "name_only_candidates": [], "inheritance_conflicts": [],
}


class AuditDialogCoverageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.run_dir = self.root / "spec/.a2h/spec-run"
        self.run_dir.mkdir(parents=True)
        (self.run_dir / "dialog-inventory.json").write_text(json.dumps(INVENTORY), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def _report(self, summary, blocking=0, inventory=INVENTORY):
        result = dialog_closure.ClosureResult(summary=summary,
                                              inventory_digest=dialog_closure.digest(inventory))
        result.findings = [{"severity": "blocking"}] * blocking
        dialog_closure.write_report(str(self.root), result)

    def test_digest_matches_dialog_closure(self):
        self.assertEqual(adc._digest(INVENTORY), dialog_closure.digest(INVENTORY))

    def test_missing_report_fails(self):
        payload, _ = adc.audit(str(self.root))
        self.assertEqual(payload["status"], "fail")
        self.assertIn("lint_coverage.py", payload["reasons"][0])

    def test_clean_report_passes(self):
        self._report({"required": 1, "closed": 1, "approved_skip": 0, "invalid": 0, "unaccounted": 0})
        payload, _ = adc.audit(str(self.root))
        self.assertEqual(payload["status"], "pass", payload["reasons"])

    def test_verdict_follows_the_lint_not_the_row_count(self):
        """Every key being indexed used to be enough for PASS while the lint said 27/62."""
        self._report({"required": 1, "closed": 0, "approved_skip": 0, "invalid": 1, "unaccounted": 0},
                     blocking=2)
        payload, _ = adc.audit(str(self.root))
        self.assertEqual(payload["status"], "fail")

    def test_stale_report_fails(self):
        other = dict(INVENTORY, candidates=[])
        self._report({"required": 0, "closed": 0, "approved_skip": 0, "invalid": 0, "unaccounted": 0},
                     inventory=other)
        payload, _ = adc.audit(str(self.root))
        self.assertEqual(payload["status"], "fail")
        self.assertTrue(any("陈旧" in r for r in payload["reasons"]))


if __name__ == "__main__":
    unittest.main()
