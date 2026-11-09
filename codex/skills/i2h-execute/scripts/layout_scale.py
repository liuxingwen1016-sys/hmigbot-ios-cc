#!/usr/bin/env python3
"""Derive an evidence-bound iOS fixed-geometry layout scale.

The result is guidance for the converter. It never rewrites target source and
does not scale typography, dynamic content, safe areas, or percentage layouts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _walk(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _frame_widths(payload: Any) -> list[float]:
    widths: list[float] = []
    for node in _walk(payload):
        frame = node.get("frame")
        if isinstance(frame, dict):
            width_value = frame.get("width")
            height_value = frame.get("height")
        elif isinstance(frame, (list, tuple)) and len(frame) >= 4:
            width_value = frame[2]
            height_value = frame[3]
        else:
            continue
        try:
            width = float(width_value)
            height = float(height_value)
        except (TypeError, ValueError):
            continue
        if width > 0 and height > 0:
            widths.append(width)
    return widths


def derive(source_width_pt: float, target_width_vp: float, source_path: Path | None = None) -> dict[str, Any]:
    if source_width_pt <= 0 or target_width_vp <= 0:
        raise ValueError("source and target widths must be positive")
    scale = target_width_vp / source_width_pt
    if not 0.5 <= scale <= 2.0:
        raise ValueError("derived layout scale is outside the supported range 0.5..2.0")
    result: dict[str, Any] = {
        "schema_version": 1,
        "tool_version": "i2h-layout-scale/1.0",
        "status": "PASS",
        "scope": "ios_fixed_geometry_only",
        "source_reference_width_pt": source_width_pt,
        "target_logical_width_vp": target_width_vp,
        "layout_scale": scale,
        "scale_formula": "target_logical_width_vp / source_reference_width_pt",
        "excluded_from_scaling": [
            "typography",
            "dynamic_content_height",
            "safe_area_and_system_bars",
            "percentage_layout",
            "hit_targets_without_geometry_evidence",
        ],
    }
    if source_path is not None:
        result["source_accessibility_json"] = str(source_path)
        result["source_accessibility_json_sha256"] = _sha256(source_path)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--source-reference-width-pt", type=float)
    source.add_argument("--ios-accessibility-json")
    parser.add_argument("--target-logical-width-vp", type=float, required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    source_path: Path | None = None
    if args.ios_accessibility_json:
        source_path = Path(args.ios_accessibility_json).expanduser().resolve()
        payload = json.loads(source_path.read_text(encoding="utf-8"))
        widths = _frame_widths(payload)
        if not widths:
            raise SystemExit("ERROR: no positive accessibility frames found")
        source_width = max(widths)
    else:
        source_width = args.source_reference_width_pt

    try:
        result = derive(source_width, args.target_logical_width_vp, source_path)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
    output = Path(args.out).expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "status": result["status"], "layout_scale": result["layout_scale"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
