"""Tests for the three new i2h CLI entry-points and related SKILL/installer contracts.

Covers:
A  execute-source spec contract (config reading, path validation, binding, exit 2)
B  execute-inputs spec contract (indexed-v1, static-v1, legacy, validation)
C  retrospect-metrics spec contract (MEASURED/UNKNOWN, two directions, precise counting)
D  SKILL.md content audit
E  installer upgrade preservation
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "migbot/scripts/migbot-install.py"
EXECUTE_SKILL_MD = ROOT / "migbot/skills/i2h-execute/SKILL.md"
RETROSPECT_SKILL_MD = ROOT / "migbot/skills/i2h-retrospect/SKILL.md"


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _install(project: Path, ios_path: str | None = None) -> subprocess.CompletedProcess:
    cmd = [sys.executable, "-B", "-X", "utf8", str(INSTALLER),
           "--project", str(project)]
    if ios_path:
        cmd += ["--ios", ios_path]
    return subprocess.run(cmd, cwd=ROOT, capture_output=True,
                          text=True, encoding="utf-8", timeout=60)


def _i2h(project: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-B", "-X", "utf8",
         str(project / ".migbot/bin/i2h"), *args],
        cwd=project, capture_output=True, text=True, encoding="utf-8", timeout=30
    )


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _write_json(path: Path, data: object) -> Path:
    return _write(path, json.dumps(data, ensure_ascii=False, indent=2))


def _make_ios_project(root: Path, name: str = "TestApp") -> Path:
    """Minimal iOS project dir accepted by execute-source validation."""
    ios = root / name
    _write(ios / f"{name}.xcodeproj/project.pbxproj",
           "// !$*UTF8*$!\n{}\n")
    _write(ios / "Sources/AppDelegate.swift", "import UIKit\n@main class A: UIResponder {}\n")
    return ios


def _make_ios_package(root: Path, name: str = "PkgApp") -> Path:
    """Minimal Swift package accepted by execute-source validation."""
    ios = root / name
    _write(ios / "Package.swift",
           "// swift-tools-version:5.9\nimport PackageDescription\n"
           "let package = Package(name: \"PkgApp\", targets: [])\n")
    return ios


def _make_plans(project: Path, indexed: bool = True) -> None:
    """Create plan files under spec/baseline/plans/."""
    base = project / "spec/baseline/plans"
    if indexed:
        _write(base / "ui-plan.md", "# ui-plan\n## Pages\n")
        _write(base / "feature-plan.md", "# feature-plan\nplan_format: indexed-v1\n## Features\n")
        _write(base / "base-plan.md", "# base-plan\n## Base\n")
        (base / "slices").mkdir(parents=True, exist_ok=True)
    else:
        _write(base / "execution-plan.md", "# old single plan\n")


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _make_complete_static_fixture(project: Path, ios: Path, target_hash: str) -> None:
    """Create complete static-v1 fixture with all required files and proper approved scope."""
    # target-input.json
    target_input = {
        "schema_version": 1,
        "producer": "test_fixture",
        "target_input_sha256": target_hash,
        "inventory": "spec/.i2h/resources-inventory.json",
        "locale": "zh_CN",
        "font_family": "HarmonyOS Sans",
        "theme": "light"
    }
    _write_json(project / "spec/.i2h/target-input.json", target_input)

    # resources-inventory.json
    inventory = {
        "schema_version": 1,
        "producer": "test_fixture",
        "project_root": str(ios),
        "target_input_sha256": target_hash
    }
    _write_json(project / "spec/.i2h/resources-inventory.json", inventory)

    # Resource indexes
    res_index_dir = project / "spec/baseline/res-index"
    for name in ["values.json", "drawables.json", "usage.json", "handoff.json"]:
        idx = {
            "schema_version": 1,
            "target_input_sha256": target_hash,
            "resources": {}
        }
        _write_json(res_index_dir / name, idx)

    # ui-delivery-approved.json
    approved = {
        "schema_version": 2,
        "status": "approved",
        "scope": "test",
        "target_input_sha256": target_hash,
        "source_project_root": str(ios),
        "approval": {
            "timestamp": "2024-11-26T00:00:00Z",
            "confirmation_ref": "test:fixture"
        },
        "units": [
            {
                "unit_id": "test_unit",
                "page_id": "TestPage",
                "required": True,
                "source_refs": [
                    {
                        "file": "TestPage.swift",
                        "line": 1,
                        "sha256": "a" * 64
                    }
                ],
                "output": {
                    "file": "entry/src/main/ets/pages/TestPage.ets",
                    "symbol": "TestPage"
                }
            }
        ]
    }
    _write_json(project / "spec/baseline/ui-delivery-approved.json", approved)


def _installed_project() -> tuple[tempfile.TemporaryDirectory, Path]:
    td = tempfile.TemporaryDirectory()
    project = Path(td.name)
    r = _install(project)
    if r.returncode != 0:
        td.cleanup()
        raise RuntimeError(f"install failed: {r.stderr[:400]}")
    return td, project


# ===========================================================================
# A — execute-source spec contract
# ===========================================================================

def test_execute_source_valid_pbxproj_exits_0():
    td, project = _installed_project()
    try:
        ios = _make_ios_project(project / "fixtures")
        cfg = json.loads((project / ".migbot/config.json").read_text(encoding="utf-8"))
        cfg["ios"] = str(ios)
        _write_json(project / ".migbot/config.json", cfg)
        r = _i2h(project, "execute-source")
        assert r.returncode == 0, r.stderr
        assert Path(r.stdout.strip()).is_absolute()
    finally:
        td.cleanup()


def test_execute_source_valid_package_swift_exits_0():
    td, project = _installed_project()
    try:
        ios = _make_ios_package(project / "fixtures")
        cfg = json.loads((project / ".migbot/config.json").read_text(encoding="utf-8"))
        cfg["ios"] = str(ios)
        _write_json(project / ".migbot/config.json", cfg)
        r = _i2h(project, "execute-source")
        assert r.returncode == 0, r.stderr
    finally:
        td.cleanup()


def test_execute_source_tilde_expansion():
    td, project = _installed_project()
    try:
        ios = _make_ios_project(project / "fixtures", "TildeApp")
        rel = os.path.relpath(str(ios), Path.home())
        cfg = json.loads((project / ".migbot/config.json").read_text(encoding="utf-8"))
        cfg["ios"] = "~/" + rel
        _write_json(project / ".migbot/config.json", cfg)
        r = _i2h(project, "execute-source")
        assert r.returncode == 0, r.stderr
    finally:
        td.cleanup()


def test_execute_source_empty_ios_key_exits_2():
    td, project = _installed_project()
    try:
        cfg = json.loads((project / ".migbot/config.json").read_text(encoding="utf-8"))
        cfg["ios"] = ""
        _write_json(project / ".migbot/config.json", cfg)
        r = _i2h(project, "execute-source")
        assert r.returncode == 2, f"expected exit 2, got {r.returncode}"
    finally:
        td.cleanup()


def test_execute_source_null_ios_key_exits_2():
    td, project = _installed_project()
    try:
        cfg = json.loads((project / ".migbot/config.json").read_text(encoding="utf-8"))
        cfg["ios"] = None
        _write_json(project / ".migbot/config.json", cfg)
        r = _i2h(project, "execute-source")
        assert r.returncode == 2
    finally:
        td.cleanup()


def test_execute_source_bad_json_exits_2_no_traceback():
    td, project = _installed_project()
    try:
        (project / ".migbot/config.json").write_bytes(b"{bad json")
        r = _i2h(project, "execute-source")
        assert r.returncode == 2
        assert "Traceback" not in r.stderr
    finally:
        td.cleanup()


def test_execute_source_bad_utf8_exits_2_no_traceback():
    td, project = _installed_project()
    try:
        (project / ".migbot/config.json").write_bytes(b"\xff\xfe{}")
        r = _i2h(project, "execute-source")
        assert r.returncode == 2
        assert "Traceback" not in r.stderr
    finally:
        td.cleanup()


def test_execute_source_binding_inventory_mismatch():
    """resources-inventory.json project_root must match config ios."""
    td, project = _installed_project()
    try:
        ios = _make_ios_project(project / "fixtures")
        cfg = json.loads((project / ".migbot/config.json").read_text(encoding="utf-8"))
        cfg["ios"] = str(ios)
        _write_json(project / ".migbot/config.json", cfg)

        # Create mismatched inventory
        inventory = {
            "schema_version": 1,
            "project_root": str(project / "other_source"),
            "target_input_sha256": "a" * 64
        }
        _write_json(project / "spec/.i2h/resources-inventory.json", inventory)

        r = _i2h(project, "execute-source")
        assert r.returncode == 2, "should fail on inventory binding mismatch"
    finally:
        td.cleanup()


def test_execute_source_binding_approved_mismatch():
    """ui-delivery-approved.json source_project_root must match config ios."""
    td, project = _installed_project()
    try:
        ios = _make_ios_project(project / "fixtures")
        cfg = json.loads((project / ".migbot/config.json").read_text(encoding="utf-8"))
        cfg["ios"] = str(ios)
        _write_json(project / ".migbot/config.json", cfg)

        # Create mismatched approved
        approved = {
            "schema_version": 2,
            "status": "approved",
            "source_project_root": str(project / "other_source"),
            "target_input_sha256": "b" * 64,
            "units": []
        }
        _write_json(project / "spec/baseline/ui-delivery-approved.json", approved)

        r = _i2h(project, "execute-source")
        assert r.returncode == 2, "should fail on approved binding mismatch"
    finally:
        td.cleanup()


# ===========================================================================
# B — execute-inputs spec contract
# ===========================================================================

def test_execute_inputs_indexed_v1_default():
    """indexed-v1 with complete static-v1 fixture should succeed."""
    td, project = _installed_project()
    try:
        ios = _make_ios_project(project / "fixtures")
        cfg = json.loads((project / ".migbot/config.json").read_text(encoding="utf-8"))
        cfg["ios"] = str(ios)
        _write_json(project / ".migbot/config.json", cfg)

        _make_plans(project, indexed=True)
        _make_complete_static_fixture(project, ios, "a" * 64)

        r = _i2h(project, "execute-inputs")
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        assert data["plan_format"] == "indexed-v1"
        assert "ui_plan" in data["plans"]
    finally:
        td.cleanup()


def test_execute_inputs_unknown_option_rejected():
    """Strict argparse must reject unknown options (no abbreviations)."""
    td, project = _installed_project()
    try:
        ios = _make_ios_project(project / "fixtures")
        cfg = json.loads((project / ".migbot/config.json").read_text(encoding="utf-8"))
        cfg["ios"] = str(ios)
        _write_json(project / ".migbot/config.json", cfg)

        _make_plans(project, indexed=True)
        _make_complete_static_fixture(project, ios, "a" * 64)

        # Test with typo that would be accepted as abbreviation
        r = _i2h(project, "execute-inputs", "--resource-polic", "legacy")
        assert r.returncode == 2, "should reject --resource-polic (typo)"
    finally:
        td.cleanup()


def test_execute_inputs_indexed_missing_slices():
    """indexed-v1 requires slices directory."""
    td, project = _installed_project()
    try:
        ios = _make_ios_project(project / "fixtures")
        cfg = json.loads((project / ".migbot/config.json").read_text(encoding="utf-8"))
        cfg["ios"] = str(ios)
        _write_json(project / ".migbot/config.json", cfg)

        _make_plans(project, indexed=True)
        _make_complete_static_fixture(project, ios, "a" * 64)

        (project / "spec/baseline/plans/slices").rmdir()
        r = _i2h(project, "execute-inputs")
        assert r.returncode == 2, "should fail without slices directory"
    finally:
        td.cleanup()


def test_execute_inputs_indexed_missing_marker():
    """indexed-v1 requires plan_format marker in feature-plan.md."""
    td, project = _installed_project()
    try:
        ios = _make_ios_project(project / "fixtures")
        cfg = json.loads((project / ".migbot/config.json").read_text(encoding="utf-8"))
        cfg["ios"] = str(ios)
        _write_json(project / ".migbot/config.json", cfg)

        _make_plans(project, indexed=True)
        _make_complete_static_fixture(project, ios, "a" * 64)

        _write(project / "spec/baseline/plans/feature-plan.md", "# stale unindexed\n")
        r = _i2h(project, "execute-inputs")
        assert r.returncode == 2, "should fail without plan_format marker"
    finally:
        td.cleanup()


def test_execute_inputs_legacy_explicit():
    """Legacy mode requires explicit --plan-format legacy."""
    td, project = _installed_project()
    try:
        ios = _make_ios_project(project / "fixtures")
        cfg = json.loads((project / ".migbot/config.json").read_text(encoding="utf-8"))
        cfg["ios"] = str(ios)
        _write_json(project / ".migbot/config.json", cfg)

        _make_plans(project, indexed=False)

        # Create approved scope for legacy
        approved = {
            "schema_version": 2,
            "status": "approved",
            "scope": "legacy",
            "source_project_root": str(ios),
            "units": [
                {
                    "unit_id": "legacy_unit",
                    "page_id": "LegacyPage",
                    "required": True,
                    "source_refs": [{"file": "Legacy.swift", "line": 1, "sha256": "b" * 64}],
                    "output": {"file": "entry/src/main/ets/pages/Legacy.ets", "symbol": "Legacy"}
                }
            ]
        }
        _write_json(project / "spec/baseline/ui-delivery-approved.json", approved)

        r = _i2h(project, "execute-inputs", "--plan-format", "legacy", "--resource-policy", "legacy")
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        assert data["plan_format"] == "legacy"
    finally:
        td.cleanup()


def test_execute_inputs_static_v1_missing_target_input():
    """static-v1 requires target-input.json."""
    td, project = _installed_project()
    try:
        _make_plans(project, indexed=True)
        r = _i2h(project, "execute-inputs", "--resource-policy", "static-v1")
        assert r.returncode == 2, "should fail without target-input.json"
    finally:
        td.cleanup()


def test_execute_inputs_static_v1_wrong_shape_target_input():
    """target-input.json must be a dict, not an array."""
    td, project = _installed_project()
    try:
        ios = _make_ios_project(project / "fixtures")
        cfg = json.loads((project / ".migbot/config.json").read_text(encoding="utf-8"))
        cfg["ios"] = str(ios)
        _write_json(project / ".migbot/config.json", cfg)

        _make_plans(project, indexed=True)
        _write_json(project / "spec/.i2h/target-input.json", [])
        r = _i2h(project, "execute-inputs")
        assert r.returncode == 2, "should fail on array target-input"
        assert "Traceback" not in r.stderr
    finally:
        td.cleanup()


def test_execute_inputs_resource_index_wrong_digest():
    """Resource index target_input_sha256 must match target-input.json."""
    td, project = _installed_project()
    try:
        ios = _make_ios_project(project / "fixtures")
        cfg = json.loads((project / ".migbot/config.json").read_text(encoding="utf-8"))
        cfg["ios"] = str(ios)
        _write_json(project / ".migbot/config.json", cfg)

        _make_plans(project, indexed=True)
        _make_complete_static_fixture(project, ios, "a" * 64)

        # Wrong hash in values.json
        values = {
            "schema_version": 1,
            "target_input_sha256": "f" * 64,
            "resources": {}
        }
        _write_json(project / "spec/baseline/res-index/values.json", values)

        r = _i2h(project, "execute-inputs")
        assert r.returncode == 2, "should fail on hash mismatch"
    finally:
        td.cleanup()


def test_execute_inputs_approved_scope_missing():
    """static-v1 requires ui-delivery-approved.json."""
    td, project = _installed_project()
    try:
        ios = _make_ios_project(project / "fixtures")
        cfg = json.loads((project / ".migbot/config.json").read_text(encoding="utf-8"))
        cfg["ios"] = str(ios)
        _write_json(project / ".migbot/config.json", cfg)

        _make_plans(project, indexed=True)

        target_hash = "a" * 64
        target_input = {
            "schema_version": 1,
            "target_input_sha256": target_hash,
            "inventory": "spec/.i2h/resources-inventory.json"
        }
        _write_json(project / "spec/.i2h/target-input.json", target_input)

        inventory = {
            "schema_version": 1,
            "project_root": str(ios),
            "target_input_sha256": target_hash
        }
        _write_json(project / "spec/.i2h/resources-inventory.json", inventory)

        # Create all required indexes
        for name in ["values.json", "drawables.json", "usage.json", "handoff.json"]:
            idx = {
                "schema_version": 1,
                "target_input_sha256": target_hash,
                "resources": {}
            }
            _write_json(project / f"spec/baseline/res-index/{name}", idx)

        r = _i2h(project, "execute-inputs")
        assert r.returncode == 2, "should fail without approved scope"
    finally:
        td.cleanup()


def test_execute_inputs_legacy_requires_approved():
    """Legacy mode also requires ui-delivery-approved.json."""
    td, project = _installed_project()
    try:
        _make_plans(project, indexed=False)
        r = _i2h(project, "execute-inputs", "--plan-format", "legacy", "--resource-policy", "legacy")
        assert r.returncode == 2, "legacy should fail without approved scope"
    finally:
        td.cleanup()


def test_execute_inputs_approved_units_must_be_nonempty():
    """Approved units array must not be empty."""
    td, project = _installed_project()
    try:
        ios = _make_ios_project(project / "fixtures")
        cfg = json.loads((project / ".migbot/config.json").read_text(encoding="utf-8"))
        cfg["ios"] = str(ios)
        _write_json(project / ".migbot/config.json", cfg)

        _make_plans(project, indexed=True)
        target_hash = "a" * 64

        target_input = {
            "schema_version": 1,
            "target_input_sha256": target_hash,
            "inventory": "spec/.i2h/resources-inventory.json"
        }
        _write_json(project / "spec/.i2h/target-input.json", target_input)

        inventory = {
            "schema_version": 1,
            "project_root": str(ios),
            "target_input_sha256": target_hash
        }
        _write_json(project / "spec/.i2h/resources-inventory.json", inventory)

        for name in ["values.json", "drawables.json", "usage.json", "handoff.json"]:
            idx = {"schema_version": 1, "target_input_sha256": target_hash, "resources": {}}
            _write_json(project / f"spec/baseline/res-index/{name}", idx)

        # Empty units
        approved = {
            "schema_version": 2,
            "status": "approved",
            "target_input_sha256": target_hash,
            "source_project_root": str(ios),
            "units": []
        }
        _write_json(project / "spec/baseline/ui-delivery-approved.json", approved)

        r = _i2h(project, "execute-inputs")
        assert r.returncode == 2, "should fail with empty units"
    finally:
        td.cleanup()


# ===========================================================================
# C — retrospect-metrics spec contract
# ===========================================================================

def test_retrospect_metrics_returns_json():
    td, project = _installed_project()
    try:
        r = _i2h(project, "retrospect-metrics")
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        assert "ios" in data
        assert "harmonyos" in data
    finally:
        td.cleanup()


def test_retrospect_metrics_missing_ets_is_unknown():
    """Missing entry/src/main/ets should be UNKNOWN with null total_lines."""
    td, project = _installed_project()
    try:
        r = _i2h(project, "retrospect-metrics")
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        assert data["harmonyos"]["status"] == "UNKNOWN"
        assert data["harmonyos"]["total_lines"] is None
        assert data["harmonyos"]["files"] is None
    finally:
        td.cleanup()


def test_retrospect_metrics_empty_ets_is_measured_zero():
    """Empty entry/src/main/ets should be MEASURED with 0 lines and 0 files."""
    td, project = _installed_project()
    try:
        (project / "entry/src/main/ets").mkdir(parents=True)
        r = _i2h(project, "retrospect-metrics")
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        assert data["harmonyos"]["status"] == "MEASURED"
        assert data["harmonyos"]["total_lines"] == 0
        assert data["harmonyos"]["files"] == 0
    finally:
        td.cleanup()


def test_retrospect_metrics_precise_line_counting():
    """Counts must be precise, including files without trailing newline."""
    td, project = _installed_project()
    try:
        ios = _make_ios_project(project / "fixtures", "CountApp")
        cfg = json.loads((project / ".migbot/config.json").read_text(encoding="utf-8"))
        cfg["ios"] = str(ios)
        _write_json(project / ".migbot/config.json", cfg)

        # iOS: 2 files, 3 lines total
        # AppDelegate.swift already has 2 lines from _make_ios_project
        _write(ios / "Sources/Other.swift", "line1")  # 1 line, no trailing newline

        # HarmonyOS: 1 file, 2 lines
        ets = project / "entry/src/main/ets"
        ets.mkdir(parents=True)
        _write(ets / "Main.ets", "line1\nline2")  # 2 lines, no trailing newline

        r = _i2h(project, "retrospect-metrics")
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)

        assert data["ios"]["status"] == "MEASURED"
        assert data["ios"]["files"] == 2
        assert data["ios"]["total_lines"] == 3

        assert data["harmonyos"]["status"] == "MEASURED"
        assert data["harmonyos"]["files"] == 1
        assert data["harmonyos"]["total_lines"] == 2
    finally:
        td.cleanup()


def test_retrospect_metrics_bad_utf8_is_unknown():
    """Bad UTF-8 file causes UNKNOWN status."""
    td, project = _installed_project()
    try:
        ios = _make_ios_project(project / "fixtures", "BadUtf8")
        (ios / "Sources/Bad.swift").write_bytes(b"\xff\xfe bad bytes\n")
        cfg = json.loads((project / ".migbot/config.json").read_text(encoding="utf-8"))
        cfg["ios"] = str(ios)
        _write_json(project / ".migbot/config.json", cfg)

        r = _i2h(project, "retrospect-metrics")
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        assert data["ios"]["status"] == "UNKNOWN"
        assert data["ios"]["total_lines"] is None
        assert data["ios"]["files"] is None
    finally:
        td.cleanup()


def test_retrospect_metrics_excludes_tests_pods():
    """Tests/ and Pods/ directories must be excluded."""
    td, project = _installed_project()
    try:
        ios = _make_ios_project(project / "fixtures", "ExcludeApp")
        cfg = json.loads((project / ".migbot/config.json").read_text(encoding="utf-8"))
        cfg["ios"] = str(ios)
        _write_json(project / ".migbot/config.json", cfg)

        # Add files in excluded directories
        _write(ios / "Tests/AppTests.swift", "import XCTest\nclass T: XCTestCase {}\n")
        _write(ios / "Pods/SomePod/Pod.swift", "public class Pod {}\n")

        r = _i2h(project, "retrospect-metrics")
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)

        # Should only count AppDelegate.swift (2 lines)
        assert data["ios"]["total_lines"] == 2
        assert data["ios"]["files"] == 1
    finally:
        td.cleanup()


def test_retrospect_metrics_harmonyos_other_project():
    """HarmonyOS pointing to different project must be UNKNOWN."""
    td, project = _installed_project()
    try:
        # Create a separate "other project"
        other_temp = tempfile.TemporaryDirectory(prefix="cc-flow-other-target-")
        td_other = Path(other_temp.name)
        other_project = td_other / "other_hmos_project"
        other_project.mkdir()
        ets = other_project / "entry/src/main/ets"
        ets.mkdir(parents=True)
        _write(ets / "Other.ets", "other\n")

        # Point harmonyos config to other project
        cfg = json.loads((project / ".migbot/config.json").read_text(encoding="utf-8"))
        cfg["harmonyos"] = str(other_project)
        _write_json(project / ".migbot/config.json", cfg)

        r = _i2h(project, "retrospect-metrics")
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)

        assert data["harmonyos"]["status"] == "UNKNOWN"
        assert data["harmonyos"]["total_lines"] is None
        assert "different project" in data["harmonyos"]["reason"]
    finally:
        td.cleanup()
        other_temp.cleanup()


def test_retrospect_metrics_has_receipts_structure():
    """retrospect-metrics must include receipts structure."""
    td, project = _installed_project()
    try:
        r = _i2h(project, "retrospect-metrics")
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)

        assert "receipts" in data
        assert "execute" in data["receipts"]
        assert "verify" in data["receipts"]
        assert "timing" in data["receipts"]
        assert "usage" in data["receipts"]

        # All should have status
        assert "status" in data["receipts"]["execute"]
        assert "status" in data["receipts"]["verify"]
        assert "status" in data["receipts"]["timing"]
        assert "status" in data["receipts"]["usage"]
    finally:
        td.cleanup()


def test_retrospect_stale_execute_marker_unknown():
    """Execute marker with stale hash must be UNKNOWN with original SHA preserved."""
    td, project = _installed_project()
    try:
        ios = _make_ios_project(project / "fixtures")
        cfg = json.loads((project / ".migbot/config.json").read_text(encoding="utf-8"))
        cfg["ios"] = str(ios)
        _write_json(project / ".migbot/config.json", cfg)

        _make_plans(project, indexed=True)
        current_hash = "a" * 64
        _make_complete_static_fixture(project, ios, current_hash)

        # Write stale execute marker with old hash
        stale_hash = "f" * 64
        marker_path = project / "spec/execution/stage5-complete.txt"
        marker_path.parent.mkdir(parents=True, exist_ok=True)

        # Create a simple marker with stale hash
        stale_marker = {
            "schema_version": 2,
            "stage": "i2h-execute",
            "status": "PASS",
            "inputs_sha256": stale_hash,
            "artifacts": []
        }
        _write_json(marker_path, stale_marker)

        # Also create migration-report.md
        _write(project / "spec/migration-report.md", "# Migration Report\n")

        r = _i2h(project, "retrospect-metrics")
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)

        exec_receipt = data["receipts"]["execute"]
        assert exec_receipt["status"] == "UNKNOWN"
        assert "path" in exec_receipt
        assert exec_receipt["path"].endswith("stage5-complete.txt")
        assert "sha256" in exec_receipt
        # SHA must be of actual file, not invented
        actual_sha = _sha256_file(marker_path)
        assert exec_receipt["sha256"] == actual_sha
    finally:
        td.cleanup()


def test_retrospect_unbound_verify_recorded_unverified():
    """Verify report without run binding must be RECORDED_UNVERIFIED with original SHA."""
    td, project = _installed_project()
    try:
        # Create verify-report.md without binding
        verify_report = project / "spec/verify-report.md"
        verify_report.parent.mkdir(parents=True, exist_ok=True)
        _write(verify_report, "# Verify Report\n## Status: PASS\n")

        r = _i2h(project, "retrospect-metrics")
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)

        verify_receipt = data["receipts"]["verify"]
        assert verify_receipt["status"] == "RECORDED_UNVERIFIED"
        assert Path(verify_receipt["path"]).resolve() == verify_report.resolve()
        assert verify_receipt["sha256"] == _sha256_file(verify_report)
        assert "lacks provable run binding" in verify_receipt["reason"]
    finally:
        td.cleanup()


def test_retrospect_missing_usage_unknown():
    """Missing usage receipt must be UNKNOWN with null cost."""
    td, project = _installed_project()
    try:
        r = _i2h(project, "retrospect-metrics")
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)

        usage_receipt = data["receipts"]["usage"]
        assert usage_receipt["status"] == "UNKNOWN"
        assert usage_receipt["total_cost_usd"] is None
        assert "no bound usage receipt" in usage_receipt["reason"]
    finally:
        td.cleanup()


def test_retrospect_valid_execute_marker_bound():
    """Valid execute marker with matching hash should be BOUND."""
    td, project = _installed_project()
    try:
        ios = _make_ios_project(project / "fixtures")
        cfg = json.loads((project / ".migbot/config.json").read_text(encoding="utf-8"))
        cfg["ios"] = str(ios)
        _write_json(project / ".migbot/config.json", cfg)

        _make_plans(project, indexed=True)
        current_hash = "a" * 64
        _make_complete_static_fixture(project, ios, current_hash)

        # Write valid execute marker using marker_contract
        sys.path.insert(0, str(ROOT / "migbot/bin/scripts/pipeline"))
        import marker_contract

        report_path = project / "spec/migration-report.md"
        _write(report_path, "# Migration Report\nStatus: Complete\n")

        marker_contract.write_marker(
            path=str(project / "spec/execution/stage5-complete.txt"),
            stage="i2h-execute",
            artifact_paths=[str(report_path)],
            inputs_sha256=current_hash,
            root=str(project)
        )

        r = _i2h(project, "retrospect-metrics")
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)

        exec_receipt = data["receipts"]["execute"]
        assert exec_receipt["status"] == "BOUND"
        assert exec_receipt["target_input_sha256"] == current_hash
        assert "validation" in exec_receipt
    finally:
        td.cleanup()


def test_real_ui_evidence_to_execute_inputs():
    """Real ui_evidence producer to installed execute-inputs integration."""
    td, project = _installed_project()
    try:
        # Create real iOS project
        ios = project / "fixtures" / "RealApp"
        ios.mkdir(parents=True)
        _write(ios / "Package.swift", "// swift-tools-version:5.9\nimport PackageDescription\n")
        _write(ios / "Sources/Screen.swift",
               'import SwiftUI\nstruct Screen: View { var body: some View { Text("Hello") } }\n')

        cfg = json.loads((project / ".migbot/config.json").read_text(encoding="utf-8"))
        cfg["ios"] = str(ios)
        _write_json(project / ".migbot/config.json", cfg)

        _make_plans(project, indexed=True)

        # Call real ui_evidence producer
        ui_evidence_script = project / ".claude/skills/i2h-spec/scripts/ui_evidence.py"
        assert ui_evidence_script.is_file(), "installed ui_evidence producer is missing"

        inventory_path = project / "spec/.i2h/resources-inventory.json"
        res_index_dir = project / "spec/baseline/res-index"

        r = subprocess.run(
            [sys.executable, "-B", str(ui_evidence_script),
             str(ios),
             "--output", str(inventory_path),
             "--res-index", str(res_index_dir)],
            cwd=project,
            capture_output=True,
            text=True,
            timeout=30
        )
        assert r.returncode == 0, f"ui_evidence failed: {r.stderr}"

        # Read auto-generated target-input.json
        target_input_path = project / "spec/.i2h/target-input.json"
        assert target_input_path.is_file()
        target_input = json.loads(target_input_path.read_text(encoding="utf-8"))
        assert target_input.get("schema_version") == 1
        real_hash = target_input["target_input_sha256"]

        # Create approved scope with real hash
        screen_sha = _sha256_file(ios / "Sources/Screen.swift")
        approved = {
            "schema_version": 2,
            "status": "approved",
            "scope": "real_evidence",
            "target_input_sha256": real_hash,
            "source_project_root": str(ios),
            "approval": {
                "timestamp": "2024-11-26T00:00:00Z",
                "confirmation_ref": "test:real_evidence"
            },
            "units": [
                {
                    "unit_id": "screen",
                    "page_id": "Screen",
                    "required": True,
                    "source_refs": [
                        {
                            "file": "Sources/Screen.swift",
                            "line": 2,
                            "sha256": screen_sha
                        }
                    ],
                    "output": {
                        "file": "entry/src/main/ets/pages/Screen.ets",
                        "symbol": "Screen"
                    }
                }
            ]
        }
        _write_json(project / "spec/baseline/ui-delivery-approved.json", approved)

        # Call execute-inputs
        r = _i2h(project, "execute-inputs")
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        assert data["resource_policy"] == "static-v1"
        assert data["resources"]["target_input_sha256"] == real_hash

        # Exercise non-empty usage from the real producer, not a copied schema.
        for expression, expected_exit in [('Image("MissingAsset")', 2), ('Image(systemName: "star")', 0)]:
            _write(ios / "Sources/Screen.swift", 'import SwiftUI\nstruct Screen: View { var body: some View { ' + expression + ' } }\n')
            produced = subprocess.run(
                [sys.executable, "-B", str(ui_evidence_script), str(ios),
                 "--output", str(inventory_path), "--res-index", str(res_index_dir)],
                cwd=project, capture_output=True, text=True, timeout=30,
            )
            assert produced.returncode == 0, produced.stderr
            next_hash = json.loads(target_input_path.read_text())["target_input_sha256"]
            approved["target_input_sha256"] = next_hash
            approved["units"][0]["source_refs"][0]["sha256"] = _sha256_file(ios / "Sources/Screen.swift")
            _write_json(project / "spec/baseline/ui-delivery-approved.json", approved)
            checked = _i2h(project, "execute-inputs")
            assert checked.returncode == expected_exit, checked.stderr + checked.stdout
            if expected_exit == 0:
                obligations = json.loads(checked.stdout)["resources"]["system_symbol_target_mapping_obligations"]
                assert any(row["name"] == "star" for row in obligations)
    finally:
        td.cleanup()


def test_selected_missing_asset_blocks():
    """Selected scope with missing named image must block."""
    td, project = _installed_project()
    try:
        ios = project / "fixtures" / "MissingApp"
        ios.mkdir(parents=True)
        _write(ios / "Package.swift", "// swift-tools-version:5.9\n")
        _write(ios / "Sources/Screen.swift",
               'import SwiftUI\nstruct Screen: View { var body: some View { Image("MissingAsset") } }\n')

        cfg = json.loads((project / ".migbot/config.json").read_text(encoding="utf-8"))
        cfg["ios"] = str(ios)
        _write_json(project / ".migbot/config.json", cfg)

        _make_plans(project, indexed=True)

        # Simulate ui_evidence output with missing asset
        current_hash = "b" * 64
        target_input = {
            "schema_version": 1,
            "target_input_sha256": current_hash,
            "inventory": "spec/.i2h/resources-inventory.json"
        }
        _write_json(project / "spec/.i2h/target-input.json", target_input)

        inventory = {
            "schema_version": 1,
            "project_root": str(ios),
            "target_input_sha256": current_hash
        }
        _write_json(project / "spec/.i2h/resources-inventory.json", inventory)

        # Create usage.json with missing asset in dict format
        usage = {
            "schema_version": 1,
            "target_input_sha256": current_hash,
            "resources": {
                "MissingAsset": {
                    "references": [
                        {
                            "kind": "image",
                            "name": "MissingAsset",
                            "file": "Sources/Screen.swift",
                            "line": 2
                        }
                    ],
                    "resolved": False,
                    "disposition": "unresolved"
                }
            }
        }
        res_index_dir = project / "spec/baseline/res-index"
        _write_json(res_index_dir / "usage.json", usage)

        for name in ["values.json", "drawables.json", "handoff.json"]:
            _write_json(res_index_dir / name, {
                "schema_version": 1,
                "target_input_sha256": current_hash,
                "resources": {}
            })

        # Approved scope selects Screen.swift
        screen_sha = _sha256_file(ios / "Sources/Screen.swift")
        approved = {
            "schema_version": 2,
            "status": "approved",
            "target_input_sha256": current_hash,
            "source_project_root": str(ios),
            "units": [
                {
                    "unit_id": "screen",
                    "source_refs": [{"file": "Sources/Screen.swift", "line": 2, "sha256": screen_sha}],
                    "output": {"file": "entry/src/main/ets/pages/Screen.ets", "symbol": "Screen"}
                }
            ]
        }
        _write_json(project / "spec/baseline/ui-delivery-approved.json", approved)

        r = _i2h(project, "execute-inputs")
        assert r.returncode == 2, "should block on missing asset"
        assert "BLOCKED" in r.stderr
    finally:
        td.cleanup()


def test_system_symbol_mapping_obligation():
    """System symbol (SF Symbol) should be recorded as mapping obligation, not block."""
    td, project = _installed_project()
    try:
        ios = project / "fixtures" / "SymbolApp"
        ios.mkdir(parents=True)
        _write(ios / "Package.swift", "// swift-tools-version:5.9\n")
        _write(ios / "Sources/Screen.swift",
               'import SwiftUI\nstruct Screen: View { var body: some View { Image(systemName: "star") } }\n')

        cfg = json.loads((project / ".migbot/config.json").read_text(encoding="utf-8"))
        cfg["ios"] = str(ios)
        _write_json(project / ".migbot/config.json", cfg)

        _make_plans(project, indexed=True)

        current_hash = "c" * 64
        target_input = {
            "schema_version": 1,
            "target_input_sha256": current_hash,
            "inventory": "spec/.i2h/resources-inventory.json"
        }
        _write_json(project / "spec/.i2h/target-input.json", target_input)

        inventory = {
            "schema_version": 1,
            "project_root": str(ios),
            "target_input_sha256": current_hash
        }
        _write_json(project / "spec/.i2h/resources-inventory.json", inventory)

        # Usage with system_symbol
        usage = {
            "schema_version": 1,
            "target_input_sha256": current_hash,
            "resources": {
                "star": {
                    "references": [
                        {
                            "kind": "system_symbol",
                            "name": "star",
                            "file": "Sources/Screen.swift",
                            "line": 2
                        }
                    ],
                    "resolved": False,
                    "disposition": "unresolved"
                }
            }
        }
        _write_json(project / "spec/baseline/res-index/usage.json", usage)

        for name in ["values.json", "drawables.json", "handoff.json"]:
            _write_json(project / f"spec/baseline/res-index/{name}", {
                "schema_version": 1,
                "target_input_sha256": current_hash,
                "resources": {}
            })

        screen_sha = _sha256_file(ios / "Sources/Screen.swift")
        approved = {
            "schema_version": 2,
            "status": "approved",
            "target_input_sha256": current_hash,
            "source_project_root": str(ios),
            "units": [
                {
                    "unit_id": "screen",
                    "source_refs": [{"file": "Sources/Screen.swift", "line": 2, "sha256": screen_sha}],
                    "output": {"file": "entry/src/main/ets/pages/Screen.ets", "symbol": "Screen"}
                }
            ]
        }
        _write_json(project / "spec/baseline/ui-delivery-approved.json", approved)

        r = _i2h(project, "execute-inputs")
        assert r.returncode == 0, f"should not block on system symbol: {r.stderr}"
        data = json.loads(r.stdout)
        assert "system_symbol_target_mapping_obligations" in data["resources"]
        obligations = data["resources"]["system_symbol_target_mapping_obligations"]
        assert len(obligations) > 0
        assert obligations[0]["name"] == "star"
        assert obligations[0]["kind"] == "system_symbol"
    finally:
        td.cleanup()


def test_all_entrypoints_truly_read_only_no_pycache():
    """Verify commands don't generate __pycache__ even without -B flag."""
    td, project = _installed_project()
    try:
        ios = _make_ios_project(project / "fixtures")
        cfg = json.loads((project / ".migbot/config.json").read_text(encoding="utf-8"))
        cfg["ios"] = str(ios)
        _write_json(project / ".migbot/config.json", cfg)

        _make_plans(project, indexed=True)
        _make_complete_static_fixture(project, ios, "d" * 64)

        # Snapshot all files before
        before = {}
        for p in project.rglob("*"):
            if p.is_file():
                before[str(p.relative_to(project))] = _sha256_file(p)

        # Run without -B flag (remove it from subprocess call)
        env = os.environ.copy()
        env.pop("PYTHONDONTWRITEBYTECODE", None)

        for cmd in ["execute-source", "execute-inputs", "retrospect-metrics"]:
            subprocess.run(
                [sys.executable, str(project / ".migbot/bin/i2h"), cmd],
                cwd=project,
                capture_output=True,
                env=env,
                timeout=30
            )

        # Verify no files changed or added
        after = {}
        for p in project.rglob("*"):
            if p.is_file():
                after[str(p.relative_to(project))] = _sha256_file(p)

        assert before == after, "read-only commands modified or added files (including __pycache__)"
    finally:
        td.cleanup()


