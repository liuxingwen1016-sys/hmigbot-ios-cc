import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from source_oracle import source_digest, validate


class SourceOracleTests(unittest.TestCase):
    def test_selected_case_requires_expected_and_source_reference(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Home.swift"
            source.write_text("let value = 1\n", encoding="utf-8")
            payload = {
                "schema_version": 1,
                "source_sha256": source_digest(root),
                "cases": [{"case_id": "home", "selected": True, "source_refs": [{"path": "Home.swift", "line": 1, "quote": "let value = 1"}]}],
            }
            result = validate(payload, root)
            self.assertEqual(result["status"], "invalid")
            self.assertTrue(any("selected case needs expected" in error for error in result["errors"]))

    def test_unselected_unresolved_case_is_reported_without_failing(self):
        payload = {
            "schema_version": 1,
            "source_sha256": "source",
            "cases": [{"case_id": "settings", "selected": False, "status": "unresolved", "source_refs": [{"path": "Settings.swift", "line": 1}]}],
        }
        result = validate(payload)
        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["resolved_count"], 0)

    def test_changed_source_hash_is_rejected(self):
        payload = {"schema_version": 1, "source_sha256": "stale", "cases": [{"case_id": "home", "expected": {"title": "Home"}, "source_refs": [{"path": "Home.swift", "line": 1}]}]}
        result = validate(payload)
        self.assertEqual(result["status"], "valid")
        self.assertIsNone(result["source_match"])

    def test_generated_build_outputs_do_not_change_source_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "App.swift").write_text("let value = 1\n", encoding="utf-8")
            before = source_digest(root)
            (root / "build").mkdir()
            (root / "build/generated.swift").write_text("generated\n", encoding="utf-8")
            (root / ".build").mkdir()
            (root / ".build/generated.swift").write_text("generated\n", encoding="utf-8")
            self.assertEqual(source_digest(root), before)


if __name__ == "__main__":
    unittest.main()
