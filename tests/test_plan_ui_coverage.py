#!/usr/bin/env python3
"""
Tests for i2h-plan UI coverage linter (lint_plan_coverage.py)

Validates:
1. Complete approved inventory parsing (142 source units, 136 required)
2. Required vs excluded page filtering
3. Legacy manifest compatibility (when no approved inventory exists)
4. Actual missing page detection with genuine failure
"""

import importlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

# Add migbot to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import from hyphenated directory using importlib
lint_module = importlib.import_module('migbot.skills.i2h-plan.scripts.lint_plan_coverage')
PlanCoverageLinter = lint_module.PlanCoverageLinter


class TestUIPageCoverage(unittest.TestCase):
    """Test UI page coverage checker with approved inventory"""

    def setUp(self):
        """Create temporary test project structure"""
        self.temp_dir = tempfile.mkdtemp()
        self.project_root = Path(self.temp_dir)
        self.spec_dir = self.project_root / "spec" / "baseline"
        self.plans_dir = self.spec_dir / "plans"
        self.spec_dir.mkdir(parents=True)
        self.plans_dir.mkdir(parents=True)

        # Create minimal required files
        (self.spec_dir / "feature-index.md").write_text("# Feature Index\n")
        (self.plans_dir / "feature-plan.md").write_text("# Feature Plan\n")

    def tearDown(self):
        """Clean up temporary directory"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_approved_inventory(self, units):
        """Create ui-delivery-approved.json with given units"""
        inventory = {
            "schema_version": 2,
            "tool_version": "i2h-ui-delivery/1.1",
            "status": "approved",
            "units": units
        }
        inventory_path = self.spec_dir / "ui-delivery-approved.json"
        with open(inventory_path, 'w') as f:
            json.dump(inventory, f, indent=2)

    def _create_minimal_required_files(self):
        """Create minimal required files for linter"""
        (self.spec_dir / "feature-index.md").write_text("# Feature Index\n")
        (self.spec_dir / "ui-manifest.md").write_text("# UI Manifest\n")
        (self.plans_dir / "feature-plan.md").write_text("# Feature Plan\n")

    def _create_ui_plan(self, page_ids):
        """Create ui-plan.md covering given page IDs"""
        content = "# UI Plan\n\n"
        for pid in page_ids:
            content += f"- {pid}\n"
        (self.plans_dir / "ui-plan.md").write_text(content)

    def _create_legacy_manifest(self, pages_with_status):
        """Create legacy ui-manifest.md (sample data only)"""
        content = "# UI Manifest\n\n| Page ID | Class | Status |\n|---------|-------|--------|\n"
        for pid, status in pages_with_status:
            content += f"| {pid} | TestClass | {status} |\n"
        (self.spec_dir / "ui-manifest.md").write_text(content)

    def test_full_approved_inventory_parsing(self):
        """Test parsing complete approved inventory (>=12 required units)"""
        # Create realistic inventory with 14 units: 12 required + 2 excluded
        units = []
        for i in range(1, 13):  # 12 required pages
            units.append({
                "unit_id": f"ios.{i:04d}.TestView",
                "page_id": f"page_{i:04d}_TestView",
                "required": True
            })
        for i in range(13, 15):  # 2 excluded pages
            units.append({
                "unit_id": f"ios.{i:04d}.LegacyView",
                "page_id": f"page_{i:04d}_LegacyView",
                "required": False
            })

        self._create_approved_inventory(units)
        self._create_ui_plan([f"page_{i:04d}_TestView" for i in range(1, 13)])

        linter = PlanCoverageLinter(str(self.project_root))
        linter._check_ui_page_coverage()

        # Should have exactly one result for UI coverage
        ui_results = [r for r in linter.results if "UI 页面" in r.name]
        self.assertEqual(len(ui_results), 1)

        result = ui_results[0]
        self.assertTrue(result.passed, "Should pass with all required pages covered")
        self.assertEqual(result.actual, 12, "Should cover 12 required pages")
        self.assertEqual(result.total, 12, "Should have 12 required pages total")

        # Check diagnostic warning about excluded pages
        self.assertTrue(any("14 页面" in w and "12 required" in w and "2 excluded"
                           for w in result.warnings),
                       "Should report source count with required/excluded breakdown")

    def test_missing_required_page_genuine_failure(self):
        """Test that missing 11th of 12 required pages causes genuine failure"""
        # Create 12 required + 2 excluded
        units = []
        for i in range(1, 13):
            units.append({
                "unit_id": f"ios.{i:04d}.TestView",
                "page_id": f"page_{i:04d}_TestView",
                "required": True
            })
        for i in range(13, 15):
            units.append({
                "unit_id": f"ios.{i:04d}.LegacyView",
                "page_id": f"page_{i:04d}_LegacyView",
                "required": False
            })

        self._create_approved_inventory(units)
        # Deliberately omit page_0011 (cover only 11 of 12)
        covered = [f"page_{i:04d}_TestView" for i in range(1, 11)]  # 1-10 only
        covered.append("page_0012_TestView")  # Add 12, skip 11
        self._create_ui_plan(covered)

        linter = PlanCoverageLinter(str(self.project_root))
        linter._check_ui_page_coverage()

        ui_results = [r for r in linter.results if "UI 页面" in r.name]
        self.assertEqual(len(ui_results), 1)

        result = ui_results[0]
        self.assertFalse(result.passed, "Should FAIL with missing required page")
        self.assertEqual(result.actual, 11, "Should show 11/12 covered")
        self.assertEqual(result.total, 12, "Should show 12 required total")
        self.assertTrue(result.blocking, "Should be blocking failure")

        # Check error mentions the specific missing page
        self.assertTrue(any("page_0011" in e for e in result.errors),
                       f"Should report missing page_0011, got errors: {result.errors}")

    def test_excluded_pages_not_inflating_required_count(self):
        """Test that required=false pages don't inflate required denominator"""
        units = []
        # 3 required pages
        for i in range(1, 4):
            units.append({
                "unit_id": f"ios.{i:04d}.MainView",
                "page_id": f"page_{i:04d}_MainView",
                "required": True
            })
        # 5 excluded pages
        for i in range(4, 9):
            units.append({
                "unit_id": f"ios.{i:04d}.LegacyView",
                "page_id": f"page_{i:04d}_LegacyView",
                "required": False
            })

        self._create_approved_inventory(units)
        # Cover only the 3 required pages
        self._create_ui_plan([f"page_{i:04d}_MainView" for i in range(1, 4)])

        linter = PlanCoverageLinter(str(self.project_root))
        linter._check_ui_page_coverage()

        ui_results = [r for r in linter.results if "UI 页面" in r.name]
        result = ui_results[0]

        self.assertTrue(result.passed, "Should pass covering only required pages")
        self.assertEqual(result.actual, 3, "Should show 3 required covered")
        self.assertEqual(result.total, 3, "Should show 3 required total (not 8)")

        # Verify source count diagnostic includes excluded
        self.assertTrue(any("8 页面" in w and "3 required" in w and "5 excluded" in w
                           for w in result.warnings),
                       "Should report 8 total source pages with breakdown")

    def test_legacy_manifest_compatibility(self):
        """Test fallback to legacy ui-manifest.md when no approved inventory"""
        # Create legacy manifest with 10 pages (sample only)
        pages = [(f"page_{i:04d}_View", "active") for i in range(1, 11)]
        self._create_legacy_manifest(pages)
        self._create_ui_plan([f"page_{i:04d}_View" for i in range(1, 11)])

        linter = PlanCoverageLinter(str(self.project_root))
        linter._check_ui_page_coverage()

        ui_results = [r for r in linter.results if "UI 页面" in r.name]
        result = ui_results[0]

        self.assertTrue(result.passed, "Should pass with legacy manifest")
        self.assertEqual(result.actual, 10, "Should cover 10 pages from manifest")
        self.assertEqual(result.total, 10, "Should have 10 pages from manifest")

    def test_legacy_manifest_skipped_pages(self):
        """Test legacy manifest with skipped status"""
        pages = [
            (f"page_{i:04d}_View", "active") for i in range(1, 6)
        ] + [
            (f"page_{i:04d}_Legacy", "skipped") for i in range(6, 9)
        ]
        self._create_legacy_manifest(pages)
        # Cover only active pages
        self._create_ui_plan([f"page_{i:04d}_View" for i in range(1, 6)])

        linter = PlanCoverageLinter(str(self.project_root))
        linter._check_ui_page_coverage()

        ui_results = [r for r in linter.results if "UI 页面" in r.name]
        result = ui_results[0]

        self.assertTrue(result.passed, "Should pass ignoring skipped pages")
        self.assertEqual(result.actual, 5, "Should cover 5 active pages")
        self.assertEqual(result.total, 5, "Should have 5 required (non-skipped)")

    def test_explicit_counts_all_required(self):
        """Test explicit source/required/excluded counts shown even when all pages required"""
        # Create inventory with ALL pages required (no exclusions)
        units = []
        for i in range(1, 13):
            units.append({
                "unit_id": f"ios.{i:04d}.TestView",
                "page_id": f"page_{i:04d}_TestView",
                "required": True
            })

        self._create_approved_inventory(units)
        self._create_minimal_required_files()
        self._create_ui_plan([f"page_{i:04d}_TestView" for i in range(1, 13)])

        linter = PlanCoverageLinter(str(self.project_root))
        linter._check_ui_page_coverage()

        ui_results = [r for r in linter.results if "UI 页面" in r.name]
        result = ui_results[0]

        self.assertTrue(result.passed, "Should pass with all required covered")
        self.assertEqual(result.actual, 12, "Should show 12 covered")
        self.assertEqual(result.total, 12, "Should show 12 required")

        # Must have explicit count diagnostic even with no exclusions
        self.assertTrue(any("12 页面: 12 required, 0 excluded" in w for w in result.warnings),
                       f"Should show explicit counts even when all required, got: {result.warnings}")
        """Test page_NNNN_ClassName normalization to page_NNNN"""
        units = [
            {
                "unit_id": "ios.0001.TestView",
                "page_id": "page_0001_TestView",
                "required": True
            },
            {
                "unit_id": "ios.0002.AnotherView",
                "page_id": "page_0002_AnotherView",
                "required": True
            }
        ]
        self._create_approved_inventory(units)

        # Plan uses various formats (all should normalize to page_NNNN)
        plan_content = """# UI Plan

- page_0001_TestView (full canonical)
- page_0002 (bare numeric)
"""
        (self.plans_dir / "ui-plan.md").write_text(plan_content)

        linter = PlanCoverageLinter(str(self.project_root))
        linter._check_ui_page_coverage()

        ui_results = [r for r in linter.results if "UI 页面" in r.name]
        result = ui_results[0]

        self.assertTrue(result.passed, "Should pass with normalized IDs")
        self.assertEqual(result.actual, 2, "Should match 2 pages via normalization")

    def test_malformed_inventory_blocks(self):
        """Test malformed approved inventory causes blocking failure (not silent fallback)"""
        # Create malformed JSON
        inventory_path = self.spec_dir / "ui-delivery-approved.json"
        inventory_path.write_text("{ invalid json }")

        # Create minimal files (no legacy manifest fallback)
        (self.spec_dir / "feature-index.md").write_text("# Feature Index\n")
        (self.plans_dir / "feature-plan.md").write_text("# Feature Plan\n")
        (self.plans_dir / "ui-plan.md").write_text("# UI Plan\n")
        (self.spec_dir / "ui-manifest.md").write_text("# UI Manifest\n")

        linter = PlanCoverageLinter(str(self.project_root))
        linter._check_ui_page_coverage()

        # Should have blocking finding for malformed JSON
        blocking_findings = [f for f in linter.findings if f.get('severity') == 'blocking']
        self.assertGreater(len(blocking_findings), 0,
                          "Should have blocking finding for malformed JSON")
        self.assertTrue(any('JSON' in f.get('message', '') for f in blocking_findings),
                       "Should report JSON parsing error")

    def test_empty_units_blocks(self):
        """Test approved inventory with empty units array causes blocking failure"""
        inventory = {
            "schema_version": 2,
            "tool_version": "i2h-ui-delivery/1.1",
            "status": "approved",
            "units": []
        }
        inventory_path = self.spec_dir / "ui-delivery-approved.json"
        with open(inventory_path, 'w') as f:
            json.dump(inventory, f)

        self._create_minimal_required_files()

        linter = PlanCoverageLinter(str(self.project_root))
        linter._check_ui_page_coverage()

        blocking_findings = [f for f in linter.findings if f.get('severity') == 'blocking']
        self.assertGreater(len(blocking_findings), 0,
                          "Should have blocking finding for empty units")
        self.assertTrue(any('empty units' in f.get('message', '').lower() for f in blocking_findings),
                       "Should report empty units error")

    def test_duplicate_normalized_page_id_blocks(self):
        """Test duplicate normalized page IDs cause blocking failure"""
        units = [
            {
                "unit_id": "ios.0001.ViewA",
                "page_id": "page_0001_ViewA",
                "required": True
            },
            {
                "unit_id": "ios.0001.ViewB",
                "page_id": "page_0001_ViewB",  # Same normalized ID as above
                "required": True
            }
        ]
        self._create_approved_inventory(units)
        self._create_minimal_required_files()

        linter = PlanCoverageLinter(str(self.project_root))
        linter._check_ui_page_coverage()

        blocking_findings = [f for f in linter.findings if f.get('severity') == 'blocking']
        self.assertGreater(len(blocking_findings), 0,
                          "Should have blocking finding for duplicate normalized ID")
        self.assertTrue(any('duplicate' in f.get('message', '').lower() for f in blocking_findings),
                       f"Should report duplicate page_id, got: {blocking_findings}")

    def test_unresolvable_page_id_blocks(self):
        """Test unresolvable page_id format causes blocking failure"""
        units = [
            {
                "unit_id": "ios.0001.Valid",
                "page_id": "page_0001_Valid",
                "required": True
            },
            {
                "unit_id": "ios.9999.Invalid",
                "page_id": "invalid_format_no_page_prefix",
                "required": True
            }
        ]
        self._create_approved_inventory(units)
        self._create_minimal_required_files()

        linter = PlanCoverageLinter(str(self.project_root))
        linter._check_ui_page_coverage()

        blocking_findings = [f for f in linter.findings if f.get('severity') == 'blocking']
        self.assertGreater(len(blocking_findings), 0,
                          "Should have blocking finding for unresolvable page_id")
        self.assertTrue(any('unresolvable' in f.get('message', '').lower() for f in blocking_findings),
                       "Should report unresolvable page_id")

    def test_formal_ui_docs_fallback_positive(self):
        """Test formal UI docs (>=12) used as fallback when inventory absent, full plan passes"""
        # Create formal UI docs directory with 12 doc files
        ui_docs_dir = self.spec_dir / "ui"
        ui_docs_dir.mkdir()
        for i in range(1, 13):
            doc_file = ui_docs_dir / f"page_{i:04d}_TestView.md"
            doc_file.write_text(f"# page_{i:04d}_TestView\n\nFormal UI documentation\n")

        # Create sample manifest with only 10 rows (should be ignored when formal docs exist)
        sample_manifest = "# UI Manifest\n\n| Page ID | Class |\n|---------|-------|\n"
        for i in range(1, 11):
            sample_manifest += f"| page_{i:04d}_SampleView | SampleView |\n"
        (self.spec_dir / "ui-manifest.md").write_text(sample_manifest)

        # Create minimal required files
        (self.spec_dir / "feature-index.md").write_text("# Feature Index\n")
        (self.plans_dir / "feature-plan.md").write_text("# Feature Plan\n")

        # Create plan covering all 12 formal docs
        plan_content = "# UI Plan\n\n"
        for i in range(1, 13):
            plan_content += f"- page_{i:04d}_TestView\n"
        (self.plans_dir / "ui-plan.md").write_text(plan_content)

        linter = PlanCoverageLinter(str(self.project_root))
        linter._check_ui_page_coverage()

        ui_results = [r for r in linter.results if "UI 页面" in r.name]
        result = ui_results[0]

        self.assertTrue(result.passed, "Should pass using formal UI docs (not sample manifest)")
        self.assertEqual(result.actual, 12, "Should cover 12 pages from formal docs")
        self.assertEqual(result.total, 12, "Should have 12 pages from formal docs (not 10 from sample)")

    def test_formal_ui_docs_fallback_missing_11th(self):
        """Test formal UI docs with missing 11th page causes blocking failure"""
        # Create formal UI docs directory with 12 doc files
        ui_docs_dir = self.spec_dir / "ui"
        ui_docs_dir.mkdir()
        for i in range(1, 13):
            doc_file = ui_docs_dir / f"page_{i:04d}_TestView.md"
            doc_file.write_text(f"# page_{i:04d}_TestView\n\nFormal UI documentation\n")

        # Create sample manifest with 10 rows (should be ignored)
        sample_manifest = "# UI Manifest\n\n| Page ID | Class |\n|---------|-------|\n"
        for i in range(1, 11):
            sample_manifest += f"| page_{i:04d}_SampleView | SampleView |\n"
        (self.spec_dir / "ui-manifest.md").write_text(sample_manifest)

        # Create minimal required files
        (self.spec_dir / "feature-index.md").write_text("# Feature Index\n")
        (self.plans_dir / "feature-plan.md").write_text("# Feature Plan\n")

        # Create plan missing page_0011
        plan_content = "# UI Plan\n\n"
        for i in range(1, 11):
            plan_content += f"- page_{i:04d}_TestView\n"
        plan_content += "- page_0012_TestView\n"
        (self.plans_dir / "ui-plan.md").write_text(plan_content)

        linter = PlanCoverageLinter(str(self.project_root))
        linter._check_ui_page_coverage()

        ui_results = [r for r in linter.results if "UI 页面" in r.name]
        result = ui_results[0]

        self.assertFalse(result.passed, "Should fail with missing page from formal docs")
        self.assertEqual(result.actual, 11, "Should show 11/12 from formal docs")
        self.assertEqual(result.total, 12, "Should have 12 total from formal docs")
        self.assertTrue(any("page_0011" in e for e in result.errors),
                       "Should report missing page_0011")



