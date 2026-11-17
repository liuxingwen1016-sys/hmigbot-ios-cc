#!/usr/bin/env python3
"""Bind Plan acceptance assertions to source ACs and evaluate current UITest evidence."""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
import json
import math
from pathlib import Path
import re
import sys
import tempfile
from zipfile import BadZipFile, ZipFile

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from generate_execute_coverage import build
from hypium_evidence import parse_hypium


DEFAULT_PLAN = 'spec/baseline/plans/acceptance-plan.json'
PLAN_MARKER = 'spec/baseline/plans/complete.txt'
BEHAVIOR_REPORT = 'spec/verify/check5/behavior-summary.json'
ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]*')
STEP = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]*')
LAYOUT = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]*\.json')
SHA256 = re.compile(r'[0-9a-f]{64}')
ATTRIBUTES = {'id', 'type', 'text', 'enabled', 'clickable', 'selected', 'checked', 'content', 'backgroundColor'}
CASE_STATUSES = {'PASS', 'FAIL', 'BLOCKED', 'DEFERRED', 'ERROR', 'SKIP'}
RUN_CONTEXT = ('version_code', 'runner_sha256', 'fixture_sha256', 'database', 'capture_profile')
RESUME_CONTEXT = (*RUN_CONTEXT, 'device', 'hap_sha256', 'visual_scope_sha256', 'requested_case')


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
    index, _ = build(root, include_continuations=True)
    rows = {row['requirement_id']: row for row in index['requirements']}
    if not rows or len(rows) != len(index['requirements']):
        raise ValueError('acceptance criteria must have unique, nonempty IDs')
    return rows


def valid_name(value, pattern=ID) -> bool:
    return isinstance(value, str) and pattern.fullmatch(value) is not None


def resume_prefix(previous: dict, current: dict, planned: list[str]) -> list[str]:
    """Validate a completed prefix at an explicit clean scene boundary."""
    if not all(valid_name(current.get(key), SHA256)
               for key in ('runner_sha256', 'fixture_sha256', 'hap_sha256', 'visual_scope_sha256')):
        raise ValueError('resume requires runner, fixture, signed package and approved scope digests')
    if any(previous.get(key) != current.get(key) for key in RESUME_CONTEXT):
        raise ValueError('resume receipt context differs from this run')
    cases = previous.get('cases')
    if previous.get('planned_cases') != planned or not isinstance(cases, dict):
        raise ValueError('resume receipt does not cover the same planned scenarios')
    completed = list(cases)
    if (not completed or len(completed) >= len(planned) or completed != planned[:len(completed)]
            or previous.get('status') != 'PAUSED_AT_SCENARIO_BOUNDARY'
            or previous.get('next_scenario') != planned[len(completed)]
            or previous.get('resume_from') or previous.get('case_fixture_setup')
            or previous.get('fixture_setup', {}).get('status') != 'PASS'
            or not all(isinstance(case, dict) and case.get('status') == 'PASS' for case in cases.values())):
        raise ValueError('resume requires a passing prefix paused before the next scenario')
    return completed


def valid_selectors(values) -> bool:
    return isinstance(values, list) and all(
        isinstance(row, dict) and row and row.keys() <= ATTRIBUTES
        and all(isinstance(value, str) for value in row.values())
        for row in values
    )


def valid_descendants(values) -> bool:
    return isinstance(values, list) and all(
        isinstance(row, dict) and row.keys() == {'ancestor', 'descendant'}
        and valid_selectors([row['ancestor'], row['descendant']]) for row in values
    )


def bound_scenarios(entry: dict) -> set[str]:
    if entry['scenario'] is None:
        return set()
    return {entry['scenario'], *(row.get('scenario', entry['scenario']) for row in entry['assertions'])}


def criterion_text(row: dict) -> tuple[str, tuple[str, ...]]:
    return row['statement'], tuple(row['continuation'])


