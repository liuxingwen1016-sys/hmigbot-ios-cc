"""Opt-in native symbol anchors and approved iOS navigation scoping (app-neutral fixtures).

Source coordinates are XCUI points in a 100x200 window; target bounds are HarmonyOS
pixels in a 300x600 window, so 3 px equal one normalized point.  The final geometry
contract stays at 4 pt: an 18 px (6 pt) shift must FAIL even after a symbol is paired.
"""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.ios_stage1_visual_gate import _comparison
from lib.ios_ui_dispatch import json_bytes, sha256
from lib.ios_ui_relationships import compare_relationships


BUNDLE, PAGE = 'sample.app', 'pages/Sample'
SYMBOL_MODE = {'native_control_roles': True, 'native_symbol_anchors': True}

SAMPLE = "StaticText, 0x110, {{10.0, 10.0}, {50.0, 20.0}}, label: 'Sample'"
STAR = "Image, 0x111, {{70.0, 10.0}, {20.0, 20.0}}, identifier: 'sample-star', label: 'Star'"
ADD_BUTTON = "Button, 0x112, {{10.0, 40.0}, {80.0, 20.0}}, label: 'Add Item'"
PLUS = "  Image, 0x113, {{12.0, 42.0}, {16.0, 16.0}}, identifier: 'sample-plus', label: 'Add'"
COPY_BUTTON = "Button, 0x114, {{10.0, 70.0}, {80.0, 20.0}}, label: 'Copy Item'"
HEART = "Image, 0x115, {{70.0, 100.0}, {20.0, 20.0}}, identifier: 'sample-heart', label: 'Heart'"
STANDARD = (SAMPLE, STAR, ADD_BUTTON, PLUS)
STAR_BOX, PLUS_BOX, HEART_BOX = '[210,30][270,90]', '[36,126][84,174]', '[210,300][270,360]'

TAB = ("TabBar, 0x130, {{0.0, 180.0}, {100.0, 20.0}}",
       "  Button, 0x131, {{0.0, 180.0}, {50.0, 20.0}}, label: 'Home'",
       "    Image, 0x132, {{18.0, 182.0}, {14.0, 14.0}}, identifier: 'sample-home', label: 'house'")

HOST = ("Other, 0x140, {{0.0, 0.0}, {100.0, 200.0}}",
        "  NavigationBar, 0x141, {{0.0, 0.0}, {100.0, 20.0}}, identifier: 'Library'",
        "  StaticText, 0x142, {{10.0, 30.0}, {50.0, 20.0}}, label: 'Host row'")
EDITOR = ("Other, 0x150, {{0.0, 40.0}, {100.0, 160.0}}",
          "  NavigationBar, 0x151, {{0.0, 40.0}, {100.0, 20.0}}, identifier: 'Edit Item'",
          "    StaticText, 0x152, {{30.0, 42.0}, {40.0, 16.0}}, label: 'Edit Item'",
          "  StaticText, 0x153, {{10.0, 70.0}, {50.0, 20.0}}, identifier: 'sample-name', label: 'Name'")


def predicate(*present):
    return {'bundle': BUNDLE, 'page_path': PAGE, 'present': list(present) or [{'text': 'Sample'}],
            'absent': [{'id': 'sample-absent'}]}


def xcui(lines):
    body = ''.join(f'      {line}\n' for line in lines)
    return ("Attributes: Application, 0x100, label: 'Sample'\nElement subtree:\n"
            "    Window (Main), 0x101, {{0.0, 0.0}, {100.0, 200.0}}\n" + body
            + "Query chain:\n    StaticText, 0x1ff, {{10.0, 50.0}, {30.0, 8.0}}, label: 'Ignore'\n")


def node(kind, bounds, children=(), **attrs):
    return {'attributes': {'type': kind, 'bounds': bounds, 'visible': 'true', **attrs}, 'children': list(children)}


def symbol(identifier, description, bounds, *, orig=None, children=(), **attrs):
    values = {'origBounds': orig or bounds, 'clickable': 'false', 'description': description, **attrs}
    if identifier is not None:
        values['id'] = identifier
    return node('SymbolGlyph', bounds, children, **values)


def button(label, bounds, children=()):
    return node('Button', bounds, children, text=label, clickable='true')


def text(label, bounds, **attrs):
    return node('Text', bounds, text=label, **attrs)


