#!/usr/bin/env python3
"""Compose page metadata from native inventory facts and reviewed semantics."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any

from runtime_view import atomic_json


FACT_FIELDS = ("view_name", "file_path", "type", "line_count", "declaration_line", "body_line", "body_source",
               "properties", "source_sha256", "ui_obligations")
SEMANTIC_FIELDS = {"purpose", "complexity", "confidence", "navigation_role", "dependencies", "ui_structure",
                   "state_management", "interactions", "conversion_strategy", "ios_source_anchors"}
IDENTITY_FIELDS = {"page_id", "view_name", "file_path"}


def merge_semantic_pages(directory: Path, input_hash: str) -> dict[str, Any]:
    if not directory.is_dir():
        raise ValueError(f"semantic page directory does not exist: {directory}")
    pages = []
    shared = None
    for path in sorted(directory.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        if (not isinstance(record, dict) or record.get("schema_version") != 1
                or record.get("target_input_sha256") != input_hash):
            raise ValueError(f"semantic page must bind the current source input: {path.name}")
        rows = record.get("pages")
        if (not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict)
                or rows[0].get("page_id") != path.stem):
            raise ValueError(f"expected one semantic page matching its filename: {path.name}")
        envelope = {key: value for key, value in record.items() if key != "pages"}
        if shared is not None and shared != envelope:
            raise ValueError(f"semantic page metadata disagrees with other page files: {path.name}")
        shared = envelope
        pages.append(rows[0])
    return {**(shared or {"schema_version": 1, "target_input_sha256": input_hash}), "pages": pages}


def compose(inventory: dict[str, Any], semantics: dict[str, Any]) -> dict[str, dict[str, Any]]:
    input_hash = inventory.get("target_input_sha256")
    if not isinstance(input_hash, str) or not input_hash or semantics.get("target_input_sha256") != input_hash:
        raise ValueError("page semantics and native inventory must bind the same source input")
    if semantics.get("schema_version") != 1 or not isinstance(semantics.get("pages"), list):
        raise ValueError("expected schema-1 semantic pages")
    facts = {(page["view_name"], page["file_path"]): page for page in inventory["pages"]}
    if len(facts) != len(inventory["pages"]):
        raise ValueError("native inventory contains duplicate page declarations")
    output = {}
    seen = set()
    for semantic in semantics["pages"]:
        key = (semantic["view_name"], semantic["file_path"])
        page_id = semantic["page_id"]
        if key not in facts or key in seen or page_id in output or not re.fullmatch(r"page_\d{4}_[A-Za-z][A-Za-z0-9_]*", page_id):
            raise ValueError(f"invalid or duplicate page identity: {page_id} {key}")
        if set(semantic) - SEMANTIC_FIELDS - IDENTITY_FIELDS:
            raise ValueError(f"page {page_id} has fields owned by the native inventory or capture tools")
        if not isinstance(semantic.get("purpose"), str) or not semantic["purpose"].strip():
            raise ValueError(f"missing purpose for page {page_id}")
        if semantic.get("confidence") not in {"high", "medium", "low"}:
            raise ValueError(f"missing or invalid confidence for page {page_id}")
        if semantic.get("complexity") not in {"simple", "medium", "complex", "very_complex"}:
            raise ValueError(f"missing or invalid complexity for page {page_id}")
        for field, expected in (("ui_structure", dict), ("state_management", dict), ("interactions", list),
                                ("conversion_strategy", dict), ("ios_source_anchors", dict)):
            if not isinstance(semantic.get(field), expected):
                raise ValueError(f"missing or invalid {field} for page {page_id}")
        native = facts[key]
        anchors = {"primary_file": key[1], **semantic["ios_source_anchors"]}
        if anchors["primary_file"] != key[1]:
            raise ValueError(f"primary source anchor does not match page {page_id}")
        meta = {field: native[field] for field in FACT_FIELDS if field in native}
        meta.update({field: value for field, value in semantic.items() if field in SEMANTIC_FIELDS or field == "page_id"})
        meta["target_input_sha256"] = input_hash
        meta["ios_source_anchors"] = anchors
        controls = native.get("ui_obligations", {}).get("accessibility_identifiers", [])
        reviewed = [action.get("identifier") for action in semantic["interactions"] if isinstance(action, dict)]
        meta["accessibility_identifiers"] = sorted({name for name in [*controls, *reviewed] if isinstance(name, str) and name})
        output[page_id] = meta
        seen.add(key)
    if seen != set(facts):
        missing = sorted(f"{name} ({path})" for name, path in set(facts) - seen)
        raise ValueError(f"missing semantics for native pages: {', '.join(missing)}")
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", required=True, type=Path)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--semantics", type=Path, help="existing combined schema-1 semantics")
    inputs.add_argument("--semantics-dir", type=Path, help="schema-1 single-page files named by page_id")
    parser.add_argument("--merged-semantics-out", type=Path, help="write the validated combined semantics for consumers")
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.merged_semantics_out is not None and args.semantics_dir is None:
        parser.error("--merged-semantics-out requires --semantics-dir")
    try:
        inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
        if args.semantics_dir is not None:
            semantics = merge_semantic_pages(args.semantics_dir, inventory.get("target_input_sha256"))
        else:
            semantics = json.loads(args.semantics.read_text(encoding="utf-8"))
        pages = compose(inventory, semantics)
        if args.merged_semantics_out is not None:
            merged = args.merged_semantics_out.resolve()
            inputs_dir = args.semantics_dir.resolve()
            meta_outputs = {(args.output_root / page_id / "meta.json").resolve() for page_id in pages}
            if merged == args.inventory.resolve() or merged.is_relative_to(inputs_dir) or merged in meta_outputs:
                raise ValueError("merged semantics output must be separate from inputs and page metadata")
            atomic_json(merged, semantics)
        for page_id, meta in pages.items():
            path = args.output_root / page_id / "meta.json"
            atomic_json(path, meta)
    except (OSError, KeyError, TypeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"status": "PASS", "pages": len(pages), "output_root": str(args.output_root)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
