#!/usr/bin/env python3
"""Integration tests for Plan schema-1 validation in pipeline_resume."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[2] / 'bin/scripts/pipeline'))

from marker_contract import write_marker
from generate_execute_coverage import build
import pipeline_resume


class PipelineResumeSchema1ValidationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        target = self.root / 'spec/.i2h/target-input.json'
        target.parent.mkdir(parents=True)
        target.write_text(json.dumps({'target_input_sha256': 'a' * 64}), encoding='utf-8')
        self.target = 'a' * 64

    def tearDown(self):
        self.tmp.cleanup()

    def create_source_fixture(self):
        """Create minimal source fixture for native producers."""
        feature_dir = self.root / 'spec/baseline/features'
        slice_dir = self.root / 'spec/baseline/plans/slices'
        feature_dir.mkdir(parents=True, exist_ok=True)
        slice_dir.mkdir(parents=True, exist_ok=True)

        (feature_dir / 'feat_001_test.md').write_text(
            '# F001: Test\n\n## Acceptance Criteria\n\n- [ ] F001-AC01 Save data\n',
            encoding='utf-8'
        )
        (slice_dir / 'slice-01-F001.md').write_text(
            'feature_id: F001\n\nmodifies_files:\n  - entry/src/main/ets/pages/Index.ets\n',
            encoding='utf-8'
        )

    def write_native_outputs(self):
        """Generate outputs using native producers including seal."""
        from acceptance_plan import current_requirements, seal

        index, coverage = build(self.root)
        current_reqs = current_requirements(self.root)
        sealed_plan = seal(current_reqs, {'schema_version': 1, 'bindings': []})

        i2h_dir = self.root / 'spec/.i2h'
        plan_dir = self.root / 'spec/baseline/plans'
        i2h_dir.mkdir(parents=True, exist_ok=True)
        plan_dir.mkdir(parents=True, exist_ok=True)

        (i2h_dir / 'requirements-index.json').write_text(
            json.dumps(index, ensure_ascii=False, indent=2), encoding='utf-8'
        )
        (i2h_dir / 'plan-coverage.json').write_text(
            json.dumps(coverage, ensure_ascii=False, indent=2), encoding='utf-8'
        )
        (plan_dir / 'acceptance-plan.json').write_text(
            json.dumps(sealed_plan, ensure_ascii=False, indent=2), encoding='utf-8'
        )
        return index, coverage, sealed_plan

    def marker(self, rel, stage, artifacts=()):
        path = self.root / rel
        for artifact in artifacts:
            p = self.root / artifact
            if not p.exists():
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text('artifact', encoding='utf-8')
        return write_marker(path, stage, artifacts, self.target, root=self.root)

    def delivery(self, status='approved'):
        units = [
            {'unit_id': 'home', 'owned_ui_roles': ['content'],
             'presentation_role': 'routed_page',
             'required_states': [{'state_id': 'home', 'arrival_mode': 'preview', 'responsibility': 'content'}],
             'output': {'file': 'entry/src/main/ets/pages/Home.ets'}},
        ]
        path = self.root / 'spec/baseline/ui-delivery-approved.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({'schema_version': 2, 'status': status,
                                    'target_input_sha256': self.target,
                                    'units': units}), encoding='utf-8')

    def test_plan_completes_with_valid_native_outputs(self):
        """Plan stage completes when native schema-1 outputs are valid."""
        self.marker('spec/baseline/spec-complete.txt', 'i2h-spec', ['spec/.i2h/resources-inventory.json'])
        self.delivery()
        self.create_source_fixture()
        self.write_native_outputs()
        self.marker('spec/baseline/plans/complete.txt', 'i2h-plan', ['spec/baseline/ui-delivery-approved.json'])

        result = pipeline_resume.pipeline_status(self.root)
        plan_stage = result['stages'][1]

        self.assertEqual(plan_stage['stage'], 'i2h-plan')
        self.assertTrue(plan_stage['complete'], plan_stage)
        self.assertTrue(plan_stage['checks']['schema1_outputs']['complete'])

    def test_plan_blocked_by_top_level_list_requirements(self):
        """Plan stage blocked when requirements-index.json is top-level list."""
        self.marker('spec/baseline/spec-complete.txt', 'i2h-spec', ['spec/.i2h/resources-inventory.json'])
        self.delivery()
        self.create_source_fixture()
        index, coverage = build(self.root)

        i2h_dir = self.root / 'spec/.i2h'
        i2h_dir.mkdir(parents=True, exist_ok=True)
        # Write as top-level list
        (i2h_dir / 'requirements-index.json').write_text(
            json.dumps(index["requirements"], ensure_ascii=False), encoding='utf-8'
        )
        (i2h_dir / 'plan-coverage.json').write_text(
            json.dumps(coverage, ensure_ascii=False), encoding='utf-8'
        )

        self.marker('spec/baseline/plans/complete.txt', 'i2h-plan', ['spec/baseline/ui-delivery-approved.json'])

        result = pipeline_resume.pipeline_status(self.root)
        plan_stage = result['stages'][1]

        self.assertFalse(plan_stage['complete'])
        self.assertIn('requirements_index_not_object', plan_stage['checks']['schema1_outputs']['errors'])

    def test_plan_blocked_by_requirement_digests_as_list(self):
        """Plan stage blocked when requirement_digests is list instead of dict."""
        self.marker('spec/baseline/spec-complete.txt', 'i2h-spec', ['spec/.i2h/resources-inventory.json'])
        self.delivery()
        self.create_source_fixture()
        index, coverage = build(self.root)

        # Mutate coverage to have digests as list
        for packet in coverage["packets"]:
            packet["requirement_digests"] = list(packet["requirement_digests"].values())

        i2h_dir = self.root / 'spec/.i2h'
        i2h_dir.mkdir(parents=True, exist_ok=True)
        (i2h_dir / 'requirements-index.json').write_text(
            json.dumps(index, ensure_ascii=False), encoding='utf-8'
        )
        (i2h_dir / 'plan-coverage.json').write_text(
            json.dumps(coverage, ensure_ascii=False), encoding='utf-8'
        )

        self.marker('spec/baseline/plans/complete.txt', 'i2h-plan', ['spec/baseline/ui-delivery-approved.json'])

        result = pipeline_resume.pipeline_status(self.root)
        plan_stage = result['stages'][1]

        self.assertFalse(plan_stage['complete'])
        self.assertTrue(any('requirement_digests_not_dict' in e
                          for e in plan_stage['checks']['schema1_outputs']['errors']))

    def test_plan_blocked_by_source_mutation(self):
        """Plan stage blocked when source AC mutates but cached index unchanged."""
        self.marker('spec/baseline/spec-complete.txt', 'i2h-spec', ['spec/.i2h/resources-inventory.json'])
        self.delivery()
        self.create_source_fixture()
        self.write_native_outputs()

        # Mutate source AC statement
        feature_file = self.root / 'spec/baseline/features/feat_001_test.md'
        content = feature_file.read_text(encoding='utf-8')
        content = content.replace('Save data', 'Load data')
        feature_file.write_text(content, encoding='utf-8')

        self.marker('spec/baseline/plans/complete.txt', 'i2h-plan', ['spec/baseline/ui-delivery-approved.json'])

        result = pipeline_resume.pipeline_status(self.root)
        plan_stage = result['stages'][1]

        self.assertFalse(plan_stage['complete'])
        self.assertTrue(any('stale_digest' in e
                          for e in plan_stage['checks']['schema1_outputs']['errors']))

    def test_plan_blocked_by_wrong_acceptance_criteria_field(self):
        """Plan stage blocked when acceptance plan uses wrong field name."""
        self.marker('spec/baseline/spec-complete.txt', 'i2h-spec', ['spec/.i2h/resources-inventory.json'])
        self.delivery()
        self.create_source_fixture()
        self.write_native_outputs()

        # Write acceptance plan with wrong field name
        plan_dir = self.root / 'spec/baseline/plans'
        plan_dir.mkdir(parents=True, exist_ok=True)
        (plan_dir / 'acceptance-plan.json').write_text(json.dumps({
            'schema_version': 1,
            'acceptance_criteria': []  # Wrong field name
        }), encoding='utf-8')

        self.marker('spec/baseline/plans/complete.txt', 'i2h-plan', ['spec/baseline/ui-delivery-approved.json'])

        result = pipeline_resume.pipeline_status(self.root)
        plan_stage = result['stages'][1]

        self.assertFalse(plan_stage['complete'])
        self.assertIn('acceptance_plan_wrong_field_name',
                     plan_stage['checks']['schema1_outputs']['errors'])


if __name__ == "__main__":
    unittest.main()
