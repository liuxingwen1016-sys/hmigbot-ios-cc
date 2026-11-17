"""Offline policy/guardian contract tests. Children are local Python mocks only."""

import argparse
import dataclasses
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from claude_task_guard import EXIT_BUDGET, EXIT_LOCKED, EXIT_TIMEOUT, ledger_path, remaining_command
from execution_policy import (
    MODELS, add_execution_arguments, apply_execution_command, apply_execution_environment,
    execution_prompt, guard_command, resolve_execution,
)


def route(*options):
    parser = argparse.ArgumentParser()
    add_execution_arguments(parser)
    return resolve_execution(parser.parse_args(["--task-id", "offline-task", *options]))


def message(message_id, **usage):
    return {"type": "assistant", "session_id": "session-one", "message": {
        "id": message_id, "model": MODELS["sonnet"], "usage": usage,
    }}


def result(result_id, cost, turns, **extra):
    return {"type": "result", "uuid": result_id, "session_id": "session-one",
            "num_turns": turns, "total_cost_usd": cost, "is_error": False, **extra}


def mock_command(events, exit_code=0, suffix=""):
    data = "".join(json.dumps(event) + "\n" for event in events)
    code = "import sys; sys.stdout.write(" + repr(data) + "); sys.stdout.flush(); "
    code += suffix + "; " if suffix else ""
    code += f"sys.exit({exit_code})"
    return [sys.executable, "-c", code]


