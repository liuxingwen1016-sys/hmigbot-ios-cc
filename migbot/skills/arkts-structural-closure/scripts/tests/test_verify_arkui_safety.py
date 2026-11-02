# -*- coding: utf-8 -*-
"""verify_arkui_safety regressions for hit-testing and route-root rules.

HITTEST_BLOCK_INTERACTIVE anchors the AntennaPod dialog incident (2026-09): dialog
panels carrying `.hitTestBehavior(HitTestMode.Block)` made every option, Cancel and
OK button dead, because Block also blocks the node's own descendants.
NAV_NESTED_DESTINATION / NAV_CONDITIONAL_ROOT anchor the same run: a visual-fix round
gave tab pages an `if (this.embedded)` build root, then wrapped every pageMap branch
in an outer NavDestination, which lost route parameters on every pushed page.

Run: python3 tests/test_verify_arkui_safety.py   (any cwd)
"""
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))
import verify_arkui_safety  # noqa: E402


def analyze(files):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for rel, text in files.items():
            path = root / 'entry/src/main/ets' / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding='utf-8')
        return verify_arkui_safety.analyze(root)


def rules(report, prefix=''):
    return [(f['rule_id'], f['severity']) for f in report['findings'] if f['rule_id'].startswith(prefix)]


def dialog(mode, child):
    return f"""
@ComponentV2
export struct ChoiceDialog {{
  build() {{
    Column() {{
      Text('title')
      {child}
    }}
    .width('80%')
    .hitTestBehavior({mode})
  }}
}}
"""


class HitTestBlockTest(unittest.TestCase):
    def test_block_over_button_fails(self):
        r = analyze({'pages/A.ets': dialog('HitTestMode.Block', "Button('OK').onClick(() => {})")})
        self.assertEqual(rules(r, 'HITTEST'), [('HITTEST_BLOCK_INTERACTIVE', 'FAIL')])
        f = r['findings'][0]
        self.assertEqual(f['evidence'], '. hitTestBehavior ( HitTestMode . Block )')
        self.assertEqual(f['owner_component'], 'Column')

    def test_default_over_button_passes(self):
        r = analyze({'pages/A.ets': dialog('HitTestMode.Default', "Button('OK')")})
        self.assertEqual(rules(r, 'HITTEST'), [])

    def test_block_over_select_event_fails(self):
        r = analyze({'pages/A.ets': dialog('HitTestMode.Block', "Text('x').onSelect(() => {})")})
        self.assertEqual(rules(r, 'HITTEST'), [('HITTEST_BLOCK_INTERACTIVE', 'FAIL')])
        r = analyze({'pages/A.ets': dialog('HitTestMode.Block', "Select([])")})
        self.assertEqual(rules(r, 'HITTEST'), [('HITTEST_BLOCK_INTERACTIVE', 'FAIL')])

    def test_block_over_text_input_fails(self):
        r = analyze({'pages/A.ets': dialog('HitTestMode.Block', "TextInput({ text: '' })")})
        self.assertEqual(rules(r, 'HITTEST'), [('HITTEST_BLOCK_INTERACTIVE', 'FAIL')])

    def test_block_over_imported_custom_component_fails(self):
        option = """
@ComponentV2
export struct OptionRow {
  build() {
    Row() { Radio({ value: 'a', group: 'g' }) }
  }
}
"""
        page = "import { OptionRow } from '../components/OptionRow'\n" + dialog('HitTestMode.Block', 'OptionRow()')
        r = analyze({'pages/A.ets': page, 'components/OptionRow.ets': option})
        self.assertEqual(rules(r, 'HITTEST'), [('HITTEST_BLOCK_INTERACTIVE', 'FAIL')])
        self.assertIn('OptionRow', r['findings'][0]['interactive_evidence'])

    def test_block_over_builder_method_fails(self):
        page = """
@ComponentV2
export struct A {
  @Builder
  entryRow() {
    Row() { Text('x') }.onClick(() => {})
  }
  build() {
    Column() { this.entryRow() }
    .hitTestBehavior(HitTestMode.Block)
  }
}
"""
        r = analyze({'pages/A.ets': page})
        self.assertEqual(rules(r, 'HITTEST'), [('HITTEST_BLOCK_INTERACTIVE', 'FAIL')])

    def test_block_without_interactive_descendants_passes(self):
        r = analyze({'pages/A.ets': dialog('HitTestMode.Block', "LoadingProgress()")})
        self.assertEqual(rules(r, 'HITTEST'), [])

    def test_block_leaf_with_own_click_passes(self):
        page = """
@ComponentV2
export struct A {
  build() {
    Stack() {
      Column().width('100%').height('100%').hitTestBehavior(HitTestMode.Block).onClick(() => {})
    }
  }
}
"""
        self.assertEqual(rules(analyze({'pages/A.ets': page}), 'HITTEST'), [])

    def test_conditional_block_warns_not_fails(self):
        r = analyze({'pages/A.ets': dialog('this.visible ? HitTestMode.Block : HitTestMode.None', "Button('OK')")})
        self.assertEqual(rules(r, 'HITTEST'), [('HITTEST_BLOCK_CONDITIONAL_UNKNOWN', 'WARN')])
        self.assertTrue(r['passed'])

    def test_block_in_comment_or_string_ignored(self):
        page = """
@ComponentV2
export struct A {
  build() {
    Column() {
      // .hitTestBehavior(HitTestMode.Block)
      Text('.hitTestBehavior(HitTestMode.Block)')
      Button('OK')
    }
  }
}
"""
        self.assertEqual(rules(analyze({'pages/A.ets': page}), 'HITTEST'), [])

    def test_one_finding_per_blocker(self):
        many = '\n'.join("Row() { Text('o').onClick(() => {}) }" for _ in range(8)) + "\nButton('Cancel')"
        r = analyze({'pages/A.ets': dialog('HitTestMode.Block', many)})
        self.assertEqual(len(rules(r, 'HITTEST')), 1)

    def test_id_stable_when_subtree_changes(self):
        a = analyze({'pages/A.ets': dialog('HitTestMode.Block', "Button('OK')")})
        b = analyze({'pages/A.ets': dialog('HitTestMode.Block', "Text('added')\n      Button('OK').margin(4)")})
        self.assertEqual([f['id'] for f in a['findings']], [f['id'] for f in b['findings']])


