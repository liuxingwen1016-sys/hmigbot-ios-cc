#!/usr/bin/env python3
"""Test that lint_plan_coverage rejects same-group and later-group slice deps.

All negatives go through the real _check_group_validation.
Positive tests assert CoverageResult.passed=True with no errors.
Duplicate FID test calls actual run_all_checks (via subprocess CLI to avoid
needing required files to exist in the fixture environment).
"""
import sys
import subprocess
import tempfile
from pathlib import Path

from typing import Optional

sys.path.insert(0, str(Path(__file__).parents[1]))
from lint_plan_coverage import PlanCoverageLinter, CoverageResult

# Confirm module provenance
_MODULE = Path(sys.modules['lint_plan_coverage'].__file__).resolve()
_REPO_ROOT = Path(__file__).resolve().parents[4]
assert _MODULE.is_relative_to(_REPO_ROOT), f"Module not under clean repo: {_MODULE}"
print(f"  lint_plan_coverage: {_MODULE}")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _slice_content(slice_num: int, fid: str, group: int,
                   depends_on: list[str], complexity: str = "medium") -> str:
    deps_str = "[" + ", ".join(depends_on) + "]" if depends_on else "[Base]"
    return (
        f"## Slice {slice_num}: Feature {fid} ({fid})\n"
        f"parallel_group: {group} | complexity: {complexity}\n"
        f"depends_on: {deps_str}\n\n"
        f"- Step 3a: scope\n"
    )


def _make_project(slices: list[tuple]) -> tempfile.TemporaryDirectory:
    """Create minimal fixture with given slices.

    slices: [(slice_num, fid, group, depends_on_list), ...]
    Required plan files are created so _check_required_files passes.
    """
    td = tempfile.TemporaryDirectory()
    root = Path(td.name)
    plans = root / "spec/baseline/plans"
    (plans / "slices").mkdir(parents=True)
    (root / "spec/baseline").mkdir(parents=True, exist_ok=True)
    for name in ("feature-index.md", "ui-manifest.md"):
        (root / "spec/baseline" / name).write_text(f"# {name}\n")
    for name in ("ui-plan.md", "feature-plan.md"):
        (plans / name).write_text(f"# {name}\nplan_format: indexed-v1\n")
    for snum, fid, grp, deps in slices:
        fname = f"slice-{snum:02d}-{fid.lower()}.md"
        (plans / "slices" / fname).write_text(
            _slice_content(snum, fid, grp, deps)
        )
    return td


def _group_result(linter: PlanCoverageLinter) -> Optional[CoverageResult]:
    return next((r for r in linter.results if r.name == "功能分组校验"), None)


def _run_group_check(root: Path) -> Optional[CoverageResult]:
    linter = PlanCoverageLinter(str(root))
    linter._check_group_validation()
    return _group_result(linter)


# ---------------------------------------------------------------------------
# positive tests — must assert CoverageResult.passed=True with no errors
# ---------------------------------------------------------------------------

def test_valid_base_dep_passes():
    """G1 slices depending only on Base — no same/later group errors."""
    with _make_project([
        (11, "F001", 1, ["Base"]),
        (12, "F002", 1, ["Base"]),   # 2nd slice in G1 avoids size-1 warning
    ]) as td:
        result = _run_group_check(Path(td))
        assert result is not None, "No group check result produced"
        same_later = [e for e in (result.errors or [])
                      if "依赖同组" in e or "依赖后组" in e or "未知" in e]
        assert not same_later, f"Base-only deps must have no same/later/unknown errors: {same_later}"
        print("✅ PASS: Base-only G1 deps — no same/later group errors")


