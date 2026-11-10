import json
import hashlib
from pathlib import Path
import tempfile
import unittest

from PIL import Image

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from compare_screenshots import ScreenshotComparator


class CompareScreenshotsTests(unittest.TestCase):
    def test_pixel_metrics_are_opt_in_and_do_not_change_default_result(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ios = root / "ios"
            harmony = root / "harmony"
            ios.mkdir()
            harmony.mkdir()
            Image.new("RGB", (20, 20), "white").save(ios / "RootView.png")
            Image.new("RGB", (20, 20), "black").save(harmony / "RootView.png")

            default = ScreenshotComparator(str(ios), str(harmony)).compare_all()
            self.assertNotIn("pixel_mae", default["comparisons"][0])

            detailed = ScreenshotComparator(str(ios), str(harmony), pixel_metrics=True).compare_all()
            comparison = detailed["comparisons"][0]
            self.assertGreater(comparison["pixel_mae"], 200)
            self.assertEqual(comparison["pixel_over_threshold_pct"], 100.0)

    def test_bound_content_region_keeps_full_screen_metric(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ios = root / "ios"
            harmony = root / "harmony"
            ios.mkdir()
            harmony.mkdir()
            source = Image.new("RGB", (20, 20), "white")
            target = Image.new("RGB", (20, 20), "white")
            source.save(ios / "Home.png")
            target.save(harmony / "Home.png")

            def sha(path):
                return hashlib.sha256(path.read_bytes()).hexdigest()

            manifest = root / "regions.json"
            manifest.write_text(json.dumps({
                "schema": "i2h-visual-regions/1",
                "pages": {
                    "Home": {
                        "source_content_rect": [0, 2, 20, 16],
                        "target_content_rect": [0, 2, 20, 16],
                        "evidence": {
                            "source_screenshot_sha256": sha(ios / "Home.png"),
                            "target_screenshot_sha256": sha(harmony / "Home.png"),
                        },
                    }
                },
            }), encoding="utf-8")

            result = ScreenshotComparator(
                str(ios), str(harmony), regions_manifest=str(manifest)
            ).compare_all()
            self.assertEqual(result["summary"]["avg_similarity"], 100.0)
            self.assertEqual(result["summary"]["content_avg_similarity"], 100.0)
            self.assertEqual(result["summary"]["content_gate"], "pass")
            self.assertTrue(result["comparisons"][0]["application_content"]["evidence_bound"])
            self.assertTrue(result["comparisons"][0]["application_content"]["system_chrome"]["excluded_from_content_metric"])

    def test_bound_content_region_rejects_stale_screenshot_hash(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ios = root / "ios"
            harmony = root / "harmony"
            ios.mkdir()
            harmony.mkdir()
            Image.new("RGB", (20, 20), "white").save(ios / "Home.png")
            Image.new("RGB", (20, 20), "white").save(harmony / "Home.png")
            manifest = root / "regions.json"
            manifest.write_text(json.dumps({
                "schema": "i2h-visual-regions/1",
                "pages": {
                    "Home": {
                        "source_content_rect": [0, 0, 20, 20],
                        "target_content_rect": [0, 0, 20, 20],
                        "evidence": {
                            "source_screenshot_sha256": "stale",
                            "target_screenshot_sha256": "stale",
                        },
                    }
                },
            }), encoding="utf-8")

            result = ScreenshotComparator(
                str(ios), str(harmony), regions_manifest=str(manifest)
            ).compare_all()
            self.assertEqual(result["summary"]["content_gate"], "fail")
            self.assertEqual(result["comparisons"][0]["application_content"]["status"], "error")
            self.assertFalse(result["comparisons"][0]["application_content"]["evidence_bound"])


if __name__ == "__main__":
    unittest.main()
