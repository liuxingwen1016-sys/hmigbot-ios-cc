import sys
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT))
from visual_rubric import evaluate


class VisualRubricTests(unittest.TestCase):
    def test_bound_platform_difference_does_not_reduce_score(self):
        result = evaluate({"differences": [{
            "id": "UI-D0001",
            "category": "design_difference",
            "severity": "high",
            "reason": "system_material_blur",
            "evidence": {
                "source_manifest_sha256": "s",
                "target_manifest_sha256": "t",
                "source_screenshot_sha256": "ss",
                "target_screenshot_sha256": "ts",
            },
        }]})
        self.assertEqual(result["visual_score"], 1.0)
        self.assertTrue(result["visual_pass"])
        self.assertTrue(result["functional_pass"])

    def test_missing_evidence_is_unknown(self):
        result = evaluate({"differences": [{"category": "design_difference", "severity": "medium", "reason": "font_rasterization"}]})
        self.assertIsNone(result["visual_score"])
        self.assertFalse(result["visual_pass"])
        self.assertTrue(result["unknown_evidence"])

    def test_functional_difference_cannot_be_waived(self):
        result = evaluate({"differences": [{"category": "control_missing", "severity": "low"}]})
        self.assertFalse(result["functional_pass"])
        self.assertEqual(result["functional_differences"][0]["disposition"], "needs_fix")


if __name__ == "__main__":
    unittest.main()