def seal(requirements: dict[str, dict], draft: dict, *, version: int = 2) -> dict:
    if draft.get('schema_version') != 1 or not isinstance(draft.get('bindings'), list):
        raise ValueError('expected schema-1 acceptance bindings')
    by_id = {}
    for binding in draft['bindings']:
        ac = binding.get('requirement_id') if isinstance(binding, dict) else None
        if not isinstance(ac, str) or ac not in requirements or ac in by_id:
            raise ValueError(f'unknown or duplicate AC: {ac}')
        hypium_test = {}
        if 'hypium' in binding:
            if not valid_hypium_test(binding['hypium']):
                raise ValueError(f'{ac}: expected a Hypium suite and test')
            hypium_test = {'hypium': binding['hypium']}
            if set(binding) == {'requirement_id', 'hypium'}:
                by_id[ac] = {'scenario': None, 'assertions': [], **hypium_test}
                continue
        scenario = binding.get('scenario')
        assertions = binding.get('assertions')
        if not valid_name(scenario) or not isinstance(assertions, list) or not assertions:
            raise ValueError(f'{ac}: expected named scenario and one or more assertions')
        for assertion in assertions:
            if not isinstance(assertion, dict) or assertion.keys() - {
                'scenario', 'step', 'layout', 'present', 'absent', 'descendants',
                'fully_visible', 'obstructions', 'within',
            }:
                raise ValueError(f'{ac}: invalid assertion keys')
            present = assertion.get('present')
            descendants = assertion.get('descendants', [])
            fully_visible = assertion.get('fully_visible', [])
            within = assertion.get('within', [])
            valid_within = isinstance(within, list) and all(
                isinstance(group, dict) and group.keys() == {'ancestor', 'present'}
                and valid_selectors([group['ancestor']]) and valid_selectors(group['present'])
                and bool(group['present']) for group in within
            )
            if (not valid_name(assertion.get('scenario', scenario))
                    or not valid_name(assertion.get('step'), STEP) or not valid_name(assertion.get('layout'), LAYOUT)
                    or not (present or descendants or fully_visible or within) or not valid_selectors(present)
                    or not valid_within
                    or not valid_selectors(fully_visible)
                    or not valid_selectors(assertion.get('obstructions', []))
                    or ('obstructions' in assertion and not fully_visible)
                    or not valid_selectors(assertion.get('absent', [])) or not valid_descendants(descendants)):
                raise ValueError(f'{ac}: each assertion requires a step, raw layout and a visible control')
        by_id[ac] = {'scenario': scenario, 'assertions': assertions, **hypium_test}

    criteria = []
    for ac, item in sorted(requirements.items()):
        row = {'requirement_id': ac, 'requirement_sha256': item['digest'], 'source_file': item['source_file'],
               **by_id.get(ac, {'scenario': None, 'assertions': []})}
        if version == 2:
            canonical = json.dumps(criterion_text(item), ensure_ascii=False, separators=(',', ':'))
            row['criterion_sha256'] = sha256(canonical.encode('utf-8')).hexdigest()
        criteria.append(row)
    return {'schema_version': version, 'criteria': criteria}


def compare_draft(previous: dict[str, dict], current: dict[str, dict], draft: dict,
                  current_draft: dict | None = None) -> dict:
    """Compare historical binding assertions with current spec text without copying them."""
    if not isinstance(draft, dict) or (current_draft is not None and not isinstance(current_draft, dict)):
        raise ValueError('expected acceptance draft objects')
    seal(previous, draft)
    if current_draft is not None:
        seal(current, current_draft)
    current_bound = {row['requirement_id'] for row in (current_draft or {}).get('bindings', [])}

    by_text = {}
    for name, row in current.items():
        by_text.setdefault(criterion_text(row), []).append(name)

    def source(row):
        if row is None:
            return None
        return {key: row[key] for key in ('source_file', 'statement', 'digest', 'continuation')}

    rows = []
    for binding in draft['bindings']:
        name = binding['requirement_id']
        old, new = previous[name], current.get(name)
        if new is None:
            status = 'ID_MISSING'
        elif criterion_text(old) != criterion_text(new):
            status = 'TEXT_CHANGED'
        else:
            status = 'AC_UNCHANGED'
        rows.append({'requirement_id': name, 'status': status, 'historical_ac': source(old),
                     'current_ac': source(new),
                     'current_draft_has_binding': name in current_bound if current_draft is not None else None,
                     'historical_binding': binding,
                     'same_text_other_ids': sorted(set(by_text.get(criterion_text(old), ())) - {name})})
    return {'schema_version': 1, 'plan_status': 'DRAFT_COMPARISON',
            'criterion_counts': {'historical': len(previous), 'current': len(current),
                                 'current_bound': len(current_bound) if current_draft is not None else None,
                                 'current_unbound': len(current) - len(current_bound) if current_draft is not None else None},
            'binding_counts': dict(Counter(row['status'] for row in rows)), 'bindings': rows}


def controls(tree: dict):
    attributes = tree['attributes']
    if attributes.get('visible') == 'true':
        yield attributes
    for child in tree['children']:
        yield from controls(child)


