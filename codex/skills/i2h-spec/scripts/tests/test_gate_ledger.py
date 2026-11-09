import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gate_ledger import check, resolve, load_registry


class GateLedgerTests(unittest.TestCase):
    def test_classification_and_release_focus(self):
        self.assertEqual(resolve(load_registry(), "C4_BUILDER_NOT_FOUND")["gate"], "closure.wiring")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "spec").mkdir()
            (root / "spec/decision-ledger.md").write_text(
                "### D-010 wiring gap\n"
                "- **类型**：工具缺口\n"
                "- **门禁**：closure.wiring / C4_BUILDER_NOT_FOUND\n"
                "- **工具输出**：`spec/out/wiring.json`\n",
                encoding="utf-8",
            )
            rc, result = check(root)
            self.assertEqual(rc, 0)
            self.assertEqual(result["focus"][0]["decision"], "D-010")
            focus = json.loads((root / "spec/gate-release/verify-focus.json").read_text())
            self.assertEqual(focus["status"], "PASS")

    def test_exact_rule_without_repair_round_is_blocked(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "spec").mkdir()
            (root / "spec/decision-ledger.md").write_text(
                "### D-011 exact\n"
                "- **类型**：工具缺口\n"
                "- **门禁**：plan.coverage / PLAN.REQUIREMENT_UNOWNED\n"
                "- **工具输出**：`spec/out/plan.json`\n",
                encoding="utf-8",
            )
            rc, result = check(root)
            self.assertEqual(rc, 1)
            self.assertIn("精确类", result["errors"][0])


if __name__ == "__main__":
    unittest.main()
