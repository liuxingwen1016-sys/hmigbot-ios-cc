"""Read the stable source acceptance criteria for one feature."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys


_PLAN_SCRIPTS = Path(__file__).resolve().parents[2] / "i2h-plan/scripts"
if str(_PLAN_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_PLAN_SCRIPTS))
from generate_execute_coverage import AC_RE, acceptance_checkboxes


def extract_acs(feature_file: Path, feature_id: str) -> list[dict]:
    if not re.fullmatch(r"F\d{3}", feature_id):
        raise ValueError("feature_id must be an exact Feature ID")
    path = Path(feature_file)
    rows = []
    seen = set()
    for line, checked, body in acceptance_checkboxes(path.read_text(encoding="utf-8-sig")):
        match = AC_RE.fullmatch(body)
        if not match or not match[1].startswith(feature_id + "-"):
            raise ValueError(f"{path}:{line}: expected a stable {feature_id} acceptance ID")
        source_id, text = match.groups()
        if source_id in seen:
            raise ValueError(f"{path}:{line}: duplicate acceptance ID {source_id}")
        seen.add(source_id)
        rows.append({"source_ac_id": source_id, "case_prefix": source_id.replace("-", "_"),
                     "checked": checked, "text": text, "line": line})
    if not rows:
        raise ValueError(f"no acceptance criteria in {path}")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feature-file", type=Path, required=True)
    parser.add_argument("--feature-id", required=True)
    args = parser.parse_args()
    try:
        rows = extract_acs(args.feature_file, args.feature_id)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"ac_inputs: {exc}\n")
    print(json.dumps(rows, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