def has_descendant(tree: dict, relationship: dict) -> bool:
    ancestor = relationship['ancestor']
    descendant = relationship['descendant']

    def visit(node, matched_ancestor=False):
        attrs = node['attributes']
        if attrs.get('visible') == 'true':
            if matched_ancestor and all(attrs.get(key) == value for key, value in descendant.items()):
                return True
            matched_ancestor = matched_ancestor or all(attrs.get(key) == value for key, value in ancestor.items())
        return any(visit(child, matched_ancestor) for child in node['children'])

    return visit(tree)


def has_grouped_controls(tree: dict, group: dict) -> bool:
    """Require all fields inside one visible instance of the containing control."""
    def visible_descendants(node):
        attrs = node['attributes']
        if attrs.get('visible') == 'false':
            return
        if attrs.get('visible') == 'true':
            yield attrs
        for child in node['children']:
            yield from visible_descendants(child)

    def visit(node):
        attrs = node['attributes']
        if attrs.get('visible') == 'false':
            return False
        if attrs.get('visible') == 'true' and all(
            attrs.get(key) == value for key, value in group['ancestor'].items()
        ):
            descendants = [attrs for child in node['children'] for attrs in visible_descendants(child)]
            if all(any(all(item.get(key) == value for key, value in selector.items())
                       for item in descendants) for selector in group['present']):
                return True
        return any(visit(child) for child in node['children'])

    return visit(tree)


def asserted_layout(directory: Path, assertion: dict) -> tuple[dict | None, str | None]:
    path = (directory / assertion['layout']).resolve()
    if path.parent != directory or not path.is_file():
        return None, 'LAYOUT_MISSING'
    try:
        raw = path.read_bytes()
        tree = json.loads(raw)
        nodes = list(controls(tree))
        relationships_match = all(has_descendant(tree, pair) for pair in assertion.get('descendants', [])) and all(
            has_grouped_controls(tree, group) for group in assertion.get('within', [])
        )
    except OSError:
        return None, 'LAYOUT_UNREADABLE'
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
        return None, 'LAYOUT_INVALID'

    def matching_nodes(selector):
        return [node for node in nodes if all(node.get(key) == value for key, value in selector.items())]

    if (not relationships_match or not all(map(matching_nodes, assertion['present']))
            or any(map(matching_nodes, assertion.get('absent', [])))):
        return None, 'LAYOUT_ASSERTION_FAILED'
    if assertion.get('fully_visible'):
        verify_scripts = Path(__file__).resolve().parents[2] / 'i2h-verify/scripts'
        if str(verify_scripts) not in sys.path:
            sys.path.insert(0, str(verify_scripts))
        from uitest_action import control_fits_viewport

        overlays = matching_nodes({'type': 'TabBar'})
        for selector in assertion.get('obstructions', []):
            matches = matching_nodes(selector)
            if not matches:
                return None, 'OBSTRUCTION_NOT_OBSERVED'
            overlays.extend(matches)
        for selector in assertion['fully_visible']:
            matches = matching_nodes(selector)
            if len(matches) != 1 or not control_fits_viewport(matches[0], tree['attributes'], overlays):
                return None, 'CONTROL_NOT_FULLY_VISIBLE'
    return {'path': path.name, 'sha256': sha256(raw).hexdigest(), 'step': assertion['step']}, None


def check_criterion(entry: dict, latest: dict) -> dict:
    scenario = entry['scenario']
    if scenario is None:
        return {**entry, 'status': 'NO_BINDING'}
    item = {**entry, 'status': 'UNVERIFIED'}
    case, run = latest.get(scenario, (None, None))
    if case is None or case['status'] != 'PASS':
        item['issues'] = [{'code': 'SCENARIO_NOT_PASSED', 'status': case['status'] if case else 'NOT_RUN'}]
        return item
    layouts, issues = [], []
    for assertion in entry['assertions']:
        step = assertion['step']
        assertion_scenario = assertion.get('scenario', scenario)
        matched_case, matched_run = latest.get(assertion_scenario, (None, None))
        steps = matched_case.get('passed_steps') if matched_case else None
        if matched_case is None or matched_case['status'] != 'PASS':
            issues.append({'code': 'SCENARIO_NOT_PASSED', 'scenario': assertion_scenario,
                           'status': matched_case['status'] if matched_case else 'NOT_RUN', 'step': step})
            continue
        if not isinstance(steps, list) or step not in steps:
            evidence, problem = None, 'STEP_MISSING'
        else:
            evidence, problem = asserted_layout(matched_run.path.parent, assertion)
        context = {} if assertion_scenario == scenario else {
            'scenario': assertion_scenario, 'run': matched_run.reference()}
        if problem:
            issues.append({'code': problem, 'step': step, 'layout': assertion['layout'], **context})
        else:
            layouts.append({**evidence, **context})
    if issues:
        item.update(issues=issues, run=run.reference())
    else:
        item.update(status='DIRECT_EVIDENCE', evidence=layouts, run=run.reference())
    return item


