#!/usr/bin/env python3
"""Run a deterministic multi-state iOS runtime capture plan.

Each plan entry delegates the actual Simulator/XCTest capture to
``ios_runtime_capture.py``.  The wrapper makes the page/state set explicit,
reuses the first successful build, preserves per-state logs, and writes one
aggregate manifest even when an individual state is blocked.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
CAPTURE_SCRIPT = SCRIPT_DIR / "ios_runtime_capture.py"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_plan(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("states"), list):
        raise ValueError("capture plan must be an object with a states array")
    states = payload["states"]
    if not states:
        raise ValueError("capture plan states must not be empty")
    seen: set[tuple[str, str]] = set()
    for index, state in enumerate(states):
        if not isinstance(state, dict):
            raise ValueError(f"states[{index}] must be an object")
        page_id = state.get("page_id")
        state_id = state.get("state_id", "normal")
        if not isinstance(page_id, str) or not page_id:
            raise ValueError(f"states[{index}].page_id is required")
        if not isinstance(state_id, str) or not state_id:
            raise ValueError(f"states[{index}].state_id must be a non-empty string")
        key = (page_id, state_id)
        if key in seen:
            raise ValueError(f"duplicate page/state: {page_id}/{state_id}")
        seen.add(key)
        if not state.get("accessibility_command") and not state.get("accessibility_json"):
            raise ValueError(f"states[{index}] needs accessibility_command or accessibility_json")
    return payload


def run_state(
    *,
    base_args: list[str],
    state: dict[str, Any],
    output_root: Path,
    skip_build: bool,
    timeout: int,
) -> dict[str, Any]:
    page_id = str(state["page_id"])
    state_id = str(state.get("state_id", "normal"))
    state_dir = output_root / page_id / "states" / state_id
    state_dir.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        str(CAPTURE_SCRIPT),
        *base_args,
        "--output-dir",
        str(state_dir),
        "--page-id",
        page_id,
        "--state-id",
        state_id,
        "--timeout",
        str(timeout),
    ]
    if skip_build:
        command.append("--skip-build")
    accessibility_command = state.get("accessibility_command")
    if accessibility_command:
        command.extend(["--accessibility-command", str(accessibility_command)])
    else:
        command.extend(["--accessibility-json", str(state["accessibility_json"])])
    started = time.monotonic()
    log_path = state_dir / "capture-plan.log"
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout + 30)
        log_path.write_text(
            "COMMAND " + json.dumps(command, ensure_ascii=False) + "\n"
            + completed.stdout
            + ("\nSTDERR\n" + completed.stderr if completed.stderr else ""),
            encoding="utf-8",
        )
        result: dict[str, Any] = {
            "page_id": page_id,
            "state_id": state_id,
            "status": "captured" if completed.returncode == 0 else "blocked",
            "exit_code": completed.returncode,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "output_dir": str(state_dir),
            "log_path": str(log_path),
        }
        if completed.returncode != 0:
            result["blocked_reason"] = (completed.stderr or completed.stdout)[-4000:]
        return result
    except subprocess.TimeoutExpired as exc:
        log_path.write_text(
            "COMMAND " + json.dumps(command, ensure_ascii=False) + "\nTIMEOUT\n"
            + str(exc),
            encoding="utf-8",
        )
        return {
            "page_id": page_id,
            "state_id": state_id,
            "status": "blocked",
            "exit_code": None,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "output_dir": str(state_dir),
            "log_path": str(log_path),
            "blocked_reason": f"capture timed out after {timeout + 30}s",
        }


def write_manifests(project_root: Path, output_root: Path, manifest: dict[str, Any]) -> dict[str, str]:
    """Write the capture manifest and a project-local downstream handoff."""
    output_manifest = output_root / "capture-plan-manifest.json"
    output_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    handoff_dir = project_root / "spec/execution/ios-runtime-capture"
    handoff_manifest = handoff_dir / "capture-plan-manifest.json"
    handoff_dir.mkdir(parents=True, exist_ok=True)
    if handoff_manifest.resolve() != output_manifest.resolve():
        handoff_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"output_manifest": str(output_manifest), "handoff_manifest": str(handoff_manifest)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, help="JSON capture plan")
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--scheme", required=True)
    parser.add_argument("--configuration", default="Debug")
    parser.add_argument("--device-id")
    parser.add_argument("--xcrun", default="xcrun")
    parser.add_argument("--derived-data", default="build/i2h-derived-data")
    parser.add_argument("--app-path")
    parser.add_argument("--bundle-id")
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args(argv)

    try:
        plan_path = Path(args.plan).expanduser().resolve()
        plan = load_plan(plan_path)
        output_root = Path(args.output_root).expanduser().resolve()
        output_root.mkdir(parents=True, exist_ok=True)
        base_args = [
            "--project-root", args.project_root,
            "--project", args.project,
            "--scheme", args.scheme,
            "--configuration", args.configuration,
            "--xcrun", args.xcrun,
            "--derived-data", args.derived_data,
        ]
        for name, value in (("device-id", args.device_id), ("app-path", args.app_path), ("bundle-id", args.bundle_id)):
            if value:
                base_args.extend([f"--{name}", value])

        results: list[dict[str, Any]] = []
        for index, state in enumerate(plan["states"]):
            results.append(
                run_state(
                    base_args=base_args,
                    state=state,
                    output_root=output_root,
                    skip_build=index > 0,
                    timeout=args.timeout,
                )
            )

        blocked = [item for item in results if item["status"] != "captured"]
        manifest = {
            "schema_version": 1,
            "status": "captured" if not blocked else "partial",
            "started_at": utc_now(),
            "plan_path": str(plan_path),
            "output_root": str(output_root),
            "state_count": len(results),
            "captured_count": len(results) - len(blocked),
            "blocked_count": len(blocked),
            "states": results,
        }
        manifest_paths = write_manifests(Path(args.project_root).expanduser().resolve(), output_root, manifest)
        manifest["handoff_manifest"] = manifest_paths["handoff_manifest"]
        # Keep both copies self-describing.  The handoff path is consumed by
        # stage1_visual_scope when the capture output lives outside the project.
        for path in {Path(manifest_paths["output_manifest"]), Path(manifest_paths["handoff_manifest"])}:
            path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return 0 if not blocked else 2
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
