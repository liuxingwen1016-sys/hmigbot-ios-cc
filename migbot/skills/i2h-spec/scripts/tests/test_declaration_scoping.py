#!/usr/bin/env python3
"""Test declaration scoping prevents contamination between sibling Views.

This test suite verifies the core fix: each View declaration's extracted facts
(properties, components, interactions, body, line_count) must be bounded by its
lexical scope, not contaminated by siblings in the same Swift file.
"""
import json
import sys
import tempfile
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from ui_evidence import detect_views


def test_two_views_same_file_no_contamination():
    """Two independent Views in one file must not contaminate each other's facts."""
    swift_code = '''
import SwiftUI

struct FirstView: View {
    @State private var firstCounter: Int = 0
    @State private var firstName: String = ""

    var body: some View {
        VStack {
            Text("First View")
            Button("First Button") {
                firstCounter += 1
            }
            TextField("First Field", text: $firstName)
        }
    }
}

struct SecondView: View {
    @State private var secondCounter: Int = 0
    @ObservedObject var secondModel: ViewModel

    var body: some View {
        HStack {
            Text("Second View")
            Toggle("Second Toggle", isOn: $secondModel.enabled)
            NavigationLink("Second Link") {
                Text("Destination")
            }
        }
    }
}
'''

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        swift_file = root / "TwoViews.swift"
        swift_file.write_text(swift_code, encoding="utf-8")

        views = detect_views(swift_file, root)

    assert len(views) == 2, f"Expected 2 views, got {len(views)}"

    first = next((v for v in views if v["view_name"] == "FirstView"), None)
    second = next((v for v in views if v["view_name"] == "SecondView"), None)

    assert first is not None, "FirstView not found"
    assert second is not None, "SecondView not found"

    # FirstView properties must not include SecondView's properties
    first_prop_names = {p["name"] for p in first["properties"]}
    assert "firstCounter" in first_prop_names, "FirstView missing firstCounter"
    assert "firstName" in first_prop_names, "FirstView missing firstName"
    assert "secondCounter" not in first_prop_names, "FirstView contaminated with secondCounter"
    assert "secondModel" not in first_prop_names, "FirstView contaminated with secondModel"
    assert len(first["properties"]) == 2, f"FirstView should have 2 properties, got {len(first['properties'])}"

    # SecondView properties must not include FirstView's properties
    second_prop_names = {p["name"] for p in second["properties"]}
    assert "secondCounter" in second_prop_names, "SecondView missing secondCounter"
    assert "secondModel" in second_prop_names, "SecondView missing secondModel"
    assert "firstCounter" not in second_prop_names, "SecondView contaminated with firstCounter"
    assert "firstName" not in second_prop_names, "SecondView contaminated with firstName"
    assert len(second["properties"]) == 2, f"SecondView should have 2 properties, got {len(second['properties'])}"

    # Components must be scoped
    first_components = first["ui_structure"]["key_components"]
    assert "VStack" in first_components, "FirstView missing VStack"
    assert "Button" in first_components, "FirstView missing Button"
    assert "TextField" in first_components, "FirstView missing TextField"
    assert "HStack" not in first_components, "FirstView contaminated with HStack"
    assert "Toggle" not in first_components, "FirstView contaminated with Toggle"
    assert "NavigationLink" not in first_components, "FirstView contaminated with NavigationLink"

    second_components = second["ui_structure"]["key_components"]
    assert "HStack" in second_components, "SecondView missing HStack"
    assert "Toggle" in second_components, "SecondView missing Toggle"
    assert "NavigationLink" in second_components, "SecondView missing NavigationLink"
    assert "VStack" not in second_components, "SecondView contaminated with VStack"
    assert "Button" not in second_components, "SecondView contaminated with Button"
    assert "TextField" not in second_components, "SecondView contaminated with TextField"

    # Interactions must be scoped
    first_interaction_types = {i["type"] for i in first["interactions"]}
    assert "button" in first_interaction_types, "FirstView missing button interaction"
    assert "input" in first_interaction_types, "FirstView missing input interaction"
    assert "navigation" not in first_interaction_types, "FirstView contaminated with navigation"

    second_interaction_types = {i["type"] for i in second["interactions"]}
    assert "input" in second_interaction_types, "SecondView missing input (Toggle) interaction"
    assert "navigation" in second_interaction_types, "SecondView missing navigation interaction"
    assert "button" not in second_interaction_types or any(
        "Button" not in str(i) for i in second["interactions"] if i["type"] == "button"
    ), "SecondView should not have FirstView's Button"

    # Line counts must be per-declaration, not whole file
    assert first["line_count"] < 20, f"FirstView line_count {first['line_count']} seems like whole file"
    assert second["line_count"] < 20, f"SecondView line_count {second['line_count']} seems like whole file"
    assert first["line_count"] > 0, "FirstView line_count should be positive"
    assert second["line_count"] > 0, "SecondView line_count should be positive"

    # Each should have declaration end line
    assert first.get("declaration_end_line") is not None, "FirstView missing declaration_end_line"
    assert second.get("declaration_end_line") is not None, "SecondView missing declaration_end_line"
    assert first["declaration_end_line"] > first["declaration_line"], "FirstView end must be after start"
    assert second["declaration_end_line"] > second["declaration_line"], "SecondView end must be after start"

    print("✓ Two views in same file: no contamination detected")
    return True


