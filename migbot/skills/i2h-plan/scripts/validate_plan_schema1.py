#!/usr/bin/env python3
"""Validate Plan schema-1 outputs against current source using native contracts.

Uses generate_execute_coverage.build() to derive expected requirements from
current source, and acceptance_plan.seal() to validate acceptance plan structure.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Import native producer contracts
from generate_execute_coverage import build
from acceptance_plan import current_requirements, seal


def _read_json(path: Path) -> Any:
    """Read JSON file, returning None on error."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def validate_plan_outputs(root: Path) -> dict[str, Any]:
    """Validate Plan schema-1 outputs against current source."""
    result = {
        "complete": False,
        "errors": [],
        "warnings": [],
    }

    # Derive expected requirements from current source
    try:
        expected_index, expected_coverage = build(root)
    except (OSError, ValueError) as exc:
        result["errors"].append(f"source_build_failed: {exc}")
        return result

    expected_reqs = {row["requirement_id"]: row for row in expected_index["requirements"]}
    expected_packets = {pkt["packet_id"]: pkt for pkt in expected_coverage["packets"]}

    # Validate requirements-index.json
    req_path = root / "spec/.i2h/requirements-index.json"
    if not req_path.is_file():
        result["errors"].append("requirements_index_missing")
        return result

    req_data = _read_json(req_path)
    if not isinstance(req_data, dict):
        result["errors"].append("requirements_index_not_object")
        return result

    if req_data.get("schema_version") != 1:
        result["errors"].append("requirements_index_schema_version")

    requirements = req_data.get("requirements")
    if not isinstance(requirements, list):
        result["errors"].append("requirements_index_requirements_not_list")
        return result

    # Check each requirement against current source
    actual_reqs = {}
    for req in requirements:
        if not isinstance(req, dict):
            result["errors"].append("requirements_index_requirement_not_object")
            continue

        req_id = req.get("requirement_id")
        if not isinstance(req_id, str) or not req_id:
            result["errors"].append("requirements_index_requirement_id_invalid")
            continue

        if req_id in actual_reqs:
            result["errors"].append(f"requirements_index_duplicate_{req_id}")
        actual_reqs[req_id] = req

        # Validate against current source
        if req_id not in expected_reqs:
            result["errors"].append(f"requirements_index_unknown_{req_id}")
            continue

        expected = expected_reqs[req_id]

        # Validate digest
        if req.get("digest") != expected["digest"]:
            result["errors"].append(f"requirements_index_stale_digest_{req_id}")

        # Validate source_file
        if req.get("source_file") != expected["source_file"]:
            result["errors"].append(f"requirements_index_wrong_source_{req_id}")

        # Validate statement matches
        if req.get("statement") != expected["statement"]:
            result["errors"].append(f"requirements_index_wrong_statement_{req_id}")

        # Validate feature_id matches
        if req.get("feature_id") != expected["feature_id"]:
            result["errors"].append(f"requirements_index_wrong_feature_{req_id}")

    # Check coverage
    missing_reqs = set(expected_reqs) - set(actual_reqs)
    if missing_reqs:
        result["errors"].append(f"requirements_index_incomplete")
        result["missing_requirements"] = sorted(missing_reqs)

    # Validate plan-coverage.json
    cov_path = root / "spec/.i2h/plan-coverage.json"
    if not cov_path.is_file():
        result["errors"].append("plan_coverage_missing")
        return result

    cov_data = _read_json(cov_path)
    if not isinstance(cov_data, dict):
        result["errors"].append("plan_coverage_not_object")
        return result

    if cov_data.get("schema_version") != 1:
        result["errors"].append("plan_coverage_schema_version")

    packets = cov_data.get("packets")
    if not isinstance(packets, list):
        result["errors"].append("plan_coverage_packets_not_list")
        return result

    # Validate packet completeness and no duplicates
    actual_packets = {}
    for packet in packets:
        if not isinstance(packet, dict):
            result["errors"].append("plan_coverage_packet_not_object")
            continue

        packet_id = packet.get("packet_id")
        if not isinstance(packet_id, str):
            result["errors"].append("plan_coverage_packet_id_invalid")
            continue

        if packet_id in actual_packets:
            result["errors"].append(f"plan_coverage_duplicate_packet_{packet_id}")
        actual_packets[packet_id] = packet

        if packet_id not in expected_packets:
            result["errors"].append(f"plan_coverage_unknown_packet_{packet_id}")
            continue

        expected_pkt = expected_packets[packet_id]

        req_ids = packet.get("requirement_ids")
        if not isinstance(req_ids, list):
            result["errors"].append(f"plan_coverage_packet_{packet_id}_requirement_ids_not_list")
            continue

        # Validate all requirement IDs are strings before set operations
        for req_id in req_ids:
            if not isinstance(req_id, str):
                result["errors"].append(f"plan_coverage_packet_{packet_id}_requirement_id_not_string")
                break
        else:
            # Validate requirement_ids match current source
            if set(req_ids) != set(expected_pkt["requirement_ids"]):
                result["errors"].append(f"plan_coverage_packet_{packet_id}_wrong_requirements")

        req_digests = packet.get("requirement_digests")
        if not isinstance(req_digests, dict):
            result["errors"].append(f"plan_coverage_packet_{packet_id}_requirement_digests_not_dict")
            continue

        # Validate each digest matches current source exactly
        for req_id in req_ids:
            if not isinstance(req_id, str):
                continue
            if req_id not in req_digests:
                result["errors"].append(f"plan_coverage_packet_{packet_id}_missing_digest_{req_id}")
            elif req_id in expected_reqs:
                if req_digests[req_id] != expected_reqs[req_id]["digest"]:
                    result["errors"].append(f"plan_coverage_packet_{packet_id}_stale_digest_{req_id}")

    # Check packet completeness
    missing_packets = set(expected_packets) - set(actual_packets)
    if missing_packets:
        result["errors"].append("plan_coverage_incomplete_packets")
        result["missing_packets"] = sorted(missing_packets)

    # Validate acceptance-plan.json - REQUIRED for native Plan admission
    plan_path = root / "spec/baseline/plans/acceptance-plan.json"
    if not plan_path.is_file():
        result["errors"].append("acceptance_plan_missing")
        return result

    plan_data = _read_json(plan_path)
    if not isinstance(plan_data, dict):
        result["errors"].append("acceptance_plan_not_object")
        return result

    if "acceptance_criteria" in plan_data and "criteria" not in plan_data:
        result["errors"].append("acceptance_plan_wrong_field_name")
        return result

    version = plan_data.get("schema_version")
    if type(version) is not int or version not in (1, 2):
        result["errors"].append("acceptance_plan_schema_version")
        return result

    if not isinstance(plan_data.get("criteria"), list):
        result["errors"].append("acceptance_plan_criteria_not_list")
        return result

    # Validate by re-sealing current requirements and comparing
    criteria = plan_data["criteria"]

    # Extract bindings from sealed plan
    bindings = []
    for criterion in criteria:
        if not isinstance(criterion, dict):
            result["errors"].append("acceptance_plan_criterion_not_object")
            continue
        binding = {"requirement_id": criterion.get("requirement_id")}
        if "hypium" in criterion:
            binding["hypium"] = criterion["hypium"]
        if criterion.get("scenario") is not None:
            binding.update(scenario=criterion["scenario"], assertions=criterion.get("assertions", []))
        if len(binding) > 1:
            bindings.append(binding)

    # Re-seal with current requirements
    try:
        current_reqs = current_requirements(root)
        expected_plan = seal(current_reqs, {"schema_version": 1, "bindings": bindings}, version=version)

        # Compare sealed plan to actual
        if plan_data != expected_plan:
            result["errors"].append("acceptance_plan_seal_mismatch")
            # Check specific mismatches
            if len(criteria) != len(expected_plan["criteria"]):
                result["errors"].append("acceptance_plan_incomplete_criteria")
    except (ValueError, KeyError, TypeError) as exc:
        result["errors"].append(f"acceptance_plan_seal_failed: {exc}")

    result["complete"] = not result["errors"]
    return result