def window(children):
    return {'attributes': {'bounds': '[0,0][300,600]'}, 'children': [node(
        'Window', '[0,0][300,600]', children, bundleName=BUNDLE, pagePath=PAGE, focused='true')]}


def standard_target(star=None, plus=None, extra=()):
    star = [symbol('sample-star', 'Star', STAR_BOX)] if star is None else star
    plus = [symbol('sample-plus', 'Add', PLUS_BOX)] if plus is None else plus
    return [text('Sample', '[30,30][180,90]'), *star, button('Add Item', '[30,120][270,180]', plus), *extra]


def dot_line(address, y):
    return "Image, 0x%x, {{20.0, %.1f}, {10.0, 10.0}}, identifier: 'sample-dot', label: 'Dot'" % (address, y)


def dot(y_px):
    return symbol('sample-dot', 'Dot', f'[60,{y_px}][90,{y_px + 30}]')


def tab_bar(kind='Column', icon=True, **attrs):
    icons = [symbol('sample-home', 'house', '[54,546][96,588]')] if icon else []
    return node(kind, '[0,540][300,600]', [button('Home', '[0,540][150,600]', icons)], **attrs)


def editor_target(modal='ModalPage'):
    return [node('Column', '[0,0][300,600]', [text('Host row', '[30,90][180,150]')]),
            node(modal, '[0,120][300,600]', [text('Edit Item', '[90,126][210,174]'),
                                              text('Name', '[30,210][180,270]', id='sample-name')],
                 id='sample-editor')]


class SymbolFixture:
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name).resolve()
        self.source = self.root / 'ios.json'
        self.target = self.root / 'harmony.json'
        self.frame = {'comparison_id': 'sample:0', 'ios_region_px': None}

    def compare(self, source_lines, target_children, *, observation=True, raw_target=None, **options):
        self.source.write_text(json.dumps({'debug_description': xcui(source_lines)}))
        self.target.write_text(json.dumps(raw_target or window(target_children)))
        pair = {'baseline': {'ui_json_path': self.source.name, 'ui_json_sha256': sha256(self.source.read_bytes())}}
        if observation is not False:
            pair['target_observation'] = predicate() if observation is True else observation
        return compare_relationships(self.root, pair, self.frame, self.target, **options)

    @staticmethod
    def unresolved(report):
        return sorted(row['label'] for row in report['unresolved'])

    @staticmethod
    def matched_ids(report):
        return sorted(row['identifier'] for row in report['native_symbol_anchors']['matched'])


