#!/bin/bash
# run_loop.sh — Drive ONE structural_loop iteration with auto-derived paths.
#
# Per a2h-execute design: the LLM main flow must dispatch repair workers itself
# (Python can't invoke 模型 agents). So this script runs ONE iteration and
# exits, letting the LLM branch on exit code.
#
# Usage:
#   bash scripts/run_loop.sh --mode slice    --target 3 --round 1 --project-root .
#   bash scripts/run_loop.sh --mode stage    --target 1 --round 1 --project-root . \
#       --diff-base abc123 --handoffs path/to/h1.md path/to/h2.md ...
#   bash scripts/run_loop.sh --mode pipeline --target final --round 1 --project-root .
#
# Auto-derived paths (under <project-root>/spec/execution/autofix-log/round-<R>/):
#   - state file: loop-state-<mode>-<target>.json
#   - latest result: loop-result-latest-<mode>-<target>.json (overwritten per iter)
#   - per-iter audit / wiring detail JSONs (named by structural_loop.py internally)
#
# Exit codes (mirror structural_loop.py iterate):
#   0 — CONVERGED: loop done, dispatch finalize and write handoff
#   1 — CONTINUE: LLM must dispatch repair worker per loop-result-latest.dispatch_prompt
#                 then re-invoke this script
#   2 — ESCALATED (STALLED / REGRESSED / EXHAUSTED): write handoff escalation
#   3 — argument / IO error

set -e