ENTRY = """
{imports}
@Entry
@ComponentV2
struct EntryPage {{
  @Provider('navPathStack') navPathStack: NavPathStack = new NavPathStack()
  @Builder
  pageMap(name: string) {{
{branches}
  }}
  build() {{
    Navigation(this.navPathStack) {{ Text('home') }}
    .navDestination(this.pageMap)
  }}
}}
"""

PAGE = """
@ComponentV2
export struct FeedPage {
  build() {
    NavDestination() { Text('feed') }
    .onReady((ctx: NavDestinationContext) => {})
  }
}
"""

CONDITIONAL_PAGE = """
@ComponentV2
export struct FeedPage {
  @Param embedded: boolean = false
  build() {
    if (this.embedded) {
      %s
    } else {
      NavDestination() { Text('feed') }
    }
  }
}
"""

SPLIT = """
@ComponentV2
export struct FeedContent {
  @Param feedId: number = 0
  build() { Column() { Text('feed') } }
}

@ComponentV2
export struct FeedPage {
  @Local ready: boolean = false
  build() {
    NavDestination() {
      if (this.ready) {
        FeedContent({ feedId: 1 })
      }
    }
    .onReady((ctx: NavDestinationContext) => { this.ready = true })
  }
}
"""


def entry(branches, imports="import { FeedPage } from './FeedPage'"):
    return ENTRY.format(imports=imports, branches=branches)


class RouteRootTest(unittest.TestCase):
    def nav(self, files):
        return rules(analyze(files), 'NAV')

    def test_outer_wrapper_over_page_destination_is_nested(self):
        wrapped = "    NavDestination() {\n      if (name === 'FeedPage') { FeedPage() }\n    }"
        got = self.nav({'pages/EntryPage.ets': entry(wrapped), 'pages/FeedPage.ets': PAGE})
        self.assertEqual(got, [('NAV_NESTED_DESTINATION', 'FAIL')])

    def test_branch_returning_page_passes(self):
        got = self.nav({'pages/EntryPage.ets': entry("    if (name === 'FeedPage') { FeedPage() }"),
                        'pages/FeedPage.ets': PAGE})
        self.assertEqual(got, [])

    def test_embedded_switch_to_content_is_conditional_root(self):
        page = CONDITIONAL_PAGE % "Column() { Text('tab') }"
        got = self.nav({'pages/EntryPage.ets': entry("    if (name === 'FeedPage') { FeedPage({ embedded: true }) }"),
                        'pages/FeedPage.ets': page})
        self.assertEqual(got, [('NAV_CONDITIONAL_ROOT', 'FAIL')])

    def test_builder_mixed_with_destination_is_conditional_root(self):
        page = (CONDITIONAL_PAGE % "this.pageContent()").replace(
            "  build() {", "  @Builder\n  pageContent() { Column() { Text('tab') } }\n  build() {", 1)
        got = self.nav({'pages/EntryPage.ets': entry("    if (name === 'FeedPage') { FeedPage() }"),
                        'pages/FeedPage.ets': page})
        self.assertEqual(got, [('NAV_CONDITIONAL_ROOT', 'FAIL')])

    def test_content_page_split_passes(self):
        got = self.nav({'pages/EntryPage.ets': entry("    if (name === 'FeedPage') { FeedPage() }"),
                        'pages/FeedPage.ets': SPLIT})
        self.assertEqual(got, [])

    def test_branch_owned_inline_destination_passes(self):
        inline = "    if (name === 'FeedContent') {\n      NavDestination() { FeedContent() }\n    }"
        got = self.nav({'pages/EntryPage.ets': entry(inline, "import { FeedContent } from './FeedPage'"),
                        'pages/FeedPage.ets': SPLIT})
        self.assertEqual(got, [])

    def test_unresolvable_dynamic_root_warns(self):
        dyn = "    if (name === 'X') { this.routes.get(name)() }"
        got = self.nav({'pages/EntryPage.ets': entry(dyn, '')})
        self.assertTrue(got and all(sev == 'WARN' for _, sev in got), got)


class TokenizerTest(unittest.TestCase):
    """gpt1030_2 FileImportService.ets:214（2026-10-18）：合法正则里的引号被当成字符串开头，报「不配对」假 FAIL。"""

    def test_quote_inside_regex_literal_does_not_break_pairing(self):
        src = """export class SavePort {
  save(name: string): string {
    const safe = [name.replace(/[\\/:*?"<>|]/g, '_')]
    const other = (name.match(/["']/) ?? [])
    return safe[0] + other.length
  }
}
"""
        report = analyze({'services/SavePort.ets': src})
        self.assertEqual(report['errors'], [])

    def test_division_is_not_a_regex(self):
        src = "export function half(a: number, b: number): number { return (a / 2) + (b / 2) }\n"
        self.assertEqual(analyze({'utils/Half.ets': src})['errors'], [])

    def test_unparseable_file_reports_analysis_error_rule(self):
        report = analyze({'pages/Broken.ets': '@Component\nstruct Broken { build() { Column() { }\n'})
        self.assertEqual([e['rule_id'] for e in report['errors']], ['ANALYSIS_ERROR'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
