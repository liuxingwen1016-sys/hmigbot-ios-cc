import tempfile
import unittest
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

import immersive_safearea_gate as gate


class ImmersiveSafeareaGateTests(unittest.TestCase):
    def test_not_required_without_source_requirement(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = gate.evaluate(Path(tmp), {"units": []})
            self.assertEqual(result["status"], "NOT_REQUIRED")

    def test_checker_output_requires_all_three_layers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            checker = root / "checker.sh"
            checker.write_text(
                "#!/bin/sh\n"
                "echo '✅ L1 [EntryAbility]: 含 setWindowLayoutFullScreen'\n"
                "echo '✅ L2 [根 Navigation]: 全工程 1 个文件含 expandSafeArea'\n"
                "echo '✅ L3 [pages/Home.ets]: 全屏页含安全区响应'\n",
                encoding="utf-8",
            )
            checker.chmod(0o755)
            result = gate.evaluate(root, {"units": [{"unit_id": "home", "needs_immersive_safearea": True}]}, checker)
            self.assertEqual(result["status"], "PASS", result)
            self.assertTrue(all(result["layers"][layer]["ok"] for layer in ("L1", "L2", "L3")))

    def test_checker_failure_is_blocking(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            checker = root / "checker.sh"
            checker.write_text("#!/bin/sh\necho '❌ L2 [根 Navigation]: 缺 expandSafeArea'\nexit 1\n", encoding="utf-8")
            checker.chmod(0o755)
            result = gate.evaluate(root, {"units": [{"unit_id": "home", "needs_immersive_safearea": True}]}, checker)
            self.assertEqual(result["status"], "FAIL")
            self.assertIn("CHECKER_FAILED", {item["code"] for item in result["errors"]})


if __name__ == "__main__":
    unittest.main()
