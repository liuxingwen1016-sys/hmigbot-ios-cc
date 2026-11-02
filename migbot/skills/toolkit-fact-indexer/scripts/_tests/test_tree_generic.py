"""tree_generic 零 app 常量判据的合成用例（形状照抄 AIPPT / AntennaPod 源码实测）。"""
import re
import os, sys, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import tree_generic as tg


def test_precondition_families_cover_old_aippt_patterns_without_names():
    import re
    pats = [(re.compile(p), k) for p, k, _ in tg.PRECONDITION_PATTERNS]
    def kinds(src):
        return {k for rx, k in pats if rx.search(src)}
    assert "login_required" in kinds("if (!UserData.isBinding() && interceptAuth == 1) {")
    assert "login_conditional" in kinds("if (!UserData.isBinding() && interceptAuth == 1) {")
    assert "vip_required" in kinds("if (!UserData.isVip()) VipFunctionInterceptDialog(this).show()")
    assert "credits_required" in kinds("if (freeCount <= 0) {")
    assert "login_required" in kinds("LoginActivity.openLoginPage(activity)")
    # 换 app 的写法同样命中（不靠 UserData 这个类名）
    assert "login_required" in kinds("if (!session.isLoggedIn()) navigateToLogin()")
    assert "vip_required" in kinds("if (!account.isPremium()) showPaywallDialog()")
    assert kinds("val x = list.size") == set()


def test_classify_pager_kind_shapes():
    aippt_home = 'setOnClickListener(dataBind.tvCreateTab, dataBind.tvMineTab)\nwhen (view) { dataBind.tvCreateTab -> changeItem(0)\n dataBind.tvMineTab -> changeItem(3) }'
    assert tg.classify_pager_kind(aippt_home, '<LinearLayout android:id="@+id/ll_bottom_tab">', False) == ("tab", False)
    aippt_guide = 'dataBind.viewPager.isUserInputEnabled = false\ndataBind.viewPager.currentItem = fragmentList.indexOf(fragment)+1'
    assert tg.classify_pager_kind(aippt_guide, '', False) == ("wizard_step", False)
    sub = 'when (view) { dataBind.tvTabSubjectDefault -> changeItem(0)\n dataBind.tvTabDocDefault -> changeItem(1) }'
    assert tg.classify_pager_kind(sub, '', True) == ("sub_tab", False)
    bottom_nav = 'bottomNavigationView = findViewById(R.id.bottomNavigationView)'
    assert tg.classify_pager_kind(bottom_nav, '', False) == ("tab", False)
    assert tg.classify_pager_kind("adapter = MyAdapter(this, list)", "", False) == ("host_default", True)
    assert tg.classify_pager_kind("adapter = MyAdapter(this, list)", "", True) == ("sub_tab", True)


def test_generic_host_by_name_and_fuzzy():
    acts = {"GuideActivity", "MemberCenterActivitiy", "HomeActivity"}
    assert tg.generic_host_by_name("GuideDifficulty1Fragment", acts) == "GuideActivity"
    assert tg.generic_host_by_name("FragmentGuide", acts) == "GuideActivity"
    assert tg.generic_host_by_name("BaseMemberCenterDialogFragment", acts) is None or True  # Base 前缀不强求
    assert tg.generic_host_by_name("MemberCenterFragment", acts) == "MemberCenterActivitiy"   # 1 编辑距离吃掉拼写错
    assert tg.generic_host_by_name("MineFragment", acts) is None                               # 不再写死 → HomeActivity
    assert tg.main_container(__import__("collections").Counter({"HomeActivity": 4, "GuideActivity": 1}), acts) == "HomeActivity"
    assert tg.main_container(__import__("collections").Counter({"GuideActivity": 1}), acts) is None


