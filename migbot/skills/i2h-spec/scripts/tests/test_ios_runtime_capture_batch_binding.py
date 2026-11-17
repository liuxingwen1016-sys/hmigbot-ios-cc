import json
from pathlib import Path
import plistlib
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ios_runtime_capture_batch as batch
from ios_evidence_protocol import bundle_identity


class BatchInstalledBindingTests(unittest.TestCase):
    def collect(self, root, *, mode='simulator', mutate=False, missing=False):
        app = root / 'Installed.app'
        app.mkdir()
        (app / 'Info.plist').write_bytes(plistlib.dumps({
            'CFBundleIdentifier': 'test.app', 'CFBundleVersion': '1',
            'CFBundleShortVersionString': '1.0',
        }))
        binary = app / 'binary'
        binary.write_bytes(b'installed build')
        observed_digest = bundle_identity(app)
        output = root / 'page/states/normal'
        output.mkdir(parents=True)
        tree = output / 'ios-accessibility.json'
        tree.write_text(json.dumps({'nodes': [{'type': 'Button', 'label': 'Go'}]}))
        png = output / 'ios-runtime.png'
        receipt = {'schema': 'hmigbot-ios-foreground-receipt/1', 'bundle_id': 'test.app',
                   'page_id': 'page', 'state_id': 'normal', 'state': 'runningForeground', 'ready': True}
        state = {'bundle_id': 'test.app', 'page_id': 'page', 'state_id': 'normal', 'output_dir': str(output)}
        if mode == 'xctest_app':
            png.write_bytes(b'\x89PNG\r\n\x1a\nframe')
            state['capture_mode'] = receipt['capture_mode'] = mode
            receipt['screenshot_sha256'] = batch.sha256(png.read_bytes()).hexdigest()
            receipt['ui_json_sha256'] = batch.sha256(tree.read_bytes()).hexdigest()
        (output / 'foreground-receipt.json').write_text(json.dumps(receipt))
        process = Mock()
        process.__enter__ = Mock(return_value=process)
        process.__exit__ = Mock(return_value=False)
        process.poll.side_effect = [None, 0]
        process.wait.return_value = 0

        def capture(command, **kwargs):
            Path(command[-1]).write_bytes(b'\x89PNG\r\n\x1a\nframe')
            if mutate:
                binary.write_bytes(b'changed build')

        args = SimpleNamespace(device_id='simulator', xcrun='xcrun', timeout=10,
                               xctest_target='UITests', scenario_id='scene', configuration_id='Debug')
        with patch.object(batch.subprocess, 'Popen', return_value=process), \
             patch.object(batch, 'query_installed_app_path', return_value=None if missing else app), \
             patch.object(batch, 'run_command', side_effect=capture) as screenshot:
            rows = batch.collect_group(args, [state], xctestrun=root / 'test.xctestrun',
                                       directory=root / 'session', app=root / 'Requested.app',
                                       identity={'bundle_sha256': 'a' * 64}, source_sha256='b' * 64)
        return rows[0], output, observed_digest, screenshot

    def test_batch_records_actual_installed_identity_and_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            row, output, observed_digest, screenshot = self.collect(Path(temporary))
            self.assertEqual(row['status'], 'captured')
            manifest = json.loads((output / 'manifest.json').read_text())
            self.assertEqual(manifest['identity']['build_sha256'], observed_digest)
            binding = manifest['build_binding']
            self.assertEqual(binding['requested_bundle_sha256'], 'a' * 64)
            self.assertEqual(binding['before_screenshot']['bundle_sha256'], observed_digest)
            self.assertEqual(binding['after_screenshot']['bundle_sha256'], observed_digest)
            self.assertTrue((output / 'foreground-capture-ack.json').is_file())
            screenshot.assert_called_once()

    def test_batch_blocks_changed_or_missing_installed_app_without_ack(self):
        for options in ({'mutate': True}, {'missing': True}):
            with self.subTest(options=options), tempfile.TemporaryDirectory() as temporary:
                row, output, _, _ = self.collect(Path(temporary), **options)
                self.assertEqual(row['status'], 'blocked')
                self.assertIn('installed app' if options.get('missing') else 'identity changed',
                              row['blocked_reason'])
                self.assertFalse((output / 'foreground-capture-ack.json').exists())
                self.assertFalse((output / 'manifest.json').exists())

    def test_app_frame_retains_its_capture_and_labels_host_validation_observations(self):
        with tempfile.TemporaryDirectory() as temporary:
            row, output, observed_digest, screenshot = self.collect(Path(temporary), mode='xctest_app')
            self.assertEqual(row['status'], 'captured')
            manifest = json.loads((output / 'manifest.json').read_text())
            self.assertEqual(manifest['identity']['build_sha256'], observed_digest)
            binding = manifest['build_binding']
            self.assertEqual(binding['binding_method'], 'foreground_receipt_artifact_double_check')
            self.assertIn('before_artifact_validation', binding)
            self.assertIn('after_artifact_validation', binding)
            self.assertNotIn('before_screenshot', binding)
            screenshot.assert_not_called()
