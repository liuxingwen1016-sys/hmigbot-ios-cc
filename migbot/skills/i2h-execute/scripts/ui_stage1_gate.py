#!/usr/bin/env python3
"""Check approved iOS Stage 1 UI delivery without a native executable."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from lib.ios_stage1_scope import gate_from_inventory, inventory_path, load_inventory
    from lib.ui_stage1_gate import check
except (ImportError, OSError, SyntaxError) as exc:
    if __name__ != "__main__":
        raise
    print(f"ui_stage1_gate tool_error: {exc}", file=sys.stderr)
    raise SystemExit(3) from None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--inventory", help="approved schema-2 inventory, relative to the project by default")
    parser.add_argument("--wiring-dir", help="historical wiring manifests or a path to the approved inventory")
    parser.add_argument("--wiring-contract", help="additional explicit Stage 1 mount and action contract")
    parser.add_argument("--inputs-index", help="frozen conversion inputs index")
    parser.add_argument("--output-json", "--output", dest="output_json", help="write the JSON report to this path")
    args = parser.parse_args(argv)
    root = Path(args.project_root).expanduser().resolve()
    approved = inventory_path(root, args.inventory)
    wiring = inventory_path(root, args.wiring_dir) if args.wiring_dir else None
    legacy = False
    try:
        if args.inventory is None and wiring is not None and not approved.exists() and not (
            args.inputs_index or args.wiring_contract
        ):
            if wiring.is_dir():
                legacy = True
            elif wiring.is_file():
                try:
                    data = json.loads(wiring.read_text(encoding="utf-8"))
                    legacy = isinstance(data, dict) and data.get("schema_version") == 1
                except (OSError, ValueError):
                    pass
        if legacy:
            result = check(root, wiring)
        else:
            selection = args.inventory
            wiring_contract = args.wiring_contract
            if selection is None and wiring_contract:
                try:
                    load_inventory(root, wiring_contract)
                except (OSError, ValueError):
                    pass
                else:
                    selection, wiring_contract = wiring_contract, None
            if selection is None and wiring is not None and not wiring.is_dir():
                selection = args.wiring_dir
            result = gate_from_inventory(root, selection, args.inputs_index, wiring_contract)
            if wiring is not None and wiring.is_dir():
                findings = [
                    {**error, "root_cause": "product_defect"}
                    for error in check(root, wiring)["errors"]
                ]
                if findings:
                    result["status"] = "BLOCKED"
                    result["errors"] = result["errors"] + findings
                    result["failure_findings"] = result["errors"]
        report = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        if args.output_json:
            path = Path(args.output_json)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(report, encoding="utf-8")
        else:
            print(report, end="")
    except (ImportError, OSError, RuntimeError) as exc:
        print(f"ui_stage1_gate tool_error: {exc}", file=sys.stderr)
        return 3
    return 0 if result["status"] == "PASS" else 1 if legacy else 2


if __name__ == "__main__":
    raise SystemExit(main())
