"""C2 integration point: caller pages that use the AppAssembly shared instance must PASS
(1016 customer false positive), and pages that never reach the target must still FAIL."""
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from plan_lib.feature_plan_parser import IntegrationPoint  # noqa: E402
from ref_graph_lib import EtsRefGraph  # noqa: E402
import verify_slice_wiring as vsw  # noqa: E402

E = "entry/src/main/ets/"

TRACKING = (
    "export class TrackingApplication {\n"
    "  startCollectInfo(): void { console.info('collect') }\n"
    "}\n")
ASSEMBLY = (
    "import { TrackingApplication } from './services/TrackingApplication'\n"
    "export class AppAssembly {\n"
    "  static shared: AppAssembly = new AppAssembly()\n"
    "  tracking: TrackingApplication = new TrackingApplication()\n"
    "  static tracking(): TrackingApplication { return AppAssembly.shared.tracking }\n"
    "}\n")

PAGES = {
    "chain": "AppAssembly.shared.tracking.startCollectInfo()",
    "plain_field": "private tracking: TrackingApplication = AppAssembly.shared.tracking\n"
                   "  onTap() { this.tracking.startCollectInfo() }",
    "factory": "AppAssembly.tracking().startCollectInfo()",
}


def _page(body):
    return (
        "import { AppAssembly } from '../AppAssembly'\n"
        "import { TrackingApplication } from '../services/TrackingApplication'\n"
        "@ComponentV2\nstruct HomePage {\n  " + body + "\n  build() { Column() {} }\n}\n")


def _w(root, rel, text):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _ip():
    return IntegrationPoint(
        description="HomePage.startCollectInfo -> TrackingApplication",
        handler_text="HomePage.startCollectInfo", target_text="TrackingApplication",
        handler_local="startCollectInfo", target_class="TrackingApplication",
        evidence_raw="", checked=False)


def _run(root):
    graph = EtsRefGraph(root).build()
    return vsw._check_single_ip(_ip(), "ip_001", graph, root)


def _setup(root, page_body, with_assembly=True):
    _w(root, E + "services/TrackingApplication.ets", TRACKING)
    if with_assembly:
        _w(root, E + "AppAssembly.ets", ASSEMBLY)
    _w(root, E + "pages/HomePage.ets", _page(page_body))


def test_shared_instance_forms_pass(tmp_path):
    for name, body in PAGES.items():
        root = tmp_path / name
        _setup(root, body)
        r = _run(root)
        assert r["status"] == "PASS", (name, r)


def test_handler_without_target_still_fails(tmp_path):
    """No assembly, no new, no typed use of the target → still FAIL, and repair says new."""
    _setup(tmp_path, "startCollectInfo() { console.info('x') }", with_assembly=False)
    _w(tmp_path, E + "pages/Other.ets",
       "import { TrackingApplication } from '../services/TrackingApplication'\n"
       "const t = new TrackingApplication()\n")
    r = _run(tmp_path)
    assert r["status"] == "FAIL" and r["failed_check"] == "C2_VM_NOT_INSTANTIATED", r


def test_assembly_owned_repair_does_not_suggest_second_instance(tmp_path):
    """Assembly owns the target but the page never reaches it → FAIL, repair points to AppAssembly."""
    _w(tmp_path, E + "services/TrackingApplication.ets", TRACKING)
    _w(tmp_path, E + "AppAssembly.ets", ASSEMBLY)
    _w(tmp_path, E + "pages/HomePage.ets",
       "@ComponentV2\nstruct HomePage {\n  startCollectInfo() { console.info('x') }\n"
       "  build() { Column() {} }\n}\n")
    r = _run(tmp_path)
    assert r["status"] == "FAIL", r
    assert "AppAssembly" in r["repair_action"] and "do not add a second" in r["repair_action"], r


# ─── C1 orphan check: same shared-instance shape ──────────────────────────────
def _orphans(root):
    graph = EtsRefGraph(root).build()
    return graph.find_orphans([root / (E + "services/TrackingApplication.ets")])


def test_c1_assembly_owned_not_orphan(tmp_path):
    for name, body in PAGES.items():
        root = tmp_path / name
        _setup(root, body)
        assert _orphans(root) == [], name


