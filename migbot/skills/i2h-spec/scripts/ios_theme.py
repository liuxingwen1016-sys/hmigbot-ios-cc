"""Lossless iOS theme source facts (standard library only).

Extracts Color, spacing, and Font expressions from Swift source, preserving
exact original expressions and source locations. Never evaluates or invents
values; unknown expressions return explicit unresolved status.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Callable


def _line_number(text: str, offset: int) -> int:
    """Convert byte offset to line number (1-indexed)."""
    return text.count("\n", 0, offset) + 1


def scan_theme_source(path: Path, root: Path) -> dict[str, Any]:
    """Extract theme declarations from Swift source without evaluation."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return {
            "path": path.relative_to(root).as_posix(),
            "read_error": str(exc),
            "colors": [],
            "spacing": [],
            "fonts": [],
        }

    sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
    relative_path = path.relative_to(root).as_posix()

    colors = []
    spacing = []
    fonts = []

    # Match Color declarations (including adaptive/dynamic colors)
    # Pattern: static let/var identifier = Color(...)
    color_pattern = re.compile(
        r'(?:static\s+)?(?:let|var)\s+([A-Za-z_]\w*)\s*:\s*Color\s*=\s*(.+?)(?=\n\s*(?:static|let|var|func|struct|class|enum|extension|\}))',
        re.DOTALL
    )

    for match in color_pattern.finditer(text):
        name = match.group(1)
        expression = match.group(2).strip()
        line = _line_number(text, match.start())

        # Detect adaptive color patterns
        is_adaptive = bool(re.search(r'\.colorScheme|Color\s*\{|\$0\s*==\s*\.dark|dynamicProvider|@Environment.*colorScheme', expression))

        colors.append({
            "name": name,
            "expression": expression,
            "source": {
                "file": relative_path,
                "line": line,
                "sha256": sha256,
            },
            "is_adaptive": is_adaptive,
            "resolved": False,  # Never evaluate expressions
        })

    # Match spacing/dimension declarations
    # Pattern: static let/var identifier: CGFloat = value
    spacing_pattern = re.compile(
        r'(?:static\s+)?(?:let|var)\s+([A-Za-z_]\w*)\s*:\s*(?:CGFloat|Double)\s*=\s*([^\n]+)',
    )

    for match in spacing_pattern.finditer(text):
        name = match.group(1)
        expression = match.group(2).strip()
        line = _line_number(text, match.start())

        # Only include if name suggests spacing/dimension
        if any(keyword in name.lower() for keyword in ['spacing', 'padding', 'margin', 'inset', 'gap', 'size', 'width', 'height', 'radius']):
            spacing.append({
                "name": name,
                "expression": expression,
                "source": {
                    "file": relative_path,
                    "line": line,
                    "sha256": sha256,
                },
                "resolved": False,  # Preserve expression, don't evaluate
            })

    # Match Font declarations
    # Pattern: static let/var identifier = Font.custom(...) or .system(...)
    font_pattern = re.compile(
        r'(?:static\s+)?(?:let|var)\s+([A-Za-z_]\w*)\s*:\s*Font\s*=\s*(.+?)(?=\n\s*(?:static|let|var|func|struct|class|enum|extension|\}))',
        re.DOTALL
    )

    for match in font_pattern.finditer(text):
        name = match.group(1)
        expression = match.group(2).strip()
        line = _line_number(text, match.start())

        # Detect custom font references
        custom_font_match = re.search(r'Font\.custom\s*\(\s*"([^"]+)"', expression)
        custom_font_name = custom_font_match.group(1) if custom_font_match else None

        fonts.append({
            "name": name,
            "expression": expression,
            "custom_font_name": custom_font_name,
            "source": {
                "file": relative_path,
                "line": line,
                "sha256": sha256,
            },
            "resolved": False,  # Preserve expression structure
        })

    return {
        "path": relative_path,
        "sha256": sha256,
        "colors": colors,
        "spacing": spacing,
        "fonts": fonts,
    }


def scan_themes(root: Path, eligible: Callable[[Path], bool] | None = None) -> dict[str, Any]:
    """Scan Swift source files for theme declarations."""
    root = root.resolve()

    # Look for files that likely contain theme definitions
    theme_files = []
    for path in sorted(root.rglob("*.swift")):
        if not path.is_file():
            continue
        if eligible is not None and not eligible(path):
            continue

        # Heuristic: file name contains "theme", "color", "style", or "design"
        name_lower = path.stem.lower()
        if any(keyword in name_lower for keyword in ['theme', 'color', 'style', 'design', 'token']):
            theme_files.append(path)

    themes = []
    all_colors = []
    all_spacing = []
    all_fonts = []

    for path in theme_files:
        theme = scan_theme_source(path, root)
        if theme["colors"] or theme["spacing"] or theme["fonts"]:
            themes.append(theme)
            all_colors.extend(theme["colors"])
            all_spacing.extend(theme["spacing"])
            all_fonts.extend(theme["fonts"])

    return {
        "themes": themes,
        "colors": all_colors,
        "spacing": all_spacing,
        "fonts": all_fonts,
        "summary": {
            "theme_file_count": len(themes),
            "color_count": len(all_colors),
            "spacing_count": len(all_spacing),
            "font_count": len(all_fonts),
        },
    }
