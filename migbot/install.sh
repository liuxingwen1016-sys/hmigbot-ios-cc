#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
target="$PWD"; host=native; scope=project; lang=""
while [ $# -gt 0 ]; do
  case "$1" in
    --target|--project) target="$2"; shift 2 ;;
    --migration-host) host="$2"; shift 2 ;;
    --scope) scope="$2"; shift 2 ;;
    --lang) lang="$2"; shift 2 ;;
    *) echo "Unknown argument: $1" >&2; exit 64 ;;
  esac
done
args=(--repo-root "$root" --project "$target" --host "$host" --scope "$scope" --yes)
[ -z "$lang" ] || args+=(--lang "$lang")
exec python3 -u -X utf8 "$root/scripts/migbot-install.py" "${args[@]}"
