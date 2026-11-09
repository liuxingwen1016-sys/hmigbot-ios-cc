#!/usr/bin/env python3
"""Report-only repair triage for i2h verification findings.

The script projects existing findings onto the current plan.  It never edits
the acceptance result or writes a repair queue, so a missing owner cannot
silently shrink verification scope.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1


def _load(path: Path) -> Any:
    value = json.loads(path.read_text(encoding="utf-8"))
    return value


def _rows(value: Any, label: str) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        plan_items = value.get("plan_items")
        if isinstance(plan_items, dict):
            return [
                {"id": ident, **item}
                for ident, item in plan_items.items()
                if isinstance(item, dict)
            ]
        for key in ("findings", "issues", "comparisons", "checks"):
            rows = value.get(key)
            if isinstance(rows, list):
                return [item for item in rows if isinstance(item, dict)]
    raise ValueError(f"{label} must be a list or an object containing findings")


def repair_priority(finding: dict[str, Any]) -> str:
    category = str(finding.get("category", "")).lower()
    rule = str(finding.get("rule", "")).upper()
    severity = str(finding.get("severity", "")).lower()
    if severity in {"blocking", "critical"} or category in {
        "crash", "startup_failure", "control_missing", "missing_control",
        "application_error_dialog",
    } or rule in {"CRASH", "UI.CRASH", "UI.STARTUP_FAILURE", "UI.MISSING_REQUIRED_CONTROL"}:
        return "P0"
    if category in {"content_mismatch", "state_mismatch", "route_mismatch", "persistence"}:
        return "P1"
    if category in {"color_mismatch", "style_mismatch", "config_difference"}:
        return "P2"
    if category == "layout_mismatch" and severity in {"low", "minor"}:
        return "P2"
    return "P1"


def _ids(finding: dict[str, Any], *names: str) -> set[str]:
    result: set[str] = set()
    for name in names:
        value = finding.get(name)
        if isinstance(value, str) and value:
            result.add(value)
        elif isinstance(value, list):
            result.update(item for item in value if isinstance(item, str) and item)
    return result


def triage(findings: list[dict[str, Any]], plan: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    plan = plan or []
    plan_rows = []
    for row in plan:
        ident = row.get("id") or row.get("item_id") or row.get("task_id")
        if not isinstance(ident, str) or not ident:
            continue
        plan_rows.append({"id": ident, **row})

    enriched = []
    for index, original in enumerate(findings, 1):
        finding = dict(original)
        finding_id = str(finding.get("id") or finding.get("finding_id") or f"finding-{index:04d}")
        finding["id"] = finding_id
        finding["repair_priority"] = repair_priority(finding)
        owner = finding.get("owner") or finding.get("owner_task") or finding.get("owner_stage")
        page_ids = _ids(finding, "page_id", "page_ids")
        feature_ids = _ids(finding, "feature_id", "feature_ids", "ac_id", "ac_ids")
        associated = []
        for task in plan_rows:
            task_owner = task.get("owner") or task.get("owner_stage")
            task_pages = _ids(task, "page_id", "page_ids")
            task_features = _ids(task, "feature_id", "feature_ids", "ac_id", "ac_ids")
            if ((owner and owner == task_owner) or page_ids & task_pages or feature_ids & task_features):
                associated.append(task["id"])
        if owner or page_ids or feature_ids:
            scope = "associated"
            reason = "matched owner/page/feature identity"
        else:
            scope = "full_ui"
            reason = "unknown ownership or missing stable scope; expand recheck"
            associated = [task["id"] for task in plan_rows]
        finding["impact"] = {
            "scope": scope,
            "reason": reason,
            "associated_plan_items": sorted(set(associated)),
            "acceptance_changed": False,
        }
        enriched.append(finding)

    enriched.sort(key=lambda item: (item["repair_priority"], item["id"]))
    counts = {level: sum(item["repair_priority"] == level for item in enriched) for level in ("P0", "P1", "P2")}
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "triaged",
        "report_only": True,
        "acceptance": "unchanged",
        "counts": counts,
        "findings": enriched,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--findings", required=True, help="JSON report or findings array")
    parser.add_argument("--plan", help="Optional JSON plan item list")
    parser.add_argument("--output-json", required=True)
    args = parser.parse_args(argv)
    findings = _rows(_load(Path(args.findings)), "findings")
    plan = _rows(_load(Path(args.plan)), "plan") if args.plan else []
    result = triage(findings, plan)
    destination = Path(args.output_json)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(destination), "status": result["status"], "counts": result["counts"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
