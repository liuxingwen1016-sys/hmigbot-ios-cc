"""CLI launcher for the bundled i2h-execute command ``ui_delivery_scope``."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from _launcher import dispatch

def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if '--project-root' in argv:
        root = Path(argv[argv.index('--project-root') + 1])
        if (root / 'spec/baseline/ui-delivery-approved.json').is_file():
            import argparse
            from lib.ios_stage1_scope import build_scope_from_inventory
            parser = argparse.ArgumentParser()
            parser.add_argument('--project-root', required=True)
            parser.add_argument('--out', required=True)
            parser.add_argument('--wiring-dir')
            parser.add_argument('--inputs-index')
            args = parser.parse_args(argv)
            result = build_scope_from_inventory(root, args.wiring_dir)
            Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
            return 0 if result.get('status') == 'READY' else 2
    return dispatch("ui_delivery_scope", argv)

if __name__ == "__main__":
    raise SystemExit(main())
