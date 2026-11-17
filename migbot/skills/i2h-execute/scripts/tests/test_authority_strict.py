"""Strict authority validation tests for production bugfix.

Test that inventory_path and load_inventory enforce strict validation:
1. inventory_path: if index exists, malformed/missing fields must ValueError (no fallback)
2. load_inventory: non-canonical approved files must have full ancestry/proof/replay validation
3. Freezer must use load_inventory shared API and reject invalid inventories before creating index
"""
from __future__ import annotations

import json
import hashlib
from pathlib import Path
import pytest
import sys

# Add lib to path - same pattern as other tests
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.ios_stage1_scope import inventory_path, load_inventory
from lib.ui_delivery_inputs_ios import freeze


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TestInventoryPathStrictValidation:
    """Test inventory_path rejects malformed index when it exists."""

    def test_index_exists_but_not_dict_must_valueerror(self, tmp_path):
        """Index file exists but is not a dict - must ValueError."""
        root = tmp_path / "project"
        index_path = root / "spec" / "execution" / "ui-inputs" / "index.json"
        index_path.parent.mkdir(parents=True)
        index_path.write_text("[]", encoding="utf-8")  # Array, not dict

        # Create canonical baseline as fallback
        baseline_path = root / "spec" / "baseline" / "ui-delivery-approved.json"
        baseline_path.parent.mkdir(parents=True)
        baseline_path.write_text(json.dumps({"schema_version": 2, "status": "approved"}), encoding="utf-8")

        # Must raise ValueError, not fall back to baseline
        with pytest.raises(ValueError, match="malformed index"):
            inventory_path(root, None)

    def test_index_exists_missing_schema_version_must_valueerror(self, tmp_path):
        """Index exists but missing schema_version - must ValueError."""
        root = tmp_path / "project"
        index_path = root / "spec" / "execution" / "ui-inputs" / "index.json"
        index_path.parent.mkdir(parents=True)
        index_path.write_text(json.dumps({"inventory_source": {}}), encoding="utf-8")

        baseline_path = root / "spec" / "baseline" / "ui-delivery-approved.json"
        baseline_path.parent.mkdir(parents=True)
        baseline_path.write_text(json.dumps({"schema_version": 2, "status": "approved"}), encoding="utf-8")

        with pytest.raises(ValueError, match="malformed index"):
            inventory_path(root, None)

    def test_index_exists_wrong_schema_version_must_valueerror(self, tmp_path):
        """Index exists with wrong schema_version - must ValueError."""
        root = tmp_path / "project"
        index_path = root / "spec" / "execution" / "ui-inputs" / "index.json"
        index_path.parent.mkdir(parents=True)
        index_path.write_text(json.dumps({"schema_version": 1}), encoding="utf-8")

        baseline_path = root / "spec" / "baseline" / "ui-delivery-approved.json"
        baseline_path.parent.mkdir(parents=True)
        baseline_path.write_text(json.dumps({"schema_version": 2, "status": "approved"}), encoding="utf-8")

        with pytest.raises(ValueError, match="malformed index"):
            inventory_path(root, None)

    def test_index_exists_missing_inventory_source_must_valueerror(self, tmp_path):
        """Index exists but missing inventory_source - must ValueError."""
        root = tmp_path / "project"
        index_path = root / "spec" / "execution" / "ui-inputs" / "index.json"
        index_path.parent.mkdir(parents=True)
        index_path.write_text(json.dumps({"schema_version": 2}), encoding="utf-8")

        baseline_path = root / "spec" / "baseline" / "ui-delivery-approved.json"
        baseline_path.parent.mkdir(parents=True)
        baseline_path.write_text(json.dumps({"schema_version": 2, "status": "approved"}), encoding="utf-8")

        with pytest.raises(ValueError, match="malformed index"):
            inventory_path(root, None)

    def test_index_exists_inventory_source_not_dict_must_valueerror(self, tmp_path):
        """Index exists but inventory_source is not dict - must ValueError."""
        root = tmp_path / "project"
        index_path = root / "spec" / "execution" / "ui-inputs" / "index.json"
        index_path.parent.mkdir(parents=True)
        index_path.write_text(json.dumps({"schema_version": 2, "inventory_source": "string"}), encoding="utf-8")

        baseline_path = root / "spec" / "baseline" / "ui-delivery-approved.json"
        baseline_path.parent.mkdir(parents=True)
        baseline_path.write_text(json.dumps({"schema_version": 2, "status": "approved"}), encoding="utf-8")

        with pytest.raises(ValueError, match="malformed index"):
            inventory_path(root, None)

    def test_index_exists_missing_path_must_valueerror(self, tmp_path):
        """Index exists but inventory_source.path missing - must ValueError."""
        root = tmp_path / "project"
        index_path = root / "spec" / "execution" / "ui-inputs" / "index.json"
        index_path.parent.mkdir(parents=True)
        index_path.write_text(json.dumps({
            "schema_version": 2,
            "inventory_source": {"sha256": "abc123"}
        }), encoding="utf-8")

        baseline_path = root / "spec" / "baseline" / "ui-delivery-approved.json"
        baseline_path.parent.mkdir(parents=True)
        baseline_path.write_text(json.dumps({"schema_version": 2, "status": "approved"}), encoding="utf-8")

        with pytest.raises(ValueError, match="malformed index"):
            inventory_path(root, None)

    def test_index_exists_path_not_string_must_valueerror(self, tmp_path):
        """Index exists but inventory_source.path is not string - must ValueError."""
        root = tmp_path / "project"
        index_path = root / "spec" / "execution" / "ui-inputs" / "index.json"
        index_path.parent.mkdir(parents=True)
        index_path.write_text(json.dumps({
            "schema_version": 2,
            "inventory_source": {"path": 123}
        }), encoding="utf-8")

        baseline_path = root / "spec" / "baseline" / "ui-delivery-approved.json"
        baseline_path.parent.mkdir(parents=True)
        baseline_path.write_text(json.dumps({"schema_version": 2, "status": "approved"}), encoding="utf-8")

        with pytest.raises(ValueError, match="malformed index"):
            inventory_path(root, None)

    def test_index_exists_missing_sha256_must_valueerror(self, tmp_path):
        """Index exists but inventory_source.sha256 missing - must ValueError."""
        root = tmp_path / "project"
        index_path = root / "spec" / "execution" / "ui-inputs" / "index.json"
        index_path.parent.mkdir(parents=True)
        index_path.write_text(json.dumps({
            "schema_version": 2,
            "inventory_source": {"path": "spec/execution/approved.json"}
        }), encoding="utf-8")

        baseline_path = root / "spec" / "baseline" / "ui-delivery-approved.json"
        baseline_path.parent.mkdir(parents=True)
        baseline_path.write_text(json.dumps({"schema_version": 2, "status": "approved"}), encoding="utf-8")

        with pytest.raises(ValueError, match="malformed index"):
            inventory_path(root, None)

    def test_index_exists_sha256_not_string_must_valueerror(self, tmp_path):
        """Index exists but inventory_source.sha256 is not string - must ValueError."""
        root = tmp_path / "project"
        index_path = root / "spec" / "execution" / "ui-inputs" / "index.json"
        index_path.parent.mkdir(parents=True)
        index_path.write_text(json.dumps({
            "schema_version": 2,
            "inventory_source": {"path": "spec/execution/approved.json", "sha256": 123}
        }), encoding="utf-8")

        baseline_path = root / "spec" / "baseline" / "ui-delivery-approved.json"
        baseline_path.parent.mkdir(parents=True)
        baseline_path.write_text(json.dumps({"schema_version": 2, "status": "approved"}), encoding="utf-8")

        with pytest.raises(ValueError, match="malformed index"):
            inventory_path(root, None)

    def test_no_index_returns_baseline(self, tmp_path):
        """No index file - should return canonical baseline without error."""
        root = tmp_path / "project"
        baseline_path = root / "spec" / "baseline" / "ui-delivery-approved.json"
        baseline_path.parent.mkdir(parents=True)
        baseline_path.write_text(json.dumps({"schema_version": 2, "status": "approved"}), encoding="utf-8")

        result = inventory_path(root, None)
        assert result == baseline_path

    def test_explicit_path_overrides_bad_index(self, tmp_path):
        """Explicit path has priority even if index is malformed."""
        root = tmp_path / "project"

        # Bad index
        index_path = root / "spec" / "execution" / "ui-inputs" / "index.json"
        index_path.parent.mkdir(parents=True)
        index_path.write_text("[]", encoding="utf-8")

        # Explicit inventory
        explicit_path = root / "custom" / "inventory.json"
        explicit_path.parent.mkdir(parents=True)
        explicit_path.write_text(json.dumps({"schema_version": 2}), encoding="utf-8")

        result = inventory_path(root, "custom/inventory.json")
        assert result == explicit_path


