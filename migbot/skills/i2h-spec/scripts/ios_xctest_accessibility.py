#!/usr/bin/env python3
"""Run an external XCUITest accessibility probe without touching the iOS source.

The iOS source project is treated as read-only.  This helper makes a temporary
copy, appends one probe test to the existing UI-test source file, and runs only
that test.  The probe writes the XCUITest debug description to
``TEST_RUNNER_I2H_UI_JSON_OUT`` so ``ios_runtime_capture.py`` can pair it with
the Simulator screenshot.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


PROBE_MARKER = "// i2h-external-accessibility-probe"


PROBE_SOURCE = r'''

// i2h-external-accessibility-probe
final class I2HAccessibilityCaptureTests: XCTestCase {
    @MainActor func testI2HAccessibilityCapture() throws {
        let environment = ProcessInfo.processInfo.environment
        let output = environment["TEST_RUNNER_I2H_UI_JSON_OUT"] ?? environment["I2H_UI_JSON_OUT"]
        guard let output else { return }

        let app = XCUIApplication()
        app.launchArguments = ["--uitesting"]
        app.launch()
        let page = environment["TEST_RUNNER_I2H_PAGE_ID"] ?? environment["I2H_PAGE_ID"] ?? ""
        guard app.waitForExistence(timeout: 10), navigate(app: app, page: page) else {
            throw NSError(domain: "i2h.accessibility", code: 1, userInfo: [NSLocalizedDescriptionKey: "target app/page did not become ready"])
        }
        let bundleID = environment["TEST_RUNNER_I2H_BUNDLE_ID"] ?? environment["I2H_BUNDLE_ID"] ?? ""
        let stateID = environment["TEST_RUNNER_I2H_STATE_ID"] ?? environment["I2H_STATE_ID"] ?? "default"
        let payload: [String: Any] = [
            "page_id": page,
            "state_id": stateID,
            "foreground_bundle_id": bundleID,
            "foreground_state": "runningForeground",
            "debug_description": app.debugDescription,
        ]
        let data = try JSONSerialization.data(withJSONObject: payload, options: [.prettyPrinted])
        try data.write(to: URL(fileURLWithPath: output), options: .atomic)
        if let receipt = environment["TEST_RUNNER_I2H_FOREGROUND_RECEIPT_OUT"] ?? environment["I2H_FOREGROUND_RECEIPT_OUT"] {
            let receiptPayload: [String: Any] = [
                "schema": "hmigbot-ios-foreground-receipt/1",
                "bundle_id": bundleID,
                "page_id": page,
                "state_id": stateID,
                "state": "runningForeground",
                "ready": true,
            ]
            let receiptData = try JSONSerialization.data(withJSONObject: receiptPayload, options: [.prettyPrinted])
            try receiptData.write(to: URL(fileURLWithPath: receipt), options: .atomic)
        }
        if let acknowledgement = environment["TEST_RUNNER_I2H_FOREGROUND_CAPTURE_ACK_OUT"] ?? environment["I2H_FOREGROUND_CAPTURE_ACK_OUT"] {
            let timeout = Double(environment["TEST_RUNNER_I2H_FOREGROUND_ACK_TIMEOUT"] ?? environment["I2H_FOREGROUND_ACK_TIMEOUT"] ?? "60") ?? 60
            let deadline = Date().addingTimeInterval(timeout)
            while !FileManager.default.fileExists(atPath: acknowledgement) {
                if Date() >= deadline {
                    throw NSError(domain: "i2h.accessibility", code: 2, userInfo: [NSLocalizedDescriptionKey: "foreground screenshot acknowledgement timed out"])
                }
                Thread.sleep(forTimeInterval: 0.05)
            }
        }
    }

    @MainActor private func navigate(app: XCUIApplication, page: String) -> Bool {
        switch page {
        case "page_0001_RootView", "page_0002_HomeView":
            return app.buttons["prepareRecipe"].waitForExistence(timeout: 10)
        case "page_0003_BeanLibraryView":
            guard app.tabBars.buttons["豆档案"].waitForExistence(timeout: 5) else { return false }
            app.tabBars.buttons["豆档案"].tap()
            return app.buttons["addBean"].waitForExistence(timeout: 5)
        case "page_0007_RecipeView":
            guard app.buttons["prepareRecipe"].waitForExistence(timeout: 5) else { return false }
            app.buttons["prepareRecipe"].tap()
            return app.staticTexts["targetWater"].waitForExistence(timeout: 5)
        case "page_0008_BrewView":
            guard app.buttons["prepareRecipe"].waitForExistence(timeout: 5) else { return false }
            app.buttons["prepareRecipe"].tap()
            guard app.buttons["startBrew"].waitForExistence(timeout: 5) else { return false }
            app.buttons["startBrew"].tap()
            return app.buttons["finishEarly"].waitForExistence(timeout: 5)
        default:
            return app.exists
        }
    }
}
'''


def copy_tree(source_root: Path, destination_root: Path) -> None:
    """Copy the source project while avoiding generated build directories."""
    ignored = shutil.ignore_patterns(".git", "build", "DerivedData", ".build")
    shutil.copytree(source_root, destination_root, ignore=ignored)


def append_probe(source_root: Path, relative_test_file: str) -> Path:
    test_file = source_root / relative_test_file
    if not test_file.is_file():
        raise RuntimeError(f"XCUITest source file not found: {test_file}")
    content = test_file.read_text(encoding="utf-8")
    if PROBE_MARKER not in content:
        test_file.write_text(content.rstrip() + PROBE_SOURCE + "\n", encoding="utf-8")
    return test_file


def run_probe(args: argparse.Namespace) -> int:
    project = Path(args.project).expanduser().resolve()
    if not project.exists():
        raise RuntimeError(f"Xcode project not found: {project}")
    output = os.environ.get("TEST_RUNNER_I2H_UI_JSON_OUT") or os.environ.get("I2H_UI_JSON_OUT")
    if not output:
        raise RuntimeError("TEST_RUNNER_I2H_UI_JSON_OUT or I2H_UI_JSON_OUT is required")

    with tempfile.TemporaryDirectory(prefix="i2h-xctest-") as directory:
        copy_root = Path(directory) / project.parent.name
        copy_tree(project.parent, copy_root)
        append_probe(copy_root, args.test_source)
        copied_project = copy_root / project.name
        derived_data = Path(args.derived_data).expanduser().resolve()
        command = [
            "xcodebuild",
            "test",
            "-project",
            str(copied_project),
            "-scheme",
            args.scheme,
            "-destination",
            args.destination,
            "-derivedDataPath",
            str(derived_data),
            "-only-testing:CuikeUITests/I2HAccessibilityCaptureTests/testI2HAccessibilityCapture",
        ]
        log_path = Path(args.log).expanduser().resolve() if args.log else None
        if log_path:
            log_path.parent.mkdir(parents=True, exist_ok=True)
        completed = subprocess.run(command, text=True, capture_output=True, timeout=args.timeout, env=os.environ.copy())
        if log_path:
            log_path.write_text(completed.stdout + "\nSTDERR\n" + completed.stderr, encoding="utf-8")
        if completed.returncode != 0:
            tail = (completed.stderr or completed.stdout)[-6000:]
            raise RuntimeError(f"xcodebuild accessibility probe failed with exit {completed.returncode}:\n{tail}")
    if not Path(output).is_file():
        raise RuntimeError(f"probe completed without writing {output}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, help="path to the read-only source .xcodeproj")
    parser.add_argument("--scheme", required=True)
    parser.add_argument("--destination", required=True, help="xcodebuild simulator destination")
    parser.add_argument("--derived-data", required=True)
    parser.add_argument("--test-source", default="Tests/UITests/CuikeUITests.swift")
    parser.add_argument("--log")
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args(argv)
    try:
        return run_probe(args)
    except (OSError, subprocess.SubprocessError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=os.sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
