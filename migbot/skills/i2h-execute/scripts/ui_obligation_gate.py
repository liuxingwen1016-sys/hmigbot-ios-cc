"""Fail-closed static checks for source UI obligations.

The converter prompt carries source facts into each delivery unit, but a
prompt-only requirement can still be dropped during generation.  This gate
checks the generated ArkUI file against the small set of high-signal facts
that are cheap to verify without a device.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
import re
from pathlib import Path, PurePosixPath
from typing import Any

from lib.ios_ui_delivery_gate import _code, _component_bodies, _imports, _method, _project_file, _reachable, _renders


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
    root_expands: bool,
) -> list[dict[str, str]]:
    """Require page-level insets when the root deliberately expands edge-to-edge."""
    if not root_expands:
        return []
    top_bar_labels = ("偏好设置", "添加咖啡豆", "豆档案", "风味手记", "冲煮台")
    visible_source = _code(source, keep_strings=True)
    if not any(label in visible_source for label in top_bar_labels):
        return []
    code = _code(source)
    if re.search(r"\.\s*safeAreaPadding\s*\(|\.\s*windowTopPadding\b|\bImmersiveScaffold\s*\(", code):
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


def _check_source_rawfiles(root: Path, sources: dict[Path, str]) -> list[dict[str, str]]:
    """Detect statically named source assets absent from the migrated package inputs."""
    inventory = root / "spec/.i2h/resources-inventory.json"
    if not inventory.is_file():
        return []
    data = _read(inventory)
    assets: dict[str, set[str]] = {}
    for asset in data.get("resources", {}).get("standalone_assets", []):
        if not isinstance(asset, dict) or asset.get("exists") is not True:
            continue
        source = asset.get("path")
        if isinstance(source, str) and re.fullmatch(r"[0-9a-f]{64}", str(asset.get("sha256", ""))):
            assets.setdefault(PurePosixPath(source).name, set()).add(source)
    if not assets:
        return []
    raw_roots = {}
    for path in sources:
        if not path.is_relative_to(root):
            continue
        parts = path.relative_to(root).parts
        for index in range(len(parts) - 2):
            if parts[index:index + 3] == ("src", "main", "ets"):
                raw_roots[path] = root.joinpath(*parts[:index], "src", "main", "resources", "rawfile")
                break
    known_raw_roots = set(raw_roots.values())
    literal = r"""(['"])([^'"\\\r\n]+)\1"""
    constant = re.compile(r"^[ \t]*(?:export\s+)?const\s+([A-Za-z_$][\w$]*)\s*(?::\s*string)?\s*=", re.M)
    call = re.compile(r"\.\s*getRaw(?:FileContent|Fd)(?:Sync)?\s*\(")
    variable_arg = re.compile(r"\s*([A-Za-z_$][\w$]*)\s*[,)]")
    issues = []
    for path, source in sources.items():
        if path not in raw_roots or "getRaw" not in source:
            continue
        code = _mask_arkts_trivia(source, keep_literals=False)
        reads = [(source[match.end():], variable_arg.match(code, match.end())) for match in call.finditer(code)]
        name_counts = Counter(match[1] for _, match in reads if match)
        values = {}
        for declaration in constant.finditer(code):
            name = declaration[1]
            match = re.match(rf"\s*{literal}\s*(?=[;\r\n]|$)", source[declaration.end():])
            if match and name_counts[name] and len(re.findall(rf"\b{re.escape(name)}\b", code)) == name_counts[name] + 1:
                values[name] = match[2]
        for snippet, variable in reads:
            direct = re.match(rf"\s*{literal}\s*[,)]", snippet)
            name = direct[2] if direct else values.get(variable[1]) if variable else None
            if not name:
                continue
            key = PurePosixPath(name)
            if key.is_absolute() or ".." in key.parts or ":" in name or not key.name:
                continue
            matches = assets.get(key.name, set())
            if len(matches) != 1 or any((raw / name).is_file() for raw in known_raw_roots):
                continue
            expected = raw_roots[path] / name
            source_asset = next(iter(matches))
            issues.append({
                "code": "source_rawfile_missing",
                "unit_id": "runtime.resources",
                "detail": (f"{path.relative_to(root).as_posix()}: {source_asset} is read as {name!r}, "
                           f"but {expected.relative_to(root).as_posix()} is absent"),
            })
    return issues


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



def _modifiers_after(code: str, start: int) -> dict[str, str]:
    values = {}
    while match := _MODIFIER.match(code, start):
        end = _closing_delimiter(code, match.end(), "(", ")")
        if end is None:
            break
        values[match[1]] = code[match.end():end].strip()
        start = end + 1
    return values


def _sheet_close_enabled(options: str) -> bool:
    # Inspect only literal, top-level properties. A spread or computed key
    # can override showClose at runtime.
    properties = options[1:-1] + ","
    start = index = 0
    values = []
    delimiters = {"(": ")", "{": "}", "[": "]"}
    while index < len(properties):
        char = properties[index]
        if char in delimiters:
            end = _closing_delimiter(properties, index + 1, char, delimiters[char])
            if end is None:
                return False
            index = end
        elif char == ",":
            property_text = properties[start:index].strip()
            start = index + 1
            if property_text:
                match = re.fullmatch(r"(\w+)\s*:\s*(.*)", property_text, re.S)
                if not match:
                    return False
                if match[1] == "showClose":
                    values.append(match[2])
        index += 1
    return values in ([], ["true"])


def _native_close_sheet_contents(source: str) -> list[tuple[str, set[str]]]:
    code = _mask_arkts_trivia(source, keep_literals=False)
    sheets = []
    for owner, component in _component_bodies(code).items():
        for method in _reachable(component, "build").values():
            for binding in _BIND_SHEET.finditer(method):
                end = _closing_delimiter(method, binding.end(), "(", ")")
                if end is None:
                    continue
                arguments = re.fullmatch(
                    r"\s*this\.\w+\s*,\s*this\.(\w+)\s*\(\s*\)\s*(?:,\s*(\{.*\}))?\s*",
                    method[binding.end():end], re.S,
                )
                if not arguments:
                    continue
                builder, options = arguments.groups()
                if options and not _sheet_close_enabled(options):
                    continue
                contents = "\n".join(_reachable(component, builder).values())
                calls = set(re.findall(r"(?<![\w.$])([A-Z_$][\w$]*)\s*\(", contents))
                if calls and (f"{owner}.{builder}", calls) not in sheets:
                    sheets.append((f"{owner}.{builder}", calls))
    return sheets


def _has_page_close_action(source: str, symbol: str, builder: str) -> bool:
    component = _component_bodies(_mask_arkts_trivia(source, keep_literals=True)).get(symbol, "")
    for method in _reachable(component, builder).values():
        code = _mask_arkts_trivia(method, keep_literals=False)
        controls = re.finditer(
            r"(?<![\w.$])(?:Text|Button)\s*\(\s*(['\"])(?:关闭|取消|Close|Cancel)\1\s*\)",
            method,
        )
        for control in controls:
            if code[control.start()].isspace():
                continue
            action = _modifiers_after(code, control.end()).get("onClick", "")
            if re.fullmatch(
                r"\(\s*\)\s*=>\s*(?:\{\s*)?this\.(?:onClose|onDismiss|closeAll|dismiss)\s*\(\s*\)\s*;?\s*\}?",
                action,
            ):
                return True
    return False


def _check_sheet_close_actions(root: Path, units: list[dict], sources: dict[Path, str]) -> list[dict[str, str]]:
    sheets = [(path, slot, calls) for path, source in sources.items() if "bindSheet" in source
              for slot, calls in _native_close_sheet_contents(source)]
    if not sheets:
        return []
    errors = []
    for unit in units:
        output = unit.get("output") or {}
        symbol, relative = output.get("symbol"), output.get("file")
        if not isinstance(symbol, str) or not isinstance(relative, str):
            continue
        path = root / relative
        source = sources.get(path, "")
        if not _has_page_close_action(source, symbol, output.get("builder") or "build"):
            continue
        for host, slot, calls in sheets:
            names = {symbol} if host == path else _imports(root, sources[host], host, path.resolve(), symbol)
            if calls & names:
                errors.append({
                    "code": "duplicate_sheet_close_action",
                    "unit_id": unit.get("unit_id", ""),
                    "detail": f"{host.relative_to(root)}:{slot} enables the native close button while {symbol} renders its own close action",
                })
    return errors


def _literal_number(value: str, code: str) -> float | None:
    if re.fullmatch(r"\d+(?:\.\d+)?", value):
        return float(value)
    if not re.fullmatch(r"[A-Za-z_]\w*", value):
        return None
    matches = re.findall(
        rf"\bconst\s+{re.escape(value)}(?:\s*:\s*number)?\s*=\s*(\d+(?:\.\d+)?)\s*;",
        code,
    )
    return float(matches[0]) if len(matches) == 1 else None


def _has_rating_symbol_contract(source: str, row: dict) -> bool:
    code = _mask_arkts_trivia(source, keep_literals=False)
    filled, empty = map(re.escape, row["target_symbols"])
    branches = re.compile(
        rf"""\s*[\w.]+\s*>=\s*[\w.]+\s*\?\s*\$r\(\s*(['"])sys\.symbol\.{filled}\1\s*\)
             \s*:\s*\$r\(\s*(['"])sys\.symbol\.{empty}\2\s*\)\s*""",
        re.VERBOSE,
    )
    width, height = row["minimum_button_pt"]
    for button in re.finditer(r"\bButton\s*\(", code):
        options = _closing_delimiter(code, button.end(), "(", ")")
        if options is None or not (block := re.match(r"\s*\{", code[options + 1:])):
            continue
        start = options + 1 + block.end()
        end = _closing_delimiter(code, start, "{", "}")
        if end is None:
            continue
        glyph = re.match(r"\s*SymbolGlyph\s*\(", code[start:end])
        if glyph is None:
            continue
        glyph_args = start + glyph.end()
        glyph_end = _closing_delimiter(code, glyph_args, "(", ")")
        if glyph_end is None or glyph_end >= end or not branches.fullmatch(source[glyph_args:glyph_end]):
            continue
        size = _literal_number(_modifiers_after(code, glyph_end + 1).get("fontSize", ""), code)
        button_modifiers = _modifiers_after(code, end + 1)
        w = _literal_number(button_modifiers.get("width", ""), code)
        h = _literal_number(button_modifiers.get("height", ""), code)
        if size == row["symbol_font_pt"] and w is not None and h is not None and w >= width and h >= height:
            return True
    return False


def _symbol_resolves(row: dict, generated_sources: list[str]) -> bool:
    target = re.escape(row["target_symbol"])
    direct = rf"""\$r\(\s*['"]sys\.symbol\.{target}['"]\s*\)"""
    sf_name = re.escape(row["source_symbol"])
    for candidate in generated_sources:
        candidate_code = _mask_arkts_trivia(candidate, keep_literals=False)
        resolver = re.search(r"\bfunction\s+symbolOf\s*\([^)]*\)[^{]*\{", candidate_code)
        if resolver is None:
            continue
        end = _closing_delimiter(candidate_code, resolver.end(), "{", "}")
        if end is None:
            continue
        body = _mask_arkts_trivia(candidate[resolver.end():end], keep_literals=True)
        if re.search(rf"""\bcase\s+['"]{sf_name}['"]\s*:\s*return\s+{direct}""", body):
            return True
    return False


def _has_tab_symbol_contract(source: str, row: dict, generated_sources: list[str]) -> bool:
    code = _mask_arkts_trivia(source, keep_literals=False)
    label = re.escape(row["label"])
    literal = rf"""(?:'{label}'|"{label}")"""
    target = re.escape(row["target_symbol"])
    direct = rf"""\$r\(\s*['"]sys\.symbol\.{target}['"]\s*\)"""
    sf_name = re.escape(row["source_symbol"])
    mapped = _symbol_resolves(row, generated_sources)
    symbol = rf"(?:{direct}|['\"]{sf_name}['\"])" if mapped else direct
    pair = rf"(?:{literal}\s*,\s*{symbol}|\btext\s*:\s*{literal}\s*,\s*icon\s*:\s*{symbol})"
    visible = _mask_arkts_trivia(source, keep_literals=True)
    for call in re.finditer(r"\b(floatingTabItem|tabBar)\s*\(", code):
        end = _closing_delimiter(code, call.end(), "(", ")")
        leading_index = r"(?:[A-Za-z0-9_]+\s*,\s*)?" if call[1] == "floatingTabItem" else ""
        if end is not None and re.match(rf"\s*\{{?\s*{leading_index}{pair}\s*(?:,|\}}|$)", visible[call.end():end]):
            return True
    return False


def _has_primary_button_symbol_contract(source: str, row: dict, sources: list[str]) -> bool:
    if not _symbol_resolves(row, sources):
        return False
    defaults = []
    for candidate in sources:
        code = _mask_arkts_trivia(candidate, keep_literals=False)
        declaration = re.search(r"\bstruct\s+PrimaryButton\s*\{", code)
        if declaration is None:
            continue
        end = _closing_delimiter(code, declaration.end(), "{", "}")
        if end is None:
            continue
        body_code = code[declaration.end():end]
        if not re.search(r"\bSymbolGlyph\s*\(\s*symbolOf\s*\(\s*this\.trailingSymbol\s*\)\s*\)", body_code):
            continue
        body = _mask_arkts_trivia(candidate[declaration.end():end], keep_literals=True)
        match = re.search(r"""@Param\s+trailingSymbol\s*:\s*string\s*=\s*(['"])([\w.-]+)\1""", body)
        defaults.append(match[2] if match else None)
    if len(defaults) != 1:
        return False

    label = re.escape(row["label"])
    expected = row["source_symbol"]
    code = _mask_arkts_trivia(source, keep_literals=False)
    visible = _mask_arkts_trivia(source, keep_literals=True)
    found = []
    for call in re.finditer(r"\bPrimaryButton\s*\(\s*\{", code):
        end = _closing_delimiter(code, call.end(), "{", "}")
        if end is None:
            continue
        props = visible[call.end():end]
        if not re.match(rf"""\s*title\s*:\s*(?:'{label}'|"{label}")\s*(?=,|$)""", props):
            continue
        override = re.match(r"""\s*title\s*:\s*(['"]).*?\1\s*,\s*trailingSymbol\s*:\s*(['"])([\w.-]+)\2\s*(?=,|$)""", props)
        if override:
            found.append(override[3])
        elif re.search(r"\btrailingSymbol\s*:", props):
            return False
        else:
            found.append(defaults[0])
    return bool(found) and all(symbol == expected for symbol in found)


def _symbol_rows(obligations: Any) -> list[dict]:
    if not isinstance(obligations, dict):
        return []
    return obligations.get("system_symbol_fidelity") or []


def _has_label_symbol_pair(source: str, row: dict) -> bool:
    code = _mask_arkts_trivia(source, keep_literals=False)
    label = re.escape(row["label"])
    target = re.escape(row["target_symbol"])
    expected = {
        "Text": re.compile(rf"""\s*(['"]){label}\1\s*"""),
        "SymbolGlyph": re.compile(rf"""\s*\$r\(\s*(['"])sys\.symbol\.{target}\1\s*\)\s*"""),
    }
    for layout in re.finditer(r"(?<![\w.])(?:Row|Column|Flex|Stack|Button)\s*\(", code):
        end = _closing_delimiter(code, layout.end(), "(", ")")
        if end is None or not (block := re.match(r"\s*\{", code[end + 1:])):
            continue
        start = end + 1 + block.end()
        end = _closing_delimiter(code, start, "{", "}")
        if end is None:
            continue
        found = set()
        depth = 0
        for token in re.compile(r"(?<![\w.])(Text|SymbolGlyph)\s*(?=\()|[(){}\[\]]").finditer(code, start, end):
            if name := token[1]:
                if depth == 0:
                    args_start = token.end() + 1
                    args_end = _closing_delimiter(code, args_start, "(", ")")
                    if args_end is not None and args_end < end and expected[name].fullmatch(source[args_start:args_end]):
                        found.add(name)
            else:
                depth += 1 if token[0] in "({[" else -1
        if found == expected.keys():
            return True
    return False


def check_label_symbols(source: str, unit: dict) -> list[dict[str, str]]:
    rows = [row for row in _symbol_rows(unit.get("source_obligations"))
            if row["role"] == "label" and row.get("target_symbol")]
    if not rows:
        return []
    output = unit.get("output", {})
    components = _component_bodies(_code(source, keep_strings=True))
    if symbol := output.get("symbol"):
        components = {symbol: components.get(symbol, "")}
    builders = [body for component in components.values()
                for body in _reachable(component, output.get("builder", "build")).values()]
    return [
        {"code": "mapped_system_symbol_mismatch", "unit_id": unit["unit_id"],
         "detail": f'Swift line {row["line"]}: {row["label"]} must share a rendered layout with SDK symbol {row["target_symbol"]}'}
        for row in rows if not any(_has_label_symbol_pair(body, row) for body in builders)
    ]


def check_date_formats(source: str, unit: dict) -> list[dict[str, str]]:
    obligations = unit.get("source_obligations")
    rows = obligations.get("date_format_calls") if isinstance(obligations, dict) else None
    if not rows:
        return []
    output = unit.get("output") or {}
    code = _mask_arkts_trivia(source, keep_literals=False)
    component = _component_bodies(code).get(output.get("symbol"), "")
    builders = _reachable(component, output.get("builder") or "build")
    errors = []
    for row in rows:
        # Match the same value in the rendered slot. Renamed fields, wrapper
        # formatters and explicit locale options still require runtime review.
        value = r"\s*\.\s*".join(re.escape(part) for part in row["value_path"].split("."))
        unqualified = rf"new\s+Date\s*\(\s*{value}\s*\)\s*\.\s*toLocaleString\s*\(\s*\)"
        if row["slot"] == "text":
            pattern = rf"(?<![\w.])Text\s*\(\s*{unqualified}\s*\)"
        else:
            pattern = rf"(?<![\w.])SectionHeading\s*\(\s*\{{[^{{}}]*\bsubtitle\s*:\s*{unqualified}\s*(?=[,}}])"
        if any(re.search(pattern, body) for body in builders.values()):
            errors.append({
                "code": "date_format_unqualified_locale",
                "unit_id": unit["unit_id"],
                "detail": (f'Swift line {row["line"]}: {row["value_path"]} specifies date .{row["date_style"]} '
                           f'and time .{row["time_style"]}; the rendered slot uses toLocaleString() defaults'),
            })
    return errors


def _local_clipboard_only(action: str, component: str) -> bool:
    """Recognize closed local handlers. Leave unknown helpers for runtime review."""
    handlers = [action]
    resolved = set()
    allowed_calls = {"catch", "if", "pasteboard.createData", "promptAction.showToast",
                     "hilog.info", "hilog.warn", "hilog.error"}
    clipboard_write = re.compile(
        r"(?<![\w.$])pasteboard\s*\.\s*getSystemPasteboard\s*\(\s*\)\s*\.\s*setData\s*\("
    )
    found_write = False
    while handlers:
        body = handlers.pop()
        body, writes = clipboard_write.subn("=", body)
        found_write |= bool(writes)
        for match in re.finditer(r"(?<![\w$])([A-Za-z_$][\w$]*(?:\s*\.\s*[A-Za-z_$][\w$]*)*)\s*\(", body):
            name = re.sub(r"\s+", "", match[1])
            if name in allowed_calls or name.endswith(".join"):
                continue
            if not name.startswith("this.") or name.count(".") != 1:
                return False
            method = name.removeprefix("this.")
            if method not in resolved:
                target = _method(component, method)
                if target is None:
                    return False
                handlers.append(target)
                resolved.add(method)
    return found_write


def check_share_links(source: str, unit: dict) -> list[dict[str, str]]:
    obligations = unit.get("source_obligations")
    rows = obligations.get("share_link_calls") if isinstance(obligations, dict) else None
    if not rows:
        return []
    output = unit.get("output") or {}
    symbol = output.get("symbol")
    component = _component_bodies(_mask_arkts_trivia(source, keep_literals=True)).get(symbol, "")
    code = _mask_arkts_trivia(component, keep_literals=False)
    errors = []
    for row in rows:
        if not (label := row.get("label")):
            continue
        quoted = rf"(['\"]){re.escape(label)}\1"
        for builder in _reachable(component, output.get("builder") or "build").values():
            masked = _mask_arkts_trivia(builder, keep_literals=False)
            for button in re.finditer(r"(?<![\w.])Button\s*\(", masked):
                end = _closing_delimiter(masked, button.end(), "(", ")")
                if end is None:
                    continue
                has_label = re.match(rf"\s*{quoted}\s*(?=,|$)", builder[button.end():end])
                if content := re.match(r"\s*\{", masked[end + 1:]):
                    start = end + 1 + content.end()
                    end = _closing_delimiter(masked, start, "{", "}")
                    if end is None:
                        continue
                    labels = re.finditer(rf"(?<![\w.])Text\s*\(\s*{quoted}\s*\)", builder[start:end])
                    has_label = any(not masked[start + match.start()].isspace() for match in labels)
                action = _modifiers_after(masked, end + 1).get("onClick", "")
                if has_label and _local_clipboard_only(action, code):
                    errors.append({
                        "code": "share_link_clipboard_only", "unit_id": unit["unit_id"],
                        "detail": f'Swift line {row["line"]}: {label} is wired only to a local clipboard handler',
                    })
    return errors


def _check_mapped_symbols(source: str, obligations: dict, unit_id: str, sources: list[str]) -> list[dict[str, str]]:
    errors = []
    for row in _symbol_rows(obligations):
        if row["role"] == "tab":
            matched = _has_tab_symbol_contract(source, row, sources)
            detail = f'{row["label"]}: expected SDK symbol {row["target_symbol"]} at the tab call'
        elif row["role"] == "rating":
            matched = _has_rating_symbol_contract(source, row)
            detail = (f'expected filled/empty branches {row["target_symbols"]}, glyph size {row["symbol_font_pt"]}, '
                      f'and an independent button minimum {row["minimum_button_pt"]}')
        elif row["role"] == "primary_button" and row.get("target_symbol"):
            matched = _has_primary_button_symbol_contract(source, row, sources)
            detail = (f'{row["label"]}: expected PrimaryButton trailing symbol '
                      f'{row["source_symbol"]} resolved to {row["target_symbol"]}')
        else:
            continue
        if not matched:
            errors.append({"code": "mapped_system_symbol_mismatch", "unit_id": unit_id,
                           "detail": f'Swift line {row["line"]}: {detail}'})
    return errors

def _check_unit(root: Path, unit: dict[str, Any], generated_sources=None, *, root_expands=False) -> list[dict[str, str]]:
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
    errors.extend(_check_foreground_safearea(source, unit, relative, root_expands))
    errors.extend(_check_symbol_fidelity(source, unit, relative))
    errors.extend(_check_mapped_symbols(source, obligations, unit_id, generated_sources or [source]))
    errors.extend(check_label_symbols(source, unit))
    errors.extend(check_date_formats(source, unit))
    errors.extend(check_share_links(source, unit))
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


def _check_drawing_bindings(root: Path, units: list[dict], bindings: Any) -> list[dict[str, str]]:
    """Verify approved, explicitly mapped drawing components from each page build path."""
    errors = []
    if not isinstance(bindings, list):
        return [{"code": "drawing_binding_invalid", "unit_id": "",
                 "detail": "drawing_component_bindings must be an array"}]
    seen = set()
    for binding in bindings:
        try:
            definition = binding["definition"]
            key = (definition["file"], definition["line"])
            output = binding["output"]
            target = _project_file(root, output["file"])
            symbol = output["symbol"]
            if (not isinstance(key[0], str) or not key[0] or type(key[1]) is not int or key[1] < 1
                    or key in seen or target.suffix != ".ets" or not re.fullmatch(r"[A-Za-z_$][\w$]*", symbol)):
                raise ValueError("expected one target ArkUI symbol and file per source definition")
            seen.add(key)
        except (KeyError, TypeError, ValueError) as exc:
            errors.append({"code": "drawing_binding_invalid", "unit_id": "", "detail": str(exc)})
            continue
        consumers = []
        for unit in units:
            obligations = unit.get("source_obligations")
            if not unit.get("required", True) or not isinstance(obligations, dict):
                continue
            if any(isinstance(row, dict) and row.get("definition") == definition
                   for row in obligations.get("drawing_component_calls") or []):
                consumers.append(unit)
        if not consumers:
            errors.append({"code": "drawing_binding_unused", "unit_id": "", "detail": f"{key[0]}:{key[1]}"})
            continue
        try:
            target_text = _code(target.read_text(encoding="utf-8"))
        except (OSError, UnicodeError):
            target_text = ""
        target_body = _component_bodies(target_text).get(symbol, "")
        if not re.search(rf"\bexport\s+struct\s+{re.escape(symbol)}\b", target_text) or not _renders(target_body, "build"):
            errors.append({"code": "drawing_implementation_missing", "unit_id": "",
                           "detail": f"{output['file']} must export a rendering {symbol}"})
            continue
        for unit in consumers:
            try:
                host = _project_file(root, unit["output"]["file"])
                source = host.read_text(encoding="utf-8")
                names = {symbol} if host == target else _imports(root, source, host, target, symbol)
                body = _component_bodies(_code(source)).get(unit["output"]["symbol"], "")
                methods = _reachable(body, unit["output"].get("builder", "build"))
                if any(re.search(rf"(?<![\w.$]){re.escape(name)}\s*\(", method)
                       for name in names for method in methods.values()):
                    continue
            except (KeyError, OSError, TypeError, ValueError):
                pass
            errors.append({"code": "shared_drawing_not_rendered", "unit_id": unit.get("unit_id", ""),
                           "detail": f"{key[0]}:{key[1]} requires a reachable call to {output['file']}:{symbol}"})
    return errors


def evaluate(root: Path | str, inventory: Path | str, *, sdk_symbol_catalog: Path | None = None) -> dict[str, Any]:
    root = Path(root).resolve()
    inventory_path = Path(inventory)
    if not inventory_path.is_absolute():
        inventory_path = root / inventory_path
    data = _read(inventory_path)
    errors: list[dict[str, str]] = []
    units = [unit for unit in data.get("units", []) if isinstance(unit, dict)]
    source_files: dict[Path, str] = {}
    for unit in units:
        relative = (unit.get("output") or {}).get("file")
        if isinstance(relative, str):
            path = root / relative
            if path.is_file():
                source_files[path] = path.read_text(encoding="utf-8")
    # The delivery inventory normally lists page outputs, while modal
    # ownership may live in an unlisted entry/root host.  Include generated
    # ArkTS files under the app source tree so centralized bindings are still
    # verified without requiring an inventory rewrite.
    for path in sorted((root / "entry/src/main/ets").rglob("*.ets")):
        if path in source_files:
            continue
        try:
            source_files[path] = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
    generated_sources = list(source_files.values())
    root_expands = any(re.search(r"\.\s*expandSafeArea\s*\(", _code(source)) for source in generated_sources)
    for unit in units:
        if isinstance(unit, dict):
            errors.extend(_check_unit(root, unit, generated_sources, root_expands=root_expands))
    errors.extend(_check_drawing_bindings(root, units, data.get("drawing_component_bindings", [])))
    errors.extend(_check_sheet_close_actions(root, units, source_files))
    errors.extend(_check_style_fidelity(root, generated_sources))
    errors.extend(_check_state_and_persistence_contract(generated_sources))
    errors.extend(_check_nav_destination_hosts(generated_sources))
    errors.extend(_check_editor_mutation(generated_sources))
    errors.extend(_check_packaged_image_input(generated_sources))
    errors.extend(_check_source_rawfiles(root, source_files))
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
        "symbol_review_required": [
            {"unit_id": unit.get("unit_id"), "line": row["line"],
             "label": row["label"], "source_symbol": row["source_symbol"]}
            for unit in units
            for row in _symbol_rows(unit.get("source_obligations"))
            if row["role"] in {"primary_button", "label"} and not row.get("target_symbol")
        ],
        "errors": errors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--inventory", default=None)
    parser.add_argument("--output-json")
    parser.add_argument("--sdk-symbol-catalog", type=Path)
    args = parser.parse_args(argv)
    project_root = Path(args.project_root).resolve()
    inventory_path = args.inventory

    if inventory_path is None:
        index_path = project_root / "spec/execution/ui-inputs/index.json"
        if index_path.is_file():
            try:
                from lib.ios_stage1_scope import load_inventory
                inventory_path, _ = load_inventory(project_root, None)
            except ValueError as e:
                result = {"schema_version": 1, "gate": "i2h-execute.ui-obligations",
                          "status": "FAIL", "inventory": str(index_path), "error": str(e), "errors": []}
                text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
                if args.output_json:
                    Path(args.output_json).write_text(text, encoding="utf-8")
                print(text, end="")
                return 2
        else:
            inventory_path = "spec/baseline/ui-delivery-approved.json"

    result = evaluate(project_root, inventory_path, sdk_symbol_catalog=args.sdk_symbol_catalog)
    inv_file = Path(inventory_path) if Path(inventory_path).is_absolute() else project_root / inventory_path
    if inv_file.is_file():
        result["inventory_sha256"] = hashlib.sha256(inv_file.read_bytes()).hexdigest()

    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output_json:
        Path(args.output_json).write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