class TestUICountPublicInterface(unittest.TestCase):
    """Integration tests using public run_all_checks interface"""

    def setUp(self):
        """Create temporary test project structure"""
        self.temp_dir = tempfile.mkdtemp()
        self.project_root = Path(self.temp_dir)
        self.spec_dir = self.project_root / "spec" / "baseline"
        self.plans_dir = self.spec_dir / "plans"
        self.spec_dir.mkdir(parents=True)
        self.plans_dir.mkdir(parents=True)

    def tearDown(self):
        """Clean up temporary directory"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_approved_inventory(self, units):
        """Create ui-delivery-approved.json with given units"""
        inventory = {
            "schema_version": 2,
            "tool_version": "i2h-ui-delivery/1.1",
            "status": "approved",
            "units": units
        }
        inventory_path = self.spec_dir / "ui-delivery-approved.json"
        with open(inventory_path, 'w') as f:
            json.dump(inventory, f, indent=2)

    def _create_minimal_required_files(self):
        """Create minimal required files for linter"""
        (self.spec_dir / "feature-index.md").write_text("# Feature Index\n")
        (self.spec_dir / "ui-manifest.md").write_text("# UI Manifest\n")
        (self.plans_dir / "feature-plan.md").write_text("# Feature Plan\n")

    def _create_ui_plan(self, page_ids):
        """Create ui-plan.md covering given page IDs"""
        content = "# UI Plan\n\n## Covered Pages\n"
        for pid in page_ids:
            content += f"- {pid}\n"
        (self.plans_dir / "ui-plan.md").write_text(content)

    def test_canonical_id_exact_match_required(self):
        """Test that page_0001_Wrong does not match page_0001_Right (canonical exact match)"""
        units = [
            {
                "unit_id": "ios.0001.RightView",
                "page_id": "page_0001_RightView",
                "required": True
            },
            {
                "unit_id": "ios.0002.TestView",
                "page_id": "page_0002_TestView",
                "required": True
            }
        ]
        self._create_approved_inventory(units)
        self._create_minimal_required_files()

        # Plan has wrong class name for page_0001
        plan_content = """# UI Plan

