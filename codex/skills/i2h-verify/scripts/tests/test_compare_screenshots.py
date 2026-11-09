import json
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


if __name__ == "__main__":
    unittest.main()
