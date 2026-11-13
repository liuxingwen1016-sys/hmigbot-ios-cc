#!/usr/bin/env python3
"""Bind Plan acceptance assertions to source ACs and evaluate current UITest evidence."""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
import tempfile

from generate_execute_coverage import build


DEFAULT_PLAN = 'spec/baseline/plans/acceptance-plan.json'
PLAN_MARKER = 'spec/baseline/plans/complete.txt'
BEHAVIOR_REPORT = 'spec/verify/check5/behavior-summary.json'
ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]*')
LAYOUT = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]*\.json')
SHA256 = re.compile(r'[0-9a-f]{64}')
ATTRIBUTES = {'id', 'type', 'text', 'enabled', 'clickable', 'selected', 'checked', 'content'}
CASE_STATUSES = {'PASS', 'FAIL', 'BLOCKED', 'DEFERRED', 'ERROR', 'SKIP'}
RUN_CONTEXT = ('version_code', 'runner_sha256', 'fixture_sha256', 'database', 'capture_profile')


@dataclass
class Run:
    path: Path
    digest: str
    data: dict

    def reference(self) -> dict:
        return {'path': str(self.path), 'sha256': self.digest}


def read(path: Path) -> dict:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError(f'expected JSON object: {path}')
    return value


def current_requirements(root: Path) -> dict[str, dict]:
    index, _ = build(root)
    rows = {row['requirement_id']: row for row in index['requirements']}
    if not rows or len(rows) != len(index['requirements']):
        raise ValueError('acceptance criteria must have unique, nonempty IDs')
    return rows


def valid_name(value, pattern=ID) -> bool:
    return isinstance(value, str) and pattern.fullmatch(value) is not None


def valid_selectors(values) -> bool:
    return isinstance(values, list) and all(
        isinstance(row, dict) and row and row.keys() <= ATTRIBUTES
        and all(isinstance(value, str) for value in row.values())
        for row in values
    )


def seal(requirements: dict[str, dict], draft: dict) -> dict:
    if draft.get('schema_version') != 1 or not isinstance(draft.get('bindings'), list):
        raise ValueError('expected schema-1 acceptance bindings')
    by_id = {}
    for binding in draft['bindings']:
        ac = binding.get('requirement_id') if isinstance(binding, dict) else None
        if not isinstance(ac, str) or ac not in requirements or ac in by_id:
            raise ValueError(f'unknown or duplicate AC: {ac}')
        scenario = binding.get('scenario')
        assertions = binding.get('assertions')
        if not valid_name(scenario) or not isinstance(assertions, list) or not assertions:
            raise ValueError(f'{ac}: expected named scenario and one or more assertions')
        for assertion in assertions:
            if not isinstance(assertion, dict) or assertion.keys() - {'step', 'layout', 'present', 'absent'}:
                raise ValueError(f'{ac}: invalid assertion keys')
            present = assertion.get('present')
            if (not valid_name(assertion.get('step')) or not valid_name(assertion.get('layout'), LAYOUT)
                    or not present or not valid_selectors(present) or not valid_selectors(assertion.get('absent', []))):
                raise ValueError(f'{ac}: each assertion requires a step, raw layout and a visible control')
        by_id[ac] = {'scenario': scenario, 'assertions': assertions}

    return {'schema_version': 1, 'criteria': [
        {'requirement_id': ac, 'requirement_sha256': item['digest'], 'source_file': item['source_file'],
         **by_id.get(ac, {'scenario': None, 'assertions': []})}
        for ac, item in sorted(requirements.items())
    ]}


def controls(tree: dict):
    attributes = tree['attributes']
    if attributes.get('visible') == 'true':
        yield attributes
    for child in tree['children']:
        yield from controls(child)


def asserted_layout(directory: Path, assertion: dict) -> dict | None:
    path = (directory / assertion['layout']).resolve()
    if path.parent != directory or not path.is_file():
        return None
    try:
        raw = path.read_bytes()
        nodes = list(controls(json.loads(raw)))
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
        return None

    def matches(selector):
        return any(all(node.get(key) == value for key, value in selector.items()) for node in nodes)

    if all(map(matches, assertion['present'])) and not any(map(matches, assertion.get('absent', []))):
        return {'path': path.name, 'sha256': sha256(raw).hexdigest(), 'step': assertion['step']}
    return None


