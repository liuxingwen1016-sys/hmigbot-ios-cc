"""Compare semantics and geometry in XCUITest and HarmonyOS UI test dumps."""
from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
from itertools import combinations
import json
import math
from pathlib import Path
import re
import struct
import sys
import unicodedata

from .ios_ui_delivery_gate import _project_file, _read_object
from .ios_ui_dispatch import atomic_write, checked_artifact, json_bytes, sha256
from .stage1_visual_acceptance import _frame


XCUI_NODE = re.compile(
    r"^(?P<indent>\s*)(?P<role>[\w ]+?(?: \(Main\))?), 0x[0-9a-fA-F]+, "
    r"\{\{([^,]+), ([^}]+)\}, \{([^,]+), ([^}]+)\}\}(?P<rest>.*)$"
)
XCUI_LABEL = re.compile(r"(?:^|, )label: '((?:\\.|[^'\\])*)'")
HDC_BOUNDS = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")
ROLE = {
    'StaticText': 'text', 'Text': 'text', 'TextClock': 'text', 'text': 'text',
    'Button': 'button', 'button': 'button', 'Link': 'button', 'MenuItem': 'button',
    'Switch': 'toggle', 'Toggle': 'toggle', 'CheckBox': 'toggle',
    'Slider': 'slider', 'TextField': 'input', 'SecureTextField': 'input',
    'TextInput': 'input', 'TextArea': 'input', 'TextView': 'input',
    'SearchField': 'input', 'Search': 'input', 'Image': 'image',
    'ScrollView': 'scroll', 'Scroll': 'scroll', 'List': 'list', 'CollectionView': 'list',
    'Cell': 'row', 'ListItem': 'row', 'NavigationBar': 'navigation',
    'TabBar': 'tabs', 'Tab': 'button', 'Menu': 'menu', 'Alert': 'dialog',
}
ANCHORS = {'text', 'button', 'toggle', 'slider', 'input', 'image'}
CONTROLS = {'button', 'toggle', 'slider', 'input'}
SYSTEM = {'StatusBar', 'Keyboard', 'WindowScene'}
GEOMETRY_TOLERANCE = 4.0


@dataclass(frozen=True)
class Node:
    role: str
    label: str
    box: tuple[float, float, float, float]
    context: tuple[tuple[str, str], ...]

    @property
    def key(self):
        return self.role, normalize(self.label)


def normalize(text):
    return ''.join(unicodedata.normalize('NFKC', text).casefold().split()) if isinstance(text, str) else ''


def rect(frame):
    if not frame or not all(math.isfinite(value) for value in frame):
        return None
    x, y, width, height = frame
    return (x, y, x + width, y + height) if width > 0 and height > 0 else None


def hdc_rect(value):
    match = HDC_BOUNDS.fullmatch(value) if isinstance(value, str) else None
    if match is None:
        return None
    left, top, right, bottom = map(int, match.groups())
    return rect((left, top, right - left, bottom - top))


def center(box):
    return ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)


def semantic_context(ancestors):
    return tuple((role, normalize(label)) for role, label in ancestors if role)


def collect_ios(data):
    description = data.get('debug_description')
    if isinstance(description, str):
        viewport, nodes, ancestors = None, [], []
        in_subtree = False
        for line in description.splitlines():
            if line.strip() == 'Element subtree:':
                in_subtree = True
            if in_subtree and line.strip() in {'Path to element:', 'Query chain:'}:
                break
            match = XCUI_NODE.match(line) if in_subtree else None
            if match is None:
                continue
            raw_role = match['role']
            indent = len(match['indent'])
            while ancestors and ancestors[-1][0] >= indent:
                ancestors.pop()
            if raw_role == 'Window (Main)' and viewport is None:
                viewport = rect(tuple(float(match[index]) for index in range(3, 7)))
            found = XCUI_LABEL.search(match['rest'])
            label = found[1].replace("\\'", "'") if found else ''
            role = ROLE.get(raw_role, '')
            excluded = raw_role in SYSTEM or (ancestors and ancestors[-1][3])
            if role in ANCHORS and normalize(label) and not excluded:
                box = rect(tuple(float(match[index]) for index in range(3, 7)))
                if box and not any(parent_role == 'button' and normalize(parent_label) == normalize(label)
                                   for _, parent_role, parent_label, _ in ancestors):
                    nodes.append(Node(role, label, box, semantic_context((r, text) for _, r, text, _ in ancestors)))
            ancestors.append((indent, role, label, bool(excluded)))
        return viewport, nodes

    viewport = rect(_frame(data.get('viewport')))
    nodes = []

    def visit(item, context=()):
        role = ROLE.get(item.get('role', item.get('type')), '')
        label = item.get('label') or ''
        box = rect(_frame(item.get('frame')))
        if role in ANCHORS and normalize(label) and box:
            nodes.append(Node(role, label, box, context))
        next_context = (*context, (role, normalize(label))) if role else context
        for child in item.get('children', []):
            visit(child, next_context)

    for item in data.get('nodes', []):
        visit(item)
    return viewport, nodes


