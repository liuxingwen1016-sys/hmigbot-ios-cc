#!/usr/bin/env python3
"""End-to-end resource fidelity tests for Core B implementation.

Tests complete integration of localizations, fonts, and themes through the
actual ui_evidence.run() pipeline with portable synthetic fixtures.
"""
import json
import struct
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from ui_evidence import run, build_res_index
from ios_localizations import scan_localizations
from ios_fonts import scan_fonts, scan_font_file
from ios_theme import scan_themes


def create_synthetic_ttf(family: str, postscript: str) -> bytes:
    """Create minimal valid TTF with family and PostScript names in name table."""
    # TTF header (sfnt version 1.0, 4 tables)
    header = struct.pack(">IHHHH", 0x00010000, 4, 128, 3, 32)

    # Table directory entries (tag, checksum, offset, length)
    # We need: head, hhea, maxp, name
    tables = []
    offset = 12 + 16 * 4  # Header + 4 table entries

    # head table (minimal) - 54 bytes
    # Format: version(I) fontRevision(I) checksum(I) magic(I) flags(H) unitsPerEm(H)
    #         created(II) modified(II) xMin(h) yMin(h) xMax(h) yMax(h)
    #         macStyle(H) lowestRecPPEM(H) fontDirectionHint(h) indexToLocFormat(h) glyphDataFormat(h)
    head_data = struct.pack(">IIIIHHIIIIhhhhHHhhh",
        0x00010000,  # version (I)
        0x00010000,  # fontRevision (I)
        0,  # checksumAdjustment (I)
        0x5F0F3CF5,  # magicNumber (I)
        0,  # flags (H)
        1000,  # unitsPerEm (H)
        0, 0,  # created (II - 64-bit as 2x32-bit)
        0, 0,  # modified (II - 64-bit as 2x32-bit)
        -100, -100,  # xMin(h), yMin(h)
        900, 900,  # xMax(h), yMax(h)
        0,  # macStyle (H)
        8,  # lowestRecPPEM (H)
        2,  # fontDirectionHint (h)
        0,  # indexToLocFormat (h)
        0   # glyphDataFormat (h)
    )
    tables.append((b"head", head_data, offset))
    offset += len(head_data)

    # hhea table (minimal) - 36 bytes
    # Format: version(I) ascent(h) descent(h) lineGap(h) advanceWidthMax(H)
    #         minLeftSideBearing(h) minRightSideBearing(h) xMaxExtent(h) caretSlopeRise(h)
    #         caretSlopeRun(h) caretOffset(h) reserved(hhhh) metricDataFormat(h) numOfLongHorMetrics(H)
    hhea_data = struct.pack(">IhhhHhhhhhhhhhhhH",
        0x00010000,  # version (I)
        800, -200,  # ascent(h), descent(h)
        0,  # lineGap (h)
        1000,  # advanceWidthMax (H)
        0, 0,  # minLeftSideBearing(h), minRightSideBearing(h)
        1000,  # xMaxExtent (h)
        1,  # caretSlopeRise (h)
        0,  # caretSlopeRun (h)
        0,  # caretOffset (h)
        0, 0, 0, 0,  # reserved (hhhh)
        0,  # metricDataFormat (h)
        1   # numOfLongHorMetrics (H)
    )
    tables.append((b"hhea", hhea_data, offset))
    offset += len(hhea_data)

    # maxp table (minimal)
    maxp_data = struct.pack(">IH", 0x00010000, 1)  # version 1.0, 1 glyph
    tables.append((b"maxp", maxp_data, offset))
    offset += len(maxp_data)

    # name table with family and PostScript name
    family_utf16 = family.encode("utf-16-be")
    postscript_utf16 = postscript.encode("utf-16-be")

    # Name records: (platformID, encodingID, languageID, nameID, length, offset)
    name_records = [
        (3, 1, 0x0409, 1, len(family_utf16)),      # Family name (Windows, Unicode, English)
        (3, 1, 0x0409, 6, len(postscript_utf16)),  # PostScript name
    ]

    string_offset = 6 + len(name_records) * 12
    string_data = family_utf16 + postscript_utf16

    name_data = struct.pack(">HHH", 0, len(name_records), string_offset)
    str_offset = 0
    for platform_id, encoding_id, language_id, name_id, length in name_records:
        name_data += struct.pack(">HHHHHH", platform_id, encoding_id, language_id,
                                name_id, length, str_offset)
        str_offset += length
    name_data += string_data

    tables.append((b"name", name_data, offset))

    # Build table directory
    table_directory = b""
    for tag, data, off in tables:
        checksum = sum(struct.unpack(f">{(len(data) + 3) // 4}I",
                                     data + b"\0" * ((4 - len(data) % 4) % 4))) & 0xFFFFFFFF
        table_directory += struct.pack(">4sIII", tag, checksum, off, len(data))

    # Assemble font
    font = header + table_directory
    for tag, data, off in tables:
        font += data

    return font