class NativeSymbolAnchorTests(SymbolFixture, unittest.TestCase):
    def test_explicit_identifiers_pair_standalone_and_button_symbols(self):
        legacy = self.compare(STANDARD, standard_target(), native_control_roles=True)
        self.assertEqual(legacy['verdict'], 'UNRESOLVED')
        self.assertEqual(self.unresolved(legacy), ['Add', 'Star'])
        report = self.compare(STANDARD, standard_target(), **SYMBOL_MODE)
        self.assertEqual(report['verdict'], 'PASS')
        self.assertEqual((report['source_anchors'], report['matched_anchors']), (4, 4))
        self.assertEqual(report['unresolved'], [])
        self.assertEqual(report['findings'], [])
        self.assertEqual(report['native_symbol_anchors']['contract'], 'native-symbol-anchors-v1')
        self.assertEqual(self.matched_ids(report), ['sample-plus', 'sample-star'])

    def test_opt_in_requires_approved_layer_native_roles_and_formal_mode(self):
        cases = [
            {'observation': False, **SYMBOL_MODE},
            {'native_symbol_anchors': True},
            {**SYMBOL_MODE, 'diagnostic_surface': ('Sample', 'ModalPage')},
        ]
        for options in cases:
            with self.subTest(options=options), self.assertRaisesRegex(ValueError, 'native symbol anchors require'):
                self.compare(STANDARD, standard_target(), **options)

    def test_default_mode_report_is_unchanged(self):
        implicit = self.compare(STANDARD, standard_target(), native_control_roles=True)
        explicit = self.compare(STANDARD, standard_target(), native_control_roles=True,
                                native_symbol_anchors=False, approved_source_navigation=False)
        self.assertEqual(implicit, explicit)
        self.assertNotIn('native_symbol_anchors', implicit)
        self.assertNotIn('approved_source_navigation', implicit)
        self.assertEqual(implicit['target_anchors'], 2)
        plain = self.compare(STANDARD, standard_target(), observation=False)
        self.assertEqual(plain['target_anchors'], 2)
        self.assertEqual(self.unresolved(plain), ['Add', 'Star'])

    def test_conflicting_or_unbound_identifiers_are_rejected(self):
        no_identifier = "Image, 0x111, {{70.0, 10.0}, {20.0, 20.0}}, label: 'Star'"
        cases = {
            'explicit id with conflicting description cannot alias': (
                (*STANDARD, HEART), [symbol('sample-star', 'Heart', STAR_BOX)],
                [symbol('sample-heart', 'Heart', HEART_BOX)]),
            'unknown id with unknown description': (
                STANDARD, [symbol('sample-moon', 'Moon', STAR_BOX)], []),
            'source image without explicit identifier': (
                (SAMPLE, no_identifier, ADD_BUTTON, PLUS), None, []),
        }
        for name, (source, star, extra) in cases.items():
            with self.subTest(name):
                report = self.compare(source, standard_target(star=star, extra=extra), **SYMBOL_MODE)
                self.assertEqual(report['verdict'], 'UNRESOLVED')
                self.assertEqual(self.unresolved(report), ['Star'])
                self.assertIn('sample-plus', self.matched_ids(report))

    def test_label_alias_is_limited_to_one_label_in_the_same_parent_context(self):
        aliased = standard_target(star=[symbol('harmony-star', 'Star', STAR_BOX)],
                                  plus=[symbol('harmony-plus', 'Add', PLUS_BOX)])
        report = self.compare(STANDARD, aliased, **SYMBOL_MODE)
        self.assertEqual(report['verdict'], 'PASS')
        self.assertEqual(self.matched_ids(report), ['sample-plus', 'sample-star'])
        moved = standard_target(plus=[], extra=[symbol('harmony-plus', 'Add', '[30,450][78,498]')])
        self.assertEqual(self.unresolved(self.compare(STANDARD, moved, **SYMBOL_MODE)), ['Add'])
        twin = "Image, 0x116, {{70.0, 100.0}, {20.0, 20.0}}, identifier: 'sample-star-alt', label: 'Star'"
        ambiguous = standard_target(star=[symbol('harmony-star', 'Star', STAR_BOX),
                                          symbol('harmony-star', 'Star', HEART_BOX)])
        report = self.compare((*STANDARD, twin), ambiguous, **SYMBOL_MODE)
        self.assertEqual(self.unresolved(report), ['Star', 'Star'])

    def test_hidden_clipped_nested_offscreen_and_background_symbols_are_rejected(self):
        cases = {
            'hidden': [symbol('sample-star', 'Star', STAR_BOX, visible='false')],
            'clipped': [symbol('sample-star', 'Star', STAR_BOX, orig='[210,30][270,100]')],
            'nested': [symbol('sample-star', 'Star', STAR_BOX, children=[node('Blank', '[220,40][260,80]')])],
        }
        for name, star in cases.items():
            with self.subTest(name):
                report = self.compare(STANDARD, standard_target(star=star), **SYMBOL_MODE)
                self.assertEqual(self.unresolved(report), ['Star'])
                self.assertEqual(self.matched_ids(report), ['sample-plus'])
        edge = "Image, 0x111, {{85.0, 10.0}, {20.0, 20.0}}, identifier: 'sample-star', label: 'Star'"
        report = self.compare((SAMPLE, edge, ADD_BUTTON, PLUS),
                              standard_target(star=[symbol('sample-star', 'Star', '[255,30][315,90]')]),
                              **SYMBOL_MODE)
        self.assertEqual(self.unresolved(report), ['Star'])
        background = window([
            node('Column', '[0,0][300,600]', [symbol('sample-star', 'Star', STAR_BOX)]),
            node('ModalPage', '[0,0][300,600]', standard_target(star=[]), id='sample-modal'),
        ])
        report = self.compare(STANDARD, None, raw_target=background, **SYMBOL_MODE)
        self.assertEqual(self.unresolved(report), ['Star'])
        self.assertEqual(self.matched_ids(report), ['sample-plus'])

    def test_parent_button_must_be_paired_and_contain_the_symbol(self):
        cases = {
            'icon exceeds parent bounds': (
                STANDARD, standard_target(plus=[symbol('sample-plus', 'Add', '[36,126][84,190]')]), ['Add']),
            'icon under a different paired button': (
                (*STANDARD, COPY_BUTTON), standard_target(plus=[], extra=[button(
                    'Copy Item', '[30,210][270,270]', [symbol('sample-plus', 'Add', '[36,216][84,264]')])]),
                ['Add']),
            'parent button is not paired': (
                STANDARD, [text('Sample', '[30,30][180,90]'), symbol('sample-star', 'Star', STAR_BOX),
                           button('Add Entry', '[30,120][270,180]', [symbol('sample-plus', 'Add', PLUS_BOX)])],
                ['Add', 'Add Item']),
            'icon is a sibling inside the button box': (
                STANDARD, standard_target(plus=[], extra=[symbol('sample-plus', 'Add', PLUS_BOX)]), ['Add']),
        }
        for name, (source, target, expected) in cases.items():
            with self.subTest(name):
                report = self.compare(source, target, **SYMBOL_MODE)
                self.assertEqual(report['verdict'], 'UNRESOLVED')
                self.assertEqual(self.unresolved(report), expected)
                self.assertEqual(report['findings'], [])

    def test_repeated_symbols_need_equal_counts_and_mutual_16pt_uniqueness(self):
        cases = {
            'paired group': ((100, 150), (300, 450), 'PASS', []),
            'fewer targets': ((100, 150), (300,), 'UNRESOLVED', ['Dot', 'Dot']),
            'more targets': ((100, 150), (300, 450, 540), 'UNRESOLVED', ['Dot', 'Dot']),
            'source sees two targets': ((100, 108), (300, 324), 'UNRESOLVED', ['Dot', 'Dot']),
            'two sources choose one target': ((100, 130), (345, 465), 'UNRESOLVED', ['Dot', 'Dot']),
            'paired group keeps 3 pt': ((100, 150), (309, 459), 'PASS', []),
            'paired group still fails 6 pt': ((100, 150), (318, 468), 'FAIL', []),
        }
        for name, (source_ys, target_ys, verdict, unresolved) in cases.items():
            with self.subTest(name):
                source = (SAMPLE, *(dot_line(0x120 + index, y) for index, y in enumerate(source_ys)))
                target = [text('Sample', '[30,30][180,90]'), *(dot(y) for y in target_ys)]
                report = self.compare(source, target, **SYMBOL_MODE)
                self.assertEqual(report['verdict'], verdict)
                self.assertEqual(self.unresolved(report), unresolved)
                if verdict == 'FAIL':
                    self.assertIn('vertical_position_drift', {item['code'] for item in report['findings']})

    def test_single_symbol_keeps_the_4pt_geometry_contract(self):
        moved = self.compare(STANDARD, standard_target(star=[symbol('sample-star', 'Star', '[210,48][270,108]')]),
                             **SYMBOL_MODE)
        self.assertEqual(moved['verdict'], 'FAIL')
        self.assertIn({'code': 'vertical_position_drift', 'labels': ['Star'], 'delta': 6.0}, moved['findings'])
        near = self.compare(STANDARD, standard_target(star=[symbol('sample-star', 'Star', '[210,39][270,99]')]),
                            **SYMBOL_MODE)
        self.assertEqual(near['verdict'], 'PASS')

    def test_tab_symbols_require_a_real_or_declared_tab_bar_and_paired_button(self):
        source = (SAMPLE, *TAB)
        accepted = {
            'declared tab bar id': (tab_bar(id='sample-tabs'), {'tab_bar_id': 'sample-tabs'}),
            'native TabBar': (tab_bar('TabBar'), {}),
        }
        for name, (bar, options) in accepted.items():
            with self.subTest(name):
                report = self.compare(source, [text('Sample', '[30,30][180,90]'), bar],
                                      audit_viewport=True, **SYMBOL_MODE, **options)
                self.assertEqual(report['verdict'], 'PASS')
                self.assertEqual(self.matched_ids(report), ['sample-home'])
        rejected = {
            'undeclared container': ([tab_bar()], {}),
            'different declared id': ([tab_bar(id='sample-tabs')], {'tab_bar_id': 'sample-other'}),
            'same-name symbol outside the bar': (
                [tab_bar(id='sample-tabs', icon=False), symbol('sample-home', 'house', '[54,546][96,588]')],
                {'tab_bar_id': 'sample-tabs'}),
        }
        for name, (bars, options) in rejected.items():
            with self.subTest(name):
                report = self.compare(source, [text('Sample', '[30,30][180,90]'), *bars],
                                      audit_viewport=True, **SYMBOL_MODE, **options)
                self.assertEqual(self.unresolved(report), ['house'])


    def test_swapped_labels_on_duplicate_id_are_unresolved(self):
        # Same identifier at two positions with different labels; if target descriptions
        # are swapped relative to source, the whole group must be rejected.
        src1 = "Image, 0x120, {{20.0, 100.0}, {10.0, 10.0}}, identifier: 'sample-dual', label: 'Alpha'"
        src2 = "Image, 0x121, {{20.0, 150.0}, {10.0, 10.0}}, identifier: 'sample-dual', label: 'Beta'"
        tgt_ok = [text('Sample', '[30,30][180,90]'),
                  symbol('sample-dual', 'Alpha', '[60,300][90,330]'),
                  symbol('sample-dual', 'Beta', '[60,450][90,480]')]
        report = self.compare((SAMPLE, src1, src2), tgt_ok, **SYMBOL_MODE)
        self.assertEqual(report['verdict'], 'PASS')
        tgt_swapped = [text('Sample', '[30,30][180,90]'),
                       symbol('sample-dual', 'Beta', '[60,300][90,330]'),
                       symbol('sample-dual', 'Alpha', '[60,450][90,480]')]
        report = self.compare((SAMPLE, src1, src2), tgt_swapped, **SYMBOL_MODE)
        self.assertEqual(report['verdict'], 'UNRESOLVED')
        self.assertEqual(self.unresolved(report), ['Alpha', 'Beta'])
    def test_navigation_selects_the_later_independent_container(self):
        source = (*HOST, *EDITOR)
        title = predicate({'text': 'Edit Item'})
        legacy = self.compare(source, editor_target(), observation=title)
        self.assertEqual(legacy['verdict'], 'UNRESOLVED')
        self.assertEqual(self.unresolved(legacy), ['Host row'])
        self.assertNotIn('approved_source_navigation', legacy)
        report = self.compare(source, editor_target(), observation=title, approved_source_navigation=True)
        self.assertEqual(report['verdict'], 'PASS')
        self.assertEqual((report['source_anchors'], report['matched_anchors']), (2, 2))
        binding = report['approved_source_navigation']
        self.assertEqual((binding['contract'], binding['identifier'], binding['binding']),
                         ('approved-ios-navigation-v1', 'Edit Item', 'present_text'))
        by_id = self.compare(source, editor_target(), observation=predicate({'id': 'sample-name'}),
                             approved_source_navigation=True)
        self.assertEqual(by_id['verdict'], 'PASS')
        self.assertEqual(by_id['approved_source_navigation']['binding'], 'control_id')

    def test_navigation_rejects_ambiguous_or_unapproved_bindings(self):
        title = predicate({'text': 'Edit Item'})
        nested = (*HOST, *('  ' + line for line in EDITOR))
        duplicate_id = (*HOST, *EDITOR,
                        "  StaticText, 0x154, {{10.0, 100.0}, {50.0, 20.0}}, identifier: 'sample-name', label: 'Name'")
        cases = {
            'title and id are not bound': ((*HOST, *EDITOR), editor_target(), predicate({'id': 'sample-editor'}), {}),
            'target has no active modal': ((*HOST, *EDITOR), editor_target('Column'), title, {}),
            'no earlier host navigation': (EDITOR, editor_target(), title, {}),
            'duplicate later title': ((*HOST, *EDITOR, *EDITOR), editor_target(), title, {}),
            'later navigation nested in the host': (nested, editor_target(), title, {}),
            'approved title is the earlier container': ((*EDITOR, *HOST), editor_target(), title, {}),
            'shared id is not unique': (duplicate_id, editor_target(), predicate({'id': 'sample-name'}), {}),
            'no approved observation': ((*HOST, *EDITOR), editor_target(), False, {}),
            'diagnostic mode': ((*HOST, *EDITOR), editor_target(), title,
                                {'diagnostic_surface': ('Edit Item', 'ModalPage')}),
        }
        for name, (source, target, observation, options) in cases.items():
            with self.subTest(name), self.assertRaisesRegex(ValueError, 'source navigation'):
                self.compare(source, target, observation=observation, approved_source_navigation=True, **options)


