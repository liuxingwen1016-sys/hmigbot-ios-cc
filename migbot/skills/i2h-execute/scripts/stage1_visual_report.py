"""CLI launcher for the bundled i2h-execute command ``stage1_visual_report``."""
from _launcher import dispatch

def main(argv=None):
    return dispatch("stage1_visual_report", argv)

if __name__ == "__main__":
    raise SystemExit(main())
