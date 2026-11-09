import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from resource_delta import init_scope, merge, submit_delta


class ResourceDeltaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "entry/src/main/resources/base/element").mkdir(parents=True)
        (self.root / "entry/src/main/resources/base/element/string.json").write_text('{"old": "value"}\n', encoding="utf-8")

    def test_task_owned_delta_merges_atomically_with_preimage(self):
        init_scope(self.root, "scope-1", [{"task_id": "task-a"}], [{"path": "entry/src/main/resources/base/element/string.json", "type": "string"}])
        submit_delta(self.root, "scope-1", "task-a", {"task_id": "task-a", "resources": [{"path": "entry/src/main/resources/base/element/string.json", "value": {"new": "value"}}]})
        result = merge(self.root, "scope-1")
        self.assertEqual(result["status"], "merged")
        self.assertEqual(json.loads((self.root / "entry/src/main/resources/base/element/string.json").read_text()), {"new": "value"})

    def test_changed_preimage_rejects_merge(self):
        init_scope(self.root, "scope-2", [{"task_id": "task-a"}], [{"path": "entry/src/main/resources/base/element/string.json"}])
        submit_delta(self.root, "scope-2", "task-a", {"task_id": "task-a", "resources": [{"path": "entry/src/main/resources/base/element/string.json", "value": {"new": "value"}}]})
        (self.root / "entry/src/main/resources/base/element/string.json").write_text('{"other": true}\n')
        with self.assertRaisesRegex(ValueError, "preimage"):
            merge(self.root, "scope-2")

    def test_duplicate_writer_and_path_escape_are_rejected(self):
        init_scope(self.root, "scope-3", [{"task_id": "task-a"}, {"task_id": "task-b"}], [{"path": "entry/src/main/resources/base/element/string.json"}])
        submit_delta(self.root, "scope-3", "task-a", {"task_id": "task-a", "resources": [{"path": "entry/src/main/resources/base/element/string.json", "value": {"a": 1}}]})
        submit_delta(self.root, "scope-3", "task-b", {"task_id": "task-b", "resources": [{"path": "entry/src/main/resources/base/element/string.json", "value": {"b": 1}}]})
        with self.assertRaisesRegex(ValueError, "multiple task writers"):
            merge(self.root, "scope-3")
        with self.assertRaisesRegex(ValueError, "unsafe"):
            submit_delta(self.root, "scope-3", "task-a", {"task_id": "task-a", "resources": [{"path": "../escape.json", "value": {}}]})

    def test_symlinked_resource_path_is_rejected(self):
        outside = self.root / "outside.json"
        outside.write_text("{}\n")
        link = self.root / "entry/src/main/resources/base/element/link.json"
        try:
            link.symlink_to(outside)
        except OSError:
            self.skipTest("symlinks unavailable")
        with self.assertRaisesRegex(ValueError, "symlink"):
            init_scope(self.root, "scope-link", [{"task_id": "task-a"}], [{"path": "entry/src/main/resources/base/element/link.json"}])


if __name__ == "__main__":
    unittest.main()
