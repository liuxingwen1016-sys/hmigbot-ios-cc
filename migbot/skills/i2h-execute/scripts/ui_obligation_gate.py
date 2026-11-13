"""Fail-closed static checks for source UI obligations.

The converter prompt carries source facts into each delivery unit, but a
prompt-only requirement can still be dropped during generation.  This gate
checks the generated ArkUI file against the small set of high-signal facts
that are cheap to verify without a device.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any


_SYMBOL_SUBSTITUTES = frozenset("★☆✓→+−☼◔↗")
_SYMBOL_FIDELITY_MARKER = re.compile(r"symbol_fidelity\s*:\s*approved\b[^\n]*\basset\s*=", re.IGNORECASE)
_ARKTS_TRIVIA = re.compile(
    r"""(?P<comment>//[^\r\n]*|/\*.*?\*/)|(?P<literal>"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`)""",
    flags=re.DOTALL,
)
_GENERIC_COUNT = re.compile(r"\basync\s+count\s*\(([^)]*\btable\w*\b[^)]*)\)\s*(?::\s*[^{};]+)?\s*\{")
_ID_PROJECTION = re.compile(r"""\.query(?:Sync)?\s*\([^;]*?,\s*\[\s*(['"])id\1\s*\]\s*\)""")
_BIND_SHEET = re.compile(r"\.\s*bindSheet\s*\(")
_MODIFIER = re.compile(r"\s*\.\s*(\w+)\s*\(")
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