- page_0001_WrongView
- page_0002_TestView
"""
        (self.plans_dir / "ui-plan.md").write_text(plan_content)

        linter = PlanCoverageLinter(str(self.project_root))
        linter._check_ui_page_coverage()

        ui_results = [r for r in linter.results if "UI 页面" in r.name]
        result = ui_results[0]

        self.assertFalse(result.passed, "Should fail when canonical ID mismatches")
        self.assertEqual(result.actual, 1, "Should only match page_0002")
        self.assertEqual(result.total, 2, "Should have 2 required")
        self.assertTrue(any("page_0001" in e for e in result.errors),
                       "Should report page_0001 as missing")

    def test_bare_alias_works_for_unambiguous_canonical(self):
        """Test that bare page_0001 matches when only one page_0001_* exists"""
        units = [
            {
                "unit_id": "ios.0001.OnlyView",
                "page_id": "page_0001_OnlyView",
                "required": True
            },
            {
                "unit_id": "ios.0002.TestView",
                "page_id": "page_0002_TestView",
                "required": True
            }
        ]
        self._create_approved_inventory(units)
        self._create_minimal_required_files()

        # Plan uses bare alias for unambiguous page
        plan_content = """# UI Plan

- page_0001
- page_0002_TestView
"""
        (self.plans_dir / "ui-plan.md").write_text(plan_content)

        linter = PlanCoverageLinter(str(self.project_root))
        linter._check_ui_page_coverage()

        ui_results = [r for r in linter.results if "UI 页面" in r.name]
        result = ui_results[0]

        self.assertTrue(result.passed, "Bare alias should work for unambiguous canonical")
        self.assertEqual(result.actual, 2, "Should match both pages")

    def test_public_wrong_class_blocks(self):
        """Test public run_all_checks with wrong canonical class name causes blocking failure"""
        units = []
        for i in range(1, 13):
            units.append({
                "unit_id": f"ios.{i:04d}.CorrectView",
                "page_id": f"page_{i:04d}_CorrectView",
                "required": True
            })

        self._create_approved_inventory(units)
        self._create_minimal_required_files()

        # Plan has wrong class name for page_0011
        plan_content = "# UI Plan\n\n"
        for i in range(1, 11):
            plan_content += f"- page_{i:04d}_CorrectView\n"
        plan_content += "- page_0011_WrongView\n"  # Wrong class!
        plan_content += "- page_0012_CorrectView\n"
        (self.plans_dir / "ui-plan.md").write_text(plan_content)

        linter = PlanCoverageLinter(str(self.project_root))
        result = linter.run_all_checks()

        self.assertFalse(result, "Should return False with wrong canonical class")

        ui_results = [r for r in linter.results if "UI 页面" in r.name]
        ui_result = ui_results[0]
        self.assertFalse(ui_result.passed, "UI coverage should fail")
        self.assertTrue(any("page_0011" in e for e in ui_result.errors),
                       "Should report page_0011 as missing due to wrong class name")

    def test_public_run_all_checks_positive(self):
        """Test public run_all_checks returns True when all required pages covered"""
        # Create 12 required + 2 excluded
        units = []
        for i in range(1, 13):
            units.append({
                "unit_id": f"ios.{i:04d}.TestView",
                "page_id": f"page_{i:04d}_TestView",
                "required": True
            })
        for i in range(13, 15):
            units.append({
                "unit_id": f"ios.{i:04d}.LegacyView",
                "page_id": f"page_{i:04d}_LegacyView",
                "required": False
            })

        self._create_approved_inventory(units)
        self._create_minimal_required_files()
        self._create_ui_plan([f"page_{i:04d}_TestView" for i in range(1, 13)])

        linter = PlanCoverageLinter(str(self.project_root))

        # Public interface: run_all_checks should return True or exit with code 2 (warnings)
        exit_code = None
        try:
            result = linter.run_all_checks()
            # If no SystemExit, result should be True
            self.assertTrue(result, "run_all_checks should return True when all required pages covered")
        except SystemExit as e:
            exit_code = e.code
            # Only exit code 2 (warnings) is acceptable, not 1 (blocking failure)
            self.assertEqual(e.code, 2, f"Should exit with code 2 (warnings) not {e.code}")

        # Check UI coverage result specifically
        ui_results = [r for r in linter.results if "UI 页面" in r.name]
        self.assertEqual(len(ui_results), 1, "Should have UI coverage result")

        ui_result = ui_results[0]
        self.assertTrue(ui_result.passed, "UI coverage should pass")
        self.assertEqual(ui_result.actual, 12, "Should cover 12 required")
        self.assertEqual(ui_result.total, 12, "Should have 12 required total")

        # Verify no blocking failures in any results
        blocking_failures = [r for r in linter.results if not r.passed and r.blocking]
        self.assertEqual(len(blocking_failures), 0,
                        f"Should have no blocking failures, got: {[r.name for r in blocking_failures]}")

    def test_legacy_bare_page_nnnn_table_positive(self):
        """Test legacy manifest with bare page_NNNN table (no inventory, no formal docs) - full plan passes"""
        # Create legacy manifest with bare page_NNNN in table (no class suffix)
        legacy_manifest = """# UI Manifest

