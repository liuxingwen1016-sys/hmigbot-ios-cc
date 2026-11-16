#!/usr/bin/env python3
"""Tests for Plan schema-1 validation using native producer contracts."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from generate_execute_coverage import build
from acceptance_plan import current_requirements, seal
import validate_plan_schema1 as validator


class ValidatePlanOutputsWithNativeProducerTest(unittest.TestCase):
    """Test validation using native producer contracts with real source fixtures."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def create_source_fixture(self, features: dict[str, list[str]], slices: dict[str, tuple[str, list[str]]]):
        """Create source features and slices.

        features: {feature_id: [list of AC statements]}
        slices: {slice_id: (feature_id, [list of files])}
        """
        feature_dir = self.root / "spec/baseline/features"
        slice_dir = self.root / "spec/baseline/plans/slices"
        feature_dir.mkdir(parents=True)
        slice_dir.mkdir(parents=True)

        for feature_id, statements in features.items():
            feat_num = feature_id[1:]  # F001 -> 001
            feat_path = feature_dir / f"feat_{feat_num}_test.md"
            ac_lines = [f"- [ ] {feature_id}-AC{i+1:02d} {stmt}" for i, stmt in enumerate(statements)]
            content = f"""# {feature_id}: Test Feature

## 基本信息

- **feature_id**: `{feature_id}`

## Acceptance Criteria

{chr(10).join(ac_lines)}
"""
            feat_path.write_text(content, encoding="utf-8")

        for slice_id, (feature_id, files) in slices.items():
            slice_path = slice_dir / f"{slice_id}.md"
            file_lines = [f"  - {f}" for f in files]
            content = f"""## Slice: Test ({feature_id})

feature_id: {feature_id}

modifies_files:
{chr(10).join(file_lines)}
"""
            slice_path.write_text(content, encoding="utf-8")

    def write_native_outputs_with_seal(self, bindings: list[dict] | None = None):
        """Generate and write outputs using native producers including sealed acceptance plan."""
        index, coverage = build(self.root)
        current_reqs = current_requirements(self.root)

        # Create sealed acceptance plan
        if bindings is None:
            # Default: empty bindings = all requirements with scenario=None
            bindings = []
        sealed_plan = seal(current_reqs, {"schema_version": 1, "bindings": bindings})

        i2h_dir = self.root / "spec/.i2h"
        plan_dir = self.root / "spec/baseline/plans"
        i2h_dir.mkdir(parents=True, exist_ok=True)
        plan_dir.mkdir(parents=True, exist_ok=True)

        (i2h_dir / "requirements-index.json").write_text(
            json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (i2h_dir / "plan-coverage.json").write_text(
            json.dumps(coverage, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (plan_dir / "acceptance-plan.json").write_text(
            json.dumps(sealed_plan, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return index, coverage, sealed_plan

    def test_valid_native_outputs_with_seal_accepted(self):
        """Valid outputs from native producers with sealed acceptance plan are accepted."""
        self.create_source_fixture(
            features={"F001": ["User can save data", "User can load data"]},
            slices={"slice-01-F001": ("F001", ["entry/src/main/ets/pages/Index.ets"])}
        )
        self.write_native_outputs_with_seal()

        result = validator.validate_plan_outputs(self.root)
        self.assertTrue(result["complete"], result)
        self.assertEqual(result["errors"], [])

    def test_missing_acceptance_plan_rejected(self):
        """Missing acceptance-plan.json is rejected for native Plan admission."""
        self.create_source_fixture(
            features={"F001": ["Save data"]},
            slices={"slice-01-F001": ("F001", ["page.ets"])}
        )
        index, coverage = build(self.root)

        i2h_dir = self.root / "spec/.i2h"
        i2h_dir.mkdir(parents=True, exist_ok=True)
        (i2h_dir / "requirements-index.json").write_text(
            json.dumps(index, ensure_ascii=False), encoding="utf-8"
        )
        (i2h_dir / "plan-coverage.json").write_text(
            json.dumps(coverage, ensure_ascii=False), encoding="utf-8"
        )
        # Do NOT write acceptance-plan.json

        result = validator.validate_plan_outputs(self.root)
        self.assertFalse(result["complete"])
        self.assertIn("acceptance_plan_missing", result["errors"])

    def test_missing_packet_rejected(self):
        """Missing packet in coverage is rejected."""
        self.create_source_fixture(
            features={"F001": ["Save"]},
            slices={"slice-01-F001": ("F001", ["page.ets"])}
        )
        index, coverage, sealed_plan = self.write_native_outputs_with_seal()

        # Remove packet from coverage
        coverage["packets"] = []

        (self.root / "spec/.i2h/plan-coverage.json").write_text(
            json.dumps(coverage, ensure_ascii=False), encoding="utf-8"
        )

        result = validator.validate_plan_outputs(self.root)
        self.assertFalse(result["complete"])
        self.assertIn("plan_coverage_incomplete_packets", result["errors"])

    def test_duplicate_packet_id_rejected(self):
        """Duplicate packet_id is rejected."""
        self.create_source_fixture(
            features={"F001": ["Save"]},
            slices={"slice-01-F001": ("F001", ["page.ets"])}
        )
        index, coverage, sealed_plan = self.write_native_outputs_with_seal()

        # Duplicate packet
        coverage["packets"].append(coverage["packets"][0].copy())

        (self.root / "spec/.i2h/plan-coverage.json").write_text(
            json.dumps(coverage, ensure_ascii=False), encoding="utf-8"
        )

        result = validator.validate_plan_outputs(self.root)
        self.assertFalse(result["complete"])
        self.assertTrue(any("duplicate_packet" in e for e in result["errors"]))

    def test_requirement_id_not_string_rejected(self):
        """Non-string requirement_id in packet causes structured error."""
        self.create_source_fixture(
            features={"F001": ["Save"]},
            slices={"slice-01-F001": ("F001", ["page.ets"])}
        )
        index, coverage, sealed_plan = self.write_native_outputs_with_seal()

        # Make requirement_id a dict
        coverage["packets"][0]["requirement_ids"] = [{"id": "F001-AC01"}]

        (self.root / "spec/.i2h/plan-coverage.json").write_text(
            json.dumps(coverage, ensure_ascii=False), encoding="utf-8"
        )

        result = validator.validate_plan_outputs(self.root)
        self.assertFalse(result["complete"])
        self.assertTrue(any("requirement_id_not_string" in e for e in result["errors"]))

    def test_top_level_list_requirements_rejected(self):
        """Top-level list requirements-index.json is rejected."""
        self.create_source_fixture(
            features={"F001": ["User can save"]},
            slices={"slice-01-F001": ("F001", ["page.ets"])}
        )
        index, coverage, sealed_plan = self.write_native_outputs_with_seal()

        # Write as top-level list
        (self.root / "spec/.i2h/requirements-index.json").write_text(
            json.dumps(index["requirements"], ensure_ascii=False), encoding="utf-8"
        )

        result = validator.validate_plan_outputs(self.root)
        self.assertFalse(result["complete"])
        self.assertIn("requirements_index_not_object", result["errors"])

    def test_requirement_digests_as_list_rejected(self):
        """requirement_digests as list instead of dict is rejected."""
        self.create_source_fixture(
            features={"F001": ["Save user data"]},
            slices={"slice-01-F001": ("F001", ["page.ets"])}
        )
        index, coverage, sealed_plan = self.write_native_outputs_with_seal()

        # Mutate coverage to have digests as list
        for packet in coverage["packets"]:
            packet["requirement_digests"] = list(packet["requirement_digests"].values())

        (self.root / "spec/.i2h/plan-coverage.json").write_text(
            json.dumps(coverage, ensure_ascii=False), encoding="utf-8"
        )

        result = validator.validate_plan_outputs(self.root)
        self.assertFalse(result["complete"])
        self.assertTrue(any("requirement_digests_not_dict" in e for e in result["errors"]))

    def test_source_mutation_invalidates_cached_index(self):
        """Mutating source AC statement invalidates cached requirements-index."""
        self.create_source_fixture(
            features={"F001": ["Original statement"]},
            slices={"slice-01-F001": ("F001", ["page.ets"])}
        )
        self.write_native_outputs_with_seal()

        # Mutate source AC statement
        feature_file = self.root / "spec/baseline/features/feat_001_test.md"
        content = feature_file.read_text(encoding="utf-8")
        content = content.replace("Original statement", "Modified statement")
        feature_file.write_text(content, encoding="utf-8")

        # Cached index/coverage/plan remain unchanged
        result = validator.validate_plan_outputs(self.root)
        self.assertFalse(result["complete"])
        self.assertTrue(any("stale_digest" in e or "wrong_statement" in e for e in result["errors"]))

    def test_tampered_statement_with_correct_digest_rejected(self):
        """Hand-written index with correct digest but wrong statement is rejected."""
        self.create_source_fixture(
            features={"F001": ["Correct statement"]},
            slices={"slice-01-F001": ("F001", ["page.ets"])}
        )
        index, coverage, sealed_plan = self.write_native_outputs_with_seal()

        # Tamper statement but keep digest correct
        index["requirements"][0]["statement"] = "Tampered statement"

        (self.root / "spec/.i2h/requirements-index.json").write_text(
            json.dumps(index, ensure_ascii=False), encoding="utf-8"
        )

        result = validator.validate_plan_outputs(self.root)
        self.assertFalse(result["complete"])
        self.assertIn("requirements_index_wrong_statement_F001-AC01", result["errors"])

    def test_wrong_packet_digest_rejected(self):
        """Wrong packet digest is rejected against current source."""
        self.create_source_fixture(
            features={"F001": ["Save data"]},
            slices={"slice-01-F001": ("F001", ["page.ets"])}
        )
        index, coverage, sealed_plan = self.write_native_outputs_with_seal()

        # Corrupt packet digest
        for packet in coverage["packets"]:
            for req_id in packet["requirement_digests"]:
                packet["requirement_digests"][req_id] = "a" * 64

        (self.root / "spec/.i2h/plan-coverage.json").write_text(
            json.dumps(coverage, ensure_ascii=False), encoding="utf-8"
        )

        result = validator.validate_plan_outputs(self.root)
        self.assertFalse(result["complete"])
        self.assertTrue(any("stale_digest" in e for e in result["errors"]))

    def test_acceptance_plan_wrong_field_name_rejected(self):
        """acceptance_criteria field instead of criteria is rejected."""
        self.create_source_fixture(
            features={"F001": ["Save"]},
            slices={"slice-01-F001": ("F001", ["page.ets"])}
        )
        self.write_native_outputs_with_seal()

        (self.root / "spec/baseline/plans/acceptance-plan.json").write_text(json.dumps({
            "schema_version": 1,
            "acceptance_criteria": []  # Wrong field name
        }), encoding="utf-8")

        result = validator.validate_plan_outputs(self.root)
        self.assertFalse(result["complete"])
        self.assertIn("acceptance_plan_wrong_field_name", result["errors"])

    def test_acceptance_plan_subset_criteria_rejected(self):
        """Acceptance plan with subset of criteria is rejected via seal mismatch."""
        self.create_source_fixture(
            features={"F001": ["Save", "Load"]},
            slices={"slice-01-F001": ("F001", ["page.ets"])}
        )
        index, coverage, sealed_plan = self.write_native_outputs_with_seal()

        # Remove one criterion
        sealed_plan["criteria"] = sealed_plan["criteria"][:1]

        (self.root / "spec/baseline/plans/acceptance-plan.json").write_text(
            json.dumps(sealed_plan, ensure_ascii=False), encoding="utf-8"
        )

        result = validator.validate_plan_outputs(self.root)
        self.assertFalse(result["complete"])
        self.assertIn("acceptance_plan_seal_mismatch", result["errors"])

    def test_empty_criteria_with_requirements_rejected(self):
        """Empty criteria list when requirements exist is rejected."""
        self.create_source_fixture(
            features={"F001": ["Save data"]},
            slices={"slice-01-F001": ("F001", ["page.ets"])}
        )
        self.write_native_outputs_with_seal()

        # Write empty criteria
        (self.root / "spec/baseline/plans/acceptance-plan.json").write_text(json.dumps({
            "schema_version": 1,
            "criteria": []
        }), encoding="utf-8")

        result = validator.validate_plan_outputs(self.root)
        self.assertFalse(result["complete"])
        self.assertIn("acceptance_plan_seal_mismatch", result["errors"])


class ModuleProvenanceTest(unittest.TestCase):
    """Verify test modules are loaded from sandbox."""

    def test_module_provenance_in_sandbox(self):
        """Verify all modules are from the canonical clean clone, not dirty repo."""
        import validate_plan_schema1
        import generate_execute_coverage
        import acceptance_plan

        _REPO_ROOT = Path(__file__).resolve().parents[4]
        for module in [validate_plan_schema1, generate_execute_coverage, acceptance_plan]:
            module_file = Path(module.__file__).resolve()
            self.assertTrue(
                module_file.is_relative_to(_REPO_ROOT),
                f"{module.__name__} not under canonical clone: {module_file}"
            )
            self.assertNotIn("ios2harmony/hmigbot-ios", str(module_file),
                             f"{module.__name__} from dirty repo: {module_file}")


if __name__ == "__main__":
    unittest.main()
