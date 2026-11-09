from lib.lint_execute_coverage import *
from lib.lint_execute_coverage import main
from _launcher import dispatch
if __name__ == '__main__': raise SystemExit(dispatch('lint_execute_coverage', fallback=main))
