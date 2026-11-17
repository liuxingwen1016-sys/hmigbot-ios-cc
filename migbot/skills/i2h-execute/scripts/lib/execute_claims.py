"""Validate implementation evidence against the frozen Execute plan."""
from __future__ import annotations

import json
from pathlib import Path


def implementation_file(root: Path, value) -> Path | None:
    if not isinstance(value, str) or not value.strip() or '\x00' in value:
        return None
    relative = Path(value)
    if relative.is_absolute() or '..' in relative.parts:
        return None
    try:
        candidate = (root / relative).resolve()
    except (OSError, RuntimeError):
        return None
    if not candidate.is_relative_to(root) or not candidate.is_file():
        return None
    return candidate


def claim_problem(root, packets, requirements, claim):
    attempt = claim.get('attempt', 1)
    if type(attempt) is not int or attempt < 1:
        return 'INVALID_ATTEMPT', 'attempt must be a positive integer'
    packet_id = claim.get('packet_id')
    if not isinstance(packet_id, str) or packet_id not in packets:
        return 'UNKNOWN_PACKET', 'packet does not exist in plan-coverage'
    packet = packets[packet_id]
    requirement = claim.get('requirement_id')
    if (not isinstance(requirement, str) or requirement not in packet.get('requirement_ids', [])
            or requirement not in requirements):
        return 'WRONG_PACKET_REQUIREMENT', 'requirement is not assigned to this packet'
    planned = packet.get('requirement_digests', {}).get(requirement)
    if not isinstance(planned, str) or not planned.strip() or planned != requirements[requirement] or planned != claim.get('requirement_digest'):
        return 'STALE_REQUIREMENT_DIGEST', 'claim, plan and requirement index must agree'
    files = claim.get('files')
    if not isinstance(files, list) or not files:
        return 'MISSING_IMPLEMENTATION_FILES', 'claim has no implementation files'
    for value in files:
        if implementation_file(root, value) is None:
            return 'INVALID_IMPLEMENTATION_FILE', f'implementation file is missing or outside project: {value!r}'
    anchors = claim.get('code_anchors', [])
    if not isinstance(anchors, list):
        return 'INVALID_CODE_ANCHOR', 'code_anchors must be an array'
    for anchor in anchors:
        if (not isinstance(anchor, dict) or anchor.get('file') not in files
                or type(anchor.get('line')) is not int or anchor['line'] < 1):
            return 'INVALID_CODE_ANCHOR', f'anchor must identify a declared file and positive line: {anchor!r}'
        path = implementation_file(root, anchor['file'])
        with path.open(encoding='utf-8', errors='replace') as stream:
            if not any(number == anchor['line'] for number, _ in enumerate(stream, 1)):
                return 'INVALID_CODE_ANCHOR', f'anchor line does not exist: {anchor!r}'
    return None


def load_plan(root):
    index = root / 'spec/.i2h'
    coverage = json.loads((index / 'plan-coverage.json').read_text(encoding='utf-8'))
    requirements = json.loads((index / 'requirements-index.json').read_text(encoding='utf-8'))
    return ({row['packet_id']: row for row in coverage['packets']},
            {row['requirement_id']: row.get('digest') for row in requirements['requirements']})
