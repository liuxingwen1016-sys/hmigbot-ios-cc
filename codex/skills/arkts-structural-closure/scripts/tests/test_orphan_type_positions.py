# -*- coding: utf-8 -*-
"""Orphan blind spot: classes used only in a generic slot or `instanceof` are not orphans.

Anchor gpt1030_2 FV-1（2026-10-18）：`Map<string, PushPageInfo>`（第二个泛型参数）与
`failure instanceof RequestCancelledError` 都是真实使用，却报 NO_IMPORTER；同一份结果里另外
5 个类全工程只有声明——那些仍须报（fail-tight）。

Run: python3 tests/test_orphan_type_positions.py   (any cwd)
"""
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))
from ref_graph_lib import EtsRefGraph  # noqa: E402

SERVICE = """\
export class PushPageInfo {
  name: string = ''
}
export class RequestCancelledError extends Error {}
export class NeverUsed {
  run(): void {}
}
export class PushService {
  private routes: Map<string, PushPageInfo> = new Map()
  handle(failure: Error): boolean {
    return failure instanceof RequestCancelledError
  }
  pick(x: Object): string { return (x as Holder).name }
}
export class Holder { name: string = '' }
"""


class OrphanTypePositions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        svc = root / "entry/src/main/ets/services/PushService.ets"
        svc.parent.mkdir(parents=True)
        svc.write_text(SERVICE, encoding="utf-8")
        self.graph = EtsRefGraph(root).build()
        self.rel = "entry/src/main/ets/services/PushService.ets"

    def tearDown(self):
        self.tmp.cleanup()

    def test_second_generic_argument_is_usage(self):
        self.assertTrue(self.graph.usage_evidence("PushPageInfo", self.rel))

    def test_instanceof_is_usage(self):
        self.assertTrue(self.graph.usage_evidence("RequestCancelledError", self.rel))

    def test_as_cast_is_usage(self):
        self.assertTrue(self.graph.usage_evidence("Holder", self.rel))

    def test_import_list_alone_is_not_usage(self):
        # `import { PushService, ImportedOnly } from` 里的 `, ImportedOnly` 不是使用
        root = Path(self.tmp.name)
        lib = root / "entry/src/main/ets/services/Lib.ets"
        lib.write_text("export class ImportedOnly {\n  run(): void {}\n}\n", encoding="utf-8")
        page = root / "entry/src/main/ets/pages/P.ets"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text("import { PushService, ImportedOnly } from '../services/Lib'\n"
                        "@Entry @ComponentV2 struct P { build() { Column() {} } }\n", encoding="utf-8")
        graph = EtsRefGraph(root).build()
        self.assertIsNone(graph.usage_evidence("ImportedOnly", "entry/src/main/ets/services/Lib.ets"))

    def test_default_plus_named_import_and_local_reexport_are_not_usage(self):
        # 1018 复查 M10：`import D, { X } from` 与 `export { A, X }`（不带 from）同样只是导入 / 导出
        root = Path(self.tmp.name)
        lib = root / "entry/src/main/ets/services/Lib2.ets"
        lib.write_text("export class OnlyListed {\n  run(): void {}\n}\nclass Helper {}\nexport { Helper, OnlyListed }\n",
                       encoding="utf-8")
        page = root / "entry/src/main/ets/pages/Q.ets"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text("import Svc, { OnlyListed } from '../services/Lib2'\n"
                        "@Entry @ComponentV2 struct Q { build() { Column() {} } }\n", encoding="utf-8")
        graph = EtsRefGraph(root).build()
        self.assertIsNone(graph.usage_evidence("OnlyListed", "entry/src/main/ets/services/Lib2.ets"))

    def test_declared_only_class_stays_orphan(self):
        self.assertIsNone(self.graph.usage_evidence("NeverUsed", self.rel))


if __name__ == "__main__":
    unittest.main()
