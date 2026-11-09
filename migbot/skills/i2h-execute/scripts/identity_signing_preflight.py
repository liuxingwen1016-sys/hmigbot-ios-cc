#!/usr/bin/env python3
"""Preflight the target bundle identity against the local signing profile.

HarmonyOS signing profiles bind a bundle name.  A converter must not replace a
template bundle name with the iOS identifier unless a matching profile exists.
This report is deliberately read-only.  It allows unsigned compilation while
blocking signed install verification when the three identities do not agree.
"""
from __future__ import annotations

import argparse
import json
import plistlib
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1


def _json5_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def read_bundle_name(app_json: Path) -> str | None:
    text = _json5_text(app_json)
    match = re.search(r"\"bundleName\"\s*:\s*\"([^\"]+)\"", text)
    return match.group(1) if match else None


def read_signing_profile(build_profile: Path) -> Path | None:
    text = _json5_text(build_profile)
    match = re.search(r"\"profile\"\s*:\s*\"([^\"]+)\"", text)
    if not match:
        return None
    return Path(match.group(1)).expanduser()


def source_bundle_id(source_root: Path) -> str | None:
    for path in sorted(source_root.rglob("Info.plist")):
        try:
            with path.open("rb") as handle:
                value = plistlib.load(handle).get("CFBundleIdentifier")
            if isinstance(value, str) and value:
                return value
        except (OSError, plistlib.InvalidFileException, ValueError):
            continue
    pattern = re.compile(r"PRODUCT_BUNDLE_IDENTIFIER\s*=\s*([^\s#]+)")
    for path in sorted(source_root.rglob("*.xcconfig")):
        try:
            match = pattern.search(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError):
            continue
        if match:
            return match.group(1).strip()
    return None


def profile_bundle_name(profile: Path, *, security_bin: str = "security") -> tuple[str | None, str | None]:
    if not profile.is_file():
        return None, "signing profile file not found"
    if shutil.which(security_bin) is None:
        return None, f"{security_bin} command not available"
    try:
        result = subprocess.run(
            [security_bin, "cms", "-D", "-i", str(profile)],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"cannot inspect signing profile: {exc}"
    if result.returncode != 0:
        return None, (result.stderr or "security cms failed").strip()
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        return None, f"invalid signing profile payload: {exc}"
    value = payload.get("bundle-info", {}).get("bundle-name")
    if not isinstance(value, str) or not value:
        return None, "signing profile has no bundle-info.bundle-name"
    return value, None


def evaluate(
    project_root: Path | str,
    *,
    source_root: Path | str | None = None,
    source_id: str | None = None,
    security_bin: str = "security",
) -> dict[str, Any]:
    root = Path(project_root).expanduser().resolve()
    app_json = root / "AppScope/app.json5"
    build_profile = root / "build-profile.json5"
    target_id = read_bundle_name(app_json) if app_json.is_file() else None
    profile = read_signing_profile(build_profile) if build_profile.is_file() else None
    source_id = source_id or (source_bundle_id(Path(source_root).expanduser().resolve()) if source_root else None)
    profile_id, profile_issue = profile_bundle_name(profile, security_bin=security_bin) if profile else (None, "signing profile path not found")

    issues: list[str] = []
    if not target_id:
        issues.append("target bundleName is missing")
    if profile_issue:
        issues.append(profile_issue)
    if source_id and target_id and source_id != target_id:
        issues.append("target bundleName differs from source CFBundleIdentifier")
    if target_id and profile_id and target_id != profile_id:
        issues.append("target bundleName differs from signing profile bundle-name")
    if target_id and target_id.startswith("com.example."):
        issues.append("target bundleName is still a template example identity")

    status = "PASS" if target_id and profile_id and target_id == profile_id and not target_id.startswith("com.example.") else "identity_signing_pending"
    return {
        "schema_version": SCHEMA_VERSION,
        "gate": "i2h-execute.identity-signing-preflight",
        "identity_status": status,
        "signed_install_allowed": status == "PASS",
        "unsigned_compile_allowed": True,
        "source_bundle_id": source_id,
        "target_bundle_name": target_id,
        "signing_profile_path": str(profile) if profile else None,
        "signing_profile_bundle_name": profile_id,
        "issues": issues,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--source-root")
    parser.add_argument("--source-bundle-id")
    parser.add_argument("--security-bin", default="security")
    parser.add_argument("--output-json", required=True)
    args = parser.parse_args(argv)
    result = evaluate(
        args.project_root,
        source_root=args.source_root,
        source_id=args.source_bundle_id,
        security_bin=args.security_bin,
    )
    output = Path(args.output_json).expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["identity_status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