class GateReplayTests(SymbolFixture, unittest.TestCase):
    """The formal Stage1 comparison recomputes the whole report from the bound raw trees."""

    def gate(self, source_lines, target_children, *, observation=True, appearance='PASS', mutate=None, **options):
        spec = self.root / 'spec'
        spec.mkdir(exist_ok=True)
        png = b'\x89PNG\r\n\x1a\nsample'
        files = {'source.png': png, 'target.png': png,
                 'source.json': json.dumps({'debug_description': xcui(source_lines)}).encode(),
                 'target.json': json.dumps(window(target_children)).encode()}
        for name, raw in files.items():
            (spec / name).write_bytes(raw)
        pair = {'baseline': {'png_path': 'spec/source.png', 'png_sha256': sha256(png),
                             'ui_json_path': 'spec/source.json', 'ui_json_sha256': sha256(files['source.json'])}}
        if observation is not False:
            pair['target_observation'] = predicate() if observation is True else observation
        relationship = compare_relationships(self.root, pair, self.frame, spec / 'target.json',
                                             sha256(files['target.json']), **options)
        if mutate is not None:
            mutate(relationship)
        (spec / 'relationship.json').write_bytes(json_bytes(relationship))
        (spec / 'appearance.json').write_bytes(json_bytes({
            'comparison_id': 'sample:0', 'verdict': appearance,
            'ios_png_sha256': sha256(png), 'harmony_png_sha256': sha256(png)}))

        def ref(name):
            return {'path': name, 'sha256': sha256((spec / name).read_bytes())}
        observed = {'ios_png_sha256': sha256(png), 'ios_region_px': None, 'verdict': 'PASS',
                    'harmony_png': ref('target.png'), 'harmony_xml': ref('target.json'),
                    'appearance_report': ref('appearance.json'), 'relationship_report': ref('relationship.json')}
        return relationship, lambda: _comparison(self.root, pair, self.frame, observed)

    def test_gate_replays_symbol_mode_and_rejects_forged_symbol_fields(self):
        relationship, run = self.gate(STANDARD, standard_target(), **SYMBOL_MODE)
        self.assertEqual(relationship['verdict'], 'PASS')
        self.assertEqual(run(), 'PASS')
        forgeries = {
            'claim legacy mode': lambda value: value.pop('native_symbol_anchors'),
            'flag instead of evidence': lambda value: value.update(native_symbol_anchors=True),
            'changed identifier': lambda value: value['native_symbol_anchors']['matched'][0].update(
                identifier='sample-forged'),
        }
        for name, mutate in forgeries.items():
            with self.subTest(name):
                _, run = self.gate(STANDARD, standard_target(), mutate=mutate, **SYMBOL_MODE)
                with self.assertRaisesRegex(ValueError, 'does not match native tree replay'):
                    run()

    def test_gate_rejects_forged_pass_and_keeps_appearance_independent(self):
        conflict = standard_target(star=[symbol('sample-star', 'Heart', STAR_BOX)])
        relationship, run = self.gate(STANDARD, conflict, **SYMBOL_MODE)
        self.assertEqual(relationship['verdict'], 'UNRESOLVED')
        with self.assertRaisesRegex(ValueError, 'lacks matching appearance and relationship evidence'):
            run()

        def forge(value):
            value.update(verdict='PASS', unresolved=[], matched_anchors=value['source_anchors'])
        _, run = self.gate(STANDARD, conflict, mutate=forge, **SYMBOL_MODE)
        with self.assertRaisesRegex(ValueError, 'does not match native tree replay'):
            run()
        _, run = self.gate(STANDARD, standard_target(), appearance='FAIL', **SYMBOL_MODE)
        with self.assertRaisesRegex(ValueError, 'lacks matching appearance and relationship evidence'):
            run()

    def test_gate_replays_approved_navigation_and_legacy_reports(self):
        source, title = (*HOST, *EDITOR), predicate({'text': 'Edit Item'})
        relationship, run = self.gate(source, editor_target(), observation=title, approved_source_navigation=True)
        self.assertEqual(run(), 'PASS')
        forgeries = {
            'claim unscoped source': lambda value: value.pop('approved_source_navigation'),
            'changed binding': lambda value: value['approved_source_navigation'].update(binding='control_id'),
        }
        for name, mutate in forgeries.items():
            with self.subTest(name):
                _, run = self.gate(source, editor_target(), observation=title, mutate=mutate,
                                   approved_source_navigation=True)
                with self.assertRaisesRegex(ValueError, 'does not match native tree replay'):
                    run()
        legacy, run = self.gate((SAMPLE, ADD_BUTTON), [text('Sample', '[30,30][180,90]'),
                                                       button('Add Item', '[30,120][270,180]')], observation=False)
        self.assertEqual(run(), 'PASS')
        self.assertFalse({'native_symbol_anchors', 'approved_source_navigation'} & set(legacy))



