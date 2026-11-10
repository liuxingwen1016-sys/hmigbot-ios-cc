import json
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from capability_gate import evaluate


class CapabilityGateTests(unittest.TestCase):
    def test_all_capabilities_pass_from_realistic_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            module = root / "entry/src/main/module.json5"
            module.parent.mkdir(parents=True)
            module.write_text('''{
              "module": {
                "requestPermissions": [{"name":"ohos.permission.CAMERA"}],
                "abilities": [{"name":"EntryAbility","metadata":[{"name":"ohos.ability.shortcuts","resource":"$profile:shortcuts"}]}],
                "extensionAbilities": [
                  {"name":"Form","type":"form","srcEntry":"./ets/Form.ets","metadata":[{"name":"ohos.extension.form","resource":"$profile:form_config"}]},
                  {"name":"Live","type":"liveForm","srcEntry":"./ets/Live.ets"}
                ]
              }
            }''')
            for rel in ("entry/src/main/ets/pages/LiveScannerView.ets", "entry/src/main/ets/pages/ScanView.ets", "entry/src/main/ets/services/OCRService.ets", "entry/src/main/ets/services/SystemServices.ets", "entry/src/main/ets/Form.ets", "entry/src/main/ets/Live.ets"):
                path = root / rel; path.parent.mkdir(parents=True, exist_ok=True)
                text = "NotificationKit" if "SystemServices" in rel else "source"
                if rel.endswith("ScanView.ets"):
                    text = "cameraPicker PhotoViewPicker abilityAccessCtrl recognizeText"
                path.write_text(text)
            profile = root / "entry/src/main/resources/base/profile"; profile.mkdir(parents=True)
            (profile / "form_config.json").write_text("{}")
            (profile / "shortcuts.json").write_text(json.dumps({"shortcuts": [{"shortcutId": "last_recipe"}]}))
            media = root / "entry/src/main/resources/base/media"
            media.mkdir(parents=True)
            (media / "sample_bean.png").write_bytes(b"png")
            result = evaluate(root)
            self.assertEqual(result["status"], "PASS")
            self.assertTrue(all(item["status"] == "PASS" for item in result["findings"]))

    def test_placeholder_ocr_surface_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            module = root / "entry/src/main/module.json5"
            module.parent.mkdir(parents=True)
            module.write_text('{"module":{"requestPermissions":[{"name":"ohos.permission.CAMERA"}]}}')
            for rel in ("entry/src/main/ets/pages/LiveScannerView.ets", "entry/src/main/ets/services/OCRService.ets"):
                path = root / rel; path.parent.mkdir(parents=True, exist_ok=True); path.write_text("sampleText()")
            result = evaluate(root)
            f101 = next(item for item in result["findings"] if item["capability"] == "F101_CAMERA_OCR")
            self.assertEqual(f101["status"], "BLOCKED")
            self.assertFalse(f101["checks"]["camera_picker_api"])
            self.assertFalse(f101["checks"]["fixture_free"])

    def test_shortcut_without_metadata_is_partial(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); module = root / "entry/src/main/module.json5"; module.parent.mkdir(parents=True)
            module.write_text('{"module":{"abilities":[{"name":"EntryAbility"}]}}')
            profile = root / "entry/src/main/resources/base/profile"; profile.mkdir(parents=True)
            (profile / "shortcuts.json").write_text('{"shortcuts":[{"shortcutId":"x"}]}')
            result = evaluate(root)
            shortcut = next(item for item in result["findings"] if item["capability"] == "F104_SHORTCUT")
            self.assertEqual(shortcut["status"], "PARTIAL")


if __name__ == "__main__":
    unittest.main()
