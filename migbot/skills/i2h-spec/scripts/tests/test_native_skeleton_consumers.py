#!/usr/bin/env python3
"""Test legacy consumers (lint_phase_a, audit_ui_coverage) read native skeleton.

Portability: module path verified relative to this file, not by hardcoded
repo-name fragment. All calls go through actual consumer functions.
"""
import json
import sys
import tempfile
from pathlib import Path

# Linters live at <repo>/migbot/bin/scripts/linters; this file is at
# <repo>/migbot/skills/i2h-spec/scripts/tests.  Four parents up is <repo>.
_REPO_ROOT = Path(__file__).resolve().parents[5]
_LINTERS_PATH = _REPO_ROOT / "migbot/bin/scripts/linters"
sys.path.insert(0, str(_LINTERS_PATH))

import lint_phase_a
import audit_ui_coverage

# Portable provenance: modules must be siblings of _LINTERS_PATH, not from
# the dirty original repo or any other installed copy.
for _mod in [lint_phase_a, audit_ui_coverage]:
    _mod_path = Path(_mod.__file__).resolve()
    assert _mod_path.parent == _LINTERS_PATH.resolve(), (
        f"Module loaded from unexpected path: {_mod_path} "
        f"(expected parent {_LINTERS_PATH.resolve()})"
    )
    print(f"  provenance OK: {_mod_path}")


def _make_skeleton(*, swiftui_views=None, uikit_viewcontrollers=None,
                   shared_components=None, swift_files=None, extra=None):
    s = {
        "schema_version": 1,
        "swift_files": swift_files or [],
        "swiftui_views": swiftui_views or [],
        "shared_components": shared_components or [],
        "uikit_viewcontrollers": uikit_viewcontrollers if uikit_viewcontrollers is not None else [],
        "source_file_count": len(swift_files or []),
    }
    if extra:
        s.update(extra)
    return s


def test_native_skeleton_recognized_no_legacy():
    """lint_phase_a reads project-skeleton.json with no project-info.json present."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "spec/.i2h").mkdir(parents=True)
        skeleton = _make_skeleton(
            swift_files=["Views/HomeView.swift", "ViewControllers/ProfileVC.swift"],
            swiftui_views=[{"class_name": "HomeView", "file_path": "Views/HomeView.swift", "line_count": 20}],
            uikit_viewcontrollers=[{"class_name": "ProfileVC", "file_path": "ViewControllers/ProfileVC.swift", "line_count": 40}],
        )
        (root / "spec/.i2h/project-skeleton.json").write_text(json.dumps(skeleton))

        findings = lint_phase_a.lint_phase_a(str(root))
        codes = {f.get("code") for f in findings}
        assert "IOS.MISSING_REQUIRED_FILE" not in codes, \
            f"Unexpected MISSING_REQUIRED_FILE when skeleton present: {findings}"
        assert "IOS.INVALID_PROJECT_STRUCTURE" not in codes, \
            f"Unexpected INVALID_PROJECT_STRUCTURE: {findings}"
        print(f"✅ PASS: native skeleton recognised; lint findings={[f.get('code') for f in findings]}")


def test_legacy_project_info_still_accepted():
    """lint_phase_a falls back to legacy project-info.json and doesn't alter extra fields."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "spec/.i2h").mkdir(parents=True)
        # Include a field that belongs to legacy format and must not be removed
        legacy_data = {
            "swift_files": ["App/Main.swift"],
            "swiftui_views": [{"class_name": "MainView", "file_path": "App/Main.swift", "line_count": 15}],
            "uikit_vcs": [],
            "extra_legacy_field": "should-survive",   # unknown field — must not be touched
        }
        (root / "spec/.i2h/project-info.json").write_text(json.dumps(legacy_data))

        findings = lint_phase_a.lint_phase_a(str(root))
        codes = {f.get("code") for f in findings}
        assert "IOS.MISSING_REQUIRED_FILE" not in codes, f"Legacy file not recognised: {findings}"

        # Verify unknown field is untouched (consumers must not rewrite the file)
        reread = json.loads((root / "spec/.i2h/project-info.json").read_text())
        assert reread.get("extra_legacy_field") == "should-survive", \
            "Legacy extra fields must not be altered"
        print("✅ PASS: legacy project-info.json accepted; extra fields preserved")


