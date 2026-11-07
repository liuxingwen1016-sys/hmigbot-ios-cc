#!/usr/bin/env python3
"""Normalize optional iOS simulator UI captures for downstream stages.

Android's runtime handoff is XML based.  iOS captures are intentionally JSON
sidecars because SwiftUI accessibility trees and UIKit hierarchies do not have
one stable XML representation.  The command validates and fingerprints a
capture when supplied; it never fabricates a runtime tree when no simulator
evidence exists.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


TOOL_VERSION = "i2h-runtime-view/1.0"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def normalize(path: Path) -> dict[str, Any]:
    try:
        source = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"runtime capture not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"runtime capture is not valid JSON: {path}: {exc}") from exc
    if not isinstance(source, dict):
        raise ValueError("runtime capture must be a JSON object")
    nodes = source.get("nodes", [])
    if nodes is None:
        nodes = []
    if not isinstance(nodes, list):
        raise ValueError("runtime capture 'nodes' must be an array")
    normalized_nodes = []
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            continue
        normalized_nodes.append({
            "id": node.get("id", f"node-{index:04d}"),
            "role": node.get("role") or node.get("type"),
            "label": node.get("label"),
            "value": node.get("value"),
            "frame": node.get("frame") or node.get("bounds"),
            "children": node.get("children", []),
            "source": node.get("source"),
        })
    warnings = []
    if not normalized_nodes:
        warnings.append("capture contains no accessibility nodes")
    if not source.get("screenshot"):
        warnings.append("capture has no screenshot path; visual comparison remains unavailable")
    return {
        "schema_version": 1,
        "tool_version": TOOL_VERSION,
        "runtime_available": True,
        "capture_sha256": digest(path),
        "page_id": source.get("page_id"),
        "captured_at": source.get("captured_at"),
        "device": source.get("device", {}),
        "screenshot": source.get("screenshot"),
        "nodes": normalized_nodes,
        "warnings": warnings,
        "provenance": {"source_file": str(path.resolve()), "format": "ios-accessibility-json"},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="iOS simulator/accessibility JSON capture")
    parser.add_argument("--output", required=True, help="normalized runtime evidence output")
    args = parser.parse_args(argv)
    try:
        result = normalize(Path(args.input).expanduser().resolve())
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    atomic_json(Path(args.output), result)
    print(json.dumps({"output": args.output, "page_id": result.get("page_id"), "nodes": len(result["nodes"]), "warnings": result["warnings"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
