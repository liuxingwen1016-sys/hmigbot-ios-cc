from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

from .execute_claims import claim_problem, load_plan

SECTION = 'execute'


def scope_deferrals(root):
    ledger = root / 'spec/decision-ledger.md'
    if not ledger.is_file():
        return {}
    sections = re.split(r'^#{2,6}\s+', ledger.read_text(encoding='utf-8'), flags=re.MULTILINE)
    deferred = {}
    for section in sections[1:]:
        heading, _, body = section.partition('\n')
        decision = re.match(r'(D-\d+)\b', heading)
        if not decision:
            continue
        for value in re.findall(r'^- \*\*延期 AC\*\*\s*[:：]\s*(.+)$', body, flags=re.MULTILINE):
            for ac in value.split(','):
                ac = ac.strip().strip('`')
                if not re.fullmatch(r'F\d+-AC\d+', ac):
                    raise ValueError(f'{decision[1]}: invalid deferred AC {ac!r}')
                if ac in deferred and deferred[ac] != decision[1]:
                    raise ValueError(f'{ac}: conflicting scope deferrals {deferred[ac]} and {decision[1]}')
                deferred[ac] = decision[1]
    return deferred


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('project', nargs='?')
    parser.add_argument('--project-root')
    parser.add_argument('--final', action='store_true')
    parser.add_argument('--report-only', action='store_true')
    args = parser.parse_args(argv)
    root = Path(args.project_root or args.project or '.').resolve()
    index = root / 'spec/.i2h'
    ledger_path = index / 'impl-claims.json'
    try:
        packets, requirements = load_plan(root)
        deferred = scope_deferrals(root)
        unknown = deferred.keys() - requirements.keys()
        if unknown:
            raise ValueError(f'decision-ledger contains unknown deferred ACs: {", ".join(sorted(unknown))}')
        ledger = json.loads(ledger_path.read_text(encoding='utf-8')) if ledger_path.exists() else {}
        claimed = set()
        findings = []
        for claim in ledger.get('claims', []):
            packet, ac = claim.get('packet_id'), claim.get('requirement_id')
            problem = claim_problem(root, packets, requirements, claim)
            if problem:
                findings.append({'rule': f'EXECUTE.{problem[0]}', 'subject': ac, 'packet_id': packet,
                                 'detail': problem[1], 'attempt': claim.get('attempt', 1)})
            else:
                claimed.add((packet, ac))
        executed = set(ledger.get('executed_packets', []))
        for packet in sorted(executed - packets.keys()):
            findings.append({'rule': 'EXECUTE.UNKNOWN_PACKET', 'subject': packet, 'packet_id': packet})
        for packet in sorted(packets if args.final else executed & packets.keys()):
            for ac in packets[packet].get('requirement_ids', []):
                if (packet, ac) not in claimed:
                    finding = {'rule': 'EXECUTE.REQUIREMENT_UNCLAIMED', 'subject': ac, 'packet_id': packet}
                    if ac in deferred:
                        finding.update(rule='EXECUTE.REQUIREMENT_DEFERRED', decision_id=deferred[ac])
                    findings.append(finding)
        output = index / 'open-findings.json'
        merged = json.loads(output.read_text(encoding='utf-8')) if output.exists() and not args.report_only else {}
        merged.setdefault('sections', {}).setdefault(SECTION, {})['findings'] = findings
        payload = json.dumps(merged, ensure_ascii=False, indent=2)
        if args.report_only:
            print(payload)
        else:
            temporary = output.with_suffix('.json.tmp')
            temporary.write_text(payload + '\n', encoding='utf-8')
            temporary.replace(output)
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
        print(f'lint_execute_coverage: {error}', file=sys.stderr)
        return 2
    return 2 if findings else 0
