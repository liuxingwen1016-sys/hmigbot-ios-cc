#!/usr/bin/env python3
"""Query and validate actual installed app bundle identity in iOS Simulator.

This module provides generic helpers for querying the actual installed app bundle
via official xcrun simctl get_app_container and validating its Info.plist metadata.
Used by ios_runtime_capture to bind manifests to the true installed binary digest
rather than the requested input app.
"""
from __future__ import annotations

import plistlib
import subprocess
from pathlib import Path
from typing import Any, Callable


def query_installed_app_path(udid: str, bundle_id: str, *, xcrun: str = "xcrun") -> Path | None:
    """Query the actual installed app bundle path via xcrun simctl get_app_container.

    Args:
        udid: Simulator UDID
        bundle_id: App bundle identifier to query
        xcrun: Path to xcrun command (default: "xcrun")

    Returns:
        Path to installed .app bundle if found and valid, None otherwise
    """
    try:
        result = subprocess.run(
            [xcrun, "simctl", "get_app_container", udid, bundle_id, "app"],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        app_path_str = result.stdout.strip()
        if not app_path_str:
            return None
        app_path = Path(app_path_str).expanduser().resolve()
        if app_path.is_dir():
            return app_path
        return None
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return None


def validate_installed_identity(
    app_path: Path,
    expected_bundle_id: str,
    *,
    compute_digest: Callable[[Path], str] | None = None,
) -> dict[str, Any]:
    """Read and validate installed app's Info.plist identity.

    Validates that the actual installed bundle matches expected identity and has
    proper version/build metadata. Raises RuntimeError on validation failures.

    Args:
        app_path: Path to installed .app bundle
        expected_bundle_id: Expected bundle identifier (must match Info.plist)
        compute_digest: Optional callable to compute bundle digest (e.g., bundle_identity)

    Returns:
        Dict with bundle_id, version, build, build_identity, app_path, and optionally bundle_sha256

    Raises:
        RuntimeError: If Info.plist is missing, not a dict, bundle_id mismatches, or version/build are invalid
    """
    info = app_path / "Info.plist"
    if not info.is_file():
        raise RuntimeError(f"Info.plist not found in installed app: {app_path}")

    with info.open("rb") as handle:
        payload = plistlib.load(handle)

    # Validate plist root is a mapping
    if not isinstance(payload, dict):
        raise RuntimeError(f"Info.plist root must be a dictionary, got {type(payload).__name__} at {app_path}")

    # Extract and validate metadata fields
    version_raw = payload.get("CFBundleShortVersionString")
    build_raw = payload.get("CFBundleVersion")
    actual_bundle_id_raw = payload.get("CFBundleIdentifier")

    # Validate bundle_id is a nonempty string
    if not isinstance(actual_bundle_id_raw, str) or not actual_bundle_id_raw.strip():
        raise RuntimeError(
            f"CFBundleIdentifier must be a nonempty string, got {type(actual_bundle_id_raw).__name__} "
            f"value {actual_bundle_id_raw!r} at {app_path}"
        )
    actual_bundle_id = actual_bundle_id_raw.strip()

    # Validate requested bundle_id matches actual Info.plist
    if actual_bundle_id != expected_bundle_id:
        raise RuntimeError(
            f"Installed bundle_id mismatch: expected {expected_bundle_id!r}, "
            f"actual {actual_bundle_id!r} at {app_path}"
        )

    # Validate version is a nonempty string
    if not isinstance(version_raw, str) or not version_raw.strip():
        raise RuntimeError(
            f"CFBundleShortVersionString must be a nonempty string, got {type(version_raw).__name__} "
            f"value {version_raw!r} at {app_path}"
        )
    version = version_raw.strip()

    # Validate build is a nonempty string
    if not isinstance(build_raw, str) or not build_raw.strip():
        raise RuntimeError(
            f"CFBundleVersion must be a nonempty string, got {type(build_raw).__name__} "
            f"value {build_raw!r} at {app_path}"
        )
    build = build_raw.strip()

    identity = {
        "bundle_id": actual_bundle_id,
        "version": version,
        "build": build,
        "build_identity": f"{actual_bundle_id}:{version}:{build}",
        "app_path": str(app_path),
    }

    if compute_digest is not None:
        identity["bundle_sha256"] = compute_digest(app_path)

    return identity
