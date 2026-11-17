from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

from .execute_claims import claim_problem, implementation_file, load_plan


def _load(root, path):
    return json.loads((root / path).read_text(encoding='utf-8'))


def _unique_object(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError(f'duplicate intent key: {key}')
        result[key] = value
    return result


def build(intent: dict, root: Path | str):
    root = Path(root).resolve()
    unconverged = intent.get('fv1_unconverged')
    orphans = set()
    if unconverged is not None:
        if intent.get('mode') != 'final' or not unconverged.get('decision'):
            raise ValueError('unconverged FV-1 requires final mode and a decision')
        loop = unconverged.get('loop_result')
        loop_path = implementation_file(root, loop)
        if loop_path is None:
            raise ValueError('unconverged FV-1 requires an existing loop result')
        orphan_report = _load(root, loop_path).get('detector_json_paths', {}).get('orphans')
        orphan_path = implementation_file(root, orphan_report)
        if orphan_path is None:
            raise ValueError('unconverged FV-1 requires an existing orphan report')
        orphans = {(root / row['file']).resolve() for row in _load(root, orphan_path)['orphans']}

    selected = intent.get('packets', {})
    if not isinstance(selected, dict):
        raise ValueError('packets must be an object indexed by packet ID')
    planned, requirements = load_plan(root) if selected else ({}, {})
    declared_features = intent.get('feature_index', {}).get('implemented', [])
    if not isinstance(declared_features, list) or any(not isinstance(f, str) for f in declared_features):
        raise ValueError('feature_index.implemented must be an array')
    claims, warnings, dropped = [], [], {}
    for packet_id, entry in selected.items():
        packet = planned.get(packet_id)
        if packet is None or not isinstance(entry, dict):
            raise ValueError(f'{packet_id}: unknown packet or invalid intent')
        feature = packet.get('feature_id') or packet_id.rsplit('-', 1)[-1]
        ids = entry.get('requirement_ids')
        whole = entry.get('whole_packet') is True or (ids is None and feature in declared_features)
        if ids is not None and entry.get('whole_packet') is True:
            raise ValueError(f'{packet_id}: choose requirement_ids or whole_packet')
        if whole:
            ids = packet['requirement_ids']
        if (not isinstance(ids, list) or not ids or not all(isinstance(ac, str) and ac for ac in ids)
                or len(ids) != len(set(ids))):
            raise ValueError(f'{packet_id}: specify unique requirement_ids or explicit whole-packet completion')
        files = entry.get('files')
        if not isinstance(files, list) or not files or not all(isinstance(file, str) for file in files):
            raise ValueError(f'{packet_id}: implementation files required')
        attempt = entry.get('attempt', 1)
        if type(attempt) is not int or attempt < 1:
            raise ValueError(f'{packet_id}: attempt must be a positive integer')
        packet_claims = []
        for ac in ids:
            claim = {'requirement_id': ac, 'packet_id': packet_id, 'files': files,
                     'requirement_digest': packet.get('requirement_digests', {}).get(ac), 'attempt': attempt}
            for field in ('code_anchors', 'symbols', 'verification_evidence'):
                if field in entry:
                    claim[field] = entry[field]
            problem = claim_problem(root, planned, requirements, claim)
            if problem:
                raise ValueError(f'{packet_id}/{ac}: {problem[0]}: {problem[1]}')
            packet_claims.append(claim)
        unresolved = [file for file in files if (root / file).resolve() in orphans]
        if unresolved:
            dropped[packet_id] = unresolved
            warnings.append(f'{packet_id} has unresolved orphan files; claims withheld')
            continue
        claims.extend(packet_claims)
    blocked_features = {planned[key].get('feature_id') or key.rsplit('-', 1)[-1] for key in dropped}
    implemented = sorted(set(declared_features) - blocked_features)
    manifest = {'impl_claims': {'claims': claims, 'executed_packets': sorted({c['packet_id'] for c in claims})},
                'feature_index': {'implemented': implemented},
                'notes': {'fv1_unconverged': {'dropped': dropped}} if unconverged else {}}
    selected_features = {planned[key].get('feature_id') or key.rsplit('-', 1)[-1] for key in selected}
    if set(declared_features) - selected_features:
        raise ValueError('feature_index.implemented must name features selected in packets')
    for key in ('mode', 'id', 'registry', 'ui_manifest'):
        if key in intent:
            manifest[key] = intent[key]
    if 'brief' in intent:
        brief = dict(intent['brief'])
        if 'content_file' in brief:
            path = implementation_file(root, brief.pop('content_file'))
            if path is None or 'content' in brief:
                raise ValueError('brief requires exactly one inline content or readable project draft')
            brief['content'] = path.read_text(encoding='utf-8')
        if (intent.get('mode') == 'group' and isinstance(brief.get('content'), str)):
            sections = set(re.findall(r'^## Slice \d+ \((F-?\d+)\)\s*$', brief['content'], re.MULTILINE))
            if selected_features - {value.replace('-', '') for value in sections}:
                raise ValueError('group brief is missing selected feature sections')
        manifest['brief'] = brief
    return manifest, warnings


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('intent')
    parser.add_argument('--project-root', required=True)
    parser.add_argument('--output', '--out', dest='output')
    parser.add_argument('--claims-only', action='store_true',
                        help='Emit a partial implementation manifest for apply_writeback --merge-evidence')
    args = parser.parse_args(argv)
    try:
        intent = json.loads(Path(args.intent).read_text(encoding='utf-8'), object_pairs_hook=_unique_object)
        manifest, warnings = build(intent, args.project_root)
        if args.claims_only:
            if manifest['feature_index']['implemented'] or manifest['notes'] or (
                    {'brief', 'registry', 'ui_manifest'} & manifest.keys()
            ):
                raise ValueError('--claims-only requires a partial intent without feature closeout or FV notes')
            manifest = {'impl_claims': manifest['impl_claims']}
        payload = json.dumps(manifest, ensure_ascii=False, indent=2)
        if args.output:
            Path(args.output).write_text(payload, encoding='utf-8')
        else:
            print(payload)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RuntimeError) as error:
        print(f'build_writeback: {error}', file=sys.stderr)
        return 2
    for warning in warnings:
        print(f'warning: {warning}', file=sys.stderr)
    return 0