def hash_package(hap: Path) -> str:
    package_digest = sha256()
    with hap.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            package_digest.update(chunk)
    return package_digest.hexdigest()


def verify_package_inputs(run: Run, hap: Path, verified: dict[str, str]) -> None:
    """Bind deterministic scenario inputs to the actual signed package."""
    for scenario, case in run.data['cases'].items():
        evidence = case.get('package_input')
        if evidence is None:
            continue
        member = evidence['member']
        if member not in verified:
            try:
                with ZipFile(hap) as package:
                    info, = (info for info in package.infolist()
                             if info.filename == member and not info.is_dir())
                    digest = sha256()
                    with package.open(info) as stream:
                        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                            digest.update(chunk)
                    verified[member] = digest.hexdigest()
            except (BadZipFile, NotImplementedError, RuntimeError, ValueError) as error:
                raise ValueError(f'invalid signed package input: {scenario}: {member}') from error
        if verified[member] != evidence['sha256']:
            raise ValueError(f'signed package input digest mismatch: {scenario}: {member}')


def valid_hypium_test(test) -> bool:
    return isinstance(test, dict) and set(test) == {'suite', 'test'} and all(
        valid_name(value, STEP) for value in test.values())


def load_hypium(receipt_path: Path, app_hash: str, test_hap: Path, device: str) -> tuple[dict, dict]:
    receipt_path, test_hap = receipt_path.resolve(strict=True), test_hap.resolve(strict=True)
    raw = receipt_path.read_bytes()
    receipt = json.loads(raw)
    test_hash = hash_package(test_hap)
    if not isinstance(receipt, dict):
        raise ValueError('expected native Hypium receipt')
    if (receipt.get('app_hap_sha256'), receipt.get('test_hap_sha256'), receipt.get('device')) != (
        app_hash, test_hash, device
    ) or type(receipt.get('exit_code')) is not int or receipt['exit_code'] != 0:
        raise ValueError('Hypium receipt does not match the packages, device or successful command exit')
    log = (receipt_path.parent / 'hypium.log').read_bytes()
    log_digest = sha256(log).hexdigest()
    if receipt.get('log_sha256') != log_digest:
        raise ValueError('Hypium log digest mismatch')
    parsed = parse_hypium(log.decode('utf-8'))
    outcomes = {(row['suite'], row['test']): row['status'] for row in parsed['cases']}
    return outcomes, {'run': {'path': str(receipt_path), 'sha256': sha256(raw).hexdigest()},
                      'signed_test_hap': str(test_hap), 'test_hap_sha256': test_hash,
                      'log_sha256': log_digest, 'test_counts': parsed['counts']}


def hypium_result(test: dict, outcomes: dict) -> dict:
    outcome = outcomes.get((test['suite'], test['test']), 'NOT_RUN')
    return {'test_status': outcome, 'status': 'DIRECT_EVIDENCE' if outcome == 'PASS' else 'UNVERIFIED'}


def evaluate_criterion(entry: dict, latest: dict, outcomes: dict) -> dict:
    if 'hypium' not in entry:
        return check_criterion(entry, latest)
    result = hypium_result(entry['hypium'], outcomes)
    if entry['scenario'] is None:
        return {**entry, **result}
    ui = check_criterion(entry, latest)
    if ui['status'] != 'DIRECT_EVIDENCE':
        result['status'] = 'UNVERIFIED'
    return {**ui, **result}


def evaluate_hypium(requirements: dict, draft: dict, receipt_path: Path,
                    app_hap: Path, test_hap: Path, device: str) -> dict:
    app_hash = hash_package(app_hap)
    outcomes, evidence = load_hypium(receipt_path, app_hash, test_hap, device)
    if draft.get('schema_version') != 1 or not isinstance(draft.get('bindings'), list):
        raise ValueError('expected schema-1 Hypium bindings')
    selected = {}
    for row in draft['bindings']:
        ac = row.get('requirement_id') if isinstance(row, dict) else None
        if not isinstance(ac, str) or ac not in requirements or ac in selected or not all(
            valid_name(row.get(key), STEP) for key in ('suite', 'test')
        ):
            raise ValueError(f'invalid or duplicate Hypium binding: {ac}')
        selected[ac] = {'suite': row['suite'], 'test': row['test'], **hypium_result(row, outcomes)}
    rows = [
        {'requirement_id': ac, 'requirement_sha256': spec['digest'], 'source_file': spec['source_file'],
         **selected.get(ac, {'status': 'NO_BINDING'})}
        for ac, spec in sorted(requirements.items())
    ]
    return {'schema_version': 1, 'plan_status': 'DRAFT', 'device': device,
            'app_hap_sha256': app_hash, **evidence, 'counts': dict(Counter(row['status'] for row in rows)),
            'criteria': rows}


