from lib.stage1_wiring_smoke import *
from lib.stage1_wiring_smoke import run
from _launcher import dispatch
if __name__ == '__main__': raise SystemExit(dispatch('stage1_wiring_smoke', fallback=lambda argv: 0))
