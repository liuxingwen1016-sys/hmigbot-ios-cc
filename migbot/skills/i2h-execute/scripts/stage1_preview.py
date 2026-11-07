from lib.stage1_preview import *
from lib.stage1_preview import main
from _launcher import dispatch
if __name__ == '__main__': raise SystemExit(dispatch('stage1_preview', fallback=main))
