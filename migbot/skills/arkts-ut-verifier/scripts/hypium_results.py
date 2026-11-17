"""Validate Hypium run receipts and compute the three independent UT metrics."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'i2h-plan/scripts'))
from hypium_evidence import SUMMARY

STATUSES = {0: 'GREEN', -1: 'ERROR', -2: 'RED', -3: 'IGNORE'}
COUNTS = {'GREEN': 'Pass', 'RED': 'Failure', 'ERROR': 'Error', 'IGNORE': 'Ignore'}
RECORD = re.compile(
    r'OHOS_REPORT_(?:STATUS_CODE: [^\r\n]*?|STATUS: (?:class|current|test)=[^\r\n]*?)'
    r'(?=OHOS_REPORT_|\r?$)', re.MULTILINE,
)
FIELD = re.compile(r'OHOS_REPORT_STATUS: (\w+)=(.*)')


def _ids(values):
    if not isinstance(values, list) or not all(isinstance(value, str) and value.strip() for value in values):
        raise ValueError('expected a JSON array of nonempty IDs')
    return set(values)


def parse_log(log: str, expected_ids: list[str]) -> dict:
    expected = _ids(expected_ids)
    diagnostics = []
    if len(expected) != len(expected_ids):
        diagnostics.append('duplicate expected IDs')
    fields, active, seen, cases = {}, {}, set(), {}
    for match in RECORD.finditer(log):
        token = match[0]
        if field := FIELD.fullmatch(token):
            fields[field[1]] = field[2].strip()
            continue
        code_text = token.removeprefix('OHOS_REPORT_STATUS_CODE: ').strip()
        current = fields.pop('current', '')
        suite = fields.pop('class', '')
        test = fields.pop('test', '')
        if not re.fullmatch(r'-?[0-9]+', code_text):
            diagnostics.append(f'invalid status code: {code_text!r}')
            continue
        code = int(code_text)
        identity = (suite, current)
        if not (suite and current.isdecimal() and test):
            diagnostics.append(f'incomplete status {code}')
        elif code == 1 and test not in seen and identity not in active:
            seen.add(test)
            active[identity] = test
        elif code in STATUSES and active.get(identity) == test:
            del active[identity]
            cases[test] = {'case_id': test, 'suite': suite, 'status': STATUSES[code]}
        else:
            diagnostics.append(f'unmatched or duplicate status {code}: {test}')
    if active:
        diagnostics.append('unfinished starts: ' + ', '.join(sorted(active.values())))
    missing = sorted(expected - cases.keys())
    unexpected = sorted(cases.keys() - expected)
    if missing or unexpected:
        diagnostics.append('completed IDs differ from expected IDs')
    counts = Counter(case['status'] for case in cases.values())
    observed = {'Tests run': len(cases), **{key: counts[status] for status, key in COUNTS.items()}}
    summaries = SUMMARY.findall(log)
    raw = {}
    if len(summaries) != 1:
        diagnostics.append('expected exactly one complete summary')
    else:
        raw = dict(zip(('Tests run', 'Failure', 'Error', 'Pass', 'Ignore'), map(int, summaries[0])))
        if raw != observed:
            diagnostics.append('summary disagrees with terminal events')
    if (re.findall(r'^OHOS_REPORT_CODE: (\S+)[ \t]*\r?$', log, re.MULTILINE) != ['0']
            or len(re.findall(r'^OHOS_REPORT_STATUS: taskconsuming=\d+(?:\.\d+)?[ \t]*\r?$', log, re.MULTILINE)) != 1):
        diagnostics.append('missing or repeated successful runner completion')
    return {'status': 'invalid' if diagnostics else 'valid', 'raw': raw, 'observed': observed,
            'cases': list(cases.values()), 'diagnostics': diagnostics,
            'missing_ids': missing, 'unexpected_ids': unexpected}


def _rate(numerator, denominator):
    return {'numerator': numerator, 'denominator': denominator,
            'percent': 100 * numerator / denominator if denominator else None}


def metrics(data: dict) -> dict:
    ac_ids = _ids(data['logic_ac_ids'])
    cases = {row['case_id']: row for row in data['cases']}
    groups = {row['group_id']: row['result'] for row in data['groups']}
    if len(cases) != len(data['cases']) or len(groups) != len(data['groups']):
        raise ValueError('duplicate case or group IDs')
    invalid = sorted(group for group, result in groups.items() if result['status'] != 'valid')
    terminal = {}
    for group, result in groups.items():
        if group in invalid:
            continue
        outcomes = {row['case_id']: row['status'] for row in result['cases']}
        if len(outcomes) != len(result['cases']) or set(outcomes.values()) - COUNTS.keys():
            raise ValueError(f'invalid terminal results for group {group}')
        terminal[group] = outcomes
    verified = set()
    obligations = defaultdict(set)
    counts = Counter()
    missing, incomplete = set(), set()
    for case_id, row in cases.items():
        acs = _ids(row['source_ac_ids'])
        if not acs or acs - ac_ids:
            raise ValueError(f'invalid source AC IDs for case {case_id}')
        for ac in acs:
            obligations[ac].add(case_id)
        required = _ids(row['required_groups'])
        missing.update(required - groups.keys())
        statuses = []
        for group in required & terminal.keys():
            if case_id in terminal[group]:
                statuses.append(terminal[group][case_id])
            else:
                incomplete.add(group)
        counts.update(statuses)
        if (required and len(statuses) == len(required) and set(statuses) == {'GREEN'}
                and row.get('quality_passed') is True):
            verified.add(case_id)
    completed_acs = {ac for ac, owners in obligations.items()
                     if owners <= verified and all(cases[owner].get('wiring_complete') is True for owner in owners)}
    return {
        'raw_pass_rate': _rate(counts['GREEN'], sum(counts[key] for key in ('GREEN', 'RED', 'ERROR'))),
        'raw_pass_rate_complete': not (invalid or missing or incomplete),
        'design_verification_rate': _rate(len(verified), len(cases)),
        'ac_completion_rate': _rate(len(completed_acs), len(ac_ids)),
        'group_raw': {group: result.get('raw', {}) for group, result in groups.items()},
        'terminal_counts': {key: counts[key] for key in COUNTS},
        'verified_ids': sorted(verified), 'unverified_ids': sorted(cases.keys() - verified),
        'completed_ac_ids': sorted(completed_acs), 'uncompleted_ac_ids': sorted(ac_ids - completed_acs),
        'invalid_groups': invalid, 'missing_groups': sorted(missing), 'incomplete_groups': sorted(incomplete),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    parse = commands.add_parser('parse')
    parse.add_argument('--log', type=Path, required=True)
    parse.add_argument('--expected-ids', type=Path, required=True)
    compute = commands.add_parser('metrics')
    compute.add_argument('--input', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == 'parse':
            result = parse_log(args.log.read_text(encoding='utf-8-sig'),
                               json.loads(args.expected_ids.read_text(encoding='utf-8-sig')))
            passed = result['status'] == 'valid'
        else:
            result = metrics(json.loads(args.input.read_text(encoding='utf-8-sig')))
            passed = result['raw_pass_rate_complete']
    except (OSError, AttributeError, KeyError, TypeError, ValueError) as exc:
        parser.exit(2, f'hypium_results: {exc}\n')
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return int(not passed)


if __name__ == '__main__':
    raise SystemExit(main())