def hash_package(hap: Path) -> str:
    package_digest = sha256()
    with hap.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            package_digest.update(chunk)
    return package_digest.hexdigest()


def load_run(path: Path) -> Run:
    path = path.resolve(strict=True)
    raw = path.read_bytes()
    run = json.loads(raw)
    if not isinstance(run, dict):
        raise ValueError(f'expected runner receipt: {path}')
    planned, cases = run.get('planned_cases'), run.get('cases')
    if (not isinstance(planned, list) or not planned or not all(map(valid_name, planned))
            or len(set(planned)) != len(planned) or not isinstance(cases, dict) or cases.keys() - set(planned)):
        raise ValueError(f'invalid scenario denominator: {path}')
    if not all(isinstance(case, dict) and isinstance(case.get('status'), str) for case in cases.values()):
        raise ValueError(f'invalid scenario result: {path}')
    return Run(path, sha256(raw).hexdigest(), run)


def admit_runs(paths: list[Path], hap_hash: str, device: str) -> list[Run]:
    runs = [load_run(path) for path in paths]
    for run in runs:
        if (run.data.get('hap_sha256'), run.data.get('device')) != (hap_hash, device):
            raise ValueError(f'device or signed package mismatch: {run.path}')
    if len({run.digest for run in runs}) != len(runs):
        raise ValueError('duplicate runner receipt')
    return runs


def latest_results(runs: list[Run]) -> dict:
    latest = {}
    for run in runs:
        for scenario in run.data['planned_cases']:
            latest[scenario] = (run.data['cases'].get(scenario), run)
    return latest


def evaluate_runs(plan: dict, requirements: dict[str, dict], runs: list[Run], hap_hash: str, device: str) -> dict:
    if not isinstance(plan, dict) or plan.get('schema_version') != 1 or not isinstance(plan.get('criteria'), list):
        raise ValueError('expected sealed schema-1 acceptance plan')
    declared = [row for row in plan['criteria'] if isinstance(row, dict) and row.get('scenario') is not None]
    bindings = [{key: row.get(key) for key in ('requirement_id', 'scenario', 'assertions')} for row in declared]
    if seal(requirements, {'schema_version': 1, 'bindings': bindings}) != plan:
        raise ValueError('acceptance plan is stale or does not cover the current source criteria')
    latest = latest_results(runs)
    rows = []
    for entry in plan['criteria']:
        scenario = entry['scenario']
        item = {**entry, 'status': 'NO_BINDING' if scenario is None else 'UNVERIFIED'}
        if scenario in latest:
            case, run = latest[scenario]
            if case is not None and case['status'] == 'PASS':
                steps = case.get('passed_steps')
                if isinstance(steps, list) and all(check['step'] in steps for check in entry['assertions']):
                    layouts = [asserted_layout(run.path.parent, check) for check in entry['assertions']]
                    if all(layouts):
                        item.update(status='DIRECT_EVIDENCE', evidence=layouts, run=run.reference())
        rows.append(item)
    return {'schema_version': 1, 'device': device, 'hap_sha256': hap_hash, 'criteria': rows,
            'counts': dict(Counter(row['status'] for row in rows))}


def evaluate(plan: dict, requirements: dict[str, dict], runs: list[Path], hap: Path, device: str) -> dict:
    hap_hash = hash_package(hap)
    return evaluate_runs(plan, requirements, admit_runs(runs, hap_hash, device), hap_hash, device)


def approved_plan(root: Path, path: Path, digest: str) -> bool:
    runtime = Path(__file__).resolve().parents[3]
    for helpers in (runtime / 'bin/scripts/pipeline', runtime.parent / '.migbot/bin/scripts/pipeline'):
        if (helpers / 'marker_contract.py').is_file():
            sys.path.insert(0, str(helpers))
            break
    else:
        raise ValueError('installed plan marker helper is missing')
    from marker_contract import read_marker, validate_marker

    marker = root / PLAN_MARKER
    if not validate_marker(marker, 'i2h-plan', allow_legacy=False, root=root)['valid']:
        return False
    reference = {'path': path.relative_to(root).as_posix(), 'sha256': digest}
    return reference in read_marker(marker)['artifacts']


