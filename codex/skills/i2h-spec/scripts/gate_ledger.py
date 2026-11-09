#!/usr/bin/env python3
"""Mechanical release-ledger check for the i2h pipeline.

The Android implementation has a much larger compiled gate registry.  The iOS
port keeps the safety-critical part source-visible: parse release decisions,
reject unknown/exact/hard rules that have not been repaired, and emit the
verify focus consumed by i2h-verify.  It never turns missing evidence into a
PASS.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


REGISTRY: dict[str, dict[str, Any]] = {
    "C4_BUILDER_NOT_FOUND": {"gate": "closure.wiring", "class": "inference", "hard": False},
    "C4_REPLACEMENT_NOT_FOUND": {"gate": "closure.wiring", "class": "inference", "hard": False},
    "SPEC.DIALOG_UNACCOUNTED": {"gate": "spec.dialog-closure", "class": "inference", "hard": False},
    "SPEC.UNCOVERED_ANCHOR_FILE": {"gate": "spec.coverage", "class": "inference", "hard": False},
    "SPEC.AC_LINE_UNPARSEABLE": {"gate": "spec.coverage", "class": "exact", "hard": False},
    "PLAN.REQUIREMENT_UNOWNED": {"gate": "plan.coverage", "class": "exact", "hard": False},
    "ROUTE_PARAM_KEY_MISMATCH": {"gate": "closure.arkui-safety", "class": "exact", "hard": True},
    "NAV_ROOT_COUNT": {"gate": "closure.arkui-safety", "class": "inference", "hard": True},
    "LOOP.NOT_CONVERGING": {"gate": "findings.queue", "class": "inference", "hard": False},
}


def load_registry() -> dict[str, dict[str, Any]]:
    return dict(REGISTRY)


def resolve(registry: dict[str, dict[str, Any]], rule: str) -> dict[str, Any] | None:
    token = rule.strip().strip("`")
    if token in registry:
        return {"rule": token, **registry[token]}
    for key, value in registry.items():
        if token.endswith(key):
            return {"rule": key, **value}
    # Gate-only entries remain inference unless a known gate is contradicted.
    if token in {value["gate"] for value in registry.values()}:
        return {"rule": token, "gate": token, "class": "inference", "hard": False}
    return None


def _field(body: str, label: str) -> str:
    match = re.search(rf"(?:^|\n)-\s*\*\*{re.escape(label)}\*\*\s*[：:]\s*(.+)", body)
    return match.group(1).strip() if match else ""


def parse_ledger(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8")
    chunks = re.split(r"(?m)^#{3,4}\s+(D-\d+)\s+", text)
    entries = []
    for index in range(1, len(chunks), 2):
        decision = chunks[index]
        body = chunks[index + 1] if index + 1 < len(chunks) else ""
        kind = _field(body, "类型")
        gate = _field(body, "门禁")
        evidence = _field(body, "证据") or _field(body, "工具输出")
        rounds = _field(body, "已修轮次")
        selected = _field(body, "选定")
        entries.append({"decision": decision, "kind": kind, "gate": gate, "evidence": evidence, "rounds": rounds, "selected": selected, "body": body})
    return entries


def _rules(gate: str) -> list[str]:
    return [part.strip().strip("`") for part in re.split(r"[/、,，]", gate) if part.strip()]


def _rounds(value: str) -> int:
    match = re.search(r"\d+", value or "")
    return int(match.group(0)) if match else 0


def check(project_root: str | Path) -> tuple[int, dict[str, Any]]:
    root = Path(project_root).expanduser().resolve()
    entries = parse_ledger(root / "spec/decision-ledger.md")
    errors: list[str] = []
    focus: list[dict[str, Any]] = []
    summary_rows: list[str] = []
    release_kinds = {"工具缺口", "未达标放行", "阶段不可判定"}
    for entry in entries:
        if entry["kind"] not in release_kinds:
            continue
        rules = _rules(entry["gate"])
        if not rules:
            errors.append(f"{entry['decision']}: 缺少门禁")
            continue
        resolved = [resolve(REGISTRY, rule) for rule in rules]
        if any(item is None for item in resolved):
            errors.append(f"{entry['decision']}: 门禁不在登记表")
            continue
        if not entry["evidence"]:
            errors.append(f"{entry['decision']}: 缺少证据或工具输出")
            continue
        for item in resolved:
            assert item is not None
            if item["hard"] and entry["kind"] == "未达标放行":
                errors.append(f"{entry['decision']}: hard 规则不能以未达标放行")
            if item["class"] == "exact" and _rounds(entry["rounds"]) < 1:
                errors.append(f"{entry['decision']}: 精确类闸疑似缺陷，必须先修复")
            focus.append({"decision": entry["decision"], "kind": entry["kind"], "gate": item["gate"], "rule": item["rule"], "ios_locations": []})
            summary_rows.append(f"| {entry['decision']} | {item['gate']} / {item['rule']} | {item['class']} |")
    output = root / "spec/gate-release"
    output.mkdir(parents=True, exist_ok=True)
    (output / "verify-focus.json").write_text(json.dumps({"schema_version": 1, "items": focus, "status": "PASS" if not errors else "FAIL"}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = ["# Gate Release Summary", "", f"status: {'PASS' if not errors else 'FAIL'}", "", "| decision | gate | class |", "|---|---|---|", *summary_rows]
    if errors:
        summary.extend(["", "## Errors", *[f"- {error}" for error in errors]])
    (output / "summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
    return (1 if errors else 0), {"status": "PASS" if not errors else "FAIL", "errors": errors, "focus": focus}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("check", "release"):
        command_parser = sub.add_parser(command)
        command_parser.add_argument("--project-root", required=True)
        command_parser.add_argument("--ios-root", "--android-root")
        command_parser.add_argument("--decision")
        command_parser.add_argument("--rule", action="append", default=[])
        command_parser.add_argument("--section")
    classify = sub.add_parser("classify")
    classify.add_argument("rule")
    args = parser.parse_args(argv)
    if args.command == "classify":
        item = resolve(REGISTRY, args.rule)
        print(json.dumps(item or {"rule": args.rule, "error": "unknown gate"}, ensure_ascii=False))
        return 0 if item else 1
    if args.command == "release":
        rc, result = check(args.project_root)
        if rc or not args.decision:
            return 1
        released = Path(args.project_root).expanduser().resolve() / "spec/gate-release/released.json"
        released.write_text(json.dumps({"decision": args.decision, "rules": args.rule, "section": args.section}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return 0
    rc, result = check(args.project_root)
    print(json.dumps(result, ensure_ascii=False))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