Legacy bare format table:

| Page ID | Description |
|---------|-------------|
| page_0001 | Home |
| page_0002 | Profile |
| page_0003 | Settings |
| page_0004 | About |
| page_0005 | Help |
| page_0006 | Privacy |
| page_0007 | Terms |
| page_0008 | Contact |
| page_0009 | FAQ |
| page_0010 | Support |
| page_0011 | Feedback |
| page_0012 | Version |

Note: page_0013 is mentioned in this paragraph but should not count as a unit.
"""
        (self.spec_dir / "ui-manifest.md").write_text(legacy_manifest)
        (self.spec_dir / "feature-index.md").write_text("# Feature Index\n")
        (self.plans_dir / "feature-plan.md").write_text("# Feature Plan\n")

        # Plan covering all 12 table entries (bare format)
        plan_content = "# UI Plan\n\n"
        for i in range(1, 13):
            plan_content += f"- page_{i:04d}\n"
        (self.plans_dir / "ui-plan.md").write_text(plan_content)

        linter = PlanCoverageLinter(str(self.project_root))
        result = linter.run_all_checks()

        # Should pass or exit with code 2 (warnings from other checks)
        if result is not None:
            # No SystemExit raised
            self.assertTrue(result, "Should return True with all bare pages covered")

        ui_results = [r for r in linter.results if "UI 页面" in r.name]
        ui_result = ui_results[0]

        self.assertTrue(ui_result.passed, "UI coverage should pass with bare format")
        self.assertEqual(ui_result.actual, 12, "Should cover 12 bare pages")
        self.assertEqual(ui_result.total, 12, "Should have 12 bare pages from table (not 13 including paragraph)")

    def test_legacy_bare_page_nnnn_table_missing_11th(self):
        """Test legacy bare page_NNNN table with missing 11th page causes blocking failure"""
        # Create legacy manifest with bare page_NNNN in table
        legacy_manifest = """# UI Manifest

