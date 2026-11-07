import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from layout_scale import derive, main


class LayoutScaleTests(unittest.TestCase):
    def test_derives_width_ratio_and_exclusions(self):
        result = derive(402, 365.7142857)
        self.assertAlmostEqual(result["layout_scale"], 0.9097370, places=5)
        self.assertEqual(result["scope"], "ios_fixed_geometry_only")
        self.assertIn("typography", result["excluded_from_scaling"])

    def test_reads_ios_accessibility_frame_and_binds_hash(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "ios-accessibility.json"
            source.write_text(json.dumps({"nodes": [{"frame": [0, 0, 402, 874]}]}))
            output = root / "layout-scale.json"
            self.assertEqual(main([
                "--ios-accessibility-json", str(source),
                "--target-logical-width-vp", "365.7142857",
                "--out", str(output),
            ]), 0)
            payload = json.loads(output.read_text())
            self.assertEqual(payload["source_reference_width_pt"], 402.0)
            self.assertEqual(payload["source_accessibility_json_sha256"], __import__("hashlib").sha256(source.read_bytes()).hexdigest())

    def test_rejects_non_positive_width(self):
        with self.assertRaises(ValueError):
            derive(0, 365)


if __name__ == "__main__":
    unittest.main()
