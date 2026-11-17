import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from zipfile import ZipFile

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

from host_build_checkpoint import diagnose
from lib.stage1_contract import digest, source_digest
from lib.host_verify_handoff import validate


class HostBuildCheckpointTests(unittest.TestCase):
    def test_real_compiler_count_wins_over_environment_words(self):
        log = (
            "> hvigor ERROR: Failed :entry:default@CompileArkTS...\r\n"
            "\x1b[31m1 ERROR: 10905402 ArkTS Compiler Error\r\n"
            "Error Message: expected one @Entry. At File: C:/app/Home.ets:2:5\r\n"
            "\x1b[31m2 ERROR: 10905402 ArkTS Compiler Error\r\n"
            "Error Message: expected one @Entry. At File: C:/app/Other.ets:3:5\r\n"
            "COMPILE RESULT:FAIL {ERROR:3 WARN:4}\r\n"
            "optional read: EPERM\r\n"
        )
        result = diagnose(log, 255)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["failed_task"], "entry:default@CompileArkTS")
        self.assertEqual((result["compiler_errors"], result["compiler_warnings"]), (3, 4))
        self.assertEqual(result["diagnostics"], [{"code": "10905402", "message": "expected one @Entry.", "count": 2}])

    def test_host_access_and_signing_are_distinct(self):
        denied = "> hvigor ERROR: Failed :entry:default@CompileArkTS...\nEPERM reading .ohpmrc"
        signing = "> hvigor ERROR: Failed :entry:default@SignHap...\nProfile invalid"
        self.assertEqual(diagnose(denied, 255)["status"], "BLOCKED")
        self.assertEqual(diagnose(signing, 255)["reason"], "signing_failed")

    def test_success_requires_exit_zero_and_hvigor_success(self):
        self.assertEqual(diagnose("> hvigor BUILD SUCCESSFUL", 0)["status"], "PASS")
        self.assertEqual(diagnose("> hvigor BUILD SUCCESSFUL", 1)["status"], "BLOCKED")
        self.assertEqual(diagnose("completed", 0)["status"], "BLOCKED")

    def test_cli_binds_log_and_rejects_changed_input(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            output = project / "spec/execution"
            output.mkdir(parents=True)
            source = project / "Index.ets"
            source.write_text("before", encoding="utf-8")
            log, report = output / "compile.log", output / "compile.json"
            command = (
                "from pathlib import Path; Path('Index.ets').write_text('after'); "
                "print('> hvigor BUILD SUCCESSFUL')"
            )
            result = subprocess.run(
                [sys.executable, "-B", str(SCRIPTS / "host_build_checkpoint.py"), "--project-root", str(project),
                 "--log", str(log), "--out", str(report), "--", sys.executable, "-c", command],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 2, result.stderr)
            data = json.loads(report.read_bytes())
            self.assertEqual(data["reason"], "build_inputs_changed")
            self.assertNotEqual(data["source_sha256"], data["source_after_sha256"])
            self.assertEqual(data["log"]["sha256"], digest(log))


    def test_installation_replay_checks_source_package_device_and_original_logs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source = root / 'Index.ets'
            source.write_text('source before install')
            evidence = root / 'spec'
            evidence.mkdir()

            def write(name, data):
                path = evidence / name
                path.write_text(data if isinstance(data, str) else json.dumps(data))
                return {'path': path.relative_to(root).as_posix(), 'sha256': digest(path)}

            bundle, version = 'fixture.app', 123
            hap = root / 'app.hap'
            with ZipFile(hap, 'w') as package:
                package.writestr('module.json', json.dumps({'app': {'bundleName': bundle, 'versionCode': version}}))
            scope = write('scope.json', {'source_sha256': source_digest(root)})
            build_log = write('build.log', '> hvigor BUILD SUCCESSFUL')
            signature_log = write('signature.log', 'INFO - verify-app success')
            install_log = write('install.log', 'msg:install bundle successfully.\nAppMod finish')
            identity_log = write('bundle.log', 'fixture.app:\n' + json.dumps({'name': bundle, 'versionCode': version}))
            common = {'status': 'PASS', 'scope_sha256': scope['sha256'], 'source_sha256': source_digest(root),
                      'hap_path': 'app.hap', 'hap_sha256': digest(hap)}
            build = write('build.json', {**common, 'kind': 'build', 'build_log': build_log, 'signature_log': signature_log})
            installation = {**common, 'kind': 'install', 'device_id': 'sim', 'bundle': bundle,
                            'version_code': version, 'install_log': install_log, 'identity_log': identity_log}
            handoff = {'schema_version': 1, 'scope': scope, 'build_receipt': build,
                       'install_receipt': write('install.json', installation)}
            self.assertEqual(validate(root, handoff), {'hap_sha256': digest(hap).removeprefix('sha256:'),
                'device': 'sim', 'bundle': bundle, 'version_code': version})
            handoff['install_receipt'] = write('install.json', {**installation, 'hap_sha256': 'sha256:' + 'a' * 64})
            with self.assertRaisesRegex(ValueError, 'different HAPs'):
                validate(root, handoff)
            handoff['install_receipt'] = write('install.json', installation)
            (evidence / 'bundle.log').write_text('modified device output')
            with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
                validate(root, handoff)
            source.write_text('source after install')
            with self.assertRaisesRegex(ValueError, 'stale for current source'):
                validate(root, handoff)


if __name__ == "__main__":
    unittest.main()
