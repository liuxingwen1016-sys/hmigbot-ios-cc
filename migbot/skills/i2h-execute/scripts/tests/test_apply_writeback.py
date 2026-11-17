#!/usr/bin/env python3
"""Fixtures for the impl_claims writeback section (reconciliation C2).

The claims ledger has no random writers: closer aggregates worker briefs into
the writeback manifest, apply_writeback.py is the only thing that touches
spec/.i2h/impl-claims.json. These tests pin the append/idempotency semantics.
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

import apply_writeback as aw  # noqa: E402


def claim(req="F001-AC01", packet="slice-03-F001", attempt=1, files=None):
    return {"requirement_id": req, "packet_id": packet,
            "files": files or ["entry/src/main/ets/X.ets"],
            "symbols": ["X.handle"], "requirement_digest": "sha256:aa", "attempt": attempt}


class ImplClaimsWriteback(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = Path(self.tmp)
        index = self.root / "spec/.i2h"
        index.mkdir(parents=True)
        requirements = {"F001-AC01": "sha256:aa", "F001-AC02": "sha256:aa"}
        (index / "plan-coverage.json").write_text(json.dumps({"packets": [{
            "packet_id": "slice-03-F001", "requirement_ids": list(requirements),
            "requirement_digests": requirements,
        }]}), encoding="utf-8")
        (index / "requirements-index.json").write_text(json.dumps({"requirements": [
            {"requirement_id": ac, "digest": digest} for ac, digest in requirements.items()
        ]}), encoding="utf-8")
        for name in ("entry/src/main/ets/X.ets", "entry/src/main/ets/Y.ets", "Y.ets", "Z.ets"):
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("// line one\n// line two\n", encoding="utf-8")
        aw.applied.clear(); aw.noops.clear(); aw.warns.clear()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _apply(self, manifest: dict, dry=False) -> int:
        mp = self.root / "wb.json"
        mp.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        argv = [str(mp), "--project-root", str(self.root)] + (["--dry-run"] if dry else [])
        aw.applied.clear(); aw.noops.clear(); aw.warns.clear()
        return aw.main(argv)

    def _ledger(self) -> dict:
        return json.loads((self.root / "spec/.i2h/impl-claims.json").read_text(encoding="utf-8"))

    def test_claims_land_and_replay_is_idempotent(self):
        manifest = {"impl_claims": {"claims": [claim()], "executed_packets": ["slice-03-F001"]}}
        self.assertEqual(self._apply(manifest), 0)
        doc = self._ledger()
        self.assertEqual(len(doc["claims"]), 1)
        self.assertEqual(doc["executed_packets"], ["slice-03-F001"])
        # crash recovery = rerun apply: nothing may duplicate
        self.assertEqual(self._apply(manifest), 0)
        doc = self._ledger()
        self.assertEqual(len(doc["claims"]), 1)
        self.assertEqual(doc["executed_packets"], ["slice-03-F001"])

    def test_same_identity_different_content_overwrites(self):
        self._apply({"impl_claims": {"claims": [claim()]}})
        self._apply({"impl_claims": {"claims": [claim(files=["entry/src/main/ets/Y.ets"])]}})
        doc = self._ledger()
        self.assertEqual(len(doc["claims"]), 1)
        self.assertEqual(doc["claims"][0]["files"], ["entry/src/main/ets/Y.ets"])

    def test_new_attempt_is_a_new_entry(self):
        self._apply({"impl_claims": {"claims": [claim(), claim(attempt=2)]}})
        self.assertEqual(len(self._ledger()["claims"]), 2)

    def test_dry_run_writes_nothing(self):
        self._apply({"impl_claims": {"claims": [claim()]}}, dry=True)
        self.assertFalse((self.root / "spec/.i2h/impl-claims.json").exists())

    def test_malformed_existing_ledger_is_never_overwritten(self):
        path = self.root / "spec/.i2h/impl-claims.json"
        path.write_text("{broken", encoding="utf-8")
        code = self._apply({"impl_claims": {"claims": [claim()]}})
        self.assertEqual(code, 1)
        self.assertEqual(path.read_text(encoding="utf-8"), "{broken")

    def _merge(self, *sections, dry=False):
        paths = []
        for number, section in enumerate(sections):
            path = self.root / f"partial-{number}.json"
            path.write_text(json.dumps(section), encoding="utf-8")
            paths.append(str(path))
        options = ["--dry-run"] if dry else []
        return aw.main([*paths, "--project-root", str(self.root), "--merge-evidence", *options])

    def test_consolidates_partial_manifests_and_existing_evidence_on_replay(self):
        old = claim()
        self._apply({"impl_claims": {"claims": [old]}})
        first_anchor = {"file": "Y.ets", "line": 1}
        second_anchor = {"file": "Z.ets", "line": 2}
        first = {"impl_claims": {"claims": [
            {**claim(files=["Y.ets"]), "code_anchors": [first_anchor], "verification_evidence": ["first.json"]},
        ], "executed_packets": [old["packet_id"]]}}
        second = {"impl_claims": {"claims": [
            {**claim(files=["Z.ets"]), "code_anchors": [second_anchor], "verification_evidence": ["second.json"]},
            claim(attempt=2),
        ], "executed_packets": [old["packet_id"]]}}
        self.assertEqual(self._merge(first, second), 0)
        doc = self._ledger()
        self.assertEqual(doc["executed_packets"], [old["packet_id"]])
        self.assertEqual(len(doc["claims"]), 2)
        merged = doc["claims"][0]
        self.assertEqual(merged["files"], [*old["files"], "Y.ets", "Z.ets"])
        self.assertEqual(merged["code_anchors"], [first_anchor, second_anchor])
        self.assertEqual(merged["verification_evidence"], ["first.json", "second.json"])
        self.assertEqual(doc["claims"][1]["attempt"], 2)
        self.assertEqual(self._merge(first, second), 0)
        self.assertEqual(self._ledger(), doc)

    def test_merge_rejects_incompatible_inputs_without_changing_ledger(self):
        self._apply({"impl_claims": {"claims": [claim()]}})
        path = self.root / "spec/.i2h/impl-claims.json"
        before = path.read_bytes()
        valid = {"impl_claims": {"claims": [claim(req="F001-AC02")]}}
        for incompatible in (
            {"impl_claims": {"claims": [{**claim(), "files": []}]}},
            {"impl_claims": {"claims": [{**claim(), "files": ["missing.ets"]}]}},
            {"impl_claims": {"claims": [claim(packet="slice-99-F999")]}},
            {"impl_claims": {"claims": [claim(), claim()]}},
            {"impl_claims": {"claims": [], "executed_packets": ["slice-03-F001"]}},
            {"impl_claims": {"claims": [{**claim(), "requirement_digest": "changed"}]}},
            {"impl_claims": {"claims": [{**claim(), "code_anchors": "not an array"}]}},
            {"impl_claims": {"claims": []}, "registry": {"resolve": ["P-S1-001"]}},
        ):
            with self.subTest(incompatible=incompatible):
                self.assertEqual(self._merge(valid, incompatible), 1)
                self.assertEqual(path.read_bytes(), before)
        self.assertEqual(self._merge(valid, dry=True), 0)
        self.assertEqual(path.read_bytes(), before)


    def test_regular_write_rejects_stale_claim_without_touching_ledger(self):
        self.assertEqual(self._apply({"impl_claims": {"claims": [claim()]}}), 0)
        path = self.root / "spec/.i2h/impl-claims.json"
        before = path.read_bytes()
        invalid = {"impl_claims": {"claims": [claim(req="F001-AC02"),
                                               {**claim(), "requirement_digest": "stale"}]}}
        self.assertEqual(self._apply(invalid, dry=True), 1)
        self.assertEqual(self._apply(invalid), 1)
        self.assertEqual(path.read_bytes(), before)


REGISTRY = """# 占位符注册表

