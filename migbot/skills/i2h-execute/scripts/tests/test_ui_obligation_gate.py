import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
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

    def test_runner_action_id_requires_an_actual_modifier(self):
        contract = {"runner_action_ids": ["openPreferences"]}
        bad = """// Button().id('openPreferences')
                  Button().accessibilityText('openPreferences')
                  const s = ".id('openPreferences')";"""
        result = self.run_gate(bad, contract)
        self.assertEqual([row["code"] for row in result["errors"]], ["runner_action_id_missing"])
        good = "Button() { Image($r('app.media.preferences')) }.id('openPreferences')"
        self.assertEqual(self.run_gate(good, contract)["status"], "PASS")

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
            output.write_text("Tabs() { TabContent() { BeanBag() }.tabBar('home') }\nColumn().borderRadius(16)", encoding="utf-8")
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
            output.write_text("Tabs() { TabContent() { BeanBag() }.tabBar('home') }.barFloatingStyle(style)\nPath()", encoding="utf-8")
            self.assertEqual(evaluate(root, inventory)["status"], "PASS")

    def test_bound_style_evidence_cannot_disappear_or_change(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inventory = root / "inventory.json"
            inventory.write_text('{"units": []}', encoding="utf-8")
            receipt = root / "spec/.i2h/target-input.json"
            receipt.parent.mkdir(parents=True)
            receipt.write_text('{"style_triggers_sha256": "expected"}', encoding="utf-8")
            self.assertEqual(evaluate(root, inventory)["errors"][0]["code"], "style_trigger_evidence_missing")
            style = root / "spec/ref/ios-style-triggers.json"
            style.parent.mkdir(parents=True)
            style.write_text('{"triggers": []}', encoding="utf-8")
            self.assertEqual(evaluate(root, inventory)["errors"][0]["code"], "style_trigger_evidence_mismatch")

    def test_completion_deadline_is_not_an_immediate_notification_timestamp(self):
        immediate = "const request: notificationManager.NotificationRequest = { deliveryTime: session.plannedEndAt };"
        result = self.run_gate(immediate + "notificationManager.publish(request)", {})
        self.assertEqual(result["errors"][0]["code"], "notification_deadline_not_scheduled")
        self.assertEqual(self.run_gate("// " + immediate + "\nnotificationManager.publish(request)", {})["status"], "PASS")
        self.assertEqual(self.run_gate("reminderAgentManager.publishReminder(timer)", {})["status"], "PASS")

    def test_recipe_mutation_requires_observable_values_or_reassignment(self):
        plain = "class RecipeValues { dose: number = 15; }\n"
        owner = "@Local values: RecipeValues = new RecipeValues();\n"
        edit = "this.values.dose += 1;"
        result = self.run_gate(plain + owner + edit, {})
        self.assertIn("unobserved_recipe_value_mutation", {issue["code"] for issue in result["errors"]})
        traced = "@ObservedV2\nclass RecipeValues { @Trace dose: number = 15; }\n"
        self.assertEqual(self.run_gate(traced + owner + edit, {})["status"], "PASS")
        self.assertEqual(self.run_gate(plain + owner + "this.values = new RecipeValues(16);", {})["status"], "PASS")
        self.assertEqual(self.run_gate(plain + owner + "if (this.values.dose >= 15) {}", {})["status"], "PASS")

    def test_tasting_form_detects_unobserved_rating_and_note(self):
        model = "@ObservedV2 class TastingValues { @Trace rating: number = 0; note: string = ''; }\n"
        owner = "@Local values: TastingValues = new TastingValues();\n"
        result = self.run_gate(model + owner + "this.values.rating = 5; this.values.note = note;", {})
        self.assertEqual([issue["code"] for issue in result["errors"]], ["unobserved_tasting_value_mutation"])
        self.assertIn("note", result["errors"][0]["detail"])
        self.assertNotIn("rating", result["errors"][0]["detail"])
        self.assertEqual(self.run_gate(model + owner + "this.values = new TastingValues();", {})["status"], "PASS")

    def test_packaged_image_uses_the_rawfile_descriptor_with_offset(self):
        source = "raw = await context.resourceManager.getRawFd(name);\n"
        result = self.run_gate(source + "image.createImageSource(raw.fd)", {})
        self.assertIn("rawfile_image_descriptor_loses_offset", {issue["code"] for issue in result["errors"]})
        self.assertEqual(self.run_gate(source + "image.createImageSource(raw)", {})["status"], "PASS")
        self.assertEqual(self.run_gate(source + "image.createImageSource(file.fd)", {})["status"], "PASS")

    def test_sdk_catalog_rejects_unresolved_system_symbol(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            catalog = root / 'id_defined.json'
            catalog.write_text(json.dumps({'record': [
                {'type': 'symbol', 'name': 'cup_fill'}, {'type': 'media', 'name': 'book_closed'},
            ]}), encoding='utf-8')
            inventory = root / 'delivery.json'
            inventory.write_text('{"units": []}', encoding='utf-8')
            output = root / 'entry/src/main/ets/Tab.ets'
            output.parent.mkdir(parents=True)
            output.write_text("SymbolGlyph($r('sys.symbol.cup_fill'))\n"
                              "SymbolGlyph($r('sys.symbol.book_closed'))\n"
                              "// SymbolGlyph($r('sys.symbol.not_real'))", encoding='utf-8')
            result = evaluate(root, inventory, sdk_symbol_catalog=catalog)
            self.assertEqual([issue['code'] for issue in result['errors']], ['sdk_symbols_unresolved'])
            self.assertEqual(result['sdk_symbols']['unresolved'], ['book_closed'])

    def test_fresh_database_does_not_alter_a_column_it_just_created(self):
        source = """import { relationalStore } from '@kit.ArkData';
        async migrate() {
          if (version < 1) {
            await this.rdb.executeSql(`CREATE TABLE IF NOT EXISTS recipe(
              id TEXT PRIMARY KEY, note TEXT NOT NULL DEFAULT '')`);
            await this.rdb.executeSql('PRAGMA user_version = 1');
            version = 1;
          }
          if (version < 2) {
            await this.rdb.executeSql("ALTER TABLE recipe ADD COLUMN note TEXT NOT NULL DEFAULT ''");
          }
        }"""
        result = self.run_gate(source, {})
        self.assertEqual([issue['code'] for issue in result['errors']], ['database_fresh_column_added_twice'])
        self.assertEqual(self.run_gate(source.replace(
            'if (version < 2) {', "if (version < 2 && !await this.hasColumn('recipe', 'note')) {"
        ), {})['status'], 'PASS')
        self.assertEqual(self.run_gate(source.replace(
            "id TEXT PRIMARY KEY, note TEXT NOT NULL DEFAULT ''", 'id TEXT PRIMARY KEY'
        ), {})['status'], 'PASS')

    def test_named_navigation_builder_hosts_its_destination_page(self):
        root = """struct RootView {
            @Builder pageMap(name: string, param: object) {
                if (name === 'BeanDetail') { BeanDetailView() }
            }
            build() { Navigation(this.stack) {}.navDestination(this.pageMap) }
        }"""
        detail = "struct BeanDetailView { build() { Text('Bean') } }"
        result = self.run_gate(root + detail, {})
        self.assertEqual([issue['code'] for issue in result['errors']], ['navigation_destination_host_missing'])
        self.assertEqual(self.run_gate(root.replace('BeanDetailView()', 'NavDestination() { BeanDetailView() }') + detail, {})['status'], 'PASS')
        self.assertEqual(self.run_gate(root + detail.replace("Text('Bean')", "NavDestination() { Text('Bean') }"), {})['status'], 'PASS')

    def test_runtime_state_and_database_contracts_are_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "entry/src/main/ets/pages/RootView.ets"
            output.parent.mkdir(parents=True)
            output.write_text(
                """@ComponentV2 export struct RootView {
  private router: AppRouter = AppRouter.shared;
  build() { Stack() {}.bindSheet(this.router.recipe !== null, this.recipeSheet()) }
}""",
                encoding="utf-8",
            )
            database = root / "entry/src/main/ets/database/DbHelper.ets"
            database.parent.mkdir(parents=True)
            database.write_text(
                """import { relationalStore } from '@kit.ArkData';
async count(table: string): Promise<number> {
  const resultSet = await store.query(predicates, ['id']);
  return resultSet.rowCount;
}
await store.executeSql('CREATE TABLE IF NOT EXISTS library_metadata (key TEXT PRIMARY KEY)');
""",
                encoding="utf-8",
            )
            inventory = root / "spec/baseline/ui-delivery-approved.json"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(json.dumps({"units": [{
                "unit_id": "root",
                "output": {"file": "entry/src/main/ets/pages/RootView.ets"},
                "source_obligations": {},
            }]}), encoding="utf-8")
            result = evaluate(root, inventory)
            codes = {row["code"] for row in result["errors"]}
            self.assertIn("observable_state_owner_missing", codes)
            self.assertIn("presentation_state_derived_binding", codes)
            self.assertIn("database_count_assumes_id", codes)
            self.assertIn("database_migration_missing", codes)

    def test_database_comment_and_version_read_do_not_count_as_upgrade(self):
        source = '''import { relationalStore } from '@kit.ArkData';
// ALTER TABLE brew ADD COLUMN note TEXT
/* await store.executeSql('ALTER TABLE brew ADD COLUMN label TEXT'); */
await store.executeSql('CREATE TABLE IF NOT EXISTS brew (id TEXT PRIMARY KEY)');
const version = await store.querySql('PRAGMA user_version');
console.info('migration planned');
'''
        self.assertIn("database_migration_missing", {row["code"] for row in self.run_gate(source, {})["errors"]})

    def test_generic_count_rejects_multiline_id_projection(self):
        source = '''import { relationalStore } from '@kit.ArkData';
await store.executeSql('CREATE TABLE IF NOT EXISTS library_metadata (key TEXT PRIMARY KEY)');
await store.executeSql('ALTER TABLE library_metadata ADD COLUMN last_recipe TEXT');
async count(table: string): Promise<number> {
  const rows = await store.query(
    new relationalStore.RdbPredicates(table),
    ['id']
  );
  return rows.rowCount;
}
'''
        self.assertIn("database_count_assumes_id", {row["code"] for row in self.run_gate(source, {})["errors"]})

    def test_worker_sample_cannot_hide_upgrade_or_projection_behind_a_name(self):
        source = '''import { relationalStore } from '@kit.ArkData';
async migrateSchema(): Promise<void> {
  await store.executeSql('CREATE TABLE IF NOT EXISTS schema_meta (key TEXT PRIMARY KEY)');
}
async count(table: string, keyColumn: string = 'id'): Promise<number> {
  const rows = await store.query(new relationalStore.RdbPredicates(table), [keyColumn]);
  return rows.rowCount;
}
'''
        codes = {row["code"] for row in self.run_gate(source, {})["errors"]}
        self.assertIn("database_count_assumes_id", codes)
        self.assertIn("database_migration_missing", codes)

    def test_id_query_in_another_method_does_not_fail_generic_count(self):
        source = '''import { relationalStore } from '@kit.ArkData';
await store.executeSql('CREATE TABLE IF NOT EXISTS brew (id TEXT PRIMARY KEY)');
await store.executeSql('ALTER TABLE brew ADD COLUMN note TEXT');
async count(table: string): Promise<number> {
  const result = await store.querySql(`SELECT COUNT(*) FROM ${table}`);
  return result.getLong(0);
}
async findBrew(): Promise<void> {
  await store.query(new relationalStore.RdbPredicates('brew'), ['id']);
}
'''
        self.assertEqual(self.run_gate(source, {})["status"], "PASS")

    def test_same_component_cannot_bind_multiple_sheets(self):
        source = '''Stack() { HomeView() }
  .bindSheet(this.showRecipe, this.recipeSheet(), { onWillDismiss: (action) => action.dismiss() })
  .bindContentCover(this.showBrew, this.brewCover())
  .backgroundColor($r('app.color.paper'))
  .bindSheet(this.showSettings, this.settingsSheet())
'''
        self.assertIn("multiple_sheets_on_same_host", {row["code"] for row in self.run_gate(source, {})["errors"]})

    def test_separate_sheet_hosts_and_quoted_examples_are_allowed(self):
        source = '''Stack() {
  Column() { HomeView() }.bindSheet(this.showRecipe, this.recipeSheet())
  Column() {}.bindSheet(this.showSettings, this.settingsSheet())
}
Text('.bindSheet(true, fake()).bindSheet(true, fake())')
'''
        self.assertEqual(self.run_gate(source, {})["status"], "PASS")


if __name__ == "__main__":
    unittest.main()