def valid_failure_diagnostic(case: dict) -> bool:
    diagnostic = case['failure_diagnostic']
    if (case['status'] not in {'FAIL', 'BLOCKED', 'ERROR'} or not isinstance(diagnostic, dict)
            or not valid_name(diagnostic.get('stage'))
            or ('code' in diagnostic and not valid_name(diagnostic['code'], STEP))):
        return False
    extra_fields = set(diagnostic) - {'stage', 'code'}
    if not extra_fields:
        return True
    if (extra_fields != {'device_model', 'reference'} or case['status'] != 'BLOCKED'
            or diagnostic['stage'] != 'device_preflight' or not valid_name(case.get('device_capability'))):
        return False
    model, reference = diagnostic['device_model'], diagnostic['reference']
    return (isinstance(model, str) and bool(model.strip()) and isinstance(reference, str)
            and re.fullmatch(r'https://[^/\s]+/\S+', reference) is not None)


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
    for scenario, case in cases.items():
        if 'package_input' in case:
            evidence = case['package_input']
            member = evidence.get('member') if isinstance(evidence, dict) else None
            if (not isinstance(member, str) or set(evidence) != {'member', 'sha256'}
                    or not all(valid_name(part, STEP) for part in member.split('/'))
                    or not valid_name(evidence['sha256'], SHA256)):
                raise ValueError(f'invalid package input receipt: {scenario}: {path}')
        if 'failure_diagnostic' in case and not valid_failure_diagnostic(case):
            raise ValueError(f'invalid failure diagnostic: {scenario}: {path}')
    if 'fixture_setup' in run:
        setup = run['fixture_setup']
        if (not isinstance(setup, dict) or setup.get('status') not in ('PASS', 'FAIL')
                or (setup['status'] == 'FAIL' and
                    (cases or not isinstance(setup.get('reason'), str) or not setup['reason'].strip()))):
            raise ValueError(f'invalid fixture setup receipt: {path}')
    setups = run.get('case_fixture_setup', {})
    if not isinstance(setups, dict) or setups.keys() - set(planned):
        raise ValueError(f'invalid scenario fixture scope: {path}')
    for scenario, setup in setups.items():
        if (not isinstance(setup, dict) or setup.get('status') not in ('PASS', 'FAIL')
                or (setup['status'] == 'FAIL' and (
                    scenario in cases or not isinstance(setup.get('reason'), str)
                    or not setup['reason'].strip()))):
            raise ValueError(f'invalid scenario fixture setup: {scenario}: {path}')
    return Run(path, sha256(raw).hexdigest(), run)


def admit_runs(paths: list[Path], hap_hash: str, device: str, *, hap: Path | None = None) -> list[Run]:
    runs = [load_run(path) for path in paths]
    verified_inputs: dict[str, str] = {}
    for index, run in enumerate(runs):
        if (run.data.get('hap_sha256'), run.data.get('device')) != (hap_hash, device):
            raise ValueError(f'device or signed package mismatch: {run.path}')
        if hap is not None:
            verify_package_inputs(run, hap, verified_inputs)
        if 'resume_from' in run.data:
            link = run.data['resume_from']
            if not isinstance(link, dict) or not index:
                raise ValueError('resumed receipt requires its original checkpoint first')
            parent = runs[index - 1]
            completed = resume_prefix(parent.data, run.data, parent.data['planned_cases'])
            if (link != {**parent.reference(), 'prior_passes': completed}
                    or run.data['planned_cases'] != parent.data['planned_cases'][len(completed):]):
                raise ValueError('resumed receipt does not match its checkpoint and remaining scenarios')
            if run.data['cases'] and run.data.get('fixture_setup', {}).get('status') != 'PASS':
                raise ValueError('resumed scenarios require a successful fixture recheck')
    if len({run.digest for run in runs}) != len(runs):
        raise ValueError('duplicate runner receipt')
    return runs


def latest_results(runs: list[Run]) -> dict:
    latest = {}
    for run in runs:
        for scenario in run.data['planned_cases']:
            latest[scenario] = (run.data['cases'].get(scenario), run)
    return latest