def test_c1_assembly_not_imported_by_ui_still_orphan(tmp_path):
    """AppAssembly creates the class but no page imports AppAssembly → still orphan,
    and the repair points to the shared instance instead of a second `new`."""
    _w(tmp_path, E + "services/TrackingApplication.ets", TRACKING)
    _w(tmp_path, E + "AppAssembly.ets", ASSEMBLY)
    _w(tmp_path, E + "pages/HomePage.ets",
       "import { TrackingApplication } from '../services/TrackingApplication'\n"
       "@ComponentV2\nstruct HomePage {\n  build() { Column() {} }\n}\n")
    found = _orphans(tmp_path)
    assert [o.reason for o in found] == ["ONLY_INSTANTIATED_BY_NON_UI"], found
    repair = vsw._orphan_repair(found[0])
    assert "AppAssembly" in repair and "do not add a second" in repair, repair


# ─── 1017：只 import 组装根、没经持有目标的成员取实例 → 不算接线 ─────────────────
def test_import_assembly_without_reaching_target_fails(tmp_path):
    """赵明负例：页面 import AppAssembly，handler 只打日志、没碰 tracking → 必须 FAIL。"""
    _setup(tmp_path, "startCollectInfo() { console.info('x') }")
    r = _run(tmp_path)
    assert r["status"] == "FAIL" and r["failed_check"] == "C2_VM_NOT_INSTANTIATED", r
    assert "do not add a second" in r["repair_action"], r


def test_assembly_reference_to_other_member_fails(tmp_path):
    """经组装根取的是别的成员（AppAssembly.shared.other），不是持有目标的 tracking → FAIL。"""
    _setup(tmp_path, "startCollectInfo() { AppAssembly.shared.other.run() }")
    assert _run(tmp_path)["status"] == "FAIL"


def test_capability_table_slot_passes(tmp_path):
    """组装根标准形态：capabilityTable 槽位持有目标，页面经 capabilityTable.<键> 调用 → PASS。"""
    _w(tmp_path, E + "services/TrackingApplication.ets", TRACKING)
    _w(tmp_path, E + "AppAssembly.ets",
       "import { TrackingApplication } from './services/TrackingApplication'\n"
       "export const capabilityTable: CapabilityTable = {\n"
       "  tracker: new TrackingApplication(),\n"
       "}\n")
    _w(tmp_path, E + "pages/HomePage.ets",
       "import { capabilityTable } from '../AppAssembly'\n"
       "@ComponentV2\nstruct HomePage {\n  startCollectInfo() { capabilityTable.tracker.startCollectInfo() }\n"
       "  build() { Column() {} }\n}\n")
    assert _run(tmp_path)["status"] == "PASS"


@pytest.mark.parametrize("body", [
    "startCollectInfo() { /* AppAssembly.shared.tracking.startCollectInfo() */ }",
    "startCollectInfo() { console.info('AppAssembly.shared.tracking.startCollectInfo()') }",
    "startCollectInfo() { console.info(`AppAssembly.shared.tracking.startCollectInfo()`) }",
    "startCollectInfo() { const fake = 'new TrackingApplication()' }",
    "startCollectInfo() { /* new TrackingApplication() */ }",
    "startCollectInfo() { /* private t: TrackingApplication */ }",
    "startCollectInfo() { unrelated.tracking.run(); AppAssembly.shared.other.run() }",
])
def test_fake_shared_usage_fails(tmp_path, body):
    _setup(tmp_path, body)
    assert _run(tmp_path)["status"] == "FAIL"


@pytest.mark.parametrize("prefix", ["// ", "/* "])
def test_handler_in_comment_does_not_count(tmp_path, prefix):
    suffix = {"// ": "\n", "/* ": " */"}[prefix]
    _setup(tmp_path, prefix + "startCollectInfo()" + suffix
           + "\n  onTap() { AppAssembly.shared.tracking.run() }")
    assert _run(tmp_path)["failed_check"] == "C2_HANDLER_NOT_WIRED"


def _handler_run(root, handler, body):
    _setup(root, body + "\n  onTap() { AppAssembly.shared.tracking.startCollectInfo() }")
    ip = IntegrationPoint(
        description=f"HomePage.{handler} -> TrackingApplication",
        handler_text=f"HomePage.{handler}", target_text="TrackingApplication",
        handler_local=handler, target_class="TrackingApplication",
        evidence_raw="", checked=False)
    return vsw._check_single_ip(ip, "ip_001", EtsRefGraph(root).build(), root)