def create_synthetic_otf(family: str, postscript: str) -> bytes:
    """Create minimal valid OTF (CFF-based) with name table."""
    # OTF uses 'OTTO' tag
    header = struct.pack(">4sHHHH", b"OTTO", 4, 128, 3, 32)

    # We'll reuse the TTF name table structure but with OTTO header
    # For simplicity, create same structure as TTF but with OTTO tag
    ttf_data = create_synthetic_ttf(family, postscript)
    # Replace first 4 bytes with OTTO
    return b"OTTO" + ttf_data[4:]


def test_font_parsing_and_registration():
    """Test TTF/OTF parsing with synthetic fonts and Info.plist registration."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)

        # Create synthetic TTF
        ttf_data = create_synthetic_ttf("Test Family", "TestFamily-Regular")
        ttf_path = root / "Fonts/TestFamily.ttf"
        ttf_path.parent.mkdir(parents=True)
        ttf_path.write_bytes(ttf_data)

        # Create synthetic OTF
        otf_data = create_synthetic_otf("Display Font", "DisplayFont-Bold")
        otf_path = root / "Fonts/DisplayFont.otf"
        otf_path.write_bytes(otf_data)

        # Create Info.plist with font registration
        import plistlib
        info_plist = root / "Info.plist"
        plist_data = {
            "CFBundleIdentifier": "com.test.app",
            "UIAppFonts": [
                "Fonts/TestFamily.ttf",
                "Fonts/DisplayFont.otf"
            ]
        }
        info_plist.write_bytes(plistlib.dumps(plist_data))

        # Test individual font parsing
        ttf_info = scan_font_file(ttf_path)
        assert ttf_info["family"] == "Test Family", f"TTF family mismatch: {ttf_info.get('family')}"
        assert ttf_info["postscript_name"] == "TestFamily-Regular", f"TTF PostScript mismatch: {ttf_info.get('postscript_name')}"
        assert ttf_info["resolved"] is True, "TTF should be resolved"
        assert "sha256" in ttf_info, "TTF missing SHA256"
        assert ttf_info["size_bytes"] == len(ttf_data), "TTF size mismatch"

        otf_info = scan_font_file(otf_path)
        assert otf_info["family"] == "Display Font", f"OTF family mismatch: {otf_info.get('family')}"
        assert otf_info["postscript_name"] == "DisplayFont-Bold", f"OTF PostScript mismatch: {otf_info.get('postscript_name')}"
        assert otf_info["resolved"] is True, "OTF should be resolved"

        # Test full font scanning
        font_facts = scan_fonts(root)
        assert font_facts["total_count"] == 2, f"Expected 2 fonts, got {font_facts['total_count']}"
        assert font_facts["resolved_count"] == 2, f"Expected 2 resolved, got {font_facts['resolved_count']}"

        fonts = font_facts["fonts"]
        assert len(fonts) == 2, f"Expected 2 font entries, got {len(fonts)}"

        # Verify font paths and hashes
        ttf_entry = next(f for f in fonts if f["path"].endswith(".ttf"))
        assert ttf_entry["family"] == "Test Family", "TTF family not preserved"
        assert len(ttf_entry["sha256"]) == 64, "Invalid SHA256"

        # Verify registration
        registrations = font_facts["registrations"]
        assert len(registrations) == 1, f"Expected 1 registration, got {len(registrations)}"
        reg_fonts = registrations[0]["fonts"]
        assert any("TestFamily.ttf" in f for f in reg_fonts), f"TTF not in registration: {reg_fonts}"
        assert any("DisplayFont.otf" in f for f in reg_fonts), f"OTF not in registration: {reg_fonts}"

        print("✅ PASS: Font parsing and registration")
        print(f"   Fonts: {font_facts['total_count']} total, {font_facts['resolved_count']} resolved")
        print(f"   TTF family: {ttf_entry['family']}")
        print(f"   Registrations: {len(registrations)}")

        return 0


def test_theme_source_preservation():
    """Test Swift Theme source parsing preserves expressions without evaluation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)

        # Create Theme.swift with colors, spacing, and fonts
        theme_swift = root / "Theme/DesignTokens.swift"
        theme_swift.parent.mkdir(parents=True)
        theme_swift.write_text("""
import SwiftUI

struct Theme {
    // Colors
    static let primaryColor: Color = Color(red: 0.2, green: 0.6, blue: 1.0)

    static let adaptiveBackground: Color = Color { colorScheme in
        colorScheme == .dark ? Color.black : Color.white
    }

    static let accentColor: Color = Color("AccentColor")

    // Spacing
    static let standardPadding: CGFloat = 16.0
    static let compactSpacing: CGFloat = 8.0
    static let cornerRadius: CGFloat = 12.0

    // Fonts
    static let titleFont: Font = Font.custom("TestFamily-Regular", size: 24)
    static let bodyFont: Font = Font.system(.body)
}
""")

        # Scan themes
        theme_facts = scan_themes(root)

        assert theme_facts["summary"]["theme_file_count"] == 1, "Should find 1 theme file"
        assert theme_facts["summary"]["color_count"] == 3, f"Expected 3 colors, got {theme_facts['summary']['color_count']}"
        assert theme_facts["summary"]["spacing_count"] == 3, f"Expected 3 spacing values, got {theme_facts['summary']['spacing_count']}"
        assert theme_facts["summary"]["font_count"] == 2, f"Expected 2 fonts, got {theme_facts['summary']['font_count']}"

        # Verify color preservation
        colors = theme_facts["colors"]
        primary = next(c for c in colors if c["name"] == "primaryColor")
        assert "Color(red: 0.2, green: 0.6, blue: 1.0)" in primary["expression"], "Color expression not preserved"
        assert primary["resolved"] is False, "Colors should not be resolved"
        assert "sha256" in primary["source"], "Missing source SHA256"
        assert primary["source"]["file"].endswith("DesignTokens.swift"), "Wrong source file"

        adaptive = next(c for c in colors if c["name"] == "adaptiveBackground")
        assert adaptive["is_adaptive"] is True, "Should detect adaptive color"
        assert "colorScheme" in adaptive["expression"], "Adaptive expression not preserved"

        # Verify spacing preservation
        spacing = theme_facts["spacing"]
        padding = next(s for s in spacing if s["name"] == "standardPadding")
        assert padding["expression"] == "16.0", f"Spacing expression wrong: {padding['expression']}"
        assert padding["resolved"] is False, "Spacing should not be resolved"

        # Verify font preservation
        fonts = theme_facts["fonts"]
        title_font = next(f for f in fonts if f["name"] == "titleFont")
        assert title_font["custom_font_name"] == "TestFamily-Regular", "Custom font name not extracted"
        assert "Font.custom" in title_font["expression"], "Font expression not preserved"
        assert title_font["resolved"] is False, "Fonts should not be resolved"

        print("✅ PASS: Theme source preservation")
        print(f"   Colors: {len(colors)} (adaptive: {sum(1 for c in colors if c.get('is_adaptive'))})")
        print(f"   Spacing: {len(spacing)}")
        print(f"   Fonts: {len(fonts)}")

        return 0


