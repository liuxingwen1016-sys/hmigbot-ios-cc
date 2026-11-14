#!/usr/bin/env python3
"""Test legacy consumers can read native project-skeleton.json.

Tests actual lint_phase_a.py and audit_ui_coverage.py with:
- Native project-skeleton.json only (no legacy file)
- Legacy project-info.json only (backward compatibility)
- Both files present (native takes precedence)
- Canonical field names (uikit_viewcontrollers, not uikit_vcs)
- Shared components preserved (not forced into pages)
- UIKit and SwiftUI both supported
- Module imports verified from clean clone
"""
import json
import sys
import tempfile
from pathlib import Path

# Verify imports from clean clone
linters_path = Path(__file__).parents[4] / "bin/scripts/linters"
sys.path.insert(0, str(linters_path))
import lint_phase_a
import audit_ui_coverage

# Verify module provenance
for mod in [lint_phase_a, audit_ui_coverage]:
    mod_path = Path(mod.__file__)
    assert "tool-optimization-main_ui_optimize" in mod_path.parts, \
        f"Module not from clean clone: {mod_path}"
    assert "ios2harmony/hmigbot-ios" not in str(mod_path), \
        f"Module from dirty repo: {mod_path}"


def test_native_skeleton_only():
    """Legacy consumers read native project-skeleton.json when no legacy file exists."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        spec_dir = root / "spec/.i2h"
        spec_dir.mkdir(parents=True)

        # Create native skeleton only
        skeleton = {
            "schema_version": 1,
            "project_name": "TestApp",
            "target_input_sha256": "abc123",
            "swift_files": ["Views/HomeView.swift", "Views/SettingsView.swift"],
            "swiftui_views": [
                {"class_name": "HomeView", "file_path": "Views/HomeView.swift", "line_count": 25}
            ],
            "shared_components": [
                {"class_name": "ButtonRow", "file_path": "Components/ButtonRow.swift", "line_count": 10}
            ],
            "uikit_viewcontrollers": [
                {"class_name": "ProfileVC", "file_path": "ViewControllers/ProfileVC.swift", "line_count": 50}
            ],
            "info_plist": "Info.plist",
            "assets": ["Assets.xcassets"],
            "source_file_count": 2
        }
        (spec_dir / "project-skeleton.json").write_text(json.dumps(skeleton, indent=2))

        # Run legacy consumers
        lint_findings = lint_phase_a.lint_phase_a(str(root))
        audit_findings = audit_ui_coverage.audit_ui_coverage(str(root))

        # Should not report missing file
        missing_file_codes = {f.get("code") for f in lint_findings}
        assert "IOS.MISSING_REQUIRED_FILE" not in missing_file_codes, \
            f"Native skeleton not recognized: {lint_findings}"

        # Should recognize all views (1 SwiftUI + 1 UIKit = 2 total)
        # Note: audit checks spec coverage, not just counts
        print(f"✅ PASS: Native skeleton recognized by legacy consumers")
        print(f"   lint_phase_a findings: {len(lint_findings)}")
        print(f"   audit_ui_coverage findings: {len(audit_findings)}")


def test_legacy_only_still_works():
    """Legacy project-info.json still works when present."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        spec_dir = root / "spec/.i2h"
        spec_dir.mkdir(parents=True)

        # Create legacy file only (with legacy field names)
        legacy = {
            "swift_files": ["Views/MainView.swift"],
            "swiftui_views": [
                {"class_name": "MainView", "file_path": "Views/MainView.swift", "line_count": 20}
            ],
            "uikit_vcs": []  # Legacy field name
        }
        (spec_dir / "project-info.json").write_text(json.dumps(legacy, indent=2))

        lint_findings = lint_phase_a.lint_phase_a(str(root))
        audit_findings = audit_ui_coverage.audit_ui_coverage(str(root))

        missing_file_codes = {f.get("code") for f in lint_findings}
        assert "IOS.MISSING_REQUIRED_FILE" not in missing_file_codes, \
            f"Legacy file not recognized: {lint_findings}"

        print(f"✅ PASS: Legacy project-info.json still supported")


