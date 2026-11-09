#!/usr/bin/env python3
"""build_writeback：FV-1 未收敛但已记「未达标放行」时，末组照常补翻认领（剩余 FAIL 落在其文件上的 slice 除外）。

Anchor: gpt1030_3（2026-10-19）D-025——末组 F015 等 FV-1 CONVERGED 才补翻，FV-1 因 6 条与 F015 无关的残留被放行后
永远补不上，23 条 AC 没人认领。
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

import build_writeback as bw  # noqa: E402

LOOP = "spec/execution/autofix-log/round-1/loop-result-latest-pipeline-final.json"
ORPHANS = "spec/execution/autofix-log/round-1/orphans-pipeline-iter1.json"


class FinalWritebackAfterReleasedFv1(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        cov = {"packets": [
            {"packet_id": "slice-14-F015", "requirement_ids": ["F015-AC01", "F015-AC02"],
             "requirement_digests": {"F015-AC01": "sha256:a", "F015-AC02": "sha256:b"}},
            {"packet_id": "slice-15-F016", "requirement_ids": ["F016-AC01"],
             "requirement_digests": {"F016-AC01": "sha256:c"}}]}
        self._write("spec/.i2h/plan-coverage.json", cov)
        self._write(LOOP, {"verdict": "STALLED", "detector_json_paths": {"orphans": ORPHANS}})
        self._write(ORPHANS, {"orphans": [
            {"file": "entry/src/main/ets/components/common/WorksItem.ets", "class_name": "WorksItem",
             "reason": "NO_IMPORTER"},
            {"file": "entry/src/main/ets/pages/F016Page.ets", "class_name": "F016Page", "reason": "NO_IMPORTER"}]})
        (self.root / "brief.md").write_text("# FV-1\n", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _write(self, rel, obj):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(obj), encoding="utf-8")

    def _intent(self, **extra):
        intent = {"mode": "final", "feature_index": {"implemented": ["F015", "F016"]},
                  "packets": {"slice-14-F015": {"files": ["entry/src/main/ets/pages/GuidePage.ets"]},
                              "slice-15-F016": {"files": ["entry/src/main/ets/pages/F016Page.ets"]}},
                  "brief": {"path": "spec/execution/briefs/final_structural_closure_brief.md",
                            "content_file": "brief.md"}}
        intent.update(extra)
        return intent

    def test_unrelated_leftovers_do_not_block_last_group_claims(self):
        m, warns = bw.build(self._intent(fv1_unconverged={"loop_result": LOOP, "decision": "D-024"}), self.root)
        claimed = sorted(c["requirement_id"] for c in m["impl_claims"]["claims"])
        self.assertEqual(claimed, ["F015-AC01", "F015-AC02"])               # F015 补翻
        self.assertEqual(m["feature_index"]["implemented"], ["F015"])        # F016 的文件仍有 FAIL：不翻
        self.assertEqual(m["notes"]["fv1_unconverged"]["dropped"],
                         {"slice-15-F016": ["entry/src/main/ets/pages/F016Page.ets"]})
        self.assertTrue(any("F016" in w for w in warns))

    def test_release_needs_a_decision_and_final_mode(self):
        with self.assertRaises(SystemExit):
            bw.build(self._intent(fv1_unconverged={"loop_result": LOOP, "decision": ""}), self.root)
        with self.assertRaises(SystemExit):
            bw.build(self._intent(fv1_unconverged={"loop_result": LOOP, "decision": "D-024"}, mode="group", id="07"),
                     self.root)

    def test_converged_fv1_claims_everything(self):
        m, _ = bw.build(self._intent(), self.root)
        self.assertEqual(len(m["impl_claims"]["claims"]), 3)
        self.assertEqual(m["feature_index"]["implemented"], ["F015", "F016"])


if __name__ == "__main__":
    unittest.main()