def test_nested_braces_in_strings():
    """String literals with braces must not extend one declaration into another."""
    swift_code = '''
import SwiftUI

struct ViewOne: View {
    @State private var jsonTemplate = """
        {
            "nested": { "braces": true }
        }
        """

    var body: some View {
        Text("View One: \\(jsonTemplate)")
    }
}

struct ViewTwo: View {
    @State private var count: Int = 0

    var body: some View {
        Button("View Two") {
            count += 1
        }
    }
}
'''

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        swift_file = root / "StringBraces.swift"
        swift_file.write_text(swift_code, encoding="utf-8")

        views = detect_views(swift_file, root)

    assert len(views) == 2, f"Expected 2 views despite string braces, got {len(views)}"

    view_one = next((v for v in views if v["view_name"] == "ViewOne"), None)
    view_two = next((v for v in views if v["view_name"] == "ViewTwo"), None)

    assert view_one is not None, "ViewOne not found"
    assert view_two is not None, "ViewTwo not found"

    # ViewOne should not contaminate ViewTwo
    view_one_props = {p["name"] for p in view_one["properties"]}
    view_two_props = {p["name"] for p in view_two["properties"]}

    assert "jsonTemplate" in view_one_props, "ViewOne missing jsonTemplate"
    assert "count" not in view_one_props, "ViewOne contaminated with count"

    assert "count" in view_two_props, "ViewTwo missing count"
    assert "jsonTemplate" not in view_two_props, "ViewTwo contaminated with jsonTemplate"

    print("✓ Nested braces in strings: declarations correctly bounded")
    return True


def test_nested_types():
    """Nested type declarations must be handled correctly."""
    swift_code = '''
import SwiftUI

struct OuterView: View {
    @State private var outerState: String = ""

    struct InnerHelper {
        var helperValue: Int
    }

    var body: some View {
        VStack {
            Text(outerState)
        }
    }
}

struct SeparateView: View {
    @State private var separateState: Bool = false

    var body: some View {
        Toggle("Separate", isOn: $separateState)
    }
}
'''

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        swift_file = root / "NestedTypes.swift"
        swift_file.write_text(swift_code, encoding="utf-8")

        views = detect_views(swift_file, root)

    # Should find only View-conforming types
    view_names = {v["view_name"] for v in views}
    assert "OuterView" in view_names, "OuterView not found"
    assert "SeparateView" in view_names, "SeparateView not found"
    assert "InnerHelper" not in view_names, "InnerHelper should not be detected as View"

    outer = next((v for v in views if v["view_name"] == "OuterView"), None)
    separate = next((v for v in views if v["view_name"] == "SeparateView"), None)

    # OuterView properties should not leak into SeparateView
    outer_props = {p["name"] for p in outer["properties"]}
    separate_props = {p["name"] for p in separate["properties"]}

    assert "outerState" in outer_props, "OuterView missing outerState"
    assert "separateState" not in outer_props, "OuterView contaminated with separateState"

    assert "separateState" in separate_props, "SeparateView missing separateState"
    assert "outerState" not in separate_props, "SeparateView contaminated with outerState"

    print("✓ Nested types: View properties correctly scoped")
    return True


def test_comments_and_multiline_strings():
    """Comments and multiline strings must not break declaration boundaries."""
    swift_code = '''
import SwiftUI

struct FirstView: View {
    @State private var first = """
        Multi
        line
        string
        """

    var body: some View {
        // Comment with } brace
        /* Block comment
           with } brace */
        Text(first)
    }
}

struct SecondView: View {
    @State private var second: Int = 0

    var body: some View {
        // Another comment }
        Button("Second") {
            second += 1
        }
    }
}
'''

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        swift_file = root / "CommentsStrings.swift"
        swift_file.write_text(swift_code, encoding="utf-8")

        views = detect_views(swift_file, root)

    assert len(views) == 2, f"Expected 2 views despite comments/strings, got {len(views)}"

    first = next((v for v in views if v["view_name"] == "FirstView"), None)
    second = next((v for v in views if v["view_name"] == "SecondView"), None)

    assert first is not None and second is not None

    first_props = {p["name"] for p in first["properties"]}
    second_props = {p["name"] for p in second["properties"]}

    assert "first" in first_props and "second" not in first_props
    assert "second" in second_props and "first" not in second_props

    print("✓ Comments and multiline strings: boundaries preserved")
    return True