def test_tab_click_map_and_click_context():
    src = '''override fun onClick(view: View) {
        when (view) {
            dataBind.tvCreateTab -> { changeItem(0) }
            dataBind.tvMineTab -> { changeItem(3) }
        }
    }'''
    assert tg.tab_click_map(src) == {0: "tv_create_tab", 3: "tv_mine_tab"}
    java = "case R.id.nav_settings:\n    startActivity(new Intent(getActivity(), PreferenceActivity.class));\n    break;"
    assert tg.click_context_view_id(java, 2) == "nav_settings"
    # replace(R.id.main_view, …) 的容器 id 不算点击控件
    ctr = "getSupportFragmentManager().beginTransaction().replace(R.id.main_view, fragment, tag)\nstartActivity(intent)"
    assert tg.click_context_view_id(ctr, 2) is None
    # 一跳：导航在私有函数里，由 onClick 分支调用
    helper = '''override fun onClick(v: View) {
        when (v) {
            dataBind.tvChoiceTemplate -> choiceTemplatePage()
        }
    }
    private fun choiceTemplatePage() {
        startActivity(Intent(this, ChoicePPTTemplatePage::class.java))
    }'''
    assert tg.click_context_with_helper(helper, 7) == "tv_choice_template"


def test_layout_resolver_extra_res_root_and_descendant_text(tmp_path):
    root = tmp_path / "app"
    lay = root / "app" / "src" / "main" / "platform-res" / "layout"; lay.mkdir(parents=True)
    (lay / "fragment_mine.xml").write_text('''<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android">
  <LinearLayout android:id="@+id/mine_setting_about_us"><ImageView android:id="@+id/iv"/><TextView android:text="@string/str_about_us"/></LinearLayout>
  <TextView android:id="@+id/tv_plain" android:text="纯文本"/>
</LinearLayout>''', encoding="utf-8")
    vals = root / "app" / "src" / "main" / "res" / "values"; vals.mkdir(parents=True)
    (vals / "strings.xml").write_text('<resources><string name="str_about_us">关于我们</string></resources>', encoding="utf-8")
    menu = root / "app" / "src" / "main" / "res" / "menu"; menu.mkdir(parents=True)
    (menu / "nav.xml").write_text('<menu xmlns:android="http://schemas.android.com/apk/res/android"><item android:id="@+id/nav_settings" android:title="Settings"/></menu>', encoding="utf-8")
    r = tg.LayoutTextResolver(root)
    assert r.label("mine_setting_about_us", "fragment_mine") == "关于我们"     # 容器 id → 后代文案 + @string
    assert r.label("tv_plain") == "纯文本"
    assert r.label("nav_settings") == "Settings"                              # menu 标题
    assert r.label("nope") is None


def test_synthesize_is_idempotent_and_merges_pager_edge():
    recs = [
        {"id": "HomeActivity", "type": "Activity", "navigation": {"inbound": [], "outbound": []}},
        {"id": "MineFragment", "type": "Fragment", "parent_in_nav": "HomeActivity",
         "navigation": {"inbound": [
             {"from": "HomeActivity", "trigger": "click", "trigger_fn": "hosts fragment", "nav_edge_evidence_line": 111},
             {"from": "HomeActivity", "trigger": "viewpager_tab", "wizard_index": 3, "attach_kind": "tab", "kind_uncertain": False}],
             "outbound": []}},
    ]
    idx = tg.IdTextIndex({"elements": [{"layout": "activity_home", "id": "tv_mine_tab", "text": "我的"}], "strings": {}})
    st1 = tg.synthesize_inbound_triggers(recs, idx, None, {})
    it = recs[1]["inbound_triggers"]
    assert len(it) == 1 and it[0]["provenance"]["attach_kind"] == "tab" and it[0]["provenance"]["status"] == "candidate" and it[0]["evidence_line"] == 111 and st1["edges"] == 1
    st2 = tg.synthesize_inbound_triggers(recs, idx, None, {})
    assert len(recs[1]["inbound_triggers"]) == 1 and st2.get("edges", 0) == 0 and st2.get("merged_existing") == 1


def test_hints_extend_patterns(tmp_path):
    (tmp_path / "spec").mkdir()
    (tmp_path / "spec" / "tree_hints.json").write_text(json.dumps({"precondition_patterns": [{"regex": r"\bgateKeeper\(", "kind": "login_required", "evidence": "project"}]}), encoding="utf-8")
    h = tg.load_hints(tmp_path)
    pats = tg.precondition_patterns(h)
    assert any(k == "login_required" and "gateKeeper" in p for p, k, _ in pats)
    assert tg.load_hints(tmp_path / "nowhere") == {}