| Page ID | Description |
|---------|-------------|
| page_0001 | Home |
| page_0002 | Profile |
| page_0003 | Settings |
| page_0004 | About |
| page_0005 | Help |
| page_0006 | Privacy |
| page_0007 | Terms |
| page_0008 | Contact |
| page_0009 | FAQ |
| page_0010 | Support |
| page_0011 | Feedback |
| page_0012 | Version |
"""
        (self.spec_dir / "ui-manifest.md").write_text(legacy_manifest)
        (self.spec_dir / "feature-index.md").write_text("# Feature Index\n")
        (self.plans_dir / "feature-plan.md").write_text("# Feature Plan\n")

        # Plan missing page_0011
        plan_content = "# UI Plan\n\n"
        for i in range(1, 11):
            plan_content += f"- page_{i:04d}\n"
        plan_content += "- page_0012\n"
        (self.plans_dir / "ui-plan.md").write_text(plan_content)

        linter = PlanCoverageLinter(str(self.project_root))
        result = linter.run_all_checks()

        self.assertFalse(result, "Should return False with missing bare page")

        ui_results = [r for r in linter.results if "UI 页面" in r.name]
        ui_result = ui_results[0]

        self.assertFalse(ui_result.passed, "UI coverage should fail")
        self.assertEqual(ui_result.actual, 11, "Should show 11/12 covered")
        self.assertEqual(ui_result.total, 12, "Should have 12 total")
        self.assertTrue(any("page_0011" in e for e in ui_result.errors),
                       "Should report missing page_0011")



        """Test public run_all_checks returns False when required page missing"""
        # Create 12 required + 2 excluded
        units = []
        for i in range(1, 13):
            units.append({
                "unit_id": f"ios.{i:04d}.TestView",
                "page_id": f"page_{i:04d}_TestView",
                "required": True
            })
        for i in range(13, 15):
            units.append({
                "unit_id": f"ios.{i:04d}.LegacyView",
                "page_id": f"page_{i:04d}_LegacyView",
                "required": False
            })

        self._create_approved_inventory(units)
        self._create_minimal_required_files()
        # Deliberately omit page_0011 (cover only 11 of 12)
        covered = [f"page_{i:04d}_TestView" for i in range(1, 11)]
        covered.append("page_0012_TestView")
        self._create_ui_plan(covered)

        linter = PlanCoverageLinter(str(self.project_root))

        # Public interface: should return False due to blocking failure
        result = linter.run_all_checks()
        self.assertFalse(result, "run_all_checks should return False with blocking failure")

        # Verify UI coverage result shows specific missing page
        ui_results = [r for r in linter.results if "UI 页面" in r.name]
        ui_result = ui_results[0]

        self.assertFalse(ui_result.passed, "UI coverage should fail")
        self.assertTrue(ui_result.blocking, "Should be blocking failure")
        self.assertEqual(ui_result.actual, 11, "Should show 11/12 covered")
        self.assertEqual(ui_result.total, 12, "Should show 12 required")
        self.assertTrue(any("page_0011" in e for e in ui_result.errors),
                       f"Should report missing page_0011, got: {ui_result.errors}")


if __name__ == '__main__':
    unittest.main()
