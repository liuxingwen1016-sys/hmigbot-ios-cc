"""Lossless iOS font resource facts (standard library only).

Extracts font family and PostScript names from TTF/OTF name tables, preserves
source bytes, and scans Info.plist for UIAppFonts registration. Never infers
font properties from filenames; unsupported formats return explicit unresolved.
"""
from __future__ import annotations

import hashlib
import plistlib
import struct
from pathlib import Path
from typing import Any, Callable


class FontParseError(ValueError):
    """Invalid font file; callers must preserve diagnostic and source bytes."""


def _read_name_table(data: bytes) -> dict[int, str]:
    """Extract name table entries from TTF/OTF using Apple's sfnt spec."""
    if len(data) < 12:
        raise FontParseError("file too short for sfnt header")

    # Read sfnt header
    tag = data[:4]
    if tag not in (b"\x00\x01\x00\x00", b"OTTO", b"true", b"typ1"):
        raise FontParseError(f"not a TrueType/OpenType font (tag: {tag!r})")

    num_tables = struct.unpack(">H", data[4:6])[0]

    # Find 'name' table directory entry
    name_offset = None
    name_length = None
    offset = 12
    for _ in range(num_tables):
        if offset + 16 > len(data):
            raise FontParseError("table directory truncated")
        table_tag = data[offset:offset+4]
        table_offset, table_length = struct.unpack(">II", data[offset+8:offset+16])
        if table_tag == b"name":
            name_offset = table_offset
            name_length = table_length
            break
        offset += 16

    if name_offset is None:
        raise FontParseError("no 'name' table found")

    if name_offset + name_length > len(data):
        raise FontParseError("name table extends beyond file")

    # Parse name table
    name_data = data[name_offset:name_offset + name_length]
    if len(name_data) < 6:
        raise FontParseError("name table too short")

    format_selector, count, string_offset = struct.unpack(">HHH", name_data[:6])
    if format_selector > 1:
        raise FontParseError(f"unsupported name table format {format_selector}")

    names = {}
    offset_base = 6
    for i in range(count):
        record_offset = offset_base + i * 12
        if record_offset + 12 > len(name_data):
            break
        platform_id, encoding_id, language_id, name_id, length, offset = struct.unpack(
            ">HHHHHH", name_data[record_offset:record_offset+12]
        )
        string_start = string_offset + offset
        string_end = string_start + length
        if string_end > len(name_data):
            continue

        raw_string = name_data[string_start:string_end]

        # Decode based on platform/encoding
        try:
            if platform_id == 0:  # Unicode
                text = raw_string.decode("utf-16-be")
            elif platform_id == 1:  # Macintosh
                text = raw_string.decode("mac_roman")
            elif platform_id == 3:  # Windows
                if encoding_id in (1, 10):  # Unicode BMP or full
                    text = raw_string.decode("utf-16-be")
                else:
                    text = raw_string.decode("latin-1")
            else:
                continue
        except (UnicodeDecodeError, LookupError):
            continue

        # Prefer English (language_id 0 for Unicode/Windows, 0 for Mac)
        if name_id in names and language_id != 0:
            continue

        names[name_id] = text

    return names


def scan_font_file(path: Path) -> dict[str, Any]:
    """Parse TTF/OTF and extract family/PostScript names from name table."""
    data = path.read_bytes()
    sha256 = hashlib.sha256(data).hexdigest()

    result: dict[str, Any] = {
        "path": path.name,
        "size_bytes": len(data),
        "sha256": sha256,
        "format": path.suffix.lower().lstrip("."),
        "resolved": False,
    }

    try:
        names = _read_name_table(data)
        # name ID 1 = Font Family, 6 = PostScript name
        if 1 in names:
            result["family"] = names[1]
            result["resolved"] = True
        if 6 in names:
            result["postscript_name"] = names[6]

        # Keep other useful names for debugging
        if 2 in names:  # Subfamily (Regular, Bold, etc.)
            result["subfamily"] = names[2]
        if 4 in names:  # Full font name
            result["full_name"] = names[4]

    except FontParseError as exc:
        result["parse_error"] = str(exc)
        result["resolved"] = False

    return result


def scan_font_registration(root: Path) -> list[dict[str, Any]]:
    """Scan Info.plist files for UIAppFonts registration."""
    registrations = []

    for info_plist in root.rglob("Info.plist"):
        try:
            with info_plist.open("rb") as f:
                plist = plistlib.load(f)

            if not isinstance(plist, dict):
                continue

            app_fonts = plist.get("UIAppFonts")
            if not isinstance(app_fonts, list):
                continue

            registrations.append({
                "source": info_plist.relative_to(root).as_posix(),
                "fonts": [font for font in app_fonts if isinstance(font, str)],
            })

        except (OSError, plistlib.InvalidFileException):
            continue

    return registrations


def scan_fonts(root: Path, eligible: Callable[[Path], bool] | None = None) -> dict[str, Any]:
    """Scan font files and registration, preserving source bytes and parse state."""
    root = root.resolve()
    font_extensions = {".ttf", ".otf"}

    fonts = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in font_extensions:
            continue
        if eligible is not None and not eligible(path):
            continue

        try:
            font_info = scan_font_file(path)
            font_info["path"] = path.relative_to(root).as_posix()
            fonts.append(font_info)
        except (OSError, UnicodeDecodeError) as exc:
            fonts.append({
                "path": path.relative_to(root).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "format": path.suffix.lower().lstrip("."),
                "resolved": False,
                "read_error": str(exc),
            })

    registrations = scan_font_registration(root)

    return {
        "fonts": fonts,
        "registrations": registrations,
        "resolved_count": sum(1 for f in fonts if f.get("resolved")),
        "total_count": len(fonts),
    }
