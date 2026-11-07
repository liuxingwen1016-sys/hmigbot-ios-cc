from lib.validate_runtime_snapshots import *
from lib.validate_runtime_snapshots import main
from _launcher import dispatch
if __name__ == '__main__': raise SystemExit(dispatch('validate_runtime_snapshots', fallback=main))
