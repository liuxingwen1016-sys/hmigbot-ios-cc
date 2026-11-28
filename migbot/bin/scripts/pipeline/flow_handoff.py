"""flow_handoff.py — three read-only CLI entry-points for the iOS→HarmonyOS pipeline.

execute-source   Print the resolved absolute iOS source root; exit 2 on any validation error.
execute-inputs   Print a JSON summary of the current indexed plan inputs and static resource
                 facts; exit non-zero when required files are absent.
retrospect-metrics  Print per-direction line-count metrics as JSON; never prints Cuike-specific
                 numbers; uses per-file reading (no wc / batched find pipeline).

All three commands are READ-ONLY: they do not write markers, approve scopes, or modify any
project file.  Callers receive facts; they decide what to do with them.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_SWIFT_SUFFIXES = {".swift", ".m", ".mm", ".h"}
_ARKTS_SUFFIXES = {".ets", ".ts"}

_EXCLUDED_IOS = {
    "Tests", "Test", "Pods", "Carthage", "DerivedData", ".build",
    "node_modules", "build", "dist", "out", ".migbot", ".git",
}
_EXCLUDED_HMOS = {
    ".git", ".build", "DerivedData", "node_modules", "build", "dist",
    "out", ".migbot", "hvigorfile", ".gradle", ".idea", "ohosTest", "test",
}


def _diag(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)


def _load_config(root: Path) -> dict[str, Any] | None:
    cfg_path = root / ".migbot" / "config.json"
    if not cfg_path.is_file():
        _diag(f"config not found: {cfg_path}")
        return None
    try:
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
    except UnicodeDecodeError as exc:
        _diag(f"config contains invalid UTF-8: {exc}")
        return None
    except (OSError, json.JSONDecodeError) as exc:
        _diag(f"config parse error: {exc}")
        return None
    if not isinstance(data, dict):
        _diag("config must be a JSON object")
        return None
    return data


def _resolve_path(value: object, root: Path) -> Path | None:
    """Resolve a config value to an absolute Path; return None on any error."""
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped:
        return None
    try:
        expanded = Path(os.path.expanduser(stripped))
    except (ValueError, RuntimeError):
        return None
    if expanded.is_absolute():
        return expanded.resolve()
    return (root / expanded).resolve()


def _is_ios_project(path: Path) -> bool:
    """True if path is root of iOS project (has project.pbxproj or Package.swift at any depth)."""
    if not path.is_dir():
        return False
    # Check immediate children first for efficiency
    if (path / "Package.swift").is_file():
        return True
    for xcodeproj in path.glob("*.xcodeproj"):
        if (xcodeproj / "project.pbxproj").is_file():
            return True
    # Recurse for nested structures
    for candidate in path.rglob("project.pbxproj"):
        if candidate.is_file():
            return True
    for candidate in path.rglob("Package.swift"):
        if candidate.is_file():
            return True
    return False


def _sha256_file(path: Path) -> str:
    """Return lowercase hex SHA256 of file contents."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _get_ios_source_root(root: Path) -> Path | None:
    """Get and validate iOS source root from config. Returns None on error (diagnostic already printed)."""
    cfg = _load_config(root)
    if cfg is None:
        return None

    ios_value = cfg.get("ios")
    if not isinstance(ios_value, str) or not ios_value.strip():
        _diag("config key 'ios' is missing, empty, or not a string")
        return None

    ios_path = _resolve_path(ios_value, root)
    if ios_path is None:
        _diag(f"config key 'ios' could not be resolved: {ios_value!r}")
        return None

    if not ios_path.is_dir():
        _diag(f"iOS source directory does not exist: {ios_path}")
        return None

    if not _is_ios_project(ios_path):
        _diag(
            f"directory does not look like an iOS project "
            f"(no project.pbxproj or Package.swift found): {ios_path}"
        )
        return None

    # Validate binding: resources-inventory.json project_root must match
    inventory_path = root / "spec" / ".i2h" / "resources-inventory.json"
    if inventory_path.is_file():
        try:
            inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
            if isinstance(inventory, dict) and "project_root" in inventory:
                inv_root_str = inventory["project_root"]
                if isinstance(inv_root_str, str):
                    inv_root = _resolve_path(inv_root_str, root)
                    if inv_root and inv_root != ios_path:
                        _diag(
                            f"resources-inventory.json project_root mismatch: "
                            f"config ios={ios_path}, inventory project_root={inv_root}"
                        )
                        return None
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            pass  # If inventory is malformed, don't block

    # Validate binding: ui-delivery-approved.json source_project_root must match
    approved_path = root / "spec" / "baseline" / "ui-delivery-approved.json"
    if approved_path.is_file():
        try:
            approved = json.loads(approved_path.read_text(encoding="utf-8"))
            if isinstance(approved, dict) and "source_project_root" in approved:
                approved_root_str = approved["source_project_root"]
                if isinstance(approved_root_str, str):
                    approved_root = _resolve_path(approved_root_str, root)
                    if approved_root and approved_root != ios_path:
                        _diag(
                            f"ui-delivery-approved.json source_project_root mismatch: "
                            f"config ios={ios_path}, approved source_project_root={approved_root}"
                        )
                        return None
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            pass  # If approved is malformed, don't block

    return ios_path


