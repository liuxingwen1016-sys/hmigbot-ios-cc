"""CLI launcher for the bundled i2h-execute command ``stage1_acceptance``."""
from _launcher import dispatch

def main(argv=None):
    return dispatch("stage1_acceptance", argv)

if __name__ == "__main__":
    raise SystemExit(main())
