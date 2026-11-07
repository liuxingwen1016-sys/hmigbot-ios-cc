#!/usr/bin/env python3
"""Deterministic, offline end-to-end contract test for the iOS pipeline.

This test intentionally stops at the boundary where a simulator, ``hdc`` or
DevEco is required.  It verifies the artifacts and recovery semantics that can
run in CI on a clean machine, and records the unavailable runtime checks as
``DEFERRED`` instead of manufacturing a PASS.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path
import sys


REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "fixtures/e2e-ios-hybrid"
SPEC_SCRIPTS = REPO / "migbot/skills/i2h-spec/scripts"
PLAN_SCRIPTS = REPO / "migbot/skills/i2h-plan/scripts"
EXECUTE_SCRIPTS = REPO / "migbot/skills/i2h-execute/scripts"
for path in (SPEC_SCRIPTS, PLAN_SCRIPTS, EXECUTE_SCRIPTS):
    sys.path.insert(0, str(path))

import ui_delivery  # noqa: E402
import ui_evidence  # noqa: E402
import ui_state_ownership  # noqa: E402
import source_layout  # noqa: E402
sys.path.insert(0, str(REPO / "migbot/bin/scripts/pipeline"))
import marker_contract  # noqa: E402
import pipeline_resume  # noqa: E402


STAGES = (
    ("i2h-spec", Path("spec/baseline/spec-complete.txt")),
    ("i2h-plan", Path("spec/baseline/plans/complete.txt")),
    ("i2h-execute", Path("spec/execution/stage5-complete.txt"), Path("spec/migration-report.md")),
    ("i2h-verify", Path("spec/verify-report.md")),
    ("i2h-retrospect", Path("spec/retrospect-complete.txt")),
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, value: str | dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, dict):
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    else:
        path.write_text(value, encoding="utf-8")


def _marker(root: Path, path: Path, stage: str, target_hash: str, artifacts=()) -> None:
    marker_contract.write_marker(
        path,
        stage,
        artifacts,
        target_hash,
        root=root,
        fixture=True,
    )


def next_stage(root: Path, target_hash: str | None = None) -> str:
    """Return the first incomplete stage using the real /i2h-run checker."""
    return pipeline_resume.pipeline_status(root)["resume_stage"]


def _make_reports(harmony: Path, target_hash: str) -> None:
    """Write truthful static-only execute/verify/retrospect artifacts."""
    for index in range(6):
        brief = harmony / f"spec/execution/briefs/stage{index}-fixture.md"
        _write(brief, f"# Stage {index} fixture brief\n\nmode: static-only\n")
        _marker(
            harmony,
            harmony / f"spec/execution/stage{index}-complete.txt",
            f"i2h-execute-stage{index}",
            target_hash,
            [brief],
        )
    _write(harmony / "spec/execution/briefs/stage1-spec-understanding.md",
           "# Stage 1 fixture brief\n\nmode: static-only\n")
    _write(harmony / "spec/execution/briefs/stage2-feature-design.md", "# Stage 2 fixture brief\n")
    _write(harmony / "spec/execution/briefs/stage3-code-generation.md", "# Stage 3 fixture brief\n")
    _write(harmony / "spec/execution/briefs/stage4-build-verification.md", "# Stage 4 fixture brief\n")
    _write(harmony / "spec/migration-report.md", """# iOS → HarmonyOS fixture migration report

- mode: `static-only`
- source evidence: PASS
- ArkTS output: PASS (fixture skeleton)
- hvigor/DevEco build: DEFERRED (environment not present)
- device install and runtime screenshots: DEFERRED (no simulator/device)
""")
    _write(harmony / "spec/verify-report.md", """# Verification report

| Check | Status | Evidence |
|---|---|---|
| CHECK-1 static ArkTS analysis | PASS | fixture source scan |
| CHECK-2 app identity | PASS | AppScope/app.json5 |
| CHECK-3 runtime behavior | DEFERRED | no hdc/simulator |
| CHECK-4 visual comparison | DEFERRED | no runtime frame |
| CHECK-5 Android oracle | SKIP | iOS source has no Android oracle |

mode: `static-only`
""")
    _write(harmony / "docs/retrospect-report-fixture.md", """# Fixture retrospect

