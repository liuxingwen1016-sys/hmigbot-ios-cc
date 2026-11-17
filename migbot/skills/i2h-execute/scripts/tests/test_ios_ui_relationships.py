"""Native dump comparison regressions with two distinct viewport coordinate spaces."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.ios_ui_dispatch import sha256
from lib.ios_ui_relationships import audit_navigation_status_bar, compare_relationships


class IOSRelationshipsTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name).resolve()
        self.source = self.root / 'ios.json'
        self.target = self.root / 'harmony.json'
        self.frame = {'comparison_id': 'example:0', 'ios_region_px': None}
        self.tree = """Attributes: Application, 0x123, label: 'Sample'
Element subtree:
    Window (Main), 0x123, {{0.0, 0.0}, {100.0, 200.0}}
      StaticText, 0x124, {{10.0, 10.0}, {50.0, 20.0}}, label: 'Sample'
      Button, 0x125, {{10.0, 40.0}, {50.0, 20.0}}, label: 'Next'
        StaticText, 0x126, {{12.0, 45.0}, {20.0, 10.0}}, label: 'Next'
      StatusBar, 0x127, {{0.0, 0.0}, {100.0, 8.0}}
        StaticText, 0x128, {{3.0, 0.0}, {40.0, 8.0}}, label: 'Clock'
Query chain:
    StaticText, 0x129, {{10.0, 50.0}, {30.0, 8.0}}, label: 'Ignore'
"""

    def compare(self, children, **options):
        self.source.write_text(json.dumps({'debug_description': self.tree}))
        self.target.write_text(json.dumps({'attributes': {'bounds': '[0,0][300,600]'}, 'children': children}))
        pair = {'baseline': {'ui_json_path': self.source.name, 'ui_json_sha256': sha256(self.source.read_bytes())}}
        return compare_relationships(self.root, pair, self.frame, self.target, **options)

    def node(self, role, bounds, label='', children=()):
        return {'attributes': {'type': role, 'bounds': bounds, 'text': label}, 'children': list(children)}

    def test_debug_description_and_button_label_inside_custom_control(self):
        report = self.compare([
            self.node('Text', '[30,30][180,90]', 'Sample'),
            self.node('Button', '[30,120][180,180]', children=[self.node('Text', '[36,135][96,165]', 'Next')]),
        ])
        self.assertEqual(report['verdict'], 'PASS')
        self.assertEqual(report['matched_anchors'], 2)

    def test_foreground_diagnostic_excludes_behind_sheet_without_hiding_missing_surface(self):
        self.tree = self.tree.replace("Query chain:", """      Other, 0x130, {{0.0, 40.0}, {100.0, 160.0}}
        NavigationBar, 0x131, {{0.0, 40.0}, {100.0, 20.0}}, identifier: 'Tasting'
        StaticText, 0x132, {{10.0, 70.0}, {50.0, 20.0}}, label: 'Foreground control'