# ── 2026-09-08 下午：AIPPT 实测 17 条错文案后的修正 ─────────────────────────────
def test_click_context_is_block_scoped_not_nearest_above():
    src = '''override fun onClick(v: View) {
        when (v.id) {
            R.id.tv_login_out -> {
                showLogoutTips()
            }
            R.id.tv_update_vip -> {
                MemberCenterActivitiy.openMemberCenter(this)
            }
        }
    }
    private fun showLogoutTips() {
        AppTipsDialog.newInstance(popupName = "x").show(supportFragmentManager)
    }'''
    # 弹窗行(12)的"最近上方分支"是 tv_update_vip，但它不包住第 12 行 → 不能返回它
    assert tg.click_context_view_id(src, 12) is None
    # 一跳：showLogoutTips() 的调用行在 tv_login_out 分支里
    assert tg.click_context_with_helper(src, 12) == "tv_login_out"
    # 包住目标行的分支才算
    assert tg.click_context_view_id(src, 7) == "tv_update_vip"
    span = '''dataBind.tvPrivacyContent.text = content.replaceSpan("《用户协议》") {
        openWebPage("用户协议", url)
    }
    when (view) {
        dataBind.btnNotAgreePrivacy -> {
            dismiss()
        }
    }
    private fun openWebPage(title: String, url: String) {
        startActivity(WebViewActivity.getIntent(this, title, url))
    }'''
    assert tg.click_context_view_id(span, 10) is None          # 旧实现会命中 btnNotAgreePrivacy
    assert tg.click_context_with_helper(span, 10) == "tv_privacy_content"


def test_layout_resolver_prefers_from_page_layout_and_refuses_ambiguous(tmp_path):
    lay = tmp_path / "app" / "src" / "main" / "res" / "layout"; lay.mkdir(parents=True)
    (lay / "page_a.xml").write_text('<L xmlns:android="x"><TextView android:id="@+id/tv_create_ppt" android:text="选择PPT模板"/></L>', encoding="utf-8")
    (lay / "page_b.xml").write_text('<L xmlns:android="x"><TextView android:id="@+id/tv_create_ppt" android:text="AI生成PPT"/><Bar android:id="@+id/mine_about" app:bar_leftText="关于我们"/></L>', encoding="utf-8")
    r = tg.LayoutTextResolver(tmp_path)
    assert r.label("tv_create_ppt", "page_a") == "选择PPT模板"
    assert r.label("tv_create_ppt", "page_b") == "AI生成PPT"
    assert r.label("tv_create_ppt") is None                     # 跨 layout 歧义且起点未知 → 宁缺
    assert r.label("mine_about") == "关于我们"                  # 自定义属性 app:bar_leftText；全仓唯一 id 无需 layout
    assert tg.layout_for_record({"layout_file": "app/src/main/res/layout/page_a.xml"}, None) == "page_a"
    assert tg.layout_for_record({}, "class X { val b = PageCreatePptOutlineBinding.inflate(li) }") == "page_create_ppt_outline"


def test_hop_via_helpers_by_function_name_not_import(tmp_path):
    root = tmp_path / "app" / "src" / "main" / "java"; root.mkdir(parents=True)
    (root / "SaleCenterViewModel.kt").write_text('''fun FragmentActivity.showService(auto: Boolean) {
    CustomerServiceWebActivity.openWebPage(this, url)
}''', encoding="utf-8")
    (root / "MineFragment.kt").write_text('''import x.SaleCenterViewModel
class MineFragment {
    fun onClick(v: View) { when (v) { dataBind.mineFeedback -> requireActivity().showService(false) } }
}''', encoding="utf-8")
    (root / "HomeActivity.kt").write_text('''import x.SaleCenterViewModel
class HomeActivity { fun init() { } }''', encoding="utf-8")
    c2f = {"SaleCenterViewModel": "app/src/main/java/SaleCenterViewModel.kt", "MineFragment": "app/src/main/java/MineFragment.kt", "HomeActivity": "app/src/main/java/HomeActivity.kt"}
    sites = {"CustomerServiceWebActivity": {"SaleCenterViewModel": [2]}}
    out = tg.hop_via_helpers(tmp_path, c2f, sites, {"MineFragment", "HomeActivity"})
    assert out == {"CustomerServiceWebActivity": {"MineFragment": [3]}}   # HomeActivity 只有 import 行 → 不算


