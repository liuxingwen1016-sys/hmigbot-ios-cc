import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ref_graph_lib import EtsRefGraph
from verify_slice_wiring import _check_single_ip


class C2Regression(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.ets = self.root / 'entry/src/main/ets/pages'
        self.ets.mkdir(parents=True)
        self.page = self.ets / 'MainPage.ets'
        self.page.write_text("export struct MainPage { cityTab() {} build() {} }")

    def check(self, target, handler='MainPage.cityTab'):
        ip = SimpleNamespace(description=target, target_class=target,
                             handler_local='cityTab', handler_text=handler,
                             target_text=target)
        return _check_single_ip(ip, 'ip1', EtsRefGraph(self.root).build(), self.root)

    def test_descriptive_nouns_but_real_missing_types_still_fail(self):
        self.assertEqual(self.check('Tab')['status'], 'PASS')
        self.assertEqual(self.check('Draw')['status'], 'PASS')
        self.assertEqual(self.check('MissingService')['status'], 'FAIL')
        (self.ets / 'Tab.ets').write_text('export class Tab {}')
        self.assertEqual(self.check('Tab')['status'], 'FAIL')

    def test_route_needs_mounted_registration_to_render_target(self):
        (self.ets / 'VipPage.ets').write_text('export struct VipPage {}')
        caller = """import { VipPage } from './VipPage';
export struct MainPage {
 cityTab() { this.stack.pushPathByName('vip', {}); }
 @Builder pageMap(name: string) { if (name === 'vip') { VipPage() } }
 build() { Navigation(this.stack) {}.navDestination(this.pageMap) }
}"""
        self.page.write_text(caller)
        self.assertEqual(self.check('VipPage')['status'], 'PASS')
        self.page.write_text(caller.replace('.navDestination(this.pageMap)', ''))
        self.assertEqual(self.check('VipPage')['status'], 'FAIL')

    def test_route_string_alone_does_not_silence_missing_target(self):
        self.page.write_text("export struct MainPage { cityTab() { this.stack.pushPathByName('MissingService', {}); } }")
        self.assertEqual(self.check('MissingService')['status'], 'FAIL')

    def test_unrelated_stack_or_file_does_not_prove_route(self):
        (self.ets / 'VipPage.ets').write_text('export struct VipPage {}')
        caller = """import { VipPage } from './VipPage';
export struct MainPage {
 cityTab() { this.otherStack.pushPathByName('vip', {}); }
 @Builder pageMap(name: string) { if (name === 'vip') { VipPage() } }
 build() { Navigation(this.stack) {}.navDestination(this.pageMap) }
}"""
        self.page.write_text(caller)
        self.assertEqual(self.check('VipPage')['status'], 'FAIL')
        self.page.write_text("export struct MainPage { cityTab() { this.stack.pushPathByName('vip', {}); } }")
        (self.ets / 'OtherPage.ets').write_text(caller.replace('this.otherStack', 'this.stack'))
        self.assertEqual(self.check('VipPage')['status'], 'FAIL')

    def test_unmounted_dispatcher_cannot_supply_constructor_evidence(self):
        (self.ets / 'VipPage.ets').write_text('export class VipPage {}')
        self.page.write_text("""import { VipPage } from './VipPage';
export struct MainPage {
 cityTab() { this.stack.pushPathByName('vip', {}); }
 @Builder pageMap(name: string) { if (name === 'vip') { const page: VipPage = new VipPage(); } }
 build() { Navigation(this.stack) {} }
}""")
        self.assertEqual(self.check('VipPage')['status'], 'FAIL')

    def test_shared_instance_remains_valid_alongside_navigation(self):
        (self.ets / 'WeatherService.ets').write_text('export class WeatherService { refresh() {} }')
        (self.ets / 'AppAssembly.ets').write_text("""import { WeatherService } from './WeatherService';
export class AppAssembly {
 static shared: AppAssembly = new AppAssembly();
 weather: WeatherService = new WeatherService();
}""")
        self.page.write_text("""import { AppAssembly } from './AppAssembly';
export struct MainPage {
 cityTab() { AppAssembly.shared.weather.refresh(); this.stack.pushPathByName('vip', {}); }
 build() { Column() {} }
}""")
        self.assertEqual(self.check('WeatherService')['status'], 'PASS')