Query chain:""")
        sheet = self.node('SheetPage', '[0,120][300,600]', children=[
            self.node('Text', '[30,210][180,270]', 'Foreground control'),
        ])
        children = [self.node('Text', '[32,30][182,90]', 'Different background'), sheet]
        opts = {'diagnostic_surface': ('Tasting', 'SheetPage'), 'audit_viewport': True}
        report = self.compare(children, **opts)
        self.assertEqual(report['source_anchors'], 1)
        self.assertEqual(report['target_anchors'], 1)
        self.assertEqual(report['matched_anchors'], 1)
        self.assertEqual(report['diagnostic_surface']['ios_navigation_identifier'], 'Tasting')
        with self.assertRaisesRegex(ValueError, 'one visible HarmonyOS surface'):
            self.compare(children[:1], **opts)
        with self.assertRaisesRegex(ValueError, 'one visible HarmonyOS surface'):
            self.compare([*children, sheet], **opts)

    def test_native_clickable_text_and_accessibility_name(self):
        control = self.node('Text', '[30,120][180,180]')
        control['attributes'].update(clickable='true', accessibilityText='Next')
        children = [self.node('Text', '[30,30][180,90]', 'Sample'), control]
        self.assertEqual(self.compare(children)['verdict'], 'UNRESOLVED')
        report = self.compare(children, native_control_roles=True)
        self.assertEqual(report['verdict'], 'PASS')
        self.assertEqual(report['matched_anchors'], 2)
        control['attributes']['clickable'] = 'false'
        self.assertEqual(self.compare(children, native_control_roles=True)['verdict'], 'UNRESOLVED')

    def test_new_overlap_and_gap_are_retained(self):
        self.tree = self.tree.replace("StaticText, 0x124", "Button, 0x124")
        report = self.compare([
            self.node('Button', '[30,30][180,90]', 'Sample'),
            self.node('Button', '[30,66][180,126]', 'Next'),
        ])
        self.assertEqual(report['verdict'], 'FAIL')
        self.assertIn('new_overlap', {item['code'] for item in report['findings']})
        self.assertIn('gap_changed', {item['code'] for item in report['findings']})

    def test_presentation_overlap_audit_preserves_findings_and_distinguishes_surfaces(self):
        self.tree = self.tree.replace("StaticText, 0x124", "Button, 0x124")
        first = self.node('Button', '[30,30][180,90]', 'Sample')
        second = self.node('Button', '[30,66][180,126]', 'Next')
        sheet = self.node('SheetPage', '[0,10][300,600]', children=[second])
        baseline = self.compare([first, sheet])
        audit = self.compare([first, sheet], audit_presentation_overlap=True)
        overlaps = audit.pop('cross_presentation_overlaps')
        self.assertEqual(audit, baseline)
        self.assertEqual(len(overlaps), 1)
        self.assertEqual(overlaps[0]['target_presentation_paths'], [(), (1,)])
        self.assertEqual(overlaps[0]['labels'], ['Sample', 'Next'])
        same_surface = self.compare([self.node('SheetPage', '[0,10][300,600]', children=[first, second])],
                                    audit_presentation_overlap=True)
        self.assertEqual(same_surface['cross_presentation_overlaps'], [])
        self.assertEqual(same_surface['findings'], baseline['findings'])

    def test_stretched_text_preserves_its_leading_alignment(self):
        report = self.compare([
            self.node('Text', '[30,30][270,90]', 'Sample'),
            self.node('Button', '[30,120][180,180]', 'Next'),
        ])
        self.assertEqual(report['verdict'], 'PASS')

    def test_single_anchor_keeps_its_geometry_contract(self):
        self.tree = self.tree.replace("label: 'Sample'", "label: ''")
        report = self.compare([self.node('Button', '[30,120][180,180]', 'Next')])
        self.assertEqual(report['verdict'], 'PASS')
        self.assertEqual(report['matched_anchors'], 1)

    def test_duplicate_buttons_cannot_match_by_position_or_id(self):
        report = self.compare([
            self.node('Text', '[30,30][180,90]', 'Sample'),
            self.node('Button', '[30,120][180,180]', 'Next'),
            self.node('Button', '[30,250][180,310]', 'Next'),
        ])
        self.assertEqual(report['verdict'], 'UNRESOLVED')
        self.assertEqual(report['unresolved'][0]['candidate_count'], 2)

    def test_viewport_audit_distinguishes_absent_from_outside(self):
        report = self.compare([self.node('Button', '[30,580][180,640]', 'Next')], audit_viewport=True)
        self.assertEqual([(row['label'], row['code']) for row in report['viewport_findings']], [
            ('Sample', 'source_anchor_absent'), ('Next', 'source_anchor_outside_target_viewport'),
        ])
        self.assertNotIn('viewport_findings', self.compare([]))

    def test_viewport_audit_reports_clipped_controls_and_retains_legacy_output(self):
        text = self.node('Text', '[30,30][180,90]', 'Sample')
        control = self.node('Text', '[30,120][180,171]', 'Next')
        control['attributes'].update(origBounds='[30,120][180,180]', clickable='true')
        custom = self.node('Row', '[24,240][276,290]')
        custom['attributes']['id'] = 'floatingTabs'
        children = [text, control, custom]
        options = {'audit_viewport': True, 'native_control_roles': True, 'tab_bar_id': 'floatingTabs'}
        result = self.compare(children, **options)
        self.assertTrue(result['audit_control_clipping'])
        self.assertEqual(result['viewport_findings'], [{
            'code': 'target_control_clipped', 'label': 'Next', 'role': 'button',
            'target_box': (10.0, 40.0, 60.0, 57.0),
            'target_original_box': (10.0, 40.0, 60.0, 60.0),
        }])
        legacy = self.compare(children, **options, audit_control_clipping=False)
        self.assertNotIn('audit_control_clipping', legacy)
        self.assertEqual(legacy['viewport_findings'], [])
        self.assertEqual(result['verdict'], legacy['verdict'])
        duplicate = self.node('Button', '[30,190][180,230]', 'Next')
        self.assertEqual(self.compare([*children, duplicate], **options)['viewport_findings'], [])
        for original in ('[30,120][180,174]', '[35,120][180,180]', 'malformed'):
            control['attributes']['origBounds'] = original
            self.assertEqual(self.compare(children, **options)['viewport_findings'], [])

    def test_viewport_audit_reports_severely_reduced_text_frame(self):
        report = self.compare([
            self.node('Text', '[30,30][180,32]', 'Sample'),
            self.node('Button', '[30,120][180,180]', 'Next'),
        ], audit_viewport=True)
        self.assertEqual([row['code'] for row in report['viewport_findings']],
                         ['target_text_frame_less_than_half_source_height'])

    def test_status_bar_audit_distinguishes_clipping_overlap_and_unknown_geometry(self):
        back = self.node('BackButton', '[12,20][50,28]')
        back['attributes'].update(id='nativeBack', visible='true', origBounds='[12,4][50,28]')
        title = self.node('Text', '[80,7][220,33]', 'Detail')
        title['attributes'].update(id='nativeTitle', visible='true', origBounds='[80,7][220,33]')
        navigation = self.node('TitleBar', '[0,4][300,34]', children=(back, title))
        app = self.node('root', '[0,20][300,600]', children=(navigation,))
        app['attributes'].update(focused='true', pagePath='Index', displayId='0')
        bar = self.node('__Common__', '[0,0][300,19]')
        bar['attributes'].update(id='StatusBarBox', visible='true', displayId='0')
        system = self.node('WindowScene', '[0,0][300,19]', children=(bar,))
        system['attributes']['bundleName'] = 'com.ohos.sceneboard'
        tree = {'children': [app, system]}

        report = self.compare(tree['children'], audit_status_bar=True)
        audit = report['navigation_status_bar']
        self.assertEqual(audit['status'], 'CLIPPED')
        self.assertEqual([(row['id'], row['status']) for row in audit['controls']],
                         [('nativeBack', 'CLIPPED'), ('nativeTitle', 'INTERSECTS')])
        self.assertNotIn('navigation_status_bar', self.compare(tree['children']))
        self.assertEqual(report['verdict'], self.compare(tree['children'])['verdict'])

        back['attributes'].update(bounds='[12,21][50,60]', origBounds='[12,21][50,60]')
        app['children'] = [back]
        self.assertEqual(audit_navigation_status_bar(tree, ['nativeBack'])['status'], 'CLEAR')
        self.assertEqual(audit_navigation_status_bar(tree, ['missing'])['missing_control_ids'], ['missing'])
        self.assertEqual(audit_navigation_status_bar(tree)['status'], 'UNAVAILABLE')
        back['attributes'].pop('origBounds')
        self.assertEqual(audit_navigation_status_bar(tree, ['nativeBack'])['status'], 'UNAVAILABLE')
        bar['attributes']['displayId'] = '1'
        self.assertEqual(audit_navigation_status_bar(tree, ['nativeBack'])['reason'],
                         'status_bar_bounds_missing_or_ambiguous')

    def test_viewport_audit_reports_content_overlap_with_visible_tab_bar(self):
        bar = self.node('TabBar', '[0,150][300,220]')
        bar['attributes']['visible'] = 'true'
        report = self.compare([
            self.node('Text', '[30,30][180,90]', 'Sample'),
            self.node('Button', '[30,120][180,180]', 'Next'),
            bar,
        ], audit_viewport=True)
        self.assertTrue(report['audit_viewport'])
        self.assertEqual(report['verdict'], 'PASS')
        self.assertEqual(report['viewport_findings'], [
            {'code': 'target_anchor_overlaps_tab_bar', 'role': 'button',
             'label': 'Next', 'overlap_height': 10.0},
        ])

    def test_declared_capsule_checks_content_overlap_and_excludes_own_children(self):
        self.tree = self.tree.replace('      StatusBar,', """      TabBar, 0x132, {{0.0, 50.0}, {100.0, 30.0}}
        Button, 0x133, {{61.0, 52.0}, {24.0, 20.0}}, label: 'Library'
      StatusBar,""")
        capsule = self.node('Row', '[24,150][276,240]', children=[
            self.node('Button', '[183,156][255,216]', 'Library'),
        ])
        capsule['attributes'].update(id='floatingTabs', visible='true')
        children = [
            self.node('Text', '[30,30][180,90]', 'Sample'),
            self.node('Button', '[30,120][180,180]', 'Next'),
            capsule,
        ]
        options = {'audit_viewport': True, 'tab_bar_id': 'floatingTabs'}
        report = self.compare(children, **options)
        self.assertEqual(report['verdict'], self.compare(children)['verdict'])
        self.assertEqual(report['custom_tab_bar_bounds'], (24, 150, 276, 240))
        self.assertEqual(report['viewport_findings'], [
            {'code': 'target_anchor_overlaps_tab_bar', 'role': 'button',
             'label': 'Next', 'overlap_height': 10.0},
        ])
        with self.assertRaisesRegex(ValueError, 'multiple visible'):
            self.compare([*children, capsule], **options)
        self.assertIsNone(self.compare(children[:-1], **options)['custom_tab_bar_bounds'])

    def test_presentation_audit_excludes_covered_bar_but_not_partially_covered_bar(self):
        capsule = self.node('Row', '[24,150][276,240]')
        capsule['attributes'].update(id='floatingTabs', visible='true')
        content = self.node('Column', '[0,0][300,600]', children=[capsule])
        action = self.node('Button', '[30,120][180,180]', 'Next')
        sheet = self.node('SheetPage', '[0,100][300,600]', children=[action])
        wrapper = self.node('SheetWrapper', '[0,0][300,600]', children=[sheet])
        for layer in (sheet, wrapper):
            layer['attributes']['visible'] = 'true'
        opts = {'audit_viewport': True, 'tab_bar_id': 'floatingTabs', 'respect_presentation': True}
        report = self.compare([content, wrapper], **opts)
        self.assertEqual(report['custom_tab_bar_bounds'], (24, 150, 276, 240))
        self.assertEqual(report['effective_tab_bar_bounds'], [])
        self.assertNotIn('target_anchor_overlaps_tab_bar', {x['code'] for x in report['viewport_findings']})
        sheet['attributes']['bounds'] = '[0,170][300,600]'
        partial = self.compare([content, wrapper], **opts)
        self.assertEqual(partial['effective_tab_bar_bounds'], [(24, 150, 276, 240)])
        self.assertIn('target_anchor_overlaps_tab_bar', {x['code'] for x in partial['viewport_findings']})
        self.assertEqual(partial['verdict'], report['verdict'])


if __name__ == '__main__':
    unittest.main()
