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
XCUI_IDENTIFIER = re.compile(r"(?:^|, )identifier: '((?:\\.|[^'\\])*)'")
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
CONTROL_CLIPPING_TOLERANCE = 1.0


@dataclass(frozen=True)
class Node:
    role: str
    label: str
    box: tuple[float, float, float, float]
    context: tuple[tuple[str, str], ...]
    presentation: tuple[int, ...] = ()
    original_box: tuple[float, float, float, float] | None = None

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


def ios_navigation_subtree(description, identifier):
    """Find the unique container holding the named XCUI navigation bar."""
    stack, matches, ends = [], [], {}
    lines = description.splitlines()
    active = False
    end = len(lines)
    for index, line in enumerate(lines):
        if line.strip() == 'Element subtree:':
            active = True
        if line.strip() in {'Path to element:', 'Query chain:'} and active:
            end = index
            break
        node = XCUI_NODE.match(line) if active else None
        if node is None:
            continue
        depth = len(node['indent'])
        while stack and stack[-1][0] >= depth:
            _, start = stack.pop()
            ends[start] = index
        named = XCUI_IDENTIFIER.search(node['rest']) if node['role'] == 'NavigationBar' else None
        if named and named[1] == identifier and stack:
            matches.append(stack[-1][1])
        stack.append((depth, index))
    if len(matches) != 1:
        raise ValueError('expected one iOS navigation bar with the requested identifier')
    start = matches[0]
    if XCUI_NODE.match(lines[start])['role'].startswith('Window'):
        raise ValueError('iOS navigation bar is not inside a dedicated container')
    return range(start, ends.get(start, end))


def collect_ios(data, *, navigation_identifier=None):
    description = data.get('debug_description')
    selected = None
    if navigation_identifier is not None:
        if not isinstance(description, str):
            raise ValueError('iOS navigation scoping requires an XCUI debug description')
        selected = ios_navigation_subtree(description, navigation_identifier)
    if isinstance(description, str):
        viewport, nodes, ancestors = None, [], []
        in_subtree = False
        for index, line in enumerate(description.splitlines()):
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
            if role in ANCHORS and normalize(label) and not excluded and (selected is None or index in selected):
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


def collect_harmony(data, *, native_control_roles=False, surface_type=None, tab_bar_id=None):
    viewport = hdc_rect(data.get('attributes', {}).get('bounds'))

    def visit(item, context=(), path=(), presentation=()):
        attrs = item.get('attributes', {})
        raw_role = attrs.get('type')
        if raw_role in SYSTEM or attrs.get('visible') in ('false', False):
            return []
        if raw_role in ('SheetPage', 'ModalPage'):
            presentation = path
        role = 'tabs' if tab_bar_id is not None and attrs.get('id') == tab_bar_id else ROLE.get(raw_role, '')
        clickable = attrs.get('clickable') == 'true'
        if clickable and (not role or (native_control_roles and role == 'text')):
            role = 'button'
        label = attrs.get('description') or attrs.get('text') or ''
        if native_control_roles:
            label = attrs.get('accessibilityText') or attrs.get('accessibilityDescription') or label
        box = hdc_rect(attrs.get('bounds'))
        next_context = (*context, (role, normalize(label))) if role else context
        descendants = [node for index, child in enumerate(item.get('children', []))
                       for node in visit(child, next_context, (*path, index), presentation)]
        if role in {'button', 'toggle'} and not normalize(label):
            labels = {node.key[1]: node.label for node in descendants if node.role == 'text'}
            if len(labels) == 1:
                label = next(iter(labels.values()))
        if role in ANCHORS and normalize(label) and box:
            if role in {'button', 'toggle', 'input'}:
                descendants = [node for node in descendants if node.role != 'text' or node.key[1] != normalize(label)]
            original = hdc_rect(attrs.get('origBounds'))
            return [Node(role, label, box, context, presentation, original), *descendants]
        return descendants

    if surface_type is None:
        return viewport, visit(data)

    def surfaces(item):
        attrs = item.get('attributes', {})
        if attrs.get('visible') in ('false', False) or attrs.get('type') in SYSTEM:
            return
        if attrs.get('type') == surface_type and hdc_rect(attrs.get('bounds')) is not None:
            yield item
        for child in item.get('children', []):
            yield from surfaces(child)

    selected = list(surfaces(data))
    if len(selected) != 1:
        raise ValueError('expected one visible HarmonyOS surface of the requested type')
    return viewport, visit(selected[0])


