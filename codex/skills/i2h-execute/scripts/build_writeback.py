from lib.build_writeback import *
from lib.build_writeback import main
from _launcher import dispatch
if __name__ == '__main__': raise SystemExit(dispatch('build_writeback', fallback=main))