@pytest.mark.parametrize("handler,body", [
    # plan 里的 handler 是近似名，实现带后缀（AIPPT7 实测 onWechat/onRefund/onContact）
    ("onWechat", "private onWechatLogin(): void {}"),
    # JS Bridge 注册名本来就是字符串（aippt_codex_v2 实测 moorJsCallBack）
    ("moorJsCallBack", "aboutToAppear() { this.ctl.registerJavaScriptProxy(this.obj, 'moorJsCallBack', []) }"),
])
def test_handler_prefix_name_or_string_literal_counts(tmp_path, handler, body):
    assert _handler_run(tmp_path, handler, body)["status"] == "PASS"


@pytest.mark.parametrize("handler,body", [
    # 词中子串不算（diceRoller 实测 source 命中 resourceManager）
    ("source", "private mgr = context.resourceManager"),
    # 只在注释里出现不算（AIPPT7 实测 setProgress 只出现在「对应 setProgress()」注释）
    ("setProgress", "// 对应 setProgress()：动画进度超前时暂停\n  private pause(): void {}"),
])
def test_handler_mid_word_or_comment_only_fails(tmp_path, handler, body):
    assert _handler_run(tmp_path, handler, body)["failed_check"] == "C2_HANDLER_NOT_WIRED"


def test_target_holder_in_comment_or_string_does_not_count(tmp_path):
    _setup(tmp_path, "startCollectInfo() { AppAssembly.shared.fake.run() }")
    _w(tmp_path, E + "AppAssembly.ets", ASSEMBLY + "\n"
       "/* fake = new TrackingApplication() */\n"
       "const note = 'fake: new TrackingApplication()'\n")
    assert _run(tmp_path)["status"] == "FAIL"


def test_assembly_chain_requires_real_import(tmp_path):
    _setup(tmp_path, "startCollectInfo() { AppAssembly.shared.tracking.run() }")
    p = tmp_path / (E + "pages/HomePage.ets")
    p.write_text(p.read_text().replace("import { AppAssembly }", "// import { AppAssembly }"))
    assert _run(tmp_path)["status"] == "FAIL"


@pytest.mark.parametrize("fake_import", [
    "/* import { AppAssembly } from '../AppAssembly' */",
    "const note = `import { AppAssembly } from '../AppAssembly'`",
])
def test_c1_fake_assembly_import_does_not_create_ui_reach(tmp_path, fake_import):
    _setup(tmp_path, "build() { Column() {} }")
    _w(tmp_path, E + "pages/HomePage.ets", fake_import + "\n@ComponentV2\nstruct HomePage {}")
    assert [o.reason for o in _orphans(tmp_path)] == ["ONLY_INSTANTIATED_BY_NON_UI"]


def test_true_static_facade_still_has_evidence_but_string_does_not(tmp_path):
    _w(tmp_path, E + "services/Facade.ets", "export class Facade { static run(): void {} }")
    _w(tmp_path, E + "pages/HomePage.ets", "const note = 'Facade.run()'")
    graph = EtsRefGraph(tmp_path).build()
    assert graph.usage_evidence("Facade", E + "services/Facade.ets") is None
    _w(tmp_path, E + "pages/HomePage.ets", "Facade.run()")
    graph = EtsRefGraph(tmp_path).build()
    assert graph.usage_evidence("Facade", E + "services/Facade.ets").startswith("static-access:")


@pytest.mark.parametrize("body", [
    "startCollectInfo() { console.info('noop') }",
    "startCollectInfo() { AppAssembly.shared.other.startCollectInfo() }",
])
def test_c1_import_or_other_capability_does_not_wire_target(tmp_path, body):
    """Pipeline has no C2 fallback: the assembly cannot exempt all owned targets."""
    _setup(tmp_path, body)
    _w(tmp_path, E + "AppAssembly.ets", ASSEMBLY.replace(
        "  tracking:", "  other: OtherTracking = new OtherTracking()\n  tracking:"))
    graph = EtsRefGraph(tmp_path).build()
    findings = graph.find_orphans([tmp_path / (E + "services/TrackingApplication.ets")])
    assert [o.reason for o in findings] == ["ONLY_INSTANTIATED_BY_NON_UI"]
    assert graph.usage_evidence("TrackingApplication", E + "services/TrackingApplication.ets") is None
    assert tmp_path / (E + "AppAssembly.ets") not in graph._ui_reachable_files()