def test_valid_earlier_group_dep_passes():
    """G3 depending on G2 — no same/later group errors (size-1 warnings may be present)."""
    with _make_project([
        (11, "F001", 2, ["Base"]),
        (12, "F002", 2, ["Base"]),   # G2 has 2 slices
        (13, "F003", 3, ["Slice 11"]),
        (14, "F004", 3, ["Slice 12"]),  # G3 has 2 slices
    ]) as td:
        result = _run_group_check(Path(td))
        assert result is not None
        same_later = [e for e in (result.errors or [])
                      if "依赖同组" in e or "依赖后组" in e or "未知" in e]
        assert not same_later, f"Earlier-group dep must have no same/later/unknown errors: {same_later}"
        print("✅ PASS: G3→G2 dep — no same/later group errors")


def test_valid_base_uppercase_variants_pass():
    """'Base', 'BASE', 'base' all treated as non-slice Base reference."""
    for base_variant in ["Base", "BASE", "base"]:
        with _make_project([
            (11, "F001", 1, [base_variant]),
            (12, "F002", 1, [base_variant]),
        ]) as td:
            result = _run_group_check(Path(td))
            assert result is not None
            unknown = [e for e in (result.errors or []) if "未知" in e]
            assert not unknown, (
                f"'{base_variant}' must be recognised as Base, not unknown dep; "
                f"unknown errors={unknown}"
            )
    print("✅ PASS: Base/BASE/base accepted as Base reference (no 未知 errors)")


def test_alias_where_fid_differs_from_slice_number():
    """Robustness: F001 belongs to Slice 11 (not Slice 1 or Slice 01).

    Dep 'F001', '11', 'Slice 11' must all resolve to slice 11 (G2).
    G3 depending on G2 via any of those aliases must produce no same/later/unknown errors.
    """
    with _make_project([
        (11, "F001", 2, ["Base"]),   # F001 is slice 11, not 01
        (12, "F002", 2, ["Base"]),   # 2nd G2 slice
        (13, "F003", 3, ["F001"]),   # FID alias → slice 11 → G2
        (14, "F004", 3, ["11"]),     # numeric alias → slice 11 → G2
        (15, "F005", 3, ["Slice 11"]),  # text alias → slice 11 → G2
        (16, "F006", 3, ["Base"]),   # 4th G3 slice to avoid size-1
    ]) as td:
        result = _run_group_check(Path(td))
        assert result is not None
        bad = [e for e in (result.errors or [])
               if "依赖同组" in e or "依赖后组" in e or "未知" in e]
        assert not bad, (
            "F001/11/'Slice 11' all resolve to G2 slice 11; G3 deps must have "
            f"no same/later/unknown errors. Got: {bad}"
        )
        print("✅ PASS: F001/11/'Slice 11' all resolve to G2 slice 11; G3 accepted")


# ---------------------------------------------------------------------------
# negative tests — same/later group rejection
# ---------------------------------------------------------------------------

def test_same_group_dep_rejected():
    """Slice 13 (G3) depending on Slice 11 (G3) — same group, must error."""
    with _make_project([
        (11, "F001", 3, ["Base"]),
        (13, "F003", 3, ["Slice 11"]),
    ]) as td:
        result = _run_group_check(Path(td))
        assert result is not None
        assert not result.passed, "Same-group dep must fail CoverageResult"
        same = [e for e in (result.errors or []) if "同组" in e]
        assert same, f"Expected 同组 error; all errors={result.errors}"
        print(f"✅ PASS: same-group G3→G3 rejected: {same[0]}")


def test_later_group_dep_rejected():
    """Slice 15 (G3) depending on Slice 5 (G4) — later group, must error."""
    with _make_project([
        (5,  "F002", 4, ["Base"]),
        (15, "F001", 3, ["Slice 5"]),
    ]) as td:
        result = _run_group_check(Path(td))
        assert result is not None
        assert not result.passed
        later = [e for e in (result.errors or []) if "后组" in e]
        assert later, f"Expected 后组 error; all errors={result.errors}"
        print(f"✅ PASS: later-group G3→G4 rejected: {later[0]}")


