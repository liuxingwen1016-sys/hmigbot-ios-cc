from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import generate_execute_coverage as generator  # noqa: E402


class GenerateExecuteCoverageTest(unittest.TestCase):
    def test_derives_requirements_and_packet_digests_from_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            features = root / "spec/baseline/features"
            slices = root / "spec/baseline/plans/slices"
            slices.mkdir(parents=True)
            features.mkdir(parents=True)
            (features / "feat_001_demo.md").write_text(
                "# F001: Demo\n\n## 基本信息\n\n- **feature_id**: `F001`\n\n"
                "## 验收标准\n\n- [ ] F001-AC01 启动时展示首页\n"
                "- [x] F001-AC02 点击按钮保存数据\n",
                encoding="utf-8",
            )
            (slices / "slice-01-F001.md").write_text(
                "## Slice 1: Demo (F001)\nfeature_id: F001\n\n"
                "modifies_files:\n  - entry/src/main/ets/pages/Index.ets\n",
                encoding="utf-8",
            )
            requirements, coverage = generator.build(root)

            self.assertEqual([item["requirement_id"] for item in requirements["requirements"]], ["F001-AC01", "F001-AC02"])
            packet = coverage["packets"][0]
            self.assertEqual(packet["packet_id"], "slice-01-F001")
            self.assertEqual(packet["requirement_ids"], ["F001-AC01", "F001-AC02"])
            self.assertEqual(packet["files"], ["entry/src/main/ets/pages/Index.ets"])
            self.assertEqual(packet["requirement_digests"]["F001-AC01"], requirements["requirements"][0]["digest"])

    def test_fails_when_a_feature_has_no_slice(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            features = root / "spec/baseline/features"
            features.mkdir(parents=True)
            (features / "feat_001_demo.md").write_text(
                "# F001: Demo\n- **feature_id**: `F001`\n## 验收标准\n- [ ] F001-AC01 Do it\n",
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                generator.build(root)


if __name__ == "__main__":
    unittest.main()
