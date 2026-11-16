#!/usr/bin/env python3
"""Test ui_delivery.validate fails-closed on placeholder/invalid host fields.

Covers the executor bypass patterns from the live project:
- Unknown/None presentation_role for required units
- host_file not safe relative POSIX .ets  (absolute, backslash, .swift, .ts, etc.)
- host_builder / child_symbol filled with placeholder text
- Required hosted/embedded slots missing any of the 3 host fields

Positive tests confirm planned future .ets hosts (that don't exist yet) pass.
Validation is exercised via the public ui_delivery.validate() contract.
"""
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parents[1]))
import ui_delivery

_MODULE = Path(sys.modules['ui_delivery'].__file__).resolve()
_REPO_ROOT = Path(__file__).resolve().parents[4]
assert _MODULE.is_relative_to(_REPO_ROOT), f"Module not under clean repo: {_MODULE}"
print(f"  ui_delivery: {_MODULE}")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _schema2_inventory(unit_id: str = "u1", page_id: str = "page_0001_Home",
                       role: str = "routed_page",
                       output_symbol: str = "MyPage",
                       output_file: str = "entry/ets/pages/MyPage.ets",
                       integration: Optional[list] = None) -> dict:
    unit = {
        "unit_id": unit_id,
        "page_id": page_id,
        "output": {"file": output_file, "symbol": output_symbol},
        "presentation_role": role,
        "owned_ui_roles": ["content"],
        "required_states": [{"state_id": "default", "responsibility": "content"}],
        "source_refs": [],
    }
    if integration is not None:
        unit["integration"] = integration
    return {"schema_version": 2, "units": [unit]}


def _codes(validate_result: dict) -> set[str]:
    return {e.get("code") for e in validate_result.get("validation", {}).get("errors", [])}


def _call(inv: dict) -> dict:
    return ui_delivery.validate("/tmp/fake_root", inv)


# ---------------------------------------------------------------------------
# presentation_role tests
# ---------------------------------------------------------------------------

def test_unknown_role_string_rejected():
    """Non-enum string role (e.g. 'UNRESOLVED') produces PRESENTATION_ROLE_UNKNOWN."""
    inv = _schema2_inventory(role="UNRESOLVED")
    assert "PRESENTATION_ROLE_UNKNOWN" in _codes(_call(inv)), \
        "String 'UNRESOLVED' must be rejected"
    print("✅ PASS: 'UNRESOLVED' role rejected")


def test_known_roles_accepted():
    """Each supported role must NOT produce PRESENTATION_ROLE_UNKNOWN."""
    for role in ("routed_page", "hosted_destination", "embedded"):
        inv = _schema2_inventory(role=role)
        codes = _codes(_call(inv))
        assert "PRESENTATION_ROLE_UNKNOWN" not in codes, \
            f"Role '{role}' must be accepted; errors={codes}"
    print("✅ PASS: all 3 known roles accepted")


def test_none_role_required_unit_rejected():
    """presentation_role=None for a required unit must produce PRESENTATION_ROLE_UNKNOWN."""
    inv = _schema2_inventory(role=None, integration=None)
    inv["units"][0]["presentation_role"] = None
    inv["units"][0]["required"] = True  # explicitly required
    codes = _codes(_call(inv))
    assert "PRESENTATION_ROLE_UNKNOWN" in codes, \
        f"None role for required unit must be rejected; got {codes}"
    print("✅ PASS: None role for required unit rejected")


def test_none_role_with_integration_slot_rejected():
    """presentation_role=None with an integration slot must produce PRESENTATION_ROLE_UNKNOWN."""
    inv = _schema2_inventory(role=None, integration=[{
        "host_file": "entry/ets/pages/Host.ets",
        "host_builder": "Builder",
        "child_symbol": "MyPage",
    }])
    inv["units"][0]["presentation_role"] = None
    codes = _codes(_call(inv))
    assert "PRESENTATION_ROLE_UNKNOWN" in codes, \
        f"None role with integration slot must be rejected; got {codes}"
    print("✅ PASS: None role + integration slot rejected")


# ---------------------------------------------------------------------------
# host_file path tests
# ---------------------------------------------------------------------------