def behavior_report(plan: dict, requirements: dict[str, dict], runs: list[Run], baseline: Run,
                    requested: list[str], hap_hash: str, device: str) -> dict:
    scope = baseline.data['planned_cases']
    scope_set = set(scope)
    bound = {entry['scenario'] for entry in plan['criteria'] if entry['scenario'] is not None}
    if requested and (len(set(requested)) != len(requested) or set(requested) != set(runs[-1].data['planned_cases'])):
        raise ValueError('requested recheck scenarios must match the latest runner receipt')
    if len(runs) > 1:
        initial = runs[0].data
        if not all(valid_name(initial.get(key), SHA256)
                   for key in ('runner_sha256', 'fixture_sha256')):
            raise ValueError('combining receipts requires runner_sha256 and fixture_sha256')
        if any(run.data.get(key) != initial.get(key) for run in runs[1:] for key in RUN_CONTEXT):
            raise ValueError('runner or fixture context mismatch')
    for run in runs:
        if set(run.data['planned_cases']) - (scope_set | bound):
            raise ValueError(f'runner scenarios exceed the baseline scope: {run.path}')
        if any(case['status'] not in CASE_STATUSES for case in run.data['cases'].values()):
            raise ValueError(f'unknown scenario status: {run.path}')
    latest = latest_results(runs)
    rows = []
    for scenario in scope + sorted(bound - scope_set):
        case, run = latest.get(scenario, (None, None))
        row = {'scenario': scenario, 'status': case['status'] if case is not None else 'NOT_RUN'}
        if case is not None and isinstance(case.get('reason'), str):
            row['reason'] = case['reason']
        if run is not None:
            row['run'] = run.reference()
        rows.append(row)
    acceptance = evaluate_runs(plan, requirements, runs, hap_hash, device)
    for criterion in acceptance['criteria']:
        # The approved plan owns assertions. The report preserves identity and
        # outcomes without repeating the full inputs to the evaluator.
        criterion.pop('assertions')
    counts = dict(Counter(row['status'] for row in rows))
    if counts.get('FAIL'):
        status = 'FAIL'
    elif counts.get('PASS') == len(rows) and acceptance['counts'].get('DIRECT_EVIDENCE') == len(requirements):
        status = 'PASS'
    else:
        status = 'INCOMPLETE'
    return {**acceptance, 'counts': {'criteria': acceptance['counts'], 'scenarios': counts},
            'status': status, 'scenario_total': len(rows), 'criterion_total': len(requirements),
            'scope': {'basis': 'runner_receipt_and_bound_scenarios', 'baseline': baseline.reference(),
                      'requested_recheck': requested},
            'runner_context': {key: runs[0].data[key] for key in RUN_CONTEXT if key in runs[0].data},
            'runs': [run.reference() for run in runs], 'scenarios': rows}


def build_behavior(root: Path, requirements: dict, name: str | None, hap: Path, device: str,
                   receipt_paths: list[Path], baseline_path: Path | None, requested: list[str]) -> dict:
    plan_path = (root / (name or DEFAULT_PLAN)).resolve()
    if root not in plan_path.parents:
        raise ValueError('acceptance plan must stay inside the project')
    raw_plan = plan_path.read_bytes() if name is not None or plan_path.exists() else None
    plan_digest = sha256(raw_plan).hexdigest() if raw_plan is not None else None
    is_approved = plan_digest is not None and approved_plan(root, plan_path, plan_digest)
    plan = json.loads(raw_plan) if is_approved else seal(requirements, {'schema_version': 1, 'bindings': []})
    hap_hash = hash_package(hap)
    runs = admit_runs(receipt_paths, hap_hash, device)
    if requested and baseline_path is None and len(runs) == 1:
        raise ValueError('scoped recheck requires the first full runner receipt as baseline')
    baseline = load_run(baseline_path) if baseline_path else runs[0]
    report = behavior_report(plan, requirements, runs, baseline, requested, hap_hash, device)
    plan_status = 'APPROVED' if is_approved else 'UNAPPROVED' if plan_digest else 'MISSING'
    return {**report, 'plan_status': plan_status, 'plan_sha256': plan_digest,
            'plan_path': plan_path.relative_to(root).as_posix(), 'signed_hap': str(hap.resolve())}


