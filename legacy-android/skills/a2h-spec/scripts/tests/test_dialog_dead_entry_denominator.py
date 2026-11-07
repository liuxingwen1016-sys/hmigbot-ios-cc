#!/usr/bin/env python3
"""死入口弹窗不进 Dialog 闭合分母：dialog_index 骨架与 dialog_closure 的 required 集合口径一致。

锚点 AIPPT（2026-10-18）：CampaignDialog / LimitedGiftDialog 的唯一入口被 `// [VV-AD-OFF]` 注释掉，
dialog_inventory 现在给出 required=false / dead_entry_only=true；匿名实例在死入口里的给 required=false。
两个下游都必须跟着不把它们算进分母，否则索引里没这行、闭合闸又要它 → 永远闭合不了。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import dialog_closure  # noqa: E402
import dialog_index  # noqa: E402

INVENTORY = {
    "schema_version": 1,
    "candidates": [
        {"dialog_id": "dlg_live", "source_fqn": "com.x.LiveDialog", "required": True, "usage_edges": [],
         "host_fqns": ["com.x.HomeActivity"], "suggested_page_type": "dialog"},
        {"dialog_id": "dlg_dead", "source_fqn": "com.x.AdDialog", "required": False, "dead_entry_only": True,
         "usage_edges": [{"source_file": "a.kt", "line": 9, "dead_entry": True}], "host_fqns": ["com.x.HomeActivity"]},
    ],
    "anonymous_instantiations": [
        {"instance_id": "dlginst_live", "base_fqn": "com.x.LiveDialog", "source_file": "a.kt", "line": 3,
         "host_fqns": ["com.x.HomeActivity"], "required": True},
        {"instance_id": "dlginst_dead", "base_fqn": "com.x.LiveDialog", "source_file": "a.kt", "line": 20,
         "host_fqns": ["com.x.HomeActivity"], "required": False, "dead_entry": True},
        {"instance_id": "dlginst_legacy", "base_fqn": "com.x.LiveDialog", "source_file": "b.kt", "line": 5,
         "host_fqns": ["com.x.HomeActivity"]},
    ],
}


class DeadEntryDenominator(unittest.TestCase):
    def test_closure_required_items_skip_dead_entries(self):
        keys = sorted(key for _kind, key, _fqn, _rec in dialog_closure._required_items(INVENTORY))
        self.assertEqual(keys, ["dlg_live", "dlginst_legacy", "dlginst_live"])

    def test_index_skeleton_rows_match_closure_denominator(self):
        rows = sorted(r.get("dialog_key") for r in dialog_index._source_facts(INVENTORY))
        closure = sorted(key for _kind, key, _fqn, _rec in dialog_closure._required_items(INVENTORY))
        self.assertEqual(rows, closure)


if __name__ == "__main__":
    unittest.main()