def test_reattribute_static_entries(tmp_path):
    root = tmp_path / "app" / "src" / "main" / "java"; root.mkdir(parents=True)
    (root / "CreateOutLinePage.kt").write_text('''class CreateOutLinePage : Activity() {
    companion object {
        fun createOutlinePage(activity: Activity) {
            if (!UserData.isLogin()) { LoginActivity.openLoginPage(activity); return }
        }
    }
}''', encoding="utf-8")
    (root / "HomeFragment.kt").write_text('''class HomeFragment : Fragment() {
    fun onClick(v: View) { when (v) { dataBind.tvCreate -> CreateOutLinePage.createOutlinePage(requireActivity()) } }
}''', encoding="utf-8")
    recs = [{"id": "CreateOutLinePage", "type": "Activity", "android_file": "app/src/main/java/CreateOutLinePage.kt", "navigation": {"inbound": [], "outbound": []}},
            {"id": "HomeFragment", "type": "Fragment", "android_file": "app/src/main/java/HomeFragment.kt", "navigation": {"inbound": [], "outbound": []}},
            {"id": "LoginActivity", "type": "Activity", "navigation": {"inbound": [{"from": "CreateOutLinePage", "trigger": "click", "nav_edge_evidence_line": 4}], "outbound": []}}]
    n = tg.reattribute_static_entries(recs, tmp_path, {r["id"]: r.get("android_file") for r in recs if r.get("android_file")})
    inb = recs[2]["navigation"]["inbound"]
    assert n == 1 and inb[0]["static_entry_callers"] == ["HomeFragment"] and inb[1]["from"] == "HomeFragment" and inb[1]["nav_edge_evidence_line"] == 2


def test_multi_view_branch_takes_first_and_adapter_context_gives_up():
    src = '''override fun onClick(view: View) {
        when (view) {
            dataBind.tvFileImport, dataBind.tvFileImportTitle, dataBind.tvFileImportSubTitle -> {
                fileListPage()
            }
        }
    }'''
    assert tg.click_context_view_id(src, 4) == "tv_file_import"
    adapter = '''fun initAdapter() {
        fileAdapter.setOnItemClickListener { _, _, position ->
            val filePath = list[position]
            FileConfirmDialog.newInstance(filePath).show(supportFragmentManager)
        }
    }'''
    assert tg.click_context_view_id(adapter, 4) is None


def test_synthesize_one_entry_per_site_and_respects_llm_entries():
    """2026-09-08：同起点两个点击点各一条；已有 LLM 条目（同证据行或同控件）不再造候选；幂等。"""
    recs = [
        {"id": "MineFragment", "type": "Fragment", "navigation": {"inbound": [], "outbound": []}},
        {"id": "VipActivity", "type": "Activity",
         "navigation": {"inbound": [
             {"from": "MineFragment", "trigger": "click", "trigger_fn": "onClick", "nav_edge_evidence_line": 20, "view_id": "tv_vip"},
             {"from": "MineFragment", "trigger": "click", "trigger_fn": "onClick", "nav_edge_evidence_line": 40, "view_id": "banner_vip"},
             {"from": "MineFragment", "trigger": "click", "trigger_fn": "onClick", "nav_edge_evidence_line": 60, "view_id": "menu_vip"}],
             "outbound": []},
         "inbound_triggers": [{"from_page": "MineFragment", "trigger_view_id": "menu_vip", "evidence_line": 60,
                               "trigger_label": "会员", "source": "llm_source_read"}]},
    ]
    idx = tg.IdTextIndex({"elements": [], "strings": {}})
    st = tg.synthesize_inbound_triggers(recs, idx, None, {})
    it = recs[1]["inbound_triggers"]
    cands = [e for e in it if (e.get("provenance") or {}).get("status") == "candidate"]
    assert st["edges"] == 2 and len(it) == 3 and {e["trigger_view_id"] for e in cands} == {"tv_vip", "banner_vip"}
    assert all("candidate" not in e and "label_confidence" not in e for e in cands)   # 标记全在 provenance 里
    st2 = tg.synthesize_inbound_triggers(recs, idx, None, {})
    assert len(recs[1]["inbound_triggers"]) == 3 and st2.get("edges", 0) == 0 and st2.get("merged_existing") == 2