def test_execute_inputs_requires_valid_source():
    """execute-inputs must validate source config before proceeding."""
    td, project = _installed_project()
    try:
        # Set invalid ios config
        cfg = json.loads((project / ".migbot/config.json").read_text(encoding="utf-8"))
        cfg["ios"] = None
        _write_json(project / ".migbot/config.json", cfg)

        _make_plans(project, indexed=True)

        r = _i2h(project, "execute-inputs")
        assert r.returncode == 2, "should fail on invalid source config"
        assert "ios" in r.stderr.lower()
    finally:
        td.cleanup()


# ===========================================================================
# D — SKILL.md content audit
# ===========================================================================

def test_execute_skill_references_three_plans():
    """SKILL.md must reference ui-plan, feature-plan, base-plan in startup."""
    text = EXECUTE_SKILL_MD.read_text(encoding="utf-8")
    # Check that startup sections reference all three plans
    assert "ui-plan" in text
    assert "feature-plan" in text
    assert "base-plan" in text


def test_execute_skill_allows_legacy_mention():
    """SKILL.md can mention execution-plan.md for legacy compatibility explanation."""
    text = EXECUTE_SKILL_MD.read_text(encoding="utf-8")
    # execution-plan.md is allowed when explaining legacy mode
    # Just ensure the main startup uses the three-plan format
    assert "ui-plan" in text and "feature-plan" in text and "base-plan" in text


