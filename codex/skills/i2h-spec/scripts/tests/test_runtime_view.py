import json
import tempfile
import unittest
from pathlib import Path

from runtime_view import normalize, parse_debug_description


DEBUG_DESCRIPTION = """Attributes: Application, 0x123, pid: 1, label: '萃刻'
Element subtree:
 →Application, 0x123, pid: 1, label: '萃刻'
    Window (Main), 0x124, {{0.0, 0.0}, {402.0, 874.0}}
      Button, 0x125, {{20.0, 66.0}, {36.0, 36.0}}, identifier: 'settings', label: '设置'
      StaticText, 0x126, {{24.0, 140.0}, {130.3, 13.3}}, label: 'BREW MOMENTS'
"""


class RuntimeViewTests(unittest.TestCase):
    def test_parse_debug_description_keeps_geometry_and_semantics(self):
        nodes = parse_debug_description(DEBUG_DESCRIPTION)
        self.assertEqual(len(nodes), 4)
        self.assertEqual(nodes[1]["role"], "Window (Main)")
        self.assertEqual(nodes[2]["identifier"], "settings")
        self.assertEqual(nodes[2]["label"], "设置")
        self.assertEqual(nodes[2]["frame"]["width"], 36.0)

    def test_normalize_uses_debug_description_when_nodes_are_absent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            capture = root / "capture.json"
            screenshot = root / "screen.png"
            ui_json = root / "ui.json"
            screenshot.write_bytes(b"png")
            ui_json.write_text("{}", encoding="utf-8")
            capture.write_text(json.dumps({
                "page_id": "page_0001_RootView",
                "state_id": "normal",
                "screenshot": "screen.png",
                "ui_json": "ui.json",
                "debug_description": DEBUG_DESCRIPTION,
            }), encoding="utf-8")
            result = normalize(capture)
            self.assertEqual(len(result["nodes"]), 4)
            self.assertEqual(result["warnings"], [])

    def test_normalize_preserves_foreground_receipt_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            capture = root / "capture.json"
            screenshot = root / "screen.png"
            ui_json = root / "ui.json"
            receipt = root / "foreground-receipt.json"
            screenshot.write_bytes(b"png")
            ui_json.write_text(json.dumps({"nodes": [{"id": "title", "role": "staticText"}]}), encoding="utf-8")
            receipt.write_text(json.dumps({"schema": "hmigbot-ios-foreground-receipt/1", "ready": True}), encoding="utf-8")
            capture.write_text(json.dumps({
                "page_id": "page_0001_RootView",
                "state_id": "normal",
                "screenshot": "screen.png",
                "ui_json": "ui.json",
                "foreground_receipt": "foreground-receipt.json",
                "nodes": [{"id": "title", "role": "staticText"}],
            }), encoding="utf-8")
            result = normalize(capture)
            self.assertIsNotNone(result["foreground_receipt_sha256"])
            self.assertEqual(result["warnings"], [])


if __name__ == "__main__":
    unittest.main()
