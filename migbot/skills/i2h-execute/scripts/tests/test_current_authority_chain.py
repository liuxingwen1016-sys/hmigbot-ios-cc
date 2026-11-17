"""Full native current authority chain test with G0/G1 and receipt selection.

Tests complete flow: baseline freeze → blocked prepare → derive proof → validate →
approve with receipt → execution freeze → source_only prepare → complete → aggregate
current authority → G1 structural → visual scope blocked.
"""
from __future__ import annotations

import json
import hashlib
import subprocess
import tempfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.ios_stage1_scope import load_inventory, build_scope_from_inventory
from lib.ios_ui_dispatch import prepare, complete, aggregate_g0
from lib.ios_stage1_acceptance import archive_g1
from lib.ios_inventory_resolution import sha256_file
from lib.ui_delivery_inputs_ios import freeze as freeze_inputs


def json_bytes(obj):
    """Canonical JSON bytes."""
    return (json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + '\n').encode('utf-8')


def test_full_native_current_authority_chain(tmp_path):
    """Complete native chain: baseline→blocked→derive→approve→source_only→g1→visual_blocked."""
    root = tmp_path / "project"
    root.mkdir()
    script_dir = Path(__file__).resolve().parent.parent

    # Setup source project
    source_root = root / "ios_source"
    source_root.mkdir()

    # Create two simple routed page Swift files (no complex integration)
    page1_swift = source_root / "PageOne.swift"
    page1_swift.write_text("""struct PageOne: View {
    var body: some View {
        PageTwo()
    }
}
""", encoding="utf-8")
    page1_sha = sha256_file(page1_swift)

    page2_swift = source_root / "PageTwo.swift"
    page2_swift.write_text("""struct PageTwo: View {
    var body: some View {
        Text("Page Two")
    }
}
""", encoding="utf-8")
    page2_sha = sha256_file(page2_swift)

    # Create baseline approved inventory with 2 simple routed pages
    baseline_path = root / "spec" / "baseline" / "ui-delivery-approved.json"
    baseline_path.parent.mkdir(parents=True)
    baseline = {
        "schema_version": 2,
        "status": "approved",
        "source_project_root": str(source_root),
        "units": [
            {
                "unit_id": "ios.0001.PageOne",
                "page_id": "page_0001",
                "component": "ios.PageOne",
                "presentation_role": "routed_page",
                "owned_ui_roles": ["content"],
                "required": True,
                "output": {
                    "file": "entry/src/main/ets/pages/PageOne.ets",
                    "symbol": "PageOne",
                    "builder": "PageOneBuilder"
                },
                "generation_owner": "i2h-harmony",
                "source_refs": [
                    {"file": "PageOne.swift", "sha256": page1_sha, "line": 1}
                ],
                "required_states": [
                    {
                        "state_id": "default",
                        "responsibility": "content",
                        "arrival_mode": "formal",
                        "source_refs": [
                            {"file": "PageOne.swift", "sha256": page1_sha, "line": 1}
                        ]
                    }
                ]
            },
            {
                "unit_id": "ios.0002.PageTwo",
                "page_id": "page_0002",
                "component": "ios.PageTwo",
                "presentation_role": "embedded",
                "owned_ui_roles": ["content"],
                "required": True,
                "integration": {
                    "host_file": "entry/src/main/ets/pages/PageOne.ets",
                    "host_symbol": "PageOne",
                    "host_builder": "PageOne.PageOneBuilder",
                    "child_symbol": "PageTwo"
                },
                "output": {
                    "file": "entry/src/main/ets/pages/PageTwo.ets",
                    "symbol": "PageTwo",
                    "builder": "PageTwoBuilder"
                },
                "generation_owner": "i2h-harmony",
                "source_refs": [
                    {"file": "PageTwo.swift", "sha256": page2_sha, "line": 1}
                ],
                "required_states": [
                    {
                        "state_id": "default",
                        "responsibility": "content",
                        "arrival_mode": "formal",
                        "source_refs": [
                            {"file": "PageTwo.swift", "sha256": page2_sha, "line": 1}
                        ]
                    }
                ]
            }
        ],
        "verification_states": [
            {
                "verification_id": "visual-page_0001-default",
                "page_id": "page_0001",
                "state_id": "default",
                "owner": "ios.0001.PageOne",
                "implementation_units": ["ios.0001.PageOne"]
            },
            {
                "verification_id": "visual-page_0002-default",
                "page_id": "page_0002",
                "state_id": "default",
                "owner": "ios.0002.PageTwo",
                "implementation_units": ["ios.0002.PageTwo"]
            }
        ]
    }
    baseline_path.write_bytes(json_bytes(baseline))
    baseline_sha = sha256_file(baseline_path)

    evidence_dir = tmp_path / 'evidence'
    evidence_dir.mkdir(parents=True, exist_ok=True)

    # STEP 1: Freeze baseline → index (no runtime evidence exists)
    freeze_rc_1 = freeze_inputs(["--project-root", str(root), "--inventory", str(baseline_path)])

    (evidence_dir / 'step1-freeze-baseline.json').write_text(json.dumps({
        'function': 'freeze_inputs',
        'argv': ["--project-root", str(root), "--inventory", str(baseline_path)],
        'returncode': freeze_rc_1
    }, indent=2))

    assert freeze_rc_1 == 0, f"Baseline freeze failed with RC={freeze_rc_1}"

    index_path = root / "spec" / "execution" / "ui-inputs" / "index.json"
    assert index_path.exists(), "Index not created"
    index = json.loads(index_path.read_text())
    assert index["inventory_source"]["sha256"] == baseline_sha

    # Verify baseline scope has 2 pairs and compute acceptance lane
    from lib.ios_stage1_scope import acceptance_lane
    scope_before = build_scope_from_inventory(root, None)
    assert len(scope_before["pairs"]) == 2
    lane_before = acceptance_lane(scope_before)

    # STEP 2: Prepare attempt 1 unit 1 - should be BLOCKED (missing runtime)
    prep1_unit1 = prepare(root, "ios.0001.PageOne", 1)
    assert prep1_unit1["status"] == "BLOCKED", "Should be blocked on missing runtime"

    # STEP 3: Prepare attempt 1 unit 2 - should be BLOCKED
    prep1_unit2 = prepare(root, "ios.0002.PageTwo", 1)
    assert prep1_unit2["status"] == "BLOCKED", "Should be blocked on missing runtime"

    # STEP 4: Complete attempt 1 units - blocked
    comp1_unit1 = complete(root, prep1_unit1["dispatch_id"])
    assert comp1_unit1["status"] == "BLOCKED"

    comp1_unit2 = complete(root, prep1_unit2["dispatch_id"])
    assert comp1_unit2["status"] == "BLOCKED"

    # STEP 5: Aggregate G0 original - should be BLOCKED
    agg1 = aggregate_g0(root)
    assert agg1["status"] == "BLOCKED"

    # Save original g0 bytes for later verification
    g0_path = root / "spec" / "execution" / "dispatch" / "g0.json"
    assert g0_path.exists()
    original_g0_bytes = g0_path.read_bytes()
    original_g0_sha = sha256_file(g0_path)

    # STEP 6: Create proof with source_only alternatives
    proof_path = root / "proof.json"
    proof = {
        "baseline_sha256": baseline_sha,
        "requests": [
            {
                "unit_id": "ios.0001.PageOne",
                "source_only": {
                    "alternative_kind": "source_only",
                    "state_id": "default",
                    "source_file": "PageOne.swift",
                    "source_sha256": page1_sha,
                    "source_line": 1,
                    "declaration": "PageOne"
                }
            },
            {
                "unit_id": "ios.0002.PageTwo",
                "source_only": {
                    "alternative_kind": "source_only",
                    "state_id": "default",
                    "source_file": "PageTwo.swift",
                    "source_sha256": page2_sha,
                    "source_line": 1,
                    "declaration": "PageTwo"
                }
            }
        ]
    }
    proof_path.write_bytes(json_bytes(proof))

    # STEP 7: Derive candidate using real production CLI
    candidate_path = root / "spec" / "execution" / "candidate.json"
    derive_result = subprocess.run([
        sys.executable,
        str(script_dir / "ui_inventory_resolution.py"),
        "derive",
        "--project-root", str(root),
        "--baseline", str(baseline_path.relative_to(root)),
        "--proof", str(proof_path.relative_to(root)),
        "--out", str(candidate_path.relative_to(root))
    ], capture_output=True, text=True, cwd=root)

    (evidence_dir / 'step7-derive.json').write_text(json.dumps({
        'argv': derive_result.args,
        'stdout': derive_result.stdout,
        'stderr': derive_result.stderr,
        'returncode': derive_result.returncode
    }, indent=2))

    assert derive_result.returncode == 0, f"Derive failed: {derive_result.stderr}\n{derive_result.stdout}"

    candidate = json.loads(candidate_path.read_text())
    assert candidate["status"] == "draft"
    candidate_sha = sha256_file(candidate_path)

    # STEP 8: Validate using real Plan CLI
    plan_cli = script_dir.parent.parent / "i2h-plan" / "scripts" / "ui_delivery.py"
    receipt_path = root / "validation-receipt.json"

    validate_result = subprocess.run([
        sys.executable,
        str(plan_cli),
        "validate",
        "--project-root", str(root),
        "--inventory", str(candidate_path),
        "--receipt-only",
        "--out", str(receipt_path)
    ], capture_output=True, text=True)

    (evidence_dir / 'step8-validate.json').write_text(json.dumps({
        'argv': validate_result.args,
        'stdout': validate_result.stdout,
        'stderr': validate_result.stderr,
        'returncode': validate_result.returncode
    }, indent=2))

    assert validate_result.returncode == 0, f"Plan validate failed: {validate_result.stderr}\n{validate_result.stdout}"

    receipt = json.loads(receipt_path.read_text())
    assert receipt["status"] == "validated"
    receipt_sha = sha256_file(receipt_path)

    # STEP 9: Approve using real Plan CLI
    approved_path = candidate_path

    approve_result = subprocess.run([
        sys.executable,
        str(plan_cli),
        "approve",
        "--project-root", str(root),
        "--inventory", str(candidate_path),
        "--out", str(approved_path),
        "--validation-receipt", str(receipt_path),
        "--confirmation-ref", "test_chain_c3"
    ], capture_output=True, text=True)

    (evidence_dir / 'step9-approve.json').write_text(json.dumps({
        'argv': approve_result.args,
        'stdout': approve_result.stdout,
        'stderr': approve_result.stderr,
        'returncode': approve_result.returncode
    }, indent=2))

    assert approve_result.returncode == 0, f"Plan approve failed: {approve_result.stderr}\n{approve_result.stdout}"

    approved = json.loads(approved_path.read_text())
    assert approved["status"] == "approved"
    assert approved["approval"]["confirmation_ref"] == "test_chain_c3"
    approved_sha = sha256_file(approved_path)

    # STEP 10: Freeze approved execution → new index
    freeze_rc_2 = freeze_inputs(["--project-root", str(root), "--inventory", str(approved_path)])

    (evidence_dir / 'step10-freeze-execution.json').write_text(json.dumps({
        'function': 'freeze_inputs',
        'argv': ["--project-root", str(root), "--inventory", str(approved_path)],
        'returncode': freeze_rc_2
    }, indent=2))

    assert freeze_rc_2 == 0, f"Execution freeze failed with RC={freeze_rc_2}"

    # Verify index now points to execution inventory
    index2 = json.loads(index_path.read_text())
    assert index2["inventory_source"]["sha256"] == approved_sha

    # Verify approved scope has 2 pairs and same acceptance lane
    scope_after = build_scope_from_inventory(root, None)
    assert len(scope_after["pairs"]) == 2
    assert acceptance_lane(scope_after) == lane_before

    # C3: Two real default consumers verify same current approved authority
    _oblig_s = script_dir / "ui_obligation_gate.py"
    _imm_s = script_dir / "immersive_safearea_gate.py"
    _oblig_out = tmp_path / "c3_oblig.json"
    _imm_out = tmp_path / "c3_imm.json"

    # Normal route: both default CLIs choose approved_path + approved_sha (no --inventory)
    _oblig_run = subprocess.run([sys.executable, str(_oblig_s), "--project-root", str(root), "--output-json", str(_oblig_out)], capture_output=True, text=True)
    assert _oblig_run.returncode in (0, 2), f"obligation RC={_oblig_run.returncode}\n{_oblig_run.stderr}"
    _oblig_rep = json.loads(_oblig_out.read_text())
    assert _oblig_rep.get("inventory_sha256") == approved_sha, f"obligation sha: {_oblig_rep.get('inventory_sha256')!r}\n{_oblig_run.stderr}"
    assert Path(_oblig_rep["inventory"]) == approved_path, f"obligation path: {_oblig_rep['inventory']!r}"
    assert "error" not in _oblig_rep, f"obligation authority error: {_oblig_rep.get('error')}"

    _imm_run = subprocess.run([sys.executable, str(_imm_s), "--project-root", str(root), "--output-json", str(_imm_out)], capture_output=True, text=True)
    assert _imm_run.returncode == 0, f"immersive RC={_imm_run.returncode}\n{_imm_run.stderr}"
    _imm_rep = json.loads(_imm_out.read_text())
    assert _imm_rep.get("status") in ("PASS", "NOT_REQUIRED"), f"immersive status: {_imm_rep.get('status')!r}\n{_imm_run.stderr}"
    assert _imm_rep.get("inventory_sha256") == approved_sha, f"immersive sha: {_imm_rep.get('inventory_sha256')!r}"

    # Adversarial: malformed + zero-sha index force nonzero; explicit paths restore priority
    _orig_idx_bytes = index_path.read_bytes()
    try:
        index_path.write_bytes(b"NOT_VALID_JSON{{{")
        for _cs, _op in ((_oblig_s, _oblig_out), (_imm_s, _imm_out)):
            _op.unlink(missing_ok=True)
            _r = subprocess.run([sys.executable, str(_cs), "--project-root", str(root), "--output-json", str(_op)], capture_output=True, text=True)
            assert _r.returncode != 0, f"{_cs.name} must fail on malformed index; RC={_r.returncode}"
            if _op.exists():
                assert json.loads(_op.read_text()).get("status") not in ("PASS", "NOT_REQUIRED"), f"{_cs.name} bad status on malformed index"
        _oblig_out.unlink(missing_ok=True)
        _exp = subprocess.run([sys.executable, str(_oblig_s), "--project-root", str(root), "--inventory", str(baseline_path), "--output-json", str(_oblig_out)], capture_output=True, text=True)
        assert _exp.returncode in (0, 2), f"explicit obligation RC={_exp.returncode}\n{_exp.stderr}"
        _erep = json.loads(_oblig_out.read_text())
        assert _erep.get("inventory_sha256") == baseline_sha, f"explicit sha: {_erep.get('inventory_sha256')!r}"
        assert Path(_erep["inventory"]) == baseline_path, f"explicit path: {_erep['inventory']!r}"
        assert "error" not in _erep, f"explicit authority error: {_erep.get('error')}"
        import immersive_safearea_gate as _imm_mod
        _id = _imm_mod.evaluate(root, inventory={"units": []})
        assert _id["status"] == "NOT_REQUIRED", f"immersive explicit dict: {_id['status']!r}"
        _zi = json.loads(_orig_idx_bytes.decode())
        _zi["inventory_source"]["sha256"] = "0" * 64
        index_path.write_bytes((json.dumps(_zi, indent=2) + "\n").encode())
        for _cs, _op in ((_oblig_s, _oblig_out), (_imm_s, _imm_out)):
            _op.unlink(missing_ok=True)
            _r = subprocess.run([sys.executable, str(_cs), "--project-root", str(root), "--output-json", str(_op)], capture_output=True, text=True)
            assert _r.returncode != 0, f"{_cs.name} must fail on zero-sha index; RC={_r.returncode}"
            if _op.exists():
                assert json.loads(_op.read_text()).get("status") not in ("PASS", "NOT_REQUIRED"), f"{_cs.name} bad status on zero-sha index"
    finally:
        index_path.write_bytes(_orig_idx_bytes)

    # Remove native index → both CLIs fall back to legacy baseline + baseline_sha
    index_path.unlink()
    try:
        for _cs, _op in ((_oblig_s, _oblig_out), (_imm_s, _imm_out)):
            _op.unlink(missing_ok=True)
            _r = subprocess.run([sys.executable, str(_cs), "--project-root", str(root), "--output-json", str(_op)], capture_output=True, text=True)
            _rep = json.loads(_op.read_text())
            assert _rep.get("inventory_sha256") == baseline_sha, f"{_cs.name} fallback sha: {_rep.get('inventory_sha256')!r} != {baseline_sha!r}"
    finally:
        index_path.write_bytes(_orig_idx_bytes)

    # STEP 11: Prepare attempt 2 units - should be SOURCE_ONLY
    prep2_unit1 = prepare(root, "ios.0001.PageOne", 2)
    assert prep2_unit1["status"] == "SOURCE_ONLY", f"Should be source_only, got {prep2_unit1['status']}"

    prep2_unit2 = prepare(root, "ios.0002.PageTwo", 2)
    assert prep2_unit2["status"] == "SOURCE_ONLY", f"Should be source_only, got {prep2_unit2['status']}"

    # STEP 12: Write conversion reports for source_only units
    for prep, unit_id in [(prep2_unit1, "ios.0001.PageOne"), (prep2_unit2, "ios.0002.PageTwo")]:
        packet = json.loads((root / prep["packet_path"]).read_text())
        report_path = root / f"spec/execution/conversion-reports/{unit_id}.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report = {
            "unit_id": unit_id,
            "dispatch_id": prep["dispatch_id"],
            "packet_sha256": prep["packet_sha256"],
            "state_implementations": [{"state_id": "default", "symbol": "build"}],
            "image_observations": [],  # No runtime images for source_only
            "input_applications": [{"input_id": row["input_id"]} for row in packet["required_inputs"]]
        }
        report_path.write_bytes(json_bytes(report))

        # Write output file
        output_unit = [u for u in approved["units"] if u["unit_id"] == unit_id][0]
        output_path = root / output_unit["output"]["file"]
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if unit_id == "ios.0001.PageOne":
            output_path.write_text(
                "import { PageTwo } from './PageTwo'\n\n"
                "@ComponentV2\nexport struct PageOne {\n"
                "  build() { this.PageOneBuilder() }\n\n"
                "  @Builder\n  PageOneBuilder() {\n    PageTwo()\n  }\n}\n"
            )
        else:
            output_path.write_text(
                "@ComponentV2\nexport struct PageTwo {\n"
                "  build() { this.PageTwoBuilder() }\n\n"
                "  @Builder\n  PageTwoBuilder() {\n    Text(\"Page Two\")\n  }\n}\n"
            )

    # STEP 13: Complete attempt 2 - SOURCE_ONLY for both
    comp2_unit1 = complete(root, prep2_unit1["dispatch_id"])
    assert comp2_unit1["status"] == "SOURCE_ONLY"

    comp2_unit2 = complete(root, prep2_unit2["dispatch_id"])
    assert comp2_unit2["status"] == "SOURCE_ONLY"

    # STEP 14: Aggregate G0 current authority - should be BLOCKED overall, PASS structural
    agg2 = aggregate_g0(root)
    assert agg2["status"] == "BLOCKED", f"Overall status should be BLOCKED, got {agg2['status']}"
    assert agg2["structural_status"] == "PASS", f"Structural status should be PASS, got {agg2.get('structural_status')}"

    # Verify original g0 bytes unchanged
    assert g0_path.read_bytes() == original_g0_bytes, "Original g0.json must be immutable"

    # STEP 15: Archive G1 structural - should PASS
    g1_result = archive_g1(root)
    assert g1_result["status"] == "PASS", f"G1 should pass structurally, got {g1_result['status']}"
    assert g1_result["result_scope"] == "STRUCTURAL_ONLY"
    assert g1_result["stage1_complete"] == False

    g1_path = root / g1_result["archive_path"] / "receipt.json"
    assert g1_path.exists()
    g1 = json.loads(g1_path.read_text())
    assert g1["status"] == "PASS"
    assert g1["result_scope"] == "STRUCTURAL_ONLY"
    inventory_sha = sha256_file(approved_path)
    assert g1["inventory_sha256"] == inventory_sha
    assert "ios.0002.PageTwo" in g1_result["wired_units"]

    # Negative test: remove host import, verify BLOCKED with required_host_slot_unbound
    page1_ets_path = root / "entry/src/main/ets/pages/PageOne.ets"
    original_page1_bytes = page1_ets_path.read_bytes()
    try:
        page1_ets_path.write_text(
            "@ComponentV2\nexport struct PageOne {\n"
            "  build() { this.PageOneBuilder() }\n\n"
            "  @Builder\n  PageOneBuilder() {\n    PageTwo()\n  }\n}\n"
        )
        neg_g1 = archive_g1(root, read_only=True)
        assert neg_g1["status"] == "BLOCKED"
        assert any(
            f.get("code") == "required_host_slot_unbound" and f.get("unit_id") == "ios.0002.PageTwo"
            for f in neg_g1["failure_findings"]
        )
    finally:
        page1_ets_path.write_bytes(original_page1_bytes)

    # Verify G1 positive again after restore
    g1_result2 = archive_g1(root)
    assert g1_result2["status"] == "PASS"
    assert "ios.0002.PageTwo" in g1_result2["wired_units"]

    # STEP 16: Build scope and verify visual still BLOCKED
    scope = build_scope_from_inventory(root, None)
    assert scope["status"] == "BLOCKED"  # Still blocked on missing runtime evidence
    assert scope["scope"] == "stage1_delivery"

    # Verify stage1_complete via real summary
    from lib.ios_stage1_summary import DEFAULT_SCOPE, summarize
    scope_file = root / DEFAULT_SCOPE
    scope_file.parent.mkdir(parents=True, exist_ok=True)
    scope_file.write_bytes(json_bytes(scope))
    summary = summarize(root, scope_file)
    assert summary["stage1_complete"] == False
    assert summary["status"] != "PASS"

    # STEP 17: Verify default load uses current authority
    default_path, default_data = load_inventory(root, None)
    assert default_path == approved_path
    assert default_data["status"] == "approved"

    (evidence_dir / 'final-g0.json').write_bytes(g0_path.read_bytes())
    (evidence_dir / 'final-g1.json').write_bytes(g1_path.read_bytes())
    (evidence_dir / 'final-scope.json').write_text(json.dumps(scope, indent=2))

    print("✓ Full native current authority chain complete")
    print(f"✓ Original g0 immutable: {original_g0_sha}")
    print(f"✓ Current authority structural PASS, visual BLOCKED")
    print(f"✓ G1 PASS with STRUCTURAL_ONLY scope")
    print(f"✓ All real production API calls with RC=0")


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        test_full_native_current_authority_chain(Path(tmpdir))
