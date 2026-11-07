"""CLI launcher for the bundled i2h-execute command ``ui_dispatch``."""
from _launcher import dispatch

def main(argv=None):
    return dispatch("ui_dispatch", argv)

if __name__ == "__main__":
    raise SystemExit(main())
