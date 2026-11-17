"""Select reusable appearance judgments for the current visual inputs."""
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from hashlib import sha256
import json
from pathlib import Path
import re
from subprocess import TimeoutExpired


FLASH_RECHECK_MODELS = frozenset({
    'deepseek-flash', 'deepseek-v4-flash', 'deepseek-v4.1-flash',
    'deepseek-v4.1-flash-1017', 'deepseek/deepseek-v4.1-flash',
})


def image_dimensions(raw):
    """Read original PNG or JPEG dimensions without an image-decoding dependency."""
    if raw.startswith(b'\x89PNG\r\n\x1a\n') and raw[12:16] == b'IHDR' and len(raw) >= 24:
        width, height = (int.from_bytes(raw[i:i+4], 'big') for i in (16, 20))
        if width and height:
            return [width, height]
    elif raw.startswith(b'\xff\xd8'):
        offset = 2
        while offset + 4 <= len(raw) and raw[offset] == 255:
            while offset < len(raw) and raw[offset] == 255:
                offset += 1
            if offset + 3 > len(raw) or raw[offset] in (0xD9, 0xDA):
                break
            marker = raw[offset]
            size = int.from_bytes(raw[offset+1:offset+3], 'big')
            if size < 2 or offset + 1 + size > len(raw):
                break
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF) and size >= 8:
                height, width = (int.from_bytes(raw[offset+i:offset+i+2], 'big') for i in (4, 6))
                if width and height:
                    return [width, height]
            offset += 1 + size
    raise ValueError('appearance image lacks valid PNG or JPEG dimensions')


def platform_review_issue(item, binding):
    """Reject missing platform observations or an explicit reversed dimension claim."""
    expected = binding.get('platform_dimensions')
    if expected is None:
        return None
    if item.get('platform_dimensions') != expected:
        return 'appearance review did not identify the dimensions of both platform originals'
    if expected['ios'] == expected['harmony']:
        return None
    notes = item.get('notes', '')
    # Restrict this check to adjacent platform and dimension claims.
    for match in re.finditer(r'\b(iOS|iPhone\s*17|HarmonyOS)\s*[:：=]?\s*[\(（]?\s*(\d{3,5})\s*[x×]\s*(\d{3,5})\b',
                             notes, re.I):
        side = 'harmony' if match[1].lower() == 'harmonyos' else 'ios'
        other = 'ios' if side == 'harmony' else 'harmony'
        if list(map(int, match.groups()[1:])) == expected[other]:
            return f'appearance notes explicitly assign the other image dimensions to {side}'
    return None


def prioritize_review_groups(groups, previous_groups):
    """Schedule slow single-comparison reviews early using verified timing samples."""
    durations = {}
    for receipt in previous_groups:
        bindings = receipt.get('review_inputs')
        seconds = receipt.get('elapsed_seconds')
        if (receipt.get('verified') is True and isinstance(bindings, dict) and len(bindings) == 1
                and type(seconds) in (int, float) and 0 < seconds <= 600):
            name = next(iter(bindings))
            durations[name] = max(durations.get(name, 0), seconds)
    return sorted(groups, key=lambda group: -max(
        (durations.get(row['comparison_id'], 0) for row in group), default=0))


def review_native_groups(review, groups, first, *, workers=4):
    """Run independent groups and split a timed-out multi-frame group once."""
    results = {}
    next_id = first + len(groups)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        pending = {}

        def schedule(index, rows, parent=None):
            timeout = min(600, 120 + 180 * len(rows))
            future = pool.submit(review, index, rows, timeout_seconds=timeout)
            pending[future] = (index, rows, parent)

        for index, rows in enumerate(groups, first):
            schedule(index, rows)
        while pending:
            completed, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in sorted(completed, key=lambda f: pending[f][0]):
                index, rows, parent = pending.pop(future)
                try:
                    result = future.result()
                except (OSError, TimeoutExpired) as error:
                    timed_out = isinstance(error, TimeoutExpired)
                    result = {'group': index, 'verified': False, 'exit_code': 124 if timed_out else None,
                              'review_inputs': {}, 'comparison_ids': [row['comparison_id'] for row in rows],
                              'issue': 'image review timed out' if timed_out else str(error)}
                results[index] = {**result, 'parent_group': parent}
                if result['exit_code'] == 124 and len(rows) > 1:
                    for row in rows:
                        schedule(next_id, [row], index)
                        next_id += 1
    return [results[index] for index in sorted(results)]


def platform_recheck_ids(sources, expected, allowed_models):
    """Find current platform failures eligible for one labeled, single-pair review."""
    accepted, conflicts = reusable_reviews(sources, expected)
    pending = {}
    for _, receipt, report in sources:
        bindings = receipt.get('review_inputs')
        outcome = receipt.get('outcome') or {}
        models = receipt.get('models')
        group = receipt.get('group')
        if (receipt.get('verified') is not False or receipt.get('exit_code') != 0
                or type(group) is not int
                or not isinstance(outcome, dict)
                or not receipt.get('report_edited') or receipt.get('missing_image_reads') != []
                or receipt.get('missing_source_context') != [] or outcome.get('is_error') is not False
                or outcome.get('context_window') != 1_000_000
                or not isinstance(models, list) or not models
                or any(not isinstance(model, str) or model not in allowed_models for model in models)
                or not isinstance(outcome.get('session_model'), str)
                or not outcome['session_model'].endswith('[1m]')
                or outcome['session_model'].lower().removesuffix('[1m]') not in allowed_models
                or not isinstance(bindings, dict) or not bindings):
            continue
        try:
            raw = report.read_bytes()
            if sha256(raw).hexdigest() != receipt.get('report_sha256'):
                continue
            rows = json.loads(raw)['comparisons']
            if not isinstance(rows, list) or len(rows) != len(bindings):
                continue
            by_id = {row['comparison_id']: row for row in rows}
            if set(by_id) != set(bindings):
                continue
            issues = {name: platform_review_issue(row, bindings[name]) for name, row in by_id.items()}
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            continue
        for name, issue in issues.items():
            binding = expected.get(name)
            if (binding is not None and issue and issue == receipt.get('issue') and binding == bindings[name]
                    and not binding.get('source_context_sha256') and name not in accepted
                    and name not in conflicts):
                pending[name] = group
    return pending


