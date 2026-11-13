from lib.stage1_visual_scope import *
from lib.stage1_visual_scope import build_scope, main
from lib.ios_stage1_scope import build_scope_from_inventory
import json
import sys
from pathlib import Path
from _launcher import dispatch


def _is_ios(argv):
    return (Path(argv[argv.index('--project-root') + 1]) / 'spec/baseline/ui-delivery-approved.json').is_file()


if __name__ == '__main__':
    argv = sys.argv[1:]
    if '--help' in argv or ('--project-root' in argv and _is_ios(argv)):
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument('--project-root', required=True)
        parser.add_argument('--out', required=True)
        parser.add_argument('--wiring-dir')
        parser.add_argument('--inputs-index')
        args = parser.parse_args(argv)
        result = build_scope_from_inventory(Path(args.project_root), args.wiring_dir)
        Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        raise SystemExit(0 if result.get('status') == 'READY' else 2)
    raise SystemExit(dispatch('stage1_visual_scope', fallback=main))
