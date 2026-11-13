#!/usr/bin/env python3
"""Compatibility name for the Python Stage 1 UI delivery gate."""
import sys


def main(argv=None):
    try:
        from ui_stage1_gate import main as stage1_main
    except (ImportError, OSError, SyntaxError) as exc:
        print(f"ui_delivery_gate tool_error: {exc}", file=sys.stderr)
        return 3
    return stage1_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