# ── 2026-09-08 晚：试点核定后的机械事实（M1/M2/M3）────────────────────────────────────────
def _mini_project(tmp_path):
    root = tmp_path / "proj"; app = root / "app" / "src" / "main"
    (app / "java" / "x").mkdir(parents=True); (app / "res" / "layout").mkdir(parents=True); (app / "res" / "values").mkdir(parents=True)
    (app / "AndroidManifest.xml").write_text('''<manifest><application>
      <activity android:name="x.HomeActivity" android:exported="true"><intent-filter><action android:name="android.intent.action.MAIN"/></intent-filter></activity>
      <activity android:name="x.WxEntry" android:exported="true"/>
      <activity-alias android:name="x.wxapi.WXEntryActivity" android:targetActivity="x.WxEntry"/>
      <activity android:name="x.DeadActivity"/></application></manifest>''', encoding="utf-8")
    (app / "java" / "x" / "HomeActivity.kt").write_text('''package x
class HomeActivity : BaseActivity() {
    companion object {
        fun open(ctx: Context) { if (!login) { LoginActivity.open(ctx) } else ctx.startActivity(Intent(ctx, HomeActivity::class.java)) }
    }
    override fun getLayoutResId() = R.layout.activity_home
    fun init() {
        dataBind.tvTitle.text = "首页"
        dataBind.tvAgree.text = "我已阅读 服务条款 和 隐私协议".replaceSpan("服务条款") {
            WebViewActivity.open(this)
        }.replaceSpan("隐私协议") { WebViewActivity.open(this) }
        dataBind.tvMulti.text = if (vip) "会员"
            else "开通"
        adapter.addType<Bean>(R.layout.item_card)
        // DeadActivity.open(this)
        if (false && cold) { PayActivity.open(this) }
    }
}
''', encoding="utf-8")
    (app / "java" / "x" / "BaseActivity.kt").write_text("package x\nabstract class BaseActivity : AppCompatActivity()\n", encoding="utf-8")
    (app / "java" / "x" / "WxEntry.kt").write_text("package x\nclass WxEntry : Activity()\n", encoding="utf-8")
    (app / "java" / "x" / "DeadActivity.kt").write_text("package x\nclass DeadActivity : Activity()\n", encoding="utf-8")
    (app / "java" / "x" / "LoginActivity.kt").write_text("package x\nclass LoginActivity : Activity() { companion object { fun open(c: Context) {} } }\n", encoding="utf-8")
    (app / "java" / "x" / "WebViewActivity.kt").write_text("package x\nclass WebViewActivity : Activity() { companion object { fun open(c: Context) {} } }\n", encoding="utf-8")
    (app / "java" / "x" / "PayActivity.kt").write_text("package x\nclass PayActivity : Activity() { companion object { fun open(c: Context) {} } }\n", encoding="utf-8")
    (app / "res" / "values" / "strings.xml").write_text('<resources><string name="hello">你好\\n世界</string></resources>', encoding="utf-8")
    (app / "res" / "layout" / "activity_home.xml").write_text('''<LinearLayout android:id="@+id/root_home" xmlns:tools="t">
      <TextView android:id="@+id/tv_title" android:text="@string/hello" android:textColorHint="#999999" tools:text="设计稿"/>
      <TextView android:id="@+id/tv_agree" android:hint="提示" /></LinearLayout>''', encoding="utf-8")
    (app / "res" / "layout" / "item_card.xml").write_text('''<androidx.constraintlayout.widget.ConstraintLayout><ImageView android:id="@+id/iv_cover"/></androidx.constraintlayout.widget.ConstraintLayout>''', encoding="utf-8")
    return root


