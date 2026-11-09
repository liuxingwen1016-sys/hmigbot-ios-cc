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
        path.parent.mkdir(parents=True)
        path.write_text("{broken", encoding="utf-8")
        code = self._apply({"impl_claims": {"claims": [claim()]}})
        self.assertEqual(code, 1)
        self.assertEqual(path.read_text(encoding="utf-8"), "{broken")


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
