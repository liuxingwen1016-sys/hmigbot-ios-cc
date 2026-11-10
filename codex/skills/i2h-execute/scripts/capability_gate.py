#!/usr/bin/env python3
"""Deterministic platform-capability gate for iOS-to-Harmony execute output."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


def _json5(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    # Only strip full-line comments.  A URI such as ``cuike://last-recipe``
    # is a valid JSON string and must not be mistaken for a comment.
    text = re.sub(r"(?m)^\s*//[^\n]*$", "", text)
    text = re.sub(r",\s*([}\]])", r"\1", text)
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def _metadata(ability: dict[str, Any], name: str) -> bool:
    return any(isinstance(item, dict) and item.get("name") == name for item in ability.get("metadata", []))


def _extension(module: dict[str, Any], extension_type: str) -> dict[str, Any] | None:
    for item in module.get("extensionAbilities", []):
        if isinstance(item, dict) and item.get("type") == extension_type:
            return item
    return None


def _entry_path(root: Path, src_entry: str) -> Path:
    value = Path(src_entry)
    if value.is_absolute():
        return value
    return root / "entry/src/main" / value


def _vision_sources(root: Path) -> tuple[str, list[str]]:
    """Read the generated F101 surface once and return its source files.

    Checking only for a file named ``OCRService.ets`` allowed a parser for
    caller-supplied strings, plus a fake viewfinder, to be reported as a
    complete camera/OCR migration.  The source-backed contract requires the
    actual page/service API chain to be present.
    """
    paths = sorted((root / "entry/src/main/ets").rglob("*.ets"))
    rows: list[str] = []
    for path in paths:
        try:
            rows.append(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            continue
    return "\n".join(rows), [path.relative_to(root).as_posix() for path in paths]


def evaluate(root: Path | str) -> dict[str, Any]:
    root = Path(root).expanduser().resolve()
    module_path = root / "entry/src/main/module.json5"
    findings: list[dict[str, Any]] = []
    if not module_path.is_file():
        return {"schema_version": 1, "status": "BLOCKED", "findings": [{"code": "MODULE_MISSING"}]}
    try:
        module = _json5(module_path).get("module", {})
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {"schema_version": 1, "status": "BLOCKED", "findings": [{"code": "MODULE_INVALID", "detail": str(exc)}]}
    abilities = [item for item in module.get("abilities", []) if isinstance(item, dict)]
    entry = next((item for item in abilities if item.get("name") == "EntryAbility"), {})

    vision_text, vision_files = _vision_sources(root)
    camera_source = root / "entry/src/main/ets/pages/LiveScannerView.ets"
    ocr_source = root / "entry/src/main/ets/services/OCRService.ets"
    permissions = module.get("requestPermissions", [])
    camera_permission = any(isinstance(item, dict) and item.get("name") == "ohos.permission.CAMERA" for item in permissions)
    camera_api = "cameraPicker" in vision_text and "abilityAccessCtrl" in vision_text
    album_api = "PhotoViewPicker" in vision_text
    ocr_api = "recognizeText" in vision_text
    has_sample_asset = any(
        path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
        and any(token in path.stem.lower() for token in ("sample", "bean"))
        for path in (root / "entry/src/main/resources").rglob("*")
    ) if (root / "entry/src/main/resources").is_dir() else False
    fixture_free = "sampleText()" not in vision_text and "sample_text" not in vision_text
    camera_pass = (
        camera_permission and camera_source.is_file() and ocr_source.is_file()
        and camera_api and album_api and ocr_api and has_sample_asset and fixture_free
    )
    findings.append({"capability": "F101_CAMERA_OCR", "status": "PASS" if camera_pass else "BLOCKED", "checks": {
        "camera_permission": camera_permission,
        "live_scanner_source": camera_source.is_file(),
        "ocr_source": ocr_source.is_file(),
        "camera_picker_api": camera_api,
        "photo_view_picker_api": album_api,
        "recognize_text_api": ocr_api,
        "sample_image_asset": has_sample_asset,
        "fixture_free": fixture_free,
        "source_files": vision_files,
    }})

    form = _extension(module, "form")
    form_source = _entry_path(root, str(form["srcEntry"])) if form and form.get("srcEntry") else None
    form_meta = bool(form and any(isinstance(item, dict) and item.get("name") == "ohos.extension.form" for item in form.get("metadata", [])))
    form_profile = root / "entry/src/main/resources/base/profile/form_config.json"
    form_pass = bool(form and form_source and form_source.is_file() and form_meta and form_profile.is_file())
    findings.append({"capability": "F103_SERVICE_CARD", "status": "PASS" if form_pass else "BLOCKED", "checks": {
        "extension": bool(form), "source": bool(form_source and form_source.is_file()), "metadata": form_meta, "profile": form_profile.is_file(),
    }})

    live = _extension(module, "liveForm")
    live_source = _entry_path(root, str(live["srcEntry"])) if live and live.get("srcEntry") else None
    notification_source = root / "entry/src/main/ets/services/SystemServices.ets"
    live_pass = bool(live and live_source and live_source.is_file() and notification_source.is_file() and "NotificationKit" in notification_source.read_text(encoding="utf-8"))
    findings.append({"capability": "F102_LIVE_FORM", "status": "PASS" if live_pass else "PARTIAL", "checks": {
        "extension": bool(live), "source": bool(live_source and live_source.is_file()), "notification_fallback": notification_source.is_file() and "NotificationKit" in notification_source.read_text(encoding="utf-8"),
    }})

    shortcut_profile = root / "entry/src/main/resources/base/profile/shortcuts.json"
    shortcut_meta = _metadata(entry, "ohos.ability.shortcuts")
    shortcut_count = 0
    if shortcut_profile.is_file():
        try:
            shortcut_count = len(_json5(shortcut_profile).get("shortcuts", []))
        except (OSError, ValueError, json.JSONDecodeError):
            findings.append({"capability": "F104_SHORTCUT", "status": "BLOCKED", "checks": {"profile_invalid": True}})
    if not any(item.get("capability") == "F104_SHORTCUT" for item in findings):
        status = "PASS" if shortcut_meta and shortcut_count > 0 else ("PARTIAL" if shortcut_profile.is_file() else "BLOCKED")
        findings.append({"capability": "F104_SHORTCUT", "status": status, "checks": {
            "metadata": shortcut_meta, "profile": shortcut_profile.is_file(), "count": shortcut_count,
        }})

    statuses = {item["status"] for item in findings}
    overall = "PASS" if statuses == {"PASS"} else "PARTIAL" if "PASS" in statuses else "BLOCKED"
    return {"schema_version": 1, "status": overall, "project_root": str(root), "findings": findings}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--output-json", required=True)
    args = parser.parse_args(argv)
    result = evaluate(args.project_root)
    Path(args.output_json).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": args.output_json, "status": result["status"]}, ensure_ascii=False))
    return 0 if result["status"] in {"PASS", "PARTIAL"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
