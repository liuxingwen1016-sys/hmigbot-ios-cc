import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import dialog_inventory as di  # noqa: E402


class DialogInventoryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        src = self.root / "app/src/main/java/com/example"
        src.mkdir(parents=True)
        (src / "Dialogs.java").write_text(r'''
package com.example;
import androidx.fragment.app.Fragment;
import androidx.appcompat.app.AppCompatDialogFragment;
import com.google.android.material.bottomsheet.BottomSheetDialogFragment;
class HostFragment extends Fragment {
  void open() {
    ChildSortDialog d = new ChildSortDialog();
    new ChildSortDialog().show(getChildFragmentManager().beginTransaction(), "sort");
    DirectDialog.newInstance().show(getChildFragmentManager(), "d");
    new ConfirmBase() { void ok() {} }.createNewDialog().show();
    ExtendedHelper.showDialog();
    ExtendedHelper helper = new ExtendedHelper(); helper.openPanel();
  }
}
class DirectDialog extends AppCompatDialogFragment {
  static DirectDialog newInstance() { return new DirectDialog(); }
}
class BaseSortDialog extends BottomSheetDialogFragment {
  Object onCreateView() { return SortDialogBinding.inflate(inflater); }
}
class ChildSortDialog extends BaseSortDialog {}
abstract class ConfirmBase {
  Object createNewDialog() { return new MaterialAlertDialogBuilder(ctx).create(); }
}
class ExtendedHelper {
  void showDialog() { new MaterialAlertDialogBuilder(ctx).setView(R.layout.dialog_extended).show(); }
  void openPanel() { new MaterialAlertDialogBuilder(ctx).show(); }
}
class HelperChild extends ExtendedHelper {}
class LayoutPatterns extends AppCompatDialogFragment {
  void showPanel() { View.inflate(ctx, R.layout.dialog_view, null); HelperBinding.inflate(inflater); }
}
class EmbeddedD extends AppCompatDialogFragment {}
class EmbeddedHostFragment extends Fragment {
  void mount() { transaction.add(R.id.slot, new EmbeddedD()); }
}
class NotADialogController {
  private void showMessage() { new MaterialAlertDialogBuilder(ctx).show(); }
}
''', encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_kotlin_nested_generic_host_and_neighbor_classes(self):
        src = self.root / "app/src/main/java/com/example/Generic.kt"
        src.write_text("""
package com.example
import androidx.appcompat.app.AppCompatActivity
import androidx.appcompat.app.AppCompatDialogFragment
abstract class GenericBase<VM : BaseViewModel<*>, DB : BaseBinding<*>> : AppCompatActivity()
class GenericHost : GenericBase<WeatherVM, WeatherBinding>() {
 fun open() { GenericDialog().show(supportFragmentManager, "x") }
}
class Neighbor : AppCompatActivity() {}
class GenericDialog : AppCompatDialogFragment() {}
""", encoding="utf-8")
        got = di.extract_dialog_inventory(str(self.root))
        dialog = next(x for x in got["candidates"] if x["source_fqn"] == "com.example.GenericDialog")
        self.assertIn("com.example.GenericHost", dialog["host_fqns"])
        self.assertNotIn("com.example.Neighbor", dialog["host_fqns"])

    def test_transitive_classification_and_layout_owner(self):
        got = di.extract_dialog_inventory(str(self.root))
        by_name = {x["source_fqn"]: x for x in got["candidates"]}
        child = by_name["com.example.ChildSortDialog"]
        self.assertEqual(child["root_kind"], "bottom_sheet_dialog_fragment")
        self.assertEqual(child["suggested_page_type"], "modal_overlay")
        self.assertFalse(child["needs_immersive_safearea"])
        self.assertEqual(child["layout_owner_fqn"], "com.example.BaseSortDialog")
        self.assertIn("sort_dialog", child["layout_sources"])

    def test_show_transaction_host_is_caller(self):
        got = di.extract_dialog_inventory(str(self.root))
        child = next(x for x in got["candidates"] if x["source_fqn"].endswith("ChildSortDialog"))
        self.assertEqual(child["host_fqns"], ["com.example.HostFragment"])
        self.assertEqual(child["usage_edges"][0]["mechanism"], "show")

    def test_factory_construction_does_not_self_host(self):
        got = di.extract_dialog_inventory(str(self.root))
        direct = next(x for x in got["candidates"] if x["source_fqn"].endswith("DirectDialog"))
        self.assertIn("com.example.HostFragment", direct["host_fqns"])
        self.assertNotIn("com.example.DirectDialog", direct["host_fqns"])

    def test_anonymous_helper_is_required_instance(self):
        got = di.extract_dialog_inventory(str(self.root))
        rows = got["anonymous_instantiations"]
        self.assertTrue(any(x["base_fqn"] == "com.example.ConfirmBase" for x in rows), rows)
        base = next(x for x in got["candidates"] if x["source_fqn"] == "com.example.ConfirmBase")
        self.assertTrue(base["required"])

    def test_cli_is_stable_json(self):
        cmd = [sys.executable, str(SCRIPTS / "dialog_inventory.py"),
               "--android-root", str(self.root), "--compact"]
        a = subprocess.run(cmd, check=True, capture_output=True, text=True).stdout
        b = subprocess.run(cmd, check=True, capture_output=True, text=True).stdout
        self.assertEqual(a, b)
        self.assertEqual(json.loads(a)["schema_version"], 1)

    def test_extended_helper_methods_and_subclasses_are_dialogs(self):
        got = di.extract_dialog_inventory(str(self.root))
        by_name = {x["source_fqn"]: x for x in got["candidates"]}
        names = set(by_name)
        self.assertIn("com.example.ExtendedHelper", names)
        self.assertIn("com.example.HelperChild", names)
        self.assertNotIn("com.example.NotADialogController", names)
        self.assertEqual(by_name["com.example.ExtendedHelper"]["host_fqns"],
                         ["com.example.HostFragment"])

    def test_common_layout_forms_select_an_owner(self):
        got = di.extract_dialog_inventory(str(self.root))
        item = next(x for x in got["candidates"]
                    if x["source_fqn"] == "com.example.LayoutPatterns")
        self.assertEqual(item["layout_owner_fqn"], "com.example.LayoutPatterns")
        self.assertIn("dialog_view", item["layout_sources"])
        self.assertIn("helper", item["layout_sources"])

    def test_add_replace_is_embedded_not_dialog_presentation(self):
        got = di.extract_dialog_inventory(str(self.root))
        item = next(x for x in got["candidates"]
                    if x["source_fqn"] == "com.example.EmbeddedD")
        self.assertTrue(item["embedded_only"])
        self.assertFalse(item["required"])
        self.assertEqual(item["presentation_modes"], ["embedded"])
        self.assertEqual(item["suggested_page_type"], "sub_component")
        self.assertIsNone(item["snapshot_ref"])
        self.assertEqual(item["embedded_usage_edges"][0]["mechanism"], "add")


class PresentationFormsTest(unittest.TestCase):
    """gpt1030_2 / AntennaPod（2026-10-18）实测漏认的四种展示写法 + 注释掉入口的死弹窗。"""

    KOTLIN = r'''
package com.k
import androidx.fragment.app.DialogFragment
import androidx.appcompat.app.AppCompatActivity
class LoadDialog : DialogFragment() {
    companion object {
        private var dialog: LoadDialog? = null
        fun showLoad(activity: AppCompatActivity, auto: Boolean = true) {
            showLoad(activity, activity.supportFragmentManager, auto)
        }
        fun showLoad(activity: AppCompatActivity, fm: FragmentManager, auto: Boolean) {
            dialog = LoadDialog().apply { arguments = Bundle() }
            dialog?.show(fm)
        }
    }
}
class IntroDialog : DialogFragment() {
    companion object { fun newInstance(title: String): IntroDialog = IntroDialog() }
}
class PayDialog : DialogFragment() {
    companion object { fun newInstance(url: String): PayDialog { return PayDialog().apply { } } }
}
class AdDialog : DialogFragment() {
    companion object { fun newInstance(): AdDialog = AdDialog() }
}
class HomeActivity : AppCompatActivity() {
    private var intro: IntroDialog? = null
    private var ad: AdDialog? = null
    fun onReady() {
        LoadDialog.showLoad(this, auto = true)
        intro = IntroDialog.newInstance("t")
        intro?.show(supportFragmentManager)
        PayDialog.newInstance("u").apply { tag = "x" }.show(supportFragmentManager)
//        showAd() // [AD-OFF]
    }
    private fun showAd() {
        ad = AdDialog.newInstance().apply { setConfirm { } }
        ad?.show(supportFragmentManager)
    }
}
'''
    JAVA = r'''
package com.j;
import androidx.fragment.app.Fragment;
abstract class SkipDialog extends MaterialAlertDialogBuilder {
  SkipDialog(Context c, int a) { super(c); }
  public void show() { create().show(); }
  protected abstract void onConfirmed(int a);
}
class SettingsFragment extends Fragment {
  void setup() {
    new SkipDialog(getContext(),
        prefs.getIntro()) {
      @Override
      protected void onConfirmed(int a) { save(a); }
    }.show();
  }
}
'''

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "app/src/main/java/com/k").mkdir(parents=True)
        (root / "app/src/main/java/com/j").mkdir(parents=True)
        (root / "app/src/main/java/com/k/All.kt").write_text(self.KOTLIN, encoding="utf-8")
        (root / "app/src/main/java/com/j/Skip.java").write_text(self.JAVA, encoding="utf-8")
        got = di.extract_dialog_inventory(str(root))
        self.by = {c["source_fqn"].rsplit(".", 1)[-1]: c for c in got["candidates"]}
        self.anonymous = got["anonymous_instantiations"]

    def tearDown(self):
        self.tmp.cleanup()

    def _edges(self, name):
        return [(e["mechanism"], e["declared_host_fqn"].rsplit(".", 1)[-1], bool(e.get("dead_entry")))
                for e in self.by[name]["usage_edges"]]

    def test_static_helper_that_presents_itself(self):
        self.assertEqual(self._edges("LoadDialog"), [("showLoad", "HomeActivity", False)])
        self.assertEqual(self.by["LoadDialog"]["host_fqns"], ["com.k.HomeActivity"])

    def test_nullable_field_receiver(self):
        self.assertEqual(self._edges("IntroDialog"), [("show", "HomeActivity", False)])

    def test_scope_function_chain_then_show(self):
        self.assertEqual(self._edges("PayDialog"), [("show", "HomeActivity", False)])

    def test_anonymous_subclass_then_show(self):
        self.assertEqual(self._edges("SkipDialog"), [("show", "SettingsFragment", False)])
        self.assertTrue(self.by["SkipDialog"]["required"])

    def test_commented_out_entry_is_not_required(self):
        ad = self.by["AdDialog"]
        self.assertEqual(self._edges("AdDialog"), [("show", "HomeActivity", True)])
        self.assertEqual(ad["usage_edges"][0]["entry_member"], "showAd")
        self.assertTrue(ad["reachable"])
        self.assertTrue(ad["dead_entry_only"])
        self.assertFalse(ad["required"])

    def test_double_slash_inside_string_does_not_kill_the_entry(self):
        # 1018 复查 M8：`"https://"` 里的 // 不是注释，同一行后面的调用照样是活入口
        root = Path(self.tmp.name)
        (root / "app/src/main/java/com/k/Url.kt").write_text(
            "package com.k\nimport androidx.fragment.app.DialogFragment\nimport androidx.appcompat.app.AppCompatActivity\n"
            "class UpgradeDialog : DialogFragment()\n"
            "class UrlActivity : AppCompatActivity() {\n"
            "    fun onUrl(url: String) {\n        if (url.startsWith(\"https://\")) showUpgrade()\n    }\n"
            "    private fun showUpgrade() {\n        UpgradeDialog().show(supportFragmentManager, \"u\")\n    }\n}\n",
            encoding="utf-8")
        got = {c["source_fqn"].rsplit(".", 1)[-1]: c for c in di.extract_dialog_inventory(str(root))["candidates"]}
        self.assertTrue(got["UpgradeDialog"]["required"])
        self.assertFalse(got["UpgradeDialog"]["dead_entry_only"])

    def test_live_dialogs_stay_required(self):
        for name in ("LoadDialog", "IntroDialog", "PayDialog"):
            self.assertTrue(self.by[name]["required"], name)
            self.assertFalse(self.by[name]["dead_entry_only"], name)


if __name__ == "__main__":
    unittest.main()