def evaluate_runs(plan: dict, requirements: dict[str, dict], runs: list[Run], hap_hash: str, device: str,
                  hypium_outcomes: dict | None = None) -> dict:
    version = plan.get('schema_version') if isinstance(plan, dict) else None
    if type(version) is not int or version not in (1, 2) or not isinstance(plan.get('criteria'), list):
        raise ValueError('expected sealed schema-1 or schema-2 acceptance plan')
    declared = [row for row in plan['criteria'] if isinstance(row, dict) and row.get('scenario') is not None]
    bindings = [{key: row[key] for key in ('requirement_id', 'scenario', 'assertions', 'hypium') if key in row}
                for row in declared]
    bindings.extend({'requirement_id': row['requirement_id'], 'hypium': row['hypium']}
                    for row in plan['criteria'] if isinstance(row, dict) and 'hypium' in row
                    and row.get('scenario') is None)
    if seal(requirements, {'schema_version': 1, 'bindings': bindings}, version=version) != plan:
        raise ValueError('acceptance plan is stale or does not cover the current source criteria')
    if any(len(bound_scenarios(entry)) > 1 for entry in plan['criteria']):
        require_same_run_context(runs)
    latest = latest_results(runs)
    rows = [evaluate_criterion(entry, latest, hypium_outcomes or {}) for entry in plan['criteria']]
    return {'schema_version': 1, 'device': device, 'hap_sha256': hap_hash, 'criteria': rows,
            'counts': dict(Counter(row['status'] for row in rows))}


def evaluate(plan: dict, requirements: dict[str, dict], runs: list[Path], hap: Path, device: str,
             hypium_run: Path | None = None, signed_test_hap: Path | None = None) -> dict:
    hap_hash = hash_package(hap)
    outcomes, evidence = optional_hypium(hypium_run, hap_hash, signed_test_hap, device)
    report = evaluate_runs(plan, requirements, admit_runs(runs, hap_hash, device, hap=hap), hap_hash, device, outcomes)
    if evidence is not None:
        report['hypium_evidence'] = evidence
    return report


def optional_hypium(run: Path | None, hap_hash: str, test_hap: Path | None, device: str):
    if (run is None) != (test_hap is None):
        raise ValueError('Hypium evidence requires both the run and the signed test HAP')
    if run is None:
        return {}, None
    return load_hypium(run, hap_hash, test_hap, device)


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


def require_same_run_context(runs: list[Run]) -> None:
    if len(runs) < 2:
        return
    initial = runs[0].data
    if not all(valid_name(initial.get(key), SHA256) for key in ('runner_sha256', 'fixture_sha256')):
        raise ValueError('combining receipts requires runner_sha256 and fixture_sha256')
    if any(run.data.get(key) != initial.get(key) for run in runs[1:] for key in RUN_CONTEXT):
        raise ValueError('runner or fixture context mismatch')


