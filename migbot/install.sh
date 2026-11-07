#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$root/.." && pwd)"
target="$PWD"; ios_path=""; host=native; scope=project; lang=""
while [ $# -gt 0 ]; do
  case "$1" in
    --target|--project) target="$2"; shift 2 ;;
    --ios|--ios-path) ios_path="$2"; shift 2 ;;
    --migration-host) host="$2"; shift 2 ;;
    --scope) scope="$2"; shift 2 ;;
    --lang) lang="$2"; shift 2 ;;
    *) echo "Unknown argument: $1" >&2; exit 64 ;;
  esac
done
args=(--project "$target")
[ -z "$ios_path" ] || args+=(--ios "$ios_path")
[ -z "$lang" ] || args+=(--lang "$lang")
# --migration-host/--scope are retained as accepted compatibility options for
# older automation.  The iOS installer is local and does not dispatch a
# remote migration host; the selected values are intentionally not forwarded.
args+=(--repo-root "$repo_root")
exec python3 -u -X utf8 "$root/scripts/migbot-install.py" "${args[@]}"
