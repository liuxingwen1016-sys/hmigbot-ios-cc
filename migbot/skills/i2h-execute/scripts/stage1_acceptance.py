#!/usr/bin/env python3
"""Archive iOS converter and assembled UI delivery checks."""
import argparse
import sys
from pathlib import Path

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root', required=True)
    parser.add_argument('--kind', required=True, choices=('g0', 'g1', 'compile', 'visual', 'next', 'smoke', 'summary'))
    parser.add_argument('--scope')
    parser.add_argument('--report')
    parser.add_argument('--build-receipt', help='current build receipt under spec')
    parser.add_argument('--wiring-contract')
    parser.add_argument('--out', '--output-json', dest='out')
    parser.add_argument('--report-only', action='store_true', help='Assess visual evidence without publishing or consuming repair rounds')
    args = parser.parse_args(argv)
    if args.report_only and args.kind != 'visual':
        parser.error('--report-only requires --kind visual')
    try:
        from lib.ios_stage1_acceptance import archive_g1
        from lib.ios_stage1_progress import record_compile, record_smoke
        from lib.ios_stage1_summary import DEFAULT_SCOPE, next_step, summarize
        from lib.ios_stage1_visual_gate import archive_visual, assess_visual
        from lib.ios_ui_delivery_gate import _project_file
        from lib.ios_ui_dispatch import aggregate_g0, atomic_write, dispatch_root, json_bytes
    except ImportError as exc:
        print(f'stage1_acceptance tool_error: {exc}', file=sys.stderr)
        return 3
    try:
        root = Path(args.project_root).expanduser().resolve()
        path = _project_file(root, args.out) if args.out else None
        if path is not None and path.is_relative_to(dispatch_root(root)):
            raise ValueError('--out must be outside the immutable dispatch archive')
        if args.kind == 'g0':
            result = aggregate_g0(root)
        elif args.kind == 'g1':
            result = archive_g1(root, args.wiring_contract)
        elif args.kind == 'visual':
            scope = _project_file(root, args.scope)
            report = _project_file(root, args.report)
            if path in {scope, report}:
                raise ValueError('--out must not overwrite an input receipt or scope')
            if args.report_only:
                result = {**assess_visual(root, scope.read_bytes(), report.read_bytes()), 'report_only': True}
            else:
                result = archive_visual(root, scope, report)
        else:
            scope = _project_file(root, args.scope or DEFAULT_SCOPE)
            report = _project_file(root, args.report) if args.report else None
            build = _project_file(root, args.build_receipt) if args.build_receipt else None
            wiring = _project_file(root, args.wiring_contract) if args.wiring_contract else None
            if path is not None and path in {scope, report, build, wiring}:
                raise ValueError('--out must not overwrite an input receipt or scope')
            if args.kind == 'compile':
                result = record_compile(root, scope, report, build, args.wiring_contract)
            elif args.kind == 'smoke':
                if report is None:
                    raise ValueError('smoke requires --report')
                result = record_smoke(root, scope, report)
            else:
                inspect = next_step if args.kind == 'next' else summarize
                result = inspect(root, scope, report, args.wiring_contract, build)
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write(path, json_bytes(result))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f'stage1_acceptance BLOCKED: {exc}', file=sys.stderr)
        return 2
    print(json_bytes(result).decode('utf-8'), end='')
    return 0 if result['status'] == 'PASS' else 2


if __name__ == '__main__':
    raise SystemExit(main())
