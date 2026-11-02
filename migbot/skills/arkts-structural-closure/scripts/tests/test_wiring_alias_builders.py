"""E22/E86-style wiring regressions: explicit route aliases and real Builder code."""
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from plan_lib.feature_plan_parser import IntegrationPoint, ParentReplacement
from ref_graph_lib import EtsRefGraph
import verify_slice_wiring as vsw

E = "entry/src/main/ets/"


def write(root, rel, text):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def replacement(root, source):
    write(root, E + "pages/Host.ets", source)
    ppr = ParentReplacement(E + "pages/Host.ets", "content", "ChildPage()", "Slice 1")
    return vsw._check_single_ppr(ppr, "ppr_001", root)


@pytest.mark.parametrize("signature", [
    "@Builder content()", "@Builder function content()",
    "@Builder export function content(): void", "export @Builder function content(): void",
    "@Builder\nexport function content(p: Params = new Params()): void",
])
def test_real_builder_forms_pass(tmp_path, signature):
    assert replacement(tmp_path, signature + " { ChildPage() }")["status"] == "PASS"


@pytest.mark.parametrize("source", [
    "// @Builder content() { ChildPage() }",
    "/* @Builder export function content() { ChildPage() } */",
    "const note = `@Builder export function content() { ChildPage() }`",
    "@Builder content();\nfunction unrelated() { ChildPage() }",
])
def test_noncode_or_missing_builder_fails(tmp_path, source):
    assert replacement(tmp_path, source)["failed_check"] == "C4_BUILDER_NOT_FOUND"


@pytest.mark.parametrize("body", [
    "/* ChildPage() */ Column() {}", "Text('ChildPage()')", "OtherChildPage()",
    "const holder = ChildPage", "Text(`ChildPage()`) ",
])
def test_missing_replacement_call_fails(tmp_path, body):
    assert replacement(tmp_path, "@Builder content() { " + body + " }")["failed_check"] == "C4_REPLACEMENT_NOT_FOUND"


def test_braces_in_strings_do_not_end_builder_early(tmp_path):
    assert replacement(tmp_path, "@Builder content() { Text('}') /* } */ ChildPage() }")["status"] == "PASS"


def test_residual_todo_still_fails(tmp_path):
    assert replacement(tmp_path, "@Builder content() { ChildPage() // TODO: implement\n}")["status"] == "FAIL"


def test_duplicate_builder_declarations_fail_closed(tmp_path):
    assert replacement(tmp_path, "@Builder content() { ChildPage() }\n"
                       "@Builder content() { ChildPage() }")["status"] == "FAIL"


def page(root, name="ActualPage", path="pages/Actual.ets"):
    return write(root, E + path,
                 "@ComponentV2\nexport struct " + name + " {\n"
                 "  onTap() { console.info('done') }\n  build() { Column() {} }\n}\n"
                 "@Builder\nexport function " + name + "Builder(): void { " + name + "() }\n")


def ip(root, name="LegacyPage", scope_files=None):
    graph = EtsRefGraph(root).build()
    entry = IntegrationPoint(name + ".onTap", name + ".onTap", "", "onTap", None, "", False)
    return vsw._check_single_ip(entry, "ip_001", graph, root, scope_files)


def route(root, body, imports="import { ActualPageBuilder } from './Actual'", path="pages/PageMapGen.ets"):
    return write(root, E + path, imports + "\n@Builder\nexport function AppPageMap(name: string) {\n" + body + "\n}")


def test_explicit_route_alias_resolves_real_host(tmp_path):
    p = page(tmp_path)
    route(tmp_path, "if (name === 'LegacyPage') { ActualPageBuilder() }")
    result = ip(tmp_path)
    assert result["status"] == "PASS" and result["caller_resolved_by"] == "route-alias"
    assert result["caller"] == str(p.relative_to(tmp_path))


def test_alias_still_checks_handler_in_real_host(tmp_path):
    page(tmp_path).write_text("@Builder export function ActualPageBuilder() { Text('missing handler') }")
    route(tmp_path, "if (name === 'LegacyPage') { ActualPageBuilder() }")
    assert ip(tmp_path)["failed_check"] == "C2_HANDLER_NOT_WIRED"


