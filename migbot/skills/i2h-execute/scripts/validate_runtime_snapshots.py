from __future__ import annotations

from lib.validate_runtime_snapshots import *
from lib.validate_runtime_snapshots import main
from _launcher import dispatch
import json
import sys
from pathlib import Path


def _arg_value(argv: list[str], *names: str) -> str | None:
    for index, value in enumerate(argv):
        if value in names and index + 1 < len(argv):
            return argv[index + 1]
    return None


def _contains_ios_evidence(argv: list[str]) -> bool:
    project_root = _arg_value(argv, '--project-root')
    pages_file = _arg_value(argv, '--pages-file', '--pages')
    if not project_root or not pages_file:
        return False
    root = Path(project_root).expanduser().resolve()
    try:
        pages_payload = json.loads(Path(pages_file).expanduser().read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return False
    pages = pages_payload.get('pages', pages_payload) if isinstance(pages_payload, dict) else pages_payload
    if not isinstance(pages, list):
        return False
    for page in pages:
        if not isinstance(page, dict) or not page.get('page_id'):
            continue
        meta_path = root / 'spec/baseline/ui-snapshots' / str(page['page_id']) / 'meta.json'
        try:
            meta = json.loads(meta_path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            continue
        evidence = meta.get('runtime_evidence')
        if isinstance(evidence, dict) and (
            is_ios_evidence(evidence, meta)
            or any(evidence.get(key) for key in ('ui_json_path', 'accessibility_json_path', 'accessibility_path'))
        ):
            return True
        states = meta.get('runtime_evidence_by_state')
        if isinstance(states, dict) and any(
            isinstance(value, dict)
            and (
                is_ios_evidence(value, meta)
                or any(value.get(key) for key in ('ui_json_path', 'accessibility_json_path', 'accessibility_path'))
            )
            for value in states.values()
        ):
            return True
    return False


def _fallback_arguments(argv: list[str]) -> list[str]:
    translated: list[str] = []
    index = 0
    while index < len(argv):
        value = argv[index]
        if value == '--pages-file':
            translated.append('--pages')
        elif value == '--capture-policy':
            translated.append('--policy')
        else:
            translated.append(value)
        index += 1
    return translated


if __name__ == '__main__':
    arguments = sys.argv[1:]
    if _contains_ios_evidence(arguments):
        raise SystemExit(main(_fallback_arguments(arguments)))
    raise SystemExit(dispatch('validate_runtime_snapshots', fallback=main))
