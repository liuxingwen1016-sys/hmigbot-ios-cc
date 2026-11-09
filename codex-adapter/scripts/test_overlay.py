#!/usr/bin/env python3
"""Overlay failure-mode tests for the hmigbot-ios Codex adapter.

The i2h source already carries the Codex-compatible stage markers, so the
repository-specific overlay is the dispatch convention banner. These tests
keep the structural overlay contract strict: every registered target must
exist, and a missing frontmatter anchor is a hard failure without mutation.
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
import sys
sys.path.insert(0, str(HERE))
import overlay as ovl  # noqa: E402

REPO = next(
    d for d in [HERE, *HERE.parents]
    if (d / "migbot" / "skills").is_dir()
)
TOUCHED = ("i2h-spec", "i2h-execute")
CTX = {"agent_names": {"hmos-builder", "i2h-migration-worker"}}


def fresh(tmp: Path) -> Path:
    if tmp.exists():
        shutil.rmtree(tmp)
    for name in TOUCHED:
        d = tmp / "skills" / name
        d.mkdir(parents=True)
        shutil.copy2(REPO / "migbot" / "skills" / name / "SKILL.md", d / "SKILL.md")
    (tmp / "agents").mkdir()
    return tmp


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="codex-overlay-test-"))
    try:
        overlays, _ = ovl.load()
        expected = sum(len(o.paths) for o in overlays)

        ok = fresh(root / "ok")
        result = ovl.apply_all(ok, CTX)
        assert len(result.applied) == expected and not result.errors, result.errors
        for name in TOUCHED:
            text = (ok / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
            assert "Codex subagent dispatch convention" in text
        print(f"① 正常路径      applied={len(result.applied)}/{expected} errors=0")

        drift = fresh(root / "drift")
        target = drift / "skills" / "i2h-spec" / "SKILL.md"
        original = target.read_text(encoding="utf-8")
        target.write_text(original.replace("---\n", "---\n", 1).replace("---\n", "", 1), encoding="utf-8")
        result = ovl.apply_all(drift, CTX)
        assert result.errors and "命中 0 次" in result.errors[0], result.errors
        assert target.read_text(encoding="utf-8") == original.replace("---\n", "---\n", 1).replace("---\n", "", 1)
        print("② frontmatter 漂移  errors=1（硬失败）且原文未被改动")

        missing = fresh(root / "missing")
        (missing / "skills" / "i2h-execute" / "SKILL.md").unlink()
        result = ovl.apply_all(missing, CTX)
        assert result.errors and "目标文件不存在" in result.errors[0], result.errors
        print("③ 目标缺失      errors=1（硬失败）")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    print("\n全部通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