def test_end_to_end_resource_integration():
    """Test complete ui_evidence.run() integration with all resource types."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)

        # Create Main app localization catalog
        main_loc = root / "Main/Resources/en.lproj/Localizable.xcstrings"
        main_loc.parent.mkdir(parents=True)
        main_catalog = {
            "sourceLanguage": "en",
            "version": "1.0",
            "strings": {
                "app_title": {
                    "extractionState": "manual",
                    "localizations": {
                        "en": {"stringUnit": {"state": "translated", "value": "Main App"}},
                        "zh-Hans": {"stringUnit": {"state": "translated", "value": "主应用"}},
                        "es": {"stringUnit": {"state": "translated", "value": "Aplicación principal"}},
                        "ja": {"stringUnit": {"state": "translated", "value": "メインアプリ"}}
                    }
                },
                "item_count": {
                    "localizations": {
                        "en": {
                            "variations": {
                                "plural": {
                                    "zero": {"stringUnit": {"state": "translated", "value": "No items"}},
                                    "one": {"stringUnit": {"state": "translated", "value": "%lld item"}},
                                    "other": {"stringUnit": {"state": "translated", "value": "%lld items"}}
                                }
                            }
                        },
                        "zh-Hans": {"stringUnit": {"state": "translated", "value": "%lld 个项目"}}
                    }
                }
            }
        }
        main_loc.write_text(json.dumps(main_catalog, ensure_ascii=False))

        # Create Widget extension localization with SAME KEY but different value
        widget_loc = root / "Widget/en.lproj/Localizable.xcstrings"
        widget_loc.parent.mkdir(parents=True)
        widget_catalog = {
            "sourceLanguage": "en",
            "strings": {
                "app_title": {  # Same key as Main
                    "localizations": {
                        "en": {"stringUnit": {"state": "translated", "value": "Widget Title"}},  # Different value
                        "zh-Hans": {"stringUnit": {"state": "translated", "value": "小组件标题"}},
                        "es": {"stringUnit": {"state": "needs_review", "value": "Título del widget"}},  # Stale
                        "ja": {"stringUnit": {"state": "new", "value": "ウィジェットタイトル"}}
                    }
                }
            }
        }
        widget_loc.write_text(json.dumps(widget_catalog, ensure_ascii=False))

        # Create fonts
        ttf_data = create_synthetic_ttf("App Font", "AppFont-Regular")
        ttf_path = root / "Fonts/AppFont.ttf"
        ttf_path.parent.mkdir(parents=True)
        ttf_path.write_bytes(ttf_data)

        otf_data = create_synthetic_otf("Title Font", "TitleFont-Bold")
        otf_path = root / "Fonts/TitleFont.otf"
        otf_path.write_bytes(otf_data)

        # Font registration
        import plistlib
        (root / "Main/Info.plist").parent.mkdir(parents=True, exist_ok=True)
        plist = {"UIAppFonts": ["Fonts/AppFont.ttf", "Fonts/TitleFont.otf"]}
        (root / "Main/Info.plist").write_bytes(plistlib.dumps(plist))

        # Create Theme
        theme = root / "Theme/AppTheme.swift"
        theme.parent.mkdir(parents=True)
        theme.write_text("""
