#!/usr/bin/env python3
"""lint_execute_coverage.py 的范围按阶段：批 / 组收口只查已收口单元，--final 才查全部。

锚点 gpt1030_2（2026-10-18）：Stage 1 第二批结算时 impl-claims.json 还不存在，
旧逻辑「executed 为空 = 全部入范围」报 EXECUTE.REQUIREMENT_UNCLAIMED 302 条、已认领 0。
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import lint_execute_coverage as lec  # noqa: E402


class ExecuteCoverageScope(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        i2h = self.root / "spec/.i2h"
        i2h.mkdir(parents=True)
        (i2h / "plan-coverage.json").write_text(json.dumps({"packets": [
            {"packet_id": "slice-01-F001", "requirement_ids": ["F001-AC01", "F001-AC02"], "requirement_digests": {"F001-AC01": "a", "F001-AC02": "b"}},
            {"packet_id": "slice-02-F002", "requirement_ids": ["F002-AC01"], "requirement_digests": {"F002-AC01": "c"}},
        ]}), encoding="utf-8")
        (i2h / "requirements-index.json").write_text(json.dumps({"requirements": [
            {"requirement_id": r, "digest": d} for r, d in zip(("F001-AC01", "F001-AC02", "F002-AC01"), "abc")
        ]}), encoding="utf-8")

        (self.root / "Main.ets").write_text("// fixture\n", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _claims(self, claims, executed):
        (self.root / "spec/.i2h/impl-claims.json").write_text(json.dumps(
            {"claims": claims, "executed_packets": executed}), encoding="utf-8")

    def _unclaimed(self):
        data = json.loads((self.root / "spec/.i2h/open-findings.json").read_text(encoding="utf-8"))
        return sorted(f["subject"] for f in data["sections"][lec.SECTION]["findings"]
                      if f["rule"] == "EXECUTE.REQUIREMENT_UNCLAIMED")

    def _run(self, *extra):
        sys.argv = ["lint_execute_coverage.py", "--project-root", str(self.root), *extra]
        return lec.main()

    def test_nothing_executed_yet_is_clean_at_batch_settlement(self):
        self.assertEqual(self._run(), 0)
        self.assertEqual(self._unclaimed(), [])

    def test_only_executed_packets_are_checked(self):
        self._claims([{"requirement_id": "F001-AC01", "packet_id": "slice-01-F001", "files": ["Main.ets"], "requirement_digest": "a"}], ["slice-01-F001"])
        self.assertEqual(self._run(), 2)
        self.assertEqual(self._unclaimed(), ["F001-AC02"])

    def test_final_checks_every_packet(self):
        self._claims([{"requirement_id": "F001-AC01", "packet_id": "slice-01-F001", "files": ["Main.ets"], "requirement_digest": "a"}], ["slice-01-F001"])
        self.assertEqual(self._run("--final"), 2)
        self.assertEqual(self._unclaimed(), ["F001-AC02", "F002-AC01"])

    def test_final_without_any_claims_reports_all(self):
        # A22 终态：全部组未收敛、一条认领都没有——终态结算仍要报出来
        self.assertEqual(self._run("--final"), 2)
        self.assertEqual(self._unclaimed(), ["F001-AC01", "F001-AC02", "F002-AC01"])

    def test_final_reports_scope_deferral_without_passing_it(self):
        (self.root / "spec/decision-ledger.md").write_text(
            "## D-906 本期范围\n\n- **延期 AC**: `F001-AC02`\n", encoding="utf-8")
        self.assertEqual(self._run("--final"), 2)
        findings = json.loads((self.root / "spec/.i2h/open-findings.json").read_text(encoding="utf-8"))
        rows = findings["sections"][lec.SECTION]["findings"]
        self.assertIn({"rule": "EXECUTE.REQUIREMENT_DEFERRED", "subject": "F001-AC02",
                       "packet_id": "slice-01-F001", "decision_id": "D-906"}, rows)
        self.assertEqual(self._unclaimed(), ["F001-AC01", "F002-AC01"])

    def test_invalid_claims_do_not_count_and_reporting_is_read_only(self):
        from contextlib import redirect_stdout
        import io

        valid = {"requirement_id": "F001-AC01", "packet_id": "slice-01-F001",
                 "files": ["Main.ets"], "requirement_digest": "a"}
        self._claims([
            {**valid, "files": []},
            {**valid, "requirement_digest": "old"},
            {**valid, "packet_id": "slice-02-F002"},
            {**valid, "files": ["missing.ets"]},
            {**valid, "code_anchors": [{"file": "Main.ets", "line": 2}]},
        ], ["slice-01-F001"])
        output = self.root / "spec/.i2h/open-findings.json"
        output.write_text('{"sections":{"verify":{"findings":[1]}}}', encoding="utf-8")
        before = output.read_bytes()
        report = io.StringIO()
        with redirect_stdout(report):
            self.assertEqual(self._run("--final", "--report-only"), 2)
        self.assertEqual(output.read_bytes(), before)
        rows = json.loads(report.getvalue())["sections"]["execute"]["findings"]
        self.assertEqual({row["rule"] for row in rows}, {
            "EXECUTE.MISSING_IMPLEMENTATION_FILES", "EXECUTE.STALE_REQUIREMENT_DIGEST",
            "EXECUTE.WRONG_PACKET_REQUIREMENT", "EXECUTE.INVALID_IMPLEMENTATION_FILE",
            "EXECUTE.INVALID_CODE_ANCHOR", "EXECUTE.REQUIREMENT_UNCLAIMED",
        })
        self.assertIn("F001-AC01", {row["subject"] for row in rows
                                   if row["rule"] == "EXECUTE.REQUIREMENT_UNCLAIMED"})
        self.assertEqual(self._run("--final"), 2)
        self.assertEqual(json.loads(output.read_bytes())["sections"]["verify"]["findings"], [1])


if __name__ == "__main__":
    unittest.main()
