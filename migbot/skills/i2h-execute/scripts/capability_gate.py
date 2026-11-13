#!/usr/bin/env python3
"""Deterministic platform-capability gate for iOS-to-Harmony execute output."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from lib.ios_stage1_scope import inventory_path, load_inventory
from lib.ios_ui_delivery_gate import _code, _component_bodies, _reachable
from lib.stage1_reachability import _IMPORT_RE, _resolve


ETS_ROOT = Path("entry/src/main/ets")
SCAN_PAGE = ETS_ROOT / "pages/ScanView.ets"
LIVE_VIEW = ETS_ROOT / "pages/LiveScannerView.ets"
OCR_SERVICE = ETS_ROOT / "services/OCRService.ets"
LIVE_SOURCE_API = re.compile(r"\bDataScannerViewController\b")


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


def _source_camera_mode(root: Path) -> tuple[str, list[dict], list[tuple[Path, str]]]:
    """Read the source files bound by the approved UI inventory, including their frozen hashes."""
    approved = inventory_path(root, None)
    if not approved.exists() and not approved.is_symlink():
        return "legacy_still_photo", [], []
    _, inventory = load_inventory(root, None)
    source_root = inventory.get("source_project_root")
    if not isinstance(source_root, str) or not Path(source_root).is_absolute() or not Path(source_root).is_dir():
        raise ValueError("the approved iOS source root is unavailable")
    source_root = Path(source_root).resolve()
    units = inventory.get("units")
    if not isinstance(units, list) or any(not isinstance(unit, dict) for unit in units):
        raise ValueError("invalid approved camera source units")
    verified = {}
    evidence = {}
    targets = set()
    for unit in units:
        if unit.get("required") is False:
            continue
        refs = unit.get("source_refs", [])
        if not isinstance(refs, list):
            raise ValueError("invalid approved source anchors")
        for ref in refs:
            if not isinstance(ref, dict) or not isinstance(ref.get("file"), str):
                raise ValueError("invalid approved source anchor")
            relative = Path(ref["file"])
            if relative.suffix.lower() not in {".swift", ".m", ".mm"}:
                continue
            source = (source_root / relative).resolve()
            if relative.is_absolute() or not source.is_relative_to(source_root):
                raise ValueError(f"source anchor escapes the approved root: {relative}")
            if source not in verified:
                raw = source.read_bytes()
                verified[source] = (hashlib.sha256(raw).hexdigest(),
                                    bool(LIVE_SOURCE_API.search(_code(raw.decode("utf-8")))))
            digest, live = verified[source]
            if str(ref.get("sha256", "")).removeprefix("sha256:") != digest:
                raise ValueError(f"source anchor changed since approval: {relative}")
            if live:
                output = unit.get("output")
                if not isinstance(output, dict) or not all(isinstance(output.get(key), str) and output[key]
                                                           for key in ("file", "symbol")):
                    raise ValueError(f"approved live scanner output is missing: {relative}")
                target = (root / output["file"]).resolve()
                if not target.is_relative_to(root / ETS_ROOT) or target.suffix != ".ets":
                    raise ValueError(f"approved live scanner output escapes the ArkTS source tree: {output['file']}")
                targets.add((target, output["symbol"]))
                evidence[relative.as_posix()] = {"file": relative.as_posix(), "sha256": digest,
                                                "api": "DataScannerViewController"}
    if not verified:
        raise ValueError("the approved inventory contains no native source anchors")
    return ("live_text" if targets else "still_photo", list(evidence.values()), sorted(targets))


def _vision_sources(root: Path, entry: Path) -> dict[Path, str]:
    """Limit static camera evidence to production files imported by the scanner entry."""
    ets_root = root / ETS_ROOT
    queue = [entry]
    sources = {}
    while queue:
        path = queue.pop().resolve()
        if path in sources or not path.is_relative_to(ets_root) or path.suffix != ".ets" or not path.is_file():
            continue
        source = path.read_text(encoding="utf-8")
        sources[path] = source
        for name in _IMPORT_RE.findall(_code(source, keep_strings=True)):
            resolved = _resolve(ets_root, path, name)
            if resolved is not None:
                queue.append(resolved)
    return sources


def _live_camera_checks(root: Path, sources: dict[Path, str], entry: Path, symbol: str) -> dict[str, bool]:
    scanner = sources.get(root / LIVE_VIEW, "")
    component = _component_bodies(_code(sources.get(entry, ""))).get(symbol, "")
    body = "\n".join(_reachable(component, "build").values())
    scanner_code = _code(scanner)
    frame_sources = []
    for source in sources.values():
        code = _code(source)
        if re.search(r"\.\s*(?:readLatestImage|readNextImage)\s*\(", code):
            frame_sources.append(code)
    receiver_releases = []
    for code in frame_sources:
        receivers = re.findall(r"\b([A-Za-z_$][\w$]*)\s*(?::\s*[\w.]+)?\s*=\s*[\w.]*createImageReceiver\s*\(", code)
        receiver_releases.extend(re.search(rf"\b{re.escape(name)}\s*\??\.\s*release\s*\(", code) is not None
                                 for name in receivers if re.search(r"\.\s*stop\s*\(", code))
    return {
        "live_scanner_mounted": bool(scanner and re.search(r"\bLiveScannerView\s*\(", body)),
        "preview_surface": bool(re.search(r"\bXComponent\s*\(", scanner_code)
                                and re.search(r"\b(?:getXComponentSurfaceId|onSurfaceCreated)\s*\(", scanner_code)),
        "preview_frame_stream": any(all(re.search(rf"\.\s*{name}\s*\(", code) for name in (
            "createCameraInput", "createPreviewOutput", "createImageReceiver", "getReceivingSurfaceId", "start"
        )) for code in frame_sources),
        "frame_ocr": any(re.search(r"\.\s*(?:recognizeFrame|recognizePixelMap|recognizeText)\s*\(", code)
                         for code in frame_sources),
        "preview_cleanup": bool(re.search(r"\baboutToDisappear\s*\(", scanner_code) and any(receiver_releases)),
    }


def _camera_finding(root: Path, permissions: list) -> dict:
    try:
        mode, evidence, targets = _source_camera_mode(root)
    except (OSError, UnicodeError, ValueError) as exc:
        return {"capability": "F101_CAMERA_OCR", "status": "BLOCKED", "code": "SOURCE_CAMERA_EVIDENCE_INVALID",
                "detail": str(exc), "result_scope": "STRUCTURAL_ONLY", "behavior_verified": False,
                "checks": {"source_camera_mode": "unresolved"}}
    if not targets:
        targets = [(root / (SCAN_PAGE if (root / SCAN_PAGE).is_file() else LIVE_VIEW), "ScanView")]
    all_sources = {}
    live_checks = []
    required_checks = []
    for entry, symbol in targets:
        sources = _vision_sources(root, entry)
        all_sources.update(sources)
        code = "\n".join(_code(source) for source in sources.values())
        checks = {
            "camera_permission": any(isinstance(item, dict) and item.get("name") == "ohos.permission.CAMERA"
                                     for item in permissions),
            "live_scanner_source": root / LIVE_VIEW in sources,
            "ocr_source": root / OCR_SERVICE in sources,
            "runtime_camera_permission": bool(re.search(r"\brequestPermissionsFromUser\s*\(", code)),
            "photo_view_picker_api": bool(re.search(r"\bPhotoViewPicker\s*\(", code)),
            "recognize_text_api": bool(re.search(r"\brecognizeText\s*\(", code)),
            "fixture_free": not bool(re.search(r"\bsampleText\s*\(\s*\)|\bsample_text\b", code)),
        }
        camera_picker = bool(re.search(r"\bcameraPicker\s*\.\s*pick\s*\(", code))
        live = _live_camera_checks(root, sources, entry, symbol)
        live_checks.append(live)
        required_checks.append({**checks, "required_camera_api": all(live.values()) if mode == "live_text" else camera_picker,
                                "camera_picker_api": camera_picker})
    checks = {key: all(row[key] for row in required_checks) for key in required_checks[0]}
    live = {key: all(row[key] for row in live_checks) for key in live_checks[0]}
    checks["sample_image_asset"] = any(
        path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
        and any(token in path.stem.lower() for token in ("sample", "bean"))
        for path in (root / "entry/src/main/resources").rglob("*")
    )
    missing = [key for key, value in checks.items() if not value and key != "camera_picker_api"]
    if mode == "live_text":
        missing.extend(key for key, value in live.items() if not value)
    return {"capability": "F101_CAMERA_OCR", "status": "BLOCKED" if missing else "PASS",
            "result_scope": "STRUCTURAL_ONLY", "behavior_verified": False, "source_evidence": evidence,
            "missing_checks": missing, "checks": {**checks, **live, "live_camera_api": all(live.values()),
                "source_camera_mode": mode, "source_files": sorted(path.relative_to(root).as_posix() for path in all_sources)}}


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

    findings.append(_camera_finding(root, module.get("requestPermissions", [])))

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
