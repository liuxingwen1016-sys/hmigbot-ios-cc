import json
import plistlib
import tempfile
import unittest
from subprocess import CompletedProcess
from unittest.mock import patch
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import identity_signing_preflight as gate

class Tests(unittest.TestCase):
    def make_project(self, target='com.example.cuiketemp'):
        td=tempfile.TemporaryDirectory(); root=Path(td.name)
        (root/'AppScope').mkdir()
        (root/'AppScope/app.json5').write_text('{"app":{"bundleName":"%s",}}' % target)
        profile=root/'profile.p7b'; profile.write_bytes(b'profile')
        (root/'build-profile.json5').write_text('{"app":{"signingConfigs":[{"material":{"profile":"%s"}}]}}' % profile)
        return td,root,profile
    def test_pending_on_profile_mismatch(self):
        td,root,profile=self.make_project('com.liuxingwen.cuike')
        self.addCleanup(td.cleanup)
        old_which,old_run=gate.shutil.which,gate.subprocess.run
        gate.shutil.which=lambda _: '/usr/bin/security'
        gate.subprocess.run=lambda *a,**k: type('R',(),{'returncode':0,'stdout':json.dumps({'bundle-info':{'bundle-name':'com.example.cuiketemp'}}),'stderr':''})()
        try:
            out=gate.evaluate(root,source_id='com.liuxingwen.cuike')
        finally:
            gate.shutil.which,gate.subprocess.run=old_which,old_run
        self.assertEqual(out['identity_status'],'identity_signing_pending')
        self.assertFalse(out['signed_install_allowed'])
        self.assertTrue(out['unsigned_compile_allowed'])
    def test_pass_requires_non_example_match(self):
        td,root,profile=self.make_project('com.liuxingwen.cuike')
        self.addCleanup(td.cleanup)
        old_which,old_run=gate.shutil.which,gate.subprocess.run
        gate.shutil.which=lambda _: '/usr/bin/security'
        gate.subprocess.run=lambda *a,**k: type('R',(),{'returncode':0,'stdout':json.dumps({'bundle-info':{'bundle-name':'com.liuxingwen.cuike'}}),'stderr':''})()
        try:
            out=gate.evaluate(root,source_id='com.liuxingwen.cuike')
        finally:
            gate.shutil.which,gate.subprocess.run=old_which,old_run
        self.assertEqual(out['identity_status'],'PASS')
        self.assertTrue(out['signed_install_allowed'])

    def test_template_match_allows_diagnostic_signed_install_but_stays_pending(self):
        td,root,profile=self.make_project('com.example.cuiketemp')
        self.addCleanup(td.cleanup)
        old_which,old_run=gate.shutil.which,gate.subprocess.run
        gate.shutil.which=lambda _: '/usr/bin/security'
        gate.subprocess.run=lambda *a,**k: type('R',(),{'returncode':0,'stdout':json.dumps({'bundle-info':{'bundle-name':'com.example.cuiketemp'}}),'stderr':''})()
        try:
            out=gate.evaluate(root,source_id='com.cuike.brew')
        finally:
            gate.shutil.which,gate.subprocess.run=old_which,old_run
        self.assertEqual(out['identity_status'],'identity_signing_pending')
        self.assertTrue(out['signed_install_allowed'])
    def test_source_bundle_id_from_info_plist(self):
        td,root,profile=self.make_project()
        self.addCleanup(td.cleanup)
        source=root/'ios'; source.mkdir();
        with (source/'Info.plist').open('wb') as f: plistlib.dump({'CFBundleIdentifier':'com.example.source'},f)
        self.assertEqual(gate.source_bundle_id(source),'com.example.source')

    def test_openssl_recovers_diagnostic_profile_without_approving_wrong_source_identity(self):
        td, root, profile = self.make_project('www.TestDemo.myapplication')
        self.addCleanup(td.cleanup)
        payload = json.dumps({'bundle-info': {'bundle-name': 'www.TestDemo.myapplication'}})
        responses = [
            CompletedProcess([], 1, '', 'security: problem decoding'),
            CompletedProcess([], 0, payload, 'CMS Verification successful'),
        ]
        with patch.object(gate.shutil, 'which', side_effect=lambda name: name), \
                patch.object(gate.subprocess, 'run', side_effect=responses) as run:
            report = gate.evaluate(root, source_id='com.cuike.brew')
        self.assertEqual(run.call_args.args[0], [
            'openssl', 'cms', '-verify', '-inform', 'DER', '-in', str(profile), '-noverify',
        ])
        self.assertEqual(report['identity_status'], 'identity_signing_pending')
        self.assertTrue(report['signed_install_allowed'])
        self.assertEqual(report['signing_profile_bundle_name'], 'www.TestDemo.myapplication')

    def test_profile_shape_errors_are_diagnostic(self):
        for value in ([], {'bundle-info': None}):
            name, error = gate.bundle_name_from_payload(json.dumps(value))
            self.assertIsNone(name)
            self.assertIn('bundle-info.bundle-name', error)

if __name__=='__main__': unittest.main()