import SwiftUI
struct AppTheme {
    static let primaryColor: Color = Color(red: 0.1, green: 0.5, blue: 0.9)
    static let adaptiveBg: Color = Color { $0 == .dark ? .black : .white }
    static let standardSpacing: CGFloat = 16.0
    static let titleFont: Font = Font.custom("AppFont-Regular", size: 22)
}
""")

        # Create a simple Swift view to avoid empty project
        view = root / "Views/HomeView.swift"
        view.parent.mkdir(parents=True)
        view.write_text("""
import SwiftUI
struct HomeView: View {
    var body: some View {
        Text("Home")
    }
}
""")

        # Create asset catalog with an image
        catalog_json = root / "Assets.xcassets/Logo.imageset/Contents.json"
        catalog_json.parent.mkdir(parents=True)
        catalog_json.write_text(json.dumps({
            "images": [{"idiom": "universal", "filename": "logo.png", "scale": "1x"}]
        }))

        # Run full scan
        output_path = root / "spec/.i2h/ui-evidence.json"
        payload = run(str(root), str(output_path))

        # Verify output was written
        assert output_path.is_file(), "Output file not created"
        inventory = payload["resources"]

        # Verify localization entries preserved (not just scalars)
        assert "localization_entries" in inventory, "localization_entries missing"
        entries = inventory["localization_entries"]
        assert len(entries) > 0, "No localization entries"

        # Verify app_title appears for both catalogs
        app_title_entries = [e for e in entries if e["key"] == "app_title"]
        assert len(app_title_entries) == 8, f"Expected 8 app_title entries (2 catalogs × 4 locales), got {len(app_title_entries)}"

        # Verify distinct values preserved per catalog
        main_en = next(e for e in app_title_entries if "Main/Resources" in e["source"]["file"] and e["locale"] == "en")
        widget_en = next(e for e in app_title_entries if "Widget" in e["source"]["file"] and e["locale"] == "en")
        assert main_en["value"] == "Main App", f"Main value wrong: {main_en.get('value')}"
        assert widget_en["value"] == "Widget Title", f"Widget value wrong: {widget_en.get('value')}"

        # Verify stale state preserved
        widget_es = next(e for e in app_title_entries if "Widget" in e["source"]["file"] and e["locale"] == "es")
        assert widget_es["localization"]["stringUnit"]["state"] == "needs_review", "Stale state not preserved"

        # Verify plural variations preserved
        item_entries = [e for e in entries if e["key"] == "item_count"]
        en_items = next(e for e in item_entries if e["locale"] == "en")
        assert "variations" in en_items["localization"], "Plural variations missing"
        assert "plural" in en_items["localization"]["variations"], "Plural key missing"
        assert len(en_items["variants"]) >= 3, f"Expected at least 3 plural variants, got {len(en_items['variants'])}"

        # Verify localization sources with fingerprints
        assert "localization_sources" in inventory, "localization_sources missing"
        sources = inventory["localization_sources"]
        assert len(sources) == 2, f"Expected 2 localization sources, got {len(sources)}"
        for source in sources:
            assert "sha256" in source, "Source missing SHA256"
            assert len(source["sha256"]) == 64, "Invalid SHA256"
            assert source["format"] == "xcstrings", f"Wrong format: {source['format']}"

        # Verify fonts
        assert "fonts" in inventory, "fonts missing"
        fonts = inventory["fonts"]
        assert len(fonts) == 2, f"Expected 2 fonts, got {len(fonts)}"

        ttf_font = next(f for f in fonts if f["path"].endswith(".ttf"))
        assert ttf_font["family"] == "App Font", f"TTF family wrong: {ttf_font.get('family')}"
        assert ttf_font["resolved"] is True, "TTF should be resolved"
        assert len(ttf_font["sha256"]) == 64, "TTF missing valid SHA256"

        # Verify font registration
        assert "font_registrations" in inventory, "font_registrations missing"
        regs = inventory["font_registrations"]
        assert len(regs) == 1, f"Expected 1 registration, got {len(regs)}"
        assert len(regs[0]["fonts"]) == 2, "Should have 2 registered fonts"

        # Verify themes
        assert "themes" in inventory, "themes missing"
        themes = inventory["themes"]
        assert len(themes) == 1, f"Expected 1 theme, got {len(themes)}"
        theme_data = themes[0]
        assert len(theme_data["colors"]) >= 2, f"Expected at least 2 colors, got {len(theme_data['colors'])}"
        assert len(theme_data["spacing"]) >= 1, f"Expected at least 1 spacing, got {len(theme_data['spacing'])}"
        assert len(theme_data["fonts"]) >= 1, f"Expected at least 1 font, got {len(theme_data['fonts'])}"

        # Verify theme color adaptive detection
        colors = theme_data["colors"]
        adaptive = next((c for c in colors if c.get("is_adaptive")), None)
        assert adaptive is not None, "Should detect adaptive color"
        assert adaptive["resolved"] is False, "Theme colors should not be resolved"

        # Verify input hash includes all resources
        target_hash = payload["target_input_sha256"]
        assert len(target_hash) == 64, "Invalid target input hash"

        # Verify summary counts
        summary = inventory["summary"]
        assert summary["localization_entry_count"] == len(entries), "Entry count mismatch"
        assert summary["localization_source_count"] == 2, "Source count wrong"
        assert summary["font_count"] == 2, "Font count wrong"
        assert summary["font_resolved_count"] == 2, "Resolved font count wrong"
        assert summary["theme_file_count"] == 1, "Theme file count wrong"

        # Verify existing asset catalog preserved
        assert summary["catalog_count"] == 1, "Asset catalog missing"
        assert summary["images"] == 1, "Image count wrong"

        # Verify diagnostics included
        assert "diagnostics" in inventory, "diagnostics missing"

        print("✅ PASS: End-to-end resource integration")
        print(f"   Localization entries: {len(entries)}")
        print(f"   Localization sources: {len(sources)} catalogs")
        print(f"   Fonts: {len(fonts)} ({summary['font_resolved_count']} resolved)")
        print(f"   Font registrations: {len(regs)}")
        print(f"   Themes: {len(themes)}")
        print(f"   Theme colors: {len(theme_data['colors'])}")
        print(f"   Asset catalogs: {summary['catalog_count']}")
        print(f"   Target input SHA256: {target_hash[:16]}...")

        return 0


def test_input_hash_sensitivity():
    """Test that target_input_sha256 changes when resource files change."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)

        # Create initial resources
        (root / "Views/Home.swift").parent.mkdir(parents=True)
        (root / "Views/Home.swift").write_text("struct Home: View { }")

        loc = root / "en.lproj/Localizable.xcstrings"
        loc.parent.mkdir(parents=True)
        loc.write_text(json.dumps({
            "sourceLanguage": "en",
            "strings": {"key1": {"localizations": {"en": {"stringUnit": {"value": "Value 1"}}}}}
        }))

        font = root / "Font.ttf"
        font.write_bytes(create_synthetic_ttf("Test", "Test-Regular"))

        # First scan
        output1 = root / "out1.json"
        payload1 = run(str(root), str(output1))
        hash1 = payload1["target_input_sha256"]

        # Modify localization
        loc.write_text(json.dumps({
            "sourceLanguage": "en",
            "strings": {"key1": {"localizations": {"en": {"stringUnit": {"value": "Value 2"}}}}}  # Changed
        }))

        # Second scan
        output2 = root / "out2.json"
        payload2 = run(str(root), str(output2))
        hash2 = payload2["target_input_sha256"]

        assert hash1 != hash2, "Hash should change when localization changes"

        # Modify font
        font.write_bytes(create_synthetic_ttf("Test", "Test-Bold"))  # Different PostScript name

        # Third scan
        output3 = root / "out3.json"
        payload3 = run(str(root), str(output3))
        hash3 = payload3["target_input_sha256"]

        assert hash2 != hash3, "Hash should change when font changes"
        assert hash1 != hash3, "All hashes should be unique"

        # Modify Info.plist (UIAppFonts registration) — must affect hash
        info_plist = root / "Info.plist"
        import plistlib
        info_plist.write_bytes(plistlib.dumps({"UIAppFonts": ["Font.ttf", "NewFont.ttf"]}))

        output4 = root / "out4.json"
        payload4 = run(str(root), str(output4))
        hash4 = payload4["target_input_sha256"]

        assert hash3 != hash4, (
            "Hash must change when Info.plist UIAppFonts registration changes; "
            "plist bytes must be part of producer input hash"
        )

        print("✅ PASS: Input hash sensitivity")
        print(f"   Initial hash: {hash1[:16]}...")
        print(f"   After loc change: {hash2[:16]}...")
        print(f"   After font change: {hash3[:16]}...")
        print(f"   After plist registration change: {hash4[:16]}...")

        return 0


def test_module_provenance():
    """Verify all modules import from the canonical clean clone, not dirty repo."""
    import ui_evidence
    import ios_localizations
    import ios_fonts
    import ios_theme

    _REPO_ROOT = Path(__file__).resolve().parents[4]
    for module in [ui_evidence, ios_localizations, ios_fonts, ios_theme]:
        path = Path(module.__file__).resolve()
        assert path.is_relative_to(_REPO_ROOT), \
            f"{module.__name__} not from canonical clone: {path}"
        assert "ios2harmony/hmigbot-ios" not in str(path), \
            f"{module.__name__} from dirty repo: {path}"

    print("✅ PASS: Module provenance")
    print(f"   ui_evidence: {ui_evidence.__file__}")
    print(f"   ios_localizations: {ios_localizations.__file__}")
    print(f"   ios_fonts: {ios_fonts.__file__}")
    print(f"   ios_theme: {ios_theme.__file__}")

    return 0


if __name__ == "__main__":
    try:
        test_module_provenance()
        test_font_parsing_and_registration()
        test_theme_source_preservation()
        test_end_to_end_resource_integration()
        test_input_hash_sensitivity()

        print("\n✅ All resource fidelity tests passed")
        sys.exit(0)
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