class TestLoadInventoryNonCanonicalStrict:
    """Test load_inventory enforces strict validation for non-canonical approved files."""

    def test_noncanonical_missing_ancestor_sha_must_reject(self, tmp_path):
        """Non-canonical approved file missing baseline_ancestor_sha256 - must reject."""
        root = tmp_path / "project"

        # Canonical baseline
        baseline_path = root / "spec" / "baseline" / "ui-delivery-approved.json"
        baseline_path.parent.mkdir(parents=True)
        baseline = {"schema_version": 2, "status": "approved", "units": []}
        baseline_path.write_text(json.dumps(baseline), encoding="utf-8")

        # Non-canonical approved without ancestor (but with validation dict to pass earlier check)
        approved_path = root / "spec" / "execution" / "derived-approved.json"
        approved_path.parent.mkdir(parents=True)
        approved = {
            "schema_version": 2,
            "status": "approved",
            "units": [],
            "approval": {"confirmation_ref": "ABC123", "candidate_sha256": "a"*64, "validation_receipt_sha256": "b"*64},
            "validation": {"errors": []}
        }
        approved_path.write_text(json.dumps(approved), encoding="utf-8")

        with pytest.raises(ValueError, match="derived inventory requires canonical baseline|ancestor"):
            load_inventory(root, "spec/execution/derived-approved.json")

    def test_noncanonical_missing_confirmation_ref_must_reject(self, tmp_path):
        """Non-canonical approved file missing approval.confirmation_ref - must reject."""
        root = tmp_path / "project"

        baseline_path = root / "spec" / "baseline" / "ui-delivery-approved.json"
        baseline_path.parent.mkdir(parents=True)
        baseline = {"schema_version": 2, "status": "approved", "units": []}
        baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
        baseline_sha = sha256_file(baseline_path)

        approved_path = root / "spec" / "execution" / "derived-approved.json"
        approved_path.parent.mkdir(parents=True)
        approved = {
            "schema_version": 2,
            "status": "approved",
            "units": [],
            "baseline_ancestor_sha256": baseline_sha,
            "approval": {}  # Missing confirmation_ref
        }
        approved_path.write_text(json.dumps(approved), encoding="utf-8")

        with pytest.raises(ValueError, match="confirmation_ref"):
            load_inventory(root, "spec/execution/derived-approved.json")

    def test_noncanonical_validation_errors_not_empty_must_reject(self, tmp_path):
        """Non-canonical approved file with validation.errors not [] - must reject."""
        root = tmp_path / "project"

        baseline_path = root / "spec" / "baseline" / "ui-delivery-approved.json"
        baseline_path.parent.mkdir(parents=True)
        baseline = {"schema_version": 2, "status": "approved", "units": []}
        baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
        baseline_sha = sha256_file(baseline_path)

        approved_path = root / "spec" / "execution" / "derived-approved.json"
        approved_path.parent.mkdir(parents=True)
        approved = {
            "schema_version": 2,
            "status": "approved",
            "units": [],
            "baseline_ancestor_sha256": baseline_sha,
            "approval": {"confirmation_ref": "ABC123"},
            "validation": {"errors": ["some error"]}  # Not empty
        }
        approved_path.write_text(json.dumps(approved), encoding="utf-8")

        with pytest.raises(ValueError, match="validation errors"):
            load_inventory(root, "spec/execution/derived-approved.json")

    def test_noncanonical_missing_proof_path_must_reject(self, tmp_path):
        """Non-canonical with ancestor but missing provenance.proof_path - must reject."""
        root = tmp_path / "project"

        baseline_path = root / "spec" / "baseline" / "ui-delivery-approved.json"
        baseline_path.parent.mkdir(parents=True)
        baseline = {"schema_version": 2, "status": "approved", "units": []}
        baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
        baseline_sha = sha256_file(baseline_path)

        approved_path = root / "spec" / "execution" / "derived-approved.json"
        approved_path.parent.mkdir(parents=True)
        approved = {
            "schema_version": 2,
            "status": "approved",
            "units": [],
            "baseline_ancestor_sha256": baseline_sha,
            "approval": {"confirmation_ref": "ABC123", "candidate_sha256": "a"*64, "validation_receipt_sha256": "b"*64},
            "validation": {"errors": []},
            "provenance": {"baseline_path": "spec/baseline/ui-delivery-approved.json", "baseline_sha256": baseline_sha, "proof_sha256": "abc"}  # Missing proof_path
        }
        approved_path.write_text(json.dumps(approved), encoding="utf-8")

        with pytest.raises(ValueError, match="proof_path"):
            load_inventory(root, "spec/execution/derived-approved.json")

    def test_noncanonical_proof_file_not_found_must_reject(self, tmp_path):
        """Non-canonical with proof_path that doesn't exist - must reject."""
        root = tmp_path / "project"

        baseline_path = root / "spec" / "baseline" / "ui-delivery-approved.json"
        baseline_path.parent.mkdir(parents=True)
        baseline = {"schema_version": 2, "status": "approved", "units": []}
        baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
        baseline_sha = sha256_file(baseline_path)

        approved_path = root / "spec" / "execution" / "derived-approved.json"
        approved_path.parent.mkdir(parents=True)
        approved = {
            "schema_version": 2,
            "status": "approved",
            "units": [],
            "baseline_ancestor_sha256": baseline_sha,
            "approval": {"confirmation_ref": "ABC123", "candidate_sha256": "a"*64, "validation_receipt_sha256": "b"*64},
            "validation": {"errors": []},
            "provenance": {
                "baseline_path": "spec/baseline/ui-delivery-approved.json",
                "baseline_sha256": baseline_sha,
                "proof_path": "spec/execution/proof.json",
                "proof_sha256": "abc123"
            }
        }
        approved_path.write_text(json.dumps(approved), encoding="utf-8")

        with pytest.raises(ValueError, match="proof not found"):
            load_inventory(root, "spec/execution/derived-approved.json")

    def test_noncanonical_proof_sha_mismatch_must_reject(self, tmp_path):
        """Non-canonical with proof SHA mismatch - must reject."""
        root = tmp_path / "project"

        baseline_path = root / "spec" / "baseline" / "ui-delivery-approved.json"
        baseline_path.parent.mkdir(parents=True)
        baseline = {"schema_version": 2, "status": "approved", "units": []}
        baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
        baseline_sha = sha256_file(baseline_path)

        proof_path = root / "spec" / "execution" / "proof.json"
        proof_path.parent.mkdir(parents=True, exist_ok=True)
        proof = {"baseline_sha256": baseline_sha, "requests": []}
        proof_path.write_text(json.dumps(proof), encoding="utf-8")
        proof_sha = sha256_file(proof_path)

        approved_path = root / "spec" / "execution" / "derived-approved.json"
        approved_path.parent.mkdir(parents=True, exist_ok=True)
        approved = {
            "schema_version": 2,
            "status": "approved",
            "units": [],
            "baseline_ancestor_sha256": baseline_sha,
            "approval": {"confirmation_ref": "ABC123", "candidate_sha256": "a"*64, "validation_receipt_sha256": "b"*64},
            "validation": {"errors": []},
            "provenance": {
                "baseline_path": "spec/baseline/ui-delivery-approved.json",
                "baseline_sha256": baseline_sha,
                "proof_path": "spec/execution/proof.json",
                "proof_sha256": "wrong_sha"  # Mismatch
            }
        }
        approved_path.write_text(json.dumps(approved), encoding="utf-8")

        with pytest.raises(ValueError, match="proof SHA mismatch"):
            load_inventory(root, "spec/execution/derived-approved.json")

    def test_noncanonical_missing_candidate_sha256_in_receipt_route_must_reject(self, tmp_path):
        """Non-canonical with validation_receipt_sha256 but missing candidate_sha256 - must reject."""
        root = tmp_path / "project"

        baseline_path = root / "spec" / "baseline" / "ui-delivery-approved.json"
        baseline_path.parent.mkdir(parents=True)
        baseline = {"schema_version": 2, "status": "approved", "units": []}
        baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
        baseline_sha = sha256_file(baseline_path)

        approved_path = root / "spec" / "execution" / "derived-approved.json"
        approved_path.parent.mkdir(parents=True)
        approved = {
            "schema_version": 2,
            "status": "approved",
            "units": [],
            "baseline_ancestor_sha256": baseline_sha,
            "approval": {
                "confirmation_ref": "ABC123",
                "validation_receipt_sha256": "receipt_sha"  # Has receipt but missing candidate
            },
            "validation": {"errors": []}
        }
        approved_path.write_text(json.dumps(approved), encoding="utf-8")

        with pytest.raises(ValueError, match="candidate_sha256"):
            load_inventory(root, "spec/execution/derived-approved.json")

    def test_canonical_baseline_legacy_semantics_pass(self, tmp_path):
        """Canonical baseline with legacy semantics (no approval fields) - should pass."""
        root = tmp_path / "project"

        baseline_path = root / "spec" / "baseline" / "ui-delivery-approved.json"
        baseline_path.parent.mkdir(parents=True)
        baseline = {"schema_version": 2, "status": "approved", "units": []}
        baseline_path.write_text(json.dumps(baseline), encoding="utf-8")

        path, data = load_inventory(root, None)
        assert path == baseline_path
        assert data == baseline


