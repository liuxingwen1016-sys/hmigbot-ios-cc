#!/usr/bin/env python3
"""Real native derive CLI for source-proven inventory resolution.

Phase B: Generates execution inventory draft with provenance from explicit resolution requests.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / 'lib'))

from ios_inventory_resolution import (
    apply_proof_to_inventory,
    load_proof,
    sha256_bytes,
    sha256_file,
    validate_approved_execution_inventory,
)


def derive(argv: list[str] | None = None) -> int:
    """Derive execution inventory draft from baseline + explicit resolution proof."""
    parser = argparse.ArgumentParser(description='Derive execution inventory from baseline + proof')
    parser.add_argument('derive', nargs='?', help='Subcommand (required)')
    parser.add_argument('--project-root', required=True, help='Project root directory')
    parser.add_argument('--baseline', required=True, help='Path to approved baseline inventory')
    parser.add_argument('--proof', required=True, help='Path to explicit resolution proof requests')
    parser.add_argument('--out', required=True, help='Output path for draft candidate')
    parser.add_argument('--validate-approved', action='store_true', help='Validate approved inventory by replay')
    args = parser.parse_args(argv)

    # Check for derive subcommand
    if args.derive != 'derive':
        print(json.dumps({'status': 'ERROR', 'error': 'must use "derive" subcommand'}))
        return 2

    root = Path(args.project_root).expanduser().resolve()

    baseline_path = Path(args.baseline)
    if not baseline_path.is_absolute():
        baseline_path = root / baseline_path

    confined, conf_err = confine_path(baseline_path, root)
    if not confined:
        print(json.dumps({'status': 'ERROR', 'error': f'baseline: {conf_err}'}))
        return 2

    if not baseline_path.is_file():
        print(json.dumps({'status': 'ERROR', 'error': f'baseline not found: {baseline_path}'}))
        return 2

    proof_path = Path(args.proof)
    if not proof_path.is_absolute():
        proof_path = root / proof_path

    confined, conf_err = confine_path(proof_path, root)
    if not confined:
        print(json.dumps({'status': 'ERROR', 'error': f'proof: {conf_err}'}))
        return 2

    if not proof_path.is_file():
        print(json.dumps({'status': 'ERROR', 'error': f'proof not found: {proof_path}'}))
        return 2

    output_path = Path(args.out)
    if not output_path.is_absolute():
        output_path = root / output_path

    confined, conf_err = confine_path(output_path, root)
    if not confined:
        print(json.dumps({'status': 'ERROR', 'error': f'out: {conf_err}'}))
        return 2

    # Handle validate-approved mode
    if args.validate_approved:
        if not output_path.is_file():
            print(json.dumps({'status': 'ERROR', 'error': f'approved inventory not found: {output_path}'}))
            return 2

        valid, errors = validate_approved_execution_inventory(output_path, baseline_path, proof_path)

        if not valid:
            result = {
                'status': 'FAIL',
                'validation': 'replay_validation',
                'errors': errors,
            }
            print(json.dumps(result, ensure_ascii=False))
            return 1

        result = {
            'status': 'PASS',
            'validation': 'replay_validation',
            'approved_inventory': str(output_path.relative_to(root)) if output_path.is_relative_to(root) else str(output_path),
        }
        print(json.dumps(result, ensure_ascii=False))
        return 0

    # Regular derive mode
    baseline_data = json.loads(baseline_path.read_text(encoding='utf-8'))
    baseline_sha = sha256_file(baseline_path)

    if baseline_data.get('schema_version') != 2:
        print(json.dumps({'status': 'ERROR', 'error': 'baseline must be schema_version 2'}))
        return 2

    if baseline_data.get('status') != 'approved':
        print(json.dumps({'status': 'ERROR', 'error': 'baseline must be status approved'}))
        return 2

    proof, error = load_proof(proof_path)
    if error:
        print(json.dumps({'status': 'ERROR', 'error': f'proof validation failed: {error}'}))
        return 2

    proof_sha = sha256_file(proof_path)

    source_root = Path(baseline_data.get('source_project_root', root / 'ios')).resolve()

    candidate, errors = apply_proof_to_inventory(baseline_data, proof, baseline_sha, source_root, proof_sha)

    if errors:
        result = {
            'status': 'ERROR',
            'error': 'proof application failed',
            'details': errors,
        }
        print(json.dumps(result, ensure_ascii=False))
        return 2

    # Add baseline ancestor and mark as draft
    candidate['baseline_ancestor_sha256'] = baseline_sha
    candidate['status'] = 'draft'
    candidate['validation'] = {'errors': []}

    # Update provenance with file paths and SHAs
    if 'provenance' not in candidate:
        candidate['provenance'] = {}

    candidate['provenance']['baseline_path'] = str(baseline_path.relative_to(root)) if baseline_path.is_relative_to(root) else str(baseline_path)
    candidate['provenance']['baseline_sha256'] = baseline_sha
    candidate['provenance']['proof_path'] = str(proof_path.relative_to(root)) if proof_path.is_relative_to(root) else str(proof_path)
    candidate['provenance']['proof_sha256'] = proof_sha

    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_bytes = (json.dumps(candidate, ensure_ascii=False, indent=2, sort_keys=True) + '\n').encode('utf-8')
    output_path.write_bytes(output_bytes)

    output_sha = sha256_bytes(output_bytes)

    result = {
        'status': 'PASS',
        'output': str(output_path.relative_to(root)) if output_path.is_relative_to(root) else str(output_path),
        'output_sha256': output_sha,
        'baseline_sha256': baseline_sha,
        'requests_applied': len(proof.get('requests', [])),
    }

    print(json.dumps(result, ensure_ascii=False))
    return 0


def confine_path(path: Path, root: Path) -> tuple[bool, str | None]:
    """Validate path is confined under root."""
    try:
        resolved = path.resolve()
        resolved_root = root.resolve()
        if not resolved.is_relative_to(resolved_root):
            return False, f"path escapes root"
        return True, None
    except Exception as e:
        return False, f"cannot resolve: {e}"


if __name__ == '__main__':
    sys.exit(derive())
