#!/usr/bin/env python3
"""Prepare and archive iOS UI converter attempts."""
import argparse
import sys
from pathlib import Path

from lib.ios_ui_dispatch import check_required_inputs, complete, json_bytes, prepare, recovery_review, reuse_metadata


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    prepare_cli = commands.add_parser('prepare')
    check_cli = commands.add_parser('check-inputs', help='verify dispatch inputs without creating an attempt')
    complete_cli = commands.add_parser('complete')
    reuse_cli = commands.add_parser('reuse-metadata')
    review_cli = commands.add_parser('recovery-review')
    for command in (prepare_cli, check_cli, complete_cli, reuse_cli, review_cli):
        command.add_argument('--project-root', required=True)
    prepare_cli.add_argument('--unit-id', required=True)
    check_scope = check_cli.add_mutually_exclusive_group(required=True)
    check_scope.add_argument('--unit-id')
    check_scope.add_argument('--all-required', action='store_true',
                             help='check all approved required units and report a compact summary')
    check_cli.add_argument('--resume-pending', action='store_true',
                           help='report an equivalent pending preparation without creating an attempt')
    prepare_cli.add_argument('--attempt', type=int, required=True)
    prepare_cli.add_argument('--no-working-copies', action='store_true')
    for command in (complete_cli, reuse_cli):
        command.add_argument('--dispatch-id', required=True)
    reuse_cli.add_argument('--packet', required=True)
    args = parser.parse_args(argv)
    root = Path(args.project_root).expanduser().resolve()
    try:
        if args.command == 'prepare':
            result = prepare(root, args.unit_id, args.attempt, no_working_copies=args.no_working_copies)
        elif args.command == 'check-inputs':
            if args.all_required:
                result = check_required_inputs(root, resume_pending=args.resume_pending)
            else:
                result = prepare(root, args.unit_id, 1, check_only=True, resume_pending=args.resume_pending)
        elif args.command == 'complete':
            result = complete(root, args.dispatch_id)
        elif args.command == 'recovery-review':
            result = recovery_review(root)
        else:
            result = reuse_metadata(root, args.dispatch_id, args.packet)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f'ui_dispatch BLOCKED: {exc}', file=sys.stderr)
        return 2
    print(json_bytes(result).decode('utf-8'), end='')
    return 2 if result['status'] == 'BLOCKED' else 0


if __name__ == '__main__':
    raise SystemExit(main())
