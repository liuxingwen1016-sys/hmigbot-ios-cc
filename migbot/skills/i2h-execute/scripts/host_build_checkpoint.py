"""Run a host build between Execute batches and produce a source-bound diagnostic."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from zipfile import BadZipFile
import re
import subprocess
import time

from lib.host_verify_handoff import HANDOFF, hap_stamp, publish, validate
from lib.ios_ui_delivery_gate import _project_file
from lib.ios_ui_dispatch import atomic_write, json_bytes
from lib.stage1_contract import digest, source_digest


ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\\u001b\[[0-?]*[ -/]*[@-~]")
COMPILE_RESULT = re.compile(r"COMPILE RESULT:FAIL\s*\{ERROR:(\d+)\s+WARN:(\d+)\}")
ARKTS_ERROR = re.compile(
    r"^\d+ ERROR:\s+(\d+) ArkTS Compiler Error\nError Message:\s*([^\n]+)", re.MULTILINE
)
BUILD_SUCCESS = re.compile(r"^.*\bhvigor\b.*\bBUILD SUCCESSFUL\b", re.MULTILINE)
FAILED_TASK = re.compile(r"\bFailed\s+:(\S+)\.\.\.")
HOST_DENIAL = re.compile(r"\b(?:EPERM|EACCES|E403|ENOTFOUND)\b|operation not permitted|sandbox violation", re.I)


def diagnose(log: str, exit_code: int | None) -> dict:
    log = ANSI.sub("", log).replace("\r\n", "\n")
    errors = Counter()
    for code, message in ARKTS_ERROR.findall(log):
        headline = message.split(" At File:", 1)[0].strip()
        errors[(code, headline)] += 1
    counts = COMPILE_RESULT.findall(log)
    tasks = FAILED_TASK.findall(log)
    report = {
        "failed_task": tasks[-1] if tasks else None,
        "compiler_errors": int(counts[-1][0]) if counts else sum(errors.values()),
        "compiler_warnings": int(counts[-1][1]) if counts else None,
        "diagnostics": [
            {"code": code, "message": message, "count": count}
            for (code, message), count in errors.most_common()
        ],
    }
    if counts or errors:
        reason, status = "arkts_compile_failed", "FAIL"
    elif exit_code == 0 and BUILD_SUCCESS.search(log):
        reason, status = "build_succeeded", "PASS"
    elif HOST_DENIAL.search(log):
        reason, status = "host_access_or_dependency_denied", "BLOCKED"
    elif tasks and tasks[-1].endswith("@SignHap"):
        reason, status = "signing_failed", "FAIL"
    else:
        reason, status = "build_result_unconfirmed", "BLOCKED"
    return {**report, "status": status, "reason": reason}


def checkpoint(root: Path, log: Path, command: list[str], timeout: float) -> dict:
    before = source_digest(root)
    started = time.monotonic()
    exit_code = None
    execution_problem = None
    with log.open("wb") as output:
        try:
            exit_code = subprocess.run(command, cwd=root, stdin=subprocess.DEVNULL,
                                       stdout=output, stderr=subprocess.STDOUT,
                                       timeout=timeout, check=False).returncode
        except subprocess.TimeoutExpired:
            execution_problem = "build_timeout"
        except OSError as exc:
            output.write(f"{exc}\n".encode("utf-8"))
            execution_problem = "host_command_unavailable"
    raw = log.read_bytes()
    after = source_digest(root)
    result = diagnose(raw.decode("utf-8", errors="replace"), exit_code)
    if execution_problem or before != after:
        result.update(status="BLOCKED", reason=execution_problem or "build_inputs_changed")
    return {
        "schema_version": 1,
        "kind": "execute-host-build-checkpoint",
        "source_sha256": before,
        "source_after_sha256": after,
        "command": command,
        "exit_code": exit_code,
        "wall_seconds": round(time.monotonic() - started, 3),
        "log": {"path": str(log), "sha256": digest(raw)},
        **result,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--log", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--check-installation", action="store_true", help="replay the recorded host installation")
    parser.add_argument("--scope", type=Path)
    parser.add_argument("--signed-hap", type=Path)
    parser.add_argument("--java")
    parser.add_argument("--sign-tool")
    parser.add_argument("--hdc")
    parser.add_argument("--device")
    parser.add_argument("--bundle")
    parser.add_argument("--timeout", type=float, default=900)
    parser.add_argument("command", nargs=argparse.REMAINDER, help="build command after --")
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    root = args.project_root.resolve()
    options = (args.scope, args.signed_hap, args.java, args.sign_tool, args.hdc, args.device, args.bundle)
    if args.check_installation:
        if command or any(options) or args.log or args.out:
            parser.error("--check-installation only reads the project's handoff")
        try:
            record = _project_file(root, HANDOFF)
            print(json.dumps(validate(root, json.loads(record.read_bytes()))))
            return 0
        except (OSError, ValueError, KeyError, TypeError, AttributeError, BadZipFile) as exc:
            parser.exit(2, f"host Verify handoff: {exc}\n")
    if any(options) and not all(options):
        parser.error("host installation requires scope, signed-hap, java, sign-tool, hdc, device and bundle")
    if not args.log or not args.out:
        parser.error("build log and output are required")
    if not command or args.timeout <= 0:
        parser.error("a build command and positive timeout are required")
    root, log, out = (path.resolve() for path in (args.project_root, args.log, args.out))
    if not root.is_dir() or log == out:
        parser.error("project directory, log and a separate report are required")
    project_evidence = root / "spec/execution"
    if any(path.is_relative_to(root) and not path.is_relative_to(project_evidence) for path in (log, out)):
        parser.error("project-local output must be inside spec/execution")
    try:
        initial_stamp = hap_stamp(_project_file(root, str(args.signed_hap))) if args.signed_hap else None
        result = checkpoint(root, log, command, args.timeout)
        atomic_write(out, json_bytes(result))
        if args.signed_hap and result["status"] == "PASS":
            publish(root, args, result, initial_stamp)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, subprocess.TimeoutExpired, BadZipFile) as exc:
        parser.exit(2, f"host build checkpoint: {exc}\n")
    print(json.dumps({key: result[key] for key in ("status", "reason", "compiler_errors")}))
    return {"PASS": 0, "FAIL": 1, "BLOCKED": 2}[result["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
