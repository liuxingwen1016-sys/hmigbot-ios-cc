from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ios_capture_job import HANDOFF, encode, job_path, join


@unittest.skipUnless(os.name == 'posix', 'XCUITest host requires POSIX process locks')
class CaptureJobJoinTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name).resolve()
        self.job = job_path(self.project, 'test-join')
        (self.job / 'states').mkdir(parents=True)
        self.plan = self.project / 'capture-plan.json'
        self.plan.write_bytes(encode({'states': ['source-state']}))
        self.manifest = self.job / 'states/capture-plan-manifest.json'
        self.manifest.write_bytes(encode({'status': 'captured', 'state_count': 1}))
        inputs = encode({'plan': str(self.plan), 'plan_sha256': sha256(self.plan.read_bytes()).hexdigest()})
        (self.job / 'inputs.json').write_bytes(inputs)
        (self.job / 'launch.json').write_bytes(encode({'pid': os.getpid()}))
        (self.job / 'result.json').write_bytes(encode({
            'status': 'captured', 'exit_code': 0, 'inputs_sha256': sha256(inputs).hexdigest(),
            'manifest_sha256': sha256(self.manifest.read_bytes()).hexdigest(),
        }))
        self.options = SimpleNamespace(project_root=self.project, job='test-join', timeout=0, publish=True)

    def test_publish_is_idempotent_and_preserves_the_first_handoff(self):
        target = self.project / HANDOFF
        self.assertEqual(join(self.options), 0)
        self.assertEqual(join(self.options), 0)
        self.assertEqual(target.read_bytes(), self.manifest.read_bytes())
        target.write_bytes(encode({'status': 'captured', 'state_count': 2}))
        with self.assertRaisesRegex(ValueError, 'another capture already owns'):
            join(self.options)

    def test_partial_publish_preserves_the_original_and_exit_code(self):
        self.manifest.write_bytes(encode({'status': 'partial', 'states': [
            {'page_id': 'Main', 'state_id': 'normal', 'status': 'captured'},
            {'page_id': 'Main', 'state_id': 'search', 'status': 'blocked'},
        ]}))
        result_path = self.job / 'result.json'
        result = json.loads(result_path.read_bytes())
        result.update(status='partial', exit_code=2,
                      manifest_sha256=sha256(self.manifest.read_bytes()).hexdigest())
        result_path.write_bytes(encode(result))
        self.assertEqual(join(self.options), 2)
        self.assertEqual((self.project / HANDOFF).read_bytes(), self.manifest.read_bytes())

    def test_stale_capture_plan_cannot_publish(self):
        self.plan.write_bytes(encode({'states': ['other-state']}))
        with self.assertRaisesRegex(ValueError, 'capture plan changed'):
            join(self.options)
        self.assertFalse((self.project / HANDOFF).exists())

    def test_terminal_receipt_can_be_joined_without_the_launch_file(self):
        (self.job / 'launch.json').unlink()
        self.assertEqual(join(self.options), 0)
        self.assertEqual((self.project / HANDOFF).read_bytes(), self.manifest.read_bytes())

    def test_start_can_reuse_the_actual_worker_and_later_its_result(self):
        scratch = self.project / 'tools'
        scratch.mkdir()
        script = scratch / 'ios_capture_job.py'
        scripts = Path(__file__).resolve().parents[1]
        shutil.copyfile(scripts / script.name, script)
        shutil.copyfile(scripts / 'ios_evidence_protocol.py', scratch / 'ios_evidence_protocol.py')
        (scratch / 'ios_runtime_capture_plan.py').write_text('''
import json
from pathlib import Path
import sys
import time

deadline = time.monotonic() + 10
while not Path("allow-finish").is_file() and time.monotonic() < deadline:
    time.sleep(.02)
if not Path("allow-finish").is_file():
    sys.exit(2)
root = Path(sys.argv[sys.argv.index("--output-root") + 1])
root.mkdir()
(root / "capture-plan-manifest.json").write_text(json.dumps({"status":"captured","state_count":1}))
''')
        with tempfile.TemporaryDirectory() as source_directory:
            source = Path(source_directory)
            (source / 'App.xcodeproj').mkdir()
            test_source = source / 'AppUITests.swift'
            test_source.write_text('// fixture')
            command = [sys.executable, '-B', str(script)]
            common = ['--project-root', str(self.project), '--job', 'reuse']
            start = [*command, 'start', *common, '--plan', str(self.plan), '--source-root', str(source),
                     '--xcode-project', 'App.xcodeproj', '--scheme', 'Fixture', '--device-id', self.project.name,
                     '--bundle-id', 'fixture.bundle', '--configuration-id', 'Fixture.Debug', '--scenario-id', 'test',
                     '--xctest-target', 'AppUITests', '--xctest-test-source', 'AppUITests.swift', '--reuse-existing']
            target = job_path(self.project, 'reuse')

            def execute(args, code=0):
                result = subprocess.run(args, text=True, capture_output=True, timeout=12)
                self.assertEqual(result.returncode, code, result.stdout + result.stderr)
                return json.loads(result.stdout) if code == 0 else result

            first = execute(start)
            try:
                second = execute(start)
                self.assertEqual(second['pid'], first['pid'])
                self.assertEqual(second['status'], 'EXISTING_LAUNCH')
                original = self.plan.read_bytes()
                self.plan.write_bytes(original + b' ')
                self.assertIn('different frozen inputs', execute(start, code=2).stderr)
                self.plan.write_bytes(original)
                test_source.write_text('// changed test probe')
                self.assertIn('different frozen inputs', execute(start, code=2).stderr)
                test_source.write_text('// fixture')
            finally:
                (target / 'allow-finish').touch()
                execute([*command, 'join', *common, '--timeout', '8'])
            self.assertEqual(execute(start)['status'], 'RESULT_AVAILABLE')
            self.assertEqual((target / 'capture-plan.json').read_bytes(), self.plan.read_bytes())
            test_source.write_text('// changed after capture')
            publish = [*command, 'join', *common, '--timeout', '0', '--publish']
            self.assertIn('source bytes changed', execute(publish, code=2).stderr)
            self.assertFalse((self.project / HANDOFF).exists())
            test_source.write_text('// fixture')
            self.assertEqual(execute(publish)['status'], 'captured')
