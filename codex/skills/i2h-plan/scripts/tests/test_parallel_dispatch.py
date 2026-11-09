import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from parallel_dispatch import dependency_groups, dispatch_p1


class ParallelDispatchTests(unittest.TestCase):
    def test_dependency_groups_are_topological_and_stable(self):
        items = [
            {"feature_id": "F002", "depends_on": ["F001"]},
            {"feature_id": "F001", "depends_on": []},
            {"feature_id": "F003", "depends_on": ["base"]},
        ]
        groups = dependency_groups(items)
        self.assertEqual([[row["feature_id"] for row in group] for group in groups], [["F001", "F003"], ["F002"]])

    def test_failed_worker_isolated_and_checkpointed(self):
        attempts = {}

        def worker(item, temp_dir):
            attempts[item["feature_id"]] = attempts.get(item["feature_id"], 0) + 1
            if item["feature_id"] == "F002":
                raise ValueError("deepseek transient")
            return {"feature_id": item["feature_id"], "temp": str(temp_dir)}

        with tempfile.TemporaryDirectory() as directory:
            result = dispatch_p1(
                [{"feature_id": "F001", "depends_on": []}, {"feature_id": "F002", "depends_on": []}],
                worker,
                checkpoint_dir=Path(directory),
                max_workers=2,
                retries=1,
            )
            self.assertEqual(result["status"], "partial")
            self.assertEqual(result["completed"], 1)
            self.assertEqual(attempts["F002"], 2)
            self.assertTrue(any(row["status"] == "failed" for row in result["checkpoints"].values()))


if __name__ == "__main__":
    unittest.main()
