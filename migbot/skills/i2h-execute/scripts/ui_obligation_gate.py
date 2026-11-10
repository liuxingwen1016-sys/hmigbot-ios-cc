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


def _check_presentation_fidelity(
    source: str,
    unit: dict[str, Any],
    relative: str,
    generated_sources=None,
) -> list[dict[str, str]]:
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
        # A routed root often delegates modal ownership to Index/RootHost
        # instead of the page file named by the source declaration.  Accept a
        # single centralized binding or complete fallback marker in the
        # generated surface, while still failing when the project has no
        # implementation for the declared presentation kind.
        if generated_sources and any(
            re.search(rf"\b{binding}\s*(?:<|\(|=)", candidate)
            or _has_presentation_fallback(candidate)
            for candidate in generated_sources
        ):
            continue
        errors.append({
            "code": "presentation_binding_missing",
            "unit_id": unit_id,
            "detail": f"{relative}: expected {binding} or a complete presentation_fallback marker",
        })
    return errors


def _check_presentation_lifecycle(
    source: str,
    unit: dict[str, Any],
    relative: str,
    generated_sources=None,
) -> list[dict[str, str]]:
    """Reject eager sheet-to-cover transitions that ArkUI can drop."""
    rows = _presentation_rows(unit)
    kinds = {str(row.get("kind", "")) for row in rows}
    if not {"sheet", "full_screen_cover"}.issubset(kinds):
        return []
    combined = "\n".join([source, *(generated_sources or [])])
    if not re.search(r"\bonDisappear\s*[:=(]|\bonDismiss\b", combined):
        return [{
            "code": "presentation_transition_dismissal_missing",
            "unit_id": str(unit.get("unit_id", "")),
            "detail": f"{relative}: sheet→full-screen transition requires an explicit post-dismiss callback",
        }]
    eager = re.search(
        r"(?:close(?:Recipe|Sheet|Modal)|dismiss(?:Recipe|Sheet|Modal))\s*\([^)]*\)\s*(?::\s*[\w<>,\[\] |]+)?\s*\{(?P<body>.*?)\}",
        combined,
        flags=re.DOTALL,
    )
    if eager and re.search(r"\b(?:showBrew|showCover|showContentCover|fullScreen)\s*=\s*true\b", eager.group("body")):
        return [{
            "code": "presentation_transition_eager",
            "unit_id": str(unit.get("unit_id", "")),
            "detail": f"{relative}: close handler opens full-screen content before sheet dismissal; move it to the host onDisappear callback",
        }]
    return []


def _check_foreground_safearea(
    source: str,
    unit: dict[str, Any],
    relative: str,
    generated_sources=None,
) -> list[dict[str, str]]:
    """Require page-level insets when the root deliberately expands edge-to-edge."""
    combined = "\n".join([source, *(generated_sources or [])])
    if not re.search(r"\.expandSafeArea\s*\(", combined):
        return []
    top_bar_labels = ("偏好设置", "添加咖啡豆", "豆档案", "风味手记", "冲煮台")
    if not any(label in source for label in top_bar_labels):
        return []
    if re.search(r"safeAreaPadding|windowTopPadding|WindowModel|ImmersiveScaffold", source):
        return []
    return [{
        "code": "foreground_safearea_missing",
        "unit_id": str(unit.get("unit_id", "")),
        "detail": f"{relative}: root expands into system bars but this interactive top bar has no page-level safe-area inset",
    }]


def _style_trigger_ids(root: Path) -> set[str]:
    path = root / "spec/ref/ios-style-triggers.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return set()
    triggers = data.get("triggers", []) if isinstance(data, dict) else []
    return {str(item.get("trigger_id")) for item in triggers if isinstance(item, dict) and item.get("trigger_id")}


def _check_style_fidelity(root: Path, generated_sources: list[str]) -> list[dict[str, str]]:
    """Keep high-signal iOS geometry and floating chrome from degrading silently."""
    trigger_ids = _style_trigger_ids(root)
    errors: list[dict[str, str]] = []
    if "floating_tabbar" in trigger_ids:
        tab_hosts = [source for source in generated_sources if re.search(r"\bTabs\s*\(", source)]
        has_floating_host = any(
            re.search(r"\b(?:borderRadius|shadow)\s*\(", source)
            and re.search(r"\b(?:position|offset|floating|customTab|tabBar)\b", source)
            for source in tab_hosts
        )
        if tab_hosts and not has_floating_host:
            errors.append({
                "code": "floating_tabbar_native_only",
                "unit_id": "style.floating_tabbar",
                "detail": "source floating TabView requires a floating/custom tab host with radius/shadow geometry",
            })
    if "custom_shape_geometry" in trigger_ids:
        bag_hosts = [source for source in generated_sources if re.search(r"\b(?:BeanBag|BagShape|bagWidth|bagHeight)\b", source)]
        if bag_hosts and not any(re.search(r"\b(?:Path|Canvas|Shape|drawPath|bezier)\b", source) for source in bag_hosts):
            errors.append({
                "code": "custom_shape_geometry_missing",
                "unit_id": "style.custom_shape_geometry",
                "detail": "source custom Shape/Path must remain a target Path/Canvas/Shape, not a rounded rectangle placeholder",
            })
    return errors


