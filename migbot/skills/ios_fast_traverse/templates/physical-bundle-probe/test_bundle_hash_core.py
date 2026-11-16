#!/usr/bin/env python3
"""
Portable regression driver for I2HBundleHashCore validation.
Calls UNMODIFIED native ios_evidence_protocol.py from canonical repo.

Tests all 9 required fixture cases:
- Empty bundle
- Single empty file
- Binary bytes (NUL, 0xff)
- Nested directory structure
- ASCII case ordering (distinct case-fold names)
- Unicode BMP (U+E000) and non-BMP (U+1F600)
- File and directory symlinks (excluded)
- EXCLUDED_PARTS (.git, build, DerivedData)
- iOS bundle simulation (_CodeSignature, embedded.mobileprovision)
"""
import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
from pathlib import Path

def skip_non_darwin():
    """Skip test on non-Darwin platforms."""
    if platform.system() != "Darwin":
        print(f"SKIP: Test requires Darwin/macOS (current: {platform.system()})")
        sys.exit(0)

def find_expected_module(script_dir: Path) -> tuple[Path, object]:
    """
    Locate and import ios_evidence_protocol.py from canonical repo.
    Returns (module_path, module_object).
    """
    # Navigate from migbot/skills/ios_fast_traverse/templates/physical-bundle-probe/ to repo root
    # Go up 5 levels: physical-bundle-probe -> templates -> ios_fast_traverse -> skills -> migbot -> repo_root
    repo_root = script_dir.parent.parent.parent.parent.parent
    expected_path = repo_root / "migbot/skills/i2h-spec/scripts/ios_evidence_protocol.py"

    if not expected_path.exists():
        raise FileNotFoundError(
            f"Cannot locate ios_evidence_protocol.py at: {expected_path}\n"
            f"Script dir: {script_dir}\n"
            f"Repo root: {repo_root}"
        )

    # Import module
    import importlib.util
    spec = importlib.util.spec_from_file_location("ios_evidence_protocol", expected_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    return expected_path.resolve(), module

def build_cli(template_dir: Path, output_dir: Path) -> Path:
    """Build macOS CLI harness. Always compile current REAL core+CLI."""
    cli_binary = output_dir / "i2h_bundle_hash_cli"

    core_m = template_dir / "I2HBundleHashCore.m"
    cli_m = template_dir / "i2h_bundle_hash_cli.m"

    if not core_m.exists() or not cli_m.exists():
        raise FileNotFoundError(f"Source files not found: {core_m}, {cli_m}")

    cmd = [
        "xcrun", "clang",
        "-fobjc-arc", "-fmodules",
        "-framework", "Foundation",
        "-o", str(cli_binary),
        str(core_m), str(cli_m)
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Build failed:\nstdout: {result.stdout}\nstderr: {result.stderr}")

    return cli_binary

def create_test_fixtures(fixtures_dir: Path) -> dict:
    """Create all required test fixtures plus optional FIFO test."""
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    fixtures = {}

    # Fixture 1: Empty bundle
    empty = fixtures_dir / "empty_bundle"
    empty.mkdir(exist_ok=True)
    fixtures["empty_bundle"] = {
        "path": str(empty),
        "description": "Empty directory with no files",
    }

    # Fixture 2: Single empty file
    single_empty = fixtures_dir / "single_empty_file"
    single_empty.mkdir(exist_ok=True)
    (single_empty / "empty.txt").write_bytes(b"")
    fixtures["single_empty_file"] = {
        "path": str(single_empty),
        "description": "Single empty file (0 bytes)",
    }

    # Fixture 3: Binary bytes including NUL and 0xff
    binary_bundle = fixtures_dir / "binary_bytes"
    binary_bundle.mkdir(exist_ok=True)
    (binary_bundle / "binary.dat").write_bytes(b"\x00\x01\x02\xff\xfe\xfd")
    (binary_bundle / "nul_only.dat").write_bytes(b"\x00\x00\x00")
    fixtures["binary_bytes"] = {
        "path": str(binary_bundle),
        "description": "Binary files with NUL and 0xff bytes",
    }

    # Fixture 4: Nested directory structure
    nested_bundle = fixtures_dir / "nested_paths"
    nested_bundle.mkdir(exist_ok=True)
    (nested_bundle / "a").mkdir(exist_ok=True)
    (nested_bundle / "a" / "b").mkdir(exist_ok=True)
    (nested_bundle / "a" / "b" / "c").mkdir(exist_ok=True)
    (nested_bundle / "a" / "file1.txt").write_text("level1")
    (nested_bundle / "a" / "b" / "file2.txt").write_text("level2")
    (nested_bundle / "a" / "b" / "c" / "file3.txt").write_text("level3")
    fixtures["nested_paths"] = {
        "path": str(nested_bundle),
        "description": "Deeply nested directory structure",
    }

    # Fixture 5: ASCII case ordering (distinct case-fold names for APFS)
    ascii_case = fixtures_dir / "ascii_case_ordering"
    ascii_case.mkdir(exist_ok=True)
    (ascii_case / "Z_upper.txt").write_text("uppercase Z")
    (ascii_case / "a_lower.txt").write_text("lowercase a")
    (ascii_case / "B_mix.txt").write_text("uppercase B")
    (ascii_case / "c_mix.txt").write_text("lowercase c")
    fixtures["ascii_case_ordering"] = {
        "path": str(ascii_case),
        "description": "ASCII case ordering with distinct names",
    }

    # Fixture 6: Unicode BMP (U+E000) and non-BMP (U+1F600), NFD vs NFC
    unicode_bundle = fixtures_dir / "unicode_ordering"
    unicode_bundle.mkdir(exist_ok=True)
    (unicode_bundle / "file_A.txt").write_text("ASCII A")
    (unicode_bundle / "file_Á.txt").write_text("A with acute NFC")
    (unicode_bundle / "file_é.txt").write_text("e-acute NFC")
    (unicode_bundle / "file_.txt").write_text("private use BMP U+E000")
    (unicode_bundle / "file_\U0001f600.txt").write_text("emoji non-BMP U+1F600")

    # Add actual NFD vs NFC variants using escaped codepoints
    # NFC: precomposed é (U+00E9)
    (unicode_bundle / "nfc_\u00e9.txt").write_text("NFC precomposed")
    # NFD: decomposed e + combining acute (U+0065 U+0301) - use escape sequence
    (unicode_bundle / "nfd_e\u0301.txt").write_text("NFD decomposed")

    # Add nested NFD directory with both NFC and NFD children (distinct prefixes)
    # Directory name uses NFD: e + combining acute (U+0065 U+0301)
    nfd_dir = unicode_bundle / "dir_e\u0301"
    nfd_dir.mkdir(exist_ok=True)
    # Child with NFC filename
    (nfd_dir / "nfc_\u00e9.txt").write_text("NFC child in NFD dir")
    # Child with NFD filename using escaped codepoint (distinct prefix to avoid collision)
    (nfd_dir / "nfd_e\u0301.txt").write_text("NFD child in NFD dir")

    fixtures["unicode_ordering"] = {
        "path": str(unicode_bundle),
        "description": "Unicode BMP (U+E000) and non-BMP (U+1F600) ordering, NFD vs NFC preservation",
    }


    # Fixture 7: File and directory symlinks (should be excluded)
    symlink_bundle = fixtures_dir / "symlinks"
    symlink_bundle.mkdir(exist_ok=True)
    (symlink_bundle / "real_file.txt").write_text("real content")
    (symlink_bundle / "real_dir").mkdir(exist_ok=True)
    (symlink_bundle / "real_dir" / "nested.txt").write_text("nested real")

    # Create symlinks
    file_symlink = symlink_bundle / "file_symlink.txt"
    dir_symlink = symlink_bundle / "dir_symlink"
    if not file_symlink.exists():
        file_symlink.symlink_to("real_file.txt")
    if not dir_symlink.exists():
        dir_symlink.symlink_to("real_dir")
    fixtures["symlinks"] = {
        "path": str(symlink_bundle),
        "description": "File and directory symlinks (excluded)",
    }

    # Fixture 8: EXCLUDED_PARTS (.git, build, DerivedData)
    excluded_bundle = fixtures_dir / "excluded_parts"
    excluded_bundle.mkdir(exist_ok=True)
    (excluded_bundle / "included.txt").write_text("included")
    (excluded_bundle / ".git").mkdir(exist_ok=True)
    (excluded_bundle / ".git" / "config").write_text("git config")
    (excluded_bundle / "build").mkdir(exist_ok=True)
    (excluded_bundle / "build" / "output.o").write_text("build output")
    (excluded_bundle / "DerivedData").mkdir(exist_ok=True)
    (excluded_bundle / "DerivedData" / "cache").write_text("cache")
    fixtures["excluded_parts"] = {
        "path": str(excluded_bundle),
        "description": "EXCLUDED_PARTS (.git, build, DerivedData)",
    }

    # Fixture 9: iOS bundle simulation with _CodeSignature and embedded.mobileprovision
    ios_sim = fixtures_dir / "ios_bundle_sim"
    ios_sim.mkdir(exist_ok=True)
    (ios_sim / "Info.plist").write_text("<?xml version=\"1.0\"?><plist></plist>")
    (ios_sim / "_CodeSignature").mkdir(exist_ok=True)
    (ios_sim / "_CodeSignature" / "CodeResources").write_text("<?xml version=\"1.0\"?><plist></plist>")
    (ios_sim / "embedded.mobileprovision").write_bytes(b"\x00PROVISION\x00")
    (ios_sim / "Assets.car").write_bytes(b"ASSETCAR")
    fixtures["ios_bundle_sim"] = {
        "path": str(ios_sim),
        "description": "iOS bundle with _CodeSignature and embedded.mobileprovision",
    }

    # Fixture 10 (optional): FIFO (named pipe) - should be skipped like Python path.is_file()
    fifo_bundle = fixtures_dir / "fifo_skip"
    fifo_bundle.mkdir(exist_ok=True)
    (fifo_bundle / "regular.txt").write_text("regular file")
    fifo_path = fifo_bundle / "named_pipe"
    try:
        import os
        os.mkfifo(str(fifo_path))
        fixtures["fifo_skip"] = {
            "path": str(fifo_bundle),
            "description": "FIFO named pipe (should be skipped like symlink)",
        }
    except (OSError, AttributeError):
        # mkfifo not available or failed, skip this fixture
        pass

    # Fixture 11: Bundle root is a symlink to real directory
    # Tests that both /var and /private/var (or other aliases) produce same hash
    real_alias_bundle = fixtures_dir / "real_alias_bundle"
    real_alias_bundle.mkdir(exist_ok=True)
    (real_alias_bundle / "data.txt").write_text("content")
    (real_alias_bundle / "nested").mkdir(exist_ok=True)
    (real_alias_bundle / "nested" / "file.txt").write_text("nested")

    # Create symlink to this bundle
    alias_symlink = fixtures_dir / "alias_symlink"
    try:
        alias_symlink.symlink_to(real_alias_bundle)
        fixtures["root_alias"] = {
            "path": str(alias_symlink),
            "description": "Bundle root via symlink (tests /var vs /private/var alias handling)",
            "canonical_path": str(real_alias_bundle),
        }
    except (OSError, AttributeError):
        # symlink creation failed, skip
        pass

    return fixtures

def run_validation(expected_module_path: Path, expected_module: object, cli_binary: Path, fixtures: dict) -> dict:
    """Run validation comparing CLI output against Python expected module."""
    # Compute expected module SHA256
    expected_module_sha256 = hashlib.sha256(expected_module_path.read_bytes()).hexdigest()

    results = {
        "expected_module": {
            "path": str(expected_module_path),
            "file": expected_module.__file__,
            "sha256": expected_module_sha256,
        },
        "cli_binary": {
            "path": str(cli_binary),
        },
        "fixtures": {},
    }

    for name, fixture_info in fixtures.items():
        fixture_path = Path(fixture_info["path"])

        # List actual fixture tree
        tree = []
        if fixture_path.is_dir():
            for item in sorted(fixture_path.rglob("*")):
                if item.is_file() and not item.is_symlink():
                    tree.append(str(item.relative_to(fixture_path)))
                elif item.is_symlink():
                    tree.append(f"{item.relative_to(fixture_path)} -> {item.readlink()} (symlink)")

        # Compute expected hash using UNMODIFIED Python module
        try:
            expected_hash = expected_module.source_identity(fixture_path)
            expected_error = None
        except Exception as exc:
            expected_hash = None
            expected_error = str(exc)

        # Compute actual hash using macOS CLI harness
        try:
            proc = subprocess.run(
                [str(cli_binary), str(fixture_path)],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if proc.returncode == 0:
                actual_hash = proc.stdout.strip()
                actual_error = None
            else:
                actual_hash = None
                actual_error = proc.stderr.strip()
        except Exception as exc:
            actual_hash = None
            actual_error = str(exc)

        # Compare
        match = (expected_hash == actual_hash) if (expected_hash and actual_hash) else False

        results["fixtures"][name] = {
            "description": fixture_info["description"],
            "path": str(fixture_path),
            "tree": tree,
            "expected_hash": expected_hash,
            "actual_hash": actual_hash,
            "match": match,
        }

        if expected_error:
            results["fixtures"][name]["expected_error"] = expected_error
        if actual_error:
            results["fixtures"][name]["actual_error"] = actual_error

    return results

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='Portable regression driver for I2HBundleHashCore validation.',
        epilog='Tests 10 fixture cases against unmodified ios_evidence_protocol.py'
    )
    parser.add_argument(
        '--output-dir',
        type=str,
        help='Output directory for test artifacts and results (default: temporary directory)'
    )

    args = parser.parse_args()

    skip_non_darwin()

    script_dir = Path(__file__).parent.resolve()

    # Find and import expected module
    try:
        expected_module_path, expected_module = find_expected_module(script_dir)
        print(f"Expected module: {expected_module_path}")
        print(f"Module __file__: {expected_module.__file__}")
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}")
        return 1

    # Use specified output directory, env var, or temp directory
    if args.output_dir:
        output_dir = Path(args.output_dir).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        use_temp = False
        print(f"Using output directory: {output_dir}")
    elif os.environ.get("TEST_OUTPUT_DIR"):
        output_dir = Path(os.environ["TEST_OUTPUT_DIR"]).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        use_temp = False
        print(f"Using output directory: {output_dir}")
    else:
        output_dir = Path(tempfile.mkdtemp(prefix="i2h_bundle_hash_test_"))
        use_temp = True
        print(f"Using temporary directory: {output_dir}")

    # Build CLI (always compile current source)
    print("Building macOS CLI harness from current source...")
    cli_binary = build_cli(script_dir, output_dir)
    print(f"Built: {cli_binary}")

    # Create fixtures
    fixtures_dir = output_dir / "fixtures"
    fixtures = create_test_fixtures(fixtures_dir)
    print(f"Created {len(fixtures)} test fixtures")

    # Run validation
    print("\nRunning validation against native Python expected module...")
    results = run_validation(expected_module_path, expected_module, cli_binary, fixtures)

    # Write results
    results_file = output_dir / "validation_results.json"
    results_file.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"Results written to: {results_file}")

    # Summary
    total = len(results["fixtures"])
    matched = sum(1 for r in results["fixtures"].values() if r["match"])
    print(f"\n=== RESULTS ===")
    print(f"Total: {total}")
    print(f"Matched: {matched}")
    print(f"Failed: {total - matched}")

    if matched < total:
        print("\nFailed fixtures:")
        for name, result in results["fixtures"].items():
            if not result["match"]:
                print(f"  {name}:")
                print(f"    Expected: {result.get('expected_hash')}")
                print(f"    Actual:   {result.get('actual_hash')}")
                if result.get("expected_error"):
                    print(f"    Expected error: {result['expected_error']}")
                if result.get("actual_error"):
                    print(f"    Actual error: {result['actual_error']}")

    # Cleanup temp directory if used
    if use_temp:
        import shutil
        shutil.rmtree(output_dir, ignore_errors=True)

    return 0 if matched == total else 1

if __name__ == "__main__":
    sys.exit(main())