def replay_behavior(root: Path, report: dict) -> dict:
    if not isinstance(report, dict) or report.get('status') != 'PASS':
        raise ValueError('functional report is not PASS')
    return build_behavior(
        root, current_requirements(root), report['plan_path'], Path(report['signed_hap']), report['device'],
        [Path(run['path']) for run in report['runs']], Path(report['scope']['baseline']['path']),
        report['scope']['requested_recheck'],
    )


def write(root: Path, name: str, data: dict) -> None:
    output = (root / name).resolve()
    if root not in output.parents:
        raise ValueError('output path must stay inside the project')
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=output.parent, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        temporary.replace(output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root', type=Path, default=Path.cwd())
    modes = parser.add_subparsers(dest='mode', required=True)
    prepare = modes.add_parser('seal')
    prepare.add_argument('--draft', required=True, type=Path)
    check = modes.add_parser('evaluate')
    behavior = modes.add_parser('behavior', help='Report first functional Verify or a scoped recheck')
    for command in (check, behavior):
        command.add_argument('--plan', default=None, help=f'default: {DEFAULT_PLAN}')
        command.add_argument('--run', type=Path, action='append', required=True, help='receipt, oldest first')
        command.add_argument('--signed-hap', type=Path, required=True)
        command.add_argument('--device', required=True)
    check.add_argument('--out', default='spec/verify/check5/acceptance-evidence.json')
    behavior.add_argument('--baseline', type=Path, help='previous receipt used only for the scenario list')
    behavior.add_argument('--case', action='append', default=[], help='scenario planned in the latest recheck')
    args = parser.parse_args()
    try:
        root = args.project_root.resolve(strict=True)
        requirements = current_requirements(root)
        if args.mode == 'seal':
            plan = seal(requirements, read(args.draft))
            write(root, DEFAULT_PLAN, plan)
            summary = {'criteria': len(requirements), 'planned': sum(row['scenario'] is not None for row in plan['criteria'])}
        elif args.mode == 'evaluate':
            plan_path = (root / (args.plan or DEFAULT_PLAN)).resolve(strict=True)
            if root not in plan_path.parents:
                raise ValueError('acceptance plan must stay inside the project')
            if (root / args.out).resolve() == plan_path:
                raise ValueError('report path cannot overwrite the acceptance plan')
            raw_plan = plan_path.read_bytes()
            report = evaluate(json.loads(raw_plan), requirements, args.run, args.signed_hap, args.device)
            write(root, args.out, {**report, 'plan_sha256': sha256(raw_plan).hexdigest()})
            summary = report['counts']
        else:
            report = build_behavior(root, requirements, args.plan, args.signed_hap, args.device,
                                    args.run, args.baseline, args.case)
            output = root / BEHAVIOR_REPORT
            inputs = [Path(run['path']) for run in [*report['runs'], report['scope']['baseline']]]
            inputs.extend((root / report['plan_path'], Path(report['signed_hap'])))
            if output.resolve() != output or output in inputs:
                raise ValueError('report path cannot overwrite an input')
            write(root, BEHAVIOR_REPORT, report)
            summary = {key: report[key] for key in ('status', 'criterion_total', 'scenario_total', 'counts', 'plan_status')}
            summary['report_sha256'] = sha256(output.read_bytes()).hexdigest()
        print(json.dumps(summary, ensure_ascii=False))
        return int(args.mode == 'behavior' and summary['status'] != 'PASS')
    except (OSError, ValueError, TypeError, KeyError) as error:
        parser.exit(2, f'acceptance plan: {error}\n')


if __name__ == '__main__':
    raise SystemExit(main())