def test_unresolved_host_file_rejected():
    inv = _schema2_inventory(role="embedded", integration=[{
        "host_file": "UNRESOLVED",
        "host_builder": "Builder",
        "child_symbol": "MyPage",
    }])
    assert "HOST_FILE_PLACEHOLDER" in _codes(_call(inv))
    print("✅ PASS: UNRESOLVED host_file rejected")


def test_swift_host_file_rejected():
    """Any non-.ets extension (including .swift) must be rejected."""
    for bad in ("iOS/Views/Home.swift", "src/pages/Home.ts", "data/style.txt"):
        inv = _schema2_inventory(role="embedded", integration=[{
            "host_file": bad,
            "host_builder": "Builder",
            "child_symbol": "MyPage",
        }])
        codes = _codes(_call(inv))
        assert "HOST_FILE_NOT_ETS" in codes, \
            f"Non-.ets extension '{bad}' must be rejected; got {codes}"
    print("✅ PASS: .swift / .ts / .txt host_file rejected (HOST_FILE_NOT_ETS)")


def test_absolute_unix_host_file_rejected():
    inv = _schema2_inventory(role="embedded", integration=[{
        "host_file": "/abs/path/Page.ets",
        "host_builder": "Builder",
        "child_symbol": "MyPage",
    }])
    assert "HOST_FILE_ABSOLUTE_PATH" in _codes(_call(inv))
    print("✅ PASS: absolute Unix path rejected")


def test_backslash_host_file_rejected():
    inv = _schema2_inventory(role="embedded", integration=[{
        "host_file": "entry\\ets\\pages\\Host.ets",
        "host_builder": "Builder",
        "child_symbol": "MyPage",
    }])
    assert "HOST_FILE_BACKSLASH_PATH" in _codes(_call(inv))
    print("✅ PASS: backslash path rejected")


def test_path_traversal_rejected():
    inv = _schema2_inventory(role="embedded", integration=[{
        "host_file": "../outside/Host.ets",
        "host_builder": "Builder",
        "child_symbol": "MyPage",
    }])
    assert "HOST_FILE_PATH_TRAVERSAL" in _codes(_call(inv))
    print("✅ PASS: path traversal (..) rejected")


def test_future_planned_ets_host_accepted():
    """Relative .ets path that doesn't exist yet — must NOT produce host errors."""
    inv = _schema2_inventory(
        role="embedded",
        output_symbol="PlannedPage",
        output_file="entry/ets/pages/PlannedPage.ets",
        integration=[{
            "host_file": "entry/ets/pages/ContainerPage.ets",  # planned, not on disk
            "host_builder": "entry.ContainerPageBuilder",
            "child_symbol": "PlannedPage",
        }],
    )
    codes = _codes(_call(inv))
    host_errors = {c for c in codes if c.startswith("HOST_") or c.startswith("CHILD_")}
    assert not host_errors, f"Future planned .ets should not error; got: {host_errors}"
    print("✅ PASS: future planned .ets host accepted")


# ---------------------------------------------------------------------------
# host_builder / child_symbol tests
# ---------------------------------------------------------------------------

def test_placeholder_host_builder_rejected():
    for bad in ("TODO", "PLACEHOLDER", ""):
        inv = _schema2_inventory(role="hosted_destination", integration=[{
            "host_file": "entry/ets/pages/Host.ets",
            "host_builder": bad,
            "child_symbol": "MyPage",
        }])
        assert "HOST_BUILDER_PLACEHOLDER" in _codes(_call(inv)), \
            f"host_builder '{bad!r}' must be rejected"
    print("✅ PASS: placeholder host_builder rejected")


def test_placeholder_child_symbol_rejected():
    inv = _schema2_inventory(role="hosted_destination", integration=[{
        "host_file": "entry/ets/pages/Host.ets",
        "host_builder": "Builder",
        "child_symbol": "UNRESOLVED",
    }])
    assert "CHILD_SYMBOL_PLACEHOLDER" in _codes(_call(inv))
    print("✅ PASS: UNRESOLVED child_symbol rejected")