def behavior_report(plan: dict, requirements: dict[str, dict], runs: list[Run], baseline: Run,
                    requested: list[str], hap_hash: str, device: str,
                    hypium_outcomes: dict | None = None) -> dict:
    scope = baseline.data['planned_cases']
    scope_set = set(scope)
    bound = set().union(*(bound_scenarios(entry) for entry in plan['criteria']))
    if requested and (len(set(requested)) != len(requested) or set(requested) != set(runs[-1].data['planned_cases'])):
        raise ValueError('requested recheck scenarios must match the latest runner receipt')
    require_same_run_context(runs)
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
        if case is not None and 'failure_diagnostic' in case:
            row['failure_diagnostic'] = case['failure_diagnostic']
        if case is not None and 'package_input' in case:
            row['package_input'] = case['package_input']
        if case is not None and case['status'] == 'BLOCKED':
            capability = case.get('device_capability')
            if valid_name(capability):
                row['device_capability'] = capability
        if case is not None and case['status'] in {'FAIL', 'ERROR'}:
            recovery = case.get('fixture_recovery')
            if isinstance(recovery, dict) and recovery.get('status') in ('PASS', 'FAIL'):
                row['fixture_recovery'] = {'status': recovery['status']}
                if isinstance(recovery.get('reason'), str):
                    row['fixture_recovery']['reason'] = recovery['reason']
        if case is not None and case['status'] == 'ERROR':
            windows = case.get('focused_windows')
            if isinstance(windows, list) and all(
                isinstance(window, dict) and all(isinstance(window.get(key), str) for key in ('bundle', 'page'))
                for window in windows
            ):
                row['focused_windows'] = [{key: window[key] for key in ('bundle', 'page')} for window in windows]
            timeout = case.get('device_timeout')
            seconds = timeout.get('seconds') if isinstance(timeout, dict) else None
            if type(seconds) in (int, float) and 0 < seconds <= sys.float_info.max and math.isfinite(seconds):
                row['device_timeout'] = {'seconds': seconds}
        if run is not None:
            row['run'] = run.reference()
            setup = run.data.get('case_fixture_setup', {}).get(scenario)
            if setup is not None:
                row['fixture_setup'] = {'status': setup['status']}
                if setup['status'] == 'FAIL':
                    row['fixture_setup']['reason'] = setup['reason']
        rows.append(row)
    acceptance = evaluate_runs(plan, requirements, runs, hap_hash, device, hypium_outcomes)
    for criterion in acceptance['criteria']:
        # The approved plan owns assertions. The report preserves identity and
        # outcomes without repeating the full inputs to the evaluator.
        criterion.pop('assertions')
    counts = dict(Counter(row['status'] for row in rows))
    if counts.get('FAIL') or any(row.get('test_status') in {'FAIL', 'ERROR'} for row in acceptance['criteria']):
        status = 'FAIL'
    elif counts.get('PASS') == len(rows) and acceptance['counts'].get('DIRECT_EVIDENCE') == len(requirements):
        status = 'PASS'
    else:
        status = 'INCOMPLETE'
    report = {**acceptance, 'counts': {'criteria': acceptance['counts'], 'scenarios': counts},
            'status': status, 'scenario_total': len(rows), 'criterion_total': len(requirements),
            'scope': {'basis': 'runner_receipt_and_bound_scenarios', 'baseline': baseline.reference(),
                      'requested_recheck': requested},
            'runner_context': {key: runs[0].data[key] for key in RUN_CONTEXT if key in runs[0].data},
            'runs': [run.reference() for run in runs], 'scenarios': rows}
    setup_runs = [{'run': run.reference(), 'status': setup['status'],
                   **({'reason': setup['reason']} if setup['status'] == 'FAIL' else {})}
                  for run in runs if (setup := run.data.get('fixture_setup')) is not None]
    if setup_runs:
        report['fixture_setup'] = setup_runs
    return report


def build_behavior(root: Path, requirements: dict, name: str | None, hap: Path, device: str,
                   receipt_paths: list[Path], baseline_path: Path | None, requested: list[str],
                   hypium_run: Path | None = None, signed_test_hap: Path | None = None) -> dict:
    plan_path = (root / (name or DEFAULT_PLAN)).resolve()
    if root not in plan_path.parents:
        raise ValueError('acceptance plan must stay inside the project')
    raw_plan = plan_path.read_bytes() if name is not None or plan_path.exists() else None
    plan_digest = sha256(raw_plan).hexdigest() if raw_plan is not None else None
    is_approved = plan_digest is not None and approved_plan(root, plan_path, plan_digest)
    plan = json.loads(raw_plan) if is_approved else seal(requirements, {'schema_version': 1, 'bindings': []})
    hap_hash = hash_package(hap)
    runs = admit_runs(receipt_paths, hap_hash, device, hap=hap)
    if requested and baseline_path is None and len(runs) == 1:
        raise ValueError('scoped recheck requires the first full runner receipt as baseline')
    baseline = load_run(baseline_path) if baseline_path else runs[0]
    outcomes, evidence = optional_hypium(hypium_run, hap_hash, signed_test_hap, device)
    report = behavior_report(plan, requirements, runs, baseline, requested, hap_hash, device, outcomes)
    if evidence is not None:
        report['hypium_evidence'] = evidence
    plan_status = 'APPROVED' if is_approved else 'UNAPPROVED' if plan_digest else 'MISSING'
    return {**report, 'plan_status': plan_status, 'plan_sha256': plan_digest,
            'plan_path': plan_path.relative_to(root).as_posix(), 'signed_hap': str(hap.resolve())}