def project_box(box, viewport, width, height):
    left, top, right, bottom = viewport
    return tuple(
        (value - origin) * scale
        for value, origin, scale in zip(box, (left, top, left, top),
                                       (width / (right-left), height / (bottom-top)) * 2)
    )


def project_nodes(nodes, viewport, width, height):
    return [
        Node(node.role, node.label, project_box(node.box, viewport, width, height),
             node.context, node.presentation,
             project_box(node.original_box, viewport, width, height) if node.original_box else None)
        for node in nodes
    ]


def in_region(node, region):
    x, y = center(node.box)
    return region[0] <= x < region[2] and region[1] <= y < region[3]


def contained(node, region):
    left, top, right, bottom = node.box
    return region[0] <= left < right <= region[2] and region[1] <= top < bottom <= region[3]


def viewport_findings(source, target, region, tab_bars=(), *, audit_control_clipping=False):
    """Identify source anchors that are fully visible and unique in the selected region."""
    source_by_key, target_by_key = defaultdict(list), defaultdict(list)
    for node in source:
        if contained(node, region):
            source_by_key[node.key].append(node)
    for node in target:
        target_by_key[node.key].append(node)
    findings = []
    for key, nodes in source_by_key.items():
        if len(nodes) != 1:
            continue
        candidates = target_by_key[key]
        label = nodes[0].label
        if not candidates:
            findings.append({'code': 'source_anchor_absent', 'role': key[0], 'label': label})
        elif len(candidates) == 1 and not contained(candidates[0], region):
            findings.append({'code': 'source_anchor_outside_target_viewport',
                             'role': key[0], 'label': label, 'target_box': candidates[0].box})
        elif len(candidates) == 1 and key[0] == 'text':
            source_height = nodes[0].box[3] - nodes[0].box[1]
            target_height = candidates[0].box[3] - candidates[0].box[1]
            if target_height < source_height / 2:
                findings.append({'code': 'target_text_frame_less_than_half_source_height',
                                 'role': key[0], 'label': label,
                                 'source_height': round(source_height, 3),
                                 'target_height': round(target_height, 3)})
        if len(candidates) == 1:
            candidate = candidates[0]
            if not any(role == 'tabs' for role, _ in candidate.context):
                original = candidate.original_box
                if (audit_control_clipping and candidate.role in CONTROLS and original
                        and contains_box(original, candidate.box)
                        and any(abs(actual - full) > CONTROL_CLIPPING_TOLERANCE
                                for actual, full in zip(candidate.box, original))):
                    findings.append({'code': 'target_control_clipped', 'role': key[0], 'label': label,
                                     'target_box': candidate.box, 'target_original_box': original})
                overlaps = [overlap(candidate.box, bar, 1) for bar in tab_bars
                            if overlap(candidate.box, bar, 0) > 0]
                if overlaps and max(overlaps) > 0:
                    findings.append({'code': 'target_anchor_overlaps_tab_bar', 'role': key[0],
                                     'label': label, 'overlap_height': round(max(overlaps), 3)})
    return findings


def visible_target_tab_bars(node, tab_bar_id=None):
    for _, box in _visible_tab_surfaces(node, tab_bar_id):
        yield box


