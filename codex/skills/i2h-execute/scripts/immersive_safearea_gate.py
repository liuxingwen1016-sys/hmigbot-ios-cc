#!/usr/bin/env python3
"""Execute the source-driven immersive/safe-area closure gate.

The iOS delivery inventory carries ``needs_immersive_safearea`` for pages
whose SwiftUI source uses an immersive modifier or a full-screen destination.
This command runs the existing structural-closure checker and writes a
content-addressed, reviewable receipt for the i2h pipeline.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any


def _read(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _inventory_path(root: Path) -> Path | None:
    for path in (
        root / "spec/baseline/ui-delivery-approved.json",
        root / "spec/baseline/plans/stage1-ui-delivery.json",
        root / "spec/baseline/plans/ui-delivery-approved.json",
    ):
        if path.is_file():
            return path
    return None


def _checker_path(root: Path, explicit: str | None = None) -> Path | None:
    candidates = []
    if explicit:
        candidates.append(Path(explicit).expanduser())
    candidates.extend((
        root / ".agents/skills/arkts-structural-closure/scripts/check-fullscreen-immersive-safearea.sh",
        Path(__file__).resolve().parents[2] / "arkts-structural-closure/scripts/check-fullscreen-immersive-safearea.sh",
    ))
    return next((path for path in candidates if path.is_file()), None)


def _layers(stdout: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for layer in ("L1", "L2", "L3"):
        passed = len(re.findall(rf"✅\s*{layer}\b", stdout))
        failed = len(re.findall(rf"❌\s*{layer}\b", stdout))
        result[layer] = {"passed": passed, "failed": failed, "ok": failed == 0 and passed > 0}
    return result


def evaluate(root: Path | str, inventory: dict[str, Any] | None = None, checker: Path | str | None = None) -> dict[str, Any]:
    project = Path(root).expanduser().resolve()
    inventory_path = _inventory_path(project)
    data = inventory or (_read(inventory_path) if inventory_path else None)
    units = data.get("units", []) if isinstance(data, dict) else []
    required_units = [
        str(unit.get("unit_id"))
        for unit in units
        if isinstance(unit, dict) and unit.get("needs_immersive_safearea") is True
    ]
    result: dict[str, Any] = {
        "schema_version": 1,
        "gate": "i2h-execute.immersive-safearea",
        "project_root": str(project),
        "required_units": required_units,
        "inventory": inventory_path.relative_to(project).as_posix() if inventory_path else None,
        "status": "PASS",
        "layers": {},
        "errors": [],
        "warnings": [],
    }
    if inventory_path:
        result["inventory_sha256"] = hashlib.sha256(inventory_path.read_bytes()).hexdigest()
    if not required_units:
        result["status"] = "NOT_REQUIRED"
        return result
    script = _checker_path(project, str(checker) if checker else None)
    if script is None:
        result["status"] = "FAIL"
        result["errors"].append({"code": "CHECKER_MISSING", "message": "fullscreen immersive checker not installed"})
        return result
    completed = subprocess.run(
        ["bash", str(script)],
        cwd=str(project),
        text=True,
        capture_output=True,
        check=False,
    )
    stdout = (completed.stdout or "") + (completed.stderr or "")
    result["checker"] = str(script)
    result["returncode"] = completed.returncode
    result["layers"] = _layers(stdout)
    result["output"] = stdout
    if completed.returncode != 0:
        result["status"] = "FAIL"
        result["errors"].append({"code": "CHECKER_FAILED", "returncode": completed.returncode})
    elif not all(layer.get("ok") for layer in result["layers"].values()):
        result["status"] = "FAIL"
        result["errors"].append({"code": "LAYER_EVIDENCE_INCOMPLETE", "message": "L1/L2/L3 evidence is incomplete"})
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--checker")
    args = parser.parse_args(argv)
    result = evaluate(args.project_root, checker=args.checker)
    out = Path(args.output_json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(out), "status": result["status"], "required_units": len(result["required_units"])}, ensure_ascii=False))
    return 0 if result["status"] in {"PASS", "NOT_REQUIRED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