class ReviewedNavigationBoundaryTests(SymbolFixture, unittest.TestCase):
    def test_source_navigation_rejects_foreign_and_duplicate_main_windows(self):
        title = predicate({'text': 'Edit Item'})
        for kind in ('Window', 'Window (Main)'):
            foreign = ("%s, 0x180, {{0.0, 0.0}, {100.0, 200.0}}" % kind,)
            source = (*HOST, *foreign, *('  '+line for line in EDITOR))
            with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, 'source navigation'):
                self.compare(source, editor_target(), observation=title, approved_source_navigation=True)

    def test_source_navigation_requires_identifiable_target_modal(self):
        for identity in (None,'   ',True):
            target = editor_target()
            target[1]['attributes'].pop('id')
            if identity is not None:target[1]['attributes']['id']=identity
            with self.subTest(identity=identity), self.assertRaisesRegex(ValueError, 'source navigation'):
                self.compare((*HOST,*EDITOR), target, observation=predicate({'text':'Edit Item'}),
                             approved_source_navigation=True)

    def test_source_navigation_rejects_blank_shared_control_labels(self):
        source = (*HOST, *(line.replace("label: 'Name'", "label: ''") for line in EDITOR))
        target = editor_target()
        target[1]['children'][1]['attributes']['text'] = ''
        with self.assertRaisesRegex(ValueError, 'source navigation'):
            self.compare(source,target,observation=predicate({'id':'sample-name'}),approved_source_navigation=True)

    def test_legacy_custom_tab_id_keeps_prior_ambiguity(self):
        source = (SAMPLE,*TAB[:2])
        target = [text('Sample','[30,30][180,90]'),tab_bar(id='sample-tabs',icon=False),
                  button('Home','[0,300][150,360]')]
        legacy = self.compare(source,target,native_control_roles=True,audit_viewport=True,tab_bar_id='sample-tabs')
        self.assertEqual(legacy['verdict'],'UNRESOLVED')
        self.assertEqual(legacy['matched_anchors'],1)
        strict = self.compare(source,target,audit_viewport=True,tab_bar_id='sample-tabs',**SYMBOL_MODE)
        self.assertEqual(strict['verdict'],'PASS')


