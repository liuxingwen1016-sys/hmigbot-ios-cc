# -*- coding: utf-8 -*-
"""ROUTE_PARAM_KEY_MISMATCH (verify_arkui_safety): caller param keys vs destination reads.

Anchors gpt1030_2 (2026-10-18): CreateOutLinePage pushed ChoicePPTTemplatePage with
`{ outlineData, query, from }`, the destination read `params?.pptOutLineData`; the cast
compiled, the read was always undefined, and tapping any template did nothing.

Run: python3 tests/test_route_param_keys.py   (any cwd)
"""
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))
import verify_arkui_safety  # noqa: E402

DEST = """
interface ChoiceParam { pptOutLineData?: Object; query?: string; from?: string }
@ComponentV2
export struct ChoicePage {
  @Local outline: Object | null = null
  build() {
    NavDestination() { Text('x') }
    .onReady((context: NavDestinationContext) => {
      const params = context.pathInfo.param as ChoiceParam | undefined
      this.outline = params?.pptOutLineData ?? null
      const q: string = params?.query ?? ''
    })
  }
}
"""

MAP = """
import { ChoicePage } from './ChoicePage'
@Builder
export function pageMap(name: string) {
  if (name === 'ChoicePage') { ChoicePage() }
}
"""


def caller(body):
    return f"""
@ComponentV2
export struct OutlinePage {{
  navPathStack: NavPathStack = new NavPathStack()
  private next(data: Object): void {{
{body}
  }}
  build() {{ NavDestination() {{ Text('y') }} }}
}}
"""


def analyze(files):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for rel, text in files.items():
            path = root / 'entry/src/main/ets/pages' / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding='utf-8')
        report = verify_arkui_safety.analyze(root)
        return [(f['rule_id'], f['severity'], f.get('symbol')) for f in report['findings']
                if f['rule_id'] == 'ROUTE_PARAM_KEY_MISMATCH']


class RouteParamKeys(unittest.TestCase):
    def test_renamed_key_in_local_variable_is_fail(self):
        body = """    const params: Record<string, Object> = JSON.parse(JSON.stringify({
      outlineData: data, query: 'q'
    })) as Record<string, Object>
    if (data === null) {
      return
    } else {
      this.navPathStack.pushPathByName('ChoicePage', params)
    }"""
        self.assertEqual(analyze({'ChoicePage.ets': DEST, 'Map.ets': MAP, 'OutlinePage.ets': caller(body)}),
                         [('ROUTE_PARAM_KEY_MISMATCH', 'FAIL', 'ChoicePage')])

    def test_matching_keys_pass(self):
        body = "    this.navPathStack.pushPathByName('ChoicePage', { pptOutLineData: data, query: 'q' })"
        self.assertEqual(analyze({'ChoicePage.ets': DEST, 'Map.ets': MAP, 'OutlinePage.ets': caller(body)}), [])

    def test_missing_optional_key_without_unread_is_warn(self):
        body = "    this.navPathStack.pushPathByName('ChoicePage', { query: 'q' })"
        self.assertEqual(analyze({'ChoicePage.ets': DEST, 'Map.ets': MAP, 'OutlinePage.ets': caller(body)}),
                         [('ROUTE_PARAM_KEY_MISMATCH', 'WARN', 'ChoicePage')])

    def test_unresolvable_caller_is_skipped(self):
        body = "    this.navPathStack.pushPathByName('ChoicePage', this.buildParams(data))"
        self.assertEqual(analyze({'ChoicePage.ets': DEST, 'Map.ets': MAP, 'OutlinePage.ets': caller(body)}), [])

    def test_instanceof_destination_is_skipped(self):
        dest = DEST.replace("this.outline = params?.pptOutLineData ?? null",
                            "if (params instanceof Object) { this.outline = params.pptOutLineData ?? null }")
        body = "    this.navPathStack.pushPathByName('ChoicePage', { outlineData: data })"
        self.assertEqual(analyze({'ChoicePage.ets': dest, 'Map.ets': MAP, 'OutlinePage.ets': caller(body)}), [])

    def test_class_instance_caller_uses_declared_fields(self):
        cls = "export class ChoiceArgs { pptOutLineData: Object | null = null\n  query: string = '' }\n"
        body = "    const a = new ChoiceArgs()\n    a.pptOutLineData = data\n    this.navPathStack.pushPathByName('ChoicePage', a)"
        self.assertEqual(analyze({'ChoicePage.ets': DEST, 'Map.ets': MAP, 'Args.ets': cls,
                                  'OutlinePage.ets': caller(body)}), [])

    def test_inherited_fields_count_as_provided(self):
        # 1018 复查 M5：参数类继承来的字段也算调用方给了
        cls = ("export class BaseArgs { from: string = '' }\n"
               "export class ChoiceArgs extends BaseArgs { pptOutLineData: Object | null = null\n  query: string = '' }\n")
        dest = DEST.replace("const q: string = params?.query ?? ''", "const q: string = params?.query ?? ''\n      const f = params?.from")
        dest = dest.replace("query?: string; from?: string }", "query?: string; from?: string }")
        body = "    const a = new ChoiceArgs()\n    this.navPathStack.pushPathByName('ChoicePage', a)"
        self.assertEqual(analyze({'ChoicePage.ets': dest, 'Map.ets': MAP, 'Args.ets': cls, 'OutlinePage.ets': caller(body)}), [])

    def test_parent_outside_project_is_skipped(self):
        cls = "export class ChoiceArgs extends SdkArgs { query: string = '' }\n"
        body = "    this.navPathStack.pushPathByName('ChoicePage', new ChoiceArgs())"
        self.assertEqual(analyze({'ChoicePage.ets': DEST, 'Map.ets': MAP, 'Args.ets': cls, 'OutlinePage.ets': caller(body)}), [])

    def test_push_path_info_form(self):
        body = "    this.navPathStack.pushPath({ name: 'ChoicePage', param: { outlineData: data } })"
        self.assertEqual(analyze({'ChoicePage.ets': DEST, 'Map.ets': MAP, 'OutlinePage.ets': caller(body)}),
                         [('ROUTE_PARAM_KEY_MISMATCH', 'FAIL', 'ChoicePage')])


if __name__ == '__main__':
    unittest.main()
