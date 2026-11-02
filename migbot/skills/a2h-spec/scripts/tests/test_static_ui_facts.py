"""Source-only behavioral regressions for target/resource/page/renderer contracts."""
import argparse
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ui_facts as ui
from target_input import atomic_json, resolve_model, validate_model, source_digest, TargetInputError, materialize_projection
from static_resource_index import ResourceIndex
from static_page_facts import PageExtractor, synthesize_view

A = 'xmlns:android="http://schemas.android.com/apk/res/android"'


class StaticFactsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "android"
        self.out = Path(self.temp.name) / "target"
        self.put("app/build.gradle", "plugins { id 'com.android.application' }\nandroid { }")
        self.put("app/src/main/java/com/example/Main.kt", """package com.example
import androidx.appcompat.app.AppCompatActivity
class Main : AppCompatActivity() {
 override fun getLayoutResId() = R.layout.main
 val adapter = HomeAdapter()
}
""")
        self.put("app/src/main/java/com/example/HomeAdapter.kt", """package com.example
class HomeAdapter {
 init {
 addItemType(ONE, R.layout.item_one)
 addItemType(TWO, R.layout.item_two)
 }
}
""")
        self.put("app/src/main/AndroidManifest.xml", f'<manifest package="com.example" {A}><application android:theme="@style/App"><activity android:name=".Main"/></application></manifest>')
        self.put("app/src/main/res/values/styles.xml", """<resources>
<style name="Parent"><item name="android:textColor">@color/title</item><item name="android:textSize">@dimen/title_size</item></style>
<style name="Child" parent="@style/Parent"><item name="android:textColor">@color/other</item></style>
<style name="App"><item name="bottomNavigationStyle">@style/Widget.Material3.BottomNavigationView</item><item name="colorSurfaceContainer">@color/surface</item></style>
<color name="title">#112233</color><color name="other">#112233</color><color name="surface">#EBEEF3</color>
<color name="unused">#202022</color><dimen name="title_size">18dp</dimen>
</resources>""")
        self.put("app/src/main/res/layout/main.xml", f"""<layout {A}><data><variable name="vm" type="VM"/></data>
<LinearLayout android:id="@+id/root" android:layout_width="match_parent" android:layout_height="match_parent">
<include layout="@layout/header" android:id="@+id/first" android:visibility="invisible"/>
<include layout="@layout/header" android:id="@+id/second"/>
<com.google.android.material.bottomnavigation.BottomNavigationView android:id="@+id/nav"/>
<androidx.recyclerview.widget.RecyclerView android:id="@+id/list"/>
<ViewStub android:id="@+id/later" android:layout="@layout/item_one"/>
</LinearLayout></layout>""")
        self.put("app/src/main/res/layout/header.xml", f'<TextView {A} android:id="@+id/title" style="@style/Child" android:textSize="20dp"/>')
        for name in ("item_one", "item_two"):
            self.put(f"app/src/main/res/layout/{name}.xml", f'<TextView {A} android:text="{name}"/>')
        self.put("app/src/main/res/drawable/weather.xml", f'<level-list {A}><item android:minLevel="0" android:maxLevel="2" android:drawable="@drawable/a"/><item android:minLevel="3" android:maxLevel="4" android:drawable="@drawable/b"/></level-list>')
        self.put("app/src/main/res/drawable/arrow.xml", f'<vector {A} android:width="24dp" android:height="24dp"><path android:pathData="M0,0L1,1" android:strokeColor="?attr/colorSurfaceContainer"/></vector>')
        self.cache = Path(self.temp.name) / "cache"
        jar = self.cache / "com.google.android.material/material/1.12.0/one/material-1.12.0.aar"
        jar.parent.mkdir(parents=True)
        with zipfile.ZipFile(jar, "w") as z:
            z.writestr("res/values/values.xml", """<resources>
<style name="Widget.Material3.BottomNavigationView"><item name="android:background">@macro/nav_container</item></style>
<macro name="nav_container">?attr/colorSurfaceContainer</macro>
</resources>""")
        self.model = resolve_model(self.root, "app", "debug", "debug", static_literals=True)
        self.model["dependencies"] = [{"group": "com.google.android.material", "artifact": "material", "version": "1.12.0"}]
        self.model["source_revision"] = source_digest(self.model)
        self.target = Path(self.temp.name) / "target-input.json"
        atomic_json(self.target, self.model)
        self.index = ResourceIndex(self.model).build(self.cache)

    def test_b2_join_static_refresh_preserves_promoted_runtime_xml(self):
        ui.prepare(self.args())
        snap = self.out / 'spec/baseline/ui-snapshots/page_0001_Main'
        meta_path = snap / 'meta.json'
        meta = json.loads(meta_path.read_text())
        actual = '<hierarchy><node package="com.example" text="Runtime title"/></hierarchy>'
        frame = snap / 'states/normal/view.xml'
        frame.parent.mkdir(parents=True)
        frame.write_text(actual)
        meta['runtime_evidence'] = {'status': 'audited', 'state': 'normal',
                                   'view_xml_path': 'states/normal/view.xml', 'view_xml_sha256': ui.digest(frame)}
        meta['runtime_evidence_by_state'] = {'normal': meta['runtime_evidence']}
        meta['view_xml_synthesized'] = False
        meta_path.write_text(json.dumps(meta))
        (snap / 'view.xml').write_text(actual)
        ui.prepare(self.args())
        self.assertEqual((snap / 'view.xml').read_text(), actual)
        self.assertIn('synthesized="true"', (snap / 'view.static.xml').read_text())
        updated = json.loads(meta_path.read_text())
        self.assertFalse(updated['view_xml_synthesized'])
        self.assertEqual(updated['runtime_evidence_by_state'], meta['runtime_evidence_by_state'])

    def tearDown(self):
        self.temp.cleanup()

    def put(self, path, value):
        p = self.root / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(value, encoding="utf-8")
        return p

    def page(self):
        extractor = PageExtractor(self.model, self.index, ui.digest(self.target))
        return extractor.extract({"activity": "com.example.Main", "page_id": "page_0001_Main", "priority": "P0"})

    def args(self, policy="static-v1"):
        return argparse.Namespace(policy=policy, target_input=str(self.target), project_root=str(self.out),
             preview_config=None, gradle_cache=str(self.cache), pages=None, decisions=None)

    def test_main_classification_not_confused_by_fragment_references(self):
        self.assertEqual(self.model["resolution"], "resolved")
        meta, visual, fixture, templates = self.page()
        self.assertEqual(meta["page_type"], "full_screen_page")
        self.assertTrue(meta["needs_immersive_safearea"])

    def test_binding_wrapper_include_overrides_and_templates(self):
        meta, visual, fixture, templates = self.page()
        self.assertFalse(any(n["class"].endswith((".layout", ".data", ".variable")) for n in visual["nodes"]))
        nodes = {n["node_key"]: n for n in visual["nodes"]}
        self.assertEqual(nodes["first"]["props"]["android:visibility"]["value"], "invisible")
        self.assertFalse(nodes["first"]["initially_visible"])
        self.assertIn("second", nodes)
        self.assertEqual(nodes["second"]["props"]["android:textSize"]["androidUnit"], "dp")
        self.assertEqual(nodes["second"]["props"]["android:textSize"]["value"], 20)
        self.assertEqual(set(templates), {"item_one", "item_two"})
        xml = synthesize_view(visual["nodes"], "com.example", ui.digest(self.target))
        self.assertNotIn('text="item_one"', xml)
        self.assertIn('visual-key="later"', xml)
        self.assertIn('bounds=""', xml)

    def test_material_macro_resolves_offline(self):
        _, visual, _, _ = self.page()
        nav = next(n for n in visual["nodes"] if n["node_key"] == "nav")
        background = nav["props"]["android:background"]
        self.assertEqual(background["value"], "#EBEEF3")
        chain = json.dumps(background["chain"])
        self.assertIn("macro/nav_container", chain)
        self.assertIn("1.12.0", chain)

    def test_reference_dimen_preserves_android_and_target_units(self):
        size = self.index.resolve("@dimen/title_size")
        self.assertEqual(size["value"], 18)
        self.assertEqual(size["androidUnit"], "dp")
        self.assertEqual(size["targetUnit"], "vp")

    def test_usage_tokens_preserve_identity_and_exclude_unused(self):
        _, visual, _, _ = self.page()
        _, tokens = ui.usage_tokens([visual], self.index)
        ids = {t["resource_id"] for t in tokens["tokens"]}
        self.assertIn("color/other", ids)
        self.assertNotIn("color/unused", ids)
        self.assertIn("color/unused", tokens["unreferenced_in_selected_scope"])

    def test_level_order_and_stroke_only_vector(self):
        level = self.index.drawables["drawable/weather@"]
        self.assertEqual([i["max_level"] for i in level["items"]], [2, 4])
        arrow = self.index.drawables["drawable/arrow@"]
        self.assertTrue(arrow["has_stroke"])
        self.assertFalse(arrow["has_fill"])

    def test_style_overlay_merges_items(self):
        self.put("app/src/debug/res/values/more.xml", '<resources><style name="Child"><item name="android:textSize">30dp</item></style></resources>')
        model = resolve_model(self.root, "app", "debug", "debug", static_literals=True)
        index = ResourceIndex(model).build()
        style = index.style("Child")
        self.assertEqual(style["android:textColor"]["raw"], "@color/other")
        self.assertEqual(style["android:textSize"]["raw"], "30dp")

    def test_wrong_flavor_files_never_participate(self):
        self.put("app/src/safe/java/com/example/Main.kt", "package com.example\nclass Main {}")
        self.put("app/src/safe/res/values/styles.xml", '<resources><color name="other">#BADBAD</color></resources>')
        self.assertEqual(self.index.resolve("@color/other")["value"], "#112233")
        self.assertFalse(any("/safe/" in p for p in self.model["source_sets"][0]["source_dirs"]))
        validate_model(self.model)

    def test_duplicate_selected_fqn_and_dynamic_dsl_fail_closed(self):
        self.put("app/src/main/java/com/example/Other.kt", "package com.example\nclass Main {}")
        with self.assertRaisesRegex(TargetInputError, "duplicate participating FQN"):
            validate_model(self.model)
        self.put("app/build.gradle", "apply from: remoteConfig; android.sourceSets.configure(dynamicSource())")
        model = resolve_model(self.root, "app", "debug", "debug", static_literals=True)
        self.assertEqual(model["resolution"], "unresolved")
        self.assertEqual(model["source_sets"], [])

    def test_identical_aar_copies_are_equivalent_conflicting_hashes_fail(self):
        import shutil
        original = next(self.cache.glob("**/*.aar"))
        duplicate = original.parent.parent / "two" / original.name
        duplicate.parent.mkdir()
        shutil.copyfile(original, duplicate)
        idx = ResourceIndex(self.model).build(self.cache)
        self.assertEqual(len(idx.artifacts), 1)
        with zipfile.ZipFile(duplicate, "a") as z:
            z.writestr("extra.txt", "different")
        idx = ResourceIndex(self.model).build(self.cache)
        self.assertTrue(any(d["code"] == "AAR_AMBIGUOUS" for d in idx.diagnostics))

    def test_legacy_is_noop_shadow_is_isolated_and_static_is_deterministic(self):
        self.assertEqual(ui.prepare(self.args("legacy"))["generated"], 0)
        self.assertFalse(self.out.exists())
        shadow = ui.prepare(self.args("static-v1-shadow"))
        self.assertIn("ui-facts-shadow", shadow["baseline"])
        self.assertFalse((self.out / "spec/baseline").exists())
        result = ui.prepare(self.args())
        baseline = Path(result["baseline"])
        first = {str(p.relative_to(baseline)): ui.digest(p) for p in baseline.rglob("*") if p.is_file()}
        again = ui.prepare(self.args())
        self.assertTrue(again["resource_cache_hit"])
        second = {str(p.relative_to(baseline)): ui.digest(p) for p in baseline.rglob("*") if p.is_file()}
        self.assertEqual(first, second)

    def test_renderer_is_idempotent_and_lint_detects_tampering(self):
        result = ui.prepare(self.args())
        baseline = Path(result["baseline"])
        snapshot = next((baseline / "ui-snapshots").glob("page_*"))
        spec = baseline / "ui" / (snapshot.name + ".md")
        spec.parent.mkdir()
        spec.write_text("# Human spec\n\nKeep this requirement.\n")
        args = argparse.Namespace(baseline=str(baseline))
        ui.render(args)
        expected = spec.read_text()
        ui.render(args)
        self.assertEqual(spec.read_text(), expected)
        spec.write_text(expected.replace("#112233", "#999999"))
        lint_args = argparse.Namespace(baseline=str(baseline), target_input=str(self.target), output=str(self.out / "lint.json"))
        report = ui.lint(lint_args)
        self.assertTrue(any(f["code"] == "SPEC_VISUAL_FACTS_STALE" for f in report["findings"]))

    def test_source_only_without_adb(self):
        import os
        env = {**os.environ, "PATH": ""}
        proc = subprocess.run([sys.executable, str(Path(ui.__file__)), "prepare", "--policy", "static-v1",
                    "--project-root", str(self.out), "--target-input", str(self.target), "--gradle-cache", str(self.cache)],
                    capture_output=True, text=True, env=env)
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        self.assertFalse(any("capture" in p.name or p.suffix == ".png" for p in self.out.rglob("*")))

    def test_p0_unresolved_cannot_be_deferred(self):
        _, visual, _, _ = self.page()
        obligation = next(o for o in visual["obligations"] if o["initially_visible"])
        with self.assertRaisesRegex(ValueError, "cannot be deferred"):
            ui.apply_decisions(visual, {"obligations": [{"id": obligation["id"], "disposition": "deferred"}]})

    def test_qualifiers_do_not_guess_locale_or_density(self):
        self.put("app/src/main/res/values-zh/strings.xml", '<resources><string name="only_zh">中文</string></resources>')
        model = resolve_model(self.root, "app", "debug", "debug", static_literals=True)
        index = ResourceIndex(model).build()
        self.assertEqual(index.resolve("@string/only_zh")["status"], "unresolved")

    def test_source_revision_and_projection_integrity(self):
        validate_model(self.model)
        projection = Path(self.temp.name) / "projection"
        materialize_projection(self.model, projection)
        with self.assertRaises(TargetInputError):
            self.put("app/src/main/java/com/example/Main.kt", "package com.example\nclass Main { val changed = true }")
            validate_model(self.model)

    def refresh(self):
        self.model = resolve_model(self.root, "app", "debug", "debug", static_literals=True)
        self.model["dependencies"] = [{"group": "com.google.android.material", "artifact": "material", "version": "1.12.0"}]
        atomic_json(self.target, self.model)
        self.index = ResourceIndex(self.model).build(self.cache)

    def test_nested_include_cycle_reports_instead_of_recursing(self):
        self.put("app/src/main/res/layout/header.xml", '<include layout="@layout/header"/>')
        self.refresh()
        _, visual, _, _ = self.page()
        self.assertTrue(any(o["kind"] == "page_structure" and o["disposition"] is None for o in visual["obligations"]))

    def test_preference_screen_without_layout_is_extracted(self):
        self.put("app/src/main/java/com/example/Settings.kt", """package com.example
import androidx.preference.PreferenceFragmentCompat
class Settings : PreferenceFragmentCompat() {
 fun onCreatePreferences() { setPreferencesFromResource(R.xml.settings, null) }
}""")
        self.put("app/src/main/res/xml/settings.xml", f'<PreferenceScreen {A}><PreferenceCategory android:title="Display"><SwitchPreferenceCompat android:key="dark" android:defaultValue="false"/></PreferenceCategory></PreferenceScreen>')
        self.refresh()
        ext = PageExtractor(self.model, self.index, ui.digest(self.target))
        _, visual, _, _ = ext.extract({"page_id": "page_0002_Settings", "activity": "com.example.Settings"})
        self.assertEqual(len(visual["preferences"]), 3)
        self.assertEqual(visual["preferences"][2]["props"]["android:defaultValue"]["value"], "false")
        self.assertFalse(any(o["kind"] == "page_structure" for o in visual["obligations"]))

    def test_dialog_generic_binding_owner_is_materialized(self):
        self.put("app/src/main/java/com/example/Sheet.kt", """package com.example
import androidx.fragment.app.DialogFragment
abstract class BaseSheet<T> : DialogFragment() {}
class Sheet : BaseSheet<SheetBodyBinding>() {}
class Caller { fun open() { Sheet().show(manager, "sheet") } }
""")
        self.put("app/src/main/res/layout/sheet_body.xml", f'<TextView {A} android:text="sheet"/>')
        self.refresh()
        result = ui.prepare(self.args())
        snapshots = Path(result["baseline"]) / "dialog-snapshots"
        self.assertTrue(any(p.name.endswith("_Sheet") for p in snapshots.glob("dlgsnap_*")))
        p = next(p for p in snapshots.glob("dlgsnap_*") if p.name.endswith("_Sheet"))
        meta = ui.read(p / "meta.json")
        self.assertFalse(meta["needs_immersive_safearea"])
        self.assertTrue((p / "view.xml").is_file())

    def test_custom_draw_constant_and_variable_have_distinct_obligations(self):
        self.put("app/src/main/java/com/example/Chart.java", """package com.example;
class Chart extends View {
 void onDraw(Canvas c) {
   paint.setColor(R.color.title);
   c.drawLine(0f, 0f, 10f, 10f, paint);
   c.drawLine(0f, 0f, getWidth(), amount, paint);
 }
}""")
        self.put("app/src/main/res/layout/header.xml", f'<com.example.Chart {A} android:id="@+id/chart"/>')
        self.refresh()
        _, visual, _, _ = self.page()
        draws = visual["custom_draw"][0]["draw_operations"]
        self.assertEqual(len(draws), 2)
        self.assertEqual(draws[0]["disposition"], "script_resolved")
        self.assertTrue(draws[1]["requires_interpretation"])
        self.assertTrue(ui.verify_citation(draws[1]["source_ref"]))

    def test_initial_source_override_wins_but_callback_is_only_candidate(self):
        self.put("app/src/main/java/com/example/Main.kt", """package com.example
import androidx.appcompat.app.AppCompatActivity
class Main : AppCompatActivity() {
 override fun getLayoutResId() = R.layout.main
 fun onCreate() {
   binding.second.setTextColor(R.color.title)
   button.setOnClickListener {
     binding.second.setTextColor(R.color.unused)
   }
 }
}""")
        self.refresh()
        _, visual, _, _ = self.page()
        title = next(n for n in visual["nodes"] if n["node_key"] == "second")
        self.assertEqual(title["props"]["android:textColor"]["raw"], "@color/title")
        facts = title["code_overrides"]
        self.assertTrue(facts[0]["initial_assignment_proven"])
        self.assertFalse(facts[1]["initial_assignment_proven"])

    def test_missing_widget_defaults_produce_open_obligation(self):
        self.model["dependencies"] = []
        self.index = ResourceIndex(self.model).build()
        _, visual, _, _ = self.page()
        self.assertTrue(any(o["disposition"] is None for o in visual["obligations"]))

    def test_gate_requires_page_specs_and_preserves_other_findings(self):
        result = ui.prepare(self.args())
        import _a2h_findings as registry
        registry.replace_section(str(self.out), "spec/other", [registry.make("OTHER", "spec", "x", "keep")])
        args = argparse.Namespace(baseline=result["baseline"], target_input=str(self.target), output=None,
                                  project_root=str(self.out), require_specs=True, after_repair=False)
        report = ui.lint(args)
        self.assertTrue(any(f["code"] == "PAGE_SPEC_MISSING" for f in report["findings"]))
        self.assertIn("spec/other", registry.load(str(self.out))["sections"])

    def test_cited_preview_choice_is_separate_from_resource_value(self):
        _, visual, _, _ = self.page()
        obligation = next(o for o in visual["obligations"] if o["kind"] == "fixture_data")
        ui.apply_decisions(visual, {"obligations": [{"id": obligation["id"], "disposition": "preview_policy",
            "owner": "Slice 1 Step 3c", "policy_ref": "source example first entry", "preview_value": 1,
            "source_refs": [obligation["source_ref"]]}]})
        self.assertEqual(visual["preview_scene"]["selections"][0]["preview_value"], 1)
        self.assertFalse(any("preview_value" in f for n in visual["nodes"] for f in n["props"].values()))

    def test_packaged_entries_load_without_original_sibling_sources(self):
        import shutil
        scripts = Path(ui.__file__).resolve().parent
        destination = Path(self.temp.name) / "isolated-scripts"
        shutil.copytree(scripts, destination)
        for name, relative in ui.read(scripts / "build-dependencies.json").items():
            shutil.copyfile((scripts / relative).resolve(), destination / (name + ".py"))
        proc = subprocess.run([sys.executable, str(destination / "ui_facts.py"), "prepare",
                               "--policy", "legacy", "--project-root", str(self.out)],
                              cwd=str(destination), capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["status"], "legacy")

    def test_output_schemas_match_the_published_contract(self):
        try:
            import jsonschema
        except ImportError:
            self.skipTest("Optional JSON schema validation dependency unavailable")
        result = ui.prepare(self.args())
        baseline = Path(result["baseline"])
        schema_root = Path(ui.__file__).resolve().parent.parent / "schemas"
        for directory in (baseline / "ui-snapshots").glob("page_*"):
            jsonschema.validate(ui.read(directory / "visual.json"), ui.read(schema_root / "visual-facts.schema.json"))
            jsonschema.validate(ui.read(directory / "fixture.json"), ui.read(schema_root / "preview-fixture.schema.json"))
        resource_schema = ui.SCRIPTS / "android2hmos_resources_convert/schemas/resource-index.schema.json"
        for name in ("values", "drawables", "usage", "design-tokens"):
            jsonschema.validate(ui.read(baseline / ("res-index/" + name + ".json")), ui.read(resource_schema))

    def test_unknown_width_qualifier_requires_a_profile(self):
        self.put("app/src/main/res/layout-w600dp/main.xml", '<TextView/>')
        self.refresh()
        record, error = self.index.select("layout", "main")
        self.assertIsNone(record)
        self.assertEqual(error, "configuration_required")
        record, error = self.index.select("layout", "main", {"width_dp": 393})
        self.assertIsNone(error)
        self.assertEqual(record["config"], "")

    def test_unresolved_value_cannot_be_upgraded_by_prose(self):
        _, visual, _, _ = self.page()
        obligation = {"id": "unresolved-color", "kind": "property", "status": "unresolved",
                      "initially_visible": True, "disposition": None}
        visual["obligations"].append(obligation)
        with self.assertRaisesRegex(ValueError, "cannot upgrade"):
            ui.apply_decisions(visual, {"obligations": [{"id": obligation["id"], "disposition": "resolved"}]})

    def test_old_manifest_tokens_are_replaced_by_the_resource_projection(self):
        result = ui.prepare(self.args())
        baseline = Path(result["baseline"])
        manifest = baseline / "ui-manifest.md"
        manifest.write_text("# UI Manifest\n\n- 设计令牌: guessed-black=#202022\n- 导航架构: keep\n")
        ui.render(argparse.Namespace(baseline=str(baseline)))
        text = manifest.read_text()
        self.assertNotIn("guessed-black", text)
        self.assertIn("res-index/design-tokens.json", text)
        self.assertIn("导航架构: keep", text)

    def test_adapter_with_no_adapter_suffix_is_discovered_by_inheritance(self):
        self.put("app/src/main/java/com/example/Main.kt", """package com.example
import androidx.appcompat.app.AppCompatActivity
class Main : AppCompatActivity() {
 override fun getLayoutResId() = R.layout.main
 val painter = ViewportPresenter()
}""")
        self.put("app/src/main/java/com/example/ViewportPresenter.kt", """package com.example
class ViewportPresenter : RecyclerView.Adapter<Row>() {
 fun onCreateViewHolder() { inflate(R.layout.item_one) }
}""")
        self.refresh()
        _, visual, _, templates = self.page()
        self.assertIn("item_one", templates)
        self.assertTrue(any(c["class"] == "com.example.ViewportPresenter" and c["kind"] == "adapter"
                            for c in visual["composition"]["children"]))

    def test_fragment_with_arbitrary_name_and_import_alias_is_discovered(self):
        self.put("app/src/main/java/com/example/Tile.kt", """package com.example
import androidx.fragment.app.Fragment as Carrier
class Tile : Carrier() { fun getLayoutResId() = R.layout.header }
""")
        self.put("app/src/main/java/com/example/Main.kt", """package com.example
import androidx.appcompat.app.AppCompatActivity
class Main : AppCompatActivity() {
 override fun getLayoutResId() = R.layout.main
 val content = Tile()
}""")
        self.refresh()
        _, visual, _, _ = self.page()
        self.assertTrue(any(c["class"] == "com.example.Tile" and c["kind"] == "fragment"
                            for c in visual["composition"]["children"]))

    def test_theme_helper_without_theme_name_resolves_constant_return(self):
        self.put("app/src/main/java/com/example/Bookkeeping.java", """package com.example;
class Bookkeeping { public static int pick() { return R.style.Child; } }
""")
        self.put("app/src/main/java/com/example/Main.kt", """package com.example
import androidx.appcompat.app.AppCompatActivity
class Main : AppCompatActivity() {
 override fun getLayoutResId() = R.layout.main
 fun onCreate() {
   val paint = Bookkeeping.pick()
   setTheme(paint)
 }
}""")
        self.refresh()
        _, visual, _, _ = self.page()
        self.assertEqual(visual["page"]["theme"]["selected"], "@style/Child")

    def test_theme_branch_is_not_selected_from_style_name(self):
        self.put("app/src/main/java/com/example/Bookkeeping.java", """package com.example;
class Bookkeeping {
 public static int pick(boolean flag) {
  if (flag) { return R.style.Child; }
  return R.style.Parent;
 }
}""")
        self.put("app/src/main/java/com/example/Main.kt", """package com.example
import androidx.appcompat.app.AppCompatActivity
class Main : AppCompatActivity() {
 override fun getLayoutResId() = R.layout.main
 fun onCreate() { setTheme(Bookkeeping.pick(flag)) }
}""")
        self.refresh()
        _, visual, _, _ = self.page()
        theme = visual["page"]["theme"]
        self.assertIsNone(theme["selected"])
        self.assertEqual(theme["reason"], "source_theme_selection_required")
        self.assertEqual({r["ref"] for r in theme["branches"]}, {"@style/App", "@style/Child", "@style/Parent"})

    def test_dark_configuration_does_not_require_dark_style_name(self):
        self.put("app/src/main/res/values-night/night.xml", '<resources><style name="App"><item name="colorSurfaceContainer">#010203</item></style></resources>')
        self.refresh()
        _, visual, _, _ = self.page()
        branch = next(b for b in visual["page"]["theme"]["branches"] if b["ref"] == "@style/App")
        self.assertEqual(branch["configurations"]["dark"]["colorSurfaceContainer"]["value"], "#010203")

    def test_explicit_resource_root_does_not_require_res_directory_name(self):
        import shutil
        relocated = self.root / "skins/palette"
        relocated.parent.mkdir()
        shutil.move(str(self.root / "app/src/main/res"), relocated)
        self.model["source_sets"][0]["res_dirs"] = ["skins/palette"]
        self.model["source_revision"] = source_digest(self.model)
        atomic_json(self.target, self.model)
        self.index = ResourceIndex(self.model).build(self.cache)
        _, visual, _, templates = self.page()
        self.assertTrue(visual["nodes"])
        self.assertIn("item_one", templates)

    def test_custom_databinding_class_without_binding_suffix_uses_xml_mapping(self):
        self.put("app/src/main/res/layout/custom_contact.xml", f'<layout {A}><data class="ContactCard"/><TextView android:text="contact"/></layout>')
        self.put("app/src/main/java/com/example/Main.kt", """package com.example
import androidx.appcompat.app.AppCompatActivity
class Main : BaseCarrier<ContactCard>() {}
abstract class BaseCarrier<T> : AppCompatActivity() {}
""")
        self.refresh()
        meta, visual, _, _ = self.page()
        self.assertEqual(meta["root_layout_candidates"], ["custom_contact"])
        self.assertEqual(visual["nodes"][0]["props"]["android:text"]["value"], "contact")

    def test_class_names_inside_strings_do_not_create_composition_edges(self):
        self.put("app/src/main/java/com/example/Tile.kt", """package com.example
import androidx.fragment.app.Fragment
class Tile : Fragment() {}
""")
        self.put("app/src/main/java/com/example/Main.kt", """package com.example
import androidx.appcompat.app.AppCompatActivity
class Main : AppCompatActivity() {
 override fun getLayoutResId() = R.layout.main
 val note = "Tile"
}""")
        self.refresh()
        _, visual, _, _ = self.page()
        self.assertFalse(any(c["class"] == "com.example.Tile" for c in visual["composition"]["children"]))


if __name__ == "__main__":
    unittest.main()
