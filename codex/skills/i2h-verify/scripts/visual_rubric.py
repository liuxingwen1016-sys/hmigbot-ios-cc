#!/usr/bin/env python3
"""Report-only visual difference rubric for iOS→HarmonyOS verification.

The rubric keeps functional completeness separate from platform visual
differences.  A design/configuration exception must bind the exact paired
evidence manifests and screenshot hashes.  Missing evidence is ``null`` and
never a passing score.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


SCHEMA = "i2h-visual-rubric/1"
PENALTIES = {"high": 0.05, "medium": 0.02, "low": 0.01}
ALLOWED_EXCEPTION_CATEGORIES = {"design_difference", "config_difference"}
PLATFORM_REASONS = {
    "system_status_bar",
    "system_navigation_bar",
    "font_rasterization",
    "system_material_blur",
    "safe_area_inset",
    "native_scroll_physics",
}
NON_WAIVABLE_CATEGORIES = {
    "control_missing",
    "content_mismatch",
    "state_mismatch",
    "control_type_mismatch",
    "route_mismatch",
    "interaction_failure",
    "application_error_dialog",
    "functional_difference",
}


def _exception_is_bound(item: dict[str, Any]) -> bool:
    evidence = item.get("evidence")
    if not isinstance(evidence, dict):
        return False
    required = {
        "source_manifest_sha256",
        "target_manifest_sha256",
        "source_screenshot_sha256",
        "target_screenshot_sha256",
    }
    return required <= set(evidence) and all(isinstance(evidence[key], str) and evidence[key] for key in required)


def evaluate(payload: dict[str, Any]) -> dict[str, Any]:
    differences = payload.get("differences")
    if not isinstance(differences, list):
        raise ValueError("differences must be an array")
    unresolved: list[dict[str, Any]] = []
    functional: list[dict[str, Any]] = []
    exceptions: list[dict[str, Any]] = []
    penalty = 0.0
    unknown = False
    for index, item in enumerate(differences, 1):
        if not isinstance(item, dict):
            raise ValueError(f"difference {index} must be an object")
        category = item.get("category")
        severity = item.get("severity", "medium")
        if category in NON_WAIVABLE_CATEGORIES:
            functional.append({**item, "id": item.get("id", f"UI-D{index:04d}"), "disposition": "needs_fix"})
            continue
        if category in ALLOWED_EXCEPTION_CATEGORIES:
            reason = item.get("reason")
            if reason not in PLATFORM_REASONS or not _exception_is_bound(item):
                unknown = True
                unresolved.append({**item, "id": item.get("id", f"UI-D{index:04d}"), "disposition": "needs_evidence"})
                continue
            exceptions.append({**item, "id": item.get("id", f"UI-D{index:04d}"), "disposition": "accepted_platform_difference"})
            continue
        unknown = True
        unresolved.append({**item, "id": item.get("id", f"UI-D{index:04d}"), "disposition": "needs_classification"})
    for item in unresolved:
        penalty += PENALTIES.get(item.get("severity", "medium"), PENALTIES["medium"])
    visual_score = None if unknown else round(max(0.0, 1.0 - penalty), 4)
    return {
        "schema_version": SCHEMA,
        "visual_score": visual_score,
        "visual_pass": visual_score is not None and visual_score >= 0.95,
        "functional_pass": not functional,
        "status": "PASS" if visual_score is not None and visual_score >= 0.95 and not functional else "FAIL",
        "unknown_evidence": unknown,
        "penalty": round(penalty, 4),
        "unresolved": unresolved,
        "accepted_platform_differences": exceptions,
        "functional_differences": functional,
        "policy": {
            "visual_threshold": 0.95,
            "functional_threshold": 1.0,
            "pHash_or_SSIM_not_authoritative": True,
            "missing_evidence_score": None,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
        result = evaluate(payload)
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}")
        return 2
    print(json.dumps({"output": str(output), "status": result["status"], "visual_score": result["visual_score"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