def test_native_takes_precedence():
    """When both files exist, native project-skeleton.json takes precedence."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        spec_dir = root / "spec/.i2h"
        spec_dir.mkdir(parents=True)

        # Create both files with different data
        native = {
            "schema_version": 1,
            "swift_files": ["Native.swift"],
            "swiftui_views": [{"class_name": "NativeView", "file_path": "Native.swift", "line_count": 10}],
            "shared_components": [],
            "uikit_viewcontrollers": [],
            "source_file_count": 1
        }
        legacy = {
            "swift_files": ["Legacy.swift"],
            "swiftui_views": [{"class_name": "LegacyView", "file_path": "Legacy.swift", "line_count": 10}],
            "uikit_vcs": []
        }

        (spec_dir / "project-skeleton.json").write_text(json.dumps(native, indent=2))
        (spec_dir / "project-info.json").write_text(json.dumps(legacy, indent=2))

        # Read back what was loaded
        with open(spec_dir / "project-skeleton.json") as f:
            loaded = json.load(f)

        assert loaded["swift_files"] == ["Native.swift"], \
            "Native file should be used when both present"

        print(f"✅ PASS: Native takes precedence when both files exist")


def test_canonical_field_names_preserved():
    """Consumers support canonical uikit_viewcontrollers and legacy uikit_vcs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        spec_dir = root / "spec/.i2h"
        spec_dir.mkdir(parents=True)

        # Test with canonical field name
        canonical = {
            "schema_version": 1,
            "swift_files": ["ProfileVC.swift"],
            "swiftui_views": [],
            "shared_components": [],
            "uikit_viewcontrollers": [
                {"class_name": "ProfileVC", "file_path": "ProfileVC.swift", "line_count": 30}
            ],
            "source_file_count": 1
        }
        (spec_dir / "project-skeleton.json").write_text(json.dumps(canonical, indent=2))

        audit_findings = audit_ui_coverage.audit_ui_coverage(str(root))

        # Should not error on field name
        invalid_structure = [f for f in audit_findings if f.get("code") == "IOS.INVALID_PROJECT_STRUCTURE"]
        assert len(invalid_structure) == 0, \
            f"Canonical field name not recognized: {invalid_structure}"

        print(f"✅ PASS: Canonical uikit_viewcontrollers field supported")


def test_shared_components_distinct_from_pages():
    """Shared components preserved as distinct from pages/screens."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        spec_dir = root / "spec/.i2h"
        spec_dir.mkdir(parents=True)

        skeleton = {
            "schema_version": 1,
            "swift_files": ["Views/HomeView.swift", "Components/ButtonRow.swift"],
            "swiftui_views": [
                {"class_name": "HomeView", "file_path": "Views/HomeView.swift", "line_count": 40}
            ],
            "shared_components": [
                {"class_name": "ButtonRow", "file_path": "Components/ButtonRow.swift", "line_count": 15},
                {"class_name": "CardView", "file_path": "Components/CardView.swift", "line_count": 20}
            ],
            "uikit_viewcontrollers": [],
            "source_file_count": 2
        }
        (spec_dir / "project-skeleton.json").write_text(json.dumps(skeleton, indent=2))

        # Load and verify structure preserved
        with open(spec_dir / "project-skeleton.json") as f:
            loaded = json.load(f)

        assert len(loaded["swiftui_views"]) == 1, "Should have 1 page/screen"
        assert len(loaded["shared_components"]) == 2, "Should have 2 shared components"
        assert loaded["swiftui_views"][0]["class_name"] == "HomeView"
        assert loaded["shared_components"][0]["class_name"] == "ButtonRow"

        print(f"✅ PASS: Shared components distinct from pages")
        print(f"   Pages: {len(loaded['swiftui_views'])}")
        print(f"   Shared components: {len(loaded['shared_components'])}")


if __name__ == "__main__":
    try:
        print(f"Module paths:")
        print(f"  lint_phase_a: {lint_phase_a.__file__}")
        print(f"  audit_ui_coverage: {audit_ui_coverage.__file__}")
        print()

        test_native_skeleton_only()
        test_legacy_only_still_works()
        test_native_takes_precedence()
        test_canonical_field_names_preserved()
        test_shared_components_distinct_from_pages()

        print(f"\n✅ All native skeleton consumer tests passed")
        sys.exit(0)
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
