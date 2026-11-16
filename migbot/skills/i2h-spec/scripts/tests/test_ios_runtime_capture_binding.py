#!/usr/bin/env python3
"""Tests for ios_installed_identity module and ios_runtime_capture binding logic.

These tests verify:
1. Generic installed identity validation functions work correctly
2. Real capture() integration with stable binding
3. Negative cases: missing query, malformed plist, wrong bundle_id, after-screenshot drift
"""
import json
import plistlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch
from argparse import Namespace

SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

from ios_installed_identity import query_installed_app_path, validate_installed_identity  # noqa: E402
from ios_runtime_capture import capture  # noqa: E402
from ios_evidence_protocol import bundle_identity  # noqa: E402


class InstalledIdentityTests(unittest.TestCase):
    """Tests for the generic ios_installed_identity module."""

    def test_query_returns_none_on_subprocess_error(self):
        """Test query_installed_app_path returns None when simctl fails."""
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(1, ['xcrun'])
            result = query_installed_app_path("UDID123", "com.example.app")
            self.assertIsNone(result)

    def test_query_returns_none_on_empty_output(self):
        """Test query_installed_app_path returns None when simctl returns empty."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(stdout="", returncode=0)
            result = query_installed_app_path("UDID123", "com.example.app")
            self.assertIsNone(result)

    def test_query_returns_path_when_valid(self):
        """Test query_installed_app_path returns Path when simctl succeeds."""
        with tempfile.TemporaryDirectory() as tmpdir:
            app_path = Path(tmpdir) / "Test.app"
            app_path.mkdir()
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = Mock(stdout=str(app_path) + "\n", returncode=0)
                result = query_installed_app_path("UDID123", "com.example.app")
                self.assertEqual(result.resolve(), app_path.resolve())

    def test_validate_rejects_missing_info_plist(self):
        """Test validate_installed_identity rejects missing Info.plist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            app_path = Path(tmpdir) / "Test.app"
            app_path.mkdir()
            with self.assertRaises(RuntimeError) as ctx:
                validate_installed_identity(app_path, "com.example.app")
            self.assertIn("Info.plist not found", str(ctx.exception))

    def test_validate_rejects_non_dict_plist(self):
        """Test validate_installed_identity rejects non-dict plist root."""
        with tempfile.TemporaryDirectory() as tmpdir:
            app_path = Path(tmpdir) / "Test.app"
            app_path.mkdir()
            info_plist = app_path / "Info.plist"
            # Write a plist array instead of dict
            with info_plist.open("wb") as f:
                plistlib.dump(["not", "a", "dict"], f)

            with self.assertRaises(RuntimeError) as ctx:
                validate_installed_identity(app_path, "com.example.app")
            self.assertIn("must be a dictionary", str(ctx.exception))

    def test_validate_rejects_bundle_id_mismatch(self):
        """Test validate_installed_identity rejects wrong bundle_id."""
        with tempfile.TemporaryDirectory() as tmpdir:
            app_path = Path(tmpdir) / "Test.app"
            app_path.mkdir()
            info_plist = app_path / "Info.plist"
            plist_data = {
                "CFBundleIdentifier": "com.wrong.bundle",
                "CFBundleShortVersionString": "1.0",
                "CFBundleVersion": "100",
            }
            with info_plist.open("wb") as f:
                plistlib.dump(plist_data, f)

            with self.assertRaises(RuntimeError) as ctx:
                validate_installed_identity(app_path, "com.example.app")
            self.assertIn("bundle_id mismatch", str(ctx.exception))
            self.assertIn("com.wrong.bundle", str(ctx.exception))

    def test_validate_rejects_non_string_version(self):
        """Test validate_installed_identity rejects non-string version."""
        with tempfile.TemporaryDirectory() as tmpdir:
            app_path = Path(tmpdir) / "Test.app"
            app_path.mkdir()
            info_plist = app_path / "Info.plist"
            plist_data = {
                "CFBundleIdentifier": "com.example.app",
                "CFBundleShortVersionString": 123,  # integer, not string
                "CFBundleVersion": "100",
            }
            with info_plist.open("wb") as f:
                plistlib.dump(plist_data, f)

            with self.assertRaises(RuntimeError) as ctx:
                validate_installed_identity(app_path, "com.example.app")
            self.assertIn("CFBundleShortVersionString must be a nonempty string", str(ctx.exception))

    def test_validate_rejects_empty_build(self):
        """Test validate_installed_identity rejects empty build string."""
        with tempfile.TemporaryDirectory() as tmpdir:
            app_path = Path(tmpdir) / "Test.app"
            app_path.mkdir()
            info_plist = app_path / "Info.plist"
            plist_data = {
                "CFBundleIdentifier": "com.example.app",
                "CFBundleShortVersionString": "1.0",
                "CFBundleVersion": "   ",  # whitespace only
            }
            with info_plist.open("wb") as f:
                plistlib.dump(plist_data, f)

            with self.assertRaises(RuntimeError) as ctx:
                validate_installed_identity(app_path, "com.example.app")
            self.assertIn("CFBundleVersion must be a nonempty string", str(ctx.exception))

    def test_validate_accepts_valid_identity(self):
        """Test validate_installed_identity accepts valid identity."""
        with tempfile.TemporaryDirectory() as tmpdir:
            app_path = Path(tmpdir) / "Test.app"
            app_path.mkdir()
            (app_path / "dummy").write_text("content")
            info_plist = app_path / "Info.plist"
            plist_data = {
                "CFBundleIdentifier": "com.example.app",
                "CFBundleShortVersionString": "2.1",
                "CFBundleVersion": "210",
            }
            with info_plist.open("wb") as f:
                plistlib.dump(plist_data, f)

            result = validate_installed_identity(app_path, "com.example.app")
            self.assertEqual(result["bundle_id"], "com.example.app")
            self.assertEqual(result["version"], "2.1")
            self.assertEqual(result["build"], "210")
            self.assertEqual(result["build_identity"], "com.example.app:2.1:210")
            self.assertEqual(result["app_path"], str(app_path))
            self.assertNotIn("bundle_sha256", result)