class TestFreezerUsesSharedAPI:
    """Test that freezer uses load_inventory shared API and rejects invalid inventories."""

    def test_freezer_rejects_noncanonical_without_ancestor(self, tmp_path):
        """Freezer must reject non-canonical inventory without ancestor before creating index."""
        root = tmp_path / "project"

        # Canonical baseline exists
        baseline_path = root / "spec" / "baseline" / "ui-delivery-approved.json"
        baseline_path.parent.mkdir(parents=True)
        baseline = {
            "schema_version": 2,
            "status": "approved",
            "units": [{"unit_id": "u1", "page_id": "p1", "required_states": [{"state_id": "s1"}]}],
            "source_project_root": str(root / "source")
        }
        baseline_path.write_text(json.dumps(baseline), encoding="utf-8")

        # Source root
        (root / "source").mkdir()

        # Non-canonical without ancestor (but with validation to pass earlier check)
        derived_path = root / "spec" / "execution" / "derived.json"
        derived_path.parent.mkdir(parents=True)
        derived = {
            "schema_version": 2,
            "status": "approved",
            "units": [{"unit_id": "u1", "page_id": "p1", "required_states": [{"state_id": "s1"}]}],
            "source_project_root": str(root / "source"),
            "approval": {"confirmation_ref": "ABC", "candidate_sha256": "a"*64, "validation_receipt_sha256": "b"*64},
            "validation": {"errors": []}
        }
        derived_path.write_text(json.dumps(derived), encoding="utf-8")

        # Freezer must reject before creating index
        index_path = root / "spec" / "execution" / "ui-inputs" / "index.json"

        with pytest.raises(ValueError, match="ancestor|baseline"):
            freeze(["--project-root", str(root), "--inventory", "spec/execution/derived.json"])

        # Index should not be created
        assert not index_path.exists()


