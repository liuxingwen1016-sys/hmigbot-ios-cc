from hashlib import sha256
import json
from pathlib import Path
from subprocess import TimeoutExpired
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.visual_review_reuse import (attempted_labeled_rechecks, compare_review_runs, labeled_recheck_ids,
                                     platform_recheck_ids, prioritize_review_groups, reusable_reviews,
                                     review_native_groups)


class ReviewReuseTest(unittest.TestCase):
    def test_group_error_does_not_discard_other_results_or_timeout_retries(self):
        groups = [[{'comparison_id': name} for name in group]
                  for group in [('slow', 'slow-again'), ('unreadable',), ('ordinary',)]]

        def review(index, rows, *, timeout_seconds):
            names = [r['comparison_id'] for r in rows]
            self.assertEqual(timeout_seconds, 480 if len(names) == 2 else 300)
            if len(names) == 2:
                raise TimeoutExpired('review worker', timeout_seconds)
            if names == ['unreadable']:
                raise OSError('review output could not be read')
            code = 124 if names == ['slow-again'] else 0
            return {'group': index, 'verified': code == 0, 'exit_code': code,
                    'review_inputs': {names[0]: {}}}

        rows = review_native_groups(review, groups, 30, workers=2)
        self.assertEqual([row['group'] for row in rows], [30, 31, 32, 33, 34])
        self.assertEqual([r['exit_code'] for r in rows], [124, None, 0, 0, 124])
        self.assertEqual([r['parent_group'] for r in rows], [None, None, None, 30, 30])
        self.assertEqual(rows[1]['comparison_ids'], ['unreadable'])
        self.assertEqual(rows[1]['issue'], 'review output could not be read')
        self.assertEqual([row['verified'] for row in rows], [False, False, True, True, False])

    def test_rechecks_only_current_platform_failures_once(self):
        with tempfile.TemporaryDirectory() as temp:
            report = Path(temp) / 'group.json'
            sizes = {'ios': [1206, 2622], 'harmony': [1256, 2760]}
            expected = {name: {'platform_dimensions': sizes, 'source_context_sha256': []}
                        for name in ('wrong', 'right')}
            swapped = {'ios': sizes['harmony'], 'harmony': sizes['ios']}
            report.write_text(json.dumps({'comparisons': [
                {'comparison_id': 'wrong', 'platform_dimensions': swapped},
                {'comparison_id': 'right', 'platform_dimensions': sizes},
            ]}))
            receipt = {
                'group': 12, 'verified': False, 'exit_code': 0, 'report_edited': True,
                'missing_image_reads': [], 'missing_source_context': [],
                'report_sha256': sha256(report.read_bytes()).hexdigest(), 'review_inputs': expected,
                'models': ['deepseek-flash'],
                'issue': 'appearance review did not identify the dimensions of both platform originals',
                'outcome': {'context_window': 1_000_000, 'session_model': 'deepseek-flash[1m]', 'is_error': False},
            }

            def route(value, current=expected):
                return platform_recheck_ids([(report, value, report)], current, {'deepseek-flash'})

            self.assertEqual(route(receipt), {'wrong': 12})
            self.assertEqual(route({**receipt, 'exit_code': 124}), {})
            self.assertEqual(route({**receipt, 'models': ['deepseek-v4-pro']}), {})
            self.assertEqual(route({**receipt, 'outcome': {**receipt['outcome'],
                                                          'session_model': 'deepseek-v4-pro[1m]'}}), {})
            self.assertEqual(route({**receipt, 'report_sha256': 'corrupt'}), {})
            labeled = {**expected, 'wrong': {**expected['wrong'], 'source_context_sha256': ['panel']}}
            self.assertEqual(route(receipt, labeled), {})
            self.assertEqual(route({**receipt, 'review_inputs': labeled}, labeled), {})

    def test_timing_priority_keeps_all_groups_and_ignores_unverified_samples(self):
        groups = [[{'comparison_id': name}] for name in ('ordinary', 'unverified', 'slow', 'new')]
        samples = [
            {'verified': True, 'review_inputs': {'ordinary': {}}, 'elapsed_seconds': 20},
            {'verified': False, 'review_inputs': {'unverified': {}}, 'elapsed_seconds': 600},
            {'verified': True, 'review_inputs': {'slow': {}}, 'elapsed_seconds': 200},
            {'verified': True, 'review_inputs': {'slow': {}}, 'elapsed_seconds': 5},
        ]
        self.assertEqual(prioritize_review_groups(groups, samples),
                         [groups[2], groups[0], groups[1], groups[3]])

    def test_singleton_timeout_can_be_rechecked_with_exact_labeled_context(self):
        with tempfile.TemporaryDirectory() as temp:
            report = Path(temp) / 'group.json'
            report.write_text('{}', encoding='utf-8')
            plain = {'ios_sha256': 'original', 'source_context_sha256': [],
                     'platform_dimensions': {'ios': [1206, 2622], 'harmony': [1256, 2760]}}
            labeled = {**plain, 'source_context_sha256': ['relationships', 'panel']}
            failed = {'group': 9, 'verified': False, 'exit_code': 124,
                      'report_sha256': sha256(report.read_bytes()).hexdigest(),
                      'review_inputs': {'keyboard': plain}}

            def source(receipt):
                return report.with_suffix('.receipt.json'), receipt, report

            def route(receipt, binding=plain):
                return labeled_recheck_ids([source(receipt)], {'keyboard': binding}, {'deepseek-flash'})

            self.assertEqual(route(failed), {'keyboard': 9})
            self.assertEqual(route(failed, {**plain, 'ios_sha256': 'new'}), {})
            self.assertEqual(route(failed, labeled), {})
            self.assertEqual(route({**failed, 'report_sha256': 'bad'}), {})
            self.assertEqual(route({**failed, 'review_inputs': {'keyboard': plain, 'other': plain}}), {})
            self.assertEqual(route({**failed, 'issue': 'visual inputs changed during the review'}), {})

            followup = {**failed, 'group': 10, 'recovery_for': 9, 'review_inputs': {'keyboard': labeled}}
            before = [source(failed)]
            after = [*before, source(followup)]
            self.assertEqual(attempted_labeled_rechecks(before, {'keyboard': labeled}), set())
            self.assertEqual(attempted_labeled_rechecks(after, {'keyboard': labeled}), {'keyboard'})
            self.assertEqual(attempted_labeled_rechecks(after, {'keyboard': plain}), set())
            self.assertEqual(route(followup, labeled), {})

    def test_comparison_requires_all_inputs_and_matching_decisions(self):
        expected = {'first': {'image': 'one'}, 'second': {'image': 'two'}}
        with tempfile.TemporaryDirectory() as temp:
            def receipt(name, severity, inputs):
                report = Path(temp) / (name + '.json')
                report.write_text(json.dumps({'comparisons': [
                    {'comparison_id': key, 'verdict': 'FAIL', 'severity': severity} for key in inputs
                ]}))
                return (report.with_suffix('.receipt.json'), {'verified': True, 'review_inputs': inputs,
                        'report_sha256': sha256(report.read_bytes()).hexdigest()}, report)

            baseline = [receipt('baseline', 'normal', expected)]
            self.assertTrue(compare_review_runs(baseline, baseline, expected)['equivalent'])
            candidate = [receipt('candidate', 'critical', {'first': expected['first'], 'second': {'image': 'old'}})]
            report = compare_review_runs(baseline, candidate, expected)
            self.assertFalse(report['equivalent'])
            self.assertEqual(report['missing_candidate'], ['second'])
            self.assertEqual(report['matched_inputs'], 1)
            self.assertEqual(report['changed_decisions'], [{
                'comparison_id': 'first', 'baseline': {'verdict': 'FAIL', 'severity': 'normal'},
                'candidate': {'verdict': 'FAIL', 'severity': 'critical'},
            }])

    def test_conflicts_stale_inputs_and_changed_reports_are_not_reused(self):
        expected = {name: {'rule_version': 2, 'source_context_sha256': ['tree']}
                    for name in ('stable', 'conflict', 'unresolved', 'stale')}
        with tempfile.TemporaryDirectory() as temp:
            def source(index, results, identities):
                report = Path(temp) / f'{index}.json'
                report.write_text(json.dumps({'comparisons': [
                    {'comparison_id': name, 'verdict': verdict, 'severity': 'normal'}
                    for name, verdict in results.items()
                ]}), encoding='utf-8')
                return report.with_suffix('.receipt.json'), {
                    'verified': True, 'report_sha256': sha256(report.read_bytes()).hexdigest(),
                    'review_inputs': identities,
                }, report

            stale = {**expected, 'stale': {'rule_version': 1, 'source_context_sha256': ['tree']}}
            a = source(1, {'stable': 'PASS', 'conflict': 'PASS', 'unresolved': 'UNRESOLVED', 'stale': 'PASS'}, stale)
            b = source(2, {'conflict': 'FAIL'}, expected)
            corrupt = source(3, {'unresolved': 'PASS'}, expected)
            corrupt[2].write_text('{}', encoding='utf-8')
            accepted, conflicts = reusable_reviews([a, b, corrupt], expected)
            self.assertEqual(set(accepted), {'stable'})
            self.assertEqual(conflicts, {'conflict'})


if __name__ == '__main__':
    unittest.main()
