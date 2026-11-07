import json
import tempfile
import unittest
from pathlib import Path

from worker import convert_assets, convert_strings


class ResourceConverterTests(unittest.TestCase):
    def test_variants_and_duplicate_filenames_are_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            assets = root / "Assets.xcassets"
            for name in ("One.imageset", "Two.imageset"):
                (assets / name).mkdir(parents=True)
                (assets / name / "same.png").write_bytes(b"image")
                (assets / name / "Contents.json").write_text('{"images":[{"filename":"same.png"}]}')
            result = convert_assets(str(root), str(root / "out"))
            outputs = {item["output"] for item in result["images"]}
            self.assertEqual(len(outputs), 2)

    def test_dark_color_and_localized_strings_are_recorded(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            colors = root / "Assets.xcassets/Brand.colorset"
            colors.mkdir(parents=True)
            colors.joinpath("Contents.json").write_text(json.dumps({"colors": [
                {"color": {"components": {"red": "1.0", "green": "0", "blue": "0"}}},
                {"appearances": [{"appearance": "luminosity-dark", "value": "luminosity"}],
                 "color": {"components": {"red": "0", "green": "0", "blue": "0"}}},
            ]}))
            locale = root / "zh-Hans.lproj"
            locale.mkdir()
            locale.joinpath("Localizable.strings").write_text('"hello" = "你好";')
            out = root / "out"
            convert_assets(str(root), str(out))
            strings = convert_strings(str(root), str(out))
            color = json.loads((out / "base/element/color.json").read_text())["color"][0]["value"]
            self.assertEqual(color["dark"], "#000000")
            self.assertEqual(strings["localizations"]["zh-Hans"], ["hello"])


if __name__ == "__main__":
    unittest.main()