class TestFourConcreteRepairs:
    """Test four concrete repairs for remaining strict validation gaps."""

    def test_repair1_validation_errors_missing_field_must_reject(self, tmp_path):
        """REPAIR 1: validation dict exists but errors field missing - must reject."""
        root = tmp_path / "project"

        baseline_path = root / "spec" / "baseline" / "ui-delivery-approved.json"
        baseline_path.parent.mkdir(parents=True)
        baseline = {"schema_version": 2, "status": "approved", "units": []}
        baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
        baseline_sha = sha256_file(baseline_path)

        approved_path = root / "spec" / "execution" / "derived-approved.json"
        approved_path.parent.mkdir(parents=True)
        approved = {
            "schema_version": 2,
            "status": "approved",
            "units": [],
            "baseline_ancestor_sha256": baseline_sha,
            "approval": {"confirmation_ref": "ABC123", "candidate_sha256": "a"*64, "validation_receipt_sha256": "b"*64},
            "validation": {}  # Missing errors field
        }
        approved_path.write_text(json.dumps(approved), encoding="utf-8")

        with pytest.raises(ValueError, match="validation missing errors field"):
            load_inventory(root, "spec/execution/derived-approved.json")

    def test_repair1_validation_errors_none_must_reject(self, tmp_path):
        """REPAIR 1: validation.errors is None (not []) - must reject."""
        root = tmp_path / "project"

        baseline_path = root / "spec" / "baseline" / "ui-delivery-approved.json"
        baseline_path.parent.mkdir(parents=True)
        baseline = {"schema_version": 2, "status": "approved", "units": []}
        baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
        baseline_sha = sha256_file(baseline_path)

        approved_path = root / "spec" / "execution" / "derived-approved.json"
        approved_path.parent.mkdir(parents=True)
        approved = {
            "schema_version": 2,
            "status": "approved",
            "units": [],
            "baseline_ancestor_sha256": baseline_sha,
            "approval": {"confirmation_ref": "ABC123", "candidate_sha256": "a"*64, "validation_receipt_sha256": "b"*64},
            "validation": {"errors": None}  # None not []
        }
        approved_path.write_text(json.dumps(approved), encoding="utf-8")

        with pytest.raises(ValueError, match="validation.errors is None, must be"):
            load_inventory(root, "spec/execution/derived-approved.json")

    def test_repair2_both_approval_hashes_missing_must_reject(self, tmp_path):
        """REPAIR 2: BOTH candidate_sha256 and validation_receipt_sha256 missing - must reject."""
        root = tmp_path / "project"

        baseline_path = root / "spec" / "baseline" / "ui-delivery-approved.json"
        baseline_path.parent.mkdir(parents=True)
        baseline = {"schema_version": 2, "status": "approved", "units": []}
        baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
        baseline_sha = sha256_file(baseline_path)

        approved_path = root / "spec" / "execution" / "derived-approved.json"
        approved_path.parent.mkdir(parents=True)
        approved = {
            "schema_version": 2,
            "status": "approved",
            "units": [],
            "baseline_ancestor_sha256": baseline_sha,
            "approval": {"confirmation_ref": "ABC123"},  # Missing both hashes
            "validation": {"errors": []}
        }
        approved_path.write_text(json.dumps(approved), encoding="utf-8")

        with pytest.raises(ValueError, match="candidate_sha256"):
            load_inventory(root, "spec/execution/derived-approved.json")

    def test_repair2_candidate_sha256_not_string_must_reject(self, tmp_path):
        """REPAIR 2: candidate_sha256 not a string - must reject."""
        root = tmp_path / "project"

        baseline_path = root / "spec" / "baseline" / "ui-delivery-approved.json"
        baseline_path.parent.mkdir(parents=True)
        baseline = {"schema_version": 2, "status": "approved", "units": []}
        baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
        baseline_sha = sha256_file(baseline_path)

        approved_path = root / "spec" / "execution" / "derived-approved.json"
        approved_path.parent.mkdir(parents=True)
        approved = {
            "schema_version": 2,
            "status": "approved",
            "units": [],
            "baseline_ancestor_sha256": baseline_sha,
            "approval": {"confirmation_ref": "ABC123", "candidate_sha256": 12345, "validation_receipt_sha256": "b"*64},
            "validation": {"errors": []}
        }
        approved_path.write_text(json.dumps(approved), encoding="utf-8")

        with pytest.raises(ValueError, match="candidate_sha256 hash string"):
            load_inventory(root, "spec/execution/derived-approved.json")

    def test_repair3_provenance_baseline_path_missing_must_reject(self, tmp_path):
        """REPAIR 3: provenance.baseline_path missing - must reject."""
        root = tmp_path / "project"

        baseline_path = root / "spec" / "baseline" / "ui-delivery-approved.json"
        baseline_path.parent.mkdir(parents=True)
        baseline = {"schema_version": 2, "status": "approved", "units": []}
        baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
        baseline_sha = sha256_file(baseline_path)

        approved_path = root / "spec" / "execution" / "derived-approved.json"
        approved_path.parent.mkdir(parents=True)
        approved = {
            "schema_version": 2,
            "status": "approved",
            "units": [],
            "baseline_ancestor_sha256": baseline_sha,
            "approval": {"confirmation_ref": "ABC123", "candidate_sha256": "a"*64, "validation_receipt_sha256": "b"*64},
            "validation": {"errors": []},
            "provenance": {"baseline_sha256": baseline_sha}  # Missing baseline_path
        }
        approved_path.write_text(json.dumps(approved), encoding="utf-8")

        with pytest.raises(ValueError, match="provenance.baseline_path"):
            load_inventory(root, "spec/execution/derived-approved.json")

    def test_repair3_provenance_baseline_sha256_missing_must_reject(self, tmp_path):
        """REPAIR 3: provenance.baseline_sha256 missing - must reject."""
        root = tmp_path / "project"

        baseline_path = root / "spec" / "baseline" / "ui-delivery-approved.json"
        baseline_path.parent.mkdir(parents=True)
        baseline = {"schema_version": 2, "status": "approved", "units": []}
        baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
        baseline_sha = sha256_file(baseline_path)

        approved_path = root / "spec" / "execution" / "derived-approved.json"
        approved_path.parent.mkdir(parents=True)
        approved = {
            "schema_version": 2,
            "status": "approved",
            "units": [],
            "baseline_ancestor_sha256": baseline_sha,
            "approval": {"confirmation_ref": "ABC123", "candidate_sha256": "a"*64, "validation_receipt_sha256": "b"*64},
            "validation": {"errors": []},
            "provenance": {"baseline_path": "spec/baseline/ui-delivery-approved.json"}  # Missing baseline_sha256
        }
        approved_path.write_text(json.dumps(approved), encoding="utf-8")

        with pytest.raises(ValueError, match="provenance.baseline_sha256"):
            load_inventory(root, "spec/execution/derived-approved.json")

    def test_repair3_provenance_baseline_path_not_canonical_must_reject(self, tmp_path):
        """REPAIR 3: provenance.baseline_path not canonical baseline - must reject."""
        root = tmp_path / "project"

        baseline_path = root / "spec" / "baseline" / "ui-delivery-approved.json"
        baseline_path.parent.mkdir(parents=True)
        baseline = {"schema_version": 2, "status": "approved", "units": []}
        baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
        baseline_sha = sha256_file(baseline_path)

        approved_path = root / "spec" / "execution" / "derived-approved.json"
        approved_path.parent.mkdir(parents=True)
        approved = {
            "schema_version": 2,
            "status": "approved",
            "units": [],
            "baseline_ancestor_sha256": baseline_sha,
            "approval": {"confirmation_ref": "ABC123", "candidate_sha256": "a"*64, "validation_receipt_sha256": "b"*64},
            "validation": {"errors": []},
            "provenance": {
                "baseline_path": "spec/baseline/other.json",  # Not canonical
                "baseline_sha256": baseline_sha
            }
        }
        approved_path.write_text(json.dumps(approved), encoding="utf-8")

        with pytest.raises(ValueError, match="provenance baseline_path must be canonical baseline"):
            load_inventory(root, "spec/execution/derived-approved.json")

    def test_repair3_provenance_baseline_sha256_mismatch_must_reject(self, tmp_path):
        """REPAIR 3: provenance.baseline_sha256 mismatch with actual - must reject."""
        root = tmp_path / "project"

        baseline_path = root / "spec" / "baseline" / "ui-delivery-approved.json"
        baseline_path.parent.mkdir(parents=True)
        baseline = {"schema_version": 2, "status": "approved", "units": []}
        baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
        baseline_sha = sha256_file(baseline_path)

        approved_path = root / "spec" / "execution" / "derived-approved.json"
        approved_path.parent.mkdir(parents=True)
        approved = {
            "schema_version": 2,
            "status": "approved",
            "units": [],
            "baseline_ancestor_sha256": baseline_sha,
            "approval": {"confirmation_ref": "ABC123", "candidate_sha256": "a"*64, "validation_receipt_sha256": "b"*64},
            "validation": {"errors": []},
            "provenance": {
                "baseline_path": "spec/baseline/ui-delivery-approved.json",
                "baseline_sha256": "wrong_sha"  # Mismatch
            }
        }
        approved_path.write_text(json.dumps(approved), encoding="utf-8")

        with pytest.raises(ValueError, match="provenance baseline_sha256 mismatch"):
            load_inventory(root, "spec/execution/derived-approved.json")

    def test_repair4_active_index_empty_sha_must_reject(self, tmp_path):
        """REPAIR 4: active index with empty SHA string - must reject."""
        root = tmp_path / "project"

        baseline_path = root / "spec" / "baseline" / "ui-delivery-approved.json"
        baseline_path.parent.mkdir(parents=True)
        baseline = {"schema_version": 2, "status": "approved", "units": []}
        baseline_path.write_text(json.dumps(baseline), encoding="utf-8")

        # Create index with empty SHA
        index_path = root / "spec" / "execution" / "ui-inputs" / "index.json"
        index_path.parent.mkdir(parents=True)
        index = {
            "schema_version": 2,
            "inventory_source": {
                "path": "spec/baseline/ui-delivery-approved.json",
                "sha256": ""  # Empty string
            }
        }
        index_path.write_text(json.dumps(index), encoding="utf-8")

        with pytest.raises(ValueError, match="inventory_source.sha256 is empty or invalid"):
            load_inventory(root, None)

    def test_repair4_active_index_whitespace_sha_must_reject(self, tmp_path):
        """REPAIR 4: active index with whitespace-only SHA - must reject."""
        root = tmp_path / "project"

        baseline_path = root / "spec" / "baseline" / "ui-delivery-approved.json"
        baseline_path.parent.mkdir(parents=True)
        baseline = {"schema_version": 2, "status": "approved", "units": []}
        baseline_path.write_text(json.dumps(baseline), encoding="utf-8")

        # Create index with whitespace SHA
        index_path = root / "spec" / "execution" / "ui-inputs" / "index.json"
        index_path.parent.mkdir(parents=True)
        index = {
            "schema_version": 2,
            "inventory_source": {
                "path": "spec/baseline/ui-delivery-approved.json",
                "sha256": "   "  # Whitespace
            }
        }
        index_path.write_text(json.dumps(index), encoding="utf-8")

        with pytest.raises(ValueError, match="inventory_source.sha256 is empty or invalid"):
            load_inventory(root, None)