def _check_style_fidelity(root: Path, generated_sources: list[str]) -> list[dict[str, str]]:
    """Keep high-signal iOS geometry and floating chrome from degrading silently."""
    receipt_path = root / "spec/.i2h/target-input.json"
    receipt = _read(receipt_path) if receipt_path.is_file() else {}
    expected = receipt.get("style_triggers_sha256")
    path = root / "spec/ref/ios-style-triggers.json"
    try:
        content = path.read_bytes()
        data = json.loads(content.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        if not expected:
            return []
        return [{"code": "style_trigger_evidence_missing", "unit_id": "style.evidence",
                 "detail": "the standard source scan recorded style evidence, but it cannot be read"}]
    if expected and (
        not isinstance(data, dict)
        or hashlib.sha256(content).hexdigest() != expected
        or data.get("target_input_sha256") != receipt.get("target_input_sha256")
    ):
        return [{"code": "style_trigger_evidence_mismatch", "unit_id": "style.evidence",
                 "detail": "style evidence no longer matches the standard source scan; rerun the scan"}]
    triggers = data.get("triggers", []) if isinstance(data, dict) else []
    trigger_ids = {item.get("trigger_id") for item in triggers if isinstance(item, dict)}
    if not trigger_ids.intersection({"floating_tabbar", "custom_shape_geometry"}):
        return []
    code = [_mask_arkts_trivia(source, keep_literals=False) for source in generated_sources]
    errors: list[dict[str, str]] = []
    if "floating_tabbar" in trigger_ids:
        uses_tabs = any(re.search(r"\bTabs\s*\(", source) for source in code)
        has_floating_host = any(
            re.search(r"\.\s*barFloatingStyle\s*\(", source)
            or (re.search(r"\b(?:floatingTabBar|customTabBar)\s*\(", source, re.IGNORECASE)
                and re.search(r"\.\s*(?:borderRadius|shadow)\s*\(", source)
                and re.search(r"\.\s*(?:position|offset|align)\s*\(", source))
            for source in code
        )
        if uses_tabs and not has_floating_host:
            errors.append({
                "code": "floating_tabbar_native_only",
                "unit_id": "style.floating_tabbar",
                "detail": "source floating TabView requires barFloatingStyle or an explicitly positioned floating/custom tab bar",
            })
    if "custom_shape_geometry" in trigger_ids:
        bag_hosts = [source for source in code if re.search(r"\b(?:BeanBag|BagShape|bagWidth|bagHeight)\b", source)]
        if bag_hosts and not any(re.search(r"\b(?:Path|Canvas|Shape|drawPath|bezier)\s*\(", source) for source in bag_hosts):
            errors.append({
                "code": "custom_shape_geometry_missing",
                "unit_id": "style.custom_shape_geometry",
                "detail": "source custom Shape/Path must remain a target Path/Canvas/Shape, not a rounded rectangle placeholder",
            })
    return errors


def _mask_arkts_trivia(source: str, keep_literals: bool) -> str:
    return _ARKTS_TRIVIA.sub(
        lambda match: match[0] if keep_literals and match.lastgroup == "literal"
        else re.sub(r"[^\r\n]", " ", match[0]),
        source,
    )


def _closing_delimiter(code: str, start: int, opening: str, closing: str) -> int | None:
    depth = 1
    for index in range(start, len(code)):
        depth += (code[index] == opening) - (code[index] == closing)
        if depth == 0:
            return index
    return None


def _has_duplicate_sheet_binding(source: str) -> bool:
    if source.count("bindSheet") < 2:
        return False
    code = _mask_arkts_trivia(source, keep_literals=False)
    for binding in _BIND_SHEET.finditer(code):
        end = _closing_delimiter(code, binding.end(), "(", ")")
        while end is not None:
            modifier = _MODIFIER.match(code, end + 1)
            if not modifier:
                break
            if modifier[1] == "bindSheet":
                return True
            end = _closing_delimiter(code, modifier.end(), "(", ")")
    return False


def _count_assumes_id(source: str, code: str) -> bool:
    for method in _GENERIC_COUNT.finditer(code):
        end = _closing_delimiter(code, method.end(), "{", "}")
        if end is None:
            continue
        body = source[method.end():end]
        if _ID_PROJECTION.search(body):
            return True
        parameters = source[method.start(1):method.end(1)]
        default_id = re.search(r"""\b(\w+)\s*(?::\s*string)?\s*=\s*(['"])id\2""", parameters)
        if default_id and re.search(
            rf"\.query(?:Sync)?\s*\([^;]*?,\s*\[\s*{re.escape(default_id[1])}\s*\]\s*\)", body
        ):
            return True
    return False


def _unobserved_editor_fields(sources: list[str], model_name: str, fields: str) -> set[str]:
    model_name = re.escape(model_name)
    definition = re.compile(rf"(?P<observed>@ObservedV2\s*)?(?:export\s+)?class\s+{model_name}\s*\{{")
    model = next(((source, match) for source in sources if (match := definition.search(source))), None)
    if model is None:
        return set()
    source, match = model
    end = _closing_delimiter(source, match.end(), "{", "}")
    traced = set()
    if match["observed"] and end is not None:
        traced = set(re.findall(rf"@Trace\s+({fields})\b", source[match.end():end]))
    unobserved: set[str] = set()
    for source in sources:
        for owner in re.findall(rf"@Local\s+(?:private\s+)?(\w+)\s*:\s*{model_name}\b", source):
            mutation = rf"\bthis\.{re.escape(owner)}\.({fields})\s*(?:\+\+|--|[+\-*/]=|=(?!=))"
            unobserved.update(set(re.findall(mutation, source)) - traced)
    return unobserved


def _check_editor_mutation(generated_sources: list[str]) -> list[dict[str, str]]:
    sources = [_mask_arkts_trivia(source, keep_literals=False) for source in generated_sources
               if "RecipeValues" in source or "TastingValues" in source]
    issues = []
    for editor, model_name, fields in (
        ("recipe", "RecipeValues", "dose|ratio|temperature"),
        ("tasting", "TastingValues", "rating|acidity|sweetness|body|tags|note"),
    ):
        unobserved = _unobserved_editor_fields(sources, model_name, fields)
        if unobserved:
            issues.append({
                "code": f"unobserved_{editor}_value_mutation", "unit_id": f"runtime.{editor}",
                "detail": f"@Local {editor} values mutate untracked fields {', '.join(sorted(unobserved))}; replace the value or observe those fields",
            })
    return issues


def _check_packaged_image_input(generated_sources: list[str]) -> list[dict[str, str]]:
    for source in generated_sources:
        if "getRawFd" not in source or "createImageSource" not in source:
            continue
        code = _mask_arkts_trivia(source, keep_literals=False)
        descriptors = re.findall(r"\b(\w+)\s*(?::[^=;\n]+)?\s*=\s*(?:await\s+)?(?:[\w.]+\.)?getRawFd\s*\(", code)
        if any(re.search(rf"\bcreateImageSource\s*\(\s*{re.escape(name)}\s*\.\s*fd\b", code)
               for name in descriptors):
            return [{
                "code": "rawfile_image_descriptor_loses_offset", "unit_id": "runtime.image",
                "detail": "pass the complete RawFileDescriptor or exact rawfile bytes to createImageSource",
            }]
    return []


def _fresh_database_duplicate_columns(source: str, code: str) -> set[str]:
    """Recognize two adjacent, unconditional steps on a fresh database."""
    issues: set[str] = set()
    for initial in re.finditer(r"\bif\s*\(\s*(\w+)\s*<\s*1\s*\)\s*\{", code):
        first_end = _closing_delimiter(code, initial.end(), "{", "}")
        if first_end is None:
            continue
        version = re.escape(initial[1])
        first = code[initial.end():first_end]
        if not re.search(rf"\b{version}\s*=\s*1\s*;?\s*$", first):
            continue
        following = re.match(rf"\s*if\s*\(\s*{version}\s*<\s*(?:[2-9]|[1-9]\d+)\s*\)\s*\{{", code[first_end + 1:])
        if following is None:
            continue
        next_start = first_end + 1 + following.end()
        next_end = _closing_delimiter(code, next_start, "{", "}")
        if next_end is None or re.search(r"\b(?:if|switch|return|throw)\b|[{}?]", first + code[next_start:next_end]):
            continue
        created = dict(re.findall(
            r"\.executesql\s*\(\s*['\"`]\s*create\s+table\s+if\s+not\s+exists\s+(\w+)\s*\(([^;]+?)\)\s*['\"`]\s*\)",
            source[initial.end():first_end].lower(),
        ))
        for table, column in re.findall(
            r"\.executesql\s*\(\s*['\"`]\s*alter\s+table\s+(\w+)\s+add\s+(?:column\s+)?(\w+)\s+",
            source[next_start:next_end].lower(),
        ):
            if table in created and re.search(rf"(?:^|,)\s*{re.escape(column)}\s+", created[table]):
                issues.add(f"{table}.{column}")
    return issues


def _check_nav_destination_hosts(sources: list[str]) -> list[dict[str, str]]:
    """Catch a page emitted bare from a named Navigation destination builder."""
    masked = [_mask_arkts_trivia(source, keep_literals=False) for source in sources]
    components: dict[str, str] = {}
    for code in masked:
        for definition in re.finditer(r"\bstruct\s+(\w+)\s*\{", code):
            end = _closing_delimiter(code, definition.end(), "{", "}")
            if end is not None:
                components[definition[1]] = code[definition.end():end]
    missing: set[tuple[str, str]] = set()
    for code in masked:
        for builder in re.findall(r"\.navDestination\(\s*this\.(\w+)\s*\)", code):
            definition = re.search(rf"@Builder\s+(?:private\s+)?{re.escape(builder)}\s*\([^)]*\)\s*\{{", code)
            if definition is None:
                continue
            end = _closing_delimiter(code, definition.end(), "{", "}")
            if end is None:
                continue
            bare = re.fullmatch(r"\s*if\s*\([^)]*\)\s*\{\s*([A-Z]\w*View)\s*\(\s*\)\s*\}\s*", code[definition.end():end])
            if bare is None or bare[1] not in components:
                continue
            if not re.search(r"\bNavDestination\s*\(", components[bare[1]]):
                missing.add((builder, bare[1]))
    return [{
        "code": "navigation_destination_host_missing",
        "unit_id": "runtime.navigation",
        "detail": f"{builder} emits {page} without a NavDestination host",
    } for builder, page in sorted(missing)]


def _check_state_and_persistence_contract(generated_sources: list[str]) -> list[dict[str, str]]:
    """Catch high-signal cross-platform runtime traps before a HAP is accepted."""
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
    for source in generated_sources:
        if _has_duplicate_sheet_binding(source):
            errors.append({
                "code": "multiple_sheets_on_same_host",
                "unit_id": "runtime.presentation",
                "detail": "a component modifier chain contains multiple bindSheet calls; mount each sheet on a distinct host",
            })
        if "deliveryTime" in source and "notificationManager" in source:
            code = _mask_arkts_trivia(source, keep_literals=False)
            if (re.search(r"\bnotificationManager\s*\.\s*publish\s*\(", code)
                and re.search(r"\bdeliveryTime\s*:\s*[\w.\s]*\b(?:plannedEndAt|scheduledAt|triggerAt|dueAt)\b", code)):
                errors.append({
                    "code": "notification_deadline_not_scheduled",
                    "unit_id": "runtime.notification",
                    "detail": "NotificationRequest.deliveryTime is generated by the system; use a scheduled reminder for a future deadline",
                })
        if "relationalStore" not in source:
            continue
        source = _mask_arkts_trivia(source, keep_literals=True)
        if not re.search(r"\bCREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\b", source, flags=re.IGNORECASE):
            continue
        code = _mask_arkts_trivia(source, keep_literals=False)
        if _count_assumes_id(source, code):
            errors.append({
                "code": "database_count_assumes_id",
                "unit_id": "runtime.database",
                "detail": "generic table count queries a hard-coded id column; metadata tables may use key or another primary key",
            })
        duplicate_columns = _fresh_database_duplicate_columns(source, code)
        if duplicate_columns:
            errors.append({
                "code": "database_fresh_column_added_twice",
                "unit_id": "runtime.database",
                "detail": "fresh schema creates and then unconditionally adds the same columns: " + ", ".join(sorted(duplicate_columns)),
            })
        migration_sql = re.search(r"""['"`]\s*(?:ALTER\s+TABLE\b|PRAGMA\s+user_version\s*=)""", source, re.IGNORECASE)
        version_write = re.search(r"\.version\s*=(?!=|>)", code)
        if not migration_sql and not version_write:
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

    runner_ids = obligations.get("runner_action_ids", [])
    if not isinstance(runner_ids, list) or any(not isinstance(value, str) or not value for value in runner_ids):
        errors.append({"code": "runner_action_ids_invalid", "unit_id": unit_id,
                       "detail": "runner_action_ids must list stable target control IDs"})
    elif runner_ids:
        code = _mask_arkts_trivia(source, keep_literals=False)
        modifiers = list(re.finditer(r"\.\s*id\s*\(", code))
        for value in dict.fromkeys(runner_ids):
            literal = re.compile(rf"\s*(['\"]){re.escape(value)}\1\s*\)")
            if not any(literal.match(source, modifier.end()) for modifier in modifiers):
                errors.append({"code": "runner_action_id_missing", "unit_id": unit_id, "detail": value})

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


def _configured_sdk_catalog(root: Path) -> Path | None:
    try:
        config = _read(root / ".migbot/config.json")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    hdc = config.get("hdc") if isinstance(config, dict) else None
    if not isinstance(hdc, str) or not Path(hdc).is_absolute():
        return None
    catalog = Path(hdc).resolve().with_name("id_defined.json")
    return catalog if catalog.is_file() else None


def _check_sdk_symbols(sources: list[str], catalog: Path | None) -> dict[str, Any]:
    if catalog is None:
        return {"status": "NOT_CHECKED", "unresolved": []}
    rows = _read(catalog).get("record", [])
    symbols = {row.get("name") for row in rows if isinstance(row, dict) and row.get("type") == "symbol"}
    if not symbols:
        raise ValueError(f"no SDK symbols in {catalog}")
    required = set()
    pattern = re.compile(r"\s*(['\"])sys\.symbol\.([\w]+)\1\s*\)")
    for source in sources:
        if "sys.symbol." not in source:
            continue
        code = _mask_arkts_trivia(source, keep_literals=False)
        for call in re.finditer(r"\$r\s*\(", code):
            match = pattern.match(source, call.end())
            if match:
                required.add(match[2])
    missing = sorted(required - symbols)
    return {"status": "FAIL" if missing else "PASS", "catalog": str(catalog), "unresolved": missing}


def evaluate(root: Path | str, inventory: Path | str, *, sdk_symbol_catalog: Path | None = None) -> dict[str, Any]:
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
    errors.extend(_check_nav_destination_hosts(generated_sources))
    errors.extend(_check_editor_mutation(generated_sources))
    errors.extend(_check_packaged_image_input(generated_sources))
    sdk_symbols = _check_sdk_symbols(generated_sources, sdk_symbol_catalog or _configured_sdk_catalog(root))
    if sdk_symbols["status"] == "FAIL":
        errors.append({
            "code": "sdk_symbols_unresolved", "unit_id": "runtime.symbols",
            "detail": "symbols absent from the target SDK catalog: " + ", ".join(sdk_symbols["unresolved"]),
        })
    return {
        "schema_version": 1,
        "gate": "i2h-execute.ui-obligations",
        "status": "PASS" if not errors else "FAIL",
        "inventory": str(inventory_path),
        "checked_units": len(data.get("units", [])),
        "sdk_symbols": sdk_symbols,
        "errors": errors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--inventory", default="spec/baseline/ui-delivery-approved.json")
    parser.add_argument("--output-json")
    parser.add_argument("--sdk-symbol-catalog", type=Path)
    args = parser.parse_args(argv)
    result = evaluate(args.project_root, args.inventory, sdk_symbol_catalog=args.sdk_symbol_catalog)
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output_json:
        Path(args.output_json).write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
