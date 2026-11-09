import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from ui_obligation_gate import evaluate  # noqa: E402


class UiObligationGateTests(unittest.TestCase):
    def run_gate(self, source: str, obligations: dict, presentation=None):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "entry/src/main/ets/pages/Test.ets"
            output.parent.mkdir(parents=True)
            output.write_text(source, encoding="utf-8")
            inventory = root / "spec/baseline/ui-delivery-approved.json"
            inventory.parent.mkdir(parents=True)
            unit = {"unit_id": "u", "output": {"file": str(output.relative_to(root))}, "source_obligations": obligations}
            if presentation is not None:
                unit["presentation"] = presentation
            inventory.write_text(json.dumps({"units": [unit]}), encoding="utf-8")
            return evaluate(root, inventory)

    def test_fixed_action_must_be_outside_scroll_and_picker_rows_are_required(self):
        obligations = {
            "fixed_bottom_action_required": True,
            "primary_action_ids": ["saveBean"],
            "compact_picker_rows_required": True,
            "form_picker_labels": [{"label": "处理法"}],
        }
        bad = "Scroll() { Column() { Button('保存').id('saveBean') } }"
        result = self.run_gate(bad, obligations)
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("fixed_action_inside_scroll", {row["code"] for row in result["errors"]})
        good = "Scroll() { Column() { Text('处理法') } } Column() { Select([{value:'水洗'}]).id('processPicker') Button('保存').id('saveBean') }"
        result = self.run_gate(good, obligations)
        self.assertEqual(result["status"], "PASS")

    def test_toolbar_search_and_chart_have_structural_markers(self):
        obligations = {
            "searchable": True,
            "searchable_placement": "toolbar",
            "chart": {"height": 120},
        }
        result = self.run_gate("TextInput() Rect()", obligations)
        self.assertEqual(result["status"], "FAIL")
        codes = {row["code"] for row in result["errors"]}
        self.assertIn("toolbar_search_inline_input", codes)
        self.assertIn("chart_line_points_missing", codes)
        result = self.run_gate("Toolbar() { Search({ value: '' }) } Canvas() { drawLine(); drawCircle(); }.height(120)", obligations)
        self.assertEqual(result["status"], "PASS")

    def test_toolbar_search_rejects_permanent_search_without_toolbar_state(self):
        obligations = {"searchable": True, "searchable_placement": "toolbar"}
        result = self.run_gate("Column() { Search({ value: '' }) }", obligations)
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("toolbar_search_inline_input", {row["code"] for row in result["errors"]})

        result = self.run_gate("Column() { if (this.showSearch) { Search({ value: '' }) } }", obligations)
        self.assertEqual(result["status"], "PASS")

    def test_accepts_legacy_string_picker_labels(self):
        obligations = {
            "compact_picker_rows_required": True,
            "form_picker_labels": ["处理法", "产地"],
        }
        source = "Column() { Select([{value:'水洗'}]); Text('处理法'); Select([{value:'埃塞俄比亚'}]); Text('产地') }"
        result = self.run_gate(source, obligations)
        self.assertEqual(result["status"], "PASS")

    def test_chart_height_matches_integer_and_decimal_forms(self):
        obligations = {"chart": {"height": 120.0}}
        source = "Canvas() { drawLine(); drawCircle(); }.height(120)"
        result = self.run_gate(source, obligations)
        self.assertEqual(result["status"], "PASS")

    def test_sheet_requires_native_binding_or_complete_fallback_marker(self):
        obligations = {"presentations": [{"kind": "sheet", "source_pattern": ".sheet"}]}
        result = self.run_gate("Column() { Text('Recipe') }", obligations)
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("presentation_binding_missing", {row["code"] for row in result["errors"]})

        result = self.run_gate("Column() { Text('Recipe') }.bindSheet(this.showRecipe)", obligations)
        self.assertEqual(result["status"], "PASS")

        marker = (
            "// presentation_fallback: kind=sheet owner=RootView state=showRecipe "
            "scrim=true corner=top detent=medium dismissal=onDismiss safe_area=host\n"
            "Column() { Text('Recipe') }"
        )
        result = self.run_gate(marker, obligations)
        self.assertEqual(result["status"], "PASS")

    def test_full_screen_cover_requires_content_cover_binding(self):
        obligations = {"presentations": [{"kind": "full_screen_cover", "source_pattern": ".fullScreenCover"}]}
        result = self.run_gate("Column() { Text('Scan') }", obligations)
        self.assertEqual(result["status"], "FAIL")
        result = self.run_gate("Column() { Text('Scan') }.bindContentCover(this.showScan)", obligations)
        self.assertEqual(result["status"], "PASS")

    def test_unicode_icon_literals_fail_without_asset_mapping(self):
        result = self.run_gate("Text('✓')", {})
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("unicode_symbol_substitute", {row["code"] for row in result["errors"]})

        result = self.run_gate("Text('加一') + Text('+')", {})
        self.assertEqual(result["status"], "FAIL")
        result = self.run_gate("// symbol_fidelity: approved asset=app.media.plus\nText('+')", {})
        self.assertEqual(result["status"], "PASS")


if __name__ == "__main__":
    unittest.main()