def _check_state_and_persistence_contract(generated_sources: list[str]) -> list[dict[str, str]]:
    """Catch two cross-platform runtime traps before a HAP is accepted."""
    errors: list[dict[str, str]] = []
    root_hosts = [source for source in generated_sources if re.search(r"\b(?:struct|class)\s+RootView\b", source)]
    for source in root_hosts:
        if re.search(r"\bprivate\s+(?:readonly\s+)?router\s*:\s*\w+", source) and not re.search(
            r"@(?:Local|State|ObjectLink|Provide|Consume)\s+router\b", source
        ):
            errors.append({
                "code": "observable_state_owner_missing",
                "unit_id": "runtime.RootView",
                "detail": "RootView router state must use an ArkUI observation decorator so route changes invalidate the host",
            })
        for match in re.finditer(r"\.bind(?:Sheet|ContentCover)\(\s*(this\.router\.[^,)]*)", source):
            errors.append({
                "code": "presentation_state_derived_binding",
                "unit_id": "runtime.RootView",
                "detail": f"modal binding uses derived router expression {match.group(1)!r}; bind an observable local/link state instead",
            })
    database_sources = [
        source for source in generated_sources
        if "relationalStore" in source and "CREATE TABLE IF NOT EXISTS" in source
    ]
    for source in database_sources:
        if re.search(r"async\s+count\s*\([^)]*table[^)]*\).*?query\([^\n]*\[\s*['\"]id['\"]\s*\]", source, flags=re.DOTALL):
            errors.append({
                "code": "database_count_assumes_id",
                "unit_id": "runtime.database",
                "detail": "generic table count queries a hard-coded id column; metadata tables may use key or another primary key",
            })
        if not re.search(r"ALTER\s+TABLE|onUpgrade|\bmigrat(?:e|ion)\b|user_version", source, flags=re.IGNORECASE):
            errors.append({
                "code": "database_migration_missing",
                "unit_id": "runtime.database",
                "detail": "relationalStore schema is created but no upgrade/migration path is declared",
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


def _check_unit(root: Path, unit: dict[str, Any], generated_sources=None) -> list[dict[str, str]]:
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
    errors.extend(_check_presentation_fidelity(source, unit, relative, generated_sources))
    errors.extend(_check_presentation_lifecycle(source, unit, relative, generated_sources))
    errors.extend(_check_foreground_safearea(source, unit, relative, generated_sources))
    errors.extend(_check_symbol_fidelity(source, unit, relative))
    return errors


def evaluate(root: Path | str, inventory: Path | str) -> dict[str, Any]:
    root = Path(root).resolve()
    inventory_path = Path(inventory)
    if not inventory_path.is_absolute():
        inventory_path = root / inventory_path
    data = _read(inventory_path)
    errors: list[dict[str, str]] = []
    units = [unit for unit in data.get("units", []) if isinstance(unit, dict)]
    generated_sources: list[str] = []
    for unit in units:
        relative = (unit.get("output") or {}).get("file")
        if isinstance(relative, str):
            path = root / relative
            if path.is_file():
                generated_sources.append(path.read_text(encoding="utf-8"))
    # The delivery inventory normally lists page outputs, while modal
    # ownership may live in an unlisted entry/root host.  Include generated
    # ArkTS files under the app source tree so centralized bindings are still
    # verified without requiring an inventory rewrite.
    known_paths = {
        (unit.get("output") or {}).get("file")
        for unit in units
        if isinstance((unit.get("output") or {}).get("file"), str)
    }
    for path in sorted((root / "entry/src/main/ets").rglob("*.ets")):
        relative = path.relative_to(root).as_posix()
        if relative in known_paths:
            continue
        try:
            generated_sources.append(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            continue
    for unit in units:
        if isinstance(unit, dict):
            errors.extend(_check_unit(root, unit, generated_sources))
    errors.extend(_check_style_fidelity(root, generated_sources))
    errors.extend(_check_state_and_persistence_contract(generated_sources))
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