@pytest.mark.parametrize("via_factory", [False, True])
def test_other_object_with_same_member_name_is_not_target(tmp_path, via_factory):
    """Reviewer fixture: other.tracking has a different type from shared.tracking."""
    body = "AppAssembly.tracking()" if via_factory else "AppAssembly.shared.other.tracking"
    _setup(tmp_path, "startCollectInfo() { " + body + ".startCollectInfo() }")
    source = ASSEMBLY.replace("  tracking:", "  other = new OtherCapabilities()\n  tracking:")
    if via_factory:
        source = source.replace("return AppAssembly.shared.tracking", "return AppAssembly.shared.other.tracking")
    _w(tmp_path, E + "AppAssembly.ets", source
       + "\nclass OtherCapabilities { tracking = new OtherTracking() }\n"
       + "class OtherTracking { startCollectInfo(): void {} }\n")
    assert _run(tmp_path)["failed_check"] == "C2_VM_NOT_INSTANTIATED"
    assert [o.reason for o in _orphans(tmp_path)] == ["ONLY_INSTANTIATED_BY_NON_UI"]


@pytest.mark.parametrize("expression", [
    "return null", "return unknownFactory()",
    "if (flag) { return AppAssembly.shared.tracking } return null",
])
def test_factory_return_type_alone_is_not_proof(tmp_path, expression):
    _setup(tmp_path, "startCollectInfo() { AppAssembly.tracking().startCollectInfo() }")
    _w(tmp_path, E + "AppAssembly.ets", ASSEMBLY.replace("return AppAssembly.shared.tracking", expression))
    assert _run(tmp_path)["failed_check"] == "C2_VM_NOT_INSTANTIATED"
    assert _orphans(tmp_path)


@pytest.mark.parametrize("source, access", [
    ("export class AppAssembly { static tracking = new TrackingApplication() }",
     "AppAssembly.tracking"),
    (ASSEMBLY.replace("static tracking()", "static get tracking()"), "AppAssembly.tracking"),
    (ASSEMBLY.replace("static tracking(): TrackingApplication { return AppAssembly.shared.tracking }",
                      "getTracking(): TrackingApplication { return this.tracking }"),
     "AppAssembly.shared.getTracking()"),
    ("const held = new TrackingApplication()\n"
     "export const capabilityTable: CapabilityTable = { tracker: held }", "capabilityTable.tracker"),
])
def test_proven_complete_paths_and_factory_returns_pass(tmp_path, source, access):
    _setup(tmp_path, "startCollectInfo() { " + access + ".startCollectInfo() }")
    _w(tmp_path, E + "AppAssembly.ets", "import { TrackingApplication } from './services/TrackingApplication'\n" + source)
    _w(tmp_path, E + "pages/HomePage.ets", _page("startCollectInfo() { " + access + ".startCollectInfo() }")
       .replace("{ AppAssembly }", "{ AppAssembly, capabilityTable }"))
    assert _run(tmp_path)["status"] == "PASS"
    assert _orphans(tmp_path) == []


def test_used_shared_target_keeps_transitive_dependencies_reachable(tmp_path):
    _setup(tmp_path, "startCollectInfo() { AppAssembly.shared.tracking.startCollectInfo() }")
    _w(tmp_path, E + "services/Repo.ets", "export class Repo {}")
    _w(tmp_path, E + "services/TrackingApplication.ets",
       "import { Repo } from './Repo'\n" + TRACKING.replace("startCollectInfo():", "repo = new Repo()\n  startCollectInfo():"))
    graph = EtsRefGraph(tmp_path).build()
    assert graph.find_orphans([tmp_path / (E + "services/Repo.ets")]) == []


def test_import_alias_resolves_complete_path_not_unrelated_receiver(tmp_path):
    _setup(tmp_path, "startCollectInfo() { Root.shared.tracking.startCollectInfo() }")
    p = tmp_path / (E + "pages/HomePage.ets")
    p.write_text(p.read_text().replace("{ AppAssembly }", "{ AppAssembly as Root }"))
    assert _run(tmp_path)["status"] == "PASS"
    assert _orphans(tmp_path) == []
    p.write_text(p.read_text().replace("Root.shared.tracking", "unrelated . Root.shared.tracking"))
    assert _run(tmp_path)["status"] == "FAIL"
    assert _orphans(tmp_path)


def test_stray_quote_in_regex_literal_does_not_mask_following_code(tmp_path):
    body = ("private esc(s: string): string { return s.replace(/'/g, '') }\n"
            "  private startCollectInfo(): void { AppAssembly.shared.tracking.startCollectInfo() }")
    assert _handler_run(tmp_path, "startCollectInfo", body)["status"] == "PASS"
    from ref_graph_lib.graph import mask_noncode
    masked = mask_noncode("a = /'/g\nb = new Foo()\nc = 'x'")
    assert "new Foo()" in masked and "'x'" not in masked
