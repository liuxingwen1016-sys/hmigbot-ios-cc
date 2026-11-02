import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zlib

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
from resource_semantics import parse_drawable, parse_font, choose_level, choose_state, linear_trim, android_string

NS = 'xmlns:android="http://schemas.android.com/apk/res/android"'


class ResourceSemanticsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.res = self.root / 'res'; self.res.mkdir(); self.out = self.root / 'out'
    def tearDown(self): self.temp.cleanup()
    def put(self, name, text):
        path = self.res / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(text); return path
    def test_level_order_overlap_and_no_match(self):
        desc = parse_drawable(ET.fromstring(f'<level-list {NS}><item android:minLevel="2" android:maxLevel="5" android:drawable="@drawable/a"/><item android:maxLevel="10" android:drawable="@drawable/b"/></level-list>'))
        self.assertEqual(choose_level(desc['items'], 3), '@drawable/a')
        self.assertEqual(choose_level(desc['items'], 0), '@drawable/b')
        self.assertIsNone(choose_level(desc['items'], 11))
        with self.assertRaises(ValueError): choose_level(desc['items'], '3')
    def test_selector_nested_false_and_missing_default(self):
        desc = parse_drawable(ET.fromstring(f'<selector {NS}><item android:state_checked="true" android:state_enabled="false"><shape><solid android:color="#ff0000"/></shape></item></selector>'))
        self.assertEqual(choose_state(desc['items'], {'checked': True, 'enabled': False})['kind'], 'shape')
        self.assertIsNone(choose_state(desc['items'], {'checked': True, 'enabled': True}))
    def test_shape_gradient_padding_dimensions_and_bounds(self):
        desc = parse_drawable(ET.fromstring(f'<shape {NS}><gradient android:type="linear" android:angle="90" android:startColor="#ff0000" android:endColor="#00ff00"/><padding android:left="4dp" android:top="2px"/><corners android:radius="6dp"/></shape>'))
        self.assertEqual(desc['bounds'], 'consumer_component_size')
        self.assertEqual(desc['properties']['padding']['left']['unit'], 'vp')
        self.assertEqual(desc['properties']['padding']['top']['unit'], 'px')
        self.assertEqual(desc['properties']['gradient']['angle'], 90)
        with self.assertRaises(ValueError): parse_drawable(ET.fromstring(f'<shape {NS}><gradient android:angle="42"/></shape>'))
    def test_compositions_keep_order_nested_values_and_runtime_inputs(self):
        xml = f'<layer-list {NS}><item android:left="2dp"><inset android:insetTop="3dp"><clip android:drawable="@drawable/a" android:clipOrientation="vertical"/></inset></item><item android:drawable="@drawable/b"/></layer-list>'
        desc = parse_drawable(ET.fromstring(xml))
        self.assertEqual(desc['items'][0]['placement']['left']['value'], 2)
        self.assertEqual(desc['items'][0]['value']['value']['kind'], 'clip')
        self.assertEqual(desc['items'][1]['value'], '@drawable/b')
        icon = parse_drawable(ET.fromstring(f'<adaptive-icon {NS}><background android:drawable="@color/bg"/><foreground android:drawable="@drawable/fg"/><monochrome android:drawable="@drawable/mono"/></adaptive-icon>'))
        self.assertEqual([r['role'] for r in icon['items']], ['background', 'foreground', 'monochrome'])
    def test_font_family_weight_style_and_download_provider_not_fake_local(self):
        family = parse_font(ET.fromstring(f'<font-family {NS}><font android:font="@font/body" android:fontWeight="700" android:fontStyle="italic"/></font-family>'))
        self.assertEqual(family['fonts'][0]['weight'], 700)
        provider = parse_font(ET.fromstring(f'<font-family {NS} android:fontProviderAuthority="fonts.example" android:fontProviderQuery="q"/>'))
        self.assertEqual(provider['kind'], 'downloadable_font'); self.assertIsNone(provider['local_file'])
    def test_ripple_and_frame_animation_lifecycle_not_static_pass(self):
        ripple = parse_drawable(ET.fromstring(f'<ripple {NS} android:color="#33000000"><item android:drawable="@drawable/bg"/></ripple>'))
        self.assertEqual(ripple['termination'], 'release_or_cancel')
        frames = parse_drawable(ET.fromstring(f'<animation-list {NS} android:oneshot="true"><item android:duration="10" android:drawable="@drawable/a"/><item android:duration="20" android:drawable="@drawable/b"/></animation-list>'))
        self.assertEqual(frames['duration_ms'], 30); self.assertTrue(frames['oneshot']); self.assertTrue(frames['consumer_required'])
    def test_exact_linear_trim_wrap_and_curve_boundary(self):
        self.assertEqual(linear_trim('M0,0 L10,0 L10,10', .25, .75, 0), 'M5,0 L10,0 L10,5')
        self.assertEqual(linear_trim('M0,0 L10,0', .75, .25, 0), 'M7.5,0 L10,0 M0,0 L2.5,0')
        with self.assertRaisesRegex(ValueError, 'curved'): linear_trim('M0,0 C1,2 3,4 5,6', 0, .5, 0)







class AndroidStringTest(unittest.TestCase):
    def test_surrogate_pair_and_escaped_whitespace(self):
        node = ET.fromstring(r'<string name="x">Hello \uD83D\uDE00\n</string>')
        self.assertEqual(android_string(node), 'Hello 😀\\n'.replace('\\n', '\n'))

if __name__=='__main__': unittest.main()

class GradientNumericAngleTest(unittest.TestCase):
    def test_integer_valued_float_and_reject_fraction_nan(self):
        for value, expected in [('270.0', 270), ('180.0', 180), ('-45.0', 315)]:
            parsed = parse_drawable(ET.fromstring('<shape><gradient angle="' + value + '" startColor="#000000" endColor="#ffffff"/></shape>'))
            self.assertEqual(parsed['properties']['gradient']['angle'], expected)
        for value in ('nan', 'inf', '45.5', '44.0'):
            with self.assertRaises(ValueError):
                parse_drawable(ET.fromstring('<shape><gradient angle="' + value + '"/></shape>'))
