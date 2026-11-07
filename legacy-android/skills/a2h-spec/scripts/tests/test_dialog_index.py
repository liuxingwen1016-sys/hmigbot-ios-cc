import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import dialog_index as idx  # noqa: E402


def manifest(row: str = "") -> str:
    return """# UI Manifest
dialog_index_schema: 1
## 弹窗 / 面板索引
| dialog key | row kind | source FQN | call site | hosts | usage / presentation | snapshot ref | body spec location | instance spec location | closure |
|---|---|---|---|---|---|---|---|---|---|
""" + row


class DialogIndexTest(unittest.TestCase):
    def test_fixed_header_and_row(self):
        row = "| `dlg_a` | named | `com.X` | `X.java:1` | `com.Host` | sheet | none | `spec/ui.md#x` | `spec/ui.md#i` | host_inline |\n"
        got = idx.parse_dialog_index(manifest(row))
        self.assertEqual(got["rows"][0]["source_fqn"], "com.X")
        self.assertEqual(got["rows"][0]["hosts"], ["com.Host"])

    def test_missing_schema_fails_by_default(self):
        with self.assertRaises(ValueError):
            idx.parse_dialog_index("## 弹窗 / 面板索引\n")

    def test_legacy_is_explicit(self):
        got = idx.parse_dialog_index("# old\n", allow_legacy=True)
        self.assertTrue(got["legacy"])

    def test_inline_row_kind_is_forbidden(self):
        row = "| a | inline | X | x:1 | H | dialog | none | x#b | x#i | host_inline |\n"
        with self.assertRaises(ValueError):
            idx.parse_dialog_index(manifest(row))

    def test_duplicate_key_fails(self):
        row = "| a | named | X | x:1 | H | dialog | none | x#b | x#i | host_inline |\n"
        with self.assertRaises(ValueError):
            idx.parse_dialog_index(manifest(row + row))

    def test_skeleton_chooses_one_owner_for_shared_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snap = root / "spec/baseline/ui-snapshots/page_0001_Host"
            ui = root / "spec/baseline/ui"
            snap.mkdir(parents=True)
            ui.mkdir(parents=True)
            (snap / "meta.json").write_text(json.dumps({"activity": "com.Host"}))
            (ui / "page_0001_Host.md").write_text("# Host")
            inv = {"candidates": [
                {"dialog_id": "dlg_a", "source_fqn": "com.A", "reachable": True,
                 "abstract": False, "host_fqns": ["com.Host"],
                 "usage_edges": [{"source_file": "A.java", "line": 1,
                                    "host_fqns": ["com.Host"]}],
                 "snapshot_ref": "spec/baseline/dialog-snapshots/shared",
                 "layout_owner_fqn": "com.Base", "suggested_page_type": "dialog"},
                {"dialog_id": "dlg_b", "source_fqn": "com.B", "reachable": True,
                 "abstract": False, "host_fqns": ["com.Host"],
                 "usage_edges": [{"source_file": "B.java", "line": 2,
                                    "host_fqns": ["com.Host"]}],
                 "snapshot_ref": "spec/baseline/dialog-snapshots/shared",
                 "layout_owner_fqn": "com.Base", "suggested_page_type": "dialog"},
            ], "anonymous_instantiations": []}
            text = idx.build_skeleton(inv, str(root))
            parsed = idx.parse_dialog_index(text)
            self.assertEqual(len(parsed["rows"]), 2)
            self.assertEqual(len({r["body_spec_location"] for r in parsed["rows"]}), 1)
            self.assertIn("page_0001_Host.md#dialog-body", parsed["rows"][0]["body_spec_location"])

    def test_owned_by_is_derived_from_body_file(self):
        row_a = "| a | named | A | A.java:1 | H | dialog | snap/a | spec/baseline/ui/page_1.md#a | spec/baseline/ui/page_1.md#i | host_inline |\n"
        row_b = "| b | named | B | B.java:1 | H | dialog | snap/b | spec/baseline/ui/page_2.md#b | spec/baseline/ui/page_1.md#i | shared_host_body |\n"
        parsed = idx.parse_dialog_index(manifest(row_a + row_b))
        got = idx.owned_by(
            parsed, "spec/baseline/ui/page_1.md", "/tmp/project",
            {"candidates": [{"source_fqn": "A", "layout_owner_fqn": "BaseA"}]})
        self.assertEqual([r["dialog_key"] for r in got["rows"]], ["a"])
        self.assertEqual(got["owned_dialog_snapshots"][0]["snapshot_ref"], "snap/a")
        self.assertEqual(got["owned_dialog_snapshots"][0]["layout_owner_fqn"], "BaseA")

    def test_skeleton_lists_every_mapped_consumer_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for number, source in ((1, "com.HostA"), (2, "com.HostB")):
                page_id = f"page_{number:04d}_Host"
                snap = root / "spec/baseline/ui-snapshots" / page_id
                ui = root / "spec/baseline/ui"
                snap.mkdir(parents=True)
                ui.mkdir(parents=True, exist_ok=True)
                (snap / "meta.json").write_text(json.dumps({"activity": source}))
                (ui / f"{page_id}.md").write_text("# Host")
            inv = {"candidates": [{
                "dialog_id": "dlg_shared", "source_fqn": "com.Shared", "required": True,
                "host_fqns": ["com.HostA", "com.HostB"],
                "usage_edges": [{"source_file": "A.java", "line": 1,
                                   "host_fqns": ["com.HostA", "com.HostB"]}],
                "snapshot_ref": "none", "layout_owner_fqn": None,
                "suggested_page_type": "dialog",
            }], "anonymous_instantiations": []}
            parsed = idx.parse_dialog_index(idx.build_skeleton(inv, str(root)))
            refs = parsed["rows"][0]["instance_spec_locations"]
            self.assertEqual(len(refs), 2)
            self.assertTrue(any("page_0001_Host.md" in ref for ref in refs))
            self.assertTrue(any("page_0002_Host.md" in ref for ref in refs))


if __name__ == "__main__":
    unittest.main()
