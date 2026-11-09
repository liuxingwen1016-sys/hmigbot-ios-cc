import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class OutputContractPromptTests(unittest.TestCase):
    def test_converter_prompt_requires_approved_output_paths(self):
        prompt = (ROOT / "references/agent-prompts/1-converter.md").read_text(encoding="utf-8")
        self.assertIn("output.file", prompt)
        self.assertIn("output.symbol", prompt)
        self.assertIn("RootView.ets", prompt)
        self.assertIn("Index.ets", prompt)

    def test_converter_prompt_covers_api26_modal_fallback_and_stepper_glyphs(self):
        prompt = (ROOT / "references/agent-prompts/1-converter.md").read_text(encoding="utf-8")
        self.assertIn("API 26", prompt)
        self.assertIn("自绘 overlay", prompt)
        self.assertIn("程序化关闭", prompt)
        self.assertIn("不要用容易被 ArkUI 字体裁剪的单字符 `+`/`-`", prompt)
        self.assertIn("增加和减少会改变正确的值", prompt)

    def test_converter_prompt_preserves_source_icon_assets(self):
        prompt = (ROOT / "references/agent-prompts/1-converter.md").read_text(encoding="utf-8")
        self.assertIn("图标和图片是 UI 事实", prompt)
        self.assertIn("禁止把有源资源或线稿图标降级为 emoji", prompt)
        self.assertIn("asset mapping", prompt)

    def test_skill_requires_output_contract_before_build(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("ui-delivery-approved.json", skill)
        self.assertIn("路径不一致时阻断执行", skill)


if __name__ == "__main__":
    unittest.main()