def test_execute_skill_no_wrong_config_key():
    """SKILL.md must not use ios_project_path or spec/.i2h/config.json."""
    text = EXECUTE_SKILL_MD.read_text(encoding="utf-8")
    assert "ios_project_path" not in text
    assert "spec/.i2h/config.json" not in text


def test_retrospect_skill_no_cuike():
    """retrospect SKILL.md must not hardcode 'Cuike'."""
    text = RETROSPECT_SKILL_MD.read_text(encoding="utf-8")
    assert "Cuike" not in text


def test_retrospect_skill_no_fixed_numbers():
    """retrospect SKILL.md must not hardcode specific line counts or rates."""
    text = RETROSPECT_SKILL_MD.read_text(encoding="utf-8")
    # Allow mentioning these in warnings about what NOT to do
    # Check they're not presented as actual values
    for forbidden in ["1,878", "1878", "2,485", "2485"]:
        assert forbidden not in text, f"SKILL.md contains hardcoded {forbidden}"

    # These should not appear even in examples
    for forbidden in ["420K"]:
        assert forbidden not in text, f"SKILL.md contains hardcoded {forbidden}"


def test_retrospect_skill_no_wc_pipeline():
    """retrospect SKILL.md must not use 'wc -l' pipeline."""
    text = RETROSPECT_SKILL_MD.read_text(encoding="utf-8")
    assert "wc -l" not in text and "wc-l" not in text