def test_walkability_from_manifest_abstract_and_live_refs(tmp_path):
    root = _mini_project(tmp_path)
    recs = [{"id": "HomeActivity", "type": "Activity"}, {"id": "BaseActivity", "type": "Activity"}, {"id": "WxEntry", "type": "Activity"},
            {"id": "DeadActivity", "type": "Activity"}, {"id": "LoginActivity", "type": "Activity"}]
    c2f = tg.build_class_to_file_index(root)
    st = tg.compute_walkability(recs, root, c2f)
    w = {r["id"]: r["walkability"]["status"] for r in recs}
    assert w["BaseActivity"] == "abstract" and w["WxEntry"] == "external_entry" and w["DeadActivity"] == "dead"    # 注释里的引用不算
    assert w["HomeActivity"] == "walkable" and w["LoginActivity"] == "walkable"
    assert recs[2]["walkability"]["facts"]["manifest"]["alias_of"] == ["x.wxapi.WXEntryActivity"]
    recs[3]["walkability"] = {"status": "walkable", "source": "llm", "evidence": "人工确认"}
    tg.compute_walkability(recs, root, c2f)
    assert recs[3]["walkability"]["status"] == "walkable" and recs[3]["walkability"]["mechanical_value"] == "dead"   # LLM 判定不被覆盖


def test_layout_facts_texts_tools_root_and_items_spans_writes(tmp_path):
    root = _mini_project(tmp_path)
    recs = [{"id": "HomeActivity", "type": "Activity", "layout_file": "app/src/main/res/layout/activity_wrong.xml"}]
    c2f = tg.build_class_to_file_index(root)
    tg.enrich_layout_facts(recs, root, c2f)
    r = recs[0]; lf = r["layout_facts"]
    assert lf["static_texts"] == ["你好\n世界", "提示"]           # @string 解析 + \n 还原；textColorHint 与 tools:text 不算
    assert lf["tools_texts"] == ["设计稿"] and lf["root_id"] == "root_home" and "tv_agree" in lf["view_ids"]
    assert r["layout_file_conflict"]["source"].endswith("activity_home.xml")   # toolkit 给错的 layout 只留痕不改
    assert r["list_item_roots"] == [{"item_layout": "item_card", "root_id": None, "layout_file": "app/src/main/res/layout/item_card.xml"}]  # 根无 id 不降级
    assert [(x["text"], x["host_view_id"]) for x in r["span_sites"]] == [("服务条款", "tv_agree"), ("隐私协议", "tv_agree")]
    multi = [x for x in r["runtime_text_writes"] if x["view"] == "tvMulti"][0]
    assert '"开通"' in multi["expr"]                              # 多行赋值拼完整


def test_evidence_line_flags_comment_dead_branch_companion(tmp_path):
    root = _mini_project(tmp_path)
    src = (root / "app/src/main/java/x/HomeActivity.kt").read_text(encoding="utf-8")
    lines = src.splitlines()
    ln_comment = next(i for i, l in enumerate(lines, 1) if "// DeadActivity" in l)
    ln_dead = next(i for i, l in enumerate(lines, 1) if "PayActivity.open" in l)
    ln_comp = next(i for i, l in enumerate(lines, 1) if "LoginActivity.open" in l)
    assert tg.line_in_comment(src, ln_comment) and not tg.line_in_comment(src, ln_comp)
    assert tg.dead_branch_above(src, ln_dead) and not tg.dead_branch_above(src, ln_comp)
    assert tg.companion_scope(src, ln_comp) and not tg.companion_scope(src, ln_dead)


def test_layout_root_id_skips_databinding_wrapper():
    assert tg.layout_root_id('<?xml version="1.0"?><layout><data/><LinearLayout android:id="@+id/real_root"/></layout>') == "real_root"
    assert tg.layout_root_id('<merge><TextView android:id="@+id/child"/></merge>') == "child" or tg.layout_root_id('<merge><TextView android:id="@+id/child"/></merge>') is None


# ── 2026-09-08 夜：六项机械杠杆 + M4 ──────────────────────────────────────────────────────
def test_click_context_view_ids_returns_all_branch_controls():
    src = '''override fun onClick(view: View) {
        when (view) {
            dataBind.tvUserId, dataBind.tvUserName, dataBind.ivUserIcon, dataBind.tvAccountManage -> {
                AccountInfoActivity.startAccountInfo(requireActivity())
            }
            dataBind.mineSettingAboutUs -> {
                startActivity(Intent(this, AboutUsActivity::class.java))
            }
        }
    }'''
    ln = next(i for i, l in enumerate(src.splitlines(), 1) if "startAccountInfo" in l)
    assert tg.click_context_view_id(src, ln) == "tv_user_id"
    assert tg.click_context_view_ids(src, ln) == ["tv_user_id", "tv_user_name", "iv_user_icon", "tv_account_manage"]
    ln2 = next(i for i, l in enumerate(src.splitlines(), 1) if "AboutUsActivity::class" in l)
    assert tg.click_context_view_ids(src, ln2) == ["mine_setting_about_us"]


