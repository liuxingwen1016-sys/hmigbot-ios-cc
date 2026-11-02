# -*- coding: utf-8 -*-
"""Regression: C2_TARGET_NOT_INSTANTIATED must not fire on static facades.

Graduated anchor from the aippt GLM_2 full run (2026-09-15)：C2 退化分支只认
`new X(` / `X.getInstance()`，对**靠静态访问接线**的 target 产生 6 条误报（全 14 slice）：

    XXTeaUtils              0 实例化 /  2 处他处静态访问   （常量持有者）
    SplashService           0        / 10                  （静态门面）
    WebContainerService     0        / 26
    CustomerContactService  0        /  7

与 C1 孤儿检查同口径改用 usage_evidence 豁免，但两点比 C1 更严：
  - defining_file 由 export_index 解析（非空串）→ 自身文件内的静态访问不算他处证据
  - own-file-use 不计入 C2：类只在自己文件里被引用，不证明它被接进页面

fail-tight 不变：任何地方都没有引用的 target 仍然 FAIL。

Run: python3 tests/test_c2_static_facade.py
"""
import json
import sys
import tempfile
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent

WIRED_FACADE = """\
export class SplashService {
  static markAgreementAccepted(): void {}
}
"""
CALLER = """\
import { SplashService } from '../services/SplashService';
@Entry @Component struct GuidePage {
  build() { Column() { Button('ok').onClick(() => { SplashService.markAgreementAccepted(); }) } }
}
"""
LONELY = """\
export class NeverUsedService {
  static dial(): void { NeverUsedService.dial(); }
}
"""


def _mk(root: Path) -> None:
    ets = root / "entry" / "src" / "main" / "ets"
    (ets / "services").mkdir(parents=True, exist_ok=True)
    (ets / "pages").mkdir(parents=True, exist_ok=True)
    (ets / "services" / "SplashService.ets").write_text(WIRED_FACADE, encoding="utf-8")
    (ets / "pages" / "GuidePage.ets").write_text(CALLER, encoding="utf-8")
    (ets / "services" / "NeverUsedService.ets").write_text(LONELY, encoding="utf-8")


def main() -> int:
    sys.path.insert(0, str(SCRIPTS_DIR))
    from ref_graph_lib.graph import EtsRefGraph  # noqa: E402

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _mk(root)
        graph = EtsRefGraph(root).build()

        # ① 静态门面：0 实例化，但他处有 X.member → 必须有证据（否则 C2 会误报）
        assert not graph.instantiators_of_class("SplashService"), "fixture 失效：不该有实例化"
        exp = graph.export_index.get("SplashService") or set()
        defining = graph._rel(next(iter(exp))) if len(exp) == 1 else ""
        ev = graph.usage_evidence("SplashService", defining)
        assert ev and ev.startswith("static-access:"), f"静态门面应有他处静态访问证据，实得 {ev!r}"
        print(f"① 静态门面      SplashService → {ev}（C2 豁免成立）")

        # ② 真未接线：只在自己文件里自引用 → own-file-use，C2 必须**不**豁免
        assert not graph.instantiators_of_class("NeverUsedService")
        exp2 = graph.export_index.get("NeverUsedService") or set()
        d2 = graph._rel(next(iter(exp2))) if len(exp2) == 1 else ""
        ev2 = graph.usage_evidence("NeverUsedService", d2)
        assert ev2 is None or ev2.startswith("own-file-use:"), \
            f"只自引用的类不该拿到他处证据，实得 {ev2!r}"
        print(f"② 仅自引用      NeverUsedService → {ev2}（C2 不豁免，仍 FAIL）")

    print("c2 static facade: PASS (①②)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
