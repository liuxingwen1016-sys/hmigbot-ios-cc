import json
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(SCRIPT_DIR))

from ios_evidence_protocol import (  # noqa: E402
    CAPTURE_SCHEMA,
    pair_manifests,
    sha256_file,
    source_identity,
    validate_manifest,
)


def manifest(root: Path, *, platform: str = "ios", page: str = "home", checkpoint: str = "home-default") -> Path:
    screenshot = root / f"{platform}.png"
    ui_json = root / f"{platform}.json"
    screenshot.write_bytes(platform.encode("utf-8"))
    ui_json.write_text(json.dumps({"nodes": []}), encoding="utf-8")
    payload = {
        "schema": CAPTURE_SCHEMA,
        "identity": {
            "platform": platform,
            "page_id": page,
            "state_id": "default",
            "scenario_id": "cuike-smoke",
            "configuration_id": "Debug",
            "checkpoint_id": checkpoint,
            "source_sha256": "a" * 64,
            "build_sha256": "b" * 64,
            "device_udid": "sim-1" if platform == "ios" else "mate-1",
            "screenshot_sha256": sha256_file(screenshot),
            "ui_json_sha256": sha256_file(ui_json),
        },
        "artifacts": {
            "screenshot": {"path": screenshot.name, "sha256": sha256_file(screenshot)},
            "ui_json": {"path": ui_json.name, "sha256": sha256_file(ui_json)},
        },
    }
    path = root / f"{platform}-manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class EvidenceProtocolTests(unittest.TestCase):
    def test_source_identity_changes_when_source_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "ios"
            source.mkdir()
            (source / "Home.swift").write_text("struct Home {}\n", encoding="utf-8")
            first = source_identity(source)
            (source / "Home.swift").write_text("struct Home { let x = 1 }\n", encoding="utf-8")
            self.assertNotEqual(first, source_identity(source))

    def test_validate_rejects_artifact_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = manifest(root)
            (root / "ios.png").write_bytes(b"changed")
            result = validate_manifest(path)
            self.assertEqual(result["status"], "stale")
            self.assertEqual(result["issues"][0]["rule"], "artifact_hash_mismatch")

    def test_validate_rejects_current_identity_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = manifest(root)
            result = validate_manifest(path, {"device_udid": "different-sim"})
            self.assertEqual(result["status"], "stale")
            self.assertTrue(any(item["rule"] == "identity_mismatch" for item in result["issues"]))

    def test_pair_missing_evidence_is_not_run(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = manifest(root, platform="ios")
            missing = root / "missing.json"
            result = pair_manifests(source, missing)
            self.assertEqual(result["status"], "not_run")
            self.assertIsNone(result["visual_score"])

    def test_design_difference_exception_is_bound_and_scored(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = manifest(root, platform="ios")
            target = manifest(root, platform="harmonyos")
            differences = [{"category": "design_difference", "severity": "high", "reason": "system status bar"}]
            first = pair_manifests(source, target, differences=differences)
            self.assertEqual(first["status"], "pass_visual")
            self.assertEqual(first["visual_score"], 0.95)
            difference = first["differences"][0]
            exception = {
                "difference_id": difference["id"],
                "observation_sha256": difference["observation_sha256"],
                "category": "design_difference",
                "reason": "platform system status bar",
                "evidence": {
                    "source_manifest_sha256": "source-manifest",
                    "target_manifest_sha256": "target-manifest",
                },
            }
            second = pair_manifests(source, target, differences=differences, exceptions=[exception])
            self.assertEqual(second["status"], "pass_visual")
            self.assertEqual(second["visual_score"], 1.0)


if __name__ == "__main__":
    unittest.main()