def _visible_tab_surfaces(node, tab_bar_id, *, respect_presentation=False):
    attrs = node.get('attributes', {})
    if attrs.get('visible') in ('false', False) or attrs.get('type') in SYSTEM:
        return
    custom = tab_bar_id is not None and attrs.get('id') == tab_bar_id
    if (custom or attrs.get('type') == 'TabBar') and attrs.get('visible') in ('true', True):
        box = hdc_rect(attrs.get('bounds'))
        if custom and box is None:
            raise ValueError('custom tab bar has invalid bounds')
        if box:
            yield custom, box
    covering_surfaces = []
    children = node.get('children', [])
    for child in reversed(children) if respect_presentation else children:
        for declared, box in _visible_tab_surfaces(child, tab_bar_id, respect_presentation=respect_presentation):
            if not any(contains_box(surface, box) for surface in covering_surfaces):
                yield declared, box
        if respect_presentation:
            covering_surfaces.extend(presentation_bounds(child))


def contains_box(outer, inner):
    return outer[0] <= inner[0] and outer[1] <= inner[1] and outer[2] >= inner[2] and outer[3] >= inner[3]


def audit_navigation_status_bar(tree, control_ids=()):
    """Diagnose top-bar geometry using the active app and its system status bar."""
    roots = tree.get('children', [])
    apps = [item for item in roots if item.get('attributes', {}).get('focused') in ('true', True)]
    if len(apps) != 1 or not apps[0].get('attributes', {}).get('pagePath'):
        return {'status': 'UNAVAILABLE', 'reason': 'focused_app_surface_missing'}

    def visible_nodes(item, in_title_bar=False):
        attrs = item.get('attributes', {})
        if attrs.get('visible') in ('false', False):
            return
        in_title_bar = in_title_bar or attrs.get('type') == 'TitleBar'
        yield attrs, in_title_bar
        for child in item.get('children', []):
            yield from visible_nodes(child, in_title_bar)

    display_id = apps[0]['attributes'].get('displayId')
    status_bars = {hdc_rect(attrs.get('bounds')) for item in roots
                   if item.get('attributes', {}).get('bundleName') == 'com.ohos.sceneboard'
                   for attrs, _ in visible_nodes(item) if attrs.get('id') == 'StatusBarBox'
                   and attrs.get('visible') in ('true', True) and attrs.get('displayId') == display_id}
    if not display_id or len(status_bars) != 1 or None in status_bars:
        return {'status': 'UNAVAILABLE', 'reason': 'status_bar_bounds_missing_or_ambiguous'}
    bar, = status_bars
    controls = []
    for attrs, in_title_bar in visible_nodes(apps[0]):
        identifier = attrs.get('id')
        role = attrs.get('type')
        selected = identifier in control_ids or (in_title_bar and role in {'BackButton', 'Button', 'Text'})
        if not selected or attrs.get('visible') not in ('true', True):
            continue
        visible = hdc_rect(attrs.get('bounds'))
        original = hdc_rect(attrs.get('origBounds'))
        overlap = (min(original[3], bar[3]) - max(original[1], bar[1])
                   if original and min(original[2], bar[2]) > max(original[0], bar[0]) else 0)
        if not original or not visible:
            status = 'UNAVAILABLE'
        elif overlap > 0 and visible[1] >= bar[3] and original[1] < visible[1]:
            status = 'CLIPPED'
        elif overlap > 0:
            status = 'INTERSECTS'
        else:
            status = 'CLEAR'
        controls.append({'id': identifier, 'type': role, 'label': attrs.get('text') or attrs.get('description'),
                         'original_px': original, 'visible_px': visible, 'status': status})
    missing = sorted(set(control_ids) - {row['id'] for row in controls})
    statuses = {row['status'] for row in controls}
    status = next((value for value in ('CLIPPED', 'INTERSECTS') if value in statuses),
                  'CLEAR' if statuses == {'CLEAR'} and not missing else 'UNAVAILABLE')
    return {'status': status, 'status_bar_px': bar, 'controls': controls, 'missing_control_ids': missing}


