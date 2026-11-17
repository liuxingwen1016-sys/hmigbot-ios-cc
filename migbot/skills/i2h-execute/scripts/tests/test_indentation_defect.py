"""Test for unreachable SHA comparison indentation defect."""
from __future__ import annotations

import json
import hashlib
from pathlib import Path
import pytest
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.ios_stage1_scope import load_inventory


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_index_sha_mismatch_after_inventory_modified_must_reject(tmp_path):
    """INDENTATION DEFECT: Valid canonical approved + native index with bound SHA.

    Modify ONLY inventory raw bytes (append valid JSON whitespace) leaving index with old SHA.
    Current code wrongly passes because actual_sha computation is unreachable under raise.
    Test must FAIL before fix, PASS after indentation fix.
    """
    root = tmp_path / "project"

    # Create valid canonical baseline
    baseline_path = root / "spec" / "baseline" / "ui-delivery-approved.json"
    baseline_path.parent.mkdir(parents=True)
    baseline = {"schema_version": 2, "status": "approved", "units": []}
    baseline_text = json.dumps(baseline, ensure_ascii=False)
    baseline_path.write_text(baseline_text, encoding="utf-8")
    baseline_sha = sha256_file(baseline_path)

    # Create native index binding this SHA
    index_path = root / "spec" / "execution" / "ui-inputs" / "index.json"
    index_path.parent.mkdir(parents=True)
    index = {
        "schema_version": 2,
        "inventory_source": {
            "path": "spec/baseline/ui-delivery-approved.json",
            "sha256": baseline_sha
        }
    }
    index_path.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")

    # Verify load works with correct SHA
    path1, data1 = load_inventory(root, None)
    assert path1 == baseline_path
    assert data1 == baseline

    # Now modify ONLY inventory raw bytes (append valid JSON whitespace)
    # This changes SHA but leaves index with old SHA
    modified_text = baseline_text + "\n\n"  # Valid JSON, different bytes
    baseline_path.write_text(modified_text, encoding="utf-8")
    new_sha = sha256_file(baseline_path)
    assert new_sha != baseline_sha, "SHA must change after modification"

    # Load must reject SHA mismatch (currently WRONGLY PASSES due to unreachable code)
    with pytest.raises(ValueError, match="inventory SHA mismatch"):
        load_inventory(root, None)


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            test_index_sha_mismatch_after_inventory_modified_must_reject(Path(tmpdir))
            print("TEST PASSED - defect is fixed")
        except AssertionError as e:
            if "DID NOT RAISE" in str(e):
                print("TEST FAILED - defect present (unreachable SHA comparison)")
            else:
                raise