class CaptureIntegrationTests(unittest.TestCase):
    """Integration tests for capture() with actual binding logic."""

    def _create_app_fixture(self, base_dir: Path, name: str, bundle_id: str, binary_content: bytes) -> Path:
        """Create a minimal app bundle fixture."""
        app_path = base_dir / f"{name}.app"
        app_path.mkdir(parents=True)
        info_plist = app_path / "Info.plist"
        plist_data = {
            "CFBundleIdentifier": bundle_id,
            "CFBundleShortVersionString": "1.0",
            "CFBundleVersion": "1",
        }
        with info_plist.open("wb") as f:
            plistlib.dump(plist_data, f)
        (app_path / "binary").write_bytes(binary_content)
        return app_path

    def test_capture_with_stable_binding(self):
        """Test capture() with stable before/after binding records correct manifest."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # Create requested app (what xcodebuild produces)
            requested_app = self._create_app_fixture(
                tmpdir / "derived/Build/Products/Debug-iphonesimulator",
                "Test",
                "com.test.app",
                b"original binary from xcodebuild"
            )

            # Create installed app (what XCTest helper actually installed)
            installed_app = self._create_app_fixture(
                tmpdir / "installed",
                "Test",
                "com.test.app",
                b"rebuilt binary different from xcodebuild"
            )

            output_dir = tmpdir / "output"
            output_dir.mkdir()

            # Compute expected digests
            requested_digest = bundle_identity(requested_app)
            installed_digest = bundle_identity(installed_app)
            self.assertNotEqual(requested_digest, installed_digest)

            # Setup args
            args = Namespace(
                project_root=str(tmpdir),
                project=str(tmpdir / "Test.xcodeproj"),
                scheme="Test",
                configuration="Debug",
                device_id="SIM123",
                require_device_id=False,
                xcrun="xcrun",
                derived_data=str(requested_app.parent.parent.parent),
                app_path=str(requested_app),
                bundle_id="com.test.app",
                output_dir=str(output_dir),
                page_id="page_001",
                state_id="normal",
                source_root=None,
                scenario_id="test",
                configuration_id="Debug",
                checkpoint_id="page_001:normal",
                accessibility_json=None,
                accessibility_command="echo helper",
                navigation_json=None,
                skip_build=True,
                dry_run=False,
                timeout=60,
            )

            with patch('ios_runtime_capture.run_command') as mock_run, \
                 patch('ios_runtime_capture.subprocess.Popen') as mock_popen, \
                 patch('ios_installed_identity.subprocess.run') as mock_simctl:

                # Mock device listing
                def run_command_side_effect(cmd, **kwargs):
                    if "list" in cmd and "devices" in cmd:
                        return Mock(stdout='{"devices": {"iOS-17": [{"udid": "SIM123", "state": "Booted", "name": "iPhone"}]}}')
                    elif "screenshot" in cmd:
                        screenshot = output_dir / "ios-runtime.png"
                        screenshot.write_bytes(b"\x89PNG\r\n\x1a\n")  # minimal PNG header
                        return Mock(stdout="", returncode=0)
                    return Mock(stdout="", returncode=0)

                mock_run.side_effect = run_command_side_effect

                # Mock simctl get_app_container to return installed path
                mock_simctl.return_value = Mock(stdout=str(installed_app) + "\n", returncode=0)

                # Mock Popen for accessibility command - produces files AFTER unlink
                mock_process = Mock()
                poll_count = [0]

                def mock_poll():
                    poll_count[0] += 1
                    if poll_count[0] == 1:
                        # First poll: helper running, create files now
                        (output_dir / "ios-accessibility.json").write_text(
                            json.dumps({"nodes": [{"type": "Button", "label": "OK"}]})
                        )
                        (output_dir / "foreground-receipt.json").write_text(json.dumps({
                            "schema": "hmigbot-ios-foreground-receipt/1",
                            "bundle_id": "com.test.app",
                            "page_id": "page_001",
                            "state_id": "normal",
                            "state": "runningForeground",
                            "ready": True,
                        }))
                        return None  # Still running
                    return 0  # Finished

                mock_process.poll = mock_poll
                mock_process.returncode = 0
                mock_process.wait = Mock()
                mock_popen.return_value = mock_process

                # Run capture
                result = capture(args)

                # Verify success
                self.assertEqual(result["status"], "captured")
                manifest_path = Path(result["manifest"])
                self.assertTrue(manifest_path.exists())

                # Read and verify manifest
                manifest = json.loads(manifest_path.read_text())

                # Manifest must use actual installed digest, not requested
                self.assertEqual(manifest["identity"]["build_sha256"], installed_digest)
                self.assertNotEqual(manifest["identity"]["build_sha256"], requested_digest)

                # Build binding must be recorded
                self.assertIn("build_binding", manifest)
                binding = manifest["build_binding"]
                self.assertTrue(binding["binding_stable"])
                self.assertEqual(binding["binding_method"], "foreground_receipt_double_check")
                self.assertEqual(binding["requested_bundle_sha256"], requested_digest)
                self.assertEqual(binding["actual_installed_bundle_sha256"], installed_digest)
                self.assertEqual(binding["before_screenshot"]["bundle_sha256"], installed_digest)
                self.assertEqual(binding["after_screenshot"]["bundle_sha256"], installed_digest)

                # Verify ACK was written
                ack_path = output_dir / "foreground-capture-ack.json"
                self.assertTrue(ack_path.exists())

    def test_capture_rejects_missing_installed_query(self):
        """Test capture() fails when installed app query returns None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            requested_app = self._create_app_fixture(
                tmpdir / "derived/Build/Products/Debug-iphonesimulator",
                "Test", "com.test.app", b"binary"
            )

            output_dir = tmpdir / "output"
            output_dir.mkdir()

            args = Namespace(
                project_root=str(tmpdir),
                project=str(tmpdir / "Test.xcodeproj"),
                scheme="Test",
                configuration="Debug",
                device_id="SIM123",
                require_device_id=False,
                xcrun="xcrun",
                derived_data=str(requested_app.parent.parent.parent),
                app_path=str(requested_app),
                bundle_id="com.test.app",
                output_dir=str(output_dir),
                page_id="page_001",
                state_id="normal",
                source_root=None,
                scenario_id="test",
                configuration_id="Debug",
                checkpoint_id="page_001:normal",
                accessibility_json=None,
                accessibility_command="echo helper",
                navigation_json=None,
                skip_build=True,
                dry_run=False,
                timeout=60,
            )

            with patch('ios_runtime_capture.run_command') as mock_run, \
                 patch('ios_runtime_capture.subprocess.Popen') as mock_popen, \
                 patch('ios_installed_identity.subprocess.run') as mock_simctl:

                mock_run.side_effect = lambda cmd, **kw: Mock(
                    stdout='{"devices": {"iOS-17": [{"udid": "SIM123", "state": "Booted", "name": "iPhone"}]}}'
                )

                # Simulate query failure - returns empty
                mock_simctl.return_value = Mock(stdout="", returncode=0)

                mock_process = Mock()
                def mock_poll():
                    # Create files on first poll
                    if not (output_dir / "ios-accessibility.json").exists():
                        (output_dir / "ios-accessibility.json").write_text(json.dumps({"nodes": []}))
                        (output_dir / "foreground-receipt.json").write_text(json.dumps({
                            "schema": "hmigbot-ios-foreground-receipt/1",
                            "bundle_id": "com.test.app",
                            "page_id": "page_001",
                            "state_id": "normal",
                            "state": "runningForeground",
                            "ready": True,
                        }))
                        return None
                    return 0

                mock_process.poll = mock_poll
                mock_process.returncode = 0
                mock_process.wait = Mock()
                mock_popen.return_value = mock_process

                with self.assertRaises(RuntimeError) as ctx:
                    capture(args)

                self.assertIn("Cannot find actual installed app", str(ctx.exception))

                # Verify no success manifest or ACK
                self.assertFalse((output_dir / "manifest.json").exists())

                # Verify process was waited on
                mock_process.wait.assert_called()

    def test_capture_rejects_wrong_bundle_id(self):
        """Test capture() fails when installed app has wrong bundle_id."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            requested_app = self._create_app_fixture(
                tmpdir / "derived/Build/Products/Debug-iphonesimulator",
                "Test", "com.test.app", b"binary"
            )

            # Installed app has WRONG bundle_id
            installed_app = tmpdir / "installed/Test.app"
            installed_app.mkdir(parents=True)
            info_plist = installed_app / "Info.plist"
            with info_plist.open("wb") as f:
                plistlib.dump({
                    "CFBundleIdentifier": "com.wrong.app",  # WRONG
                    "CFBundleShortVersionString": "1.0",
                    "CFBundleVersion": "1",
                }, f)
            (installed_app / "binary").write_bytes(b"data")

            output_dir = tmpdir / "output"
            output_dir.mkdir()

            args = Namespace(
                project_root=str(tmpdir),
                project=str(tmpdir / "Test.xcodeproj"),
                scheme="Test",
                configuration="Debug",
                device_id="SIM123",
                require_device_id=False,
                xcrun="xcrun",
                derived_data=str(requested_app.parent.parent.parent),
                app_path=str(requested_app),
                bundle_id="com.test.app",
                output_dir=str(output_dir),
                page_id="page_001",
                state_id="normal",
                source_root=None,
                scenario_id="test",
                configuration_id="Debug",
                checkpoint_id="page_001:normal",
                accessibility_json=None,
                accessibility_command="echo helper",
                navigation_json=None,
                skip_build=True,
                dry_run=False,
                timeout=60,
            )

            with patch('ios_runtime_capture.run_command') as mock_run, \
                 patch('ios_runtime_capture.subprocess.Popen') as mock_popen, \
                 patch('ios_installed_identity.subprocess.run') as mock_simctl:

                mock_run.side_effect = lambda cmd, **kw: Mock(
                    stdout='{"devices": {"iOS-17": [{"udid": "SIM123", "state": "Booted", "name": "iPhone"}]}}'
                )

                mock_simctl.return_value = Mock(stdout=str(installed_app) + "\n", returncode=0)

                mock_process = Mock()
                def mock_poll():
                    if not (output_dir / "ios-accessibility.json").exists():
                        (output_dir / "ios-accessibility.json").write_text(json.dumps({"nodes": []}))
                        (output_dir / "foreground-receipt.json").write_text(json.dumps({
                            "schema": "hmigbot-ios-foreground-receipt/1",
                            "bundle_id": "com.test.app",
                            "page_id": "page_001",
                            "state_id": "normal",
                            "state": "runningForeground",
                            "ready": True,
                        }))
                        return None
                    return 0

                mock_process.poll = mock_poll
                mock_process.returncode = 0
                mock_process.wait = Mock()
                mock_popen.return_value = mock_process

                with self.assertRaises(RuntimeError) as ctx:
                    capture(args)

                self.assertIn("bundle_id mismatch", str(ctx.exception))
                self.assertIn("com.wrong.app", str(ctx.exception))
                self.assertFalse((output_dir / "manifest.json").exists())
                mock_process.wait.assert_called()

    def test_capture_rejects_digest_change_after_screenshot(self):
        """Test capture() fails when installed app digest changes after screenshot."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            requested_app = self._create_app_fixture(
                tmpdir / "derived/Build/Products/Debug-iphonesimulator",
                "Test", "com.test.app", b"binary"
            )

            installed_app = self._create_app_fixture(
                tmpdir / "installed", "Test", "com.test.app", b"installed v1"
            )

            output_dir = tmpdir / "output"
            output_dir.mkdir()

            args = Namespace(
                project_root=str(tmpdir),
                project=str(tmpdir / "Test.xcodeproj"),
                scheme="Test",
                configuration="Debug",
                device_id="SIM123",
                require_device_id=False,
                xcrun="xcrun",
                derived_data=str(requested_app.parent.parent.parent),
                app_path=str(requested_app),
                bundle_id="com.test.app",
                output_dir=str(output_dir),
                page_id="page_001",
                state_id="normal",
                source_root=None,
                scenario_id="test",
                configuration_id="Debug",
                checkpoint_id="page_001:normal",
                accessibility_json=None,
                accessibility_command="echo helper",
                navigation_json=None,
                skip_build=True,
                dry_run=False,
                timeout=60,
            )

            with patch('ios_runtime_capture.run_command') as mock_run, \
                 patch('ios_runtime_capture.subprocess.Popen') as mock_popen, \
                 patch('ios_installed_identity.subprocess.run') as mock_simctl:

                def run_command_side_effect(cmd, **kwargs):
                    if "list" in cmd and "devices" in cmd:
                        return Mock(stdout='{"devices": {"iOS-17": [{"udid": "SIM123", "state": "Booted", "name": "iPhone"}]}}')
                    elif "screenshot" in cmd:
                        # MUTATE installed app binary during screenshot
                        (installed_app / "binary").write_bytes(b"installed v2 CHANGED")
                        screenshot = output_dir / "ios-runtime.png"
                        screenshot.write_bytes(b"\x89PNG\r\n\x1a\n")
                        return Mock(stdout="", returncode=0)
                    return Mock(stdout="", returncode=0)

                mock_run.side_effect = run_command_side_effect
                mock_simctl.return_value = Mock(stdout=str(installed_app) + "\n", returncode=0)

                mock_process = Mock()
                def mock_poll():
                    if not (output_dir / "ios-accessibility.json").exists():
                        (output_dir / "ios-accessibility.json").write_text(json.dumps({"nodes": []}))
                        (output_dir / "foreground-receipt.json").write_text(json.dumps({
                            "schema": "hmigbot-ios-foreground-receipt/1",
                            "bundle_id": "com.test.app",
                            "page_id": "page_001",
                            "state_id": "normal",
                            "state": "runningForeground",
                            "ready": True,
                        }))
                        return None
                    return 0

                mock_process.poll = mock_poll
                mock_process.returncode = 0
                mock_process.wait = Mock()
                mock_popen.return_value = mock_process

                with self.assertRaises(RuntimeError) as ctx:
                    capture(args)

                self.assertIn("bundle digest changed during capture", str(ctx.exception))
                self.assertFalse((output_dir / "manifest.json").exists())
                mock_process.wait.assert_called()


if __name__ == "__main__":
    # Print import paths for verification
    print("=== Import Path Verification ===")
    print(f"ios_installed_identity.__file__ = {sys.modules['ios_installed_identity'].__file__}")
    print(f"ios_runtime_capture.__file__ = {sys.modules['ios_runtime_capture'].__file__}")
    print(f"ios_evidence_protocol.__file__ = {sys.modules['ios_evidence_protocol'].__file__}")
    print(f"SCRIPT_DIR = {SCRIPT_DIR}")

    # Verify we're testing the sandbox versions
    helper_file = Path(sys.modules['ios_installed_identity'].__file__).resolve()
    collector_file = Path(sys.modules['ios_runtime_capture'].__file__).resolve()
    expected_helper = (SCRIPT_DIR / "ios_installed_identity.py").resolve()
    expected_collector = (SCRIPT_DIR / "ios_runtime_capture.py").resolve()

    assert helper_file == expected_helper, f"Helper mismatch: {helper_file} != {expected_helper}"
    assert collector_file == expected_collector, f"Collector mismatch: {collector_file} != {expected_collector}"
    print("✅ Import paths verified: testing sandbox modules")
    print()

    unittest.main()