# ===========================================================================
# E — installer upgrade preservation
# ===========================================================================

def test_installer_upgrade_preserves_config():
    td, project = _installed_project()
    try:
        cfg_path = project / ".migbot/config.json"
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        cfg["ios"] = "/custom/ios/path"
        cfg["custom_key"] = "preserved"
        _write_json(cfg_path, cfg)

        # Upgrade
        r = _install(project)
        assert r.returncode == 0, r.stderr

        cfg2 = json.loads(cfg_path.read_text(encoding="utf-8"))
        assert cfg2["ios"] == "/custom/ios/path"
        assert cfg2["custom_key"] == "preserved"
    finally:
        td.cleanup()


def test_installer_upgrade_preserves_approved_scope():
    td, project = _installed_project()
    try:
        approved = project / "spec/baseline/ui-delivery-approved.json"
        approved.parent.mkdir(parents=True, exist_ok=True)
        sentinel = {"schema_version": 2, "status": "approved", "units": [], "_test": "sentinel"}
        _write_json(approved, sentinel)
        original_bytes = approved.read_bytes()

        # Upgrade
        r = _install(project)
        assert r.returncode == 0, r.stderr

        assert approved.exists()
        assert approved.read_bytes() == original_bytes
    finally:
        td.cleanup()


def test_all_entrypoints_are_read_only():
    """execute-source, execute-inputs, retrospect-metrics must not modify files."""
    td, project = _installed_project()
    try:
        ios = _make_ios_project(project / "fixtures")
        cfg = json.loads((project / ".migbot/config.json").read_text(encoding="utf-8"))
        cfg["ios"] = str(ios)
        _write_json(project / ".migbot/config.json", cfg)

        _make_plans(project, indexed=True)
        _make_complete_static_fixture(project, ios, "a" * 64)

        # Snapshot all files
        before = {}
        for p in project.rglob("*"):
            if p.is_file():
                before[str(p.relative_to(project))] = _sha256_file(p)

        # Run all three commands
        _i2h(project, "execute-source")
        _i2h(project, "execute-inputs")
        _i2h(project, "retrospect-metrics")

        # Verify no files changed
        after = {}
        for p in project.rglob("*"):
            if p.is_file():
                after[str(p.relative_to(project))] = _sha256_file(p)

        assert before == after, "read-only commands modified files"
    finally:
        td.cleanup()