def test_native_takes_precedence_consumer_sees_correct_counts():
    """When both files exist, audit consumer uses native skeleton counts, not legacy."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "spec/.i2h").mkdir(parents=True)
        # Native: 2 SwiftUI + 1 UIKit
        native = _make_skeleton(
            swift_files=["N1.swift", "N2.swift", "N3.swift"],
            swiftui_views=[
                {"class_name": "NativeA", "file_path": "N1.swift", "line_count": 10},
                {"class_name": "NativeB", "file_path": "N2.swift", "line_count": 10},
            ],
            uikit_viewcontrollers=[
                {"class_name": "NativeVC", "file_path": "N3.swift", "line_count": 20},
            ],
        )
        # Legacy: only 1 SwiftUI, no UIKit
        legacy = {
            "swift_files": ["Legacy.swift"],
            "swiftui_views": [{"class_name": "LegacyView", "file_path": "Legacy.swift", "line_count": 5}],
            "uikit_vcs": [],
        }
        (root / "spec/.i2h/project-skeleton.json").write_text(json.dumps(native))
        (root / "spec/.i2h/project-info.json").write_text(json.dumps(legacy))

        # Create ui/ dir with 3 page specs matching native count
        ui_dir = root / "spec/baseline/ui"
        ui_dir.mkdir(parents=True)
        for name in ("page_0001_NativeA.md", "page_0002_NativeB.md", "page_0003_NativeVC.md"):
            (ui_dir / name).write_text(f"# {name}\n")

        findings = audit_ui_coverage.audit_ui_coverage(str(root))
        low_cov = [f for f in findings if f.get("code") == "IOS.UI_COVERAGE_LOW"]
        # 3 specs / 3 sources = 100 % -> no warning expected
        assert len(low_cov) == 0, (
            "Coverage should be 100% against native (3/3), but got LOW warning.\n"
            "This likely means the legacy denominator (1 view) was used instead."
        )
        print("✅ PASS: native precedence; consumer denominator = 3 (not legacy 1)")


def test_canonical_uikit_empty_list_not_or_fallback():
    """uikit_viewcontrollers=[] must not fall back to uikit_vcs via `or`."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "spec/.i2h").mkdir(parents=True)
        # Skeleton with canonical key present but empty list AND stale legacy key with entries
        data = {
            "schema_version": 1,
            "swift_files": ["V.swift"],
            "swiftui_views": [{"class_name": "Only", "file_path": "V.swift", "line_count": 10}],
            "shared_components": [],
            "uikit_viewcontrollers": [],          # canonical, empty — must be honoured
            "uikit_vcs": [{"class_name": "Stale", "file_path": "S.swift"}],  # stale legacy
        }
        (root / "spec/.i2h/project-skeleton.json").write_text(json.dumps(data))

        # Create 1 spec page matching the 1 swiftui_view
        ui_dir = root / "spec/baseline/ui"
        ui_dir.mkdir(parents=True)
        (ui_dir / "page_0001_Only.md").write_text("# Only\n")

        findings = audit_ui_coverage.audit_ui_coverage(str(root))
        low_cov = [f for f in findings if f.get("code") == "IOS.UI_COVERAGE_LOW"]
        # Denominator must be 1 (canonical empty UIKit) → 1/1 = 100 %, no warning
        assert len(low_cov) == 0, (
            "uikit_viewcontrollers=[] with uikit_vcs stale entry must not inflate denominator.\n"
            f"Got findings: {findings}"
        )
        print("✅ PASS: canonical empty uikit_viewcontrollers honoured; stale uikit_vcs ignored")


def test_shared_components_not_in_coverage_denominator():
    """Shared components must not inflate the page-coverage denominator."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "spec/.i2h").mkdir(parents=True)
        skeleton = _make_skeleton(
            swift_files=["Views/Page.swift", "Components/Row.swift"],
            swiftui_views=[{"class_name": "PageView", "file_path": "Views/Page.swift", "line_count": 30}],
            shared_components=[
                {"class_name": "RowView", "file_path": "Components/Row.swift", "line_count": 8}
            ],
            uikit_viewcontrollers=[],
        )
        (root / "spec/.i2h/project-skeleton.json").write_text(json.dumps(skeleton))

        # 1 spec for 1 page; shared component has no spec (correct)
        ui_dir = root / "spec/baseline/ui"
        ui_dir.mkdir(parents=True)
        (ui_dir / "page_0001_PageView.md").write_text("# PageView\n")

        findings = audit_ui_coverage.audit_ui_coverage(str(root))
        low_cov = [f for f in findings if f.get("code") == "IOS.UI_COVERAGE_LOW"]
        # 1 spec / 1 page (component excluded) = 100 %; if components are counted → 1/2 = 50 %
        assert len(low_cov) == 0, (
            "Shared components must not count in denominator.\n"
            f"Got findings: {findings}"
        )
        print("✅ PASS: shared components excluded from page-coverage denominator")


if __name__ == "__main__":
    try:
        print("Module paths:")
        print(f"  lint_phase_a: {lint_phase_a.__file__}")
        print(f"  audit_ui_coverage: {audit_ui_coverage.__file__}")
        print()

        test_native_skeleton_recognized_no_legacy()
        test_legacy_project_info_still_accepted()
        test_native_takes_precedence_consumer_sees_correct_counts()
        test_canonical_uikit_empty_list_not_or_fallback()
        test_shared_components_not_in_coverage_denominator()

        print("\n✅ All native skeleton consumer tests passed")
        sys.exit(0)
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
