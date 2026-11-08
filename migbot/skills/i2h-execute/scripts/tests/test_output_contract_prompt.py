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

    def test_skill_requires_output_contract_before_build(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("ui-delivery-approved.json", skill)
        self.assertIn("路径不一致时阻断执行", skill)


if __name__ == "__main__":
    unittest.main()
