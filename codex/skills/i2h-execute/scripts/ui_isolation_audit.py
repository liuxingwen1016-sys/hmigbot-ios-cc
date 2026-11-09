"""CLI launcher for the bundled i2h-execute command ``ui_isolation_audit``."""
from _launcher import dispatch

def main(argv=None):
    return dispatch("ui_isolation_audit", argv)

if __name__ == "__main__":
    raise SystemExit(main())