def test_existing_struct_and_unique_inline_scope_still_resolve(tmp_path):
    p = page(tmp_path)
    assert ip(tmp_path, "ActualPage")["status"] == "PASS"
    p.write_text(p.read_text() + "\nconst InlineDialog = true\n")
    result = ip(tmp_path, "InlineDialog", [str(p.relative_to(tmp_path))])
    assert result["status"] == "PASS" and result["caller_resolved_by"] == "scope-mention"


@pytest.mark.parametrize("body", [
    "// if (name === 'LegacyPage') { ActualPageBuilder() }",
    "/* if (name === 'LegacyPage') { ActualPageBuilder() } */",
    "Text(`if (name === 'LegacyPage') { ActualPageBuilder() }`)",
    "if (name === 'LegacyPage') { /* ActualPageBuilder() */ }",
    "if (name === 'LegacyPage') { Text('ActualPageBuilder()') }",
])
def test_noncode_alias_or_builder_does_not_resolve(tmp_path, body):
    page(tmp_path)
    p = route(tmp_path, body)
    assert ip(tmp_path, scope_files=[str(p.relative_to(tmp_path))])["failed_check"] == "C2_PAGE_NOT_FOUND"


def test_unregistered_page_suffix_is_not_an_alias(tmp_path):
    page(tmp_path)
    assert ip(tmp_path, "Actual")["status"] == "PASS"  # real file name
    assert ip(tmp_path, "ActualPagePage")["failed_check"] == "C2_PAGE_NOT_FOUND"


def test_alias_without_import_is_not_wiring(tmp_path):
    page(tmp_path)
    route(tmp_path, "if (name === 'LegacyPage') { ActualPageBuilder() }", imports="")
    assert ip(tmp_path)["failed_check"] == "C2_PAGE_NOT_FOUND"


@pytest.mark.parametrize("callee", [
    "unrelated.ActualPageBuilder", "unrelated . ActualPageBuilder",
    "unrelated?.ActualPageBuilder", "new ActualPageBuilder",
])
def test_unrelated_receiver_method_is_not_registered_builder(tmp_path, callee):
    page(tmp_path)
    route(tmp_path, "if (name === 'LegacyPage') { " + callee + "() }")
    assert ip(tmp_path)["failed_check"] == "C2_PAGE_NOT_FOUND"


def test_conflicting_explicit_aliases_fail_closed(tmp_path):
    page(tmp_path)
    page(tmp_path, "OtherPage", "pages/Other.ets")
    route(tmp_path, "if (name === 'LegacyPage') { ActualPageBuilder() }\n"
          "if (name === 'LegacyPage') { OtherPageBuilder() }",
          "import { ActualPageBuilder } from './Actual'\nimport { OtherPageBuilder } from './Other'")
    assert ip(tmp_path)["failed_check"] == "C2_PAGE_NOT_FOUND"


def test_ambiguous_same_filename_is_not_first_match(tmp_path):
    page(tmp_path, path="pages/LegacyPage.ets")
    page(tmp_path, "OtherPage", "views/LegacyPage.ets")
    assert ip(tmp_path)["failed_check"] == "C2_PAGE_NOT_FOUND"


def test_alias_index_scans_once_per_graph_and_refreshes_next_graph(tmp_path, monkeypatch):
    actual = page(tmp_path)
    map_file = route(tmp_path, "if (name === 'LegacyPage') { ActualPageBuilder() }\n"
                     "if (name === 'OtherAlias') { ActualPageBuilder() }")
    graph = EtsRefGraph(tmp_path).build()
    assert vsw._route_alias_file("LegacyPage", graph) == (actual, True)
    with monkeypatch.context() as patch:
        def no_reread(*args, **kwargs):
            raise AssertionError("route index must not reread sources for another IP")
        patch.setattr(Path, "read_text", no_reread)
        assert vsw._route_alias_file("OtherAlias", graph) == (actual, True)
    map_file.write_text(map_file.read_text().replace("LegacyPage", "NewAlias"))
    next_graph = EtsRefGraph(tmp_path).build()
    assert vsw._route_alias_file("LegacyPage", next_graph) == (None, False)
    assert vsw._route_alias_file("NewAlias", next_graph) == (actual, True)