## 注册表

| P-ID | location | trigger_condition | status | kind | resolve_by |
|------|----------|-------------------|--------|------|------------|
| P-S1-001 | entry/src/main/ets/pages/A.ets#onTap | Slice 1 Step 3d | registered | forward-ref | Slice 1 Step 3d |
| P-S2-001 | entry/src/main/ets/services/X.ets#init | 广告 SDK 入仓 | registered | thirdparty-sdk | |
"""


class RegistryWriteback(unittest.TestCase):
    """resolve[] 只翻 status=resolved，任何 kind 都不删行（可追溯 + Class 2 对账）。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = Path(self.tmp)
        reg = self.root / "spec/placeholder-registry.md"
        reg.parent.mkdir(parents=True)
        reg.write_text(REGISTRY, encoding="utf-8")
        aw.applied.clear(); aw.noops.clear(); aw.warns.clear()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _apply(self, manifest: dict) -> int:
        mp = self.root / "wb.json"
        mp.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        aw.applied.clear(); aw.noops.clear(); aw.warns.clear()
        return aw.main([str(mp), "--project-root", str(self.root)])

    def test_resolve_keeps_rows_for_every_kind(self):
        code = self._apply({"registry": {"resolve": ["P-S1-001", "P-S2-001", "P-S9-999"]}})
        self.assertEqual(code, 0)
        text = (self.root / "spec/placeholder-registry.md").read_text(encoding="utf-8")
        for pid in ("P-S1-001", "P-S2-001"):
            row = next(l for l in text.splitlines() if l.startswith(f"| {pid} "))
            self.assertIn("| resolved |", row, row)
        self.assertEqual(text.count("| P-S"), 2)               # 没有任何行被删
        self.assertTrue(any("P-S9-999" in n for n in aw.noops))  # 不存在的行只记 noop
        # 重放幂等
        self.assertEqual(self._apply({"registry": {"resolve": ["P-S1-001"]}}), 0)
        self.assertEqual((self.root / "spec/placeholder-registry.md").read_text(encoding="utf-8"), text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
