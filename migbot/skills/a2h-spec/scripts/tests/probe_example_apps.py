#!/usr/bin/env python3
"""Optional local E1/E5/E10–E15 probes. Outputs only into a caller-owned scratch directory.

These reviewed example models are fixtures, not a general Gradle resolver.
"""
import argparse
import json
from pathlib import Path
import re
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ui_facts as ui
from target_input import resolve_model, atomic_json, strip_comments, digest


def model(root, app):
    sets = []
    # Explicit, reviewed main source scopes for the three supplied repositories.
    module_dirs = sorted({p.parent for p in root.glob("**/build.gradle") if not any(
        v in p.relative_to(root).parts for v in ("build", ".gradle", ".git", "node_modules"))})
    module_dirs = [p for p in module_dirs if p != root / "app"] + [root / "app"]
    for priority, directory in enumerate(module_dirs):
        base = directory / "src/main"
        row = {"name": str(directory.relative_to(root)) + ":main", "priority": priority * 10,
               "source_dirs": [], "res_dirs": [], "asset_dirs": []}
        for key, names in (("source_dirs", ("java", "kotlin")), ("res_dirs", ("res", "platform-res")), ("asset_dirs", ("assets",))):
            row[key] = [str((base / n).relative_to(root)) for n in names if (base / n).is_dir()]
        if (base / "AndroidManifest.xml").is_file():
            row["manifest"] = str((base / "AndroidManifest.xml").relative_to(root))
        if any(row[k] for k in ("source_dirs", "res_dirs", "asset_dirs")) or row.get("manifest"):
            sets.append(row)
        if app == "antenna":
            free = directory / "src/free"
            selected = {"name": str(directory.relative_to(root)) + ":free", "priority": priority * 10 + 1,
                        "source_dirs": [], "res_dirs": [], "asset_dirs": []}
            for key, names in (("source_dirs", ("java", "kotlin")), ("res_dirs", ("res",)), ("asset_dirs", ("assets",))):
                selected[key] = [str((free / n).relative_to(root)) for n in names if (free / n).is_dir()]
            if any(selected[k] for k in ("source_dirs", "res_dirs", "asset_dirs")):
                sets.append(selected)
    if app == "weather":
        for name in ("java", "res"):
            if not (root / ("app/src/weather/" + name)).is_dir():
                raise ValueError("Weather fixture source root missing")
        sets.append({"name": "app:weatherpro", "priority": 10000,
                     "source_dirs": ["app/src/weather/java"], "res_dirs": ["app/src/weather/res"], "asset_dirs": []})
        flavors = {"app": "weatherpro", "abi": "abi64"}
    elif app == "aippt":
        flavors = {"brand": "deepaiqnppt"}
    else:
        flavors = {"market": "free"}
    variant = "".join(v[0].upper() + v[1:] for v in flavors.values()) + "Debug"
    variant = variant[0].lower() + variant[1:]
    symlinks = [{"path": str(p.resolve()), "sha256": digest(p)}
                for directory in module_dirs for p in (directory / "src/main/assets").glob("*")
                if p.is_symlink() and p.is_file()]
    return {"schema_version": 1, "ui_quality_policy": "fidelity-v1", "ui_facts_policy": "static-v1",
            "android_root": str(root), "resolution": "resolved",
            "target": {"module": "app", "variant": variant, "build_type": "debug",
                       "flavor_dimensions": list(flavors), "flavors": flavors},
            "source_sets": sets, "resolution_evidence": [{"source": "reviewed three-app regression fixture",
                         "note": "Weather app sourceSets remaps weatherpro to src/weather; AIPPT main includes platform-res"}],
            "allowed_symlink_targets": symlinks,
            "dependencies": ([{"group": "com.google.android.material", "artifact": "material", "version": "1.12.0",
                              "source": "AntennaPod/build.gradle googleMaterialVersion"}] if app == "antenna" else [])}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--examples-root", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()
    root, output = Path(args.examples_root), Path(args.output)
    cases = [
        ("aippt", root / "AIPPT_mock/AIPPT_mock_kit", [
            ("com.aipptzhizuozz.bjh.fragment.HomeFragment", "page_0001_HomeFragment"),
            ("com.aipptzhizuozz.bjh.page.HomeActivity", "page_0002_HomeActivity")]),
        ("weather", root / "app_hnaccurateweather_live_android", [
            ("com.cstools.weather.ui.main.MainActivity", "page_0001_MainActivity"),
            ("com.cstools.weather.ui.weather.fragment.NewWeatherFragment", "page_0002_NewWeatherFragment"),
            ("com.cstools.weather.ui.weatherdetail.activity.LifeDetailActivity", "page_0003_LifeDetailActivity")]),
        ("antenna", root / "AntennaPod", [
            ("de.danoeh.antennapod.activity.MainActivity", "page_0001_MainActivity"),
            ("de.danoeh.antennapod.ui.screen.home.HomeFragment", "page_0002_HomeFragment"),
            ("de.danoeh.antennapod.ui.preferences.screen.AutoDownloadPreferencesFragment", "page_0003_AutoDownloadPreferencesFragment")])]
    reports = []
    for name, source, pages in cases:
        fixture = output / name
        explicit = fixture / "reviewed-model.json"
        atomic_json(explicit, model(source, name))
        selection = resolve_model(source, resolved_input=explicit)
        if selection["resolution"] != "resolved":
            reports.append({"app": name, "status": "target-unresolved", "diagnostics": selection["diagnostics"]})
            continue
        target = fixture / "spec/.a2h/target-input.json"
        atomic_json(target, selection)
        preview_path = fixture / "preview.json"
        atomic_json(preview_path, {"theme_mode": "light", "api": 34, "width_dp": 393, "height_dp": 851,
                                  "smallest_width_dp": 393, "layout_direction": "ldltr"})
        pages_path = fixture / "pages.json"
        atomic_json(pages_path, [{"activity": f, "page_id": i, "priority": "P0",
            **({"theme": "@style/Theme.AntennaPod.Light.NoTitle",
                "theme_policy_ref": "Reviewed Light non-dynamic regression profile from source theme return table and preference defaults"}
               if name == "antenna" else {})} for f, i in pages])
        options = argparse.Namespace(policy="static-v1", target_input=str(target), project_root=str(fixture),
                                     preview_config=str(preview_path), gradle_cache=None, pages=str(pages_path), decisions=None)
        try:
            result = ui.prepare(options)
            row = {"app": name, "status": "prepared", "cold_ms": result["total_ms"], "pages": [],
                   "generated_snapshot_count": result["pages"], "cold_resource_cache_hit": result["resource_cache_hit"]}
            for _, page_id in pages:
                directory = fixture / "spec/baseline/ui-snapshots" / page_id
                visual = ui.read(directory / "visual.json")
                meta = ui.read(directory / "meta.json")
                checks = {"page": page_id, "nodes": len(visual["nodes"]),
                          "templates": [t["template_id"] for t in meta["recycler_item_templates"]],
                          "page_type": meta["page_type"], "theme": visual["page"]["theme"]["selected"],
                          "open": len(visual["unresolved_summary"]), "preferences": len(visual["preferences"])}
                if name == "antenna":
                    nav = next((n for n in visual["nodes"] if n["class"].endswith("BottomNavigationView")), None)
                    checks["nav_background"] = nav["props"].get("android:background") if nav else None
                if name == "weather":
                    values = ui.read(fixture / "spec/baseline/res-index/values.json")
                    checks["wrong_flavor_resources"] = sum(any("/" + f + "/" in r["source"]["file"] for f in ("safe", "lucky", "cloud"))
                                                         for r in values["resources"])
                    level = ui.read(fixture / "spec/baseline/res-index/drawables.json")["resources"].get("drawable/level_weather@", {})
                    checks["weather_level_items"] = len(level.get("items", []))
                    if page_id.endswith("MainActivity"):
                        assert meta["page_type"] == "full_screen_page"
                    if page_id.endswith("NewWeatherFragment"):
                        assert len([t for t in meta["recycler_item_templates"] if t["item_type"] is not None]) == 7, checks
                    if page_id.endswith("LifeDetailActivity"):
                        icons = [n for n in visual["nodes"] if n["props"].get("android:layout_width", {}).get("value") == 148]
                        assert icons and any(n["props"].get("android:layout_alignParentRight", {}).get("value") == "true" for n in icons)
                        assert any(n["props"].get("android:visibility", {}).get("value") == "invisible" for n in visual["nodes"])
                    assert checks["wrong_flavor_resources"] == 0 and checks["weather_level_items"] == 21
                if name == "aippt" and page_id.endswith("HomeFragment"):
                    assert "item_home_example" in checks["templates"]
                    from static_resource_index import ResourceIndex
                    index = ResourceIndex.load(selection, fixture / "spec/baseline/res-index")
                    radius = index.resolve("@dimen/dimen_main_btn_radius")
                    assert radius["value"] == 30 and radius["androidUnit"] == "dp", radius
                    checks["button_radius"] = radius
                    template = ui.read(directory / "templates/item_home_example.json")
                    shape = next(n for n in template["nodes"] if n["class"].endswith("ShapeLinearLayout"))
                    assert shape["props"]["app:shape_strokeColor"]["value"] == "#E6E3FF"
                    assert shape["props"]["app:shape_strokeSize"]["value"] == 1
                    tokens = ui.read(fixture / "spec/baseline/res-index/design-tokens.json")["tokens"]
                    assert not any(t["resource_id"] == "color/color_home_tab_bg" for t in tokens)
                if name == "antenna" and page_id.endswith("MainActivity"):
                    assert checks["nav_background"] and checks["nav_background"]["value"] == "#EBEEF3"
                    assert meta["page_type"] == "full_screen_page"
                    descriptors = ui.read(fixture / "spec/baseline/res-index/drawables.json")["resources"]
                    arrow = descriptors["drawable/ic_curved_arrow@"]
                    assert arrow["paints"][0]["fill"] is None and arrow["paints"][0]["stroke"] == "?attr/action_icon_color"
                    assert arrow["paints"][1]["fill"] == "?attr/action_icon_color"
                    assert descriptors["mipmap/ic_launcher@anydpi-v26"]["kind"] == "adaptive_icon"
                if name == "antenna" and "PreferencesFragment" in page_id:
                    assert visual["preferences"]
                row["pages"].append(checks)
            hot = ui.prepare(options)
            row["hot_ms"] = hot["total_ms"]
            row["resource_cache_hit"] = hot["resource_cache_hit"]
            reports.append(row)
        except Exception as exc:
            reports.append({"app": name, "status": "failed", "error": type(exc).__name__ + ": " + str(exc)})
    atomic_json(output / "example-probe-report.json", reports)
    print(json.dumps(reports, ensure_ascii=False, indent=2))
    return 0 if all(r["status"] == "prepared" for r in reports) else 2


if __name__ == "__main__":
    raise SystemExit(main())
