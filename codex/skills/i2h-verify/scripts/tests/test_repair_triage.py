import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from repair_triage import _rows, repair_priority, triage


class RepairTriageTests(unittest.TestCase):
    def test_priority_orders_missing_controls_before_content_and_style(self):
        self.assertEqual(repair_priority({"category": "control_missing"}), "P0")
        self.assertEqual(repair_priority({"category": "content_mismatch"}), "P1")
        self.assertEqual(repair_priority({"category": "layout_mismatch", "severity": "low"}), "P2")

    def test_unknown_scope_expands_without_closing_acceptance(self):
        result = triage(
            [{"id": "f-1", "category": "style_mismatch"}],
            [{"id": "page-1", "page_ids": ["p1"]}, {"id": "page-2", "page_ids": ["p2"]}],
        )
        finding = result["findings"][0]
        self.assertEqual(finding["impact"]["scope"], "full_ui")
        self.assertEqual(finding["impact"]["associated_plan_items"], ["page-1", "page-2"])
        self.assertFalse(finding["impact"]["acceptance_changed"])
        self.assertEqual(result["acceptance"], "unchanged")

    def test_page_and_feature_identity_limits_scope(self):
        result = triage(
            [{"id": "f-1", "category": "state_mismatch", "page_ids": ["p1"]}],
            [{"id": "page-1", "page_ids": ["p1"]}, {"id": "page-2", "page_ids": ["p2"]}],
        )
        self.assertEqual(result["findings"][0]["impact"]["scope"], "associated")
        self.assertEqual(result["findings"][0]["impact"]["associated_plan_items"], ["page-1"])

    def test_plan_items_projection_is_supported(self):
        rows = _rows({"plan_items": {"page-1": {"page_ids": ["p1"]}}}, "plan")
        self.assertEqual(rows, [{"id": "page-1", "page_ids": ["p1"]}])


if __name__ == "__main__":
    unittest.main()
