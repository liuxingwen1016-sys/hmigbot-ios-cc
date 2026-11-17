import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "i2h-plan/scripts"))
from source_index import build_index, slice_index, swift_system_symbol_facts
from ui_evidence import run
import ui_delivery


class SourceIndexTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "Views/HomeView.swift").parent.mkdir(parents=True)
        (self.root / "Views/HomeView.swift").write_text(
            "import SwiftUI\n"
            "struct HomeView: View {\n"
            "  @State private var count: Int = 0\n"
            "  var body: some View { NavigationLink(destination: DetailView()) { Text(\"Home\") } }\n"
            "  func refresh() { count += 1 }\n"
            "}\n"
            "struct HistoryRow: View { var body: some View { Text(\"Row\") } }\n"
            "struct DetailView: View { var body: some View { Text(\"Detail\") } }\n",
            encoding="utf-8",
        )
        (self.root / "Core/Domain.swift").parent.mkdir(parents=True)
        (self.root / "Core/Domain.swift").write_text("struct BrewSession { let id: String }\n", encoding="utf-8")
        (self.root / "Components/Card.swift").parent.mkdir(parents=True)
        (self.root / "Components/Card.swift").write_text(
            "import SwiftUI\nstruct Card: View { var body: some View { Text(\"Card\") } }\n",
            encoding="utf-8",
        )

    def test_symbol_facts_preserve_variant_and_distinct_icon_and_frame_sizes(self):
        rows = swift_system_symbol_facts("""
            // Image(systemName: "ignored")
            Image(systemName: values.rating >= rating ? "star.fill" : "star")
                .font(.system(size: 28, weight: .semibold))
                .foregroundStyle(Palette.accent)
                .frame(minWidth: 44, minHeight: 44)
            Label("豆档案", systemImage: "square.stack.3d.up")
            UIImage(systemName: "plus", withConfiguration: config)
            Image(systemName: "timer").font(.system(size: size + 1))
        """)
        self.assertEqual([row["name"] for row in rows],
                         ["star.fill", "star", "square.stack.3d.up", "plus", "timer"])
        for row, selected in zip(rows[:2], (True, False)):
            self.assertEqual(row["condition"], "values.rating >= rating")
            self.assertEqual(row["when"], selected)
            self.assertEqual(row["symbol_font_pt"], 28)
            self.assertEqual(row["frame_pt"], {"minWidth": 44, "minHeight": 44})
            self.assertEqual(row["foreground_expression"], "Palette.accent")
        self.assertNotIn("symbol_font_pt", rows[-1])

    def test_shared_primary_button_facts_track_default_override_and_definition(self):
        definition = self.root / "Components/PrimaryButton.swift"
        definition.write_text('''import SwiftUI
struct PrimaryButton: View {
    var symbol: String = "arrow.right"
    var body: some View { Image(systemName: symbol) }
}
''', encoding="utf-8")
        (self.root / "Views/HomeView.swift").write_text('''import SwiftUI
struct HomeView: View {
    var body: some View {
        PrimaryButton(title: "Continue") {}
        PrimaryButton(title: "Start", symbol: "play.fill") {}
        PrimaryButton(title: "Scan", symbol: "viewfinder") {}
        // PrimaryButton(title: "Comment") {}
        PrimaryButton(title: "Dynamic", symbol: settings.icon) {}
    }
}
''', encoding="utf-8")
        target = self.root / "target"
        output = target / "spec/.i2h/resources-inventory.json"
        evidence = run(str(self.root), str(output))
        view = next(row for row in evidence["pages"] if row["view_name"] == "HomeView")
        facts = view["ui_obligations"]["system_symbol_fidelity"]
        self.assertEqual([(row["label"], row["origin"], row.get("target_symbol")) for row in facts], [
            ("Continue", "component_default", "arrow_right"),
            ("Start", "explicit", "play_fill"),
            ("Scan", "explicit", None),
        ])
        self.assertEqual(facts[0]["line"], 4)
        draft = ui_delivery.draft(target, target / "draft.json")
        unit = next(row for row in draft["units"] if row["component"] == "ios.HomeView")
        self.assertEqual(unit["output"]["symbol"], "HomeView")
        anchor = next(ref for ref in unit["source_refs"] if ref["file"] == "Components/PrimaryButton.swift")
        self.assertEqual(anchor["line"], 3)
        self.assertEqual(anchor["sha256"], hashlib.sha256(definition.read_bytes()).hexdigest())
        self.assertEqual(unit["source_obligations"]["system_symbol_fidelity"], facts)

    def test_literal_label_symbols_reach_the_delivery_manifest(self):
        (self.root / "Views/HomeView.swift").write_text('''import SwiftUI
struct HomeView: View {
    var body: some View {
        PhotosPicker(selection: $photo) {
            Label("Open album", systemImage: "photo")
        }
        Label("Share", systemImage: "square.and.arrow.up")
        Text("Home").tabItem { Label("Tab", systemImage: "photo") }
        Label(title, systemImage: "photo")
    }
}
''', encoding="utf-8")
        target = self.root / "target"
        run(str(self.root), str(target / "spec/.i2h/resources-inventory.json"))
        draft = ui_delivery.draft(target, target / "draft.json")
        unit = next(row for row in draft["units"] if row["component"] == "ios.HomeView")
        self.assertEqual(unit["source_obligations"]["system_symbol_fidelity"], [
            {"role": "label", "line": 5, "label": "Open album", "source_symbol": "photo", "target_symbol": "picture"},
            {"role": "label", "line": 7, "label": "Share", "source_symbol": "square.and.arrow.up"},
        ])

    def test_share_link_payload_and_literal_label_survive_delivery_draft(self):
        (self.root / "Views/HomeView.swift").write_text('''import SwiftUI
struct HomeView: View {
    var body: some View {
        ShareLink(item: shareText(row)) { Label("Share this", systemImage: "square.and.arrow.up") }
        SwiftUI.ShareLink(items: urls)
        // ShareLink(item: hidden)
        Text("ShareLink(item: fake)")
    }
}
''', encoding="utf-8")
        target = self.root / "target"
        run(str(self.root), str(target / "spec/.i2h/resources-inventory.json"))
        draft = ui_delivery.draft(target, target / "draft.json")
        unit = next(row for row in draft["units"] if row["component"] == "ios.HomeView")
        self.assertEqual(unit["source_obligations"]["share_link_calls"], [
            {"line": 4, "payload_argument": "item", "label": "Share this"},
            {"line": 5, "payload_argument": "items"},
        ])

    def test_date_display_options_survive_index_and_delivery_draft(self):
        (self.root / "Views/HomeView.swift").write_text('''import SwiftUI
struct HomeView: View {
    var body: some View {
        Text(item.session.startedAt.formatted(date: .long, time: .shortened))
        SectionHeading(title: "Recent", subtitle: latest.startedAt.formatted(date: .abbreviated,
            time: .omitted))
        // Text(comment.startedAt.formatted(date: .long, time: .shortened))
        Text("Text(example.formatted(date: .long, time: .shortened))")
        Text(target.formatted(date: selectedStyle, time: .shortened))
        consume(irrelevant.formatted(date: .long, time: .shortened))
    }
}
''', encoding="utf-8")
        target = self.root / "target"
        run(str(self.root), str(target / "spec/.i2h/resources-inventory.json"))
        draft = ui_delivery.draft(target, target / "draft.json")
        unit = next(row for row in draft["units"] if row["component"] == "ios.HomeView")
        self.assertEqual(unit["source_obligations"]["date_format_calls"], [
            {"line": 4, "value_path": "item.session.startedAt", "slot": "text",
             "date_style": "long", "time_style": "shortened"},
            {"line": 5, "value_path": "latest.startedAt", "slot": "subtitle",
             "date_style": "abbreviated", "time_style": "omitted"},
        ])

    def test_shared_drawing_links_each_call_and_freezes_definition_once_per_page(self):
        definition = self.root / "Components/Card.swift"
        definition.write_text('''import SwiftUI
struct Card: View {
    var body: some View { BadgeShape().fill(.red) }
}
private struct BadgeShape: Shape {
    func path(in rect: CGRect) -> Path { Path(rect) }
}
''', encoding="utf-8")
        (self.root / "Views/HomeView.swift").write_text('''import SwiftUI
struct HomeView: View {
    var body: some View {
        Card(tint: resolve("a(b)")).frame(width: 30, height: 50)
        Card().frame(width: layout.width, height: 10).frame(width: 90, height: 90)
        // Card().frame(width: 9, height: 9)
        Text("Card()")
    }
}
struct DetailView: View { var body: some View { Card().frame(width: 70, height: 90) } }
''', encoding="utf-8")
        target = self.root / "out"
        evidence = run(str(self.root), str(target / "spec/.i2h/resources-inventory.json"))
        pages = {v["view_name"]: v for v in evidence["pages"]}
        home = pages["HomeView"]["ui_obligations"]["drawing_component_calls"]
        detail = pages["DetailView"]["ui_obligations"]["drawing_component_calls"]
        self.assertEqual([call["line"] for call in home], [4, 5])
        self.assertEqual(home[0]["arguments"], 'tint: resolve("a(b)")')
        self.assertEqual(home[0]["frame_pt"], {"width": 30, "height": 50})
        self.assertNotIn("frame_pt", home[1])
        self.assertEqual(detail[0]["frame_pt"], {"width": 70, "height": 90})
        self.assertEqual(detail[0]["definition"], home[0]["definition"])
        self.assertEqual(home[0]["shape_definitions"], [
            {"name": "BadgeShape", "file": "Components/Card.swift", "line": 5}])
        draft = ui_delivery.draft(target, target / "draft.json")
        units = draft["units"]
        for unit in units:
            refs = [ref for ref in unit["source_refs"] if ref["file"] == "Components/Card.swift"]
            self.assertEqual(len(refs), 1)
            self.assertEqual(refs[0]["sha256"], hashlib.sha256(definition.read_bytes()).hexdigest())
            self.assertEqual(unit["source_obligations"]["drawing_component_calls"],
                             pages[unit["output"]["symbol"]]["ui_obligations"]["drawing_component_calls"])
        check = ui_delivery.validate(target, draft)["validation"]
        self.assertEqual(check["errors"], [])
        self.assertEqual(check["warnings"], [{
            "code": "SHARED_DRAWING_BINDING_UNSPECIFIED", "definition": home[0]["definition"],
            "unit_ids": sorted(unit["unit_id"] for unit in units),
        }])
        binding = {"definition": home[0]["definition"],
                   "output": {"file": "entry/src/main/ets/components/CardArt.ets", "symbol": "CardArt"}}
        draft["drawing_component_bindings"] = [binding]
        self.assertEqual(ui_delivery.validate(target, draft)["validation"], {"errors": [], "warnings": []})
        draft["drawing_component_bindings"].extend([
            binding, {**binding, "definition": {"file": "Components/Card.swift", "line": 999}},
        ])
        errors = ui_delivery.validate(target, draft)["validation"]["errors"]
        self.assertEqual([(row["code"], row["index"]) for row in errors],
                         [("DRAWING_BINDING_INVALID", 1), ("DRAWING_BINDING_INVALID", 2)])

        (self.root / "Core/Alternate.swift").write_text("struct Card: View { var body: some View { Canvas {} } }\n")
        refreshed = build_index(self.root, target / "new-index.json")
        self.assertTrue(all("drawing_component_calls" not in page["ui_obligations"] for page in refreshed["pages"]))

    def test_index_contains_full_source_surface_and_cache_hit(self):
        output = self.root / "spec/.i2h/cache/source-index.json"
        first = build_index(self.root, output)
        second = build_index(self.root, output)
        self.assertFalse(first["cache_hit"])
        self.assertTrue(second["cache_hit"])
        self.assertEqual(first["cache_key"], second["cache_key"])
        self.assertTrue(json.loads(output.read_text(encoding="utf-8"))["cache_hit"])
        self.assertEqual(first["summary"]["swift_file_count"], 3)
        home = next(row for row in first["swift_files"] if row["path"].endswith("HomeView.swift"))
        self.assertEqual(home["properties"][0]["wrapper"], "@State")
        self.assertEqual(home["methods"][0]["name"], "refresh")
        self.assertTrue(home["routes"])
        self.assertEqual(len(first["pages"]), 2)
        self.assertEqual(len(first["components"]), 2)
        self.assertEqual({row["view_name"] for row in first["components"]}, {"Card", "HistoryRow"})

    def test_ui_evidence_writes_index_metadata_and_page_slice(self):
        evidence = self.root / "spec/.i2h/resources-inventory.json"
        payload = run(str(self.root), str(evidence))
        index_path = self.root / "spec/.i2h/cache/source-index.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        metadata = payload["resources"]["source_index"]
        self.assertEqual(metadata["cache_key"], index["cache_key"])
        sliced = slice_index(index, page_ids=[index["pages"][0]["page_id"]])
        self.assertEqual(len(sliced["pages"]), 1)
        self.assertEqual(len(sliced["swift_files"]), 1)

    def test_source_change_invalidates_checkpoint_key(self):
        output = self.root / "spec/.i2h/cache/source-index.json"
        first = build_index(self.root, output)
        (self.root / "Core/Domain.swift").write_text("struct BrewSession { let id: String; let name: String }\n", encoding="utf-8")
        second = build_index(self.root, output)
        self.assertNotEqual(first["cache_key"], second["cache_key"])
        self.assertFalse(second["cache_hit"])

    def test_old_tool_cache_is_invalidated_after_obligations_schema_change(self):
        output = self.root / "spec/.i2h/cache/source-index.json"
        current = build_index(self.root, output, force=True)
        source_hash = current["source_tree_sha256"]
        old_key = hashlib.sha256(
            f"{source_hash}\0i2h-source-index/1.1\0{current['template_sha256']}".encode("utf-8")
        ).hexdigest()
        output.write_text(json.dumps({"cache_key": old_key, "cache_hit": False}), encoding="utf-8")
        rebuilt = build_index(self.root, output)
        self.assertFalse(rebuilt["cache_hit"])
        self.assertTrue(all("ui_obligations" in page for page in rebuilt["pages"]))

    def test_page_and_delivery_obligations_are_scoped_for_same_file_views(self):
        source = self.root / "Views/BeanViews.swift"
        source.write_text(
            "import SwiftUI\n"
            "struct BeanLibraryView: View {\n"
            "  var body: some View { ScrollView { Button(\"添加档案\") {} } }\n"
            "}\n"
            "struct BeanDetailView: View {\n"
            "  var body: some View { Button(\"编辑\") {} }\n"
            "}\n"
            "struct BeanEditorView: View {\n"
            "  var body: some View { Form { Picker(\"处理法\", selection: .constant(0)) { Text(\"水洗\") } Button(\"保存档案\") {} } }\n"
            "}\n",
            encoding="utf-8",
        )
        index = build_index(self.root, self.root / "spec/.i2h/cache/source-index.json", force=True)
        pages = {row["view_name"]: row for row in index["pages"] if row["file_path"] == "Views/BeanViews.swift"}
        self.assertEqual([row["kind"] for row in pages["BeanLibraryView"]["ui_obligations"]["interactive_controls"]], ["button"])
        self.assertFalse(pages["BeanLibraryView"]["ui_obligations"]["has_form"])
        self.assertEqual([row["kind"] for row in pages["BeanDetailView"]["ui_obligations"]["interactive_controls"]], ["button"])
        self.assertTrue(pages["BeanEditorView"]["ui_obligations"]["has_form"])
        self.assertEqual([row["kind"] for row in pages["BeanEditorView"]["ui_obligations"]["interactive_controls"]], ["picker", "button"])
        self.assertTrue(pages["BeanEditorView"]["ui_obligations"]["compact_picker_rows_required"])
        self.assertEqual(pages["BeanEditorView"]["ui_obligations"]["form_picker_labels"], ["处理法"])

        evidence = self.root / "spec/.i2h/resources-inventory.json"
        payload = run(str(self.root), str(evidence), source_index_output=str(self.root / "spec/.i2h/cache/source-index.json"), source_index_force=True)
        inventory = ui_delivery.draft(self.root, self.root / "delivery.json")
        units = {unit["component"]: unit for unit in inventory["units"]}
        self.assertEqual(units["ios.BeanLibraryView"]["source_obligations"], pages["BeanLibraryView"]["ui_obligations"])
        self.assertEqual(units["ios.BeanDetailView"]["source_obligations"], pages["BeanDetailView"]["ui_obligations"])
        self.assertEqual(units["ios.BeanEditorView"]["source_obligations"], pages["BeanEditorView"]["ui_obligations"])

    def test_delivery_preserves_host_presentation_obligations_and_full_screen_mapping(self):
        source = self.root / "Views/PresentationViews.swift"
        source.write_text(
            "import SwiftUI\n"
            "struct HostView: View {\n"
            "  var body: some View { Text(\"Home\").sheet(isPresented: $showSheet) { SheetView() }.fullScreenCover(isPresented: $showFull) { FullView() } }\n"
            "}\n"
            "struct SheetView: View { var body: some View { Text(\"Sheet\") } }\n"
            "struct FullView: View { var body: some View { Text(\"Full\") } }\n",
            encoding="utf-8",
        )
        index = build_index(self.root, self.root / "spec/.i2h/cache/source-index.json", force=True)
        evidence = self.root / "spec/.i2h/resources-inventory.json"
        run(str(self.root), str(evidence), source_index_output=str(self.root / "spec/.i2h/cache/source-index.json"), source_index_force=True)
        inventory = ui_delivery.draft(self.root, self.root / "delivery.json")
        units = {unit["component"]: unit for unit in inventory["units"]}
        host = units["ios.HostView"]
        self.assertEqual({row["kind"] for row in host["source_obligations"]["presentations"]}, {"sheet", "full_screen_cover"})
        self.assertEqual({row["kind"] for row in host["presentation"]["source_obligations"]}, {"sheet", "full_screen_cover"})
        self.assertEqual(units["ios.SheetView"]["presentation"]["harmony_mapping"], "bindSheet")
        self.assertEqual(units["ios.FullView"]["presentation"]["source"], ".fullScreenCover")
        self.assertEqual(units["ios.FullView"]["presentation"]["harmony_mapping"], "bindContentCover")


if __name__ == "__main__":
    unittest.main()
