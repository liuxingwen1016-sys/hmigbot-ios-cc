import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "i2h-plan/scripts"))
from source_index import build_index, slice_index
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

        evidence = self.root / "spec/.i2h/resources-inventory.json"
        payload = run(str(self.root), str(evidence), source_index_output=str(self.root / "spec/.i2h/cache/source-index.json"), source_index_force=True)
        inventory = ui_delivery.draft(self.root, self.root / "delivery.json")
        units = {unit["component"]: unit for unit in inventory["units"]}
        self.assertEqual(units["ios.BeanLibraryView"]["source_obligations"], pages["BeanLibraryView"]["ui_obligations"])
        self.assertEqual(units["ios.BeanDetailView"]["source_obligations"], pages["BeanDetailView"]["ui_obligations"])
        self.assertEqual(units["ios.BeanEditorView"]["source_obligations"], pages["BeanEditorView"]["ui_obligations"])


if __name__ == "__main__":
    unittest.main()
