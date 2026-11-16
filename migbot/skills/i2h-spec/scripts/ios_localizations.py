"""Lossless, source-addressed iOS localization facts (standard library only).

The scalar projection is for legacy readers. ``entries`` is authoritative:
plural/device/substitution trees and extraction metadata must not be flattened
into an arbitrary translation. This module does not choose Harmony qualifiers.
"""
from __future__ import annotations

import hashlib
import json
import plistlib
import re
from pathlib import Path
from typing import Any, Callable
from xml.parsers.expat import ExpatError


class LocalizationError(ValueError):
    """Invalid source localization; callers must not publish an empty success."""


def _object(value: Any, context: str) -> dict:
    if not isinstance(value, dict):
        raise LocalizationError(f"{context}: expected object")
    return value


def _unique(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise LocalizationError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _invalid_constant(value: str) -> Any:
    raise LocalizationError(f"invalid JSON constant {value}")


def _pointer(parts: list[str]) -> str:
    return "/" + "/".join(part.replace("~", "~0").replace("/", "~1") for part in parts)


def _decode_quoted(value: str) -> str:
    """Decode Apple's C-style escapes, including octal and Unicode escapes."""
    escapes = {"n": "\n", "r": "\r", "t": "\t", "b": "\b", "f": "\f",
               "a": "\a", "v": "\v", '"': '"', "'": "'", "\\": "\\"}
    pieces = []
    index = 0
    while index < len(value):
        char = value[index]
        index += 1
        if char != "\\":
            pieces.append(char)
            continue
        if index == len(value):
            raise LocalizationError("unterminated string escape")
        char = value[index]
        index += 1
        if char in escapes:
            pieces.append(escapes[char])
        elif char in {"u", "U"}:
            digits = value[index:index + 4]
            if len(digits) != 4 or not re.fullmatch(r"[0-9a-fA-F]{4}", digits):
                raise LocalizationError("Unicode escape requires four hex digits")
            pieces.append(chr(int(digits, 16)))
            index += 4
        elif char in "01234567":
            digits = char
            while index < len(value) and len(digits) < 3 and value[index] in "01234567":
                digits += value[index]
                index += 1
            pieces.append(chr(int(digits, 8)))
        elif char == "\n":
            continue  # escaped physical line continuation
        else:
            raise LocalizationError(f"unknown string escape: \\{char}")
    # Combine valid UTF-16 surrogate pairs while rejecting orphan surrogates.
    return "".join(pieces).encode("utf-16", "surrogatepass").decode("utf-16")


def parse_strings(path: Path) -> dict[str, str]:
    """Read classic quoted strings and XML/binary string plists, including UTF-16."""
    data = path.read_bytes()
    try:
        encoding = "utf-16" if data.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
        text = "" if data.startswith(b"bplist") else data.decode(encoding)
        if data.startswith(b"bplist") or text.lstrip().startswith(("<?xml", "<plist")):
            result = _object(plistlib.loads(data), str(path))
            if not all(isinstance(k, str) and isinstance(v, str) for k, v in result.items()):
                raise LocalizationError(f"{path}: strings plist must contain string values")
            return result
        quoted = r'"((?:\\.|[^"\\])*)"'
        pair = re.compile(quoted + r"\s*=\s*" + quoted + r"\s*;", re.S)
        trivia = re.compile(r"(?:\s+|/\*.*?\*/|//[^\n]*(?:\n|$))+", re.S)
        result = {}
        offset = 0
        while offset < len(text):
            ignored = trivia.match(text, offset)
            if ignored:
                offset = ignored.end()
                continue
            match = pair.match(text, offset)
            if not match:
                raise LocalizationError(f"{path}: invalid .strings syntax at offset {offset}")
            key, value = map(_decode_quoted, match.groups())
            if key in result:
                raise LocalizationError(f"{path}: duplicate string key {key!r}")
            result[key] = value
            offset = match.end()
        return result
    except (UnicodeError, json.JSONDecodeError, plistlib.InvalidFileException, ExpatError) as exc:
        raise LocalizationError(f"{path}: invalid .strings: {exc}") from exc


def _units(node: dict, path: list[str], context: str) -> list[dict]:
    """Walk known variation axes without losing nested device/plural or substitutions."""
    leaves = []
    if "stringUnit" in node:
        unit = _object(node["stringUnit"], context + "/stringUnit")
        if not isinstance(unit.get("value"), str):
            raise LocalizationError(f"{context}/stringUnit/value: expected string")
        if "state" in unit and not isinstance(unit["state"], str):
            raise LocalizationError(f"{context}/stringUnit/state: expected string")
        leaves.append({"path": path + ["stringUnit"], **unit})
    if "variations" in node:
        axes = _object(node["variations"], context + "/variations")
        for axis, options in sorted(axes.items()):
            for selector, child in sorted(_object(options, context + "/variations/" + axis).items()):
                child_path = path + ["variations", axis, selector]
                leaves.extend(_units(_object(child, context + _pointer(child_path)), child_path, context))
    if "substitutions" in node:
        for name, child in sorted(_object(node["substitutions"], context + "/substitutions").items()):
            child_path = path + ["substitutions", name]
            leaves.extend(_units(_object(child, context + _pointer(child_path)), child_path, context))
    return leaves


def scan_localizations(root: Path, eligible: Callable[[Path], bool] | None = None) -> dict[str, Any]:
    """Return scalars, lossless records, source hashes and explicit diagnostics."""
    root = root.resolve()
    files = sorted(p for p in root.rglob("*") if p.is_file()
                   and p.suffix in {".strings", ".stringsdict", ".xcstrings"}
                   and (eligible is None or eligible(p)))
    result: dict[str, Any] = {"localizations": {}, "entries": [], "sources": [], "diagnostics": []}
    for path in files:
        relative = path.relative_to(root).as_posix()
        source = {"file": relative, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "format": path.suffix[1:]}
        result["sources"].append(source)
        locale = next((part[:-6] for part in reversed(path.parts) if part.endswith(".lproj")), "und")
        def add(key: str, language: str, payload: dict, *, source_language: str | None = None,
                entry_metadata: dict | None = None, pointer: list[str] | None = None,
                inferred: bool = False) -> None:
            location = relative + _pointer(pointer or [key])
            variants = _units(payload, [], location)
            record = {"key": key, "locale": language, "table": path.stem,
                      "source_language": source_language, "localization": payload,
                      "entry_metadata": entry_metadata or {}, "variants": variants,
                      "source": {**source, "pointer": _pointer(pointer or [key])},
                      "inferred_from_key": inferred}
            scalar = payload.get("stringUnit")
            if isinstance(scalar, dict) and not ("variations" in payload or "substitutions" in payload):
                record["value"] = scalar["value"]
                result["localizations"].setdefault(language, {}).setdefault(relative, {})[key] = scalar["value"]
            else:
                result["localizations"].setdefault(language, {}).setdefault(relative, {})
            if not variants:
                result["diagnostics"].append({"code": "localization-without-string-unit", "source": record["source"], "key": key, "locale": language})
            result["entries"].append(record)
        try:
            if path.suffix == ".strings":
                for key, value in sorted(parse_strings(path).items()):
                    add(key, locale, {"stringUnit": {"value": value}})
            elif path.suffix == ".stringsdict":
                payload = _object(plistlib.loads(path.read_bytes()), relative)
                for key, entry in sorted(payload.items()):
                    entry = _object(entry, relative + "/" + key)
                    if not isinstance(entry.get("NSStringLocalizedFormatKey"), str):
                        raise LocalizationError(f"{relative}/{key}: NSStringLocalizedFormatKey must be string")
                    record = {"key": key, "locale": locale, "table": path.stem, "source_language": None,
                              "localization": entry, "entry_metadata": {}, "variants": [],
                              "source": {**source, "pointer": _pointer([key])}, "inferred_from_key": False}
                    for variable, rules in entry.items():
                        if variable == "NSStringLocalizedFormatKey":
                            continue
                        rules = _object(rules, f"{relative}/{key}/{variable}")
                        for selector, value in rules.items():
                            if not isinstance(value, str):
                                raise LocalizationError(f"{relative}/{key}/{variable}/{selector}: expected string")
                            if not selector.startswith("NSString"):
                                record["variants"].append({"path": [variable, selector], "value": value})
                    # Preserve the native format dictionary; no arbitrary plural is a scalar.
                    result["entries"].append(record)
                    result["localizations"].setdefault(locale, {}).setdefault(relative, {})
            else:
                payload = _object(json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=_unique,
                                             parse_constant=_invalid_constant), relative)
                source_language = payload.get("sourceLanguage")
                if not isinstance(source_language, str) or not source_language.strip():
                    raise LocalizationError(f"{relative}: sourceLanguage must be non-empty string")
                strings = _object(payload.get("strings"), relative + "/strings")
                source["source_language"] = source_language
                source["catalog_metadata"] = {k: v for k, v in payload.items() if k != "strings"}
                for key, entry in sorted(strings.items()):
                    entry = _object(entry, relative + "/strings/" + key)
                    locales = _object(entry.get("localizations", {}), relative + "/strings/" + key + "/localizations")
                    metadata = {k: v for k, v in entry.items() if k != "localizations"}
                    for language, localized in sorted(locales.items()):
                        if not language.strip():
                            raise LocalizationError(f"{relative}/{key}: locale must not be empty")
                        add(key, language, _object(localized, f"{relative}/{key}/{language}"),
                            source_language=source_language, entry_metadata=metadata,
                            pointer=["strings", key, "localizations", language])
                    if source_language not in locales:
                        add(key, source_language, {"stringUnit": {"value": key}}, source_language=source_language,
                            entry_metadata=metadata, pointer=["strings", key], inferred=True)
        except (UnicodeError, json.JSONDecodeError, plistlib.InvalidFileException, ExpatError, LocalizationError) as exc:
            raise LocalizationError(f"{relative}: {exc}") from exc
    return result


def scalar_projection(facts: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Legacy projection: ambiguous table keys remain in facts plus a diagnostic."""
    result: dict[str, dict[str, str]] = {}
    ambiguous = set()
    for entry in facts["entries"]:
        if "value" not in entry:
            continue
        values = result.setdefault(entry["locale"], {})
        key, value = entry["key"], entry["value"]
        identity = (entry["locale"], key)
        if identity in ambiguous:
            continue
        if key in values and values[key] != value:
            values.pop(key)
            ambiguous.add(identity)
            facts["diagnostics"].append({"code": "ambiguous-localization-key", "locale": entry["locale"],
                                         "key": key, "reason": "multiple source tables; consume localization_entries"})
        else:
            values[key] = value
    return result
