#!/usr/bin/env python3
"""Test lint_plan_coverage reads canonical feat_*.md files and extracts complexity correctly."""
import json
import tempfile
from pathlib import Path
import sys

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parents[1]))
from lint_plan_coverage import PlanCoverageLinter


def test_parse_feature_specs_canonical():
    """Verify _parse_feature_specs reads feat_*.md with markdown bold complexity."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        features_dir = root / "spec/baseline/features"
        features_dir.mkdir(parents=True)

        # Create canonical feat_fNNN_name.md file with markdown bold complexity
        canonical = features_dir / "feat_f001_test_feature.md"
        canonical.write_text("""# F001: Test Feature

## 基本信息

- **Feature ID**: `F001`
- **复杂度**: medium
- **优先级**: P0
""")

        # Create legacy F*.md file (should still be supported)
        legacy = features_dir / "F002_legacy.md"
        legacy.write_text("- **复杂度**: high\n")

        linter = PlanCoverageLinter(str(root))
        features = linter._parse_feature_specs()

        # Should find both F001 and F002
        assert "F001" in features, f"Expected F001 in {features.keys()}"
        assert features["F001"]["complexity"] == "medium", f"Expected medium, got {features['F001']}"

        assert "F002" in features, f"Expected F002 in {features.keys()}"
        assert features["F002"]["complexity"] == "high", f"Expected high, got {features['F002']}"

        print("✅ PASS: Parses both canonical and legacy formats with markdown bold complexity")
        return 0


def test_feature_id_extraction():
    """Verify feature ID extraction from multiple formats."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        features_dir = root / "spec/baseline/features"
        features_dir.mkdir(parents=True)

        # Canonical: feat_fNNN_name.md
        (features_dir / "feat_f001_auth.md").write_text("- **复杂度**: simple\n")

        # Canonical alt: feat_NNN_name.md
        (features_dir / "feat_099_network.md").write_text("- **复杂度**: complex\n")

        # Legacy: FNNN_name.md
        (features_dir / "F200_helper.md").write_text("- **复杂度**: medium\n")

        # Heading-based: no ID in filename
        (features_dir / "some_feature.md").write_text("# F300: Some Feature\n\n- **复杂度**: low\n")

        linter = PlanCoverageLinter(str(root))
        features = linter._parse_feature_specs()

        assert "F001" in features
        assert "F099" in features
        assert "F200" in features
        assert "F300" in features
        assert len(features) == 4

        print("✅ PASS: Feature ID extraction works for all formats")
        return 0


def test_complexity_extraction_formats():
    """Verify complexity extraction from multiple template formats."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        features_dir = root / "spec/baseline/features"
        features_dir.mkdir(parents=True)

        # Markdown bold format (feature spec template)
        (features_dir / "feat_f001_markdown.md").write_text("- **复杂度**: `low`\n")

        # YAML-like format (slice template)
        (features_dir / "feat_f002_yaml.md").write_text("complexity: simple\n")

        # Inline format
        (features_dir / "feat_f003_inline.md").write_text("parallel_group: 1 | complexity: medium\n")

        linter = PlanCoverageLinter(str(root))
        features = linter._parse_feature_specs()

        assert features["F001"]["complexity"] == "low"
        assert features["F002"]["complexity"] == "simple"
        assert features["F003"]["complexity"] == "medium"

        print("✅ PASS: Complexity extraction works for all template formats")
        return 0


def test_duplicate_feature_ids_rejected():
    """Verify that duplicate feature IDs produce blocking finding."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        features_dir = root / "spec/baseline/features"
        features_dir.mkdir(parents=True)

        # Two files with same feature ID
        (features_dir / "F001_first.md").write_text("- **复杂度**: low\n")
        (features_dir / "feat_f001_duplicate.md").write_text("- **复杂度**: high\n")

        linter = PlanCoverageLinter(str(root))
        features = linter._parse_feature_specs()

        # Should have blocking finding for duplicate
        duplicate_findings = [f for f in linter.findings if f.get("code") == "IOS.AMBIGUOUS_FEATURE_ID"]
        assert len(duplicate_findings) == 1, f"Expected 1 duplicate finding, got {len(duplicate_findings)}"
        assert duplicate_findings[0]["severity"] == "blocking"
        assert "F001" in duplicate_findings[0]["message"]

        print("✅ PASS: Duplicate feature IDs produce blocking finding")
        return 0


def test_slice_fid_from_heading():
    """Verify slice FID extraction from heading when no explicit field."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        slices_dir = root / "spec/baseline/plans/slices"
        slices_dir.mkdir(parents=True)

        # Slice with FID in heading only (native template format)
        slice_file = slices_dir / "slice-01-f001.md"
        slice_file.write_text("""## Slice 1: Bean Management (F001)
parallel_group: 1 | complexity: simple
depends_on: [Base]

Steps:
1. Create BeanStore
""")

        linter = PlanCoverageLinter(str(root))
        slices = linter._parse_slices()

        assert "01" in slices, f"Slice not found: {slices.keys()}"
        assert slices["01"]["feature_id"] == "F001", f"FID not extracted from heading: {slices['01']}"
        assert slices["01"]["complexity"] == "simple"

        print("✅ PASS: Slice FID extracted from heading")
        return 0


if __name__ == "__main__":
    try:
        test_parse_feature_specs_canonical()
        test_feature_id_extraction()
        test_complexity_extraction_formats()
        test_duplicate_feature_ids_rejected()
        test_slice_fid_from_heading()
        print("\n✅ All tests passed")
        sys.exit(0)
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
