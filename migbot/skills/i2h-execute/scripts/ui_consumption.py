"""CLI launcher for the bundled i2h-execute command ``ui_consumption``."""
from _launcher import dispatch

def main(argv=None):
    return dispatch("ui_consumption", argv)

if __name__ == "__main__":
    raise SystemExit(main())