if __name__ == "__main__":
    import sys
    # Run tests
    failures = []
    for name, obj in list(globals().items()):
        if name.startswith("test_") and callable(obj):
            try:
                print(f"Running {name}...", end=" ")
                obj()
                print("PASS")
            except Exception as e:
                print(f"FAIL: {e}")
                failures.append((name, e))

    if failures:
        print(f"\n{len(failures)} test(s) failed:")
        for name, e in failures:
            print(f"  {name}: {e}")
        sys.exit(1)
    else:
        print(f"\nAll tests passed!")
        sys.exit(0)


def test_timing_directory_receipts_are_discoverable_without_inferred_duration():
    td, project = _installed_project()
    try:
        timing = project / "spec/.i2h/timing/running-fixture.json"
        _write_json(timing, {"run_id": "running-fixture", "status": "running"})
        result = _i2h(project, "retrospect-metrics")
        assert result.returncode == 0, result.stderr
        observed = json.loads(result.stdout)["receipts"]["timing"]
        assert observed["status"] == "RECORDED_UNVERIFIED"
        assert Path(observed["path"]).resolve() == timing.resolve()
        assert observed["sha256"] == _sha256_file(timing)
        assert observed.get("duration_seconds") is None
    finally:
        td.cleanup()


def test_actual_retrospect_closeout_requires_hash_and_writes_original_schema2():
    import re
    td, project = _installed_project()
    try:
        text = (project / ".claude/skills/i2h-retrospect/SKILL.md").read_text(encoding="utf-8")
        snippets = re.findall(r"```bash\n(.*?)\n```", text, flags=re.S)
        step, = [block for block in snippets if "marker_contract.write_marker(" in block]
        date = subprocess.check_output(["date", "+%Y-%m-%d"], text=True).strip()
        report = project / ("docs/retrospect-report-" + date + ".md")
        _write(report, "# Fixture report\n\nVerify: UNKNOWN\n")
        marker = project / "spec/retrospect-complete.txt"
        result = subprocess.run(["/bin/bash", "-c", step], cwd=project, capture_output=True, text=True, timeout=15)
        assert result.returncode != 0
        assert not marker.exists(), "unknown input must not mint a completion marker"
        _write_json(project / "spec/.i2h/target-input.json", {"target_input_sha256": "a" * 64})
        result = subprocess.run(["/bin/bash", "-c", step], cwd=project, capture_output=True, text=True, timeout=15)
        assert result.returncode == 0, result.stderr + result.stdout
        recorded = json.loads(marker.read_text())
        assert recorded["schema_version"] == 2
        assert recorded["stage"] == "i2h-retrospect"
        assert recorded["inputs_sha256"] == "a" * 64
        assert recorded["artifacts"][0]["sha256"] == _sha256_file(report)
        assert (project / ".migbot/metrics" / project.name / "retrospect.done").is_file()
    finally:
        td.cleanup()