The static source/resource contracts passed. Runtime and DevEco build checks
remain `DEFERRED`; this report does not claim a device or compiler result.
""")
    # The stage5 marker is written after all artifacts so its content hashes
    # bind the report and generated ArkTS pages to this execution.
    _marker(
        harmony,
        harmony / "spec/execution/stage5-complete.txt",
        "i2h-execute",
        target_hash,
        [
            "spec/migration-report.md",
            "spec/execution/ui-state-ownership.json",
            "entry/src/main/ets/pages/HomeView.ets",
            "entry/src/main/ets/pages/DetailViewController.ets",
        ],
    )
    _marker(
        harmony,
        harmony / "spec/retrospect-complete.txt",
        "i2h-retrospect",
        target_hash,
        ["docs/retrospect-report-fixture.md"],
    )


def run_fixture() -> dict:
    temp = tempfile.TemporaryDirectory(prefix="hmigbot-e2e-")
    root = Path(temp.name)
    try:
        fixture = root / "fixture"
        shutil.copytree(FIXTURE, fixture)
        ios = fixture / "ios-app"
        harmony = fixture / "harmony-app"
        evidence_path = harmony / "spec/.i2h/resources-inventory.json"
        res_index = harmony / "spec/baseline/res-index"
        evidence = ui_evidence.run(str(ios), str(evidence_path), str(res_index))
        skeleton = ui_evidence.build_skeleton(evidence)
        _write(harmony / "spec/.i2h/project-skeleton.json", skeleton)
        target_hash = evidence["target_input_sha256"]

        view_types = {row["type"] for row in evidence["views"]}
        assert "SwiftUI View" in view_types and "UIKit ViewController" in view_types
        assert evidence["resources"]["summary"]["catalog_count"] == 1
        assert evidence["resources"]["summary"]["localization_languages"] == 1
        assert skeleton["target_input_sha256"] == target_hash
        index_rows = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(res_index.glob("*.json"))]
        assert {path.stem for path in res_index.glob("*.json")} >= {"values", "drawables", "usage", "design-tokens", "handoff"}
        assert all(row.get("target_input_sha256") == target_hash for row in index_rows)

        layout = source_layout.extract(ios)
        out = harmony / "spec/baseline/source-layout.json"
        _write(out, layout)
        assert len(layout["sources"]) == 3
        delivery = ui_delivery.draft(harmony, harmony / "spec/baseline/ui-delivery-draft.json")
        # Draft defaults are intentionally conservative. The fixture makes
        # ownership explicit before validation rather than accepting a shared
        # `default/content` state for two source views.
        for unit, state_id, output_file in zip(
            delivery["units"], ("home", "detail"), ("entry/src/main/ets/pages/HomeView.ets", "entry/src/main/ets/pages/DetailViewController.ets")
        ):
            unit["required_states"][0]["state_id"] = state_id
            unit["required_states"][0]["arrival_mode"] = "preview"
            unit["output"]["file"] = output_file
        delivery["presentation"].update({"runtime_required": False, "mode": "static-only"})
        checked = ui_delivery.validate(harmony, delivery)
        assert checked["status"] == "validated", checked
        approved = ui_delivery.approve(harmony, checked, "fixture:static-review")
        _write(harmony / "spec/baseline/ui-delivery-approved.json", approved)
        ownership = ui_state_ownership.review(harmony, approved)
        assert ownership["status"] == "PASS", ownership
        _write(harmony / "spec/execution/ui-state-ownership.json", ownership)

        _marker(
            harmony,
            harmony / "spec/baseline/spec-complete.txt",
            "i2h-spec",
            target_hash,
            ["spec/.i2h/resources-inventory.json"],
        )
        _marker(
            harmony,
            harmony / "spec/baseline/plans/complete.txt",
            "i2h-plan",
            target_hash,
            ["spec/baseline/ui-delivery-approved.json"],
        )
        assert next_stage(harmony, target_hash) == "i2h-execute"
        _make_reports(harmony, target_hash)
        assert next_stage(harmony, target_hash) == "complete"
        (harmony / "spec/verify-report.md").unlink()
        assert next_stage(harmony, target_hash) == "i2h-verify"
        _write(harmony / "spec/verify-report.md", "# restored static-only verify\n\nCHECK-1: PASS\n")
        # A restored verify report without the original migration report is not
        # enough to finish retrospect; recreate the truthful report and resume.
        (harmony / "spec/migration-report.md").unlink()
        assert next_stage(harmony, target_hash) == "i2h-execute"
        _write(harmony / "spec/migration-report.md", "# restored\nmode: static-only\nbuild: DEFERRED\n")
        _marker(
            harmony,
            harmony / "spec/execution/stage5-complete.txt",
            "i2h-execute",
            target_hash,
            [
                "spec/migration-report.md",
                "spec/execution/ui-state-ownership.json",
                "entry/src/main/ets/pages/HomeView.ets",
                "entry/src/main/ets/pages/DetailViewController.ets",
            ],
        )
        assert next_stage(harmony, target_hash) == "complete"
        return {"target_input_sha256": target_hash, "views": len(evidence["views"]), "root": fixture}
    finally:
        temp.cleanup()


class OfflineI2HFixtureTest(unittest.TestCase):
    def test_full_static_only_pipeline_and_resume_contract(self):
        result = run_fixture()
        self.assertEqual(result["views"], 2)
        self.assertRegex(result["target_input_sha256"], r"^[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main(verbosity=2)
