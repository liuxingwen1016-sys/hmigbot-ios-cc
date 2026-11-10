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

    def test_sheet_to_cover_transition_cannot_open_cover_from_close_handler(self):
        obligations = {
            "presentations": [
                {"kind": "sheet", "source_pattern": ".sheet"},
                {"kind": "full_screen_cover", "source_pattern": ".fullScreenCover"},
            ]
        }
        source = (
            "Column() { Text('Root') }"
            ".bindSheet(this.showRecipe, this.recipeSheet(), { onDisappear: () => {} })"
            ".bindContentCover(this.showBrew, this.brewCover())"
        )
        eager_router = "closeRecipe() { this.recipe = null; this.showBrew = true; }"
        result = self.run_gate(source + eager_router, obligations)
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("presentation_transition_eager", {row["code"] for row in result["errors"]})

        deferred_router = "closeRecipe() { this.recipe = null; }"
        result = self.run_gate(source + deferred_router, obligations)
        self.assertEqual(result["status"], "PASS")

    def test_expanded_root_requires_foreground_top_bar_inset(self):
        obligations = {}
        bad = (
            "Column() { Row() { Text('萃刻'); Text('偏好设置').onClick(() => {}) }"
            ".padding({ top: 10 }) }"
            ".expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.TOP])"
        )
        result = self.run_gate(bad, obligations)
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("foreground_safearea_missing", {row["code"] for row in result["errors"]})

        good = (
            "Column() { Row() { Text('萃刻'); Text('偏好设置').onClick(() => {}) }"
            ".safeAreaPadding({ top: 24 }) }"
            ".expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.TOP])"
        )
        result = self.run_gate(good, obligations)
        self.assertEqual(result["status"], "PASS")

    def test_hosted_presentation_can_use_centralized_binding_file(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            host = root / "entry/src/main/ets/pages/RootView.ets"
            entry = root / "entry/src/main/ets/Index.ets"
            host.parent.mkdir(parents=True)
            entry.parent.mkdir(parents=True, exist_ok=True)
            host.write_text("Column() { Text('Home') }", encoding="utf-8")
            entry.write_text("RootView().bindSheet(this.showRecipe)", encoding="utf-8")
            inventory = root / "spec/baseline/ui-delivery-approved.json"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(json.dumps({"units": [{
                "unit_id": "u",
                "output": {"file": "entry/src/main/ets/pages/RootView.ets"},
                "source_obligations": {"presentations": [{"kind": "sheet"}]},
            }]}), encoding="utf-8")
            result = evaluate(root, inventory)
            self.assertEqual(result["status"], "PASS")

    def test_unicode_icon_literals_fail_without_asset_mapping(self):
        result = self.run_gate("Text('✓')", {})
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("unicode_symbol_substitute", {row["code"] for row in result["errors"]})

        result = self.run_gate("Text('加一') + Text('+')", {})
        self.assertEqual(result["status"], "FAIL")
        result = self.run_gate("// symbol_fidelity: approved asset=app.media.plus\nText('+')", {})
        self.assertEqual(result["status"], "PASS")

    def test_style_triggers_reject_native_only_tab_and_rounded_bag(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "entry/src/main/ets/pages/RootView.ets"
            output.parent.mkdir(parents=True)
            output.write_text("Tabs() { TabContent() { BeanBag() } }", encoding="utf-8")
            trigger_path = root / "spec/ref/ios-style-triggers.json"
            trigger_path.parent.mkdir(parents=True)
            trigger_path.write_text(json.dumps({"triggers": [
                {"trigger_id": "floating_tabbar"},
                {"trigger_id": "custom_shape_geometry"},
            ]}), encoding="utf-8")
            inventory = root / "spec/baseline/ui-delivery-approved.json"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(json.dumps({"units": [{
                "unit_id": "root",
                "output": {"file": "entry/src/main/ets/pages/RootView.ets"},
                "source_obligations": {},
            }]}), encoding="utf-8")
            result = evaluate(root, inventory)
            codes = {row["code"] for row in result["errors"]}
            self.assertIn("floating_tabbar_native_only", codes)
            self.assertIn("custom_shape_geometry_missing", codes)


if __name__ == "__main__":
    unittest.main()