def test_same_filename_resolved_by_slice_scope(tmp_path):
    # AIPPT_830/0909/0910 实测：components/ 与 pages/ 各有一个 RecommendComponent.ets，
    # slice wires.page 已写明 components/ 那个——不能报「未落为文件」。
    want = page(tmp_path, "LegacyPage", "components/LegacyPage.ets")
    page(tmp_path, "LegacyPage", "pages/LegacyPage.ets")
    result = ip(tmp_path, scope_files=[str(want.relative_to(tmp_path))])
    assert result["status"] == "PASS"
    assert result["caller"] == str(want.relative_to(tmp_path))
    assert result["caller_resolved_by"] == "file-in-scope"


def test_ambiguous_same_filename_reports_candidates_not_missing(tmp_path):
    page(tmp_path, path="pages/LegacyPage.ets")
    page(tmp_path, "OtherPage", "views/LegacyPage.ets")
    result = ip(tmp_path)
    assert result["failed_check"] == "C2_PAGE_NOT_FOUND"
    assert result["caller_resolved_by"] == "ambiguous-file"
    assert len(result["candidates"]) == 2
    assert "多个候选" in result["reason"] and "不要再新建" in result["repair_action"]


def test_no_assembly_short_circuits_shared_instance_scan(tmp_path, monkeypatch):
    page(tmp_path)
    graph = EtsRefGraph(tmp_path).build()
    assert graph._assembly_files == []
    def no_resolve(*args, **kwargs):
        raise AssertionError("no AppAssembly in project: must not touch the filesystem")
    monkeypatch.setattr(Path, "resolve", no_resolve)
    assert graph.shared_instance_evidence(tmp_path / E / "pages/Actual.ets", "ActualPage") is None



def test_builder_with_access_modifier_is_found(tmp_path):
    # gpt1030_2 ChoicePPTTemplatePage.ets:32-33：`@Builder\n  private templateCatalog()` 曾报 BUILDER_NOT_FOUND
    assert replacement(tmp_path, "@Builder\n  private content() { ChildPage() }")["status"] == "PASS"


def _shell_and_content(root):
    write(root, E + "pages/ChildPage.ets",
          "@ComponentV2\nexport struct ChildContent {\n  build() { Column() { Text('x') } }\n}\n"
          "@ComponentV2\nexport struct ChildPage {\n"
          "  build() { NavDestination() { ChildContent({ preview: false }) }.hideTitleBar(true) }\n}\n")


def test_embedding_the_wrapped_content_counts_as_the_page(tmp_path):
    # P-29：页面拆成 NavDestination 外壳 + 可嵌入 Content；嵌 Content 就是嵌这个页（gpt1030_2 D-043）
    _shell_and_content(tmp_path)
    got = replacement(tmp_path, "@Builder content() { ChildContent({ preview: true }) }")
    assert got["status"] == "PASS" and got["matched_via"] == "wrapped-content:ChildContent"


def test_unrelated_component_is_still_missing(tmp_path):
    _shell_and_content(tmp_path)
    write(tmp_path, E + "pages/Other.ets", "@ComponentV2\nexport struct OtherContent { build() { Column() {} } }\n")
    got = replacement(tmp_path, "@Builder content() { OtherContent() }")
    assert got["failed_check"] == "C4_REPLACEMENT_NOT_FOUND"


