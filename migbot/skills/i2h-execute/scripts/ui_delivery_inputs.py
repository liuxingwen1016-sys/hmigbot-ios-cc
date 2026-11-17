"""Freeze the approved iOS UI delivery inputs with the bundled Python tool."""
from __future__ import annotations

import sys

from lib.ui_delivery_inputs_ios import freeze


def main(argv=None):
    try:
        return freeze(argv)
    except (OSError, ValueError) as exc:
        print(f"ui_delivery_inputs BLOCKED: {exc}", file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
