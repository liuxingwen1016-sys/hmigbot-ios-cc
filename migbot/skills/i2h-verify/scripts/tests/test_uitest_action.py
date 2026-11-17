import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from uitest_action import (
    ForegroundError, fully_visible_control, grouped_row_action_center, label_action_center,
    overlaps_obstruction, require_focused_app,
    selected_tab_label, visible_tab_bar_bounds,
)


def node(kind, rect, *children, **attributes):
    return {"attributes": {"type": kind, "bounds": rect, "visible": "true", "enabled": "true",
                           "hostWindowId": "2", **attributes}, "children": children}


class ActionTest(unittest.TestCase):
    def test_control_clipped_before_tab_bar_is_not_fully_visible(self):
        bar = [(0, 2459, 1256, 2662)]
        control = {'visible': 'true', 'enabled': 'true', 'bounds': '[84,2400][581,2459]'}
        self.assertTrue(fully_visible_control(control, bar))
        self.assertFalse(fully_visible_control({**control, 'origBounds': '[84,2400][581,2475]'}, bar))
        self.assertFalse(fully_visible_control({**control, 'visible': 'false'}, bar))
        self.assertFalse(fully_visible_control({**control, 'enabled': 'false'}, bar))

    def test_control_frame_can_overlap_tab_bar_while_center_is_clear(self):
        overlays = [(0, 2459, 1256, 2662)]
        self.assertTrue(overlaps_obstruction({'bounds': '[84,2300][581,2475]'}, overlays))
        self.assertFalse(overlaps_obstruction({'bounds': '[84,2284][581,2459]'}, overlays))
        self.assertFalse(overlaps_obstruction({'bounds': '[1260,2300][1300,2475]'}, overlays))

    def test_visible_tab_bar_bounds_does_not_require_tab_ids(self):
        visible = node('TabBar', '[0,2459][1256,2662]')
        hidden = node('TabBar', '[0,0][100,80]', visible='false')
        self.assertEqual(visible_tab_bar_bounds(node('Root', '[0,0][1256,2760]', visible, hidden)),
                         [(0, 2459, 1256, 2662)])

    def test_foreground_requires_the_expected_focused_bundle(self):
        def root(bundle, focused):
            return {"attributes": {"bundleName": bundle, "focused": focused, "pagePath": "pages/Index"}}
        require_focused_app({"children": [root("app", "true"), root("system", "false")]}, "app")
        for children in ([root("other", "true")], [root("app", "false")],
                         [root("app", "true"), root("other", "true")],
                         [{"attributes": {"bundleName": "app", "focused": "true"}}]):
            with self.assertRaisesRegex(ValueError, "expected foreground"):
                require_focused_app({"children": children}, "app")

    def test_foreground_error_keeps_the_focused_system_page(self):
        tree = {"children": [node("root", "[0,0][100,100]", bundleName="ime",
                                  focused="true", pagePath="pages/permission/StartupPage"),
                             node("root", "[0,0][100,100]", bundleName="app",
                                  focused="false", pagePath="pages/Index")]}
        with self.assertRaises(ForegroundError) as caught:
            require_focused_app(tree, "app")
        self.assertEqual(caught.exception.windows, [{"bundle": "ime", "page": "pages/permission/StartupPage"}])

    def test_label_resolves_clickable_parent_without_tapping_disabled_or_other_window(self):
        label = node("Text", "[42,10][55,20]", text="Done")
        button = node("Button", "[30,0][70,30]", label, clickable="true")
        self.assertEqual(label_action_center(button, "Done"), (50, 15))
        for change in ({"enabled": "false"}, {"hostWindowId": "3"}, {"bounds": "[0,0][10,10]"}):
            tree = node("Button", "[30,0][70,30]", label, clickable="true", **change)
            with self.assertRaisesRegex(ValueError, "found 0"):
                label_action_center(tree, "Done")
        with self.assertRaisesRegex(ValueError, "found 0"):
            label_action_center(node("Row", "[0,0][100,100]", label, clickable="true"), "Done")

    def test_direct_action_and_ambiguity(self):
        action = node("Button", "[20,0][50,30]", clickable="true", text="Done")
        self.assertEqual(label_action_center(action, "Done"), (35, 15))
        duplicate = node("Button", "[60,0][90,30]", clickable="true", text="Done")
        with self.assertRaisesRegex(ValueError, "found 2"):
            label_action_center(node("Column", "[0,0][100,100]", action, duplicate), "Done")

    def test_scoped_label_resolves_only_the_visible_custom_action(self):
        label = node("Text", "[42,10][55,20]", text="Save")
        row = node("Row", "[30,0][70,30]", label, clickable="true")
        container = node("Column", "[0,0][80,40]", row, id="saveBean")
        outside = node("Button", "[85,0][98,30]", text="Save", clickable="true")
        root = node("root", "[0,0][100,100]", container, outside)
        self.assertEqual(label_action_center(root, "Save"), (91, 15))
        self.assertEqual(label_action_center(root, "Save", container_id="saveBean"), (50, 15))
        with self.assertRaisesRegex(ValueError, "expected one visible action container"):
            label_action_center(root, "Save", container_id="missing")
        duplicate = node("root", "[0,0][100,100]", container, outside, container)
        with self.assertRaisesRegex(ValueError, "expected one visible action container"):
            label_action_center(duplicate, "Save", container_id="saveBean")
        row["attributes"]["origBounds"] = "[30,0][80,30]"
        with self.assertRaisesRegex(ValueError, "found 0"):
            label_action_center(root, "Save", container_id="saveBean")

    def test_grouped_row_uses_visible_child_labels_and_rejects_ambiguity(self):
        bean = node("Text", "[10,10][45,25]", text="Bean")
        rating = node("Text", "[55,10][75,25]", text="Four")
        row = node("Row", "[0,0][100,50]", bean, rating,
                   text="Unstable localized summary", clickable="true", origBounds="[0,0][100,50]")
        list_row = node("ListItem", "[0,50][100,100]",
                        node("Text", "[10,60][45,75]", text="Bean"),
                        node("Text", "[55,60][75,75]", text="Four"),
                        clickable="true", origBounds="[0,50][100,100]")
        scope = node("Column", "[0,0][100,100]", row, id="recent")
        window = node("root", "[0,0][100,100]", scope, list_row,
                      focused="true", bundleName="sample", pagePath="Index")
        tree = node("WindowManager", "[0,0][100,100]", window)
        labels = ("Bean", "Four")
        self.assertEqual(grouped_row_action_center(tree, labels, bundle="sample", container_id="recent"), (50, 25))
        with self.assertRaisesRegex(ValueError, "found 2"):
            grouped_row_action_center(tree, labels, bundle="sample")
        for changes in ({"hostWindowId": "7"}, {"visible": "false"}, {"clickable": "true"}):
            before = rating["attributes"].copy()
            rating["attributes"].update(changes)
            with self.assertRaisesRegex(ValueError, "found 0"):
                grouped_row_action_center(tree, labels, bundle="sample", container_id="recent")
            rating["attributes"] = before
        with self.assertRaises(ForegroundError):
            grouped_row_action_center(tree, labels, bundle="another")
        row["attributes"]["origBounds"] = "[0,0][100,55]"
        with self.assertRaisesRegex(ValueError, "found 0"):
            grouped_row_action_center(tree, labels, bundle="sample", container_id="recent")
        row["attributes"]["origBounds"] = "[0,0][100,50]"
        scope["children"] += (node("Stack", "[0,43][100,68]", id="overlay"),)
        with self.assertRaisesRegex(ValueError, "found 0"):
            grouped_row_action_center(tree, labels, bundle="sample", container_id="recent",
                                     obstruction_ids=("overlay",))

    def test_native_tab_selection_belongs_to_the_parent_of_the_label(self):
        label = node("Text", "[0,0][20,20]", text="Library")
        selected = node("Column", "[0,0][30,30]", label, selected="true")
        outside = node("Text", "[30,0][60,20]", text="Home", selected="true")
        bar = node("TabBar", "[0,0][100,30]", selected)
        tree = node("Column", "[0,0][100,100]", bar, outside)
        self.assertEqual(selected_tab_label(tree, {"Library", "Home"}), "Library")
        with self.assertRaisesRegex(ValueError, r"found \[\]"):
            selected_tab_label(outside, {"Home"})

    def test_scoped_tab_selection_reads_the_visible_button_parent(self):
        label = node("Text", "[32,10][75,20]", text="Library")
        selected = node("Button", "[30,0][80,30]", label, selected="true")
        hidden = node("Column", "[0,0][30,30]",
                      node("Text", "[0,5][20,20]", text="Home", selected="true"), visible="false")
        capsule = node("Row", "[0,0][100,30]", selected, hidden, id="floatingTabs")
        outside = node("Text", "[82,0][100,20]", text="Home", selected="true")
        tree = node("root", "[0,0][120,40]", capsule, outside)
        labels = {"Library", "Home"}
        self.assertEqual(selected_tab_label(tree, labels, container_id="floatingTabs"), "Library")
        with self.assertRaisesRegex(ValueError, "selected TabBar label"):
            selected_tab_label(tree, labels)
        with self.assertRaisesRegex(ValueError, "expected one visible tab container"):
            selected_tab_label(tree, labels, container_id="unknownTabs")
        duplicate = node("root", "[0,0][120,40]", capsule, capsule)
        with self.assertRaisesRegex(ValueError, "expected one visible tab container"):
            selected_tab_label(duplicate, labels, container_id="floatingTabs")


class CLIRefusalTest(unittest.TestCase):
    """Test that the module refuses CLI invocation with clear guidance."""

    def test_no_args_refuses_with_nonzero_exit(self):
        import subprocess
        result = subprocess.run(
            [sys.executable, str(Path(__file__).resolve().parents[1] / "uitest_action.py")],
            capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("library module", result.stderr)
        self.assertIn("require_focused_app", result.stderr)
        self.assertIn("label_action_center", result.stderr)
        self.assertIn("selected_tab_label", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_cli_args_refuses_with_nonzero_exit(self):
        import subprocess
        result = subprocess.run(
            [sys.executable, str(Path(__file__).resolve().parents[1] / "uitest_action.py"),
             "--hdc", "/fake/hdc", "--action", "click", "--control-id", "test_button"],
            capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("library module", result.stderr)
        self.assertIn("cannot be invoked as a CLI", result.stderr)
        self.assertEqual(result.stdout, "")