def collect_harmony(data):
    viewport = hdc_rect(data.get('attributes', {}).get('bounds'))

    def visit(item, context=()):
        attrs = item.get('attributes', {})
        raw_role = attrs.get('type')
        if raw_role in SYSTEM or attrs.get('visible') in ('false', False):
            return []
        role = ROLE.get(raw_role, '')
        if not role and attrs.get('clickable') == 'true':
            role = 'button'
        label = attrs.get('description') or attrs.get('text') or ''
        box = hdc_rect(attrs.get('bounds'))
        next_context = (*context, (role, normalize(label))) if role else context
        descendants = [node for child in item.get('children', []) for node in visit(child, next_context)]
        if role in {'button', 'toggle'} and not normalize(label):
            labels = {node.key[1]: node.label for node in descendants if node.role == 'text'}
            if len(labels) == 1:
                label = next(iter(labels.values()))
        if role in ANCHORS and normalize(label) and box:
            if role in {'button', 'toggle', 'input'}:
                descendants = [node for node in descendants if node.role != 'text' or node.key[1] != normalize(label)]
            return [Node(role, label, box, context), *descendants]
        return descendants

    return viewport, visit(data)


def project_box(box, viewport, width, height):
    left, top, right, bottom = viewport
    return tuple(
        (value - origin) * scale
        for value, origin, scale in zip(box, (left, top, left, top),
                                       (width / (right-left), height / (bottom-top)) * 2)
    )


def in_region(node, region):
    x, y = center(node.box)
    return region[0] <= x < region[2] and region[1] <= y < region[3]


def match(source, target):
    source_groups, target_groups = defaultdict(list), defaultdict(list)
    for node in source:
        source_groups[node.key].append(node)
    for node in target:
        target_groups[node.key].append(node)
    pairs, unresolved = [], []
    for key, group in source_groups.items():
        candidates = target_groups[key]
        if len(group) == len(candidates) == 1:
            pairs.append((group[0], candidates[0]))
            continue
        for node in group:
            equivalent = [candidate for candidate in candidates if candidate.context == node.context]
            if len(equivalent) == 1 and sum(other.context == node.context for other in group) == 1:
                pairs.append((node, equivalent[0]))
            else:
                unresolved.append({'role': node.role, 'label': node.label, 'context': node.context,
                                   'candidate_count': len(candidates)})
    return pairs, unresolved


def overlap(first, second, axis):
    return min(first[axis+2], second[axis+2]) - max(first[axis], second[axis])


def horizontal_delta(source, target, width, tolerance):
    source_left, _, source_right, _ = source.box
    target_left, _, target_right, _ = target.box
    if source.role != 'text':
        return max(abs(source_left - target_left), abs(source_right - target_right))
    # ArkUI may stretch a Text node to its parent width even when the rendered
    # glyphs occupy less space. Compare the source alignment, not the far edge.
    if abs(center(source.box)[0] - width / 2) <= tolerance:
        return abs(center(source.box)[0] - center(target.box)[0])
    if source_left > width - source_right:
        return abs(source_right - target_right)
    return abs(source_left - target_left)


def geometry(pairs, width, tolerance):
    findings = []
    for source, target in pairs:
        edge_delta = horizontal_delta(source, target, width, tolerance)
        vertical_delta = abs(center(source.box)[1] - center(target.box)[1])
        for code, delta in (('horizontal_edge_drift', edge_delta), ('vertical_position_drift', vertical_delta)):
            if delta > tolerance:
                findings.append({'code': code, 'labels': [source.label], 'delta': round(delta, 3)})
    for (source, target), (other_source, other_target) in combinations(pairs, 2):
        if (source.role in CONTROLS and other_source.role in CONTROLS
                and not all(overlap(source.box, other_source.box, axis) > tolerance for axis in (0, 1))
                and all(overlap(target.box, other_target.box, axis) > tolerance for axis in (0, 1))):
            findings.append({'code': 'new_overlap', 'labels': [source.label, other_source.label]})
    for axis in (0, 1):
        ordered = sorted(pairs, key=lambda pair: center(pair[0].box)[axis])
        for index, (source, target) in enumerate(ordered):
            neighbors = [(other_source, other_target) for other_source, other_target in ordered[index+1:]
                         if other_source.box[axis] >= source.box[axis+2]
                         and overlap(source.box, other_source.box, 1-axis) > tolerance]
            if not neighbors:
                continue
            other_source, other_target = min(neighbors, key=lambda pair: pair[0].box[axis])
            source_gap = other_source.box[axis] - source.box[axis+2]
            target_gap = other_target.box[axis] - target.box[axis+2]
            if center(other_target.box)[axis] < center(target.box)[axis]:
                findings.append({'code': 'order_changed', 'axis': axis, 'labels': [source.label, other_source.label]})
            elif abs(source_gap - target_gap) > tolerance:
                findings.append({'code': 'gap_changed', 'axis': axis, 'labels': [source.label, other_source.label],
                                 'delta': round(target_gap - source_gap, 3)})
    return findings


