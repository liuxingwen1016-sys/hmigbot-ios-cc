#!/usr/bin/env python3
"""sweep_resources.py 的 SVG 可用性校验：鸿蒙画不出来的一律算，会画走样的只在被引用时算。"""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import sweep_resources as sw  # noqa: E402

GOOD = ('<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" viewBox="0 0 100 100">'
        '<rect x="0" y="0" width="100" height="100" rx="8" fill="#3C2AF8"/></svg>')
PREFIXED = ("<?xml version='1.0' encoding='utf-8'?>\n"
            '<ns0:svg xmlns:ns0="http://www.w3.org/2000/svg" width="100" height="100" viewBox="0 0 100 100">'
            '<ns0:defs><ns0:linearGradient id="g"><ns0:stop offset="0%" stop-color="#3c2af8"/></ns0:linearGradient>'
            '</ns0:defs><ns0:rect fill="url(#g)" width="100" height="100"/></ns0:svg>')
REMNANT = ('<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24">'
           '<rect width="24" height="24" rx="@dimen/btn_radius" fill="#FFFFFF"/></svg>')


class SweepSvg(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.ets = self.root / "entry/src/main/ets/pages"
        self.ets.mkdir(parents=True)
        self.media = self.root / "entry/src/main/resources/base/media"
        self.media.mkdir(parents=True)
        (self.media / "btn_ok.svg").write_text(GOOD, encoding="utf-8")
        (self.media / "btn_ns0.svg").write_text(PREFIXED, encoding="utf-8")
        (self.media / "btn_remnant.svg").write_text(REMNANT, encoding="utf-8")
        (self.media / "lib_remnant.svg").write_text(REMNANT, encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _page(self, *names):
        refs = "\n".join(f"Text('x').backgroundImage($r('app.media.{n}'))" for n in names)
        (self.ets / "P.ets").write_text(f"@Entry\n@ComponentV2\nstruct P {{ build() {{ Column() {{ {refs} }} }} }}\n",
                                        encoding="utf-8")

    def _run(self, *extra):
        return sw.main(["--project-root", str(self.root), "--output-json", "out.json", *extra])

    def test_valid_svg_passes(self):
        self.assertEqual(sw.svg_problems(self.media / "btn_ok.svg"), [])
        self._page("btn_ok")
        self.assertEqual(self._run(), 0)

    def test_prefixed_namespace_is_fatal(self):
        probs = sw.svg_problems(self.media / "btn_ns0.svg")
        self.assertTrue(any(p.startswith("svg_namespace_prefixed") for p in probs), probs)
        self._page("btn_ns0")
        self.assertEqual(self._run(), 1)

    def test_fix_is_lossless_and_clears_problem(self):
        before = ET.fromstring((self.media / "btn_ns0.svg").read_text(encoding="utf-8"))
        self._page("btn_ns0")
        self.assertEqual(self._run("--fix-svg"), 0)
        text = (self.media / "btn_ns0.svg").read_text(encoding="utf-8")
        self.assertIn("<svg ", text)
        self.assertNotIn("ns0:", text)
        after = ET.fromstring(text)
        self.assertEqual([e.tag for e in before.iter()], [e.tag for e in after.iter()])
        self.assertEqual([e.attrib for e in before.iter()], [e.attrib for e in after.iter()])

    def test_unresolved_android_ref_counts_only_when_referenced(self):
        self.assertIn("android_remnant", sw.svg_problems(self.media / "btn_remnant.svg"))
        self._page("btn_remnant")
        self.assertEqual(self._run(), 1)

    def test_unreferenced_remnant_is_warning_in_full_scan(self):
        self._page("btn_ok")
        (self.media / "btn_ns0.svg").unlink()
        (self.media / "btn_remnant.svg").unlink()
        self.assertEqual(self._run("--all-svg"), 0)
        import json
        doc = json.loads((self.root / "out.json").read_text(encoding="utf-8"))
        self.assertEqual([e["file"].split("/")[-1] for e in doc["svg_warnings_unreferenced"]], ["lib_remnant.svg"])

    def test_full_scan_catches_unreferenced_prefixed_svg(self):
        self._page("btn_ok")
        self.assertEqual(self._run("--all-svg"), 1)

    def test_broken_svg_with_fix_is_reported_not_crashed(self):
        # 1018 复查 M9：截断的前缀 SVG 在 --fix-svg 下不能把整次 sweep 打崩
        (self.media / "broken.svg").write_text('<svg xmlns:ns0="http://www.w3.org/2000/svg"><ns0:path d="M0', encoding="utf-8")
        self._page("btn_ok")
        self.assertEqual(self._run("--all-svg", "--fix-svg"), 1)
        import json
        doc = json.loads((self.root / "out.json").read_text(encoding="utf-8"))
        broken = [e for e in doc["invalid_svg"] if e["file"].endswith("broken.svg")]
        self.assertTrue(broken and broken[0]["problems"][0].startswith("parse_error"), doc["invalid_svg"])

    def test_declared_but_unused_prefix_is_fine(self):
        # 1018 复查 L8：只多声明了前缀、元素不带前缀（Inkscape 写法）不是渲染问题
        (self.media / "inkscape.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" xmlns:svg="http://www.w3.org/2000/svg" width="2" height="2">'
            '<rect width="2" height="2" fill="#000"/></svg>', encoding="utf-8")
        self.assertEqual(sw.svg_problems(self.media / "inkscape.svg"), [])


if __name__ == "__main__":
    unittest.main()
