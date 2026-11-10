import json
import tempfile
import unittest
from pathlib import Path

import sys

SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

from ios_runtime_capture import write_foreground_ack  # noqa: E402


class ForegroundHandshakeTests(unittest.TestCase):
    def test_ack_binds_screenshot_and_page_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            screenshot = root / "ios-runtime.png"
            ack = root / "foreground-capture-ack.json"
            screenshot.write_bytes(b"png")
            payload = write_foreground_ack(
                ack,
                bundle_id="com.example.cuike",
                page_id="page_0001_RootView",
                state_id="normal",
                screenshot=screenshot,
            )
            saved = json.loads(ack.read_text(encoding="utf-8"))
            self.assertEqual(saved, payload)
            self.assertEqual(saved["schema"], "hmigbot-ios-foreground-ack/1")
            self.assertEqual(saved["bundle_id"], "com.example.cuike")
            self.assertEqual(len(saved["screenshot_sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