def test_line_numbers_and_source_positions():
    """Line numbers and source positions must be accurate for each declaration."""
    swift_code = '''import SwiftUI

struct FirstView: View {
    @State private var a: Int = 0

    var body: some View {
        Text("First")
    }
}

struct SecondView: View {
    @State private var b: Int = 0

    var body: some View {
        Text("Second")
    }
}
'''

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        swift_file = root / "LineNumbers.swift"
        swift_file.write_text(swift_code, encoding="utf-8")

        views = detect_views(swift_file, root)

    first = next((v for v in views if v["view_name"] == "FirstView"), None)
    second = next((v for v in views if v["view_name"] == "SecondView"), None)

    assert first is not None and second is not None

    # FirstView starts around line 3
    assert 2 <= first["declaration_line"] <= 4, f"FirstView declaration_line {first['declaration_line']} unexpected"

    # SecondView starts around line 11
    assert 10 <= second["declaration_line"] <= 12, f"SecondView declaration_line {second['declaration_line']} unexpected"

    # Declaration end lines must not overlap
    assert first["declaration_end_line"] < second["declaration_line"], \
        f"FirstView end {first['declaration_end_line']} overlaps SecondView start {second['declaration_line']}"

    # Property line numbers must be within declaration bounds
    for prop in first["properties"]:
        assert first["declaration_line"] <= prop["line"] <= first["declaration_end_line"], \
            f"FirstView property {prop['name']} line {prop['line']} outside bounds"

    for prop in second["properties"]:
        assert second["declaration_line"] <= prop["line"] <= second["declaration_end_line"], \
            f"SecondView property {prop['name']} line {prop['line']} outside bounds"

    print("✓ Line numbers and positions: accurate per declaration")
    return True


def test_real_detection_downstream():
    """Test actual detect_views execution produces valid JSON with scoped data."""
    swift_code = '''
import SwiftUI

struct PageOne: View {
    @State private var pageOneText: String = ""
    @State private var pageOneCount: Int = 0

    var body: some View {
        VStack {
            TextField("Page One", text: $pageOneText)
            Button("Page One Action") {
                pageOneCount += 1
            }
        }
    }
}

struct PageTwo: View {
    @State private var pageTwoEnabled: Bool = false

    var body: some View {
        Form {
            Toggle("Page Two", isOn: $pageTwoEnabled)
            Picker("Page Two Picker", selection: .constant(0)) {
                Text("Option")
            }
        }
    }
}
'''

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        swift_file = root / "RealDetection.swift"
        swift_file.write_text(swift_code, encoding="utf-8")

        views = detect_views(swift_file, root)

    # Serialize to JSON to verify structure
    json_output = json.dumps(views, indent=2)
    parsed = json.loads(json_output)

    assert len(parsed) == 2, f"Expected 2 views in JSON, got {len(parsed)}"

    page_one = next((v for v in parsed if v["view_name"] == "PageOne"), None)
    page_two = next((v for v in parsed if v["view_name"] == "PageTwo"), None)

    assert page_one is not None and page_two is not None

    # Validate ui_obligations are scoped
    page_one_controls = page_one.get("ui_obligations", {}).get("interactive_controls", [])
    page_two_controls = page_two.get("ui_obligations", {}).get("interactive_controls", [])

    page_one_control_kinds = {c["kind"] for c in page_one_controls}
    page_two_control_kinds = {c["kind"] for c in page_two_controls}

    # PageOne should have text_field and button
    assert "text_field" in page_one_control_kinds, "PageOne missing text_field control"
    assert "button" in page_one_control_kinds, "PageOne missing button control"
    assert "picker" not in page_one_control_kinds, "PageOne contaminated with picker"
    assert "toggle" not in page_one_control_kinds, "PageOne contaminated with toggle"

    # PageTwo should have toggle and picker
    assert "toggle" in page_two_control_kinds, "PageTwo missing toggle control"
    assert "picker" in page_two_control_kinds, "PageTwo missing picker control"
    assert "button" not in page_two_control_kinds or len([c for c in page_two_controls if c["kind"] == "button"]) == 0, \
        "PageTwo should not have PageOne's button"
    assert "text_field" not in page_two_control_kinds, "PageTwo contaminated with text_field"

    # Validate containers are scoped
    page_one_containers = page_one.get("ui_obligations", {}).get("containers", [])
    page_two_containers = page_two.get("ui_obligations", {}).get("containers", [])

    assert "VStack" in page_one_containers, "PageOne missing VStack container"
    assert "Form" not in page_one_containers, "PageOne contaminated with Form"

    assert "Form" in page_two_containers, "PageTwo missing Form container"
    assert "VStack" not in page_two_containers, "PageTwo contaminated with VStack"

    print("✓ Real detection downstream: valid scoped JSON output")
    return True


def run_all_tests():
    """Run all test cases and report results."""
    tests = [
        test_two_views_same_file_no_contamination,
        test_nested_braces_in_strings,
        test_nested_types,
        test_comments_and_multiline_strings,
        test_line_numbers_and_source_positions,
        test_real_detection_downstream,
    ]

    print("Running declaration scoping tests...\n")

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            failed += 1
            print(f"✗ {test.__name__} FAILED: {e}")
        except Exception as e:
            failed += 1
            print(f"✗ {test.__name__} ERROR: {e}")

    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed")
    print(f"{'='*60}")

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
