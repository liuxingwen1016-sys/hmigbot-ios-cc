#!/usr/bin/env python3
"""Validate selected source-side truth values for high-risk i2h flows.

An oracle is a reviewed input to test design, not proof that the target
implementation passed. Unselected or unresolved cases remain visible in the
report and do not become a full-pipeline gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1


def source_digest(root: Path) -> str:
    digest = hashlib.sha256()
    excluded = {".git", ".build", "build", "DerivedData", ".i2h", "Generated"}
    for path in sorted(p for p in root.rglob("*") if p.is_file() and not excluded.intersection(p.parts)):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def validate(payload: dict[str, Any], source_root: Path | None = None) -> dict[str, Any]:
    errors: list[str] = []
    cases = payload.get("cases")
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append("schema_version must be 1")
    if not isinstance(payload.get("source_sha256"), str) or not payload.get("source_sha256"):
        errors.append("source_sha256 is required")
    if not isinstance(cases, list) or not cases:
        errors.append("cases must be a non-empty array")
        cases = []
    seen: set[str] = set()
    result_cases = []
    for item in cases:
        if not isinstance(item, dict):
            errors.append("case must be an object")
            continue
        ident = item.get("case_id")
        if not isinstance(ident, str) or not ident or ident in seen:
            errors.append("case_id must be unique and non-empty")
            continue
        seen.add(ident)
        selected = item.get("selected", False) is True
        refs = item.get("source_refs", [])
        if not isinstance(refs, list) or not refs:
            errors.append(f"{ident}: source_refs are required")
            refs = []
        if selected and "expected" not in item:
            errors.append(f"{ident}: selected case needs expected value")
        status = item.get("status", "resolved" if "expected" in item else "unresolved")
        if status not in {"resolved", "unresolved"}:
            errors.append(f"{ident}: status must be resolved or unresolved")
        checked_refs = []
        for ref in refs:
            if not isinstance(ref, dict) or not isinstance(ref.get("path"), str) or not isinstance(ref.get("line"), int):
                errors.append(f"{ident}: malformed source_ref")
                continue
            if source_root is not None:
                path = (source_root / ref["path"]).resolve()
                if source_root not in path.parents or not path.is_file():
                    errors.append(f"{ident}: source_ref outside source root or missing")
                else:
                    lines = path.read_text(encoding="utf-8").splitlines()
                    line = ref["line"]
                    if line < 1 or line > len(lines):
                        errors.append(f"{ident}: source_ref line outside file")
                    elif "quote" in ref and ref["quote"] != lines[line - 1]:
                        errors.append(f"{ident}: source_ref quote changed")
            checked_refs.append(ref)
        result_cases.append({**item, "selected": selected, "status": status, "source_refs": checked_refs})
    source_match = None
    if source_root is not None and isinstance(payload.get("source_sha256"), str):
        source_match = source_digest(source_root) == payload["source_sha256"]
        if not source_match:
            errors.append("source_sha256 does not match current source")
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "valid" if not errors else "invalid",
        "selected_count": sum(item.get("selected") is True for item in result_cases),
        "resolved_count": sum(item.get("status") == "resolved" for item in result_cases),
        "source_match": source_match,
        "errors": errors,
        "cases": result_cases,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--source-root")
    parser.add_argument("--output-json", required=True)
    args = parser.parse_args(argv)
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    result = validate(payload, Path(args.source_root).resolve() if args.source_root else None)
    destination = Path(args.output_json)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(destination), "status": result["status"], "errors": len(result["errors"])}, ensure_ascii=False))
    return 0 if result["status"] == "valid" else 2


if __name__ == "__main__":
    raise SystemExit(main())
