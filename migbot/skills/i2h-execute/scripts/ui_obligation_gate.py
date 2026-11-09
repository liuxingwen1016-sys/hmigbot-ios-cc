"""Fail-closed static checks for source UI obligations.

The converter prompt carries source facts into each delivery unit, but a
prompt-only requirement can still be dropped during generation.  This gate
checks the generated ArkUI file against the small set of high-signal facts
that are cheap to verify without a device.
"""
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Any


_SYMBOL_SUBSTITUTES = frozenset("★☆✓→+−☼◔↗")
_SYMBOL_FIDELITY_MARKER = re.compile(r"symbol_fidelity\s*:\s*approved\b[^\n]*\basset\s*=", re.IGNORECASE)
_PRESENTATION_FALLBACK_KEYS = (
    "owner",
    "state",
    "scrim",
    "corner",
    "detent",
    "dismissal",
    "safe_area",
)


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _scroll_body_ranges(source: str) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    for match in re.finditer(r"\bScroll\s*\([^\n]*\)\s*\{", source):
        opening = source.find("{", match.start())
        depth = 0
        for index in range(opening, len(source)):
            if source[index] == "{":
                depth += 1
            elif source[index] == "}":
                depth -= 1
                if depth == 0:
                    ranges.append((opening, index + 1))
                    break
    return ranges


def _inside_ranges(index: int, ranges: list[tuple[int, int]]) -> bool:
    return any(start <= index < end for start, end in ranges)


def _has_id(source: str, value: str) -> bool:
    # Accessibility identifiers can be emitted as ArkUI ``id`` modifiers or
    # as the shared actionID field used by the generated interaction helpers.
    if "\\(" in value:
        value = value.split("\\(", 1)[0]
    escaped = re.escape(value)
    return bool(
        re.search(rf"\.id\(\s*['\"]{escaped}['\"]", source)
        or re.search(rf"actionID\s*:\s*['\"]{escaped}['\"]", source)
        or (value and re.search(rf"['\"]{escaped}['\"]", source))
    )


def _row_value(row: Any, key: str) -> Any:
    """Read obligation rows emitted by both old and current spec writers.

    Early i2h-spec reports represented picker labels as plain strings.  The
    richer schema uses objects so it can carry a source anchor and control
    identifier alongside the label.  The execute gate must accept both forms
    because old approved inventories remain valid inputs.
    """
    if isinstance(row, dict):
        return row.get(key)
    if key == "label" and isinstance(row, str):
        return row
    return None


def _contains_numeric_literal(source: str, expected: Any) -> bool:
    """Match numeric source literals by value, allowing ``120``/``120.0``."""
    try:
        expected_value = float(expected)
    except (TypeError, ValueError):
        return False
    for match in re.finditer(r"(?<![\w.])[-+]?(?:\d+(?:\.\d+)?)(?![\w.])", source):
        try:
            if math.isclose(float(match.group(0)), expected_value, rel_tol=0.0, abs_tol=1e-9):
                return True
        except ValueError:
            continue
    return False


def _presentation_rows(unit: dict[str, Any]) -> list[dict[str, Any]]:
    """Return source modifiers owned by this generated host unit.

    A destination unit sourced from ``.sheet { DestinationView() }`` is not
    itself the owner of the modal binding.  The host declaration's
    ``source_obligations.presentations`` rows are therefore the authoritative
    rows for this gate.
    """
    obligations = unit.get("source_obligations") or {}
    rows = obligations.get("presentations", []) if isinstance(obligations, dict) else []
    return [row for row in rows if isinstance(row, dict)]


def _has_presentation_fallback(source: str) -> bool:
    """Check the explicit, reviewable custom-overlay contract.

    Native ``bindSheet``/``bindContentCover`` is preferred.  A custom overlay
    is accepted only when one bounded marker declares the owner, state,
    scrim, corner/detent geometry, dismissal path and safe-area responsibility.
    This prevents an arbitrary ``pageKey`` overlay from silently replacing a
    source presentation while keeping valid API-compatible fallbacks possible.
    """
    marker = re.search(r"presentation_fallback\s*[:=]", source, flags=re.IGNORECASE)
    if not marker:
        return False
    window = source[marker.start(): marker.start() + 1200]
    return all(re.search(rf"\b{re.escape(key)}\s*[:=]", window, flags=re.IGNORECASE) for key in _PRESENTATION_FALLBACK_KEYS)


def _check_presentation_fidelity(source: str, unit: dict[str, Any], relative: str) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    unit_id = str(unit.get("unit_id", ""))
    for row in _presentation_rows(unit):
        kind = str(row.get("kind", ""))
        if kind not in {"sheet", "full_screen_cover"}:
            continue
        binding = "bindSheet" if kind == "sheet" else "bindContentCover"
        if re.search(rf"\b{binding}\s*(?:<|\(|=)", source):
            continue
        if _has_presentation_fallback(source):
            continue
        errors.append({
            "code": "presentation_binding_missing",
            "unit_id": unit_id,
            "detail": f"{relative}: expected {binding} or a complete presentation_fallback marker",
        })
    return errors


