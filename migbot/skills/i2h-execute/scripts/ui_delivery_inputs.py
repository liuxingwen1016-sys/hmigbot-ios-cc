"""CLI launcher for the bundled i2h-execute command ``ui_delivery_inputs``."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from _launcher import dispatch


def _ios_inventory(argv):
    try:
        inventory_arg = argv[argv.index("--inventory") + 1]
        path = Path(inventory_arg)
        if not path.is_absolute():
            root = Path(argv[argv.index("--project-root") + 1])
            path = root / path
        data = json.loads(path.read_text(encoding="utf-8"))
        source_root = data.get("source_project_root")
        return isinstance(source_root, str) and any(Path(source_root).glob("**/*.swift"))
    except (ValueError, IndexError, OSError, json.JSONDecodeError):
        return False

def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if _ios_inventory(argv):
        from lib.ui_delivery_inputs_ios import freeze
        try:
            return freeze(argv)
        except (OSError, ValueError) as exc:
            print(f'ui_delivery_inputs BLOCKED: {exc}', file=sys.stderr)
            return 2
    return dispatch("ui_delivery_inputs", argv)

if __name__ == "__main__":
    raise SystemExit(main())
