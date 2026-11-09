"""CLI launcher for the bundled i2h-execute command ``ui_relationships``."""
from _launcher import dispatch

def main(argv=None):
    return dispatch("ui_relationships", argv)

if __name__ == "__main__":
    raise SystemExit(main())