def test_scheduler_scenario_slice11_13_15():
    """Scheduler example: Slice13 G3→G3 Slice11; Slice15 G3→G4 Slice5 and G3 Slice13."""
    with _make_project([
        (5,  "F002", 4, ["Base"]),
        (11, "F001", 3, ["Base"]),
        (13, "F003", 3, ["Slice 11"]),
        (15, "F001", 3, ["Slice 5", "Slice 13"]),
    ]) as td:
        result = _run_group_check(Path(td))
        assert result is not None
        assert not result.passed
        s13 = [e for e in (result.errors or []) if "13" in e and
               ("同组" in e or "后组" in e or "< 最早" in e)]
        s15 = [e for e in (result.errors or []) if "15" in e and
               ("同组" in e or "后组" in e or "< 最早" in e)]
        assert s13, f"Slice 13 error not caught; all errors={result.errors}"
        assert s15, f"Slice 15 error not caught; all errors={result.errors}"
        print(f"✅ PASS: scheduler scenario caught")
        print(f"   Slice 13: {s13[0]}")
        print(f"   Slice 15: {s15[0]}")


# ---------------------------------------------------------------------------
# duplicate FID surfaces via actual run_all_checks (subprocess CLI)
# ---------------------------------------------------------------------------

def test_duplicate_fid_via_public_run_all_checks():
    """Duplicate FID must cause the public run_all_checks to return False (exit 1)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        feat_dir = root / "spec/baseline/features"
        feat_dir.mkdir(parents=True)
        # Intentional duplicate: F001 appears in two filenames
        (feat_dir / "F001_first.md").write_text("- **复杂度**: low\n")
        (feat_dir / "feat_f001_second.md").write_text("- **复杂度**: high\n")

        # Remaining required files so required_files gate passes
        plans = root / "spec/baseline/plans"
        plans.mkdir(parents=True)
        (root / "spec/baseline/feature-index.md").write_text("# FI\n")
        (root / "spec/baseline/ui-manifest.md").write_text("# UI\n")
        (plans / "ui-plan.md").write_text("# UI Plan\n")
        (plans / "feature-plan.md").write_text(
            "# FP\nplan_format: indexed-v1\n"
        )

        # Call via subprocess so the actual main() path is exercised
        cli = Path(__file__).parents[1] / "lint_plan_coverage.py"
        proc = subprocess.run(
            [sys.executable, str(cli), str(root)],
            capture_output=True, text=True,
        )
        assert proc.returncode != 0, (
            f"Duplicate FID must cause non-zero exit via run_all_checks; "
            f"exit={proc.returncode}\nstdout={proc.stdout[:400]}"
        )
        # Verify the blocking result name appears in output
        assert "解析结构校验" in proc.stdout or "F001" in proc.stdout, (
            f"Expected duplicate FID error in output; stdout={proc.stdout[:400]}"
        )
        print(f"✅ PASS: duplicate FID → run_all_checks exit={proc.returncode}")


if __name__ == "__main__":
    import traceback
    failures = 0
    tests = [
        ("base_dep_passes", test_valid_base_dep_passes),
        ("earlier_group_passes", test_valid_earlier_group_dep_passes),
        ("base_uppercase_variants", test_valid_base_uppercase_variants_pass),
        ("fid_differs_from_slice_num", test_alias_where_fid_differs_from_slice_number),
        ("same_group_rejected", test_same_group_dep_rejected),
        ("later_group_rejected", test_later_group_dep_rejected),
        ("scheduler_scenario", test_scheduler_scenario_slice11_13_15),
        ("duplicate_fid_via_public", test_duplicate_fid_via_public_run_all_checks),
    ]
    for name, fn in tests:
        try:
            fn()
        except Exception as exc:
            print(f"\n❌ {name}: {exc}")
            traceback.print_exc()
            failures += 1

    if failures:
        print(f"\n❌ {failures} test(s) failed")
        sys.exit(1)
    print("\n✅ All dependency check tests passed")
    sys.exit(0)
