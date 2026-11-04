#!/usr/bin/env python3
"""layout_dims_gate.py：源布局写死的 dp/sp 值要么落进本页代码，要么写进转换报告「尺寸偏差」段。"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import layout_dims_gate as gate  # noqa: E402

LAYOUT = """<?xml version="1.0" encoding="utf-8"?>
<LinearLayout xmlns:ios="http://schemas.ios.com/apk/res/ios"
    xmlns:app="http://schemas.ios.com/apk/res-auto"
    xmlns:tools="http://schemas.ios.com/tools"
    ios:layout_width="match_parent" ios:layout_height="match_parent">
    <TextView ios:id="@+id/tv_title" ios:layout_width="wrap_content"
        ios:layout_height="wrap_content" ios:layout_marginTop="120dp"
        ios:textSize="24sp" tools:layout_marginStart="77dp" ios:padding="1dp"/>
    <TextView ios:id="@+id/tv_go" ios:layout_width="194dp" ios:layout_height="50dp"
        app:shape_radius="15dp" ios:layout_marginBottom="0dp"/>
</LinearLayout>
"""

PAGE_OK = """import { Btn } from '../components/Btn'
@ComponentV2
export struct GuidePage {
  build() {
    Column() {
      Text('t').fontSize(24).margin({ top: 120 })
      Btn()
    }
  }
}
"""

BTN = """@ComponentV2
export struct Btn {
  build() {
    Text('go').width(194).height('50vp').borderRadius($r('app.float.radius_btn'))
  }
}
"""


class LayoutDimsGate(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.proj = self.tmp / "hm"
        self.ios = self.tmp / "ios"
        self.layout_dir = self.ios / "app/src/main/res/layout"
        self.layout_dir.mkdir(parents=True)
        (self.layout_dir / "page_guide.xml").write_text(LAYOUT, encoding="utf-8")
        self.snap = self.proj / "spec/baseline/ui-snapshots/page_0001_GuideActivity"
        self.snap.mkdir(parents=True)
        self._meta(["app/src/main/res/layout/page_guide.xml"])
        ui = self.proj / "spec/baseline/ui"
        ui.mkdir(parents=True)
        self.spec = ui / "page_0001_GuideActivity.md"
        self.spec.write_text("# Guide\n- 源码布局: app/src/main/res/layout/page_guide.xml\n"
                             "- 输出文件: `entry/src/main/ets/pages/GuidePage.ets`\n", encoding="utf-8")
        self.ets = self.proj / "entry/src/main/ets"
        (self.ets / "pages").mkdir(parents=True)
        (self.ets / "components").mkdir(parents=True)
        self.page = self.ets / "pages/GuidePage.ets"
        self.page.write_text(PAGE_OK, encoding="utf-8")
        (self.ets / "components/Btn.ets").write_text(BTN, encoding="utf-8")
        elem = self.proj / "entry/src/main/resources/base/element"
        elem.mkdir(parents=True)
        (elem / "float.json").write_text(json.dumps({"float": [{"name": "radius_btn", "value": "15vp"}]}),
                                         encoding="utf-8")
        self.reports = self.proj / "spec/execution/conversion-reports"
        self.reports.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _meta(self, sources):
        (self.snap / "meta.json").write_text(json.dumps({"layout_sources": sources}), encoding="utf-8")

    def _run(self, pages=None):
        out = self.tmp / "out.json"
        argv = ["--project-root", str(self.proj), "--ios-root", str(self.ios), "--output-json", str(out)]
        if pages is not None:
            argv += ["--pages", *pages]
        rc = gate.main(argv)
        return rc, json.loads(out.read_text(encoding="utf-8"))["pages"][0]

    def test_all_values_present_across_page_and_imported_component(self):
        rc, row = self._run()
        self.assertEqual((rc, row["verdict"]), (0, "PASS"), row)
        self.assertEqual(row["dims_total"], 5)  # 120 / 24 / 194 / 50 / 15；tools: 与 0/1 不计

    def test_missing_value_fails_with_view_and_attr(self):
        self.page.write_text(PAGE_OK.replace("margin({ top: 120 })", "margin({ top: 100 })"), encoding="utf-8")
        rc, row = self._run()
        self.assertEqual((rc, row["verdict"]), (1, "FAIL"))
        self.assertEqual([m["value"] for m in row["missing"]], ["120"])
        self.assertIn("page_guide:tv_title@layout_marginTop", row["missing"][0]["where"])

    def test_deviation_section_explains_value(self):
        self.page.write_text(PAGE_OK.replace("margin({ top: 120 })", "margin({ top: 100 })"), encoding="utf-8")
        (self.reports / "page_0001.md").write_text(
            "## Conversion Report\n### 尺寸偏差\n- 120dp tv_title@layout_marginTop: 宿主已留 20 安全区，这里写 100\n"
            "### State Variables\n- 999dp 不在偏差段里，不算\n", encoding="utf-8")
        rc, row = self._run()
        self.assertEqual((rc, row["verdict"]), (0, "PASS"), row)
        self.assertEqual(row["explained"], ["120"])

    def test_numbers_in_comments_do_not_count(self):
        self.page.write_text(PAGE_OK.replace("margin({ top: 120 })", "margin({ top: 100 }) // 安卓 120dp")
                             .replace("build() {", "/* 120 */ build() {"), encoding="utf-8")
        rc, row = self._run()
        self.assertEqual(row["verdict"], "FAIL")

    def test_reexport_shell_is_followed(self):
        real = self.ets / "components/GuideContent.ets"
        real.write_text(PAGE_OK.replace("'../components/Btn'", "'./Btn'").replace("GuidePage", "GuideContent"),
                        encoding="utf-8")
        self.page.write_text("export { GuideContent as GuidePage } from '../components/GuideContent'\n",
                             encoding="utf-8")
        rc, row = self._run()
        self.assertIn("entry/src/main/ets/components/GuideContent.ets", row["code_files"])
        # Btn 在两跳之外，不算本页代码
        self.assertEqual(sorted(m["value"] for m in row["missing"]), ["15", "194", "50"])

    def test_imported_pages_and_logic_files_do_not_count(self):
        # 本页 import 了别的页面和一个 service：别的页面整份不算，service 只算具名常量
        self.page.write_text("import { OtherPage } from './OtherPage'\nimport { Svc } from '../services/Svc'\n"
                             + PAGE_OK, encoding="utf-8")
        (self.ets / "pages/OtherPage.ets").write_text(
            "@ComponentV2\nexport struct OtherPage { build() { Text('x').width(120).fontSize(24) } }\n",
            encoding="utf-8")
        (self.ets / "services").mkdir()
        (self.ets / "services/Svc.ets").write_text(
            "export const TITLE_TOP: number = 120\nexport class Svc { progress = 24 }\n", encoding="utf-8")
        other_snap = self.proj / "spec/baseline/ui-snapshots/page_0002_OtherActivity"
        other_snap.mkdir()
        (self.proj / "spec/baseline/ui/page_0002_OtherActivity.md").write_text(
            "- 输出文件: entry/src/main/ets/pages/OtherPage.ets\n", encoding="utf-8")
        self.page.write_text(self.page.read_text(encoding="utf-8")
                             .replace(".fontSize(24).margin({ top: 120 })", ""), encoding="utf-8")
        rc, row = self._run()
        self.assertNotIn("entry/src/main/ets/pages/OtherPage.ets", row["code_files"] + row["const_files"])
        self.assertEqual(row["const_files"], ["entry/src/main/ets/services/Svc.ets"])
        self.assertEqual([m["value"] for m in row["missing"]], ["24"])  # 120 由具名常量提供，24 只在逻辑里

    def test_layout_path_resolved_by_name_and_include_expanded(self):
        other = self.ios / "app/src/main/platform-res/layout"
        other.mkdir(parents=True)
        (self.layout_dir / "page_guide.xml").rename(other / "page_guide.xml")
        (other / "page_guide.xml").write_text(
            LAYOUT.replace("</LinearLayout>", '    <include layout="@layout/part_tip"/>\n</LinearLayout>'),
            encoding="utf-8")
        (other / "part_tip.xml").write_text(
            '<FrameLayout xmlns:ios="http://schemas.ios.com/apk/res/ios" '
            'ios:id="@+id/tip" ios:layout_height="37dp"/>', encoding="utf-8")
        rc, row = self._run()
        self.assertEqual(row["layouts"], ["page_guide.xml", "part_tip.xml"])
        self.assertEqual([m["value"] for m in row["missing"]], ["37"])

    def test_output_file_from_report_when_spec_has_none(self):
        self.spec.write_text("# Guide\n- 输出文件: 由后续 i2h-execute 分配\n", encoding="utf-8")
        (self.reports / "page_0001.md").write_text(
            "### Page Processed\n| Page ID | Label | Type | Output File |\n|---|---|---|---|\n"
            "| page_0001_GuideActivity | x | Base Page | GuidePage.ets |\n", encoding="utf-8")
        rc, row = self._run()
        self.assertEqual(row["verdict"], "PASS", row)

    def test_unconverted_page_is_not_a_failure_in_full_scan(self):
        self.page.unlink()
        rc, row = self._run()
        self.assertEqual((rc, row["verdict"]), (0, "NOT_CONVERTED"))

    def test_requested_page_without_output_fails(self):
        self.page.unlink()
        rc, row = self._run(pages=["page_0001"])
        self.assertEqual((rc, row["verdict"]), (1, "FAIL"))
        self.assertIn("output .ets not found", row["reason"])

    def test_report_without_page_prefix_is_read(self):
        self.page.write_text(PAGE_OK.replace("margin({ top: 120 })", "margin({ top: 100 })"), encoding="utf-8")
        (self.reports / "0001.md").write_text("### 尺寸偏差\n- 120dp tv_title@layout_marginTop: 宿主留了安全区\n",
                                              encoding="utf-8")
        rc, row = self._run(pages=["0001"])
        self.assertEqual((rc, row["verdict"]), (0, "PASS"), row)
        self.assertEqual(row["report"], "spec/execution/conversion-reports/0001.md")

    def test_unrecognised_page_id_is_an_error_not_a_full_scan(self):
        out = self.tmp / "out.json"
        rc = gate.main(["--project-root", str(self.proj), "--ios-root", str(self.ios),
                        "--pages", "HomePage", "--output-json", str(out)])
        self.assertEqual(rc, 2)
        self.assertFalse(out.exists())

    def test_skip_without_layout_sources_or_dims(self):
        self._meta([])
        self.assertEqual(self._run()[1]["verdict"], "SKIP")
        (self.layout_dir / "page_guide.xml").write_text(
            '<FrameLayout xmlns:ios="http://schemas.ios.com/apk/res/ios" '
            'ios:layout_height="1dp"/>', encoding="utf-8")
        self._meta(["app/src/main/res/layout/page_guide.xml"])
        rc, row = self._run()
        self.assertEqual((rc, row["verdict"]), (0, "SKIP"))


if __name__ == "__main__":
    unittest.main()