# ---------------------------------------------------------------------------
# execute-source
# ---------------------------------------------------------------------------

def cmd_execute_source(root: Path) -> int:
    """Validate and print the iOS source root from .migbot/config.json."""
    ios_path = _get_ios_source_root(root)
    if ios_path is None:
        return 2

    print(str(ios_path))
    return 0


# ---------------------------------------------------------------------------
# execute-inputs
# ---------------------------------------------------------------------------

def cmd_execute_inputs(root: Path, argv: list[str]) -> int:
    """Read and report the current plan inputs and static resource facts."""
    # Validate iOS source first (shared with execute-source)
    ios_path = _get_ios_source_root(root)
    if ios_path is None:
        return 2

    # Strict argparse: reject unknown options and abbreviations
    parser = argparse.ArgumentParser(prog="i2h execute-inputs", add_help=False, allow_abbrev=False)
    parser.add_argument("--plan-format", default="indexed-v1")
    parser.add_argument("--resource-policy", default="static-v1")
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        _diag("unknown or invalid arguments")
        return 2

    plan_format = args.plan_format
    resource_policy = args.resource_policy

    plans_dir = root / "spec" / "baseline" / "plans"
    result: dict[str, Any] = {
        "plan_format": plan_format,
        "resource_policy": resource_policy,
    }

    # Plan inputs
    if plan_format == "indexed-v1":
        required = ["ui-plan.md", "feature-plan.md", "base-plan.md"]
        missing = [name for name in required if not (plans_dir / name).is_file()]
        if missing:
            _diag(
                "indexed-v1 plan files missing (use --plan-format legacy for "
                f"single-file mode): {', '.join(missing)}"
            )
            return 2

        # Verify slices directory exists
        slices_dir = plans_dir / "slices"
        if not slices_dir.is_dir():
            _diag("indexed-v1 requires slices directory: spec/baseline/plans/slices/")
            return 2

        # Verify feature-plan.md contains plan_format: indexed-v1 marker
        feature_plan = plans_dir / "feature-plan.md"
        try:
            feature_text = feature_plan.read_text(encoding="utf-8")
            if "plan_format: indexed-v1" not in feature_text and "plan_format:indexed-v1" not in feature_text:
                _diag("feature-plan.md missing 'plan_format: indexed-v1' marker")
                return 2
        except (OSError, UnicodeDecodeError) as exc:
            _diag(f"cannot read feature-plan.md: {exc}")
            return 2

        result["plans"] = {
            "ui_plan": str(plans_dir / "ui-plan.md"),
            "feature_plan": str(plans_dir / "feature-plan.md"),
            "base_plan": str(plans_dir / "base-plan.md"),
        }
        result["plans"]["slices_dir"] = str(slices_dir)
        result["plans"]["slice_count"] = len(list(slices_dir.glob("*.md")))
    elif plan_format == "legacy":
        legacy_plan = plans_dir / "execution-plan.md"
        if not legacy_plan.is_file():
            _diag("legacy plan file not found: spec/baseline/plans/execution-plan.md")
            return 2
        result["plans"] = {"execution_plan": str(legacy_plan)}
    else:
        _diag(f"unknown --plan-format: {plan_format!r}")
        return 2

    # Resource facts validation
    spec_i2h = root / "spec" / ".i2h"
    if resource_policy == "static-v1":
        # Read and validate target-input.json
        ti_path = spec_i2h / "target-input.json"
        if not ti_path.is_file():
            _diag(
                "static-v1 resource facts not found: spec/.i2h/target-input.json "
                "(run ui_evidence.py to produce, or use --resource-policy legacy)"
            )
            return 2

        try:
            target_input = json.loads(ti_path.read_text(encoding="utf-8"))
        except UnicodeDecodeError as exc:
            _diag(f"target-input.json contains invalid UTF-8: {exc}")
            return 2
        except (OSError, json.JSONDecodeError) as exc:
            _diag(f"target-input.json unreadable or invalid JSON: {exc}")
            return 2

        # Validate target-input.json structure
        if not isinstance(target_input, dict):
            _diag("target-input.json must be a JSON object")
            return 2

        schema_version = target_input.get("schema_version")
        target_hash = target_input.get("target_input_sha256")
        inventory_path_str = target_input.get("inventory")

        if schema_version != 1:
            _diag(f"target-input.json schema_version must be 1, got: {schema_version}")
            return 2

        if not isinstance(target_hash, str) or len(target_hash) != 64:
            _diag("target-input.json target_input_sha256 must be a 64-character hex string")
            return 2

        if not isinstance(inventory_path_str, str):
            _diag("target-input.json inventory must be a string path")
            return 2

        # Validate inventory file exists and matches hash
        inventory_path = _resolve_path(inventory_path_str, root)
        if not inventory_path or not inventory_path.is_file():
            _diag(f"inventory file not found: {inventory_path_str}")
            return 2

        try:
            inventory_data = json.loads(inventory_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            _diag(f"inventory file unreadable: {exc}")
            return 2

        if not isinstance(inventory_data, dict):
            _diag("inventory must be a JSON object")
            return 2

        # Validate inventory hash matches target_input_sha256
        inv_hash = inventory_data.get("target_input_sha256")
        if inv_hash != target_hash:
            _diag(
                f"inventory target_input_sha256 mismatch: "
                f"target-input={target_hash}, inventory={inv_hash}"
            )
            return 2

        # Validate project_root binding
        cfg = _load_config(root)
        if cfg:
            ios_value = cfg.get("ios")
            if ios_value:
                ios_path = _resolve_path(ios_value, root)
                inv_root_str = inventory_data.get("project_root")
                if isinstance(inv_root_str, str):
                    inv_root = _resolve_path(inv_root_str, root)
                    if ios_path and inv_root and inv_root != ios_path:
                        _diag(
                            f"inventory project_root mismatch with config ios: "
                            f"config={ios_path}, inventory={inv_root}"
                        )
                        return 2

        # Validate resource indexes
        res_index_dir = root / "spec" / "baseline" / "res-index"
        required_indexes = ["values.json", "drawables.json", "usage.json", "handoff.json"]

        for idx_name in required_indexes:
            idx_path = res_index_dir / idx_name
            if not idx_path.is_file():
                _diag(f"resource index missing: {idx_path}")
                return 2

            try:
                idx_data = json.loads(idx_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
                _diag(f"resource index {idx_name} unreadable: {exc}")
                return 2

            if not isinstance(idx_data, dict):
                _diag(f"resource index {idx_name} must be a JSON object")
                return 2

            # Validate hash matches
            idx_schema = idx_data.get("schema_version")
            idx_hash = idx_data.get("target_input_sha256")

            if idx_schema != 1:
                _diag(f"{idx_name} schema_version must be 1, got: {idx_schema}")
                return 2

            if idx_hash != target_hash:
                _diag(
                    f"{idx_name} target_input_sha256 mismatch: "
                    f"expected={target_hash}, got={idx_hash}"
                )
                return 2

        # Check optional design-tokens
        design_tokens_path = res_index_dir / "design-tokens.json"
        if design_tokens_path.is_file():
            try:
                dt_data = json.loads(design_tokens_path.read_text(encoding="utf-8"))
                if isinstance(dt_data, dict):
                    dt_hash = dt_data.get("target_input_sha256")
                    if dt_hash and dt_hash != target_hash:
                        _diag(f"design-tokens.json hash mismatch: expected={target_hash}, got={dt_hash}")
                        return 2
            except (OSError, json.JSONDecodeError, UnicodeDecodeError):
                pass  # Optional file, don't block if malformed

        # Validate approved scope
        approved_path = root / "spec" / "baseline" / "ui-delivery-approved.json"
        if not approved_path.is_file():
            _diag("ui-delivery-approved.json not found (required for static-v1)")
            return 2

        try:
            approved = json.loads(approved_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            _diag(f"ui-delivery-approved.json unreadable: {exc}")
            return 2

        if not isinstance(approved, dict):
            _diag("ui-delivery-approved.json must be a JSON object")
            return 2

        # Validate approved scope schema
        approved_schema = approved.get("schema_version")
        if approved_schema != 2:
            _diag(f"ui-delivery-approved.json schema_version must be 2, got: {approved_schema}")
            return 2

        approved_status = approved.get("status")
        if approved_status != "approved":
            _diag(f"ui-delivery-approved.json status must be 'approved', got: {approved_status}")
            return 2

        approved_hash = approved.get("target_input_sha256")
        if approved_hash != target_hash:
            _diag(
                f"ui-delivery-approved.json target_input_sha256 mismatch: "
                f"expected={target_hash}, got={approved_hash}"
            )
            return 2

        # Validate source_project_root binding
        approved_root_str = approved.get("source_project_root")
        if cfg and ios_value and isinstance(approved_root_str, str):
            approved_root = _resolve_path(approved_root_str, root)
            if ios_path and approved_root and approved_root != ios_path:
                _diag(
                    f"ui-delivery-approved.json source_project_root mismatch: "
                    f"config ios={ios_path}, approved={approved_root}"
                )
                return 2

        approved_units = approved.get("units")
        if not isinstance(approved_units, list):
            _diag("ui-delivery-approved.json must have 'units' array")
            return 2

        if not approved_units:
            _diag("ui-delivery-approved.json units array must not be empty")
            return 2

        # Check for unresolved resources in selected scope
        usage_path = res_index_dir / "usage.json"
        try:
            usage_data = json.loads(usage_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            _diag(f"usage.json unreadable: {exc}")
            return 2

        if not isinstance(usage_data, dict):
            _diag("usage.json must be a JSON object")
            return 2

        resources = usage_data.get("resources")
        if not isinstance(resources, dict):
            _diag("usage.json resources must be a dict")
            return 2

        # Build set of selected source files from approved units
        selected_files = set()
        for unit in approved_units:
            if isinstance(unit, dict):
                source_refs = unit.get("source_refs")
                if isinstance(source_refs, list):
                    for ref in source_refs:
                        if isinstance(ref, dict):
                            ref_file = ref.get("file")
                            if ref_file:
                                selected_files.add(ref_file)

        if not selected_files:
            _diag("approved units must have non-empty source_refs")
            return 2

        # Check for unresolved resources in selected files
        # Separate system symbols (target mapping obligations) from missing assets
        system_symbol_obligations = []

        for resource_name, resource_info in resources.items():
            if not isinstance(resource_info, dict):
                continue

            resolved = resource_info.get("resolved")
            disposition = resource_info.get("disposition")
            references = resource_info.get("references")

            if not isinstance(references, list):
                continue

            # Check if any reference is in selected scope
            in_selected_scope = False
            has_system_symbol = False
            has_regular_asset = False

            for ref in references:
                if not isinstance(ref, dict):
                    continue

                ref_file = ref.get("file")
                ref_kind = ref.get("kind")

                if ref_file in selected_files:
                    in_selected_scope = True
                    if ref_kind == "system_symbol":
                        has_system_symbol = True
                    elif ref_kind in ("image", "color", "localization"):
                        has_regular_asset = True

            # Only check resources in selected scope
            if in_selected_scope and (not resolved or disposition == "unresolved"):
                # If it's ONLY system symbols, record as mapping obligation
                if has_system_symbol and not has_regular_asset:
                    for ref in references:
                        if isinstance(ref, dict) and ref.get("kind") == "system_symbol":
                            system_symbol_obligations.append({
                                "name": ref.get("name"),
                                "source_file": ref.get("file"),
                                "source_line": ref.get("line"),
                                "kind": "system_symbol"
                            })
                else:
                    # Regular missing asset blocks execution
                    _diag(
                        f"BLOCKED: unresolved resource in selected scope: "
                        f"{resource_name} (disposition={disposition}, resolved={resolved})"
                    )
                    return 2

        # Compute approved manifest SHA
        approved_sha = _sha256_file(approved_path)

        result["resources"] = {
            "schema_version": schema_version,
            "target_input_sha256": target_hash,
            "inventory": inventory_path_str,
            "approved_manifest_sha256": approved_sha,
            "approved_units_count": len(approved_units),
        }

        if system_symbol_obligations:
            result["resources"]["system_symbol_target_mapping_obligations"] = system_symbol_obligations

    elif resource_policy == "legacy":
        # Legacy also requires approved scope
        approved_path = root / "spec" / "baseline" / "ui-delivery-approved.json"
        if not approved_path.is_file():
            _diag("ui-delivery-approved.json not found (required even for legacy)")
            return 2

        try:
            approved = json.loads(approved_path.read_text(encoding="utf-8"))
            if not isinstance(approved, dict):
                _diag("ui-delivery-approved.json must be a JSON object")
                return 2
            if approved.get("status") != "approved":
                _diag("legacy resource policy requires approved scope")
                return 2
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            _diag(f"ui-delivery-approved.json unreadable: {exc}")
            return 2

        result["resources"] = {
            "mode": "legacy",
            "note": "explicitly selected legacy resource scope",
            "approved_manifest_sha256": _sha256_file(approved_path),
        }
    else:
        _diag(f"unknown --resource-policy: {resource_policy!r}")
        return 2

    print(json.dumps(result, ensure_ascii=False))
    return 0


# ---------------------------------------------------------------------------
# retrospect-metrics
# ---------------------------------------------------------------------------

def _count_sources(root_path: Path, suffixes: set[str], excluded_dirs: set[str]) -> dict[str, Any]:
    """Count lines in source files; return MEASURED or UNKNOWN.

    Uses os.walk with explicit error handling and no symlink following.
    """
    if not root_path or not root_path.is_dir():
        return {"status": "UNKNOWN", "total_lines": None, "files": None,
                "reason": "directory not found"}

    by_type: dict[str, int] = {}
    file_count = 0
    total = 0

    def on_error(err: OSError) -> None:
        """Raise on walk errors to trigger UNKNOWN status."""
        raise err

    try:
        for dirpath_str, dirnames, filenames in os.walk(str(root_path), onerror=on_error, followlinks=False):
            dirpath = Path(dirpath_str)

            # Skip symlink directories
            if dirpath.is_symlink():
                continue

            # Prune excluded directories by relative path
            try:
                rel = dirpath.relative_to(root_path)
                rel_parts = set(rel.parts)
                if rel_parts & excluded_dirs:
                    dirnames[:] = []  # Don't descend into this tree
                    continue
            except ValueError:
                continue

            # Also prune subdirectories that match exclusion names
            dirnames[:] = [d for d in dirnames if d not in excluded_dirs]

            for filename in filenames:
                filepath = dirpath / filename

                # Skip symlinks
                if filepath.is_symlink():
                    continue

                suffix = filepath.suffix.lower()
                if suffix not in suffixes:
                    continue

                try:
                    text = filepath.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    return {"status": "UNKNOWN", "total_lines": None, "files": None,
                            "reason": f"bad UTF-8 in {filepath.name}"}
                except OSError as exc:
                    return {"status": "UNKNOWN", "total_lines": None, "files": None,
                            "reason": f"cannot read {filepath.name}: {exc}"}

                lines = text.count('\n')
                # If file doesn't end with newline, the last line still counts
                if text and not text.endswith('\n'):
                    lines += 1

                key = suffix.lstrip(".")
                by_type[key] = by_type.get(key, 0) + lines
                total += lines
                file_count += 1

    except OSError as exc:
        return {"status": "UNKNOWN", "total_lines": None, "files": None,
                "reason": f"traversal error: {exc}"}

    return {
        "status": "MEASURED",
        "total_lines": total,
        "files": file_count,
        "by_type": dict(sorted(by_type.items()))
    }


def _count_lines_ios(ios_path: Path) -> dict[str, Any]:
    """Count lines in Swift/ObjC source files; return MEASURED or UNKNOWN."""
    return _count_sources(ios_path, _SWIFT_SUFFIXES, _EXCLUDED_IOS)


def _count_lines_hmos(hmos_path: Path, root: Path) -> dict[str, Any]:
    """Count lines in ArkTS/TS files under entry/src/main/ets; return MEASURED or UNKNOWN."""
    if not hmos_path or not hmos_path.is_dir():
        return {"status": "UNKNOWN", "total_lines": None, "files": None,
                "reason": "harmonyos directory not found"}

    # If harmonyos points to a different project (not current root), reject
    try:
        hmos_path.relative_to(root)
    except ValueError:
        return {"status": "UNKNOWN", "total_lines": None, "files": None,
                "reason": f"harmonyos path points to different project: {hmos_path}"}

    scan_root = hmos_path / "entry" / "src" / "main" / "ets"

    if not scan_root.exists():
        return {"status": "UNKNOWN", "total_lines": None, "files": None,
                "reason": "entry/src/main/ets directory not found"}

    if not scan_root.is_dir():
        return {"status": "UNKNOWN", "total_lines": None, "files": None,
                "reason": "entry/src/main/ets is not a directory"}

    # Empty ets directory is MEASURED 0
    result = _count_sources(scan_root, _ARKTS_SUFFIXES, _EXCLUDED_HMOS)
    if result["status"] == "MEASURED":
        result["path"] = str(hmos_path)
    return result


def cmd_retrospect_metrics(root: Path) -> int:
    """Print per-direction line-count metrics as JSON."""
    cfg = _load_config(root)

    ios_value = cfg.get("ios") if cfg else None
    hmos_value = cfg.get("harmonyos") if cfg else None

    ios_path = _resolve_path(ios_value, root) if ios_value else None

    # Resolve harmonyos path; if it points to a different project, that's UNKNOWN
    if hmos_value:
        hmos_path = _resolve_path(hmos_value, root)
    else:
        hmos_path = root

    ios_metrics = _count_lines_ios(ios_path) if ios_path else {
        "status": "UNKNOWN", "total_lines": None, "files": None,
        "reason": "ios path not configured"
    }
    if ios_metrics["status"] == "MEASURED" and ios_path:
        ios_metrics["path"] = str(ios_path)

    hmos_metrics = _count_lines_hmos(hmos_path, root)

    # Build receipts structure
    receipts: dict[str, Any] = {}

    # Get current target_input_sha256
    current_target_hash: str | None = None
    target_input_path = root / "spec" / ".i2h" / "target-input.json"
    if target_input_path.is_file():
        try:
            ti_data = json.loads(target_input_path.read_text(encoding="utf-8"))
            if isinstance(ti_data, dict):
                current_target_hash = ti_data.get("target_input_sha256")
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            pass

    # Load marker_contract for stage resolution and validation
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        import marker_contract
    except ImportError:
        marker_contract = None

    # Execute receipt
    if marker_contract:
        execute_resolution = marker_contract.resolve_stage(root, "i2h-execute")
        if execute_resolution.complete:
            marker_path = execute_resolution.paths[0]
            marker_sha = _sha256_file(marker_path)

            # Validate marker
            validation = marker_contract.validate_marker(
                marker_path, "i2h-execute",
                expected_hash=current_target_hash,
                root=root
            )

            if validation.get("valid") and current_target_hash:
                receipts["execute"] = {
                    "status": "BOUND",
                    "path": str(marker_path),
                    "sha256": marker_sha,
                    "target_input_sha256": current_target_hash,
                    "validation": validation
                }
            else:
                receipts["execute"] = {
                    "status": "UNKNOWN",
                    "path": str(marker_path),
                    "sha256": marker_sha,
                    "reason": f"validation failed or hash mismatch: {validation.get('errors', [])}",
                    "validation": validation
                }
        else:
            receipts["execute"] = {
                "status": "UNKNOWN",
                "reason": "execute marker not found or incomplete"
            }
            if execute_resolution.paths:
                observed_marker = execute_resolution.paths[0]
                receipts["execute"]["path"] = str(observed_marker)
                try:
                    receipts["execute"]["sha256"] = _sha256_file(observed_marker)
                except OSError as exc:
                    receipts["execute"]["sha256"] = None
                    receipts["execute"]["reason"] = str(exc)
    else:
        receipts["execute"] = {
            "status": "UNKNOWN",
            "reason": "marker_contract module not available"
        }

    # Verify receipt
    if marker_contract:
        verify_resolution = marker_contract.resolve_stage(root, "i2h-verify")
        if verify_resolution.paths:
            verify_path = verify_resolution.paths[0]
            verify_sha = _sha256_file(verify_path)
            receipts["verify"] = {
                "status": "RECORDED_UNVERIFIED",
                "path": str(verify_path),
                "sha256": verify_sha,
                "reason": "markdown report exists but lacks provable run binding"
            }
        else:
            receipts["verify"] = {
                "status": "UNKNOWN",
                "reason": "verify report not found"
            }
    else:
        receipts["verify"] = {
            "status": "UNKNOWN",
            "reason": "marker_contract module not available"
        }

    # Timing receipt
    timing_records = []
    timing_dir = root / "spec" / ".i2h" / "timing"
    try:
        if timing_dir.is_dir() and not timing_dir.is_symlink():
            for json_file in sorted(timing_dir.glob("*.json")):
                if json_file.is_file() and not json_file.is_symlink():
                    timing_records.append({
                        "path": str(json_file),
                        "sha256": _sha256_file(json_file)
                    })
    except OSError:
        receipts["timing"] = {
            "status": "UNKNOWN",
            "reason": "failed to enumerate timing directory"
        }
        timing_records = None

    if timing_records is not None:
        stage_marks = root / ".migbot" / "metrics" / root.name / "stage-marks.jsonl"
        timing_error = None
        try:
            if stage_marks.is_file() and not stage_marks.is_symlink():
                timing_records.append({
                    "path": str(stage_marks),
                    "sha256": _sha256_file(stage_marks)
                })
        except OSError as exc:
            timing_error = str(exc)

        if timing_error:
            receipts["timing"] = {
                "status": "UNKNOWN", "reason": timing_error,
                "candidates": timing_records,
            }
        elif len(timing_records) == 1:
            receipts["timing"] = {
                "status": "RECORDED_UNVERIFIED",
                "path": timing_records[0]["path"],
                "sha256": timing_records[0]["sha256"]
            }
        elif len(timing_records) > 1:
            receipts["timing"] = {
                "status": "RECORDED_UNVERIFIED",
                "candidates": timing_records,
                "reason": "multiple timing records found; cannot determine unique run binding"
            }
        else:
            receipts["timing"] = {
                "status": "UNKNOWN",
                "reason": "no timing records found"
            }

    # Usage receipt
    receipts["usage"] = {
        "status": "UNKNOWN",
        "total_cost_usd": None,
        "reason": "no bound usage receipt for current run"
    }

    result = {
        "ios": ios_metrics,
        "harmonyos": hmos_metrics,
        "receipts": receipts
    }
    print(json.dumps(result, ensure_ascii=False))
    return 0
