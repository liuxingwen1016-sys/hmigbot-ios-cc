#!/usr/bin/env python3
"""Launch one explicitly assigned Claude task using the shared routing policy."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile

from execution_policy import (
    MODELS, PROFILES, add_execution_arguments, apply_execution_command,
    apply_execution_environment, execution_prompt, guard_command, resolve_execution,
)


def sanitized_settings(settings: dict, route) -> dict:
    result = dict(settings)
    result["env"] = apply_execution_environment(settings.get("env", {}), route)
    result["model"] = route.model
    result.pop("effortLevel", None)
    effort_by_family = {item["model"]: item["effort"] for item in PROFILES.values()}
    rows = {key: dict(value) for key, value in settings.get("modelSettings", {}).items()}
    for family, model in MODELS.items():
        rows.setdefault(model, {})["effortLevel"] = effort_by_family[family]
    result["modelSettings"] = rows
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", help="Evidence label; task ID remains stable across retries.")
    parser.add_argument("--cwd", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, help="Stable ledger root; defaults to CWD/.migbot/execution.")
    parser.add_argument("--prompt-file", type=Path, required=True)
    parser.add_argument("--plugin", type=Path)
    parser.add_argument("--resume")
    parser.add_argument("--settings", type=Path, default=Path.home() / ".claude/settings.json")
    parser.add_argument("--claude-bin", default="claude")
    parser.add_argument("--dry-run", action="store_true", help="Print a credential-free plan; never launch Claude.")
    parser.add_argument("--permission-mode", help="Explicit Claude permission mode; otherwise retain user settings.")
    add_execution_arguments(parser)
    args = parser.parse_args(argv)
    if not args.task_id:
        parser.error("--task-id is required; reuse it and --run-dir across retries/resumes")
    route = resolve_execution(args)
    cwd = args.cwd.resolve()
    if not cwd.is_dir() or not args.prompt_file.is_file():
        parser.error("--cwd must be a directory and --prompt-file an existing file")
    run_dir = (args.run_dir or cwd / ".migbot/execution").resolve()
    cmd = [args.claude_bin, "--print", "--verbose", "--output-format", "stream-json",
           "--append-system-prompt", execution_prompt(route)]
    if args.plugin:
        cmd += ["--plugin-dir", str(args.plugin.resolve())]
    if args.resume:
        cmd += ["--resume", args.resume]
    if args.permission_mode:
        cmd += ["--permission-mode", args.permission_mode]
    cmd = apply_execution_command(cmd, route)
    if args.dry_run:
        print(json.dumps({
            "dry_run": True, "stage": args.stage, "task_id": route.task_id,
            "profile": route.profile, "model": route.model, "effort": route.effort,
            "max_turns": route.max_turns, "max_budget_usd_cli_estimate": route.max_budget_usd,
            "timeout_seconds": route.timeout_seconds, "cwd": str(cwd),
            "run_dir": str(run_dir), "resume": bool(args.resume),
            "subagent_default": MODELS["sonnet"], "family_models": MODELS,
        }, ensure_ascii=False))
        return 0
    # Do not print either the supplied configuration or a command containing it.
    settings = sanitized_settings(json.loads(args.settings.read_text()), route)
    fd, config = tempfile.mkstemp(prefix="hmigbot-task-settings-", suffix=".json")
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump(settings, stream, ensure_ascii=False)
        cmd += ["--settings", config]
        bounded = guard_command(cmd, route, run_dir, args.stage)
        env = apply_execution_environment(os.environ, route)
        env.pop("CLAUDECODE", None)
        env.pop("CLAUDE_CODE_ENTRYPOINT", None)
        with args.prompt_file.open("rb") as prompt:
            child = subprocess.Popen(bounded, cwd=cwd, env=env, stdin=prompt,
                                     start_new_session=True)
            previous_handlers = {}

            def forward_signal(signum, _frame):
                try:
                    os.killpg(child.pid, signum)
                except ProcessLookupError:
                    pass

            try:
                for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
                    previous_handlers[signum] = signal.signal(signum, forward_signal)
                return child.wait()
            finally:
                if child.poll() is None:
                    forward_signal(signal.SIGTERM, None)
                    try:
                        child.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        forward_signal(signal.SIGKILL, None)
                        child.wait()
                for signum, previous in previous_handlers.items():
                    signal.signal(signum, previous)
    finally:
        Path(config).unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, TypeError) as exc:
        # Exception text can contain user-supplied configuration. Report its type only.
        print(f"Claude task configuration failed ({type(exc).__name__})", file=sys.stderr)
        raise SystemExit(2)
