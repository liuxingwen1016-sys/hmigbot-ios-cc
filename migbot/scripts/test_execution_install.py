import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
INSTALLER = ROOT / "migbot/scripts/migbot-install.py"


class ExecutionInstallTests(unittest.TestCase):
    def test_launcher_sanitizes_settings_and_passes_routing_to_fake_cli(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            settings = project / "settings.json"
            settings.write_text(json.dumps({
                "model": "claude-fable-5-1", "effortLevel": "max",
                "permissions": {"deny": ["Read(secret-file)"]},
                "env": {
                    "ANTHROPIC_AUTH_TOKEN": "dummy-test-token",
                    "ANTHROPIC_BASE_URL": "https://invalid.example.test",
                    "ANTHROPIC_DEFAULT_HAIKU_MODEL": "claude-fable-5-1",
                    "CLAUDE_CODE_EFFORT_LEVEL": "max",
                    "CLAUDE_CODE_SUBAGENT_MODEL_FORCE": "1",
                },
            }))
            original = settings.read_bytes()
            prompt = project / "prompt.txt"
            prompt.write_text("Offline integration test; no network access.")
            fake = project / "fake-claude"
            fake.write_text("""#!/usr/bin/env python3
import json, os, pathlib, sys
args = sys.argv
cfg_path = args[args.index('--settings') + 1]
cfg = json.loads(pathlib.Path(cfg_path).read_text())
captured = {'model': args[args.index('--model') + 1],
 'effort': args[args.index('--effort') + 1],
 'max_turns': args[args.index('--max-turns') + 1],
 'max_budget': args[args.index('--max-budget-usd') + 1],
 'haiku': cfg['env']['ANTHROPIC_DEFAULT_HAIKU_MODEL'],
 'sonnet': cfg['env']['ANTHROPIC_DEFAULT_SONNET_MODEL'],
 'has_force': 'CLAUDE_CODE_SUBAGENT_MODEL_FORCE' in cfg['env'],
 'has_global_effort': 'CLAUDE_CODE_EFFORT_LEVEL' in cfg['env'],
 'auth_preserved': cfg['env'].get('ANTHROPIC_AUTH_TOKEN') == 'dummy-test-token',
 'permissions': cfg['permissions'], 'temp_settings': cfg_path}
pathlib.Path('captured.json').write_text(json.dumps(captured))
print(json.dumps({'type':'result','uuid':'fake-route-result','session_id':'fake-route-session',
 'num_turns':1,'total_cost_usd':0.01,'usage':{'input_tokens':1,'output_tokens':1},
 'modelUsage':{captured['model']:{'inputTokens':1,'outputTokens':1,
 'cacheReadInputTokens':0,'cacheCreationInputTokens':0,'costUSD':0.01}}}), flush=True)
""")
            fake.chmod(0o755)
            result = subprocess.run([
                sys.executable, "-B", str(ROOT / "migbot/scripts/run_claude_task.py"),
                "offline-integration", "--task-id", "offline-integration", "--cwd", str(project),
                "--prompt-file", str(prompt), "--settings", str(settings),
                "--claude-bin", str(fake), "--profile", "search",
            ], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            captured = json.loads((project / "captured.json").read_text())
            self.assertEqual((captured["model"], captured["effort"]), ("claude-haiku-5-5", "low"))
            self.assertEqual(captured["haiku"], "claude-haiku-5-5")
            self.assertEqual(captured["sonnet"], "claude-sonnet-5-5")
            self.assertFalse(captured["has_force"])
            self.assertFalse(captured["has_global_effort"])
            self.assertTrue(captured["auth_preserved"])
            self.assertEqual(captured["permissions"], {"deny": ["Read(secret-file)"]})
            self.assertEqual(settings.read_bytes(), original)
            self.assertFalse(Path(captured["temp_settings"]).exists())
            self.assertNotIn("dummy-test-token", result.stdout + result.stderr)

    def test_incomplete_routing_package_is_rejected(self):
        spec = importlib.util.spec_from_file_location("installer", INSTALLER)
        installer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(installer)
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, "missing execution runtime"):
                installer.validate_execution_runtime(Path(temporary))

    def test_install_upgrade_and_offline_routing_preserve_user_configuration(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            user_agent = project / ".claude/agents/my-user-agent.md"
            user_agent.parent.mkdir(parents=True)
            user_agent.write_text("user-owned-agent\n")
            settings = project / ".claude/settings.json"
            settings.write_text('{"model":"my-existing-model"}\n')
            marker = project / "spec/baseline/already-approved.json"
            marker.parent.mkdir(parents=True)
            marker.write_text('{"accepted":true}\n')
            originals = {p: p.read_bytes() for p in (user_agent, settings, marker)}

            def install():
                result = subprocess.run(
                    [sys.executable, "-B", str(INSTALLER), "--project", str(project)],
                    capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout[-1500:])

            install()
            source_runtime = ROOT / "migbot"
            installed = project / ".migbot/runtime"
            relative_files = [
                "config/execution-policy.json", "scripts/execution_policy.py",
                "scripts/claude_task_guard.py", "scripts/run_claude_task.py",
                "references/execution-policy.md",
            ]
            for relative in relative_files:
                self.assertEqual((installed / relative).read_bytes(),
                                 (source_runtime / relative).read_bytes(), relative)
            for source in (source_runtime / "agents").glob("*.md"):
                self.assertEqual((project / ".claude/agents" / source.name).read_bytes(),
                                 source.read_bytes())
            prompt = project / "task.txt"
            prompt.write_text("Do not run; this is an offline route check.")
            for profile, model, effort in (
                ("search", "claude-haiku-5-5", "low"),
                ("implementation", "claude-sonnet-5-5", "medium"),
                ("complex", "claude-opus-5-5", "high"),
                ("expert", "claude-fable-5-1", "max"),
            ):
                result = subprocess.run([
                    sys.executable, "-B", str(installed / "scripts/run_claude_task.py"),
                    "offline-check", "--cwd", str(project), "--prompt-file", str(prompt),
                    "--task-id", "offline-check", "--profile", profile,
                    "--claude-bin", "/this-binary-must-never-run", "--dry-run",
                ], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                plan = json.loads(result.stdout)
                self.assertEqual((plan["model"], plan["effort"]), (model, effort))
            self.assertFalse((project / ".migbot/execution").exists())
            # Upgrade repairs shipped files, but preserves user files and frozen data.
            (installed / "config/execution-policy.json").write_text("damaged shipped copy")
            install()
            self.assertEqual((installed / "config/execution-policy.json").read_bytes(),
                             (source_runtime / "config/execution-policy.json").read_bytes())
            for path, expected in originals.items():
                self.assertEqual(path.read_bytes(), expected)


if __name__ == "__main__":
    unittest.main()
