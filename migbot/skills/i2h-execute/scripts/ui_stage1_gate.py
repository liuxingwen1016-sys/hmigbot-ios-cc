from lib.ui_stage1_gate import *
from lib.ui_stage1_gate import main
from lib.ios_stage1_scope import gate_from_inventory
import json
import sys
from pathlib import Path
from _launcher import dispatch


def _is_ios(argv):
    return (Path(argv[argv.index('--project-root') + 1]) / 'spec/baseline/ui-delivery-approved.json').is_file()


def _ios_main(argv):
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--project-root', required=True)
    parser.add_argument('--output-json', required=True)
    parser.add_argument('--wiring-dir')
    parser.add_argument('--wiring-contract')
    parser.add_argument('--inputs-index')
    args = parser.parse_args(argv)
    result = gate_from_inventory(Path(args.project_root), args.wiring_contract or args.wiring_dir, args.inputs_index)
    Path(args.output_json).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if result.get('status') == 'PASS' else 2


if __name__ == '__main__':
    argv = sys.argv[1:]
    if '--project-root' in argv and _is_ios(argv):
        raise SystemExit(_ios_main(argv))
    raise SystemExit(dispatch('ui_stage1_gate', fallback=main))
