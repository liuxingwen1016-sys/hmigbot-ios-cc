"""Resolve feature specifications and the paths owned by each UT stage."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re


FEATURE_STEM = re.compile(r"(?:(?i:feat)_)?[Ff]?(\d{3})[-_]([^.]+)(?:\.(.+))?\Z")


def resolve_features(project_root: Path, scope: str | None = None) -> dict:
    root = Path(project_root).expanduser().resolve()
    source = root / "spec/baseline/features"
    requested = list(dict.fromkeys(item.strip() for item in scope.split(","))) if scope is not None else None
    if requested is not None and not all(re.fullmatch(r"F[0-9]+", item) for item in requested):
        raise ValueError("scope must contain comma-separated exact Feature IDs")
    mains = {}
    addenda = {}
    for path in sorted(source.glob("*.md")):
        match = FEATURE_STEM.fullmatch(path.stem)
        if not match:
            continue
        feature = f"F{match[1]}"
        if requested is not None and feature not in requested:
            continue
        (addenda if match[3] else mains).setdefault(feature, []).append(path)
    if requested is not None:
        missing = [key for key in requested if key not in mains]
        if missing:
            raise ValueError("Missing Feature specs: " + ", ".join(missing))
    if not mains:
        raise ValueError(f"No Feature specs in {source}")
    results = []
    ut = root / "spec/verify/ut"
    for feature in requested or sorted(mains):
        if len(mains[feature]) != 1:
            raise ValueError(f"Duplicate Feature {feature}: " + ", ".join(path.name for path in mains[feature]))
        main = mains[feature][0]
        supplements = addenda.get(feature, [])
        for path in supplements:
            if path.stem.split(".", 1)[0] != main.stem:
                raise ValueError(f"Addendum does not match {main.name}: {path.name}")
        short_name = FEATURE_STEM.fullmatch(main.stem)[2].replace("-", "_")
        stem = f"{feature}_{short_name}"
        results.append({
            "feature_id": feature,
            "feature_file": str(main),
            "addendum_files": list(map(str, supplements)),
            "oracle_file": str(ut / "android-oracle" / f"{stem}.md"),
            "design_file": str(ut / "ut-design" / f"{stem}.md"),
            "unimplemented_file": str(ut / "unimplemented" / f"{stem}.json"),
            "generation_file": str(ut / "generation" / f"{stem}.json"),
            "test_file": str(root / "entry/src/ohosTest/ets/test/ut" / f"{stem}.test.ets"),
        })
    return {"schema_version": 1, "project_root": str(root), "features": results}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--scope", help="comma-separated Feature IDs")
    args = parser.parse_args()
    try:
        result = resolve_features(args.project_root, args.scope)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"feature_inputs: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
