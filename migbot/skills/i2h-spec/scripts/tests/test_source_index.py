import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from source_index import build_index, slice_index
from ui_evidence import run


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
            "struct DetailView: View { var body: some View { Text(\"Detail\") } }\n",
            encoding="utf-8",
        )
        (self.root / "Core/Domain.swift").parent.mkdir(parents=True)
        (self.root / "Core/Domain.swift").write_text("struct BrewSession { let id: String }\n", encoding="utf-8")

    def test_index_contains_full_source_surface_and_cache_hit(self):
        output = self.root / "spec/.i2h/cache/source-index.json"
        first = build_index(self.root, output)
        second = build_index(self.root, output)
        self.assertFalse(first["cache_hit"])
        self.assertTrue(second["cache_hit"])
        self.assertEqual(first["cache_key"], second["cache_key"])
        self.assertTrue(json.loads(output.read_text(encoding="utf-8"))["cache_hit"])
        self.assertEqual(first["summary"]["swift_file_count"], 2)
        home = next(row for row in first["swift_files"] if row["path"].endswith("HomeView.swift"))
        self.assertEqual(home["properties"][0]["wrapper"], "@State")
        self.assertEqual(home["methods"][0]["name"], "refresh")
        self.assertTrue(home["routes"])
        self.assertEqual(len(first["pages"]), 2)

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


if __name__ == "__main__":
    unittest.main()
