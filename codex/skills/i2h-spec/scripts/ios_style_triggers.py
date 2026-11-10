#!/usr/bin/env python3
"""Detect source-backed iOS style triggers without loading style skills globally.

The detector is intentionally report-only.  It emits source anchors and
existing ArkUI skills that may help the Plan stage.  It never claims that an
iOS material, sheet, or navigation effect has a native HarmonyOS equivalent.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


SCHEMA = "i2h-ios-style-triggers/1"

RULES: tuple[dict[str, Any], ...] = (
    {
        "id": "custom_shape_geometry",
        "patterns": (
            r"\b(?:struct|enum|class)\s+\w+\s*:\s*(?:InsettableShape|Shape)\b",
            r"\bPath\s*(?:\{|\()",
            r"\bCanvas\s*\{",
            r"\.path\s*\(",
        ),
        "reference": "ios-custom-shape-geometry",
        "suggested_skills": ["arkts-component-builder", "arkts-ui-alignment"],
        "native_api_candidates": ["Path", "Canvas", "Shape"],
        "fallback": "custom_shape_path_with_source_geometry",
    },
    {
        "id": "floating_tabbar",
        "patterns": (r"\bTabView\s*\(",),
        "reference": "ios-floating-tabbar",
        "suggested_skills": ["arkts-component-builder", "arkts-ui-alignment"],
        "native_api_candidates": ["Tabs"],
        "fallback": "custom_tab_bar_with_explicit_selection_state",
    },
    {
        "id": "glass_toolbar",
        "patterns": (r"\bToolbarItem(?:Group)?\b", r"\.toolbar\s*\{"),
        "reference": "ios-glass-toolbar",
        "suggested_skills": ["arkts-component-builder", "arkts-ui-alignment"],
        "native_api_candidates": ["Navigation.toolbar"],
        "fallback": "custom_toolbar_background_and_button_group",
    },
    {
        "id": "search_presentation",
        "patterns": (r"\.searchable\s*\(",),
        "reference": "ios-search-presentation",
        "suggested_skills": ["arkts-component-builder", "arkts-ui-alignment"],
        "native_api_candidates": ["Search"],
        "fallback": "toolbar_search_with_explicit_focus_and_cancel_state",
    },
    {
        "id": "detent_sheet",
        "patterns": (r"\.(?:sheet|fullScreenCover)\s*\(",),
        "reference": "ios-detent-sheet",
        "suggested_skills": ["arkts-component-builder", "arkts-ui-alignment"],
        "native_api_candidates": ["bindSheet", "bindContentCover"],
        "fallback": "root_host_overlay_with_explicit_close_and_scrim",
    },
    {
        "id": "glass_slider",
        "patterns": (r"\bSlider\s*\(",),
        "reference": "ios-glass-slider",
        "suggested_skills": ["arkts-component-builder", "arkts-ui-alignment"],
        "native_api_candidates": ["Slider"],
        "fallback": "native_slider_with_source_value_and_enabled_state",
    },
    {
        "id": "lazy_grid",
        "patterns": (r"\bLazyVGrid\s*\(", r"\bLazyHGrid\s*\("),
        "reference": "ios-lazy-grid",
        "suggested_skills": ["arkts-component-builder", "arkts-ui-alignment"],
        "native_api_candidates": ["Grid", "GridItem"],
        "fallback": "native_grid_with_source_columns_spacing_and_adaptive_minimum",
    },
    {
        "id": "glass_switch",
        "patterns": (r"\bToggle\s*\(",),
        "reference": "ios-glass-switch",
        "suggested_skills": ["arkts-component-builder", "arkts-ui-alignment"],
        "native_api_candidates": ["Toggle"],
        "fallback": "native_switch_with_source_state_and_enabled_state",
    },
    {
        "id": "large_title",
        "patterns": (r"\.font\s*\(\s*\.largeTitle", r"\.navigationTitle\s*\("),
        "reference": "ios-large-title",
        "suggested_skills": ["arkts-navigation-builder", "arkts-ui-alignment"],
        "native_api_candidates": ["Navigation.titleMode"],
        "fallback": "explicit_title_mode_and_scroll_state",
    },
    {
        "id": "anchored_popover",
        "patterns": (r"\.popover\s*\(",),
        "reference": "ios-anchored-popover",
        "suggested_skills": ["arkts-component-builder", "arkts-ui-alignment"],
        "native_api_candidates": ["bindPopup"],
        "fallback": "anchored_custom_overlay_with_dismiss_region",
    },
    {
        "id": "context_menu",
        "patterns": (r"\.contextMenu\s*\(",),
        "reference": "ios-context-menu",
        "suggested_skills": ["arkts-component-builder", "arkts-ui-alignment"],
        "native_api_candidates": ["bindContextMenu"],
        "fallback": "long_press_menu_with_preview_state",
    },
    {
        "id": "segmented_control",
        "patterns": (r"Picker\s*\([^\n]*\.segmented", r"UISegmentedControl"),
        "reference": "ios-segmented-control",
        "suggested_skills": ["arkts-component-builder", "arkts-ui-alignment"],
        "native_api_candidates": ["CapsuleSegmentButton"],
        "fallback": "custom_single_selection_segment_row",
    },
    {
        "id": "background_extension",
        "patterns": (r"\.backgroundExtensionEffect\s*\(",),
        "reference": "ios-background-extension",
        "suggested_skills": ["arkts-component-builder", "arkts-ui-alignment"],
        "native_api_candidates": [],
        "fallback": "mirrored_background_asset_with_blur_and_clip",
    },
    {
        "id": "scroll_edge",
        "patterns": (r"\.scrollEdgeEffectStyle\s*\(",),
        "reference": "ios-scroll-edge",
        "suggested_skills": ["arkts-component-builder", "arkts-ui-alignment"],
        "native_api_candidates": ["Navigation.scrollEffectOptions"],
        "fallback": "non_interactive_edge_readability_overlay",
    },
    {
        "id": "glass_morph",
        "patterns": (r"\bGlassEffectContainer\b", r"\bglassEffect(?:ID|Union)\b"),
        "reference": "ios-glass-morph",
        "suggested_skills": ["arkts-component-builder", "arkts-ui-alignment"],
        "native_api_candidates": ["geometryTransition"],
        "fallback": "explicit_transition_without_material_equivalence_claim",
    },
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _line(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def detect(root: str | Path) -> dict[str, Any]:
    source = Path(root).expanduser().resolve()
    if not source.is_dir():
        raise FileNotFoundError(source)
    triggers: list[dict[str, Any]] = []
    for path in sorted(source.rglob("*.swift")):
        if any(part in {".git", "build", "DerivedData", "Tests", "Test"} for part in path.parts):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        relative = path.relative_to(source).as_posix()
        for rule in RULES:
            matches: list[dict[str, Any]] = []
            for pattern in rule["patterns"]:
                for match in re.finditer(pattern, text):
                    matches.append({"line": _line(text, match.start()), "pattern": pattern})
            if not matches:
                continue
            deduped = {(item["line"], item["pattern"]): item for item in matches}
            triggers.append({
                "trigger_id": rule["id"],
                "reference": rule["reference"],
                "source_anchor": {"path": relative, "sha256": _sha256(path), "lines": sorted(deduped)},
                "suggested_skills": list(rule["suggested_skills"]),
                "native_api_candidates": list(rule["native_api_candidates"]),
                "fallback": rule["fallback"],
                "compatibility": {
                    "mode": "probe_current_sdk_before_native_use",
                    "native_api_is_optional": True,
                    "root_overlay_fallback_required": rule["id"] in {"detent_sheet", "anchored_popover", "context_menu"},
                },
            })
    return {
        "schema_version": SCHEMA,
        "source_root": str(source),
        "source_sha256": hashlib.sha256("".join(item["source_anchor"]["sha256"] for item in triggers).encode()).hexdigest(),
        "triggers": triggers,
        "trigger_count": len(triggers),
        "untriggered_styles": sorted({rule["id"] for rule in RULES} - {item["trigger_id"] for item in triggers}),
        "policy": "triggered_references_only; no global style-skill loading",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_root")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        value = detect(args.source_root)
        output = Path(args.output).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        print(f"ERROR: {exc}")
        return 2
    print(json.dumps({"output": str(output), "trigger_count": value["trigger_count"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