def replay_behavior(root: Path, report: dict) -> dict:
    if not isinstance(report, dict) or report.get('status') != 'PASS':
        raise ValueError('functional report is not PASS')
    evidence = report.get('hypium_evidence')
    return build_behavior(
        root, current_requirements(root), report['plan_path'], Path(report['signed_hap']), report['device'],
        [Path(run['path']) for run in report['runs']], Path(report['scope']['baseline']['path']),
        report['scope']['requested_recheck'],
        Path(evidence['run']['path']) if evidence is not None else None,
        Path(evidence['signed_test_hap']) if evidence is not None else None,
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
    diff = modes.add_parser('compare-draft', help='Compare historical AC bindings against current source AC text')
    diff.add_argument('--previous-project-root', required=True, type=Path)
    diff.add_argument('--previous-draft', required=True, type=Path)
    diff.add_argument('--draft', type=Path, help='current draft for the bound/unbound counts')
    check = modes.add_parser('evaluate')
    hypium = modes.add_parser('evaluate-hypium', help='Preview AC bindings against a native Hypium run')
    hypium.add_argument('--draft', type=Path, required=True)
    hypium.add_argument('--run', type=Path, required=True)
    hypium.add_argument('--signed-hap', type=Path, required=True)
    hypium.add_argument('--signed-test-hap', type=Path, required=True)
    hypium.add_argument('--device', required=True)
    behavior = modes.add_parser('behavior', help='Report first functional Verify or a scoped recheck')
    for command in (check, behavior):
        command.add_argument('--plan', default=None, help=f'default: {DEFAULT_PLAN}')
        command.add_argument('--run', type=Path, action='append', required=True, help='receipt, oldest first')
        command.add_argument('--signed-hap', type=Path, required=True)
        command.add_argument('--device', required=True)
        command.add_argument('--hypium-run', type=Path, help='native Hypium receipt for logic bindings')
        command.add_argument('--signed-test-hap', type=Path, help='signed test package for the Hypium receipt')
    check.add_argument('--out', default='spec/verify/check5/acceptance-evidence.json')
    check.add_argument('--draft', type=Path, help='Preview unapproved bindings without writing Plan or Verify reports')
    behavior.add_argument('--baseline', type=Path, help='previous receipt used only for the scenario list')
    behavior.add_argument('--case', action='append', default=[], help='scenario planned in the latest recheck')
    args = parser.parse_args()
    try:
        root = args.project_root.resolve(strict=True)
        requirements = current_requirements(root)
        if args.mode == 'seal':
            plan = seal(requirements, read(args.draft))
            write(root, DEFAULT_PLAN, plan)
            summary = {'criteria': len(requirements),
                       'planned': sum(row['scenario'] is not None or 'hypium' in row for row in plan['criteria'])}
        elif args.mode == 'compare-draft':
            historical = current_requirements(args.previous_project_root.resolve(strict=True))
            previous_raw = args.previous_draft.read_bytes()
            current_raw = args.draft.read_bytes() if args.draft else None
            report = compare_draft(historical, requirements, json.loads(previous_raw),
                                   json.loads(current_raw) if current_raw is not None else None)
            report['previous_draft_sha256'] = sha256(previous_raw).hexdigest()
            report['current_draft_sha256'] = sha256(current_raw).hexdigest() if current_raw is not None else None
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0
        elif args.mode == 'evaluate-hypium':
            report = evaluate_hypium(requirements, read(args.draft), args.run,
                                     args.signed_hap, args.signed_test_hap, args.device)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0
        elif args.mode == 'evaluate':
            if args.draft is not None:
                if args.plan is not None:
                    raise ValueError('--draft and --plan cannot be combined')
                draft = read(args.draft)
                plan = seal(requirements, draft)
                report = evaluate(plan, requirements, args.run, args.signed_hap, args.device,
                                  args.hypium_run, args.signed_test_hap)
                print(json.dumps({**report, 'plan_status': 'DRAFT'}, ensure_ascii=False, indent=2))
                return 0
            plan_path = (root / (args.plan or DEFAULT_PLAN)).resolve(strict=True)
            if root not in plan_path.parents:
                raise ValueError('acceptance plan must stay inside the project')
            if (root / args.out).resolve() == plan_path:
                raise ValueError('report path cannot overwrite the acceptance plan')
            raw_plan = plan_path.read_bytes()
            if args.hypium_run is not None or args.signed_test_hap is not None:
                raise ValueError('use evaluate --draft or behavior for mixed Hypium evidence')
            report = evaluate(json.loads(raw_plan), requirements, args.run, args.signed_hap, args.device)
            write(root, args.out, {**report, 'plan_sha256': sha256(raw_plan).hexdigest()})
            summary = report['counts']
        else:
            report = build_behavior(root, requirements, args.plan, args.signed_hap, args.device,
                                    args.run, args.baseline, args.case, args.hypium_run, args.signed_test_hap)
            output = root / BEHAVIOR_REPORT
            inputs = [Path(run['path']) for run in [*report['runs'], report['scope']['baseline']]]
            inputs.extend((root / report['plan_path'], Path(report['signed_hap'])))
            if evidence := report.get('hypium_evidence'):
                receipt_path = Path(evidence['run']['path'])
                inputs.extend((receipt_path, receipt_path.with_name('hypium.log').resolve(),
                               Path(evidence['signed_test_hap'])))
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
