import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from uitest_action import label_action_center, require_focused_app, selected_tab_label


def node(kind, rect, *children, **attributes):
    return {"attributes": {"type": kind, "bounds": rect, "visible": "true", "enabled": "true",
                           "hostWindowId": "2", **attributes}, "children": children}


class ActionTest(unittest.TestCase):
    def test_foreground_requires_the_expected_focused_bundle(self):
        def root(bundle, focused):
            return {"attributes": {"bundleName": bundle, "focused": focused, "pagePath": "pages/Index"}}
        require_focused_app({"children": [root("app", "true"), root("system", "false")]}, "app")
        for children in ([root("other", "true")], [root("app", "false")],
                         [root("app", "true"), root("other", "true")],
                         [{"attributes": {"bundleName": "app", "focused": "true"}}]):
            with self.assertRaisesRegex(ValueError, "expected foreground"):
                require_focused_app({"children": children}, "app")

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

    def test_native_tab_selection_belongs_to_the_parent_of_the_label(self):
        label = node("Text", "[0,0][20,20]", text="Library")
        selected = node("Column", "[0,0][30,30]", label, selected="true")
        outside = node("Text", "[30,0][60,20]", text="Home", selected="true")
        bar = node("TabBar", "[0,0][100,30]", selected)
        tree = node("Column", "[0,0][100,100]", bar, outside)
        self.assertEqual(selected_tab_label(tree, {"Library", "Home"}), "Library")
        with self.assertRaisesRegex(ValueError, r"found \[\]"):
            selected_tab_label(outside, {"Home"})
