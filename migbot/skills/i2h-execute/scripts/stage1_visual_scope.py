from lib.stage1_visual_scope import *
from lib.stage1_visual_scope import build_scope
from _launcher import dispatch
if __name__ == '__main__': raise SystemExit(dispatch('stage1_visual_scope', fallback=lambda argv: 0))
