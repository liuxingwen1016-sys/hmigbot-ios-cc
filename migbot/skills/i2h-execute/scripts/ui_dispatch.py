#!/usr/bin/env python3
"""Prepare and archive iOS UI converter attempts."""
import argparse
import sys
from pathlib import Path

from lib.ios_ui_dispatch import complete, json_bytes, prepare, reuse_metadata


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    prepare_cli = commands.add_parser('prepare')
    complete_cli = commands.add_parser('complete')
    reuse_cli = commands.add_parser('reuse-metadata')
    for command in (prepare_cli, complete_cli, reuse_cli):
        command.add_argument('--project-root', required=True)
    prepare_cli.add_argument('--unit-id', required=True)
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
        elif args.command == 'complete':
            result = complete(root, args.dispatch_id)
        else:
            result = reuse_metadata(root, args.dispatch_id, args.packet)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f'ui_dispatch BLOCKED: {exc}', file=sys.stderr)
        return 2
    print(json_bytes(result).decode('utf-8'), end='')
    return 2 if result['status'] == 'BLOCKED' else 0


if __name__ == '__main__':
    raise SystemExit(main())