def test_child_symbol_mismatch_rejected():
    inv = _schema2_inventory(
        role="embedded",
        output_symbol="RealSymbol",
        integration=[{
            "host_file": "entry/ets/pages/Host.ets",
            "host_builder": "Builder",
            "child_symbol": "WrongSymbol",
        }],
    )
    assert "CHILD_SYMBOL_MISMATCH" in _codes(_call(inv))
    print("✅ PASS: child_symbol != output.symbol rejected")


# ---------------------------------------------------------------------------
# required fields for hosted/embedded roles
# ---------------------------------------------------------------------------

def test_hosted_destination_requires_all_three_fields():
    """hosted_destination with any missing field produces HOST_FIELD_REQUIRED."""
    for missing in ("host_file", "host_builder", "child_symbol"):
        slot = {
            "host_file": "entry/ets/pages/Host.ets",
            "host_builder": "Builder",
            "child_symbol": "MyPage",
        }
        del slot[missing]
        inv = _schema2_inventory(role="hosted_destination", integration=[slot])
        codes = _codes(_call(inv))
        assert "HOST_FIELD_REQUIRED" in codes, \
            f"hosted_destination missing '{missing}' must produce HOST_FIELD_REQUIRED; got {codes}"
    print("✅ PASS: hosted_destination requires all 3 host fields")


def test_embedded_requires_all_three_fields():
    """embedded with any missing field produces HOST_FIELD_REQUIRED."""
    for missing in ("host_file", "host_builder", "child_symbol"):
        slot = {
            "host_file": "entry/ets/pages/Host.ets",
            "host_builder": "Builder",
            "child_symbol": "MyPage",
        }
        del slot[missing]
        inv = _schema2_inventory(role="embedded", integration=[slot])
        codes = _codes(_call(inv))
        assert "HOST_FIELD_REQUIRED" in codes, \
            f"embedded missing '{missing}' must produce HOST_FIELD_REQUIRED; got {codes}"
    print("✅ PASS: embedded requires all 3 host fields")


def test_hosted_destination_empty_integration_rejected():
    """hosted_destination with no integration slots produces INTEGRATION_REQUIRED."""
    inv = _schema2_inventory(role="hosted_destination", integration=None)
    codes = _codes(_call(inv))
    assert "INTEGRATION_REQUIRED" in codes, \
        f"hosted_destination with no integration must be rejected; got {codes}"
    print("✅ PASS: hosted_destination requires integration slots")


def test_embedded_empty_integration_rejected():
    """embedded with no integration slots produces INTEGRATION_REQUIRED."""
    inv = _schema2_inventory(role="embedded", integration=[])
    codes = _codes(_call(inv))
    assert "INTEGRATION_REQUIRED" in codes, \
        f"embedded with empty integration must be rejected; got {codes}"
    print("✅ PASS: embedded requires integration slots")


if __name__ == "__main__":
    import traceback
    failures = 0
    tests = [
        ("unknown_role", test_unknown_role_string_rejected),
        ("known_roles", test_known_roles_accepted),
        ("none_role_required", test_none_role_required_unit_rejected),
        ("none_role_with_slot", test_none_role_with_integration_slot_rejected),
        ("unresolved_host", test_unresolved_host_file_rejected),
        ("non_ets_extension", test_swift_host_file_rejected),
        ("absolute_unix", test_absolute_unix_host_file_rejected),
        ("backslash", test_backslash_host_file_rejected),
        ("traversal", test_path_traversal_rejected),
        ("future_ets", test_future_planned_ets_host_accepted),
        ("placeholder_builder", test_placeholder_host_builder_rejected),
        ("placeholder_child", test_placeholder_child_symbol_rejected),
        ("child_mismatch", test_child_symbol_mismatch_rejected),
        ("hosted_requires_fields", test_hosted_destination_requires_all_three_fields),
        ("embedded_requires_fields", test_embedded_requires_all_three_fields),
        ("hosted_empty_integration", test_hosted_destination_empty_integration_rejected),
        ("embedded_empty_integration", test_embedded_empty_integration_rejected),
    ]
    for name, fn in tests:
        try:
            fn()
        except Exception as exc:
            print(f"\n❌ {name}: {exc}")
            traceback.print_exc()
            failures += 1

    if failures:
        print(f"\n❌ {failures} test(s) failed")
        sys.exit(1)
    print("\n✅ All UI delivery host validation tests passed")
    sys.exit(0)