@pytest.mark.parametrize("token", ["F014", "UI", "API"])
def test_non_type_target_tokens_are_not_instantiation_targets(tmp_path, token):
    # gpt1030_2 Group 1：「F014 拥有通用 WebView」「对应 UI 源分支」被当成类名查实例化
    write(tmp_path, E + "pages/Some.ets", "@ComponentV2\nexport struct Some { build() { Column() {} } }\n")
    graph = EtsRefGraph(tmp_path).build()
    entry = IntegrationPoint("x → y", "", token + " 拥有通用能力", None, token, "", False)
    assert vsw._check_single_ip(entry, "ip_001", graph, tmp_path)["status"] == "PASS"



def _cse(root, handler, source):
    from plan_lib.feature_plan_parser import CrossSliceEdit
    write(root, E + "pages/Target.ets", source)
    return vsw._check_single_cse(CrossSliceEdit(E + "pages/Target.ets", handler, "Slice 2"), "cse_001", root)


def test_state_field_handler_counts_as_wired(tmp_path):
    # ds1030 slice 20：对接名是 `@Local searchKeyword` 状态字段，不是方法
    src = "@ComponentV2\nexport struct Target {\n  @Local searchKeyword: string = ''\n  build() { Column() {} }\n}\n"
    assert _cse(tmp_path, "searchKeyword", src)["status"] == "PASS"


def test_field_only_in_comment_is_not_wired(tmp_path):
    src = "@ComponentV2\nexport struct Target {\n  // @Local searchKeyword: string = ''\n  build() { Column() {} }\n}\n"
    assert _cse(tmp_path, "searchKeyword", src)["failed_check"] == "C3_HANDLER_NOT_FOUND"


def test_slash_joined_handlers_are_each_checked(tmp_path):
    src = ("@ComponentV2\nexport struct Target {\n  @Local adSwitch: number = 0\n"
           "  canShow(): boolean { return this.adSwitch > 0 }\n  build() { Column() {} }\n}\n")
    assert _cse(tmp_path, "adSwitch/canShow", src)["status"] == "PASS"
    assert _cse(tmp_path, "adSwitch/missingOne", src)["failed_check"] == "C3_HANDLER_NOT_FOUND"


def test_routed_page_component_counts_as_instantiated(tmp_path):
    # ds1030：PPTFilePage 由路由表 `PPTFilePage()` 渲染，从来不会 `new PPTFilePage(`
    write(tmp_path, E + "pages/FilePage.ets", "@ComponentV2\nexport struct FilePage { build() { NavDestination() {} } }\n")
    write(tmp_path, E + "pages/Map.ets", "import { FilePage } from './FilePage'\n@Builder\nexport function pageMap(name: string) {\n"
                                         "  if (name === 'FilePage') { FilePage() }\n}\n")
    graph = EtsRefGraph(tmp_path).build()
    entry = IntegrationPoint("x → FilePage", "", "FilePage 打开文件", None, "FilePage", "", False)
    got = vsw._check_single_ip(entry, "ip_001", graph, tmp_path)
    assert got["status"] == "PASS" and "rendered" in got.get("note", "")


def test_unrendered_component_still_fails(tmp_path):
    write(tmp_path, E + "pages/FilePage.ets", "@ComponentV2\nexport struct FilePage { build() { NavDestination() {} } }\n")
    graph = EtsRefGraph(tmp_path).build()
    entry = IntegrationPoint("x → FilePage", "", "FilePage 打开文件", None, "FilePage", "", False)
    assert vsw._check_single_ip(entry, "ip_001", graph, tmp_path)["status"] == "FAIL"



def test_object_literal_key_is_not_a_member_field(tmp_path):
    # 对象字面量里的同名键（传给子组件的参数）不是本页的字段
    src = ("@ComponentV2\nexport struct Target {\n  build() {\n    Child({\n      searchKeyword: 'x'\n    })\n  }\n}\n")
    assert _cse(tmp_path, "searchKeyword", src)["failed_check"] == "C3_HANDLER_NOT_FOUND"


def test_class_field_counts_as_member(tmp_path):
    src = "export class TargetVm {\n  private fileList: string[] = []\n}\n"
    assert _cse(tmp_path, "fileList", src)["status"] == "PASS"


