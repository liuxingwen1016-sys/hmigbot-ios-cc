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
            {"packet_id": "slice-01-F001", "requirement_ids": ["F001-AC01", "F001-AC02"]},
            {"packet_id": "slice-02-F002", "requirement_ids": ["F002-AC01"]},
        ]}), encoding="utf-8")
        (i2h / "requirements-index.json").write_text(json.dumps({"requirements": [
            {"requirement_id": r, "status": "active"} for r in ("F001-AC01", "F001-AC02", "F002-AC01")
        ]}), encoding="utf-8")

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
        self._claims([{"requirement_id": "F001-AC01", "packet_id": "slice-01-F001"}], ["slice-01-F001"])
        self.assertEqual(self._run(), 2)
        self.assertEqual(self._unclaimed(), ["F001-AC02"])

    def test_final_checks_every_packet(self):
        self._claims([{"requirement_id": "F001-AC01", "packet_id": "slice-01-F001"}], ["slice-01-F001"])
        self.assertEqual(self._run("--final"), 2)
        self.assertEqual(self._unclaimed(), ["F001-AC02", "F002-AC01"])

    def test_final_without_any_claims_reports_all(self):
        # A22 终态：全部组未收敛、一条认领都没有——终态结算仍要报出来
        self.assertEqual(self._run("--final"), 2)
        self.assertEqual(self._unclaimed(), ["F001-AC01", "F001-AC02", "F002-AC01"])


if __name__ == "__main__":
    unittest.main()