def labeled_recheck_ids(sources, expected, allowed_models):
    """Plan one labeled follow-up for current platform failures or singleton timeouts."""
    pending = platform_recheck_ids(sources, expected, allowed_models)
    accepted, conflicts = reusable_reviews(sources, expected)
    for _, receipt, report in sources:
        inputs = receipt.get('review_inputs')
        group = receipt.get('group')
        if (receipt.get('exit_code') != 124 or receipt.get('verified') is not False
                or receipt.get('issue') == 'visual inputs changed during the review'
                or not isinstance(inputs, dict) or len(inputs) != 1 or type(group) is not int):
            continue
        name, binding = next(iter(inputs.items()))
        if (not isinstance(binding, dict) or binding != expected.get(name)
                or not binding.get('platform_dimensions') or binding.get('source_context_sha256')
                or name in accepted or name in conflicts):
            continue
        try:
            if sha256(report.read_bytes()).hexdigest() != receipt.get('report_sha256'):
                continue
        except OSError:
            continue
        pending.setdefault(name, group)
    return pending


def attempted_labeled_rechecks(sources, expected):
    """Find persisted labeled attempts for the exact current inputs."""
    attempted = set()
    for _, receipt, _ in sources:
        inputs = receipt.get('review_inputs')
        if (type(receipt.get('recovery_for')) is not int
                or not isinstance(inputs, dict) or len(inputs) != 1):
            continue
        name, binding = next(iter(inputs.items()))
        if isinstance(binding, dict) and binding.get('source_context_sha256') and binding == expected.get(name):
            attempted.add(name)
    return attempted


def reusable_reviews(
    sources: list[tuple[Path, dict, Path]], expected: dict[str, dict]
) -> tuple[dict[str, tuple[Path, dict]], set[str]]:
    """Return current judgments and IDs whose valid reviews disagree.

    Expected identities come from the current comparison inputs. A valid
    transport receipt alone does not settle an unresolved or conflicting pair.
    """
    accepted = {}
    conflicting = set()
    for receipt_path, receipt, report in sources:
        if receipt.get('verified') is not True:
            continue
        bindings = receipt.get('review_inputs')
        if not isinstance(bindings, dict):
            continue
        try:
            raw = report.read_bytes()
            if sha256(raw).hexdigest() != receipt.get('report_sha256'):
                continue
            entries = json.loads(raw).get('comparisons')
        except (OSError, ValueError, AttributeError):
            continue
        if not isinstance(entries, list) or not all(isinstance(row, dict) for row in entries):
            continue
        ids = [row.get('comparison_id') for row in entries]
        if not all(isinstance(name, str) and name for name in ids) or len(set(ids)) != len(ids):
            continue
        for name, row in zip(ids, entries):
            if name not in expected or bindings.get(name) != expected[name]:
                continue
            side_check = expected[name].get('expected_side_check')
            if side_check is not None and row.get('side_check') != side_check:
                continue
            if platform_review_issue(row, expected[name]):
                continue
            verdict = row.get('verdict')
            if verdict not in ('PASS', 'FAIL') or row.get('severity') not in ('normal', 'critical'):
                continue
            prior = accepted[name][1] if name in accepted else None
            if prior and (prior['verdict'] != verdict or (verdict == 'FAIL' and prior['severity'] != row['severity'])):
                conflicting.add(name)
            accepted[name] = receipt_path, row
    return {name: row for name, row in accepted.items() if name not in conflicting}, conflicting


def compare_review_runs(baseline, candidate, expected):
    """Compare review decisions under identical inputs before adopting a new policy."""
    old, old_conflicts = reusable_reviews(baseline, expected)
    new, new_conflicts = reusable_reviews(candidate, expected)
    changes = []
    for name in sorted(old.keys() & new.keys()):
        before, after = (entries[name][1] for entries in (old, new))
        original = {key: before[key] for key in ('verdict', 'severity')}
        revised = {key: after[key] for key in ('verdict', 'severity')}
        if original != revised:
            changes.append({'comparison_id': name, 'baseline': original, 'candidate': revised})
    missing_baseline = sorted(expected.keys() - old.keys())
    missing_candidate = sorted(expected.keys() - new.keys())
    return {'comparison_total': len(expected), 'matched_inputs': len(old.keys() & new.keys()),
            'missing_baseline': missing_baseline, 'missing_candidate': missing_candidate,
            'conflicting_baseline': sorted(old_conflicts), 'conflicting_candidate': sorted(new_conflicts),
            'changed_decisions': changes,
            'equivalent': bool(expected) and not (missing_baseline or missing_candidate or changes)}
