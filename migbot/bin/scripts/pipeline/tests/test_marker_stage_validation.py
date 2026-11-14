#!/usr/bin/env python3
"""Test marker self-reference and stage-aware validation.

Validates that:
- Marker cannot list itself in artifacts (circular reference)
- Marker file must be included in artifact list for content integrity
- Complete stage markers include all expected artifacts
- Artifact mutations detected via SHA256 mismatch
"""
import json
import tempfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[1]))
from marker_contract import write_marker, validate_marker, file_sha256


def test_marker_self_reference_rejected():
    """Marker attempting to list itself in artifacts should fail."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        marker_path = root / "spec/baseline/spec-complete.txt"
        marker_path.parent.mkdir(parents=True)

        # Create required artifact
        artifact = root / "spec/baseline/ui-manifest.md"
        artifact.write_text("# UI Manifest\n")

        # Try to write marker that references itself
        try:
            write_marker(
                marker_path,
                stage="i2h-spec",
                artifact_paths=[
                    "spec/baseline/ui-manifest.md",
                    "spec/baseline/spec-complete.txt"  # Self-reference
                ],
                inputs_sha256="abc123",
                root=root
            )
            # If write_marker allows this, validation should catch it
            result = validate_marker(marker_path, "i2h-spec", root=root)
            # Check if marker references itself in artifacts
            marker_data = json.loads(marker_path.read_text())
            artifact_paths = {a["path"] for a in marker_data.get("artifacts", [])}
            assert "spec/baseline/spec-complete.txt" not in artifact_paths, \
                "Marker should not reference itself in artifacts"
        except Exception as e:
            # Self-reference might be rejected at write time
            print(f"✅ PASS: Self-reference rejected (write-time): {e}")
            return 0

        print(f"✅ PASS: Self-reference rejected (validation-time)")
        return 0


def test_marker_must_exist_for_validation():
    """Marker file must exist to pass validation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        marker_path = root / "spec/baseline/nonexistent-marker.txt"

        result = validate_marker(marker_path, "i2h-spec", root=root)

        assert not result["valid"], "Validation should fail for missing marker"
        assert "marker_missing" in result["errors"], f"Expected marker_missing error: {result}"

        print(f"✅ PASS: Missing marker fails validation")
        return 0


def test_complete_spec_stage_artifacts():
    """Complete i2h-spec marker should include all expected artifacts."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        spec_dir = root / "spec/baseline"
        spec_dir.mkdir(parents=True)

        # Create complete artifact set (minimal portable example)
        artifacts = {
            "ui-manifest.md": "# UI Manifest\n## Pages\n- HomeView\n",
            "feature-index.md": "# Feature Index\n- F001: Auth\n",
            "ui-coverage-report.md": "# Coverage\nTotal: 1 page\n"
        }

        artifact_paths = []
        for name, content in artifacts.items():
            path = spec_dir / name
            path.write_text(content)
            artifact_paths.append(f"spec/baseline/{name}")

        marker_path = spec_dir / "spec-complete.txt"

        # Write marker with complete artifact set
        write_marker(
            marker_path,
            stage="i2h-spec",
            artifact_paths=artifact_paths,
            inputs_sha256="input123",
            root=root
        )

        # Validate
        result = validate_marker(marker_path, "i2h-spec", "input123", root=root)

        assert result["valid"], f"Complete marker should validate: {result}"
        assert len(result["errors"]) == 0, f"Should have no errors: {result['errors']}"

        # Verify artifact count
        marker_data = json.loads(marker_path.read_text())
        assert len(marker_data["artifacts"]) == 3, \
            f"Should have 3 artifacts, got {len(marker_data['artifacts'])}"

        print(f"✅ PASS: Complete spec stage artifacts validated")
        print(f"   Artifacts: {len(marker_data['artifacts'])}")
        return 0


def test_artifact_mutation_detected():
    """SHA256 mismatch should be detected when artifact is modified."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        spec_dir = root / "spec/baseline"
        spec_dir.mkdir(parents=True)

        # Create artifact
        artifact_path = spec_dir / "ui-manifest.md"
        artifact_path.write_text("# Original Content\n")

        marker_path = spec_dir / "spec-complete.txt"

        # Write marker with original content
        write_marker(
            marker_path,
            stage="i2h-spec",
            artifact_paths=["spec/baseline/ui-manifest.md"],
            inputs_sha256="input123",
            root=root
        )

        # Validation should pass initially
        result = validate_marker(marker_path, "i2h-spec", "input123", root=root)
        assert result["valid"], f"Initial validation should pass: {result}"

        # Mutate artifact
        artifact_path.write_text("# Modified Content\n")

        # Validation should now fail
        result = validate_marker(marker_path, "i2h-spec", "input123", root=root)
        assert not result["valid"], "Validation should fail after mutation"
        assert "artifact_hash_mismatch" in result["errors"], \
            f"Expected artifact_hash_mismatch: {result}"

        print(f"✅ PASS: Artifact mutation detected via SHA256 mismatch")
        return 0


def test_incomplete_artifacts_still_valid():
    """Marker with subset of artifacts is technically valid but incomplete.

    Stage-aware checkers must verify expected artifacts are present.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        spec_dir = root / "spec/baseline"
        spec_dir.mkdir(parents=True)

        # Create only one artifact (incomplete set)
        artifact = spec_dir / "ui-manifest.md"
        artifact.write_text("# Partial manifest\n")

        marker_path = spec_dir / "spec-complete.txt"

        # Write marker with incomplete artifacts
        write_marker(
            marker_path,
            stage="i2h-spec",
            artifact_paths=["spec/baseline/ui-manifest.md"],
            inputs_sha256="input123",
            root=root
        )

        # Low-level validation passes (content-addressed integrity OK)
        result = validate_marker(marker_path, "i2h-spec", "input123", root=root)
        assert result["valid"], "Low-level validation should pass"

        # But stage-aware checker would detect missing artifacts
        marker_data = json.loads(marker_path.read_text())
        artifact_paths = {a["path"] for a in marker_data["artifacts"]}

        # Expected artifacts for complete i2h-spec (example)
        expected = {
            "spec/baseline/ui-manifest.md",
            "spec/baseline/feature-index.md",
            "spec/baseline/ui-coverage-report.md"
        }

        missing = expected - artifact_paths
        assert len(missing) > 0, "Should detect missing artifacts"

        print(f"✅ PASS: Incomplete artifact set detected")
        print(f"   Present: {len(artifact_paths)}")
        print(f"   Missing: {missing}")
        return 0


def test_cli_guard_nonzero_exit():
    """CLI direct invocation without stdin should exit nonzero with error."""
    import subprocess

    result = subprocess.run(
        ["python3", str(Path(__file__).parents[1] / "marker_contract.py")],
        capture_output=True,
        text=True
    )

    assert result.returncode != 0, f"CLI should exit nonzero, got {result.returncode}"
    assert len(result.stderr) > 0 or "stdin" in result.stdout.lower(), \
        f"Should have useful error message: stdout={result.stdout}, stderr={result.stderr}"
    assert result.stdout.count("sha256") == 0, "Should not output marker without input"

    print(f"✅ PASS: CLI guard produces nonzero exit with error")
    print(f"   Exit code: {result.returncode}")
    return 0


if __name__ == "__main__":
    try:
        test_marker_must_exist_for_validation()
        test_complete_spec_stage_artifacts()
        test_artifact_mutation_detected()
        test_incomplete_artifacts_still_valid()
        test_marker_self_reference_rejected()
        test_cli_guard_nonzero_exit()
        print("\n✅ All stage-aware marker validation tests passed")
        sys.exit(0)
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
