#!/usr/bin/env python3
"""Marker validation tests: stage-aware artifact checks.

Tests:
- Self-reference: marker cannot list itself in artifacts (write_marker rejects it)
- Missing marker fails validate_marker
- Byte-sealed artifact integrity detected via SHA256
- Incomplete-but-sealed marker: low-level PASS, stage-aware detector catches gap
- CLI guard: direct invocation exits nonzero with useful stderr
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

# Portable provenance: pipeline scripts are siblings of this tests/ dir's parent
_PIPELINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PIPELINE))
from marker_contract import write_marker, validate_marker


def test_marker_self_reference_rejected():
    """write_marker must reject the marker path when it appears in artifact_paths."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        marker_path = root / "spec/baseline/spec-complete.txt"
        marker_path.parent.mkdir(parents=True)

        (root / "spec/baseline/ui-manifest.md").write_text("# UI Manifest\n")

        # Attempt to include the marker itself as an artifact.
        # write_marker resolves every path; spec-complete.txt does not yet exist
        # (it's the output), so it raises FileNotFoundError — specific rejection.
        raised = None
        try:
            write_marker(
                marker_path,
                stage="i2h-spec",
                artifact_paths=[
                    "spec/baseline/ui-manifest.md",
                    "spec/baseline/spec-complete.txt",   # self-reference
                ],
                inputs_sha256="abc123",
                root=root,
            )
        except FileNotFoundError as e:
            raised = e

        assert raised is not None, (
            "write_marker must raise FileNotFoundError when artifact path "
            "does not exist (self-reference is impossible to satisfy before write)"
        )
        assert "spec-complete.txt" in str(raised), f"Error should name the offending path: {raised}"
        # Marker must not have been created
        assert not marker_path.exists(), "Marker file must not be created on self-reference"
        print(f"✅ PASS: self-reference raises FileNotFoundError, no marker written")


def test_marker_must_exist_for_validation():
    """validate_marker returns marker_missing for a path that does not exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        result = validate_marker(root / "spec/baseline/nonexistent.txt", "i2h-spec", root=root)
        assert not result["valid"], "Validation must fail when marker absent"
        assert "marker_missing" in result["errors"], f"Expected marker_missing: {result}"
        print("✅ PASS: absent marker → marker_missing")


def test_artifact_mutation_detected():
    """validate_marker returns artifact_hash_mismatch after artifact content changes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        spec_dir = root / "spec/baseline"
        spec_dir.mkdir(parents=True)
        artifact = spec_dir / "ui-manifest.md"
        artifact.write_text("# Original\n")
        marker_path = spec_dir / "spec-complete.txt"

        write_marker(marker_path, stage="i2h-spec",
                     artifact_paths=["spec/baseline/ui-manifest.md"],
                     inputs_sha256="h1", root=root)

        assert validate_marker(marker_path, "i2h-spec", "h1", root=root)["valid"]

        artifact.write_text("# Modified\n")
        result = validate_marker(marker_path, "i2h-spec", "h1", root=root)
        assert not result["valid"], "Validation must fail after mutation"
        assert "artifact_hash_mismatch" in result["errors"], f"Expected hash mismatch: {result}"
        print("✅ PASS: artifact mutation detected via SHA256 mismatch")


def test_low_level_sealed_incomplete_marker_detected_by_pipeline_resume():
    """A byte-sealed marker with only 1 artifact must be detected as incomplete
    by the stage-aware pipeline_resume._validate_marker_artifacts check.

    Low-level validate_marker passes (content-addressed integrity is fine).
    Stage-aware check fails because required spec evidence is absent.
    """
    _PLAN_SCRIPTS = Path(__file__).resolve().parents[5] / "migbot/skills/i2h-plan/scripts"
    sys.path.insert(0, str(_PLAN_SCRIPTS))
    from pipeline_resume import _validate_marker_artifacts

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir).resolve()  # resolve /var→/private/var on macOS
        spec_dir = root / "spec/baseline"
        spec_dir.mkdir(parents=True)
        # Create only one artifact — missing resources-inventory.json
        artifact = spec_dir / "ui-manifest.md"
        artifact.write_text("# Partial\n")
        marker_path = root / "spec/baseline/spec-complete.txt"

        write_marker(marker_path, stage="i2h-spec",
                     artifact_paths=["spec/baseline/ui-manifest.md"],
                     inputs_sha256="h1", root=root)

        # Low-level validation passes
        low_result = validate_marker(marker_path, "i2h-spec", "h1", root=root)
        assert low_result["valid"], "Low-level must pass for content-intact sealed marker"

        # Stage-aware gate rejects it: required spec evidence absent
        from marker_contract import resolve_stage
        stage_res = resolve_stage(root, "i2h-spec")
        marker_dict = {"paths": [str(p.relative_to(root)) for p in stage_res.paths]}
        stage_errors = _validate_marker_artifacts(root, "i2h-spec", marker_dict)
        assert stage_errors, (
            "Stage-aware check must reject sealed marker missing required "
            "spec/.i2h/resources-inventory.json (or target-input.json). "
            f"Got no errors; marker artifacts: "
            f"{[a['path'] for a in json.loads(marker_path.read_text()).get('artifacts', [])]}"
        )
        assert any("spec_evidence" in e for e in stage_errors), \
            f"Expected spec evidence error; got: {stage_errors}"
        print(f"✅ PASS: sealed incomplete marker rejected by stage-aware check: {stage_errors}")


def test_cli_guard_nonzero_exit_no_marker_output():
    """Running marker_contract.py directly must exit nonzero with useful stderr."""
    result = subprocess.run(
        ["python3", str(_PIPELINE / "marker_contract.py")],
        capture_output=True, text=True,
    )
    assert result.returncode != 0, (
        f"CLI direct invocation must exit nonzero; got {result.returncode}"
    )
    assert result.stderr.strip(), (
        f"stderr must contain usage explanation; got empty. stdout={result.stdout!r}"
    )
    # Must not silently create or print a marker JSON blob
    assert '"schema_version"' not in result.stdout, \
        "Must not output a marker JSON when invoked as CLI"
    print(f"✅ PASS: CLI guard exit={result.returncode}, stderr present, no marker output")


if __name__ == "__main__":
    failures = 0
    for name, fn in [
        ("self_reference_rejected", test_marker_self_reference_rejected),
        ("marker_must_exist", test_marker_must_exist_for_validation),
        ("mutation_detected", test_artifact_mutation_detected),
        ("sealed_incomplete_stage_rejected",
         test_low_level_sealed_incomplete_marker_detected_by_pipeline_resume),
        ("cli_guard", test_cli_guard_nonzero_exit_no_marker_output),
    ]:
        try:
            fn()
        except Exception as exc:
            import traceback
            print(f"\n❌ {name}: {exc}")
            traceback.print_exc()
            failures += 1

    if failures:
        print(f"\n❌ {failures} test(s) failed")
        sys.exit(1)
    print("\n✅ All marker stage validation tests passed")
    sys.exit(0)
