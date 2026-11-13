import hashlib
import json
import tempfile
import unittest
from pathlib import Path
import sys

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

from lib.stage1_visual_scope import build_scope  # noqa: E402


class RuntimeCaptureScopeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.page_id = "page_0001_Home"
        self.state_id = "normal"
        self.capture_root = self.root / "external-capture"
        self.output_dir = self.capture_root / self.page_id / "states" / self.state_id
        self.output_dir.mkdir(parents=True)
        self.wiring_dir = self.root / "spec/execution/wiring"
        self.wiring_dir.mkdir(parents=True)
        (self.wiring_dir / "home.json").write_text(json.dumps({
            "schema_version": 1,
            "unit_id": "home",
            "status": "preview_prepared",
            "pages": [{
                "page_id": self.page_id,
                "state_id": self.state_id,
                "output_file": "entry/src/main/ets/pages/Home.ets",
            }],
        }), encoding="utf-8")
        self._write_capture()

    def tearDown(self):
        self.temp.cleanup()

    def _write_capture(self):
        png = self.output_dir / "ios-runtime.png"
        ui_json = self.output_dir / "ios-accessibility.json"
        png.write_bytes(b"png-evidence")
        ui_json.write_text(json.dumps({"nodes": [{
            "id": "home-title", "role": "staticText", "label": "首页",
            "frame": [0, 0, 100, 40],
        }]}), encoding="utf-8")
        evidence = {
            "status": "audited",
            "page_id": self.page_id,
            "state": self.state_id,
            "state_id": self.state_id,
            "png_path": "states/normal/ios-runtime.png",
            "png_sha256": hashlib.sha256(png.read_bytes()).hexdigest(),
            "ui_json_path": "states/normal/ios-accessibility.json",
            "ui_json_sha256": hashlib.sha256(ui_json.read_bytes()).hexdigest(),
            "source_platform": "ios",
            "app": {"bundle_id": "com.example.cuike"},
            "device": {"udid": "SIM-1"},
        }
        (self.capture_root / self.page_id / "meta.json").write_text(json.dumps({
            "page_id": self.page_id,
            "runtime_evidence": evidence,
            "runtime_evidence_by_state": {self.state_id: evidence},
        }), encoding="utf-8")
        manifest = {
            "schema_version": 1,
            "status": "captured",
            "output_root": str(self.capture_root),
            "states": [{
                "page_id": self.page_id,
                "state_id": self.state_id,
                "status": "captured",
                "output_dir": str(self.output_dir),
            }],
        }
        self.manifest = self.root / "capture-plan-manifest.json"
        self.manifest.write_text(json.dumps(manifest), encoding="utf-8")

    def test_external_capture_manifest_is_materialized_into_scope(self):
        destination = self.root / "spec/baseline/ui-snapshots" / self.page_id
        destination.mkdir(parents=True, exist_ok=True)
        meta = destination / "meta.json"
        meta.write_text(json.dumps({"layout_sources": ["Home.swift"]}), encoding="utf-8")
        frozen_meta = meta.read_bytes()
        scope = build_scope(self.wiring_dir, self.root, self.manifest)
        self.assertEqual(scope["status"], "READY")
        self.assertEqual(scope["runtime_capture"]["status"], "synced")
        baseline = scope["units"][0]["pages"][0]["baseline"]
        self.assertEqual(baseline["evidence_kind"], "ios-accessibility-json")
        self.assertEqual(meta.read_bytes(), frozen_meta)
        runtime_meta = json.loads((destination / "runtime-meta.json").read_bytes())
        self.assertEqual(list(runtime_meta["runtime_evidence_by_state"]), ["normal"])
        self.assertTrue((destination / "states/normal/ios-runtime.png").is_file())

    def test_project_local_manifest_is_discovered_automatically(self):
        local_manifest = self.root / "spec/execution/ios-runtime-capture/capture-plan-manifest.json"
        local_manifest.parent.mkdir(parents=True)
        local_manifest.write_text(self.manifest.read_text(), encoding="utf-8")
        scope = build_scope(self.wiring_dir, self.root)
        self.assertEqual(scope["runtime_capture"]["manifest"], str(local_manifest.resolve()))

    def test_partial_manifest_fails_closed(self):
        payload = json.loads(self.manifest.read_text())
        payload["status"] = "partial"
        payload["states"][0]["status"] = "blocked"
        payload["states"][0]["blocked_reason"] = "simulator offline"
        self.manifest.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "runtime capture manifest is partial"):
            build_scope(self.wiring_dir, self.root, self.manifest)


if __name__ == "__main__":
    unittest.main()
