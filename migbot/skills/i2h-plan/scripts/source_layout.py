#!/usr/bin/env python3
"""Extract source-backed SwiftUI/UIKit layout obligations.

The extractor records relationships and source literals; it never derives a
layout value from a screenshot.  Unknown/dynamic expressions stay unresolved
so the converter or reviewer must make the decision explicitly.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extract_file(path: Path, root: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    nodes = []
    for match in re.finditer(r"\b(VStack|HStack|ZStack|LazyVStack|LazyHStack|List|ScrollView|Form|NavigationStack|GeometryReader|UIView|UIStackView|UICollectionView|UITableView)\b", text):
        name = match.group(1)
        line = text.count("\n", 0, match.start()) + 1
        nodes.append({"kind": "container", "type": name, "line": line, "source": {"file": path.relative_to(root).as_posix(), "line": line}})
    dimensions = []
    for match in re.finditer(r"\.(padding|frame|offset|cornerRadius|spacing)\s*\(([^\n)]*)\)", text):
        expression = match.group(2).strip()
        line = text.count("\n", 0, match.start()) + 1
        literal = re.fullmatch(r"[-+]?\d+(?:\.\d+)?", expression)
        dimensions.append({"modifier": match.group(1), "expression": expression, "resolution": "source_literal" if literal else "unresolved", "value": float(expression) if literal and "." in expression else (int(expression) if literal else None), "unit": "pt_or_adaptive", "source": {"file": path.relative_to(root).as_posix(), "line": line}})
    relationships = []
    for match in re.finditer(r"\b(NavigationLink|TabView|sheet|fullScreenCover|overlay|background)\b", text):
        line = text.count("\n", 0, match.start()) + 1
        relationships.append({"type": match.group(1), "line": line, "source": {"file": path.relative_to(root).as_posix(), "line": line}})
    return {"file": path.relative_to(root).as_posix(), "sha256": sha256(path), "nodes": nodes, "dimensions": dimensions, "relationships": relationships, "unresolved": [item["expression"] for item in dimensions if item["resolution"] == "unresolved"]}


def extract(project_root: str | Path, view_file: str | None = None) -> dict[str, Any]:
    root = Path(project_root).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"project root not found: {root}")
    files = [root / view_file] if view_file else sorted(root.rglob("*.swift"))
    files = [p for p in files if p.is_file() and "Tests" not in p.parts and "Test" not in p.name]
    layouts = [extract_file(path, root) for path in files]
    return {"schema_version": 1, "tool_version": "i2h-source-layout/1.0", "authority": "ios_source_constraints_v1", "project_root": str(root), "sources": [{"file": item["file"], "sha256": item["sha256"]} for item in layouts], "layouts": layouts, "layout_obligations": [dimension for item in layouts for dimension in item["dimensions"]]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    extract_parser = sub.add_parser("extract")
    extract_parser.add_argument("--project-root", required=True)
    extract_parser.add_argument("--view-file")
    extract_parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    try:
        result = extract(args.project_root, args.view_file)
        path = Path(args.out); path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"output": args.out, "sources": len(result["sources"]), "obligations": len(result["layout_obligations"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
