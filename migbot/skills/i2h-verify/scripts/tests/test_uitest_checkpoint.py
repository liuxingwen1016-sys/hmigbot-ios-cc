from pathlib import Path
import json
from subprocess import TimeoutExpired
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from uitest_action import ForegroundError
from uitest_checkpoint import (CheckpointTimeout, capture_checkpoint, capture_uitest_artifact,
                               core_vision_ocr_preflight, device_timeout_details, hdc_failure_details,
                               write_visual_arrival)


def tree(ready=False, bundle='app'):
    return {'ready': ready, 'children': [{'attributes': {
        'bundleName': bundle, 'focused': 'true', 'pagePath': 'pages/Index',
    }}]}


class CheckpointTest(unittest.TestCase):
    def test_core_vision_ocr_blocks_only_a_confirmed_emulator(self):
        send = Mock(return_value='emulator\r\n')
        block = core_vision_ocr_preflight(send)
        send.assert_called_once_with('shell', 'param', 'get', 'const.product.model')
        self.assertEqual(block['status'], 'BLOCKED')
        self.assertEqual(block['device_capability'], 'core_vision_ocr')
        self.assertEqual(block['failure_diagnostic']['device_model'], 'emulator')
        for output in ('Mate 80', '', 'service failed: 1001400001'):
            send.return_value = output
            self.assertIsNone(core_vision_ocr_preflight(send))
        send.side_effect = TimeoutExpired('hdc', 2)
        with self.assertRaises(TimeoutExpired):
            core_vision_ocr_preflight(send)

    def test_native_download_commits_before_exact_remote_cleanup(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            files = {}
            removed = []

            def send(*args):
                if args[:3] == ('shell', 'uitest', 'dumpLayout'):
                    files[args[-1]] = json.dumps(tree(True)).encode()
                    return 'DumpLayout saved to: ' + args[-1]
                if args[:2] == ('shell', 'snapshot_display'):
                    files[args[-1]] = b'\xff\xd8\xffjpeg'
                    return ''
                if args[:2] == ('file', 'recv'):
                    Path(args[-1]).write_bytes(files[args[2]])
                    return ''
                self.assertEqual(args[:3], ('shell', 'rm', '-f'))
                target = root / ('target.json' if args[-1].endswith('.json') else 'target.jpeg')
                self.assertEqual(target.read_bytes(), files[args[-1]])
                removed.append(args[-1])
                del files[args[-1]]

            for _ in range(2):
                self.assertEqual(capture_uitest_artifact(root/'target.json', kind='layout', send=send), tree(True))
            self.assertEqual(capture_uitest_artifact(root/'target.jpeg', kind='image', send=send), root/'target.jpeg')
            self.assertEqual(len(set(removed)), 3)
            self.assertTrue(all(path.startswith('/data/local/tmp/i2h-uitest-') for path in removed))
            self.assertEqual(files, {})
            self.assertEqual({path.name for path in root.iterdir()}, {'target.json', 'target.jpeg'})

    def test_failed_or_invalid_download_preserves_prior_local_evidence_and_remote_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            final = root/'target.json'
            final.write_bytes(b'prior')
            for failure in (TimeoutExpired(['hdc'], 10), None):
                def send(*args):
                    if args[:3] == ('shell', 'uitest', 'dumpLayout'):
                        return 'DumpLayout saved to:' + args[-1]
                    self.assertEqual(args[:2], ('file', 'recv'))
                    Path(args[-1]).write_bytes(b'partial')
                    if failure is not None:
                        raise failure

                with self.assertRaises(TimeoutExpired if failure is not None else ValueError) as caught:
                    capture_uitest_artifact(final, kind='layout', send=send)
                self.assertTrue(caught.exception.remote_uitest_artifact.endswith('.json'))
                if failure is not None:
                    self.assertEqual(device_timeout_details(caught.exception), {
                        'seconds': 10, 'remote_uitest_artifact': caught.exception.remote_uitest_artifact,
                    })
                self.assertEqual(final.read_bytes(), b'prior')
                self.assertEqual(list(root.iterdir()), [final])

    def test_cleanup_failure_is_reported_without_discarding_local_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            final = Path(temporary)/'target.png'
            png = b'\x89PNG\r\n\x1a\nfixture'

            def send(*args):
                if args[:2] == ('file', 'recv'):
                    Path(args[-1]).write_bytes(png)
                elif args[:3] == ('shell', 'rm', '-f'):
                    raise RuntimeError('device disconnected')
                return ''

            with self.assertWarnsRegex(RuntimeWarning, 'remote cleanup failed.*i2h-uitest-'):
                capture_uitest_artifact(final, kind='image', send=send)
            self.assertEqual(final.read_bytes(), png)

    def test_hdc_reports_environment_errors_even_with_zero_exit(self):
        samples = (
            ("error: failed to start ability.\nError Code:10106102  Error Message:The device screen is locked",
             "device_screen_locked", "10106102"),
            ("[Fail][E001005] Device not found or connected\r\n", "device_disconnected", "E001005"),
        )
        for output, kind, code in samples:
            with self.subTest(kind=kind):
                self.assertEqual(hdc_failure_details(0, output, ""),
                                 {"kind": kind, "code": code, "exit_code": 0})

    def test_hdc_keeps_unrecognized_failure_and_allows_success(self):
        self.assertEqual(hdc_failure_details(1, "", "transport unavailable"),
                         {"kind": "hdc_command_failed", "exit_code": 1})
        self.assertIsNone(hdc_failure_details(0, "start ability successfully.", ""))

    def test_arrival_binds_the_matched_tree_and_is_written_only_after_capture(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            layout, image, build, install, receipt = (root / name for name in (
                'layout.json', 'target.jpeg', 'build.json', 'install.json', 'arrival.json'))
            matched = tree(ready=True)
            layout.write_text(json.dumps(matched))
            for path in (build, install):
                path.write_text('{}')

            def record(name, state):
                write_visual_arrival(root, receipt, pair={
                    'pair_id': 'pair', 'arrival_mode': 'formal', 'page_id': 'page', 'state_id': 'state',
                    'comparisons': [{'comparison_id': 'pair:0'}],
                }, capture_run_id='actual-run', device_id='device', screenshot=image,
                    layout=layout, matched_tree=state, build_receipt=build, install_receipt=install)

            options = dict(bundle='app', read_layout=lambda name: matched, is_ready=lambda state: state['ready'],
                           capture_image=lambda name: image.write_bytes(b'\xff\xd8\xfffixture'),
                           record_arrival=record)
            capture_checkpoint('ready', approved_images=set(), **options)
            self.assertFalse(receipt.exists())
            capture_checkpoint('ready', approved_images={'ready'}, **options)
            data = json.loads(receipt.read_bytes())
            self.assertEqual(data['observed_state_id'], 'state')
            self.assertEqual(data['frames'][0]['harmony_xml'], data['landing_evidence'])
            layout.write_text('{}')
            with self.assertRaisesRegex(ValueError, 'state-ready tree'):
                capture_checkpoint('ready', approved_images={'ready'}, **options)
            self.assertEqual(json.loads(receipt.read_bytes()), data)

    def capture(self, reader, image, scope):
        return capture_checkpoint('ready', bundle='app', read_layout=reader,
                                  is_ready=lambda state: state['ready'], capture_image=image,
                                  approved_images=scope)

    @patch('uitest_checkpoint.time.sleep')
    def test_uses_matching_sample_and_only_captures_approved_image(self, sleep):
        for scope in ({'ready'}, set()):
            matched = tree(ready=True)
            reader = Mock(side_effect=[tree(), matched])
            image = Mock()
            self.assertIs(self.capture(reader, image, scope), matched)
            self.assertEqual(reader.call_count, 2)
            if scope:
                image.assert_called_once_with('ready')
            else:
                image.assert_not_called()

    @patch('uitest_checkpoint.time.monotonic', side_effect=[0, 8])
    def test_unready_state_does_not_capture_an_image(self, clock):
        image = Mock()
        reader = Mock(return_value=tree())
        with self.assertRaisesRegex(CheckpointTimeout, 'ready'):
            self.capture(reader, image, {'ready'})
        reader.assert_called_once_with('ready')
        image.assert_not_called()

    @patch('uitest_checkpoint.time.sleep')
    @patch('uitest_checkpoint.time.monotonic', side_effect=[0, .1, .2, .3, .4, .5, .6, .95])
    def test_image_readiness_restarts_after_a_transient_state(self, clock, sleep):
        latest = tree(ready=True)
        reader = Mock(side_effect=[tree(ready=True), tree(), latest, latest, latest])
        image = Mock()
        receipt = Mock()
        result = capture_checkpoint('ready', bundle='app', read_layout=reader,
                                    is_ready=lambda state: state['ready'], capture_image=image,
                                    approved_images={'ready'}, image_ready_seconds=.3,
                                    record_arrival=receipt)
        self.assertIs(result, latest)
        self.assertEqual(reader.call_count, 5)
        image.assert_called_once_with('ready')
        receipt.assert_called_once_with('ready', latest)

    def test_formal_screenshot_requires_same_app_and_state_after_capture(self):
        matched = tree(ready=True)
        confirmed = {**matched, 'capture_tree': 'after'}
        for after, error in ((confirmed, None), (tree(), CheckpointTimeout),
                             (tree(ready=True, bundle='different'), ForegroundError)):
            with self.subTest(after=after):
                reader, image, receipt = Mock(side_effect=[matched, after]), Mock(), Mock()
                options = dict(bundle='app', read_layout=reader, is_ready=lambda state: state['ready'],
                               capture_image=image, approved_images={'ready'}, record_arrival=receipt)
                if error:
                    with self.assertRaises(error):
                        capture_checkpoint('ready', **options)
                    receipt.assert_not_called()
                else:
                    self.assertIs(capture_checkpoint('ready', **options), confirmed)
                    receipt.assert_called_once_with('ready', confirmed)
                self.assertEqual(reader.call_count, 2)
                image.assert_called_once_with('ready')

    @patch('uitest_checkpoint.time.monotonic', side_effect=[0, 9, 0, 9])
    def test_a_late_ready_sample_cannot_pass_or_trigger_a_screenshot(self, clock):
        for scope in (set(), {'ready'}):
            reader, image = Mock(return_value=tree(ready=True)), Mock()
            with self.assertRaises(CheckpointTimeout):
                self.capture(reader, image, scope)
            image.assert_not_called()

    def test_foreground_change_and_transport_timeout_stop_immediately(self):
        image = Mock()
        reader = Mock(return_value=tree(ready=True, bundle='system'))
        with self.assertRaises(ForegroundError):
            self.capture(reader, image, None)
        reader.assert_called_once_with('ready')
        timeout = TimeoutExpired(['hdc', 'private input'], 35)
        reader = Mock(side_effect=timeout)
        with self.assertRaises(TimeoutExpired) as caught:
            self.capture(reader, image, None)
        self.assertEqual(device_timeout_details(caught.exception), {'seconds': 35})
        reader.assert_called_once_with('ready')
        image.assert_not_called()


if __name__ == '__main__':
    unittest.main()