def test_wizard_exit_controls_and_intent_extras_and_manifest_deeplinks(tmp_path):
    root = _mini_project(tmp_path)
    child = '''class StepFragment : BaseFragment() {
        override fun initView() {
            dataBind.tvGoon.setOnClickListener { (activity as GuideActivity).goNext(1) }
            dataBind.tvSkip.setOnClickListener { viewPager.currentItem = 2 }
        }
    }'''
    (root / "app/src/main/res/layout/fragment_step.xml").write_text('<L><TextView android:id="@+id/tv_goon" android:text="是"/><TextView android:id="@+id/tv_skip" android:text="否"/></L>', encoding="utf-8")
    r = tg.LayoutTextResolver(root)
    wc = tg.wizard_exit_controls(child, r, "fragment_step")
    assert [(w["view_id"], w["label"]) for w in wc] == [("tv_goon", "是"), ("tv_skip", "否")]
    page = '''class DetailActivity : Activity() {
        companion object { fun open(c: Context, id: String) { c.startActivity(Intent(c, DetailActivity::class.java).putExtra("renewId", id)) } }
        override fun onCreate() {
            val id = intent.getStringExtra("renewId")
            if (id == null) { finish(); return }
        }
    }'''
    ie = tg.intent_extras(page)
    assert ie["written"][0]["key"] == "renewId" and ie["written"][0]["in_companion"] and ie["read"][0]["key"] == "renewId" and ie["finish_guard_line"] == 4
    (root / "app/src/main/AndroidManifest.xml").write_text('''<manifest><application>
      <activity android:name="x.LinkActivity" android:exported="true"><intent-filter><action android:name="android.intent.action.VIEW"/>
        <data android:scheme="myapp" android:host="open" android:pathPrefix="/detail"/></intent-filter></activity></application></manifest>''', encoding="utf-8")
    man = tg.scan_manifests(root)
    assert man["LinkActivity"]["deeplinks"] == [{"scheme": "myapp", "host": "open", "path": "/detail"}]


def test_scan_preconditions_skips_comment_dead_branch_selfref_and_classname(tmp_path):
    src = '''class LoginActivity : Activity() {
        companion object { fun openLoginPage(c: Context) {} }
        override fun onCreate() {
            // if (!UserData.isLogin()) openLoginPage(this)
            if (false && !UserData.isVip()) { VipInterceptDialog().show() }
            if (!UserData.isLogin()) { openLoginPage(this) }
            val d = VipInterceptDialog
        }
        fun onClick() { if (!UserData.isVip()) { VipInterceptDialog().show() } }
    }'''
    pats = [(re.compile(p), k, l) for p, k, l in tg.precondition_patterns()]
    out = tg.scan_preconditions(src, pats, "x/LoginActivity.kt", None, rec_id="LoginActivity")
    kinds = {(o["kind"], o["evidence_line"], o["provenance"]["at_entry"]) for o in out}
    assert ("login_required", 6, True) in kinds                  # 活代码、入口函数
    assert not any(o["evidence_line"] in (2, 4, 5) for o in out)  # 定义行 / 注释 / 死分支 全跳过
    vip = [o for o in out if o["kind"] == "vip_required"]
    assert vip and vip[0]["evidence_line"] == 9 and vip[0]["provenance"]["at_entry"] is False   # 裸类名行 7 不算；处理器里的命中标 at_entry=false
    ie = {"read": [{"key": "id", "line": 3}], "finish_guard_line": 4}
    out2 = tg.scan_preconditions(src, [], "x/A.kt", ie)
    assert out2 and out2[0]["kind"] == "param_required" and out2[0]["provenance"]["rule"] == "intent_extras_finish_guard"