def _check_symbol_fidelity(source: str, unit: dict[str, Any], relative: str) -> list[dict[str, str]]:
    """Reject isolated Unicode/emoji glyphs used as visual icon substitutes."""
    if _SYMBOL_FIDELITY_MARKER.search(source):
        return []
    errors: list[dict[str, str]] = []
    unit_id = str(unit.get("unit_id", ""))
    # Restrict detection to string literals.  This avoids treating arithmetic
    # plus/minus or operators in normal ArkTS expressions as visual glyphs.
    for match in re.finditer(r"(['\"])(?P<value>(?:\\.|(?!\1).)*)\1", source, flags=re.DOTALL):
        value = match.group("value")
        hits = [symbol for symbol in _SYMBOL_SUBSTITUTES if symbol in value]
        # '+' and '−' are common in ordinary copy, so only reject them when
        # they are the whole literal.  The other glyphs are icon-shaped and
        # are rejected whenever they appear in a literal.
        hits = [symbol for symbol in hits if symbol not in {"+", "−"} or value.strip() == symbol]
        if not hits:
            continue
        for symbol in sorted(set(hits)):
            errors.append({
                "code": "unicode_symbol_substitute",
                "unit_id": unit_id,
                "detail": f"{relative}: literal {symbol!r} requires a mapped asset/SF Symbol or symbol_fidelity approval",
            })
    return errors


def _check_unit(root: Path, unit: dict[str, Any]) -> list[dict[str, str]]:
    output = unit.get("output") or {}
    relative = output.get("file")
    obligations = unit.get("source_obligations") or {}
    if not isinstance(relative, str):
        return []
    if not isinstance(obligations, dict):
        obligations = {}
    path = root / relative
    if not path.is_file():
        return [{"code": "output_missing", "unit_id": unit.get("unit_id", ""), "detail": relative}]
    source = path.read_text(encoding="utf-8")
    errors: list[dict[str, str]] = []
    unit_id = str(unit.get("unit_id", ""))

    ids = [str(row.get("value")) for row in obligations.get("accessibility_identifiers", []) if row.get("value")]
    ids.extend(str(value) for value in obligations.get("primary_action_ids", []) if value)
    for value in ids:
        if not _has_id(source, value):
            errors.append({"code": "action_id_missing", "unit_id": unit_id, "detail": value})

    if obligations.get("fixed_bottom_action_required"):
        ranges = _scroll_body_ranges(source)
        for value in obligations.get("primary_action_ids", []):
            match = re.search(
                rf"(?:\.id\(\s*['\"]{re.escape(str(value))}['\"]|actionID\s*:\s*['\"]{re.escape(str(value))}['\"])",
                source,
            )
            if match and _inside_ranges(match.start(), ranges):
                errors.append({"code": "fixed_action_inside_scroll", "unit_id": unit_id, "detail": str(value)})
        if not re.search(r"\b(?:PrimaryButton|Button)\s*\(", source):
            errors.append({"code": "fixed_action_control_missing", "unit_id": unit_id, "detail": relative})

    if obligations.get("compact_picker_rows_required"):
        labels = [
            str(label)
            for row in obligations.get("form_picker_labels", [])
            if (label := _row_value(row, "label"))
        ]
        picker_count = len(re.findall(r"\bSelect\s*\(", source))
        if picker_count < len(labels):
            errors.append({"code": "compact_picker_missing", "unit_id": unit_id, "detail": f"expected {len(labels)} Select controls"})
        for label in labels:
            if label not in source:
                errors.append({"code": "picker_label_missing", "unit_id": unit_id, "detail": label})
        if labels and "TagPill" in source:
            errors.append({"code": "picker_chip_substitution", "unit_id": unit_id, "detail": relative})

    if obligations.get("searchable") and obligations.get("searchable_placement") == "toolbar":
        if re.search(r"\bTextInput\s*\(", source):
            errors.append({"code": "toolbar_search_inline_input", "unit_id": unit_id, "detail": relative})
        # ArkUI Search is still an inline control unless the generated page
        # gives it an explicit toolbar host or an expansion/focus state.  A
        # prompt-only rule previously let a permanent Search() push the first
        # screen down even though the iOS searchable modifier was toolbar
        # collapsed on initial render.
        if re.search(r"\bSearch\s*\(", source) and not re.search(
            r"\b(?:Toolbar|toolbar)\b|\b(?:searchExpanded|showSearch|searchVisible|isSearchExpanded)\b",
            source,
        ):
            errors.append({"code": "toolbar_search_inline_input", "unit_id": unit_id, "detail": relative})
        if not re.search(r"search|Search|toolbar|Toolbar", source):
            errors.append({"code": "toolbar_search_missing", "unit_id": unit_id, "detail": relative})

    chart = obligations.get("chart")
    if isinstance(chart, dict) and chart:
        has_line = re.search(r"\b(?:Line|line|drawLine)\b", source)
        has_point = re.search(r"\b(?:Point|point|drawCircle)\b", source)
        if not (has_line and has_point):
            errors.append({"code": "chart_line_points_missing", "unit_id": unit_id, "detail": relative})
        if chart.get("height") is not None and not _contains_numeric_literal(source, chart["height"]):
            errors.append({"code": "chart_height_missing", "unit_id": unit_id, "detail": str(chart["height"])})
    errors.extend(_check_presentation_fidelity(source, unit, relative))
    errors.extend(_check_symbol_fidelity(source, unit, relative))
    return errors


def evaluate(root: Path | str, inventory: Path | str) -> dict[str, Any]:
    root = Path(root).resolve()
    inventory_path = Path(inventory)
    if not inventory_path.is_absolute():
        inventory_path = root / inventory_path
    data = _read(inventory_path)
    errors: list[dict[str, str]] = []
    for unit in data.get("units", []):
        if isinstance(unit, dict):
            errors.extend(_check_unit(root, unit))
    return {
        "schema_version": 1,
        "gate": "i2h-execute.ui-obligations",
        "status": "PASS" if not errors else "FAIL",
        "inventory": str(inventory_path),
        "checked_units": len(data.get("units", [])),
        "errors": errors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--inventory", default="spec/baseline/ui-delivery-approved.json")
    parser.add_argument("--output-json")
    args = parser.parse_args(argv)
    result = evaluate(args.project_root, args.inventory)
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output_json:
        Path(args.output_json).write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