class PolicyTests(unittest.TestCase):
    def test_profiles_and_model_overrides_use_real_ids_and_efforts(self):
        expected = {"search": ("haiku", "low", 10, .5, 300),
                    "deterministic": ("haiku", "low", 10, .5, 300),
                    "implementation": ("sonnet", "medium", 25, 3, 900),
                    "complex": ("opus", "high", 30, 8, 1200),
                    "expert": ("fable", "max", 30, 12, 1200)}
        self.assertEqual(route().profile, "implementation")
        for profile, (family, effort, turns, cost, timeout) in expected.items():
            with self.subTest(profile=profile):
                selected = route("--profile", profile)
                self.assertEqual((selected.model, selected.effort, selected.max_turns,
                                  selected.max_budget_usd, selected.timeout_seconds),
                                 (MODELS[family], effort, turns, cost, timeout))
                for model in (family, MODELS[family]):
                    overridden = route("--model", model)
                    self.assertEqual((overridden.model, overridden.effort), (MODELS[family], effort))
        self.assertEqual(route("--model", "opus", "--effort", "low").effort, "low")

    def test_numeric_limits_reject_nan_inf_zero_negative_and_fractional_turns(self):
        for flag in ("--max-turns", "--max-budget-usd", "--timeout-seconds"):
            for value in ("nan", "NaN", "inf", "-inf", "0", "-1"):
                with self.subTest(flag=flag, value=value), self.assertRaises(argparse.ArgumentTypeError):
                    resolve_execution(argparse.Namespace(profile="implementation", task_id="t",
                                                         **{flag[2:].replace("-", "_"): value}))
        with self.assertRaises(argparse.ArgumentTypeError):
            resolve_execution(argparse.Namespace(task_id="t", max_turns=1.5))
        with self.assertRaises(argparse.ArgumentTypeError):
            resolve_execution(argparse.Namespace(task_id="t", timeout_seconds=True))

    def test_missing_task_id_requires_a_stable_stage(self):
        with self.assertRaisesRegex(ValueError, "task-id"):
            resolve_execution(argparse.Namespace())
        self.assertEqual(resolve_execution(argparse.Namespace(stage="repair-home")).task_id,
                         "repair-home")
        with self.assertRaises(ValueError):
            resolve_execution(argparse.Namespace(task_id="bad\nidentity"))
        with self.assertRaises(ValueError):
            resolve_execution(argparse.Namespace(task_id="t", model="unknown-model"))

    def test_environment_keeps_credentials_and_proxy_but_removes_model_forces(self):
        env = {"ANTHROPIC_AUTH_TOKEN": "secret-placeholder", "ANTHROPIC_BASE_URL": "local-fixture",
               "ANTHROPIC_FORCE_PROXY": "yes", "PATH": "/bin", "_FORCE": "fable",
               "CLAUDE_CODE_EFFORT_LEVEL": "max", "CLAUDE_CODE_SUBAGENT_MODEL": "fable",
               "CLAUDE_CODE_SUBAGENT_EFFORT": "max", "MAX_THINKING_TOKENS": "99999",
               "CLAUDE_CODE_FORCE_OPUS": "1", "ANTHROPIC_MODEL": "fable",
               "ANTHROPIC_DEFAULT_HAIKU_MODEL": "fable"}
        selected = apply_execution_environment(env, route("--profile", "expert"))
        for key in ("ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "ANTHROPIC_FORCE_PROXY", "PATH"):
            self.assertEqual(selected[key], env[key])
        for key in ("_FORCE", "CLAUDE_CODE_EFFORT_LEVEL", "CLAUDE_CODE_SUBAGENT_EFFORT",
                    "CLAUDE_CODE_FORCE_OPUS", "ANTHROPIC_MODEL", "MAX_THINKING_TOKENS"):
            self.assertNotIn(key, selected)
        self.assertEqual(selected["CLAUDE_CODE_SUBAGENT_MODEL"], MODELS["sonnet"])
        self.assertEqual(selected["CLAUDE_CODE_AUTO_COMPACT_WINDOW"], "100000")
        for family, model in MODELS.items():
            self.assertEqual(selected[f"ANTHROPIC_DEFAULT_{family.upper()}_MODEL"], model)
        self.assertEqual(env["CLAUDE_CODE_EFFORT_LEVEL"], "max")

    def test_command_replaces_routing_and_caps_preserving_permissions_and_prompt(self):
        selected = route("--profile", "search")
        cmd = ["claude", "--model=old", "--effort", "max", "--max-turns", "99",
               "--max-budget-usd=90", "--allowedTools", "Read", "--", "--model=literal-prompt"]
        actual = apply_execution_command(cmd, selected)
        self.assertEqual(actual[-2:], ["--", "--model=literal-prompt"])
        self.assertEqual(actual[:3], ["claude", "--allowedTools", "Read"])
        for flag, value in (("--model", MODELS["haiku"]), ("--effort", "low"),
                            ("--max-turns", "10"), ("--max-budget-usd", "0.5")):
            self.assertEqual(actual.count(flag), 1)
            self.assertEqual(actual[actual.index(flag) + 1], value)
        wrapped = guard_command(["sandbox-exec", "-f", "restricted.sb", *actual],
                                selected, ".", "fixture")
        self.assertEqual(wrapped[wrapped.index("--") + 1:],
                         ["sandbox-exec", "-f", "restricted.sb", *actual])
        self.assertIn("two rounds without progress", execution_prompt(selected))


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.run_dir = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def run_mock(self, events, selected=None, exit_code=0, suffix=""):
        selected = selected or route()
        return subprocess.run(guard_command(mock_command(events, exit_code, suffix), selected,
                                            self.run_dir, "mock-stage"),
                              capture_output=True, timeout=8)

    def ledger(self):
        return json.loads(ledger_path(self.run_dir, "offline-task").read_text())

    def test_resume_deduplicates_message_ids_and_cumulative_model_usage_and_cost(self):
        first_message = message("m1", input_tokens=10, output_tokens=2,
                                cache_read_input_tokens=4, cache_creation_input_tokens=3)
        usage1 = {MODELS["sonnet"]: {"inputTokens": 10, "outputTokens": 2,
                                   "cacheReadInputTokens": 4, "cacheCreationInputTokens": 3,
                                   "costUSD": .2}}
        terminal1 = result("r1", .2, 1, modelUsage=usage1)
        first = self.run_mock([first_message, terminal1, terminal1])
        self.assertEqual(first.returncode, 0, first.stderr)
        usage2 = {MODELS["sonnet"]: {"inputTokens": 20, "outputTokens": 4,
                                   "cacheReadInputTokens": 8, "cacheCreationInputTokens": 6,
                                   "costUSD": .35}}
        second = self.run_mock([first_message, terminal1,
                                message("m2", input_tokens=10, output_tokens=2,
                                        cache_read_input_tokens=4, cache_creation_input_tokens=3),
                                result("r2", .35, 1, modelUsage=usage2)])
        self.assertEqual(second.returncode, 0, second.stderr)
        ledger = self.ledger()
        self.assertEqual(len(ledger["attempts"]), 2)
        self.assertEqual(ledger["num_turns"], 2)
        self.assertEqual(ledger["estimated_cost_usd"], .35)
        self.assertEqual(ledger["usage"], {"input_tokens": 20, "output_tokens": 4,
                                          "cache_read_input_tokens": 8,
                                          "cache_creation_input_tokens": 6})
        self.assertTrue(ledger["cost_complete"])

    def test_budget_exhaustion_blocks_resume_and_cannot_be_enlarged_by_new_arguments(self):
        selected = route("--max-budget-usd", "0.3")
        self.assertEqual(self.run_mock([result("r1", .3, 1)], selected).returncode, 0)
        marker = self.run_dir / "should-not-run"
        denied = self.run_mock([result("r2", .4, 2)], route("--max-budget-usd", "99"),
                               suffix=f"open({str(marker)!r}, 'w').close()")
        self.assertEqual(denied.returncode, EXIT_BUDGET, denied.stderr)
        self.assertFalse(marker.exists())
        self.assertEqual(len(self.ledger()["attempts"]), 1)
        self.assertEqual(self.ledger()["limits"]["max_budget_usd"], .3)

    def test_turns_and_wallclock_are_cumulative(self):
        selected = route("--max-turns", "1")
        self.assertEqual(self.run_mock([result("r1", .1, 1)], selected).returncode, 0)
        self.assertEqual(self.run_mock([result("r2", .1, 1)], selected).returncode, EXIT_BUDGET)
        self.assertEqual(self.ledger()["num_turns"], 1)

    def test_result_only_attempts_count_independent_turns_without_assistant_messages(self):
        selected = route("--max-turns", "2")
        self.assertEqual(self.run_mock([result("r1", .1, 1)], selected).returncode, 0)
        self.assertEqual(self.run_mock([result("r2", .2, 1)], selected).returncode, 0)
        self.assertEqual(self.ledger()["num_turns"], 2)
        self.assertEqual(self.run_mock([result("r3", .3, 1)], selected).returncode, EXIT_BUDGET)

    def test_remaining_limits_preserve_literal_prompt_after_double_dash(self):
        command = ["sandbox-exec", "-f", "fixture.sb", "claude", "--max-turns", "25",
                   "--max-budget-usd=3", "--", "--max-turns", "literal-prompt"]
        changed = remaining_command(command, 4, .2)
        self.assertEqual(changed[:4], command[:4])
        self.assertEqual(changed[4:7], ["--max-turns", "4", "--max-budget-usd=0.2"])
        self.assertEqual(changed[7:], command[7:])

    def test_failure_preserves_known_input_cache_and_unknown_output_and_cost(self):
        failed = self.run_mock([message("m1", input_tokens=11,
                                        cache_read_input_tokens=7,
                                        cache_creation_input_tokens=5)], exit_code=7)
        self.assertEqual(failed.returncode, 7)
        ledger = self.ledger()
        self.assertEqual(ledger["usage"]["input_tokens"], 11)
        self.assertEqual(ledger["usage"]["cache_read_input_tokens"], 7)
        self.assertEqual(ledger["usage"]["cache_creation_input_tokens"], 5)
        self.assertIsNone(ledger["usage"]["output_tokens"])
        self.assertIsNone(ledger["estimated_cost_usd"])
        self.assertFalse(ledger["cost_complete"])
        self.assertEqual(self.run_mock([result("r2", .1, 1)]).returncode, EXIT_BUDGET)

    def test_partial_stream_event_usage_survives_missing_terminal_result(self):
        events = [
            {"type": "stream_event", "session_id": "session-one", "event": {
                "type": "message_start", "message": {"id": "m1", "model": MODELS["sonnet"],
                                                        "usage": {"input_tokens": 13,
                                                                  "cache_read_input_tokens": 8}}}},
            {"type": "stream_event", "session_id": "session-one", "event": {
                "type": "message_delta", "usage": {"output_tokens": 3}}},
            {"type": "stream_event", "session_id": "session-one", "event": {
                "type": "message_delta", "usage": {"output_tokens": 5}}},
        ]
        failed = self.run_mock(events)
        self.assertNotEqual(failed.returncode, 0)
        self.assertEqual(self.ledger()["usage"]["output_tokens"], 5)
        self.assertEqual(self.ledger()["usage"]["input_tokens"], 13)
        self.assertFalse(self.ledger()["cost_complete"])

    def test_assistant_zero_output_is_unknown_without_terminal_accounting(self):
        failed = self.run_mock([message("m1", input_tokens=11, output_tokens=0,
                                        cache_creation_input_tokens=4)], exit_code=1)
        self.assertEqual(failed.returncode, 1)
        self.assertIsNone(self.ledger()["usage"]["output_tokens"])
        self.assertFalse(self.ledger()["usage_complete"]["output_tokens"])
        self.assertEqual(self.ledger()["usage"]["input_tokens"], 11)
        self.assertEqual(self.ledger()["usage"]["cache_creation_input_tokens"], 4)

    def test_terminal_usage_saves_output_when_model_usage_is_missing(self):
        completed = self.run_mock([message("m1", input_tokens=11, output_tokens=0),
                                   result("r1", .15, 1, usage={"input_tokens": 11,
                                                              "output_tokens": 7,
                                                              "cache_read_input_tokens": 2})])
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(self.ledger()["usage"]["output_tokens"], 7)
        self.assertFalse(self.ledger()["usage_complete"]["output_tokens"])

    def test_main_loop_result_usage_adds_independent_turns_as_incomplete_lower_bound(self):
        first = self.run_mock([message("m1", output_tokens=0),
                               result("r1", .1, 1, usage={"output_tokens": 7})])
        self.assertEqual(first.returncode, 0, first.stderr)
        second = self.run_mock([message("m2", output_tokens=0),
                                result("r2", .2, 1, usage={"output_tokens": 3})])
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(self.ledger()["usage"]["output_tokens"], 10)
        self.assertFalse(self.ledger()["usage_complete"]["output_tokens"])

    def test_old_model_usage_snapshot_does_not_cover_new_partial_output(self):
        first = self.run_mock([message("m1", output_tokens=0), result("r1", .1, 1, modelUsage={
            MODELS["sonnet"]: {"outputTokens": 7, "costUSD": .1}})])
        self.assertEqual(first.returncode, 0, first.stderr)
        second = self.run_mock([message("m2", input_tokens=2, output_tokens=0)], exit_code=1)
        self.assertEqual(second.returncode, 1)
        self.assertEqual(self.ledger()["usage"]["output_tokens"], 7)
        self.assertFalse(self.ledger()["usage_complete"]["output_tokens"])

    def test_zero_cost_zero_turn_terminal_errors_have_a_finite_attempt_budget(self):
        events = [result("free-result", 0, 0, is_error=True)]
        for _ in range(3):
            self.assertEqual(self.run_mock(events).returncode, 1)
        self.assertEqual(self.run_mock(events).returncode, EXIT_BUDGET)
        self.assertEqual(len(self.ledger()["attempts"]), 3)

    def test_binary_stdout_is_transparent_and_stderr_does_not_dump_environment(self):
        payload = b"\xff\x00fixture\n" + json.dumps(result("r1", .1, 1)).encode() + b"\n"
        command = [sys.executable, "-c", "import sys; sys.stdout.buffer.write(" + repr(payload) + ")"]
        env = dict(os.environ, ANTHROPIC_AUTH_TOKEN="never-echo-this-fixture-secret",
                   ANTHROPIC_BASE_URL="fixture-private-endpoint")
        completed = subprocess.run(guard_command(command, route(), self.run_dir, "binary"),
                                   capture_output=True, env=env, timeout=5)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, payload)
        self.assertNotIn(b"never-echo", completed.stderr)
        self.assertNotIn(b"fixture-private", completed.stderr)

    def test_watchdog_kills_process_group_including_a_term_ignoring_parent(self):
        marker = self.run_dir / "surviving-descendant"
        descendant = f"import time; time.sleep(1.5); open({str(marker)!r}, 'w').close()"
        code = ("import signal,subprocess,sys,time; "
                "signal.signal(signal.SIGTERM,signal.SIG_IGN); "
                f"subprocess.Popen([{sys.executable!r},'-c',{descendant!r}]); "
                "print('started',flush=True); time.sleep(10)")
        completed = subprocess.run(guard_command([sys.executable, "-c", code],
                                                  route("--timeout-seconds", ".2"),
                                                  self.run_dir, "timeout"),
                                   capture_output=True, timeout=5)
        self.assertEqual(completed.returncode, EXIT_TIMEOUT, completed.stderr)
        self.assertEqual(completed.stdout, b"started\n")
        self.assertEqual(self.ledger()["attempts"][0]["status"], "timeout")
        time.sleep(.9)
        self.assertFalse(marker.exists())
        self.assertEqual(self.run_mock([result("r2", .1, 1)]).returncode, EXIT_BUDGET)

    def test_lock_prevents_concurrent_attempts(self):
        command = mock_command([], suffix="import time; time.sleep(.5)")
        # The first attempt need not reach a terminal result for locking to be tested.
        first = subprocess.Popen(guard_command(command, route(), self.run_dir, "concurrent"),
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        deadline = time.monotonic() + 3
        while not ledger_path(self.run_dir, "offline-task").exists() and time.monotonic() < deadline:
            time.sleep(.01)
        second = self.run_mock([result("r2", .1, 1)])
        self.assertEqual(second.returncode, EXIT_LOCKED, second.stderr)
        first.communicate(timeout=5)

    def test_backpressure_cannot_block_wallclock_or_signal_cleanup(self):
        for mode in ("timeout", "signal"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temp:
                code = "import os,time; os.write(1,b'x'*(4*1024*1024)); time.sleep(20)"
                selected = route("--timeout-seconds", ".2" if mode == "timeout" else "10")
                child = subprocess.Popen(guard_command([sys.executable, "-c", code], selected,
                                                       temp, "backpressure"),
                                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                try:
                    if mode == "signal":
                        deadline = time.monotonic() + 2
                        while not ledger_path(temp, selected.task_id).exists() and time.monotonic() < deadline:
                            time.sleep(.01)
                        time.sleep(.15)
                        child.send_signal(signal.SIGTERM)
                    # Deliberately do not read stdout until the guardian has exited.
                    child.wait(timeout=2)
                    self.assertEqual(child.returncode, EXIT_TIMEOUT if mode == "timeout" else 143)
                    data = json.loads(ledger_path(temp, selected.task_id).read_text())
                    self.assertEqual(data["attempts"][0]["status"], mode if mode == "timeout" else "interrupted")
                    self.assertIn("output_truncated", data["attempts"][0])
                    self.assertLessEqual(data["attempts"][0]["output_truncated"]["stdout"],
                                         1024 * 1024 + 65536)
                finally:
                    if child.poll() is None:
                        child.kill()
                    child.communicate(timeout=3)

    def test_cli_error_still_records_cost_and_known_tokens(self):
        completed = self.run_mock([message("m1", input_tokens=17, cache_read_input_tokens=9),
                                   result("r1", .15, 1, is_error=True, subtype="error_max_turns")])
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(self.ledger()["estimated_cost_usd"], .15)
        self.assertEqual(self.ledger()["usage"]["input_tokens"], 17)
        self.assertIsNone(self.ledger()["usage"]["output_tokens"])


if __name__ == "__main__":
    unittest.main()
