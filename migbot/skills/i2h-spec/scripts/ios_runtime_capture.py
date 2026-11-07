#!/usr/bin/env python3
"""Capture an iOS Simulator screenshot and accessibility JSON evidence.

The runner owns the deterministic simulator steps. Accessibility trees are
provided by an XCTest/XCUITest helper through ``--accessibility-command`` or
an already-produced JSON file through ``--accessibility-json``. The runner
never fabricates an accessibility tree when that evidence is unavailable.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import plistlib
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Sequence


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from runtime_view import atomic_json, normalize  # noqa: E402


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def run_command(command: Sequence[str], *, timeout: int, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )


def choose_device(xcrun: str, requested: str | None) -> str:
    if requested:
        return requested
    payload = json.loads(run_command([xcrun, "simctl", "list", "devices", "available", "-j"], timeout=30).stdout)
    devices = payload.get("devices", {})
    candidates: list[dict[str, Any]] = []
    for runtime, rows in devices.items():
        if "iOS" not in runtime or not isinstance(rows, list):
            continue
        candidates.extend(row for row in rows if isinstance(row, dict) and "iPhone" in row.get("name", ""))
    booted = next((row for row in candidates if row.get("state") == "Booted" and row.get("udid")), None)
    selected = booted or next((row for row in candidates if row.get("udid")), None)
    if not selected:
        raise RuntimeError("no available iPhone Simulator found")
    return str(selected["udid"])


def ensure_booted(xcrun: str, device: str, timeout: int) -> None:
    state = run_command([xcrun, "simctl", "list", "devices", "-j"], timeout=30).stdout
    payload = json.loads(state)
    current = next(
        (
            row
            for rows in payload.get("devices", {}).values()
            if isinstance(rows, list)
            for row in rows
            if isinstance(row, dict) and row.get("udid") == device
        ),
        None,
    )
    if not current:
        raise RuntimeError(f"Simulator not found: {device}")
    if current.get("state") != "Booted":
        run_command([xcrun, "simctl", "boot", device], timeout=timeout)
    run_command([xcrun, "simctl", "bootstatus", device, "-b"], timeout=timeout)


def find_app(derived_data: Path, explicit: str | None) -> Path:
    if explicit:
        app = Path(explicit).expanduser().resolve()
        if not app.is_dir():
            raise RuntimeError(f"app bundle not found: {app}")
        return app
    apps = sorted(derived_data.glob("Build/Products/*-iphonesimulator/*.app"))
    if not apps:
        raise RuntimeError(f"no Simulator .app found below {derived_data}")
    return apps[0]


def bundle_id(app: Path, explicit: str | None) -> str:
    if explicit:
        return explicit
    info = app / "Info.plist"
    if not info.is_file():
        raise RuntimeError(f"Info.plist not found in app bundle: {app}")
    with info.open("rb") as handle:
        payload = plistlib.load(handle)
    value = payload.get("CFBundleIdentifier")
    if not value:
        raise RuntimeError(f"CFBundleIdentifier missing from {info}")
    return str(value)


def app_identity(app: Path, identifier: str) -> dict[str, str]:
    version = ""
    build = ""
    info = app / "Info.plist"
    if info.is_file():
        with info.open("rb") as handle:
            payload = plistlib.load(handle)
        version = str(payload.get("CFBundleShortVersionString", ""))
        build = str(payload.get("CFBundleVersion", ""))
    return {
        "bundle_id": identifier,
        "version": version,
        "build": build,
        "build_identity": f"{identifier}:{version}:{build}",
    }


def update_snapshot_meta(output_dir: Path, page_id: str, state_id: str, normalized: dict[str, Any]) -> Path | None:
    if output_dir.parent.name != "states":
        return None
    snapshot_root = output_dir.parent.parent
    meta_path = snapshot_root / "meta.json"
    meta: dict[str, Any] = {}
    if meta_path.is_file():
        try:
            value = json.loads(meta_path.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                meta = value
        except json.JSONDecodeError:
            meta = {}
    normalized_status = normalized.get("status")
    state_evidence = {
        "status": normalized_status if normalized_status in {"blocked", "captured", "audited"} else ("audited" if not normalized.get("warnings") else "captured"),
        "page_id": page_id,
        "state": state_id,
        "state_id": state_id,
        "captured_at": normalized.get("captured_at"),
        "device": normalized.get("device", {}),
        "device_id": normalized.get("device", {}).get("udid"),
        "app": normalized.get("app", {}),
        "app_identity": normalized.get("app", {}).get("bundle_id"),
        "build_identity": normalized.get("app", {}).get("build_identity"),
        "png_path": (output_dir / "ios-runtime.png").relative_to(snapshot_root).as_posix(),
        "png_sha256": normalized.get("screenshot_sha256"),
        "ui_json_path": (output_dir / "ios-accessibility.json").relative_to(snapshot_root).as_posix(),
        "ui_json_sha256": normalized.get("ui_json_sha256"),
        "source_platform": "ios",
    }
    if normalized.get("blocked_reason"):
        state_evidence["blocked_reason"] = normalized["blocked_reason"]
    by_state = meta.get("runtime_evidence_by_state")
    if not isinstance(by_state, dict):
        by_state = {}
    by_state[state_id] = state_evidence
    meta.update({"page_id": page_id, "runtime_evidence_by_state": by_state})
    meta.setdefault("runtime_evidence", state_evidence)
    atomic_json(meta_path, meta)
    return meta_path


def copy_accessibility_json(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise RuntimeError(f"accessibility JSON not found: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def capture(args: argparse.Namespace) -> dict[str, Any]:
    project_root = Path(args.project_root).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    xcrun = args.xcrun
    device = choose_device(xcrun, args.device_id)
    derived_data = Path(args.derived_data).expanduser().resolve()
    project = Path(args.project).expanduser()
    if not project.is_absolute():
        project = project_root / project
    project = project.resolve()

    plan = {
        "project_root": str(project_root),
        "project": str(project),
        "scheme": args.scheme,
        "device_id": device,
        "derived_data": str(derived_data),
        "page_id": args.page_id,
        "state_id": args.state_id,
        "output_dir": str(output_dir),
    }
    if args.dry_run:
        return {"status": "dry_run", "plan": plan}

    ensure_booted(xcrun, device, args.timeout)
    if not args.skip_build:
        run_command(
            [
                "xcodebuild",
                "-project",
                str(project),
                "-scheme",
                args.scheme,
                "-configuration",
                args.configuration,
                "-destination",
                f"platform=iOS Simulator,id={device}",
                "-derivedDataPath",
                str(derived_data),
                "CODE_SIGNING_ALLOWED=NO",
                "build",
            ],
            timeout=args.timeout,
        )

    app = find_app(derived_data, args.app_path)
    app_bundle_id = bundle_id(app, args.bundle_id)
    identity = app_identity(app, app_bundle_id)
    run_command([xcrun, "simctl", "install", device, str(app)], timeout=args.timeout)
    run_command([xcrun, "simctl", "launch", device, app_bundle_id], timeout=args.timeout)

    ui_json = output_dir / "ios-accessibility.json"
    screenshot = output_dir / "ios-runtime.png"
    screenshot_taken = False
    if args.accessibility_json:
        ui_json.unlink(missing_ok=True)
        copy_accessibility_json(Path(args.accessibility_json).expanduser().resolve(), ui_json)
    elif args.accessibility_command:
        # XCTest tears down the app after the test returns.  Capture as soon as
        # the helper publishes the accessibility tree so the screenshot still
        # belongs to the target page instead of SpringBoard.
        ui_json.unlink(missing_ok=True)
        screenshot.unlink(missing_ok=True)
        command_env = os.environ.copy()
        command_env.update(
            {
                "I2H_SIMULATOR_UDID": device,
                "I2H_BUNDLE_ID": app_bundle_id,
                "I2H_UI_JSON_OUT": str(ui_json),
                "I2H_PAGE_ID": args.page_id,
                "I2H_STATE_ID": args.state_id,
                # XCTest runners reliably inherit TEST_RUNNER_* values.
                "TEST_RUNNER_I2H_SIMULATOR_UDID": device,
                "TEST_RUNNER_I2H_BUNDLE_ID": app_bundle_id,
                "TEST_RUNNER_I2H_UI_JSON_OUT": str(ui_json),
                "TEST_RUNNER_I2H_PAGE_ID": args.page_id,
                "TEST_RUNNER_I2H_STATE_ID": args.state_id,
            }
        )
        log_path = output_dir / "accessibility-command.log"
        with log_path.open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                ["/bin/zsh", "-lc", args.accessibility_command],
                env=command_env,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
            )
            deadline = time.monotonic() + args.timeout
            try:
                while process.poll() is None:
                    if not screenshot_taken and ui_json.is_file():
                        time.sleep(0.25)
                        run_command([xcrun, "simctl", "io", device, "screenshot", str(screenshot)], timeout=args.timeout)
                        screenshot_taken = True
                    if time.monotonic() > deadline:
                        process.kill()
                        raise RuntimeError(f"accessibility command timed out after {args.timeout}s")
                    time.sleep(0.05)
            finally:
                process.wait(timeout=30)
            if process.returncode != 0:
                tail = log_path.read_text(encoding="utf-8", errors="replace")[-4000:]
                raise RuntimeError(f"accessibility command failed with exit {process.returncode}:\n{tail}")
    else:
        raise RuntimeError("accessibility evidence is required. Pass --accessibility-json or --accessibility-command")
    if not ui_json.is_file():
        raise RuntimeError(f"accessibility command did not create {ui_json}")

    if not screenshot_taken:
        run_command([xcrun, "simctl", "io", device, "screenshot", str(screenshot)], timeout=args.timeout)

    ui_payload = json.loads(ui_json.read_text(encoding="utf-8"))
    raw = {
        "schema_version": 2,
        "page_id": args.page_id,
        "state_id": args.state_id,
        "captured_at": utc_now(),
        "device": {"udid": device},
        "app": {**identity, "app_path": str(app)},
        "screenshot": screenshot.name,
        "ui_json": ui_json.name,
        "nodes": ui_payload.get("nodes", []) if isinstance(ui_payload, dict) else [],
    }
    raw_path = output_dir / "capture.json"
    atomic_json(raw_path, raw)
    normalized = normalize(raw_path)
    normalized_path = output_dir / "runtime-evidence.json"
    atomic_json(normalized_path, normalized)
    snapshot_meta = update_snapshot_meta(output_dir, args.page_id, args.state_id, normalized)
    manifest = {
        "status": "audited" if not normalized["warnings"] else "captured",
        "page_id": args.page_id,
        "state_id": args.state_id,
        "runtime_evidence": normalized,
        "png_path": screenshot.name,
        "ui_json_path": ui_json.name,
        "png_sha256": normalized.get("screenshot_sha256"),
        "ui_json_sha256": normalized.get("ui_json_sha256"),
    }
    atomic_json(output_dir / "manifest.json", manifest)
    return {
        "status": "captured",
        "manifest": str(output_dir / "manifest.json"),
        "snapshot_meta": str(snapshot_meta) if snapshot_meta else None,
        "warnings": normalized["warnings"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--project", required=True, help=".xcodeproj path, relative to project root or absolute")
    parser.add_argument("--scheme", required=True)
    parser.add_argument("--configuration", default="Debug")
    parser.add_argument("--device-id")
    parser.add_argument("--xcrun", default="xcrun")
    parser.add_argument("--derived-data", default="build/i2h-derived-data")
    parser.add_argument("--app-path")
    parser.add_argument("--bundle-id")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--page-id", required=True)
    parser.add_argument("--state-id", default="normal")
    parser.add_argument("--accessibility-json")
    parser.add_argument("--accessibility-command")
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args(argv)
    try:
        result = capture(args)
    except (OSError, RuntimeError, subprocess.SubprocessError, json.JSONDecodeError, plistlib.InvalidFileException) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