def presentation_bounds(node):
    """Read actual native surfaces, rather than the larger sheet wrapper."""
    attrs = node.get('attributes', {})
    if attrs.get('visible') not in ('true', True):
        return
    if attrs.get('type') in ('ModalPage', 'SheetPage'):
        box = hdc_rect(attrs.get('bounds'))
        if box:
            yield box
    if attrs.get('type') == 'SheetWrapper':
        for child in node.get('children', []):
            yield from presentation_bounds(child)


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


def geometry(pairs, width, tolerance, *, cross_presentation_overlaps=None):
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
            finding = {'code': 'new_overlap', 'labels': [source.label, other_source.label]}
            findings.append(finding)
            if cross_presentation_overlaps is not None and target.presentation != other_target.presentation:
                cross_presentation_overlaps.append({
                    **finding, 'target_presentation_paths': [target.presentation, other_target.presentation],
                    'target_boxes': [target.box, other_target.box],
                })
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


def compare_relationships(root, pair, frame, target_path, target_sha256=None, *, audit_viewport=False,
                          native_control_roles=False, diagnostic_surface=None, tab_bar_id=None,
                          respect_presentation=False, audit_presentation_overlap=False,
                          audit_status_bar=False, navigation_control_ids=(), audit_control_clipping=None):
    if audit_control_clipping is None:
        audit_control_clipping = audit_viewport
    if audit_control_clipping and not audit_viewport:
        raise ValueError('control clipping audit requires a viewport audit')
    if respect_presentation and (tab_bar_id is None or not audit_viewport):
        raise ValueError('presentation-aware viewport audit requires a custom tab bar ID')
    if tab_bar_id is not None and (
        not audit_viewport or diagnostic_surface is not None
        or not isinstance(tab_bar_id, str) or not re.fullmatch(r'[\w.-]+', tab_bar_id)
    ):
        raise ValueError('custom tab bar ID requires an unscoped viewport audit and a valid control ID')
    if not isinstance(navigation_control_ids, (tuple, list)) or any(
        not isinstance(name, str) or not re.fullmatch(r'[\w.-]+', name) for name in navigation_control_ids
    ):
        raise ValueError('invalid navigation control ID')
    if audit_status_bar and diagnostic_surface is not None:
        raise ValueError('status bar audit requires an unscoped foreground tree')
    if navigation_control_ids and not audit_status_bar:
        raise ValueError('navigation control IDs require a status bar audit')
    baseline = pair['baseline']
    source = checked_artifact(_project_file(root, baseline['ui_json_path']), baseline['ui_json_sha256'])
    target = checked_artifact(target_path, target_sha256) if target_sha256 else target_path.read_bytes()
    source_data, target_data = json.loads(source), json.loads(target)
    if not isinstance(source_data, dict) or not isinstance(target_data, dict):
        raise ValueError('native dumps must be JSON objects')
    ios_nav, harmony_surface = diagnostic_surface or (None, None)
    source_view, source_nodes = collect_ios(source_data, navigation_identifier=ios_nav)
    target_view, target_nodes = collect_harmony(target_data, native_control_roles=native_control_roles,
                                               surface_type=harmony_surface)
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
    projected_nodes = [project_nodes(source_nodes, source_view, width, height),
                       project_nodes(target_nodes, target_view, width, height)]
    source_nodes, target_nodes = ([node for node in nodes if in_region(node, region)] for nodes in projected_nodes)
    pairs, unresolved = match(source_nodes, target_nodes)
    cross_presentation_overlaps = [] if audit_presentation_overlap else None
    findings = geometry(pairs, width, GEOMETRY_TOLERANCE,
                        cross_presentation_overlaps=cross_presentation_overlaps)
    verdict = 'FAIL' if findings else 'UNRESOLVED' if unresolved or not pairs else 'PASS'
    report = {
        'schema_version': 1, 'comparison_id': frame['comparison_id'], 'verdict': verdict,
        'ios_ui_sha256': sha256(source), 'harmony_ui_sha256': sha256(target),
        'ios_viewport': source_view, 'harmony_viewport': target_view,
        'geometry_units': 'normalized-ios-viewport-points', 'geometry_tolerance': GEOMETRY_TOLERANCE,
        'source_anchors': len(source_nodes), 'target_anchors': len(target_nodes), 'matched_anchors': len(pairs),
        'unresolved': unresolved, 'findings': findings,
    }
    if native_control_roles:
        report['native_control_roles'] = True
    if audit_presentation_overlap:
        report['cross_presentation_overlaps'] = cross_presentation_overlaps
    if audit_status_bar:
        report['navigation_control_ids'] = sorted(set(navigation_control_ids))
        report['navigation_status_bar'] = audit_navigation_status_bar(target_data, navigation_control_ids)
    if diagnostic_surface is not None:
        report['diagnostic_surface'] = {'ios_navigation_identifier': ios_nav,
                                        'harmony_surface_type': harmony_surface}
    if audit_viewport:
        report['audit_viewport'] = True
        if audit_control_clipping:
            report['audit_control_clipping'] = True
        detected = [] if diagnostic_surface is not None else list(_visible_tab_surfaces(target_data, tab_bar_id))
        viewport_target = projected_nodes[1]
        if tab_bar_id is not None:
            custom = [box for declared, box in detected if declared]
            if len(custom) > 1:
                raise ValueError('custom tab bar ID matches multiple visible controls')
            report['tab_bar_id'] = tab_bar_id
            report['custom_tab_bar_bounds'] = custom[0] if custom else None
            if custom:
                _, audit_nodes = collect_harmony(target_data, native_control_roles=native_control_roles,
                                                 tab_bar_id=tab_bar_id)
                viewport_target = project_nodes(audit_nodes, target_view, width, height)
        if respect_presentation:
            report['respect_presentation'] = True
            effective = list(_visible_tab_surfaces(target_data, tab_bar_id, respect_presentation=True))
            report['effective_tab_bar_bounds'] = [box for _, box in effective]
        else:
            effective = detected
        bars = [project_box(box, target_view, width, height) for _, box in effective]
        report['viewport_findings'] = viewport_findings(projected_nodes[0], viewport_target, region, bars,
                                                        audit_control_clipping=audit_control_clipping)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root', required=True)
    parser.add_argument('--scope', required=True)
    parser.add_argument('--comparison-id', required=True)
    parser.add_argument('--harmony-tree', required=True)
    parser.add_argument('--out')
    parser.add_argument('--audit-viewport', action='store_true',
                        help='Diagnose absent, clipped or overlapping target viewport anchors')
    parser.add_argument('--native-control-roles', action='store_true',
                        help='Recognize UITest clickable text and explicit accessibility names')
    parser.add_argument('--tab-bar-id', help='Include a project-declared custom bottom bar in the viewport audit')
    parser.add_argument('--respect-presentation', action='store_true',
                        help='Exclude bottom bars fully covered by a later native sheet or modal')
    parser.add_argument('--audit-presentation-overlap', action='store_true',
                        help='Record which new overlaps span distinct native sheets or modals')
    parser.add_argument('--audit-status-bar', action='store_true', help='Check foreground title controls against the status bar')
    parser.add_argument('--navigation-control-id', action='append', default=[],
                        help='Also audit this declared custom title or navigation control ID')
    parser.add_argument('--diagnostic-surface', nargs=2, metavar=('IOS_NAV_IDENTIFIER', 'HARMONY_SURFACE_TYPE'),
                        help='Inspect a known foreground layer. Output is diagnostic and cannot satisfy acceptance.')
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
        result = compare_relationships(root, pair, frame, _project_file(root, args.harmony_tree),
                                       audit_viewport=args.audit_viewport, native_control_roles=args.native_control_roles,
                                       diagnostic_surface=args.diagnostic_surface, tab_bar_id=args.tab_bar_id,
                                       respect_presentation=args.respect_presentation,
                                       audit_presentation_overlap=args.audit_presentation_overlap,
                                       audit_status_bar=args.audit_status_bar,
                                       navigation_control_ids=args.navigation_control_id)
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