class ReviewedTabButtonPairingTests(SymbolFixture, unittest.TestCase):
    def scene(self):
        source = (SAMPLE,"Button, 0x160, {{0.0, 100.0}, {50.0, 20.0}}, label: 'Home'",*TAB)
        target = [text('Sample','[30,30][180,90]'),button('Home','[0,300][150,360]'),tab_bar(id='sample-tabs')]
        return source,target

    def test_tab_and_ordinary_same_name_buttons_pair_only_in_opt_in_mode(self):
        source,target=self.scene()
        options={'audit_viewport':True,'tab_bar_id':'sample-tabs'}
        legacy=self.compare(source,target,native_control_roles=True,**options)
        self.assertEqual(legacy['verdict'],'UNRESOLVED')
        self.assertEqual(legacy['matched_anchors'],1)
        strict=self.compare(source,target,**SYMBOL_MODE,**options)
        self.assertEqual(strict['verdict'],'PASS')
        self.assertEqual(strict['matched_anchors'],4)
        self.assertEqual(self.matched_ids(strict),['sample-home'])

    def test_ambiguous_non_tab_buttons_are_not_resolved_by_position(self):
        source,target=self.scene()
        target.append(button('Home','[0,390][150,450]'))
        result=self.compare(source,target,**SYMBOL_MODE,audit_viewport=True,tab_bar_id='sample-tabs')
        self.assertEqual(result['verdict'],'UNRESOLVED')
        self.assertEqual(self.unresolved(result),['Home'])

    def test_wrong_declared_tab_bar_keeps_same_name_buttons_unresolved(self):
        source,target=self.scene()
        result=self.compare(source,target,**SYMBOL_MODE,audit_viewport=True,tab_bar_id='sample-other')
        self.assertEqual(result['verdict'],'UNRESOLVED')
        self.assertEqual(self.unresolved(result),['Home','Home','house'])

if __name__ == '__main__':
    unittest.main()