def compare_relationships(root, pair, frame, target_path, target_sha256=None):
    baseline = pair['baseline']
    source = checked_artifact(_project_file(root, baseline['ui_json_path']), baseline['ui_json_sha256'])
    target = checked_artifact(target_path, target_sha256) if target_sha256 else target_path.read_bytes()
    source_data, target_data = json.loads(source), json.loads(target)
    if not isinstance(source_data, dict) or not isinstance(target_data, dict):
        raise ValueError('native dumps must be JSON objects')
    source_view, source_nodes = collect_ios(source_data)
    target_view, target_nodes = collect_harmony(target_data)
    if source_view is None or target_view is None:
        raise ValueError('both native dumps must provide a valid viewport')
    width, height = source_view[2]-source_view[0], source_view[3]-source_view[1]
    region = (0, 0, width, height)
    if frame.get('ios_region_px') is not None:
        png = checked_artifact(_project_file(root, baseline['png_path']), baseline['png_sha256'])
        if len(png) < 24 or png[:8] != b'\x89PNG\r\n\x1a\n' or png[12:16] != b'IHDR':
            raise ValueError('iOS source PNG does not have an IHDR viewport')
        pixel_width, pixel_height = struct.unpack('>II', png[16:24])
        x, y, region_width, region_height = frame['ios_region_px']
        if not (0 <= x < x+region_width <= pixel_width and 0 <= y < y+region_height <= pixel_height):
            raise ValueError('iOS comparison region is outside the source screenshot')
        region = project_box((x, y, x+region_width, y+region_height), (0, 0, pixel_width, pixel_height), width, height)
    scoped = []
    for viewport, nodes in ((source_view, source_nodes), (target_view, target_nodes)):
        projected = [Node(node.role, node.label, project_box(node.box, viewport, width, height), node.context)
                     for node in nodes]
        scoped.append([node for node in projected if in_region(node, region)])
    source_nodes, target_nodes = scoped
    pairs, unresolved = match(source_nodes, target_nodes)
    findings = geometry(pairs, width, GEOMETRY_TOLERANCE)
    verdict = 'FAIL' if findings else 'UNRESOLVED' if unresolved or not pairs else 'PASS'
    return {
        'schema_version': 1, 'comparison_id': frame['comparison_id'], 'verdict': verdict,
        'ios_ui_sha256': sha256(source), 'harmony_ui_sha256': sha256(target),
        'ios_viewport': source_view, 'harmony_viewport': target_view,
        'geometry_units': 'normalized-ios-viewport-points', 'geometry_tolerance': GEOMETRY_TOLERANCE,
        'source_anchors': len(source_nodes), 'target_anchors': len(target_nodes), 'matched_anchors': len(pairs),
        'unresolved': unresolved, 'findings': findings,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root', required=True)
    parser.add_argument('--scope', required=True)
    parser.add_argument('--comparison-id', required=True)
    parser.add_argument('--harmony-tree', required=True)
    parser.add_argument('--out')
    args = parser.parse_args(argv)
    try:
        root = Path(args.project_root).expanduser().resolve()
        scope = _read_object(_project_file(root, args.scope))
        if scope.get('schema_version') != 2:
            raise ValueError('an iOS schema-2 visual scope is required')
        selected = [(pair, frame) for pair in scope['pairs'] for frame in pair['comparisons']
                    if frame['comparison_id'] == args.comparison_id]
        if len(selected) != 1:
            raise ValueError('comparison ID must select one frozen frame')
        pair, frame = selected[0]
        result = compare_relationships(root, pair, frame, _project_file(root, args.harmony_tree))
        raw = json_bytes(result)
        if args.out:
            output = _project_file(root, args.out)
            if output.exists():
                raise ValueError('relationship report already exists')
            atomic_write(output, raw)
        else:
            print(raw.decode('utf-8'), end='')
    except (OSError, ValueError, TypeError, KeyError, ZeroDivisionError, struct.error) as exc:
        print(f'ui_relationships tool_error: {exc}', file=sys.stderr)
        return 3
    return 0 if result['verdict'] == 'PASS' else 2
