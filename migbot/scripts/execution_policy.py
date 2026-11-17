#!/usr/bin/env python3
"""Small shared routing contract for Claude CLI callers (no network operations)."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence


POLICY_PATH = Path(__file__).resolve().parents[1] / "config" / "execution-policy.json"
POLICY = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
MODELS = POLICY["models"]
PROFILES = POLICY["profiles"]
EFFORTS = ("low", "medium", "high", "max")
MODEL_EFFORTS = {p["model"]: p["effort"] for p in PROFILES.values()}


@dataclass(frozen=True)
class ExecutionRoute:
    profile: str
    model: str
    effort: str
    max_turns: int
    max_budget_usd: float
    timeout_seconds: float
    task_id: str


def positive_number(value: object) -> float:
    """argparse-compatible validation, also used for non-CLI callers."""
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise argparse.ArgumentTypeError("must be a finite positive number") from exc
    if isinstance(value, bool) or not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("must be a finite positive number")
    return number


def positive_int(value: object) -> int:
    number = positive_number(value)
    if not number.is_integer():
        raise argparse.ArgumentTypeError("must be a positive integer")
    return int(number)


def add_execution_arguments(parser: argparse.ArgumentParser,
                            default_profile: str = "implementation") -> None:
    if default_profile not in PROFILES:
        raise ValueError(f"unknown execution profile: {default_profile}")
    group = parser.add_argument_group("bounded model execution")
    group.add_argument("--profile", choices=tuple(PROFILES), default=default_profile)
    group.add_argument("--effort", choices=EFFORTS)
    group.add_argument("--model", choices=tuple(MODELS) + tuple(MODELS.values()))
    group.add_argument("--max-turns", type=positive_int)
    group.add_argument("--max-budget-usd", type=positive_number)
    group.add_argument("--timeout-seconds", type=positive_number)
    group.add_argument("--task-id", help="reuse with the same run directory for resume accounting")


def resolve_execution(args: argparse.Namespace) -> ExecutionRoute:
    profile = getattr(args, "profile", None) or POLICY["default_profile"]
    if profile not in PROFILES:
        raise ValueError(f"unknown execution profile: {profile}")
    preset = PROFILES[profile]
    selected = getattr(args, "model", None) or preset["model"]
    family = selected if selected in MODELS else next(
        (key for key, model in MODELS.items() if model == selected), None)
    if family is None:
        raise ValueError("model must be an execution-policy family or full model ID")
    # A model override also selects its natural effort unless effort was explicit.
    effort = getattr(args, "effort", None) or MODEL_EFFORTS[family]
    if effort not in EFFORTS:
        raise ValueError(f"unknown execution effort: {effort}")
    task_id = getattr(args, "task_id", None) or getattr(args, "stage", None)
    if task_id is None:
        raise ValueError("--task-id is required when no stable stage is available")
    if not isinstance(task_id, str) or not task_id.strip() or len(task_id) > 256:
        raise ValueError("task_id must contain 1 to 256 characters")
    if any(ord(c) < 32 for c in task_id):
        raise ValueError("task_id must not contain control characters")

    def limit(name: str, validator):
        value = getattr(args, name, None)
        return validator(preset[name] if value is None else value)

    return ExecutionRoute(profile, MODELS[family], effort,
                          limit("max_turns", positive_int),
                          limit("max_budget_usd", positive_number),
                          limit("timeout_seconds", positive_number), task_id)


def apply_execution_environment(env: Mapping[str, str], route: ExecutionRoute) -> dict[str, str]:
    """Keep credentials; remove inherited routing overrides, then map real families."""
    blocked = {
        "ANTHROPIC_MODEL", "ANTHROPIC_SMALL_FAST_MODEL", "ANTHROPIC_REASONING_MODEL",
        "CLAUDE_MODEL", "CLAUDE_CODE_EFFORT_LEVEL", "CLAUDE_CODE_SUBAGENT_MODEL",
        "SUBAGENT_MODEL", "CLAUDE_CODE_SUBAGENT_EFFORT", "MAX_THINKING_TOKENS", "_FORCE",
        "CLAUDE_CODE_FORCE_OPUS", "CLAUDE_CODE_FORCE_SONNET",
        "CLAUDE_CODE_FORCE_HAIKU", "CLAUDE_CODE_FORCE_FABLE",
    }
    result = {
        key: value for key, value in env.items()
        if key not in blocked and not (
            "FORCE" in key.upper() and
            ("MODEL" in key.upper() or "EFFORT" in key.upper()))
    }
    for family, model in MODELS.items():
        result[f"ANTHROPIC_DEFAULT_{family.upper()}_MODEL"] = model
    # This is an overridable fallback for generic Agents, not a global force flag.
    result["CLAUDE_CODE_SUBAGENT_MODEL"] = MODELS[POLICY["default_subagent_model"]]
    result["CLAUDE_CODE_AUTO_COMPACT_WINDOW"] = str(POLICY["context"]["auto_compact_window"])
    return result


def apply_execution_command(cmd: Sequence[str], route: ExecutionRoute) -> list[str]:
    """Replace parent CLI routing/limits while preserving all other arguments."""
    replacements = {"--model": route.model, "--effort": route.effort,
                    "--max-turns": str(route.max_turns),
                    "--max-budget-usd": str(route.max_budget_usd)}
    result: list[str] = []
    index = 0
    while index < len(cmd):
        item = str(cmd[index])
        if item == "--":
            break
        option = item.split("=", 1)[0]
        if option in replacements:
            if "=" not in item:
                if index + 1 >= len(cmd):
                    raise ValueError(f"missing value for {option}")
                index += 1
        else:
            result.append(item)
        index += 1
    for option, value in replacements.items():
        result.extend((option, value))
    result.extend(str(item) for item in cmd[index:])
    return result


def execution_prompt(route: ExecutionRoute) -> str:
    return (
        f"Execution contract: task={route.task_id}; parent={route.model}/{route.effort}; "
        f"limits={route.max_turns} turns, ${route.max_budget_usd:g} CLI estimate, "
        f"{route.timeout_seconds:g}s cumulative wallclock. "
        "This task routing replaces older blanket model/max-effort instructions. "
        "Use existing deterministic scripts for fixed operations. Route search/read-only work "
        "to haiku/low, routine implementation to sonnet/medium, difficult reasoning to opus/high; "
        "fable/max requires explicit expert selection. Set each subtask's model and effort; "
        "unqualified Agents default to sonnet. Read bounded excerpts, not full logs. "
        f"Keep working context near {POLICY['context']['soft_context_target']} tokens when possible; "
        "the CLI auto-compaction window is a separate setting, not a hard context cap. "
        "After two rounds without progress change strategy. Validate with real acceptance checks "
        "and report evidence; do not claim unrun checks passed."
    )


def guard_command(cmd: Sequence[str], route: ExecutionRoute,
                  run_dir: os.PathLike[str] | str, stage: str) -> list[str]:
    """Wrap the entire original command, including any sandbox-exec restrictions."""
    guard = Path(__file__).with_name("claude_task_guard.py")
    return [sys.executable, str(guard), "--run-dir", str(Path(run_dir).resolve()),
            "--stage", str(stage), "--profile", route.profile,
            "--model", route.model, "--effort", route.effort,
            "--max-turns", str(route.max_turns),
            "--max-budget-usd", str(route.max_budget_usd),
            "--timeout-seconds", str(route.timeout_seconds),
            "--task-id", route.task_id, "--", *map(str, cmd)]
