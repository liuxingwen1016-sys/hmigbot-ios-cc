#!/usr/bin/env python3
"""Build the execute requirement index from the approved plan artifacts.

The execute phase consumes ``spec/.i2h/requirements-index.json`` and
``spec/.i2h/plan-coverage.json``.  Older i2h-plan runs only emitted markdown
plans, which left execute with an undocumented, hand-authored input.  This
generator derives both JSON files from feature acceptance criteria and slice
files, and fails closed when the plan is incomplete.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


AC_RE = re.compile(r"^\s*-\s*\[[ xX]\]\s+([A-Z][0-9]{3}-AC[0-9]{2})\s+(.+?)\s*$")
FEATURE_RE = re.compile(r"^\s*-\s*\*\*feature_id\*\*:\s*`?([A-Z][0-9]{3})`?\s*$")
MODIFIES_RE = re.compile(r"^\s*-\s+([^#\s].*?)\s*$")


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _feature_id(path: Path, text: str) -> str:
    match = FEATURE_RE.search(text)
    if match:
        return match.group(1)
    match = re.search(r"feat_[0-9]+_([A-Za-z0-9]+)", path.stem)
    if match:
        return "F" + match.group(0).split("_")[1]
    heading = re.match(r"^#\s+(F[0-9]{3})\b", text)
    if heading:
        return heading.group(1)
    raise ValueError(f"cannot determine feature id from {path}")


def _acceptance_criteria(path: Path, text: str, source_file: str | None = None) -> list[dict[str, str]]:
    in_section = False
    result: list[dict[str, str]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("## 验收标准") or line.startswith("## Acceptance Criteria"):
            in_section = True
            continue
        if in_section and line.startswith("## "):
            break
        if not in_section:
            continue
        match = AC_RE.match(raw)
        if not match:
            continue
        requirement_id, statement = match.groups()
        canonical = f"{requirement_id} {statement}"
        result.append({
            "requirement_id": requirement_id,
            "statement": statement,
            "source_file": source_file or str(path),
            "digest": _digest(canonical),
        })
    return result


def _slice_packet(path: Path, text: str, requirement_digests: dict[str, str], source_file: str | None = None) -> dict[str, Any]:
    match = re.search(r"^##\s+Slice\s+[^:(]+\s*\((F[0-9]{3})\)", text, re.MULTILINE)
    feature_id = match.group(1) if match else None
    if not feature_id:
        match = re.search(r"^feature_id:\s*(F[0-9]{3})\s*$", text, re.MULTILINE)
        feature_id = match.group(1) if match else None
    if not feature_id:
        raise ValueError(f"cannot determine feature id from {path}")

    files: list[str] = []
    in_modifies = False
    for raw in text.splitlines():
        line = raw.strip()
        if line == "modifies_files:":
            in_modifies = True
            continue
        if in_modifies and line and not line.startswith("-"):
            in_modifies = False
        if in_modifies:
            match = MODIFIES_RE.match(line)
            if match:
                files.append(match.group(1))

    packet_id = path.stem
    requirement_ids = sorted(requirement_digests)
    return {
        "packet_id": packet_id,
        "feature_id": feature_id,
        "requirement_ids": requirement_ids,
        "requirement_digests": {key: requirement_digests[key] for key in requirement_ids},
        "files": files,
        "source_file": source_file or str(path),
    }


def build(project_root: str | Path) -> tuple[dict[str, Any], dict[str, Any]]:
    root = Path(project_root).expanduser().resolve()
    feature_dir = root / "spec/baseline/features"
    slice_dir = root / "spec/baseline/plans/slices"
    if not feature_dir.is_dir():
        raise ValueError(f"missing feature directory: {feature_dir}")
    if not slice_dir.is_dir():
        raise ValueError(f"missing slice directory: {slice_dir}")

    requirements: list[dict[str, Any]] = []
    by_feature: dict[str, list[dict[str, str]]] = {}
    for path in sorted(feature_dir.glob("feat_*.md")):
        text = path.read_text(encoding="utf-8")
        feature_id = _feature_id(path, text)
        relative_path = str(path.relative_to(root))
        criteria = _acceptance_criteria(path, text, relative_path)
        if not criteria:
            raise ValueError(f"no acceptance criteria found for {feature_id}: {path}")
        by_feature[feature_id] = criteria
        for criterion in criteria:
            requirements.append({
                "requirement_id": criterion["requirement_id"],
                "feature_id": feature_id,
                "status": "active",
                "statement": criterion["statement"],
                "source_file": criterion["source_file"],
                "digest": criterion["digest"],
            })

    packets: list[dict[str, Any]] = []
    packet_features: set[str] = set()
    for path in sorted(slice_dir.glob("slice-*.md")):
        text = path.read_text(encoding="utf-8")
        feature_match = re.search(r"^feature_id:\s*(F[0-9]{3})\s*$", text, re.MULTILINE)
        feature_id = feature_match.group(1) if feature_match else None
        if feature_id is None:
            feature_match = re.search(r"\((F[0-9]{3})\)", text)
            feature_id = feature_match.group(1) if feature_match else None
        if feature_id is None:
            raise ValueError(f"cannot determine feature id from {path}")
        if feature_id not in by_feature:
            raise ValueError(f"slice {path.name} has no matching feature spec {feature_id}")
        criteria = by_feature[feature_id]
        relative_path = str(path.relative_to(root))
        packet = _slice_packet(path, text, {item["requirement_id"]: item["digest"] for item in criteria}, relative_path)
        packets.append(packet)
        packet_features.add(feature_id)

    missing = sorted(set(by_feature) - packet_features)
    if missing:
        raise ValueError(f"features without plan slices: {', '.join(missing)}")

    requirements.sort(key=lambda item: item["requirement_id"])
    index = {
        "schema_version": 1,
        "source": "i2h-plan/generate_execute_coverage.py",
        "source_project_root": str(root),
        "requirements": requirements,
    }
    coverage = {
        "schema_version": 1,
        "source": "i2h-plan/generate_execute_coverage.py",
        "source_project_root": str(root),
        "packets": packets,
    }
    return index, coverage


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--requirements-out")
    parser.add_argument("--coverage-out")
    args = parser.parse_args(argv)
    try:
        requirements, coverage = build(args.project_root)
        root = Path(args.project_root).expanduser().resolve()
        out_dir = root / "spec/.i2h"
        req_path = Path(args.requirements_out).expanduser() if args.requirements_out else out_dir / "requirements-index.json"
        cov_path = Path(args.coverage_out).expanduser() if args.coverage_out else out_dir / "plan-coverage.json"
        req_path.parent.mkdir(parents=True, exist_ok=True)
        cov_path.parent.mkdir(parents=True, exist_ok=True)
        req_path.write_text(json.dumps(requirements, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        cov_path.write_text(json.dumps(coverage, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"requirements": len(requirements["requirements"]), "packets": len(coverage["packets"]), "requirements_out": str(req_path), "coverage_out": str(cov_path)}, ensure_ascii=False))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
