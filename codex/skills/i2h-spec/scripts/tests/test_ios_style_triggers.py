import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT))
from ios_style_triggers import detect


class IOSStyleTriggerTests(unittest.TestCase):
    def test_only_source_patterns_trigger_styles(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Home.swift").write_text(
                'struct Home: View { var body: some View { TabView(selection: $tab) { Text("x") }.searchable(text: $q).sheet(isPresented: $show) { Text("s") } } }',
                encoding="utf-8",
            )
            result = detect(root)
        ids = {item["trigger_id"] for item in result["triggers"]}
        self.assertEqual(ids, {"floating_tabbar", "search_presentation", "detent_sheet"})
        self.assertIn("glass_morph", result["untriggered_styles"])

    def test_trigger_contains_source_hash_and_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Recipe.swift"
            source.write_text("struct Recipe: View { var body: some View { Slider(value: $ratio) } }\n", encoding="utf-8")
            result = detect(root)
        row = next(item for item in result["triggers"] if item["trigger_id"] == "glass_slider")
        self.assertEqual(row["source_anchor"]["path"], "Recipe.swift")
        self.assertTrue(row["source_anchor"]["sha256"])
        self.assertTrue(row["fallback"])


if __name__ == "__main__":
    unittest.main()