def test_shared_component_from_another_file_is_not_the_page(tmp_path):
    # 外壳页包的是别处声明的通用组件（ImmersiveScaffold / AppLoadDialog）：嵌入它不等于嵌入这个页
    write(tmp_path, E + "components/Scaffold.ets", "@ComponentV2\nexport struct Scaffold { build() { Column() {} } }\n")
    write(tmp_path, E + "pages/ChildPage.ets",
          "import { Scaffold } from '../components/Scaffold'\n"
          "@ComponentV2\nexport struct ChildPage {\n  build() { NavDestination() { Scaffold() } }\n}\n")
    got = replacement(tmp_path, "@Builder content() { Scaffold() }")
    assert got["failed_check"] == "C4_REPLACEMENT_NOT_FOUND"



def test_title_bar_in_shell_is_not_the_page(tmp_path):
    # 1018 复查 M6：外壳同时渲染标题栏和内容时，只嵌标题栏不算嵌了页面；嵌 <页名>Content 才算
    write(tmp_path, E + "pages/FeedPage.ets",
          "@ComponentV2\nexport struct FeedTitleBar { build() { Row() {} } }\n"
          "@ComponentV2\nexport struct FeedContent { build() { Column() {} } }\n"
          "@ComponentV2\nexport struct FeedPage {\n  build() { NavDestination() { FeedTitleBar() FeedContent() } }\n}\n")
    write(tmp_path, E + "pages/Host.ets", "@Builder content() { FeedTitleBar() }\n")
    ppr = ParentReplacement(E + "pages/Host.ets", "content", "FeedPage()", "Slice 1")
    assert vsw._check_single_ppr(ppr, "ppr_001", tmp_path)["failed_check"] == "C4_REPLACEMENT_NOT_FOUND"
    write(tmp_path, E + "pages/Host.ets", "@Builder content() { FeedContent() }\n")
    assert vsw._check_single_ppr(ppr, "ppr_001", tmp_path)["matched_via"] == "wrapped-content:FeedContent"


def _registry(root, rows):
    lines = ["| P-ID | location | trigger_condition | status | kind | resolve_by |", "|---|---|---|---|---|---|"]
    lines += [f"| {pid} | {loc} | t | registered | forward-ref | Slice {n} Step 3d |" for pid, loc, n in rows]
    write(root, "spec/placeholder-registry.md", "\n".join(lines) + "\n")


def test_field_handler_with_fwd_ref_marker_still_fails(tmp_path):
    # 1018 复查 M7：字段形态也要查 FWD-REF 残留（精确类）——标记按登记表归到这个字段
    _registry(tmp_path, [("P-S3-001", E + "pages/Target.ets#searchKeyword", 3)])
    src = ("@ComponentV2\nexport struct Target {\n  // FWD-REF: P-S3-001 resolve_by=Slice 3 Step 3a\n"
           "  @Local searchKeyword: string = ''\n  build() { Column() {} }\n}\n")
    assert _cse(tmp_path, "searchKeyword", src)["failed_check"] == "C3_FWD_REF_NOT_REMOVED"


def test_marker_registered_for_another_handler_is_not_counted(tmp_path):
    # 1018 三审 中4：紧挨在上一行、但登记给别的 handler（别的切片）的标记，不算这个字段没清
    _registry(tmp_path, [("P-S7-001", E + "pages/Target.ets#onPay", 7)])
    src = ("@ComponentV2\nexport struct Target {\n  // FWD-REF: P-S7-001 resolve_by=Slice 7 Step 3d\n"
           "  @Local keyword: string = ''\n  onPay() { this.keyword = '' }\n  build() { Column() {} }\n}\n")
    assert _cse(tmp_path, "keyword", src)["status"] == "PASS"


def test_registered_marker_separated_by_decorator_is_still_found(tmp_path):
    _registry(tmp_path, [("P-S3-002", E + "pages/Target.ets#keyword", 3)])
    src = ("@ComponentV2\nexport struct Target {\n  // FWD-REF: P-S3-002 resolve_by=Slice 3 Step 3d\n"
           "  @Trace\n  @Local keyword: string = ''\n  build() { Column() {} }\n}\n")
    assert _cse(tmp_path, "keyword", src)["failed_check"] == "C3_FWD_REF_NOT_REMOVED"