# ─── Windows / Git-Bash (MSYS/MINGW) path fix ────────────────────────────────
# Under MINGW/Git-Bash, `pwd` yields an MSYS path like `/d/Coding/...`. A native
# Windows python.exe CANNOT open it — it mis-resolves `/d/...` to `D:\d\...` and
# fails ("can't open file 'D:\\d\\...\\structural_loop.py'"). Convert any ABSOLUTE
# MSYS path that is handed to python.exe into a native path via `cygpath -m`
# (mixed mode = `D:/...`, forward slashes → safe to pass through the shell).
# Relative paths (`.`, `./x`) are left untouched so they keep resolving against the
# unchanged cwd. No-op on Linux/macOS (no `cygpath`; paths are already native).
winpath() { if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s' "$1"; fi; }
maybe_native() { case "$1" in /*) winpath "$1" ;; *) printf '%s' "$1" ;; esac; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STRUCTURAL_LOOP="$(maybe_native "$SCRIPT_DIR/structural_loop.py")"

# ─── Python 解释器解析 ───────────────────────────────────────────────────────
# 本脚本此前硬依赖 PATH 上的 `python3`。但把 skill 编译成 Nuitka standalone 的
# 初衷正是摆脱用户环境的 Python 依赖 —— 没装 python3 的机器上二进制齐备却跑不起来。
# 故优先探测同目录下的编译产物 `_entry.bin`（可直接跑子命令），再回退系统解释器。
ENTRY_BIN=""
# Windows（Git Bash / MSYS）上编译产物是 _entry.exe；旧写法只认 .bin，于是退回 python structural_loop.py
# ——那也是 launcher shim，绕一圈仍转发到 _entry.exe，但白白依赖了 PATH 上的 python。
for _cand in "$SCRIPT_DIR/bin"/*/_entry.dist/_entry.bin "$SCRIPT_DIR/bin"/*/_entry.dist/_entry.exe \
             "$SCRIPT_DIR/_entry.dist/_entry.bin" "$SCRIPT_DIR/_entry.dist/_entry.exe"; do
    [[ -x "$_cand" ]] && { ENTRY_BIN="$_cand"; break; }
done
PY=""
for _p in python3 python; do
    command -v "$_p" >/dev/null 2>&1 && { PY="$_p"; break; }
done
# 直调 _entry 绕过了 exec-shim，shim 负责的 ARKTS_SKILL_DIR 就没人 export——冻结态里凡从它
# 解析的跨 skill 路径（六闸 / icon_autofix / immersive .sh）全部落空，静默 skip 或 gate-not-run
# （AIPPT FV-1 T1）。本脚本就在真实 scripts/ 里，无条件以它为准（父进程继承来的别的 skill 值也纠正）。
export ARKTS_SKILL_DIR="$SCRIPT_DIR"

# 跑 structural_loop：有二进制走子命令自调，否则用系统解释器跑 .py
run_structural_loop() {
    if [[ -n "$ENTRY_BIN" ]]; then
        "$ENTRY_BIN" structural_loop "$@"
    else
        "$PY" "$STRUCTURAL_LOOP" "$@"
    fi
}

MODE=""
TARGET=""
ROUND=""
PROJECT_ROOT=""
DIFF_BASE=""
SLICES=""
HANDOFFS=()
ANDROID_RES=()
SCOPE_FILES=()
DENSITY=""
MAX_ITER=""

# ─── Parse args ──────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --mode) MODE="$2"; shift 2 ;;
        --target) TARGET="$2"; shift 2 ;;
        --round) ROUND="$2"; shift 2 ;;
        --project-root) PROJECT_ROOT="$2"; shift 2 ;;
        --diff-base) DIFF_BASE="$2"; shift 2 ;;
        --slices) SLICES="$2"; shift 2 ;;
        --handoffs)
            shift
            while [[ $# -gt 0 && "$1" != --* ]]; do
                HANDOFFS+=("$1")
                shift
            done
            ;;
        --android-res)
            shift
            while [[ $# -gt 0 && "$1" != --* ]]; do
                ANDROID_RES+=("$1")
                shift
            done
            ;;
        --scope-files)
            shift
            while [[ $# -gt 0 && "$1" != --* ]]; do
                SCOPE_FILES+=("$1")
                shift
            done
            ;;
        --density) DENSITY="$2"; shift 2 ;;
        --max-iter) MAX_ITER="$2"; shift 2 ;;
        -h|--help)
            sed -n '2,30p' "$0"
            exit 0
            ;;
        *)
            echo "error: unknown arg $1" >&2
            exit 3
            ;;
    esac
done

# ─── Validate ────────────────────────────────────────────────────────────────
if [[ -z "$MODE" || -z "$TARGET" || -z "$ROUND" || -z "$PROJECT_ROOT" ]]; then
    echo "error: --mode, --target, --round, --project-root all required" >&2
    exit 3
fi
if [[ "$MODE" != "stage" && "$MODE" != "slice" && "$MODE" != "group" && "$MODE" != "pipeline" ]]; then
    echo "error: --mode must be 'stage' / 'slice' / 'group' / 'pipeline', got '$MODE'" >&2
    exit 3
fi
if [[ "$MODE" == "stage" && -z "$DIFF_BASE" ]]; then
    echo "error: --diff-base required for --mode=stage" >&2
    exit 3
fi
if [[ "$MODE" == "group" && -z "$SLICES" ]]; then
    echo "error: --slices N,M,... required for --mode=group" >&2
    exit 3
fi
if [[ ! -d "$PROJECT_ROOT" ]]; then
    echo "error: project root does not exist: $PROJECT_ROOT" >&2
    exit 3
fi

# ─── Derive paths ────────────────────────────────────────────────────────────
LOG_DIR="$PROJECT_ROOT/spec/execution/autofix-log/round-$ROUND"
mkdir -p "$LOG_DIR"
STATE_FILE="$LOG_DIR/loop-state-$MODE-$TARGET.json"
RESULT_FILE="$LOG_DIR/loop-result-latest-$MODE-$TARGET.json"

# 开始本次扫描前作废 latest。否则解释器起不来 / 本次没写 JSON 时，下游会
# 把上一轮 CONVERGED 当作新结果。保留 .prev 仅作历史证据，不再读取它。
if [[ -e "$RESULT_FILE" || -L "$RESULT_FILE" ]]; then
    if [[ -d "$RESULT_FILE.prev" ]] || ! mv -f -- "$RESULT_FILE" "$RESULT_FILE.prev"; then
        echo "[run_loop.sh] INCOMPLETE: cannot invalidate previous result; result_json is not valid for this run: $RESULT_FILE" >&2
        exit 3
    fi
fi
if [[ -z "$ENTRY_BIN" && -z "$PY" ]]; then
    echo "[run_loop.sh] INCOMPLETE: neither a compiled _entry.bin nor python3/python was found" >&2
    exit 3
fi

# ─── Build structural_loop iterate args ──────────────────────────────────────
LOOP_ARGS=(
    iterate
    --project-root "$(maybe_native "$PROJECT_ROOT")"
    --mode "$MODE"
    --target "$TARGET"
    --state-file "$(maybe_native "$STATE_FILE")"
    --output-json "$(maybe_native "$RESULT_FILE")"
)
if [[ -n "$DIFF_BASE" ]]; then
    LOOP_ARGS+=(--diff-base "$DIFF_BASE")   # git SHA, not a path → never converted
fi
if [[ -n "$SLICES" ]]; then
    LOOP_ARGS+=(--slices "$SLICES")         # mode=group: comma-separated slice numbers
fi
if [[ ${#HANDOFFS[@]} -gt 0 ]]; then
    LOOP_ARGS+=(--handoffs)
    for _h in "${HANDOFFS[@]}"; do LOOP_ARGS+=("$(maybe_native "$_h")"); done
fi
if [[ ${#SCOPE_FILES[@]} -gt 0 ]]; then
    LOOP_ARGS+=(--scope-files "${SCOPE_FILES[@]}")   # mode=slice/group: 各 slice 自建文件（相对 project root，不转 native）
fi
if [[ ${#ANDROID_RES[@]} -gt 0 ]]; then
    LOOP_ARGS+=(--android-res)
    for _r in "${ANDROID_RES[@]}"; do LOOP_ARGS+=("$(maybe_native "$_r")"); done
fi
if [[ -n "$DENSITY" ]]; then
    LOOP_ARGS+=(--density "$DENSITY")
fi
if [[ -n "$MAX_ITER" ]]; then
    LOOP_ARGS+=(--max-iter "$MAX_ITER")     # risk-conditional iteration cap (item6); structural_loop defaults to 8 when omitted
fi

# ─── Invoke ──────────────────────────────────────────────────────────────────
set +e
run_structural_loop "${LOOP_ARGS[@]}"
LOOP_EXIT=$?
set -e

# 只有协议内退出码和本轮新产物可用于分支；异常退出即便先写了 PASS 也不能采信。
case "$LOOP_EXIT" in
    0|1|2) ;;
    *)
        if [[ -e "$RESULT_FILE" || -L "$RESULT_FILE" ]]; then
            mv -f -- "$RESULT_FILE" "$RESULT_FILE.failed" || true
        fi
        echo "[run_loop.sh] INCOMPLETE: structural_loop exited $LOOP_EXIT; no valid result for this run" >&2
        exit 3
        ;;
esac
if [[ ! -f "$RESULT_FILE" ]]; then
    echo "[run_loop.sh] INCOMPLETE: structural_loop produced no result for this run" >&2
    exit 3
fi

# ─── Echo verdict line on stderr for LLM visibility ──────────────────────────
if [[ -f "$RESULT_FILE" ]]; then
    RESULT_NATIVE="$(maybe_native "$RESULT_FILE")"
    STATE_NATIVE="$(maybe_native "$STATE_FILE")"
    LOG_DIR_NATIVE="$(maybe_native "$LOG_DIR")"
    # 路径作为参数传递，避免路径里的引号成为 Python 源码。编译态无系统 Python
    # 时摘要可省略，当前二进制退出码 + 新产物仍保留原有无 Python 运行能力。
    _SUMMARY=$(
        { [[ -n "$PY" ]] && "$PY" -c '
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
allowed = {0: {"CONVERGED"}, 1: {"CONTINUE"}, 2: {"STALLED", "REGRESSED", "EXHAUSTED"}}
if d.get("verdict") not in allowed[int(sys.argv[2])]:
    raise ValueError("result verdict does not match process exit code")
summary = [d.get("verdict", "?"), d.get("iteration", "?"),
           d.get("current_state", {}).get("total_fail", "?")]
print("\n".join(str(value) for value in summary))
' "$RESULT_NATIVE" "$LOOP_EXIT"; } 2>/dev/null || true
    )
    if [[ -n "$PY" && -z "$_SUMMARY" ]]; then
        # PATH 可能仅有 Windows Store alias / 坏 shim / Python2。它不能成为
        # 已健康运行的 _entry 的新增依赖；真正可用的 Python3 解析失败仍须阻断。
        if [[ -n "$ENTRY_BIN" ]] && ! "$PY" -c 'import json, sys; assert sys.version_info[0] >= 3' >/dev/null 2>&1; then
            PY=""
        else
            mv -f -- "$RESULT_FILE" "$RESULT_FILE.failed" || true
            echo "[run_loop.sh] INCOMPLETE: result JSON is unreadable or disagrees with exit code" >&2
            exit 3
        fi
    fi
    VERDICT=$(sed -n '1p' <<<"$_SUMMARY"); VERDICT=${VERDICT:-?}
    ITER=$(sed -n '2p' <<<"$_SUMMARY");    ITER=${ITER:-?}
    FAIL=$(sed -n '3p' <<<"$_SUMMARY");    FAIL=${FAIL:-?}
    echo "[run_loop.sh] mode=$MODE target=$TARGET iter=$ITER verdict=$VERDICT total_fail=$FAIL" >&2
    echo "[run_loop.sh] result_json=$RESULT_NATIVE" >&2
    echo "[run_loop.sh] state_file=$STATE_NATIVE" >&2
    if [[ "$LOOP_EXIT" -eq 1 ]]; then
        echo "[run_loop.sh] CONTINUE → dispatch repair worker with result.dispatch_prompt, then re-invoke this script" >&2
    elif [[ "$LOOP_EXIT" -eq 0 ]]; then
        FINAL_JSON=$([[ "$MODE" == "pipeline" ]] && echo "loops-final-structural-closure" || echo "loops-$MODE-$TARGET")
        # 提示里给出本机实际可用的调用方式（编译态用 _entry.bin 子命令，否则系统解释器）
        if [[ -n "$ENTRY_BIN" ]]; then
            FINAL_CMD="$ENTRY_BIN structural_loop finalize"
        else
            FINAL_CMD="$PY $STRUCTURAL_LOOP finalize"
        fi
        echo "[run_loop.sh] CONVERGED → call: $FINAL_CMD --state-file $STATE_NATIVE --output-json $LOG_DIR_NATIVE/$FINAL_JSON.json" >&2
        echo "[run_loop.sh] NOTE: finalize 会跑 detector 完成度闸；缺项将判 INCOMPLETE 而非 PASS" >&2
    elif [[ "$LOOP_EXIT" -eq 2 ]]; then
        echo "[run_loop.sh] ESCALATED → finalize then write handoff escalation section" >&2
    fi
fi

exit $LOOP_EXIT
