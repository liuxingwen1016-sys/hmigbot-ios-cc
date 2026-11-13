import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from capability_gate import evaluate


def write(root, path, text):
    file = root / path
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(text, encoding="utf-8")
    return file


def camera_fixture(root, *, live_source, live_target):
    write(root, "entry/src/main/module.json5", '{"module":{"requestPermissions":[{"name":"ohos.permission.CAMERA"}]}}')
    source_text = ("import VisionKit\nlet canScan = DataScannerViewController.isSupported\n" if live_source
                   else "let picker = UIImagePickerController()\n// DataScannerViewController is a different API\n")
    source = write(root, "source/Scanner.swift", source_text)
    scan = "entry/src/main/ets/pages/ScanView.ets"
    write(root, "spec/baseline/ui-delivery-approved.json", json.dumps({
        "schema_version": 2, "status": "approved", "source_project_root": str(source.parent), "units": [{
            "output": {"file": scan, "symbol": "ScanView"},
            "source_refs": [{"file": "Scanner.swift", "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}],
        }],
    }))
    write(root, scan, """
import { LiveScannerView } from './LiveScannerView';
export struct ScanView {
  start() { manager.requestPermissionsFromUser(ctx, permissions); new photoAccessHelper.PhotoViewPicker(); }
  build() { LiveScannerView() }
}
""")
    write(root, "entry/src/main/ets/services/OCRService.ets", "recognizeFrame() { textRecognition.recognizeText(info); }")
    scanner = "entry/src/main/ets/pages/LiveScannerView.ets"
    ocr_import = "import { OCRService } from '../services/OCRService';\n"
    if live_target:
        write(root, scanner, """
import { LiveCameraScanner } from '../services/LiveCameraScanner';
export struct LiveScannerView {
  build() { XComponent({ type: XComponentType.SURFACE }).onLoad(() => this.open()) }
  open() { new LiveCameraScanner(this.controller.getXComponentSurfaceId()) }
  aboutToDisappear() { this.scanner.close() }
}
""")
        write(root, "entry/src/main/ets/services/LiveCameraScanner.ets", ocr_import + """
function start() {
  const input = manager.createCameraInput(device);
  const receiver = image.createImageReceiver(size, format, 3);
  manager.createPreviewOutput(profile, screenSurface);
  manager.createPreviewOutput(profile, receiver.getReceivingSurfaceId());
  receiver.on('imageArrival', async () => OCRService.recognizeFrame(await receiver.readLatestImage()));
  session.start();
}
function close() { session.stop(); input.close(); receiver.release(); }
""")
    else:
        write(root, scanner, ocr_import + """
export struct LiveScannerView {
  build() { Button('拍照').onClick(() => this.pick()) }
  pick() { cameraPicker.pick(ctx, types, profile); OCRService.recognizeFrame(image); }
}
""")
    write(root, "entry/src/main/resources/base/media/sample_bean.png", "fixture")
    return source


def camera_finding(result):
    return next(item for item in result["findings"] if item["capability"] == "F101_CAMERA_OCR")


class CapabilityGateTests(unittest.TestCase):
    def test_all_capabilities_pass_from_realistic_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            camera_fixture(root, live_source=False, live_target=False)
            (root / "spec/baseline/ui-delivery-approved.json").unlink()  # Original CLI caller without an inventory.
            module = root / "entry/src/main/module.json5"
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
            write(root, "entry/src/main/ets/services/SystemServices.ets", "NotificationKit")
            write(root, "entry/src/main/ets/Form.ets", "source")
            write(root, "entry/src/main/ets/Live.ets", "source")
            profile = root / "entry/src/main/resources/base/profile"; profile.mkdir(parents=True)
            (profile / "form_config.json").write_text("{}")
            (profile / "shortcuts.json").write_text(json.dumps({"shortcuts": [{"shortcutId": "last_recipe"}]}))
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

    def test_live_source_requires_the_live_path_and_a_fresh_anchor(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            camera_fixture(root, live_source=True, live_target=False)
            f101 = camera_finding(evaluate(root))
            self.assertEqual(f101["status"], "BLOCKED")
            self.assertEqual(f101["checks"]["source_camera_mode"], "live_text")
            self.assertTrue(f101["checks"]["camera_picker_api"])
            source = camera_fixture(root, live_source=True, live_target=True)
            f101 = camera_finding(evaluate(root))
            self.assertEqual(f101["status"], "PASS")
            self.assertFalse(f101["checks"]["camera_picker_api"])
            self.assertTrue(f101["checks"]["live_camera_api"])
            self.assertFalse(f101["behavior_verified"])
            source.write_text("import SwiftUI\n", encoding="utf-8")
            f101 = camera_finding(evaluate(root))
            self.assertEqual(f101["status"], "BLOCKED")
            self.assertEqual(f101["code"], "SOURCE_CAMERA_EVIDENCE_INVALID")

    def test_live_camera_requires_mounted_preview_frame_ocr_and_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for file, token in (
                ("pages/ScanView.ets", "LiveScannerView()"),
                ("pages/LiveScannerView.ets", "XComponent("),
                ("services/LiveCameraScanner.ets", "receiver.readLatestImage()"),
                ("services/LiveCameraScanner.ets", "OCRService.recognizeFrame("),
                ("services/LiveCameraScanner.ets", "receiver.release()"),
            ):
                with self.subTest(file=file, token=token):
                    camera_fixture(root, live_source=True, live_target=True)
                    path = root / "entry/src/main/ets" / file
                    original = path.read_text(encoding="utf-8")
                    path.write_text(original.replace(token, "placeholder") + "\n// " + token + "\n", encoding="utf-8")
                    write(root, "entry/src/main/ets/Detached.ets", original)
                    self.assertEqual(camera_finding(evaluate(root))["status"], "BLOCKED")

    def test_packaged_command_keeps_still_and_live_modes_distinct(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for live_source, live_target, expected in ((False, False, "PASS"), (True, False, "BLOCKED"),
                                                        (True, True, "PASS")):
                with self.subTest(live_source=live_source, live_target=live_target):
                    camera_fixture(root, live_source=live_source, live_target=live_target)
                    output = root / "capability.json"
                    script = Path(__file__).resolve().parents[1] / "capability_gate.py"
                    result = subprocess.run([sys.executable, "-B", str(script), "--project-root", str(root),
                                             "--output-json", str(output)], capture_output=True, text=True,
                                            encoding="utf-8", timeout=20)
                    f101 = camera_finding(json.loads(output.read_text(encoding="utf-8")))
                    self.assertEqual(f101["status"], expected, result.stderr)
                    self.assertEqual(result.returncode, 0 if expected == "PASS" else 2)

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