def test_method_branch_only_counts_its_own_marker(tmp_path):
    _registry(tmp_path, [("P-S7-001", E + "pages/Target.ets#onPay", 7), ("P-S3-003", E + "pages/Target.ets:4", 3)])
    other = ("@ComponentV2\nexport struct Target {\n  onSearch(k: string) {\n    this.run(k)\n  }\n"
             "  // FWD-REF: P-S7-001 resolve_by=Slice 7 Step 3d\n  onPay() {}\n  build() { Column() {} }\n}\n")
    assert _cse(tmp_path, "onSearch", other)["status"] == "PASS"
    own = other.replace("    this.run(k)\n", "    // FWD-REF: P-S3-003 resolve_by=Slice 3 Step 3d\n    this.run(k)\n")
    assert _cse(tmp_path, "onSearch", own)["failed_check"] == "C3_FWD_REF_NOT_REMOVED"


def test_empty_default_callback_field_is_skeleton(tmp_path):
    src = ("@ComponentV2\nexport struct Target {\n  @Param onSearch: (k: string) => void = (k: string) => {}\n"
           "  build() { Column() {} }\n}\n")
    assert _cse(tmp_path, "onSearch", src)["failed_check"] == "C3_HANDLER_BODY_SKELETON"
    real = src.replace("(k: string) => {}", "(k: string) => { this.run(k) }")
    assert _cse(tmp_path, "onSearch", real)["status"] == "PASS"



def test_page_content_and_body_names_are_page_bodies(tmp_path):
    # 1018 二审 #6：`FeedPageContent` 与按条件渲染的 `FeedBody` 都是页面主体
    write(tmp_path, E + "pages/FeedPage.ets",
          "@ComponentV2\nexport struct FeedTitleBar { build() { Row() {} } }\n"
          "@ComponentV2\nexport struct FeedPageContent { build() { Column() {} } }\n"
          "@ComponentV2\nexport struct FeedLoading { build() { Column() {} } }\n"
          "@ComponentV2\nexport struct FeedBody { build() { Column() {} } }\n"
          "@ComponentV2\nexport struct FeedPage {\n  build() { NavDestination() { FeedTitleBar() FeedPageContent()\n"
          "    if (this.loading) { FeedLoading() } else { FeedBody() } } }\n}\n")
    ppr = ParentReplacement(E + "pages/Host.ets", "content", "FeedPage()", "Slice 1")
    for body in ("FeedPageContent()", "FeedBody()"):
        write(tmp_path, E + "pages/Host.ets", "@Builder content() { " + body + " }\n")
        vsw._struct_cache.clear()
        assert vsw._check_single_ppr(ppr, "ppr_001", tmp_path)["status"] == "PASS", body
    write(tmp_path, E + "pages/Host.ets", "@Builder content() { FeedTitleBar() }\n")
    vsw._struct_cache.clear()
    assert vsw._check_single_ppr(ppr, "ppr_001", tmp_path)["status"] == "FAIL"


def test_unrelated_fwd_ref_below_field_is_not_counted(tmp_path):
    # 1018 二审 #7：字段下一行是给别的 handler 的 FWD-REF，不算到这个字段头上
    src = ("@ComponentV2\nexport struct Target {\n  @Local keyword: string = ''\n"
           "  // FWD-REF: P-S7-001 resolve_by=Slice 7 Step 3d onPay\n  build() { Column() {} }\n}\n")
    assert _cse(tmp_path, "keyword", src)["status"] == "PASS"


def test_passed_through_event_is_not_skeleton(tmp_path):
    src = ("@ComponentV2\nexport struct Target {\n  @Event onSearch: (k: string) => void = (k: string) => {}\n"
           "  build() { Child({ onSearch: this.onSearch }) }\n}\n")
    assert _cse(tmp_path, "onSearch", src)["status"] == "PASS"