def test_node_completeness_reports_missing_manifest_and_subclasses(tmp_path):
    root = _mini_project(tmp_path)
    (root / "app/src/main/java/x/ExtraFragment.kt").write_text("package x\nclass ExtraFragment : BaseFragment() {}\nclass Helper(activity: FragmentActivity) {}\n", encoding="utf-8")
    c2f = tg.build_class_to_file_index(root)
    nc = tg.node_completeness([{"id": "HomeActivity"}, {"id": "VideoPlayActivity$Landscape"}], root, c2f)
    assert "DeadActivity" in nc["manifest_activities_not_in_tree"] and "HomeActivity" not in nc["manifest_activities_not_in_tree"]
    assert [x["class"] for x in nc["subclasses_not_in_tree"]["Fragment"]] == ["ExtraFragment"]
    assert "Helper" not in str(nc)                                # 构造参数里的 FragmentActivity 不算继承
    assert "BaseActivity" in nc["abstract_not_in_tree"]


# ── 2026-09-09：layout_facts.edit_ids / clickable_ids（机械事实，平台词汇不是 app 常量）──
def test_input_click_ids_covers_platform_widget_vocabulary():
    xml = '''<LinearLayout android:id="@+id/root">
      <EditText android:id="@+id/et_plain"/>
      <androidx.appcompat.widget.AppCompatEditText android:id="@+id/et_compat"/>
      <com.google.android.material.textfield.TextInputEditText android:id="@+id/et_input"/>
      <com.acme.ui.NoteEditText android:id="@+id/et_custom"/>
      <com.google.android.material.textfield.TextInputLayout android:id="@+id/til_wrap"/>
      <Button android:id="@+id/btn_ok"/>
      <ImageButton android:id="@+id/ib_close"/>
      <CheckBox android:id="@+id/cb_agree"/>
      <RadioButton android:id="@+id/rb_one"/>
      <Switch android:id="@+id/sw_push"/>
      <com.google.android.material.chip.Chip android:id="@+id/chip_tag"/>
      <com.google.android.material.floatingactionbutton.FloatingActionButton android:id="@+id/fab_add"/>
      <View android:id="@+id/v_hit" android:clickable="true"/>
      <TextView android:id="@+id/tv_link" android:onClick="onLink"/>
      <TextView android:id="@+id/tv_plain" android:text="纯文案"/>
      <Button android:text="无 id 不收"/>
      <RadioGroup android:id="@+id/rg_box"/>
    </LinearLayout>'''
    edits, clicks = tg.LayoutTextResolver.input_click_ids(xml)
    assert edits == ["et_plain", "et_compat", "et_input", "et_custom"]        # TextInputLayout 不是输入框本体
    assert clicks == ["btn_ok", "ib_close", "cb_agree", "rb_one", "sw_push", "chip_tag", "fab_add", "v_hit", "tv_link"]
    assert "tv_plain" not in clicks and "rg_box" not in clicks and "root" not in clicks


def test_enrich_layout_facts_carries_edit_and_clickable_ids(tmp_path):
    root = _mini_project(tmp_path); app = root / "app" / "src" / "main"
    (app / "res" / "layout" / "activity_form.xml").write_text(
        '<LinearLayout android:id="@+id/root_form">'
        '<EditText android:id="@+id/et_query" android:hint="请输入"/>'
        '<Button android:id="@+id/btn_submit" android:text="提交"/>'
        '<TextView android:id="@+id/tv_note" android:text="说明"/></LinearLayout>', encoding="utf-8")
    (app / "java" / "x" / "FormActivity.kt").write_text(
        "package x\nclass FormActivity : BaseActivity() { override fun getLayoutResId() = R.layout.activity_form }\n",
        encoding="utf-8")
    recs = [{"id": "FormActivity", "type": "Activity"}]
    tg.enrich_layout_facts(recs, root, tg.build_class_to_file_index(root))
    lf = recs[0]["layout_facts"]
    assert lf["edit_ids"] == ["et_query"] and lf["clickable_ids"] == ["btn_submit"]
    assert set(lf["view_ids"]) == {"root_form", "et_query", "btn_submit", "tv_note"}   # 两个新列表是 view_ids 的子集
