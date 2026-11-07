"""CLI launcher for the bundled i2h-execute command ``ui_delivery_scope``."""
from _launcher import dispatch

def main(argv=None):
    return dispatch("ui_delivery_scope", argv)

if __name__ == "__main__":
    raise SystemExit(main())
