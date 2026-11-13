#!/usr/bin/env python3
"""Read scoped Plan inputs from the canonical specifications without rewriting them."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re


UI = 'spec/baseline/ui-manifest.md'
FEATURES = 'spec/baseline/feature-index.md'
HEADING = re.compile(r'^ {0,3}(#{1,6})[ \t]+(.+?)\s*$')
FENCE = re.compile(r'^ {0,3}(`{3,}|~{3,})(.*)$')
FEATURE_ID = re.compile(r'^F[0-9]{3}$')
SHARED = re.compile(r'共享(?:基础设施|组件|服务)|公共(?:组件|服务)|\bshared (?:components?|services?)\b', re.I)
PAGES = re.compile(r'SwiftUI\s+Views?\s*清单|UIKit\s+ViewControllers?\s*清单|页面清单|\bpage inventory\b', re.I)
NAVIGATION = re.compile(r'页面关系图|页面导航|\bnavigation (?:graph|relationships)\b', re.I)
UI_CONVENTIONS = re.compile(r'全局约定|转换批次规划|\bglobal conventions\b', re.I)
STACK = re.compile(r'技术栈映射总览|\btechnology stack mapping\b', re.I)


@dataclass(frozen=True)
class Section:
    start: int
    end: int
    title: str


def headings(lines: list[str]) -> list[Section]:
    marks: list[tuple[int, int, str]] = []
    open_fence = ''
    for index, line in enumerate(lines):
        fence = FENCE.match(line)
        if open_fence:
            if fence and fence[1].startswith(open_fence) and not fence[2].strip():
                open_fence = ''
            continue
        if fence:
            open_fence = fence[1]
            continue
        heading = HEADING.match(line)
        if heading:
            marks.append((index, len(heading[1]), heading[2]))
    sections = []
    for position, (start, level, title) in enumerate(marks):
        end = next((row[0] for row in marks[position + 1:] if row[1] <= level), len(lines))
        if level in (2, 3):
            sections.append(Section(start, end, title))
    return sections


def feature_heading(section: Section, feature: str) -> bool:
    return re.match(rf'^{feature}(?:\s|[:：.)-]|$)', section.title) is not None


def choose(path: str, role: str, sections: list[Section], feature_ids: list[str]) -> tuple[list[Section], str | None]:
    shared = [section for section in sections if SHARED.search(section.title)]
    if path == FEATURES:
        explicit = []
        for feature in feature_ids:
            matches = [section for section in sections if feature_heading(section, feature)]
            if len(matches) != 1:
                return [], f'feature heading for {feature} not uniquely recognized'
            explicit.extend(matches)
        if not (shared or explicit):
            return [], 'shared capability sections not recognized'
        stack = [section for section in sections if STACK.search(section.title)]
        return shared + explicit + stack, None

    if not shared:
        return [], 'shared component sections not recognized'
    if role == 'base':
        return shared, None
    pages = [section for section in sections if PAGES.search(section.title)]
    navigation = [section for section in sections if NAVIGATION.search(section.title)]
    if not pages or not navigation:
        return [], 'page inventory or navigation sections not recognized'
    conventions = [section for section in sections if role == 'ui' and UI_CONVENTIONS.search(section.title)]
    return pages + navigation + shared + conventions, None


def scoped_document(project: Path, path: str, role: str, feature_ids: list[str]) -> dict:
    source = (project / path).resolve(strict=True)
    if project not in source.parents:
        raise ValueError(f'specification is outside the project: {path}')
    raw = source.read_bytes()
    lines = raw.decode('utf-8').splitlines(keepends=True)
    sections, fallback = choose(path, role, headings(lines), feature_ids)
    if fallback:
        sections = [Section(0, len(lines), 'Full canonical specification')]
    spans = []
    for section in sorted(set(sections), key=lambda item: (item.start, -item.end)):
        if spans and section.end <= spans[-1].end:
            continue
        spans.append(section)
    return {
        'path': path, 'sha256': sha256(raw).hexdigest(), 'source_bytes': len(raw), 'fallback': fallback,
        'excerpts': [{'first_line': span.start + 1, 'last_line': span.end,
                      'text': ''.join(lines[span.start:span.end])} for span in spans],
    }


def build_view(project: Path, role: str, feature_ids: list[str]) -> list[dict]:
    project = project.resolve(strict=True)
    paths = (UI, FEATURES) if role == 'base' else (UI,)
    return [scoped_document(project, path, role, feature_ids) for path in paths]


def markdown(documents: list[dict]) -> str:
    parts = []
    for doc in documents:
        if doc['fallback']:
            parts.append(f"<!-- full input: {doc['fallback']} -->\n")
        for span in doc['excerpts']:
            parts.append(f"<!-- {doc['path']}:{span['first_line']}-{span['last_line']} sha256:{doc['sha256']} -->\n"
                         + span['text'].rstrip('\r\n') + '\n')
    return '\n'.join(parts)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root', type=Path, default=Path.cwd())
    parser.add_argument('--role', choices=('ui', 'base', 'slice'), required=True)
    parser.add_argument('--shared-feature-id', action='append', default=[])
    parser.add_argument('--json', action='store_true', help='Report exact spans and provenance as JSON')
    args = parser.parse_args()
    if args.shared_feature_id and (args.role != 'base' or not all(FEATURE_ID.fullmatch(f) for f in args.shared_feature_id)):
        parser.error('--shared-feature-id requires --role base and a canonical F-ID')
    try:
        documents = build_view(args.project_root, args.role, args.shared_feature_id)
    except (OSError, ValueError) as error:
        parser.exit(2, f'plan input view: {error}\n')
    print(json.dumps(documents, ensure_ascii=False, indent=2) if args.json else markdown(documents), end='')


if __name__ == '__main__':
    main()
