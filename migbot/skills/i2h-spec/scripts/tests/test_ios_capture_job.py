from hashlib import sha256
import os
from pathlib import Path
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

    def test_stale_capture_plan_cannot_publish(self):
        self.plan.write_bytes(encode({'states': ['other-state']}))
        with self.assertRaisesRegex(ValueError, 'capture plan changed'):
            join(self.options)
        self.assertFalse((self.project / HANDOFF).exists())
